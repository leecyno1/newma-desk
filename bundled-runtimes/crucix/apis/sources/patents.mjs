// USPTO PatentsView — Patent Intelligence
// No auth required. Tracks patent filings in strategic technology areas.
// API v1: https://search.patentsview.org/api/v1/patent/
// Useful for detecting R&D trends, tech competition, state-backed innovation.

import { safeFetch, daysAgo } from '../utils/fetch.mjs';

const BASE = 'https://search.patentsview.org/api/v1';

// Strategic technology domains and their search terms
const STRATEGIC_DOMAINS = {
  ai: {
    label: 'Artificial Intelligence',
    terms: ['artificial intelligence', 'machine learning', 'deep learning', 'neural network', 'large language model'],
  },
  quantum: {
    label: 'Quantum Computing',
    terms: ['quantum computing', 'quantum processor', 'qubit', 'quantum entanglement', 'quantum cryptography'],
  },
  nuclear: {
    label: 'Nuclear Technology',
    terms: ['nuclear fusion', 'nuclear reactor', 'nuclear fuel', 'uranium enrichment', 'small modular reactor'],
  },
  hypersonic: {
    label: 'Hypersonic & Advanced Propulsion',
    terms: ['hypersonic', 'scramjet', 'directed energy weapon', 'railgun', 'advanced propulsion'],
  },
  semiconductor: {
    label: 'Semiconductor & Chip Technology',
    terms: ['semiconductor', 'integrated circuit', 'lithography', 'chip fabrication', 'transistor'],
  },
  biotech: {
    label: 'Biotechnology & Synthetic Biology',
    terms: ['synthetic biology', 'gene editing', 'CRISPR', 'mRNA', 'bioweapon'],
  },
  space: {
    label: 'Space & Satellite Technology',
    terms: ['satellite', 'space launch', 'orbital', 'space debris', 'anti-satellite'],
  },
};

// Search patents by keyword query
export async function searchPatents(query, opts = {}) {
  const {
    since = daysAgo(90),
    limit = 10,
    sort = 'patent_date',
    sortDir = 'desc',
  } = opts;

  // PatentsView v1 API uses query params with JSON values
  const q = JSON.stringify({
    _and: [
      { _gte: { patent_date: since } },
      { _text_any: { patent_abstract: query } },
    ],
  });

  const f = JSON.stringify([
    'patent_id',
    'patent_title',
    'patent_date',
    'patent_abstract',
    'assignee_organization',
    'patent_type',
  ]);

  const o = JSON.stringify({ [sort]: sortDir });

  const params = new URLSearchParams({
    q,
    f,
    o,
    s: String(limit),
  });

  return safeFetch(`${BASE}/patent/?${params}`, { timeout: 20000 });
}

// Search by assignee organization
export async function searchByAssignee(orgName, opts = {}) {
  const { since = daysAgo(180), limit = 10 } = opts;

  const q = JSON.stringify({
    _and: [
      { _gte: { patent_date: since } },
      { _contains: { assignee_organization: orgName } },
    ],
  });

  const f = JSON.stringify([
    'patent_id',
    'patent_title',
    'patent_date',
    'patent_abstract',
    'assignee_organization',
  ]);

  const o = JSON.stringify({ patent_date: 'desc' });

  const params = new URLSearchParams({
    q,
    f,
    o,
    s: String(limit),
  });

  return safeFetch(`${BASE}/patent/?${params}`, { timeout: 20000 });
}

// Compact patent record for briefing output
function compactPatent(p) {
  return {
    id: p.patent_id,
    title: p.patent_title,
    date: p.patent_date,
    assignee: p.assignee_organization || 'Unknown',
    type: p.patent_type,
  };
}

// Search a single domain, combining its keyword terms
async function searchDomain(domain, since) {
  const terms = domain.terms.join(' ');
  const data = await searchPatents(terms, { since, limit: 10 });

  // PatentsView v1 returns { patents: [...] } or similar
  const patents = data?.patents || data?.results || [];
  if (!Array.isArray(patents)) return [];
  return patents.map(compactPatent);
}

// Briefing — search recent patents in key strategic tech areas
export async function briefing() {
  const since = daysAgo(90);
  const domainEntries = Object.entries(STRATEGIC_DOMAINS);
  const recentPatents = {};
  const signals = [];

  // Run all domain searches in parallel
  const results = await Promise.all(
    domainEntries.map(async ([key, domain]) => {
      const patents = await searchDomain(domain, since);
      return { key, label: domain.label, patents };
    })
  );

  let totalFound = 0;
  for (const { key, label, patents } of results) {
    recentPatents[key] = patents;
    totalFound += patents.length;

    if (patents.length > 0) {
      // Identify dominant assignees (potential state-backed programs)
      const assigneeCounts = {};
      patents.forEach(p => {
        if (p.assignee && p.assignee !== 'Unknown') {
          assigneeCounts[p.assignee] = (assigneeCounts[p.assignee] || 0) + 1;
        }
      });

      // Flag organizations with high patent density in strategic areas
      Object.entries(assigneeCounts).forEach(([org, count]) => {
        if (count >= 3) {
          signals.push(`HIGH ACTIVITY: ${org} filed ${count} ${label} patents in last 90 days`);
        }
      });
    }
  }

  // Track key defense/intelligence organizations specifically
  const watchOrgs = [
    'Raytheon', 'Lockheed Martin', 'Northrop Grumman', 'BAE Systems',
    'China Academy', 'Huawei', 'SMIC', 'Samsung', 'TSMC',
    'US Department', 'Navy', 'Air Force', 'Army', 'DARPA',
  ];

  for (const { patents } of results) {
    for (const p of patents) {
      if (watchOrgs.some(org => p.assignee?.toLowerCase().includes(org.toLowerCase()))) {
        signals.push(`WATCH ORG: "${p.title}" by ${p.assignee} (${p.date})`);
      }
    }
  }

  return {
    source: 'USPTO Patents',
    timestamp: new Date().toISOString(),
    searchWindow: `${since} to ${new Date().toISOString().split('T')[0]}`,
    totalFound,
    recentPatents,
    signals: signals.length > 0
      ? signals
      : ['No unusual patent filing patterns detected in strategic domains'],
    domains: Object.fromEntries(
      domainEntries.map(([key, domain]) => [key, domain.label])
    ),
  };
}

// Run standalone
if (process.argv[1]?.endsWith('patents.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
