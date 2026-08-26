import {
  Activity,
  Archive,
  Bot,
  Check,
  ChevronRight,
  CircleDot,
  ClipboardCheck,
  GitBranch,
  Grid3X3,
  GripVertical,
  History,
  KeyRound,
  Network,
  PanelLeft,
  Pin,
  Plus,
  RefreshCw,
  RotateCcw,
  Rows3,
  Save,
  ShieldCheck,
  Trash2,
  UserRoundCog,
  UsersRound,
  X,
} from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import { connectModHost, type ModHostConnection } from "@newma-desk/mod-sdk";

import { workflowClient } from "./api";
import { axisLetter, matrixCoordinate, moveOrSwapNode, reorderAxisById, resolveWorkflowMatrix, summarizeTemplateVersionDiff } from "./matrix";
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
  ready: "可领取",
  claimed: "已领取",
  running: "执行中",
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

function workspaceFromSearch(): WorkflowWorkspace {
  const value = new URLSearchParams(window.location.search).get("workspace");
  return value && Object.hasOwn(MOD_IDS, value) ? value as WorkflowWorkspace : "overview";
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
  return {
    view: { id: MOD_IDS[workspace], title: WORKSPACE_META[workspace].title },
    visibleBlocks: [
      { id: "workflow-header", type: "workflow-header", title: WORKSPACE_META[workspace].title },
      { id: `workflow-${workspace}-main`, type: workspace, title: WORKSPACE_META[workspace].title },
      { id: "workflow-responsibility", type: "responsibility", title: "责任与授权" },
      { id: "workflow-artifacts", type: "artifacts", title: "节点交付物" },
    ],
    selection: run ? { workflowRunId: run.id, workflowTemplateId: run.templateId } : {},
    filters: { workspace },
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

function MetricCard({ icon, label, value, note }: { icon: React.ReactNode; label: string; value: number; note: string }) {
  return <article className="metric-card"><div>{icon}</div><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

type MatrixNode = WorkflowNodeDefinition | WorkflowNodeRun;

function workflowNodeStatus(node: MatrixNode) {
  return "status" in node && typeof node.status === "string" ? node.status : "";
}

interface DependencyPath extends WorkflowEdge { d: string }

function WorkflowDependencyLines({ tableRef, edges, layoutKey, selectedNodeId }: { tableRef: React.RefObject<HTMLDivElement | null>; edges: WorkflowEdge[]; layoutKey: string; selectedNodeId?: string }) {
  const markerId = useId().replace(/:/g, "");
  const [layer, setLayer] = useState<{ width: number; height: number; paths: DependencyPath[] }>({ width: 0, height: 0, paths: [] });

  useEffect(() => {
    const table = tableRef.current;
    if (!table) return;
    const measure = () => {
      const tableRect = table.getBoundingClientRect();
      const elements = new Map<string, HTMLElement>();
      table.querySelectorAll<HTMLElement>("[data-node-id]").forEach((element) => {
        if (element.dataset.nodeId) elements.set(element.dataset.nodeId, element);
      });
      const paths = edges.flatMap((edge) => {
        const source = elements.get(edge.source)?.getBoundingClientRect();
        const target = elements.get(edge.target)?.getBoundingClientRect();
        if (!source || !target) return [];
        const sourceCenter = { x: source.left - tableRect.left + source.width / 2, y: source.top - tableRect.top + source.height / 2 };
        const targetCenter = { x: target.left - tableRect.left + target.width / 2, y: target.top - tableRect.top + target.height / 2 };
        const dx = targetCenter.x - sourceCenter.x;
        const dy = targetCenter.y - sourceCenter.y;
        let start = sourceCenter;
        let end = targetCenter;
        let d = "";
        if (Math.abs(dx) >= Math.abs(dy)) {
          const direction = dx >= 0 ? 1 : -1;
          start = { x: sourceCenter.x + direction * source.width / 2, y: sourceCenter.y };
          end = { x: targetCenter.x - direction * target.width / 2, y: targetCenter.y };
          const bend = Math.max(34, Math.abs(end.x - start.x) * .42);
          d = `M ${start.x} ${start.y} C ${start.x + direction * bend} ${start.y}, ${end.x - direction * bend} ${end.y}, ${end.x} ${end.y}`;
        } else {
          const direction = dy >= 0 ? 1 : -1;
          start = { x: sourceCenter.x, y: sourceCenter.y + direction * source.height / 2 };
          end = { x: targetCenter.x, y: targetCenter.y - direction * target.height / 2 };
          const bend = Math.max(34, Math.abs(end.y - start.y) * .42);
          d = `M ${start.x} ${start.y} C ${start.x} ${start.y + direction * bend}, ${end.x} ${end.y - direction * bend}, ${end.x} ${end.y}`;
        }
        return [{ ...edge, d }];
      });
      setLayer({ width: Math.max(table.scrollWidth, Math.ceil(tableRect.width)), height: Math.max(table.scrollHeight, Math.ceil(tableRect.height)), paths });
    };
    const frame = requestAnimationFrame(measure);
    const observer = new ResizeObserver(measure);
    observer.observe(table);
    table.querySelectorAll<HTMLElement>("[data-node-id]").forEach((element) => observer.observe(element));
    window.addEventListener("resize", measure);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); window.removeEventListener("resize", measure); };
  }, [edges, layoutKey, tableRef]);

  if (!layer.paths.length) return null;
  return <svg className="dependency-layer" width={layer.width} height={layer.height} viewBox={`0 0 ${layer.width} ${layer.height}`} aria-hidden="true">
    <defs><marker id={markerId} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M 0 0 L 8 4 L 0 8 z" /></marker></defs>
    {layer.paths.map((path) => {
      const related = Boolean(selectedNodeId && (path.source === selectedNodeId || path.target === selectedNodeId));
      const dimmed = Boolean(selectedNodeId && !related);
      return <path className={`dependency-line ${related ? "related" : ""} ${dimmed ? "dimmed" : ""}`} d={path.d} markerEnd={`url(#${markerId})`} key={`${path.source}-${path.target}`} />;
    })}
  </svg>;
}

function WorkflowMatrixBoard({ lanes: sourceLanes, stages: sourceStages, nodes: sourceNodes, edges, principals, selectedNodeId, activeStageId, onStageChange, onSelectNode }: { lanes: WorkflowLaneDefinition[]; stages: WorkflowStageDefinition[]; nodes: MatrixNode[]; edges: WorkflowEdge[]; principals?: Principal[]; selectedNodeId?: string; activeStageId: string; onStageChange(value: string): void; onSelectNode(id: string): void }) {
  const { lanes, stages, nodes } = resolveWorkflowMatrix(sourceNodes, sourceLanes, sourceStages);
  const [activeLaneId, setActiveLaneId] = useState("");
  useEffect(() => { if (activeLaneId && !lanes.some((lane) => lane.id === activeLaneId)) setActiveLaneId(""); }, [activeLaneId, lanes]);
  const visibleLanes = activeLaneId ? lanes.filter((lane) => lane.id === activeLaneId) : lanes;
  const visibleStages = activeStageId ? stages.filter((stage) => stage.id === activeStageId) : stages;
  const columns = `200px repeat(${Math.max(visibleStages.length, 1)}, minmax(175px, 1fr))`;
  const tableRef = useRef<HTMLDivElement>(null);
  const layoutKey = `${activeLaneId}|${activeStageId}|${lanes.map((lane) => lane.id).join(",")}|${stages.map((stage) => stage.id).join(",")}|${nodes.map((node) => `${node.id}:${node.laneId}:${node.stageId}`).join(",")}`;
  return <div className="matrix-board">
    <div className="matrix-composer">
      <aside className="lane-navigator" aria-label="纵向业务域导航">
        <header><Rows3 /><span><strong>业务域</strong><small>纵向二级模块</small></span></header>
        <button className={`lane-nav-all ${!activeLaneId ? "active" : ""}`} onClick={() => setActiveLaneId("")}><Grid3X3 /><span><strong>全部业务域</strong><small>{lanes.length} 个 Lane</small></span></button>
        {lanes.map((lane, laneIndex) => {
          const promoted = nodes.filter((node) => node.laneId === lane.id && node.promotedToMenu);
          return <section className={`lane-nav-section ${activeLaneId === lane.id ? "active" : ""}`} key={lane.id}>
            <button className="lane-nav-button" onClick={() => { setActiveLaneId(lane.id); onStageChange(""); }}><span className="axis-code">{axisLetter(laneIndex)}</span><span><strong>{lane.name}</strong><small>{lane.description || "纵向业务模块"}</small></span></button>
            {promoted.length ? <div className="lane-promoted-menu">{promoted.map((node) => <button className={selectedNodeId === node.id ? "active" : ""} key={node.id} onClick={() => { setActiveLaneId(node.laneId); onStageChange(node.stageId); onSelectNode(node.id); }}><Pin /><span>{node.name}</span><small>{matrixCoordinate(node.laneId, node.stageId, lanes, stages)}</small></button>)}</div> : <small className="lane-empty-note">暂无成熟节点入口</small>}
          </section>;
        })}
      </aside>
      <div className="matrix-stage-canvas">
        <nav className="stage-tabs" aria-label="横向流程阶段">
          <button className={!activeStageId ? "active" : ""} onClick={() => onStageChange("")}><Grid3X3 />全景</button>
          {stages.map((stage, index) => <button className={activeStageId === stage.id ? "active" : ""} key={stage.id} onClick={() => onStageChange(stage.id)}><span>{index + 1}</span>{stage.name}</button>)}
        </nav>
        <div className="matrix-scroll">
          <div className="matrix-table" ref={tableRef}>
            <WorkflowDependencyLines tableRef={tableRef} edges={edges} layoutKey={layoutKey} selectedNodeId={selectedNodeId} />
            <div className="matrix-header-row" style={{ gridTemplateColumns: columns }}>
              <div className="matrix-corner"><PanelLeft /><span><strong>纵向业务域</strong><small>二级模块与成熟入口</small></span></div>
              {visibleStages.map((stage) => {
                const stageIndex = stages.findIndex((item) => item.id === stage.id);
                return <div className="matrix-stage-header" key={stage.id}><span>{stageIndex + 1}</span><div><strong>{stage.name}</strong><small>{stage.description || "横向流程阶段"}</small></div></div>;
              })}
            </div>
            {visibleLanes.map((lane) => {
              const laneIndex = lanes.findIndex((item) => item.id === lane.id);
              const promoted = nodes.filter((node) => node.laneId === lane.id && node.promotedToMenu);
              return <div className="matrix-data-row" style={{ gridTemplateColumns: columns }} key={lane.id}>
                <div className="matrix-lane-header"><span className="axis-code">{axisLetter(laneIndex)}</span><div><strong>{lane.name}</strong><small>{lane.description || "纵向业务模块"}</small>{promoted.length ? <div className="promoted-links">{promoted.map((node) => <button key={node.id} onClick={() => { onStageChange(node.stageId); onSelectNode(node.id); }}><Pin />{node.name}</button>)}</div> : null}</div></div>
                {visibleStages.map((stage) => {
                  const node = nodes.find((item) => item.laneId === lane.id && item.stageId === stage.id);
                  if (!node) return <div className="matrix-empty-cell" key={stage.id}><span>{matrixCoordinate(lane.id, stage.id, lanes, stages)}</span><small>暂无节点</small></div>;
                  const status = workflowNodeStatus(node);
                  const accountable = "accountablePrincipalId" in node ? principalName(principals || [], node.accountablePrincipalId) : node.roleKey;
                  return <button data-node-id={node.id} className={`matrix-node-card kind-${node.kind} ${status ? `status-${status}` : ""} ${selectedNodeId === node.id ? "active" : ""}`} key={stage.id} onClick={() => onSelectNode(node.id)}>
                    <header><span>{matrixCoordinate(node.laneId, node.stageId, lanes, stages)}</span>{node.promotedToMenu ? <Pin /> : null}</header>
                    <strong>{node.name}</strong><small>{node.description || node.roleKey}</small>
                    <footer><span>{accountable}</span><em>{status ? statusLabel(status) : node.kind}</em></footer>
                  </button>;
                })}
              </div>;
            })}
          </div>
        </div>
      </div>
    </div>
  </div>;
}

function OverviewView({ overview }: { overview: WorkflowOverview }) {
  const liveRuns = overview.runs.filter((run) => !["completed", "cancelled"].includes(run.status));
  const [sourceId, setSourceId] = useState(liveRuns[0] ? `run:${liveRuns[0].id}` : overview.templates[0] ? `template:${overview.templates[0].id}` : "");
  const [activeStageId, setActiveStageId] = useState("");
  const run = sourceId.startsWith("run:") ? overview.runs.find((item) => item.id === sourceId.slice(4)) : undefined;
  const requestedTemplateId = sourceId.startsWith("template:") ? sourceId.slice(9) : run?.templateId;
  const template = overview.templates.find((item) => item.id === requestedTemplateId) || overview.templates[0];
  const matrixSource = run || template;
  const [selectedNodeId, setSelectedNodeId] = useState(matrixSource?.nodes[0]?.id || "");
  useEffect(() => {
    const sourceExists = sourceId.startsWith("run:")
      ? overview.runs.some((item) => item.id === sourceId.slice(4))
      : overview.templates.some((item) => item.id === sourceId.slice(9));
    if (!sourceExists) setSourceId(liveRuns[0] ? `run:${liveRuns[0].id}` : overview.templates[0] ? `template:${overview.templates[0].id}` : "");
  }, [liveRuns, overview.runs, overview.templates, sourceId]);
  useEffect(() => {
    if (matrixSource && !matrixSource.nodes.some((node) => node.id === selectedNodeId)) setSelectedNodeId(matrixSource.nodes[0]?.id || "");
  }, [matrixSource, selectedNodeId]);
  const selectedNode = matrixSource?.nodes.find((node) => node.id === selectedNodeId);
  const selectedStatus = selectedNode ? workflowNodeStatus(selectedNode) : "";
  const assignments = overview.runs.flatMap((run) => run.nodes.map((node) => ({ run, node }))).filter(({ node }) => !["completed", "cancelled", "skipped"].includes(node.status));
  return <div className="view-stack">
    <section className="metric-grid">
      <MetricCard icon={<GitBranch />} label="流程模板" value={overview.metrics.templates} note="均保留版本" />
      <MetricCard icon={<Activity />} label="进行中" value={overview.metrics.activeRuns} note={`${overview.metrics.readyNodes} 个活跃节点`} />
      <MetricCard icon={<ClipboardCheck />} label="待审核" value={overview.metrics.waitingReview} note="责任人与审核人分离" />
      <MetricCard icon={<KeyRound />} label="有效授权" value={overview.metrics.activeGrants} note="可覆盖多个工作流" />
      <MetricCard icon={<Bot />} label="服务器 Agent" value={overview.metrics.serverAgents} note="可授权，也可被授权" />
    </section>
    <section className="panel organization-canvas">
      <header className="panel-heading"><div><span>ORGANIZATION MATRIX</span><h2>组织工作流画布</h2></div>{overview.runs.length || overview.templates.length ? <select aria-label="画布来源" value={sourceId} onChange={(event) => { setSourceId(event.target.value); setActiveStageId(""); }}><optgroup label="运行实例">{overview.runs.map((item) => <option value={`run:${item.id}`} key={item.id}>{item.title} · {runStatusLabel(item.status)}</option>)}</optgroup><optgroup label="模板预览">{overview.templates.map((item) => <option value={`template:${item.id}`} key={item.id}>{item.name} · v{item.currentVersion}</option>)}</optgroup></select> : <small>暂无画布</small>}</header>
      {matrixSource ? <WorkflowMatrixBoard lanes={matrixSource.lanes} stages={matrixSource.stages} nodes={matrixSource.nodes} edges={matrixSource.edges} principals={overview.principals} selectedNodeId={selectedNodeId} activeStageId={activeStageId} onStageChange={setActiveStageId} onSelectNode={setSelectedNodeId} /> : <EmptyState>请先建立一个工作流模板。</EmptyState>}
      {selectedNode ? <div className="matrix-focus-bar"><span className="axis-code">{matrixCoordinate(selectedNode.laneId, selectedNode.stageId, matrixSource!.lanes, matrixSource!.stages)}</span><div><strong>{selectedNode.name}</strong><small>{selectedNode.description || "尚未填写节点说明"}</small></div><span>{selectedNode.roleKey}</span>{selectedStatus ? <em className={`status-pill status-${selectedStatus}`}>{statusLabel(selectedStatus)}</em> : null}</div> : null}
    </section>
    <section className="two-column overview-lower">
      <article className="panel">
        <header className="panel-heading"><div><span>RESPONSIBILITY</span><h2>组织待办</h2></div><small>{assignments.length} 项</small></header>
        <div className="assignment-list">{assignments.slice(0, 12).map(({ run, node }) => <div key={`${run.id}-${node.id}`}>
          <span className={`status-dot status-${node.status}`} /><div><strong>{node.name}</strong><small>{run.title} · {node.roleKey}</small></div>
          <span>{principalName(overview.principals, node.accountablePrincipalId)}</span><em>{statusLabel(node.status)}</em>
        </div>)}</div>
      </article>
      <article className="panel">
        <header className="panel-heading"><div><span>ACTIVITY LEDGER</span><h2>最近组织活动</h2></div><small>执行与责任分开记录</small></header>
        <div className="event-table compact">{overview.recentEvents.slice(0, 10).map((event) => <div key={event.sequence}>
          <time>{displayTime(event.createdAt)}</time><strong>{event.type}</strong><span>{principalName(overview.principals, event.actorPrincipalId)}</span><span>{event.accountablePrincipalId ? `责任：${principalName(overview.principals, event.accountablePrincipalId)}` : "组织事件"}</span>
        </div>)}</div>
      </article>
    </section>
  </div>;
}

interface DraftNode extends WorkflowNodeDefinition { predecessors: string[] }
type DesignerDrag = { kind: "lane" | "stage" | "node"; id: string } | null;

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
  edges: Array<{ source: string; target: string }>;
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
  const [dragging, setDragging] = useState<DesignerDrag>(null);
  const [dropTarget, setDropTarget] = useState("");
  const tableRef = useRef<HTMLDivElement>(null);
  const editing = overview.templates.find((item) => item.id === editingId);
  const selectedNode = nodes.find((node) => node.id === selectedNodeId);
  const draftEdges = useMemo(() => nodes.flatMap((node) => node.predecessors.map((source) => ({ source, target: node.id }))), [nodes]);

  const refreshVersions = async (templateId: string) => {
    setVersionsLoading(true);
    try { setVersions(await onLoadVersions(templateId)); }
    finally { setVersionsLoading(false); }
  };

  const load = (template?: WorkflowTemplate) => {
    if (!template) {
      const blank = blankMatrix();
      setEditingId(""); setName("组织协作流程"); setDescription("把组织任务拆成可授权、可审核、可交付的节点。"); setLanes(blank.lanes); setStages(blank.stages); setNodes(blank.nodes); setSelectedNodeId(blank.nodes[0]?.id || ""); setActiveStageId(""); setVersions([]); return;
    }
    const resolved = resolveWorkflowMatrix(template.nodes, template.lanes, template.stages);
    setEditingId(template.id); setName(template.name); setDescription(template.description);
    setLanes(resolved.lanes); setStages(resolved.stages);
    setNodes(resolved.nodes.map((node) => ({ ...node, predecessors: template.edges.filter((edge) => edge.target === node.id).map((edge) => edge.source) })));
    setSelectedNodeId(resolved.nodes[0]?.id || ""); setActiveStageId("");
    void refreshVersions(template.id);
  };
  const patchNode = (id: string, patch: Partial<DraftNode>) => setNodes((current) => current.map((node) => node.id === id ? { ...node, ...patch } : node));
  const nextId = (prefix: string, ids: string[]) => { let index = ids.length + 1; while (ids.includes(`${prefix}-${index}`)) index += 1; return `${prefix}-${index}`; };
  const addLane = () => setLanes((current) => [...current, { id: nextId("lane", current.map((item) => item.id)), name: `业务域 ${axisLetter(current.length)}`, description: "" }]);
  const addStage = () => setStages((current) => [...current, { id: nextId("stage", current.map((item) => item.id)), name: `阶段 ${current.length + 1}`, description: "" }]);
  const removeLane = (laneId: string) => { if (lanes.length <= 1) return; const removed = new Set(nodes.filter((node) => node.laneId === laneId).map((node) => node.id)); setLanes((current) => current.filter((lane) => lane.id !== laneId)); setNodes((current) => current.filter((node) => !removed.has(node.id)).map((node) => ({ ...node, predecessors: node.predecessors.filter((id) => !removed.has(id)) }))); if (selectedNodeId && removed.has(selectedNodeId)) setSelectedNodeId(""); };
  const removeStage = (stageId: string) => { if (stages.length <= 1) return; const removed = new Set(nodes.filter((node) => node.stageId === stageId).map((node) => node.id)); setStages((current) => current.filter((stage) => stage.id !== stageId)); setNodes((current) => current.filter((node) => !removed.has(node.id)).map((node) => ({ ...node, predecessors: node.predecessors.filter((id) => !removed.has(id)) }))); if (activeStageId === stageId) setActiveStageId(""); if (selectedNodeId && removed.has(selectedNodeId)) setSelectedNodeId(""); };
  const addNodeAt = (laneId: string, stageId: string) => {
    const id = nextId("node", nodes.map((node) => node.id));
    const node: DraftNode = { id, name: "新工作节点", description: "", roleKey: "owner", kind: "task", requiresReview: false, outputs: [], laneId, stageId, promotedToMenu: false, predecessors: [] };
    setNodes((current) => [...current, node]); setSelectedNodeId(id);
  };
  const removeNode = (nodeId: string) => { setNodes((current) => current.filter((node) => node.id !== nodeId).map((node) => ({ ...node, predecessors: node.predecessors.filter((id) => id !== nodeId) }))); setSelectedNodeId(""); };
  const togglePredecessor = (nodeId: string, predecessorId: string) => patchNode(nodeId, { predecessors: selectedNode?.predecessors.includes(predecessorId) ? selectedNode.predecessors.filter((id) => id !== predecessorId) : [...(selectedNode?.predecessors || []), predecessorId] });
  const beginDrag = (event: React.DragEvent, value: Exclude<DesignerDrag, null>) => {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", `${value.kind}:${value.id}`);
    setDragging(value);
  };
  const endDrag = () => { setDragging(null); setDropTarget(""); };
  const dropAxis = (kind: "lane" | "stage", targetId: string) => {
    if (!dragging || dragging.kind !== kind) return;
    if (kind === "lane") setLanes((current) => reorderAxisById(current, dragging.id, targetId));
    else setStages((current) => reorderAxisById(current, dragging.id, targetId));
    endDrag();
  };
  const dropNode = (laneId: string, stageId: string) => {
    if (!dragging || dragging.kind !== "node") return;
    setNodes((current) => moveOrSwapNode(current, dragging.id, laneId, stageId));
    setSelectedNodeId(dragging.id);
    endDrag();
  };
  const restoreVersion = async (version: WorkflowTemplateVersion) => {
    if (!editing || version.version === editing.currentVersion) return;
    await onRestore(editing.id, version.version, editing.currentVersion, `恢复 v${version.version} · ${version.changeNote || "历史版本"}`);
    const resolved = resolveWorkflowMatrix(version.nodes, version.lanes, version.stages);
    setName(version.name); setDescription(version.description); setLanes(resolved.lanes); setStages(resolved.stages);
    setNodes(resolved.nodes.map((node) => ({ ...node, predecessors: version.edges.filter((edge) => edge.target === node.id).map((edge) => edge.source) })));
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
  const visibleStages = activeStageId ? stages.filter((stage) => stage.id === activeStageId) : stages;
  const columns = `200px repeat(${Math.max(visibleStages.length, 1)}, minmax(175px, 1fr))`;
  const layoutKey = `${activeStageId}|${lanes.map((lane) => lane.id).join(",")}|${stages.map((stage) => stage.id).join(",")}|${nodes.map((node) => `${node.id}:${node.laneId}:${node.stageId}`).join(",")}`;
  return <div className="designer-layout">
    <aside className="template-sidebar panel"><header className="panel-heading"><div><span>TEMPLATES</span><h2>模板版本</h2></div><button className="icon-button" onClick={() => load()} title="新建模板"><Plus /></button></header>
      <div className="template-list"><button className={!editingId ? "active" : ""} onClick={() => load()}><Plus /><span><strong>新建流程</strong><small>从空白编排</small></span></button>{overview.templates.map((template) => <button className={editingId === template.id ? "active" : ""} onClick={() => load(template)} key={template.id}><GitBranch /><span><strong>{template.name}</strong><small>v{template.currentVersion} · {template.nodes.length} 节点</small></span></button>)}</div>
      {editing ? <section className="template-version-history"><header><span><History /><strong>版本历史</strong></span><button title="刷新版本" disabled={versionsLoading} onClick={() => void refreshVersions(editing.id)}><RefreshCw className={versionsLoading ? "spin" : ""} /></button></header><div>{versions.map((version) => {
        const diff = summarizeTemplateVersionDiff(editing, version);
        const isCurrent = version.version === editing.currentVersion;
        return <article className={isCurrent ? "current" : ""} key={version.version}><header><strong>v{version.version}</strong><time>{displayTime(version.createdAt)}</time></header><p>{version.changeNote || "未填写版本说明"}</p><div className="version-diff-tags"><span>节点 +{diff.addedNodes} / -{diff.removedNodes} / ~{diff.changedNodes}</span><span>依赖 {diff.changedEdges}</span>{diff.metadataChanged ? <span>名称 / 说明</span> : null}{diff.laneOrderChanged || diff.stageOrderChanged ? <span>行列变化</span> : null}</div>{isCurrent ? <em>当前版本</em> : <button disabled={busy} onClick={() => void restoreVersion(version)}><RotateCcw />恢复为新版本</button>}</article>;
      })}{!versionsLoading && !versions.length ? <small className="version-empty">暂无版本记录</small> : null}</div></section> : null}
    </aside>
    <section className="panel designer-canvas">
      <header className="designer-header"><div><label>流程名称<input value={name} onChange={(event) => setName(event.target.value)} /></label><label>流程说明<input value={description} onChange={(event) => setDescription(event.target.value)} /></label></div><button className="primary-button" onClick={() => void save()} disabled={busy}><Save />{editing ? `保存为 v${editing.currentVersion + 1}` : "创建模板"}</button></header>
      {editing ? <label className="change-note">版本说明<input value={changeNote} onChange={(event) => setChangeNote(event.target.value)} /></label> : null}
      <div className="matrix-authoring-bar"><div><Rows3 /><span><strong>{lanes.length} 个纵向业务域</strong><small>作为工作流内的二级模块</small></span><button onClick={addLane}><Plus />增加业务域</button></div><div><Grid3X3 /><span><strong>{stages.length} 个横向阶段</strong><small>通过上方标签切换</small></span><button onClick={addStage}><Plus />增加阶段</button></div></div>
      <nav className="stage-tabs designer-stage-tabs"><button className={!activeStageId ? "active" : ""} onClick={() => setActiveStageId("")}><Grid3X3 />全景</button>{stages.map((stage, index) => <button className={activeStageId === stage.id ? "active" : ""} onClick={() => setActiveStageId(stage.id)} key={stage.id}><span>{index + 1}</span>{stage.name}</button>)}</nav>
      <div className="designer-matrix-workspace">
        <div className="matrix-scroll designer-matrix-scroll"><div className="matrix-table" ref={tableRef}>
          <WorkflowDependencyLines tableRef={tableRef} edges={draftEdges} layoutKey={layoutKey} selectedNodeId={selectedNodeId} />
          <div className="matrix-header-row designer-grid-row" style={{ gridTemplateColumns: columns }}>
            <div className="matrix-corner"><PanelLeft /><span><strong>横 × 竖组织画布</strong><small>拖动行列排序，拖动节点移动或交换</small></span></div>
            {visibleStages.map((stage) => <div
              className={`axis-editor stage-axis-editor ${dropTarget === `stage:${stage.id}` ? "drop-target" : ""}`}
              key={stage.id}
              onDragOver={(event) => { if (dragging?.kind === "stage") { event.preventDefault(); event.dataTransfer.dropEffect = "move"; setDropTarget(`stage:${stage.id}`); } }}
              onDrop={(event) => { event.preventDefault(); dropAxis("stage", stage.id); }}
            >
              <span className="axis-drag-handle" draggable onDragStart={(event) => beginDrag(event, { kind: "stage", id: stage.id })} onDragEnd={endDrag} title="拖动阶段排序"><GripVertical /></span>
              <span className="axis-code">{stages.findIndex((item) => item.id === stage.id) + 1}</span>
              <div><input value={stage.name} onChange={(event) => setStages((current) => current.map((item) => item.id === stage.id ? { ...item, name: event.target.value } : item))} /><input value={stage.description} placeholder="阶段说明" onChange={(event) => setStages((current) => current.map((item) => item.id === stage.id ? { ...item, description: event.target.value } : item))} /></div>
              <button title="删除阶段" disabled={stages.length <= 1} onClick={() => removeStage(stage.id)}><Trash2 /></button>
            </div>)}
          </div>
          {lanes.map((lane, laneIndex) => <div className={`matrix-data-row designer-grid-row ${dropTarget === `lane:${lane.id}` ? "axis-drop-row" : ""}`} style={{ gridTemplateColumns: columns }} key={lane.id}>
            <div
              className="axis-editor lane-axis-editor"
              onDragOver={(event) => { if (dragging?.kind === "lane") { event.preventDefault(); event.dataTransfer.dropEffect = "move"; setDropTarget(`lane:${lane.id}`); } }}
              onDrop={(event) => { event.preventDefault(); dropAxis("lane", lane.id); }}
            >
              <span className="axis-drag-handle" draggable onDragStart={(event) => beginDrag(event, { kind: "lane", id: lane.id })} onDragEnd={endDrag} title="拖动业务域排序"><GripVertical /></span>
              <span className="axis-code">{axisLetter(laneIndex)}</span>
              <div><input value={lane.name} onChange={(event) => setLanes((current) => current.map((item) => item.id === lane.id ? { ...item, name: event.target.value } : item))} /><input value={lane.description} placeholder="业务域说明" onChange={(event) => setLanes((current) => current.map((item) => item.id === lane.id ? { ...item, description: event.target.value } : item))} /></div>
              <button title="删除业务域" disabled={lanes.length <= 1} onClick={() => removeLane(lane.id)}><Trash2 /></button>
            </div>
            {visibleStages.map((stage) => {
              const node = nodes.find((item) => item.laneId === lane.id && item.stageId === stage.id);
              const targetKey = `node:${lane.id}:${stage.id}`;
              const dropEvents = {
                onDragOver: (event: React.DragEvent) => { if (dragging?.kind === "node") { event.preventDefault(); event.dataTransfer.dropEffect = "move"; setDropTarget(targetKey); } },
                onDrop: (event: React.DragEvent) => { event.preventDefault(); dropNode(lane.id, stage.id); },
              };
              return node ? <button
                data-node-id={node.id}
                draggable
                className={`matrix-node-card authoring-node kind-${node.kind} ${selectedNodeId === node.id ? "active" : ""} ${dragging?.kind === "node" && dragging.id === node.id ? "dragging" : ""} ${dropTarget === targetKey ? "drop-target" : ""}`}
                onClick={() => setSelectedNodeId(node.id)}
                onDragStart={(event) => beginDrag(event, { kind: "node", id: node.id })}
                onDragEnd={endDrag}
                key={stage.id}
                {...dropEvents}
              ><header><span>{matrixCoordinate(lane.id, stage.id, lanes, stages)}</span>{node.promotedToMenu ? <Pin /> : null}</header><strong>{node.name}</strong><small>{node.roleKey}</small><footer><span>{node.predecessors.length} 个前置</span><em>{node.kind}</em></footer></button> : <button className={`matrix-add-cell ${dropTarget === targetKey ? "drop-target" : ""}`} onClick={() => addNodeAt(lane.id, stage.id)} key={stage.id} {...dropEvents}><Plus /><strong>{matrixCoordinate(lane.id, stage.id, lanes, stages)}</strong><small>建立工作节点</small></button>;
            })}
          </div>)}
        </div></div>
        {selectedNode ? <aside className="node-inspector"><header><div><span>{matrixCoordinate(selectedNode.laneId, selectedNode.stageId, lanes, stages)}</span><h3>{selectedNode.name}</h3></div><button title="删除节点" onClick={() => removeNode(selectedNode.id)}><Trash2 /></button></header><div className="inspector-fields"><label>节点名称<input value={selectedNode.name} onChange={(event) => patchNode(selectedNode.id, { name: event.target.value })} /></label><div className="form-two"><label>节点 ID<input value={selectedNode.id} onChange={(event) => { const previous = selectedNode.id; const next = event.target.value; setNodes((current) => current.map((node) => node.id === previous ? { ...node, id: next } : { ...node, predecessors: node.predecessors.map((id) => id === previous ? next : id) })); setSelectedNodeId(next); }} /></label><label>类型<select value={selectedNode.kind} onChange={(event) => patchNode(selectedNode.id, { kind: event.target.value as DraftNode["kind"] })}><option value="task">执行节点</option><option value="review">审查节点</option><option value="gate">决策 Gate</option><option value="automation">自动化</option></select></label></div><label>职能角色<input value={selectedNode.roleKey} onChange={(event) => patchNode(selectedNode.id, { roleKey: event.target.value })} /></label><div className="form-two"><label>纵向业务域<select value={selectedNode.laneId} onChange={(event) => patchNode(selectedNode.id, { laneId: event.target.value })}>{lanes.map((lane) => <option disabled={nodes.some((node) => node.id !== selectedNode.id && node.laneId === lane.id && node.stageId === selectedNode.stageId)} value={lane.id} key={lane.id}>{lane.name}</option>)}</select></label><label>横向阶段<select value={selectedNode.stageId} onChange={(event) => patchNode(selectedNode.id, { stageId: event.target.value })}>{stages.map((stage) => <option disabled={nodes.some((node) => node.id !== selectedNode.id && node.laneId === selectedNode.laneId && node.stageId === stage.id)} value={stage.id} key={stage.id}>{stage.name}</option>)}</select></label></div><label>节点说明<textarea value={selectedNode.description} onChange={(event) => patchNode(selectedNode.id, { description: event.target.value })} /></label><label>交付物<input value={selectedNode.outputs.join(", ")} onChange={(event) => patchNode(selectedNode.id, { outputs: event.target.value.split(",").map((item) => item.trim()) })} /></label><fieldset className="predecessor-picker"><legend>前置节点</legend>{nodes.filter((node) => node.id !== selectedNode.id).map((node) => <label key={node.id}><input type="checkbox" checked={selectedNode.predecessors.includes(node.id)} onChange={() => togglePredecessor(selectedNode.id, node.id)} /><span>{matrixCoordinate(node.laneId, node.stageId, lanes, stages)}</span>{node.name}</label>)}</fieldset><label className="check-label"><input type="checkbox" checked={selectedNode.requiresReview} onChange={(event) => patchNode(selectedNode.id, { requiresReview: event.target.checked })} />完成后必须审核</label><label className="check-label promoted-toggle"><input type="checkbox" checked={selectedNode.promotedToMenu} onChange={(event) => patchNode(selectedNode.id, { promotedToMenu: event.target.checked })} /><Pin />成熟节点提升为二级入口</label></div></aside> : <aside className="node-inspector empty-inspector"><Grid3X3 /><strong>选择一个网格节点</strong><small>可编辑职能、依赖、交付物和菜单入口。</small></aside>}
      </div>
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

function NodeDetail({ overview, snapshot, node, busy, onClaim, onRelease, onSubmit, onReview, onData, onArtifact, onAssign }: { overview: WorkflowOverview; snapshot: WorkflowRunSnapshot; node: WorkflowNodeRun; busy: boolean; onClaim(): Promise<void>; onRelease(): Promise<void>; onSubmit(): Promise<void>; onReview(decision: "approve" | "request_changes"): Promise<void>; onData(slot: string, data: unknown): Promise<void>; onArtifact(input: { artifactKey: string; label: string; kind: string; content?: unknown; inputArtifactIds?: string[] }): Promise<void>; onAssign(accountable: string, reviewer?: string | null): Promise<void> }) {
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
    <div className="node-actions">{["ready", "stale"].includes(node.status) ? <button className="primary-button" disabled={busy} onClick={() => void onClaim()}><CircleDot />领取节点</button> : null}{["claimed", "running"].includes(node.status) ? <><button className="primary-button" disabled={busy} onClick={() => void onSubmit()}><Check />提交节点</button><button disabled={busy} onClick={() => void onRelease()}>释放租约</button></> : null}{node.status === "waiting_review" ? <><button className="primary-button" disabled={busy} onClick={() => void onReview("approve")}><ShieldCheck />审核通过</button><button disabled={busy} onClick={() => void onReview("request_changes")}>退回修改</button></> : null}</div>
    <details open><summary>节点数据 <span>版本 {node.dataRevision}</span></summary><div className="detail-form"><label>数据槽<input value={slot} onChange={(event) => setSlot(event.target.value)} /></label><label>JSON / 文本<textarea value={dataText} onChange={(event) => setDataText(event.target.value)} /></label><button disabled={busy} onClick={() => { let value: unknown = dataText; try { value = JSON.parse(dataText); } catch { /* save as text */ } void onData(slot, value); }}><Save />保存数据版本</button></div></details>
    <details open><summary>节点交付物 <span>{node.artifactCount} 个版本</span></summary><div className="detail-form"><div className="form-two"><label>交付物键<input value={artifactKey} onChange={(event) => setArtifactKey(event.target.value)} /></label><label>类型<select value="document" disabled><option>document</option></select></label></div><label>名称<input value={artifactLabel} onChange={(event) => setArtifactLabel(event.target.value)} /></label><label>内容<textarea value={artifactContent} onChange={(event) => setArtifactContent(event.target.value)} /></label><label>输入交付物 ID<input value={parents} onChange={(event) => setParents(event.target.value)} placeholder={currentArtifacts.slice(0, 2).map((item) => item.id).join(", ")} /></label><button disabled={busy} onClick={() => void onArtifact({ artifactKey, label: artifactLabel, kind: "document", content: artifactContent, inputArtifactIds: parents.split(",").map((value) => value.trim()).filter(Boolean) })}><Archive />保存交付版本</button></div></details>
    <details><summary>责任分配 <span>授权不改变责任</span></summary><div className="detail-form"><label>责任人<select value={accountable} onChange={(event) => setAccountable(event.target.value)}>{overview.principals.map((principal) => <option key={principal.id} value={principal.id}>{principal.name}</option>)}</select></label><label>审核人<select value={reviewer} onChange={(event) => setReviewer(event.target.value)}><option value="">不指定</option>{overview.principals.map((principal) => <option key={principal.id} value={principal.id}>{principal.name}</option>)}</select></label><button disabled={busy} onClick={() => void onAssign(accountable, reviewer || null)}><UserRoundCog />更新责任快照</button></div></details>
  </aside>;
}

function RunsView({ overview, snapshot, selectedRunId, selectedNodeId, busy, onSelectRun, onSelectNode, onCreateRun, actions }: { overview: WorkflowOverview; snapshot?: WorkflowRunSnapshot; selectedRunId: string; selectedNodeId: string; busy: boolean; onSelectRun(id: string): void; onSelectNode(id: string): void; onCreateRun(input: { templateId: string; title: string; assignments: Record<string, string>; reviewers: Record<string, string> }): Promise<void>; actions: { claim(node: WorkflowNodeRun): Promise<void>; release(node: WorkflowNodeRun): Promise<void>; submit(node: WorkflowNodeRun): Promise<void>; review(node: WorkflowNodeRun, decision: "approve" | "request_changes"): Promise<void>; data(node: WorkflowNodeRun, slot: string, value: unknown): Promise<void>; artifact(node: WorkflowNodeRun, input: { artifactKey: string; label: string; kind: string; content?: unknown; inputArtifactIds?: string[] }): Promise<void>; assign(node: WorkflowNodeRun, accountable: string, reviewer?: string | null): Promise<void> } }) {
  const run = snapshot?.run;
  const selectedNode = run?.nodes.find((node) => node.id === selectedNodeId) || run?.nodes[0];
  const [activeStageId, setActiveStageId] = useState("");
  useEffect(() => { setActiveStageId(""); }, [selectedRunId]);
  return <div className="view-stack"><RunCreation overview={overview} busy={busy} onCreate={onCreateRun} />
    <section className="run-workbench">
      <article className="panel run-canvas"><header className="panel-heading"><div><span>RUN CONTROL</span><h2>横竖节点运行图</h2></div><select value={selectedRunId} onChange={(event) => onSelectRun(event.target.value)}><option value="">选择运行</option>{overview.runs.map((item) => <option key={item.id} value={item.id}>{item.title} · {runStatusLabel(item.status)}</option>)}</select></header>
        {run ? <><div className="run-title"><div><strong>{run.title}</strong><span>{overview.templates.find((item) => item.id === run.templateId)?.name} · v{run.templateVersion}</span></div><em className={`status-pill status-${run.status}`}>{runStatusLabel(run.status)} · r{run.revision}</em></div><WorkflowMatrixBoard lanes={run.lanes} stages={run.stages} nodes={run.nodes} edges={run.edges} principals={overview.principals} selectedNodeId={selectedNode?.id} activeStageId={activeStageId} onStageChange={setActiveStageId} onSelectNode={onSelectNode} /></> : <EmptyState>选择一个运行，查看节点与责任。</EmptyState>}
      </article>
      {run && selectedNode ? <NodeDetail overview={overview} snapshot={snapshot} node={selectedNode} busy={busy} onClaim={() => actions.claim(selectedNode)} onRelease={() => actions.release(selectedNode)} onSubmit={() => actions.submit(selectedNode)} onReview={(decision) => actions.review(selectedNode, decision)} onData={(slot, value) => actions.data(selectedNode, slot, value)} onArtifact={(input) => actions.artifact(selectedNode, input)} onAssign={(accountable, reviewer) => actions.assign(selectedNode, accountable, reviewer)} /> : null}
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
  return <section className="panel"><header className="panel-heading"><div><span>ARTIFACT LINEAGE</span><h2>组织交付物</h2></div><small>{artifacts.length} 个当前版本</small></header>
    <div className="artifact-grid">{artifacts.length ? artifacts.map((artifact) => {
      const run = overview.runs.find((item) => item.id === artifact.runId);
      const node = run?.nodes.find((item) => item.id === artifact.nodeId);
      return <article key={artifact.id} className={artifact.stale ? "stale" : ""}><header><Archive /><span>{artifact.kind}</span><em>v{artifact.version}</em></header><h3>{artifact.label}</h3><p>{run?.title || artifact.runId} · {node?.name || artifact.nodeId}</p><dl><div><dt>生产者</dt><dd>{principalName(overview.principals, artifact.createdBy)}</dd></div><div><dt>输入引用</dt><dd>{artifact.inputArtifactIds.length}</dd></div><div><dt>状态</dt><dd>{artifact.stale ? "上游变化，需重做" : "当前有效"}</dd></div></dl><small>{artifact.id}</small></article>;
    }) : <EmptyState>节点保存交付物后会在这里形成版本库。</EmptyState>}</div>
  </section>;
}

function AuditView({ overview }: { overview: WorkflowOverview }) {
  return <section className="panel"><header className="panel-heading"><div><span>EVENT LEDGER</span><h2>完整审计</h2></div><small>{overview.recentEvents.length} 条最近记录</small></header>
    <div className="audit-table"><div className="audit-row head"><span>时间</span><span>事件</span><span>实际执行者</span><span>责任人</span><span>授权来源</span><span>详情</span></div>{overview.recentEvents.map((event) => <div className="audit-row" key={event.sequence}><span>{displayTime(event.createdAt)}</span><strong>{event.type}</strong><span>{principalName(overview.principals, event.actorPrincipalId)}</span><span>{principalName(overview.principals, event.accountablePrincipalId)}</span><span>{event.delegationGrantId || "直接权限"}</span><code>{JSON.stringify(event.payload)}</code></div>)}</div>
  </section>;
}

function SettingsView({ overview, busy, onCreate }: { overview: WorkflowOverview; busy: boolean; onCreate(input: { kind: "human" | "server_agent"; name: string; role: string; endpoint?: string; externalRef?: string; capabilities?: string[] }): Promise<void> }) {
  const [kind, setKind] = useState<"human" | "server_agent">("server_agent");
  const [name, setName] = useState("研究执行 Agent");
  const [endpoint, setEndpoint] = useState("");
  const [capabilities, setCapabilities] = useState("research, writing");
  return <div className="settings-layout"><section className="panel principal-form"><header className="panel-heading"><div><span>PRINCIPAL REGISTRY</span><h2>登记成员或 Agent</h2></div><UsersRound /></header><label>主体类型<select value={kind} onChange={(event) => setKind(event.target.value as typeof kind)}><option value="server_agent">服务器 Agent</option><option value="human">组织成员</option></select></label><label>显示名称<input value={name} onChange={(event) => setName(event.target.value)} /></label>{kind === "server_agent" ? <label>服务器端点<input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="http://127.0.0.1:8788" /></label> : null}<label>能力标签<input value={capabilities} onChange={(event) => setCapabilities(event.target.value)} /></label><button className="primary-button" disabled={busy || !name.trim()} onClick={() => void onCreate({ kind, name, role: "member", endpoint: endpoint || undefined, capabilities: capabilities.split(",").map((item) => item.trim()).filter(Boolean) })}><Plus />登记主体</button></section>
    <section className="panel"><header className="panel-heading"><div><span>ORGANIZATION</span><h2>{overview.organization.name}</h2></div><small>{overview.principals.length} 个主体</small></header><div className="principal-list">{overview.principals.map((principal) => <article key={principal.id}><div className={principal.kind === "server_agent" ? "agent-avatar" : "human-avatar"}>{principal.kind === "server_agent" ? <Bot /> : <UsersRound />}</div><div><strong>{principal.name}</strong><span>{principal.id}</span></div><em>{principal.role}</em><div className="capability-tags">{principal.capabilities.map((item) => <span key={item}>{item}</span>)}</div><small>{principal.endpoint || principal.externalRef || "本地身份"}</small></article>)}</div></section></div>;
}

type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;

export function WorkflowCenterApp() {
  const workspace = workspaceFromSearch();
  const modId = MOD_IDS[workspace];
  const [identity, setIdentity] = useState<Identity | undefined>(() => window.self === window.top ? { userId: "local-user", workspaceId: "local-workspace" } : undefined);
  const [actingPrincipalId, setActingPrincipalId] = useState("");
  const [overview, setOverview] = useState<WorkflowOverview>();
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [snapshot, setSnapshot] = useState<WorkflowRunSnapshot>();
  const [artifacts, setArtifacts] = useState<WorkflowArtifact[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [host, setHost] = useState<EmbeddedHost>();
  const client = useMemo(() => identity ? workflowClient(identity, actingPrincipalId) : undefined, [actingPrincipalId, identity]);
  const contextRef = useRef<ModPageContext>(buildContext(workspace));
  const actionRef = useRef<(actionId: string, input: Record<string, unknown>) => Promise<unknown>>(async () => ({}));

  const loadRun = useCallback(async (runId = selectedRunId) => {
    if (!client || !runId) { setSnapshot(undefined); return undefined; }
    const next = await client.run(runId);
    setSnapshot(next);
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
  return <main className="workflow-root">
    <header className="workflow-header"><div><span>WORKFLOW CONTROL</span><h1>{meta.title}</h1><p>{meta.description}</p></div><div className="header-controls"><label>当前执行身份<select value={actingPrincipalId || overview.currentPrincipal.id} onChange={(event) => setActingPrincipalId(event.target.value)}>{overview.principals.map((principal) => <option value={principal.id} key={principal.id}>{principal.kind === "server_agent" ? "Agent · " : "成员 · "}{principal.name}</option>)}</select></label><button className="icon-button" disabled={busy} onClick={() => void refresh()} title="刷新"><RefreshCw className={busy ? "spin" : ""} /></button></div></header>
    {error ? <div className="error-banner">{error}<button onClick={() => setError("")}><X /></button></div> : null}
    {workspace === "overview" ? <OverviewView overview={overview} /> : null}
    {workspace === "designer" ? <DesignerView overview={overview} busy={busy} onCreate={(input) => runMutation(() => client!.createTemplate(input)).then(() => undefined)} onVersion={(id, input) => runMutation(() => client!.createTemplateVersion(id, input)).then(() => undefined)} onLoadVersions={async (id) => (await client!.templateVersions(id)).versions} onRestore={(id, sourceVersion, expectedVersion, note) => runMutation(() => client!.restoreTemplateVersion(id, sourceVersion, expectedVersion, note)).then(() => undefined)} /> : null}
    {workspace === "runs" ? <RunsView overview={overview} snapshot={snapshot} selectedRunId={selectedRunId} selectedNodeId={selectedNodeId} busy={busy} onSelectRun={(id) => { setSelectedRunId(id); void loadRun(id); }} onSelectNode={setSelectedNodeId} onCreateRun={async (input) => { const created = await runMutation(() => client!.createRun(input), ""); setSelectedRunId(created.id); await loadRun(created.id); }} actions={operations} /> : null}
    {workspace === "delegations" ? <DelegationsView overview={overview} busy={busy} onCreate={(input) => runMutation(() => client!.createGrant(input)).then(() => undefined)} onRevoke={(id) => runMutation(() => client!.revokeGrant(id)).then(() => undefined)} /> : null}
    {workspace === "artifacts" ? <ArtifactsView overview={overview} artifacts={artifacts} /> : null}
    {workspace === "audit" ? <AuditView overview={overview} /> : null}
    {workspace === "settings" ? <SettingsView overview={overview} busy={busy} onCreate={(input) => runMutation(() => client!.createPrincipal(input)).then(() => undefined)} /> : null}
  </main>;
}
