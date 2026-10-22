import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
const script = readFileSync(`${root}/instock/web/static/js/stock-financial-evidence.js`, 'utf8');
function render(data, verify) {
    const dom = new JSDOM('<main></main>', {runScripts: 'outside-only'});
    try {
        dom.window.eval(script);
        const root = dom.window.document.querySelector('main');
        dom.window.InStockFinancialEvidence(root, data);
        verify(key => root.querySelector(`[data-metric="${key}"]`), root);
    } finally {dom.window.close();}
}

test('units, source date, true zero and missing values remain distinct', () => {
    render({metrics: {pe: 20, revenueGrowthPct: 0, cashConversionPct: null}, evidence: [
        {id: 'growth.revenue_yoy', value: 0, asOf: '2026-06-30', source: 'THS financial abstract'},
    ]}, card => {
        assert.equal(card('pe').querySelector('b').textContent, '20.00倍');
        assert.match(card('pe').textContent, /日期未提供.*来源：未提供/);
        assert.equal(card('revenueGrowthPct').querySelector('b').textContent, '0.00%');
        assert.match(card('revenueGrowthPct').textContent, /报告期：2026-06-30.*THS/);
        assert.equal(card('cashConversionPct').querySelector('b').textContent, '--');
        assert.match(card('cashConversionPct').textContent, /每股参考比值不替代/);
        assert.equal(card('debtRatioPct').querySelector('b').textContent, '--');
    });
});

test('proxy is separate and traces its input evidence without executing source text', () => {
    render({metrics: {cashConversionPct: null}, evidence: [
        {id: 'profitability.eps', label: 'EPS', source: '<img src=x onerror=alert(1)>', asOf: '2026-06-30'},
        {id: 'cash_flow.op_cf_ps', label: '每股经营现金流', source: 'THS', asOf: '2026-06-30'},
        {id: 'derived.per_share_cash_earnings_proxy', value: 0.2144, sourceType: 'derived', source: 'Newma Financial Analytics',
            asOf: '2026-06-30', dependsOn: ['cash_flow.op_cf_ps', 'profitability.eps'], method: '每股经营现金流 / EPS', note: '不进入盈利质量评分'},
    ]}, (card, root) => {
        assert.equal(card('cashConversionPct').querySelector('b').textContent, '--');
        assert.match(card('derived.per_share_cash_earnings_proxy').textContent, /0.21倍.*THS.*EPS.*不进入盈利质量评分/);
        assert.equal(root.querySelector('img'), null);
    });
});

test('legacy snapshots are labelled for review rather than silently reinterpreted', () => {
    const data = {metrics: {cashConversionPct: 21.44}, evidence: [{id: 'derived.cash_conversion',
        value: 21.44, dependsOn: ['profitability.eps'], sourceType: 'derived'}]};
    const before = JSON.stringify(data);
    render(data, card => {
        assert.match(card('cashConversionPct').textContent, /历史每股口径估算（待复核）.*21.44%.*原记录保留/);
    });
    assert.equal(JSON.stringify(data), before);
});

test('derived cards expose raw amount and report publication without asserting a historical vintage', () => {
    render({metrics: {cashConversionPct: 20}, evidence: [
        {id: 'disclosure.cn_operating_cash_flow', label: '合并经营现金流净额', value: 2000000, unit: 'CNY',
            periodStart: '2026-01-01', asOf: '2026-06-30', reportPublishedAt: '2026-08-25', source: 'Sina', url: 'https://quotes.sina.cn/example'},
        {id: 'derived.cash_conversion', sourceType: 'derived', method: '现金流/合并净利润', dependsOn: ['disclosure.cn_operating_cash_flow']},
    ]}, card => {
        const item = card('cashConversionPct');
        assert.match(item.textContent, /2,000,000元.*2026-01-01—2026-06-30.*报告披露 2026-08-25（当前版本未核验）/);
        assert.equal(item.querySelector('details').open, false);
        assert.equal(item.querySelector('a').href, 'https://quotes.sina.cn/example');
    });
});

test('quote source clock and retrieval clock remain separate, including unknown and legacy snapshots', () => {
    const facts = {metrics: {pe: 20, pb: 2}, evidence: [
        {id:'valuation.pe_ttm', value:20, asOf:'2026-10-19T15:00:03+08:00', retrievedAt:'2026-10-20T00:30:00+08:00', timeBasis:'source_quote', source:'Tencent quote'},
        {id:'valuation.pb', value:2, asOf:null, retrievedAt:'2026-10-20T00:30:00+08:00', timeBasis:'unknown', source:'Tencent quote'},
    ]};
    render(facts, card => {
        assert.match(card('pe').textContent, /行情源时间：2026-10-19T15:00:03\+08:00/);
        assert.match(card('pe').textContent, /系统获取：2026-10-20T00:30:00\+08:00（不代表实时行情）/);
        assert.match(card('pb').textContent, /行情源时间未核实：日期未提供/);
    });
    delete facts.evidence[0].timeBasis;
    render(facts, card => assert.match(card('pe').textContent, /旧快照，时间口径未核验/));
});
