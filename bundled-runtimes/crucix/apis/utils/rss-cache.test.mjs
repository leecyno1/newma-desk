import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { fetchNewsResult, synthesize, DEFAULT_NEWS_FEEDS } from '../../dashboard/inject.mjs';

const feeds = [['https://example.org/rss', 'Synthetic']];
const xml = '<rss><channel><item><title>India growth report</title></item></channel></rss>';
async function fixture(t) {
  const dir = await mkdtemp(join(tmpdir(), 'crucix-rss-cache-test-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  return dir;
}

test('RSS survives repeat failure and offline restoration without refreshing its clock', async (t) => {
  const cacheDir = await fixture(t);
  let mode = 'ok';
  t.mock.method(globalThis, 'fetch', async () => new Response(mode === 'ok' ? xml : '<html>Unavailable</html>'));
  const first = await fetchNewsResult(feeds, { cacheDir });
  assert.equal(first.news.length, 1);
  mode = 'error';
  for (let attempt = 0; attempt < 2; attempt++) {
    const failed = await fetchNewsResult(feeds, { cacheDir });
    assert.equal(failed.meta.status, 'partial');
    assert.equal(failed.meta.coverage.failed, 1);
    assert.equal(failed.meta.items[0].count, null);
    assert.equal(failed.meta.items[0].availableCount, 1);
    assert.equal(failed.news[0].cached, true);
    assert.equal(failed.news[0].collectedAt, first.news[0].collectedAt);
    assert.equal(failed.news[0].date, null);
  }
  const before = await readFile(join(cacheDir, 'rss-cache.json'), 'utf8');
  t.mock.method(globalThis, 'fetch', async () => { assert.fail('Offline restore must not fetch'); });
  const restored = await fetchNewsResult(feeds, { cacheDir, refresh: false });
  assert.equal(restored.news[0].collectedAt, first.news[0].collectedAt);
  assert.equal(restored.meta.mode, 'cache');
  assert.equal(restored.meta.items[0].status, 'error');
  assert.equal(await readFile(join(cacheDir, 'rss-cache.json'), 'utf8'), before);
});

test('valid empty feed replaces old articles, changed URL/name and state directory never borrow results', async (t) => {
  const cacheDir = await fixture(t);
  t.mock.method(globalThis, 'fetch', async () => new Response(xml));
  await fetchNewsResult(feeds, { cacheDir });
  for (const changed of [[['https://example.org/other', 'Synthetic']], [['https://example.org/rss', 'Other']]]) {
    assert.deepEqual((await fetchNewsResult(changed, { cacheDir, refresh: false })).news, []);
  }
  const otherDir = await fixture(t);
  assert.deepEqual((await fetchNewsResult(feeds, { cacheDir: otherDir, refresh: false })).news, []);
  t.mock.method(globalThis, 'fetch', async () => new Response('<rss><channel/></rss>'));
  const empty = await fetchNewsResult(feeds, { cacheDir });
  assert.equal(empty.meta.status, 'ok');
  assert.equal(empty.meta.items[0].count, 0);
  t.mock.method(globalThis, 'fetch', async () => new Response('Unavailable', { status: 503 }));
  const failed = await fetchNewsResult(feeds, { cacheDir });
  assert.deepEqual(failed.news, []);
  assert.equal(failed.meta.items[0].availableCount, 0);
  assert.equal(failed.meta.items[0].count, null);
});

test('missing, corrupt and unwritable caches are explicit while live results remain available', async (t) => {
  const cacheDir = await fixture(t);
  t.mock.method(globalThis, 'fetch', async () => new Response(xml));
  const missing = await fetchNewsResult(feeds, { cacheDir, refresh: false });
  assert.equal(missing.meta.cache.status, 'missing');
  await writeFile(join(cacheDir, 'rss-cache.json'), '{broken');
  const corrupt = await fetchNewsResult(feeds, { cacheDir, refresh: false });
  assert.equal(corrupt.meta.cache.status, 'error');
  assert.deepEqual(corrupt.news, []);
  const blocker = join(cacheDir, 'not-a-directory');
  await writeFile(blocker, 'fixture');
  const live = await fetchNewsResult(feeds, { cacheDir: blocker });
  assert.equal(live.news.length, 1);
  assert.equal(live.meta.cache.status, 'error');
  assert.equal(live.meta.status, 'partial');
});

test('synthesized feed propagates cached source time rather than current sweep time', async (t) => {
  const cacheDir = await fixture(t);
  t.mock.method(globalThis, 'fetch', async () => new Response(xml));
  const first = await fetchNewsResult([DEFAULT_NEWS_FEEDS[0]], { cacheDir });
  t.mock.method(globalThis, 'fetch', async () => { assert.fail('No refresh'); });
  const view = await synthesize({ crucix: { timestamp: '2099-01-01T00:00:00Z' }, sources: {} },
    { refreshNews: false, newsCacheDir: cacheDir });
  assert.equal(view.newsFeed[0].collectedAt, first.news[0].collectedAt);
  assert.equal(view.newsFeed[0].cached, true);
  assert.equal(view.newsFeed[0].timestamp, null);
  assert.equal(view.newsMeta.mode, 'cache');
});
