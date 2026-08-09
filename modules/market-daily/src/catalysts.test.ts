import { describe, expect, it } from "vitest";

import { marketEvidenceToCatalyst } from "./catalysts";

describe("marketEvidenceToCatalyst", () => {
  it("maps historical timeline evidence into the shared catalyst contract", () => {
    const result = marketEvidenceToCatalyst({
      id: "announcement:1",
      timestamp: Date.UTC(2026, 7, 3),
      type: "announcement",
      title: "定期报告",
      detail: "公司公告",
      source: "东方财富公告",
      evidenceId: "announcement:1",
    }, { market: "CN", symbol: "600519", name: "贵州茅台" });

    expect(result.status).toBe("confirmed");
    expect(result.impactedAssets[0]?.symbol).toBe("600519");
    expect(result.confirmationConditions).toHaveLength(1);
  });
});
