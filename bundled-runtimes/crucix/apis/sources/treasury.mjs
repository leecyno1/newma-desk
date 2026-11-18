// US Treasury Fiscal Data — outstanding debt and monthly average financing rates.
// Average interest rates on outstanding securities are NOT market yield curves.

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

// Monthly average interest rates on outstanding Treasury debt (not traded yields).
export async function getAvgInterestRates() {
  const params = new URLSearchParams({
    'fields': 'record_date,security_type_desc,security_desc,avg_interest_rate_amt',
    'sort': '-record_date',
    'page[size]': '1000',
    // A 30-day window can exclude the latest published month at month-end.
    'filter': `record_date:gte:${daysAgo(120)}`,
  });
  return safeFetch(`${BASE}/v2/accounting/od/avg_interest_rates?${params}`);
}

function numeric(value) {
  return /^[-+]?\d+(?:\.\d+)?$/.test(String(value)) && Number.isFinite(Number(value)) ? Number(value) : null;
}

function dataset(response, mapRow, requiredFields) {
  if (response?.error || !Array.isArray(response?.data)) {
    const httpStatus = Number.isInteger(response?.status) && response.status >= 400 && response.status <= 599 ? response.status : null;
    return { rows: [], coverage: { status: 'error', latestDate: null, count: null, httpStatus,
      errorCode: httpStatus ? 'HTTP_ERROR' : response?.error ? 'REQUEST_FAILED' : 'INVALID_RESPONSE' } };
  }
  const validDate = row => typeof row?.record_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(row.record_date)
    && Number.isFinite(Date.parse(row.record_date)) && new Date(row.record_date).toISOString().slice(0, 10) === row.record_date
    && row.record_date <= today();
  const dated = response.data.filter(validDate).sort((a, b) => b.record_date.localeCompare(a.record_date));
  const latestDate = dated[0]?.record_date || null;
  const rows = dated.map(mapRow);
  const newest = rows.filter(row => row.date === latestDate);
  const invalid = dated.length !== response.data.length || newest.some(row => requiredFields.some(key => row[key] === null || row[key] === ''));
  const truncated = Number(response.meta?.['total-pages']) > 1;
  return { rows, coverage: { latestDate, count: newest.length, truncated,
    status: invalid || truncated ? 'partial' : rows.length ? 'ok' : 'no_data' } };
}

// Briefing — key treasury data
export async function briefing() {
  const [debt, rates] = await Promise.all([
    getDebtToThePenny(14),
    getAvgInterestRates(),
  ]);

  const debtResult = dataset(debt, d => ({ date: d.record_date,
    totalDebt: numeric(d.tot_pub_debt_out_amt) === null ? null : String(d.tot_pub_debt_out_amt),
    publicDebt: numeric(d.debt_held_public_amt) === null ? null : String(d.debt_held_public_amt),
    intragovDebt: numeric(d.intragov_hold_amt) === null ? null : String(d.intragov_hold_amt),
    unit: 'USD', frequency: 'daily',
  }), ['totalDebt', 'publicDebt', 'intragovDebt']);
  const rateResult = dataset(rates, r => ({ date: r.record_date,
    security: typeof r.security_desc === 'string' ? r.security_desc : '',
    securityType: typeof r.security_type_desc === 'string' ? r.security_type_desc : '',
    rate: numeric(r.avg_interest_rate_amt), unit: 'percent', frequency: 'monthly',
    basis: 'outstanding-debt-average-interest-rate',
  }), ['rate', 'security']);
  const statuses = [debtResult.coverage.status, rateResult.coverage.status];

  return {
    source: 'US Treasury',
    timestamp: new Date().toISOString(),
    status: statuses.every(s => s === 'ok') ? 'ok' : statuses.every(s => s === 'error') ? 'error'
      : statuses.every(s => s === 'no_data') ? 'no_data' : 'partial',
    coverage: { debt: debtResult.coverage, interestRates: rateResult.coverage },
    debt: debtResult.rows.slice(0, 5),
    interestRates: rateResult.rows.filter(r => r.date === rateResult.coverage.latestDate),
    debtUrl: `${BASE}/v2/accounting/od/debt_to_penny`,
    ratesUrl: `${BASE}/v2/accounting/od/avg_interest_rates`,
    signals: [],
    note: 'Outstanding debt and average financing cost are observations, not market yields or standalone trading signals.',
  };
}

if (process.argv[1]?.endsWith('treasury.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
