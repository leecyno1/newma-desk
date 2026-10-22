import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const html = readFileSync(process.env.INSTOCK_TEST_SOURCE
  ? join(process.env.INSTOCK_TEST_SOURCE, 'instock/web/templates/industry_chain.html')
  : new URL('../../bundled-runtimes/instock-analysis/instock/web/templates/industry_chain.html', import.meta.url), 'utf8');
const script = html.slice(html.lastIndexOf('<script>') + 8, html.lastIndexOf('</script>'));
const packet = () => ({schema_version: '2.0', theme: '测试产业链', market: 'CN', as_of: '2026-10-15',
  evidence: [{id: 'source-1', claim: '测试材料，不是真实投资结论'}],
  chain: {nodes: [], links: []}, layers: [], candidates: []});
const result = value => ({...value, engine: {name: 'instock-industry-chain-research'},
  data_state: 'partial', summary: {chain_node_count: 0, chain_link_count: 0, candidate_count: 0, evidence_count: value.evidence.length},
  snapshot: {snapshot_id: 'test-chain', result: {summary: {}}}, verification: {sources_verified: false},
  limitations: ['测试数据，仅用于验证交互']});

function page(overrides = {}, {material = null, map = null, evidence = null} = {}) {
  const dom = new JSDOM(html, {url: 'http://localhost/mods/industry-chain', runScripts: 'outside-only'});
  const {window} = dom;
  let context, handler;
  window.InStockNewmaDesk = {setContextProvider: fn => {context = fn;},
    setUiActionHandler: fn => {handler = fn;}, publishContext() {}, ...overrides};
  window.InStockChainMaterials = () => ({setBusy() {}, context: () => material,
    material: () => material, evidence: () => evidence});
  window.InStockChainMapInput = () => ({setBusy() {}, context: () => map,
    material: async () => map, invalidateConfirmation() {}});
  window.InStockResearchOrigin = () => ({setData() {}, context: () => null, parameters: () => ({})});
  window.InStockChainReviews = () => ({setData() {}, context: () => ({candidateChecks: []}), select() {}, useQuote() {}});
  window.InStockChainSources = () => ({reset() {}, context: () => null, document: () => null,
    mount: () => window.document.createElement('span')});
  window.eval(script);
  return {dom, window,
    context: () => context(),
    action: async (input = {}, id = 'analysis.industry-chain') => handler(id, input),
    edit(id, value) {
      const element = window.document.getElementById(id);
      element.value = value;
      element.dispatchEvent(new window.Event('input', {bubbles: true}));
    },
    text: id => window.document.getElementById(id).textContent,
  };
}

test('UI action validates the visible packet and awaits the rendered, unverified result', async () => {
  let submitted;
  const p = page({fetchAnalysis: async (url, options) => {
    submitted = JSON.parse(options.body);
    assert.equal(url, '/api/v1/industry-chain/research');
    assert.equal(options.method, 'POST');
    return {ok: true, json: async () => ({ok: true, data: result(submitted)})};
  }});
  try {
    assert.equal(p.context().actions[0].available, false);
    const value = {...packet(), notes: ['一', '二']};
    p.edit('chain-packet-input', JSON.stringify(value));
    await assert.rejects(p.action({packet: value}), /隐藏输入/);
    assert.equal(submitted, undefined);
    const response = await p.action();
    assert.equal(submitted.notes, '一；二');
    assert.deepEqual(submitted.evidence, value.evidence);
    assert.equal(response.snapshot.snapshot_id, 'test-chain');
    assert.equal(response.verification.sources_verified, false);
    assert.match(p.text('chain-state'), /来源及主张待核验/);
    assert.equal(p.context().data.dataState, 'partial');
    assert.equal(p.context().tasks.length, 0);
  } finally {p.dom.window.close();}
});

test('unrated relationships retain notes and never display a fabricated zero score', async () => {
  const value = packet();
  value.notes = '联网被拒绝，官方原文尚未核验';
  const payload = result(value);
  payload.summary.notes = value.notes;
  payload.chain = {nodes: [{id: 'upstream', name: '待核验节点', stage: 'upstream', role: '来源待核验',
    criticality_score: null, bottleneck_score: null, layer_count: 0, evidence_ids: ['source-1'], evidence_summary: {total: 1}}], links: [], critical_nodes: []};
  const p = page({fetchAnalysis: async () => ({ok: true, json: async () => ({ok: true, data: payload})})});
  try {
    p.edit('chain-packet-input', JSON.stringify(value));
    await p.action();
    assert.equal(p.window.document.querySelector('.chain-node-score').textContent, '待评级');
    assert.match(p.text('chain-critical-list'), /暂无可评级/);
    assert.match(p.text('chain-layer-list'), /未补零/);
    assert.match(p.text('chain-footnote'), /联网被拒绝/);
    assert.equal(p.context().data.summary.notes, value.notes);
  } finally {p.dom.window.close();}
});

test('manual host result keeps confirmed company material and graph references', async () => {
  const material = {sourceSnapshotId: 'financial-1'};
  const map = {artifactId: 'graph-1', reviewRequired: true};
  const evidence = {id: 'company-revenue', claim: '已确认收入材料，不证明供需关系'};
  let submitted, agentCalls = 0;
  const p = page({config: {user: {id: 'u'}, workspace: {id: 'w'}, runtime: {aiExecution: 'host'}},
    requestAgent: () => {agentCalls++;}, canInvokeAction: () => true,
    invokeAction: async (id, input) => {
      submitted = input; return {ok: true, data: result(input)};
    }}, {material, map, evidence});
  try {
    p.edit('chain-theme-input', '测试产业链');
    p.edit('chain-date-input', '2026-10-15');
    await p.window.InStockIndustryChainResearch.collect();
    assert.equal(p.context().selection.collectionTask.status, 'host-pending');
    p.edit('chain-packet-input', JSON.stringify({...packet(),
      evidence: [...packet().evidence, {id: evidence.id, claim: '不采用Agent改写的收入主张'}]}));
    const response = await p.action();
    assert.equal(agentCalls, 1);
    assert.deepEqual(submitted.evidence.find(row => row.id === evidence.id), evidence);
    assert.equal(response.materialUsedInCurrentResearch, material);
    assert.equal(response.industryMapInputUsed, map);
    assert.equal(p.context().selection.materialUsedInCurrentResearch, material);
    assert.equal(p.context().selection.collectionTask.status, 'completed');
    assert.equal(p.context().selection.collectionTask.industryMapInputUsed, map);
  } finally {p.dom.window.close();}
});

test('invalid JSON, service failure and busy requests cannot report validation success', async () => {
  let complete;
  const p = page({canInvokeAction: () => true, invokeAction: () => new Promise(resolve => {complete = resolve;})});
  try {
    p.edit('chain-packet-input', '{invalid');
    await assert.rejects(p.action(), /不是有效 JSON/);
    assert.equal(complete, undefined);
    p.edit('chain-packet-input', JSON.stringify(packet()));
    const pending = p.action();
    await assert.rejects(p.action(), /正在处理/);
    complete({ok: false, error: {message: '引用不存在'}});
    await assert.rejects(pending, /引用不存在/);
    assert.match(p.text('chain-alert'), /引用不存在/);
    assert.equal(p.context().data.snapshot, undefined);
    assert.equal(p.context().tasks.length, 0);
  } finally {p.dom.window.close();}
});

test('changed packet or workspace rejects late results without overwriting the new page', async () => {
  const pending = [];
  const config = {user: {id: 'u'}, workspace: {id: 'a'}, instanceId: 'page-1'};
  const p = page({config, canInvokeAction: () => true,
    invokeAction: () => new Promise(resolve => pending.push(resolve))});
  try {
    p.edit('chain-packet-input', JSON.stringify(packet()));
    const old = p.action();
    p.edit('chain-packet-input', JSON.stringify({...packet(), theme: '新研究'}));
    const current = p.action();
    pending[1]({ok: true, data: result({...packet(), theme: '新研究'})});
    await current;
    pending[0]({ok: true, data: result(packet())});
    await assert.rejects(old, /已变化/);
    assert.equal(p.text('stat-chain-theme'), '新研究');
    assert.equal(p.window.document.getElementById('chain-alert').style.display, 'none');
    const switched = p.action();
    config.workspace.id = 'b';
    p.window.document.dispatchEvent(new p.window.Event('vibedesk:init'));
    pending[2]({ok: true, data: result(packet())});
    await assert.rejects(switched, /已变化/);
    assert.equal(p.context().data.snapshot, undefined);
    assert.equal(p.window.document.getElementById('chain-packet-input').value, '');
    assert.equal(p.window.document.getElementById('chain-alert').style.display, 'none');
  } finally {p.dom.window.close();}
});
