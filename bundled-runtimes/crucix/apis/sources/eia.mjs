// EIA — US Energy Information Administration
// Oil prices, natural gas, crude inventories. Free API key required.
// Gracefully degrades without key.

import { safeFetch } from '../utils/fetch.mjs';
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
  return safeFetch(url);
}

// Extract latest value from EIA response
function extractLatest(resp) {
  const data = resp?.response?.data;
  if (!data?.length) return null;
  return {
    value: parseFloat(data[0].value),
    period: data[0].period,
    unit: data[0]['unit-name'] || data[0].unit || null,
  };
}

// Extract recent values for trend analysis
function extractRecent(resp, count = 5) {
  const data = resp?.response?.data;
  if (!data?.length) return [];
  return data.slice(0, count).map(d => ({
    value: parseFloat(d.value),
    period: d.period,
  }));
}

// Briefing — oil prices, gas prices, inventories
export async function briefing(apiKey) {
  if (!apiKey) {
    return {
      source: 'EIA',
      error: 'No EIA API key. Register free at https://www.eia.gov/opendata/register.php',
      hint: 'Set EIA_API_KEY environment variable',
      timestamp: new Date().toISOString(),
    };
  }

  const [wtiResp, brentResp, gasResp, inventoryResp] = await Promise.all([
    fetchSeries(apiKey, OIL_SERIES.wti),
    fetchSeries(apiKey, OIL_SERIES.brent),
    fetchSeries(apiKey, GAS_SERIES.henryHub),
    fetchSeries(apiKey, INVENTORY_SERIES.crudeStocks),
  ]);

  const signals = [];

  // Oil prices
  const wti = extractLatest(wtiResp);
  const brent = extractLatest(brentResp);
  const wtiRecent = extractRecent(wtiResp, 5);
  const brentRecent = extractRecent(brentResp, 5);

  if (wti && wti.value > 100) signals.push(`WTI crude above $100 at $${wti.value}/bbl`);
  if (wti && wti.value < 50) signals.push(`WTI crude below $50 at $${wti.value}/bbl — supply glut or demand destruction`);
  if (brent && wti && (brent.value - wti.value) > 10) {
    signals.push(`Brent-WTI spread wide at $${(brent.value - wti.value).toFixed(2)} — supply/logistics divergence`);
  }

  // Gas prices
  const gas = extractLatest(gasResp);
  if (gas && gas.value > 6) signals.push(`Natural gas elevated at $${gas.value}/MMBtu`);
  if (gas && gas.value > 9) signals.push(`Natural gas crisis-level at $${gas.value}/MMBtu`);

  // Inventories
  const inv = extractLatest(inventoryResp);
  const invRecent = extractRecent(inventoryResp, 5);

  // Check week-over-week inventory change
  if (invRecent.length >= 2) {
    const weekChange = invRecent[0].value - invRecent[1].value;
    if (Math.abs(weekChange) > 5000) {
      const direction = weekChange > 0 ? 'build' : 'draw';
      signals.push(`Large crude inventory ${direction}: ${weekChange > 0 ? '+' : ''}${(weekChange / 1000).toFixed(1)}M barrels`);
    }
  }

  return {
    source: 'EIA',
    timestamp: new Date().toISOString(),
    oilPrices: {
      wti: wti ? { ...wti, label: OIL_SERIES.wti.label, recent: wtiRecent } : null,
      brent: brent ? { ...brent, label: OIL_SERIES.brent.label, recent: brentRecent } : null,
      spread: wti && brent ? +(brent.value - wti.value).toFixed(2) : null,
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
