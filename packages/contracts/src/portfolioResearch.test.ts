import { describe, expect, it } from "vitest";

import { portfolioResearchCoverageSchema } from "./portfolioResearch";

const reference = {
  id: "archive:thesis-tracker:thesis-1",
  kind: "thesis" as const,
  sourceModId: "thesis-tracker",
  artifactId: "thesis-1",
  title: "贵州茅台核心逻辑",
  status: "active" as const,
  security: { market: "CN", symbol: "600519", name: "贵州茅台" },
  asOf: "2026-09-01",
  updatedAt: "2026-08-05T07:00:00.000Z",
  tags: ["active"],
  sourceRevision: 2,
};

const coverage = {
  schemaVersion: "newma-desk.portfolio-research-coverage.v1" as const,
  userId: "user-1",
  workspaceId: "workspace-1",
  generatedAt: "2026-08-05T08:00:00.000Z",
  summary: {
    positionCount: 1,
    completeCount: 0,
    partialCount: 1,
    missingCount: 0,
    attentionCount: 0,
    activeReferenceCount: 1,
  },
  positions: [{
    market: "CN" as const,
    symbol: "600519",
    name: "贵州茅台",
    accountIds: ["main"],
    status: "partial" as const,
    referenceCount: 1,
    activeReferenceCount: 1,
    coreKinds: ["thesis" as const],
    supportingKinds: [],
    missingGroups: ["supporting-analysis" as const],
    attentionReasons: [],
    latestUpdatedAt: "2026-08-05T07:00:00.000Z",
    references: [reference],
  }],
};

describe("portfolio research coverage contract", () => {
  it("accepts reference-only research coverage", () => {
    expect(portfolioResearchCoverageSchema.parse(coverage)).toEqual(coverage);
  });

  it("rejects copied research bodies and duplicate securities", () => {
    expect(() => portfolioResearchCoverageSchema.parse({
      ...coverage,
      positions: [{
        ...coverage.positions[0],
        references: [{ ...reference, content: "copied thesis body" }],
      }],
    })).toThrow();
    expect(() => portfolioResearchCoverageSchema.parse({
      ...coverage,
      positions: [coverage.positions[0], coverage.positions[0]],
    })).toThrow(/unique/);
  });
});
