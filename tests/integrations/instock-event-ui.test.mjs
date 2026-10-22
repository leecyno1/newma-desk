import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const tick = () => new Promise(resolve => setImmediate(resolve));
function payload(id = 'initial', symbol = '300502') {
  return {engine: {name: 'instock-event-flow'}, snapshot: {snapshot_id: id}, query: {symbol},
    input_mode: 'desk_symbol', market: 'CN', as_of: '2026-10-20', data_state: 'partial',
    summary: {deduplicated_events: 2, fresh_events: 2}, coverage: {}, failures: [], limitations: [],
    alerts: ['positive', 'negative'].map(direction => ({symbol, type: 'announcement', direction,
      title: `测试证据-${direction}`, occurred_at: '2026-10-19', freshness: 'fresh', evidence_strength: 'medium', intensity_score: 50}))};
}
async function page({delayedInit = false, embedded = true, navigationReady = true} = {}) {
  const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
  const html = readFileSync(`${root}/instock/web/templates/event_flow.html`, 'utf8');
  const dom = new JSDOM(html, {url: 'http://localhost/mods/event-flow', runScripts: 'outside-only'});
  const {window} = dom, requests = [], navigations = [], selections = [];
  let context, ui, selection;
  window.InStockNewmaDesk = {embedded, config: {user:{id:'u'},workspace:{id:'w'},instanceId:'one'}, canInvokeAction: () => true, publishContext() {},
    navigate(target, search) {navigations.push({target, search}); return navigationReady;},
    emit(event, data) {selections.push({event, data});},
    setContextProvider(fn) {context = fn;}, setUiActionHandler(fn) {ui = fn;}, subscribe(fn) {selection = fn;},
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
  requests[0].resolve(payload()); await tick();
  return {dom, window, requests, navigations, selections, field: id => window.document.getElementById('event-' + id),
    context: () => context(), invoke: (input = {}) => ui('analysis.event-flow', input),
    select: data => selection({event: 'security.selected', source: 'instock-czsc', payload: data}),
    changeScope() {window.InStockNewmaDesk.config.workspace.id += '-next'; window.document.dispatchEvent(new window.CustomEvent('vibedesk:init'));}};
}

test('security selection rejects non-company assets, other markets and self events', async () => {
  const p = await page();
  try {
    for (const data of [{symbol:'600519',market:'HK'}, ...['etf','fund','index','bond','future','other'].map(assetType => ({symbol:'512800',market:'CN',assetType})),
      {symbol:'600519',market:'CN',source:'instock-event-flow'}]) p.select(data);
    await tick();
    assert.equal(p.requests.length, 1);
    assert.equal(p.field('symbol').value, '300502');
    assert.equal(p.context().data.snapshot.snapshot_id, 'initial');
  } finally {p.dom.window.close();}
});

test('security selection carries its cutoff and clears an unrelated previous cutoff', async () => {
  const p = await page();
  try {
    p.select({symbol:'600519',market:'CN',assetType:'stock',asOf:'2026-06-30'}); await tick();
    assert.equal(JSON.stringify(p.requests.at(-1).input), JSON.stringify({symbol:'600519',asOf:'2026-06-30'}));
    assert.equal(p.context().data.snapshot, undefined);
    assert.equal(p.context().selectedSecurity, null);
    const dated = {...payload('dated','600519'),as_of:'2026-06-30'};
    p.requests.at(-1).resolve(dated); await tick();
    p.select({symbol:'300502',market:'CN',assetType:'stock'}); await tick();
    assert.equal(p.field('date').value, '');
    assert.equal(JSON.stringify(p.requests.at(-1).input), JSON.stringify({symbol:'300502'}));
    p.requests.at(-1).resolve(payload('latest')); await tick();
  } finally {p.dom.window.close();}
});

test('superseded event requests cannot unlock or overwrite the new selection', async () => {
  for (const fails of [false,true]) {
    const p = await page();
    try {
      const oldPending = p.invoke(), old = p.requests.at(-1);
      p.select({symbol:'600519',market:'CN',assetType:'stock',asOf:'2026-06-30'}); await tick();
      assert.equal(p.requests.length, 3);
      assert.equal(p.context().data.snapshot, undefined);
      if (fails) old.reject(new Error('旧证券读取失败')); else old.resolve(payload('late'));
      await assert.rejects(oldPending); await tick();
      assert.equal(p.context().data.queryState.running, true);
      assert.equal(p.field('run').disabled, true);
      assert.equal(p.context().data.queryState.error, null);
      p.requests.at(-1).resolve({...payload('current','600519'),as_of:'2026-06-30'}); await tick();
      assert.equal(p.context().data.snapshot.snapshot_id, 'current');
      assert.equal(p.context().data.queryState.running, false);
      const link = new URL(p.field('research-link').href);
      assert.equal(link.searchParams.get('symbol'),'600519');
      assert.equal(link.searchParams.get('asOf'),'2026-06-30');
      assert.equal(link.searchParams.get('eventFlowSnapshotId'),'current');
    } finally {p.dom.window.close();}
  }
});

test('editing or changing workspace withdraws old evidence and prevents stale card broadcasts', async () => {
  for (const scope of [false,true]) {
    const p = await page();
    try {
      const card = p.field('list').querySelector('article');
      if (scope) p.changeScope();
      else {p.field('symbol').value='600519';p.field('symbol').dispatchEvent(new p.window.Event('input'));}
      card.click();
      assert.equal(p.selections.length,0);
      assert.equal(p.context().data.snapshot,undefined);
      assert.equal(p.context().selectedSecurity,null);
      assert.equal(p.field('count').textContent,'--');
      assert.equal(p.field('list').querySelectorAll('article').length,0);
      assert.equal(p.field('research-link').style.display,'none');
    } finally {p.dom.window.close();}
  }
});

test('same-scope runtime updates preserve evidence and the active query', async () => {
  const p = await page();
  try {
    p.window.document.dispatchEvent(new p.window.CustomEvent('vibedesk:init'));
    assert.equal(p.context().data.snapshot.snapshot_id,'initial');
    const pending = p.invoke();
    p.window.document.dispatchEvent(new p.window.CustomEvent('vibedesk:init'));
    assert.equal(p.context().data.queryState.running,true);
    p.requests.at(-1).resolve(payload('same-scope')); await pending;
    assert.equal(p.context().data.snapshot.snapshot_id,'same-scope');
  } finally {p.dom.window.close();}
});
test('event first load waits for the initial Desk handshake before capturing request scope', async () => {
  const p = await page({delayedInit: true});
  try {
    assert.equal(p.requests.length, 1);
    assert.equal(p.context().data.snapshot?.snapshot_id, 'initial');
    assert.equal(p.context().data.queryState.resultMatchesCurrentInput, true);
    assert.equal(p.context().data.queryState.running, false);
  } finally {p.dom.window.close();}
});
test('related evidence is grouped without losing sources and filtered context remains explicit', async () => {
  const p = await page();
  try {
    const pending = p.invoke();
    const result = payload('related');
    result.alerts = result.alerts.map((item, i) => ({...item, id: `r${i}`,
      type: i ? 'news' : 'announcement', title: i ? '董事长提议回购' : '关于回购提议的公告',
      source_ref: `https://example.test/${i}`, details: {source: i ? '媒体甲' : null}}));
    result.related_groups = [{label:'回购 · 提议/计划', primary_event_id:'r0', event_ids:['r0','r1'],
      identity_verified:false, independent_source_count:null, direction_conflict:true,
      note:'关联待核验，不代表独立信号或多源确认。'}];
    p.requests[1].resolve(result); await pending;
    const group = p.field('list').querySelector('.event-related');
    assert.ok(group);
    assert.equal(group.querySelectorAll('article').length, 2);
    assert.equal(group.querySelectorAll('a').length, 2);
    assert.match(group.textContent, /方向相反/);
    assert.match(group.textContent, /不代表独立信号/);
    assert.equal(p.context().data.relatedGroups[0].visible_event_ids.length, 2);
    p.field('direction-filter').value = 'negative';
    p.field('direction-filter').dispatchEvent(new p.window.Event('change'));
    assert.equal(p.field('list').querySelectorAll('article').length, 1);
    assert.deepEqual([...p.context().data.relatedGroups[0].visible_event_ids], ['r1']);
    assert.equal(p.context().data.relatedGroups[0].hidden_by_filter, 1);
    assert.match(p.field('list').textContent, /另有 1 条被当前筛选隐藏/);
  } finally {p.dom.window.close();}
});
test('source response count does not disguise empty or failed coverage', async () => {
  const p = await page();
  try {
    assert.equal(p.field('source-status').textContent, '覆盖状态未提供');
    const pending = p.invoke();
    const result = payload('partial');
    result.coverage = {requested_sources:3, failed_sources:1, sources:
      ['available','empty','failed'].map((state,i) => ({id:String(i),label:`来源${i}`,state,records:state === 'available' ? 12 : 0}))};
    p.requests[1].resolve(result); await pending;
    assert.equal(p.field('sources').textContent, '2/3');
    assert.equal(p.field('source-status').textContent, '有记录 1 · 空 1 · 失败 1');
    assert.equal(p.context().data.coverage.failed_sources, 1);
  } finally {p.dom.window.close();}
});
test('event evidence displays missing metrics, publication and basis without truncating the warning', async () => {
  const p = await page();
  try {
    const pending = p.invoke();
    const result = payload('values');
    result.alerts = [{...result.alerts[0], type: 'holder_change', details: {
      holder_count: null, holder_change_pct: 0, average_shares_per_holder: null,
      observation_date: '2026-06-30', published_at: '2026-08-25',
      average_shares_basis: '总A股股数/股东户数', data_quality_note: '部分数值未知，不以零或持平代替',
    }}];
    p.requests[1].resolve(result); await pending;
    const text = p.field('list').textContent;
    assert.match(text, /股东户数 --/);
    assert.match(text, /户数环比 0\.00%/);
    assert.match(text, /统计期 2026-06-30/);
    assert.match(text, /披露日 2026-08-25/);
    assert.match(text, /总A股股数\/股东户数/);
    assert.match(text, /不以零或持平代替/);
    assert.equal(p.context().data.topAlerts[0].details.average_shares_per_holder, null);
  } finally {p.dom.window.close();}
});
test('flow evidence shows sample dates and missing totals without displaying an invented percentile', async () => {
  const p = await page();
  try {
    const pending = p.invoke();
    const result = payload('short-flow');
    result.alerts = [{...result.alerts[0], type: 'fund_flow', details: {
      main_net_5d_cny: null, main_net_20d_cny: null, latest_main_net_cny: 0,
      five_day_abs_percentile_pct: null, window_5d_records: 3, window_5d_valid_records: 2,
      window_5d_start: '2026-10-15', window_5d_end: '2026-10-19', percentile_sample_count: 0,
      window_basis: '按有记录日期去重，未核验交易日连续性', data_quality_note: '样本不足，不填零',
    }}];
    p.requests[1].resolve(result); await pending;
    const text = p.field('list').textContent;
    assert.match(text, /5条日记录主力净额 --/);
    assert.match(text, /绝对值分位 --/);
    assert.match(text, /5条窗口有效记录 2/);
    assert.match(text, /5条窗口起始日 2026-10-15/);
    assert.match(text, /此前完整窗口数 0/);
    assert.doesNotMatch(text, /此前完整窗口数 0\.00%/);
    assert.match(text, /未核验交易日连续性/);
    assert.equal(p.context().data.topAlerts[0].details.main_net_5d_cny, null);
  } finally {p.dom.window.close();}
});
test('event handoff stays in Desk and carries the rendered snapshot and date', async () => {
  const p = await page();
  try {
    const click = new p.window.MouseEvent('click', {bubbles: true, cancelable: true});
    p.field('research-link').dispatchEvent(click);
    assert.equal(click.defaultPrevented, true);
    assert.equal(p.navigations[0].target, 'instock-stock-research');
    const query = new URLSearchParams(p.navigations[0].search);
    assert.equal(query.get('symbol'), '300502');
    assert.equal(query.get('eventFlowSnapshotId'), 'initial');
    assert.equal(query.get('asOf'), '2026-10-20');
    p.field('list').querySelector('article').click();
    assert.equal(p.selections[0].data.asOf, '2026-10-20');
    p.field('symbol').value = '600519';
    p.field('symbol').dispatchEvent(new p.window.Event('input'));
    assert.equal(p.field('research-link').style.display, 'none');
    p.field('research-link').dispatchEvent(new p.window.MouseEvent('click', {cancelable: true}));
    assert.equal(p.navigations.length, 1);
  } finally {p.dom.window.close();}
});

test('corporate action evidence keeps missing values, progress and effective dates distinct', async () => {
  const p = await page();
  try {
    const pending = p.invoke();
    const result = payload('corporate');
    result.limitations = ['corporate_action_rows_excluded_without_timely_disclosure'];
    result.alerts = [{...result.alerts[0], type: 'dividend', details: {
      cash_dividend_cny_per_10_shares: 0, transfer_shares_per_10: 4, bonus_shares_per_10: null,
      published_at: '2026-06-04', effective_at: null, plan: '董事会预案',
      plan_description: '10转4股', event_date_basis: '当前方案披露日',
    }}, {...result.alerts[1], type: 'lockup', details: {
      able_shares_10k: null, unlock_ratio: 0.001735906791, published_at: null,
      effective_at: '2026-11-01', risk_basis: '占流通股本的小数比例；解禁不代表实际减持',
    }}];
    p.requests[1].resolve(result); await pending;
    const text = p.field('list').textContent;
    assert.match(text, /每10股派息 0/);
    assert.match(text, /每10股转增 4/);
    assert.match(text, /每10股送股 --/);
    assert.match(text, /方案进度 董事会预案/);
    assert.match(text, /除权除息日 --/);
    assert.match(text, /解禁日 2026-11-01/);
    assert.match(text, /可流通万股 --/);
    assert.match(text, /占流通股本 0\.17%/);
    assert.match(text, /不代表实际减持/);
    assert.match(p.field('failures').textContent, /披露日晚于截止日或未核验/);
    assert.equal(p.context().data.topAlerts[0].details.bonus_shares_per_10, null);
    assert.equal(p.context().data.topAlerts[0].detailLabels.effective_at, '除权除息日');
    assert.equal(p.context().data.topAlerts[1].detailLabels.effective_at, '解禁日');
  } finally {p.dom.window.close();}
});
test('event handoff never falls into standalone scope when Desk navigation is unavailable', async () => {
  const p = await page({navigationReady: false});
  try {
    const click = new p.window.MouseEvent('click', {cancelable: true});
    p.field('research-link').dispatchEvent(click);
    assert.equal(click.defaultPrevented, true);
    assert.match(p.field('alert').textContent, /工作区|导航/);
    p.changeScope();
    assert.equal(p.field('research-link').style.display, 'none');
  } finally {p.dom.window.close();}
});
test('standalone event handoff keeps its ordinary evidence link', async () => {
  const p = await page({embedded: false});
  try {
    assert.equal(p.field('research-link').getAttribute('target'), '_blank');
    const query = new URL(p.field('research-link').href).searchParams;
    assert.equal(query.get('eventFlowSnapshotId'), 'initial');
    assert.equal(p.navigations.length, 0);
  } finally {p.dom.window.close();}
});
test('event action reads the displayed code and filters Context to visible evidence', async () => {
  const p = await page();
  try {
    p.field('symbol').value = '600519'; p.field('symbol').dispatchEvent(new p.window.Event('input'));
    assert.equal(p.context().data.queryState.resultMatchesCurrentInput, false);
    assert.throws(() => p.invoke({symbol: '000001'}), /不接受隐藏输入/);
    const pending = p.invoke();
    assert.equal(p.requests[1].input.symbol, '600519');
    await assert.rejects(p.invoke(), /正在读取/);
    p.requests[1].resolve({ok: true, data: payload('new', '600519')});
    assert.equal((await pending).snapshot.snapshot_id, 'new');
    assert.equal(p.context().data.queryState.resultMatchesCurrentInput, true);
    p.field('direction-filter').value = 'positive';
    p.field('direction-filter').dispatchEvent(new p.window.Event('change'));
    assert.equal(p.context().data.topAlerts.length, 1);
    assert.equal(p.context().data.topAlerts[0].direction, 'positive');
    assert.doesNotMatch(p.field('list').textContent, /测试证据-negative/);
  } finally {p.dom.window.close();}
});
test('event packet action requires real visible input and never submits the empty template', async () => {
  const p = await page();
  try {
    assert.throws(() => p.invoke({mode: 'packet'}), /空模板不能/);
    assert.equal(p.requests.length, 1);
    const packet = {schema_version: 'instock-event-flow-packet-v1', as_of: '2026-10-20', market: 'CN',
      events: [{symbol: '600519', type: 'announcement', title: '已填入的测试证据'}]};
    p.field('packet').value = JSON.stringify(packet);
    const pending = p.invoke({mode: 'packet'});
    assert.equal(JSON.stringify(p.requests[1].input), JSON.stringify(packet));
    p.requests[1].resolve({...payload('packet'), input_mode: 'packet', query: {}});
    await pending;
    assert.equal(p.context().filters.inputMode, 'packet');
    assert.equal(p.context().data.queryState.resultMatchesCurrentInput, true);
  } finally {p.dom.window.close();}
});
test('event action propagates failure and rejects results after input/history/scope changes', async () => {
  const p = await page();
  try {
    const failed = p.invoke(); p.requests.at(-1).reject(new Error('公告服务不可用'));
    await assert.rejects(failed, /公告服务不可用/);
    assert.match(p.field('alert').textContent, /公告服务不可用/);
    assert.equal(p.field('run').disabled, false);
    for (const event of ['input', 'instock:history-selected', 'vibedesk:init']) {
      const pending = p.invoke();
      if (event === 'input') { p.field('symbol').value = '600519'; p.field('symbol').dispatchEvent(new p.window.Event('input')); }
      else if (event === 'vibedesk:init') p.changeScope();
      else p.window.document.dispatchEvent(new p.window.CustomEvent(event, {detail: {payload: payload('history'), view_source: 'history'}}));
      p.requests.at(-1).resolve(payload('late'));
      await assert.rejects(pending, /本次事件结果未采用/);
      assert.notEqual(p.context().data.snapshot?.snapshot_id, 'late');
    }
  } finally {p.dom.window.close();}
});

test('event history restores security, cutoff and action inputs without rewriting the record', async () => {
  const p = await page();
  try {
    const historical = {...payload('old', '600519'), as_of: '2026-06-03'};
    p.window.document.dispatchEvent(new p.window.CustomEvent('instock:history-selected', {
      detail: {payload: historical, view_source: 'history'},
    }));
    assert.equal(p.field('symbol').value, '600519');
    assert.equal(p.field('date').value, '2026-06-03');
    assert.equal(p.context().filters.asOf, '2026-06-03');
    assert.equal(p.context().data.viewSource, 'history');
    assert.equal(p.context().data.queryState.resultMatchesCurrentInput, true);
    assert.equal(new URL(p.window.location.href).searchParams.get('asOf'), '2026-06-03');
    const pending = p.invoke();
    assert.equal(JSON.stringify(p.requests.at(-1).input), JSON.stringify({symbol: '600519', asOf: '2026-06-03'}));
    p.requests.at(-1).resolve({...historical, snapshot: {snapshot_id: 'refreshed'}});
    await pending;
    assert.equal(p.context().data.viewSource, 'current');
    assert.equal(historical.snapshot.snapshot_id, 'old');
  } finally {p.dom.window.close();}
});

test('history packet without original input preserves draft and declares it unmatched', async () => {
  const p = await page();
  try {
    const draft = p.field('packet').value;
    const historical = {...payload('packet'), input_mode: 'packet', query: {}};
    p.window.document.dispatchEvent(new p.window.CustomEvent('instock:history-selected', {detail: {payload: historical}}));
    assert.equal(p.field('packet').value, draft);
    assert.equal(p.context().filters.inputMode, 'packet');
    assert.equal(p.context().data.queryState.resultMatchesCurrentInput, false);
    assert.match(p.field('alert').textContent, /原始输入|事件包/);
    assert.equal(p.field('research-link').style.display, 'none');
    assert.throws(() => p.invoke(), /空模板不能/);
  } finally {p.dom.window.close();}
});

test('restoring a result clears stale errors and never invents packet effective-date semantics', async () => {
  const p = await page();
  try {
    const failed = p.invoke(); p.requests.at(-1).reject(new Error('来源失败'));
    await assert.rejects(failed, /来源失败/);
    const historical = {...payload('packet'), input_mode: 'packet', query: {}};
    historical.alerts = [{...historical.alerts[0], type: 'dividend', details: {effective_at: '2026-06-11'}}];
    p.window.InStockEventFlow.acceptActionResult(historical);
    assert.equal(p.context().data.queryState.error, null);
    assert.match(p.field('list').textContent, /生效日期 2026-06-11/);
    assert.equal(p.context().data.topAlerts[0].detailLabels.effective_at, '生效日期');
  } finally {p.dom.window.close();}
});
