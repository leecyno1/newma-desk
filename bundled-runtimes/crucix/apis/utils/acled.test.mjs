import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { summarizeEvents } from '../sources/acled.mjs';
import { synthesize, generateIdeas } from '../../dashboard/inject.mjs';
import { sourceHealth } from './source-health.mjs';

const period = { start: '2026-10-21', end: '2026-10-27' };
const event = (id = 'sample-1', fatalities = '0') => ({ event_id_cnty: id, event_date: period.end,
  fatalities, latitude: '0', longitude: '0', country: 'Example', region: 'Example region', event_type: 'Battles' });
let instance = 0;
async function source(t, enabled = true) {
  const previous = [process.env.ACLED_EMAIL, process.env.ACLED_PASSWORD];
  process.env.ACLED_EMAIL = enabled ? 'synthetic@example.invalid' : '';
  process.env.ACLED_PASSWORD = enabled ? 'test-secret-only' : '';
  t.after(() => ['ACLED_EMAIL', 'ACLED_PASSWORD'].forEach((key, i) => {
    if (previous[i] === undefined) delete process.env[key]; else process.env[key] = previous[i];
  }));
  return import(`../sources/acled.mjs?unit=${++instance}`);
}

test('missing credentials cause no request and survive synthesis as unknown counts', async t => {
  const api = await source(t, false);
  const mock = t.mock.method(globalThis, 'fetch', () => { throw new Error('unexpected request'); });
  const result = await api.briefing();
  assert.equal(mock.mock.callCount(), 0);
  assert.equal(result.status, 'no_credentials');
  assert.equal(result.totalEvents, null);
  const payload = await synthesize({ sources: { ACLED: result } }, { refreshNews: false });
  assert.equal(payload.acled.totalEvents, null);
  assert.equal(payload.acled.totalFatalities, null);
  assert.match(payload.health[0].reason, /未知/);
});

test('OAuth has documented scope, uses actual expiry and never logs credentials in debug mode', async t => {
  const api = await source(t);
  let now = 100000, logins = 0;
  t.mock.method(Date, 'now', () => now);
  const log = t.mock.method(console, 'error', () => {});
  const debug = process.argv.includes('--debug');
  if (!debug) process.argv.push('--debug');
  t.after(() => { if (!debug) process.argv.splice(process.argv.indexOf('--debug'), 1); });
  t.mock.method(globalThis, 'fetch', async (url, opts) => {
    assert.equal(opts.redirect, 'error');
    if (String(url).endsWith('/oauth/token')) {
      logins++;
      const params = new URLSearchParams(opts.body);
      assert.equal(params.get('scope'), 'authenticated');
      assert.equal(params.get('client_id'), 'acled');
      return Response.json({ access_token: 'synthetic-token', token_type: 'Bearer', expires_in: 120 });
    }
    assert.equal(opts.headers.Authorization, 'Bearer synthetic-token');
    assert.equal(opts.headers.Cookie, undefined);
    return Response.json({ status: 200, data: [] });
  });
  await api.getEvents(); await api.getEvents(); assert.equal(logins, 1);
  now += 61000; await api.getEvents(); assert.equal(logins, 2);
  assert.equal(log.mock.callCount(), 0);
});

test('failed OAuth never silently tries cookie login or returns an upstream body', async t => {
  const api = await source(t);
  const mock = t.mock.method(globalThis, 'fetch', async url => {
    assert.ok(String(url).endsWith('/oauth/token'));
    return new Response('private-token test-secret-only', { status: 401 });
  });
  const result = await api.briefing();
  assert.equal(mock.mock.callCount(), 1);
  assert.equal(result.status, 'error');
  assert.equal(result.httpStatus, 401);
  assert.equal(result.totalEvents, null);
  assert.doesNotMatch(JSON.stringify(result), /private-token|test-secret-only/);
});

test('data denial invalidates the token without retrying; malformed envelopes never mean no events', async t => {
  const api = await source(t);
  let logins = 0;
  t.mock.method(globalThis, 'fetch', async url => {
    if (String(url).endsWith('/oauth/token')) { logins++; return Response.json({ access_token: 'synthetic', expires_in: 86400 }); }
    return new Response('private reason', { status: 403 });
  });
  const denied = await api.briefing();
  assert.equal(denied.httpStatus, 403); assert.equal(logins, 1);
  await api.briefing(); assert.equal(logins, 2);
  for (const bad of [{}, { data: {} }, { error: 'error' }]) {
    const result = summarizeEvents(bad, period);
    assert.equal(result.status, 'error'); assert.equal(result.totalEvents, null);
  }
});

test('true zero survives while sample limit, missing fatalities and duplicate records stay explicit', () => {
  const empty = summarizeEvents({ data: [] }, period);
  assert.equal(empty.status, 'ok'); assert.equal(empty.totalEvents, 0); assert.equal(empty.totalFatalities, 0);
  const partial = summarizeEvents({ data: [event('a', '0'), event('a', '0'), event('b', ''),
    { ...event('c'), event_date: '2026-10-01' }, null] }, period, 5);
  assert.equal(partial.status, 'partial'); assert.equal(partial.totalEvents, 2); assert.equal(partial.totalFatalities, null);
  assert.deepEqual(partial.coverage, { returned: 5, accepted: 2, invalid: 2, duplicates: 1, unknownFatalities: 1, truncated: true });
  assert.equal(partial.byRegion['Example region'].count, 2);
  assert.equal(partial.byRegion['Example region'].fatalities, null);
});

test('event identities, original dates and zero coordinates survive synthesis; invalid coordinates do not plot', async () => {
  const result = summarizeEvents({ data: [event('zero-coordinates', 3), { ...event('bad-coordinates', 2), latitude: '91', longitude: '' }] }, period);
  const payload = await synthesize({ sources: { ACLED: result } }, { refreshNews: false });
  assert.equal(payload.acled.deadliestEvents[0].id, 'zero-coordinates');
  assert.equal(payload.acled.deadliestEvents[0].lat, 0); assert.equal(payload.acled.deadliestEvents[0].lon, 0);
  assert.equal(payload.acled.deadliestEvents[0].date, period.end);
  assert.equal(payload.acled.deadliestEvents[1].lat, null); assert.equal(payload.acled.deadliestEvents[1].lon, null);
  assert.equal(payload.acled.totalFatalities, 5);
  assert.doesNotMatch(JSON.stringify(generateIdeas(payload)), /Conflict Fueling|Defense Procurement/);
});

test('legacy fake zero is unknown even if the old timing said success', async () => {
  const old = { sources: { ACLED: { totalEvents: 0, totalFatalities: 0 } }, timing: { ACLED: { status: 'ok', reason: '采集完成' } } };
  assert.equal(sourceHealth(old).health[0].status, 'unknown');
  assert.equal((await synthesize(old, { refreshNews: false })).acled.totalEvents, null);
});

test('actual dashboard count formatter distinguishes unknown from true zero', () => {
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const fn = html.match(/function acledCountText\(field\)\{[\s\S]*?\n\}/)[0];
  for (const [acled, expected] of [[{}, '—'], [{ totalEvents: 0 }, '—'],
    [{ status: 'ok', basis: 'bounded-event-sample', totalEvents: 0 }, '0']]) {
    const render = vm.runInNewContext(`${fn}; acledCountText`, { D: { acled } });
    assert.equal(render('totalEvents'), expected);
  }
});
