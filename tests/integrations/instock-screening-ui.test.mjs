import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const tick = () => new Promise(resolve => setImmediate(resolve));
const screens = [
  {file: 'technical_signals', action: 'analysis.technical-signals', prefix: 'signal', engine: 'instock-technical-signal-center'},
  {file: 'stock_candidates', action: 'analysis.stock-candidates', prefix: 'candidate', engine: 'instock-stock-candidate-engine'},
];
function fixture(screen, id = 'new') {
  return {engine: {name: screen.engine}, as_of: '2026-10-20', snapshot: {snapshot_id: id},
    summary: {candidate_count: 0}, coverage: {}, rows: [], candidates: [], data_state: 'partial'};
}
async function page(screen, {delayedInit = false, embedded = true} = {}) {
  const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
  const html = readFileSync(`${root}/instock/web/templates/${screen.file}.html`, 'utf8');
  const dom = new JSDOM(html, {url: `http://localhost/mods/${screen.file}`, runScripts: 'outside-only'});
  const {window} = dom;
  let context, handler;
  const requests = [];
  window.echarts = {init: () => ({setOption() {}, resize() {}, dispose() {}})};
  window.InStockNewmaDesk = {embedded, canInvokeAction: () => embedded,
    setContextProvider(fn) {context = fn;}, publishContext() {}, setUiActionHandler(fn) {handler = fn;},
    invokeAction(id, input) {return new Promise((resolve, reject) => requests.push({id, input, resolve, reject}));},
    fetchAnalysis(url) {return new Promise((resolve, reject) => requests.push({url, reject,
      resolve(body) {resolve({ok: true, json: async () => body});}}));}};
  let ready;
  if (delayedInit) {
    const handshake = new Promise(resolve => {ready = resolve;});
    window.InStockNewmaDesk.whenReady = () => handshake;
  }
  const script = [...window.document.querySelectorAll('script')].find(item => item.textContent.includes('(function ()'));
  window.eval(script.textContent);
  if (delayedInit) {
    assert.equal(requests.length, 0);
    window.document.dispatchEvent(new window.CustomEvent('vibedesk:init'));
    ready(true); await tick();
  }
  requests[0].resolve({ok: true, data: fixture(screen, 'initial')}); await tick();
  return {dom, window, requests, context: () => context(), invoke: (input = {}) => handler(screen.action, input)};
}
for (const embedded of [false, true]) test(`stock_candidates ${embedded ? 'Desk' : 'standalone'}: table and context retain missing, zero and negative scan valuation`, async () => {
  const p = await page(screens[1], {embedded});
  try {
    const pending = p.invoke();
    const data = fixture(screens[1], 'nullable-valuation');
    data.candidates = [
      {pe: null, pb: null}, {pe: 0, pb: 0}, {pe: -10, pb: -2}, {pe: 18, pb: 2},
    ].map((values, index) => ({...values, rank: index + 1, symbol: `00000${index + 1}`, name: `口径${index}`,
      market: 'CN', industry: '银行', score: 50, status: '观察', metrics: {momentum_20_pct: 1},
      classic_signals: [], history_bars: 120, technical_confidence: 1, history_mode: 'full',
      history_source: 'sina-unadjusted', history_adjust: 'none', history_has_more: false,
      fundamentals: {}, risks: ['扫描估值口径待核验']}));
    p.requests.at(-1).resolve({ok: true, data});
    await pending;
    const rows = [...p.window.document.querySelectorAll('#candidate-body tr')];
    assert.deepEqual(rows.map(row => row.cells[8].textContent), ['-- / --', '0.0 / 0.0', '-10.0 / -2.0', '18.0 / 2.0']);
    assert.equal(p.context().data.selectedCandidate.pe, null);
    assert.equal(p.context().data.selectedCandidate.history_adjust, 'none');
    assert.match(p.window.document.getElementById('candidate-detail').textContent, /sina-unadjusted · 未复权/);
    assert.match(p.window.document.getElementById('candidate-detail').textContent, /不代表全部上市历史/);
    const note = p.window.document.getElementById('candidate-valuation-note').textContent;
    assert.match(note, /旧引擎历史中的 0 可能由缺失归零/);
    assert.equal(p.context().data.scanValuationNote, note);
    rows[1].click();
    assert.equal(p.context().data.selectedCandidate.pe, 0);
    rows[2].click();
    assert.equal(p.context().data.selectedCandidate.pe, -10);
  } finally {p.dom.window.close();}
});
for (const screen of screens) for (const embedded of [false, true]) test(`${screen.file} ${embedded ? 'Desk' : 'standalone'}: unknown adjustment remains visible and reaches Agent`, async () => {
  const p = await page(screen, {embedded});
  try {
    const pending = p.invoke();
    const data = fixture(screen, 'unknown-adjustment');
    const row = {rank: 1, symbol: '000001', name: '口径核验', market: 'CN', industry: '银行',
      score: 50, technical_score: 50, status: '观察', bias: 'neutral', history_bars: 120,
      history_mode: 'full', technical_confidence: 1, history_source: 'test-http', history_adjust: 'unknown',
      metrics: {momentum_20_pct: 1}, indicators: {}, indicator_signals: {buy: [], sell: []}, patterns: [],
      classic_signals: [], classic_strategies: [], fundamentals: {}, risks: ['复权口径未知，需复核']};
    data.rows = [row]; data.candidates = [row];
    data.coverage = {analyzed_count: 1, unadjusted_history_count: 0, unknown_adjustment_history_count: 1};
    data.limitations = ['price_history_adjustment_requires_review'];
    data.evidence_quality = {items: [{id: 'price_history', label: '日线覆盖', state: 'partial', detail: '口径未知 1 只'}]};
    p.requests.at(-1).resolve({ok: true, data});
    await pending;
    assert.match(p.window.document.getElementById(`${screen.prefix}-detail`).textContent, /复权口径未知/);
    const context = p.context().data;
    assert.equal((context.selectedCandidate || context.selectedSignal).history_adjust, 'unknown');
    assert.equal(context.coverage.unknown_adjustment_history_count, 1);
    assert.equal(context.coverage.unadjusted_history_count, 0);
    assert.equal(context.dataState, 'partial');
  } finally {p.dom.window.close();}
});

test('technical_signals: Agent exclusion evidence matches the visible table and preserves full counts', async () => {
  const p = await page(screens[0]);
  try {
    const pending = p.invoke();
    const data = fixture(screens[0], 'large-exclusion');
    data.excluded_by_rules = Array.from({length: 1263}, (_, index) => ({
      symbol: String(600000 + index), name: `候选${index}`, market: 'CN',
      stage: 'market_prefilter', reasons: ['成交额不足'],
    }));
    data.coverage.excluded_by_rules_count = 1263;
    p.requests.at(-1).resolve({ok: true, data});
    await pending;
    const context = p.context().data;
    assert.equal(p.window.document.getElementById('signal-excluded-body').children.length, 200);
    assert.equal(context.excludedByRules.length, 200);
    assert.equal(context.excludedByRulesTotal, 1263);
    assert.equal(context.excludedByRulesOmitted, 1063);
    assert.equal(context.coverage.excluded_by_rules_count, 1263);
    assert.equal(context.excludedByRules[199].symbol, '600199');
    assert.match(p.window.document.getElementById('signal-excluded-note').textContent, /1263.*200/);
    assert.equal(data.excluded_by_rules.length, 1263, 'do not truncate the analysis result');
  } finally {p.dom.window.close();}
});
test('technical_signals: preset updates show stale result notice after all controls change', async () => {
  const p = await page(screens[0]);
  try {
    const preset = p.window.document.getElementById('signal-preset');
    const notice = p.window.document.getElementById('screen-query-status');
    preset.value = 'trend_breakout';
    preset.dispatchEvent(new p.window.Event('change'));
    assert.equal(p.context().filters.universeSize, 100);
    assert.equal(p.context().filters.minTechnicalScore, 65);
    assert.equal(p.context().data.queryState.resultMatchesCurrentFilters, false);
    assert.equal(notice.hidden, false);
    assert.match(notice.textContent, /尚未按当前条件重算/);
    assert.equal(p.context().data.snapshot.snapshot_id, 'initial');
    const pending = p.invoke();
    assert.equal(p.requests.at(-1).input.requiredStrategies, 'breakthrough_platform');
    p.requests.at(-1).resolve({ok: true, data: fixture(screens[0], 'preset')});
    await pending;
    assert.equal(notice.hidden, true);
  } finally {p.dom.window.close();}
});
for (const screen of screens) {
  test(`${screen.file}: changed filters visibly mark retained results until successful rerun`, async () => {
    const p = await page(screen);
    try {
      const notice = p.window.document.getElementById('screen-query-status');
      assert.ok(notice, 'visible query status must exist');
      assert.equal(notice.hidden, true);
      const control = p.window.document.getElementById(`${screen.prefix}-universe`);
      const original = control.value;
      control.value = '30'; control.dispatchEvent(new p.window.Event('change'));
      assert.equal(notice.hidden, false);
      assert.match(notice.textContent, /尚未按当前条件重算/);
      assert.equal(p.context().data.queryState.resultMatchesCurrentFilters, false);
      assert.equal(p.context().data.snapshot.snapshot_id, 'initial');
      control.value = original; control.dispatchEvent(new p.window.Event('change'));
      assert.equal(notice.hidden, true);
      control.value = '30'; control.dispatchEvent(new p.window.Event('change'));
      const pending = p.invoke();
      assert.match(notice.textContent, /正在计算.*上次结果/);
      p.requests.at(-1).reject(new Error('上游暂不可用'));
      await assert.rejects(pending, /上游暂不可用/);
      assert.match(notice.textContent, /尚未按当前条件重算/);
      const retry = p.invoke();
      p.requests.at(-1).resolve({ok: true, data: fixture(screen, 'matched')});
      await retry;
      assert.equal(notice.hidden, true);
      assert.equal(p.context().data.queryState.resultMatchesCurrentFilters, true);
    } finally {p.dom.window.close();}
  });
  test(`${screen.file}: daily scan date and missing coverage stay visible and reach Agent`, async () => {
    const p = await page(screen);
    try {
      const pending = p.invoke();
      const data = fixture(screen);
      data.coverage.scan_observations = [{market: 'CN', source: 'tushare-daily', frequency: 'daily', realtime: false,
        as_of: '2026-10-19T15:00:00+08:00', listed_count: 5575, quote_count: 5564, missing_quote_count: 11,
        note: '缺失原因未核验'}];
      p.requests.at(-1).resolve({ok: true, data});
      await pending;
      const panel = p.window.document.getElementById('scan-observations');
      assert.equal(panel.hidden, false);
      assert.match(panel.textContent, /日频 \/ 非实时.*2026-10-19.*5564\/5575.*未覆盖 11/);
      assert.deepEqual(JSON.parse(JSON.stringify(p.context().data.coverage.scan_observations)), data.coverage.scan_observations);
      const refresh = p.invoke();
      p.requests.at(-1).resolve({ok: true, data: fixture(screen, 'other-source')});
      await refresh;
      assert.equal(panel.hidden, true);
      assert.equal(panel.textContent, '');
    } finally {p.dom.window.close();}
  });
  test(`${screen.file}: partial market scan is visible and reaches Agent context`, async () => {
    const p = await page(screen);
    try {
      const pending = p.invoke();
      const data = fixture(screen);
      data.coverage = {scan_failed_count: 1, scan_skipped_count: 10,
        scan_failures: [{market: 'CN', sort: 'amount', order: 'desc', error: '行情源不可用', skipped_axes: 10}]};
      data.limitations = ['partial_market_scan_coverage'];
      p.requests.at(-1).resolve({ok: true, data});
      await pending;
      assert.deepEqual(JSON.parse(JSON.stringify(p.context().data.coverage)), data.coverage);
      assert.match(p.window.document.getElementById(`${screen.prefix}-meta`).textContent, /扫描失败 1.*未执行 10/);
      assert.match(p.window.document.getElementById(`${screen.prefix}-meta`).textContent, /覆盖不完整/);
      if (screen.prefix === 'signal') {
        assert.match(p.window.document.getElementById('signal-detail').textContent, /不能据此判断整个市场/);
      }
    } finally {p.dom.window.close();}
  });
  test(`${screen.file}: first result survives initial Desk handshake`, async () => {
    const p = await page(screen, {delayedInit: true});
    try {
      assert.equal(p.requests.length, 1);
      assert.equal(p.context().data.snapshot?.snapshot_id, 'initial');
      assert.equal(p.context().data.queryState.resultMatchesCurrentFilters, true);
    } finally {p.dom.window.close();}
  });
  test(`${screen.file}: host uses visible filters, waits, and rejects busy/hidden overrides`, async () => {
    const p = await page(screen);
    try {
      const control = p.window.document.getElementById(`${screen.prefix}-min-amount`);
      control.value = '5'; control.dispatchEvent(new p.window.Event('input'));
      assert.equal(p.context().data.queryState.resultMatchesCurrentFilters, false);
      assert.throws(() => p.invoke({minAmount: 1}), /不接受隐藏输入/);
      const pending = p.invoke();
      assert.equal(p.requests[1].input.minAmount, 500000000);
      assert.equal(p.requests[1].input.refresh, '1');
      assert.equal(p.context().data.queryState.running, true);
      assert.equal(p.context().actions[0].available, false);
      await assert.rejects(p.invoke(), /正在运行/);
      p.requests[1].resolve({ok: true, data: fixture(screen)});
      const result = await pending;
      assert.equal(result.snapshot.snapshot_id, 'new');
      assert.equal(p.context().data.snapshot.snapshot_id, 'new');
      assert.equal(p.context().data.queryState.resultMatchesCurrentFilters, true);
      assert.equal(p.context().data.queryState.running, false);
    } finally {p.dom.window.close();}
  });
  test(`${screen.file}: failure reaches host and page without claiming a fresh result`, async () => {
    const p = await page(screen);
    try {
      const pending = p.invoke();
      p.requests[1].reject(new Error('数据源断开'));
      await assert.rejects(pending, /数据源断开/);
      assert.equal(p.context().data.snapshot.snapshot_id, 'initial');
      assert.equal(p.context().data.queryState.error, '数据源断开');
      assert.match(p.window.document.getElementById(`${screen.prefix}-alert`).textContent, /数据源断开/);
      assert.equal(p.window.document.getElementById(`${screen.prefix}-run`).disabled, false);
    } finally {p.dom.window.close();}
  });
  test(`${screen.file}: edits, history selection and scope changes reject late results`, async () => {
    const p = await page(screen);
    try {
      for (const event of ['input', 'instock:history-selected', 'vibedesk:init']) {
        const pending = p.invoke();
        const request = p.requests.at(-1);
        if (event === 'input') {
          const control = p.window.document.getElementById(`${screen.prefix}-min-amount`);
          control.value = '7'; control.dispatchEvent(new p.window.Event('input'));
        } else p.window.document.dispatchEvent(new p.window.CustomEvent(event,
          {detail: {payload: fixture(screen, 'history'), view_source: 'history'}}));
        request.resolve({ok: true, data: fixture(screen, 'late')});
        await assert.rejects(pending, /本次结果未采用/);
        assert.notEqual(p.context().data.snapshot.snapshot_id, 'late');
        assert.equal(p.context().data.queryState.running, false);
      }
    } finally {p.dom.window.close();}
  });
}
