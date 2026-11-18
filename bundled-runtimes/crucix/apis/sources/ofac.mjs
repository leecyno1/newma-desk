// OFAC public list metadata. File-order examples are not recent designations or screening.
import { SaxesParser } from 'saxes';
import { sourceFetch, sourceSignal } from '../utils/source-request.mjs';

const EXPORTS_BASE = 'https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports';
const SDN_XML_URL = `${EXPORTS_BASE}/SDN.XML`;
const SDN_ADVANCED_URL = `${EXPORTS_BASE}/SDN_ADVANCED.XML`;
const CONS_ADVANCED_URL = `${EXPORTS_BASE}/CONS_ADVANCED.XML`;
const SAMPLE_LIMIT = 10;

function publicationDate(value) {
  const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(value);
  const iso = match ? `${match[3]}-${match[1].padStart(2, '0')}-${match[2].padStart(2, '0')}` : value;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null;
  const time = Date.parse(`${iso}T00:00:00Z`);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === iso
    && time <= Date.now() ? iso : null;
}

function listParser(advanced) {
  const parser = new SaxesParser({ xmlns: true });
  const stack = [];
  const samples = [];
  const metadata = {};
  let root = null, collection = false, entry = null, field = null, entryCount = 0;
  const invalid = () => { throw new Error('Invalid sanctions XML'); };
  parser.on('error', invalid);
  parser.on('doctype', invalid);
  parser.on('opentag', tag => {
    const name = tag.local;
    const parent = stack.at(-1);
    stack.push(name);
    if (stack.length === 1) {
      root = name;
      if (root !== (advanced ? 'Sanctions' : 'sdnList')) invalid();
    }
    if (advanced && stack.length === 2 && name === 'DistinctParties') collection = true;
    if (advanced && stack.length === 3 && parent === 'DistinctParties' && name === 'DistinctParty') entryCount++;
    if (!advanced && stack.length === 2 && name === 'sdnEntry') {
      entry = { uid: '', firstName: '', lastName: '', type: '', programs: [] };
      collection = true;
    }
    let key;
    if (!advanced && stack.length === 3 && ['publshInformation', 'publishInformation'].includes(parent)
        && ['Publish_Date', 'Record_Count'].includes(name)) key = name;
    if (advanced && stack.length === 3 && parent === 'DateOfIssue' && ['Year', 'Month', 'Day'].includes(name)) key = name;
    if (key) field = { depth: stack.length, key, target: metadata, text: '' };
    else if (entry && stack.length === 3 && parent === 'sdnEntry'
        && ['uid', 'firstName', 'lastName', 'sdnType'].includes(name)) {
      field = { depth: stack.length, key: name === 'sdnType' ? 'type' : name, target: entry, text: '' };
    } else if (entry && stack.length === 4 && parent === 'programList' && name === 'program') {
      field = { depth: stack.length, key: 'program', target: entry, text: '' };
    }
  });
  const append = value => { if (field) field.text += value; };
  parser.on('text', append);
  parser.on('cdata', append);
  parser.on('closetag', () => {
    if (field && field.depth === stack.length) {
      if (field.key === 'program') field.target.programs.push(field.text.trim());
      else field.target[field.key] = field.text.trim();
      field = null;
    }
    if (entry && stack.length === 2 && stack.at(-1) === 'sdnEntry') {
      if (!/^\d+$/.test(entry.uid) || !entry.lastName || !entry.type) invalid();
      entryCount++;
      if (samples.length < SAMPLE_LIMIT) samples.push({ uid: entry.uid,
        name: [entry.firstName, entry.lastName].filter(Boolean).join(' '), type: entry.type,
        programs: entry.programs });
      entry = null;
    }
    stack.pop();
  });
  return { parser, finish() {
    parser.close(); // A header or truncated body is never a complete list.
    const rawCount = metadata.Record_Count;
    const recordCount = /^\d+$/.test(rawCount || '') && Number.isSafeInteger(Number(rawCount)) ? Number(rawCount) : null;
    if (!root || (!collection && (advanced || recordCount === null))) invalid();
    const rawDate = advanced ? [metadata.Year, metadata.Month?.padStart(2, '0'), metadata.Day?.padStart(2, '0')].join('-')
      : metadata.Publish_Date || '';
    const publishDate = publicationDate(rawDate);
    const gaps = [];
    if (!publishDate) gaps.push('名单发布日期缺失或无效');
    if (!advanced && recordCount === null) gaps.push('缺少声明记录数量');
    if (!advanced && recordCount !== null && recordCount !== entryCount) gaps.push('解析数量与声明数量不一致');
    return { status: gaps.length ? 'partial' : 'ok', reason: gaps.join('；') || '完整读取名单',
      publishDate, entryCount, recordCount, hasData: true, complete: !gaps.length,
      countBasis: advanced ? 'distinct-parties' : 'sdn-entries', sampleEntries: advanced ? null : samples };
  } };
}

const unavailable = (errorCode, reason, httpStatus = null) => ({ status: 'error', errorCode, reason, httpStatus,
  publishDate: null, entryCount: null, recordCount: null, hasData: false, complete: false,
  dataSize: null, sampleEntries: null });

async function fetchList(url, advanced = false) {
  const caller = sourceSignal();
  caller?.throwIfAborted();
  const timeout = AbortSignal.timeout(25000);
  const signal = sourceSignal(timeout);
  let response;
  try {
    response = await sourceFetch(url, { signal, headers: { 'User-Agent': 'Crucix/1.0', Accept: 'application/xml, text/xml' } });
    if (!response.ok) {
      await response.body?.cancel().catch(() => {});
      return unavailable('HTTP_ERROR', '名单请求失败', response.status);
    }
    const parsed = listParser(advanced);
    const decoder = new TextDecoder('utf-8', { fatal: true });
    let dataSize = 0;
    // Keep only metadata and ten examples; never buffer the full large XML document.
    for await (const chunk of response.body) {
      signal.throwIfAborted();
      dataSize += chunk.byteLength;
      if (dataSize > 128 * 1024 * 1024) return unavailable('RESPONSE_TOO_LARGE', '名单文件超过解析上限');
      parsed.parser.write(decoder.decode(chunk, { stream: true }));
    }
    signal.throwIfAborted();
    parsed.parser.write(decoder.decode());
    return { ...parsed.finish(), dataSize };
  } catch {
    caller?.throwIfAborted();
    return unavailable(timeout.aborted ? 'TIMEOUT' : 'INVALID_RESPONSE', timeout.aborted
      ? '名单读取超时' : '名单连接失败或 XML 不完整/无效');
  } finally {
    if (response?.body && !response.body.locked) await response.body.cancel().catch(() => {});
  }
}

export async function getSDNMetadata() { return fetchList(SDN_XML_URL); }
export async function getSDNAdvanced() { return fetchList(SDN_ADVANCED_URL, true); }
export async function getConsolidatedMetadata() { return fetchList(CONS_ADVANCED_URL, true); }

export async function briefing() {
  // OFAC states classic/advanced editions contain the same core SDN list.
  // One classic download supplies metadata and examples; no duplicate advanced fetches.
  const { sampleEntries, hasData, ...metadata } = await getSDNMetadata();
  return {
    source: 'OFAC Sanctions', timestamp: new Date().toISOString(), status: metadata.status,
    lastUpdated: metadata.publishDate,
    sdnList: { ...metadata, dataAvailable: hasData },
    advancedList: { status: 'not_requested', publishDate: null, entryCount: null, recordCount: null, dataAvailable: false },
    sampleEntries, sampleBasis: 'first-in-file-not-recent',
    coverage: { requested: 1, succeeded: metadata.status === 'ok' ? 1 : 0,
      partial: metadata.status === 'partial' ? 1 : 0, failed: metadata.status === 'error' ? 1 : 0 },
    note: '仅美国 OFAC SDN 名单元数据和文件顺序前十条；不是最新新增、全世界制裁总量，非合规筛查或风险评级；未覆盖非 SDN 名单。',
    endpoints: { sdnXml: SDN_XML_URL, sdnAdvanced: SDN_ADVANCED_URL, consolidatedAdvanced: CONS_ADVANCED_URL },
  };
}

if (process.argv[1]?.endsWith('ofac.mjs')) console.log(JSON.stringify(await briefing(), null, 2));
