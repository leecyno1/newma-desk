import assert from 'node:assert/strict';
import test from 'node:test';
import { briefing, getDataset, getEntity } from '../sources/opensanctions.mjs';
import { sourceHealth, sourceOutcome } from './source-health.mjs';

const catalog = { datasets: [{ name: 'sanctions', title: 'Sanctions', entity_count: 100,
  updated_at: '2026-10-20T00:00:00Z' }], current: ['sanctions'], outdated: [], index_stale: false };
const entity = { id: 'sample-id', caption: 'Sample only', schema: 'Company', datasets: ['sanctions'],
  properties: { topics: ['sanction'], country: ['xx'] }, last_seen: '2026-10-20T00:00:00Z' };
const search = (rows = [], value = rows.length, relation = 'eq') => ({ limit: 10, offset: 0,
  total: { value, relation }, results: rows, facets: {} });
function setKey(t, value = 'test-not-a-real-key') {
  const previous = process.env.OPENSANCTIONS_API_KEY;
  process.env.OPENSANCTIONS_API_KEY = value;
  t.after(() => { if (previous === undefined) delete process.env.OPENSANCTIONS_API_KEY;
    else process.env.OPENSANCTIONS_API_KEY = previous; });
}

test('no key means no outgoing request and unknown risk, not zero sanctions', async t => {
  setKey(t, '');
  const mock = t.mock.method(globalThis, 'fetch', () => { throw new Error('must not request'); });
  const data = await briefing();
  assert.equal(mock.mock.callCount(), 0);
  assert.equal(data.status, 'no_key');
  assert.equal(data.totalSanctionedEntities, null);
  assert.equal(data.sampledUniqueEntities, null);
  assert.equal(data.recentSearches, null);
  assert.equal(data.coverage.notAttempted, 6);
  assert.match(sourceOutcome('OpenSanctions', data).reason, /风险未知/);
});

test('401 stays failure and credentials are only in the header, never results', async t => {
  setKey(t);
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async (url, opts) => {
    calls++;
    assert.equal(opts.headers.Authorization, 'ApiKey test-not-a-real-key');
    assert.doesNotMatch(String(url), /test-not-a-real-key/);
    return new Response('private upstream details', { status: 401 });
  });
  const data = await briefing();
  assert.equal(calls, 7); // Six keyword requests and one catalog; no retries.
  assert.equal(data.status, 'error');
  assert.equal(data.sampledUniqueEntities, null);
  assert.equal(data.coverage.failed, 6);
  assert.ok(data.recentSearches.every(row => row.totalResults === null && row.entities === null && row.httpStatus === 401));
  assert.match(sourceOutcome('OpenSanctions', data).reason, /0\/6.*401/);
  assert.doesNotMatch(JSON.stringify(data), /private upstream|test-not-a-real-key/);
});

test('invalid responses do not become successful zero counts', async t => {
  setKey(t);
  const invalid = [{}, { results: [], total: 0 }, { results: [], total: { value: 2 } },
    { results: [entity], total: { value: 0 } }, { results: [null], total: { value: 1 } },
    { results: [], total: { value: 0, relation: 'unknown' } }];
  t.mock.method(globalThis, 'fetch', async url => Response.json(String(url).endsWith('/catalog') ? catalog : invalid.shift()));
  const data = await briefing();
  assert.equal(data.status, 'error');
  assert.ok(data.recentSearches.every(row => row.errorCode === 'INVALID_RESPONSE' && row.totalResults === null));
});

test('valid empty searches retain real zero without implying global absence', async t => {
  setKey(t);
  t.mock.method(globalThis, 'fetch', async url => Response.json(String(url).endsWith('/catalog') ? catalog : search()));
  const data = await briefing();
  assert.equal(data.status, 'ok');
  assert.equal(data.coverage.succeeded, 6);
  assert.ok(data.recentSearches.every(row => row.totalResults === 0 && row.totalRelation === 'eq'));
  assert.equal(data.sampledUniqueEntities, 0);
  assert.equal(data.totalSanctionedEntities, null);
  assert.match(data.note, /不是全球制裁总量/);
});

test('sample overlap is deduplicated, lower bounds and source timestamps are retained', async t => {
  setKey(t);
  t.mock.method(globalThis, 'fetch', async url => {
    const target = new URL(url);
    if (target.pathname === '/catalog') return Response.json(catalog);
    assert.equal(target.pathname, '/search/default');
    assert.equal(target.searchParams.get('filter_op'), 'AND');
    assert.equal(target.searchParams.get('topics'), 'sanction');
    return Response.json(search([entity], 10000, 'gte'));
  });
  const data = await briefing();
  assert.equal(data.sampledUniqueEntities, 1);
  assert.equal(data.totalSanctionedEntities, null);
  assert.equal(data.recentSearches[0].totalResults, 10000);
  assert.equal(data.recentSearches[0].totalRelation, 'gte');
  assert.equal(data.recentSearches[0].sampleLimited, true);
  assert.deepEqual(data.recentSearches[0].entities[0].topics, ['sanction']);
  assert.equal(data.recentSearches[0].entities[0].lastSeen, entity.last_seen);
  assert.equal(data.datasets[0].lastUpdated, catalog.datasets[0].updated_at);
});

test('mixed success and failed metadata remain partial without discarding valid samples', async t => {
  setKey(t);
  t.mock.method(globalThis, 'fetch', async url => {
    const target = new URL(url);
    return target.pathname === '/catalog' || target.searchParams.get('q') === 'Iran'
      ? new Response('', { status: 403 }) : Response.json(search([entity]));
  });
  const data = await briefing();
  assert.equal(data.status, 'partial');
  assert.equal(data.coverage.succeeded, 5);
  assert.equal(data.sampledUniqueEntities, 1);
  assert.equal(data.metadataStatus, 'error');
  assert.equal(data.datasets, null);
  assert.match(sourceOutcome('OpenSanctions', data).reason, /5\/6.*403.*目录/);
});

test('stale catalog cannot report complete freshness and helper uses current endpoints', async t => {
  setKey(t);
  const urls = [];
  t.mock.method(globalThis, 'fetch', async url => {
    urls.push(new URL(url).pathname);
    return Response.json(String(url).endsWith('/catalog') ? { ...catalog, index_stale: true }
      : String(url).includes('/entities/') ? entity : search());
  });
  const data = await briefing();
  assert.equal(data.status, 'partial');
  assert.equal(data.metadataStatus, 'stale');
  assert.equal((await getDataset('sanctions')).name, 'sanctions');
  assert.equal((await getEntity('sample-id')).id, 'sample-id');
  assert.ok(urls.includes('/catalog') && urls.includes('/entities/sample-id'));
  assert.ok(!urls.includes('/collections') && !urls.some(url => url.startsWith('/datasets/')));
});

test('legacy false-zero snapshots are unknown even if old timing claims success', () => {
  const result = sourceHealth({ sources: { OpenSanctions: { recentSearches: [], totalSanctionedEntities: 0 } },
    timing: { OpenSanctions: { status: 'ok', reason: '采集完成' } } });
  assert.equal(result.health[0].status, 'unknown');
  assert.equal(result.counts.sourcesUnknown, 1);
  assert.equal(result.counts.sourcesOk, 0);
});
