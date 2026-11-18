import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { fetchAllNews, buildNewsFeed } from '../../dashboard/inject.mjs';

function mockFeed(t, title, sourceUrl = 'feeds.bbci.co.uk/news/world') {
  const date = new Date(Date.now() - 3600000).toUTCString();
  t.mock.method(globalThis, 'fetch', async (url) => new Response(
    String(url).includes(sourceUrl)
      ? `<rss><channel><item><title>${title}</title><link>https://example.org/news</link><pubDate>${date}</pubDate></item></channel></rss>`
      : '<rss><channel></channel></rss>'
  ));
}

test('RSS reference regions are deterministic and identified as headline hints', async (t) => {
  mockFeed(t, 'south africa publishes economic outlook');
  const first = await fetchAllNews();
  const second = await fetchAllNews();
  assert.equal(first.length, 1);
  // Two collections have different clocks; geography and article content do not.
  assert.deepEqual(first.map(({ collectedAt, ...item }) => item), second.map(({ collectedAt, ...item }) => item));
  assert.ok(Date.parse(second[0].collectedAt) >= Date.parse(first[0].collectedAt));
  assert.equal(first[0].geoBasis, 'headline-keyword');
  assert.equal(first[0].region, 'South Africa');
  assert.equal(first[0].lat, -30);
  assert.equal(first[0].lon, 25);
});

test('RSS without a place stays in the news feed, not at its publisher location', async (t) => {
  mockFeed(t, 'BUSINESS FUNDING gives us hope', 'sbs.com.au/');
  const news = await fetchAllNews();
  assert.equal(news.length, 1);
  assert.equal(news[0].geoBasis, 'unlocated');
  assert.equal(news[0].lat, null);
  assert.equal(news[0].lon, null);
  assert.equal(news[0].region, 'Global');
  const feed = buildNewsFeed(news, {}, [], []);
  assert.equal(feed[0].headline, 'BUSINESS FUNDING gives us hope');
  assert.equal(feed[0].url, 'https://example.org/news');
});

test('map uses only bounded, explicitly labelled RSS hints; legacy jitter is not reused', () => {
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const helper = html.match(/function newsMapItems\(\) \{[\s\S]*?\n\}/)?.[0];
  assert.ok(helper);
  const data = [
    { title: 'hint', lat: 0, lon: 0, geoBasis: 'headline-keyword' },
    { title: 'legacy', lat: 10, lon: 20 },
    { title: 'unknown', lat: null, lon: null, geoBasis: 'unlocated' },
    { title: 'out of range', lat: 91, lon: 10, geoBasis: 'headline-keyword' },
  ];
  const points = vm.runInNewContext(`${helper}; newsMapItems()`, { D: { news: data } });
  assert.deepEqual(Array.from(points, p => p.title), ['hint']);
  assert.equal((html.match(/newsMapItems\(\)\.forEach/g) || []).length, 2, 'both map modes use the same filter');
  assert.doesNotMatch(html, /const osintGeo=/, 'Telegram order must not create event locations');
});

