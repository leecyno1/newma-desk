import assert from 'node:assert/strict';
import test from 'node:test';
import { briefing, getSDNMetadata, getSDNAdvanced, getConsolidatedMetadata } from '../sources/ofac.mjs';
import { sourceHealth, sourceOutcome } from './source-health.mjs';
import { withSourceDeadline } from './source-request.mjs';
import { synthesize } from '../../dashboard/inject.mjs';

const namespace = 'https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML';
const row = (id = 1) => `<sdnEntry><uid>${id}</uid><firstName>测试</firstName><lastName>A &amp; B</lastName>
  <sdnType>Entity</sdnType><programList><program>TEST</program></programList>
  <akaList><aka><uid>999</uid><lastName>Not the primary name</lastName></aka></akaList></sdnEntry>`;
const list = (rows = [row()], count = rows.length, date = '11/04/2026') =>
  `<?xml version="1.0"?><sdnList xmlns="${namespace}"><publshInformation>
  <Publish_Date>${date}</Publish_Date><Record_Count>${count}</Record_Count></publshInformation>
  <!--${'padding'.repeat(100)}-->${rows.join('')}</sdnList>`;

function mockXml(t, xml) {
  return t.mock.method(globalThis, 'fetch', async () => new Response(xml, { headers: { 'Content-Type': 'text/xml' } }));
}

test('one complete SDN stream supplies metadata and bounded file-order samples, not recent additions', async t => {
  const bytes = new TextEncoder().encode(list(Array.from({ length: 12 }, (_, i) => row(i + 1))));
  const requests = [];
  t.mock.method(globalThis, 'fetch', async url => {
    requests.push(String(url));
    let offset = 0;
    return new Response(new ReadableStream({ pull(controller) {
      if (offset >= bytes.length) return controller.close();
      controller.enqueue(bytes.slice(offset, offset += 31)); // Splits XML tags and UTF-8 characters.
    } }));
  });
  const data = await briefing();
  assert.deepEqual(requests, ['https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML']);
  assert.equal(data.status, 'ok');
  assert.equal(data.lastUpdated, '2026-11-04');
  assert.equal(data.sdnList.entryCount, 12);
  assert.equal(data.sdnList.recordCount, 12);
  assert.equal(data.sdnList.complete, true);
  assert.equal(data.sdnList.dataSize, bytes.length);
  assert.equal(data.sampleEntries.length, 10);
  assert.equal(data.sampleEntries[0].name, '测试 A & B');
  assert.equal(data.sampleEntries[0].uid, '1');
  assert.deepEqual(data.sampleEntries[0].programs, ['TEST']);
  assert.equal(data.sampleBasis, 'first-in-file-not-recent');
  assert.equal(data.advancedList.status, 'not_requested');
  assert.deepEqual(data.coverage, { requested: 1, succeeded: 1, partial: 0, failed: 0 });
  assert.match(data.note, /非.*合规筛查/);
});

test('complete empty lists retain true zero, unlike unavailable lists', async t => {
  mockXml(t, list([]));
  const data = await briefing();
  assert.equal(data.status, 'ok');
  assert.equal(data.sdnList.entryCount, 0);
  assert.equal(data.sdnList.recordCount, 0);
  assert.deepEqual(data.sampleEntries, []);
});

test('record-count disagreement and missing publication evidence remain partial', async t => {
  const mock = mockXml(t, list([row()], 2));
  const mismatch = await briefing();
  assert.equal(mismatch.status, 'partial');
  assert.equal(mismatch.sdnList.entryCount, 1);
  assert.equal(mismatch.sdnList.recordCount, 2);
  assert.equal(mismatch.sdnList.complete, false);
  assert.match(mismatch.sdnList.reason, /数量/);
  mock.mock.mockImplementation(async () => new Response(`<sdnList xmlns="${namespace}">${row()}</sdnList>`));
  const missing = await briefing();
  assert.equal(missing.status, 'partial');
  assert.equal(missing.lastUpdated, null);
  assert.equal(missing.sdnList.recordCount, null);
});

test('HTML, truncated XML and malformed records are not a healthy or empty sanctions list', async t => {
  const mock = mockXml(t, '');
  for (const xml of ['<html>Access denied</html>', list().slice(0, 700),
    '<sdnList/>', list(['<sdnEntry><uid>1</uid></sdnEntry>']),
    '<!DOCTYPE sdnList [<!ENTITY x "unexpected">]>' + list(),
    list().replace('11/04/2026', '02/30/2026')]) {
    mock.mock.mockImplementation(async () => new Response(xml));
    const data = await briefing();
    assert.notEqual(data.status, 'ok');
    if (data.status === 'error') {
      assert.equal(data.sdnList.entryCount, null);
      assert.equal(data.sdnList.dataAvailable, false);
      assert.equal(data.sampleEntries, null);
    } else assert.equal(data.lastUpdated, null);
  }
});

test('an HTTP rejection is reported once and does not expose the response body', async t => {
  const mock = t.mock.method(globalThis, 'fetch', async () => new Response('private rejection details', { status: 403 }));
  const data = await briefing();
  assert.equal(mock.mock.callCount(), 1);
  assert.equal(data.status, 'error');
  assert.equal(data.sdnList.httpStatus, 403);
  assert.equal(data.lastUpdated, null);
  assert.equal(data.sdnList.entryCount, null);
  assert.match(sourceOutcome('OFAC', data).reason, /403/);
  assert.doesNotMatch(JSON.stringify(data), /private rejection/);
});

test('exported advanced helpers read their own schema instead of counting classic SDN elements', async t => {
  const paths = [];
  t.mock.method(globalThis, 'fetch', async url => {
    paths.push(new URL(url).pathname);
    return new Response(`<Sanctions xmlns="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADVANCED_XML" Version="3">
      <DateOfIssue><Year>2026</Year><Month>11</Month><Day>4</Day></DateOfIssue>
      <DistinctParties><DistinctParty FixedRef="1"/><DistinctParty FixedRef="2"/></DistinctParties></Sanctions>`);
  });
  for (const result of [await getSDNAdvanced(), await getConsolidatedMetadata()]) {
    assert.equal(result.status, 'ok');
    assert.equal(result.publishDate, '2026-11-04');
    assert.equal(result.entryCount, 2);
    assert.equal(result.recordCount, null, 'advanced format has no declared classic Record_Count');
    assert.equal(result.countBasis, 'distinct-parties');
  }
  assert.ok(paths[0].endsWith('/SDN_ADVANCED.XML'));
  assert.ok(paths[1].endsWith('/CONS_ADVANCED.XML'));
});

test('the source deadline cancels a stalled body without another request', async t => {
  let cancelled = false;
  const mock = t.mock.method(globalThis, 'fetch', async (_url, { signal }) => new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('<sdnList>'));
      signal.addEventListener('abort', () => { cancelled = true; controller.error(signal.reason); }, { once: true });
    },
  })));
  await assert.rejects(withSourceDeadline('OFAC', getSDNMetadata, 30), /timed out/);
  assert.equal(cancelled, true);
  assert.equal(mock.mock.callCount(), 1);
});

test('legacy false success is unknown; current failed/partial evidence overrides old timing', async t => {
  const old = sourceHealth({ sources: { OFAC: { sdnList: { dataAvailable: true, entryCount: 1 } } },
    timing: { OFAC: { status: 'ok', reason: '采集完成' } } });
  assert.equal(old.health[0].status, 'unknown');
  const mock = mockXml(t, list([row()], 5));
  const data = await briefing();
  const current = sourceHealth({ sources: { OFAC: data }, timing: { OFAC: { status: 'ok', reason: '采集完成' } } });
  assert.equal(current.health[0].status, 'partial');
  assert.equal(current.counts.sourcesOk, 0);
  assert.match(current.health[0].reason, /完整|数量/);
  mock.mock.mockImplementation(async () => new Response('denied', { status: 403 }));
  assert.equal(sourceHealth({ sources: { OFAC: await briefing() } }).counts.sourcesFailed, 1);
});

test('OFAC failures survive dashboard synthesis rather than becoming a healthy zero', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('', { status: 403 }));
  const data = await briefing();
  const output = await synthesize({ crucix: { timestamp: data.timestamp }, sources: { OFAC: data },
    timing: { OFAC: { status: 'ok', reason: 'old success' } } }, { refreshNews: false });
  assert.equal(output.health.find(row => row.n === 'OFAC').status, 'error');
  assert.match(output.health.find(row => row.n === 'OFAC').reason, /403/);
  assert.equal(output.meta.sourcesOk, 0);
  assert.equal(output.meta.sourcesFailed, 1);
  assert.equal(output.ofac.status, 'error');
  assert.equal(output.ofac.collectedAt, data.timestamp);
  assert.equal(output.ofac.sdnList.entryCount, null);
});

test('synthesis retains only SDN metadata, not file-order names or an invented designation event', async t => {
  mockXml(t, list([row()], 1));
  const data = await briefing();
  const output = await synthesize({ crucix: {}, sources: { OFAC: data } }, { refreshNews: false });
  assert.equal(output.ofac.status, 'ok');
  assert.equal(output.ofac.sdnList.entryCount, 1);
  assert.equal(output.ofac.sdnList.publishDate, data.lastUpdated);
  assert.equal(output.ofac.sdnList.countBasis, 'sdn-entries');
  assert.equal(output.ofac.sampleEntries, undefined);
  assert.equal(output.ofac.advancedList, undefined);
  const absent = await synthesize({ crucix: {}, sources: {} }, { refreshNews: false });
  assert.equal(absent.ofac, null);
  const legacy = await synthesize({ crucix: {}, sources: { OFAC: { sdnList: { entryCount: 1 } } } }, { refreshNews: false });
  assert.equal(legacy.ofac.status, 'unknown');
});
