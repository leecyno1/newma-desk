import { describe, expect, it } from "vitest";
import { diagnosisFor } from "./diagnosis";
import { productionFor, type Production } from "./production";
import { pricesFor, type Prices } from "./prices";
import { contextFor, type Industry, type Snapshot } from "./research";

const coal = {name: "煤炭开采和洗选业", revenueYoy: 10.4, profitYoy: 51.6} as Industry;
const report = {period: "2026年1—8月", periodEnd: "2026-08-31", publishedAt: "2026-09-28", sourceUrl: "financial", taxonomy: "NBS", unit: "亿元", rows: [coal]} as Snapshot;
const product = {name: "原煤", kind: "product", monthYoy: -7.7, cumulativeYoy: -3.3, raw: {}} as Production["metrics"][number];
const source = {periodEnd: report.periodEnd, publishedAt: "2026-09-15", sourceUrl: "production", metrics: [product], limitations: [], discoveryErrors: []} as unknown as Production;
const price = {periodEnd: report.periodEnd, sourceUrl: "price", publishedAt: "2026-09-09", monthlyPeriod: "2026年8月", metrics: [{name: coal.name, monthMom: 2.8, monthYoy: 26.6, yearToDateAverageYoy: 7.6, raw: {}}], limitations: [], baseNotes: [], discoveryErrors: []} as unknown as Prices;
function evidence(row = coal, prod: Production | null = source, pp: Prices | null = price, status = "ready") {
  const p = productionFor(report, row, prod, status, "");
  const prices = pricesFor(report, row, pp, status, "", p);
  return {p, prices, result: diagnosisFor(report, row, p, prices, [], "idle")!};
}

describe("行业诊断：结论不超出同期证据", () => {
  it("煤炭涨价减产增利，以具体口径和原文支撑分化判断", () => {
    const {result} = evidence();
    expect(result.headline).toBe("累计利润增长；当月量价方向分化");
    expect(result.facts[0].text).toContain("51.6%");
    expect(result.facts[1].text).toContain("当月同比 -7.7%");
    expect(result.facts[2].text).toContain("年内平均同比 7.6%");
    expect(result.facts.slice(0, 3).map(row => row.sourceUrl)).toEqual(["financial", "production", "price"]);
    expect(result.questions).toHaveLength(3);
    expect(result.observations.join()).toContain("不能量化归因");
  });
  it("电子产品分化不外推为整个半导体景气", () => {
    const row = {...coal, name: "计算机、通信和其他电子设备制造业"};
    const {result} = evidence(row, {...source, metrics: [{...product, name: "集成电路", monthYoy: 20.6, cumulativeYoy: 22.3}, {...product, name: "微型计算机设备", monthYoy: -25.6, cumulativeYoy: -14.7}]}, {...price, metrics: [{...price.metrics[0]!, name: row.name}]});
    expect(result.headline).toContain("细分产品产量分化");
    expect(result.observations.join()).toContain("不能代表产品价值");
  });
  it("零值保留，缺值不算增长也不补零", () => {
    const zero = evidence({...coal, revenueYoy: 0, profitYoy: 0}, null, null, "idle").result;
    expect(zero.headline).toContain("累计利润零增长");
    expect(zero.facts[0].text).toContain("0.0%");
    const missing = evidence({...coal, profitYoy: null}, {...source, metrics: [{...product, monthYoy: null, cumulativeYoy: null}]}, {...price, metrics: [{...price.metrics[0]!, monthMom: null, monthYoy: null, yearToDateAverageYoy: null}]}).result;
    expect(missing.headline).toBe("利润同比缺失或不可比；量价证据尚待补齐");
    expect(missing.facts[2].state).toBe("同比缺失 / 不可比");
    expect(missing.facts[0].text).toContain("—");
  });
  it("未加载、刷新失败、错行业或错期，不遗留旧交叉判断", () => {
    const {p, prices} = evidence();
    for (const patch of [{status: "idle"}, {status: "loading"}, {status: "failed"}, {industry: "其他行业"}]) {
      const result = diagnosisFor(report, coal, {...p, ...patch}, {...prices, ...patch}, [], "idle")!;
      expect(result.headline).toContain("量价证据尚待补齐");
      expect(result.observations).toEqual([]);
      expect(result.facts[1].sourceUrl).toBeNull();
      expect(result.facts[2].sourceUrl).toBeNull();
    }
    const wrongPeriod = diagnosisFor(report, coal, {...p, publication: {...p.publication!, periodEnd: "2026-07-31"}}, {...prices, publication: {...prices.publication!, periodEnd: "2026-07-31"}}, [], "idle")!;
    expect(wrongPeriod.observations).toEqual([]);
    expect(diagnosisFor(null, coal, p, prices, [], "idle")).toBeNull();
    expect(diagnosisFor(report, undefined, p, prices, [], "idle")).toBeNull();
  });
  it("历史仅作相邻累计同比百分点对照，后发布资料提示现时补证", () => {
    const {p, prices} = evidence();
    const prior = {...report, sourceUrl: "prior", periodEnd: "2026-07-31", publishedAt: "2026-08-27", rows: [{...coal, profitYoy: 40}]};
    const result = diagnosisFor(report, coal, p, prices, [report, prior], "ready")!;
    expect(result.facts[3].text).toContain("11.6 个百分点");
    expect(result.facts[3].sourceUrl).toBe("prior");
    const noFuture = diagnosisFor(prior, prior.rows[0], p, prices, [report, prior], "ready")!;
    expect(noFuture.headline).toContain("量价证据尚待补齐");
    expect(noFuture.facts[3].state).toBe("不可比较");
    const later = evidence(coal, {...source, publishedAt: "2026-10-10"}, {...price, publishedAt: "2026-10-11"}).result;
    expect(later.timingNotes).toHaveLength(2);
    expect(later.timingNotes.join()).toContain("现时补证");
  });
  it("页面、导出同一诊断对象；财务刷新失败撤下Agent诊断", () => {
    const {p, prices, result} = evidence();
    const context = contextFor(report, [coal], coal, [], {}, "ready", "", null, "idle", "", [], p, prices, result);
    expect(context.data.summary?.diagnosis).toBe(result);
    expect(contextFor(null, [], undefined, [], {}, "failed", "", null, "idle", "", [], p, prices, result).data.summary?.diagnosis).toBeNull();
  });
});
