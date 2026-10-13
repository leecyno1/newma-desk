import { describe, expect, it } from "vitest";
import type { ModPageContext } from "@newma-desk/contracts";
import { captureAnswerContext, readAnswerContext, canFollowup, matchesFollowup } from "./copilotAnswerContext";

const page = (): ModPageContext => ({
  view: {id: "earnings-workbench", title: "财报研究"}, visibleBlocks: [],
  selection: {name: "贵州茅台", symbol: "600519", market: "CN", workbookId: "book-a", fiscalPeriod: "2024年报"},
  filters: {periodEnd: "2024-12-31", basis: "annual", currency: "CNY"},
  data: {summary: {metrics: [{reported: 1708.99}]}}, actions: [], tasks: [],
});

describe("Copilot answer context", () => {
  it("captures identity by value without retaining financial data", () => {
    const context = page();
    const record = captureAnswerContext(context, "structured");
    context.selection.name = "另一公司";
    context.filters.periodEnd = "2025-12-31";
    expect(record).toMatchObject({subject: "贵州茅台 · 600519 · CN", periodEnd: "2024-12-31", workbookId: "book-a"});
    expect(JSON.stringify(record)).not.toContain("1708.99");
    expect(readAnswerContext(JSON.parse(JSON.stringify(record)))).toEqual(record);
  });

  it("does not infer workbook identity from fallback evidence", () => {
    for (const source of ["manifest", "dom-html", "visual"] as const) {
      const record = captureAnswerContext(page(), source);
      expect(record.subject).toBeUndefined();
      expect(record.workbookId).toBeUndefined();
      expect(record.viewTitle).toBe("财报研究");
    }
  });

  it("keeps old or invalid records unknown instead of backfilling", () => {
    expect(readAnswerContext(undefined)).toBeUndefined();
    expect(readAnswerContext({capturedAt: "invalid", source: "structured"})).toBeUndefined();
    expect(readAnswerContext({capturedAt: "2026-09-19T00:00:00Z", source: "guessed"})).toBeUndefined();
  });

  it("allows explicit followup only with the same complete workbook identity", () => {
    const record = captureAnswerContext(page(), "structured");
    expect(canFollowup(record)).toBe(true);
    expect(matchesFollowup(record, {...record, capturedAt: "2026-09-20T00:00:00Z"})).toBe(true);
    for (const key of ["workbookId", "symbol", "market", "currency", "periodEnd", "basis", "fiscalPeriod", "subject"] as const) {
      expect(matchesFollowup(record, {...record, [key]: "changed"})).toBe(false);
    }
    expect(canFollowup({...record, currency: undefined})).toBe(false);
    expect(canFollowup({...record, basis: "unknown"})).toBe(false);
    expect(matchesFollowup(record, {...record, source: "manifest"})).toBe(false);
    expect(matchesFollowup(undefined, record)).toBe(false);
  });
});
