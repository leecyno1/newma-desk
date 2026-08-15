import type { ModPageContext } from "@newma-desk/contracts";

import { isCreatorStage } from "./types";
import type {
  CreatorRegistry,
  CreatorMarketplace,
  CreatorRunSummary,
  CreatorSnapshot,
  CreatorWorkspace,
  MarketplacePreset,
  SnapshotNode,
  SnapshotStage,
} from "./types";

const PAGE_TITLES: Record<CreatorWorkspace, string> = {
  dashboard: "Creator Studio 状态看板",
  intake: "Creator Studio 内容采集",
  brief: "Creator Studio 选题 Brief",
  draft: "Creator Studio 初稿生产",
  transwrite: "Creator Studio 多通路转写",
  publish: "Creator Studio 发布",
  postmortem: "Creator Studio 复盘",
  marketplace: "Creator Studio 超市项目",
  settings: "Creator Studio 项目设置",
};

const nodeTargetSchema = {
  type: "object",
  properties: {
    stageId: { type: "string" },
    nodeId: { type: "string" },
  },
  additionalProperties: false,
};

export function buildCreatorContext(input: {
  workspace: CreatorWorkspace;
  registry?: CreatorRegistry;
  runs: CreatorRunSummary[];
  marketplace?: CreatorMarketplace;
  marketplacePresets?: MarketplacePreset[];
  snapshot?: CreatorSnapshot;
  selectedStage?: SnapshotStage;
  selectedNode?: SnapshotNode;
}): ModPageContext {
  const {
    workspace, registry, runs, marketplace, marketplacePresets = [], snapshot, selectedStage, selectedNode,
  } = input;
  const hasRun = Boolean(snapshot);
  const workflowNodes = snapshot?.stages.flatMap((stage) => stage.nodes) ?? [];
  const actionAvailable = (actionId: string) =>
    workflowNodes.some((node) => node.availableActions.includes(actionId));
  const workflow = snapshot?.stages.map((stage) => ({
    id: stage.id,
    name: stage.name,
    status: stage.status,
    progress: stage.progress,
    nodes: stage.nodes.map((node) => ({
      id: node.id,
      name: node.name,
      status: node.status,
      progress: node.progress,
      materialStatus: node.materialValidation.status,
      artifactCount: node.artifacts.length,
      availableActions: node.availableActions,
    })),
  })) ?? registry?.stages.map((stage) => ({
    id: stage.id,
    name: stage.name,
    status: "pending",
    nodes: stage.nodes.map((node) => ({ id: node.id, name: node.name, status: "pending" })),
  })) ?? [];

  return {
    view: { id: `creator-${workspace}`, title: PAGE_TITLES[workspace] },
    visibleBlocks: [
      { id: "creator-header", type: "workflow-header", title: PAGE_TITLES[workspace] },
      { id: `creator-${workspace}-main`, type: workspace, title: PAGE_TITLES[workspace] },
      ...(isCreatorStage(workspace)
        ? [{ id: "creator-node-workspace", type: "node-workspace", title: selectedNode?.name }]
        : []),
    ],
    selection: {
      runId: snapshot?.run.runId,
      runTitle: snapshot?.run.title,
      stageId: selectedStage?.id,
      stageName: selectedStage?.name,
      nodeId: selectedNode?.id,
      nodeName: selectedNode?.name,
    },
    filters: { workspace },
    data: {
      asOf: snapshot?.generatedAt,
      source: "newma-creator-studio-run-control",
      freshness: snapshot ? "live" : "unknown",
      summary: {
        run: snapshot?.run ?? null,
        runs,
        counters: snapshot?.counters ?? {},
        publishState: snapshot?.publishState ?? null,
        lineageState: snapshot?.lineageState ?? null,
        workflow,
        selectedNode: selectedNode ? {
          status: selectedNode.status,
          progress: selectedNode.progress,
          materialValidation: selectedNode.materialValidation,
          outputs: selectedNode.outputs,
          executor: selectedNode.executor,
          capabilities: selectedNode.capabilities,
          editors: selectedNode.editors,
          parameters: selectedNode.parameters,
          executionResult: selectedNode.executionResult ?? null,
          staleAt: selectedNode.staleAt,
          staleReason: selectedNode.staleReason,
          artifacts: selectedNode.artifacts,
          availableActions: selectedNode.availableActions,
          latestFeedback: selectedNode.feedback.at(-1) ?? null,
        } : null,
        marketplace: workspace === "marketplace" && marketplace ? {
          counts: marketplace.counts,
          items: [
            ...marketplace.pipelines,
            ...marketplace.projects,
            ...marketplace.skills,
            ...marketplace.templates,
          ].map((item) => ({
            id: item.id,
            kind: item.kind,
            name: item.name,
            summary: item.summary,
            stageIds: item.stageIds ?? [],
            status: item.status.label,
          })),
          presets: marketplacePresets.map((preset) => ({
            presetId: preset.presetId,
            version: preset.version,
            name: preset.name,
            itemId: preset.itemId,
            itemKind: preset.itemKind,
            target: preset.target,
            parameters: preset.parameters,
          })),
        } : null,
        note: "所有工作流变更均通过 Creator Command 写入共享 Run Control；页面与 Agent 不维护独立状态。",
      },
    },
    actions: [
      {
        id: "creator.run.create",
        label: "从任意节点新建任务",
        available: Boolean(registry),
        inputSchema: {
          type: "object",
          required: ["title", "stageId", "nodeId", "materials"],
          properties: {
            title: { type: "string" },
            stageId: { type: "string" },
            nodeId: { type: "string" },
            materials: { type: "array" },
          },
        },
      },
      {
        id: "creator.run.select",
        label: "切换创作任务",
        available: runs.length > 0,
        inputSchema: {
          type: "object",
          required: ["runId"],
          properties: { runId: { type: "string" } },
        },
      },
      {
        id: "creator.node.select",
        label: "切换工作流节点",
        available: hasRun,
        inputSchema: {
          type: "object",
          required: ["stageId", "nodeId"],
          properties: {
            stageId: { type: "string" },
            nodeId: { type: "string" },
          },
        },
      },
      { id: "creator.node.run", label: "运行目标节点", available: actionAvailable("creator.node.run"), inputSchema: nodeTargetSchema },
      { id: "creator.node.retry", label: "重试目标节点", available: actionAvailable("creator.node.retry"), inputSchema: nodeTargetSchema },
      { id: "creator.node.cancel", label: "取消目标节点", available: actionAvailable("creator.node.cancel"), inputSchema: nodeTargetSchema },
      {
        id: "creator.publish.confirm",
        label: "明确确认执行发布",
        available: actionAvailable("creator.publish.confirm"),
        inputSchema: {
          type: "object",
          required: ["confirmed", "confirmationText"],
          properties: {
            ...nodeTargetSchema.properties,
            confirmed: { type: "boolean", const: true },
            confirmationText: { type: "string", const: "确认发布" },
            note: { type: "string" },
          },
        },
      },
      {
        id: "creator.editor.launch",
        label: "打开节点编辑器",
        available: actionAvailable("creator.editor.launch"),
        inputSchema: {
          type: "object",
          required: ["editorId"],
          properties: {
            ...nodeTargetSchema.properties,
            sessionId: { type: "string" },
            editorId: { type: "string" },
          },
        },
      },
      {
        id: "creator.editor.save",
        label: "保存编辑器产物",
        available: actionAvailable("creator.editor.save"),
        inputSchema: {
          type: "object",
          required: ["outputs"],
          properties: {
            ...nodeTargetSchema.properties,
            sessionId: { type: "string" },
            outputs: { type: "array" },
          },
        },
      },
      { id: "creator.editor.close", label: "关闭编辑会话", available: actionAvailable("creator.editor.close"), inputSchema: nodeTargetSchema },
      {
        id: "creator.node.configure",
        label: "配置当前节点参数",
        available: actionAvailable("creator.node.configure"),
        inputSchema: {
          type: "object",
          required: ["parameters"],
          properties: {
            ...nodeTargetSchema.properties,
            parameters: { type: "object", additionalProperties: true },
            replace: { type: "boolean" },
          },
        },
      },
      {
        id: "creator.node.submit-feedback",
        label: "提交修改反馈",
        available: actionAvailable("creator.node.submit-feedback"),
        inputSchema: {
          type: "object",
          required: ["message"],
          properties: { ...nodeTargetSchema.properties, message: { type: "string" } },
        },
      },
      { id: "creator.node.approve", label: "审核通过目标节点", available: actionAvailable("creator.node.approve"), inputSchema: nodeTargetSchema },
      {
        id: "creator.node.request-changes",
        label: "退回当前节点",
        available: actionAvailable("creator.node.request-changes"),
        inputSchema: {
          type: "object",
          properties: { ...nodeTargetSchema.properties, message: { type: "string" } },
        },
      },
      {
        id: "creator.material.attach",
        label: "向当前节点补充素材",
        available: actionAvailable("creator.material.attach"),
        inputSchema: {
          type: "object",
          required: ["type", "path"],
          properties: {
            ...nodeTargetSchema.properties,
            type: { type: "string" },
            path: { type: "string" },
            label: { type: "string" },
          },
        },
      },
      {
        id: "creator.artifact.register",
        label: "登记当前节点交付物",
        available: actionAvailable("creator.artifact.register"),
        inputSchema: {
          type: "object",
          required: ["type", "path"],
          properties: {
            ...nodeTargetSchema.properties,
            type: { type: "string" },
            path: { type: "string" },
            label: { type: "string" },
          },
        },
      },
      {
        id: "creator.handoff.create",
        label: "转接交付物到目标节点",
        available: actionAvailable("creator.handoff.create"),
        inputSchema: {
          type: "object",
          required: ["targetStageId", "targetNodeId"],
          properties: {
            ...nodeTargetSchema.properties,
            targetStageId: { type: "string" },
            targetNodeId: { type: "string" },
            artifactIds: { type: "array", items: { type: "string" } },
          },
        },
      },
      { id: "creator.workflow.continue", label: "从已完成节点进入下一节点", available: actionAvailable("creator.workflow.continue"), inputSchema: nodeTargetSchema },
      {
        id: "creator.marketplace.check-compatibility",
        label: "检查超市能力与工作流节点的兼容性",
        available: true,
        inputSchema: {
          type: "object",
          required: ["itemId", "itemKind"],
          properties: {
            itemId: { type: "string" },
            itemKind: { type: "string", enum: ["project", "skill", "pipeline", "template"] },
            ...nodeTargetSchema.properties,
          },
        },
      },
      {
        id: "creator.marketplace.save-preset",
        label: "将超市能力保存为版本化预设",
        available: true,
        inputSchema: {
          type: "object",
          required: ["name", "itemId", "itemKind"],
          properties: {
            name: { type: "string" },
            itemId: { type: "string" },
            itemKind: { type: "string", enum: ["project", "skill", "pipeline", "template"] },
            ...nodeTargetSchema.properties,
            parameters: { type: "object", additionalProperties: true },
          },
        },
      },
      {
        id: "creator.marketplace.list-preset-versions",
        label: "查看能力预设的历史版本",
        available: true,
        inputSchema: {
          type: "object",
          required: ["presetId"],
          properties: { presetId: { type: "string" } },
        },
      },
      {
        id: "creator.marketplace.update-preset",
        label: "用新参数生成能力预设的新版本",
        available: true,
        inputSchema: {
          type: "object",
          required: ["presetId", "name", "parameters", "expectedVersion"],
          properties: {
            presetId: { type: "string" },
            name: { type: "string" },
            ...nodeTargetSchema.properties,
            parameters: { type: "object", additionalProperties: true },
            expectedVersion: { type: "integer", minimum: 1 },
          },
        },
      },
      {
        id: "creator.marketplace.apply-preset",
        label: "将能力预设应用到目标节点",
        available: actionAvailable("creator.marketplace.apply-preset"),
        inputSchema: {
          type: "object",
          required: ["presetId", "stageId", "nodeId"],
          properties: {
            presetId: { type: "string" },
            presetVersion: { type: "integer", minimum: 1 },
            ...nodeTargetSchema.properties,
          },
        },
      },
      { id: "creator.capability.detect", label: "检测本地创作能力", available: true, inputSchema: { type: "object" } },
      { id: "creator.run.refresh", label: "刷新当前任务", available: hasRun, inputSchema: { type: "object" } },
    ],
    tasks: snapshot?.stages.flatMap((stage) => stage.nodes)
      .filter((node) => node.status === "running")
      .map((node) => ({ id: `${snapshot.run.runId}:${node.id}`, status: node.status, actionId: "creator.node.run" })) ?? [],
  };
}
