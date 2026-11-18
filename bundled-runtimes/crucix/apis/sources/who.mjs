// WHO — World Health Organization Global Health Observatory
// No auth required. Disease outbreak monitoring.

import { safeFetch } from '../utils/fetch.mjs';

const GHO_BASE = 'https://ghoapi.azureedge.net/api';
const DON_API = 'https://www.who.int/api/news/diseaseoutbreaknews';

// Get GHO indicator data
export async function getIndicator(code, opts = {}) {
  const { filter = '', top = 20 } = opts;
  let url = `${GHO_BASE}/${code}?$top=${top}&$orderby=TimeDim desc`;
  if (filter) url += `&$filter=${filter}`;
  return safeFetch(url);
}

// Key health indicators
const INDICATORS = {
  MDG_0000000020: 'TB incidence (per 100k)',
  MALARIA_EST_CASES: 'Malaria estimated cases',
  WHOSIS_000001: 'Life expectancy at birth',
  UHC_INDEX_REPORTED: 'UHC Service Coverage Index',
};

// The default page contains old records, not the latest announcements.
// Request the time window at WHO, then validate it locally as well.
async function outbreakResult() {
  const end = new Date();
  const start = new Date(end.getTime() - 30 * 86400000);
  const window = { start: start.toISOString(), end: end.toISOString(), days: 30 };
  const params = new URLSearchParams({
    '$filter': `PublicationDate ge ${window.start} and PublicationDate le ${window.end}`,
    '$orderby': 'PublicationDate desc', '$top': '100',
  });
  const data = await safeFetch(`${DON_API}?${params}`, { retries: 0 });
  const error = 'WHO 公告查询失败或响应格式无效，不能判断近期没有公告';
  if (data?.error || !Array.isArray(data?.value)) return { status: 'error', items: [], window, gaps: { request: error }, error };
  const gaps = {};
  const valid = data.value.filter(item => typeof item?.Title === 'string' && item.Title.trim()
    && typeof item.PublicationDate === 'string' && Number.isFinite(Date.parse(item.PublicationDate)));
  if (valid.length !== data.value.length) gaps.records = '部分公告标题或日期无效，已保留有效记录';
  if (data.value.length && !valid.length) return { status: 'error', items: [], window, gaps, error };
  const recent = valid.filter(item => Date.parse(item.PublicationDate) >= start.getTime() && Date.parse(item.PublicationDate) <= end.getTime());
  if (recent.length !== valid.length) gaps.window = '来源返回了窗口外公告，已排除；窗口覆盖需复核';
  if (data['@odata.nextLink'] || data.value.length >= 100) gaps.pagination = '来源仍可能有后续公告，本次最多读取100条，不代表窗口全量';
  recent.sort((a, b) => Date.parse(b.PublicationDate) - Date.parse(a.PublicationDate));
  const items = recent.map(item => ({
    title: item.Title, date: item.PublicationDate, donId: item.DonId || null,
    url: typeof item.ItemDefaultUrl === 'string' && item.ItemDefaultUrl.startsWith('/') && !item.ItemDefaultUrl.startsWith('//')
      ? `https://www.who.int/emergencies/disease-outbreak-news${item.ItemDefaultUrl}` : null,
    summary: (typeof (item.Summary || item.Overview) === 'string' ? (item.Summary || item.Overview) : '')
      .replace(/<[^>]*>/g, '').slice(0, 300) || null,
  }));
  return { status: Object.keys(gaps).length ? 'partial' : 'ok', items, window, gaps };
}

// Preserve the existing direct caller's array/error contract.
export async function getOutbreakNews() {
  const result = await outbreakResult();
  return result.error ? { error: result.error } : result.items;
}

// Briefing
export async function briefing() {
  const outbreaks = await outbreakResult();

  return {
    source: 'WHO',
    timestamp: new Date().toISOString(),
    status: outbreaks.status,
    window: outbreaks.window,
    gaps: outbreaks.gaps,
    outbreakCount: outbreaks.status === 'ok' || outbreaks.items.length ? outbreaks.items.length : null,
    diseaseOutbreakNews: outbreaks.items.slice(0, 15),
    outbreakError: outbreaks.error || null,
    monitoringCapabilities: [
      'Disease Outbreak News (DONs)',
      'Global health indicators (GHO)',
      'Pandemic early warning signals',
      'Cross-reference with GDELT health event mentions',
    ],
  };
}

if (process.argv[1]?.endsWith('who.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
