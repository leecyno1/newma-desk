import assert from 'node:assert/strict';
import test from 'node:test';
import { synthesize, generateIdeas } from '../../dashboard/inject.mjs';
import { energySnapshot } from '../../dashboard/energy.mjs';
import { generateLLMIdeas } from '../../lib/llm/ideas.mjs';
import { computeDelta } from '../../lib/delta/engine.mjs';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const now = new Date('2026-11-14T12:00:00Z');
const spot = (value = 80, period = '2026-11-13', history = []) => energySnapshot({
  oilPrices: { wti: { value, period, recent: history } },
});
const future = (value = 80, observedAt = '2026-11-13T20:00:00Z') => energySnapshot({}, {
  'CL=F': { price: value, currency: 'USD', observedAt },
});
const changes = delta => [...delta.signals.escalated, ...delta.signals.deescalated];
async function prompt(energy, delta) {
  let context;
  await generateLLMIdeas({ isConfigured: true, async complete(_system, user) {
    context = user;
    return { text: '[{"title":"Synthetic QA","type":"WATCH","confidence":"LOW"}]' };
  } }, { energy }, delta);
  return context;
}
const clock = t => t.mock.timers.enable({ apis: ['Date'], now });

test('energy model input preserves kind, source, date and thousand-barrel inventory units', async t => {
  clock(t);
  const energy = energySnapshot({ oilPrices: { wti: { value: 80, period: '2026-11-13' } },
    inventories: { crudeStocks: { value: 420000, period: '2026-11-06' } } });
  const text = await prompt(energy);
  assert.match(text, /wti=80 美元\/桶.*spot.*2026-11-13.*EIA.*RWTC/);
  assert.match(text, /crudeStocks=420000 千桶.*inventory.*2026-11-06/);
  assert.doesNotMatch(text, /\$null|nullbbl|420000bbl/);
  assert.match(await prompt(future()), /wti=80 美元\/桶.*futures.*2026-11-13T20:00:00Z.*CL=F/);
});

for (const [name, energy] of [
  ['legacy scalar', { wti: 987654 }], ['stale spot', spot(987654, '2026-10-01')],
  ['future observation', future(987654, '2026-11-15T00:00:00Z')],
  ['undated quote', future(987654, null)],
  ['unknown unit', energySnapshot({}, { 'CL=F': { price: 987654, currency: 'EUR', observedAt: now.toISOString() } })],
]) {
  test(`${name} cannot become a current energy model observation`, async t => {
    clock(t);
    const text = await prompt(energy);
    assert.match(text, /wti=unavailable/);
    assert.doesNotMatch(text, /987654/);
  });
}

test('FRED forwarding of the original EIA series and real zero inventory remain valid', async t => {
  clock(t);
  const energy = energySnapshot({ oilPrices: { wti: { value: -1, period: '2026-11-13',
    source: { id: 'FRED-public', seriesId: 'DCOILWTICO', originalSeriesId: 'RWTC' } } },
  inventories: { crudeStocks: { value: 0, period: '2026-11-06' } } });
  assert.match(await prompt(energy), /wti=-1 美元\/桶.*FRED-public.*DCOILWTICO/);
  assert.match(await prompt(energy), /crudeStocks=0 千桶/);
});

test('dated spot momentum is independent of array order and remains an observation, not a long recommendation', async () => {
  const data = await synthesize({ sources: {} }, { refreshNews: false });
  const history = [{ period: '2026-11-12', value: 70 }, { period: '2026-11-13', value: 80 }];
  for (const points of [history, [...history].reverse()]) {
    const idea = generateIdeas({ ...data, energy: spot(80, '2026-11-13', points) }, { now })
      .find(row => /Oil Momentum/.test(row.title));
    assert.ok(idea);
    assert.equal(idea.type, 'watch');
    assert.match(idea.text, /2026-11-12.*2026-11-13.*\+14\.3%/);
  }
});

test('zero baseline, conflicting history, terminal mismatch and undated values do not create momentum', async () => {
  const data = await synthesize({ sources: {} }, { refreshNews: false });
  for (const history of [
    [{ period: '2026-11-12', value: 0 }, { period: '2026-11-13', value: 80 }],
    [{ period: '2026-11-12', value: -70 }, { period: '2026-11-13', value: 80 }],
    [{ period: '2026-11-12', value: 70 }, { period: '2026-11-12', value: 60 }, { period: '2026-11-13', value: 80 }],
    [{ period: '2026-11-12', value: 70 }, { period: '2026-11-13', value: 90 }],
    [{ value: 70 }, { value: 80 }],
  ]) {
    assert.ok(!generateIdeas({ ...data, energy: spot(80, '2026-11-13', history) }, { now })
      .some(row => /Oil Momentum|Oil Under Pressure/.test(row.title)));
  }
});

test('bounded OSINT plus a high oil price does not establish a causal long', async () => {
  const data = await synthesize({ sources: {} }, { refreshNews: false });
  const idea = generateIdeas({ ...data, tg: { status: 'ok', scope: { channels: ['synthetic'], limit: 15 },
    collectedAt: now.toISOString(), urgent: Array.from({ length: 4 }, () => ({ text: 'sample' })) },
    energy: spot() }, { now }).find(row => /Conflict.*Energy/.test(row.title));
  assert.ok(idea);
  assert.equal(idea.type, 'watch');
  assert.match(idea.text, /not establish|not prove/i);
});

test('energy delta rejects spot/futures switches, stale/undated values and same-date revisions', t => {
  clock(t);
  for (const [previous, current] of [[spot(70), future()], [future(70, null), future()],
    [spot(70, '2026-10-01'), spot()], [spot(70), spot()]]) {
    const delta = computeDelta({ energy: current }, { energy: previous });
    assert.deepEqual(changes(delta), []);
    assert.ok(delta.comparisonGaps.some(row => row.key === 'wti'));
  }
});

test('dated same-basis energy delta carries provenance and survives model filtering', async t => {
  clock(t);
  const energy = spot(), delta = computeDelta({ energy }, { energy: spot(70, '2026-11-12') });
  const entry = changes(delta).find(row => row.key === 'wti');
  assert.equal(entry.fromDate, '2026-11-12');
  assert.equal(entry.toDate, '2026-11-13');
  assert.equal(entry.unit, '美元/桶');
  assert.equal(entry.energyBasis.kind, 'spot');
  assert.match(await prompt(energy, delta), /ESCALATED:.*70 → 80.*2026-11-12 → 2026-11-13/);
});

test('legacy or mismatched energy delta cannot bypass current model validation', async t => {
  clock(t);
  const legacy = { summary: { direction: 'risk-off' }, signals: { escalated: [
    { key: 'wti', label: 'WTI', from: 70, to: 987654 },
  ] } };
  assert.doesNotMatch(await prompt(spot(), legacy), /987654|direction=risk-off/);
});

test('selected spot and own futures chart history both run oldest to newest', () => {
  const points = [{ period: '2026-11-13', value: 80 }, { period: '2026-11-12', value: 70 }];
  assert.deepEqual(spot(80, '2026-11-13', points).wtiRecent, [70, 80]);
  const energy = energySnapshot({ oilPrices: { wti: { value: 80, period: '2026-11-13', recent: points } } }, {
    'CL=F': { price: 90, currency: 'USD', observedAt: now.toISOString(),
      history: [{ date: '2026-11-12', close: 85 }, { date: '2026-11-13', close: 88 }] },
  });
  assert.deepEqual(energy.wtiRecent, [85, 88]);
  assert.deepEqual(energy.observations[0].history, []); // Daily futures closes are not intraday quotes.
});

test('native energy cards show missing values, real zero, kind and original evidence without inventing USD', () => {
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const start = html.indexOf('function energyMetricCards('), end = html.indexOf('\nfunction deltaStateText(', start);
  assert.ok(start >= 0 && end > start);
  const render = vm.runInNewContext(`${html.slice(start, end)}; energyMetricCards`);
  assert.equal(render({ wti: 987654 })[0].v, '--');
  assert.equal(render(spot(0))[0].v, '0');
  assert.match(render(spot())[0].s, /美元\/桶.*2026-11-13.*EIA\/RWTC/);
  assert.match(render(future())[0].l, /futures/);
  assert.equal(render(energySnapshot({}, { 'CL=F': { price: 80, currency: 'EUR' } }))[0].v, '--');
});

test('nonpositive energy delta retains absolute movement without an invented relative return', async t => {
  clock(t);
  const energy = spot(80), delta = computeDelta({ energy }, { energy: spot(-1, '2026-11-12') });
  assert.equal(changes(delta)[0].pctChange, null);
  const text = await prompt(energy, delta);
  assert.match(text, /-1 → 80.*\+81.*relative unavailable/);
  assert.doesNotMatch(text, /8100/);
});

test('same quote timestamp is unchanged only at the same price; own later quote carries roll caveat', async t => {
  clock(t);
  const energy = future(80), delta = computeDelta({ energy }, { energy: future(70, '2026-11-12T20:00:00Z') });
  assert.match(await prompt(energy, delta), /ESCALATED:.*continuous futures may roll/);
  assert.ok(computeDelta({ energy }, { energy }).signals.unchanged.includes('wti'));
  const revised = computeDelta({ energy }, { energy: future(70) });
  assert.deepEqual(changes(revised), []);
  assert.ok(revised.comparisonGaps.some(row => row.key === 'wti'));
});
