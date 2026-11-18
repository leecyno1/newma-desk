import assert from 'node:assert/strict';
import test from 'node:test';
import { briefing, getSeriesV1 } from '../sources/bls.mjs';
import { sourceOutcome } from './source-health.mjs';

const row = (year, period, value) => ({ year: String(year), period, value: String(value) });
const series = (seriesID, data) => ({ seriesID, data });
async function read(t, rows) {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ status: 'REQUEST_SUCCEEDED', Results: { series: rows } }));
  return briefing();
}

test('BLS HTTP failure is distinct and never leaks HTML or response details', async t => {
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => { calls++; return new Response('private denial page', { status: 403 }); });
  const result = await briefing();
  assert.equal(result.httpStatus, 403);
  assert.equal(result.errorCode, 'HTTP_ERROR');
  assert.equal(calls, 1);
  assert.match(sourceOutcome('BLS', result).reason, /403/);
  assert.doesNotMatch(JSON.stringify(result), /private denial/);
});

test('BLS malformed JSON and provider errors are safe and distinguishable', async t => {
  const mock = t.mock.method(globalThis, 'fetch', async () => new Response('<private>'));
  assert.equal((await briefing()).errorCode, 'INVALID_RESPONSE');
  mock.mock.mockImplementation(async () => Response.json({ status: 'REQUEST_NOT_PROCESSED', message: ['private diagnostic'] }));
  const result = await briefing();
  assert.equal(result.errorCode, 'PROVIDER_ERROR');
  assert.doesNotMatch(JSON.stringify(result), /private/);
});

test('annual averages and quarters never replace a monthly observation', async t => {
  const result = await read(t, [series('CUUR0000SA0', [
    row(2025, 'M13', 999), row(2025, 'Q05', 888), row(2025, 'M12', 110),
    row(2025, 'M11', 100), row(2024, 'M12', 100),
  ])]);
  const cpi = result.indicators[0];
  assert.equal(cpi.value, 110);
  assert.equal(cpi.date, '2025-12');
  assert.equal(cpi.momChangePct, 10);
  assert.equal(cpi.yoyChangePct, 10);
  assert.equal(cpi.seasonalAdjustment, 'not-seasonally-adjusted');
  assert.equal(cpi.unit, 'index');
  assert.equal(result.indicators.length, 5);
  assert.deepEqual(result.coverage, { requested: 5, succeeded: 1, failed: 4 });
  assert.equal(sourceOutcome('BLS', result).status, 'partial');
  assert.ok(!result.signals.some(s => /MoM jump|MoM rising/.test(s)));
});

test('missing months are not bridged and newest missing values are not backfilled', async t => {
  const result = await read(t, [
    series('CUUR0000SA0', [row(2026, 'M09', 110), row(2026, 'M07', 100)]),
    series('LNS14000000', [row(2026, 'M09', '-'), row(2026, 'M08', 4.2)]),
  ]);
  assert.equal(result.indicators[0].momChangePct, null);
  const ue = result.indicators.find(s => s.id === 'LNS14000000');
  assert.equal(ue.value, null);
  assert.equal(ue.date, '2026-09');
  assert.equal(ue.momChange, null);
});

test('December-January comparison works and unemployment change is percentage points', async t => {
  const result = await read(t, [series('LNS14000000', [row(2026, 'M01', 4.2), row(2025, 'M12', 4.0)])]);
  const ue = result.indicators.find(s => s.id === 'LNS14000000');
  assert.equal(ue.momChange, 0.2);
  assert.equal(ue.changeUnit, 'percentage-points');
  assert.equal(ue.seasonalAdjustment, 'seasonally-adjusted');
});

test('zero is a valid observation but a zero denominator has no percentage change', async t => {
  const result = await read(t, [series('CES0000000001', [row(2026, 'M09', 0), row(2026, 'M08', 0)])]);
  const payrolls = result.indicators.find(s => s.id === 'CES0000000001');
  assert.equal(payrolls.value, 0);
  assert.equal(payrolls.momChange, 0);
  assert.equal(payrolls.momChangePct, null);
});

test('malformed rows and nonnumeric values cannot count as available series', async t => {
  const result = await read(t, [null, series('unrequested', [row(2026, 'M09', 100)]),
    series('CUUR0000SA0', [null, row(2026, 'M09', '123oops'), row(2026, 'M00', 1)])]);
  assert.equal(result.indicators[0].value, null);
  assert.equal(result.indicators.length, 5);
  assert.equal(result.coverage.succeeded, 0);
  assert.equal(sourceOutcome('BLS', result).status, 'error');
});

test('single-series URL has exactly one separator and encodes the series identifier', async t => {
  let requested;
  t.mock.method(globalThis, 'fetch', async url => { requested = String(url); return Response.json({}); });
  await getSeriesV1('LNS14000000');
  assert.equal(new URL(requested).pathname, '/publicAPI/v1/timeseries/data/LNS14000000');
});
