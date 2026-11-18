// Safecast — Global radiation monitoring (150M+ readings)
// No auth required. CC0 public domain. Citizen-science network.

import { safeFetch } from '../utils/fetch.mjs';

const BASE = 'https://api.safecast.org';

// Get recent measurements in an area
export async function getMeasurements(opts = {}) {
  const {
    latitude = null,
    longitude = null,
    distance = 100, // km
    limit = 50,
    since = null,
    capturedAfter = null,
    capturedBefore = null,
    unit = null,
  } = opts;

  // JSON pagination overrides Rails' limit scope. The live endpoint did not
  // honor order in verification; use an explicit observation window instead.
  const params = new URLSearchParams({ per_page: String(limit) });
  if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
    params.set('latitude', String(latitude));
    params.set('longitude', String(longitude));
    params.set('distance', String(distance * 1000)); // meters
  }
  if (since) params.set('since', since);
  if (capturedAfter) params.set('captured_after', capturedAfter);
  if (capturedBefore) params.set('captured_before', capturedBefore);
  if (unit) params.set('unit', unit);

  return safeFetch(`${BASE}/measurements.json?${params}`);
}

// Key nuclear sites to monitor
const NUCLEAR_SITES = {
  zaporizhzhia: { lat: 47.51, lon: 34.58, label: 'Zaporizhzhia NPP (Ukraine)', radius: 100 },
  chernobyl: { lat: 51.39, lon: 30.1, label: 'Chernobyl Exclusion Zone', radius: 50 },
  bushehr: { lat: 28.83, lon: 50.89, label: 'Bushehr NPP (Iran)', radius: 100 },
  yongbyon: { lat: 39.8, lon: 125.75, label: 'Yongbyon (North Korea)', radius: 100 },
  fukushima: { lat: 37.42, lon: 141.03, label: 'Fukushima Daiichi', radius: 50 },
  dimona: { lat: 31.0, lon: 35.15, label: 'Dimona (Israel)', radius: 100 },
};

// Briefing — check radiation levels near key nuclear sites
export async function briefing() {
  const now = Date.now();
  const windowStart = new Date(now - 24 * 3600 * 1000).toISOString();
  const windowEnd = new Date(now).toISOString();
  const results = await Promise.all(
    Object.entries(NUCLEAR_SITES).map(async ([key, site]) => {
      const data = await getMeasurements({
        latitude: site.lat,
        longitude: site.lon,
        distance: site.radius,
        limit: 10,
        capturedAfter: windowStart, capturedBefore: windowEnd, unit: 'cpm',
      });

      const valid = Array.isArray(data);
      const measurements = (valid ? data : []).filter(m => m && Number.isFinite(m.value) && m.value >= 0
        && ['cpm', 'usv', 'nsv'].includes(String(m.unit).toLowerCase())
        && Number.isFinite(Date.parse(m.captured_at)) && Date.parse(m.captured_at) <= now);
      const recent = measurements.filter(m => now - Date.parse(m.captured_at) <= 24 * 3600 * 1000);
      const cpm = recent.filter(m => m.unit.toLowerCase() === 'cpm');
      const devices = new Set(cpm.map(m => m.device_id));
      // Safecast device_id describes a manufacturer/model/sensor type, not a
      // physical station or proof of identical calibration.
      const comparable = cpm.length > 0 && devices.size === 1 && cpm[0].device_id != null;
      const values = comparable ? cpm.map(m => m.value) : [];
      const status = !valid ? 'error' : measurements.length < data.length || recent.length < measurements.length
        || recent.some(m => m.unit.toLowerCase() !== 'cpm') ? 'partial' : 'ok';

      return {
        site: site.label,
        key,
        latitude: site.lat, longitude: site.lon, radiusKm: site.radius, geoBasis: 'query-radius-center',
        windowStart, windowEnd, sampleLimit: 10,
        status, reason: !valid ? 'Safecast request failed or returned an invalid response'
          : !data.length ? 'Valid empty sample; radiation safety unknown'
            : status === 'partial' ? 'Historical or invalid readings; current radiation safety unknown'
              : 'Sample only; no calibrated site safety assessment',
        sampleReadings: valid ? measurements.length : null,
        recentReadings: valid ? recent.length : null,
        avgCPM: values.length ? values.reduce((a, b) => a + b, 0) / values.length : null,
        maxCPM: values.length > 0 ? Math.max(...values) : null,
        deviceId: comparable ? cpm[0].device_id : null,
        anomaly: null,
        lastReading: measurements.map(m => new Date(m.captured_at).toISOString()).sort().at(-1) || null,
        measurements: measurements.slice(0, 10).map(m => ({ value: m.value, unit: m.unit,
          deviceId: m.device_id ?? null, observedAt: new Date(m.captured_at).toISOString() })),
      };
    })
  );

  return {
    source: 'Safecast',
    timestamp: new Date().toISOString(),
    sites: results,
    status: results.every(r => r.status === 'ok') ? 'ok' : results.every(r => r.status === 'error') ? 'error' : 'partial',
    signals: ['Radiation safety unassessed: sampled readings are not calibrated site-wide safety measurements'],
  };
}

if (process.argv[1]?.endsWith('safecast.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
