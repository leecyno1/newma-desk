// EIA — US Energy Information Administration
// Oil prices, natural gas, crude inventories. Falls back to public EIA/FRED tables.

import { safeFetch } from '../utils/fetch.mjs';
import { energyNumber, energyPeriod, fetchPublicSeries } from './eia-public.mjs';
import '../utils/env.mjs';

const BASE = 'https://api.eia.gov/v2';

// Series definitions with their v2 API paths
const OIL_SERIES = {
  wti: {
    label: 'WTI Crude Oil ($/bbl)',
    path: '/petroleum/pri/spt/data/',
    params: { frequency: 'daily', 'data[0]': 'value', facets: { series: ['RWTC'] } },
  },
  brent: {
    label: 'Brent Crude Oil ($/bbl)',
    path: '/petroleum/pri/spt/data/',
    params: { frequency: 'daily', 'data[0]': 'value', facets: { series: ['RBRTE'] } },
  },
};

const GAS_SERIES = {
  henryHub: {
    label: 'Henry Hub Natural Gas ($/MMBtu)',
    path: '/natural-gas/pri/fut/data/',
    params: { frequency: 'daily', 'data[0]': 'value', facets: { series: ['RNGWHHD'] } },
  },
};

const INVENTORY_SERIES = {
  crudeStocks: {
    label: 'US Crude Oil Inventories (thousand barrels)',
    path: '/petroleum/stoc/wstk/data/',
    params: { frequency: 'weekly', 'data[0]': 'value', facets: { series: ['WCESTUS1'] } },
  },
};

// Build the URL for a v2 API query
function buildUrl(apiKey, path, params, length = 10) {
  const url = new URL(`${BASE}${path}`);
  url.searchParams.set('api_key', apiKey);
  if (params.frequency) url.searchParams.set('frequency', params.frequency);
  if (params['data[0]']) url.searchParams.set('data[0]', params['data[0]']);
  url.searchParams.set('sort[0][column]', 'period');
  url.searchParams.set('sort[0][direction]', 'desc');
  url.searchParams.set('length', String(length));

  // Add facets
  if (params.facets) {
    for (const [facetKey, facetValues] of Object.entries(params.facets)) {
      facetValues.forEach((v, i) => {
        url.searchParams.set(`facets[${facetKey}][]`, v);
      });
    }
  }

  return url.toString();
}

// Fetch a single EIA series
export async function fetchSeries(apiKey, seriesDef, length = 10) {
  const url = buildUrl(apiKey, seriesDef.path, seriesDef.params, length);
  // Leave enough time for the public fallback within the orchestrator's 30s budget.
  return safeFetch(url, { timeout: 8000, retries: 0 });
}

async function loadSeries(apiKey, definition) {
  const seriesId = definition.params.facets.series[0];
  if (apiKey) {
    const response = await fetchSeries(apiKey, definition);
    const recent = (response?.response?.data || []).map(row => ({
      value: energyNumber(row.value), period: energyPeriod(row.period),
      unit: row['unit-name'] || row.unit || row.units || null,
    })).filter(row => row.value !== null && row.period).sort((a, b) => b.period.localeCompare(a.period)).slice(0, 5);
    if (recent.length) return { ...recent[0], recent };
  }
  // Do not copy provider error text: it can contain the API key or full request URL.
  const reason = apiKey ? 'EIA API 未返回有效观测，改用同口径公开数据。' : '未配置 EIA API Key，改用同口径公开数据。';
  try {
    return await fetchPublicSeries(seriesId, reason);
  } catch (error) {
    return { error: `${reason}备用来源暂不可用：${error.name === 'TimeoutError' ? '请求超时' : '请求失败或数据无效'}。` };
  }
}

// Briefing — oil prices, gas prices, inventories
export async function briefing(apiKey) {
  const results = await Promise.all([
    loadSeries(apiKey, OIL_SERIES.wti), loadSeries(apiKey, OIL_SERIES.brent),
    loadSeries(apiKey, GAS_SERIES.henryHub), loadSeries(apiKey, INVENTORY_SERIES.crudeStocks),
  ]);
  const ids = ['wti', 'brent', 'naturalGas', 'crudeStocks'];
  const gaps = Object.fromEntries(results.flatMap((row, i) => row.error ? [[ids[i], row.error]] : []));
  const [wti, brent, gas, inv] = results.map(row => row.error ? null : row);
  const spread = wti && brent && wti.period === brent.period ? +(brent.value - wti.value).toFixed(2) : null;

  const signals = [];

  // Oil prices
  if (wti && wti.value > 100) signals.push(`WTI crude above $100 at $${wti.value}/bbl`);
  if (wti && wti.value < 50) signals.push(`WTI crude below $50 at $${wti.value}/bbl — supply glut or demand destruction`);
  if (spread !== null && spread > 10) {
    signals.push(`Brent-WTI spread wide at $${spread.toFixed(2)} — supply/logistics divergence`);
  }

  // Gas prices
  if (gas && gas.value > 6) signals.push(`Natural gas elevated at $${gas.value}/MMBtu`);
  if (gas && gas.value > 9) signals.push(`Natural gas crisis-level at $${gas.value}/MMBtu`);

  // Inventories
  const invRecent = inv?.recent || [];

  // Check week-over-week inventory change
  if (invRecent.length >= 2 && Date.parse(invRecent[0].period) - Date.parse(invRecent[1].period) === 7 * 86400000) {
    const weekChange = invRecent[0].value - invRecent[1].value;
    if (Math.abs(weekChange) > 5000) {
      const direction = weekChange > 0 ? 'build' : 'draw';
      signals.push(`Large crude inventory ${direction}: ${weekChange > 0 ? '+' : ''}${(weekChange / 1000).toFixed(1)}M barrels`);
    }
  }

  return {
    source: 'EIA',
    timestamp: new Date().toISOString(),
    gaps,
    ...(Object.keys(gaps).length === 4 ? { error: '能源 API 与公开备用数据均不可用' } : {}),
    oilPrices: {
      wti: wti ? { ...wti, label: OIL_SERIES.wti.label } : null,
      brent: brent ? { ...brent, label: OIL_SERIES.brent.label } : null,
      spread,
    },
    gasPrice: gas ? { ...gas, label: GAS_SERIES.henryHub.label } : null,
    inventories: {
      crudeStocks: inv ? { ...inv, label: INVENTORY_SERIES.crudeStocks.label, recent: invRecent } : null,
    },
    signals,
  };
}

if (process.argv[1]?.endsWith('eia.mjs')) {
  const data = await briefing(process.env.EIA_API_KEY);
  console.log(JSON.stringify(data, null, 2));
}
