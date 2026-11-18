import assert from 'node:assert/strict';
import test from 'node:test';
import { briefing as gscpiBriefing } from '../sources/gscpi.mjs';
import { synthesize, generateIdeas } from '../../dashboard/inject.mjs';
import { generateLLMIdeas } from '../../lib/llm/ideas.mjs';
import { computeDelta } from '../../lib/delta/engine.mjs';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const now = new Date('2026-11-14T12:00:00Z');
const clock = t => t.mock.timers.enable({ apis: ['Date'], now });
async function csv(t, text) {
  t.mock.method(globalThis, 'fetch', async () => new Response(text));
  return gscpiBriefing();
}
const quote = (price = 2700, observedAt = '2026-11-13T20:00:00Z', currency = 'USD') => ({ price, currency, observedAt,
  changePct: 2, prevClose: 2650, previousCloseBasis: 'daily-bars', history: [] });
const view = quotes => synthesize({ sources: { YFinance: { quotes } } }, { refreshNews: false });
async function prompt(data, delta = null) {
  let context;
  await generateLLMIdeas({ isConfigured: true, async complete(_rules, user) {
    context = user;
    return { text: '[{"title":"Synthetic QA","type":"WATCH","confidence":"LOW"}]' };
  } }, data, delta);
  return context;
}

test('supply chain uses one explicit latest vintage, never fills its blanks from older columns', async t => {
  clock(t);
  const raw = await csv(t, 'Date,46296,46327\n31-Oct-2026,987654,#N/A\n30-Sep-2026,8,1.2\n');
  assert.equal(raw.latest.date, '2026-09');
  assert.equal(raw.latest.value, 1.2);
  assert.equal(raw.latest.vintage, '46327');
  const context = await prompt({ gscpi: (await synthesize({ sources: { GSCPI: raw } }, { refreshNews: false })).gscpi });
  assert.doesNotMatch(context, /987654/);
  assert.match(context, /collection partial.*missing vintage cells 1/);
});

for (const [date, value] of [['31-Oct-2026', '1.2junk'], ['31-Oct-2026', 'Infinity'],
  ['31-Feb-2026', '2'], ['30-Nov-2026', '2'], ['31-Dec-2026', '2']]) {
  test(`invalid/incomplete supply observation ${date}/${value} cannot be current`, async t => {
    clock(t);
    const raw = await csv(t, `Date,46327\n${date},${value}\n`);
    assert.equal(raw.latest, null);
    assert.equal(raw.status, 'no_data');
    assert.deepEqual(raw.signals, []);
  });
}

test('nonadjacent supply months are not called month-on-month or a three-month trend', async t => {
  clock(t);
  const raw = await csv(t, 'Date,46327\n31-Oct-2026,2\n31-Jul-2026,1\n31-Mar-2026,0\n');
  assert.equal(raw.trend, 'insufficient data');
  assert.ok(!raw.signals.some(text => /month-over-month|trending higher/.test(text)));
});

test('zero supply pressure is the historical average, with explicit units and source', async t => {
  clock(t);
  const raw = await csv(t, 'Date,46327\n31-Oct-2026,0\n30-Sep-2026,-1\n31-Aug-2026,-2\n');
  assert.equal(raw.latest.interpretation, 'historical average');
  const data = await synthesize({ sources: { GSCPI: raw } }, { refreshNews: false });
  assert.match(await prompt(data), /GSCPI=0 standard-deviations.*2026-10.*46327/);
});

test('synthesis keeps supply collection time and no-data receipts even without a latest value', async t => {
  clock(t);
  const raw = await csv(t, 'Date,46327\n31-Oct-2026,#N/A\n');
  const data = await synthesize({ sources: { GSCPI: raw } }, { refreshNews: false });
  assert.equal(data.gscpi.status, 'no_data');
  assert.equal(data.gscpi.missing, 1);
  assert.equal(data.gscpi.vintage, '46327');
  assert.equal(data.gscpi.collectedAt, raw.timestamp);
});

test('bare, old or unverified supply snapshots cannot become current model evidence', async t => {
  clock(t);
  for (const row of [{ value: 987654 }, { value: 987654, date: '2024-01' }]) {
    const text = await prompt({ gscpi: row });
    assert.match(text, /GSCPI=unavailable/);
    assert.doesNotMatch(text, /987654/);
  }
});

test('supply/inflation interaction validates aligned months and observes NSA changes without causal trades', async t => {
  clock(t);
  const raw = await csv(t, 'Date,46327\n31-Oct-2026,2\n30-Sep-2026,1\n31-Aug-2026,0\n');
  const base = await synthesize({ sources: { GSCPI: raw } }, { refreshNews: false });
  const labor = (id, value) => ({ id, value, date: '2026-10', frequency: 'monthly', unit: 'index',
    seasonalAdjustment: 'not-seasonally-adjusted', momChange: 1, momChangePct: 1, momPreviousPeriod: '2026-09' });
  const bls = [labor('WPUFD49104', 110), labor('CUUR0000SA0', 310)];
  const idea = generateIdeas({ ...base, bls }, { now }).find(row => /Supply Chain and Inflation/.test(row.title));
  assert.ok(idea);
  assert.equal(idea.type, 'watch');
  assert.match(idea.text, /NSA|not-seasonally-adjusted/);
  assert.match(idea.text, /not establish|not prove/);
  assert.ok(!generateIdeas({ ...base, bls: bls.map(row => ({ ...row, date: '2024-01' })) }, { now })
    .some(row => /Supply Chain and Inflation/.test(row.title)));
});

test('metal synthesis/model keeps futures, USD per troy ounce, original quote time and symbol', async t => {
  clock(t);
  const data = await view({ 'GC=F': quote() });
  assert.equal(data.metals.observations[0].source.seriesId, 'GC=F');
  assert.match(await prompt(data), /gold=2700 USD\/troy-ounce.*futures.*2026-11-13T20:00:00Z.*GC=F/);
});

test('old, future, undated and non-USD metal quotes do not enter the model as current', async t => {
  clock(t);
  for (const row of [quote(987654, '2024-01-01T00:00:00Z'), quote(987654, '2026-11-15T00:00:00Z'),
    quote(987654, null), quote(987654, now.toISOString(), 'EUR')]) {
    const text = await prompt(await view({ 'GC=F': row }));
    assert.match(text, /gold=unavailable/);
    assert.doesNotMatch(text, /987654/);
  }
  assert.doesNotMatch(await prompt({ metals: { gold: 987654, goldChangePct: 999 } }), /987654|999/);
});

test('metal zero remains zero with valid dated evidence', async t => {
  clock(t);
  assert.match(await prompt(await view({ 'GC=F': quote(0) })), /gold=0 USD\/troy-ounce/);
});

test('metal delta requires dated matching futures basis and rejects old/same-time revisions', async t => {
  clock(t);
  const current = await view({ 'GC=F': quote(2800) });
  const previous = await view({ 'GC=F': quote(2700, '2026-11-12T20:00:00Z') });
  const delta = computeDelta(current, previous);
  const entry = delta.signals.escalated.find(row => row.key === 'gold');
  assert.equal(entry.unit, 'USD/troy-ounce');
  assert.equal(entry.fromDate, '2026-11-12T20:00:00Z');
  assert.match(await prompt(current, delta), /ESCALATED:.*2700 → 2800.*continuous futures may roll/);
  for (const old of [quote(2700), quote(2700, '2024-01-01T00:00:00Z')]) {
    const result = computeDelta(current, await view({ 'GC=F': old }));
    assert.ok(result.comparisonGaps.some(row => row.key === 'gold'));
    assert.ok(!result.signals.escalated.some(row => row.key === 'gold'));
  }
});

test('legacy metal delta cannot smuggle unverified values into model context', async t => {
  clock(t);
  const text = await prompt(await view({ 'GC=F': quote() }), { summary: { direction: 'risk-off' },
    signals: { escalated: [{ key: 'gold', from: 2700, to: 987654 }] } });
  assert.doesNotMatch(text, /987654|direction=risk-off/);
});

test('reported metal session change requires an explicit prior-close basis, not an arbitrary percentage', async t => {
  clock(t);
  assert.match(await prompt(await view({ 'GC=F': quote() })), /reported prior close 1\.89%.*daily-bars.*prior-session date not supplied/);
  const row = { ...quote(), prevClose: null, changePct: 987654 };
  const text = await prompt(await view({ 'GC=F': row }));
  assert.match(text, /reported session change unavailable/);
  assert.doesNotMatch(text, /987654/);
});

test('native commodity cards preserve metal kind, troy-ounce units, quote date and unknown currency', async () => {
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const start = html.indexOf('function energyMetricCards('), end = html.indexOf('\nfunction deltaStateText(', start);
  const render = vm.runInNewContext(`${html.slice(start, end)}; energyMetricCards`);
  const defs = [['gold', 'Gold', 58]];
  const data = await view({ 'GC=F': quote() });
  const card = render(data.metals, defs)[0];
  assert.match(card.l, /futures/);
  assert.match(card.s, /USD\/troy-ounce.*2026-11-13.*GC=F/);
  assert.equal(render((await view({ 'GC=F': quote(0) })).metals, defs)[0].v, '0');
  assert.equal(render((await view({ 'GC=F': quote(2700, now.toISOString(), 'EUR') })).metals, defs)[0].v, '--');
});

test('supply parser excludes conflicting duplicate months and no-data overrides old healthy timing', async t => {
  clock(t);
  const raw = await csv(t, 'Date,46327\n31-Oct-2026,1\n31-Oct-2026,2\n');
  assert.equal(raw.latest, null);
  const data = await synthesize({ sources: { GSCPI: raw }, timing: { GSCPI: { status: 'ok', reason: 'old timing' } } }, { refreshNews: false });
  assert.equal(data.health[0].status, 'unknown');
});
