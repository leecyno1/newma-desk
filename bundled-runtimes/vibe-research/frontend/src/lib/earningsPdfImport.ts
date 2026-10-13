import { researchApiUrl, type EarningsPdfImport } from './api';
import { blankEarningsWorkbook, calculateVariance, type EarningsMetric, type EarningsSource, type EarningsWorkbook } from './earningsWorkbench';

function discussionSources(document: EarningsPdfImport, selectedIds: string[]): EarningsSource[] {
  const pdfUrl = new URL(researchApiUrl(`/myreports/file/${encodeURIComponent(document.reportId)}?inline=true`), window.location.origin).href;
  const confirmedAt = new Date().toISOString();
  return (document.discussion || []).filter(row=>selectedIds.includes(row.id)).map(passage=>({
    id:`uploaded:${document.reportId}:${passage.id}`, label:`${passage.topics.join(' / ')} · PDF 第 ${passage.page} 页`,
    kind:'filing', url:`${pdfUrl}#page=${passage.page}`, status:'available',
    periodEnd:document.periodEnd || undefined, basis:document.basis, retrievedAt:new Date(document.retrievedAt).toISOString(),
    discussion:{reportId:document.reportId, text:passage.text, topics:passage.topics,
      pdfPage:passage.page, pdfPageCount:document.pageCount, readPages:document.readPages,
      truncated:passage.truncated, confirmedAt, contentOrigin:'pdf-text'},
  }));
}

function assertLinkedReport(workbook: EarningsWorkbook, document: EarningsPdfImport) {
  const linked = workbook.sourceMaterials.some(source => (source.importedReport?.reportId || source.discussion?.reportId || source.capitalNote?.reportId) === document.reportId);
  if (!linked) throw new Error('该 PDF 未关联当前底稿，请重新选择已关联文件');
  if (!document.periodEnd || document.security.market !== workbook.security.market || document.security.symbol !== workbook.security.symbol
    || document.security.currency !== workbook.security.currency || document.periodEnd !== workbook.fiscalPeriod.periodEnd || document.basis !== workbook.fiscalPeriod.basis) {
    throw new Error('财报证券、报告期或币种口径与当前底稿不一致，未补充原文');
  }
}

export function missingPdfDiscussion(workbook: EarningsWorkbook, document: EarningsPdfImport) {
  assertLinkedReport(workbook, document);
  return (document.discussion || []).filter(passage => !workbook.sourceMaterials.some(source =>
    source.discussion?.reportId === document.reportId && source.discussion.pdfPage === passage.page));
}

export const CAPITAL_FACT_IDS = ['capital-cash-funds', 'capital-short-borrowings', 'capital-long-borrowings',
  'capital-bonds-payable', 'capital-current-noncurrent-liabilities', 'capital-lease-liabilities',
  'capital-share-capital', 'capital-customer-deposits'];

export function missingPdfCapital(workbook: EarningsWorkbook, document: EarningsPdfImport) {
  assertLinkedReport(workbook, document);
  return (document.capitalCandidates || []).filter(row => CAPITAL_FACT_IDS.includes(row.id)
    && !workbook.operatingMetrics.some(metric => metric.id === row.id)
    && !workbook.sourceMaterials.some(source => source.id === `uploaded:${document.reportId}:${row.id}`));
}

export function missingPdfCapitalNotes(workbook: EarningsWorkbook, document: EarningsPdfImport) {
  assertLinkedReport(workbook, document);
  return (document.capitalNotes || []).filter(row => !workbook.sourceMaterials.some(source =>
    source.capitalNote?.reportId === document.reportId && source.capitalNote.pdfPage === row.page && source.capitalNote.title === row.title));
}

export function appendPdfCapitalNotes(workbook: EarningsWorkbook, document: EarningsPdfImport, selectedIds: string[]): EarningsWorkbook {
  const rows = missingPdfCapitalNotes(workbook, document).filter(row => selectedIds.includes(row.id));
  if (!rows.length) throw new Error('没有新的资本附注；已采用原文不重复添加');
  if (workbook.sourceMaterials.length + rows.length > 100) throw new Error('底稿来源已达上限，请先整理');
  const confirmedAt = new Date().toISOString();
  const pdfUrl = new URL(researchApiUrl(`/myreports/file/${encodeURIComponent(document.reportId)}?inline=true`), window.location.origin).href;
  const additions: EarningsSource[] = rows.map(row => ({
    id: `uploaded:${document.reportId}:${row.id}`, label: `${row.title} · PDF 第 ${row.page} 页`, kind: 'filing',
    url: `${pdfUrl}#page=${row.page}`, status: 'available', periodEnd: document.periodEnd!, basis: document.basis,
    retrievedAt: new Date(document.retrievedAt).toISOString(),
    capitalNote: {reportId: document.reportId, title: row.title, text: row.text, topics: row.topics,
      pdfPage: row.page, pdfPageCount: document.pageCount, readPages: document.capitalNotesReadPages || [],
      truncated: row.truncated, confirmedAt, contentOrigin: 'pdf-text'},
  }));
  return {...workbook, sourceMaterials: [...workbook.sourceMaterials, ...additions], updatedAt: confirmedAt};
}

export function appendPdfCapital(workbook: EarningsWorkbook, document: EarningsPdfImport, selectedIds: string[]): EarningsWorkbook {
  const rows = missingPdfCapital(workbook, document).filter(row => selectedIds.includes(row.id));
  if (!rows.length) throw new Error('没有新的资本项目；已有项目不会重复添加或覆盖');
  const extracted = workbookFromPdf({...document, candidates: rows}, rows.map(row => row.id));
  if (workbook.operatingMetrics.length + rows.length > 50 || workbook.sourceMaterials.length + rows.length > 100) throw new Error('底稿指标或来源已达上限，请先整理');
  return {...workbook, updatedAt: new Date().toISOString(),
    operatingMetrics: [...workbook.operatingMetrics, ...extracted.operatingMetrics.map(metric => ({...metric,
      note: `${metric.note} 合并报表原始项目，仅供资本核验参考；不是可直接使用的稀释股数、总债务或可归属现金。`}))],
    sourceMaterials: [...workbook.sourceMaterials, ...extracted.sourceMaterials],
  };
}

export function appendPdfDiscussion(workbook: EarningsWorkbook, document: EarningsPdfImport, selectedIds: string[]): EarningsWorkbook {
  const missing = missingPdfDiscussion(workbook, document).filter(row=>selectedIds.includes(row.id));
  if (!missing.length) throw new Error('没有选中新的经营讨论；已采用页不会重复添加或覆盖');
  const additions = discussionSources(document, missing.map(row=>row.id));
  if (workbook.sourceMaterials.length + additions.length > 100) throw new Error('底稿来源超过 100 项，请先整理来源');
  return {...workbook, sourceMaterials:[...workbook.sourceMaterials,...additions], updatedAt:new Date().toISOString()};
}

export function workbookFromPdf(document: EarningsPdfImport, selectedIds: string[], discussionIds: string[] = []): EarningsWorkbook {
  if (!document.periodEnd || !document.security.symbol || !document.security.name) throw new Error('财报身份不完整，不能采用');
  const selected = document.candidates.filter(row => selectedIds.includes(row.id));
  if (!selected.length) throw new Error('请至少选择一个已核对的指标');
  const workbook = blankEarningsWorkbook();
  const confirmedAt = new Date().toISOString();
  const retrievedAt = new Date(document.retrievedAt).toISOString();
  const pdfUrl = new URL(researchApiUrl(`/myreports/file/${encodeURIComponent(document.reportId)}?inline=true`), window.location.origin).href;
  workbook.security = {...document.security};
  workbook.mode = 'reported';
  workbook.fiscalPeriod = {label: `${document.periodEnd.slice(0,4)} 年报`, periodEnd: document.periodEnd, basis: document.basis, reportingTime: 'unknown'};
  for (const row of selected) {
    if (!Number.isFinite(row.value) || !row.excerpt || row.page < 1 || row.page > document.pageCount) throw new Error('候选证据不完整，请重新提取');
    const sourceId = `uploaded:${document.reportId}:${row.id}`;
    workbook.sourceMaterials.push({id: sourceId, label: `${document.name} · 第 ${row.page} 页`, kind: 'filing',
      url: `${pdfUrl}#page=${row.page}`, status: 'available', periodEnd: document.periodEnd, basis: document.basis, retrievedAt,
      importedReport: {reportId: document.reportId, rawValue: row.rawValue, rawUnit: row.rawUnit, columnHeader: row.columnHeader, confirmedAt},
      excerpt: {text: row.excerpt, pdfPage: row.page, pdfPageCount: document.pageCount, pdfUrl, metricId: row.id, reportedValue: row.value, unit: row.unit, contentOrigin: 'pdf-text', association: 'user-linked'},
    });
    const base = workbook.metrics.find(metric => metric.id === row.id);
    const metric: EarningsMetric = calculateVariance({...(base || {id: row.id, category: 'operating', internalEstimate: null, consensus: null, varianceVsConsensus: {amount:null,percent:null,bps:null}}),
      label: row.label, unit: row.unit, reported: row.value, reportedOrigin: 'manual', reportedBasis: document.basis,
      reportedCurrency: document.security.currency, periodEnd: document.periodEnd, sourceIds: [sourceId],
      note: `PDF 文字提取后由用户确认；原值 ${row.rawValue} ${row.rawUnit}，物理页 ${row.page}。不是自动审计。`,
    });
    if (base) workbook.metrics = workbook.metrics.map(item => item.id === row.id ? metric : item);
    else workbook.operatingMetrics.push(metric);
  }
  workbook.sourceMaterials.push(...discussionSources(document,discussionIds));
  workbook.verification = {status:'partial', latestPeriodChecked:false, checkedAt:confirmedAt, primarySourceIds:workbook.sourceMaterials.map(source=>source.id)};
  workbook.gaps = [...document.warnings, '一致预期未提供，不计算 Beat/Miss；缺少的指标保持空白。'];
  return workbook;
}
