import assert from 'node:assert/strict';
import test from 'node:test';
import { energySnapshot } from '../../bundled-runtimes/crucix/dashboard/energy.mjs';
import { collect } from '../../bundled-runtimes/crucix/apis/sources/yfinance.mjs';
import { briefing } from '../../bundled-runtimes/crucix/apis/sources/eia.mjs';
import { parseSpotCsv, parseStocksCsv } from '../../bundled-runtimes/crucix/apis/sources/eia-public.mjs';

const stocksCsv = '"STUB_1","8/28/26","8/21/26","Difference","8/29/25","Percent Change"\r\n'
  + '"Crude Oil","711.064","718.636","-7.572","825.417","-13.900"\r\n'
  + '"Commercial (Excluding SPR)","424.460","428.910","-4.450","420.707","0.900"\r\n';

test('public CSV parsers skip missing/invalid prices and select commercial stock levels, not changes', () => {
  assert.deepEqual(parseSpotCsv('observation_date,DCOILWTICO\n2026-09-02,\n2026-09-01,91.48\n2026-08-31,.\n2026-08-30,0\n2026-08-29,-37\n2026-02-30,99', 'DCOILWTICO'), [
    { period: '2026-09-01', value: 91.48 }, { period: '2026-08-30', value: 0 }, { period: '2026-08-29', value: -37 },
  ]);
  assert.deepEqual(parseSpotCsv('observation_date,DCOILBRENTEU\n2026-09-01,91', 'DCOILWTICO'), []);
  assert.deepEqual(parseStocksCsv(stocksCsv), [
    { period: '2026-08-28', value: 424460 }, { period: '2026-08-21', value: 428910 },
  ]);
  assert.deepEqual(parseStocksCsv(stocksCsv.replace('Commercial (Excluding SPR)', 'SPR')), []);
  assert.deepEqual(parseStocksCsv(stocksCsv.replace('"424.460"', '""')), [{ period: '2026-08-21', value: 428910 }]);
});

test('no-key collection uses public spot/inventory sources and keeps provenance through the dashboard', async (t) => {
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (input) => {
    const url = new URL(input);
    requests.push(url);
    return new Response(url.hostname === 'ir.eia.gov' ? stocksCsv
      : `observation_date,${url.searchParams.get('id')}\n2026-09-01,91.48\n2026-09-02,`);
  });
  const data = await briefing();
  assert.equal(requests.length, 4);
  assert.ok(requests.every(url => !url.searchParams.has('api_key')));
  assert.ok(requests.filter(url => url.hostname === 'fred.stlouisfed.org').every(url => url.searchParams.has('cosd')));
  assert.deepEqual(data.gaps, {});
  assert.equal(data.inventories.crudeStocks.value, 424460);
  const snapshot = energySnapshot(data);
  assert.equal(snapshot.observations[0].kind, 'spot');
  assert.equal(snapshot.observations[0].period, '2026-09-01');
  assert.equal(snapshot.observations[0].source.id, 'FRED-public');
  assert.equal(snapshot.observations[0].source.originalSeriesId, 'RWTC');
  assert.equal(snapshot.observations[0].source.seriesId, 'DCOILWTICO');
  assert.match(snapshot.observations[0].source.fallbackReason, /未配置 EIA/);
  assert.equal(snapshot.observations[3].source.url, 'https://ir.eia.gov/wpsr/table4.csv');
  assert.match(snapshot.observations[3].note, /百万桶 × 1000/);
});

test('only missing API series fall back, and different observation dates never produce a spread', async (t) => {
  const fallbackIds = [];
  t.mock.method(globalThis, 'fetch', async (input) => {
    const url = new URL(input);
    if (url.hostname === 'api.eia.gov') {
      const series = url.searchParams.get('facets[series][]');
      const rows = series === 'RBRTE' ? [] : [{ period: '2026-09-09', value: '' },
        { period: '2026-09-08', value: series === 'WCESTUS1' ? '424460' : '70' }];
      return new Response(JSON.stringify({ response: { data: rows } }));
    }
    fallbackIds.push(url.searchParams.get('id'));
    return new Response('observation_date,DCOILBRENTEU\n2026-09-01,96.02');
  });
  const data = await briefing('test-key');
  assert.deepEqual(fallbackIds, ['DCOILBRENTEU']);
  assert.equal(data.oilPrices.wti.value, 70);
  assert.equal(data.oilPrices.wti.period, '2026-09-08');
  assert.equal(data.oilPrices.spread, null);
  assert.ok(!data.signals.some(signal => signal.includes('spread')));
  assert.match(data.oilPrices.brent.source.fallbackReason, /未返回有效观测/);
});

test('a failed fallback leaves an explicit per-series gap and never zero or a credential-bearing error', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new Error('request failed api_key=private-test-key'); });
  const data = await briefing('private-test-key');
  assert.ok(data.error);
  assert.equal(Object.keys(data.gaps).length, 4);
  assert.equal(data.oilPrices.wti, null);
  assert.equal(data.inventories.crudeStocks, null);
  assert.ok(!JSON.stringify(data).includes('private-test-key'));
  const observation = energySnapshot(data).observations[0];
  assert.equal(observation.value, null);
  assert.match(observation.note, /备用来源暂不可用/);
});

test('keeps Yahoo futures value, unit and quote time together instead of retaining the EIA spot label', () => {
  const result = energySnapshot({ oilPrices: { wti: { value: 70, period: '2026-09-08', recent: [{ value: 70 }] } } }, {
    'CL=F': { price: 72, currency: 'USD', observedAt: '2026-09-09T18:00:00Z', history: [{ close: 71 }] },
  });
  assert.equal(result.wti, 72);
  assert.deepEqual(result.wtiRecent, [71]);
  assert.equal(result.observations[0].kind, 'futures');
  assert.equal(result.observations[0].source.seriesId, 'CL=F');
  assert.equal(result.observations[0].period, null);
  assert.equal(result.observations[0].observedAt, '2026-09-09T18:00:00Z');
  assert.equal(result.observations[0].unit, '美元/桶');
});

test('retains EIA data periods and inventory units when Yahoo is unavailable', () => {
  const result = energySnapshot({
    oilPrices: { wti: { value: -37, period: '2026-09-08' } },
    inventories: { crudeStocks: { value: 420000, period: '2026-09-04' } },
  }, { 'CL=F': { price: null } });
  assert.equal(result.wti, -37);
  assert.equal(result.observations[0].kind, 'spot');
  assert.equal(result.observations[0].source.seriesId, 'RWTC');
  assert.equal(result.observations[3].value, 420000);
  assert.equal(result.observations[3].unit, '千桶');
  assert.equal(result.observations[3].period, '2026-09-04');
  assert.equal(result.observations[3].frequency, 'weekly');
  assert.equal(result.brent, null);
});

test('does not replace unknown quote time with a history date or collection timestamp', () => {
  const result = energySnapshot({}, { 'CL=F': { price: 0, history: [{ date: '2026-09-09', close: 70 }] } });
  assert.equal(result.wti, 0);
  assert.equal(result.observations[0].observedAt, null);
  assert.equal(result.observations[0].period, null);
  assert.equal(result.observations[0].unit, null);
  assert.equal(energySnapshot().wti, null);
});

for (const timestamp of [1788976800, undefined]) {
  test(`Yahoo collector preserves ${timestamp ? 'the actual' : 'unknown'} quote time`, async (t) => {
    t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ chart: { result: [{
      meta: { regularMarketPrice: 72, currency: 'USD', regularMarketTime: timestamp },
      timestamp: [1788912000], indicators: { quote: [{ close: [70] }] },
    }] } })));
    const result = await collect();
    assert.equal(result.quotes['CL=F'].observedAt, timestamp ? new Date(timestamp * 1000).toISOString() : null);
    assert.equal(result.quotes['CL=F'].price, 72);
  });
}
