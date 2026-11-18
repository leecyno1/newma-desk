// OpenSanctions — Global Sanctions & PEP Aggregator
// Hosted API requires an authorized API key; keyword samples are not compliance screening.

import '../utils/env.mjs';
import { safeFetch } from '../utils/fetch.mjs';

const BASE = 'https://api.opensanctions.org';

async function request(path) {
  const key = process.env.OPENSANCTIONS_API_KEY?.trim();
  if (!key) return { errorCode: 'MISSING_CREDENTIALS', error: '未配置 OPENSANCTIONS_API_KEY' };
  const data = await safeFetch(`${BASE}${path}`, { timeout: 15000, retries: 0,
    headers: { Authorization: `ApiKey ${key}` } });
  if (data?.error) {
    const httpStatus = Number.isInteger(data.status) && data.status >= 400 && data.status <= 599 ? data.status : null;
    return { errorCode: httpStatus ? 'HTTP_ERROR' : 'REQUEST_FAILED', httpStatus,
      error: httpStatus ? `制裁来源请求失败（HTTP ${httpStatus}）` : '制裁来源请求失败' };
  }
  return data;
}

// Search sanctioned entities by name/keyword
export async function searchEntities(query, opts = {}) {
  const { limit = 20, schema, topics } = opts;

  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
    filter_op: 'AND',
  });
  if (schema) params.set('schema', schema);    // e.g. "Person", "Company", "Organization"
  if (topics) params.set('topics', topics);     // e.g. "sanction", "crime", "poi"

  return request(`/search/default?${params}`);
}

// Get available datasets/collections
export async function getCollections() {
  return request('/catalog');
}

// Get details about a specific dataset
export async function getDataset(name) {
  const catalog = await getCollections();
  if (catalog?.error) return catalog;
  return (Array.isArray(catalog?.datasets) && catalog.datasets.find(item => item?.name === name))
    || { errorCode: 'DATASET_UNAVAILABLE', error: '目录中没有可用的指定数据集' };
}

// Get a specific entity by ID
export async function getEntity(entityId) {
  return request(`/entities/${encodeURIComponent(entityId)}`);
}

// Compact entity for briefing output
function compactEntity(e) {
  return {
    id: e.id,
    name: e.caption || e.name,
    schema: e.schema,
    datasets: e.datasets,
    topics: e.properties?.topics || [],
    countries: e.properties?.country || [],
    lastSeen: e.last_seen,
    firstSeen: e.first_seen,
  };
}

// Compact search results
function compactSearchResult(result, query) {
  const total = result?.total;
  const relation = total?.relation ?? 'eq';
  if (result?.error || !Array.isArray(result?.results) || !Number.isInteger(total?.value) || total.value < 0
    || !['eq', 'gte'].includes(relation) || total.value < result.results.length
    || (total.value > 0 && result.results.length === 0)
    || result.results.some(e => !e || typeof e.id !== 'string' || !e.id || typeof e.caption !== 'string')) {
    return { query, status: 'error', totalResults: null, totalRelation: null, entities: null,
      errorCode: result?.errorCode || 'INVALID_RESPONSE', httpStatus: result?.httpStatus ?? null };
  }
  const entities = result.results.map(compactEntity);
  return {
    query, status: 'ok',
    totalResults: total.value, totalRelation: relation,
    entities: entities.slice(0, 10),
    sampleLimited: total.value > Math.min(entities.length, 10) || relation === 'gte',
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
  const base = { source: 'OpenSanctions', timestamp: new Date().toISOString(),
    monitoringTargets: BRIEFING_QUERIES, totalSanctionedEntities: null,
    note: '六个关键词的搜索样本，不是全球制裁总量、国家风险评级或合规筛查；各查询可能重叠。' };
  if (!process.env.OPENSANCTIONS_API_KEY?.trim()) return { ...base, status: 'no_key',
    message: '需配置已获授权的 OPENSANCTIONS_API_KEY；未执行制裁查询，风险未知',
    coverage: { requested: BRIEFING_QUERIES.length, succeeded: 0, failed: 0, notAttempted: BRIEFING_QUERIES.length },
    recentSearches: null, sampledUniqueEntities: null, datasets: null, metadataStatus: 'not_attempted' };
  // Run searches in parallel
  const results = await Promise.all(
    BRIEFING_QUERIES.map(async (query) => {
      const data = await searchEntities(query, { limit: 10, topics: 'sanction' });
      return compactSearchResult(data, query);
    })
  );

  // Also fetch dataset metadata for context
  const collections = await getCollections();
  const catalogValid = Array.isArray(collections?.datasets) && !collections.error
    && collections.datasets.every(c => c && typeof c.name === 'string' && typeof c.title === 'string');
  const metadataStatus = !catalogValid ? 'error'
    : collections.index_stale || collections.outdated?.length ? 'stale' : 'ok';
  const datasetSummary = catalogValid
    ? collections.datasets.slice(0, 10).map(c => ({
        name: c.name,
        title: c.title,
        entityCount: c.entity_count,
        lastUpdated: c.updated_at,
      }))
    : null;
  const succeeded = results.filter(row => row.status === 'ok').length;

  return {
    ...base,
    status: !succeeded ? 'error' : succeeded < results.length || metadataStatus !== 'ok' ? 'partial' : 'ok',
    coverage: { requested: results.length, succeeded, failed: results.length - succeeded, notAttempted: 0 },
    recentSearches: results,
    sampledUniqueEntities: succeeded ? new Set(results.flatMap(row => (row.entities || []).map(e => e.id))).size : null,
    datasets: datasetSummary,
    metadataStatus,
    metadataHttpStatus: collections?.httpStatus ?? null,
  };
}

// Run standalone
if (process.argv[1]?.endsWith('opensanctions.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
