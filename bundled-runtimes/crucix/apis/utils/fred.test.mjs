import assert from 'node:assert/strict';
import test from 'node:test';
import { briefing } from '../sources/fred.mjs';
import { sourceHealth, sourceOutcome } from './source-health.mjs';

const row = (date, value) => ({ date, value });
async function read(t, response) {
  t.mock.timers.enable({ apis: ['Date'], now: new Date('2026-11-14T12:00:00Z') });
  t.mock.method(globalThis, 'fetch', async url => response(new URL(url).searchParams.get('series_id'), new URL(url)));
  return briefing('synthetic-key');
}
const indicator = (data, id = 'DFF') => data.indicators.find(r => r.id === id);

test('partial FRED coverage uses all requested series, not only successful rows', async t => {
  const data = await read(t, id => id === 'DFF'
    ? Response.json({ observations: [row('2026-11-13', '4.25')] }) : new Response('', { status: 403 }));
  assert.equal(data.indicators.length, 21);
  assert.equal(indicator(data).value, 4.25);
  assert.equal(data.coverage.requested, 21);
  assert.equal(data.coverage.succeeded, 1);
  assert.equal(data.coverage.failed, 20);
  assert.equal(sourceOutcome('FRED', data).status, 'partial');
  assert.match(sourceOutcome('FRED', data).reason, /1\/21/);
  assert.match(sourceOutcome('FRED', data).reason, /403/);
});

test('all HTTP failures stay errors and never copy keys or private diagnostics', async t => {
  let calls = 0;
  const data = await read(t, () => { calls++; return new Response('private diagnostic', { status: 403 }); });
  assert.equal(calls, 21);
  assert.equal(data.coverage.failed, 21);
  assert.equal(indicator(data).httpStatus, 403);
  assert.equal(indicator(data).errorCode, 'HTTP_ERROR');
  assert.equal(sourceOutcome('FRED', data).status, 'error');
  assert.doesNotMatch(JSON.stringify(data), /synthetic-key|private diagnostic|api_key=/);
});

test('provider rejection and malformed payloads are not valid empty series', async t => {
  const data = await read(t, id => id === 'DFF'
    ? Response.json({ error_code: 400, error_message: 'private token detail' }) : Response.json({ rawText: 'private' }));
  assert.equal(indicator(data).errorCode, 'PROVIDER_ERROR');
  assert.equal(indicator(data, 'DGS2').errorCode, 'INVALID_RESPONSE');
  assert.equal(data.coverage.failed, 21);
  assert.equal(data.signals.length, 0);
  assert.doesNotMatch(JSON.stringify(data), /private/);
});

test('empty observations are distinct from request failure and zero observations survive', async t => {
  const data = await read(t, id => Response.json({ observations: id === 'DFF' ? [row('2026-11-13', '0')] : [] }));
  assert.equal(indicator(data).value, 0);
  assert.equal(data.coverage.empty, 20);
  assert.equal(data.coverage.failed, 0);
  assert.equal(indicator(data, 'DGS2').status, 'no_data');
  assert.equal(sourceOutcome('FRED', data).status, 'partial');
});

test('valid all-empty responses do not masquerade as a healthy source', async t => {
  const data = await read(t, () => Response.json({ observations: [] }));
  assert.equal(data.coverage.empty, 21);
  assert.equal(data.status, 'no_data');
  assert.equal(sourceOutcome('FRED', data).status, 'unknown');
});

test('dates are checked and sorted, future or out-of-query rows cannot become latest signals', async t => {
  const data = await read(t, (_id, url) => {
    assert.equal(url.searchParams.get('observation_end'), '2026-11-14');
    assert.equal(url.searchParams.get('limit'), '5');
    return Response.json({ observations: [row('2026-11-11', '2'), row('2099-01-01', '999'),
      row('2026-02-30', '999'), row('2020-01-01', '999'), row('2026-11-13', '0')] });
  });
  assert.equal(indicator(data).value, 0);
  assert.equal(indicator(data).date, '2026-11-13');
  assert.deepEqual(indicator(data).recent, [0, 2]);
  assert.equal(data.status, 'partial');
  assert.deepEqual(data.signals, []);
});

test('holiday dot may use a prior value but a malformed latest observation cannot', async t => {
  const data = await read(t, id => Response.json({ observations: [
    row('2026-11-14', id === 'DFF' ? '.' : '30oops'), row('2026-11-13', '10'),
  ] }));
  assert.equal(indicator(data).value, 10);
  assert.equal(indicator(data).date, '2026-11-13');
  assert.equal(indicator(data, 'VIXCLS').value, null);
  assert.equal(indicator(data, 'VIXCLS').date, '2026-11-14');
  assert.deepEqual(data.signals, []);
});

test('same-date conflicts do not pick an arbitrary value or silently use older data', async t => {
  const data = await read(t, () => Response.json({ observations: [
    row('2026-11-13', '-1'), row('2026-11-13', '1'), row('2026-11-12', '-2'),
  ] }));
  assert.equal(indicator(data, 'T10Y2Y').value, null);
  assert.deepEqual(data.signals, []);
  assert.equal(sourceOutcome('FRED', data).status, 'error');
});

test('identical repeats collapse and legitimate negative spreads retain their dated signal', async t => {
  const data = await read(t, () => Response.json({ observations: [
    row('2026-11-13', '-0.25'), row('2026-11-13', '-0.25'), row('2026-11-12', '0'),
  ] }));
  assert.equal(indicator(data, 'T10Y2Y').value, -0.25);
  assert.deepEqual(indicator(data, 'T10Y2Y').recent, [-0.25, 0]);
  assert.equal(data.coverage.succeeded, 21);
  assert.equal(sourceOutcome('FRED', data).status, 'ok');
  assert.equal(data.signals.length, 2);
});

test('legacy timing cannot certify complete FRED coverage without a collection receipt', () => {
  const old = { indicators: [{ id: 'DFF', value: 4 }] };
  assert.equal(sourceOutcome('FRED', old).status, 'unknown');
  const result = sourceHealth({ sources: { FRED: old }, timing: { FRED: { status: 'ok', reason: 'old success' } } });
  assert.equal(result.health[0].status, 'unknown');
});

test('missing key does not make any request', async t => {
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => { calls++; throw new Error('must not connect'); });
  assert.equal(sourceOutcome('FRED', await briefing('')).status, 'error');
  assert.equal(calls, 0);
});
