import { describe, expect, it } from "vitest";

import { researchRecordWorkspaceSchema } from "./researchRecord";

const workspace = {
  schemaVersion: "newma-desk.research-records.v1" as const,
  updatedAt: "2026-08-05T00:00:00.000Z",
  records: [{
    id: "note:1",
    kind: "复盘",
    title: "每日复盘",
    content: "# 结论\n\n保留来源与反方风险。",
    ts: 1_785_859_200_000,
  }],
};

describe("research record contract", () => {
  it("accepts a bounded Desk research record workspace", () => {
    expect(researchRecordWorkspaceSchema.parse(workspace)).toEqual(workspace);
  });

  it("rejects empty content and unknown fields", () => {
    expect(() => researchRecordWorkspaceSchema.parse({ ...workspace, records: [{ ...workspace.records[0], content: "" }] })).toThrow();
    expect(() => researchRecordWorkspaceSchema.parse({ ...workspace, legacyKey: "vr-notes" })).toThrow();
  });
});
