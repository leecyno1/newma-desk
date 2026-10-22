import type { Snapshot } from "./research";

export const IMPACTS = {pending: "待核验", strengthened: "支持增强", weakened: "证据削弱", invalidated: "条件已触发"};
export type Impact = keyof typeof IMPACTS;
export interface EvidenceRef {url: string; periodEnd: string; publishedAt: string; fetchedAt: string}
export interface Review {at: string; note: string; impact: Impact; nextReview: string; source: EvidenceRef}
export interface ResearchEntry {
  id: string; industry: string; statement: string; supporting: string; counter: string; invalidation: string;
  nextReview: string; createdAt: string; source: EvidenceRef; reviews: Review[]; archivedAt?: string;
}
export interface TrackingBook {schemaVersion: 1; entries: ResearchEntry[]}
export const emptyBook = (): TrackingBook => ({schemaVersion: 1, entries: []});
export const evidenceRef = (report: Snapshot): EvidenceRef => ({url: report.sourceUrl, periodEnd: report.periodEnd, publishedAt: report.publishedAt, fetchedAt: report.fetchedAt});
export function localDay(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export function validDay(day: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(day) && !Number.isNaN(Date.parse(day)) && new Date(day).toISOString().slice(0, 10) === day;
}
export function reviewState(entry: ResearchEntry, current: EvidenceRef, today = localDay()) {
  const latest = entry.reviews.at(-1);
  const source = latest?.source ?? entry.source;
  return {impact: latest?.impact ?? "pending", due: (latest?.nextReview ?? entry.nextReview) <= today,
    reportChanged: source.url !== current.url || source.periodEnd !== current.periodEnd,
    recollected: source.url === current.url && source.fetchedAt !== current.fetchedAt};
}
export function addReview(book: TrackingBook, id: string, review: Review): TrackingBook {
  const entry = book.entries.find(row => row.id === id);
  if (!entry || entry.reviews.length >= 20) throw new Error("记录不存在或已达20次复核上限，请导出后新建跟踪。");
  if (entry.archivedAt) throw new Error("请先恢复归档记录再复核。");
  if (!review.note.trim() || !validDay(review.nextReview)) throw new Error("请填写复核证据与有效日期。");
  return {...book, entries: book.entries.map(row => row.id === id ? {...row, reviews: [...row.reviews, review]} : row)};
}
export type TrackingFilter = "active" | "due" | "attention" | "archived";
export function trackingOverview(book: TrackingBook, filter: TrackingFilter = "active", today = localDay()) {
  const rows = book.entries.map(entry => {
    const last = entry.reviews.at(-1);
    const nextReview = last?.nextReview ?? entry.nextReview;
    const impact = last?.impact ?? "pending";
    return {id: entry.id, industry: entry.industry, statement: entry.statement, nextReview, impact,
      due: !entry.archivedAt && nextReview <= today, archivedAt: entry.archivedAt ?? null,
      attention: !entry.archivedAt && (impact === "weakened" || impact === "invalidated"), periodEnd: (last?.source ?? entry.source).periodEnd};
  });
  return {counts: {active: rows.filter(r => !r.archivedAt).length, due: rows.filter(r => r.due).length,
    attention: rows.filter(r => r.attention).length, archived: rows.filter(r => r.archivedAt).length},
    rows: rows.filter(r => filter === "archived" ? !!r.archivedAt : filter === "due" ? r.due : filter === "attention" ? r.attention : !r.archivedAt)
      .sort((a, b) => a.nextReview.localeCompare(b.nextReview) || a.id.localeCompare(b.id))};
}
export function archiveEntry(book: TrackingBook, id: string, archivedAt: string | null): TrackingBook {
  if (!book.entries.some(row => row.id === id)) throw new Error("记录已不存在，请重新读取。");
  return {...book, entries: book.entries.map(row => row.id === id ? {...row, archivedAt: archivedAt ?? undefined} : row)};
}
export function readBook(value: unknown): TrackingBook {
  const book = value as TrackingBook | null;
  const text = (x: unknown) => typeof x === "string";
  const source = (x: EvidenceRef) => x && [x.url, x.periodEnd, x.publishedAt, x.fetchedAt].every(text) && /^https?:\/\//.test(x.url);
  if (!book || book.schemaVersion !== 1 || !Array.isArray(book.entries) || book.entries.length > 30
    || !book.entries.every(e => e && [e.id, e.industry, e.statement, e.supporting, e.counter, e.invalidation, e.createdAt].every(text)
      && (e.archivedAt === undefined || text(e.archivedAt) && Number.isFinite(Date.parse(e.archivedAt)))
      && validDay(e.nextReview) && source(e.source) && Array.isArray(e.reviews) && e.reviews.length <= 20
      && e.reviews.every(r => r && text(r.at) && text(r.note) && Object.hasOwn(IMPACTS, r.impact) && validDay(r.nextReview) && source(r.source)))
    || new Set(book.entries.map(e => e.id)).size !== book.entries.length) throw new Error("跟踪记录格式不兼容，已停止写入。");
  return book;
}
