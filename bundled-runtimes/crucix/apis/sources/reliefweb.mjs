import { sourceFetch as fetch, sourceSignal } from '../utils/source-request.mjs';
import '../utils/env.mjs';

// ReliefWeb — UN OCHA humanitarian crisis tracking
// Requires approved appname since Nov 2025. Register at https://apidoc.reliefweb.int/parameters#appname
// HDX can supplement missing queries, but datasets are not ReliefWeb reports.

import { safeFetch } from '../utils/fetch.mjs';
import { queryReceipt } from '../utils/source-health.mjs';

const BASE = 'https://api.reliefweb.int/v2';
// Register your own appname at https://apidoc.reliefweb.int/parameters#appname
// and configure RELIEFWEB_APPNAME. Never borrow a default application's approval.

const HDX_BASE = 'https://data.humdata.org/api/3/action';

// POST-based search for reports (ReliefWeb API v2 POST format)
async function rwPost(endpoint, body) {
  const appname = process.env.RELIEFWEB_APPNAME?.trim();
  if (!appname) return { error: '未配置已获批准的 RELIEFWEB_APPNAME', status: 'no_credentials' };
  const url = `${BASE}/${endpoint}?${new URLSearchParams({ appname })}`;
  try {
    const signal = AbortSignal.timeout(15000);
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'Crucix/1.0',
      },
      body: JSON.stringify(body),
      signal,
    });
    if (!res.ok) {
      await res.body?.cancel().catch(() => {});
      return { error: `ReliefWeb HTTP ${res.status}`, httpStatus: res.status };
    }
    return await res.json();
  } catch (e) {
    sourceSignal()?.throwIfAborted();
    return { error: 'ReliefWeb 请求失败或响应格式无效' };
  }
}

// Search recent reports via ReliefWeb API (POST method)
export async function searchReports(opts = {}) {
  const { query = '', limit = 15 } = opts;
  const body = {
    limit,
    fields: {
      include: [
        'title',
        'date.created',
        'country.name',
        'disaster_type.name',
        'url_alias',
        'source.name',
      ],
    },
    sort: ['date.created:desc'],
  };
  if (query) {
    body.query = { value: query };
  }
  return rwPost('reports', body);
}

// Get active disasters via ReliefWeb API (POST method)
export async function getDisasters(opts = {}) {
  const { limit = 15 } = opts;
  const body = {
    limit,
    fields: {
      include: ['name', 'date.created', 'country.name', 'type.name', 'status'],
    },
    filter: {
      field: 'status',
      value: 'current',
    },
    sort: ['date.created:desc'],
  };
  return rwPost('disasters', body);
}

// Fallback: search HDX (Humanitarian Data Exchange) for crisis datasets
async function hdxFallback(limit = 15) {
  const data = await safeFetch(
    `${HDX_BASE}/package_search?q=crisis+OR+disaster+OR+emergency&rows=${limit}&sort=metadata_modified+desc`
  );
  if (!data?.error && data?.success === true && Array.isArray(data?.result?.results)) {
    const valid = data.result.results.filter(pkg => typeof pkg?.title === 'string' && pkg.title.trim()
      && typeof pkg.name === 'string' && pkg.name.trim());
    return { items: valid.map(pkg => ({
      title: pkg.title,
      date: pkg.metadata_modified,
      source: pkg.dataset_source || pkg.organization?.title,
      countries: Array.isArray(pkg.groups) ? pkg.groups.map(g => g?.display_name).filter(Boolean) : [],
      url: `https://data.humdata.org/dataset/${encodeURIComponent(pkg.name)}`,
    })), partial: valid.length !== data.result.results.length };
  }
  return { items: null, partial: false };
}

function collection(result, field) {
  if (result?.error || result?.errors?.length || !Array.isArray(result?.data)) return { items: null, partial: false };
  const items = result.data.filter(row => typeof row?.fields?.[field] === 'string' && row.fields[field].trim());
  return { items: result.data.length && !items.length ? null : items, partial: items.length !== result.data.length };
}

const names = (rows) => Array.isArray(rows) ? rows.map(row => row?.name).filter(name => typeof name === 'string') : [];
function reportUrl(value) {
  try {
    const url = new URL(value, 'https://reliefweb.int');
    return typeof value === 'string' && value && url.origin === 'https://reliefweb.int'
      && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

// Briefing — get latest humanitarian crises
export async function briefing() {
  if (!process.env.RELIEFWEB_APPNAME?.trim()) return {
    source: 'ReliefWeb (UN OCHA)', timestamp: new Date().toISOString(), status: 'no_credentials',
    coverage: { requested: 2, succeeded: 0, failed: 0, skipped: 2 },
    gaps: { configuration: '需要自行申请并配置已获批准的 RELIEFWEB_APPNAME；未发送请求' },
    latestReports: null, activeDisasters: null, hdxDatasets: null,
  };
  const [reports, disasters] = await Promise.all([
    searchReports({ limit: 15 }),
    getDisasters({ limit: 15 }),
  ]);

  const reportRows = collection(reports, 'title');
  const disasterRows = collection(disasters, 'name');
  const succeeded = Number(reportRows.items !== null) + Number(disasterRows.items !== null);
  const queryStatus = {
    reports: queryReceipt(reports, reportRows.items !== null, reportRows.partial),
    disasters: queryReceipt(disasters, disasterRows.items !== null, disasterRows.partial),
  };
  const gaps = {};
  for (const [key, rows] of [['reports', reportRows], ['disasters', disasterRows]]) {
    if (rows.items === null) gaps[key] = '查询失败或响应格式无效，不能判断没有事件';
    else if (rows.partial) gaps[key] = '部分记录无效，已保留有效记录';
  }
  const latestReports = reportRows.items?.map(r => ({
      title: r.fields?.title,
      date: r.fields?.date?.created,
      countries: names(r.fields?.country),
      disasterType: names(r.fields?.disaster_type),
      source: names(r.fields?.source),
      url: reportUrl(r.fields?.url_alias),
    })) ?? null;
  const activeDisasters = disasterRows.items?.map(d => ({
      name: d.fields?.name,
      date: d.fields?.date?.created,
      countries: names(d.fields?.country),
      type: names(d.fields?.type),
      status: d.fields?.status,
    })) ?? null;
  let hdxDatasets = null;
  if (succeeded < 2) {
    const fallback = await hdxFallback(15);
    hdxDatasets = fallback.items;
    if (hdxDatasets === null || fallback.partial) gaps.hdx = '备用数据集不可用或覆盖不完整，不能替代原始报告';
  }

  return {
    source: 'ReliefWeb (UN OCHA)',
    timestamp: new Date().toISOString(),
    status: succeeded === 2 && !Object.keys(gaps).length ? 'ok'
      : succeeded || hdxDatasets?.length ? 'partial' : 'error',
    coverage: { requested: 2, succeeded, failed: 2 - succeeded },
    gaps, queryStatus, latestReports, activeDisasters, hdxDatasets,
    ...(succeeded < 2 ? {
      rwError: 'ReliefWeb 部分或全部查询不可用，见覆盖缺口',
      rwNote: 'ReliefWeb 需要已批准的 RELIEFWEB_APPNAME；HDX 仅为补充数据集，不计入原始报告/灾害查询成功数。',
    } : {}),
  };
}

if (process.argv[1]?.endsWith('reliefweb.mjs')) {
  const data = await briefing();
  console.log(JSON.stringify(data, null, 2));
}
