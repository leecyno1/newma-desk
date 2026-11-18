import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { briefing as who, getOutbreakNews } from '../sources/who.mjs';
import { briefing as reliefweb } from '../sources/reliefweb.mjs';
import { sourceOutcome } from './source-health.mjs';
import { synthesize } from '../../dashboard/inject.mjs';

const recent = () => new Date(Date.now() - 86400000).toISOString();
const response = (body) => new Response(JSON.stringify(body));

function approvedApp(t) {
  const previous = process.env.RELIEFWEB_APPNAME;
  process.env.RELIEFWEB_APPNAME = 'synthetic-approved-app';
  t.after(() => {
    if (previous === undefined) delete process.env.RELIEFWEB_APPNAME;
    else process.env.RELIEFWEB_APPNAME = previous;
  });
}

test('ReliefWeb without an approved app setting skips requests instead of impersonating a default app', async (t) => {
  approvedApp(t);
  process.env.RELIEFWEB_APPNAME = '';
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => { calls++; return response({ data: [] }); });
  const data = await reliefweb();
  assert.equal(calls, 0, 'neither ReliefWeb nor HDX should run for missing configuration');
  assert.equal(data.status, 'no_credentials');
  assert.deepEqual(data.coverage, { requested: 2, succeeded: 0, failed: 0, skipped: 2 });
  assert.equal(data.latestReports, null);
  assert.equal(data.activeDisasters, null);
  assert.match(sourceOutcome('ReliefWeb', data).reason, /RELIEFWEB_APPNAME/);
});

test('ReliefWeb uses documented v2 and current disasters and keeps HTTP rejection', async (t) => {
  approvedApp(t);
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (String(url).includes('/package_search?')) return response({ success: true, result: { results: [] } });
    requests.push({ url: new URL(url), body: JSON.parse(options.body) });
    return new Response('private bot rejection body', { status: 406 });
  });
  const data = await reliefweb();
  assert.equal(requests.length, 2);
  assert(requests.every(row => row.url.pathname.startsWith('/v2/')));
  assert.equal(requests.find(row => row.url.pathname.endsWith('/disasters')).body.filter.value, 'current');
  assert.equal(data.queryStatus.reports.httpStatus, 406);
  assert.equal(data.queryStatus.disasters.httpStatus, 406);
  assert.match(sourceOutcome('ReliefWeb', data).reason, /406/);
  assert.doesNotMatch(JSON.stringify(data), /private bot/);
});

test('WHO requests the recent window instead of filtering the oldest default page', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => {
    const params = new URL(url).searchParams;
    assert.equal(params.get('$orderby'), 'PublicationDate desc');
    assert.match(params.get('$filter'), /^PublicationDate ge /);
    assert.equal(params.get('$top'), '100');
    return response({ value: [{ Title: 'Synthetic outbreak bulletin', PublicationDate: recent(), ItemDefaultUrl: '/synthetic-test' }] });
  });
  const data = await who();
  assert.equal(data.status, 'ok');
  assert.equal(data.outbreakCount, 1);
  assert.equal(data.diseaseOutbreakNews[0].url, 'https://www.who.int/emergencies/disease-outbreak-news/synthetic-test');
  const view = await synthesize({ crucix: {}, sources: { WHO: data } }, { refreshNews: false });
  assert.equal(view.newsFeed[0].source, 'WHO');
  assert.equal(view.newsFeed[0].timestampBasis, 'published');
  assert.equal(view.newsFeed[0].timestamp, data.diseaseOutbreakNews[0].date);
  assert.equal((await getOutbreakNews()).length, 1, 'legacy caller still receives an array');
});

test('WHO distinguishes provider failures, malformed responses and valid empty windows', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async () => response({ error: 'synthetic provider private detail' }));
  for (const body of [{ error: 'synthetic provider private detail' }, { value: {} }, { value: [null, { Title: 'bad date' }] }]) {
    mock.mock.mockImplementation(async () => response(body));
    const data = await who();
    assert.equal(sourceOutcome('WHO', data).status, 'error');
    assert.equal(data.outbreakCount, null);
    assert.doesNotMatch(JSON.stringify(data), /provider private detail/);
    const dashboard = await synthesize({ crucix: {}, sources: { WHO: data } }, { refreshNews: false });
    assert.equal(dashboard.whoMeta.count, null);
    assert.equal(dashboard.health[0].status, 'error');
  }
  mock.mock.mockImplementation(async () => response({ value: [] }));
  const empty = await who();
  assert.equal(empty.status, 'ok');
  assert.equal(empty.outbreakCount, 0);
  const dashboard = await synthesize({ crucix: {}, sources: { WHO: empty } }, { refreshNews: false });
  assert.equal(dashboard.whoMeta.count, 0);
});

test('WHO retains usable bulletins but marks malformed, out-of-window and paginated coverage', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => response({
    value: [{ Title: 'Synthetic recent', PublicationDate: recent() },
      { Title: 'Synthetic old', PublicationDate: '2006-03-20T00:00:00Z' }, null],
    '@odata.nextLink': 'http://www.who.int/api/news/diseaseoutbreaknews?$skip=100',
  }));
  const data = await who();
  assert.equal(sourceOutcome('WHO', data).status, 'partial');
  assert.equal(data.diseaseOutbreakNews.length, 1);
  assert.equal(data.outbreakCount, 1);
  assert.ok(data.gaps.records && data.gaps.window && data.gaps.pagination);
});

test('ReliefWeb keeps a successful branch when another fails and HDX is unavailable', async (t) => {
  approvedApp(t);
  t.mock.method(globalThis, 'fetch', async (url) => response(String(url).includes('/reports?')
    ? { data: [{ fields: { title: 'Synthetic report', url_alias: 'https://reliefweb.int/report/test', date: { created: recent() } } }] }
    : { error: 'synthetic private failure' }));
  const data = await reliefweb();
  assert.equal(sourceOutcome('ReliefWeb', data).status, 'partial');
  assert.equal(data.latestReports.length, 1);
  assert.equal(data.latestReports[0].url, 'https://reliefweb.int/report/test');
  assert.equal(data.activeDisasters, null);
  assert.equal(data.hdxDatasets, null);
  assert.deepEqual(data.coverage, { requested: 2, succeeded: 1, failed: 1 });
  assert.doesNotMatch(JSON.stringify(data), /private failure/);
  const view = await synthesize({ crucix: {}, sources: { ReliefWeb: data } }, { refreshNews: false });
  assert.equal(view.newsFeed[0].source, 'ReliefWeb');
  assert.equal(view.health[0].status, 'partial');
});

test('ReliefWeb invalid envelopes cannot masquerade as two empty successful queries', async (t) => {
  approvedApp(t);
  const mock = t.mock.method(globalThis, 'fetch', async () => response({ message: 'wrong shape' }));
  const failed = await reliefweb();
  assert.equal(sourceOutcome('ReliefWeb', failed).status, 'error');
  assert.equal(failed.latestReports, null);
  assert.equal(failed.activeDisasters, null);
  assert.deepEqual(failed.coverage, { requested: 2, succeeded: 0, failed: 2 });
  let requests = 0;
  mock.mock.mockImplementation(async () => { requests++; return response({ data: [] }); });
  const empty = await reliefweb();
  assert.equal(empty.status, 'ok');
  assert.deepEqual(empty.latestReports, []);
  assert.deepEqual(empty.activeDisasters, []);
  assert.equal(requests, 2, 'valid empty results do not launch a fallback');
});

test('HDX datasets are supplemental evidence, not a successful ReliefWeb report query', async (t) => {
  approvedApp(t);
  t.mock.method(globalThis, 'fetch', async (url) => response(String(url).includes('/package_search?')
    ? { success: true, result: { results: [{ name: 'synthetic-crisis', title: 'Synthetic dataset', metadata_modified: recent() }] } }
    : { error: 'not approved' }));
  const data = await reliefweb();
  assert.equal(sourceOutcome('ReliefWeb', data).status, 'partial');
  assert.equal(data.latestReports, null);
  assert.equal(data.activeDisasters, null);
  assert.equal(data.hdxDatasets.length, 1);
  assert.deepEqual(data.coverage, { requested: 2, succeeded: 0, failed: 2 });
  assert.ok(data.gaps.reports && data.gaps.disasters);
  const view = await synthesize({ crucix: {}, sources: { ReliefWeb: data } }, { refreshNews: false });
  assert.deepEqual(view.newsFeed, [], 'datasets must not be published as disaster reports');
});

test('ReliefWeb keeps valid disasters while marking malformed entries and the missing report side', async (t) => {
  approvedApp(t);
  t.mock.method(globalThis, 'fetch', async (url) => response(String(url).includes('/disasters?')
    ? { data: [null, { fields: { name: 'Synthetic flood', country: [{ name: 'Example' }], status: 'ongoing' } }] }
    : { error: 'unavailable' }));
  const data = await reliefweb();
  assert.equal(sourceOutcome('ReliefWeb', data).status, 'partial');
  assert.equal(data.latestReports, null);
  assert.equal(data.activeDisasters.length, 1);
  assert.ok(data.gaps.disasters);
});

test('WHO dashboard distinguishes unknown, true zero and partial counts without fabricated locations', () => {
  const html = readFileSync(new URL('../../dashboard/public/jarvis.html', import.meta.url), 'utf8');
  const helper = html.match(/function whoCountText\(\) \{[\s\S]*?\n\}/)?.[0];
  assert.ok(helper);
  for (const [status, count, expected] of [['error', null, '—'], ['ok', 0, 0], ['partial', 3, '3+'], ['ok', 4, 4]]) {
    assert.equal(vm.runInNewContext(`${helper}; whoCountText()`, { D: { who: [], whoMeta: { status, count } } }), expected);
  }
  assert.doesNotMatch(html, /const whoGeo=/);
});
