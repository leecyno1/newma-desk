import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
const tick = () => new Promise(resolve => setImmediate(resolve));
function panel(name) {
  const dom = new JSDOM('<main class="market-workbench"><section id="panel"></section></main>', {url: 'http://localhost/mods/market-workbench', runScripts: 'outside-only'});
  const {window} = dom, requests = [];
  window.fetch = () => {throw new Error('anonymous fetch is forbidden');};
  window.InStockNewmaDesk = {fetchAnalysis(url, options = {}) {
    return new Promise(resolve => requests.push({url, options, resolve: (data, status = 200) => resolve({
      ok: status === 200, status, json: async () => ({ok: status === 200, data}),
    })}));
  }};
  window.eval(readFileSync(`${root}/instock/web/static/js/market-${name}.js`, 'utf8'));
  const factories = {structure: 'InStockMarketStructure', continuity: 'InStockMarketContinuity', evidence: 'InStockMarketEvidence', journal: 'InStockMarketJournal'};
  const container = window.document.getElementById('panel');
  const api = name === 'journal' ? window[factories[name]](container, () => ({}), () => {})
    : window[factories[name]](container, () => {}, () => '2026-10-22', () => {});
  return {dom, window, requests, api, container,
    change: () => window.document.dispatchEvent(new window.CustomEvent('instock:session-changed'))};
}

for (const name of ['structure', 'continuity', 'evidence']) {
  test(`${name}: uses signed transport, clears selection and ignores late old-session data`, async () => {
    const p = panel(name);
    try {
      const pending = name === 'evidence' ? p.api.select({code: '512800', industry: '银行'}, '2026-10-22') : p.api.refresh(false);
      assert.equal(p.requests.length, 1);
      p.change();
      assert.equal(p.requests[0].options.signal.aborted, true);
      p.requests[0].resolve({schemaVersion: `newma-desk.market-${name}.v1`, code: '512800', requestedDate: '2026-10-22'});
      await pending;
      assert.equal(p.api.context().data, null);
      assert.equal(p.api.context().loading, false);
      if (name === 'evidence') assert.equal(p.api.context().selected, null);
      const next = name === 'evidence' ? p.api.select({code: '512800', industry: '银行'}, '2026-10-22') : p.api.refresh(false);
      p.requests.at(-1).resolve({}, 403); await next;
      assert.match(p.api.context().error, /尚未获得当前工作区授权/);
      assert.equal(p.api.context().data, null);
    } finally {p.dom.window.close();}
  });
}

test('journal: session change removes drafts and old lists; late save cannot restore a record', async () => {
  const p = panel('journal');
  try {
    const form = p.container.querySelector('[data-journal-form]');
    form.elements.judgment.value = 'synthetic old account judgment';
    form.elements.watch.value = 'synthetic observation';
    p.container.querySelector('[data-journal-reload]').click();
    form.dispatchEvent(new p.window.Event('submit', {bubbles: true, cancelable: true}));
    assert.equal(p.requests.length, 2);
    assert.equal(p.requests[1].options.method, 'POST');
    p.change();
    assert.equal(form.elements.judgment.value, '');
    p.requests[0].resolve({items: [{id: 'old', judgment: 'old account'}], hasMore: false, offset: 0});
    p.requests[1].resolve({id: 'old', evidence: {}, notes: {}, checks: [], asOf: '2026-10-22'});
    await tick();
    assert.equal(p.api.context().mode, 'live');
    assert.equal(p.api.context().followUpQueue, null);
    assert.equal(p.container.querySelector('[data-journal-record]').textContent, '');
    assert.equal(p.container.querySelector('.journal-list').textContent, '');
    assert.doesNotMatch(p.container.textContent, /复盘已保存|old account/);
    p.container.querySelector('[data-journal-reload]').click();
    p.requests.at(-1).resolve({}, 403); await tick();
    assert.match(p.container.textContent, /未读取或写入本机共享记录/);
  } finally {p.dom.window.close();}
});
