import { describe, expect, it } from "vitest";

import {
  INVESTMENT_DOMAINS,
  INVESTMENT_DOMAIN_IDS,
  investmentDomainProject,
  isInvestmentDomainId,
} from "./investmentDomain";

describe("investment domain registry", () => {
  it("keeps the fifteen stable domains in product order", () => {
    expect(INVESTMENT_DOMAINS).toHaveLength(15);
    expect(INVESTMENT_DOMAINS.map((domain) => domain.id)).toEqual(
      INVESTMENT_DOMAIN_IDS,
    );
    expect(INVESTMENT_DOMAINS.map((domain) => domain.order)).toEqual(
      Array.from({ length: 15 }, (_, index) => (index + 1) * 10),
    );
  });

  it("builds a compact Chinese project identity for the sidebar", () => {
    const market = INVESTMENT_DOMAINS[0]!;
    expect(investmentDomainProject(market)).toMatchObject({
      id: "market-surface",
      name: "市场面",
      logo: { type: "letter", text: "市场" },
    });
  });

  it("recognizes only registered domain ids", () => {
    expect(isInvestmentDomainId("bond-research")).toBe(true);
    expect(isInvestmentDomainId("vibe-research")).toBe(false);
  });
});
