import { describe, expect, it } from "vitest";

import { valuationWorkspaceSchema } from "./valuation";

function workspace() {
  const drivers = [2027, 2028, 2029, 2030, 2031].map((year, index) => ({
    year,
    revenueGrowthPct: 12 - index,
    ebitMarginPct: 20 + index,
    taxRatePct: 25,
    daPctRevenue: 3,
    capexPctRevenue: 4,
    nwcPctDeltaRevenue: 5,
  }));
  return {
    schemaVersion: "newma-desk.valuation-workbench.v1" as const,
    updatedAt: "2026-08-04T08:00:00.000Z",
    models: [{
      id: "valuation-300308",
      name: "中际旭创轻量 DCF",
      modelScope: "driver-based-dcf" as const,
      security: { market: "CN", symbol: "300308", name: "中际旭创", currency: "CNY" },
      asOf: "2026-08-04",
      unitScale: "百万元",
      selectedScenario: "base" as const,
      historicals: [{
        period: "2026E",
        revenue: 42000,
        ebitMarginPct: 25,
        daPctRevenue: 3,
        capexPctRevenue: 5,
        nwcPctDeltaRevenue: 4,
        sourceIds: ["research:300308"],
      }],
      capitalInputs: {
        currentPrice: 180,
        dilutedSharesM: 1120,
        totalDebtM: 3000,
        cashM: 6000,
        riskFreeRatePct: 2,
        beta: 1.2,
        equityRiskPremiumPct: 6,
        preTaxCostDebtPct: 4,
        taxRatePct: 25,
      },
      scenarios: [
        { id: "bear" as const, label: "悲观", waccPct: 11, terminalGrowthPct: 2, rationale: "需求和利润率承压", drivers },
        { id: "base" as const, label: "基准", waccPct: 9.5, terminalGrowthPct: 2.5, rationale: "增长逐步回归稳态", drivers },
        { id: "bull" as const, label: "乐观", waccPct: 8.5, terminalGrowthPct: 3, rationale: "需求与经营杠杆优于预期", drivers },
      ],
      projections: drivers.map((driver, index) => ({
        year: driver.year,
        revenue: 47000 + index * 5000,
        revenueGrowthPct: driver.revenueGrowthPct,
        ebit: 9400 + index * 1200,
        ebitMarginPct: driver.ebitMarginPct,
        nopat: 7050 + index * 900,
        depreciationAmortization: 1410 + index * 150,
        capex: 1880 + index * 200,
        changeNwc: 200,
        unleveredFcf: 6380 + index * 850,
        discountPeriod: index + 0.5,
        discountFactor: 0.95 - index * 0.07,
        pvFcf: 6061 + index * 400,
      })),
      result: {
        scenarioId: "base" as const,
        pvExplicitFcfM: 32000,
        terminalValueM: 120000,
        pvTerminalValueM: 76000,
        enterpriseValueM: 108000,
        netDebtM: -3000,
        equityValueM: 111000,
        impliedPrice: 99.11,
        currentPrice: 180,
        impliedReturnPct: -44.94,
        terminalValueSharePct: 70.37,
      },
      sensitivity: {
        waccPct: [8.5, 9, 9.5, 10, 10.5],
        terminalGrowthPct: [1.5, 2, 2.5, 3, 3.5],
        impliedPrices: Array.from({ length: 5 }, () => [80, 90, 99.11, 110, 120]),
        center: { row: 2 as const, column: 2 as const },
      },
      auditChecks: [{ id: "terminal-growth", label: "终值增长", status: "pass" as const, message: "终值增长低于 WACC" }],
      sourceMaterials: [{ id: "research:300308", label: "Evidence Ledger", asOf: "2026-08-04", source: "Newma Research", status: "available" as const }],
      gaps: ["债务与现金需要回到财报附注核验"],
      createdAt: "2026-08-04T08:00:00.000Z",
      updatedAt: "2026-08-04T08:00:00.000Z",
    }],
  };
}

describe("valuation workbench contract", () => {
  it("accepts a driver-based DCF with three scenarios, source trails and a centered sensitivity grid", () => {
    const parsed = valuationWorkspaceSchema.parse(workspace());

    expect(parsed.models[0]?.scenarios).toHaveLength(3);
    expect(parsed.models[0]?.sensitivity.impliedPrices).toHaveLength(5);
    expect(parsed.models[0]?.result.scenarioId).toBe("base");
  });

  it("rejects invalid terminal growth and undeclared recommendation fields", () => {
    const invalid = workspace();
    invalid.models[0]!.scenarios[1]!.terminalGrowthPct = 9.5;
    expect(() => valuationWorkspaceSchema.parse(invalid)).toThrow();

    const recommendation = workspace() as ReturnType<typeof workspace> & {
      models: Array<ReturnType<typeof workspace>["models"][number] & { recommendation?: string }>;
    };
    recommendation.models[0]!.recommendation = "buy";
    expect(() => valuationWorkspaceSchema.parse(recommendation)).toThrow();
  });
});
