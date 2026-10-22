import { describe, expect, it } from "vitest";
import { capacityFor, capacityPeriodEnd, type Capacity } from "./capacity";
import { contextFor, type Industry, type Snapshot } from "./research";
import { diagnosisFor } from "./diagnosis";
import { productionFor } from "./production";
import { pricesFor } from "./prices";

const coal = {name: "煤炭开采和洗选业", revenueYoy: 10, profitYoy: 20} as Industry;
const report = {periodEnd: "2026-08-31", publishedAt: "2026-09-28", rows: [coal]} as Snapshot;
const source: Capacity = {title: "测试季度报告", sourceUrl: "test", publisher: "测试源", publishedAt: "2026-07-15", periodEnd: "2026-06-30",
  quarterPeriod: "2026年二季度", yearToDatePeriod: "2026年上半年", coverage: 1, fetchedAt: "2026-10-18T00:00:00Z", cached: false, discovery: "测试", discoveryErrors: [], limitations: [],
  metrics: [{name: coal.name, scope: "industry", quarterRate: 61.2, quarterYoyPp: -8.1, yearToDateRate: 63.6, yearToDateYoyPp: -7, raw: {}},
    {name: "制造业", scope: "group", quarterRate: 73.5, quarterYoyPp: -0.8, yearToDateRate: 73.7, yearToDateYoyPp: -0.5, raw: {}}]};

describe("季度产能证据", () => {
  it("选择财务月末之前已完成季度，正确处理跨年与季度末", () => {
    for (const [month, expected] of [["2026-08-31", "2026-06-30"], ["2026-09-30", "2026-09-30"], ["2026-02-28", "2025-12-31"], ["2026-05-31", "2026-03-31"]]) {
      expect(capacityPeriodEnd(month)).toBe(expected);
    }
    expect(capacityPeriodEnd()).toBeUndefined();
  });
  it("季度和年内累计保留独立值，说明滞后而不做利润归因", () => {
    const evidence = capacityFor(report, coal, source, "ready", "");
    expect(evidence.metric?.quarterRate).toBe(61.2);
    expect(evidence.metric?.yearToDateRate).toBe(63.6);
    expect(evidence.timingNote).toContain("滞后季度参考");
    expect(evidence.observations.join()).toContain("不直接判定订单下滑");
    expect(evidence.publicationNote).toBeNull();
    expect(capacityFor({...report, publishedAt: "2026-07-01"}, coal, source, "ready", "").publicationNote).toContain("现时补证");
  });
  it("无直接行业匹配不拿门类替代，零与缺失不混同", () => {
    expect(capacityFor(report, {...coal, name: "制造业"}, source, "ready", "").metric).toBeNull();
    expect(capacityFor(report, {...coal, name: "测试行业"}, source, "ready", "").observations).toEqual([]);
    const zero = {...source, metrics: [{...source.metrics[0]!, quarterYoyPp: 0}]};
    expect(capacityFor(report, coal, zero, "ready", "").observations.join()).toContain("持平");
    expect(capacityFor(report, coal, {...source, metrics: [{...zero.metrics[0]!, quarterYoyPp: null}]}, "ready", "").observations).toEqual([]);
  });
  it("未来季度、错期、加载和失败撤下旧证据", () => {
    for (const periodEnd of ["2026-03-31", "2026-09-30"]) {
      expect(capacityFor(report, coal, {...source, periodEnd}, "ready", "")).toMatchObject({status: "mismatch", metric: null, publication: null});
    }
    for (const status of ["loading", "failed"]) expect(capacityFor(report, coal, source, status, "").metric).toBeNull();
    expect(capacityFor(null, coal, source, "ready", "")).toMatchObject({status: "idle", metric: null});
  });
  it("诊断和Agent使用同一季度对象，财务刷新失败不残留", () => {
    const capacity = capacityFor(report, coal, source, "ready", "");
    const production = productionFor(report, coal, null, "idle", "");
    const prices = pricesFor(report, coal, null, "idle", "", production);
    const diagnosis = diagnosisFor(report, coal, production, prices, [], "idle", capacity);
    expect(diagnosis?.facts[4].text).toContain("2026年二季度");
    expect(diagnosis?.facts[4].text).toContain("滞后季度参考");
    expect(contextFor(report, [coal], coal, [], {}, "ready", "", null, "idle", "", [], production, prices, diagnosis, capacity).data.summary?.capacity).toBe(capacity);
    expect(contextFor(null, [], undefined, [], {}, "failed", "", null, "idle", "", [], production, prices, diagnosis, capacity).data.summary?.capacity).toBeNull();
    expect(diagnosisFor(report, coal, production, prices, [], "idle", {...capacity, financialPeriodEnd: "2026-07-31"})?.facts[4].sourceUrl).toBeNull();
  });
});
