// NOAA / National Weather Service — Severe weather alerts & climate events
// No auth required. Real-time alerts.

import { safeFetch } from '../utils/fetch.mjs';

const NWS_BASE = 'https://api.weather.gov';

// Get all active weather alerts (US)
export async function getActiveAlerts(opts = {}) {
  const {
    severity = null,  // Extreme, Severe, Moderate, Minor
    urgency = null,   // Immediate, Expected, Future
    event = null,     // e.g. "Tornado Warning", "Hurricane Warning"
  } = opts;

  // /alerts/active is an unpaginated collection; `limit` causes HTTP 400.
  const params = new URLSearchParams({ status: 'actual' });
  if (severity) params.set('severity', severity);
  if (urgency) params.set('urgency', urgency);
  if (event) params.set('event', event);

  return safeFetch(`${NWS_BASE}/alerts/active?${params}`, {
    headers: { 'Accept': 'application/geo+json' },
  });
}

// Get severe alerts only
export async function getSevereAlerts() {
  return getActiveAlerts({ severity: 'Extreme,Severe' });
}

function alertLocation(geometry) {
  let coordinates;
  if (geometry?.type === 'Point') coordinates = [geometry.coordinates];
  else if (geometry?.type === 'Polygon') coordinates = geometry.coordinates?.[0];
  else if (geometry?.type === 'MultiPolygon') coordinates = geometry.coordinates?.flatMap(p => p?.[0] || []);
  if (!Array.isArray(coordinates) || !coordinates.length || coordinates.some(c => !Array.isArray(c)
    || !Number.isFinite(c[0]) || !Number.isFinite(c[1]) || Math.abs(c[0]) > 180 || Math.abs(c[1]) > 90)) {
    return { lat: null, lon: null, geoBasis: null };
  }
  const lons = coordinates.map(c => c[0]), lats = coordinates.map(c => c[1]);
  if (Math.max(...lons) - Math.min(...lons) > 180) return { lat: null, lon: null, geoBasis: null };
  return { lat: (Math.min(...lats) + Math.max(...lats)) / 2,
    lon: (Math.min(...lons) + Math.max(...lons)) / 2,
    geoBasis: geometry.type === 'Point' ? 'source-point' : 'alert-area-bounds-center' };
}

// Briefing — severe weather events that could impact markets/supply chains
export async function briefing() {
  const alerts = await getSevereAlerts();
  if (alerts?.error || !Array.isArray(alerts?.features)) {
    const httpStatus = Number.isInteger(alerts?.status) && alerts.status >= 400 && alerts.status <= 599 ? alerts.status : null;
    return { source: 'NOAA/NWS', timestamp: new Date().toISOString(), status: 'error',
      totalSevereAlerts: null, topAlerts: [],
      errorCode: httpStatus ? 'HTTP_ERROR' : alerts?.error ? 'REQUEST_FAILED' : 'INVALID_RESPONSE', httpStatus,
      error: httpStatus ? `Weather alerts unavailable (HTTP ${httpStatus})` : 'Weather alerts unavailable' };
  }
  const features = alerts.features.filter(f => typeof f?.properties?.event === 'string'
    && f.properties.event.trim() && ['Extreme', 'Severe'].includes(f.properties.severity));
  const displayLimit = 50;

  // Categorize by impact type
  const hurricanes = features.filter(f => /hurricane|typhoon|tropical/i.test(f.properties?.event));
  const tornadoes = features.filter(f => /tornado/i.test(f.properties?.event));
  const floods = features.filter(f => /flood/i.test(f.properties?.event));
  const winter = features.filter(f => /blizzard|ice storm|winter/i.test(f.properties?.event));
  const fire = features.filter(f => /fire/i.test(f.properties?.event));
  const other = features.filter(f => {
    const e = f.properties?.event || '';
    return !/hurricane|typhoon|tropical|tornado|flood|blizzard|ice storm|winter|fire/i.test(e);
  });

  return {
    source: 'NOAA/NWS',
    timestamp: new Date().toISOString(),
    updatedAt: alerts.updated || null,
    status: features.length < alerts.features.length || alerts.pagination?.next ? 'partial' : 'ok',
    totalSevereAlerts: features.length,
    coverage: { region: 'US/NWS', severity: ['Extreme', 'Severe'], returned: alerts.features.length,
      valid: features.length, invalid: alerts.features.length - features.length,
      displayed: Math.min(features.length, displayLimit), displayLimit,
      complete: features.length === alerts.features.length && !alerts.pagination?.next },
    summary: {
      hurricanes: hurricanes.length,
      tornadoes: tornadoes.length,
      floods: floods.length,
      winterStorms: winter.length,
      wildfires: fire.length,
      other: other.length,
    },
    topAlerts: features.slice(0, displayLimit).map(f => {
      return {
        id: f.properties.id || f.id || null,
        url: f.id || null,
        event: f.properties?.event,
        severity: f.properties?.severity,
        urgency: f.properties?.urgency,
        headline: f.properties?.headline,
        areas: f.properties?.areaDesc,
        sent: f.properties?.sent || null,
        effective: f.properties?.effective || null,
        onset: f.properties?.onset,
        expires: f.properties?.expires,
        ...alertLocation(f.geometry),
      };
    }),
  };
}

if (process.argv[1]?.endsWith('noaa.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
