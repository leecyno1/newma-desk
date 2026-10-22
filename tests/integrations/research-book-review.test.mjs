import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
const html = readFileSync(`${root}/instock/web/templates/research_book.html`, 'utf8');
const script = readFileSync(`${root}/instock/web/static/js/research-book.js`, 'utf8');

function page({invokeAction} = {}) {
  const dom = new JSDOM(html, {url: 'http://localhost/mods/research-book', runScripts: 'outside-only'});
  const {window} = dom;
  let context, uiAction, selection;
  window.InStockNewmaDesk = {embedded: false, setContextProvider(fn) {context = fn;}, publishContext() {},
    setUiActionHandler(fn) {uiAction = fn;}, subscribe(fn) {selection = fn;},
    canInvokeAction: () => Boolean(invokeAction), invokeAction};
  window.HTMLElement.prototype.scrollIntoView = function () {};
  window.eval(script);
  return {dom, window, context: () => context().data, fullContext: () => context(),
    select: (value, source = 'instock-company') => selection({event: 'security.selected', source, payload: value}),
    invokeUi: (id, input = {}) => uiAction(id, input),
    text: id => window.document.getElementById(id).textContent,
    render(payload) {window.document.dispatchEvent(new window.CustomEvent('instock:history-selected', {
      detail: {module_id: 'research-book', payload},
    }));}};
}

function edit(p, values) {
  for (const [id, value] of Object.entries(values)) {
    const field = p.window.document.getElementById(id); field.value = value;
    field.dispatchEvent(new p.window.Event('input'));
  }
}
function addObservation(p) {
  edit(p, {'book-symbol': '300502', 'book-stock-name': '测试公司', 'book-sector': '通信',
    'book-thesis': '非真实投资观察', 'book-invalidation': '验收条件', 'book-weight-input': '25'});
  p.window.document.getElementById('book-add').click();
}

test('Agent reads current name, cutoff and unsaved editor separately from the draft and history', () => {
  const p = page();
  try {
    addObservation(p);
    edit(p, {'book-name': '未检查组合', 'book-date': '2026-10-21', 'book-symbol': '600519',
      'book-stock-name': '未加入公司', 'book-thesis': '尚未加入的理由'});
    assert.equal(p.fullContext().filters.name, '未检查组合');
    assert.equal(p.fullContext().filters.asOf, '2026-10-21');
    assert.equal(p.context().draftItems.length, 1);
    assert.equal(p.context().editor.symbol, '600519');
    assert.equal(p.context().editor.thesis, '尚未加入的理由');
    assert.equal(p.context().editor.mode, 'new');
    p.render(payload());
    assert.equal(p.context().name, '验收组合');
    assert.equal(p.fullContext().filters.name, '未检查组合');
    assert.equal(p.context().editor.symbol, '600519');
    p.window.document.querySelector('#book-draft button').click();
    assert.equal(p.context().editor.mode, 'editing');
    assert.equal(p.context().editor.index, 0);
    p.window.document.getElementById('book-cancel').click();
    assert.equal(p.context().editor.symbol, '');
    assert.equal(p.context().draftItems.length, 1);
  } finally {p.dom.window.close();}
});

test('running and failed checks agree with Agent action availability and preserve draft', async () => {
  let reject;
  const p = page({invokeAction: () => new Promise((_, fail) => {reject = fail;})});
  try {
    addObservation(p);
    const request = p.invokeUi('analysis.research-book');
    assert.equal(p.context().status, 'running');
    assert.equal(p.fullContext().actions[0].available, false);
    await assert.rejects(p.invokeUi('analysis.research-book'), /仍在检查/);
    reject(new Error('验收服务不可用'));
    await assert.rejects(request, /验收服务不可用/);
    assert.equal(p.context().status, 'error');
    assert.match(p.context().error, /验收服务不可用/);
    assert.equal(p.fullContext().actions[0].available, true);
    assert.equal(p.context().draftItems.length, 1);
  } finally {p.dom.window.close();}
});

test('late checks cannot restore old results or unlock the replacement check', async () => {
  const pending = [];
  const p = page({invokeAction: () => new Promise((resolve, reject) => pending.push({resolve, reject}))});
  try {
    addObservation(p);
    const old = p.invokeUi('analysis.research-book');
    edit(p, {'book-name': '新组合'});
    const next = p.invokeUi('analysis.research-book');
    pending[0].resolve({ok: true, data: payload()});
    await assert.rejects(old, /组合或工作区已变化/);
    assert.equal(p.context().status, 'running');
    assert.equal(p.fullContext().actions[0].available, false);
    pending[1].resolve({ok: true, data: {...payload(), name: '新组合'}});
    await next;
    assert.equal(p.context().status, 'checked');
    assert.equal(p.context().name, '新组合');
    assert.equal(p.fullContext().actions[0].available, true);
  } finally {p.dom.window.close();}
});

test('security events reject explicit non-stocks and update editor without adding a position', () => {
  const p = page();
  try {
    edit(p, {'book-symbol': '300502'});
    for (const assetType of ['etf', 'fund', 'future', 'index', 'bond', 'other']) {
      p.select({symbol: '512800', market: 'CN', assetType});
    }
    p.select({symbol: '600519', market: 'HK', assetType: 'stock'});
    p.select({symbol: '600519', market: 'CN'}, 'instock-research-book');
    assert.equal(p.window.document.getElementById('book-symbol').value, '300502');
    p.select({symbol: '600519', market: 'CN', assetType: 'equity', name: '股票观察', sector: '食品饮料'});
    assert.equal(p.context().editor.symbol, '600519');
    assert.equal(p.context().draftItems.length, 0);
    assert.equal(p.window.localStorage.length, 0);
  } finally {p.dom.window.close();}
});

test('a late failed check cannot publish errors or old draft into a different workspace', async () => {
  let reject;
  const p = page({invokeAction: () => new Promise((_, fail) => {reject = fail;})});
  try {
    addObservation(p);
    const old = p.invokeUi('analysis.research-book');
    Object.assign(p.window.InStockNewmaDesk, {embedded: true, config: {user: {id: 'u'}, workspace: {id: 'next'}}});
    p.window.document.dispatchEvent(new p.window.Event('vibedesk:init'));
    reject(new Error('旧范围检查失败'));
    await assert.rejects(old, /旧范围检查失败/);
    assert.equal(p.context().status, 'unchecked');
    assert.equal(p.context().error, null);
    assert.equal(p.context().draftItems.length, 0);
    assert.equal(p.context().editor.symbol, '');
    assert.equal(p.window.document.getElementById('book-alert').style.display, 'none');
  } finally {p.dom.window.close();}
});

function payload() {
  const review = {state: 'needs_review', reasons: [{code: 'thesis_text_differs', snapshot_id: 'dossier:1'},
    {code: 'invalidation_not_carried', snapshot_id: 'dossier:1', conditions: ['现金回收下降']},
    {code: 'periodic_review_due', snapshot_id: 'dossier:1', calendar_age_days: 95}],
    comparisons: [{snapshot_id: 'dossier:1', as_of: '2026-01-01', calendar_age_days: 95,
      source_conclusion: '来源看好交付', source_invalidation: ['现金回收下降'], thesis_text_differs: true}],
    condition_evaluation: 'not_evaluated', boundary: '文字不同不代表逻辑已证伪。'};
  const item = {symbol: '300502', name: '测试公司', market: 'CN', sector: '通信', target_weight_pct: 25,
    thesis: '用户独立观察理由', invalidation: ['订单下降'], risk_tags: [], snapshot_ids: [],
    snapshot_references: [], snapshot_coverage: 'none', thesis_review: review};
  return {engine: {name: 'instock-research-book', version: '1.6.0'}, name: '验收组合', as_of: '2026-04-06',
    summary: {items: 1, total_target_weight_pct: 25, cash_weight_pct: 75},
    review_summary: {items_to_review: 1, review_target_weight_pct: 25, without_comparable_dossier: 0, text_aligned_items: 0,
      condition_evaluation: 'not_evaluated'}, items: [item], exposures: {}, warnings: [], limitations: []};
}

test('host UI check uses the visible draft and propagates actual failure', async () => {
  let failed = false, observed;
  const p = page({invokeAction: async (id, input) => {
    observed = input;
    if (failed) throw new Error('数据服务不可用');
    return {ok: true, data: {...payload(), name: input.name}};
  }});
  try {
    for (const [id, value] of Object.entries({'book-name': '当前可见草稿', 'book-symbol': '300502',
      'book-stock-name': '测试公司', 'book-sector': '通信', 'book-thesis': '仅测试', 'book-invalidation': '验收失败'})) {
      p.window.document.getElementById(id).value = value;
    }
    p.window.document.getElementById('book-add').click();
    const result = await p.invokeUi('analysis.research-book');
    assert.equal(observed.name, '当前可见草稿');
    assert.equal(observed.items[0].symbol, '300502');
    assert.equal(result.name, '当前可见草稿');
    assert.equal(result.summary.items, 1);
    assert.equal(p.context().name, result.name);
    assert.throws(() => p.invokeUi('analysis.research-book', {name: '隐藏覆盖'}), /不接受隐藏输入/);
    failed = true;
    await assert.rejects(p.invokeUi('analysis.research-book'), /数据服务不可用/);
    assert.match(p.text('book-alert'), /数据服务不可用/);
    assert.equal(p.context().name, undefined);
  } finally {p.dom.window.close();}
});

test('source differences, unmatched conditions and cutoff age agree with Agent context', () => {
  const p = page();
  try {
    const data = payload(); p.render(data);
    assert.match(p.text('book-thesis-summary'), /待复核 1\/1 项，涉及研究权重 25%/);
    assert.match(p.text('book-list'), /观察理由与来源结论文字不同/);
    assert.match(p.text('book-list'), /现金回收下降/);
    assert.match(p.text('book-list'), /95 个自然日/);
    assert.match(p.text('book-list'), /来源看好交付/);
    assert.equal(p.context().thesisReview, data.review_summary);
    assert.equal(p.context().items[0].thesis_review.condition_evaluation, 'not_evaluated');
    p.window.document.querySelector('#book-review-agenda button').click();
    assert.equal(p.window.document.activeElement.id, 'book-result-0');
    assert.equal(p.window.localStorage.length, 0); // History inspection never overwrites local draft.
  } finally {p.dom.window.close();}
});

test('queue counts observations once, orders by exposure and preserves zero-weight watch items', () => {
  const p = page();
  try {
    const data = payload();
    data.items.unshift({...data.items[0], name: '零权重观察', target_weight_pct: 0});
    data.review_summary.items_to_review = 2;
    p.render(data);
    const buttons = p.window.document.querySelectorAll('#book-review-agenda button');
    assert.equal(buttons.length, 2);
    assert.match(buttons[0].textContent, /测试公司.*25%/);
    assert.match(buttons[1].textContent, /零权重观察.*0%/);
    assert.match(p.text('book-thesis-summary'), /待复核 2\/2 项，涉及研究权重 25%/);
  } finally {p.dom.window.close();}
});

test('aligned wording is not a verified thesis and legacy results require recheck', () => {
  const p = page();
  try {
    const data = payload();
    data.items[0].thesis_review = {...data.items[0].thesis_review, state: 'text_aligned', reasons: []};
    data.review_summary = {...data.review_summary, items_to_review: 0, review_target_weight_pct: 0, text_aligned_items: 1};
    p.render(data);
    assert.equal(p.window.document.querySelectorAll('#book-review-agenda button').length, 0);
    assert.match(p.text('book-list'), /文字已对齐，证伪仍未验证/);
    delete data.review_summary; delete data.items[0].thesis_review;
    p.render(data);
    assert.match(p.text('book-thesis-summary'), /旧结果未生成/);
    assert.equal(p.context().thesisReview, null);
    assert.equal(p.context().thesisReviewState, 'legacy_requires_recheck');
  } finally {p.dom.window.close();}
});

test('editing clears review queue and context; source text renders literally', () => {
  const p = page();
  try {
    const data = payload();
    data.items[0].thesis_review.comparisons[0].source_conclusion = '<img src=x onerror=alert(1)>';
    p.render(data);
    assert.match(p.text('book-list'), /<img src=x/);
    assert.equal(p.window.document.querySelectorAll('#book-list img').length, 0);
    p.window.document.getElementById('book-thesis').dispatchEvent(new p.window.Event('input'));
    assert.match(p.text('book-thesis-summary'), /旧结论已撤下/);
    assert.equal(p.window.document.querySelectorAll('#book-review-agenda button').length, 0);
    assert.equal(p.context().status, 'unchecked');
    assert.equal(p.context().thesisReview, undefined);
  } finally {p.dom.window.close();}
});

test('successful check replaces unchecked copy and workspace switch clears its findings', async () => {
  const p = page();
  try {
    const bridge = p.window.InStockNewmaDesk;
    bridge.fetchAnalysis = async () => ({ok: true, json: async () => ({ok: true, data: payload()})});
    for (const [id, value] of Object.entries({'book-symbol': '300502', 'book-stock-name': '测试公司',
      'book-sector': '通信', 'book-thesis': '验收理由', 'book-invalidation': '验收条件', 'book-weight-input': '25'})) {
      p.window.document.getElementById(id).value = value;
    }
    p.window.document.getElementById('book-add').click();
    assert.match(p.text('book-handoff'), /尚未检查/);
    p.window.document.getElementById('book-run').click();
    await new Promise(resolve => setImmediate(resolve));
    assert.match(p.text('book-handoff'), /已完成当前草稿检查/);
    assert.equal(p.context().thesisReview.items_to_review, 1);
    bridge.embedded = true;
    bridge.config = {user: {id: 'another-user'}, workspace: {id: 'another-workspace'}};
    p.window.document.dispatchEvent(new p.window.Event('vibedesk:init'));
    assert.equal(p.window.document.querySelectorAll('#book-review-agenda button').length, 0);
    assert.equal(p.context().thesisReview, undefined);
    assert.equal(p.context().draftItems.length, 0);
  } finally {p.dom.window.close();}
});
