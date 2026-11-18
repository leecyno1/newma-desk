import { sourceFetch as fetch } from '../utils/source-request.mjs';

// BLS — Bureau of Labor Statistics
// CPI, unemployment, nonfarm payrolls, PPI. No auth required (v1 API).
// v2 with registration key supports more requests; availability is checked per response.

import { safeFetch } from '../utils/fetch.mjs';

const V1_BASE = 'https://api.bls.gov/publicAPI/v1/timeseries/data/';
const V2_BASE = 'https://api.bls.gov/publicAPI/v2/timeseries/data/';

// Key economic series
const SERIES = {
  'CUUR0000SA0':    'CPI-U All Items',
  'CUUR0000SA0L1E': 'CPI-U Core (ex Food & Energy)',
  'LNS14000000':    'Unemployment Rate',
  'CES0000000001':  'Nonfarm Payrolls (thousands)',
  'WPUFD49104':     'PPI WPUFD49104 (category unverified)',
};

const SERIES_BASIS = {
  CUUR0000SA0: { unit: 'index', changeUnit: 'index-points', seasonalAdjustment: 'not-seasonally-adjusted' },
  CUUR0000SA0L1E: { unit: 'index', changeUnit: 'index-points', seasonalAdjustment: 'not-seasonally-adjusted' },
  LNS14000000: { unit: 'percent', changeUnit: 'percentage-points', seasonalAdjustment: 'seasonally-adjusted' },
  CES0000000001: { unit: 'thousands-of-persons', changeUnit: 'thousands-of-persons', seasonalAdjustment: 'seasonally-adjusted' },
  WPUFD49104: { unit: 'index', changeUnit: 'index-points', seasonalAdjustment: 'not-seasonally-adjusted' },
};

// Fetch a single series via GET (v1, no key needed)
export async function getSeriesV1(seriesId) {
  return safeFetch(`${V1_BASE}${encodeURIComponent(seriesId)}`);
}

// Fetch one or more series via POST (v2 if key available, v1 otherwise)
export async function getSeries(seriesIds, opts = {}) {
  const { startYear, endYear, apiKey } = opts;
  const now = new Date();
  const start = startYear || String(now.getFullYear() - 1);
  const end = endYear || String(now.getFullYear());

  const base = apiKey ? V2_BASE : V1_BASE;
  const payload = {
    seriesid: Array.isArray(seriesIds) ? seriesIds : [seriesIds],
    startyear: start,
    endyear: end,
  };
  if (apiKey) payload.registrationkey = apiKey;

  try {
    const signal = AbortSignal.timeout(15000);
    const res = await fetch(base, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    });
    if (!res.ok) {
      await res.body?.cancel().catch(() => {});
      return { error: `BLS 请求失败（HTTP ${res.status}）`, errorCode: 'HTTP_ERROR', httpStatus: res.status };
    }
    try {
      const data = await res.json();
      return data?.error ? { error: 'BLS 返回来源错误', errorCode: 'PROVIDER_ERROR' } : data;
    }
    catch { return { error: 'BLS 未返回有效 JSON', errorCode: 'INVALID_RESPONSE' }; }
  } catch (e) {
    return { error: 'BLS 请求失败或超时', errorCode: 'REQUEST_FAILED' };
  }
}

// All configured series are monthly. M13 is an annual average, not December.
function monthlyObservations(seriesData) {
  if (!Array.isArray(seriesData?.data)) return [];
  return seriesData.data.filter(d => d && /^\d{4}$/.test(d.year) && /^M(0[1-9]|1[0-2])$/.test(d.period))
    .map(d => ({
      ordinal: Number(d.year) * 12 + Number(d.period.slice(1)) - 1,
      period: `${d.year}-${d.period}`,
      date: `${d.year}-${d.period.slice(1)}`,
      // Preserve a missing newest month; do not silently use an older valid value.
      value: /^[-+]?\d+(?:\.\d+)?$/.test(String(d.value)) && Number.isFinite(Number(d.value)) ? Number(d.value) : null,
    }))
    .sort((a, b) => b.ordinal - a.ordinal);
}

function periodChange(observations, months) {
  const latest = observations[0];
  const previous = observations.find(d => d.ordinal === latest?.ordinal - months);
  if (!Number.isFinite(latest?.value) || !Number.isFinite(previous?.value)) return null;
  const change = latest.value - previous.value;
  return {
    change: +change.toFixed(4),
    changePct: previous.value !== 0 ? +((change / previous.value) * 100).toFixed(4) : null,
    previousPeriod: previous.date,
  };
}

// Briefing — pull latest CPI, unemployment, payrolls
export async function briefing(apiKey) {
  const seriesIds = Object.keys(SERIES);
  const resp = await getSeries(seriesIds, { apiKey });

  if (resp?.error) {
    return { source: 'BLS', error: resp.errorCode ? resp.error : 'BLS 返回来源错误',
      errorCode: resp.errorCode || 'PROVIDER_ERROR',
      ...(Number.isInteger(resp.httpStatus) ? { httpStatus: resp.httpStatus } : {}), timestamp: new Date().toISOString() };
  }

  if (resp?.status !== 'REQUEST_SUCCEEDED' || !Array.isArray(resp.Results?.series)) {
    return {
      source: 'BLS',
      error: 'BLS 返回来源错误或无效序列结构',
      errorCode: 'PROVIDER_ERROR',
      timestamp: new Date().toISOString(),
    };
  }

  const indicators = [];
  const signals = [];

  for (const id of seriesIds) {
    const observations = monthlyObservations(resp.Results.series.find(s => s?.seriesID === id));
    const latest = observations[0];
    const value = latest?.value ?? null;
    const mom = periodChange(observations, 1);
    const yoy = periodChange(observations, 12);

    indicators.push({
      id,
      label: SERIES[id],
      ...SERIES_BASIS[id],
      frequency: 'monthly',
      value,
      period: latest?.period ?? null,
      date: latest?.date ?? null,
      momChange: mom ? mom.change : null,
      momChangePct: mom ? mom.changePct : null,
      momPreviousPeriod: mom?.previousPeriod ?? null,
      yoyChangePct: yoy?.changePct ?? null,
      yoyPreviousPeriod: yoy?.previousPeriod ?? null,
    });

    // Dated observations, not policy/trading conclusions. NSA CPI monthly moves
    // are not interchangeable with the seasonally-adjusted headline release.
    if (id === 'LNS14000000' && value > 5.0) {
      signals.push(`Unemployment ${value}% (${latest.date}, seasonally adjusted)`);
    }
    if (id.startsWith('CUUR') && Number.isFinite(yoy?.changePct)) {
      signals.push(`${SERIES[id]} YoY ${yoy.changePct}% (${latest.date}, not seasonally adjusted)`);
    }
    if (id === 'CES0000000001' && mom && mom.change < -50) {
      signals.push(`Nonfarm payrolls dropped by ${Math.abs(mom.change)}K (${latest.date}, seasonally adjusted)`);
    }
  }

  return {
    source: 'BLS',
    timestamp: new Date().toISOString(),
    coverage: { requested: seriesIds.length, succeeded: indicators.filter(d => d.value !== null).length,
      failed: indicators.filter(d => d.value === null).length },
    indicators,
    signals,
  };
}

if (process.argv[1]?.endsWith('bls.mjs')) {
  const data = await briefing(process.env.BLS_API_KEY);
  console.log(JSON.stringify(data, null, 2));
}
