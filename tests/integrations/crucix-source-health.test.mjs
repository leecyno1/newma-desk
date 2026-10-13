import assert from 'node:assert/strict';
import test from 'node:test';
import { sourceOutcome, sourceHealth } from '../../bundled-runtimes/crucix/apis/utils/source-health.mjs';
import { runSource } from '../../bundled-runtimes/crucix/apis/briefing.mjs';
import { collect } from '../../bundled-runtimes/crucix/apis/sources/yfinance.mjs';
import { briefing as weather } from '../../bundled-runtimes/crucix/apis/sources/noaa.mjs';

test('resolved errors and credential placeholders never count as successful collection', async () => {
  for (const data of [{ error: 'No FRED API key' }, { status: 'no_credentials' }, { status: 'no_key' }, { error: 'Provider error' }]) {
    const result = await runSource('test-source', async () => data);
    assert.equal(result.status, 'error');
    assert.deepEqual(result.data, data);
  }
  const failure = await runSource('failed', async () => { throw new Error('https://provider?api_key=secret'); });
  assert.equal(failure.status, 'error');
  assert.ok(!JSON.stringify(failure).includes('secret'));
});

test('old snapshots include timed-out sources and recompute one consistent set of counts', () => {
  const result = sourceHealth({
    sources: { good: { events: [] }, FRED: { error: 'No FRED API key' }, old: { stale: true },
      Maritime: { status: 'ready' }, YFinance: { summary: { totalSymbols: 2, ok: 2 }, quotes: { valid: { price: 0 }, invalid: { price: null } } } },
    errors: [{ name: 'timed-out', error: 'timeout' }], timing: { 'timed-out': { status: 'error' } },
  });
  assert.deepEqual(result.counts, { sourcesQueried: 6, sourcesOk: 1, sourcesFailed: 2, sourcesPartial: 1, sourcesStale: 1, sourcesUnknown: 1 });
  assert.ok(result.health.some(row => row.n === 'timed-out' && row.status === 'error'));
  assert.equal(result.health.find(row => row.n === 'good').status, 'ok');
});

test('partial source results preserve useful records without marking all observations stale', () => {
  assert.equal(sourceOutcome('OpenSky', { error: 'one hotspot failed', hotspots: [{ error: 'failed' }, { aircraft: [] }] }).status, 'partial');
  assert.equal(sourceOutcome('EIA', { oilPrices: { wti: { value: 0 } }, gaps: { brent: 'missing' } }).status, 'partial');
  assert.equal(sourceOutcome('ReliefWeb', { rwError: '403', hdxDatasets: [{ title: 'Data' }] }).status, 'partial');
  assert.equal(sourceOutcome('WHO', { outbreakError: 'failed', diseaseOutbreakNews: [] }).status, 'error');
  assert.equal(sourceOutcome('Safecast', { sites: [{ avgCPM: null }] }).status, 'error');
  assert.equal(sourceOutcome('FRED', { indicators: [] }).status, 'error');
});

test('Yahoo failures retain each symbol, exclude invalid numbers and do not become zero-valued market rows', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ chart: { result: [{ meta: {}, indicators: { quote: [{}] } }] } })));
  const result = await collect();
  assert.equal(result.summary.ok, 0);
  assert.equal(Object.keys(result.quotes).length, result.summary.totalSymbols);
  assert.ok(result.quotes['CL=F'].error);
  assert.deepEqual(result.indexes, []);
  assert.deepEqual(result.commodities, []);
  assert.equal(sourceOutcome('YFinance', result).status, 'error');
});

test('zero weather alerts are valid only when the source returned a real feature collection', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ features: [] })));
  const empty = await weather();
  assert.equal(empty.totalSevereAlerts, 0);
  assert.equal(sourceOutcome('NOAA', empty).status, 'ok');
  mock.mock.mockImplementation(async () => new Response(JSON.stringify({ error: 'upstream unavailable' })));
  const failed = await weather();
  assert.ok(failed.error);
  assert.equal(failed.totalSevereAlerts, undefined);
  assert.equal(sourceOutcome('NOAA', failed).status, 'error');
});
