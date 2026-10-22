import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
const source = readFileSync(`${root}/instock/web/static/js/vibedesk-bridge.js`, 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
function bridge() {
  const dom = new JSDOM('<main><h1>测试</h1></main>', {url: 'http://127.0.0.1:19988/mods/research-book',
    referrer: 'http://127.0.0.1:5888/', runScripts: 'outside-only'});
  const {window} = dom, messages = [];
  Object.assign(window, {Headers, AbortController, AbortSignal});
  const parent = {postMessage(message) {messages.push(message);}};
  Object.defineProperty(window, 'parent', {value: parent});
  Object.defineProperty(window.document, 'currentScript', {value: {dataset: {
    modId: 'instock-research-book', parentOrigins: 'http://127.0.0.1:5888'}}});
  const send = (data, origin = 'http://127.0.0.1:5888', from = parent) => window.dispatchEvent(new window.MessageEvent('message', {data, origin, source: from}));
  window.eval(source);
  const init = {type: 'vibedesk:init', protocolVersion: '1.0', instanceId: 'one', modId: 'instock-research-book',
    workspace: {id: 'workspace'}, user: {id: 'user'}, environment: {theme: 'light', locale: 'zh-CN', timezone: 'Asia/Shanghai'},
    grants: {actions: ['analysis.research-book']}};
  send(init);
  const request = {type: 'vibedesk:ui-action-request', requestId: 'request-one', instanceId: 'one',
    modId: 'instock-research-book', actionId: 'analysis.research-book', input: {}};
  return {dom, api: window.InStockNewmaDesk, messages, send, init, request};
}

function signed(b, overrides = {}) {
  return {...b.init, session: {accessToken: 'synthetic-a', expiresAt: new Date(Date.now() + 60000).toISOString()},
    grants: {actions: ['analysis.research-book'], permissions: ['analysis.read']}, ...overrides};
}

test('session cleanup publishes only the fully cleared multi-panel context', async () => {
  const b = bridge();
  try {
    const init = signed(b); b.send(init); await tick();
    let oldEvidence = 'old account';
    b.api.setContextProvider(() => ({view: {id: 'page', title: '测试'}, data: {summary: {oldEvidence}}}));
    b.dom.window.document.addEventListener('instock:session-changed', () => b.api.publishContext());
    b.dom.window.document.addEventListener('instock:session-changed', () => {oldEvidence = null;});
    b.messages.length = 0; b.send({...init, instanceId: 'two'}); await tick();
    const contexts = b.messages.filter(m => m.type === 'vibedesk:context');
    assert.equal(contexts.length, 1);
    assert.equal(contexts[0].context.data.summary.oldEvidence, null);
  } finally {b.dom.window.close();}
});

test('analysis transport uses current signature and ignores theme-only init', async () => {
  const b = bridge();
  try {
    const init = signed(b); b.send(init);
    let options, complete;
    b.dom.window.fetch = (_, value) => {options = value; return new Promise(resolve => {complete = resolve;});};
    const pending = b.api.fetchAnalysis('/api/v1/analysis-history'); await tick();
    const revision = b.api.sessionRevision;
    b.send({...init, environment: {...init.environment, theme: 'dark'}});
    assert.equal(b.api.sessionRevision, revision);
    assert.equal(options.signal.aborted, false);
    assert.equal(options.headers.get('X-Newma-Desk-Session'), 'synthetic-a');
    assert.equal(options.credentials, 'omit'); assert.equal(options.redirect, 'error');
    complete({json: async () => ({data: [1]})});
    assert.deepEqual(await (await pending).json(), {data: [1]});
  } finally {b.dom.window.close();}
});

for (const field of ['token', 'instance', 'permissions', 'actions']) {
  test(`analysis response is rejected after ${field} changes and returns to A`, async () => {
    const b = bridge();
    try {
      const init = signed(b); b.send(init);
      let complete, options;
      b.dom.window.fetch = (_, value) => {options = value; return new Promise(resolve => {complete = resolve;});};
      const pending = b.api.fetchAnalysis('/api/v1/analysis-history'); await tick();
      const changed = field === 'token' ? {...init, session: {...init.session, accessToken: 'synthetic-b'}}
        : field === 'instance' ? {...init, instanceId: 'two'}
        : {...init, grants: {...init.grants, [field]: []}};
      b.send(changed); b.send(init);
      assert.equal(options.signal.aborted, true);
      complete({json: async () => ({private: 'old'})});
      await assert.rejects(pending, /丢弃旧研究响应/);
    } finally {b.dom.window.close();}
  });
}

test('body parsing and page action results cannot cross A to B to A', async () => {
  const b = bridge();
  try {
    const init = signed(b); b.send(init);
    let finishBody, finishAction;
    b.dom.window.fetch = async () => ({json: () => new Promise(resolve => {finishBody = resolve;})});
    const response = await b.api.fetchAnalysis('/api/v1/analysis-history');
    const body = response.json();
    b.api.setUiActionHandler(() => new Promise(resolve => {finishAction = resolve;}));
    b.send(b.request); await tick();
    b.send({...init, instanceId: 'two'}); b.send(init);
    finishAction({private: 'old'}); finishBody({private: 'old'});
    await assert.rejects(body, /丢弃旧研究响应/); await tick();
    assert.equal(b.messages.filter(m => m.type === 'vibedesk:ui-action-result').length, 0);
  } finally {b.dom.window.close();}
});

test('expired and malformed or missing analysis grants never fetch', async () => {
  const b = bridge();
  try {
    let calls = 0; b.dom.window.fetch = async () => {calls++;};
    for (const permissions of [[], 'analysis.read', {}]) {
      b.send(signed(b, {grants: {permissions}}));
      await assert.rejects(b.api.fetchAnalysis('/api/v1/analysis-history'), /会话尚未就绪/);
    }
    b.send(signed(b, {session: {accessToken: 'synthetic', expiresAt: '2000-01-01'}}));
    await assert.rejects(b.api.fetchAnalysis('/api/v1/analysis-history'), /会话尚未就绪/);
    assert.equal(calls, 0);
  } finally {b.dom.window.close();}
});

test('history changes with the session, not the theme, and ignores late restores', async () => {
  const b = bridge();
  try {
    const init = signed(b); b.send(init);
    b.dom.window.document.body.innerHTML = '<button id="stock-suite-history-button"></button><section id="stock-suite-history"><div id="stock-suite-history-list"></div></section>';
    const requests = [], selections = [];
    b.api.fetchAnalysis = url => new Promise(resolve => requests.push({url, resolve: data => resolve({ok: true, json: async () => ({data})})}));
    b.dom.window.document.addEventListener('instock:history-selected', event => selections.push(event.detail));
    b.dom.window.eval(readFileSync(`${root}/instock/web/static/js/stock-suite-shell.js`, 'utf8'));
    assert.equal(requests.length, 1);
    b.send({...init, environment: {...init.environment, theme: 'dark'}});
    assert.equal(requests.length, 1);
    const record = {history_id: 'one', title: 'old account', generated_at: '2026-10-01'};
    requests[0].resolve([record]); await tick();
    b.dom.window.document.querySelector('.stock-suite-history-item').click();
    assert.equal(requests.length, 2);
    b.send({...init, instanceId: 'two'});
    assert.equal(requests.length, 3);
    requests[1].resolve({...record, payload: {private: 'old'}}); await tick();
    assert.equal(selections.length, 0);
    assert.doesNotMatch(b.dom.window.document.getElementById('stock-suite-history-list').textContent, /old account/);
    requests[2].resolve([]); await tick();
  } finally {b.dom.window.close();}
});

test('page actions await completion, return result and publish updated context', async () => {
  const b = bridge();
  try {
    let complete, count = 0;
    b.api.setContextProvider(() => ({view: {id: 'book', title: '测试'}, data: {summary: {count}}}));
    b.api.setUiActionHandler(() => new Promise(resolve => {complete = () => {count = 1; resolve({count});};}));
    b.send(b.request); await tick();
    assert.equal(b.messages.filter(m => m.type === 'vibedesk:ui-action-result').length, 0);
    complete(); await tick();
    const reply = b.messages.find(m => m.type === 'vibedesk:ui-action-result');
    assert.equal(reply.ok, true); assert.equal(reply.result.count, 1);
    assert.equal(b.messages.at(-1).type, 'vibedesk:context');
    assert.equal(b.messages.at(-1).context.data.summary.count, 1);
  } finally {b.dom.window.close();}
});

test('untrusted, stale and ungranted messages do not execute page actions', async () => {
  const b = bridge();
  try {
    let calls = 0;
    b.api.setUiActionHandler(() => {calls++;});
    b.send(b.request, 'https://untrusted.example');
    b.send(b.request, 'http://127.0.0.1:5888', {});
    b.send({...b.request, instanceId: 'old'});
    b.send({...b.request, actionId: 'analysis.not-granted'});
    await tick(); assert.equal(calls, 0);
    assert.equal(b.messages.at(-1).error.code, 'action_not_granted');
    b.api.setUiActionHandler(() => {throw new Error('真实失败');});
    b.send(b.request); await tick();
    const reply = b.messages.findLast(m => m.type === 'vibedesk:ui-action-result');
    assert.equal(reply.ok, false); assert.equal(reply.error.message, '真实失败');
  } finally {b.dom.window.close();}
});

test('a late result is not delivered after workspace changes', async () => {
  const b = bridge();
  try {
    let complete;
    b.api.setUiActionHandler(() => new Promise(resolve => {complete = resolve;}));
    b.send(b.request);
    b.send({...b.init, instanceId: 'two', workspace: {id: 'different'}});
    complete({done: true}); await tick();
    assert.equal(b.messages.filter(m => m.type === 'vibedesk:ui-action-result').length, 0);
  } finally {b.dom.window.close();}
});

test('data actions use the host deadline once, without resolving early or retrying', async () => {
  const b = bridge();
  try {
    const timers = new Map(); let sequence = 0, now = 0;
    b.dom.window.setTimeout = (fn, ms) => {timers.set(++sequence, {fn, at: now + ms}); return sequence;};
    b.dom.window.clearTimeout = id => timers.delete(id);
    const advance = ms => {now += ms; for (const [id, timer] of timers) if (timer.at <= now) {timers.delete(id); timer.fn();}};
    let settled = false;
    const action = b.api.invokeAction('analysis.research-book', {}).finally(() => {settled = true;});
    const request = b.messages.find(m => m.type === 'vibedesk:action-request');
    const pending = {...request, type: 'vibedesk:action-pending', timeoutSeconds: 120}; delete pending.input;
    b.send({...pending, timeoutSeconds: 300}, 'https://untrusted.example');
    b.send({...pending, actionId: 'analysis.other'});
    b.send({...pending, timeoutSeconds: 301});
    assert.equal([...timers.values()][0].at, 35000);
    b.send(pending);
    advance(68000); await tick();
    assert.equal(settled, false);
    b.send({...pending, timeoutSeconds: 300});
    assert.equal([...timers.values()][0].at, 120000, 'duplicate pending cannot keep extending the request');
    b.send({...request, input: undefined, type: 'vibedesk:action-result', status: 200, ok: true, result: {count: 49}});
    assert.equal((await action).count, 49);
    assert.equal(timers.size, 0);
    assert.equal(b.messages.filter(m => m.type === 'vibedesk:action-request').length, 1);
  } finally {b.dom.window.close();}
});

test('a host deadline reports unknown completion and ignores a late result', async () => {
  const b = bridge();
  try {
    const timers = new Map(); let sequence = 0;
    b.dom.window.setTimeout = (fn, ms) => {timers.set(++sequence, {fn, ms}); return sequence;};
    b.dom.window.clearTimeout = id => timers.delete(id);
    const action = b.api.invokeAction('analysis.research-book', {});
    const rejected = assert.rejects(action, /结果尚未确认.*可能仍在运行/);
    const request = b.messages.find(m => m.type === 'vibedesk:action-request');
    b.send({...request, type: 'vibedesk:action-pending', timeoutSeconds: 120});
    [...timers.values()][0].fn();
    await rejected;
    b.send({...request, type: 'vibedesk:action-result', status: 200, ok: true, result: {count: 49}});
    assert.equal(b.messages.filter(m => m.type === 'vibedesk:action-request').length, 1);
  } finally {b.dom.window.close();}
});
