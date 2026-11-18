import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import { readFileSync, mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { briefing as fires } from '../sources/firms.mjs';
import { briefing as receivers } from '../sources/kiwisdr.mjs';
import { synthesize, generateIdeas, fetchNewsResult } from '../../dashboard/inject.mjs';
import { countObservation } from '../../lib/delta/count-observations.mjs';
import { MemoryManager } from '../../lib/delta/memory.mjs';
import { TelegramAlerter } from '../../lib/alerts/telegram.mjs';
import { DiscordAlerter } from '../../lib/alerts/discord.mjs';

const header = 'latitude,longitude,acq_date,acq_time,confidence,daynight,frp';
const now = new Date('2026-11-14T12:00:00Z');
const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');

test('FIRMS valid empty CSV is true zero; HTML, malformed rows and missing responses stay unknown', async t => {
  t.mock.timers.enable({ apis: ['Date'], now });
  const old = process.env.FIRMS_MAP_KEY;
  process.env.FIRMS_MAP_KEY = 'synthetic-qa-only';
  t.after(() => { if (old === undefined) delete process.env.FIRMS_MAP_KEY; else process.env.FIRMS_MAP_KEY = old; });
  let body = header;
  t.mock.method(globalThis, 'fetch', async () => new Response(body));
  const empty = await fires();
  const dashboard = await synthesize({ sources: { FIRMS: empty } }, { refreshNews: false });
  assert.equal(empty.status, 'ok');
  assert.equal(countObservation(dashboard, 'thermal_total', now).value, 0);
  for (body of ['', '<html>Unauthorized</html>', header + '\nnot,a,valid,row', header + '\n91,1,2026-11-14,1100,h,N,5']) {
    const failed = await fires();
    assert.equal(failed.status, 'error');
    const view = await synthesize({ sources: { FIRMS: failed } }, { refreshNews: false });
    assert.ok(view.thermal.every(row => row.det === null && row.night === null));
    assert.equal(countObservation(view, 'thermal_total', now), null);
  }
});

test('partial FIRMS preserves known regions but does not sum incomplete coverage', async t => {
  const old = process.env.FIRMS_MAP_KEY;
  process.env.FIRMS_MAP_KEY = 'synthetic-qa-only';
  t.after(() => { if (old === undefined) delete process.env.FIRMS_MAP_KEY; else process.env.FIRMS_MAP_KEY = old; });
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => new Response(calls++ === 0 ? '<html>Failure</html>' : header));
  const view = await synthesize({ sources: { FIRMS: await fires() } }, { refreshNews: false });
  assert.equal(calls, 6);
  assert.equal(view.thermalMeta.status, 'partial');
  assert.equal(view.thermal[0].det, null);
  assert.equal(view.thermal[1].det, 0);
  assert.equal(countObservation(view, 'thermal_total'), null);
});

test('Receiverbook directory cannot fabricate online receivers, listeners or utilization', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('var receivers = ' + JSON.stringify([
    { label: 'Example, Test', location: { coordinates: [0, 0] }, receivers: [{ label: 'Synthetic' }] },
  ]) + ';'));
  const data = await receivers();
  assert.equal(data.basis, 'directory-only');
  assert.equal(data.network.totalReceivers, 1);
  for (const key of ['online', 'offline', 'totalUsers', 'totalCapacity', 'utilizationPct']) assert.equal(data.network[key], null);
  assert.deepEqual(data.signals, []);
  const view = await synthesize({ sources: { KiwiSDR: data } }, { refreshNews: false });
  assert.equal(view.sdr.online, null);
  assert.equal(view.sdr.total, 1);
  assert.equal(countObservation(view, 'sdr_online'), null);
});

test('RSS scope records the actual feed URLs, not only mutable display names', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('<rss><channel/></rss>'));
  const data = await fetchNewsResult([['https://example.invalid/one', 'Shared name'], ['https://example.invalid/two', 'Shared name']]);
  assert.deepEqual(countObservation({ news: data.news, newsMeta: data.meta }, 'news_count').scope.feeds,
    ['https://example.invalid/one', 'https://example.invalid/two']);
});

test('read-only RSS restoration matches original receipts, never changed feed evidence', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('<rss><channel/></rss>'));
  const dir = mkdtempSync(join(process.env.CRUCIX_RUNS_DIR, 'rss-restore-'));
  const raw = { crucix: { timestamp: new Date().toISOString() }, sources: {} };
  const current = await synthesize(raw, { newsCacheDir: dir });
  const memory = new MemoryManager(dir);
  memory.addRun(current);
  const restored = await synthesize(raw, { refreshNews: false, newsCacheDir: dir });
  assert.equal(restored.newsMeta.mode, 'cache');
  assert.equal(restored.newsMeta.cachedSources, 19);
  assert.equal(countObservation(restored, 'news_count'), null, 'cached RSS is not a new collection');
  assert.equal(new MemoryManager(dir).restoreDelta(restored).status, 'baseline');
  restored.newsMeta.items[0].url = 'https://changed.invalid/rss';
  assert.equal(new MemoryManager(dir).restoreDelta(restored).status, 'unavailable');
});

for (const [name, Class] of [['Telegram', TelegramAlerter], ['Discord', DiscordAlerter]]) {
  test(`${name} does not evaluate or send emergency alerts based on sample counts`, async () => {
    const alerter = new Class({});
    // Enable the normal decision entry but make any attempted provider/send fail the test.
    Object.defineProperty(alerter, 'isConfigured', { value: true });
    alerter.sendMessage = async () => { throw new Error('Must not send'); };
    const signals = [
      { key: 'thermal_total', severity: 'critical', direction: 'up' },
      { key: 'conflict_events', severity: 'critical', direction: 'up' },
      { key: 'tg_urgent:legacy', item: { channel: 'synthetic' } },
    ];
    const delta = { summary: { totalChanges: 3, direction: 'risk-off' }, signals: { escalated: signals } };
    assert.equal(await alerter.evaluateAndAlert({ isConfigured: true, complete() { throw new Error('Must not call model'); } }, delta, {}), false);
    assert.equal(alerter._ruleBasedEvaluation(signals, delta).shouldAlert, false);
  });
}

test('legacy thermal/OSINT arrays cannot claim satellite confirmation or create a rule idea', async () => {
  const data = await synthesize({ sources: {} }, { refreshNews: false });
  const ideas = generateIdeas({ ...data, thermal: [{ det: 999999 }], tg: { urgent: Array.from({ length: 5 }, () => ({})) } });
  assert.ok(!ideas.some(row => /Satellite|Thermal/.test(row.title)));
});

test('native HTML keeps unknown totals distinct from zero and has no fixed intensity bars', () => {
  const thermal = html.match(/function thermalCountText\([\s\S]*?\n\}/)[0];
  const who = html.match(/function whoCountText\([\s\S]*?\n\}/)[0];
  const render = D => vm.runInNewContext(`${thermal};${who};[thermalCountText('det'),whoCountText()]`, { D });
  assert.deepEqual(Array.from(render({ thermal: [], who: [] })), ['—', '—']);
  assert.deepEqual(Array.from(render({ thermal: [{ det: 0 }], thermalMeta: { status: 'ok', scope: {} },
    who: [], whoMeta: { status: 'ok', count: 0 } })), ['0', 0]);
  assert.match(render({ thermal: [{ det: null }], who: [{}] })[1], /shown.*unknown/);
  assert.doesNotMatch(html, /Satellite Confirms Conflict Intensity|width:\$\{s\.p\}%/);
  for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
    if (match[1].trim()) new vm.Script(match[1]);
  }
});
