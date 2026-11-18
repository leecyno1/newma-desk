import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdirSync, mkdtempSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import vm from 'node:vm';
import { MemoryManager } from '../../lib/delta/memory.mjs';

const now = new Date('2026-11-14T12:00:00Z');
const snapshot = (value, date, timestamp = `${date}T12:00:00Z`) => ({
  meta: { timestamp }, fred: [{ id: 'VIXCLS', value, date }],
  metals: { gold: 2700 }, airMeta: { fallback: false }, news: [{ title: 'Synthetic report' }],
});
function fixture(t) {
  t.mock.timers.enable({ apis: ['Date'], now });
  mkdirSync(process.env.CRUCIX_RUNS_DIR, { recursive: true });
  const dir = mkdtempSync(join(process.env.CRUCIX_RUNS_DIR, 'restore-'));
  const memory = new MemoryManager(dir);
  const previous = snapshot(20, '2026-11-12');
  const current = snapshot(25, '2026-11-13');
  memory.addRun(previous);
  memory.addRun(current);
  return { dir, memory: new MemoryManager(dir), current, previous };
}

test('matching saved sweep restores its original delta without writing or appending history', t => {
  const { dir, memory, current } = fixture(t);
  const before = readFileSync(memory.hotPath);
  const restored = memory.restoreDelta(current);
  assert.equal(restored.status, 'restored');
  assert.equal(restored.timestamp, current.meta.timestamp);
  assert.equal(restored.delta.signals.escalated[0].pctChange, 25);
  assert.equal(restored.delta.signals.escalated[0].fromDate, '2026-11-12');
  assert.equal(memory.getRunHistory().length, 2);
  assert.ok(before.equals(readFileSync(memory.hotPath)));
  assert.equal(new MemoryManager(dir).getRunHistory().length, 2);
});

test('a different sweep is unavailable, not unchanged or an unrelated last delta', t => {
  const { memory, current } = fixture(t);
  current.meta.timestamp = '2026-11-14T01:00:00Z';
  const restored = memory.restoreDelta(current);
  assert.equal(restored.status, 'unavailable');
  assert.equal(restored.delta, null);
});

for (const [label, change] of [
  ['FRED observation', data => { data.fred[0].value = 99; }],
  ['metal price', data => { data.metals.gold = 9999; }],
  ['air fallback', data => { data.airMeta.fallback = true; }],
  ['RSS count', data => { data.news.push({ title: 'Another report' }); }],
]) {
  test(`same timestamp with changed ${label} cannot borrow saved history`, t => {
    const { memory, current } = fixture(t);
    change(current);
    assert.equal(memory.restoreDelta(current).status, 'unavailable');
    assert.equal(memory.restoreDelta(current).delta, null);
  });
}

test('first saved run is an explicit baseline; missing history is unavailable', t => {
  const { memory, previous, current } = fixture(t);
  assert.equal(memory.restoreDelta(previous).status, 'baseline');
  memory.hot.runs = [];
  assert.equal(memory.restoreDelta(current).status, 'unavailable');
});

test('saved delta itself must belong to the matching run', t => {
  const { memory, current } = fixture(t);
  memory.hot.runs[0].delta.timestamp = '2026-11-10T00:00:00Z';
  assert.equal(memory.restoreDelta(current).status, 'unavailable');
  assert.equal(memory.restoreDelta(current).delta, null);
});

test('actual HTML differentiates restored history, baseline and unavailable comparison', () => {
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const fn = html.match(/function deltaStateText\([\s\S]*?\n\}/)?.[0];
  assert.ok(fn);
  const format = vm.runInNewContext(`${fn};deltaStateText`);
  assert.match(format({ deltaState: { status: 'restored', timestamp: '2026-11-13T12:00:00Z' } }), /Saved comparison.*2026-11-13.*not a new sweep/);
  assert.match(format({ deltaState: { status: 'baseline' } }), /Baseline only/);
  assert.match(format({ deltaState: { status: 'unavailable' } }), /Comparison unavailable/);
  assert.doesNotMatch(format({}), /No changes/);
});

for (const [name, registration, next] of [
  ['Telegram', "telegramAlerter.onCommand('/brief'", "telegramAlerter.onCommand('/portfolio'"],
  ['Discord', "discordAlerter.onCommand('brief'", "discordAlerter.onCommand('portfolio'"],
]) {
  test(`${name} brief uses the displayed snapshot comparison, never unrelated latest memory`, async () => {
    const source = readFileSync(new URL('../../server.mjs', import.meta.url), 'utf8');
    const start = source.indexOf(registration), end = source.indexOf(next, start);
    assert.ok(start > 0 && end > start);
    let brief;
    const alerter = { onCommand(_name, handler) { brief = handler; } };
    const currentData = { deltaState: { status: 'restored', timestamp: '2026-11-13T12:00:00Z' },
      delta: { summary: { direction: 'risk-off', totalChanges: 1, criticalChanges: 0 } } };
    vm.runInNewContext(source.slice(start, end), { currentData,
      telegramAlerter: alerter, discordAlerter: alerter,
      memory: { getLastDelta() { throw new Error('Unrelated memory must not be used'); } } });
    assert.match(await brief(), /Saved comparison.*2026-11-13.*not a new sweep/);
    currentData.deltaState.status = 'unavailable';
    currentData.delta = null;
    const text = await brief();
    assert.match(text, /Comparison unavailable/);
    assert.doesNotMatch(text, /RISK-OFF/);
  });
}
