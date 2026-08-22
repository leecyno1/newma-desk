import { describe, expect, it } from "vitest";

import {
  INVESTMENT_DOMAINS,
  INVESTMENT_DOMAIN_IDS,
  investmentDomainProject,
  isInvestmentDomainId,
} from "./investmentDomain";

describe("investment domain registry", () => {
  it("keeps the sixteen stable domains in product order", () => {
    expect(INVESTMENT_DOMAINS).toHaveLength(16);
    expect(INVESTMENT_DOMAINS.map((domain) => domain.id)).toEqual(
      INVESTMENT_DOMAIN_IDS,
    );
    expect(INVESTMENT_DOMAINS.map((domain) => domain.order)).toEqual([
      0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150,
    ]);
  });

  it("builds a compact Chinese project identity for the sidebar", () => {
    const market = INVESTMENT_DOMAINS[4]!;
    expect(investmentDomainProject(market)).toMatchObject({
      id: "market-surface",
      name: "市场",
      logo: { type: "letter", text: "市场" },
    });
  });

  it("recognizes only registered domain ids", () => {
    expect(isInvestmentDomainId("risk-management")).toBe(true);
    expect(isInvestmentDomainId("bond-research")).toBe(false);
    expect(isInvestmentDomainId("vibe-research")).toBe(false);
  });
});
