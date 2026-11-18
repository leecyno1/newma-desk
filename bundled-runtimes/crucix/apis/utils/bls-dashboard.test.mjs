import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { synthesize, generateIdeas } from '../../dashboard/inject.mjs';

test('BLS cards show missing values, negative and zero moves without fabricated percentages', () => {
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const fn = html.match(/function blsMetricCards\(cpi, ue\) \{[\s\S]*?\n\}/)?.[0];
  assert.ok(fn);
  const cards = vm.runInNewContext(`${fn};blsMetricCards`);
  const missing = cards({ value: null, date: '2026-09' }, { value: null });
  assert.deepEqual(Array.from(missing, row => row.v), ['--', '--']);
  assert.doesNotMatch(JSON.stringify(missing), /undefined|null%|\+-/);
  const valid = cards({ yoyChangePct: -0.2, momChangePct: 0, date: '2026-09' }, { value: 4.2, momChange: 0.2, date: '2026-09' });
  assert.equal(valid[0].v, '-0.20%');
  assert.match(valid[0].s, /MoM 0.00% \(NSA\)/);
  assert.match(valid[1].s, /\+0.20 pp MoM/);
});

test('missing labor or NSA PPI cannot generate the old confident macro recommendations', async () => {
  const bls = [{ id: 'CUUR0000SA0', value: 310, date: '2026-09', seasonalAdjustment: 'not-seasonally-adjusted' },
    { id: 'WPUFD49104', value: 140, date: '2026-09', momChangePct: 3, seasonalAdjustment: 'not-seasonally-adjusted' },
    { id: 'LNS14000000', value: null, date: '2026-09' },
    { id: 'CES0000000001', value: 100, date: '2026-09', momChange: -100 }];
  const view = await synthesize({ sources: { BLS: { indicators: bls } } }, { refreshNews: false });
  assert.equal(view.bls[0].seasonalAdjustment, 'not-seasonally-adjusted');
  const ideas = generateIdeas({ ...view, fred: [{ id: 'T10Y2Y', value: 0.5 }], gscpi: { value: 2 } });
  assert.ok(!ideas.some(row => /Inflation Pipeline|Weak Labor/.test(row.title)));
});
