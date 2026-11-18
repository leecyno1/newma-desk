import assert from 'node:assert/strict';
import test from 'node:test';
import { collect } from '../sources/yfinance.mjs';
import { sourceOutcome } from './source-health.mjs';

const epoch = value => Date.parse(value) / 1000;
const current = epoch('2026-10-26T20:00:00Z');
const previous = epoch('2026-10-23T13:30:00Z');
function chart(meta = {}, close = [100, 110], timestamp = [previous, current]) {
  return { chart: { result: [{ meta: {
    regularMarketPrice: 110, regularMarketTime: current,
    chartPreviousClose: 80, exchangeTimezoneName: 'America/New_York', ...meta,
  }, timestamp, indicators: { quote: [{ close }] } }] } };
}
async function quote(t, payload) {
  t.mock.method(globalThis, 'fetch', async () => Response.json(payload));
  return (await collect()).quotes.TLT;
}

test('HTTP rejection retains safe status and does not become an empty quote', async (t) => {
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => {
    calls++;
    return new Response('private upstream diagnostic', { status: 403 });
  });
  const data = await collect();
  assert.equal(data.quotes.TLT.httpStatus, 403);
  assert.equal(data.quotes.TLT.errorCode, 'HTTP_ERROR');
  assert.equal(calls, 15);
  assert.equal(sourceOutcome('YFinance', data).status, 'error');
  assert.match(sourceOutcome('YFinance', data).reason, /403/);
  assert.equal(data.summary.ok, 0);
  assert.doesNotMatch(JSON.stringify(data), /private upstream/);
});

test('daily change uses prior session close, never the five-day chart baseline', async (t) => {
  const q = await quote(t, chart());
  assert.equal(q.prevClose, 100);
  assert.equal(q.change, 10);
  assert.equal(q.changePct, 10);
  assert.equal(q.previousCloseBasis, 'daily-bars');
  assert.equal(q.observedAt, '2026-10-26T20:00:00.000Z');
});

test('explicit previous close takes priority and an unchanged price stays zero', async (t) => {
  const q = await quote(t, chart({ previousClose: 110 }));
  assert.equal(q.prevClose, 110);
  assert.equal(q.changePct, 0);
  assert.equal(q.previousCloseBasis, 'provider');
});

test('missing or misaligned previous session remains unknown, not flat', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => Response.json(chart({}, [null, 110])));
  for (const payload of [chart({}, [null, 110]), chart({}, [100], [previous]), chart({ exchangeTimezoneName: null })]) {
    mock.mock.mockImplementation(async () => Response.json(payload));
    const q = (await collect()).quotes.TLT;
    assert.equal(q.price, 110);
    assert.equal(q.prevClose, null);
    assert.equal(q.change, null);
    assert.equal(q.changePct, null);
    assert.equal(q.currency, null);
  }
});

test('history uses exchange calendar date and does not skip a missing prior bar', async (t) => {
  const q = await quote(t, chart({
    regularMarketTime: epoch('2026-10-26T01:00:00Z'), exchangeTimezoneName: 'America/Los_Angeles',
  }, [90, null, 110], [epoch('2026-10-24T01:00:00Z'), epoch('2026-10-25T01:00:00Z'), epoch('2026-10-26T01:00:00Z')]));
  assert.equal(q.history.at(-1).date, '2026-10-25');
  assert.equal(q.changePct, null);
});

test('malformed/provider errors remain distinct without leaking response text', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => new Response('<html>private</html>'));
  const invalid = await collect();
  assert.equal(invalid.quotes.TLT.errorCode, 'INVALID_RESPONSE');
  mock.mock.mockImplementation(async () => Response.json({ chart: { error: { description: 'private' } } }));
  const failed = await collect();
  assert.equal(failed.quotes.TLT.errorCode, 'PROVIDER_ERROR');
  assert.doesNotMatch(JSON.stringify([invalid, failed]), /private/);
});

test('partial symbol failures retain valid quotes and honest coverage', async (t) => {
  t.mock.method(globalThis, 'fetch', async url => String(url).includes('/TLT?')
    ? Response.json(chart()) : new Response('', { status: 403 }));
  const data = await collect();
  assert.equal(data.summary.ok, 1);
  assert.equal(data.summary.failed, 14);
  assert.equal(data.rates.length, 1);
  assert.equal(sourceOutcome('YFinance', data).status, 'partial');
});
