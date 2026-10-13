import {
  Archive,
  ArrowRight,
  Bot,
  Check,
  ChevronRight,
  CircleDot,
  GitBranch,
  Grid3X3,
  History,
  KeyRound,
  Network,
  Pause,
  Pin,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Rows3,
  Save,
  ShieldCheck,
  Square,
  Trash2,
  UserRoundCog,
  UsersRound,
  X,
} from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import { connectModHost, type ModHostConnection } from "@newma-desk/mod-sdk";

import { workflowClient } from "./api";
import type {
  OrganizationWorkflowCanvasProps,
  WorkflowCanvasAdd,
  WorkflowCanvasMove,
} from "./canvas/WorkflowCanvas";
import { axisLetter, matrixCoordinate, moveOrSwapNode, resolveWorkflowMatrix, summarizeTemplateVersionDiff } from "./matrix";
import type {
  DelegationGrant,
  Identity,
  Principal,
  WorkflowArtifact,
  WorkflowEdge,
  WorkflowLaneDefinition,
  WorkflowNodeDefinition,
  WorkflowNodeRun,
  WorkflowOverview,
  WorkflowRun,
  WorkflowRunSnapshot,
  WorkflowRuntimeExecution,
  WorkflowRuntimeJob,
  WorkflowRuntimeTrigger,
  WorkflowScope,
  WorkflowStageDefinition,
  WorkflowTemplate,
  WorkflowTemplateVersion,
  WorkflowWorkspace,
} from "./types";

const MOD_IDS: Record<WorkflowWorkspace, string> = {
  overview: "workflow-overview",
  designer: "workflow-designer",
  runs: "workflow-runs",
  delegations: "workflow-delegations",
  artifacts: "workflow-artifacts",
  audit: "workflow-audit",
  settings: "workflow-settings",
};

const LazyOrganizationWorkflowCanvas = lazy(async () => {
  const module = await import("./canvas/WorkflowCanvas");
  return { default: module.OrganizationWorkflowCanvas };
});

function WorkflowCanvas(props: OrganizationWorkflowCanvasProps) {
  return <Suspense fallback={<div className={`organization-flow-canvas is-loading ${props.editable ? "is-editable" : "is-readonly"}`} role="status"><span>正在加载流程画布…</span></div>}>
    <LazyOrganizationWorkflowCanvas {...props} />
  </Suspense>;
}

const WORKSPACE_META: Record<WorkflowWorkspace, { title: string; description: string }> = {
  overview: { title: "组织工作流", description: "在纵向业务域与横向阶段组成的画布中总览组织协作。" },
  designer: { title: "流程编排", description: "编排横竖矩阵、交叉节点、执行依赖、职能与审核 Gate。" },
  runs: { title: "运行中心", description: "在组织矩阵中领取节点、保存交付物、提交审核并推进下游。" },
  delegations: { title: "授权中心", description: "按模板、运行、节点或职能授权，支持多工作流和转授权链。" },
  artifacts: { title: "交付物", description: "查看每个节点的版本化交付物、输入谱系与失效状态。" },
  audit: { title: "审计账本", description: "追踪责任人、实际执行者、授权来源与每次状态变化。" },
  settings: { title: "组织与 Agent", description: "登记成员、服务器 Agent、角色、端点与能力标签。" },
};

const STATUS_LABELS: Record<string, string> = {
  pending: "等待前置",
  queued: "排队中",
  ready: "可领取",
  leased: "已调度",
  claimed: "已领取",
  running: "执行中",
  waiting: "等待外部结果",
  retry_wait: "等待重试",
  paused: "已暂停",
  waiting_review: "待审核",
  completed: "已完成",
  blocked: "已阻塞",
  failed: "失败",
  cancelled: "已取消",
  skipped: "已跳过",
  stale: "需重做",
  needs_rework: "需要返工",
  active: "有效",
  revoked: "已撤销",
};

const ACTION_LABELS: Record<string, string> = {
  read: "读取",
  write: "写入",
  execute: "执行",
  review: "审核",
  assign: "分配",
  delegate: "转授权",
  admin: "管理",
};

const EDGE_KIND_LABELS: Record<NonNullable<WorkflowEdge["kind"]>, string> = {
  handoff: "任务交接",
  data: "数据传递",
  condition: "条件路由",
  approval: "审核流转",
};

function workflowEdgeKey(source: string, target: string) {
  return `${source}->${target}`;
}

function normalizeWorkflowEdge(edge: WorkflowEdge): WorkflowEdge {
  return {
    source: edge.source,
    target: edge.target,
    name: edge.name || "",
    description: edge.description || "",
    kind: edge.kind || "handoff",
    condition: edge.condition || "",
    parameters: edge.parameters || {},
  };
}

type WorkflowEdgeDetails = Omit<WorkflowEdge, "source" | "target">;

function workflowEdgeDetailMap(edges: WorkflowEdge[]) {
  return Object.fromEntries(edges.map((edge) => {
    const normalized = normalizeWorkflowEdge(edge);
    const { source, target, ...details } = normalized;
    return [workflowEdgeKey(source, target), details];
  })) as Record<string, WorkflowEdgeDetails>;
}

function edgeParametersText(parameters?: Record<string, unknown>) {
  return Object.entries(parameters || {}).map(([key, value]) => `${key}=${typeof value === "string" ? value : JSON.stringify(value)}`).join("\n");
}

function parseEdgeParameters(value: string) {
  return Object.fromEntries(value.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
    const divider = line.indexOf("=");
    if (divider < 0) return [line, ""];
    const key = line.slice(0, divider).trim();
    const raw = line.slice(divider + 1).trim();
    if (!raw) return [key, ""];
    try { return [key, JSON.parse(raw)]; } catch { return [key, raw]; }
  }).filter(([key]) => key));
}

function workspaceFromSearch(): WorkflowWorkspace {
  const value = new URLSearchParams(window.location.search).get("workspace");
  return value && Object.hasOwn(MOD_IDS, value) ? value as WorkflowWorkspace : "overview";
}

function overviewLaneIndexFromSearch() {
  const value = new URLSearchParams(window.location.search).get("lane")?.trim().toLowerCase();
  if (!value) return null;
  const index = { a: 0, b: 1, c: 2, d: 3 }[value as "a" | "b" | "c" | "d"];
  return typeof index === "number" ? index : null;
}

function modIdFromSearch(workspace: WorkflowWorkspace) {
  const laneIndex = workspace === "overview" ? overviewLaneIndexFromSearch() : null;
  return laneIndex === null ? MOD_IDS[workspace] : `workflow-overview-lane-${["a", "b", "c", "d"][laneIndex]}`;
}

function parentOrigin() {
  if (document.referrer) {
    try { return new URL(document.referrer).origin; } catch { /* local fallback */ }
  }
  return "http://127.0.0.1:5888";
}

function displayTime(value?: string | null) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function principalName(principals: Principal[], id?: string | null) {
  return principals.find((item) => item.id === id)?.name || id || "未分配";
}

function statusLabel(status: string) {
  return STATUS_LABELS[status] || status;
}

function runStatusLabel(status: string) {
  return status === "active" ? "进行中" : statusLabel(status);
}

function scopeLabel(scope: WorkflowScope, overview: WorkflowOverview) {
  if (scope.type === "organization") return "整个组织";
  const run = scope.runId ? overview.runs.find((item) => item.id === scope.runId) : undefined;
  const template = scope.templateId ? overview.templates.find((item) => item.id === scope.templateId) : undefined;
  if (scope.type === "template") return `模板 · ${template?.name || scope.templateId}`;
  if (scope.type === "run") return `运行 · ${run?.title || scope.runId}`;
  if (scope.type === "node") return `节点 · ${run?.title || scope.runId} / ${run?.nodes.find((item) => item.id === scope.nodeId)?.name || scope.nodeId}`;
  return `职能 · ${run?.title || template?.name || ""} / ${scope.roleKey}`;
}

function buildContext(workspace: WorkflowWorkspace, overview?: WorkflowOverview, run?: WorkflowRun): ModPageContext {
  const laneIndex = workspace === "overview" ? overviewLaneIndexFromSearch() : null;
  return {
    view: { id: modIdFromSearch(workspace), title: WORKSPACE_META[workspace].title },
    visibleBlocks: workspace === "overview"
      ? [{ id: "workflow-overview-canvas", type: "workflow-canvas", title: "组织工作流画布" }]
      : [
        { id: `workflow-${workspace}-main`, type: workspace, title: WORKSPACE_META[workspace].title },
        { id: "workflow-responsibility", type: "responsibility", title: "责任与授权" },
        { id: "workflow-artifacts", type: "artifacts", title: "节点交付物" },
      ],
    selection: run ? { workflowRunId: run.id, workflowTemplateId: run.templateId } : {},
    filters: { workspace, ...(laneIndex === null ? {} : { lane: axisLetter(laneIndex) }) },
    data: {
      source: "newma-desk/workflow-control",
      freshness: "fresh",
      summary: overview?.metrics || {},
    },
    actions: [
      { id: "workflow.refresh", label: "刷新工作流", available: true, inputSchema: { type: "object", additionalProperties: false } },
      { id: "workflow.node.claim", label: "领取节点", available: Boolean(run), inputSchema: { type: "object", additionalProperties: true } },
      { id: "workflow.node.submit", label: "提交节点", available: Boolean(run), inputSchema: { type: "object", additionalProperties: true } },
    ],
    tasks: run?.nodes.filter((node) => !["completed", "skipped", "cancelled"].includes(node.status)).map((node) => {
      const actionId = ["ready", "stale"].includes(node.status)
        ? "workflow.node.claim"
        : ["claimed", "running"].includes(node.status)
          ? "workflow.node.submit"
          : node.status === "waiting_review"
            ? "workflow.node.review"
            : undefined;
      return { id: node.id, status: node.status, ...(actionId ? { actionId } : {}) };
    }) || [],
  };
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return <div className="empty-state"><Network /> <p>{children}</p></div>;
}

type MatrixNode = WorkflowNodeDefinition | WorkflowNodeRun;

function WorkflowMatrixBoard({ lanes: sourceLanes, stages: sourceStages, nodes: sourceNodes, edges, principals, selectedNodeId, activeStageId, onStageChange, onSelectNode }: { lanes: WorkflowLaneDefinition[]; stages: WorkflowStageDefinition[]; nodes: MatrixNode[]; edges: WorkflowEdge[]; principals?: Principal[]; selectedNodeId?: string; activeStageId: string; onStageChange(value: string): void; onSelectNode(id: string): void }) {
  const { lanes, stages, nodes } = resolveWorkflowMatrix(sourceNodes, sourceLanes, sourceStages);
  return <div className="workflow-matrix-board">
    <nav className="stage-tabs" aria-label="横向流程阶段"><button className={!activeStageId ? "active" : ""} onClick={() => onStageChange("")}><Grid3X3 />全流程</button>{stages.map((stage, index) => <button className={activeStageId === stage.id ? "active" : ""} key={stage.id} onClick={() => onStageChange(activeStageId === stage.id ? "" : stage.id)}><span>{index + 1}</span>{stage.name}</button>)}</nav>
    <WorkflowCanvas lanes={lanes} stages={stages} nodes={nodes} edges={edges} principals={principals} selectedNodeId={selectedNodeId} activeStageId={activeStageId} showCoordinates={false} showHud={false} showAxes onSelectNode={onSelectNode} />
  </div>;
}

function OverviewView({ overview, busy, actingPrincipalId, onActingPrincipalChange, onRefresh }: { overview: WorkflowOverview; busy: boolean; actingPrincipalId: string; onActingPrincipalChange(value: string): void; onRefresh(): void }) {
  const liveRuns = overview.runs.filter((run) => !["completed", "cancelled"].includes(run.status));
  const [sourceId, setSourceId] = useState(liveRuns[0] ? `run:${liveRuns[0].id}` : overview.templates[0] ? `template:${overview.templates[0].id}` : "");
  const [activeStageId, setActiveStageId] = useState("");
  const run = sourceId.startsWith("run:") ? overview.runs.find((item) => item.id === sourceId.slice(4)) : undefined;
  const requestedTemplateId = sourceId.startsWith("template:") ? sourceId.slice(9) : run?.templateId;
  const template = overview.templates.find((item) => item.id === requestedTemplateId) || overview.templates[0];
  const matrixSource = run || template;
  const matrix = useMemo(() => matrixSource ? resolveWorkflowMatrix(matrixSource.nodes, matrixSource.lanes, matrixSource.stages) : undefined, [matrixSource]);
  const laneIndex = overviewLaneIndexFromSearch();
  const activeLaneId = laneIndex === null ? "" : matrix?.lanes[laneIndex]?.id || "";
  const [selectedNodeId, setSelectedNodeId] = useState("");
  useEffect(() => {
    const sourceExists = sourceId.startsWith("run:")
      ? overview.runs.some((item) => item.id === sourceId.slice(4))
      : overview.templates.some((item) => item.id === sourceId.slice(9));
    if (!sourceExists) setSourceId(liveRuns[0] ? `run:${liveRuns[0].id}` : overview.templates[0] ? `template:${overview.templates[0].id}` : "");
  }, [liveRuns, overview.runs, overview.templates, sourceId]);
  useEffect(() => {
    if (matrix && selectedNodeId && !matrix.nodes.some((node) => node.id === selectedNodeId)) setSelectedNodeId("");
  }, [matrix, selectedNodeId]);
  return <div className="overview-canvas-shell">
    <div className="overview-canvas-toolbar">
      <label className="overview-toolbar-select overview-source-select"><Network /><select aria-label="画布来源" value={sourceId} disabled={!overview.runs.length && !overview.templates.length} onChange={(event) => { setSourceId(event.target.value); setActiveStageId(""); setSelectedNodeId(""); }}>
        {!overview.runs.length && !overview.templates.length ? <option value="">暂无画布</option> : null}
        {overview.runs.length ? <optgroup label="运行实例">{overview.runs.map((item) => <option value={`run:${item.id}`} key={item.id}>{item.title} · {runStatusLabel(item.status)}</option>)}</optgroup> : null}
        {overview.templates.length ? <optgroup label="模板预览">{overview.templates.map((item) => <option value={`template:${item.id}`} key={item.id}>{item.name} · v{item.currentVersion}</option>)}</optgroup> : null}
      </select></label>
      {matrix ? <nav className="overview-stage-tabs" aria-label="横向流程阶段"><button className={!activeStageId ? "active" : ""} onClick={() => setActiveStageId("")}><Grid3X3 />全流程</button>{matrix.stages.map((stage, index) => <button className={activeStageId === stage.id ? "active" : ""} key={stage.id} onClick={() => setActiveStageId(activeStageId === stage.id ? "" : stage.id)}><span>{index + 1}</span>{stage.name}</button>)}</nav> : <span />}
      <div className="overview-toolbar-actions"><label className="overview-toolbar-select overview-identity-select"><UserRoundCog /><select aria-label="当前执行身份" value={actingPrincipalId} onChange={(event) => onActingPrincipalChange(event.target.value)}>{overview.principals.map((principal) => <option value={principal.id} key={principal.id}>{principal.kind === "server_agent" ? "Agent · " : "成员 · "}{principal.name}</option>)}</select></label><button className="icon-button" disabled={busy} onClick={onRefresh} title="刷新"><RefreshCw className={busy ? "spin" : ""} /></button></div>
    </div>
    {matrixSource && matrix ? <WorkflowCanvas lanes={matrix.lanes} stages={matrix.stages} nodes={matrix.nodes} edges={matrixSource.edges} principals={overview.principals} selectedNodeId={selectedNodeId} activeLaneId={activeLaneId} activeStageId={activeStageId} showCoordinates={false} showHud={false} onSelectNode={setSelectedNodeId} /> : <EmptyState>请先建立一个工作流模板。</EmptyState>}
  </div>;
}

interface DraftNode extends WorkflowNodeDefinition { predecessors: string[] }

interface MatrixDraft {
  lanes: WorkflowLaneDefinition[];
  stages: WorkflowStageDefinition[];
  nodes: DraftNode[];
}

type TemplateInput = {
  name: string;
  description: string;
  lanes: WorkflowLaneDefinition[];
  stages: WorkflowStageDefinition[];
  nodes: WorkflowNodeDefinition[];
  edges: WorkflowEdge[];
};

function blankMatrix(): MatrixDraft {
  const lanes = [
    { id: "mandate", name: "任务与立项", description: "定义问题与验收口径" },
    { id: "production", name: "专业生产", description: "完成核心研究或创作" },
    { id: "governance", name: "复核与决策", description: "挑战、审核与拍板" },
    { id: "delivery", name: "交付与运营", description: "交付、归档与持续跟踪" },
  ];
  const stages = [
    { id: "intake", name: "受理", description: "明确目标" },
    { id: "work", name: "执行", description: "形成成果" },
    { id: "review", name: "复核", description: "检查与决策" },
    { id: "delivery", name: "交付", description: "验收归档" },
  ];
  const nodes: DraftNode[] = [
    { id: "intake", name: "任务受理", description: "确认目标、范围与验收口径。", roleKey: "sponsor", kind: "task", requiresReview: false, outputs: ["任务说明"], laneId: "mandate", stageId: "intake", promotedToMenu: true, predecessors: [] },
    { id: "work", name: "专业执行", description: "完成核心职能并沉淀阶段成果。", roleKey: "owner", kind: "task", requiresReview: false, outputs: ["阶段成果"], laneId: "production", stageId: "work", promotedToMenu: false, predecessors: ["intake"] },
    { id: "review", name: "复核决策", description: "审核事实、分歧与交付条件。", roleKey: "reviewer", kind: "gate", requiresReview: false, outputs: ["决策记录"], laneId: "governance", stageId: "review", promotedToMenu: true, predecessors: ["work"] },
    { id: "delivery", name: "审核交付", description: "完成验收、归档与后续安排。", roleKey: "delivery_owner", kind: "task", requiresReview: true, outputs: ["正式交付物"], laneId: "delivery", stageId: "delivery", promotedToMenu: true, predecessors: ["review"] },
  ];
  return { lanes, stages, nodes };
}

function ProcessInspector({ edge, nodes, parameterText, onPatch, onParameters, onClose, onRemove }: { edge: WorkflowEdge; nodes: DraftNode[]; parameterText: string; onPatch(patch: WorkflowEdgeDetails): void; onParameters(value: string): void; onClose(): void; onRemove(): void }) {
  const source = nodes.find((node) => node.id === edge.source);
  const target = nodes.find((node) => node.id === edge.target);
  return <aside className="node-inspector process-inspector"><header><div><span><ArrowRight /></span><div><small>PROCESS</small><h3>{edge.name || EDGE_KIND_LABELS[edge.kind || "handoff"]}</h3></div></div><div className="node-inspector-actions"><button title="关闭过程编辑器" onClick={onClose}><X /></button><button title="删除过程" onClick={onRemove}><Trash2 /></button></div></header><div className="inspector-fields">
    <div className="process-route"><span><small>FROM</small><strong>{source?.name || edge.source}</strong></span><ArrowRight /><span><small>TO</small><strong>{target?.name || edge.target}</strong></span></div>
    <label>过程名称<input value={edge.name || ""} placeholder={EDGE_KIND_LABELS[edge.kind || "handoff"]} onChange={(event) => onPatch({ name: event.target.value })} /></label>
    <label>过程类型<select value={edge.kind || "handoff"} onChange={(event) => onPatch({ kind: event.target.value as NonNullable<WorkflowEdge["kind"]> })}>{Object.entries(EDGE_KIND_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
    <label>过程说明<textarea value={edge.description || ""} placeholder="说明这一步如何把上游结果转成下游输入。" onChange={(event) => onPatch({ description: event.target.value })} /></label>
    <label>触发条件<textarea value={edge.condition || ""} placeholder="例如：score >= 80 && approved == true" onChange={(event) => onPatch({ condition: event.target.value })} /></label>
    <label>过程参数<textarea className="process-parameters" value={parameterText} placeholder={'input=artifact.current\nretry=2\nstrict=true'} onChange={(event) => onParameters(event.target.value)} /><small>每行一个 key=value，数值、布尔值和 JSON 会自动识别。</small></label>
  </div></aside>;
}

function NodeInspector({ node, nodes, lanes, stages, onPatch, onRename, onTogglePredecessor, onClose, onRemove }: { node: DraftNode; nodes: DraftNode[]; lanes: WorkflowLaneDefinition[]; stages: WorkflowStageDefinition[]; onPatch(patch: Partial<DraftNode>): void; onRename(next: string): void; onTogglePredecessor(predecessorId: string): void; onClose(): void; onRemove(): void }) {
  const serializedParameters = JSON.stringify(node.executorParameters || {}, null, 2);
  const [parameterText, setParameterText] = useState(serializedParameters);
  const [parameterError, setParameterError] = useState("");
  useEffect(() => { setParameterText(serializedParameters); setParameterError(""); }, [node.id]);
  const updateParameters = (value: string) => {
    setParameterText(value);
    try {
      const parsed = value.trim() ? JSON.parse(value) : {};
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("执行参数必须是 JSON 对象");
      setParameterError("");
      onPatch({ executorParameters: parsed as Record<string, unknown> });
    } catch (reason) {
      setParameterError(reason instanceof Error ? reason.message : "JSON 格式错误");
    }
  };
  return <aside className="node-inspector"><header><div><span>{matrixCoordinate(node.laneId, node.stageId, lanes, stages)}</span><h3>{node.name}</h3></div><div className="node-inspector-actions"><button title="关闭编辑器" onClick={onClose}><X /></button><button title="删除节点" onClick={onRemove}><Trash2 /></button></div></header><div className="inspector-fields">
    <label>节点名称<input value={node.name} onChange={(event) => onPatch({ name: event.target.value })} /></label>
    <div className="form-two"><label>节点 ID<input value={node.id} onChange={(event) => onRename(event.target.value)} /></label><label>类型<select value={node.kind} onChange={(event) => onPatch({ kind: event.target.value as DraftNode["kind"] })}><option value="task">执行节点</option><option value="review">审查节点</option><option value="gate">决策 Gate</option><option value="automation">自动化</option></select></label></div>
    <label>职能角色<input value={node.roleKey} onChange={(event) => onPatch({ roleKey: event.target.value })} /></label>
    <div className="form-two"><label>纵向业务域<select value={node.laneId} onChange={(event) => onPatch({ laneId: event.target.value })}>{lanes.map((lane) => <option disabled={nodes.some((item) => item.id !== node.id && item.laneId === lane.id && item.stageId === node.stageId)} value={lane.id} key={lane.id}>{lane.name}</option>)}</select></label><label>横向阶段<select value={node.stageId} onChange={(event) => onPatch({ stageId: event.target.value })}>{stages.map((stage) => <option disabled={nodes.some((item) => item.id !== node.id && item.laneId === node.laneId && item.stageId === stage.id)} value={stage.id} key={stage.id}>{stage.name}</option>)}</select></label></div>
    <label>节点说明<textarea value={node.description} onChange={(event) => onPatch({ description: event.target.value })} /></label>
    <label>交付物<input value={node.outputs.join(", ")} onChange={(event) => onPatch({ outputs: event.target.value.split(",").map((item) => item.trim()) })} /></label>
    <fieldset className="executor-settings"><legend>自动执行</legend><label>执行器<select value={node.executorId || ""} onChange={(event) => { const executorId = event.target.value || null; const emptyParameters = !Object.keys(node.executorParameters || {}).length; const executorParameters = executorId === "agent_runtime" && emptyParameters ? { mode: "research" } : executorId === "server_agent" && emptyParameters ? { principalId: "", prompt: "执行当前节点", profile: "deep" } : executorId === "http_capability" && emptyParameters ? { capabilityId: "market.overview", input: {} } : node.executorParameters || {}; setParameterText(JSON.stringify(executorParameters, null, 2)); onPatch({ executorId, executorParameters }); }}><option value="">人工处理</option><option value="agent_runtime">Newma / 本地 Agent</option><option value="server_agent">远程 Server Agent</option><option value="http_capability">白名单 HTTP 能力</option><option value="data_transform">数据转换</option><option value="noop">自动通过</option><option value="agent_handoff">Agent 转交</option></select></label><label>执行参数 JSON<textarea className="executor-parameters" value={parameterText} onChange={(event) => updateParameters(event.target.value)} />{parameterError ? <small className="field-error">{parameterError}</small> : <small>{node.executorId === "server_agent" ? "填写 principalId、prompt、profile；远端仍通过该 Desk 的统一 Agent Gateway 执行。" : node.executorId === "http_capability" ? "只填写已登记的 capabilityId、可选 serviceId、input 与 mapping；不能填写 URL、方法或认证头。" : "Agent 可配置 prompt、mode、capability、adapter；不填写 adapter 时使用统一运行时偏好。"}</small>}</label><div className="form-two"><label>重试次数<input type="number" min="0" max="10" value={node.retryLimit ?? 0} onChange={(event) => onPatch({ retryLimit: Number(event.target.value) })} /></label><label>重试延迟（秒）<input type="number" min="0" max="3600" value={node.retryDelaySeconds ?? 0} onChange={(event) => onPatch({ retryDelaySeconds: Number(event.target.value) })} /></label></div><label>超时（秒）<input type="number" min="1" max="86400" value={node.timeoutSeconds ?? 300} onChange={(event) => onPatch({ timeoutSeconds: Number(event.target.value) })} /></label></fieldset>
    <fieldset className="predecessor-picker"><legend>前置节点 / 过程</legend>{nodes.filter((item) => item.id !== node.id).map((item) => <label key={item.id}><input type="checkbox" checked={node.predecessors.includes(item.id)} onChange={() => onTogglePredecessor(item.id)} /><span>{matrixCoordinate(item.laneId, item.stageId, lanes, stages)}</span>{item.name}</label>)}</fieldset>
    <label className="check-label"><input type="checkbox" checked={node.requiresReview} onChange={(event) => onPatch({ requiresReview: event.target.checked })} />完成后必须审核</label><label className="check-label promoted-toggle"><input type="checkbox" checked={node.promotedToMenu} onChange={(event) => onPatch({ promotedToMenu: event.target.checked })} /><Pin />成熟节点提升为二级入口</label>
  </div></aside>;
}

function DesignerView({ overview, busy, onCreate, onVersion, onLoadVersions, onRestore }: { overview: WorkflowOverview; busy: boolean; onCreate(input: TemplateInput): Promise<void>; onVersion(templateId: string, input: TemplateInput & { expectedVersion: number; changeNote: string }): Promise<void>; onLoadVersions(templateId: string): Promise<WorkflowTemplateVersion[]>; onRestore(templateId: string, sourceVersion: number, expectedVersion: number, changeNote: string): Promise<void> }) {
  const [editingId, setEditingId] = useState("");
  const [name, setName] = useState("组织协作流程");
  const [description, setDescription] = useState("把组织任务拆成可授权、可审核、可交付的节点。 ");
  const initial = useMemo(blankMatrix, []);
  const [lanes, setLanes] = useState<WorkflowLaneDefinition[]>(initial.lanes);
  const [stages, setStages] = useState<WorkflowStageDefinition[]>(initial.stages);
  const [nodes, setNodes] = useState<DraftNode[]>(initial.nodes);
  const [selectedNodeId, setSelectedNodeId] = useState(initial.nodes[0]?.id || "");
  const [activeStageId, setActiveStageId] = useState("");
  const [changeNote, setChangeNote] = useState("调整节点与职能");
  const [versions, setVersions] = useState<WorkflowTemplateVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [edgeDetails, setEdgeDetails] = useState<Record<string, WorkflowEdgeDetails>>({});
  const [selectedEdgeKey, setSelectedEdgeKey] = useState("");
  const [edgeParameterDrafts, setEdgeParameterDrafts] = useState<Record<string, string>>({});
  const editing = overview.templates.find((item) => item.id === editingId);
  const selectedNode = nodes.find((node) => node.id === selectedNodeId);
  const draftEdges = useMemo(() => nodes.flatMap((node) => node.predecessors.map((source) => normalizeWorkflowEdge({ source, target: node.id, ...edgeDetails[workflowEdgeKey(source, node.id)] }))), [edgeDetails, nodes]);
  const selectedEdge = draftEdges.find((edge) => workflowEdgeKey(edge.source, edge.target) === selectedEdgeKey);

  const refreshVersions = async (templateId: string) => {
    setVersionsLoading(true);
    try { setVersions(await onLoadVersions(templateId)); }
    finally { setVersionsLoading(false); }
  };

  const load = (template?: WorkflowTemplate) => {
    if (!template) {
      const blank = blankMatrix();
      setEditingId(""); setName("组织协作流程"); setDescription("把组织任务拆成可授权、可审核、可交付的节点。"); setLanes(blank.lanes); setStages(blank.stages); setNodes(blank.nodes); setSelectedNodeId(blank.nodes[0]?.id || ""); setActiveStageId(""); setVersions([]); setVersionsOpen(false); setInspectorOpen(false); setEdgeDetails({}); setSelectedEdgeKey(""); setEdgeParameterDrafts({}); return;
    }
    const resolved = resolveWorkflowMatrix(template.nodes, template.lanes, template.stages);
    setEditingId(template.id); setName(template.name); setDescription(template.description);
    setLanes(resolved.lanes); setStages(resolved.stages);
    setNodes(resolved.nodes.map((node) => ({ ...node, predecessors: template.edges.filter((edge) => edge.target === node.id).map((edge) => edge.source) })));
    setEdgeDetails(workflowEdgeDetailMap(template.edges)); setSelectedEdgeKey(""); setEdgeParameterDrafts({});
    setSelectedNodeId(resolved.nodes[0]?.id || ""); setActiveStageId(""); setVersionsOpen(false); setInspectorOpen(false);
    void refreshVersions(template.id);
  };
  const patchNode = (id: string, patch: Partial<DraftNode>) => setNodes((current) => current.map((node) => node.id === id ? { ...node, ...patch } : node));
  const renameNodeId = (previous: string, next: string) => {
    setNodes((current) => current.map((node) => node.id === previous ? { ...node, id: next } : { ...node, predecessors: node.predecessors.map((id) => id === previous ? next : id) }));
    const remapKey = (key: string) => {
      const [source = "", target = ""] = key.split("->");
      return workflowEdgeKey(source === previous ? next : source, target === previous ? next : target);
    };
    setEdgeDetails((current) => Object.fromEntries(Object.entries(current).map(([key, value]) => [remapKey(key), value])));
    setEdgeParameterDrafts((current) => Object.fromEntries(Object.entries(current).map(([key, value]) => [remapKey(key), value])));
    setSelectedEdgeKey((current) => current ? remapKey(current) : "");
    setSelectedNodeId(next);
  };
  const nextId = (prefix: string, ids: string[]) => { let index = ids.length + 1; while (ids.includes(`${prefix}-${index}`)) index += 1; return `${prefix}-${index}`; };
  const addLane = () => setLanes((current) => [...current, { id: nextId("lane", current.map((item) => item.id)), name: `业务域 ${axisLetter(current.length)}`, description: "" }]);
  const addStage = () => setStages((current) => [...current, { id: nextId("stage", current.map((item) => item.id)), name: `阶段 ${current.length + 1}`, description: "" }]);
  const removeNodesFromCanvas = (removed: Set<string>) => {
    const keepEdge = (key: string) => { const [source, target] = key.split("->"); return !removed.has(source || "") && !removed.has(target || ""); };
    setNodes((current) => current.filter((node) => !removed.has(node.id)).map((node) => ({ ...node, predecessors: node.predecessors.filter((id) => !removed.has(id)) })));
    setEdgeDetails((current) => Object.fromEntries(Object.entries(current).filter(([key]) => keepEdge(key))));
    setEdgeParameterDrafts((current) => Object.fromEntries(Object.entries(current).filter(([key]) => keepEdge(key))));
    if (selectedNodeId && removed.has(selectedNodeId)) setSelectedNodeId("");
    if (selectedEdgeKey && !keepEdge(selectedEdgeKey)) { setSelectedEdgeKey(""); setInspectorOpen(false); }
  };
  const removeLane = (laneId: string) => { if (lanes.length <= 1) return; const removed = new Set(nodes.filter((node) => node.laneId === laneId).map((node) => node.id)); setLanes((current) => current.filter((lane) => lane.id !== laneId)); removeNodesFromCanvas(removed); };
  const removeStage = (stageId: string) => { if (stages.length <= 1) return; const removed = new Set(nodes.filter((node) => node.stageId === stageId).map((node) => node.id)); setStages((current) => current.filter((stage) => stage.id !== stageId)); removeNodesFromCanvas(removed); if (activeStageId === stageId) setActiveStageId(""); };
  const addNodeAt = ({ laneId, stageId, canvasX, canvasY }: WorkflowCanvasAdd) => {
    const occupied = nodes.find((node) => node.laneId === laneId && node.stageId === stageId);
    if (occupied) { setSelectedNodeId(occupied.id); setSelectedEdgeKey(""); setInspectorOpen(true); return; }
    const id = nextId("node", nodes.map((node) => node.id));
    const node: DraftNode = { id, name: "新工作节点", description: "", roleKey: "owner", kind: "task", requiresReview: false, outputs: [], laneId, stageId, promotedToMenu: false, canvasX, canvasY, predecessors: [] };
    setNodes((current) => [...current, node]); setSelectedNodeId(id); setSelectedEdgeKey(""); setInspectorOpen(true);
  };
  const removeNode = (nodeId: string) => { setNodes((current) => current.filter((node) => node.id !== nodeId).map((node) => ({ ...node, predecessors: node.predecessors.filter((id) => id !== nodeId) }))); setEdgeDetails((current) => Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(`${nodeId}->`) && !key.endsWith(`->${nodeId}`)))); setSelectedNodeId(""); setSelectedEdgeKey(""); setInspectorOpen(false); };
  const togglePredecessor = (nodeId: string, predecessorId: string) => {
    const key = workflowEdgeKey(predecessorId, nodeId);
    const exists = Boolean(selectedNode?.predecessors.includes(predecessorId));
    patchNode(nodeId, { predecessors: exists ? selectedNode!.predecessors.filter((id) => id !== predecessorId) : [...(selectedNode?.predecessors || []), predecessorId] });
    if (exists) {
      setEdgeDetails((current) => Object.fromEntries(Object.entries(current).filter(([itemKey]) => itemKey !== key)));
      if (selectedEdgeKey === key) { setSelectedEdgeKey(""); setInspectorOpen(false); }
    } else {
      setEdgeDetails((current) => ({ ...current, [key]: current[key] || { name: "任务交接", kind: "handoff", description: "", condition: "", parameters: {} } }));
    }
  };
  const patchEdge = (key: string, patch: WorkflowEdgeDetails) => setEdgeDetails((current) => ({ ...current, [key]: { ...current[key], ...patch } }));
  const selectEdge = (edge: WorkflowEdge) => {
    const key = workflowEdgeKey(edge.source, edge.target);
    setSelectedEdgeKey(key); setSelectedNodeId(""); setInspectorOpen(true);
    setEdgeParameterDrafts((current) => ({ ...current, [key]: current[key] ?? edgeParametersText(edge.parameters) }));
  };
  const removeEdge = (edge: WorkflowEdge) => {
    setNodes((current) => current.map((node) => node.id === edge.target ? { ...node, predecessors: node.predecessors.filter((id) => id !== edge.source) } : node));
    setEdgeDetails((current) => Object.fromEntries(Object.entries(current).filter(([key]) => key !== workflowEdgeKey(edge.source, edge.target))));
    setEdgeParameterDrafts((current) => Object.fromEntries(Object.entries(current).filter(([key]) => key !== workflowEdgeKey(edge.source, edge.target))));
    setSelectedEdgeKey(""); setInspectorOpen(false);
  };
  const moveCanvasNode = ({ nodeId, laneId, stageId, canvasX, canvasY }: WorkflowCanvasMove) => {
    setNodes((current) => {
      const moving = current.find((node) => node.id === nodeId);
      const occupied = current.find((node) => node.id !== nodeId && node.laneId === laneId && node.stageId === stageId);
      if (!moving) return current;
      return moveOrSwapNode(current, nodeId, laneId, stageId).map((node) => {
        if (node.id === nodeId) return { ...node, canvasX, canvasY };
        if (occupied && node.id === occupied.id) return { ...node, canvasX: null, canvasY: null };
        return node;
      });
    });
    setSelectedNodeId(nodeId); setSelectedEdgeKey("");
  };
  const connectNodes = (source: string, target: string) => {
    if (source === target) return;
    const key = workflowEdgeKey(source, target);
    setNodes((current) => current.map((node) => node.id === target
      ? { ...node, predecessors: node.predecessors.includes(source) ? node.predecessors : [...node.predecessors, source] }
      : node));
    setEdgeDetails((current) => ({
      ...current,
      [key]: current[key] || { name: "任务交接", kind: "handoff", description: "", condition: "", parameters: {} },
    }));
    setSelectedEdgeKey(key);
    setSelectedNodeId("");
    setInspectorOpen(true);
  };
  const restoreVersion = async (version: WorkflowTemplateVersion) => {
    if (!editing || version.version === editing.currentVersion) return;
    await onRestore(editing.id, version.version, editing.currentVersion, `恢复 v${version.version} · ${version.changeNote || "历史版本"}`);
    const resolved = resolveWorkflowMatrix(version.nodes, version.lanes, version.stages);
    setName(version.name); setDescription(version.description); setLanes(resolved.lanes); setStages(resolved.stages);
    setNodes(resolved.nodes.map((node) => ({ ...node, predecessors: version.edges.filter((edge) => edge.target === node.id).map((edge) => edge.source) })));
    setEdgeDetails(workflowEdgeDetailMap(version.edges)); setSelectedEdgeKey(""); setEdgeParameterDrafts({}); setInspectorOpen(false);
    setSelectedNodeId(resolved.nodes[0]?.id || ""); setActiveStageId(""); setChangeNote(`基于恢复的 v${version.version} 继续调整`);
    await refreshVersions(editing.id);
  };
  const save = async () => {
    const cleaned = nodes.map(({ predecessors: _predecessors, ...node }) => ({ ...node, outputs: node.outputs.filter(Boolean) }));
    if (editing) {
      await onVersion(editing.id, { name, description, lanes, stages, nodes: cleaned, edges: draftEdges, expectedVersion: editing.currentVersion, changeNote });
      await refreshVersions(editing.id);
    } else await onCreate({ name, description, lanes, stages, nodes: cleaned, edges: draftEdges });
  };
  return <div className="designer-layout">
    <section className="designer-shell">
      <header className="template-toolbar">
        <div className="template-picker"><GitBranch /><label><span>流程模板</span><select value={editingId} onChange={(event) => load(overview.templates.find((template) => template.id === event.target.value))}><option value="">新建流程 · 从空白编排</option>{overview.templates.map((template) => <option value={template.id} key={template.id}>{template.name} · v{template.currentVersion} · {template.nodes.length} 节点</option>)}</select></label><button className="icon-button" onClick={() => load()} title="新建模板"><Plus /></button></div>
        {editing ? <div className="version-menu"><button className={`version-toggle ${versionsOpen ? "active" : ""}`} onClick={() => setVersionsOpen((open) => !open)}><History /><span><strong>v{editing.currentVersion}</strong><small>{versions.length} 个版本</small></span><ChevronRight /></button>{versionsOpen ? <section className="template-version-history"><header><span><History /><strong>版本历史</strong></span><button title="刷新版本" disabled={versionsLoading} onClick={() => void refreshVersions(editing.id)}><RefreshCw className={versionsLoading ? "spin" : ""} /></button></header><div>{versions.map((version) => {
          const diff = summarizeTemplateVersionDiff(editing, version);
          const isCurrent = version.version === editing.currentVersion;
          return <article className={isCurrent ? "current" : ""} key={version.version}><div><strong>v{version.version}</strong><time>{displayTime(version.createdAt)}</time><p>{version.changeNote || "未填写版本说明"}</p><small>节点 +{diff.addedNodes}/-{diff.removedNodes}/~{diff.changedNodes} · 依赖 {diff.changedEdges}{diff.metadataChanged ? " · 信息" : ""}{diff.laneOrderChanged || diff.stageOrderChanged ? " · 行列" : ""}</small></div>{isCurrent ? <em>当前</em> : <button title={`恢复 v${version.version}`} disabled={busy} onClick={() => void restoreVersion(version)}><RotateCcw /></button>}</article>;
        })}{!versionsLoading && !versions.length ? <small className="version-empty">暂无版本记录</small> : null}</div></section> : null}</div> : <small className="template-draft-state">尚未保存</small>}
      </header>
      <section className="designer-canvas">
      <header className="designer-header"><div className="designer-meta-fields"><label><span>流程名称</span><input value={name} onChange={(event) => setName(event.target.value)} /></label><label><span>流程说明</span><input value={description} onChange={(event) => setDescription(event.target.value)} /></label>{editing ? <label><span>版本说明</span><input value={changeNote} onChange={(event) => setChangeNote(event.target.value)} /></label> : null}</div><div className="designer-save"><small>{lanes.length} × {stages.length} · {nodes.length} 节点</small><button className="primary-button" onClick={() => void save()} disabled={busy}><Save />{editing ? `保存 v${editing.currentVersion + 1}` : "创建模板"}</button></div></header>
      <details className="canvas-axis-manager"><summary><span><Grid3X3 /><strong>业务域与阶段</strong><small>{lanes.length} × {stages.length}，展开编辑画布坐标轴</small></span><span><button onClick={(event) => { event.preventDefault(); addLane(); }}><Plus />业务域</button><button onClick={(event) => { event.preventDefault(); addStage(); }}><Plus />阶段</button></span></summary><div className="canvas-axis-manager-body">
        <section><header><Rows3 /><strong>纵向业务域</strong></header><div>{lanes.map((lane, laneIndex) => <article key={lane.id}><span className="axis-code">{axisLetter(laneIndex)}</span><label><input value={lane.name} onChange={(event) => setLanes((current) => current.map((item) => item.id === lane.id ? { ...item, name: event.target.value } : item))} /><input value={lane.description} placeholder="业务域说明" onChange={(event) => setLanes((current) => current.map((item) => item.id === lane.id ? { ...item, description: event.target.value } : item))} /></label><button title="删除业务域" disabled={lanes.length <= 1} onClick={() => removeLane(lane.id)}><Trash2 /></button></article>)}</div></section>
        <section><header><Grid3X3 /><strong>横向阶段</strong></header><div>{stages.map((stage, index) => <article key={stage.id}><span className="axis-code">{index + 1}</span><label><input value={stage.name} onChange={(event) => setStages((current) => current.map((item) => item.id === stage.id ? { ...item, name: event.target.value } : item))} /><input value={stage.description} placeholder="阶段说明" onChange={(event) => setStages((current) => current.map((item) => item.id === stage.id ? { ...item, description: event.target.value } : item))} /></label><button title="删除阶段" disabled={stages.length <= 1} onClick={() => removeStage(stage.id)}><Trash2 /></button></article>)}</div></section>
      </div></details>
      <nav className="stage-tabs designer-stage-tabs"><button className={!activeStageId ? "active" : ""} onClick={() => setActiveStageId("")}><Grid3X3 />全景</button>{stages.map((stage, index) => <button className={activeStageId === stage.id ? "active" : ""} onClick={() => setActiveStageId(activeStageId === stage.id ? "" : stage.id)} key={stage.id}><span>{index + 1}</span>{stage.name}</button>)}</nav>
      <div className="designer-matrix-workspace">
        <WorkflowCanvas
          lanes={lanes}
          stages={stages}
          nodes={nodes}
          edges={draftEdges}
          editable
          selectedNodeId={selectedNodeId}
          selectedEdgeKey={selectedEdgeKey}
          activeStageId={activeStageId}
          onSelectNode={(id) => { setSelectedNodeId(id); setSelectedEdgeKey(""); setInspectorOpen(true); }}
          onSelectEdge={selectEdge}
          onMoveNode={moveCanvasNode}
          onConnectNodes={connectNodes}
          onAddNode={addNodeAt}
        />
        {selectedEdge && inspectorOpen ? <ProcessInspector edge={selectedEdge} nodes={nodes} parameterText={edgeParameterDrafts[selectedEdgeKey] ?? edgeParametersText(selectedEdge.parameters)} onPatch={(patch) => patchEdge(selectedEdgeKey, patch)} onParameters={(value) => { setEdgeParameterDrafts((current) => ({ ...current, [selectedEdgeKey]: value })); patchEdge(selectedEdgeKey, { parameters: parseEdgeParameters(value) }); }} onClose={() => { setSelectedEdgeKey(""); setInspectorOpen(false); }} onRemove={() => removeEdge(selectedEdge)} /> : selectedNode && inspectorOpen ? <NodeInspector key={`${editingId}:${selectedNode.id}`} node={selectedNode} nodes={nodes} lanes={lanes} stages={stages} onPatch={(patch) => patchNode(selectedNode.id, patch)} onRename={(next) => renameNodeId(selectedNode.id, next)} onTogglePredecessor={(predecessorId) => togglePredecessor(selectedNode.id, predecessorId)} onClose={() => setInspectorOpen(false)} onRemove={() => removeNode(selectedNode.id)} /> : null}
      </div>
      </section>
    </section>
  </div>;
}

function RunCreation({ overview, busy, onCreate }: { overview: WorkflowOverview; busy: boolean; onCreate(input: { templateId: string; title: string; assignments: Record<string, string>; reviewers: Record<string, string> }): Promise<void> }) {
  const [templateId, setTemplateId] = useState(overview.templates[0]?.id || "");
  const [title, setTitle] = useState("新协作任务");
  const template = overview.templates.find((item) => item.id === templateId) || overview.templates[0];
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [reviewers, setReviewers] = useState<Record<string, string>>({});
  useEffect(() => { if (!templateId && overview.templates[0]) setTemplateId(overview.templates[0].id); }, [overview.templates, templateId]);
  if (!template) return <EmptyState>请先建立一个流程模板。</EmptyState>;
  return <section className="panel run-create-panel"><header className="panel-heading"><div><span>NEW RUN</span><h2>发起工作流</h2></div><button className="primary-button" disabled={busy || !title.trim()} onClick={() => void onCreate({ templateId: template.id, title, assignments, reviewers })}><Plus />开始运行</button></header>
    <div className="run-create-fields"><label>选择模板<select value={template.id} onChange={(event) => { setTemplateId(event.target.value); setAssignments({}); setReviewers({}); }}><option value="" disabled>选择模板</option>{overview.templates.map((item) => <option value={item.id} key={item.id}>{item.name} · v{item.currentVersion}</option>)}</select></label><label>任务名称<input value={title} onChange={(event) => setTitle(event.target.value)} /></label></div>
    <div className="assignment-builder">{template.nodes.map((node) => <div key={node.id}><span><strong>{node.name}</strong><small>{node.roleKey} · {node.requiresReview ? "需要审核" : "直接推进"}</small></span><label>责任人<select value={assignments[node.id] || overview.currentPrincipal.id} onChange={(event) => setAssignments((current) => ({ ...current, [node.id]: event.target.value }))}>{overview.principals.map((principal) => <option value={principal.id} key={principal.id}>{principal.kind === "server_agent" ? "Agent · " : "成员 · "}{principal.name}</option>)}</select></label>{node.requiresReview ? <label>审核人<select value={reviewers[node.id] || overview.currentPrincipal.id} onChange={(event) => setReviewers((current) => ({ ...current, [node.id]: event.target.value }))}>{overview.principals.map((principal) => <option value={principal.id} key={principal.id}>{principal.name}</option>)}</select></label> : <span className="no-review">无需审核</span>}</div>)}</div>
  </section>;
}

function NodeDetail({ overview, snapshot, node, runtimeJob, busy, onClaim, onRelease, onSubmit, onReview, onData, onArtifact, onAssign, onRetryRuntime }: { overview: WorkflowOverview; snapshot: WorkflowRunSnapshot; node: WorkflowNodeRun; runtimeJob?: WorkflowRuntimeJob; busy: boolean; onClaim(): Promise<void>; onRelease(): Promise<void>; onSubmit(): Promise<void>; onReview(decision: "approve" | "request_changes"): Promise<void>; onData(slot: string, data: unknown): Promise<void>; onArtifact(input: { artifactKey: string; label: string; kind: string; content?: unknown; inputArtifactIds?: string[] }): Promise<void>; onAssign(accountable: string, reviewer?: string | null): Promise<void>; onRetryRuntime(): Promise<void> }) {
  const [slot, setSlot] = useState("worklog");
  const [dataText, setDataText] = useState("{\n  \"summary\": \"\"\n}");
  const [artifactKey, setArtifactKey] = useState("deliverable");
  const [artifactLabel, setArtifactLabel] = useState(node.outputs[0] || "节点交付物");
  const [artifactContent, setArtifactContent] = useState("");
  const [parents, setParents] = useState("");
  const [accountable, setAccountable] = useState(node.accountablePrincipalId);
  const [reviewer, setReviewer] = useState(node.reviewerPrincipalId || "");
  useEffect(() => { setAccountable(node.accountablePrincipalId); setReviewer(node.reviewerPrincipalId || ""); setArtifactLabel(node.outputs[0] || "节点交付物"); }, [node]);
  const currentArtifacts = snapshot.artifacts.filter((artifact) => artifact.isCurrent);
  return <aside className="node-detail panel">
    <header><div><span>{node.roleKey}</span><h2>{node.name}</h2><p>{node.description || "该节点尚未填写说明。"}</p></div><span className={`status-pill status-${node.status}`}>{statusLabel(node.status)}</span></header>
    <section className="responsibility-card"><div><small>责任人</small><strong>{principalName(overview.principals, node.accountablePrincipalId)}</strong></div><div><small>当前领取</small><strong>{node.claim ? principalName(overview.principals, node.claim.principalId) : "未领取"}</strong></div><div><small>审核人</small><strong>{principalName(overview.principals, node.reviewerPrincipalId)}</strong></div></section>
    {runtimeJob ? <section className="runtime-job-card"><header><div><Bot /><span><small>执行器</small><strong>{runtimeJob.executorId}</strong></span></div><span className={`status-pill status-${runtimeJob.status}`}>{statusLabel(runtimeJob.status)}</span></header><dl><div><dt>尝试</dt><dd>{runtimeJob.attempt} / {runtimeJob.maxAttempts}</dd></div><div><dt>超时</dt><dd>{runtimeJob.timeoutSeconds}s</dd></div><div><dt>更新时间</dt><dd>{displayTime(runtimeJob.updatedAt)}</dd></div></dl>{runtimeJob.result ? <pre>{JSON.stringify(runtimeJob.result, null, 2)}</pre> : null}{runtimeJob.error ? <pre className="runtime-error">{JSON.stringify(runtimeJob.error, null, 2)}</pre> : null}{["failed", "blocked"].includes(runtimeJob.status) ? <button disabled={busy} onClick={() => void onRetryRuntime()}><RotateCcw />重试执行</button> : null}</section> : null}
    <div className="node-actions">{["ready", "stale"].includes(node.status) ? <button className="primary-button" disabled={busy} onClick={() => void onClaim()}><CircleDot />领取节点</button> : null}{["claimed", "running"].includes(node.status) ? <><button className="primary-button" disabled={busy} onClick={() => void onSubmit()}><Check />提交节点</button><button disabled={busy} onClick={() => void onRelease()}>释放租约</button></> : null}{node.status === "waiting_review" ? <><button className="primary-button" disabled={busy} onClick={() => void onReview("approve")}><ShieldCheck />审核通过</button><button disabled={busy} onClick={() => void onReview("request_changes")}>退回修改</button></> : null}</div>
    <details open><summary>节点数据 <span>版本 {node.dataRevision}</span></summary><div className="detail-form"><label>数据槽<input value={slot} onChange={(event) => setSlot(event.target.value)} /></label><label>JSON / 文本<textarea value={dataText} onChange={(event) => setDataText(event.target.value)} /></label><button disabled={busy} onClick={() => { let value: unknown = dataText; try { value = JSON.parse(dataText); } catch { /* save as text */ } void onData(slot, value); }}><Save />保存数据版本</button></div></details>
    <details open><summary>节点交付物 <span>{node.artifactCount} 个版本</span></summary><div className="detail-form"><div className="form-two"><label>交付物键<input value={artifactKey} onChange={(event) => setArtifactKey(event.target.value)} /></label><label>类型<select value="document" disabled><option>document</option></select></label></div><label>名称<input value={artifactLabel} onChange={(event) => setArtifactLabel(event.target.value)} /></label><label>内容<textarea value={artifactContent} onChange={(event) => setArtifactContent(event.target.value)} /></label><label>输入交付物 ID<input value={parents} onChange={(event) => setParents(event.target.value)} placeholder={currentArtifacts.slice(0, 2).map((item) => item.id).join(", ")} /></label><button disabled={busy} onClick={() => void onArtifact({ artifactKey, label: artifactLabel, kind: "document", content: artifactContent, inputArtifactIds: parents.split(",").map((value) => value.trim()).filter(Boolean) })}><Archive />保存交付版本</button></div></details>
    <details><summary>责任分配 <span>授权不改变责任</span></summary><div className="detail-form"><label>责任人<select value={accountable} onChange={(event) => setAccountable(event.target.value)}>{overview.principals.map((principal) => <option key={principal.id} value={principal.id}>{principal.name}</option>)}</select></label><label>审核人<select value={reviewer} onChange={(event) => setReviewer(event.target.value)}><option value="">不指定</option>{overview.principals.map((principal) => <option key={principal.id} value={principal.id}>{principal.name}</option>)}</select></label><button disabled={busy} onClick={() => void onAssign(accountable, reviewer || null)}><UserRoundCog />更新责任快照</button></div></details>
  </aside>;
}

function RunsView({ overview, snapshot, runtimeExecution, runtimeTriggers, selectedRunId, selectedNodeId, busy, onSelectRun, onSelectNode, onCreateRun, actions, runtimeActions }: { overview: WorkflowOverview; snapshot?: WorkflowRunSnapshot; runtimeExecution?: WorkflowRuntimeExecution; runtimeTriggers: WorkflowRuntimeTrigger[]; selectedRunId: string; selectedNodeId: string; busy: boolean; onSelectRun(id: string): void; onSelectNode(id: string): void; onCreateRun(input: { templateId: string; title: string; assignments: Record<string, string>; reviewers: Record<string, string> }): Promise<void>; actions: { claim(node: WorkflowNodeRun): Promise<void>; release(node: WorkflowNodeRun): Promise<void>; submit(node: WorkflowNodeRun): Promise<void>; review(node: WorkflowNodeRun, decision: "approve" | "request_changes"): Promise<void>; data(node: WorkflowNodeRun, slot: string, value: unknown): Promise<void>; artifact(node: WorkflowNodeRun, input: { artifactKey: string; label: string; kind: string; content?: unknown; inputArtifactIds?: string[] }): Promise<void>; assign(node: WorkflowNodeRun, accountable: string, reviewer?: string | null): Promise<void> }; runtimeActions: { start(): Promise<void>; tick(): Promise<void>; pause(): Promise<void>; resume(): Promise<void>; cancel(): Promise<void>; retry(job: WorkflowRuntimeJob): Promise<void>; createTrigger(input: { triggerType: "event" | "schedule"; eventType?: string; intervalSeconds?: number; cronExpression?: string; timezone?: string }): Promise<void>; setTriggerEnabled(trigger: WorkflowRuntimeTrigger, enabled: boolean): Promise<void> } }) {
  const run = snapshot?.run;
  const selectedNode = run?.nodes.find((node) => node.id === selectedNodeId) || run?.nodes[0];
  const runtimeJob = runtimeExecution?.jobs.find((job) => job.nodeId === selectedNode?.id);
  const runtimeCounts = runtimeExecution?.jobs.reduce((counts, job) => ({ ...counts, [job.status]: (counts[job.status] || 0) + 1 }), {} as Record<string, number>) || {};
  const [activeStageId, setActiveStageId] = useState("");
  const [triggerType, setTriggerType] = useState<"event" | "schedule">("event");
  const [eventType, setEventType] = useState("research.ready");
  const [intervalSeconds, setIntervalSeconds] = useState(3600);
  const [scheduleMode, setScheduleMode] = useState<"interval" | "cron">("cron");
  const [cronExpression, setCronExpression] = useState("0 9 * * 1-5");
  const [scheduleTimezone, setScheduleTimezone] = useState("Asia/Shanghai");
  useEffect(() => { setActiveStageId(""); }, [selectedRunId]);
  return <div className="view-stack"><RunCreation overview={overview} busy={busy} onCreate={onCreateRun} />
    <section className="run-workbench">
      <article className="panel run-canvas"><header className="panel-heading"><div><span>RUN CONTROL</span><h2>横竖节点运行图</h2></div><select value={selectedRunId} onChange={(event) => onSelectRun(event.target.value)}><option value="">选择运行</option>{overview.runs.map((item) => <option key={item.id} value={item.id}>{item.title} · {runStatusLabel(item.status)}</option>)}</select></header>
        {run ? <><div className="run-title"><div><strong>{run.title}</strong><span>{overview.templates.find((item) => item.id === run.templateId)?.name} · v{run.templateVersion}</span></div><em className={`status-pill status-${run.status}`}>{runStatusLabel(run.status)} · r{run.revision}</em></div><div className="runtime-control-strip"><div className="runtime-state"><Bot /><span><strong>{runtimeExecution ? statusLabel(runtimeExecution.status) : "尚未自动运行"}</strong><small>{runtimeExecution ? `完成 ${runtimeCounts.completed || 0} · 等待 ${(runtimeCounts.waiting || 0) + (runtimeCounts.pending || 0) + (runtimeCounts.retry_wait || 0)} · 失败 ${(runtimeCounts.failed || 0) + (runtimeCounts.blocked || 0)}` : "人工节点仍可单独领取与提交"}</small></span></div><div className="runtime-buttons">{!runtimeExecution || ["completed", "failed", "cancelled"].includes(runtimeExecution.status) ? <button className="primary-button" disabled={busy} onClick={() => void runtimeActions.start()}><Play />自动运行</button> : null}{runtimeExecution?.status === "running" ? <><button disabled={busy} onClick={() => void runtimeActions.tick()}><RefreshCw />推进</button><button disabled={busy} onClick={() => void runtimeActions.pause()}><Pause />暂停</button></> : null}{runtimeExecution?.status === "paused" ? <button className="primary-button" disabled={busy} onClick={() => void runtimeActions.resume()}><Play />恢复</button> : null}{runtimeExecution && ["queued", "running", "paused"].includes(runtimeExecution.status) ? <button disabled={busy} onClick={() => void runtimeActions.cancel()}><Square />取消</button> : null}</div></div><details className="runtime-trigger-panel"><summary><span><RefreshCw />触发规则</span><small>{runtimeTriggers.length} 条</small></summary><div className="runtime-trigger-list">{runtimeTriggers.map((trigger) => <article key={trigger.id}><span><strong>{trigger.triggerType === "event" ? trigger.eventType : trigger.cronExpression ? `${trigger.cronExpression} · ${trigger.timezone}` : `每 ${trigger.intervalSeconds} 秒`}</strong><small>{trigger.triggerType === "schedule" && trigger.nextFireAt ? `下次 ${displayTime(trigger.nextFireAt)}` : trigger.triggerType === "event" ? "收到同名事件时创建新运行" : "已暂停"}</small></span><button disabled={busy} onClick={() => void runtimeActions.setTriggerEnabled(trigger, !trigger.enabled)}>{trigger.enabled ? "停用" : "启用"}</button></article>)}</div><div className="runtime-trigger-form"><select value={triggerType} onChange={(event) => setTriggerType(event.target.value as "event" | "schedule")}><option value="event">事件触发</option><option value="schedule">定时触发</option></select>{triggerType === "event" ? <input value={eventType} onChange={(event) => setEventType(event.target.value)} placeholder="事件名，如 research.ready" /> : <><select value={scheduleMode} onChange={(event) => setScheduleMode(event.target.value as "interval" | "cron")}><option value="cron">Cron</option><option value="interval">固定间隔</option></select>{scheduleMode === "cron" ? <><input value={cronExpression} onChange={(event) => setCronExpression(event.target.value)} placeholder="0 9 * * 1-5" /><input value={scheduleTimezone} onChange={(event) => setScheduleTimezone(event.target.value)} placeholder="Asia/Shanghai" /></> : <label><span>间隔秒数</span><input type="number" min={1} value={intervalSeconds} onChange={(event) => setIntervalSeconds(Number(event.target.value))} /></label>}</>}<button className="primary-button" disabled={busy || (triggerType === "event" ? !eventType.trim() : scheduleMode === "cron" ? !cronExpression.trim() || !scheduleTimezone.trim() : intervalSeconds < 1)} onClick={() => void runtimeActions.createTrigger(triggerType === "event" ? { triggerType, eventType: eventType.trim() } : scheduleMode === "cron" ? { triggerType, cronExpression: cronExpression.trim(), timezone: scheduleTimezone.trim() } : { triggerType, intervalSeconds })}><Plus />添加规则</button></div></details><WorkflowMatrixBoard lanes={run.lanes} stages={run.stages} nodes={run.nodes} edges={run.edges} principals={overview.principals} selectedNodeId={selectedNode?.id} activeStageId={activeStageId} onStageChange={setActiveStageId} onSelectNode={onSelectNode} /></> : <EmptyState>选择一个运行，查看节点与责任。</EmptyState>}
      </article>
      {run && selectedNode ? <NodeDetail overview={overview} snapshot={snapshot} node={selectedNode} runtimeJob={runtimeJob} busy={busy} onClaim={() => actions.claim(selectedNode)} onRelease={() => actions.release(selectedNode)} onSubmit={() => actions.submit(selectedNode)} onReview={(decision) => actions.review(selectedNode, decision)} onData={(slot, value) => actions.data(selectedNode, slot, value)} onArtifact={(input) => actions.artifact(selectedNode, input)} onAssign={(accountable, reviewer) => actions.assign(selectedNode, accountable, reviewer)} onRetryRuntime={() => runtimeJob ? runtimeActions.retry(runtimeJob) : Promise.resolve()} /> : null}
    </section>
  </div>;
}

function DelegationsView({ overview, busy, onCreate, onRevoke }: { overview: WorkflowOverview; busy: boolean; onCreate(input: { delegatePrincipalId: string; scope: WorkflowScope; actions: string[]; allowRedelegate: boolean; maxRedelegationDepth: number }): Promise<void>; onRevoke(id: string): Promise<void> }) {
  const [delegateId, setDelegateId] = useState(overview.principals.find((item) => item.id !== overview.currentPrincipal.id)?.id || "");
  const [scopeType, setScopeType] = useState<WorkflowScope["type"]>("run");
  const [templateId, setTemplateId] = useState(overview.templates[0]?.id || "");
  const [runId, setRunId] = useState(overview.runs[0]?.id || "");
  const run = overview.runs.find((item) => item.id === runId);
  const [nodeId, setNodeId] = useState(run?.nodes[0]?.id || "");
  const [roleKey, setRoleKey] = useState(run?.nodes[0]?.roleKey || "");
  const [actions, setActions] = useState(["read", "write", "execute"]);
  const [redelegate, setRedelegate] = useState(false);
  useEffect(() => { const next = overview.runs.find((item) => item.id === runId); if (next && !next.nodes.some((node) => node.id === nodeId)) setNodeId(next.nodes[0]?.id || ""); if (next && !next.nodes.some((node) => node.roleKey === roleKey)) setRoleKey(next.nodes[0]?.roleKey || ""); }, [nodeId, overview.runs, roleKey, runId]);
  const buildScope = (): WorkflowScope => {
    if (scopeType === "organization") return { type: "organization" };
    if (scopeType === "template") return { type: "template", templateId };
    if (scopeType === "run") return { type: "run", runId };
    if (scopeType === "node") return { type: "node", runId, nodeId };
    return { type: "role", runId, roleKey };
  };
  const toggleAction = (action: string) => setActions((current) => current.includes(action) ? current.filter((item) => item !== action) : [...current, action]);
  return <div className="delegation-layout">
    <section className="panel delegation-form"><header className="panel-heading"><div><span>DELEGATION GRANT</span><h2>新建授权</h2></div><KeyRound /></header>
      <p className="explain-box">授权只覆盖执行职能，不转移原责任。授权者不能授出自己没有的范围或动作。</p>
      <label>被授权人<select value={delegateId} onChange={(event) => setDelegateId(event.target.value)}><option value="">选择成员或 Agent</option>{overview.principals.filter((item) => item.id !== overview.currentPrincipal.id).map((principal) => <option value={principal.id} key={principal.id}>{principal.kind === "server_agent" ? "Agent · " : "成员 · "}{principal.name}</option>)}</select></label>
      <label>授权范围<select value={scopeType} onChange={(event) => setScopeType(event.target.value as WorkflowScope["type"])}><option value="organization">整个组织</option><option value="template">流程模板</option><option value="run">单个运行</option><option value="node">单个节点</option><option value="role">运行中的职能</option></select></label>
      {scopeType === "template" ? <label>模板<select value={templateId} onChange={(event) => setTemplateId(event.target.value)}>{overview.templates.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> : null}
      {["run", "node", "role"].includes(scopeType) ? <label>工作流运行<select value={runId} onChange={(event) => setRunId(event.target.value)}><option value="">选择运行</option>{overview.runs.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label> : null}
      {scopeType === "node" ? <label>节点<select value={nodeId} onChange={(event) => setNodeId(event.target.value)}>{run?.nodes.map((node) => <option key={node.id} value={node.id}>{node.name}</option>)}</select></label> : null}
      {scopeType === "role" ? <label>职能<select value={roleKey} onChange={(event) => setRoleKey(event.target.value)}>{[...new Set(run?.nodes.map((node) => node.roleKey) || [])].map((role) => <option key={role} value={role}>{role}</option>)}</select></label> : null}
      <fieldset><legend>允许动作</legend><div className="action-checks">{Object.entries(ACTION_LABELS).map(([action, label]) => <label key={action}><input type="checkbox" checked={actions.includes(action)} onChange={() => toggleAction(action)} />{label}</label>)}</div></fieldset>
      <label className="check-label"><input type="checkbox" checked={redelegate} onChange={(event) => { setRedelegate(event.target.checked); setActions((current) => event.target.checked ? [...new Set([...current, "delegate"])] : current); }} />允许被授权人继续转授权 1 层</label>
      <button className="primary-button" disabled={busy || !delegateId || !actions.length} onClick={() => void onCreate({ delegatePrincipalId: delegateId, scope: buildScope(), actions, allowRedelegate: redelegate, maxRedelegationDepth: redelegate ? 1 : 0 })}><ShieldCheck />创建授权</button>
    </section>
    <section className="panel grant-ledger"><header className="panel-heading"><div><span>GRANT LEDGER</span><h2>授权关系</h2></div><small>{overview.grants.length} 条</small></header>
      <div className="grant-list">{overview.grants.length ? overview.grants.map((grant) => <article key={grant.id} className={grant.status !== "active" ? "revoked" : ""}><header><span className={`status-pill status-${grant.status}`}>{statusLabel(grant.status)}</span><small>{displayTime(grant.createdAt)}</small></header><div className="grant-route"><strong>{principalName(overview.principals, grant.delegatorPrincipalId)}</strong><ChevronRight /><strong>{principalName(overview.principals, grant.delegatePrincipalId)}</strong></div><p>{scopeLabel(grant.scope, overview)}</p><div className="grant-actions">{grant.actions.map((action) => <span key={action}>{ACTION_LABELS[action] || action}</span>)}</div>{grant.parentGrantId ? <small>来自上游授权 {grant.parentGrantId}</small> : <small>直接责任或管理权限</small>}{grant.status === "active" ? <button disabled={busy} onClick={() => void onRevoke(grant.id)}>撤销并级联</button> : null}</article>) : <EmptyState>暂无授权记录。</EmptyState>}</div>
    </section>
  </div>;
}

function ArtifactsView({ overview, artifacts }: { overview: WorkflowOverview; artifacts: WorkflowArtifact[] }) {
  return <section className="panel"><header className="collection-toolbar"><span><Archive />当前有效版本</span><small>{artifacts.length} 个</small></header>
    <div className="artifact-grid">{artifacts.length ? artifacts.map((artifact) => {
      const run = overview.runs.find((item) => item.id === artifact.runId);
      const node = run?.nodes.find((item) => item.id === artifact.nodeId);
      return <article key={artifact.id} className={artifact.stale ? "stale" : ""}><header><Archive /><span>{artifact.kind}</span><em>v{artifact.version}</em></header><h3>{artifact.label}</h3><p>{run?.title || artifact.runId} · {node?.name || artifact.nodeId}</p><dl><div><dt>生产者</dt><dd>{principalName(overview.principals, artifact.createdBy)}</dd></div><div><dt>输入引用</dt><dd>{artifact.inputArtifactIds.length}</dd></div><div><dt>状态</dt><dd>{artifact.stale ? "上游变化，需重做" : "当前有效"}</dd></div></dl><small>{artifact.id}</small></article>;
    }) : <EmptyState>节点保存交付物后会在这里形成版本库。</EmptyState>}</div>
  </section>;
}

function AuditView({ overview }: { overview: WorkflowOverview }) {
  return <section className="panel"><header className="collection-toolbar"><span><History />最近事件</span><small>{overview.recentEvents.length} 条</small></header>
    <div className="audit-table"><div className="audit-row head"><span>时间</span><span>事件</span><span>实际执行者</span><span>责任人</span><span>授权来源</span><span>详情</span></div>{overview.recentEvents.map((event) => <div className="audit-row" key={event.sequence}><span>{displayTime(event.createdAt)}</span><strong>{event.type}</strong><span>{principalName(overview.principals, event.actorPrincipalId)}</span><span>{principalName(overview.principals, event.accountablePrincipalId)}</span><span>{event.delegationGrantId || "直接权限"}</span><code>{JSON.stringify(event.payload)}</code></div>)}</div>
  </section>;
}

function SettingsView({ overview, busy, onCreate }: { overview: WorkflowOverview; busy: boolean; onCreate(input: { kind: "human" | "server_agent"; name: string; role: string; endpoint?: string; externalRef?: string; capabilities?: string[] }): Promise<void> }) {
  const [kind, setKind] = useState<"human" | "server_agent">("server_agent");
  const [name, setName] = useState("研究执行 Agent");
  const [endpoint, setEndpoint] = useState("");
  const [capabilities, setCapabilities] = useState("research, writing, workflow.execute");
  return <div className="settings-layout"><section className="panel principal-form"><header className="panel-heading"><div><span>PRINCIPAL REGISTRY</span><h2>登记成员或 Agent</h2></div><UsersRound /></header><label>主体类型<select value={kind} onChange={(event) => { const nextKind = event.target.value as typeof kind; setKind(nextKind); if (nextKind === "server_agent" && !capabilities.includes("workflow.execute")) setCapabilities([capabilities, "workflow.execute"].filter(Boolean).join(", ")); }}><option value="server_agent">服务器 Agent</option><option value="human">组织成员</option></select></label><label>显示名称<input value={name} onChange={(event) => setName(event.target.value)} /></label>{kind === "server_agent" ? <label>远端 Desk API<input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="http://127.0.0.1:8911" /><small>不是模型或 Hermes 地址；远端 Desk 会继续按统一 Agent 设置路由。</small></label> : null}<label>能力标签<input value={capabilities} onChange={(event) => setCapabilities(event.target.value)} /></label><button className="primary-button" disabled={busy || !name.trim()} onClick={() => void onCreate({ kind, name, role: "member", endpoint: endpoint || undefined, capabilities: capabilities.split(",").map((item) => item.trim()).filter(Boolean) })}><Plus />登记主体</button></section>
    <section className="panel"><header className="panel-heading"><div><span>ORGANIZATION</span><h2>{overview.organization.name}</h2></div><small>{overview.principals.length} 个主体</small></header><div className="principal-list">{overview.principals.map((principal) => <article key={principal.id}><div className={principal.kind === "server_agent" ? "agent-avatar" : "human-avatar"}>{principal.kind === "server_agent" ? <Bot /> : <UsersRound />}</div><div><strong>{principal.name}</strong><span>{principal.id}</span></div><em>{principal.role}</em><div className="capability-tags">{principal.capabilities.map((item) => <span key={item}>{item}</span>)}</div><small>{principal.endpoint || principal.externalRef || "本地身份"}</small></article>)}</div></section></div>;
}

type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;

export function WorkflowCenterApp() {
  const workspace = workspaceFromSearch();
  const modId = modIdFromSearch(workspace);
  const embeddedInDesk = window.self !== window.top;
  const [identity, setIdentity] = useState<Identity | undefined>(() => window.self === window.top ? { userId: "local-user", workspaceId: "local-workspace" } : undefined);
  const [actingPrincipalId, setActingPrincipalId] = useState("");
  const [overview, setOverview] = useState<WorkflowOverview>();
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [snapshot, setSnapshot] = useState<WorkflowRunSnapshot>();
  const [runtimeExecution, setRuntimeExecution] = useState<WorkflowRuntimeExecution>();
  const [runtimeTriggers, setRuntimeTriggers] = useState<WorkflowRuntimeTrigger[]>([]);
  const [artifacts, setArtifacts] = useState<WorkflowArtifact[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [host, setHost] = useState<EmbeddedHost>();
  const client = useMemo(() => identity ? workflowClient(identity, actingPrincipalId) : undefined, [actingPrincipalId, identity]);
  const contextRef = useRef<ModPageContext>(buildContext(workspace));
  const actionRef = useRef<(actionId: string, input: Record<string, unknown>) => Promise<unknown>>(async () => ({}));

  const loadRun = useCallback(async (runId = selectedRunId) => {
    if (!client || !runId) { setSnapshot(undefined); setRuntimeExecution(undefined); setRuntimeTriggers([]); return undefined; }
    const [next, runtimeList, triggerList] = await Promise.all([client.run(runId), client.runtimeExecutions(runId), client.runtimeTriggers(runId)]);
    const latestRuntime = runtimeList.executions[0];
    const nextRuntime = latestRuntime ? await client.runtimeExecution(latestRuntime.id) : undefined;
    setSnapshot(next);
    setRuntimeExecution(nextRuntime);
    setRuntimeTriggers(triggerList.triggers);
    setSelectedNodeId((current) => next.run.nodes.some((node) => node.id === current) ? current : next.run.nodes.find((node) => !["completed", "pending"].includes(node.status))?.id || next.run.nodes[0]?.id || "");
    return next;
  }, [client, selectedRunId]);

  const refresh = useCallback(async () => {
    if (!client) return;
    setError("");
    const next = await client.overview();
    if (workspace === "audit") next.recentEvents = (await client.events()).events;
    setOverview(next);
    if (!actingPrincipalId || !next.principals.some((item) => item.id === actingPrincipalId)) setActingPrincipalId(next.currentPrincipal.id);
    const nextRunId = next.runs.some((item) => item.id === selectedRunId) ? selectedRunId : next.runs[0]?.id || "";
    setSelectedRunId(nextRunId);
    if (workspace === "artifacts") setArtifacts((await client.artifacts()).artifacts);
    if (nextRunId) await loadRun(nextRunId);
  }, [actingPrincipalId, client, loadRun, selectedRunId, workspace]);

  useEffect(() => { if (!client) return; let active = true; setLoading(true); void refresh().catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "工作流读取失败"); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [client, refresh]);

  useEffect(() => {
    let active = true; let connection: ModHostConnection | undefined;
    void connectModHost({ modId, parentOrigin: parentOrigin(), sdkVersion: "0.1.0", capabilities: ["actions", "context", "theme"] }).then((next) => {
      if (!active) { next.close(); return; }
      connection = next; if (!next.embedded) return;
      setHost(next); setActingPrincipalId(""); setIdentity({ userId: next.config.user.id, workspaceId: next.config.workspace.id });
      next.subscribe((config) => { setActingPrincipalId(""); setIdentity({ userId: config.user.id, workspaceId: config.workspace.id }); });
      next.setContextProvider(() => contextRef.current);
      next.setUiActionHandler((actionId, input) => actionRef.current(actionId, input));
    }).catch(() => undefined);
    return () => { active = false; connection?.close(); setHost(undefined); };
  }, [modId]);

  const runMutation = useCallback(async <T,>(operation: () => Promise<T>, runId = selectedRunId): Promise<T> => {
    setBusy(true); setError("");
    try { const result = await operation(); await refresh(); if (runId) await loadRun(runId); return result; }
    catch (reason) { const message = reason instanceof Error ? reason.message : "工作流操作失败"; setError(message); throw reason; }
    finally { setBusy(false); }
  }, [loadRun, refresh, selectedRunId]);

  useEffect(() => {
    if (!client || workspace !== "runs" || !runtimeExecution || !["queued", "running"].includes(runtimeExecution.status) || !selectedRunId) return;
    const timer = window.setTimeout(() => {
      void loadRun(selectedRunId).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "运行状态刷新失败"));
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [client, loadRun, runtimeExecution, selectedRunId, workspace]);

  const selectedNode = snapshot?.run.nodes.find((node) => node.id === selectedNodeId);
  const operations = {
    claim: async (node: WorkflowNodeRun) => { if (client && snapshot) await runMutation(() => client.claimNode(snapshot.run.id, node.id, snapshot.run.revision)); },
    release: async (node: WorkflowNodeRun) => { if (client && snapshot) await runMutation(() => client.releaseNode(snapshot.run.id, node.id, snapshot.run.revision)); },
    submit: async (node: WorkflowNodeRun) => { if (client && snapshot) await runMutation(() => client.submitNode(snapshot.run.id, node.id, snapshot.run.revision)); },
    review: async (node: WorkflowNodeRun, decision: "approve" | "request_changes") => { if (client && snapshot) await runMutation(() => client.reviewNode(snapshot.run.id, node.id, snapshot.run.revision, decision)); },
    data: async (node: WorkflowNodeRun, slot: string, value: unknown) => { if (client && snapshot) await runMutation(() => client.saveNodeData(snapshot.run.id, node.id, snapshot.run.revision, slot, value)); },
    artifact: async (node: WorkflowNodeRun, input: { artifactKey: string; label: string; kind: string; content?: unknown; inputArtifactIds?: string[] }) => { if (client && snapshot) await runMutation(() => client.saveArtifact(snapshot.run.id, node.id, { ...input, expectedRevision: snapshot.run.revision })); },
    assign: async (node: WorkflowNodeRun, accountable: string, reviewer?: string | null) => { if (client && snapshot) await runMutation(() => client.assignNode(snapshot.run.id, node.id, { expectedRevision: snapshot.run.revision, accountablePrincipalId: accountable, reviewerPrincipalId: reviewer })); },
  };
  const runtimeOperations = {
    start: async () => { if (client && selectedRunId) await runMutation(() => client.startRuntime(selectedRunId), selectedRunId); },
    tick: async () => { if (client && runtimeExecution) await runMutation(() => client.tickRuntime(runtimeExecution.id), selectedRunId); },
    pause: async () => { if (client && runtimeExecution) await runMutation(() => client.pauseRuntime(runtimeExecution.id, "manual_pause"), selectedRunId); },
    resume: async () => { if (client && runtimeExecution) await runMutation(() => client.resumeRuntime(runtimeExecution.id, "manual_resume"), selectedRunId); },
    cancel: async () => { if (client && runtimeExecution) await runMutation(() => client.cancelRuntime(runtimeExecution.id, "manual_cancel"), selectedRunId); },
    retry: async (job: WorkflowRuntimeJob) => { if (client && runtimeExecution) await runMutation(() => client.retryRuntimeJob(runtimeExecution.id, job.id), selectedRunId); },
    createTrigger: async (input: { triggerType: "event" | "schedule"; eventType?: string; intervalSeconds?: number; cronExpression?: string; timezone?: string }) => { if (client && selectedRunId) await runMutation(() => client.createRuntimeTrigger(selectedRunId, input), selectedRunId); },
    setTriggerEnabled: async (trigger: WorkflowRuntimeTrigger, enabled: boolean) => { if (client) await runMutation(() => client.setRuntimeTriggerEnabled(trigger.id, enabled), selectedRunId); },
  };

  const dispatch = useCallback(async (actionId: string, input: Record<string, unknown>) => {
    if (!client) throw new Error("工作流尚未连接");
    if (actionId === "workflow.refresh") { await refresh(); return { refreshed: true }; }
    const runId = typeof input.runId === "string" ? input.runId : selectedRunId;
    const nodeId = typeof input.nodeId === "string" ? input.nodeId : selectedNode?.id;
    const activeRun = runId ? await client.run(runId) : undefined;
    if (actionId === "workflow.run.create") return runMutation(() => client.createRun(input as unknown as { templateId: string; title: string; assignments: Record<string, string>; reviewers: Record<string, string> }), runId);
    if (!activeRun || !nodeId) throw new Error("请指定工作流运行和节点");
    if (actionId === "workflow.node.claim") return runMutation(() => client.claimNode(runId, nodeId, activeRun.run.revision), runId);
    if (actionId === "workflow.node.submit") return runMutation(() => client.submitNode(runId, nodeId, activeRun.run.revision, String(input.note || "")), runId);
    if (actionId === "workflow.node.review") return runMutation(() => client.reviewNode(runId, nodeId, activeRun.run.revision, input.decision === "request_changes" ? "request_changes" : "approve", String(input.note || "")), runId);
    if (actionId === "workflow.grant.create") return runMutation(() => client.createGrant(input as unknown as { delegatePrincipalId: string; scope: WorkflowScope; actions: string[]; allowRedelegate: boolean; maxRedelegationDepth: number }));
    throw new Error(`不支持工作流动作 ${actionId}`);
  }, [client, refresh, runMutation, selectedNode?.id, selectedRunId]);
  actionRef.current = dispatch;

  contextRef.current = buildContext(workspace, overview, snapshot?.run);
  useEffect(() => { host?.publishContext(contextRef.current); }, [host, overview, snapshot, workspace]);

  const meta = WORKSPACE_META[workspace];
  if (!identity || loading || !overview) return <main className="workflow-root loading-screen"><RefreshCw className="spin" /><strong>正在载入组织工作流…</strong>{error ? <p>{error}</p> : null}</main>;
  const headerControls = <div className="header-controls"><label>当前执行身份<select value={actingPrincipalId || overview.currentPrincipal.id} onChange={(event) => setActingPrincipalId(event.target.value)}>{overview.principals.map((principal) => <option value={principal.id} key={principal.id}>{principal.kind === "server_agent" ? "Agent · " : "成员 · "}{principal.name}</option>)}</select></label><button className="icon-button" disabled={busy} onClick={() => void refresh()} title="刷新"><RefreshCw className={busy ? "spin" : ""} /></button></div>;
  return <main className={`workflow-root workspace-${workspace} ${embeddedInDesk ? "is-embedded" : "is-standalone"}`}>
    {workspace !== "overview" ? embeddedInDesk ? <div className="workflow-command-bar">{headerControls}</div> : <header className="workflow-header"><div><span>WORKFLOW CONTROL</span><h1>{meta.title}</h1><p>{meta.description}</p></div>{headerControls}</header> : null}
    {error ? <div className="error-banner">{error}<button onClick={() => setError("")}><X /></button></div> : null}
    {workspace === "overview" ? <OverviewView overview={overview} busy={busy} actingPrincipalId={actingPrincipalId || overview.currentPrincipal.id} onActingPrincipalChange={setActingPrincipalId} onRefresh={() => void refresh()} /> : null}
    {workspace === "designer" ? <DesignerView overview={overview} busy={busy} onCreate={(input) => runMutation(() => client!.createTemplate(input)).then(() => undefined)} onVersion={(id, input) => runMutation(() => client!.createTemplateVersion(id, input)).then(() => undefined)} onLoadVersions={async (id) => (await client!.templateVersions(id)).versions} onRestore={(id, sourceVersion, expectedVersion, note) => runMutation(() => client!.restoreTemplateVersion(id, sourceVersion, expectedVersion, note)).then(() => undefined)} /> : null}
    {workspace === "runs" ? <RunsView overview={overview} snapshot={snapshot} runtimeExecution={runtimeExecution} runtimeTriggers={runtimeTriggers} selectedRunId={selectedRunId} selectedNodeId={selectedNodeId} busy={busy} onSelectRun={(id) => { setSelectedRunId(id); void loadRun(id); }} onSelectNode={setSelectedNodeId} onCreateRun={async (input) => { const created = await runMutation(() => client!.createRun(input), ""); setSelectedRunId(created.id); await loadRun(created.id); }} actions={operations} runtimeActions={runtimeOperations} /> : null}
    {workspace === "delegations" ? <DelegationsView overview={overview} busy={busy} onCreate={(input) => runMutation(() => client!.createGrant(input)).then(() => undefined)} onRevoke={(id) => runMutation(() => client!.revokeGrant(id)).then(() => undefined)} /> : null}
    {workspace === "artifacts" ? <ArtifactsView overview={overview} artifacts={artifacts} /> : null}
    {workspace === "audit" ? <AuditView overview={overview} /> : null}
    {workspace === "settings" ? <SettingsView overview={overview} busy={busy} onCreate={(input) => runMutation(() => client!.createPrincipal(input)).then(() => undefined)} /> : null}
  </main>;
}
