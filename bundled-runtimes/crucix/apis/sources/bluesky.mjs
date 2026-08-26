// Bluesky — AT Protocol social intelligence
// No auth required for public search. Real-time social sentiment on geopolitical/market topics.
// Public API: app.bsky.feed.searchPosts (full-text search, sorted by latest)

import { safeFetch } from '../utils/fetch.mjs';

const BASE = 'https://public.api.bsky.app/xrpc';

// Rate-limit-safe delay
function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// Search public posts by query string
export async function searchPosts(query, opts = {}) {
  const { limit = 25, sort = 'latest' } = opts;
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
    sort,
  });
  return safeFetch(`${BASE}/app.bsky.feed.searchPosts?${params}`);
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

// Categorize posts by topic bucket based on keyword matching
function categorize(posts, keywords) {
  return posts.filter(p =>
    keywords.some(k => p.text?.toLowerCase().includes(k))
  );
}

// Briefing — search key geopolitical/market terms and categorize
export async function briefing() {
  const searchQueries = [
    { label: 'conflict', q: 'Iran war OR missile strike OR sanctions' },
    { label: 'markets', q: 'market crash OR oil prices OR gold OR recession' },
    { label: 'health', q: 'pandemic OR outbreak OR epidemic' },
  ];

  const allPosts = [];
  const topicResults = {};

  for (const { label, q } of searchQueries) {
    const result = await searchPosts(q, { limit: 25 });
    const posts = (result?.posts || []).map(compactPost);
    topicResults[label] = posts;
    allPosts.push(...posts);
    // Small delay between searches to be polite to the API
    await delay(1500);
  }

  return {
    source: 'Bluesky',
    timestamp: new Date().toISOString(),
    topics: {
      conflict: topicResults.conflict || [],
      markets: topicResults.markets || [],
      health: topicResults.health || [],
    },
  };
}

// Run standalone
if (process.argv[1]?.endsWith('bluesky.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
