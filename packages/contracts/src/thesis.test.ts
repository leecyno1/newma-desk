import { describe, expect, it } from "vitest";

import { investmentThesisPortfolioSchema } from "./thesis";

const pillars = Array.from({ length: 3 }, (_, index) => ({
  id: `pillar-${index + 1}`,
  title: `支柱 ${index + 1}`,
  expectation: "收入和经营效率持续改善",
  currentStatus: "等待下一期财报验证",
  trend: "pending" as const,
  evidenceIds: [],
}));

const risks = Array.from({ length: 3 }, (_, index) => ({
  id: `risk-${index + 1}`,
  statement: `风险 ${index + 1}`,
  invalidationCondition: "核心经营指标连续两个报告期低于预期",
  status: "monitoring" as const,
  evidenceIds: [],
}));

function portfolio() {
  return {
    schemaVersion: "newma-desk.investment-thesis.v1",
    updatedAt: "2026-08-04T08:00:00.000Z",
    theses: [{
      id: "thesis-cn-600519",
      security: { market: "CN", symbol: "600519", name: "贵州茅台", exchange: "SH" },
      title: "品牌与渠道韧性研究",
      statement: "核心假设是品牌势能与渠道质量能够支持收入质量和现金流韧性。",
      status: "active",
      conviction: "medium",
      pillars,
      invalidationRisks: risks,
      linkedCatalysts: [{ id: "earnings:600519:2026-h1", title: "2026 半年报", date: "2026-08-29" }],
      evidence: [{
        id: "evidence:600519:2026-h1",
        source: { id: "company-announcement", label: "公司公告", url: "https://example.com/notice" },
        summary: "半年报收入和现金流仍需正式公告确认。",
        asOf: "2026-08-04",
        freshness: { status: "fresh", ageDays: 0 },
        confidence: { level: "medium", score: 0.7, rationale: "已找到公告预约日期，尚未发布正文" },
        impact: "neutral",
        pillarId: "pillar-1",
        createdAt: "2026-08-04T08:00:00.000Z",
      }],
      updates: [{
        id: "update:600519:2026-08-04",
        date: "2026-08-04",
        dataPoint: "半年报尚未发布，继续等待正式数据",
        impact: "neutral",
        pillarId: "pillar-1",
        evidenceIds: ["evidence:600519:2026-h1"],
        conviction: "medium",
      }],
      valuation: {
        method: "历史区间与现金流交叉核验",
        referenceValue: null,
        currency: "CNY",
        asOf: "2026-08-04",
        assumptions: ["不把单一估值倍数作为投资建议"],
      },
      nextReviewAt: "2026-09-30",
      gaps: ["缺少最新渠道库存的一手证据"],
      createdAt: "2026-08-04T08:00:00.000Z",
      updatedAt: "2026-08-04T08:00:00.000Z",
    }],
  };
}

describe("investment thesis contract", () => {
  it("accepts a falsifiable thesis with pillars, risks, evidence, and review history", () => {
    const parsed = investmentThesisPortfolioSchema.parse(portfolio());

    expect(parsed.theses[0]?.pillars).toHaveLength(3);
    expect(parsed.theses[0]?.evidence[0]?.impact).toBe("neutral");
  });

  it("requires at least three pillars and rejects portfolio-action fields", () => {
    const tooFew = portfolio();
    tooFew.theses[0]!.pillars = pillars.slice(0, 2);
    expect(() => investmentThesisPortfolioSchema.parse(tooFew)).toThrow();

    const withAction = portfolio() as ReturnType<typeof portfolio> & {
      theses: Array<ReturnType<typeof portfolio>["theses"][number] & { action?: string }>;
    };
    withAction.theses[0]!.action = "increase";
    expect(() => investmentThesisPortfolioSchema.parse(withAction)).toThrow();
  });
});
