import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync, mkdirSync, mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import vm from 'node:vm';
import { computeDelta } from '../../lib/delta/engine.mjs';
import { MemoryManager } from '../../lib/delta/memory.mjs';
import { generateLLMIdeas } from '../../lib/llm/ideas.mjs';
import { TelegramAlerter } from '../../lib/alerts/telegram.mjs';

const now = new Date('2026-11-14T12:00:00Z');
const snapshot = (value, date = '2026-11-13', id = 'VIXCLS') => ({
  meta: { timestamp: now.toISOString() }, fred: [{ id, value, date }],
});
const changed = delta => [...delta.signals.escalated, ...delta.signals.deescalated];
const clock = t => t.mock.timers.enable({ apis: ['Date'], now });
async function prompt(data, delta) {
  let context;
  const result = await generateLLMIdeas({ isConfigured: true, async complete(_rules, user) {
    context = user;
    return { text: JSON.stringify([{ title: 'Synthetic QA', type: 'WATCH', confidence: 'LOW' }]) };
  } }, data, delta);
  assert.ok(result);
  return context;
}

test('dated FRED delta and actual model input agree on before/after values and relative change', async t => {
  clock(t);
  const current = snapshot(25), delta = computeDelta(current, snapshot(20, '2026-11-12'));
  const entry = changed(delta)[0];
  assert.equal(entry.pctChange, 25);
  assert.equal(entry.change, 5);
  assert.equal(entry.fromDate, '2026-11-12');
  assert.equal(entry.toDate, '2026-11-13');
  const context = await prompt(current, delta);
  assert.match(context, /20\s*→\s*25.*\+25(?:\.0)?%/);
  assert.match(context, /2026-11-12\s*→\s*2026-11-13/);
  assert.doesNotMatch(context, /undefined|NaN/);
});

test('de-escalation is included in actual model context, not silently omitted', async t => {
  clock(t);
  const current = snapshot(20), delta = computeDelta(current, snapshot(25, '2026-11-12'));
  const context = await prompt(current, delta);
  assert.match(context, /DEESCALATED:.*25\s*→\s*20.*-20(?:\.0)?%/);
});

for (const [label, previous, current] of [
  ['old', snapshot(20, '2026-10-01'), snapshot(30, '2026-10-02')],
  ['future', snapshot(20), snapshot(30, '2026-11-15')],
  ['missing date', snapshot(20, null), snapshot(30)],
  ['invalid date', snapshot(20, '2026-02-30'), snapshot(30)],
  ['date regression', snapshot(20), snapshot(30, '2026-11-12')],
  ['same-date revision', snapshot(20), snapshot(30)],
]) {
  test(`${label} is not a new FRED market movement or an unchanged verified observation`, t => {
    clock(t);
    const delta = computeDelta(current, previous);
    assert.deepEqual(changed(delta), []);
    assert.ok(!delta.signals.unchanged.includes('vix'));
    assert.ok(delta.comparisonGaps.some(row => row.key === 'vix'));
  });
}

test('repeated identical observation is unchanged; weekly mortgage uses its longer window', t => {
  clock(t);
  assert.ok(computeDelta(snapshot(20), snapshot(20)).signals.unchanged.includes('vix'));
  const delta = computeDelta(snapshot(6, '2026-11-06', 'MORTGAGE30US'), snapshot(5, '2026-11-01', 'MORTGAGE30US'));
  assert.equal(changed(delta)[0].key, 'mortgage');
  assert.equal(changed(delta)[0].fromDate, '2026-11-01');
});

test('zero baseline retains absolute movement but relative percentage stays unknown', async t => {
  clock(t);
  const current = snapshot(0.25, '2026-11-13', 'T10Y2Y');
  const delta = computeDelta(current, snapshot(0, '2026-11-12', 'T10Y2Y'));
  const entry = changed(delta)[0];
  assert.ok(entry);
  assert.equal(entry.from, 0);
  assert.equal(entry.pctChange, null);
  assert.equal(entry.change, 0.25);
  assert.equal(entry.changeUnit, 'percentage points');
  assert.equal(entry.severity, 'moderate');
  const context = await prompt(current, delta);
  assert.match(context, /0\s*→\s*0\.25.*\+0\.25 percentage points.*relative unavailable/);
  assert.doesNotMatch(context, /null%|undefined|NaN|0\.0%/);
});

test('finite values are required and valid negative bases retain the correct arithmetic', t => {
  clock(t);
  for (const value of [NaN, Infinity, '25']) {
    assert.deepEqual(changed(computeDelta(snapshot(value), snapshot(20, '2026-11-12'))), []);
  }
  const entry = changed(computeDelta(snapshot(0.1, '2026-11-13', 'T10Y2Y'),
    snapshot(-0.1, '2026-11-12', 'T10Y2Y')))[0];
  assert.equal(entry.pctChange, 200);
  assert.ok(Math.abs(entry.change - 0.2) < 1e-12);
});

test('count increase from zero does not invent a 100 percent growth rate', t => {
  clock(t);
  const sample = (count, asOf) => ({ news: { count }, newsMeta: { status: 'ok', cachedSources: 0, asOf, limit: 50,
    items: [{ url: 'https://example.invalid/feed', status: 'ok', cached: false, asOf }] } });
  const delta = computeDelta(sample(5, '2026-11-14T11:50:00Z'), sample(0, '2026-11-14T11:40:00Z'));
  const entry = changed(delta).find(row => row.key === 'news_count');
  assert.equal(entry.pctChange, null);
  assert.equal(entry.change, 5);
});

test('legacy undated FRED delta is not smuggled back into model context', async t => {
  clock(t);
  const delta = { summary: { direction: 'risk-off', totalChanges: 1, criticalChanges: 1 },
    signals: { escalated: [{ key: 'vix', label: 'VIX', from: 20, to: 999, pctChange: 4895, severity: 'critical' }] } };
  const context = await prompt(snapshot(20), delta);
  assert.doesNotMatch(context, /999|4895|direction=risk-off/);
  assert.match(context, /excluded=1.*unverified|unverified.*excluded=1/);
});

test('saved dated FRED delta must still match the current observed value and date', async t => {
  clock(t);
  const delta = computeDelta(snapshot(25), snapshot(20, '2026-11-12'));
  const context = await prompt(snapshot(20), delta);
  assert.doesNotMatch(context, /20\s*→\s*25/);
  assert.match(context, /excluded=1/);
});

test('original memory round trip retains observation dates for the next comparison', t => {
  clock(t);
  mkdirSync(process.env.CRUCIX_RUNS_DIR, { recursive: true });
  const dir = mkdtempSync(join(process.env.CRUCIX_RUNS_DIR, 'delta-memory-'));
  const memory = new MemoryManager(dir);
  assert.equal(memory.addRun(snapshot(20, '2026-11-12')), null);
  const reopened = new MemoryManager(dir);
  assert.equal(reopened.getLastRun().fred[0].date, '2026-11-12');
  assert.equal(changed(reopened.addRun(snapshot(25)))[0].fromDate, '2026-11-12');
});

test('alert context and actual HTML delta formatter do not render null percent', () => {
  const entry = { key: '10y2y', label: '10Y-2Y Spread', from: 0, to: 0.25, change: 0.25,
    pctChange: null, unit: 'percentage points', changeUnit: 'percentage points',
    fromDate: '2026-11-12', toDate: '2026-11-13' };
  const context = new TelegramAlerter({ botToken: '', chatId: '' })._buildSignalContext([entry],
    { summary: { direction: 'mixed', totalChanges: 1, criticalChanges: 0 } });
  assert.match(context, /0\s*→\s*0\.25.*\+0\.25 percentage points.*relative unavailable/);
  assert.doesNotMatch(context, /null%|undefined|NaN/);
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const fn = html.match(/function deltaChangeText\([\s\S]*?\n\}/)?.[0];
  assert.ok(fn);
  const format = vm.runInNewContext(`${fn};deltaChangeText`);
  assert.match(format(entry), /0\s*→\s*0\.25.*\+0\.25 percentage points/);
  assert.doesNotMatch(format(entry), /null%|undefined|NaN/);
  assert.equal(format({ label: 'Nuclear anomaly', direction: 'resolved' }), 'resolved');
});

test('actual delta panel discloses incomplete comparisons even when some changes are present', () => {
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const fn = html.match(/function deltaChangeText\([\s\S]*?\n\}/)?.[0];
  const stateFn = html.match(/function deltaStateText\([\s\S]*?\n\}/)?.[0];
  const start = html.indexOf('  // DELTA PANEL —');
  const end = html.indexOf("  document.getElementById('rightRail')", start);
  assert.ok(start > 0 && end > start);
  const result = vm.runInNewContext(`${fn};${stateFn};${html.slice(start, end)};deltaHtml`, {
    D: { delta: { summary: { totalChanges: 1, direction: 'mixed' }, comparisonGaps: [{ key: 'vix' }],
      signals: { escalated: [{ key: 'news_count', label: 'News Items', from: 0, to: 5, change: 5, pctChange: null }] } } },
    t: (_key, fallback) => fallback,
  });
  assert.match(result, /Comparison incomplete.*1 indicator/);
  assert.match(result, /News Items/);
  assert.doesNotMatch(result, /null%|undefined|NaN/);
});
