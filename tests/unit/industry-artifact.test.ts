import { describe, expect, it } from "vitest";
import { industryAnswerToArtifact } from "../../bundled-runtimes/vibe-research/frontend/src/lib/industry-artifact";
const options = { sectorKey: "cpo", sectorLabel: "光互联", question: "梳理结构" };
describe("industry text extraction boundaries", () => {
  it("does not turn parallel tree groups into supply or causal links", () => {
    const graph = industryAnswerToArtifact("旋转执行器\n├─ 电机\n└─ 减速器\n直线执行器\n├─ 丝杠\n└─ 电机", options);
    expect(graph?.nodes).toHaveLength(2);
    expect(graph?.edges).toEqual([]);
    expect(graph?.metadata?.evidenceStatus).toBe("unverified");
  });
  it("retains only explicit arrow direction and labels it unverified", () => {
    const graph = industryAnswerToArtifact("芯片 → 光引擎 → 系统", options);
    expect(graph?.edges).toHaveLength(2);
    expect(graph?.edges[0]).toMatchObject({ source: "stage-1", target: "stage-2", label: "原文箭头（含义待核实）" });
  });
  it("does not infer a chain from prose", () => {
    expect(industryAnswerToArtifact("光模块的研究需要核实证据。", options)).toBeNull();
  });
});
