import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { briefing, getAvgInterestRates } from '../sources/treasury.mjs';
import { synthesize, generateIdeas } from '../../dashboard/inject.mjs';
import { sourceOutcome } from './source-health.mjs';

const debtRow = (date, value = '40000000000000.12') => ({ record_date: date, tot_pub_debt_out_amt: value,
  debt_held_public_amt: '32000000000000.12', intragov_hold_amt: '8000000000000.00' });
const rateRow = (date, value = '3.500', security = 'Treasury Notes') => ({ record_date: date,
  security_desc: security, security_type_desc: 'Marketable', avg_interest_rate_amt: value });
async function read(t, debt, rates) {
  t.mock.method(globalThis, 'fetch', async url => Response.json({ data: String(url).includes('debt_to_penny') ? debt : rates }));
  return briefing();
}

test('rate lookback spans publication gaps and retains the security type', async t => {
  let queried;
  t.mock.method(globalThis, 'fetch', async url => { queried = new URL(url); return Response.json({ data: [] }); });
  await getAvgInterestRates();
  assert.ok(queried.searchParams.get('fields').includes('security_type_desc'));
  const start = queried.searchParams.get('filter').split(':').at(-1);
  assert.ok((Date.now() - Date.parse(start)) / 86400000 >= 119);
});

test('HTTP rejections are unavailable, never zero debt or successful empty rates', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('private credentials', { status: 403 }));
  const result = await briefing();
  assert.equal(result.status, 'error');
  assert.equal(result.coverage.debt.httpStatus, 403);
  assert.equal(result.coverage.interestRates.errorCode, 'HTTP_ERROR');
  assert.equal(sourceOutcome('Treasury', result).status, 'error');
  assert.doesNotMatch(JSON.stringify(result), /private credentials/);
  const view = await synthesize({ sources: { Treasury: result } }, { refreshNews: false });
  assert.equal(view.treasury.totalDebt, null);
});

test('empty valid responses mean no observations, not zero national debt', async t => {
  const result = await read(t, [], []);
  assert.equal(result.status, 'no_data');
  assert.equal(sourceOutcome('Treasury', result).status, 'unknown');
});

test('latest monthly set is not mixed with prior months and a missing newest value is not backfilled', async t => {
  const result = await read(t, [debtRow('2026-01-02', null), debtRow('2026-01-01')],
    [rateRow('2025-12-31', '3'), rateRow('2026-01-31', null), rateRow('2026-01-31', '0', 'Treasury Bills')]);
  assert.equal(result.status, 'partial');
  assert.equal(result.debt[0].date, '2026-01-02');
  assert.equal(result.debt[0].totalDebt, null);
  assert.equal(result.interestRates.length, 2);
  assert.equal(result.interestRates[0].rate, null);
  assert.equal(result.interestRates[1].rate, 0);
  assert.ok(result.interestRates.every(r => r.basis === 'outstanding-debt-average-interest-rate' && r.date === '2026-01-31'));
});

test('debt precision, rates and source dates survive synthesis without a directional trade', async t => {
  const source = await read(t, [debtRow('2026-01-02')], [rateRow('2025-12-31')]);
  const view = await synthesize({ sources: { Treasury: source } }, { refreshNews: false });
  assert.equal(view.treasury.totalDebt, '40000000000000.12');
  assert.equal(view.treasury.date, '2026-01-02');
  assert.equal(view.treasury.interestRates[0].rate, 3.5);
  assert.doesNotMatch(JSON.stringify(generateIdeas(view)), /Fiscal Trajectory|gold, bitcoin|appreciation thesis intact/);
});

test('partial source success remains usable and source failure is visible', async t => {
  t.mock.method(globalThis, 'fetch', async url => String(url).includes('debt_to_penny')
    ? Response.json({ data: [debtRow('2026-01-02')] }) : new Response('', { status: 403 }));
  const source = await briefing();
  assert.equal(source.status, 'partial');
  assert.equal(source.debt.length, 1);
  assert.equal(source.interestRates.length, 0);
  assert.match(sourceOutcome('Treasury', source).reason, /1\/2.*403/);
});

test('debt display needs a source date and a valid number, not NaN or legacy fake zero', () => {
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const fn = html.match(/function treasuryDebtLabel\(treasury\) \{[\s\S]*?\n\}/)?.[0];
  const render = vm.runInNewContext(`${fn};treasuryDebtLabel`);
  assert.equal(render({ totalDebt: '0' }), '--');
  assert.equal(render({ totalDebt: null, date: '2026-01-02' }), '--');
  assert.equal(render({ totalDebt: '40000000000000', date: '2026-01-02' }), '$40.00T · 2026-01-02');
});
