// Bluesky — AT Protocol social intelligence
// No auth required for public search. Real-time social sentiment on geopolitical/market topics.
// Public API: app.bsky.feed.searchPosts (full-text search, sorted by latest)

import { safeFetch } from '../utils/fetch.mjs';
import { sourceDelay as delay } from '../utils/source-request.mjs';
import { queryReceipt } from '../utils/source-health.mjs';

const BASE = 'https://public.api.bsky.app/xrpc';

// Search public posts by query string
export async function searchPosts(query, opts = {}) {
  const { limit = 25, sort = 'latest' } = opts;
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
    sort,
  });
  // Three topic requests and two 1.5s pauses fit the 30s source deadline.
  return safeFetch(`${BASE}/app.bsky.feed.searchPosts?${params}`, { timeout: 8000, retries: 0 });
}

// Compact a post for briefing output
function compactPost(post) {
  const record = post?.record || post;
  const author = post?.author;
  return {
    text: (record?.text || '').slice(0, 200),
    author: author?.handle || author?.displayName || 'unknown',
    date: record?.createdAt || null,
    likes: post?.likeCount ?? 0,
  };
}

// Briefing — search key geopolitical/market terms and categorize
export async function briefing() {
  const searchQueries = [
    { label: 'conflict', q: 'Iran war OR missile strike OR sanctions' },
    { label: 'markets', q: 'market crash OR oil prices OR gold OR recession' },
    { label: 'health', q: 'pandemic OR outbreak OR epidemic' },
  ];

  const topicResults = {};
  const queryStatus = {};
  const gaps = {};
  let succeeded = 0;

  for (const [index, { label, q }] of searchQueries.entries()) {
    const result = await searchPosts(q, { limit: 25 });
    const envelope = !result?.error && Array.isArray(result?.posts);
    const posts = envelope ? result.posts.filter(post => {
      const text = post?.record?.text ?? post?.text;
      return typeof text === 'string' && text.trim();
    }).map(compactPost) : [];
    const known = envelope && (result.posts.length === 0 || posts.length > 0);
    topicResults[label] = known ? posts : null;
    if (known) succeeded++;
    if (!known) gaps[label] = '主题查询失败或响应格式无效，不能据此判断没有讨论';
    else if (posts.length !== result.posts.length) gaps[label] = '部分帖子格式无效，已保留有效记录';
    queryStatus[label] = queryReceipt(result, known, !!gaps[label]);
    // Wait only between queries; cancellation still stops the sequence.
    if (index < searchQueries.length - 1) await delay(1500);
  }

  return {
    source: 'Bluesky',
    timestamp: new Date().toISOString(),
    status: succeeded === 0 ? 'error' : Object.keys(gaps).length ? 'partial' : 'ok',
    coverage: { requested: searchQueries.length, succeeded, failed: searchQueries.length - succeeded },
    gaps, queryStatus,
    topics: topicResults,
  };
}

// Run standalone
if (process.argv[1]?.endsWith('bluesky.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
