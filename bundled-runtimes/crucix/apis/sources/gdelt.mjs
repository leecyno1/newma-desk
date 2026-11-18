// GDELT — Global Database of Events, Language, and Tone
// No auth required. Updates every 15 minutes. Monitors news in 100+ languages.
// DOC 2.0 API: full-text search across last 3 months of global news
// GEO 2.0 API: geolocation mapping of events

import { safeFetch } from '../utils/fetch.mjs';
import { sourceDelay as delay, sourceSignal } from '../utils/source-request.mjs';
import { queryReceipt } from '../utils/source-health.mjs';

const BASE = 'https://api.gdeltproject.org/api/v2';
// Two 12s requests plus the 5.5s inter-query pause fit the 30s source deadline.
// Do not let safeFetch's 2s retry violate GDELT's 5s request spacing.
const REQUEST = { timeout: 12000, retries: 0 };

// Search recent global events/articles by keyword
export async function searchEvents(query = '', opts = {}) {
  const {
    mode = 'ArtList',       // ArtList, TimelineVol, TimelineVolInfo, TimelineTone, TimelineLang, TimelineSourceCountry
    maxRecords = 75,
    timespan = '24h',       // e.g. "24h", "7d", "3m"
    format = 'json',
    sortBy = 'DateDesc',    // DateDesc, DateAsc, ToneDesc, ToneAsc
  } = opts;

  // If no query, use broad geopolitical terms
  const q = query || '(conflict OR crisis OR military OR sanctions OR war OR economy)';
  const params = new URLSearchParams({
    query: q,
    mode,
    maxrecords: String(maxRecords),
    timespan,
    format,
    sort: sortBy,
  });

  return safeFetch(`${BASE}/doc/doc?${params}`, REQUEST);
}

// Get tone/sentiment timeline for a topic
export async function toneTrend(query, timespan = '7d') {
  const params = new URLSearchParams({
    query,
    mode: 'TimelineTone',
    timespan,
    format: 'json',
  });
  return safeFetch(`${BASE}/doc/doc?${params}`, REQUEST);
}

// Get volume timeline for a topic (how much coverage)
export async function volumeTrend(query, timespan = '7d') {
  const params = new URLSearchParams({
    query,
    mode: 'TimelineVol',
    timespan,
    format: 'json',
  });
  return safeFetch(`${BASE}/doc/doc?${params}`, REQUEST);
}

// GEO API — geographic event mapping
export async function geoEvents(query = '', opts = {}) {
  const {
    mode = 'PointData',
    timespan = '24h',
    format = 'GeoJSON',
    maxPoints = 500,
  } = opts;

  const q = query || '(conflict OR military OR protest OR explosion)';
  const params = new URLSearchParams({
    query: q,
    mode,
    timespan,
    format,
    maxpoints: String(maxPoints),
  });

  return safeFetch(`${BASE}/geo/geo?${params}`, REQUEST);
}

// Compact article for briefing
function compactArticle(a) {
  return {
    title: a.title,
    url: a.url,
    date: a.seendate,
    domain: a.domain,
    language: a.language,
    country: a.sourcecountry,
  };
}

// Briefing mode — get top global events summary (sequential due to rate limit)
export async function briefing() {
  // Single broad query to stay within rate limits
  const all = await searchEvents(
    '(conflict OR military OR economy OR crisis OR war OR sanctions OR tariff OR strike OR outbreak)',
    { maxRecords: 50, timespan: '24h' }
  );

  const gaps = {};
  const articleEnvelope = !all?.error && Array.isArray(all?.articles);
  const articles = articleEnvelope ? all.articles
    .filter(a => typeof a?.title === 'string' && a.title.trim()).map(compactArticle) : [];
  const articlesKnown = articleEnvelope && (all.articles.length === 0 || articles.length > 0);
  if (!articlesKnown) gaps.articles = '文章查询失败或响应格式无效，不能据此判断没有新闻';
  else if (articles.length !== all.articles.length) gaps.articles = '部分文章格式无效，已保留有效记录';
  const queryStatus = { articles: queryReceipt(all, articlesKnown, !!gaps.articles) };

  // Categorize by keyword matching in titles
  const categorize = (keywords) => articles.filter(a =>
    keywords.some(k => a.title?.toLowerCase().includes(k))
  );

  const throttled = all?.status === 429 || all?.httpStatus === 429;
  let geoPoints = [];
  let geoKnown = false;
  if (throttled) {
    gaps.geo = '文章接口限流，本轮地图查询未执行；地图数据未知';
    queryStatus.geo = { status: 'skipped', reason: gaps.geo, asOf: new Date().toISOString() };
  } else {
    // Space ordinary requests, but never continue this batch after HTTP 429.
    await delay(5500);
    try {
      const geo = await geoEvents('(conflict OR military OR protest OR crisis)', { maxPoints: 30, timespan: '24h' });
      const geoEnvelope = !geo?.error && Array.isArray(geo?.features);
      geoPoints = (geoEnvelope ? geo.features : []).filter(f => {
        const coordinates = f?.geometry?.coordinates;
        return Array.isArray(coordinates) && Number.isFinite(coordinates[0]) && Number.isFinite(coordinates[1])
          && Math.abs(coordinates[0]) <= 180 && Math.abs(coordinates[1]) <= 90;
      }).map(f => ({
        lat: f.geometry.coordinates[1],
        lon: f.geometry.coordinates[0],
        name: typeof (f.properties?.name ?? f.properties?.html) === 'string' ? (f.properties.name ?? f.properties.html) : '',
        count: Number.isFinite(f.properties?.count) ? f.properties.count : null,
        type: f.properties?.type || 'event',
      }));
      geoKnown = geoEnvelope && (geo.features.length === 0 || geoPoints.length > 0);
      if (!geoKnown) gaps.geo = '地理事件查询失败或响应格式无效，不能据此判断没有事件';
      else if (geoPoints.length !== geo.features.length) gaps.geo = '部分地理事件坐标无效，已保留有效记录';
      queryStatus.geo = queryReceipt(geo, geoKnown, !!gaps.geo);
    } catch {
      sourceSignal()?.throwIfAborted();
      gaps.geo = '地理事件查询失败，已保留文章查询结果';
      queryStatus.geo = queryReceipt(null, false);
    }
  }
  const succeeded = Number(articlesKnown) + Number(geoKnown);

  return {
    source: 'GDELT',
    timestamp: new Date().toISOString(),
    status: succeeded === 0 ? 'error' : Object.keys(gaps).length ? 'partial' : 'ok',
    coverage: { requested: 2, succeeded, failed: 2 - succeeded - Number(throttled), ...(throttled ? { skipped: 1 } : {}) },
    gaps, queryStatus,
    totalArticles: articlesKnown ? articles.length : null,
    allArticles: articles,
    geoPoints,
    conflicts: categorize(['military', 'conflict', 'war', 'strike', 'missile', 'attack', 'bomb', 'troops']),
    economy: categorize(['economy', 'recession', 'inflation', 'market', 'sanctions', 'tariff', 'trade', 'gdp']),
    health: categorize(['pandemic', 'outbreak', 'epidemic', 'disease', 'virus', 'health']),
    crisis: categorize(['crisis', 'disaster', 'emergency', 'refugee', 'famine']),
  };
}

// Run standalone
if (process.argv[1]?.endsWith('gdelt.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
