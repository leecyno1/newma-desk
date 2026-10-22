import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const tick = () => new Promise(resolve => setImmediate(resolve));
function analysis(id = 'initial') {
  return {ok: true, data: {engine: {name: 'czsc', version: 'test'},
    summary: {fx_count: 46, bi_count: 14, zs_count: 2, trend_strength: 88.2, latest_signal: '一卖'},
    actual_bars: 120, insight: {},
    snapshot: {snapshot_id: id, freshness: {state: 'unknown'}}, end_date: '2026-10-19', chart: {}}};
}
async function page() {
  const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
  const html = readFileSync(`${root}/instock/web/templates/czsc_chart.html`, 'utf8');
  const dom = new JSDOM(html, {url: 'http://localhost/mods/czsc', runScripts: 'outside-only'});
  const {window} = dom, requests = [], transport = [], timers = new Map();
  let context, ui, seq = 0;
  window.setTimeout = fn => {timers.set(++seq, fn); return seq;};
  window.clearTimeout = id => timers.delete(id);
  window.matchMedia = () => ({matches: false});
  window.HTMLElement.prototype.scrollIntoView = () => {};
  window.echarts = {init: () => ({setOption() {}, resize() {}, clear() {}})};
  window.InStockNewmaDesk = {embedded: true, config: {user: {id: 'user'}, workspace: {id: 'one'}},
    fetchAnalysis(url, options = {}) {
      return new Promise((resolve, reject) => transport.push({url, options, resolve, reject}));
    },
    canInvokeAction: () => true, publishContext() {}, setContextProvider(fn) {context = fn;},
    setUiActionHandler(fn) {ui = fn;}, invokeAction(id, input) {
      return new Promise((resolve, reject) => requests.push({id, input, resolve, reject}));
    }};
  window.eval([...window.document.querySelectorAll('script')].find(s => s.textContent.includes('(function ()')).textContent);
  requests[0].resolve(analysis()); await tick();
  return {dom, window, requests, transport, timers, context: () => context(), field: id => window.document.getElementById(id),
    invoke: (id = 'analysis.czsc', input = {}) => ui(id, input)};
}
test('CZSC current analysis waits for rendering and rejects hidden input/busy/failure', async () => {
  const p = await page();
  try {
    assert.equal(p.context().data.summary.snapshotId, 'initial');
    assert.equal(p.context().data.summary.fxCount, 46);
    assert.equal(p.context().data.summary.biCount, 14);
    assert.equal(p.context().data.summary.zsCount, 2);
    assert.equal(p.context().data.summary.latestSignal, '一卖');
    assert.equal(p.context().data.summary.actualBars, 120);
    assert.throws(() => p.invoke('analysis.czsc', {code: '000001'}), /不接受隐藏输入/);
    const pending = p.invoke();
    assert.throws(() => p.invoke(), /正在运行/);
    assert.equal(p.requests.at(-1).input.code, '300502');
    p.requests.at(-1).resolve(analysis('new'));
    assert.equal((await pending).snapshot.snapshot_id, 'new');
    assert.equal(p.context().data.summary.snapshotId, 'new');
    const failed = p.invoke(); p.requests.at(-1).reject(new Error('结构行情不可用'));
    await assert.rejects(failed, /结构行情不可用/);
    assert.match(p.field('error-box').textContent, /结构行情不可用/);
  } finally {p.dom.window.close();}
});
test('CZSC edited conditions discard old analysis instead of reporting success', async () => {
  const p = await page();
  try {
    const pending = p.invoke();
    p.field('stock-code').value = '600519'; p.field('stock-code').dispatchEvent(new p.window.Event('input'));
    assert.equal(p.context().data.summary.snapshotId, null);
    assert.equal(p.context().data.summary.fxCount, null);
    assert.equal(p.context().data.summary.biCount, null);
    assert.equal(p.context().data.summary.zsCount, null);
    assert.equal(p.context().data.summary.actualBars, null);
    assert.equal(p.context().data.summary.trendStrength, null);
    assert.equal(p.context().visibleBlocks.length, 0);
    assert.match(p.field('data-meta').textContent, /尚未生成分析结果/);
    assert.equal(p.field('data-meta').title, '');
    p.requests.at(-1).resolve(analysis('late'));
    await assert.rejects(pending, /本次结构结果未采用/);
    assert.equal(p.context().data.summary.snapshotId, null);
  } finally {p.dom.window.close();}
});
test('CZSC context distinguishes genuine zero counts from missing data', async () => {
  const p = await page();
  try {
    const pending = p.invoke();
    const response = analysis('short-history');
    response.data.summary = {fx_count: 0, bi_count: 0, zs_count: 0, trend_strength: 0};
    p.requests.at(-1).resolve(response); await pending;
    assert.equal(p.context().data.summary.fxCount, 0);
    assert.equal(p.context().data.summary.biCount, 0);
    assert.equal(p.context().data.summary.zsCount, 0);
    assert.equal(p.context().data.summary.trendStrength, 0);
    assert.equal(p.context().data.summary.latestSignal, null);
  } finally {p.dom.window.close();}
});
test('CZSC context shares visible provenance and clears it when conditions change', async () => {
  const p = await page();
  try {
    const pending = p.invoke();
    const response = analysis('provenance');
    response.data.data_source = 'newma-desk';
    response.data.snapshot.provenance = {
      upstream_source: 'tencent', upstream_as_of: '2026-10-19T20:44:49Z',
      market: 'CN', timeframe: '1d', adjust: 'qfq', as_of_mode: 'client_filter',
    };
    p.requests.at(-1).resolve(response); await pending;
    assert.match(p.field('data-meta').textContent, /腾讯行情.*前复权/);
    assert.deepEqual(JSON.parse(JSON.stringify(p.context().data.summary.marketData)), {
      source: 'newma-desk', upstreamSource: 'tencent', upstreamAsOf: '2026-10-19T20:44:49Z',
      market: 'CN', timeframe: '1d', adjust: 'qfq', asOfMode: 'client_filter',
    });
    p.field('stock-code').value = '600519';
    p.field('stock-code').dispatchEvent(new p.window.Event('input'));
    assert.equal(p.context().data.summary.marketData, null);
  } finally {p.dom.window.close();}
});
test('CZSC scan returns a queued task identity, not a finished analysis', async () => {
  const p = await page();
  try {
    await assert.rejects(p.invoke('analysis.czsc.scan'), /至少输入/);
    p.field('scan-symbols').value = '600519,510300';
    const pending = p.invoke('analysis.czsc.scan');
    await assert.rejects(p.invoke('analysis.czsc.scan'), /不能重复创建/);
    const req = p.requests.at(-1);
    assert.deepEqual(Array.from(req.input.symbols), ['600519', '510300']);
    req.resolve({ok: true, data: {scan_id: 'scan-test', status: 'queued', parameters: req.input,
      progress: {total: 2, completed: 0}}});
    const result = await pending;
    assert.equal(result.scanId, 'scan-test');
    assert.equal(result.completed, false); assert.equal(result.status, 'queued');
    assert.equal(p.context().tasks[0].id, 'scan-test');
    assert.equal(p.context().tasks[0].status, 'queued');
    // A failed observation is not a terminal job; enabling the button must not create another task.
    p.field('scan-start').disabled = false;
    await assert.rejects(p.invoke('analysis.czsc.scan'), /不能重复创建/);
  } finally {p.dom.window.close();}
});
test('CZSC workspace switch drops late scan creation without claiming cancellation', async () => {
  const p = await page();
  try {
    p.field('scan-symbols').value = '600519';
    const pending = p.invoke('analysis.czsc.scan');
    p.window.InStockNewmaDesk.config.workspace.id = 'two';
    p.window.document.dispatchEvent(new p.window.Event('vibedesk:init'));
    p.requests.at(-1).resolve({scan_id: 'old-workspace-job', status: 'running'});
    await assert.rejects(pending, /后台任务可能仍在运行/);
    assert.equal(p.context().tasks.length, 0);
    assert.equal(p.context().data.summary.batchScan, null);
  } finally {p.dom.window.close();}
});

async function queuedScan(p) {
  p.field('scan-symbols').value = '600519,510300';
  const pending = p.invoke('analysis.czsc.scan');
  const record = {scan_id: 'scan-current', status: 'running', parameters: p.requests.at(-1).input,
    progress: {total: 2, completed: 0, succeeded: 0, failed: 0}};
  p.requests.at(-1).resolve(record); await pending;
  return record;
}
const httpRecord = record => ({ok: true, json: async () => ({ok: true, data: record})});

test('CZSC late cancellation cannot restore another workspace task or its error', async () => {
  for (const fails of [false, true]) {
    const p = await page();
    try {
      const record = await queuedScan(p);
      p.field('scan-cancel').click();
      const request = p.transport.at(-1);
      assert.equal(request.options.method, 'DELETE');
      p.window.InStockNewmaDesk.config.workspace.id = 'two';
      p.window.document.dispatchEvent(new p.window.Event('vibedesk:init'));
      if (fails) request.reject(new Error('旧范围取消失败'));
      else request.resolve(httpRecord({...record, status: 'cancelling'}));
      await tick();
      assert.equal(p.context().data.summary.batchScan, null);
      assert.equal(p.context().tasks.length, 0);
      assert.equal(p.field('scan-error').style.display, 'none');
      assert.equal(p.field('scan-state').style.display, 'none');
    } finally {p.dom.window.close();}
  }
});

test('CZSC cancellation invalidates an already running observation', async () => {
  const p = await page();
  try {
    const record = await queuedScan(p);
    const [timerId, poll] = Array.from(p.timers.entries()).at(-1);
    p.timers.delete(timerId); poll();
    const oldPoll = p.transport.at(-1);
    p.field('scan-cancel').click();
    p.transport.at(-1).resolve(httpRecord({...record, status: 'cancelling', progress: {...record.progress, cancel_requested: true}}));
    await tick();
    oldPoll.resolve(httpRecord(record)); await tick();
    assert.equal(p.context().data.summary.batchScan.status, 'cancelling');
    assert.equal(p.context().data.summary.batchScan.progress.cancelRequested, true);
    assert.equal(p.field('scan-cancel').disabled, true);
  } finally {p.dom.window.close();}
});

test('CZSC interrupted observation can resume the same task without creating a new scan', async () => {
  const p = await page();
  try {
    const record = await queuedScan(p);
    const [timerId, poll] = Array.from(p.timers.entries()).at(-1);
    p.timers.delete(timerId); poll();
    p.transport.at(-1).reject(new Error('临时网络中断')); await tick();
    assert.equal(p.field('scan-start').disabled, true);
    assert.equal(p.context().data.summary.batchScan.observation.state, 'interrupted');
    assert.equal(p.context().tasks[0].id, record.scan_id);
    assert.equal(p.field('scan-refresh').disabled, false);
    p.field('scan-refresh').click();
    assert.equal(p.transport.at(-1).url, '/api/v1/czsc/scans/scan-current');
    p.transport.at(-1).resolve(httpRecord({...record, status: 'completed',
      progress: {total: 2, completed: 2, succeeded: 0, failed: 2}, result: {candidates: [], failures: []}}));
    await tick();
    assert.equal(p.requests.filter(r => r.id === 'analysis.czsc.scan').length, 1);
    assert.equal(p.context().data.summary.batchScan.status, 'completed');
    assert.equal(p.context().data.summary.batchScan.observation.state, 'current');
    assert.equal(p.context().tasks.length, 0);
    assert.equal(p.field('scan-start').disabled, false);
    assert.equal(p.field('scan-error').style.display, 'none');
  } finally {p.dom.window.close();}
});

test('CZSC missing task is marked unavailable, never completed or cancelled', async () => {
  const p = await page();
  try {
    await queuedScan(p);
    const [timerId, poll] = Array.from(p.timers.entries()).at(-1);
    p.timers.delete(timerId); poll();
    p.transport.at(-1).resolve({ok: false, status: 404,
      json: async () => ({error: {message: '批量扫描任务不存在或已过期'}})});
    await tick();
    assert.equal(p.context().data.summary.batchScan.status, 'unavailable');
    assert.equal(p.context().data.summary.batchScan.observation.state, 'missing');
    assert.equal(p.context().tasks.length, 0);
    assert.equal(p.field('scan-start').disabled, false);
    assert.match(p.field('scan-error').textContent, /不表示扫描完成或已取消/);
  } finally {p.dom.window.close();}
});

test('CZSC choosing a batch result clears the previous security before its request completes', async () => {
  const p = await page();
  try {
    const record = await queuedScan(p);
    const [timerId, poll] = Array.from(p.timers.entries()).at(-1);
    p.timers.delete(timerId); poll();
    p.transport.at(-1).resolve(httpRecord({...record, status: 'completed', result: {
      candidates: [{rank: 1, symbol: '600519', candidate_score: 60, structure_stability: {score: 80}}]}}));
    await tick();
    p.field('scan-rows').querySelector('button').click();
    assert.equal(p.context().selection.symbol, '600519');
    assert.equal(p.context().data.summary.snapshotId, null);
    assert.equal(p.context().data.summary.fxCount, null);
    assert.equal(p.context().visibleBlocks.length, 0);
    assert.equal(p.field('result').style.display, 'none');
    const request = p.requests.at(-1);
    assert.equal(request.input.code, '600519');
    request.resolve(analysis('selected-result')); await tick();
    assert.equal(p.context().data.summary.snapshotId, 'selected-result');
  } finally {p.dom.window.close();}
});

test('CZSC untyped batch securities never inherit a stock or ETF identity from the previous selection', async () => {
  const p = await page();
  try {
    const record = await queuedScan(p);
    const [timerId, poll] = Array.from(p.timers.entries()).at(-1);
    p.timers.delete(timerId); poll();
    p.transport.at(-1).resolve(httpRecord({...record, status: 'completed', result: {
      candidates: [{rank: 1, symbol: '510300', candidate_score: 60, structure_stability: {score: 80}}]}}));
    await tick();
    p.field('scan-rows').querySelector('button').click();
    assert.equal(p.context().selection.symbol, '510300');
    assert.equal(p.context().selection.assetType, 'other');
    assert.equal(p.context().wiki.primarySubject.assetType, 'other');
    assert.equal(new URL(p.window.location.href).searchParams.get('assetType'), 'other');
    p.requests.at(-1).resolve(analysis('untyped-result')); await tick();
    assert.equal(p.field('czsc-research-link').style.display, 'none');
    p.field('stock-code').value = '600519';
    p.field('stock-code').dispatchEvent(new p.window.Event('input'));
    assert.equal(p.context().selection.assetType, 'other');
  } finally {p.dom.window.close();}
});

test('CZSC old dated history is preserved but explicitly marked for recomputation', async () => {
  const p = await page();
  try {
    const old = analysis('old-date-version').data;
    old.engine.analysis_version = '2.2.0';
    p.window.document.dispatchEvent(new p.window.CustomEvent('instock:history-selected', {
      detail: {payload: old, view_source: 'history'},
    }));
    assert.match(p.field('data-meta').textContent, /日期可能受时区影响/);
    assert.match(p.context().data.summary.periodDateWarning, /重新分析/);
    assert.equal(p.context().data.summary.snapshotId, 'old-date-version');
    const pending = p.invoke();
    const corrected = analysis('corrected-date-version');
    corrected.data.engine.analysis_version = '2.2.1';
    p.requests.at(-1).resolve(corrected); await pending;
    assert.equal(p.context().data.summary.periodDateWarning, null);
    assert.doesNotMatch(p.field('data-meta').textContent, /日期可能受时区影响/);
  } finally {p.dom.window.close();}
});
