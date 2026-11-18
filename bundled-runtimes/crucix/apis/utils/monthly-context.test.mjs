import assert from 'node:assert/strict';
import test from 'node:test';
import { synthesize, generateIdeas } from '../../dashboard/inject.mjs';
import { generateLLMIdeas } from '../../lib/llm/ideas.mjs';
import { computeDelta } from '../../lib/delta/engine.mjs';

const now = new Date('2026-11-14T12:00:00Z');
const labor = (value, date = '2026-10', id = 'LNS14000000') => ({ id, value, date, frequency: 'monthly',
  unit: id === 'LNS14000000' ? 'percent' : 'thousands-of-persons', seasonalAdjustment: 'seasonally-adjusted' });
const view = async bls => ({ ...await synthesize({ sources: { BLS: { indicators: bls } } }, { refreshNews: false }),
  fred: [{ id: 'T10Y2Y', value: 0.5, date: '2026-11-13' }] });
async function prompt(data, delta = null) {
  let context;
  await generateLLMIdeas({ isConfigured: true, async complete(_system, user) {
    context = user;
    return { text: JSON.stringify([{ title: 'Synthetic QA', type: 'WATCH', confidence: 'LOW' }]) };
  } }, data, delta);
  assert.equal(typeof context, 'string');
  return context;
}

for (const period of ['2025-01', '2026-11', '2026-12', '2026-00', '2026-13']) {
  test(`${period} labor does not drive a current yield-curve interaction`, async () => {
    const data = await view([labor(5, period), labor(150000, period, 'CES0000000001')]);
    assert.ok(!generateIdeas(data, { now }).some(row => /Weak Labor/.test(row.title)));
  });
}

test('recent completed labor period is dated and supports review, not a high-confidence hedge', async () => {
  const data = await view([labor(5), labor(150000, '2026-10', 'CES0000000001')]);
  const idea = generateIdeas(data, { now }).find(row => /Weak Labor/.test(row.title));
  assert.ok(idea);
  assert.equal(idea.type, 'watch');
  assert.equal(idea.confidence, 'Medium');
  assert.match(idea.text, /2026-10.*different frequencies|different frequencies.*2026-10/i);
});

test('a nonadjacent payroll change cannot manufacture weak labor', async () => {
  const data = await view([labor(4.2), { ...labor(150000, '2026-10', 'CES0000000001'),
    momChange: -100, momPreviousPeriod: '2026-07' }]);
  assert.ok(!generateIdeas(data, { now }).some(row => /Weak Labor/.test(row.title)));
});

test('actual monthly model context keeps dates, levels, units, adjustment and adjacent changes', async t => {
  t.mock.timers.enable({ apis: ['Date'], now });
  const context = await prompt({ bls: [
    { ...labor(4.5), momChange: 0.2, momPreviousPeriod: '2026-09' },
    { ...labor(150000, '2026-10', 'CES0000000001'), momChange: -100, momPreviousPeriod: '2026-09' },
    { id: 'CUUR0000SA0', value: 310, date: '2026-10', frequency: 'monthly', unit: 'index',
      seasonalAdjustment: 'not-seasonally-adjusted', momChange: 0, momChangePct: 0, momPreviousPeriod: '2026-09' },
  ] });
  assert.match(context, /LNS14000000=4\.5 percent.*2026-10.*seasonally-adjusted.*0\.2 percentage-points/);
  assert.match(context, /CES0000000001=150000 thousands-of-persons.*-100 thousands-of-persons/);
  assert.match(context, /CUUR0000SA0=310 index.*not-seasonally-adjusted.*0 index-points.*0%/);
});

for (const row of [labor(987654, '2024-01'), labor(987654, '2026-11'),
  { id: 'LNS14000000', value: 987654, date: '2026-10' }]) {
  test(`old, incomplete or unverified monthly model input stays unavailable (${JSON.stringify(row)})`, async t => {
    t.mock.timers.enable({ apis: ['Date'], now });
    const context = await prompt({ bls: [row] });
    assert.doesNotMatch(context, /987654/);
    assert.match(context, /LNS14000000=unavailable/);
  });
}

test('monthly window crosses year boundaries and retains a real zero', async t => {
  t.mock.timers.enable({ apis: ['Date'], now: new Date('2027-01-14T12:00:00Z') });
  const context = await prompt({ bls: [{ ...labor(0, '2026-12'), momChange: 0, momPreviousPeriod: '2026-11' }] });
  assert.match(context, /LNS14000000=0 percent.*2026-12.*0 percentage-points/);
});

test('monthly delta preserves periods and excludes same-period revisions and old values', t => {
  t.mock.timers.enable({ apis: ['Date'], now });
  const snapshot = row => ({ bls: [row] });
  const delta = computeDelta(snapshot(labor(5)), snapshot(labor(4.2, '2026-09')));
  const entry = delta.signals.escalated.find(row => row.key === 'unemployment');
  assert.equal(entry.fromDate, '2026-09');
  assert.equal(entry.toDate, '2026-10');
  assert.equal(entry.unit, 'percent');
  assert.equal(entry.changeUnit, 'percentage-points');
  for (const [previous, current] of [[labor(4.2), labor(5)], [labor(4.2, '2024-01'), labor(5, '2024-02')]]) {
    const result = computeDelta(snapshot(current), snapshot(previous));
    assert.equal(result.signals.escalated.length, 0);
    assert.ok(result.comparisonGaps.some(row => row.key === 'unemployment'));
  }
});

test('legacy monthly delta cannot bypass the model observation policy', async t => {
  t.mock.timers.enable({ apis: ['Date'], now });
  const context = await prompt({ bls: [labor(4.2)] }, { summary: { direction: 'risk-off' },
    signals: { escalated: [{ key: 'unemployment', label: 'Unemployment', from: 4.2, to: 987654 }] } });
  assert.doesNotMatch(context, /987654|direction=risk-off/);
  assert.match(context, /excluded=1/);
});

const treasury = (value = '40000000000000.12', date = '2026-11-13') => ({
  totalDebt: value, date, coverage: { debt: { status: 'ok' } },
  debt: [{ totalDebt: value, date, unit: 'USD', frequency: 'daily' }],
});

test('Treasury model input reads the actual USD stock and original date, not object-as-trillions', async t => {
  t.mock.timers.enable({ apis: ['Date'], now });
  const context = await prompt({ treasury: treasury() });
  assert.match(context, /totalDebt=40000000000000\.12 USD.*2026-11-13/);
  assert.doesNotMatch(context, /\[object Object\]|40000000000000\.12T/);
});

test('missing, stale, failed and bare legacy Treasury inputs cannot become current debt', async t => {
  t.mock.timers.enable({ apis: ['Date'], now });
  for (const data of [treasury(null), treasury('987654', '2024-01-01'), 987654,
    { ...treasury('987654'), coverage: { debt: { status: 'error' } } }]) {
    const context = await prompt({ treasury: data });
    assert.match(context, /TREASURY:.*unavailable/);
    assert.doesNotMatch(context, /987654|\[object Object\]|nullT/);
  }
});

test('Treasury zero remains zero when evidence has a date and USD unit', async t => {
  t.mock.timers.enable({ apis: ['Date'], now });
  assert.match(await prompt({ treasury: treasury('0') }), /totalDebt=0 USD/);
});
