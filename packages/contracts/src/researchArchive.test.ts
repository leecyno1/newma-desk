import { describe, expect, it } from "vitest";

import { researchArchiveIndexSchema } from "./researchArchive";

const index = {
  schemaVersion: "newma-desk.research-archive.v1" as const,
  userId: "user-1",
  workspaceId: "workspace-1",
  generatedAt: "2026-08-05T08:00:00.000Z",
  entries: [{
    id: "archive:thesis-tracker:thesis:1",
    kind: "thesis" as const,
    sourceModId: "thesis-tracker",
    artifactId: "thesis:1",
    title: "产品迭代逻辑",
    status: "active" as const,
    security: { market: "CN", symbol: "300308", name: "中际旭创" },
    asOf: "2026-09-01",
    updatedAt: "2026-08-05T07:00:00.000Z",
    tags: ["active", "medium"],
    sourceRevision: 2,
  }],
};

describe("research archive contract", () => {
  it("accepts a reference-only archive index", () => {
    expect(researchArchiveIndexSchema.parse(index)).toEqual(index);
  });

  it("rejects copied artifact payloads and duplicate references", () => {
    expect(() => researchArchiveIndexSchema.parse({
      ...index,
      entries: [{ ...index.entries[0], content: "copied body" }],
    })).toThrow();
    expect(() => researchArchiveIndexSchema.parse({
      ...index,
      entries: [index.entries[0], index.entries[0]],
    })).toThrow(/unique/);
  });
});
