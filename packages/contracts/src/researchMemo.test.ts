import { describe, expect, it } from "vitest";

import { researchMemoWorkspaceSchema } from "./researchMemo";

function workspace() {
  const now = "2026-08-04T08:00:00.000Z";
  return {
    schemaVersion: "newma-desk.research-memo.v1" as const,
    updatedAt: now,
    memos: [{
      id: "memo-300308",
      title: "中际旭创研究备忘录",
      status: "current" as const,
      security: { market: "CN", symbol: "300308", name: "中际旭创", currency: "CNY" },
      boundary: {
        asOf: "2026-08-04",
        horizon: "未来 12 个月，重点跟踪未来 3–6 个月催化",
        fiscalYear: "FY2026",
        reportingCurrency: "CNY",
        scope: "经营驱动、竞争格局、财报、估值与催化剂",
        disclosureLimits: ["一致预期口径待核验"],
      },
      executiveView: {
        bias: "neutral" as const,
        conviction: "medium" as const,
        conclusion: "需求仍强，但估值与供给扩张需要同步观察。",
        coreThesis: "高速光模块需求与份额变化是主要价值驱动。",
        keyDebate: "需求持续性是否足以覆盖供给扩张。",
        variantPerception: "市场可能低估产品迭代速度，也可能高估利润率持续性。",
        whatMayBeMissing: "客户资本开支结构与 1.6T 放量节奏。",
        breakpoint: "核心客户需求、份额与毛利率同时连续恶化。",
      },
      linkedArtifacts: [{
        id: "artifact-thesis",
        kind: "thesis" as const,
        sourceModId: "thesis-tracker",
        artifactId: "thesis-300308",
        title: "光模块需求与份额逻辑",
        asOf: "2026-08-04",
        status: "linked" as const,
      }],
      keyDrivers: [1, 2, 3].map((index) => ({
        id: `driver-${index}`,
        name: `驱动 ${index}`,
        whyItMatters: "影响增长、利润率或估值假设。",
        currentView: "当前证据中性。",
        monitorMetric: `指标 ${index}`,
        confirmationCondition: "指标改善且有原始来源确认。",
        falsificationCondition: "指标持续恶化并偏离基准假设。",
        sourceIds: ["source-1"],
      })),
      scenarios: [
        { id: "bear" as const, label: "悲观", probabilityPct: 25, operatingPath: "需求与利润率低于基准", valuationReference: "引用估值工作台悲观情景", triggerConditions: ["订单下修"], evidenceIds: ["source-1"] },
        { id: "base" as const, label: "基准", probabilityPct: 50, operatingPath: "增长逐步回归稳态", valuationReference: "引用估值工作台基准情景", triggerConditions: ["收入符合预期"], evidenceIds: ["source-1"] },
        { id: "bull" as const, label: "乐观", probabilityPct: 25, operatingPath: "需求和份额优于预期", valuationReference: "引用估值工作台乐观情景", triggerConditions: ["1.6T 放量"], evidenceIds: ["source-1"] },
      ],
      catalysts: [{ id: "catalyst-1", title: "半年报", window: "2026-08", expectedPath: "核验需求和利润率", confirmationConditions: ["财报披露"], invalidationConditions: ["日期变化"] }],
      risks: [1, 2, 3].map((index) => ({
        id: `risk-${index}`,
        type: "fundamental" as const,
        statement: `风险 ${index}`,
        severity: "medium" as const,
        likelihood: "unknown" as const,
        earlyWarnings: ["指标转弱"],
        breakCondition: `证伪条件 ${index}`,
        sourceIds: ["source-1"],
      })),
      monitoring: [1, 2, 3].map((index) => ({
        id: `monitor-${index}`,
        metric: `跟踪指标 ${index}`,
        latest: "待更新",
        trend: "unknown" as const,
        threshold: "偏离基准假设时复核",
        frequency: "月度",
        sourceIds: ["source-1"],
      })),
      sources: [{ id: "source-1", label: "公司公告", kind: "company" as const, claimType: "reported" as const, asOf: "2026-08-04", status: "verified" as const }],
      gaps: ["客户结构需要补充原始披露"],
      nextReviewAt: "2026-09-04",
      versions: [{ version: 1, createdAt: now, summary: "创建研究备忘录", changedSections: ["全部"] }],
      createdAt: now,
      updatedAt: now,
    }],
  };
}

describe("research memo contract", () => {
  it("accepts a versioned, source-linked and falsifiable research memo", () => {
    const parsed = researchMemoWorkspaceSchema.parse(workspace());
    expect(parsed.memos[0]?.linkedArtifacts[0]?.sourceModId).toBe("thesis-tracker");
    expect(parsed.memos[0]?.scenarios).toHaveLength(3);
    expect(parsed.memos[0]?.versions[0]?.version).toBe(1);
  });

  it("rejects invalid scenario weights and recommendation fields", () => {
    const invalid = workspace();
    invalid.memos[0]!.scenarios[1]!.probabilityPct = 40;
    expect(() => researchMemoWorkspaceSchema.parse(invalid)).toThrow();

    const recommendation = workspace() as ReturnType<typeof workspace> & {
      memos: Array<ReturnType<typeof workspace>["memos"][number] & { recommendation?: string }>;
    };
    recommendation.memos[0]!.recommendation = "buy";
    expect(() => researchMemoWorkspaceSchema.parse(recommendation)).toThrow();
  });
});
