// ACLED — Armed Conflict Location & Event Data
// Auth strategy (tries in order):
//   1. Cookie-based session: POST /user/login?_format=json → session cookie
//   2. OAuth Bearer token:   POST /oauth/token → Authorization header
// Set ACLED_EMAIL and ACLED_PASSWORD in .env (your myACLED login credentials).
// Data endpoint: GET https://acleddata.com/api/acled/read

import { daysAgo } from '../utils/fetch.mjs';
import '../utils/env.mjs';

const LOGIN_URL = 'https://acleddata.com/user/login?_format=json';
const TOKEN_URL = 'https://acleddata.com/oauth/token';
const API_BASE  = 'https://acleddata.com/api/acled/read';

// Session cache
let sessionCache = { cookies: null, token: null, method: null, expires: 0 };

// Strategy 1: Cookie-based session login (mirrors browser login)
async function loginCookie(email, password) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(LOGIN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: email, pass: password }),
      redirect: 'manual',
      signal: controller.signal,
    });
    clearTimeout(timer);

    // Collect Set-Cookie headers
    const setCookies = res.headers.getSetCookie?.() || [];
    const cookieStr = setCookies.map(c => c.split(';')[0]).join('; ');

    if (res.ok && cookieStr) {
      return { cookies: cookieStr };
    }

    // Some Drupal sites return 303 redirect on successful login — cookies still set
    if (res.status >= 300 && res.status < 400 && cookieStr) {
      return { cookies: cookieStr };
    }

    const errText = await res.text().catch(() => '');
    return { error: `Cookie login failed (HTTP ${res.status}): ${errText.slice(0, 200)}` };
  } catch (e) {
    clearTimeout(timer);
    const cause = e.cause ? ` → ${e.cause.message || e.cause.code || e.cause}` : '';
    return { error: `Cookie login error: ${e.message}${cause}` };
  }
}

// Strategy 2: OAuth2 password grant
async function loginOAuth(email, password) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const body = new URLSearchParams({
      username: email,
      password: password,
      grant_type: 'password',
      client_id: 'acled',
    });

    const res = await fetch(TOKEN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      return { error: `OAuth failed (HTTP ${res.status}): ${errText.slice(0, 200)}` };
    }

    const data = await res.json();
    if (!data.access_token) {
      return { error: `OAuth response missing access_token: ${JSON.stringify(data).slice(0, 200)}` };
    }

    return { token: data.access_token };
  } catch (e) {
    clearTimeout(timer);
    const cause = e.cause ? ` → ${e.cause.message || e.cause.code || e.cause}` : '';
    return { error: `OAuth error: ${e.message}${cause}` };
  }
}

// Try both auth strategies
async function authenticate() {
  const email    = process.env.ACLED_EMAIL;
  const password = process.env.ACLED_PASSWORD;
  if (!email || !password) {
    return { error: 'No ACLED credentials. Set ACLED_EMAIL and ACLED_PASSWORD in .env.' };
  }

  // Return cached session if still valid
  if (sessionCache.method && Date.now() < sessionCache.expires) {
    return sessionCache;
  }

  const errors = [];
  const debug = process.argv.includes('--debug');

  // Try OAuth first (official programmatic method per ACLED docs)
  const oauthResult = await loginOAuth(email, password);
  if (oauthResult.token) {
    if (debug) console.error(`[ACLED DEBUG] OAuth OK — token: ${oauthResult.token.slice(0, 20)}...`);
    sessionCache = { cookies: null, token: oauthResult.token, method: 'oauth', expires: Date.now() + 23 * 60 * 60 * 1000 };
    return sessionCache;
  }
  errors.push(`OAuth: ${oauthResult.error}`);
  if (debug) console.error(`[ACLED DEBUG] OAuth failed: ${oauthResult.error}`);

  // Fall back to cookie-based session
  const cookieResult = await loginCookie(email, password);
  if (cookieResult.cookies) {
    if (debug) console.error(`[ACLED DEBUG] Cookie OK — cookies: ${cookieResult.cookies.slice(0, 80)}...`);
    sessionCache = { cookies: cookieResult.cookies, token: null, method: 'cookie', expires: Date.now() + 12 * 60 * 60 * 1000 };
    return sessionCache;
  }
  errors.push(`Cookie: ${cookieResult.error}`);

  return { error: `All ACLED auth methods failed.\n${errors.join('\n')}` };
}

// Build headers based on auth method
function authHeaders(session) {
  const headers = { 'User-Agent': 'Crucix/1.0', 'Content-Type': 'application/json' };
  if (session.method === 'cookie' && session.cookies) {
    headers['Cookie'] = session.cookies;
  } else if (session.method === 'oauth' && session.token) {
    headers['Authorization'] = `Bearer ${session.token}`;
  }
  return headers;
}

// Event type constants
export const EVENT_TYPES = [
  'Battles',
  'Explosions/Remote violence',
  'Violence against civilians',
  'Protests',
  'Riots',
  'Strategic developments',
];

// Query conflict events with flexible filters
export async function getEvents(opts = {}) {
  const {
    limit = 500,
    eventDateStart,
    eventDateEnd,
    eventType,
    country,
    region,
  } = opts;

  const session = await authenticate();
  if (session.error) return { error: session.error };

  const params = new URLSearchParams({ _format: 'json', limit: String(limit) });
  if (eventDateStart && eventDateEnd) {
    params.set('event_date', `${eventDateStart}|${eventDateEnd}`);
    params.set('event_date_where', 'BETWEEN');
  }
  if (eventType) params.set('event_type', eventType);
  if (country) params.set('country', country);
  if (region) params.set('region', String(region));

  const debug = process.argv.includes('--debug');
  try {
    const url = `${API_BASE}?${params}`;
    const hdrs = authHeaders(session);
    if (debug) {
      console.error(`[ACLED DEBUG] Data request: GET ${url}`);
      console.error(`[ACLED DEBUG] Headers: ${JSON.stringify(hdrs)}`);
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 25000);
    const res = await fetch(url, {
      headers: hdrs,
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (debug) console.error(`[ACLED DEBUG] Data response: HTTP ${res.status}`);

    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      if (debug) console.error(`[ACLED DEBUG] Error body: ${errText.slice(0, 500)}`);
      if (res.status === 401 || res.status === 403) {
        // Clear cache and report
        sessionCache = { cookies: null, token: null, method: null, expires: 0 };
        const hint = res.status === 403
          ? '\n→ Fix: Log in at https://acleddata.com/user/login, then:\n'
            + '  1. Accept Terms of Use (profile → Terms of Use button → check the box)\n'
            + '  2. Complete all required profile fields\n'
            + '  3. Ensure your account has the "API" access group\n'
            + '  Contact access@acleddata.com if issues persist.'
          : '';
        return { error: `ACLED data access denied (HTTP ${res.status}, auth method: ${session.method}). Response: ${errText.slice(0, 300)}${hint}` };
      }
      return { error: `HTTP ${res.status}: ${errText.slice(0, 200)}` };
    }

    const data = await res.json();

    // ACLED may return a 200 with an error status in the body
    if (data?.status && data.status !== 200) {
      return { error: `ACLED API error: status ${data.status} — ${data.message || 'Unknown error'}` };
    }

    return data;
  } catch (e) {
    if (e.name === 'AbortError') {
      return { error: 'ACLED data request timed out (25s)' };
    }
    const rootCause = e.cause ? `${e.cause.message || e.cause.code || e.cause}` : '';
    return { error: `ACLED data error: ${e.message}${rootCause ? ' → ' + rootCause : ''}` };
  }
}

// Summarize events by a given field
function groupBy(events, field) {
  const map = {};
  for (const e of events) {
    const key = e[field] || 'Unknown';
    if (!map[key]) map[key] = { count: 0, fatalities: 0 };
    map[key].count += 1;
    map[key].fatalities += parseInt(e.fatalities, 10) || 0;
  }
  return map;
}

// Briefing — last 7 days of global conflict events
export async function briefing() {
  if (!process.env.ACLED_EMAIL || !process.env.ACLED_PASSWORD) {
    return {
      source: 'ACLED',
      timestamp: new Date().toISOString(),
      status: 'no_credentials',
      message: 'Set ACLED_EMAIL and ACLED_PASSWORD in .env. Register at https://acleddata.com/user/register',
    };
  }

  const start = daysAgo(7);
  const end   = daysAgo(0);

  const data = await getEvents({
    eventDateStart: start,
    eventDateEnd: end,
    limit: 2000,
  });

  if (data?.error) {
    return { source: 'ACLED', timestamp: new Date().toISOString(), error: data.error };
  }

  let events = data?.data || [];

  // Enrich all events with numeric lat/lon
  events = events.map(e => ({
    ...e,
    lat: parseFloat(e.latitude) || null,
    lon: parseFloat(e.longitude) || null,
  }));

  const totalFatalities = events.reduce(
    (sum, e) => sum + (parseInt(e.fatalities, 10) || 0), 0
  );

  const byRegion  = groupBy(events, 'region');
  const byType    = groupBy(events, 'event_type');
  const byCountry = groupBy(events, 'country');

  const topCountries = Object.entries(byCountry)
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 10)
    .reduce((obj, [k, v]) => { obj[k] = v; return obj; }, {});

  const deadliestEvents = events
    .filter(e => parseInt(e.fatalities, 10) > 0)
    .sort((a, b) => (parseInt(b.fatalities, 10) || 0) - (parseInt(a.fatalities, 10) || 0))
    .slice(0, 15)
    .map(e => ({
      date:       e.event_date,
      type:       e.event_type,
      subType:    e.sub_event_type,
      country:    e.country,
      location:   e.location,
      fatalities: parseInt(e.fatalities, 10) || 0,
      lat:        parseFloat(e.latitude) || null,
      lon:        parseFloat(e.longitude) || null,
      notes:      e.notes?.slice(0, 200),
    }));

  return {
    source: 'ACLED',
    timestamp: new Date().toISOString(),
    period: { start, end },
    totalEvents: events.length,
    totalFatalities,
    byRegion,
    byType,
    topCountries,
    deadliestEvents,
  };
}

if (process.argv[1]?.endsWith('acled.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
