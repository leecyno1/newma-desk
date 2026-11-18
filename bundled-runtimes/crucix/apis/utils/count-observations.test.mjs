import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { computeDelta } from '../../lib/delta/engine.mjs';
import { currentDeltaSignal } from '../../lib/delta/format.mjs';
import { MemoryManager } from '../../lib/delta/memory.mjs';
import { generateLLMIdeas } from '../../lib/llm/ideas.mjs';

const now = new Date('2026-11-14T12:00:00Z');
const clock = t => t.mock.timers.enable({ apis: ['Date'], now });
const timestamp = '2026-11-14T11:50:00Z';
export const newsSample = (count, asOf = timestamp) => ({
  meta: { timestamp: asOf }, news: { count }, newsMeta: { status: 'ok', asOf, cachedSources: 0,
    limit: 50, items: [{ url: 'https://example.invalid/rss', status: 'ok', cached: false, asOf }] },
});
const changes = delta => [...delta.signals.escalated, ...delta.signals.deescalated];

test('missing and failed counts never create de-escalation or verified unchanged zero', t => {
  clock(t);
  const delta = computeDelta({}, { tg: { urgent: [{ text: 'old' }] }, thermal: [{ det: 900 }],
    who: [{ title: 'old' }], acled: { totalEvents: 10, totalFatalities: 20 }, sdr: { online: 10 } });
  assert.deepEqual(changes(delta), []);
  assert.ok(!delta.signals.unchanged.includes('news_count'));
  assert.ok(delta.comparisonGaps.some(row => row.key === 'thermal_total'));
  assert.notEqual(delta.summary.direction, 'risk-on');
});

test('true zero sample comparison retains scope, dates and no invented relative rate', t => {
  clock(t);
  const current = newsSample(5), previous = newsSample(0, '2026-11-14T11:40:00Z');
  const entry = changes(computeDelta(current, previous)).find(row => row.key === 'news_count');
  assert.equal(entry.change, 5);
  assert.equal(entry.pctChange, null);
  assert.equal(entry.fromDate, previous.meta.timestamp);
  assert.equal(entry.toDate, timestamp);
  assert.equal(entry.countBasis, 'collection-sample-v1');
  assert.ok(currentDeltaSignal(entry, current, now));
  assert.ok(!currentDeltaSignal({ ...entry, change: 999 }, current, now));
});

test('different query scope, partial, cached, old and regressed samples cannot be compared', t => {
  clock(t);
  const previous = newsSample(10, '2026-11-14T11:40:00Z');
  for (const mutate of [
    d => { d.newsMeta.items[0].url = 'https://other.invalid/rss'; },
    d => { d.newsMeta.status = 'partial'; },
    d => { d.newsMeta.cachedSources = 1; },
    d => { d.newsMeta.asOf = '2026-11-14T08:00:00Z'; },
    d => { d.newsMeta.asOf = '2026-11-14T11:30:00Z'; },
  ]) {
    const current = newsSample(0); mutate(current);
    const delta = computeDelta(current, previous);
    assert.ok(!changes(delta).some(row => row.key === 'news_count'));
    assert.ok(delta.comparisonGaps.some(row => row.key === 'news_count'));
  }
});

test('WHO uses reported window count, not the truncated ten-item display', t => {
  clock(t);
  const sample = (count, asOf) => ({ who: Array.from({ length: 10 }, () => ({ title: 'sample' })),
    whoMeta: { status: 'ok', count, collectedAt: asOf, window: { start: '2026-10-15', end: '2026-11-14' } } });
  const delta = computeDelta(sample(30, timestamp), sample(20, '2026-11-14T11:40:00Z'));
  const entry = changes(delta).find(row => row.key === 'who_alerts');
  assert.equal(entry.from, 20); assert.equal(entry.to, 30);
  assert.notEqual(delta.summary.direction, 'risk-off');
});

test('changing RSS selection rules is not an increase in comparable news samples', t => {
  clock(t);
  const current = newsSample(10), previous = newsSample(3, '2026-11-14T11:40:00Z');
  current.newsMeta.selection = 'regional-reserve-30d-url-v2';
  assert.ok(!changes(computeDelta(current, previous)).some(row => row.key === 'news_count'));
  previous.newsMeta.selection = current.newsMeta.selection;
  const entry = changes(computeDelta(current, previous)).find(row => row.key === 'news_count');
  assert.equal(entry.countScope.selection, current.newsMeta.selection);
  assert.equal(entry.change, 7);
});

test('memory reopens comparable evidence, without laundering legacy missing counts', t => {
  clock(t);
  const dir = mkdtempSync(join(process.env.CRUCIX_RUNS_DIR, 'count-memory-'));
  const memory = new MemoryManager(dir);
  memory.addRun(newsSample(0, '2026-11-14T11:40:00Z'));
  const reopened = new MemoryManager(dir);
  const current = newsSample(5);
  assert.ok(changes(reopened.addRun(current)).some(row => row.key === 'news_count'));
  assert.equal(new MemoryManager(dir).restoreDelta(current).status, 'restored');
  assert.equal(memory._compactForStorage({}).news.count, null);
});

test('no Telegram baseline does not promote every shown post into a new alert', t => {
  clock(t);
  const delta = computeDelta({ tg: { urgent: [{ text: 'Example urgent post', postId: 'x' }] } }, {});
  assert.ok(!delta.signals.new.some(row => row.key.startsWith('tg_urgent:')));
});

test('model rejects legacy bare count changes and discloses unavailable samples', async t => {
  clock(t);
  let context;
  await generateLLMIdeas({ isConfigured: true, async complete(_rules, user) {
    context = user;
    return { text: '[]' };
  } }, { thermal: [{ region: 'Legacy', det: 900 }], air: [{ region: 'Unknown', total: null }] }, {
    summary: { direction: 'risk-on' }, signals: { deescalated: [
      { key: 'thermal_total', label: 'Thermal', from: 999, to: 0, change: -999, pctChange: -100 },
    ] },
  });
  assert.doesNotMatch(context, /999|Legacy: 900|Unknown: null|direction=risk-on/);
  assert.match(context, /thermal_total=unavailable/);
  assert.match(context, /sample.*(?:not|never).*safety/i);
});
