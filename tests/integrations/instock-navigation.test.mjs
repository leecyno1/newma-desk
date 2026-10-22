import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
const script = readFileSync(`${root}/instock/web/static/js/stock-suite-shell.js`, 'utf8');
function page({embedded = true, ready = true} = {}) {
  const dom = new JSDOM('<main></main><form id="stock-suite-search"><input id="stock-suite-symbol"></form>',
    {url: 'http://localhost/mods/czsc', runScripts: 'outside-only'});
  const {window} = dom, calls = [];
  window.InStockNewmaDesk = {embedded, navigate(modId, search) {calls.push({modId, search}); return ready;}};
  window.eval(script);
  function link(href, options = {}) {
    const a = window.document.createElement('a');
    a.href = href; a.target = '_blank'; a.innerHTML = '<span>进入研究</span>';
    window.document.querySelector('main').append(a);
    if (options.download) a.setAttribute('download', 'report');
    if (options.handled) a.addEventListener('click', e => e.preventDefault());
    const event = new window.MouseEvent(options.type || 'click', {bubbles: true, cancelable: true,
      button: options.button || 0, ctrlKey: Boolean(options.ctrlKey)});
    a.firstElementChild.dispatchEvent(event);
    return event;
  }
  return {dom, window, calls, link};
}

test('embedded internal links preserve source evidence and route via Desk', () => {
  const p = page();
  try {
    const query = '?symbol=300502&bars=120&asOf=2026-10-19&sourceModule=instock-czsc&sourceSnapshotId=czsc%3Aevidence';
    for (const route of ['stock-research', 'czsc', 'stock-candidates', 'industry-chain', 'strategy-validation', 'research-book', 'rotation', 'event-flow', 'market-map', 'market-workbench', 'technical-signals']) {
      assert.equal(p.link(`/mods/${route}${query}`).defaultPrevented, true);
      assert.deepEqual(p.calls.at(-1), {modId: `instock-${route}`, search: query});
    }
    assert.equal(p.calls.length, 11);
  } finally {p.dom.window.close();}
});

test('embedded unavailable navigation shows failure and never falls into standalone', () => {
  const p = page({ready: false});
  try {
    assert.equal(p.link('/mods/stock-research?symbol=300502').defaultPrevented, true);
    assert.match(p.window.document.querySelector('[role="alert"]').textContent, /未切换到独立页面/);
    assert.equal(p.window.location.pathname, '/mods/czsc');
  } finally {p.dom.window.close();}
});

test('standalone, external, downloads and already handled links retain their own behavior', () => {
  for (const embedded of [true, false]) {
    const p = page({embedded});
    try {
      if (!embedded) assert.equal(p.link('/mods/stock-research').defaultPrevented, false);
      assert.equal(p.link('https://example.org/mods/stock-research').defaultPrevented, false);
      assert.equal(p.link('/mods/stock-research', {download: true}).defaultPrevented, false);
      assert.equal(p.link('/mods/stock-research', {handled: true}).defaultPrevented, true);
      assert.equal(p.calls.length, 0);
    } finally {p.dom.window.close();}
  }
});

test('modified clicks and shared search do not escape the embedded workspace', () => {
  const p = page();
  try {
    assert.equal(p.link('/mods/czsc?code=300502', {ctrlKey: true}).defaultPrevented, true);
    assert.equal(p.link('/mods/czsc?code=300502', {type: 'auxclick', button: 1}).defaultPrevented, true);
    p.window.document.getElementById('stock-suite-symbol').value = '600519';
    p.window.document.getElementById('stock-suite-search').dispatchEvent(new p.window.Event('submit', {bubbles: true, cancelable: true}));
    assert.equal(p.calls.length, 3);
    assert.deepEqual(p.calls.at(-1), {modId: 'instock-stock-research', search: '?symbol=600519&period=daily&bars=240'});
  } finally {p.dom.window.close();}
});

function runtimePage(fetchHealth) {
  const dom = new JSDOM('<div class="stock-suite-runtime"><span id="stock-suite-runtime-state"></span></div>',
    {url: 'http://localhost/mods/strategy-validation', runScripts: 'outside-only'});
  dom.window.fetch = fetchHealth;
  dom.window.eval(script);
  const settle = () => new Promise(resolve => setImmediate(resolve));
  return {dom, window: dom.window, settle,
    root: dom.window.document.querySelector('.stock-suite-runtime'),
    state: dom.window.document.getElementById('stock-suite-runtime-state')};
}
const healthResponse = marketData => ({ok: true, json: async () => ({ok: true,
  data: {readiness: {status: 'ready', market_data: marketData}}})});

test('runtime badge rechecks actual health after analysis instead of retaining an outage', async () => {
  let ready = false, calls = 0;
  const p = runtimePage(async () => {calls++; return healthResponse(ready);});
  try {
    await p.settle();
    assert.equal(p.state.textContent, '数据不可用');
    ready = true;
    p.window.InStockAnalysisHistory.rendered('latest');
    await p.settle();
    assert.equal(calls, 2);
    assert.equal(p.state.textContent, '正常');
    assert.equal(p.root.className, 'stock-suite-runtime is-ready');
  } finally {p.window.close();}
});

test('runtime badge reflects failure and recovery when returning to the page', async () => {
  let fail = false;
  const p = runtimePage(async () => {if (fail) throw new Error('offline'); return healthResponse(true);});
  try {
    await p.settle();
    fail = true;
    p.window.dispatchEvent(new p.window.Event('focus'));
    await p.settle();
    assert.equal(p.state.textContent, '不可用');
    assert.equal(p.root.className, 'stock-suite-runtime is-error');
    fail = false;
    Object.defineProperty(p.window.document, 'visibilityState', {value: 'visible'});
    p.window.document.dispatchEvent(new p.window.Event('visibilitychange'));
    await p.settle();
    assert.equal(p.state.textContent, '正常');
    assert.equal(p.root.className, 'stock-suite-runtime is-ready');
  } finally {p.window.close();}
});

test('simultaneous runtime triggers share the in-flight health check', async () => {
  let finish, calls = 0;
  const p = runtimePage(() => {calls++; return new Promise(resolve => {finish = resolve;});});
  try {
    p.window.InStockAnalysisHistory.rendered('latest');
    p.window.dispatchEvent(new p.window.Event('focus'));
    assert.equal(calls, 1);
    finish(healthResponse(true));
    await p.settle();
    assert.equal(p.state.textContent, '正常');
  } finally {p.window.close();}
});
