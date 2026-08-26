// US Treasury Fiscal Data — Government debt, spending, yields
// No auth required. Daily updates.

import { safeFetch, today, daysAgo } from '../utils/fetch.mjs';

const BASE = 'https://api.fiscaldata.treasury.gov/services/api/fiscal_service';

// Debt to the Penny (daily national debt)
export async function getDebtToThePenny(days = 30) {
  const params = new URLSearchParams({
    'fields': 'record_date,tot_pub_debt_out_amt,intragov_hold_amt,debt_held_public_amt',
    'sort': '-record_date',
    'page[size]': '30',
    'filter': `record_date:gte:${daysAgo(days)}`,
  });
  return safeFetch(`${BASE}/v2/accounting/od/debt_to_penny?${params}`);
}

// Daily Treasury Statement (government cash flow)
export async function getDailyStatement(days = 7) {
  const params = new URLSearchParams({
    'fields': 'record_date,account_type,close_today_bal',
    'sort': '-record_date',
    'page[size]': '20',
    'filter': `record_date:gte:${daysAgo(days)}`,
  });
  return safeFetch(`${BASE}/v1/accounting/dts/deposits_withdrawals_operating_cash?${params}`);
}

// Treasury yield curves (average interest rates on debt)
export async function getAvgInterestRates() {
  const params = new URLSearchParams({
    'fields': 'record_date,security_desc,avg_interest_rate_amt',
    'sort': '-record_date',
    'page[size]': '50',
    'filter': `record_date:gte:${daysAgo(30)}`,
  });
  return safeFetch(`${BASE}/v2/accounting/od/avg_interest_rates?${params}`);
}

// Briefing — key treasury data
export async function briefing() {
  const [debt, rates] = await Promise.all([
    getDebtToThePenny(14),
    getAvgInterestRates(),
  ]);

  const debtData = debt?.data || [];
  const latestDebt = debtData[0];
  const signals = [];

  if (latestDebt) {
    const totalDebt = parseFloat(latestDebt.tot_pub_debt_out_amt);
    if (totalDebt > 36_000_000_000_000) {
      signals.push(`National debt at $${(totalDebt / 1e12).toFixed(2)}T`);
    }
  }

  return {
    source: 'US Treasury',
    timestamp: new Date().toISOString(),
    debt: debtData.slice(0, 5).map(d => ({
      date: d.record_date,
      totalDebt: d.tot_pub_debt_out_amt,
      publicDebt: d.debt_held_public_amt,
      intragovDebt: d.intragov_hold_amt,
    })),
    interestRates: (rates?.data || []).slice(0, 20).map(r => ({
      date: r.record_date,
      security: r.security_desc,
      rate: r.avg_interest_rate_amt,
    })),
    signals,
  };
}

if (process.argv[1]?.endsWith('treasury.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
