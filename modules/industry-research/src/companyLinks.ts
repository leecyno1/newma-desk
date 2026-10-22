import type { CompanyWorkbook } from './company';
import type { Snapshot } from './research';

export interface CompanyLink {
  industry: string; workbookId: string; reason: string; reviewedAt: string;
  security: CompanyWorkbook['security']; fiscalPeriod: CompanyWorkbook['fiscalPeriod'];
  workbookUpdatedAt: string; sourceRevision: number;
  report: {url: string; periodEnd: string};
}
export interface CompanyLinks {schemaVersion: 1; entries: CompanyLink[]}
export const emptyLinks = (): CompanyLinks => ({schemaVersion: 1, entries: []});
const linkKey = (link: CompanyLink) => JSON.stringify([link.industry, link.workbookId]);
export function readLinks(value: unknown): CompanyLinks {
  const book = value as CompanyLinks | null;
  const text = (x: unknown) => typeof x === 'string' && x.trim().length > 0;
  if (!book || book.schemaVersion !== 1 || !Array.isArray(book.entries) || book.entries.length > 50
    || !book.entries.every(e => e && [e.industry,e.workbookId,e.reason,e.reviewedAt,e.workbookUpdatedAt].every(text)
      && e.reason.length <= 800 && Number.isFinite(Date.parse(e.reviewedAt)) && Number.isInteger(e.sourceRevision) && e.sourceRevision >= 0
      && e.security && [e.security.name,e.security.symbol,e.security.market,e.security.currency].every(text)
      && e.fiscalPeriod && text(e.fiscalPeriod.label) && e.report && [e.report.url,e.report.periodEnd].every(text))
    || new Set(book.entries.map(linkKey)).size !== book.entries.length) throw new Error('关联记录格式不兼容，已停止写入。');
  return book;
}
export function saveLink(book: CompanyLinks, entry: CompanyLink): CompanyLinks {
  const key = linkKey(entry), exists = book.entries.some(row => linkKey(row) === key);
  return readLinks({...book, entries: exists ? book.entries.map(row => linkKey(row) === key ? entry : row) : [...book.entries,entry]});
}
export function linkState(link: CompanyLink, workbooks: CompanyWorkbook[] | undefined, report: Snapshot | null) {
  if (!workbooks) return '待读取当前底稿';
  const book = workbooks.find(row => row.id === link.workbookId);
  if (!book) return '底稿已删除或不在当前投影';
  if (book.updatedAt !== link.workbookUpdatedAt || book.mode !== 'reported'
    || (['name','symbol','market','currency'] as const).some(key=>book.security[key]!==link.security[key])
    || (['label','periodEnd','basis'] as const).some(key=>book.fiscalPeriod[key]!==link.fiscalPeriod[key])) return '底稿已变更，需重新核验';
  if (!report || report.sourceUrl !== link.report.url || report.periodEnd !== link.report.periodEnd) return '行业报告已切换，需重新核验';
  return '版本记录一致，载入后仍须确认';
}
