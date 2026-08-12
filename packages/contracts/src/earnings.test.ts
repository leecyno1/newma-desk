import { describe, expect, it } from "vitest";

import { earningsResearchWorkspaceSchema } from "./earnings";

function workspace() {
  return {
    schemaVersion: "newma-desk.earnings-research.v1",
    updatedAt: "2026-08-04T08:00:00.000Z",
    workbooks: [{
      id: "earnings:CN:600519:2026-H1",
      security: {
        market: "CN",
        symbol: "600519",
        name: "贵州茅台",
        exchange: "SH",
        currency: "CNY",
      },
      mode: "reported",
      fiscalPeriod: {
        label: "2026 半年报",
        periodEnd: "2026-06-30",
        reportingDate: "2026-08-29",
        reportingTime: "unknown",
      },
      verification: {
        status: "verified",
        latestPeriodChecked: true,
        checkedAt: "2026-08-04T08:00:00.000Z",
        primarySourceIds: ["company-filing"],
      },
      headline: "收入符合预期，利润率变化仍需结合渠道和现金流解释。",
      metrics: [{
        id: "revenue",
        label: "营业收入",
        category: "financial",
        unit: "亿元",
        reported: 910,
        internalEstimate: 900,
        consensus: 905,
        varianceVsConsensus: { amount: 5, percent: 0.55, bps: null },
        sourceIds: ["company-filing"],
        asOf: "2026-06-30",
      }],
      operatingMetrics: [],
      guidance: [],
      scenarios: [
        { id: "above", type: "above", condition: "核心指标高于预期", operatingPath: "验证经营改善", researchResponse: "核验改善来源和持续性", indicators: ["收入"] },
        { id: "inline", type: "inline", condition: "核心指标符合预期", operatingPath: "维持原有经营路径", researchResponse: "聚焦结构变化", indicators: ["毛利率"] },
        { id: "below", type: "below", condition: "核心指标低于预期", operatingPath: "经营假设承压", researchResponse: "检查一次性因素与证伪条件", indicators: ["现金流"] },
      ],
      estimateRevisions: [{
        id: "eps-2026e",
        label: "EPS",
        period: "2026E",
        unit: "元",
        previous: 70,
        current: 68,
        reason: "毛利率和费用率假设调整",
        sourceIds: ["internal-model"],
      }],
      thesisImpacts: [{
        id: "impact-brand",
        impact: "neutral",
        summary: "暂不改变品牌与渠道韧性的核心命题。",
        evidenceIds: ["company-filing"],
      }],
      sourceMaterials: [{
        id: "company-filing",
        label: "公司半年报",
        kind: "filing",
        url: "https://example.com/filing",
        asOf: "2026-08-29",
        status: "verified",
      }],
      gaps: ["缺少渠道库存的一手拆分"],
      createdAt: "2026-08-04T08:00:00.000Z",
      updatedAt: "2026-08-04T08:00:00.000Z",
    }],
  };
}

describe("earnings research contract", () => {
  it("accepts a source-linked preview and post-earnings comparison loop", () => {
    const parsed = earningsResearchWorkspaceSchema.parse(workspace());

    expect(parsed.workbooks[0]?.metrics[0]?.varianceVsConsensus.percent).toBe(0.55);
    expect(parsed.workbooks[0]?.scenarios).toHaveLength(3);
  });

  it("requires exactly three conditional scenarios and rejects trading actions", () => {
    const missingScenario = workspace();
    missingScenario.workbooks[0]!.scenarios.pop();
    expect(() => earningsResearchWorkspaceSchema.parse(missingScenario)).toThrow();

    const withAction = workspace() as ReturnType<typeof workspace> & {
      workbooks: Array<ReturnType<typeof workspace>["workbooks"][number] & { action?: string }>;
    };
    withAction.workbooks[0]!.action = "buy";
    expect(() => earningsResearchWorkspaceSchema.parse(withAction)).toThrow();
  });
});
