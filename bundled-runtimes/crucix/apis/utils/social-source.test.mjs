import assert from 'node:assert/strict';
import test from 'node:test';
import { briefing as gdelt } from '../sources/gdelt.mjs';
import { briefing as bluesky } from '../sources/bluesky.mjs';
import { sourceOutcome } from './source-health.mjs';
import { synthesize } from '../../dashboard/inject.mjs';
import { withSourceDeadline } from './source-request.mjs';

for (const [name, briefing, expectedCalls] of [['GDELT', gdelt, 2], ['Bluesky', bluesky, 3]]) {
  test(`${name} retains earlier valid results when its final query times out`, { timeout: 30000 }, async (t) => {
    let calls = 0;
    t.mock.method(globalThis, 'fetch', async (url, { signal }) => {
      calls++;
      const final = name === 'GDELT' ? String(url).includes('/geo/') : new URL(url).searchParams.get('q').includes('pandemic');
      if (final) return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true }));
      return new Response(JSON.stringify(name === 'GDELT' ? { articles: [{ title: 'Synthetic valid article' }] }
        : { posts: [{ record: { text: 'Synthetic valid post' } }] }));
    });
    const data = await withSourceDeadline(name, briefing);
    assert.equal(data.status, 'partial');
    assert.equal(calls, expectedCalls, 'no retries or repeated earlier queries');
    assert.equal(data.coverage.succeeded, expectedCalls - 1);
    assert.equal(data.coverage.failed, 1);
    assert.equal(data.queryStatus[name === 'GDELT' ? 'geo' : 'health'].reason, '来源请求超时');
    assert.match(sourceOutcome(name, data).reason, /超时/);
    if (name === 'GDELT') assert.equal(data.totalArticles, 1);
    else assert.equal(data.topics.conflict.length, 1);
  });
}

test('GDELT stops the batch after HTTP 429 and marks geography skipped, not a failed or empty query', async (t) => {
  const urls = [];
  t.mock.method(globalThis, 'fetch', async url => {
    urls.push(new URL(url));
    return new Response('synthetic private limit response', { status: 429 });
  });
  const data = await gdelt();
  assert.equal(urls.length, 1, 'no retry or next endpoint after rate limiting');
  assert(urls.every(url => /^\(.+ OR .+\)$/.test(url.searchParams.get('query'))));
  assert.equal(data.queryStatus.articles.httpStatus, 429);
  assert.equal(data.queryStatus.geo.status, 'skipped');
  assert.equal(data.queryStatus.geo.httpStatus, undefined, 'do not invent a response for an unexecuted query');
  assert.match(data.queryStatus.geo.reason, /限流.*未执行/);
  assert.deepEqual(data.coverage, { requested: 2, succeeded: 0, failed: 1, skipped: 1 });
  assert.match(sourceOutcome('GDELT', data).reason, /429/);
  assert.match(sourceOutcome('GDELT', data).reason, /1项未执行/);
  assert.equal(data.totalArticles, null);
  assert.doesNotMatch(JSON.stringify(data), /private limit/);
  const view = await synthesize({ crucix: {}, sources: { GDELT: data } }, { refreshNews: false });
  assert.deepEqual(view.gdelt.coverage, data.coverage);
  assert.equal(view.gdelt.totalArticles, null);
  assert.match(view.health[0].reason, /1项未执行/);
});

test('Bluesky preserves HTTP rejection in each topic and synthesized health', async (t) => {
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => { calls++; return new Response('private denial body', { status: 403 }); });
  const data = await bluesky();
  assert.equal(calls, 3);
  assert.equal(data.queryStatus.conflict.httpStatus, 403);
  assert.equal(data.queryStatus.markets.httpStatus, 403);
  assert.equal(data.queryStatus.health.httpStatus, 403);
  assert.match(sourceOutcome('Bluesky', data).reason, /403/);
  const view = await synthesize({ crucix: {}, sources: { Bluesky: data } }, { refreshNews: false });
  assert.match(view.health[0].reason, /403/);
  assert.doesNotMatch(JSON.stringify(data), /private denial/);
});

test('GDELT failed responses remain unavailable through dashboard synthesis', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ error: 'synthetic provider secret' })));
  const data = await gdelt();
  assert.equal(sourceOutcome('GDELT', data).status, 'error');
  assert.equal(data.totalArticles, null);
  assert.deepEqual(data.coverage, { requested: 2, succeeded: 0, failed: 2 });
  assert.ok(data.gaps.articles);
  assert.ok(data.gaps.geo);
  assert.doesNotMatch(JSON.stringify(data), /provider secret/);
  const view = await synthesize({ crucix: { timestamp: '2026-10-27T00:00:00Z' }, sources: { GDELT: data } }, { refreshNews: false });
  assert.equal(view.gdelt.totalArticles, null);
  assert.equal(view.gdelt.conflicts, null);
  assert.equal(view.health.find(item => item.n === 'GDELT').status, 'error');
});

test('Bluesky failed queries are not reported as three successful empty topics', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ error: 'synthetic provider secret' })));
  const data = await bluesky();
  assert.equal(sourceOutcome('Bluesky', data).status, 'error');
  assert.deepEqual(data.topics, { conflict: null, markets: null, health: null });
  assert.deepEqual(data.coverage, { requested: 3, succeeded: 0, failed: 3 });
  assert.equal(Object.keys(data.gaps).length, 3);
  assert.doesNotMatch(JSON.stringify(data), /provider secret/);
});

test('valid empty GDELT collections preserve real zero counts', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => new Response(JSON.stringify(
    String(url).includes('/geo/') ? { type: 'FeatureCollection', features: [] } : { articles: [] },
  )));
  const data = await gdelt();
  assert.equal(sourceOutcome('GDELT', data).status, 'ok');
  assert.equal(data.totalArticles, 0);
  assert.deepEqual(data.coverage, { requested: 2, succeeded: 2, failed: 0 });
  const view = await synthesize({ crucix: {}, sources: { GDELT: data } }, { refreshNews: false });
  assert.equal(view.gdelt.totalArticles, 0);
  assert.equal(view.gdelt.conflicts, 0);
});

test('GDELT keeps valid articles and indexing time when geographic coverage fails', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => new Response(JSON.stringify(
    String(url).includes('/geo/') ? { error: 'unavailable' } : {
      articles: [{ title: 'Shipping conflict', url: 'https://example.com/story', seendate: '20261026T120000Z' }],
    },
  )));
  const data = await gdelt();
  assert.equal(sourceOutcome('GDELT', data).status, 'partial');
  assert.equal(data.totalArticles, 1);
  assert.equal(data.conflicts.length, 1);
  assert.deepEqual(data.coverage, { requested: 2, succeeded: 1, failed: 1 });
  assert.ok(data.gaps.geo);
  const view = await synthesize({ crucix: {}, sources: { GDELT: data } }, { refreshNews: false });
  assert.equal(view.health[0].status, 'partial');
  assert.equal(view.newsFeed[0].timestamp, '2026-10-26T12:00:00.000Z');
  assert.equal(view.newsFeed[0].timestampBasis, 'indexed');
});

test('GDELT preserves valid map evidence when the article query is malformed', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => new Response(JSON.stringify(
    String(url).includes('/geo/') ? { features: [
      { geometry: { coordinates: [0, 0] }, properties: { name: 'Synthetic point', count: 0 } },
      { geometry: { coordinates: [999, 999] } },
    ] } : { articles: [null, { title: 7 }] },
  )));
  const data = await gdelt();
  assert.equal(sourceOutcome('GDELT', data).status, 'partial');
  assert.equal(data.totalArticles, null);
  assert.equal(data.geoPoints.length, 1);
  assert.equal(data.geoPoints[0].count, 0);
  assert.ok(data.gaps.articles);
  assert.ok(data.gaps.geo);
});

test('Bluesky preserves an empty success, valid posts and a failed topic separately', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => {
    const query = new URL(url).searchParams.get('q');
    return new Response(JSON.stringify(query.includes('Iran') ? { posts: [] }
      : query.includes('market') ? { posts: [{ record: { text: 'Synthetic market post', createdAt: '2026-10-26T12:00:00Z' }, author: { handle: 'example.test' } }] }
      : { message: 'wrong response shape' }));
  });
  const data = await bluesky();
  assert.equal(sourceOutcome('Bluesky', data).status, 'partial');
  assert.deepEqual(data.topics.conflict, []);
  assert.equal(data.topics.markets[0].text, 'Synthetic market post');
  assert.equal(data.topics.health, null);
  assert.deepEqual(data.coverage, { requested: 3, succeeded: 2, failed: 1 });
  assert.deepEqual(Object.keys(data.gaps), ['health']);
});

test('valid empty Bluesky results are successful; malformed posts cannot masquerade as empty', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => new Response('{"posts":[]}'));
  const empty = await bluesky();
  assert.equal(sourceOutcome('Bluesky', empty).status, 'ok');
  assert.deepEqual(empty.topics, { conflict: [], markets: [], health: [] });
  mock.mock.mockImplementation(async () => new Response('{"posts":[null,{"record":{"text":12}}]}'));
  const invalid = await bluesky();
  assert.equal(sourceOutcome('Bluesky', invalid).status, 'error');
  assert.deepEqual(invalid.topics, { conflict: null, markets: null, health: null });
});
