import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
const script = readFileSync(`${root}/instock/web/static/js/stock-statement-review.js`, 'utf8');
const data = () => ({identity: {symbol: '300502'}, snapshot: {snapshot_id: 'fixture'}, fundamentals: {mode: 'latest_snapshot', evidence: [
    {id: 'disclosure.cn_net_income', value: 100, asOf: '2026-06-30', periodStart: '2026-01-01', unit: 'CNY', currency: 'CNY'},
    {id: 'disclosure.cn_liabilities', value: 0, asOf: '2026-06-30', unit: 'CNY', currency: 'CNY'},
]}});
const report = () => ({symbol: '300502', announcementId: 'AN202608240006746577', contentOrigin: 'pdf-text', periodEnd: '2026-06-30', title: '中报', readPages: [1, 2], pdfPageCount: 30,
    pdfUrl: 'https://pdf.dfcfw.com/report.pdf', facts: [
        {id: 'net_income', value: 100, asOf: '2026-06-30', periodStart: '2026-01-01', unit: 'CNY', currency: 'CNY', scope: 'consolidated', page: 20, headerPage: 19, columnHeader: '合并利润表', excerpt: '<img onerror=fail>'},
        {id: 'liabilities', value: 0, asOf: '2026-06-30', unit: 'CNY', currency: 'CNY', scope: 'consolidated', page: 18, headerPage: 17},
    ]});
function setup(run) {
    const dom = new JSDOM('<main></main>', {runScripts: 'outside-only'}); dom.window.eval(script);
    return Promise.resolve().then(() => run(dom.window.InStockStatementReview, dom.window)).finally(() => dom.window.close());
}

test('old embedded manifests explain missing permission without issuing requests', () => setup(async ({create}, win) => {
    const root = win.document.querySelector('main'); let granted = false, calls = 0;
    const review = create({root, bridge: {embedded: true, canInvokeAction: () => granted,
        fetchAnalysis: async () => { calls++; throw new Error('must not run'); }}, onChange() {}});
    review.setData(data());
    assert.match(root.textContent, /更新公司档案模组后刷新/);
    assert.ok(Array.from(root.querySelectorAll('button')).every(button => button.disabled));
    root.querySelector('form').dispatchEvent(new win.Event('submit', {cancelable: true}));
    assert.equal(calls, 0);
    granted = true; review.setData(data());
    assert.ok(Array.from(root.querySelectorAll('button')).every(button => !button.disabled));
    assert.doesNotMatch(root.textContent, /尚未授权/);
}));

test('compares same-period consolidated amounts, keeps zero and missing distinct without mutating snapshots', () => setup(({compare}) => {
    const current = data(), pdf = report(), before = JSON.stringify(current);
    assert.deepEqual(Array.from(compare(current, pdf), row => row.status), ['matched', 'missing', 'missing', 'matched']);
    pdf.facts[0].value = 99;
    assert.equal(compare(current, pdf)[0].status, 'different');
    assert.equal(compare(current, pdf)[0].difference, 1);
    for (const [key, value] of [['asOf', '2025-06-30'], ['periodStart', '2026-04-01'], ['scope', 'parent'], ['currency', 'USD']]) {
        const wrong = report(); wrong.facts[0][key] = value;
        assert.equal(compare(current, wrong)[0].status, 'incomparable');
    }
    assert.equal(JSON.stringify(current), before);
    assert.throws(() => compare(current, {...pdf, symbol: '600519'}), /证券/);
}));

test('renders source pages and comparison, clears result after source or dossier change', () => setup(async ({create}, win) => {
    const root = win.document.querySelector('main'); let changes = 0;
    const review = create({root, bridge: {fetchAnalysis: async () => ({ok: true, json: async () => ({data: report()})})}, onChange: () => ++changes});
    review.setData(data()); root.querySelector('input').value = 'AN202608240006746577';
    root.querySelector('form').dispatchEvent(new win.Event('submit', {cancelable: true}));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(review.context().rows[0].status, 'matched');
    assert.equal(review.feedback().state, 'completed');
    assert.equal(review.feedback().error, null);
    assert.match(root.textContent, /金额一致 2\/4/);
    assert.equal(root.querySelector('img'), null);
    assert.match(root.querySelector('table a').href, /#page=20$/);
    root.querySelector('input').dispatchEvent(new win.Event('input'));
    assert.equal(review.context(), null);
    assert.equal(root.querySelector('table'), null);
    review.setData({...data(), fundamentals: {mode: 'historical_evidence_only'}});
    assert.equal(root.querySelector('button').disabled, true);
    assert.match(root.textContent, /不使用现在读取的原件/);
    assert.ok(changes >= 3);
}));

test('late result cannot attach to a changed security or selection', () => setup(async ({create}, win) => {
    let resolve; const pending = new Promise(done => resolve = done);
    const root = win.document.querySelector('main');
    const review = create({root, bridge: {fetchAnalysis: () => pending}, onChange() {}});
    review.setData(data()); root.querySelector('input').value = 'AN202608240006746577';
    root.querySelector('form').dispatchEvent(new win.Event('submit', {cancelable: true}));
    review.setData(null); resolve({ok: true, json: async () => ({data: report()})});
    await new Promise(done => setImmediate(done));
    assert.equal(review.context(), null);
    assert.equal(review.feedback().state, 'idle');
    assert.equal(review.feedback().error, null);
    assert.equal(root.querySelector('table'), null);
}));

test('incomparable amounts expose actual units and both periods, not a fabricated yuan label', () => setup(async ({create}, win) => {
    const root = win.document.querySelector('main'), current = data();
    Object.assign(current.fundamentals.evidence[0], {unit: 'USD', currency: 'USD', periodStart: '2026-04-01'});
    const review = create({root, bridge: {fetchAnalysis: async () => ({ok: true, json: async () => ({data: report()})})}, onChange() {}});
    review.setData(current); root.querySelector('input').value = 'AN202608240006746577';
    root.querySelector('form').dispatchEvent(new win.Event('submit', {cancelable: true}));
    await new Promise(resolve => setImmediate(resolve));
    const row = root.querySelector('tbody tr');
    assert.equal(row.dataset.status, 'incomparable');
    assert.match(row.children[1].textContent, /100 美元/);
    assert.doesNotMatch(row.children[1].textContent, /100 元/);
    assert.match(row.children[1].textContent, /2026-04-01 至 2026-06-30/);
    assert.match(row.children[2].textContent, /100 元/);
    assert.match(row.children[2].textContent, /2026-01-01 至 2026-06-30/);
    assert.equal(review.context().rows[0].snapshotCurrency, 'USD');
}));

test('unavailable source leaves a useful original link and never claims completed verification', () => setup(async ({create}, win) => {
    const root = win.document.querySelector('main');
    const review = create({root, bridge: {fetchAnalysis: async () => ({ok: false, json: async () => ({error: {message: '来源未返回 PDF'}})})}, onChange() {}});
    review.setData(data()); root.querySelector('input').value = 'AN202608240006746577';
    root.querySelector('form').dispatchEvent(new win.Event('submit', {cancelable: true}));
    await new Promise(done => setImmediate(done));
    assert.equal(review.context(), null);
    assert.match(root.textContent, /未完成核对：来源未返回 PDF/);
    assert.equal(review.feedback().state, 'failed');
    assert.equal(review.feedback().error, '来源未返回 PDF');
    assert.equal(review.feedback().message, root.querySelector('[role="status"]').textContent);
    assert.equal(root.querySelector('a').href, 'https://data.eastmoney.com/notices/detail/300502/AN202608240006746577.html');
    assert.equal(root.querySelector('table'), null);
    root.querySelector('input').dispatchEvent(new win.Event('input'));
    assert.equal(review.feedback().state, 'idle');
    assert.equal(review.feedback().error, null);
}));

test('unrecognized statements retain the full original and explicitly count missing evidence', () => setup(async ({create}, win) => {
    const root = win.document.querySelector('main');
    const pdf = {...report(), facts: [], reportPublishedAt: '2026-08-25', retrievedAt: '2026-10-20T00:00:00Z'};
    const review = create({root, bridge: {fetchAnalysis: async () => ({ok: true, json: async () => ({data: pdf})})}, onChange() {}});
    review.setData(data()); root.querySelector('input').value = 'AN202608240006746577';
    root.querySelector('form').dispatchEvent(new win.Event('submit', {cancelable: true}));
    await new Promise(resolve => setImmediate(resolve));
    assert.match(root.textContent, /金额一致 0\/4/);
    assert.match(root.textContent, /证据不足 4 项/);
    assert.match(root.textContent, /不是历史版本日期/);
    assert.equal(root.querySelector('a').href, pdf.pdfUrl);
    assert.equal(root.querySelector('a').textContent, '打开完整财报原件');
    assert.equal(review.context().rows.every(row => row.status === 'missing'), true);
}));

test('official announcement links select cninfo explicitly and changing source clears old results', () => setup(async ({create}, win) => {
    const root=win.document.querySelector('main'), requests=[];
    const review=create({root,bridge:{fetchAnalysis:async url=>{
        requests.push(new URL(url,'http://localhost'));
        return {ok:true,json:async()=>({data:{...report(),announcementId:'1225499406',announcementSource:'cninfo',pdfUrl:'https://static.cninfo.com.cn/finalpage/2026-08-25/1225499406.PDF'}})};
    }},onChange(){}});
    review.setData(data());
    const input=root.querySelector('input'), source=root.querySelector('select');
    input.value='https://www.cninfo.com.cn/new/disclosure/detail?stockCode=300502&announcementId=1225499406';
    input.dispatchEvent(new win.Event('input'));
    assert.equal(source.value,'cninfo');
    root.querySelector('form').dispatchEvent(new win.Event('submit',{cancelable:true}));
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(requests[0].searchParams.get('source'),'cninfo');
    assert.equal(review.context().report.announcementSource,'cninfo');
    assert.match(root.querySelector('table a').href,/static.cninfo.com.cn/);
    source.value='eastmoney'; source.dispatchEvent(new win.Event('change'));
    assert.equal(review.context(),null);
    assert.equal(root.querySelector('table'),null);
    assert.match(root.textContent,/不会自动替换原件/);
    input.value='https://example.com/AN202608240006746577.html';
    root.querySelector('form').dispatchEvent(new win.Event('submit',{cancelable:true}));
    assert.equal(requests.length,1);
}));

test('discover official reports, select a version and compare only after explicit submission', () => setup(async ({create}, win) => {
    const root=win.document.querySelector('main'), calls=[];
    const review=create({root,bridge:{fetchAnalysis:async url=>{
        calls.push(url);
        return {ok:true,json:async()=>({data:{symbol:'300502',source:'cninfo',begin:'2025-10-20',end:'2026-10-20',hasMore:true,boundary:'最近365日第一页，非全历史',
            items:[{announcementId:'1225499406',title:'2026年半年度报告',periodEnd:'2026-06-30',date:'2026-08-25',url:'https://www.cninfo.com.cn/new/disclosure/detail?announcementId=1225499406'}]}})};
    }},onChange(){}});
    review.setData(data());
    Array.from(root.querySelectorAll('button')).find(button=>button.textContent==='查找本公司巨潮财报').click();
    await new Promise(resolve=>setImmediate(resolve));
    assert.match(calls[0],/statement-announcements\?symbol=300502/);
    assert.match(root.textContent,/未显示全部结果/);
    assert.equal(review.choices().items.length,1);
    assert.equal(review.context(),null);
    root.querySelector('li button').click();
    assert.equal(root.querySelector('input').value,'1225499406');
    assert.equal(review.selection().source,'cninfo');
    assert.equal(review.selection().announcementId,'1225499406');
    assert.equal(calls.length,1);
    assert.equal(review.choices(),null);
    assert.match(root.textContent,/请点击“核对财报原件”/);
}));

test('late official search cannot populate a different dossier', () => setup(async ({create},win) => {
    let resolve;
    const root=win.document.querySelector('main');
    const review=create({root,bridge:{fetchAnalysis:()=>new Promise(done=>resolve=done)},onChange(){}});
    review.setData(data()); Array.from(root.querySelectorAll('button')).find(button=>button.textContent==='查找本公司巨潮财报').click();
    review.setData(null);
    resolve({ok:true,json:async()=>({data:{symbol:'300502',source:'cninfo',items:[]}})});
    await new Promise(done=>setImmediate(done));
    assert.equal(review.choices(),null);
    assert.equal(root.querySelector('ul'),null);
}));
