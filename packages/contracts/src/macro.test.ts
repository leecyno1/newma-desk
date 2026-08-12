import { describe, expect, it } from "vitest";

import { macroMonitorFeedSchema } from "./macro";

const indicator = {
  id: "cn-pmi",
  name: "中国官方制造业 PMI",
  region: "CN",
  category: "growth",
  unit: "index",
  period: "2026-07-31",
  releaseDate: "2026-07-31",
  nextReleaseDate: "2026-08-31",
  value: 51.2,
  forecast: 50.8,
  previous: 49.8,
  change: 1.4,
  direction: "higher",
  source: { id: "jin10-macro", label: "金十宏观数据聚合", url: "https://datacenter.jin10.com/" },
  evidenceId: "macro:cn-pmi:2026-07-31",
  asOf: "2026-07-31",
  freshness: { status: "fresh", ageDays: 3 },
  confidence: { level: "medium", score: 0.72, rationale: "需回到原发布机构复核" },
  history: [{ period: "2026-07-31", value: 51.2 }],
};

describe("macro monitor contract", () => {
  it("accepts evidence-based indicators and scheduled events", () => {
    const parsed = macroMonitorFeedSchema.parse({
      schemaVersion: "newma-desk.macro-monitor.v1",
      generatedAt: "2026-08-03T00:00:00Z",
      horizon: { start: "2026-08-03", end: "2026-08-10", days: 7 },
      regime: {
        growth: { label: "增长", signal: "positive", summary: "PMI 51.2", evidenceIds: [indicator.evidenceId] },
        inflation: { label: "价格", signal: "neutral", summary: "CPI 平稳", evidenceIds: [] },
        liquidity: { label: "流动性", signal: "mixed", summary: "M2 与 LPR 信号不同", evidenceIds: [] },
        confidence: { level: "medium", score: 0.6, rationale: "部分指标新鲜" },
      },
      indicators: [indicator],
      events: [{
        id: "calendar:2026-08-04:pmi",
        date: "2026-08-04",
        time: "09:30",
        region: "中国",
        currency: null,
        title: "制造业 PMI 公布",
        importance: "medium",
        status: "scheduled",
        actual: null,
        forecast: 50.5,
        previous: 50.2,
        source: { id: "baidu-economic-calendar", label: "百度股市通经济日历", url: "https://finance.baidu.com/calendar" },
        evidenceId: "macro-calendar:2026-08-04:pmi",
        asOf: "2026-08-03T00:00:00Z",
      }],
      sources: [{ id: "public-macro-aggregators", label: "公开宏观数据聚合", status: "ok", count: 1, asOf: "2026-08-03T00:00:00Z" }],
      gaps: [{ capability: "official-primary-source-verification", reason: "required" }],
      disclaimer: "仅供研究",
    });

    expect(parsed.indicators.at(0)?.id).toBe("cn-pmi");
    expect(parsed.events).toHaveLength(1);
  });

  it("rejects an out-of-range calendar horizon", () => {
    expect(() => macroMonitorFeedSchema.parse({
      schemaVersion: "newma-desk.macro-monitor.v1",
      generatedAt: "2026-08-03T00:00:00Z",
      horizon: { start: "2026-08-03", end: "2026-10-01", days: 60 },
      regime: {}, indicators: [], events: [], sources: [], gaps: [], disclaimer: "test",
    })).toThrow();
  });
});
