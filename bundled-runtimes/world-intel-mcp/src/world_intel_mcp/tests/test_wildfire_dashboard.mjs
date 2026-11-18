import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../dashboard/index.html', import.meta.url), 'utf8');
for (const block of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(block[1]);
const mapCode = html.slice(html.indexOf('function isCurrentFireRegion(region)'), html.indexOf('function updateMapConvergence(data)'));
const hudCode = html.slice(html.indexOf('function updateHudStats(data)'), html.indexOf('// ════════════ DATA DRAWER'));
const elements = { '#cntFires': {}, '#hudStats': {} };
const layer = { markers: [], clearLayers() { this.markers = []; }, getLayers() { return this.markers; } };
const context = vm.createContext({
  $: selector => elements[selector], mapLayers: { fires: layer }, safe: value => value,
  esc: value => String(value), showDetail() {},
  L: { divIcon: () => ({}), marker: () => ({ bindTooltip() {}, on() {}, addTo(target) { target.markers.push(this); } }) },
});
vm.runInContext(mapCode + '\n' + hudCode, context);
context.updateMapFires(null);
assert.equal(elements['#cntFires'].textContent, 'unknown');
const data = { status: 'partial', total_fires: null, coverage: { available: 1, requested: 2 }, fires_by_region: {
  fresh: { status: 'ok', freshness: 'fresh', collected_at: '2020-01-01T00:00:00Z', cache_expires_at: '2099-01-01T00:00:00Z', top_clusters: [{ lat: 1, lon: 2, fire_count: 1 }] },
  stale: { status: 'stale', top_clusters: [{ lat: 3, lon: 4, fire_count: 4 }] },
  expired: { status: 'ok', freshness: 'fresh', collected_at: '2000-01-01T00:00:00Z', cache_expires_at: '2000-01-02T00:00:00Z', top_clusters: [{ lat: 5, lon: 6, fire_count: 2 }] },
} };
context.updateMapFires(data);
assert.equal(layer.markers.length, 1);
assert.match(elements['#cntFires'].title, /partial.*1\/2/i);
context.updateHudStats({ wildfires: data });
assert.match(elements['#hudStats'].innerHTML, /partial/i);
assert.doesNotMatch(elements['#hudStats'].innerHTML, /class="v (warn|crit)"/);
const expiredOnly = { status: 'ok', freshness: 'fresh', fires_by_region: { expired: data.fires_by_region.expired } };
context.updateMapFires(expiredOnly);
context.updateHudStats({ wildfires: expiredOnly });
assert.equal(elements['#cntFires'].textContent, 'unknown');
assert.match(elements['#hudStats'].innerHTML, /unknown/);
const detailCode = html.slice(html.indexOf('var COLORS ='), html.indexOf("$('#detailClose')"));
Object.assign(elements, { '#detailHeader': {}, '#detailBody': {}, '#detail': { classList: { add() {} } } });
context._clearWebcamRefresh = () => {};
vm.runInContext(detailCode, context);
context.showDetail('fire', { lat: 1, lon: 2, fire_count: 60, max_frp: 120, _region: 'sample' });
assert.match(elements['#detailHeader'].innerHTML, /thermal/i);
assert.match(elements['#detailBody'].innerHTML, /not verified/i);
assert.doesNotMatch(elements['#detailBody'].innerHTML, /df-v (crit|high)/);
console.log('wildfire dashboard states passed');
