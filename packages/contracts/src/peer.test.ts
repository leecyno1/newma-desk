import { describe, expect, it } from "vitest";

import { peerComparisonWorkspaceSchema } from "./peer";

function workspace() {
  const securities = [
    { market: "CN", symbol: "300308", name: "中际旭创", currency: "CNY" },
    { market: "CN", symbol: "300394", name: "天孚通信", currency: "CNY" },
    { market: "CN", symbol: "002281", name: "光迅科技", currency: "CNY" },
  ];
  return {
    schemaVersion: "newma-desk.peer-comparison.v1",
    updatedAt: "2026-08-04T08:00:00.000Z",
    cases: [{
      id: "peer-case-optics",
      name: "光模块核心公司比较",
      researchQuestion: "quality",
      target: securities[0],
      members: securities.map((security, index) => ({
        security,
        role: index === 0 ? "target" as const : "direct" as const,
        included: true,
        rationale: "业务模式和主要下游具有可比性",
        exceptions: index === 2 ? ["产品结构不同"] : [],
      })),
      period: { label: "最新报告期", asOf: "2026-08-04", fiscalAlignment: "aligned", unitScale: "原始披露口径" },
      metrics: [
        { id: "revenueGrowthPct", label: "营收增长", category: "operating", unit: "%", higherIsBetter: true },
        { id: "grossMarginPct", label: "毛利率", category: "quality", unit: "%", higherIsBetter: true },
        { id: "pe", label: "PE", category: "valuation", unit: "x", higherIsBetter: null },
      ],
      rows: securities.map((security, index) => ({
        security,
        isTarget: index === 0,
        period: "2026-06-30",
        coverageRatio: 0.8,
        values: { revenueGrowthPct: 20 - index, grossMarginPct: 35 + index, pe: 30 + index },
        scores: { quality: 70 + index },
        sourceIds: [`research:${security.symbol}`],
        warnings: [],
      })),
      statistics: {
        revenueGrowthPct: { max: 20, q75: 19.5, median: 19, q25: 18.5, min: 18 },
        grossMarginPct: { max: 37, q75: 36.5, median: 36, q25: 35.5, min: 35 },
        pe: { max: 32, q75: 31.5, median: 31, q25: 30.5, min: 30 },
      },
      strategicDimensions: [{
        id: "scale",
        label: "规模与交付",
        moat: "scale-economies",
        targetAssessment: "客户覆盖和交付规模较强",
        peerObservation: "同业在器件能力或细分客户上各有优势",
        trajectory: "improving",
        sourceIds: ["research:300308"],
      }],
      sourceMaterials: securities.map((security) => ({
        id: `research:${security.symbol}`,
        label: `${security.name} Evidence Ledger`,
        symbol: security.symbol,
        asOf: "2026-08-04",
        status: "available" as const,
      })),
      synthesis: {
        durableAdvantages: ["规模交付能力"],
        structuralVulnerabilities: ["客户集中度"],
        currentVsTrajectory: "当前规模领先，但需持续验证产品结构和毛利率趋势。",
      },
      gaps: ["不同公司报告期存在轻微错位"],
      createdAt: "2026-08-04T08:00:00.000Z",
      updatedAt: "2026-08-04T08:00:00.000Z",
    }],
  };
}

describe("peer comparison contract", () => {
  it("accepts comparable peers, consistent metrics, statistics, and source trails", () => {
    const parsed = peerComparisonWorkspaceSchema.parse(workspace());

    expect(parsed.cases[0]?.members).toHaveLength(3);
    expect(parsed.cases[0]?.statistics.pe?.median).toBe(31);
  });

  it("requires at least two peers and rejects trading recommendations", () => {
    const tooSmall = workspace();
    tooSmall.cases[0]!.members = tooSmall.cases[0]!.members.slice(0, 1);
    expect(() => peerComparisonWorkspaceSchema.parse(tooSmall)).toThrow();

    const withRecommendation = workspace() as ReturnType<typeof workspace> & {
      cases: Array<ReturnType<typeof workspace>["cases"][number] & { recommendation?: string }>;
    };
    withRecommendation.cases[0]!.recommendation = "buy target";
    expect(() => peerComparisonWorkspaceSchema.parse(withRecommendation)).toThrow();
  });
});
