// USAspending — Federal spending, defense contracts, procurement signals
// No auth required. Updated daily.

import { safeFetch, daysAgo } from '../utils/fetch.mjs';

const BASE = 'https://api.usaspending.gov/api/v2';

// Award type codes — required by the spending_by_award endpoint
// Contracts: A=BPA Call, B=Purchase Order, C=Delivery Order, D=Definitive Contract
// Grants: 02=Block Grant, 03=Formula Grant, 04=Project Grant, 05=Cooperative Agreement
// Direct payments: 06=Direct Payment (unrestricted), 07=Direct Payment (specified use)
// Loans: 08=Direct Loan, 09=Guaranteed/Insured Loan
// IDVs: IDV_A=GWAC, IDV_B=IDC, IDV_B_A=IDC / IDV, IDV_B_B=IDC / Multiple Award,
//        IDV_B_C=IDC / FSS, IDV_C=FSS, IDV_D=BOA, IDV_E=BPA
const CONTRACT_CODES = ['A', 'B', 'C', 'D'];
const ALL_AWARD_CODES = ['A', 'B', 'C', 'D', '02', '03', '04', '05', '06', '07', '08', '09'];

// Search recent awards/contracts
export async function searchAwards(opts = {}) {
  const {
    keywords = ['defense', 'military'],
    limit = 20,
    sortField = 'Award Amount',
    order = 'desc',
    awardTypeCodes = CONTRACT_CODES,
    days = 30,
  } = opts;

  const body = {
    filters: {
      keywords,
      time_period: [{ start_date: daysAgo(days), end_date: daysAgo(0) }],
      award_type_codes: awardTypeCodes,
    },
    fields: [
      'Award ID',
      'Recipient Name',
      'Award Amount',
      'Description',
      'Awarding Agency',
      'Start Date',
      'Award Type',
    ],
    limit,
    page: 1,
    sort: sortField,
    order,
  };

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    const res = await fetch(`${BASE}/search/spending_by_award/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok) {
      const errBody = await res.text().catch(() => '');
      return { error: `HTTP ${res.status}: ${errBody.slice(0, 300)}`, results: [] };
    }
    return res.json();
  } catch (e) {
    return { error: e.message, results: [] };
  }
}

// Get top agencies by spending
export async function getAgencySpending() {
  return safeFetch(`${BASE}/references/toptier_agencies/`);
}

// Search for defense-specific spending
export async function getDefenseSpending(days = 30) {
  return searchAwards({
    keywords: ['defense', 'military', 'missile', 'ammunition', 'aircraft', 'naval'],
    limit: 20,
    sortField: 'Award Amount',
    order: 'desc',
    awardTypeCodes: CONTRACT_CODES,
    days,
  });
}

// Briefing
export async function briefing() {
  const [defense, agencies] = await Promise.all([
    getDefenseSpending(14),
    getAgencySpending(),
  ]);

  return {
    source: 'USAspending',
    timestamp: new Date().toISOString(),
    recentDefenseContracts: (defense?.results || []).slice(0, 10).map(r => ({
      awardId: r['Award ID'],
      recipient: r['Recipient Name'],
      amount: r['Award Amount'],
      description: r['Description'],
      agency: r['Awarding Agency'],
      date: r['Start Date'],
      type: r['Award Type'],
    })),
    topAgencies: (agencies?.results || []).slice(0, 10).map(a => ({
      name: a.agency_name,
      budget: a.budget_authority_amount,
      obligations: a.obligated_amount,
      outlays: a.outlay_amount,
    })),
    ...(defense?.error ? { defenseError: defense.error } : {}),
  };
}

if (process.argv[1]?.endsWith('usaspending.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
