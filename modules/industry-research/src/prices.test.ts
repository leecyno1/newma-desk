import { describe, expect, it } from "vitest";
import { pricesFor, type Prices } from "./prices";
import type { ProductionEvidence } from "./production";
import { contextFor, type Industry, type Snapshot } from "./research";

const coal = {name: "煤炭开采和洗选业", revenueYoy: 10.4, profitYoy: 51.6} as Industry;
const report = {periodEnd: "2026-08-31", publishedAt: "2026-09-28"} as Snapshot;
const metric = {name: coal.name, monthMom: 2.8, monthYoy: 26.6, yearToDateAverageYoy: 7.6, raw: {}};
const prices = {periodEnd: report.periodEnd, publishedAt: "2026-09-09", metrics: [metric], limitations: [], baseNotes: [], discoveryErrors: []} as unknown as Prices;
const production = {industry: coal.name, publication: {periodEnd: report.periodEnd, sourceUrl: "production"}, metrics: [{kind: "product", name: "原煤", monthYoy: -7.7}]} as ProductionEvidence;

describe("同期间行业价格验证", () => {
  it("区分年内平均与月度口径，涨价减产不称量价齐升", () => {
    const evidence = pricesFor(report, coal, prices, "ready", "", production);
    expect(evidence.metric?.yearToDateAverageYoy).toBe(7.6);
    expect(evidence.observations.join()).toContain("不宜概括为量价齐升");
    expect(evidence.observations.join()).toContain("不能量化归因");
    expect(evidence.productionCheck?.metrics[0]?.monthYoy).toBe(-7.7);
  });
  it("不把不同期间或行业的产量混入量价对照", () => {
    for (const wrong of [{...production, industry: "其他行业"}, {...production, publication: {...production.publication!, periodEnd: "2026-07-31"}}]) {
      const evidence = pricesFor(report, coal, prices, "ready", "", wrong);
      expect(evidence.productionCheck).toBeNull();
      expect(evidence.observations.join()).not.toContain("产量同比方向");
    }
    expect(pricesFor(report, coal, {...prices, periodEnd: "2026-09-30"}, "ready", "", production)).toMatchObject({metric: null, observations: [], publication: null});
  });
  it("缺值不补零，环比上涨不掩盖同比下降，不匹配行业不替代", () => {
    const other = {...prices, metrics: [{...metric, monthYoy: -2, yearToDateAverageYoy: null}]};
    expect(pricesFor(report, coal, other, "ready", "").observations.join()).toContain("环比与同比方向不同");
    expect(pricesFor(report, coal, other, "ready", "").metric?.yearToDateAverageYoy).toBeNull();
    expect(pricesFor(report, {...coal, name: "相似煤炭"}, prices, "ready", "").metric).toBeNull();
    expect(pricesFor(report, coal, {...prices, metrics: [{...metric, monthYoy: 0, yearToDateAverageYoy: 0}]}, "ready", "").metric?.monthYoy).toBe(0);
  });
  it("失败撤掉价格及交叉判断，财务失败不保留价格上下文", () => {
    const failed = pricesFor(report, coal, null, "failed", "源失败", production);
    expect(failed).toMatchObject({metric: null, observations: [], productionCheck: null});
    const context = contextFor(null, [], undefined, [], {}, "failed", "", null, "idle", "", [], production, failed);
    expect(context.data.summary?.prices).toBeNull();
  });
});
