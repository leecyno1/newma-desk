import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { synthesize, generateIdeas } from '../../dashboard/inject.mjs';

const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
const metricFunction = html.match(/function fredMetricText\([\s\S]*?\n\}/)?.[0];

test('actual FRED formatter does not coerce missing M2 to zero or hide real zero', () => {
  assert.ok(metricFunction);
  const format = vm.runInNewContext(`${metricFunction}; fredMetricText`);
  for (const value of [null, undefined, NaN, Infinity]) {
    assert.equal(format(value, { digits: 1, scale: 1000, prefix: '$', suffix: 'T' }), '--');
  }
  assert.equal(format(0, { suffix: '%' }), '0%');
  assert.equal(format(-0.25, { digits: 2 }), '-0.25');
  assert.equal(format(21000, { digits: 1, scale: 1000, prefix: '$', suffix: 'T' }), '$21.0T');
});

test('actual lower metric cards keep missing Fed Funds unknown and zero VIX visible', () => {
  const start = html.indexOf('  const vixLive = mkt.vix;');
  const end = html.indexOf('\n  // Attach sparklines', start);
  const energyFunction = html.match(/function energyMetricCards\([\s\S]*?\n\}/)?.[0];
  assert.ok(energyFunction);
  const evaluate = value => vm.runInNewContext(`${metricFunction}; ${energyFunction}; ${html.slice(start, end)}; metrics`, {
    mkt: {}, D: { fred: [{ id: 'VIXCLS', value }], energy: {} }, ff: { value },
    metals: {}, gscpi: null, cpi: null, ue: null, blsMetricCards: () => [],
  });
  assert.equal(evaluate(null).find(row => row.l === 'Fed Funds').v, '--');
  assert.equal(evaluate(null).find(row => row.l === 'VIX').v, '--');
  assert.equal(evaluate(0).find(row => row.l === 'Fed Funds').v, '0%');
  assert.equal(evaluate(0).find(row => row.l === 'VIX').v, '0.0');
});

test('FRED missing indicators and coverage survive synthesis instead of healthy old timing', async () => {
  const raw = { source: 'FRED', status: 'partial',
    coverage: { requested: 21, succeeded: 1, partial: 0, failed: 20, empty: 0 },
    indicators: [{ id: 'DFF', label: 'Fed Funds Rate', value: 0, date: '2026-11-13', recent: [0] },
      { id: 'VIXCLS', label: 'VIX', value: null, date: null, recent: [], httpStatus: 403 }], signals: [] };
  const view = await synthesize({ sources: { FRED: raw }, timing: { FRED: { status: 'ok', reason: 'old timing' } } }, { refreshNews: false });
  assert.equal(view.fred[0].value, 0);
  assert.equal(view.fred[1].value, null);
  assert.equal(view.meta.sourcesPartial, 1);
  assert.equal(view.meta.sourcesOk, 0);
  assert.equal(view.health[0].status, 'partial');
  assert.match(view.health[0].reason, /1\/21.*403/);
  assert.ok(!generateIdeas(view).some(row => /Volatility|Safe Haven/.test(row.title)));
});

test('legacy FRED snapshot stays readable but no longer certifies complete collection', async () => {
  const view = await synthesize({ sources: { FRED: { indicators: [{ id: 'DFF', value: 4 }] } },
    timing: { FRED: { status: 'ok', reason: 'old success' } } }, { refreshNews: false });
  assert.equal(view.fred[0].value, 4);
  assert.equal(view.health[0].status, 'unknown');
  assert.equal(view.meta.sourcesUnknown, 1);
});
