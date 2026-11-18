// ACLED: official OAuth API, bounded event samples (not a complete global conflict census).
import { sourceFetch as fetch, sourceSignal } from '../utils/source-request.mjs';
import { daysAgo } from '../utils/fetch.mjs';
import '../utils/env.mjs';

const TOKEN_URL = 'https://acleddata.com/oauth/token';
const API_BASE = 'https://acleddata.com/api/acled/read';
let sessionCache = null;

function failure(errorCode, httpStatus = null) {
  return { errorCode, httpStatus, error: httpStatus ? `ACLED 请求失败（HTTP ${httpStatus}）` : 'ACLED 请求不可用或响应格式无效' };
}

async function authenticate() {
  const email = process.env.ACLED_EMAIL, password = process.env.ACLED_PASSWORD;
  if (!email?.trim() || !password) { sessionCache = null; return failure('MISSING_CREDENTIALS'); }
  if (sessionCache?.email === email && sessionCache.password === password && Date.now() < sessionCache.expires) return sessionCache;
  sessionCache = null;
  try {
    const response = await fetch(TOKEN_URL, {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(15000),
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: email, password, grant_type: 'password', client_id: 'acled', scope: 'authenticated' }).toString(),
    });
    if (!response.ok) { await response.body?.cancel(); return failure('AUTH_FAILED', response.status); }
    const data = await response.json();
    if (typeof data?.access_token !== 'string' || !data.access_token.trim()
      || (data.token_type && data.token_type.toLowerCase() !== 'bearer')) return failure('INVALID_AUTH_RESPONSE');
    // Missing expiry permits this request only; never invent a 23-hour lifetime.
    const seconds = Number.isFinite(data.expires_in) ? Math.max(0, data.expires_in - 60) : 0;
    sessionCache = { token: data.access_token, email, password, expires: Date.now() + seconds * 1000 };
    return sessionCache;
  } catch (error) {
    sourceSignal()?.throwIfAborted();
    return failure(error instanceof SyntaxError ? 'INVALID_AUTH_RESPONSE' : 'AUTH_FAILED');
  }
}

export const EVENT_TYPES = ['Battles', 'Explosions/Remote violence', 'Violence against civilians', 'Protests', 'Riots', 'Strategic developments'];

export async function getEvents(opts = {}) {
  const { limit = 500, eventDateStart, eventDateEnd, eventType, country, region } = opts;
  const session = await authenticate();
  if (session.error) return session;
  const params = new URLSearchParams({ _format: 'json', limit: String(limit) });
  if (eventDateStart && eventDateEnd) {
    params.set('event_date', `${eventDateStart}|${eventDateEnd}`);
    params.set('event_date_where', 'BETWEEN');
  }
  if (eventType) params.set('event_type', eventType);
  if (country) params.set('country', country);
  if (region) params.set('region', String(region));
  try {
    const response = await fetch(`${API_BASE}?${params}`, {
      redirect: 'error', signal: AbortSignal.timeout(25000),
      headers: { 'User-Agent': 'Crucix/1.0', Authorization: `Bearer ${session.token}` },
    });
    if (!response.ok) {
      if ([401, 403].includes(response.status)) sessionCache = null;
      await response.body?.cancel();
      return failure('HTTP_ERROR', response.status);
    }
    const data = await response.json();
    if (data?.error || (data?.status !== undefined && Number(data.status) !== 200)) return failure('PROVIDER_ERROR');
    return Array.isArray(data?.data) ? data : failure('INVALID_RESPONSE');
  } catch (error) {
    sourceSignal()?.throwIfAborted();
    return failure(error instanceof SyntaxError ? 'INVALID_RESPONSE' : 'REQUEST_FAILED');
  }
}

const number = value => (typeof value === 'number' || typeof value === 'string') && String(value).trim() !== ''
  && Number.isFinite(Number(value)) ? Number(value) : null;
const deaths = value => { const n = number(value); return n !== null && Number.isInteger(n) && n >= 0 ? n : null; };
const coordinate = (value, max) => { const n = number(value); return n !== null && Math.abs(n) <= max ? n : null; };
function date(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value ? value : null;
}
function groupBy(events, field) {
  const groups = Object.create(null);
  for (const event of events) {
    const key = typeof event[field] === 'string' && event[field] ? event[field] : 'Unknown';
    const group = groups[key] ||= { count: 0, fatalities: 0, unknownFatalities: 0 };
    group.count++;
    if (event.fatalities === null) { group.unknownFatalities++; group.fatalities = null; }
    else if (group.fatalities !== null) group.fatalities += event.fatalities;
  }
  return groups;
}

export function summarizeEvents(data, period, limit = 2000) {
  const base = { source: 'ACLED', timestamp: new Date().toISOString(), period, sampleLimit: limit,
    basis: 'bounded-event-sample', note: '指定窗口内已报告事件样本；可能修订或覆盖不全，不能据此判断地区安全。' };
  if (data?.error || !Array.isArray(data?.data)) return { ...base,
    status: data?.errorCode === 'MISSING_CREDENTIALS' ? 'no_credentials' : 'error',
    errorCode: data?.errorCode || 'INVALID_RESPONSE', httpStatus: data?.httpStatus ?? null,
    totalEvents: null, totalFatalities: null, byRegion: {}, byType: {}, topCountries: {}, deadliestEvents: [],
    coverage: { returned: null, accepted: null, invalid: null, duplicates: null, unknownFatalities: null, truncated: false } };
  const unique = new Map();
  let invalid = 0, duplicates = 0;
  for (const row of data.data) {
    const observed = date(row?.event_date);
    if (!row || typeof row.event_id_cnty !== 'string' || !row.event_id_cnty || !observed
      || observed < period.start || observed > period.end) { invalid++; continue; }
    if (unique.has(row.event_id_cnty)) { duplicates++; continue; }
    unique.set(row.event_id_cnty, { ...row, event_date: observed, fatalities: deaths(row.fatalities),
      lat: coordinate(row.latitude, 90), lon: coordinate(row.longitude, 180) });
  }
  const events = [...unique.values()];
  const unknownFatalities = events.filter(e => e.fatalities === null).length;
  const truncated = data.data.length >= limit;
  const partial = invalid > 0 || duplicates > 0 || unknownFatalities > 0 || truncated;
  const valid = events.length > 0 || data.data.length === 0;
  return { ...base, status: !valid ? 'error' : partial ? 'partial' : 'ok',
    coverage: { returned: data.data.length, accepted: events.length, invalid, duplicates, unknownFatalities, truncated },
    totalEvents: valid ? events.length : null,
    totalFatalities: valid && !unknownFatalities ? events.reduce((sum, e) => sum + e.fatalities, 0) : null,
    byRegion: groupBy(events, 'region'), byType: groupBy(events, 'event_type'),
    topCountries: Object.fromEntries(Object.entries(groupBy(events, 'country')).sort((a, b) => b[1].count - a[1].count).slice(0, 10)),
    deadliestEvents: events.filter(e => e.fatalities > 0).sort((a, b) => b.fatalities - a.fatalities).slice(0, 15).map(e => ({
      id: e.event_id_cnty, date: e.event_date, type: e.event_type, subType: e.sub_event_type, country: e.country,
      location: e.location, fatalities: e.fatalities, lat: e.lat, lon: e.lon,
      notes: typeof e.notes === 'string' ? e.notes.slice(0, 200) : '',
    })),
  };
}

export async function briefing() {
  // Inclusive bounds: today plus the six preceding dates.
  const period = { start: daysAgo(6), end: daysAgo(0) };
  const data = await getEvents({ eventDateStart: period.start, eventDateEnd: period.end, limit: 2000 });
  return summarizeEvents(data, period);
}

if (process.argv[1]?.endsWith('acled.mjs')) console.log(JSON.stringify(await briefing(), null, 2));
