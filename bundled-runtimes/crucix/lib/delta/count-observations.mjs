// Comparable collection samples, never a census, incident delta or safety rating.
export const COUNT_METRICS = [
  { key: 'urgent_posts', field: 'tg', label: 'Shown urgent OSINT samples' },
  { key: 'thermal_total', field: 'thermal', label: 'Thermal query-region samples (overlapping)' },
  { key: 'air_total', field: 'air', label: 'Aircraft query-region samples (overlapping)' },
  { key: 'who_alerts', field: 'who', label: 'WHO reports in query window' },
  { key: 'conflict_events', field: 'acled', label: 'ACLED reported event samples' },
  { key: 'conflict_fatalities', field: 'acled', label: 'ACLED reported sample fatalities' },
  { key: 'sdr_online', field: 'sdr', label: 'Verified online SDR receivers' },
  { key: 'news_count', field: 'news', label: 'Shown RSS samples (capped)' },
  { key: 'sources_ok', field: 'health', label: 'Successful source checks (not market risk)' },
];

export const collectionSignal = signal => COUNT_METRICS.some(metric => metric.key === signal.key)
  || signal.key?.startsWith('tg_urgent') || signal.key === 'source_degradation';

const count = value => Number.isSafeInteger(value) && value >= 0;
const sum = (rows, field) => Array.isArray(rows) && rows.length && rows.every(row => count(row[field]))
  ? rows.reduce((total, row) => total + row[field], 0) : null;
const names = rows => rows.map(row => row.channel || row.url || row.n).sort();
const time = value => typeof value === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? Date.parse(value) : NaN;
const recent = (value, now) => Number.isFinite(time(value)) && time(value) <= now.getTime()
  && now.getTime() - time(value) <= 2 * 3600000;

export function countObservation(data, key, now = new Date()) {
  let value, asOf, scope, unit = 'records', period = null;
  if (key === 'urgent_posts') {
    const tg = data.tg;
    if (tg?.status !== 'ok' || !Array.isArray(tg.urgent) || !tg.scope) return null;
    value = tg.urgent.length; asOf = tg.collectedAt; scope = tg.scope;
  } else if (key === 'thermal_total') {
    const meta = data.thermalMeta;
    if (meta?.status !== 'ok' || !meta.scope) return null;
    value = sum(data.thermal, 'det'); asOf = meta.collectedAt; scope = meta.scope; unit = 'detections';
  } else if (key === 'air_total') {
    const meta = data.airMeta;
    if (meta?.fallback !== false || !meta.scope || !Array.isArray(data.air)
      || data.air.some(row => row.status !== 'ok' || !recent(row.observedAt, now))) return null;
    value = sum(data.air, 'total'); asOf = meta.timestamp; scope = meta.scope; unit = 'regional-aircraft-samples';
  } else if (key === 'who_alerts') {
    const meta = data.whoMeta;
    if (meta?.status !== 'ok' || !meta.window?.start || !meta.window?.end) return null;
    value = meta.count; asOf = meta.collectedAt; period = meta.window;
    scope = { source: 'WHO-DON', window: meta.window, limit: 100 };
  } else if (key === 'conflict_events' || key === 'conflict_fatalities') {
    const acled = data.acled;
    if (acled?.status !== 'ok' || acled.basis !== 'bounded-event-sample' || !acled.period?.start || !acled.period?.end
      || !count(acled.sampleLimit) || !acled.coverage || acled.coverage.truncated !== false) return null;
    value = key === 'conflict_events' ? acled.totalEvents : acled.totalFatalities;
    asOf = acled.collectedAt; period = acled.period;
    scope = { source: 'ACLED', period, limit: acled.sampleLimit }; unit = key === 'conflict_events' ? 'records' : 'reported-fatalities';
  } else if (key === 'sdr_online') {
    // Receiverbook is a directory; it does not probe live receiver connectivity.
    return null;
  } else if (key === 'news_count') {
    const meta = data.newsMeta;
    if (meta?.status !== 'ok' || meta.cachedSources !== 0 || !meta.items?.length
      || meta.items.some(row => row.status !== 'ok' || row.cached || !row.url || !recent(row.asOf, now))) return null;
    value = Array.isArray(data.news) ? data.news.length : data.news?.count;
    asOf = meta.asOf; scope = { source: 'RSS', feeds: names(meta.items), limit: meta.limit, selection: meta.selection || 'regional-reserve-30d-v1' };
  } else if (key === 'sources_ok') {
    const rows = data.health;
    if (!Array.isArray(rows) || !rows.length || rows.some(row => !row.n || !['ok', 'error', 'partial', 'stale', 'unknown'].includes(row.status))
      || rows.length !== data.meta?.sourcesQueried) return null;
    value = rows.filter(row => row.status === 'ok').length;
    if (value !== data.meta?.sourcesOk) return null;
    asOf = data.meta.timestamp; scope = { sources: names(rows) }; unit = 'source-checks';
  }
  // Two-hour local collection window; not a source publication guarantee.
  if (!count(value) || !recent(asOf, now)) return null;
  return { value, asOf, scope, unit, period, basis: 'collection-sample-v1' };
}

export function sameCountScope(a, b) {
  return a && b && a.basis === b.basis && a.unit === b.unit && JSON.stringify(a.scope) === JSON.stringify(b.scope);
}
