import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const html = readFileSync(new URL('../../bundled-runtimes/instock-analysis/instock/web/templates/market_map.html', import.meta.url), 'utf8');
const source = html.slice(html.indexOf('    function buildContext()'), html.indexOf('    function publish()'));

function context(state) {
  return JSON.parse(JSON.stringify(vm.runInNewContext(`${source}; buildContext()`, {
    state, actionId: 'analysis.market-map', deskBridge: { canInvokeAction: () => true },
  })));
}

test('cloud-map context preserves current filters, selection and actual market summary', () => {
  const state = {
    capacity: 100, sizeMode: 'market_cap', industry: '银行',
    selected: { symbol: '601398', name: '工商银行' },
    data: {
      as_of: '2026-09-15', data_state: 'complete',
      summary: { advancers: 32, decliners: 66 },
      coverage: { full_market: false, displayed_securities: 100 },
      snapshot: { snapshot_id: 'test-map' },
    },
  };
  const first = context(state);
  assert.deepEqual(first.selection.security, { market: 'CN', symbol: '601398', name: '工商银行' });
  assert.deepEqual(first.filters, { capacity: 100, sizeMode: 'market_cap', industry: '银行' });
  assert.deepEqual(first.data.summary.summary, state.data.summary);
  assert.equal(first.data.summary.coverage.full_market, false);
  assert.equal(first.selectedSecurity, undefined);
  assert.deepEqual(Object.keys(first.data).sort(), ['asOf', 'freshness', 'source', 'summary']);
  state.sizeMode = 'amount';
  state.industry = '电子';
  state.selected = null;
  const second = context(state);
  assert.equal(second.filters.sizeMode, 'amount');
  assert.equal(second.filters.industry, '电子');
  assert.deepEqual(second.selection, {});
  assert.equal(first.filters.industry, '银行');
  assert.ok(Buffer.byteLength(JSON.stringify(second)) < 24000);
});

test('unloaded map reports loading without fabricating market figures', () => {
  const result = context({ data: null, selected: null, capacity: 500, sizeMode: 'amount', industry: '' });
  assert.deepEqual(result.data.summary, { status: 'loading' });
  assert.equal(result.data.asOf, undefined);
  assert.equal(result.filters.capacity, 500);
});
