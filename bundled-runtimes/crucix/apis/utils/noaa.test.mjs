import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { briefing, getActiveAlerts } from '../sources/noaa.mjs';
import { synthesize } from '../../dashboard/inject.mjs';
import { sourceOutcome } from './source-health.mjs';

const feature = (id, geometry = null) => ({ id: `https://api.weather.gov/alerts/${id}`, geometry,
  properties: { id, event: 'Coastal Flood Warning', severity: 'Severe', areaDesc: 'Example coastal region',
    headline: 'Synthetic warning', sent: '2026-10-27T07:00:00Z', onset: '2026-10-27T06:00:00Z', expires: '2026-10-27T10:00:00Z' } });

test('active collection never sends unsupported pagination limit and retains filters', async t => {
  let seen;
  t.mock.method(globalThis, 'fetch', async url => { seen = new URL(url); return Response.json({ features: [] }); });
  await getActiveAlerts({ limit: 50, severity: 'Extreme,Severe', urgency: 'Immediate', event: 'Flood Warning' });
  assert.equal(seen.pathname, '/alerts/active');
  assert.equal(seen.searchParams.has('limit'), false);
  assert.equal(seen.searchParams.get('status'), 'actual');
  assert.equal(seen.searchParams.get('severity'), 'Extreme,Severe');
  assert.equal(seen.searchParams.get('urgency'), 'Immediate');
});

test('request rejection and malformed data never become zero warnings or leak bodies', async t => {
  const mock = t.mock.method(globalThis, 'fetch', async () => new Response('private diagnostic', { status: 400 }));
  let result = await briefing();
  assert.equal(result.totalSevereAlerts, null);
  assert.equal(result.httpStatus, 400);
  assert.match(sourceOutcome('NOAA', result).reason, /400/);
  assert.doesNotMatch(JSON.stringify(result), /private/);
  const view = await synthesize({ sources: { NOAA: result } }, { refreshNews: false });
  assert.equal(view.noaa.totalAlerts, null);
  mock.mock.mockImplementation(async () => Response.json({ unexpected: [] }));
  result = await briefing();
  assert.equal(result.errorCode, 'INVALID_RESPONSE');
});

test('valid empty alerts are zero, not a request failure', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ features: [], updated: '2026-10-27T07:00:00Z' }));
  const result = await briefing();
  assert.equal(result.totalSevereAlerts, 0);
  assert.equal(result.status, 'ok');
  assert.equal(sourceOutcome('NOAA', result).status, 'ok');
});

test('warnings without geometry retain identity, source time and coverage through synthesis', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ features: Array.from({ length: 61 }, (_, i) => feature(String(i))) }));
  const result = await briefing();
  assert.equal(result.totalSevereAlerts, 61);
  assert.equal(result.topAlerts.length, 50);
  assert.equal(result.coverage.complete, true);
  assert.equal(result.coverage.displayed, 50);
  const view = await synthesize({ sources: { NOAA: result } }, { refreshNews: false });
  assert.equal(view.noaa.totalAlerts, 61);
  assert.equal(view.noaa.alerts.length, 50);
  assert.equal(view.noaa.alerts[0].sent, '2026-10-27T07:00:00Z');
  assert.equal(view.noaa.alerts[0].lat, null);
});

test('malformed records are partial; multipolygon reference includes all exterior rings', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ features: [null, feature('multi', {
    type: 'MultiPolygon', coordinates: [[[[0, 0], [2, 0], [2, 2], [0, 0]]], [[[10, 10], [12, 10], [12, 12], [10, 10]]]],
  }), feature('bad', { type: 'Point', coordinates: [200, 95] })] }));
  const result = await briefing();
  assert.equal(result.status, 'partial');
  assert.equal(result.coverage.invalid, 1);
  assert.equal(result.topAlerts[0].lon, 6);
  assert.equal(result.topAlerts[0].lat, 6);
  assert.equal(result.topAlerts[0].geoBasis, 'alert-area-bounds-center');
  assert.equal(result.topAlerts[1].lat, null);
});

test('both map modes only map validated weather geometry, never null coordinates at zero', () => {
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const reference = html.match(/function referenceMapItems\(items, basis\) \{[\s\S]*?\n\}/)[0];
  const weather = html.match(/function weatherMapItems\(items\) \{[\s\S]*?\n\}/)[0];
  const run = vm.runInNewContext(`${reference}\n${weather};weatherMapItems`);
  const result = run([{ lat: null, lon: null }, { lat: 0, lon: 0, geoBasis: 'source-point' },
    { lat: 1, lon: 2, geoBasis: 'alert-area-bounds-center' }, { lat: 2, lon: 3 }]);
  assert.equal(result.length, 2);
  assert.equal((html.match(/weatherMapItems\(D.noaa\?\.alerts\)/g) || []).length, 2);
});
