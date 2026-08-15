import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  CreatorMarketplace,
  CreatorSnapshot,
  MarketplaceCompatibility,
  MarketplaceItem,
  MarketplacePreset,
  SnapshotNode,
  SnapshotStage,
} from "./types";
import { MarketplaceView, WorkbenchView } from "./views";

const status: MarketplaceItem["status"] = {
  discovery: "discovered",
  registration: "workflow_registered",
  installation: "installed",
  runtime: "available",
  compatibility: "compatible",
  label: "可直接使用",
  tone: "ready",
  reasons: ["已绑定工作流"],
};

const marketplace: CreatorMarketplace = {
  schema_version: "newma.creator_marketplace.v2",
  generated_at: "2026-08-15T00:00:00+08:00",
  counts: { projects: 1, repositories: 1, skills: 1, pipelines: 1, templates: 1, ready: 4 },
  pipelines: [{
    id: "vox", kind: "pipeline", name: "VOX 流水线", summary: "调查型解释视频",
    category: "production", status,
    flow: [{ id: "script", name: "剧本重写" }, { id: "scene", name: "导演分镜" }],
  }],
  projects: [{
    id: "video-shotcraft", kind: "project", name: "video-shotcraft",
    summary: "用于镜头配方和 Remotion 动效。", category: "video", status,
    capabilityLabels: ["镜头配方库", "电影化运镜"],
  }],
  repositories: [],
  skills: [{
    id: "newma-vox-skills", kind: "skill", name: "Newma VOX 视频制作",
    summary: "完整执行 VOX 视频生产。", category: "视频生产", status,
  }],
  templates: [{
    id: "bold-poster", kind: "template", name: "Bold Poster", summary: "标题模板。",
    category: "presentation", categoryLabel: "标题与观点呈现", status,
    preview: { assetPath: "preview.png", url: "/preview.png", kind: "image", alt: "preview" },
  }],
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("WorkbenchView", () => {
  it("shows publish control and sends the fixed one-time confirmation", async () => {
    const node = {
      id: "publish_execute",
      name: "执行发布",
      description: "执行真实发布",
      status: "pending",
      progress: 0,
      materialValidation: { status: "ready", missing: [], bindings: [] },
      materials: [],
      outputs: ["platform_receipts"],
      artifacts: [],
      capabilities: ["publish_cli"],
      editors: [],
      actions: [],
      parameters: {},
      feedback: [],
      logs: [],
      attempt: 0,
      availableActions: ["creator.publish.confirm"],
    } as unknown as SnapshotNode;
    const stage = {
      id: "publish",
      name: "发布",
      status: "pending",
      progress: 0,
      nodes: [node],
    } as SnapshotStage;
    const snapshot = {
      run: { runId: "run-publish", title: "发布测试" },
      stages: [stage],
      handoffs: [],
      publishState: {
        schemaVersion: "newma.creator-publish-state.v1",
        preflight: {
          nodeStatus: "succeeded",
          taskCount: 1,
          blockers: [],
          warnings: [],
          accountHealth: { accounts: [{ label: "公众号", status: "available" }] },
        },
      },
    } as unknown as CreatorSnapshot;
    const dispatch = vi.fn(async () => snapshot);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<WorkbenchView
      snapshot={snapshot}
      selectedStage={stage}
      selectedNode={node}
      dispatch={dispatch}
      busy={false}
      onCreate={vi.fn()}
    />);

    fireEvent.click(screen.getByRole("button", { name: "发布控制" }));
    expect(screen.getByText("公众号")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "确认发布" }));

    await waitFor(() => expect(dispatch).toHaveBeenCalledWith(
      "creator.publish.confirm",
      {
        stageId: "publish",
        nodeId: "publish_execute",
        confirmed: true,
        confirmationText: "确认发布",
      },
    ));
  });
});

describe("MarketplaceView", () => {
  it("shows pipeline flows and lets users inspect projects and template previews", () => {
    render(<MarketplaceView marketplace={marketplace} presets={[]} loading={false} busyAction="" dispatch={vi.fn()} />);

    expect(screen.getAllByText("VOX 流水线").length).toBeGreaterThan(0);
    expect(screen.getAllByText("剧本重写").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /项目与仓库/ }));
    expect(screen.getAllByText("video-shotcraft").length).toBeGreaterThan(0);
    expect(screen.getAllByText("镜头配方库").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /组件模板/ }));
    expect(screen.getAllByRole("img", { name: "preview" }).length).toBeGreaterThan(0);
  });

  it("checks compatibility, saves a preset and applies it to the selected node", async () => {
    const selectedNode = { id: "scene", name: "导演分镜" } as SnapshotNode;
    const renderNode = { id: "render", name: "渲染合成" } as SnapshotNode;
    const selectedStage = { id: "transwrite", name: "多通路转写", nodes: [selectedNode, renderNode] } as SnapshotStage;
    const snapshot = { run: { runId: "run-1", title: "DeepSeek 视频" }, stages: [selectedStage] } as CreatorSnapshot;
    const compatibility: MarketplaceCompatibility = {
      schemaVersion: "newma.creator-marketplace-compatibility.v1",
      status: "compatible",
      canSave: true,
      canApply: true,
      item: { id: "vox", kind: "pipeline", name: "VOX 流水线" },
      target: { stageId: "transwrite", nodeId: "scene", name: "导演分镜" },
      checks: [{ id: "runtime", status: "pass", label: "运行环境可用" }],
      recommendedNodes: [],
      demo: { mode: "flow", available: true },
    };
    const preset: MarketplacePreset = {
      schemaVersion: "newma.creator-marketplace-preset.v1",
      presetId: "preset-1",
      version: 1,
      name: "VOX 流水线 预设",
      itemId: "vox",
      itemKind: "pipeline",
      target: { stageId: "transwrite", nodeId: "scene" },
      parameters: {},
      compatibility,
      createdAt: "2026-08-15T00:00:00+08:00",
      updatedAt: "2026-08-15T00:00:00+08:00",
    };
    const dispatch = vi.fn(async (actionId: string) => {
      if (actionId === "creator.marketplace.check-compatibility") return compatibility;
      if (actionId === "creator.marketplace.save-preset") return preset;
      return snapshot;
    });

    render(<MarketplaceView
      marketplace={marketplace}
      presets={[]}
      snapshot={snapshot}
      selectedStage={selectedStage}
      selectedNode={selectedNode}
      loading={false}
      busyAction=""
      dispatch={dispatch}
    />);

    fireEvent.change(screen.getByLabelText("目标工作流节点"), { target: { value: "transwrite::render" } });
    fireEvent.click(screen.getByRole("button", { name: "＋ 添加参数" }));
    fireEvent.change(screen.getByLabelText("参数名称 2"), { target: { value: "duration" } });
    fireEvent.change(screen.getByLabelText("参数值 2"), { target: { value: "60" } });
    fireEvent.click(screen.getByRole("button", { name: "检查兼容性" }));
    expect(await screen.findByText("运行环境可用")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "保存并应用" }));

    await waitFor(() => expect(dispatch).toHaveBeenCalledWith(
      "creator.marketplace.save-preset",
      expect.objectContaining({
        stageId: "transwrite",
        nodeId: "render",
        parameters: { pipelineId: "vox", duration: 60 },
      }),
    ));
    await waitFor(() => expect(dispatch).toHaveBeenCalledWith(
      "creator.marketplace.apply-preset",
      { presetId: "preset-1", stageId: "transwrite", nodeId: "render" },
    ));
  });

  it("updates presets as new versions and can apply a historical version", async () => {
    const node = { id: "scene", name: "导演分镜" } as SnapshotNode;
    const stage = { id: "transwrite", name: "多通路转写", nodes: [node] } as SnapshotStage;
    const snapshot = { run: { runId: "run-1", title: "版本测试" }, stages: [stage] } as CreatorSnapshot;
    const compatibility: MarketplaceCompatibility = {
      schemaVersion: "compatibility.v1",
      status: "compatible",
      canSave: true,
      canApply: true,
      item: { id: "vox", kind: "pipeline", name: "VOX 流水线" },
      target: { stageId: "transwrite", nodeId: "scene", name: "导演分镜" },
      checks: [],
      recommendedNodes: [],
      demo: { mode: "flow", available: true },
    };
    const versionOne = {
      schemaVersion: "preset.v1", presetId: "preset-1", version: 1, name: "VOX 预设",
      itemId: "vox", itemKind: "pipeline", parameters: { duration: 30 }, compatibility,
      createdAt: "2026-08-15T00:00:00+08:00", updatedAt: "2026-08-15T00:00:00+08:00",
    } as MarketplacePreset;
    const versionTwo = { ...versionOne, version: 2, parameters: { duration: 60 } };
    const dispatch = vi.fn(async (actionId: string) => {
      if (actionId === "creator.marketplace.check-compatibility") return compatibility;
      if (actionId === "creator.marketplace.update-preset") return versionTwo;
      if (actionId === "creator.marketplace.list-preset-versions") return { versions: [versionTwo, versionOne] };
      return snapshot;
    });

    render(<MarketplaceView
      marketplace={marketplace}
      presets={[versionOne]}
      snapshot={snapshot}
      selectedStage={stage}
      selectedNode={node}
      loading={false}
      busyAction=""
      dispatch={dispatch}
    />);

    fireEvent.click(screen.getByRole("button", { name: "更新为 v2" }));
    await waitFor(() => expect(dispatch).toHaveBeenCalledWith(
      "creator.marketplace.update-preset",
      expect.objectContaining({ presetId: "preset-1", expectedVersion: 1 }),
    ));
    expect((await screen.findAllByText("1 个参数")).length).toBe(2);
    const historyApplyButtons = await screen.findAllByRole("button", { name: "应用此版本" });
    fireEvent.click(historyApplyButtons.at(-1)!);
    await waitFor(() => expect(dispatch).toHaveBeenCalledWith(
      "creator.marketplace.apply-preset",
      { presetId: "preset-1", presetVersion: 1, stageId: "transwrite", nodeId: "scene" },
    ));
  });
});
