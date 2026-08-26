// OpenSanctions — Global Sanctions & PEP Aggregator
// No auth required for basic queries. Aggregates sanctions data from
// OFAC, EU, UN, and 30+ other sources into a unified searchable dataset.

import { safeFetch } from '../utils/fetch.mjs';

const BASE = 'https://api.opensanctions.org';

// Search sanctioned entities by name/keyword
export async function searchEntities(query, opts = {}) {
  const { limit = 20, schema, topics } = opts;

  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
  });
  if (schema) params.set('schema', schema);    // e.g. "Person", "Company", "Organization"
  if (topics) params.set('topics', topics);     // e.g. "sanction", "crime", "poi"

  return safeFetch(`${BASE}/search/default?${params}`, { timeout: 15000 });
}

// Get available datasets/collections
export async function getCollections() {
  return safeFetch(`${BASE}/collections`, { timeout: 15000 });
}

// Get details about a specific dataset
export async function getDataset(name) {
  return safeFetch(`${BASE}/datasets/${name}`, { timeout: 15000 });
}

// Get a specific entity by ID
export async function getEntity(entityId) {
  return safeFetch(`${BASE}/entities/${entityId}`, { timeout: 15000 });
}

// Compact entity for briefing output
function compactEntity(e) {
  return {
    id: e.id,
    name: e.caption || e.name,
    schema: e.schema,
    datasets: e.datasets,
    topics: e.topics,
    countries: e.properties?.country || [],
    lastSeen: e.last_seen,
    firstSeen: e.first_seen,
  };
}

// Compact search results
function compactSearchResult(result, query) {
  const entities = (result?.results || []).map(compactEntity);
  return {
    query,
    totalResults: result?.total || 0,
    entities: entities.slice(0, 10),
  };
}

// Key entities/subjects to monitor for sanctions intelligence
const BRIEFING_QUERIES = [
  'Iran',
  'Russia',
  'North Korea',
  'Syria',
  'Venezuela',
  'Wagner',
];

// Briefing — search for notable sanctioned entities across key targets
export async function briefing() {
  // Run searches in parallel
  const results = await Promise.all(
    BRIEFING_QUERIES.map(async (query) => {
      const data = await searchEntities(query, { limit: 10, topics: 'sanction' });
      return compactSearchResult(data, query);
    })
  );

  // Also fetch dataset metadata for context
  const collections = await getCollections();
  const datasetSummary = Array.isArray(collections)
    ? collections.slice(0, 10).map(c => ({
        name: c.name,
        title: c.title,
        entityCount: c.entity_count,
        lastUpdated: c.updated_at,
      }))
    : [];

  // Aggregate totals
  const totalSanctionedEntities = results.reduce(
    (sum, r) => sum + (r.totalResults || 0), 0
  );

  return {
    source: 'OpenSanctions',
    timestamp: new Date().toISOString(),
    recentSearches: results,
    totalSanctionedEntities,
    datasets: datasetSummary,
    monitoringTargets: BRIEFING_QUERIES,
  };
}

// Run standalone
if (process.argv[1]?.endsWith('opensanctions.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
