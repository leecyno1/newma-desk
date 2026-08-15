import { describe, expect, it } from "vitest";

import { buildCreatorContext } from "./context";
import type { CreatorMarketplace, CreatorSnapshot, MarketplacePreset, SnapshotNode } from "./types";

describe("Creator Studio Agent context", () => {
  it("exposes the same command ids used by the visual workbench", () => {
    const context = buildCreatorContext({
      workspace: "intake",
      runs: [],
    });

    expect(context.actions.map((action) => action.id)).toContain("creator.node.run");
    expect(context.actions.map((action) => action.id)).toContain("creator.workflow.continue");
    expect(context.data.source).toBe("newma-creator-studio-run-control");
  });

  it("uses backend availableActions for Agent action availability", () => {
    const node = {
      id: "review",
      name: "审核",
      status: "waiting_user",
      progress: 100,
      materialValidation: { status: "ready", missing: [], bindings: [] },
      artifacts: [],
      outputs: [],
      capabilities: [],
      editors: [],
      parameters: {},
      feedback: [],
      availableActions: ["creator.node.approve", "creator.node.request-changes"],
    } as unknown as SnapshotNode;
    const snapshot = {
      run: { runId: "creator-test", title: "审核任务" },
      stages: [{ id: "intake", name: "内容采集", nodes: [node] }],
    } as unknown as CreatorSnapshot;
    const context = buildCreatorContext({
      workspace: "intake",
      runs: [],
      snapshot,
      selectedNode: node,
    });
    const actions = new Map(context.actions.map((action) => [action.id, action.available]));

    expect(actions.get("creator.node.approve")).toBe(true);
    expect(actions.get("creator.node.request-changes")).toBe(true);
    expect(actions.get("creator.node.run")).toBe(false);
  });

  it("exposes the same explicit publish confirmation to the Desk Agent", () => {
    const node = {
      id: "publish_execute",
      name: "执行发布",
      status: "pending",
      progress: 0,
      materialValidation: { status: "ready", missing: [], bindings: [] },
      artifacts: [],
      outputs: [],
      capabilities: [],
      editors: [],
      parameters: {},
      feedback: [],
      availableActions: ["creator.publish.confirm"],
    } as unknown as SnapshotNode;
    const snapshot = {
      run: { runId: "creator-publish", title: "发布任务" },
      stages: [{ id: "publish", name: "发布", nodes: [node] }],
      publishState: { schemaVersion: "newma.creator-publish-state.v1" },
    } as unknown as CreatorSnapshot;
    const context = buildCreatorContext({
      workspace: "publish",
      runs: [],
      snapshot,
      selectedNode: node,
    });
    const action = context.actions.find((item) => item.id === "creator.publish.confirm");

    expect(action?.available).toBe(true);
    expect(action?.inputSchema).toEqual(expect.objectContaining({
      required: ["confirmed", "confirmationText"],
    }));
    expect((context.data.summary as Record<string, unknown>).publishState).toBeTruthy();
  });

  it("publishes marketplace choices and presets to the Desk Agent", () => {
    const marketplace = {
      counts: { projects: 0, repositories: 0, skills: 0, pipelines: 1, templates: 0, ready: 1 },
      pipelines: [{
        id: "vox",
        kind: "pipeline",
        name: "VOX 流水线",
        stageIds: ["transwrite"],
        status: { label: "可直接使用" },
      }],
      projects: [],
      skills: [],
      templates: [],
    } as unknown as CreatorMarketplace;
    const preset = {
      presetId: "preset-1",
      version: 1,
      name: "VOX 预设",
      itemId: "vox",
      itemKind: "pipeline",
      parameters: { duration: 60 },
    } as unknown as MarketplacePreset;
    const context = buildCreatorContext({
      workspace: "marketplace",
      runs: [],
      marketplace,
      marketplacePresets: [preset],
    });
    const summary = context.data.summary as Record<string, unknown>;
    const catalog = summary.marketplace as { items: Array<{ id: string }>; presets: Array<{ presetId: string }> };

    expect(catalog.items[0].id).toBe("vox");
    expect(catalog.presets[0].presetId).toBe("preset-1");
    expect(context.actions.map((action) => action.id)).toContain("creator.marketplace.apply-preset");
    expect(context.actions.map((action) => action.id)).toContain("creator.marketplace.update-preset");
  });
});
