import { describe, expect, it } from "vitest";
import { addReview, archiveEntry, emptyBook, readBook, reviewState, trackingOverview, validDay, type ResearchEntry } from "./tracking";
const source = {url: "https://www.stats.gov.cn/report", periodEnd: "2026-08-31", publishedAt: "2026-09-28", fetchedAt: "2026-10-18T01:00:00Z"};
const entry: ResearchEntry = {id: "test", industry: "测试行业", statement: "合成假设", supporting: "测试支持", counter: "测试反证", invalidation: "测试条件", nextReview: "2026-10-20", createdAt: "2026-10-18T01:00:00Z", source, reviews: []};
describe("行业研究跟踪", () => {
  it("跨行业队列只计未归档项，到期包含当日并按日期排序", () => {
    const book = {schemaVersion: 1 as const, entries: [entry, {...entry, id: "other", industry: "另一行业", nextReview: "2026-10-19"}, {...entry, id: "closed", archivedAt: "2026-10-19T01:00:00Z"}]};
    expect(trackingOverview(book, "due", "2026-10-20").rows.map(r => r.id)).toEqual(["other", "test"]);
    expect(trackingOverview(book, "active", "2026-10-19").counts).toEqual({active: 2, due: 1, attention: 0, archived: 1});
    expect(trackingOverview(book, "archived", "2026-10-20").rows.map(r => r.id)).toEqual(["closed"]);
  });
  it("归档可恢复，不删除证据；未恢复不能追加复核", () => {
    const book = {schemaVersion: 1 as const, entries: [entry]};
    const archived = archiveEntry(book, entry.id, "2026-10-19T01:00:00Z");
    expect(archived.entries[0]?.source).toEqual(source);
    expect(book.entries[0]?.archivedAt).toBeUndefined();
    expect(readBook(archived).entries).toHaveLength(1);
    expect(() => addReview(archived, entry.id, {at: "now", note: "复核", impact: "pending", nextReview: "2026-11-01", source})).toThrow("恢复");
    expect(trackingOverview(archiveEntry(archived, entry.id, null), "due", "2026-10-20").counts.due).toBe(1);
  });
  it("复核以最新日期和用户结论为准，归档退出关注队列", () => {
    const book = addReview({schemaVersion: 1, entries: [entry]}, entry.id, {at: "2026-10-19T01:00:00Z", note: "反证", impact: "weakened", nextReview: "2026-11-10", source});
    expect(trackingOverview(book, "attention", "2026-10-20").counts).toMatchObject({due: 0, attention: 1});
    expect(trackingOverview(archiveEntry(book, entry.id, "2026-10-19T01:00:00Z"), "attention").rows).toEqual([]);
  });
  it("保存初始判断，追加复核不改原始证据或原数组", () => {
    const book = {schemaVersion: 1 as const, entries: [entry]};
    const result = addReview(book, "test", {at: "2026-10-20T01:00:00Z", note: "新证据", impact: "weakened", nextReview: "2026-11-20", source});
    expect(result.entries[0]?.statement).toBe(entry.statement);
    expect(result.entries[0]?.source).toEqual(source);
    expect(book.entries[0]?.reviews).toEqual([]);
    expect(reviewState(result.entries[0]!, source, "2026-10-21")).toMatchObject({impact: "weakened", due: false});
  });
  it("新报告及重新采集只提示复核，不改变观点", () => {
    expect(reviewState(entry, {...source, periodEnd: "2026-09-30", url: "https://www.stats.gov.cn/next"}, "2026-10-20")).toMatchObject({reportChanged: true, impact: "pending", due: true});
    expect(reviewState(entry, {...source, fetchedAt: "2026-10-19T01:00:00Z"}, "2026-10-19")).toMatchObject({recollected: true, reportChanged: false, due: false});
  });
  it("拒绝不兼容文档，避免覆盖和危险链接", () => {
    expect(readBook(emptyBook()).entries).toEqual([]);
    expect(readBook({schemaVersion: 1, entries: [entry]}).entries).toHaveLength(1);
    for (const value of [null, {schemaVersion: 2, entries: []}, {schemaVersion: 1, entries: [entry, entry]}, {schemaVersion: 1, entries: [{...entry, source: {...source, url: "javascript:alert(1)"}}]}]) expect(() => readBook(value)).toThrow();
  });
  it("复核需要依据及有效日历日期", () => {
    expect(validDay("2026-02-30")).toBe(false);
    expect(validDay("2028-02-29")).toBe(true);
    expect(() => addReview({schemaVersion: 1, entries: [entry]}, "test", {at: "now", note: "", impact: "pending", nextReview: "2026-10-20", source})).toThrow();
  });
});
