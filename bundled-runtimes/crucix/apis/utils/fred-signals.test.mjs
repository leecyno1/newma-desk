import assert from 'node:assert/strict';
import test from 'node:test';
import { briefing } from '../sources/fred.mjs';
import { synthesize, generateIdeas } from '../../dashboard/inject.mjs';
import { generateLLMIdeas } from '../../lib/llm/ideas.mjs';

const now = new Date('2026-11-14T12:00:00Z');
const observation = (id, value, date = '2026-11-13') => ({ id, value, date });
const base = () => synthesize({ sources: {} }, { refreshNews: false });
const ideasFor = async fred => generateIdeas({ ...await base(), fred }, { now });

for (const value of [null, undefined, NaN, Infinity, '0.25']) {
  test(`unknown or invalid spread (${String(value)}) does not throw or invent a curve signal`, async () => {
    const ideas = await ideasFor([observation('T10Y2Y', value)]);
    assert.deepEqual(ideas, []);
  });
}

test('missing VIX cannot become low volatility and missing HY cannot become tight credit', async () => {
  assert.deepEqual(await ideasFor([observation('VIXCLS', null), observation('BAMLH0A0HYM2', 6)]), []);
  const ideas = await ideasFor([observation('VIXCLS', 35), observation('BAMLH0A0HYM2', null)]);
  assert.ok(ideas.some(row => row.title === 'Elevated Volatility Regime'));
  assert.ok(!ideas.some(row => /Credit|Safe Haven/.test(row.title)));
});

test('flat spread is not inversion and a positive observation is not proof of normalization', async () => {
  const flat = await ideasFor([observation('T10Y2Y', 0)]);
  assert.equal(flat[0].title, 'Flat Yield Curve');
  assert.match(flat[0].text, /2026-11-13.*0\.00/);
  assert.doesNotMatch(JSON.stringify(flat), /Inverted|Normalizing|Recession signal fading/);
  const positive = await ideasFor([observation('T10Y2Y', 0.5)]);
  assert.equal(positive[0].title, 'Positive Yield Spread');
  assert.doesNotMatch(JSON.stringify(positive), /Normalizing|Steepening|Recession signal fading/);
  assert.equal((await ideasFor([observation('T10Y2Y', -0.5)]))[0].title, 'Yield Curve Inverted');
});

test('old, future, missing and invalid observation dates cannot drive current suggestions', async () => {
  for (const date of ['2026-11-06', '2026-11-15', null, '2026-02-30', 'bad-date']) {
    assert.deepEqual(await ideasFor([observation('T10Y2Y', -1, date), observation('VIXCLS', 45, date),
      observation('BAMLH0A0HYM2', 6, date)]), [], String(date));
  }
  assert.ok((await ideasFor([observation('T10Y2Y', -1, '2026-11-07')])).length > 0);
});

test('cross-market comparisons require the same observation date', async () => {
  const mismatched = await ideasFor([observation('VIXCLS', 10), observation('BAMLH0A0HYM2', 6, '2026-11-12')]);
  assert.deepEqual(mismatched, []);
  const aligned = await ideasFor([observation('VIXCLS', 10), observation('BAMLH0A0HYM2', 6)]);
  assert.equal(aligned[0].title, 'Credit Stress Ignored by Equity Vol');
  assert.match(aligned[0].text, /2026-11-13/);
});

test('collector retains old observations but does not issue current alerts from them', async t => {
  t.mock.timers.enable({ apis: ['Date'], now });
  let date = '2026-10-01';
  t.mock.method(globalThis, 'fetch', async url => {
    const id = new URL(url).searchParams.get('series_id');
    const value = ['T10Y2Y', 'T10Y3M'].includes(id) ? '-1' : id === 'VIXCLS' ? '45' : '6';
    return Response.json({ observations: [{ date, value }] });
  });
  const old = await briefing('synthetic-key');
  assert.equal(old.indicators.find(row => row.id === 'VIXCLS').value, 45);
  assert.deepEqual(old.signals, []);
  date = '2026-11-13';
  assert.equal((await briefing('synthetic-key')).signals.length, 5);
});

test('actual model context keeps dates and zero, excludes old values, and respects weekly mortgage cadence', async t => {
  t.mock.timers.enable({ apis: ['Date'], now });
  let context, rules;
  const provider = { isConfigured: true, async complete(system, user) {
    rules = system; context = user;
    return { text: JSON.stringify([{ title: 'Synthetic QA only', type: 'WATCH', ticker: 'TEST',
      confidence: 'LOW', rationale: 'Not a real investment idea', risk: 'Synthetic', horizon: 'Days' }]) };
  } };
  await generateLLMIdeas(provider, { fred: [observation('VIXCLS', 0),
    observation('DGS10', 987.65, '2026-10-01'), observation('DFF', null),
    observation('MORTGAGE30US', 6, '2026-11-02')] }, null);
  assert.match(context, /VIXCLS=0.*2026-11-13/);
  assert.doesNotMatch(context, /987\.65|DFF=null/);
  assert.match(context, /DGS10=unavailable/);
  assert.match(context, /MORTGAGE30US=6.*2026-11-02/);
  assert.match(context, /7.*14.*calendar days/i);
  assert.match(rules, /fewer.*ideas|abstain/i);
});
