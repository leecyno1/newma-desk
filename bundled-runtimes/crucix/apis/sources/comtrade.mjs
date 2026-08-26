// UN Comtrade — Global Trade Data
// Public preview endpoint requires no key. Full API needs free registration.
// Tracks commodity trade flows between nations: crude oil, gas, gold, semiconductors, arms.
// Reporter codes: 842 (US), 156 (China), 276 (Germany), 392 (Japan), 826 (UK), 643 (Russia), 356 (India)

import { safeFetch, daysAgo, today } from '../utils/fetch.mjs';

const BASE = 'https://comtradeapi.un.org/public/v1';

// Strategic commodity codes (HS classification)
const STRATEGIC_COMMODITIES = {
  '2709': 'Crude Petroleum',
  '2711': 'Natural Gas (LNG & Pipeline)',
  '7108': 'Gold (unwrought/semi-manufactured)',
  '8542': 'Semiconductors (Electronic Integrated Circuits)',
  '93':   'Arms & Ammunition',
  '2844': 'Radioactive Elements (Nuclear)',
  '8471': 'Computers & Processing Units',
  '2701': 'Coal',
  '7601': 'Aluminium (unwrought)',
  '2612': 'Uranium & Thorium Ores',
};

// Key reporter/partner country codes
const COUNTRIES = {
  842: 'United States',
  156: 'China',
  276: 'Germany',
  392: 'Japan',
  826: 'United Kingdom',
  643: 'Russia',
  356: 'India',
  410: 'South Korea',
  158: 'Taiwan',
  380: 'Italy',
};

// Get trade data for a specific reporter, commodity, and period
export async function getTradeData(opts = {}) {
  const {
    reporterCode = 842,        // default: US
    period = new Date().getFullYear(),
    cmdCode = '2709',          // default: crude oil
    flowCode = 'M',            // M = imports, X = exports
    partnerCode = null,        // null = all partners
  } = opts;

  const params = new URLSearchParams({
    reporterCode: String(reporterCode),
    period: String(period),
    cmdCode,
    flowCode,
  });
  if (partnerCode) params.set('partnerCode', String(partnerCode));

  return safeFetch(`${BASE}/preview/C/A/HS?${params}`, { timeout: 20000 });
}

// Get bilateral trade between two countries for a commodity
export async function getBilateralTrade(reporter, partner, cmdCode, period) {
  return getTradeData({
    reporterCode: reporter,
    partnerCode: partner,
    cmdCode,
    period: period || new Date().getFullYear(),
  });
}

// Check multiple commodities for a given reporter
async function checkReporterCommodities(reporterCode, commodityCodes, period) {
  const results = [];
  for (const cmdCode of commodityCodes) {
    const data = await getTradeData({
      reporterCode,
      cmdCode,
      period,
      flowCode: 'M', // imports
    });
    results.push({
      commodity: STRATEGIC_COMMODITIES[cmdCode] || cmdCode,
      cmdCode,
      data,
    });
  }
  return results;
}

// Compact a trade record for briefing output
function compactRecord(rec) {
  return {
    reporter: rec.reporterDesc || rec.reporterCode,
    partner: rec.partnerDesc || rec.partnerCode,
    commodity: rec.cmdDesc || rec.cmdCode,
    flow: rec.flowDesc || rec.flowCode,
    value: rec.primaryValue || rec.cifvalue || rec.fobvalue || null,
    quantity: rec.qty || rec.netWgt || null,
    unit: rec.qtyUnitAbbr || rec.qtyUnitDesc || null,
    period: rec.period,
  };
}

// Detect anomalies in trade data (unusually large flows, new partners, etc.)
function detectAnomalies(tradeRecords) {
  const signals = [];
  if (!Array.isArray(tradeRecords) || tradeRecords.length === 0) return signals;

  const values = tradeRecords
    .map(r => r.value)
    .filter(v => typeof v === 'number' && v > 0);

  if (values.length > 2) {
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    const stdDev = Math.sqrt(values.reduce((a, v) => a + (v - avg) ** 2, 0) / values.length);

    tradeRecords.forEach(r => {
      if (typeof r.value === 'number' && r.value > avg + 2 * stdDev) {
        signals.push(
          `OUTLIER: ${r.commodity} trade with ${r.partner} = $${(r.value / 1e9).toFixed(2)}B ` +
          `(mean: $${(avg / 1e9).toFixed(2)}B)`
        );
      }
    });
  }

  return signals;
}

// Briefing — check recent trade data for key commodities, detect anomalies
export async function briefing() {
  const currentYear = new Date().getFullYear();
  const prevYear = currentYear - 1;

  // Key combinations to check: US imports of strategic commodities
  const keyCommodities = ['2709', '2711', '7108', '8542', '93'];
  const keyReporters = [842, 156]; // US, China

  const tradeFlows = [];
  const signals = [];

  for (const reporter of keyReporters) {
    for (const cmdCode of keyCommodities) {
      // Try current year first, fall back to previous year
      let data = await getTradeData({
        reporterCode: reporter,
        cmdCode,
        period: currentYear,
        flowCode: 'M',
      });

      // Comtrade returns data in different structures; normalize
      let records = data?.data || data?.dataset || [];
      if (!Array.isArray(records)) records = [];

      // If no current year data, try previous year
      if (records.length === 0) {
        data = await getTradeData({
          reporterCode: reporter,
          cmdCode,
          period: prevYear,
          flowCode: 'M',
        });
        records = data?.data || data?.dataset || [];
        if (!Array.isArray(records)) records = [];
      }

      const compact = records.slice(0, 10).map(compactRecord);
      if (compact.length > 0) {
        tradeFlows.push({
          reporter: COUNTRIES[reporter] || reporter,
          commodity: STRATEGIC_COMMODITIES[cmdCode] || cmdCode,
          cmdCode,
          topPartners: compact,
          totalRecords: records.length,
        });

        // Run anomaly detection
        const anomalies = detectAnomalies(compact);
        signals.push(...anomalies);
      }
    }
  }

  return {
    source: 'UN Comtrade',
    timestamp: new Date().toISOString(),
    tradeFlows,
    signals: signals.length > 0
      ? signals
      : ['No significant trade anomalies detected in sampled commodities'],
    status: tradeFlows.length > 0 ? 'ok' : 'no_data',
    note: 'Comtrade data often lags 1-2 months. Recent periods may be incomplete.',
    coveredCommodities: STRATEGIC_COMMODITIES,
    coveredCountries: COUNTRIES,
  };
}

// Run standalone
if (process.argv[1]?.endsWith('comtrade.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
