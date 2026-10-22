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
