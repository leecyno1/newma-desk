// FRED — Federal Reserve Economic Data
// 840,000+ time series. Free API key required.
// Key indicators: yield curve, CPI, unemployment, money supply, GDP, fed funds rate

import { safeFetch, today, daysAgo } from '../utils/fetch.mjs';
import { fredSignalObservation } from '../utils/fred-signals.mjs';

const BASE = 'https://api.stlouisfed.org/fred';

// Key series IDs for macro intelligence
const KEY_SERIES = {
  // Yield curve & rates
  DFF: 'Fed Funds Rate',
  DGS2: '2-Year Treasury Yield',
  DGS10: '10-Year Treasury Yield',
  DGS30: '30-Year Treasury Yield',
  T10Y2Y: '10Y-2Y Spread (Yield Curve)',
  T10Y3M: '10Y-3M Spread',
  // Inflation
  CPIAUCSL: 'CPI All Items',
  CPILFESL: 'Core CPI (ex Food & Energy)',
  PCEPI: 'PCE Price Index',
  MICH: 'Michigan Inflation Expectations',
  // Labor
  UNRATE: 'Unemployment Rate',
  PAYEMS: 'Nonfarm Payrolls',
  ICSA: 'Initial Jobless Claims',
  // Money & credit
  M2SL: 'M2 Money Supply',
  WALCL: 'Fed Balance Sheet Total Assets',
  // Fear gauges
  VIXCLS: 'VIX (Fear Index)',
  BAMLH0A0HYM2: 'High Yield Spread (Credit Stress)',
  // Commodities via FRED
  DCOILWTICO: 'WTI Crude Oil',
  GOLDAMGBD228NLBM: 'Gold Price (London Fix)',
  // Housing
  MORTGAGE30US: '30-Year Mortgage Rate',
  // Global
  DTWEXBGS: 'USD Trade Weighted Index',
};

// Get latest value for a series
async function getSeriesLatest(seriesId, apiKey, startDate, endDate) {
  const params = new URLSearchParams({
    series_id: seriesId,
    api_key: apiKey,
    file_type: 'json',
    sort_order: 'desc',
    limit: '5',
    observation_start: startDate,
    observation_end: endDate,
  });
  return safeFetch(`${BASE}/series/observations?${params}`);
}

function seriesResult(id, label, data, startDate, endDate) {
  const base = { id, label, value: null, date: null, recent: [] };
  if (data?.error) {
    const httpStatus = Number.isInteger(data.status) && data.status >= 400 && data.status <= 599 ? data.status : null;
    return { ...base, status: 'error', errorCode: httpStatus ? 'HTTP_ERROR' : 'REQUEST_FAILED', ...(httpStatus ? { httpStatus } : {}) };
  }
  if (data?.error_code) return { ...base, status: 'error', errorCode: 'PROVIDER_ERROR' };
  if (!Array.isArray(data?.observations)) return { ...base, status: 'error', errorCode: 'INVALID_RESPONSE' };

  const dates = new Map();
  let rejected = false;
  for (const row of data.observations) {
    const date = row?.date;
    if (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(Date.parse(date))
      || new Date(date).toISOString().slice(0, 10) !== date || date < startDate || date > endDate) {
      rejected = true;
      continue;
    }
    const text = typeof row.value === 'string' ? row.value.trim() : '';
    const missing = text === '.';
    const value = typeof row.value === 'number' && Number.isFinite(row.value) ? row.value
      : /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?$/i.test(text) && Number.isFinite(Number(text)) ? Number(text) : null;
    if (!missing && value === null) rejected = true;
    const previous = dates.get(date);
    if (previous && (previous.value !== value || previous.missing !== missing)) {
      dates.set(date, { date, value: null, missing: false, conflict: true });
      rejected = true;
    } else if (!previous?.conflict) {
      dates.set(date, { date, value, missing });
    }
  }
  const rows = [...dates.values()].sort((a, b) => b.date.localeCompare(a.date));
  // A normal FRED holiday '.' may fall back. Malformed/conflicting latest values may not.
  const latest = rows.find(row => !row.missing);
  const recent = rows.filter(row => row.value !== null).slice(0, 5).map(row => row.value);
  if (!latest) return { ...base, date: rows[0]?.date || null, status: rejected ? 'error' : 'no_data',
    ...(rejected ? { errorCode: 'INVALID_OBSERVATIONS' } : {}) };
  return { ...base, value: latest.value, date: latest.date, recent,
    status: latest.value === null ? 'error' : rejected ? 'partial' : 'ok',
    ...(latest.value === null ? { errorCode: 'INVALID_OBSERVATIONS' } : {}) };
}

// Briefing — pull all key indicators
export async function briefing(apiKey) {
  if (!apiKey) {
    return {
      source: 'FRED',
      error: 'No FRED API key. Get one free at https://fred.stlouisfed.org/docs/api/api_key.html',
      hint: 'Set FRED_API_KEY environment variable',
    };
  }

  const entries = Object.entries(KEY_SERIES);
  const startDate = daysAgo(90), endDate = today();
  const results = await Promise.all(
    entries.map(async ([id, label]) => {
      const data = await getSeriesLatest(id, apiKey, startDate, endDate);
      return seriesResult(id, label, data, startDate, endDate);
    })
  );

  // Compute derived signals
  const signalClock = new Date(`${endDate}T00:00:00Z`);
  const get = (id) => fredSignalObservation(results.find(r => r.id === id), { now: signalClock })?.value ?? null;
  const yieldCurve10y2y = get('T10Y2Y');
  const yieldCurve10y3m = get('T10Y3M');
  const vix = get('VIXCLS');
  const hySpread = get('BAMLH0A0HYM2');

  const signals = [];
  if (yieldCurve10y2y !== null && yieldCurve10y2y < 0) signals.push('YIELD CURVE INVERTED (10Y-2Y) — recession signal');
  if (yieldCurve10y3m !== null && yieldCurve10y3m < 0) signals.push('YIELD CURVE INVERTED (10Y-3M) — stronger recession signal');
  if (vix !== null && vix > 30) signals.push(`VIX ELEVATED at ${vix} — high fear/volatility`);
  if (vix !== null && vix > 40) signals.push(`VIX EXTREME at ${vix} — crisis-level fear`);
  if (hySpread !== null && hySpread > 5) signals.push(`HIGH YIELD SPREAD WIDE at ${hySpread}% — credit stress`);

  const succeeded = results.filter(row => Number.isFinite(row.value)).length;
  const partial = results.filter(row => row.status === 'partial').length;
  const failed = results.filter(row => row.status === 'error').length;
  const empty = results.filter(row => row.status === 'no_data').length;
  return {
    source: 'FRED',
    timestamp: new Date().toISOString(),
    status: succeeded === entries.length && !partial ? 'ok' : succeeded ? 'partial' : failed ? 'error' : 'no_data',
    coverage: { requested: entries.length, succeeded, partial, failed, empty },
    indicators: results,
    signals,
  };
}

if (process.argv[1]?.endsWith('fred.mjs')) {
  const data = await briefing(process.env.FRED_API_KEY);
  console.log(JSON.stringify(data, null, 2));
}
