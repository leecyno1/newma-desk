// OFAC — US Treasury Office of Foreign Assets Control Sanctions
// No auth required. Monitors the Specially Designated Nationals (SDN) list
// and consolidated sanctions list for changes.

import { safeFetch } from '../utils/fetch.mjs';

const EXPORTS_BASE = 'https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports';

// SDN list endpoints
const SDN_XML_URL = `${EXPORTS_BASE}/SDN.XML`;
const SDN_ADVANCED_URL = `${EXPORTS_BASE}/SDN_ADVANCED.XML`;
const CONS_ADVANCED_URL = `${EXPORTS_BASE}/CONS_ADVANCED.XML`;

// Parse basic info from SDN XML (publish date, entry count)
function parseSDNMetadata(xml) {
  if (!xml || xml.error) return { error: xml?.error || 'No data returned' };

  const raw = xml.rawText || '';

  // Extract publish date
  const publishDate = raw.match(/<Publish_Date>(.*?)<\/Publish_Date>/)?.[1]
    || raw.match(/<publish_date>(.*?)<\/publish_date>/i)?.[1]
    || null;

  // Count SDN entries
  const entryMatches = raw.match(/<sdnEntry>/gi);
  const entryCount = entryMatches ? entryMatches.length : null;

  // Extract record count if present
  const recordCount = raw.match(/<Record_Count>(.*?)<\/Record_Count>/)?.[1]
    || raw.match(/<records_count>(.*?)<\/records_count>/i)?.[1]
    || null;

  return {
    publishDate,
    entryCount,
    recordCount: recordCount ? parseInt(recordCount, 10) : null,
    hasData: raw.length > 0,
    dataSize: raw.length,
  };
}

// Fetch SDN list metadata (smaller initial chunk via timeout)
export async function getSDNMetadata() {
  // The full SDN XML is large; safeFetch will get the first 500 chars
  // which should include the header/publish date
  const data = await safeFetch(SDN_XML_URL, { timeout: 20000 });
  return parseSDNMetadata(data);
}

// Fetch advanced SDN data (includes more structured info)
export async function getSDNAdvanced() {
  const data = await safeFetch(SDN_ADVANCED_URL, { timeout: 20000 });
  return parseSDNMetadata(data);
}

// Fetch consolidated list metadata
export async function getConsolidatedMetadata() {
  const data = await safeFetch(CONS_ADVANCED_URL, { timeout: 20000 });
  return parseSDNMetadata(data);
}

// Parse recent SDN entries from XML snippet
function parseRecentEntries(xml) {
  if (!xml || xml.error) return [];

  const raw = xml.rawText || '';
  const entries = [];
  const entryRegex = /<sdnEntry>([\s\S]*?)<\/sdnEntry>/gi;
  let match;
  let count = 0;

  while ((match = entryRegex.exec(raw)) !== null && count < 20) {
    const content = match[1];
    const uid = content.match(/<uid>(.*?)<\/uid>/i)?.[1];
    const lastName = content.match(/<lastName>(.*?)<\/lastName>/i)?.[1];
    const firstName = content.match(/<firstName>(.*?)<\/firstName>/i)?.[1];
    const sdnType = content.match(/<sdnType>(.*?)<\/sdnType>/i)?.[1];

    // Extract programs
    const programs = [];
    const progRegex = /<program>(.*?)<\/program>/gi;
    let progMatch;
    while ((progMatch = progRegex.exec(content)) !== null) {
      programs.push(progMatch[1]);
    }

    if (uid || lastName) {
      entries.push({
        uid,
        name: [firstName, lastName].filter(Boolean).join(' '),
        type: sdnType,
        programs,
      });
      count++;
    }
  }

  return entries;
}

// Briefing — report on sanctions list status and metadata
export async function briefing() {
  const [sdnMeta, advancedMeta] = await Promise.all([
    getSDNMetadata(),
    getSDNAdvanced(),
  ]);

  // Try to extract any entries visible in the advanced data
  const sampleEntries = parseRecentEntries(
    await safeFetch(SDN_ADVANCED_URL, { timeout: 25000 })
  );

  return {
    source: 'OFAC Sanctions',
    timestamp: new Date().toISOString(),
    lastUpdated: sdnMeta.publishDate || advancedMeta.publishDate || 'unknown',
    sdnList: {
      publishDate: sdnMeta.publishDate,
      entryCount: sdnMeta.entryCount,
      recordCount: sdnMeta.recordCount,
      dataAvailable: sdnMeta.hasData,
    },
    advancedList: {
      publishDate: advancedMeta.publishDate,
      entryCount: advancedMeta.entryCount,
      recordCount: advancedMeta.recordCount,
      dataAvailable: advancedMeta.hasData,
    },
    sampleEntries: sampleEntries.slice(0, 10),
    endpoints: {
      sdnXml: SDN_XML_URL,
      sdnAdvanced: SDN_ADVANCED_URL,
      consolidatedAdvanced: CONS_ADVANCED_URL,
    },
  };
}

// Run standalone
if (process.argv[1]?.endsWith('ofac.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
