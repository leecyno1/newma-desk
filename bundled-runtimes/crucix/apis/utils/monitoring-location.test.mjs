import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { briefing as airBriefing } from '../sources/opensky.mjs';
import { briefing as radiationBriefing, getMeasurements } from '../sources/safecast.mjs';
import { synthesize } from '../../dashboard/inject.mjs';
import { sourceOutcome } from './source-health.mjs';
import { computeDelta } from '../../lib/delta/engine.mjs';

test('air query centers follow source identity after reorder, not list index', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ time: Math.floor(Date.now()/1000), states: [] }));
  const source = await airBriefing();
  const view = await synthesize({ sources: { OpenSky: { ...source, hotspots: [...source.hotspots].reverse() } } }, { refreshNews: false });
  assert.equal(view.air[0].key, 'hornOfAfrica');
  assert.equal(view.air[0].lat, 10);
  assert.equal(view.air[0].lon, 47.5);
  assert.equal(view.air[0].geoBasis, 'query-bounds-center');
  assert.equal(view.air[0].total, 0);
  assert.equal(view.airMeta.fallback, false, 'valid zero must not load historical activity');
});

test('OpenSky malformed and rejected responses remain unavailable, not zero aircraft', async (t) => {
  for (const response of [{ unrelated: [] }, { error: 'unavailable' }]) {
    t.mock.method(globalThis, 'fetch', async () => Response.json(response));
    const source = await airBriefing();
    assert.equal(source.status, 'error');
    assert.ok(source.hotspots.every(h => h.totalAircraft === null && h.noCallsign === null));
    assert.equal(sourceOutcome('OpenSky', source).status, 'error');
    const view = await synthesize({ sources: { OpenSky: source } }, { refreshNews: false });
    assert.equal(view.airMeta.liveTotal, null);
  }
});

test('radiation query centers are explicit and empty or failed samples are not normal', async (t) => {
  for (const response of [[], { error: 'unavailable' }]) {
    t.mock.method(globalThis, 'fetch', async () => Response.json(response));
    const source = await radiationBriefing();
    assert.ok(source.sites.every(s => s.anomaly === null));
    assert.doesNotMatch(source.signals.join(' '), /within normal|ELEVATED RADIATION/);
    assert.equal(source.sites[0].recentReadings, Array.isArray(response) ? 0 : null);
    const view = await synthesize({ sources: { Safecast: { ...source, sites: [...source.sites].reverse() } } }, { refreshNews: false });
    assert.equal(view.nuke[0].key, 'dimona');
    assert.equal(view.nuke[0].lon, 35.15);
    assert.equal(view.nuke[0].geoBasis, 'query-radius-center');
    assert.equal(view.nuke[0].anom, null);
  }
});

test('radiation samples retain units, devices and observation times without mixed means', async (t) => {
  const recent = new Date(Date.now()-1000).toISOString();
  const old = '2000-01-01T00:00:00Z';
  const rows = [
    { value: 30, unit: 'cpm', device_id: 1, captured_at: recent },
    { value: 90, unit: 'cpm', device_id: 2, captured_at: recent },
    { value: 0.1, unit: 'usv', device_id: 1, captured_at: recent },
    { value: 999, unit: 'cpm', device_id: 1, captured_at: old },
    { value: 100, unit: 'cpm', device_id: 1, captured_at: '2099-01-01T00:00:00Z' },
  ];
  t.mock.method(globalThis, 'fetch', async () => Response.json(rows));
  let site = (await radiationBriefing()).sites[0];
  assert.equal(site.avgCPM, null);
  assert.equal(site.recentReadings, 3);
  assert.equal(site.sampleReadings, 4);
  assert.equal(site.status, 'partial');
  assert.equal(site.lastReading, recent);
  assert.deepEqual(site.measurements.map(m => m.unit), ['cpm', 'cpm', 'usv', 'cpm']);
  t.mock.method(globalThis, 'fetch', async () => Response.json([rows[0], { ...rows[0], value: 0 }]));
  site = (await radiationBriefing()).sites[0];
  assert.equal(site.avgCPM, 15);
  assert.equal(site.anomaly, null, 'a measured mean is not a calibrated safety assessment');
  t.mock.method(globalThis, 'fetch', async () => Response.json([rows[3]]));
  site = (await radiationBriefing()).sites[0];
  assert.equal(site.recentReadings, 0);
  assert.equal(site.avgCPM, null);
  assert.equal(site.status, 'partial');
});

test('zero coordinates are valid query centers and legacy coordinates are not invented', async (t) => {
  let queried;
  t.mock.method(globalThis, 'fetch', async url => { queried = new URL(url); return Response.json([]); });
  await getMeasurements({ latitude: 0, longitude: 0 });
  assert.equal(queried.searchParams.get('latitude'), '0');
  assert.equal(queried.searchParams.get('per_page'), '50');
  await radiationBriefing();
  assert.equal(queried.searchParams.get('per_page'), '10');
  assert.equal(queried.searchParams.get('unit'), 'cpm');
  assert.ok(Date.parse(queried.searchParams.get('captured_before')) > Date.parse(queried.searchParams.get('captured_after')));
  const view = await synthesize({ sources: { OpenSky: { hotspots: [{ region: 'legacy', totalAircraft: 1 }] },
    Safecast: { sites: [{ site: 'legacy', avgCPM: 5, recentReadings: 1, anomaly: false }] } } }, { refreshNews: false });
  assert.equal(view.air[0].lat, null);
  assert.equal(view.nuke[0].lat, null);
  assert.equal(view.nuke[0].anom, null);
  assert.equal(view.nuke[0].cpm, null);
});

test('both map modes use validated reference points and no synthetic routes', () => {
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const helper = html.match(/function referenceMapItems\(items, basis\) \{[\s\S]*?\n\}/)?.[0];
  assert.ok(helper);
  const points = vm.runInNewContext(helper + ';referenceMapItems(rows,"query-bounds-center")', { rows: [
    { key: 'valid', geoBasis: 'query-bounds-center', lat: 0, lon: 0 },
    { key: 'legacy', lat: 1, lon: 2 },
    { key: 'bad', geoBasis: 'query-bounds-center', lat: 100, lon: 2 },
  ] });
  assert.deepEqual(Array.from(points, p => p.key), ['valid']);
  assert.equal((html.match(/referenceMapItems\(D.air,/g) || []).length, 2);
  assert.equal((html.match(/referenceMapItems\(D.nuke,/g) || []).length, 2);
  assert.doesNotMatch(html, /airCoords|nukeCoords|globalHubs|arcs.push|D.nuke.every\(s=>!s.anom\)/);
  assert.match(html, /globe.arcsData\(\[\]\)/);
});

test('missing radiation assessment never resolves an earlier anomaly', () => {
  const result = computeDelta({ nuke: [{ anom: null }], air: [{ total: null }] },
    { nuke: [{ anom: true }], air: [{ total: 200 }] });
  assert.ok(!result.signals.deescalated.some(s => s.key === 'nuke_anomaly'));
  assert.ok(!result.signals.unchanged.includes('air_total'));
});
