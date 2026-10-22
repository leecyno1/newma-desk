import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const base = process.env.INSTOCK_TEST_SOURCE
    ? pathToFileURL(resolve(process.env.INSTOCK_TEST_SOURCE, 'instock/web') + '/')
    : new URL('../../bundled-runtimes/instock-analysis/instock/web/', import.meta.url);
const tick = () => new Promise(resolve => setImmediate(resolve));
const fixture = (id = 'initial') => ({engine: {name: 'instock-stock-research-dossier'},
    identity: {symbol: '300502', name: '示例公司'}, snapshot: {snapshot_id: id},
    assessment: {}, fundamentals: {mode: 'latest_snapshot', quality: {}, evidence: []},
    technical: {}, disclosures: {}, as_of: '2026-10-20', data_state: 'partial'});
async function page() {
    const dom = new JSDOM(readFileSync(new URL('templates/stock_research.html', base), 'utf8'),
        {url: 'http://localhost/mods/stock-research', runScripts: 'outside-only'});
    const win = dom.window; let context, handler, selection;
    const requests = [], sourceRequests = [];
    const bridge = win.InStockNewmaDesk = {embedded: true,
        config: {user: {id: 'u'}, workspace: {id: 'w'}, instanceId: 'one'},
        canInvokeAction: () => true, setContextProvider(fn) {context = fn;}, publishContext() {},
        setUiActionHandler(fn) {handler = fn;}, subscribe(fn) {selection = fn;},
        invokeAction(id, input) {return new Promise((resolve, reject) => requests.push({id, input, resolve, reject}));},
        fetchAnalysis(path) {return new Promise((resolve, reject) => sourceRequests.push({path, resolve, reject}));}};
    win.InStockStockChainReviews = win.InStockResearchOrigin = () => ({setData() {}, context: () => null, parameters: () => ({})});
    win.echarts = {init: () => ({setOption() {}, resize() {}, dispose() {}})};
    for (const name of ['stock-financial-evidence.js', 'stock-statement-review.js']) win.eval(readFileSync(new URL('static/js/' + name, base), 'utf8'));
    win.eval([...win.document.querySelectorAll('script')].find(node => node.textContent.includes('(function ()')).textContent);
    await tick(); requests[0].resolve({ok: true, data: fixture()}); await tick();
    return {dom, win, bridge, requests, sourceRequests, context: () => context(), invoke: (id, input = {}) => handler(id, input), selection};
}

test('company page action waits for visible result and reports running/failure honestly', async () => {
    const p = await page();
    try {
        assert.throws(() => p.invoke('analysis.stock-research', {symbol: '600519'}), /隐藏输入/);
        const pending = p.invoke('analysis.stock-research'); await tick();
        assert.equal(p.context().data.queryState.running, true);
        assert.equal(p.context().filters.symbol, '300502');
        assert.equal(p.context().actions[0].available, false);
        assert.equal(p.context().data.snapshot.snapshot_id, 'initial');
        assert.equal(p.context().data.queryState.retainedPreviousResult, true);
        assert.match(p.win.document.getElementById('dossier-meta').textContent, /保留上次成功档案/);
        await assert.rejects(p.invoke('analysis.stock-research'), /正在运行/);
        p.requests.at(-1).resolve({ok: true, data: fixture('new')});
        assert.equal((await pending).snapshot.snapshot_id, 'new');
        assert.equal(p.context().data.snapshot.snapshot_id, 'new');
        const failed = p.invoke('analysis.stock-research'); await tick();
        p.requests.at(-1).reject(new Error('数据源断开'));
        await assert.rejects(failed, /数据源断开/);
        assert.equal(p.context().data.queryState.error, '数据源断开');
        assert.equal(p.context().data.queryState.running, false);
        assert.equal(p.context().data.snapshot.snapshot_id, 'new');
        assert.equal(p.context().data.freshness, 'stale');
        assert.equal(p.context().data.queryState.retainedPreviousResult, true);
        assert.match(p.win.document.getElementById('dossier-name').textContent, /示例公司/);
        assert.match(p.win.document.getElementById('dossier-alert').textContent, /刷新失败.*保留.*数据源断开/);
        const retry = p.invoke('analysis.stock-research'); await tick();
        p.requests.at(-1).resolve({ok: true, data: fixture('recovered')}); await retry;
        assert.equal(p.context().data.snapshot.snapshot_id, 'recovered');
        assert.equal(p.context().data.queryState.retainedPreviousResult, false);
        assert.notEqual(p.context().data.freshness, 'stale');
        assert.equal(p.win.document.getElementById('dossier-alert').style.display, 'none');
    } finally {p.dom.window.close();}
});

test('failed request for another selection never retains the previous company', async () => {
    const p = await page();
    try {
        // Also covers the security event path, whose form update does not emit input.
        p.win.document.getElementById('dossier-symbol').value = '600519';
        const pending = p.invoke('analysis.stock-research'); await tick();
        assert.equal(p.context().data.snapshot, undefined);
        assert.equal(p.context().data.queryState.retainedPreviousResult, false);
        p.requests.at(-1).reject(new Error('该证券读取失败'));
        await assert.rejects(pending, /读取失败/);
        assert.equal(p.context().data.snapshot, undefined);
        assert.equal(p.win.document.getElementById('dossier-name').textContent, '--');
    } finally {p.dom.window.close();}
});

test('editing filters clears the retained failure message with the old result', async () => {
    const p = await page();
    try {
        const pending = p.invoke('analysis.stock-research'); await tick();
        p.requests.at(-1).reject(new Error('数据断开')); await assert.rejects(pending);
        assert.equal(p.win.document.getElementById('dossier-alert').style.display, 'block');
        const field = p.win.document.getElementById('dossier-symbol');
        field.value = '600519'; field.dispatchEvent(new p.win.Event('input'));
        assert.equal(p.context().data.snapshot, undefined);
        assert.equal(p.context().data.queryState.error, null);
        assert.equal(p.win.document.getElementById('dossier-alert').style.display, 'none');
    } finally {p.dom.window.close();}
});

test('edits and history selection prevent stale company actions from claiming success', async () => {
    const p = await page();
    try {
        for (const history of [false, true]) {
            const pending = p.invoke('analysis.stock-research'); await tick();
            if (history) p.win.document.dispatchEvent(new p.win.CustomEvent('instock:history-selected', {detail: {payload: fixture('history')}}));
            else {
                const field = p.win.document.getElementById('dossier-symbol'); field.value = '600519'; field.dispatchEvent(new p.win.Event('input'));
            }
            p.requests.at(-1).resolve({ok: true, data: fixture('late')});
            await assert.rejects(pending, /本次结果未采用/);
            assert.notEqual(p.context().data.snapshot?.snapshot_id, 'late');
        }
    } finally {p.dom.window.close();}
});

test('company host action finds reports in the same panel and rejects cross-company requests', async () => {
    const p = await page();
    try {
        assert.throws(() => p.invoke('analysis.stock-statement-announcements', {symbol: '600519'}), /当前公司档案不符/);
        const pending = p.invoke('analysis.stock-statement-announcements');
        assert.equal(p.context().data.statementTask, 'find');
        assert.throws(() => p.invoke('analysis.stock-statement-announcements'), /正在运行/);
        const listing = {symbol: '300502', source: 'cninfo', items: [], begin: '2025-10-20', end: '2026-10-20', boundary: '非全历史'};
        p.sourceRequests.at(-1).resolve({ok: true, json: async () => ({data: listing})});
        assert.equal((await pending).symbol, '300502');
        assert.equal(p.context().data.statementAnnouncements, listing);
        assert.equal(p.context().data.statementFeedback.operation, 'find');
        assert.equal(p.context().data.statementFeedback.state, 'completed');
        assert.match(p.win.document.getElementById('dossier-statement-review').textContent, /未找到支持/);
        assert.equal(p.context().data.statementTask, null);
    } finally {p.dom.window.close();}
});

test('a late success or failure cannot replace a newer cutoff result', async () => {
    for (const failOld of [false, true]) {
        const p = await page();
        try {
            const oldPending = p.invoke('analysis.stock-research'); await tick();
            const oldRequest = p.requests.at(-1);
            const cutoff = p.win.document.getElementById('dossier-date');
            cutoff.value = '2026-06-30'; cutoff.dispatchEvent(new p.win.Event('input'));
            assert.equal(p.context().data.snapshot, undefined);
            const newPending = p.invoke('analysis.stock-research'); await tick();
            assert.equal(p.requests.at(-1).input.asOf, '2026-06-30');
            const historical = {...fixture('cutoff-result'), as_of: '2026-06-30',
                fundamentals: {mode: 'historical_evidence_only', quality: {}, evidence: []}};
            p.requests.at(-1).resolve({ok: true, data: historical}); await newPending;
            if (failOld) oldRequest.reject(new Error('旧请求失败'));
            else oldRequest.resolve({ok: true, data: fixture('late-current')});
            await assert.rejects(oldPending);
            assert.equal(p.context().filters.asOf, '2026-06-30');
            assert.equal(p.context().data.snapshot.snapshot_id, 'cutoff-result');
            assert.equal(p.context().data.queryState.error, null);
            assert.equal(p.context().data.queryState.running, false);
            assert.equal(p.win.document.getElementById('dossier-alert').style.display, 'none');
        } finally {p.dom.window.close();}
    }
});

test('sample price uses the actual bar date and adjustment, shared with Agent context', async () => {
    const p = await page();
    try {
        const payload = {...fixture('weekend-cutoff'), as_of: '2026-06-28',
            snapshot: {snapshot_id: 'weekend-cutoff', parameters: {asOf: '2026-06-28'}},
            technical: {end_date: '2026-06-26',
                snapshot: {data_window: {end_date: '2026-06-26', requested_as_of: '2026-06-28'}, provenance: {adjust: 'qfq'}},
                cost_distribution: {state: 'available', current_price: 100, profile: []}}};
        const before = JSON.stringify(payload);
        const pending = p.invoke('analysis.stock-research'); await tick();
        p.requests.at(-1).resolve({ok: true, data: payload}); await pending;
        const note = p.win.document.getElementById('dossier-cost-basis').textContent;
        assert.match(note, /样本末价日期：2026-06-26.*查询截止日：2026-06-28.*前复权.*不代表实时行情.*不等于当时原始成交价/);
        assert.equal(p.context().data.technicalPriceBasis.displayText, note);
        const cards = p.win.document.getElementById('dossier-cost-summary').textContent;
        assert.match(cards, /样本末价100\.00/);
        assert.doesNotMatch(cards, /当前价/);
        assert.equal(JSON.stringify(payload), before);
        const field = p.win.document.getElementById('dossier-date');
        field.value = '2026-06-30'; field.dispatchEvent(new p.win.Event('input'));
        assert.equal(p.win.document.getElementById('dossier-cost-basis').textContent, '');
        assert.equal(p.context().data.technicalPriceBasis, null);
    } finally {p.dom.window.close();}
});

test('host-selected report is visible, compared, and returned only after the source responds', async () => {
    const p = await page();
    try {
        const pending = p.invoke('analysis.stock-statement-evidence', {symbol: '300502', source: 'cninfo', announcementId: '1225499406'});
        assert.equal(p.win.document.getElementById('statement-source').value, 'cninfo');
        assert.equal(p.win.document.getElementById('statement-announcement').value, '1225499406');
        assert.equal(p.context().data.statementTask, 'compare');
        const report = {symbol: '300502', announcementId: '1225499406', announcementSource: 'cninfo',
            contentOrigin: 'pdf-text', periodEnd: '2026-06-30', title: '示例中报', readPages: [1], pdfPageCount: 1,
            pdfUrl: 'https://static.cninfo.com.cn/finalpage/2026-08-25/1225499406.PDF', facts: []};
        p.sourceRequests.at(-1).resolve({ok: true, json: async () => ({data: report})});
        const result = await pending;
        assert.equal(result.snapshotId, 'initial');
        assert.equal(p.context().data.statementReview, result);
        assert.match(p.win.document.getElementById('dossier-statement-review').textContent, /证据不足 4 项/);
        const failedRefresh = p.invoke('analysis.stock-research'); await tick();
        assert.equal(p.context().data.statementReview, result);
        p.requests.at(-1).reject(new Error('刷新暂不可用'));
        await assert.rejects(failedRefresh, /刷新暂不可用/);
        assert.equal(p.context().data.statementReview, result);
        assert.equal(p.context().data.snapshot.snapshot_id, result.snapshotId);
        const stale = p.invoke('analysis.stock-statement-evidence');
        p.win.document.getElementById('dossier-symbol').dispatchEvent(new p.win.Event('input'));
        p.sourceRequests.at(-1).resolve({ok: true, json: async () => ({data: report})});
        await assert.rejects(stale, /未采用/);
        assert.equal(p.context().data.statementReview, null);
    } finally {p.dom.window.close();}
});

test('failed statement action publishes the same error as the page without changing the dossier', async () => {
    const p = await page();
    try {
        const pending = p.invoke('analysis.stock-statement-evidence', {source: 'cninfo', announcementId: '1225475868'});
        assert.equal(p.context().data.statementFeedback.state, 'running');
        p.sourceRequests.at(-1).resolve({ok: false, json: async () => ({error: {message: '所选公告未通过证券身份校验'}})});
        await assert.rejects(pending, /证券身份校验/);
        assert.equal(p.context().data.statementFeedback.state, 'failed');
        assert.equal(p.context().data.statementFeedback.operation, 'compare');
        assert.equal(p.context().data.statementFeedback.error, '所选公告未通过证券身份校验');
        assert.equal(p.context().data.statementFeedback.message,
            p.win.document.querySelector('#dossier-statement-review [role="status"]').textContent);
        assert.equal(p.context().data.statementReview, null);
        assert.equal(p.context().data.snapshot.snapshot_id, 'initial');
        p.win.document.getElementById('statement-announcement').dispatchEvent(new p.win.Event('input'));
        assert.equal(p.context().data.statementFeedback.state, 'idle');
        assert.equal(p.context().data.statementFeedback.error, null);
    } finally {p.dom.window.close();}
});

test('restored records are not assumed to match the current visible request', async () => {
    const p = await page();
    try {
        p.win.document.dispatchEvent(new p.win.CustomEvent('instock:history-selected', {
            detail: {payload: fixture('restored'), view_source: 'latest'}}));
        const pending = p.invoke('analysis.stock-research'); await tick();
        assert.equal(p.context().data.snapshot, undefined);
        p.requests.at(-1).resolve({ok: true, data: fixture('current')}); await pending;
        assert.equal(p.context().data.snapshot.snapshot_id, 'current');
    } finally {p.dom.window.close();}
});

test('history restores its saved query and clears unrelated live references', async () => {
    const p = await page();
    try {
        p.win.document.getElementById('dossier-bars').value = '120';
        p.win.document.getElementById('dossier-date').value = '2026-01-01';
        p.win.document.getElementById('dossier-event-flow').value = 'unrelated';
        const saved = {symbol: '300502', period: 'weekly', bars: 480, asOf: null,
            eventFlowSnapshotId: null, industryChainSnapshotId: 'chain:saved'};
        p.win.document.dispatchEvent(new p.win.CustomEvent('instock:history-selected', {
            detail: {parameters: saved, payload: fixture('historical'), view_source: 'history'}}));
        assert.equal(p.context().filters.period, 'weekly');
        assert.equal(p.context().filters.bars, 480);
        assert.equal(p.context().filters.asOf, undefined);
        assert.equal(p.context().filters.eventFlowSnapshotId, undefined);
        assert.equal(p.context().filters.industryChainSnapshotId, 'chain:saved');
        assert.equal(p.context().data.queryState.viewSource, 'history');
        assert.deepEqual(JSON.parse(JSON.stringify(p.context().data.queryState.resultParameters)),
            {symbol: '300502', period: 'weekly', bars: 480, industryChainSnapshotId: 'chain:saved'});
        assert.equal(new URL(p.win.location.href).searchParams.get('bars'), '480');
        assert.equal(p.requests.length, 1, 'restoring history must not fetch a new dossier');
        p.win.document.dispatchEvent(new p.win.CustomEvent('instock:history-selected', {
            detail: {parameters: {symbol: '300502', period: 'daily', bars: 120}, payload: fixture('saved-latest'), view_source: 'latest'}}));
        assert.equal(p.context().filters.bars, 120);
        assert.equal(p.context().filters.industryChainSnapshotId, undefined);
        assert.equal(p.context().data.queryState.viewSource, 'saved-latest');
        assert.equal(p.context().data.queryState.savedVersion, true);
        assert.match(p.context().data.queryState.displayStatus, /最近保存版本/);
        assert.match(p.win.document.getElementById('dossier-meta').textContent, /最近保存版本/);
    } finally {p.dom.window.close();}
});

test('incomplete history does not invent its parameters from the live form', async () => {
    const p = await page();
    try {
        p.win.document.dispatchEvent(new p.win.CustomEvent('instock:history-selected', {
            detail: {parameters: {symbol: '300502'}, payload: fixture('legacy'), view_source: 'history'}}));
        assert.equal(p.context().data.snapshot.snapshot_id, 'legacy');
        assert.equal(p.context().data.queryState.resultParameters, null);
        assert.match(p.win.document.getElementById('dossier-meta').textContent, /历史查询参数不完整/);
    } finally {p.dom.window.close();}
});

test('security event and new Desk instance supersede old work without false success', async () => {
    const p = await page();
    try {
        const pending = p.invoke('analysis.stock-research'); await tick();
        const old = p.requests.at(-1);
        p.selection({event: 'security.selected', source: 'watchlist', payload: {symbol: '600519'}}); await tick();
        assert.equal(p.requests.at(-1).input.symbol, '600519');
        old.resolve({ok: true, data: fixture('late')});
        await assert.rejects(pending, /未采用/);
        p.bridge.config.instanceId = 'two';
        p.win.document.dispatchEvent(new p.win.Event('vibedesk:init'));
        p.requests.at(-1).resolve({ok: true, data: fixture('late-new')}); await tick();
        assert.equal(p.context().data.snapshot, undefined);
        assert.equal(p.context().data.queryState.running, false);
    } finally {p.dom.window.close();}
});
