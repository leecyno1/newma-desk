import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "static/index.html").read_text(encoding="utf-8")


def run_js(source: str) -> None:
    result = subprocess.run(["node", "-e", source], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def function_source(start: str, end: str) -> str:
    return start + HTML.split(start, 1)[1].split(end, 1)[0]


def test_news_analysis_obeys_current_filters_and_empty_results():
    functions = function_source("function filterNewsItems", "function renderNewsListItems")
    functions += function_source("async function runNewsBatchAnalysis", "function bindNewsEngineControls")
    run_js("""
const assert = require('node:assert/strict');
const elements = {
    newsSearchInput: {value: '银行'}, newsSourceSelect: {value: 'source-a'},
    newsBatchAnalyzeBtn: {disabled: false, textContent: 'AI 批量解读'},
};
const document = {getElementById: id => elements[id]};
const requests = [];
const window = {VibeDeskBridge: {
    isEmbedded: true, canRequestAgent: () => true,
    requestAgent: request => requests.push(request),
}};
let status = '';
const setNewsRefreshState = (_, value) => {status = value;};
const formatNewsTime = () => '2026-10-14';
const newsAllItems = [{id: 'old', title: '历史消息'}];
let newsFilteredItems = [];
""" + functions + """
(async () => {
    await runNewsBatchAnalysis();
    assert.equal(requests.length, 0);
    assert.equal(status, '暂无新闻样本');
    newsFilteredItems = [
        {id: 'right', title: '银行政策', source_id: 'source-a', url: 'https://example.com/right'},
        {id: 'wrong-source', title: '银行政策', source_id: 'source-b'},
        {id: 'wrong-keyword', title: '科技政策', source_id: 'source-a'},
    ];
    await runNewsBatchAnalysis();
    assert.equal(requests.length, 1);
    assert.match(requests[0].prompt, /right/);
    assert.match(requests[0].prompt, /source-a/);
    assert.match(requests[0].prompt, /2026-10-14/);
    assert.ok(requests[0].prompt.includes('https://example.com/right'));
    assert.doesNotMatch(requests[0].prompt, /wrong-source|wrong-keyword/);
})().catch(error => {console.error(error); process.exitCode = 1;});
""")


def test_news_refresh_does_not_restore_cached_results_or_apply_late_responses():
    function = function_source("async function loadNewsEngine", "async function runNewsBatchAnalysis")
    run_js("""
const assert = require('node:assert/strict');
const elements = {newsItemsList: {}, newsSearchInput: {value: ''}, newsSourceSelect: {value: ''}};
const document = {getElementById: id => elements[id]};
let cache = [{id: 'old', title: '旧缓存'}];
let newsAllItems = cache, newsCurrentPage = 1, newsRequestId = 0;
let rendered = [], pending = [];
const lazyCacheRead = () => cache;
const lazyCacheWrite = (_, items) => {cache = items; return items;};
const lazyMergeItems = (a, b) => [...a, ...b];
const renderNewsListItems = items => {rendered = items;};
const showCachedList = (_, render) => {render(cache); return true;};
const newsHasVisibleRows = () => true;
const setNewsRefreshState = () => {};
const escapeHtml = String;
const requestJson = () => new Promise(resolve => pending.push(resolve));
""" + function + """
(async () => {
    const first = loadNewsEngine();
    pending.shift()({items: []});
    await first;
    assert.deepEqual(rendered, []);
    assert.deepEqual(newsAllItems, []);
    const oldRequest = loadNewsEngine();
    elements.newsSearchInput.value = '最新';
    const latestRequest = loadNewsEngine();
    const latest = [{id: 'latest', title: '最新新闻'}];
    pending.pop()({items: latest});
    await latestRequest;
    pending.pop()({items: [{id: 'stale', title: '延迟返回'}]});
    await oldRequest;
    assert.deepEqual(rendered, latest);
    assert.deepEqual(newsAllItems, latest);
})().catch(error => {console.error(error); process.exitCode = 1;});
""")
