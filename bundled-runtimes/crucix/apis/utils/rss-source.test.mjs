import assert from 'node:assert/strict';
import test from 'node:test';
import { parseNewsFeed, fetchNewsSource } from '../../dashboard/rss.mjs';
import { fetchNewsResult, buildNewsFeed, synthesize } from '../../dashboard/inject.mjs';

test('RSS, RDF and Atom decode real feed fields, entities and CDATA', () => {
  const feeds = [
    '<rss><channel><item><title><![CDATA[India & policy]]></title><link>https://example.org/a</link><pubDate>2026-01-01T00:00:00Z</pubDate></item></channel></rss>',
    '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><item><title>India &amp; policy</title><link>https://example.org/a</link></item></rdf:RDF>',
    '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>India &amp; policy</title><link href="https://example.org/a"/><updated>2026-01-01T00:00:00Z</updated></entry></feed>',
  ];
  for (const xml of feeds) {
    const result = parseNewsFeed(xml, 'Synthetic');
    assert.equal(result.status, 'ok');
    assert.equal(result.items[0].title, 'India & policy');
    assert.equal(result.items[0].url, 'https://example.org/a');
  }
  assert.equal(parseNewsFeed(feeds[2], 'Synthetic').items[0].date, null, 'Atom updated is not publication time');
});

test('empty feeds differ from HTML, malformed XML, unsupported formats and invalid records', () => {
  for (const xml of ['<rss><channel/></rss>', '<feed xmlns="http://www.w3.org/2005/Atom"/>']) {
    assert.equal(parseNewsFeed(xml, 'Synthetic').count, 0);
  }
  for (const xml of ['<html>Login</html>', '<rss><channel><item></channel></rss>', '<rss/>', '<rss><channel><item><title/></item></channel></rss>']) {
    const result = parseNewsFeed(xml, 'Synthetic');
    assert.equal(result.status, 'error');
    assert.equal(result.count, null);
  }
  const partial = parseNewsFeed('<rss><channel><item><title>Good</title><pubDate>bad-date</pubDate></item><item/></channel></rss>', 'Synthetic');
  assert.equal(partial.status, 'partial');
  assert.equal(partial.items[0].date, null);
});

test('HTTP errors are not empty feeds and never leak response bodies', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('private rejection body', { status: 403 }));
  const data = await fetchNewsSource('https://example.org/rss', 'Synthetic');
  assert.equal(data.status, 'error');
  assert.equal(data.count, null);
  assert.equal(data.httpStatus, 403);
  assert.equal(data.errorCode, 'RSS_HTTP_ERROR');
  assert.doesNotMatch(JSON.stringify(data), /private rejection/);
});

for (const [code, expected] of [
  ['ECONNREFUSED', 'RSS_CONNECTION_REFUSED'], ['ENOTFOUND', 'RSS_DNS_ERROR'],
  ['EAI_AGAIN', 'RSS_DNS_ERROR'], ['CERT_HAS_EXPIRED', 'RSS_TLS_ERROR'],
  ['ERR_TLS_CERT_ALTNAME_INVALID', 'RSS_TLS_ERROR'], ['UND_ERR_CONNECT_TIMEOUT', 'RSS_TIMEOUT'],
  ['UND_ERR_SOCKET', 'RSS_NETWORK_ERROR'],
]) {
  test(`RSS ${code} keeps a safe distinct failure instead of zero or invalid XML`, async t => {
    let calls = 0;
    t.mock.method(globalThis, 'fetch', async () => {
      calls++;
      throw new TypeError('synthetic-private-network-detail', { cause: { code } });
    });
    const result = await fetchNewsSource('https://example.org/rss', 'Synthetic');
    assert.equal(result.errorCode, expected);
    assert.equal(result.status, 'error');
    assert.equal(result.count, null);
    assert.equal(calls, 1, 'Diagnostics must not trigger retries or alternate sources');
    assert.doesNotMatch(JSON.stringify(result), /synthetic-private-network-detail/);
  });
}

test('RSS grouping and ticker preserve same-headline reports from distinct URLs and publishers', async t => {
  const title = 'A long policy and international economic outlook report '.repeat(3);
  const date = new Date(Date.now() - 60_000).toISOString();
  const entry = (url, headline = title) => `<item><title>${headline}</title><link>${url}</link><pubDate>${date}</pubDate></item>`;
  t.mock.method(globalThis, 'fetch', async url => new Response(`<rss><channel>${String(url).endsWith('/a')
    ? entry('https://example.org/report-1') + entry('https://example.org/report-2') + entry('https://example.org/report-1')
    : entry('https://example.org/report-1')}</channel></rss>`));
  const result = await fetchNewsResult([['https://example.org/a', 'Source A'], ['https://example.org/b', 'Source B']]);
  assert.equal(result.news.length, 3);
  assert.equal(result.meta.selection, 'regional-reserve-30d-url-v2');
  assert.equal(result.news[0].title, title.trim());
  const ticker = buildNewsFeed(result.news, {}, [], []);
  assert.equal(ticker.length, 3);
  assert.deepEqual(ticker.map(row => [row.source, row.url]), [
    ['Source A', 'https://example.org/report-1'], ['Source A', 'https://example.org/report-2'], ['Source B', 'https://example.org/report-1'],
  ]);
});

test('RSS without article links compares full headlines before bounded display', async t => {
  const prefix = 'A report with a shared headline prefix '.repeat(5);
  t.mock.method(globalThis, 'fetch', async () => new Response(`<rss><channel>
    <item><title>${prefix}One</title></item><item><title>${prefix}Two</title></item>
    <item><title>${prefix}One</title></item></channel></rss>`));
  const result = await fetchNewsResult([['https://example.org/a', 'Source A']]);
  assert.equal(result.news.length, 2);
  assert.ok(result.news[0].title.endsWith('One'));
  assert.ok(result.news[1].title.endsWith('Two'));
});

test('aggregate retains healthy, empty and failed coverage without inventing full success', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => new Response(String(url).includes('good')
    ? '<rss><channel><item><title>India growth outlook</title></item></channel></rss>'
    : String(url).includes('empty') ? '<rss><channel/></rss>' : '<html>Login</html>'));
  const data = await fetchNewsResult([['https://example.org/good', 'Good'], ['https://example.org/empty', 'Empty'], ['https://example.org/bad', 'Bad']]);
  assert.equal(data.meta.status, 'partial');
  assert.deepEqual(data.meta.coverage, { requested: 3, succeeded: 2, partial: 0, failed: 1 });
  assert.equal(data.news.length, 1);
  assert.deepEqual(data.meta.items.map(item => item.count), [1, 0, null]);
  const view = await synthesize({ crucix: {}, sources: {} });
  assert.equal(view.newsMeta.status, 'error', 'all default mocked feeds are invalid HTML');
  assert.equal(view.newsMeta.coverage.failed, 19);
  assert.deepEqual(view.news, []);
});

test('manual snapshot restoration does not claim RSS was scanned', async (t) => {
  let requests = 0;
  t.mock.method(globalThis, 'fetch', async () => { requests++; throw new Error('Unexpected'); });
  const view = await synthesize({ crucix: {}, sources: {} }, { refreshNews: false });
  assert.equal(requests, 0);
  assert.equal(view.newsMeta.status, 'unknown');
  assert.equal(view.newsMeta.coverage.requested, 0);
  assert.equal(view.newsMeta.asOf, null);
});

