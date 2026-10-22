import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const tick = () => new Promise(resolve => setImmediate(resolve));
function payload(name, id = 'new') {
  return {engine: {name: `instock-${name.replaceAll('_', '-')}`}, as_of: '2026-10-20',
    snapshot: {snapshot_id: id}, summary: {}, coverage: {}, groups: []};
}
async function page(name, {delayedInit = false, initial} = {}) {
  const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
  const html = readFileSync(`${root}/instock/web/templates/${name}.html`, 'utf8');
  const dom = new JSDOM(html, {url: `http://localhost/mods/${name}`, runScripts: 'outside-only'});
  const {window} = dom, requests = [];
  let context, handler, archive = false, holdEvidence = false, completeEvidence;
  const structure = {error: '', historical: false, days: 5};
  window.requestAnimationFrame = fn => fn();
  window.echarts = {init: () => ({setOption() {}, resize() {}, dispose() {}, on() {},
    isDisposed: () => false, getModel: () => ({getSeriesByIndex: () => null})})};
  window.InStockMarketStructure = () => ({context: () => structure,
    historical() {structure.historical = true;}, refresh() {
      structure.historical = false;
      return holdEvidence ? new Promise(resolve => {completeEvidence = resolve;}) : Promise.resolve();
    }});
  window.InStockMarketEvidence = () => ({context: () => ({}), select() {}});
  window.InStockMarketContinuity = () => ({context: () => ({error: '缺少同日连续性证据'}),
    pending() {}, historical() {}, refresh: async () => {}});
  window.InStockMarketJournal = () => ({live() {archive = false;},
    context: () => archive ? {mode: 'archive', record: {id: 'saved', asOf: '2026-10-01'}} : {mode: 'live'}});
  window.InStockNewmaDesk = {embedded: true, canInvokeAction: () => true,
    setContextProvider(fn) {context = fn;}, publishContext() {}, setUiActionHandler(fn) {handler = fn;},
    invokeAction(id, input) {return new Promise((resolve, reject) => requests.push({id, input, resolve, reject}));}};
  let ready;
  if (delayedInit) {
    const handshake = new Promise(resolve => {ready = resolve;});
    window.InStockNewmaDesk.whenReady = () => handshake;
  }
  window.eval([...window.document.querySelectorAll('script')].find(s => s.textContent.includes('(function ()')).textContent);
  if (delayedInit) {
    assert.equal(requests.length, 0);
    window.document.dispatchEvent(new window.CustomEvent('vibedesk:init'));
    ready(true); await tick();
  }
  requests[0].resolve({ok: true, data: initial || payload(name, 'initial')}); await tick();
  return {dom, window, requests, context: () => context(),
    snapshot: () => (context().data.snapshot || context().data.summary?.snapshot)?.snapshot_id,
    invoke: (input = {}) => handler(`analysis.${name.replaceAll('_', '-')}`, input),
    hold() {holdEvidence = true;}, complete() {completeEvidence();}, archive() {archive = true;}};
}
for (const missing of [false, true]) {
  test(`market map: ${missing ? 'missing' : 'zero'} metrics and daily coverage match Context`, async () => {
    const value = missing ? null : 0;
    const row = {symbol: '600001', name: '测试银行', industry: '银行', market_cap: 1e10,
      price: value, change_pct: value, amount: value, turnover_pct: value, volume_ratio: value};
    const data = {...payload('market_map', 'metrics'), data_source: 'tushare-daily', data_state: 'partial',
      groups: [{name: '银行', stock_count: 1, change_pct: value, items: [row]}],
      summary: {flat: missing ? 0 : 1, unknown_change: missing ? 1 : 0},
      coverage: {unclassified_securities: 43, contributing_rankings: [{source: 'tushare-daily',
        coverage: {frequency: 'daily', realtime: false, listedCount: 5575, quoteCount: 5564,
          missingQuoteCount: 11, note: '缺失原因未核验'}}]}};
    const p = await page('market_map', {initial: data});
    try {
      const doc = p.window.document;
      const cards = [...doc.querySelectorAll('#market-map-detail .desk-detail-card')];
      const values = Object.fromEntries(cards.map(card => [card.querySelector('span').textContent,
        card.querySelector('strong').textContent]));
      assert.equal(values['换手率'], missing ? '--' : '0.00%');
      assert.equal(values['量比'], missing ? '--' : '0.00');
      assert.equal(values['成交额'], missing ? '--' : '0');
      assert.equal(values['最新价'], missing ? '--' : '0.00');
      assert.equal(doc.querySelector('#market-map-detail .desk-score').textContent, missing ? '--' : '0.00%');
      assert.match(doc.getElementById('market-map-flat').textContent, new RegExp(`涨跌缺失 ${missing ? 1 : 0}`));
      const disclosure = doc.getElementById('market-map-rankings').textContent;
      assert.match(disclosure, /日频.*非实时/);
      assert.match(disclosure, /5564\/5575/);
      assert.match(disclosure, /未覆盖 11/);
      assert.match(disclosure, /43.*未分类/);
      assert.equal(p.context().data.summary.selectedSecurity.change_pct, value);
      assert.equal(p.context().data.summary.coverage.contributing_rankings[0].coverage.missingQuoteCount, 11);
    } finally {p.dom.window.close();}
  });
}
test('market map: membership evidence is visible and matches selected Context', async () => {
  const row = {symbol: '601857', name: '中国石油', industry: '石油石化', industry_l2: '炼化及贸易',
    raw_industry: '石油开采', market_cap: 1e10, change_pct: 1, classification_verified: true,
    industry_classification: {source: 'tushare.index_member_all', inDate: '2007-11-01',
      receivedAt: '2026-10-22T09:09:21+08:00', pointInTime: false}};
  const data = {...payload('market_map'), groups: [{name: '石油石化', stock_count: 1, items: [row]}],
    coverage: {verified_l2_securities: 1, unverified_classification_securities: 0, unclassified_securities: 0}};
  const p = await page('market_map', {initial: data});
  try {
    const text = p.window.document.getElementById('market-map-detail').textContent;
    assert.match(text, /石油石化 → 炼化及贸易/);
    assert.match(text, /tushare.index_member_all/);
    assert.match(text, /原始行业标签：石油开采/);
    assert.match(text, /非历史点时/);
    assert.match(p.window.document.getElementById('market-map-rankings').textContent, /证券成员已核验 1/);
    assert.equal(p.context().data.summary.selectedSecurity.classification_verified, true);
    assert.equal(p.context().data.summary.selectedSecurity.industry_classification.inDate, '2007-11-01');
  } finally {p.dom.window.close();}
});

test('market map: session change clears old evidence and old finally does not unlock a new run', async () => {
  const p = await page('market_map');
  try {
    const old = p.invoke(), oldRequest = p.requests.at(-1);
    p.window.document.dispatchEvent(new p.window.CustomEvent('instock:session-changed'));
    assert.equal(p.snapshot(), undefined);
    assert.equal(p.window.document.getElementById('market-map-detail').textContent, '');
    assert.match(p.window.document.getElementById('market-map-meta').textContent, /会话授权已变化/);
    const next = p.invoke(), nextRequest = p.requests.at(-1);
    oldRequest.resolve({ok: true, data: payload('market_map', 'old')});
    await assert.rejects(old, /本次结果未采用/);
    assert.equal(p.context().data.queryState.running, true);
    nextRequest.resolve({ok: true, data: payload('market_map', 'current')}); await next;
    assert.equal(p.snapshot(), 'current');
    assert.equal(p.context().data.queryState.running, false);
  } finally {p.dom.window.close();}
});
for (const name of ['market_map', 'market_workbench']) {
  test(`${name}: first result survives initial Desk handshake`, async () => {
    const p = await page(name, {delayedInit: true});
    try {
      assert.equal(p.requests.length, 1);
      assert.equal(p.snapshot(), 'initial');
      assert.equal(p.context().data.queryState.running, false);
    } finally {p.dom.window.close();}
  });
  test(`${name}: refresh returns the rendered snapshot and propagates failures`, async () => {
    const p = await page(name);
    try {
      assert.equal(p.snapshot(), 'initial');
      assert.throws(() => p.invoke({capacity: 500}), /不接受隐藏输入/);
      const pending = p.invoke();
      await assert.rejects(p.invoke(), /正在运行/);
      assert.equal(p.context().actions[0].available, false);
      p.requests.at(-1).resolve({ok: true, data: payload(name)});
      const result = await pending;
      assert.equal(result.snapshot.snapshot_id, 'new');
      assert.equal(p.snapshot(), 'new');
      const failed = p.invoke(); p.requests.at(-1).reject(new Error('行情不可用'));
      await assert.rejects(failed, /行情不可用/);
      assert.equal(p.context().data.queryState.error, '行情不可用');
      assert.equal(p.context().data.queryState.running, false);
    } finally {p.dom.window.close();}
  });
  test(`${name}: history and scope changes cannot be overwritten by a late refresh`, async () => {
    const p = await page(name);
    try {
      for (const event of ['instock:history-selected', name === 'market_map' ? 'instock:session-changed' : 'vibedesk:init']) {
        const pending = p.invoke();
        p.window.document.dispatchEvent(new p.window.CustomEvent(event,
          {detail: {payload: payload(name, 'historical'), view_source: 'history'}}));
        p.requests.at(-1).resolve({ok: true, data: payload(name, 'late')});
        await assert.rejects(pending, /本次结果未采用/);
        assert.notEqual(p.snapshot(), 'late');
      }
    } finally {p.dom.window.close();}
  });
}
test('market map: industry filter updates the preview and selected Context together', async () => {
  const row = (symbol, industry) => ({symbol, name: symbol, industry, change_pct: 1, market_cap: 1e10});
  const initial = {...payload('market_map'), groups: [
    {name: '电子', stock_count: 1, items: [row('688001', '电子')]},
    {name: '银行', stock_count: 1, items: [row('601398', '银行')]},
  ]};
  const p = await page('market_map', {initial});
  try {
    assert.equal(p.context().selection.security.symbol, '688001');
    const select = p.window.document.getElementById('market-map-industry');
    select.value = '银行'; select.dispatchEvent(new p.window.Event('change'));
    assert.equal(p.context().filters.industry, '银行');
    assert.equal(p.context().selection.security.symbol, '601398');
    assert.match(p.window.document.getElementById('market-map-detail').textContent, /601398/);
    assert.doesNotMatch(p.window.document.getElementById('market-map-detail').textContent, /688001/);
  } finally {p.dom.window.close();}
});
test('market workbench waits for evidence, reports gaps and protects archive view', async () => {
  const p = await page('market_workbench');
  try {
    p.hold();
    const pending = p.invoke(); let settled = false;
    pending.then(() => {settled = true;});
    p.requests.at(-1).resolve({ok: true, data: payload('market_workbench')}); await tick();
    assert.equal(settled, false); assert.equal(p.snapshot(), 'initial');
    p.complete(); const result = await pending;
    assert.match(result.marketContinuity.error, /缺少同日/);
    p.archive();
    assert.equal(p.context().actions.length, 0);
    assert.throws(() => p.invoke(), /正在回看存档/);
    assert.equal(p.context().view.id, 'market-review-archive');
  } finally {p.dom.window.close();}
});

for (const missing of [false, true]) {
  test(`workbench: ${missing ? 'missing' : 'zero'} metrics, source dates and handoff match visible board`, async () => {
    const value = missing ? null : 0;
    const row = {symbol: '600001', name: '测试银行', industry: '银行', scan_as_of: '2026-10-19T15:00:00+08:00',
      price: value, change_pct: value, amount: value, turnover_pct: value, volume_ratio: value, pe: value, pb: 6.7};
    const initial = {...payload('market_workbench'), as_of: '2026-10-20',
      source_dates: {emotion: '2026-10-20', leaderboards: {gainers: '2026-10-19'}},
      failures: [{board: 'amount', error: '全市场成交额榜暂时为空'}],
      leaderboards: {gainers: [row]}, market_emotion: {state: 'available', date: '2026-10-20'},
      sector_basis: {source: 'ranked_scan_sample', sample_sort: 'ranked_boards_union', sample_size: 309}};
    const p = await page('market_workbench', {initial});
    try {
      const doc = p.window.document;
      const text = doc.getElementById('market-body').textContent;
      assert.match(text, missing ? /-- \/ 6\.7/ : /0\.0 \/ 6\.7/);
      const cards = Object.fromEntries([...doc.querySelectorAll('#market-detail .desk-detail-card')]
        .map(card => [card.querySelector('span').textContent, card.querySelector('strong').textContent]));
      assert.equal(cards['换手率'], missing ? '--' : '0.00%');
      assert.equal(cards['量比'], missing ? '--' : '0.00');
      assert.equal(cards['成交额'], missing ? '--' : '0');
      assert.equal(cards['PE / PB'], missing ? '-- / 6.7' : '0.0 / 6.7');
      const link = doc.querySelector('#market-detail a');
      assert.equal(new URL(link.href).searchParams.get('asOf'), '2026-10-19');
      assert.match(doc.getElementById('market-board-scope').textContent, /2026-10-19/);
      assert.match(doc.getElementById('market-review-asof').textContent, /情绪 2026-10-20/);
      assert.match(doc.getElementById('market-sector-note').textContent, /多榜合并/);
      assert.equal(p.context().data.sourceDates.emotion, '2026-10-20');
      assert.equal(p.context().data.selectedSecurity.pe, value);
      assert.equal(p.context().data.failures[0].board, 'amount');
      assert.match(doc.getElementById('market-source-failures').textContent, /成交额榜.*暂时为空/);
    } finally {p.dom.window.close();}
  });
}

test('workbench: undated old snapshot does not pass the overview date as a stock cutoff', async () => {
  const initial = {...payload('market_workbench'), leaderboards: {gainers: [{symbol: '600001', name: '旧样本'}]}};
  const p = await page('market_workbench', {initial});
  try {
    const doc = p.window.document;
    assert.equal(new URL(doc.querySelector('#market-detail a').href).searchParams.has('asOf'), false);
    assert.match(doc.getElementById('market-board-scope').textContent, /日期未核验/);
  } finally {p.dom.window.close();}
});

test('workbench: refresh replaces selected metrics; empty board clears preview and Context', async () => {
  const row = {symbol: '600001', name: '测试银行', pe: 5};
  const p = await page('market_workbench', {initial: {...payload('market_workbench'), leaderboards: {gainers: [row]}}});
  try {
    const pending = p.invoke();
    p.requests.at(-1).resolve({ok: true, data: {...payload('market_workbench'), leaderboards: {gainers: [{...row, pe: 8}]}}});
    await pending;
    assert.equal(p.context().data.selectedSecurity.pe, 8);
    p.window.document.querySelector('[data-board="amount"]').click();
    assert.equal(p.context().selectedSecurity, null);
    assert.doesNotMatch(p.window.document.getElementById('market-detail').textContent, /测试银行/);
  } finally {p.dom.window.close();}
});
