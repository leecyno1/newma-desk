import { describe, expect, it, vi } from "vitest";
vi.mock("../../bundled-runtimes/vibe-research/frontend/src/lib/vibedesk", () => ({ getVibeDeskConfig: () => null }));
import { evidenceCoverage, evidenceError, evidenceLink, evidenceTiming, industryTargets, industryStructureError, reviseIndustryStructure, validateIndustryBook, type IndustryEvidence, type IndustryVersion } from "../../bundled-runtimes/vibe-research/frontend/src/lib/industryWorkspace";
import { HBM_GRAPH, HBM_REFERENCES } from "../../bundled-runtimes/vibe-research/frontend/src/data/hbm-research";
const spec = { moduleId: "industry-map", title: "合成测试", nodes: [{ id: "a", label: "甲" }, { id: "b", label: "乙" }], edges: [{ source: "a", target: "b", label: "供应" }] };
const record: IndustryEvidence = { id: "one", target: industryTargets(spec)[2].key, title: "合成公告", url: "https://example.com/source", locator: "第 2 页", excerpt: "合成测试摘录", publishedAt: "", nextReview: "", judgment: "supports", note: "", recordedAt: "2026-10-19T01:00:00Z" };
describe("industry workspace evidence", () => {
  it("keeps public HBM references pending review and binds them to explicit relations", () => {
    expect(industryStructureError(HBM_GRAPH)).toBeNull();
    expect(HBM_REFERENCES).toHaveLength(HBM_GRAPH.edges.length);
    for (const reference of HBM_REFERENCES) {
      expect(evidenceError(reference, HBM_GRAPH)).toBeNull();
      expect(industryTargets(HBM_GRAPH).some((target) => target.key === reference.target)).toBe(true);
      expect(reference.reviewRequired).toBeTruthy();
      expect(reference.judgment).toBe("unclear");
    }
    expect(new Set(HBM_REFERENCES.map((item) => item.target)).size).toBe(HBM_GRAPH.edges.length);
    expect(evidenceCoverage(HBM_GRAPH, HBM_REFERENCES)).toMatchObject({ recordedTargets: 0, needsReview: 6 });
    expect(HBM_REFERENCES.filter((item) => item.url.includes("micron.com")).every((item) => item.publishedAt === "")).toBe(true);
    expect(HBM_REFERENCES.find((item) => item.url.includes("skhynix"))?.excerpt).toContain("remains uncertain");
    expect(HBM_GRAPH.edges.find((edge) => edge.source === "hybrid")?.label).toContain("未定");
  });
  it("binds directed edges and keeps conflicting evidence visible", () => {
    expect(industryTargets(spec)[2].key).not.toBe(industryTargets({ ...spec, edges: [{ source: "b", target: "a", label: "供应" }] })[2].key);
    const counts = evidenceCoverage(spec, [record, { ...record, id: "two", judgment: "refutes" }]);
    expect(counts).toMatchObject({ targets: 3, recordedTargets: 1, missingTargets: 2, conflictingTargets: 1 });
  });
  it("does not count an unmatched old relation as graph coverage", () => {
    expect(evidenceError({ ...record, target: "missing" }, spec)).toBeTruthy();
    expect(evidenceCoverage(spec, [{ ...record, target: "missing" }]).recordedTargets).toBe(0);
  });
  it("does not turn missing dates or future publications into fresh evidence", () => {
    expect(evidenceTiming(record, "2026-10-19")).toBe("资料日期未知");
    expect(evidenceTiming({ ...record, publishedAt: "2026-10-20" }, "2026-10-19")).toBe("资料日期晚于当前日期");
    expect(evidenceTiming({ ...record, publishedAt: "2026-09-01", nextReview: "2026-10-19" }, "2026-10-19")).toBe("到期复核");
    expect(evidenceError({ ...record, publishedAt: "2026-02-30" }, spec)).toBeTruthy();
  });
  it("rejects executable links and untraceable claims", () => {
    expect(evidenceLink("javascript:alert(1)")).toBeNull();
    expect(evidenceLink("https://name:password@example.com/")).toBeNull();
    expect(evidenceError({ ...record, locator: "" }, spec)).toBeTruthy();
    expect(evidenceError({ ...record, excerpt: "" }, spec)).toBeTruthy();
  });
  it("rejects mismatched topics and broken version histories instead of silently emptying them", () => {
    const value = { schemaVersion: "newma-desk.industry-map.v1" as const, sectorKey: "humanoid", versions: [{ number: 1, basedOn: null, savedAt: "2026-10-19", provenance: "synthetic", spec, evidence: [record] }] };
    expect(() => validateIndustryBook(value, "humanoid")).not.toThrow();
    expect(() => validateIndustryBook(value, "cpo")).toThrow();
    expect(() => validateIndustryBook({ ...value, versions: [{ ...value.versions[0], number: 3 }] }, "humanoid")).toThrow();
  });
  it("keeps deleted relationship evidence as pending review without changing the saved version", () => {
    const version: IndustryVersion = { number: 1, basedOn: null, savedAt: "2026-10-19", provenance: "synthetic", spec, evidence: [record] };
    const changed = reviseIndustryStructure(version, { ...spec, edges: [] });
    expect(changed.evidence[0]).toMatchObject({ excerpt: record.excerpt, target: record.target, reviewRequired: { targetLabel: "甲 → 乙 · 供应" } });
    expect(evidenceCoverage(changed.spec, changed.evidence)).toMatchObject({ recordedTargets: 0, needsReview: 1 });
    expect(evidenceError(changed.evidence[0], changed.spec)).toBeNull();
    expect(() => validateIndustryBook({ schemaVersion: "newma-desk.industry-map.v1", sectorKey: "hbm", versions: [changed] }, "hbm")).not.toThrow();
    expect(version.evidence[0].reviewRequired).toBeUndefined();
    expect(version.spec.edges).toHaveLength(1);
  });
  it("invalidates node and adjacent edge evidence, but not unrelated evidence or title-only edits", () => {
    const version: IndustryVersion = { number: 1, basedOn: null, savedAt: "", provenance: "synthetic", spec, evidence: [record, { ...record, id: "a-record", target: "node:a" }, { ...record, id: "b-record", target: "node:b" }] };
    expect(reviseIndustryStructure(version, { ...spec, title: "新标题" }).evidence.every((item) => !item.reviewRequired)).toBe(true);
    const changed = reviseIndustryStructure(version, { ...spec, nodes: [{ id: "a", label: "新甲" }, spec.nodes[1]] });
    expect(changed.evidence.map((item) => Boolean(item.reviewRequired))).toEqual([true, true, false]);
    const restored = reviseIndustryStructure(changed, spec);
    expect(evidenceCoverage(spec, restored.evidence)).toMatchObject({ recordedTargets: 1, needsReview: 2 });
    expect(restored.evidence[0].reviewRequired?.targetLabel).toBe("甲 → 乙 · 供应");
  });
  it("requires complete nodes and valid distinct directed relations before preview/save", () => {
    expect(industryStructureError({ ...spec, nodes: [], edges: [] })).toContain("至少");
    expect(industryStructureError({ ...spec, nodes: [{ id: "a", label: " " }, spec.nodes[1]] })).toContain("节点名称");
    expect(industryStructureError({ ...spec, edges: [{ source: "a", target: "a" }] })).toContain("不同");
    expect(industryStructureError({ ...spec, edges: [{ source: "missing", target: "a" }] })).toContain("现有");
    expect(industryStructureError({ ...spec, edges: [...spec.edges, ...spec.edges] })).toContain("重复");
    expect(industryStructureError(spec)).toBeNull();
  });
});
