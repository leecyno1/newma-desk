import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { collect } from '../sources/yfinance.mjs';
import { synthesize } from '../../dashboard/inject.mjs';

test('synthesis retains unknown daily change and original observation time', async (t) => {
  t.mock.method(globalThis, 'fetch', async url => String(url).includes('/TLT?')
    ? Response.json({ chart: { result: [{ meta: { regularMarketPrice: 110,
      regularMarketTime: 1793044800, currency: 'USD' } }] } })
    : new Response('', { status: 403 }));
  const data = await collect();
  const view = await synthesize({ crucix: {}, sources: { YFinance: data } }, { refreshNews: false });
  assert.equal(view.markets.rates[0].changePct, null);
  assert.equal(view.markets.rates[0].observedAt, '2026-10-26T20:00:00.000Z');
  assert.equal(view.markets.rates[0].currency, 'USD');
  assert.equal(view.markets.vix, null);
  assert.equal(view.health[0].status, 'partial');
  assert.match(view.health[0].reason, /403/);
});

test('actual card renderer distinguishes missing change, unchanged price and unknown currency', () => {
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const start = html.indexOf('  const mktCard = (q) => {');
  const end = html.indexOf('\n  // VIX', start);
  assert.ok(start >= 0 && end > start);
  const render = vm.runInNewContext(`${html.slice(start, end)}\nmktCard`);
  const q = { symbol: 'TLT', name: '20Y+ Treasury', price: 110, changePct: null, currency: null };
  const unknown = render(q);
  assert.match(unknown, /Change unavailable/);
  assert.doesNotMatch(unknown, /null%|0%|9650|9660|\$/);
  assert.match(render({ ...q, changePct: 0, currency: 'USD' }), /\+0%/);
  assert.match(render({ ...q, currency: 'USD' }), /\$110/);
  assert.match(render({ ...q, currency: 'HKD' }), /110 HKD/);
  assert.equal(render({ ...q, price: null }), '');
});
