import { describe, expect, it } from "vitest";
import { productionFor, type Production, type ProductionMetric } from "./production";
import type { Industry, Snapshot } from "./research";

const coal = {name: "煤炭开采和洗选业", revenueYoy: 10.4, profitYoy: 51.6} as Industry;
const electronic = {...coal, name: "计算机、通信和其他电子设备制造业"};
const report = {periodEnd: "2026-08-31", publishedAt: "2026-09-28"} as Snapshot;
const metric = (name: string, cumulativeYoy: number | null, kind: "product" | "valueAdded" = "product"): ProductionMetric => ({name, cumulativeYoy, kind, monthYoy: 0, monthValue: 10, cumulativeValue: 20, unit: "万吨", raw: {}});
const source = {periodEnd: report.periodEnd, publishedAt: "2026-09-15", sourceUrl: "official", metrics: [metric(coal.name, 0.8, "valueAdded"), metric("原煤", -3.3), metric(electronic.name, 15.7, "valueAdded"), metric("集成电路", 22.3), metric("微型计算机设备", -14.7), metric("移动通信手持机", -5.6)], limitations: ["样本不同"], discoveryErrors: []} as unknown as Production;

describe("生产与盈利交叉验证", () => {
  it("全国产销率只作独立背景，不加入当前行业指标或方向判断", () => {
    const nationalSales = {scope: "全国规模以上工业", monthRate: 96.8, monthYoyPp: -0.1, cumulativeRate: 96.2, cumulativeYoyPp: 0.1, raw: {}};
    const evidence = productionFor(report, coal, {...source, nationalSales}, "ready", "");
    expect(evidence.nationalSales).toEqual(nationalSales);
    expect(evidence.metrics).toEqual(productionFor(report, coal, source, "ready", "").metrics);
    expect(evidence.observations).toEqual(productionFor(report, coal, source, "ready", "").observations);
    expect(productionFor({...report, periodEnd: "2026-07-31"}, coal, {...source, nationalSales}, "ready", "").nationalSales).toBeNull();
  });
  it("煤炭只取本行业与原煤证据，分化不是因果结论", () => {
    const evidence = productionFor(report, coal, source, "ready", "");
    expect(evidence.metrics.map(row => row.name)).toEqual([coal.name, "原煤"]);
    expect(evidence.observations.join()).toContain("方向分化");
    expect(evidence.observations.join()).toContain("不能直接归因");
  });
  it("电子产品分化不外推整个半导体盈利，不混入煤炭", () => {
    const evidence = productionFor(report, electronic, source, "ready", "");
    expect(evidence.metrics).toHaveLength(4);
    expect(evidence.metrics.some(row => row.name === "原煤")).toBe(false);
    expect(evidence.observations.join()).toContain("主要产品产量走势分化");
    expect(evidence.observations.join()).toContain("不能代表产品价值");
  });
  it("不匹配行业、报告期变化和失败不会残留旧证据", () => {
    expect(productionFor(report, {...coal, name: "无匹配行业"}, source, "ready", "").metrics).toEqual([]);
    const wrong = productionFor({...report, periodEnd: "2026-07-31"}, coal, source, "ready", "");
    expect(wrong).toMatchObject({status: "mismatch", publication: null, metrics: [], observations: []});
    expect(productionFor(report, coal, null, "failed", "失败")).toMatchObject({metrics: [], observations: [], publication: null});
  });
  it("零值不是分化信号，缺值不补零，并披露后发数据", () => {
    const result = productionFor(report, coal, {...source, publishedAt: "2026-10-01", metrics: [metric("原煤", 0)]}, "ready", "");
    expect(result.observations.join()).not.toContain("方向分化");
    expect(result.timingNote).toContain("发布晚于");
    const missing = productionFor(report, coal, {...source, metrics: [metric("原煤", null)]}, "ready", "");
    expect(missing.metrics[0]?.cumulativeYoy).toBeNull();
    expect(missing.missing.join()).toContain("部分同比不可比或缺失");
  });
});
