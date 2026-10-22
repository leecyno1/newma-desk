import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {JSDOM} from 'jsdom';

const root = process.env.INSTOCK_TEST_SOURCE || new URL('../../bundled-runtimes/instock-analysis/', import.meta.url).pathname;
const bridgeScript = readFileSync(`${root}/instock/web/static/js/vibedesk-bridge.js`, 'utf8');
const shellScript = readFileSync(`${root}/instock/web/static/js/stock-suite-shell.js`, 'utf8');
function page({preference, dark = false, embedded = false, storageBlocked = false} = {}) {
  const dom = new JSDOM('<label id="stock-suite-theme-control">主题<select id="stock-suite-theme"><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select></label>',
    {url: 'http://localhost/mods/research-book', runScripts: 'outside-only'});
  const {window} = dom;
  if (preference) window.localStorage.setItem('instock.theme', preference);
  if (storageBlocked) Object.defineProperty(window, 'localStorage', {get() {throw new Error('storage blocked');}});
  const system = new window.EventTarget();
  system.matches = dark;
  window.matchMedia = () => system;
  if (embedded) Object.defineProperty(window, 'parent', {value: {postMessage() {}}});
  window.eval(bridgeScript);
  window.eval(shellScript);
  const select = window.document.getElementById('stock-suite-theme');
  const choose = value => {select.value = value; select.dispatchEvent(new window.Event('change'));};
  const systemChange = value => {system.matches = value; system.dispatchEvent(new window.Event('change'));};
  return {dom, window, api: window.InStockNewmaDesk, select, choose, systemChange};
}

test('standalone defaults to system and switches using the shared theme events', () => {
  const p = page({dark: true});
  try {
    assert.equal(p.api.theme, 'dark');
    assert.equal(p.select.value, 'system');
    p.systemChange(false);
    assert.equal(p.api.theme, 'light');
    let repaint;
    p.window.document.addEventListener('instock:themechange', e => {repaint = e.detail;});
    p.choose('dark');
    assert.equal(p.api.theme, 'dark');
    assert.equal(p.window.document.documentElement.dataset.theme, 'dark');
    assert.equal(p.window.localStorage.getItem('instock.theme'), 'dark');
    assert.equal(repaint.theme, 'dark');
    p.systemChange(true); p.systemChange(false);
    assert.equal(p.api.theme, 'dark', 'explicit choice wins over system changes');
    p.choose('system');
    assert.equal(p.api.theme, 'light');
  } finally {p.dom.window.close();}
});

test('saved standalone preference survives reload and unavailable storage is optional', () => {
  for (const options of [{preference: 'dark'}, {preference: 'invalid', dark: true}, {storageBlocked: true, dark: true}]) {
    const p = page(options);
    try {
      assert.equal(p.api.theme, 'dark');
      p.choose('light');
      assert.equal(p.api.theme, 'light');
    } finally {p.dom.window.close();}
  }
});

test('embedded theme remains owned by host, not standalone preferences or controls', () => {
  const p = page({embedded: true, preference: 'dark', dark: true});
  try {
    assert.equal(p.window.document.getElementById('stock-suite-theme-control').hidden, true);
    assert.equal(p.api.setStandaloneTheme('dark'), false);
    assert.equal(p.window.localStorage.getItem('instock.theme'), 'dark');
    assert.equal(p.api.theme, 'light');
  } finally {p.dom.window.close();}
});

test('another standalone tab updates theme and selector without changing business input', () => {
  const p = page();
  try {
    const input = p.window.document.createElement('input');
    input.value = '600519';
    p.window.document.body.append(input);
    p.window.dispatchEvent(new p.window.StorageEvent('storage', {key: 'instock.theme', newValue: 'dark'}));
    assert.equal(p.api.theme, 'dark');
    assert.equal(p.select.value, 'dark');
    assert.equal(input.value, '600519');
    p.window.dispatchEvent(new p.window.StorageEvent('storage', {key: 'other.preference', newValue: 'light'}));
    assert.equal(p.api.theme, 'dark');
    p.window.dispatchEvent(new p.window.StorageEvent('storage', {key: null}));
    assert.equal(p.select.value, 'system');
    assert.equal(p.api.theme, 'light');
  } finally {p.dom.window.close();}
});
