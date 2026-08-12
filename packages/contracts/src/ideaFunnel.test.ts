import { describe, expect, it } from "vitest";

import { ideaFunnelWorkspaceSchema } from "./ideaFunnel";

function workspace() {
  const now = "2026-08-04T09:00:00.000Z";
  return {
    schemaVersion: "newma-desk.idea-funnel.v1" as const,
    updatedAt: now,
    ideas: [{
      id: "idea-300308",
      title: "高速光模块需求与份额研究线索",
      security: { market: "CN", symbol: "300308", name: "中际旭创", currency: "CNY" },
      stage: "shortlist" as const,
      priority: "high" as const,
      researchStyle: "growth" as const,
      origin: { type: "theme" as const, label: "AI 算力产业链", sourceModId: "industry-map", artifactId: "ai-computing", asOf: "2026-08-04", discoveredAt: now },
      searchCriteria: {
        markets: ["CN"], sectors: ["通信设备"], styles: ["growth" as const], themes: ["AI 算力"], marketCapRange: "中大型",
        rules: [{ id: "rule-growth", metric: "收入增速", operator: "gte" as const, value: "15%", rationale: "验证景气兑现" }],
      },
      researchQuestion: "高速光模块需求与公司份额能否支持未来两年的增长质量？",
      initialHypothesis: "产品迭代和客户资本开支可能支持收入增长。",
      opposingHypothesis: "供给扩张和客户集中可能导致增速与利润率回落。",
      whyNow: "1.6T 产品导入和下一次财报构成验证窗口。",
      marketMayMiss: "市场可能低估迭代速度，也可能高估利润率持续性。",
      metrics: [{ id: "metric-growth", label: "收入增速", value: "待核验", peerReference: "同业中位数待补", asOf: "2026-08-04", sourceIds: ["source-industry"] }],
      signals: [
        { id: "signal-1", type: "thematic" as const, direction: "supports" as const, summary: "AI 资本开支仍是产业链主驱动", sourceIds: ["source-industry"] },
        { id: "signal-2", type: "risk" as const, direction: "challenges" as const, summary: "供给扩张可能压缩利润率", sourceIds: ["source-industry"] },
      ],
      scorecard: { relevance: 85, evidenceQuality: 60, novelty: 55, catalystClarity: 75, falsifiability: 80, researchEffort: 50, total: 68 },
      catalysts: [{ id: "catalyst-1", title: "半年报", window: "2026-08", confirmationCondition: "收入和利润率披露", invalidationCondition: "披露日期变化", sourceIds: [] }],
      risks: [{ id: "risk-1", statement: "需求或份额低于预期", earlyWarning: "订单与毛利率转弱", falsificationCondition: "核心指标连续两个报告期恶化", sourceIds: [] }],
      linkedArtifacts: [{ id: "artifact-industry", sourceModId: "industry-map", artifactId: "ai-computing", title: "AI 算力产业链", asOf: "2026-08-04", status: "linked" as const }],
      sources: [{ id: "source-industry", label: "产业链研究", kind: "research" as const, asOf: "2026-08-04", status: "available" as const }],
      gaps: ["财务与客户数据待核验"],
      nextActions: [{ id: "action-1", kind: "filing" as const, label: "核验最新财报", status: "pending" as const, completionStandard: "补齐收入、利润率和客户风险来源" }],
      handoff: { targetModId: "thesis-tracker" as const, status: "ready" as const, note: "通过初筛后建立可证伪逻辑" },
      reviewLog: [{ id: "review-1", createdAt: now, stage: "shortlist" as const, summary: "进入研究短名单" }],
      createdAt: now,
      updatedAt: now,
    }],
  };
}

describe("idea funnel contract", () => {
  it("accepts a source-backed, two-sided and actionable research candidate", () => {
    const parsed = ideaFunnelWorkspaceSchema.parse(workspace());
    expect(parsed.ideas[0]?.signals).toHaveLength(2);
    expect(parsed.ideas[0]?.handoff.targetModId).toBe("thesis-tracker");
  });

  it("rejects one-sided candidates and recommendation fields", () => {
    const invalid = workspace();
    invalid.ideas[0]!.signals = invalid.ideas[0]!.signals.slice(0, 1);
    expect(() => ideaFunnelWorkspaceSchema.parse(invalid)).toThrow();

    const recommendation = workspace() as ReturnType<typeof workspace> & {
      ideas: Array<ReturnType<typeof workspace>["ideas"][number] & { recommendation?: string }>;
    };
    recommendation.ideas[0]!.recommendation = "buy";
    expect(() => ideaFunnelWorkspaceSchema.parse(recommendation)).toThrow();
  });
});
