import {
  ArrowRight,
  Box,
  Check,
  CircleAlert,
  CircleDot,
  ClipboardCheck,
  Clock3,
  Database,
  FileOutput,
  FileUp,
  Gauge,
  Layers3,
  MessageSquareText,
  PackagePlus,
  Play,
  RotateCcw,
  Search,
  Settings2,
  Square,
  Store,
  Workflow,
  Wrench,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { formatTime, statusLabel, statusTone } from "./presenters";
import type {
  CapabilityDetection,
  CreatorMarketplace,
  CreatorProductFile,
  CreatorRegistry,
  CreatorRunSummary,
  CreatorSnapshot,
  MarketplaceCompatibility,
  MarketplaceItem,
  MarketplacePreset,
  PublishIssue,
  SnapshotNode,
  SnapshotStage,
} from "./types";
import type { DeskAgentPreferences } from "./api";

function parseOpenChatCutProjectId(value: string): string | undefined {
  const input = value.trim();
  if (!input) return undefined;
  if (/^[A-Za-z0-9_-]{1,160}$/.test(input)) return input;
  const match = input.match(/#\/editor\/([^/?#]+)/);
  if (!match) return undefined;
  try {
    const projectId = decodeURIComponent(match[1]);
    return /^[A-Za-z0-9_-]{1,160}$/.test(projectId) ? projectId : undefined;
  } catch {
    return undefined;
  }
}

function remainingTime(deadline: string | undefined, now: number): string {
  if (!deadline) return "";
  const seconds = Math.max(0, Math.floor((new Date(deadline).getTime() - now) / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return seconds > 0 ? `${minutes}:${String(rest).padStart(2, "0")}` : "已超时";
}

export type ActionDispatcher = (
  actionId: string,
  input?: Record<string, unknown>,
) => Promise<unknown>;

function StatusPill({ status }: { status?: string }) {
  return <span className={"status-pill tone-" + statusTone(status)}><i />{statusLabel(status)}</span>;
}

function canRunAction(node: SnapshotNode, actionId: string) {
  return node.availableActions.includes(actionId);
}

function publishIssueLabel(issue: PublishIssue) {
  return [issue.kind, issue.channel, issue.slot, issue.taskId, issue.status]
    .filter(Boolean)
    .join(" · ");
}

function EmptyStudio({ onCreate }: { onCreate(): void }) {
  return (
    <section className="empty-studio">
      <div className="empty-orbit"><Workflow size={42} /><i /><i /><i /></div>
      <span className="eyebrow">EMPTY RUNWAY</span>
      <h2>还没有创作任务</h2>
      <p>从内容采集、长文、视频分镜或发布节点直接起步，系统会校验该节点所需素材。</p>
      <button className="primary-button" onClick={onCreate}><PackagePlus size={16} />新建第一个任务</button>
    </section>
  );
}

export function DashboardView({
  snapshot,
  selectedStage,
  selectedNode,
  onCreate,
  dispatch,
  runs = [],
  onSelectRun,
}: {
  snapshot?: CreatorSnapshot;
  selectedStage?: SnapshotStage;
  selectedNode?: SnapshotNode;
  onCreate(): void;
  dispatch: ActionDispatcher;
  runs?: CreatorRunSummary[];
  onSelectRun?(runId: string): void;
}) {
  if (!snapshot) return <EmptyStudio onCreate={onCreate} />;
  return (
    <div className="dashboard-view">
      <section className="runs-overview">
        <div className="section-heading">
          <div><span>TASK BOARD</span><h2>任务总览</h2></div>
          <small>{runs.length} 个任务{onSelectRun ? " · 点击切换" : ""}</small>
        </div>
        <div className="runs-grid">
          {runs.map((run) => (
            <button
              key={run.runId}
              className={"run-card" + (run.runId === snapshot.run.runId ? " active" : "")}
              onClick={() => onSelectRun?.(run.runId)}
            >
              <strong>{run.title}</strong>
              <span className="run-card-meta">
                <StatusPill status={run.status} />
                <small>{run.activeStageId ? "当前：" + run.activeStageId : "未开始"}</small>
              </span>
            </button>
          ))}
        </div>
      </section>
      <section className="run-hero">
        <div className="run-hero-copy">
          <span className="eyebrow">LIVE PRODUCTION MAP</span>
          <div className="run-title-line">
            <h1>{snapshot.run.title}</h1>
            <StatusPill status={snapshot.run.status} />
          </div>
          <p>任务状态由 Run Control 统一维护，Agent 与可视化操作会回到同一份快照。</p>
        </div>
        <div className="progress-dial" style={{ "--progress": snapshot.run.progress } as React.CSSProperties}>
          <strong>{snapshot.run.progress}</strong>
          <span>%</span>
        </div>
        <div className="hero-metrics">
          <article><ClipboardCheck size={16} /><strong>{snapshot.counters.waitingReview}</strong><span>待审核</span></article>
          <article><Box size={16} /><strong>{snapshot.counters.newArtifacts}</strong><span>新交付物</span></article>
          <article><CircleAlert size={16} /><strong>{snapshot.counters.blockedNodes}</strong><span>需处理</span></article>
        </div>
      </section>

      <section className="workflow-map">
        <div className="section-heading">
          <div><span>FLOW TUNNEL</span><h2>六阶段动态流程</h2></div>
          <small>更新 {formatTime(snapshot.generatedAt)}</small>
        </div>
        <div className="stage-map-grid">
          {snapshot.stages.map((stage, stageIndex) => (
            <article
              className={"stage-map-card " + (selectedStage?.id === stage.id ? "selected" : "")}
              style={{ "--stage-color": stage.color || "var(--creator-accent)" } as React.CSSProperties}
              key={stage.id}
              onClick={() => void dispatch("creator.node.select", {
                stageId: stage.id,
                nodeId: stage.nodes[0]?.id,
              })}
            >
              <div className="stage-map-index">{String(stageIndex + 1).padStart(2, "0")}</div>
              <div className="stage-map-title"><h3>{stage.name}</h3><StatusPill status={stage.status} /></div>
              <div className="stage-progress"><i style={{ width: String(stage.progress) + "%" }} /></div>
              <div className="node-dot-row">
                {stage.nodes.map((node) => (
                  <button
                    key={node.id}
                    title={node.name + " · " + statusLabel(node.status)}
                    className={"node-dot tone-" + statusTone(node.status) + (selectedNode?.id === node.id && selectedStage?.id === stage.id ? " selected" : "")}
                    onClick={(event) => {
                      event.stopPropagation();
                      void dispatch("creator.node.select", { stageId: stage.id, nodeId: node.id });
                    }}
                  >
                    <i />
                  </button>
                ))}
              </div>
              <footer><span>{stage.nodes.length} 个节点</span><strong>{stage.progress}%</strong></footer>
            </article>
          ))}
        </div>
      </section>

      <div className="dashboard-lower-grid">
        <section className="active-node-card">
          <div className="section-heading compact">
            <div><span>ACTIVE NODE</span><h2>{selectedNode?.name || "选择一个节点"}</h2></div>
            {selectedNode && <StatusPill status={selectedNode.status} />}
          </div>
          {selectedNode ? (
            <>
              <p>{selectedNode.description}</p>
              <dl className="node-facts">
                <div><dt>素材状态</dt><dd>{selectedNode.materialValidation.status === "ready" ? "已满足" : "缺 " + selectedNode.materialValidation.missing.length + " 项"}</dd></div>
                <div><dt>交付产品</dt><dd>{selectedNode.product?.availableCount || productFiles(selectedNode).length} 项</dd></div>
                <div><dt>执行次数</dt><dd>{selectedNode.attempt}</dd></div>
                <div><dt>可用能力</dt><dd>{selectedNode.capabilities.length} 项</dd></div>
              </dl>
              <div className="button-row">
                <button
                  className="primary-button"
                  disabled={!canRunAction(selectedNode, "creator.node.run")}
                  onClick={() => void dispatch("creator.node.run", {
                    stageId: selectedStage?.id,
                    nodeId: selectedNode.id,
                  })}
                ><Play size={15} />运行节点</button>
                <button className="secondary-button" disabled={!canRunAction(selectedNode, "creator.workflow.continue")} onClick={() => void dispatch("creator.workflow.continue", {
                  stageId: selectedStage?.id,
                  nodeId: selectedNode.id,
                })}>下一节点<ArrowRight size={15} /></button>
              </div>
            </>
          ) : <p className="quiet-card">点击流程图中的节点查看状态。</p>}
        </section>

        <section className="notification-board">
          <div className="section-heading compact">
            <div><span>INBOX</span><h2>待办与交付</h2></div>
            <small>{snapshot.notifications.length} 条</small>
          </div>
          <div className="notification-list">
            {snapshot.notifications.length === 0 ? <p className="quiet-card">当前没有待处理提醒。</p> : snapshot.notifications.slice(-8).reverse().map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  if (item.kind === "artifact") {
                    const stage = snapshot.stages.find((s) => s.id === item.stageId);
                    const node = stage?.nodes.find((n) => n.id === item.nodeId);
                    const art = node?.product?.deliverables.find((a) =>
                      a.artifactId === item.artifactId || a.path === item.artifactPath,
                    );
                    const handler = (window as unknown as { __creatorStudioOpenArtifact?: (path: string, label?: string) => void }).__creatorStudioOpenArtifact;
                    if (art?.path && handler) {
                      handler(art.path, art.label);
                      return;
                    }
                  }
                  void dispatch("creator.node.select", { stageId: item.stageId, nodeId: item.nodeId });
                }}
              >
                {item.kind === "review" ? <ClipboardCheck size={16} /> : item.kind === "artifact" ? <Box size={16} /> : <CircleAlert size={16} />}
                <span><strong>{item.title}</strong><small>{item.stageId} / {item.nodeId}</small></span>
                <ArrowRight size={14} />
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

const WORKSPACE_TABS = [
  ["status", "状态"],
  ["materials", "输入素材"],
  ["files", "本环节文件"],
  ["parameters", "参数配置"],
  ["feedback", "修改与反馈"],
  ["publish", "发布控制"],
  ["editor", "人工编辑"],
  ["logs", "运行日志"],
  ["handoff", "转接下一节点"],
] as const;


interface TopicCardOption {
  topic_id?: string;
  seed_id?: string;
  title?: string;
  one_line_judgment?: string;
  core_proposition?: string;
  reader_payoff?: string;
  score?: number;
  priority?: number;
  recommended?: boolean;
}

type TopicFilter = "top" | "recommended" | "all" | "s" | "a" | "b" | "c";

function topicScore(card: TopicCardOption): number {
  return Number(card.score ?? card.priority ?? 0);
}

function topicGrade(card: TopicCardOption): "S" | "A" | "B" | "C" {
  const score = topicScore(card);
  if (score >= 95) return "S";
  if (score >= 90) return "A";
  if (score >= 85) return "B";
  return "C";
}

function ReviewWorkCard({
  stage,
  node,
  dispatch,
  busy,
  fetchPreview,
}: {
  stage: SnapshotStage;
  node: SnapshotNode;
  dispatch: ActionDispatcher;
  busy: boolean;
  fetchPreview?(path: string): Promise<{ content?: string }>;
}) {
  const [topicCards, setTopicCards] = useState<TopicCardOption[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [topicFilter, setTopicFilter] = useState<TopicFilter>("top");
  const [topicSearch, setTopicSearch] = useState("");

  useEffect(() => {
    let active = true;
    setTopicCards([]);
    setSelected([]);
    setTopicFilter("top");
    setTopicSearch("");
    const interaction = node.product?.interaction;
    if (interaction?.mode === "select" && fetchPreview) {
      const sourceType = interaction.sourceType || "topic_cards";
      const source = stage.nodes.flatMap((item) => [
        ...(item.product?.deliverables || []),
        ...item.artifacts,
      ]).find((item) => item.type === sourceType && !["stale", "superseded", "failed"].includes(item.status));
      if (source) {
        fetchPreview(source.path)
          .then((result) => {
            const parsed = JSON.parse(result.content || "{}") as { topic_cards?: TopicCardOption[] } | TopicCardOption[];
            const cards = Array.isArray(parsed) ? parsed : parsed.topic_cards || [];
            if (active) setTopicCards(cards);
          })
          .catch(() => undefined);
      }
    }
    return () => { active = false; };
    // 依赖不含 revision：任何命令都会 +1，若依赖它则每次命令后卡片清空重拉，
    // 页面高度骤变会把滚动位置钳回顶部（浏览交付物时跳顶的根因之一）
  }, [stage, node.id, node.product?.interaction, fetchPreview]);

  // 可用性判断用 availableActions（全限定名）；actions 是展示用短名
  const canApprove = node.availableActions.includes("creator.node.approve");
  const canComplete = node.availableActions.includes("creator.node.complete");
  const canRequestChanges = node.availableActions.includes("creator.node.request-changes");
  const interaction = node.product?.interaction;
  const minSelect = interaction?.minSelect || 1;
  const maxSelect = interaction?.maxSelect || Number.POSITIVE_INFINITY;
  const rankedCards = useMemo(
    () => [...topicCards].sort((left, right) => topicScore(right) - topicScore(left)),
    [topicCards],
  );
  const recommendedCards = useMemo(() => {
    const marked = rankedCards.filter((card) => card.recommended);
    return (marked.length ? marked : rankedCards).slice(0, Number.isFinite(maxSelect) ? maxSelect : 10);
  }, [rankedCards, maxSelect]);
  const visibleCards = useMemo(() => {
    const keyword = topicSearch.trim().toLowerCase();
    return rankedCards.filter((card, index) => {
      if (topicFilter === "top" && index >= 10) return false;
      if (topicFilter === "recommended" && !recommendedCards.includes(card)) return false;
      if (["s", "a", "b", "c"].includes(topicFilter) && topicGrade(card).toLowerCase() !== topicFilter) return false;
      if (!keyword) return true;
      return [card.topic_id, card.title, card.one_line_judgment, card.core_proposition, card.reader_payoff]
        .some((value) => String(value || "").toLowerCase().includes(keyword));
    });
  }, [rankedCards, recommendedCards, topicFilter, topicSearch]);
  const selectionReady = interaction?.mode !== "select"
    || (selected.length >= minSelect && selected.length <= maxSelect);

  const approve = () => void dispatch("creator.node.approve", {
    stageId: stage.id,
    nodeId: node.id,
    ...(selected.length ? { selectedTopicIds: selected, note: "批准所选选题：" + selected.join("、") } : {}),
  });

  if (node.status !== "waiting_user") return null;

  return (
    <section className="review-workcard">
      <header className="review-workcard-header">
        <strong>人工介入 · {node.name}</strong>
        <StatusPill status={node.status} />
      </header>
      {topicCards.length > 0 ? (
        <div className="topic-review-shell">
          <div className="topic-review-toolbar">
            <label className="topic-search">
              <Search size={14} />
              <input aria-label="搜索选题" value={topicSearch} onChange={(event) => setTopicSearch(event.target.value)} placeholder="搜索标题、判断或关键词" />
            </label>
            <div className="topic-filter-row" aria-label="选题筛选">
              {([
                ["top", "优先 10"],
                ["recommended", "系统推荐"],
                ["all", "全部"],
                ["s", "S"],
                ["a", "A"],
                ["b", "B"],
                ["c", "C"],
              ] as Array<[TopicFilter, string]>).map(([id, label]) => (
                <button key={id} type="button" className={topicFilter === id ? "active" : ""} onClick={() => setTopicFilter(id)}>{label}</button>
              ))}
            </div>
          </div>
          <div className="topic-selection-summary">
            <span>已选 <strong>{selected.length}</strong> / {Number.isFinite(maxSelect) ? maxSelect : "不限"}，至少选择 {minSelect} 个</span>
            <div>
              <button type="button" onClick={() => setSelected(recommendedCards.map((card) => String(card.topic_id || "")).filter(Boolean))}>采用系统推荐</button>
              <button type="button" disabled={!selected.length} onClick={() => setSelected([])}>清空</button>
            </div>
          </div>
          <div className="topic-option-list">
            {visibleCards.map((card) => {
              const id = String(card.topic_id || "");
              const active = selected.includes(id);
              const atLimit = !active && selected.length >= maxSelect;
              return (
                <button
                  key={id}
                  type="button"
                  aria-pressed={active}
                  className={"topic-option" + (active ? " active" : "")}
                  onClick={() => {
                    if (active) setSelected(selected.filter((item) => item !== id));
                    else if (!atLimit) setSelected([...selected, id]);
                  }}
                >
                  <span className="topic-option-meta">
                    <b>{id}</b>
                    <i>{topicGrade(card)} · {topicScore(card)} 分</i>
                    {card.recommended ? <em>推荐</em> : null}
                  </span>
                  <strong>{String(card.title || "")}</strong>
                  <p>{String(card.one_line_judgment || "")}</p>
                  {card.core_proposition ? <small>{String(card.core_proposition)}</small> : null}
                  {active ? <span className="topic-selected-mark"><Check size={12} />已选择</span> : null}
                </button>
              );
            })}
            {visibleCards.length === 0 ? <p className="quiet-card topic-no-result">没有匹配的选题。</p> : null}
          </div>
        </div>
      ) : null}
      <p className="review-note">
        {node.description} 批准后流程自动进入下一节点；退回将把修改意见送回执行方。
      </p>
      <div className="button-row">
        {canApprove && (
          <button
            className="primary-button"
            disabled={busy || !selectionReady}
            onClick={approve}
          ><Check size={15} />{interaction?.mode === "select"
              ? selected.length
                ? `${interaction.actionLabel || "确认所选"}（${selected.length}）`
                : `请选择 ${minSelect}—${Number.isFinite(maxSelect) ? maxSelect : "多"} 个`
              : "批准"}</button>
        )}
        {canComplete && (
          <button
            className="primary-button"
            disabled={busy}
            onClick={() => void dispatch("creator.node.complete", { stageId: stage.id, nodeId: node.id })}
          ><Check size={15} />确认完成</button>
        )}
        {canRequestChanges && (
          <button
            className="danger-button"
            disabled={busy}
            onClick={() => void dispatch("creator.node.request-changes", { stageId: stage.id, nodeId: node.id, message: "请按反馈修改" })}
          >退回修改</button>
        )}
      </div>
    </section>
  );
}

function productFiles(node: SnapshotNode): CreatorProductFile[] {
  if (node.product?.deliverables) return node.product.deliverables;
  return node.artifacts
    .filter((item) => !["system", "packet", "runtime"].includes(item.origin || ""))
    .map((item) => ({
      id: item.id,
      name: item.path.split("/").pop() || item.type,
      label: item.label || item.type,
      type: item.type,
      path: item.path,
      relativePath: item.path,
      role: "primary",
      status: item.status,
      source: "artifact",
      artifactId: item.id,
      version: item.version,
    }));
}

function ProductDeliveryCard({
  node,
  openArtifact,
}: {
  node: SnapshotNode;
  openArtifact?(path: string, label?: string): void;
}) {
  const deliverables = productFiles(node);
  const supporting = node.product?.supportingFiles || [];
  const expected = node.product?.expected || [];
  return (
    <section className="product-delivery-card">
      <header className="product-delivery-header">
        <div>
          <span>本节点交付产品</span>
          <h2>{node.product?.title || node.name}</h2>
          <p>{node.product?.summary || node.description}</p>
        </div>
        <strong>{deliverables.length}<small>份可审核</small></strong>
      </header>
      {deliverables.length ? (
        <div className="product-file-grid">
          {deliverables.map((file) => (
            <button key={file.id} type="button" onClick={() => openArtifact?.(file.path, file.label)}>
              <FileOutput size={19} />
              <span><strong>{file.label}</strong><small>点击查看内容 · {statusLabel(file.status)}</small></span>
              <ArrowRight size={14} />
            </button>
          ))}
        </div>
      ) : (
        <div className="product-empty">
          <Clock3 size={18} />
          <div><strong>本节点还没有生成可审核产品</strong><small>{expected.length ? `等待：${expected.map((item) => item.label).join("、")}` : "运行节点后将在这里显示交付内容"}</small></div>
        </div>
      )}
      {expected.length > 0 && (
        <div className="product-readiness">
          {expected.map((item) => <span className={item.ready ? "ready" : "pending"} key={item.type}>{item.ready ? <Check size={12} /> : <Clock3 size={12} />}{item.label}</span>)}
        </div>
      )}
      {supporting.length > 0 && (
        <details className="supporting-files">
          <summary>参考资料与底层文档（{supporting.length}）</summary>
          <div>
            {supporting.map((file) => <button key={file.id} type="button" onClick={() => openArtifact?.(file.path, file.label)}><Database size={14} />{file.label}</button>)}
          </div>
        </details>
      )}
    </section>
  );
}

export function WorkbenchView({
  snapshot,
  selectedStage,
  selectedNode,
  dispatch,
  busy,
  onCreate,
  fetchPreview,
  openArtifact,
}: {
  snapshot?: CreatorSnapshot;
  selectedStage?: SnapshotStage;
  selectedNode?: SnapshotNode;
  dispatch: ActionDispatcher;
  busy: boolean;
  onCreate(): void;
  fetchPreview?(path: string): Promise<{ content?: string }>;
  openArtifact?(path: string, label?: string): void;
}) {
  const [tab, setTab] = useState<(typeof WORKSPACE_TABS)[number][0]>("status");
  const [materialType, setMaterialType] = useState("");
  const [materialPath, setMaterialPath] = useState("");
  const [artifactType, setArtifactType] = useState("");
  const [artifactPath, setArtifactPath] = useState("");
  const [selectedEditorId, setSelectedEditorId] = useState("");
  const [editorOutputType, setEditorOutputType] = useState("");
  const [editorOutputPath, setEditorOutputPath] = useState("");
  const [agentPrompt, setAgentPrompt] = useState("请根据当前分镜、素材清单和节点反馈完成剪辑，先生成可审核提案，不要直接改正式时间线。");
  const [externalProjectInput, setExternalProjectInput] = useState("");
  const [projectBindingError, setProjectBindingError] = useState("");
  const [editorExportUrl, setEditorExportUrl] = useState("");
  const [editorRenderId, setEditorRenderId] = useState("");
  const [clockNow, setClockNow] = useState(Date.now());
  const [templateName, setTemplateName] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [feedback, setFeedback] = useState("");
  const [parameterJson, setParameterJson] = useState("{}");
  const [parameterError, setParameterError] = useState("");
  const targetOptions = useMemo(() => snapshot?.stages.flatMap((stage) => (
    stage.nodes.map((node) => ({ stageId: stage.id, nodeId: node.id, label: stage.name + " / " + node.name }))
  )) ?? [], [snapshot]);
  const [handoffTarget, setHandoffTarget] = useState("");

  useEffect(() => {
    setParameterJson(JSON.stringify(selectedNode?.parameters ?? {}, null, 2));
    setParameterError("");
  }, [selectedNode?.id, selectedNode?.parameters]);

  useEffect(() => {
    const editors = selectedNode?.editorSession?.editors ?? [];
    const preferred = editors.find((item) => item.id === selectedNode?.editorSession?.selectedEditorId)
      ?? editors.find((item) => item.status === "available")
      ?? editors[0];
    setSelectedEditorId(preferred?.id || "");
    setEditorOutputType(selectedNode?.editorSession?.outputContract[0] || "");
    setEditorOutputPath("");
    setExternalProjectInput(selectedNode?.editorSession?.externalProject?.projectId || "");
    setProjectBindingError("");
    setEditorExportUrl("");
    setEditorRenderId("");
    setTemplateName(snapshot?.run.title ? `${snapshot.run.title} 剪辑模板` : "");
    setTemplateId("");
  }, [
    selectedNode?.editorSession?.sessionId,
    selectedNode?.editorSession?.selectedEditorId,
    selectedNode?.editorSession?.externalProject?.projectId,
    selectedNode?.id,
    snapshot?.run.title,
  ]);

  useEffect(() => {
    const deadline = selectedNode?.editorSession?.collaboration?.reviewDeadlineAt;
    if (!deadline) return undefined;
    setClockNow(Date.now());
    const timer = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [selectedNode?.editorSession?.collaboration?.reviewDeadlineAt]);

  useEffect(() => {
    if (selectedStage?.id !== "publish" && tab === "publish") setTab("status");
  }, [selectedStage?.id, tab]);

  if (!snapshot || !selectedStage || !selectedNode) return <EmptyStudio onCreate={onCreate} />;
  const defaultTarget = targetOptions.find((item) => (
    item.stageId !== selectedStage.id || item.nodeId !== selectedNode.id
  ));
  const target = handoffTarget || (defaultTarget
    ? defaultTarget.stageId + "." + defaultTarget.nodeId
    : "");
  const nodeTarget = { stageId: selectedStage.id, nodeId: selectedNode.id };
  const selectedEditor = selectedNode.editorSession?.editors.find((editor) => editor.id === selectedEditorId);
  const publishState = snapshot.publishState;
  const handoffArtifacts = selectedNode.artifacts.filter((artifact) =>
    ["created", "approved", "succeeded"].includes(artifact.status),
  );
  const outgoingHandoffs = snapshot.handoffs.filter((handoff) =>
    handoff.source.stageId === selectedStage.id && handoff.source.nodeId === selectedNode.id,
  );
  const collaborationStatus = selectedNode.editorSession?.collaboration?.status;
  const stageFiles = snapshot.fileCatalog?.entries?.filter((item) => item.stageId === selectedStage.id) || [];
  const userFiles = stageFiles.filter((item) => item.role === "primary" || item.role === "supporting");
  const backgroundFiles = stageFiles.filter((item) => item.role === "system" || item.role === "raw");
  const reviewTime = collaborationStatus === "awaiting_review"
    ? remainingTime(selectedNode.editorSession?.collaboration?.reviewDeadlineAt, clockNow)
    : "";

  const currentProjectId = () => {
    const value = externalProjectInput.trim();
    if (!value) {
      setProjectBindingError("");
      return selectedNode.editorSession?.externalProject?.projectId || "";
    }
    const projectId = parseOpenChatCutProjectId(value);
    if (!projectId) {
      setProjectBindingError("请粘贴 OpenChatCut 工程链接，或填写有效工程 ID");
      return null;
    }
    setProjectBindingError("");
    return projectId;
  };

  const attachMaterial = async (event: FormEvent) => {
    event.preventDefault();
    await dispatch("creator.material.attach", {
      ...nodeTarget,
      type: materialType,
      path: materialPath,
      source: "manual",
    });
    setMaterialPath("");
  };
  const registerArtifact = async (event: FormEvent) => {
    event.preventDefault();
    await dispatch("creator.artifact.register", {
      ...nodeTarget,
      type: artifactType,
      path: artifactPath,
    });
    setArtifactPath("");
  };
  const submitFeedback = async (actionId: string) => {
    await dispatch(actionId, { ...nodeTarget, message: feedback });
    setFeedback("");
  };
  const createHandoff = async () => {
    const [targetStageId, targetNodeId] = String(target).split(".", 2);
    await dispatch("creator.handoff.create", {
      ...nodeTarget,
      targetStageId,
      targetNodeId,
      artifactIds: handoffArtifacts.map((artifact) => artifact.id),
    });
  };
  const saveParameters = async () => {
    try {
      const parameters = JSON.parse(parameterJson) as Record<string, unknown>;
      if (!parameters || Array.isArray(parameters) || typeof parameters !== "object") throw new Error();
      setParameterError("");
      await dispatch("creator.node.configure", { ...nodeTarget, parameters, replace: true });
    } catch {
      setParameterError("参数必须是合法的 JSON 对象");
    }
  };
  const launchEditor = async () => {
    const externalProjectId = selectedEditorId === "openchatcut" ? currentProjectId() : "";
    if (externalProjectId === null) return;
    const next = await dispatch("creator.editor.launch", {
      ...nodeTarget,
      sessionId: selectedNode.editorSession?.sessionId,
      editorId: selectedEditorId,
      externalProjectId,
    }) as CreatorSnapshot;
    const node = next.stages
      .find((stage) => stage.id === selectedStage.id)
      ?.nodes.find((item) => item.id === selectedNode.id);
    const launchUrl = node?.editorSession?.launch?.launchUrl;
    if (launchUrl) window.open(launchUrl, "_blank", "noopener,noreferrer");
  };
  const saveEditor = async (event: FormEvent) => {
    event.preventDefault();
    await dispatch("creator.editor.save", {
      ...nodeTarget,
      sessionId: selectedNode.editorSession?.sessionId,
      outputs: [{ type: editorOutputType, path: editorOutputPath }],
    });
    setEditorOutputPath("");
  };
  const startAgentEdit = async () => {
    const externalProjectId = selectedEditorId === "openchatcut" ? currentProjectId() : "";
    if (externalProjectId === null) return;
    const next = await dispatch("creator.editor.start-agent", {
      ...nodeTarget,
      sessionId: selectedNode.editorSession?.sessionId,
      editorId: selectedEditorId,
      approvalMode: "manual",
      prompt: agentPrompt,
      externalProjectId,
    }) as CreatorSnapshot;
    const node = next.stages
      .find((stage) => stage.id === selectedStage.id)
      ?.nodes.find((item) => item.id === selectedNode.id);
    const launchUrl = node?.editorSession?.launch?.launchUrl;
    if (launchUrl) window.open(launchUrl, "_blank", "noopener,noreferrer");
    window.parent.postMessage({
      type: "vibedesk:copilot-open",
      mode: "edit",
      prompt: agentPrompt.trim(),
    }, "*");
  };
  const reviewProposal = async (decision: "applied" | "rejected") => {
    await dispatch("creator.editor.review-proposal", {
      ...nodeTarget,
      sessionId: selectedNode.editorSession?.sessionId,
      decision,
      externalProjectId: selectedNode.editorSession?.externalProject?.projectId,
      note: decision === "applied" ? "已在 OpenChatCut 审核并应用" : "已在 OpenChatCut 拒绝提案",
    });
  };
  const importEditorExport = async (event: FormEvent) => {
    event.preventDefault();
    const externalProjectId = currentProjectId();
    if (!externalProjectId) {
      if (externalProjectId !== null) setProjectBindingError("导入前请先绑定 OpenChatCut 工程");
      return;
    }
    await dispatch("creator.editor.import-export", {
      ...nodeTarget,
      sessionId: selectedNode.editorSession?.sessionId,
      externalProjectId,
      downloadUrl: editorExportUrl,
      renderId: editorRenderId,
    });
    setEditorExportUrl("");
    setEditorRenderId("");
  };
  const saveEditorTemplate = async (event: FormEvent) => {
    event.preventDefault();
    await dispatch("creator.editor.save-template", {
      ...nodeTarget,
      sessionId: selectedNode.editorSession?.sessionId,
      templateId,
      name: templateName,
      mode: "project",
      sourceAction: "manage_template.save",
    });
    setTemplateId("");
  };
  const confirmPublish = async () => {
    if (!window.confirm("确认后，当前节点将获得一次真实发布执行权限。是否继续？")) return;
    await dispatch("creator.publish.confirm", {
      ...nodeTarget,
      confirmed: true,
      confirmationText: "确认发布",
    });
  };

  return (
    <div
      className="workbench-layout"
      style={{ "--stage-color": selectedStage.color || "var(--creator-accent)" } as React.CSSProperties}
    >
      <main className="node-workspace">
        <section className="node-lane">
          <div className="section-heading compact">
            <div><span>NODE LANE</span><h2>{selectedStage.name}</h2></div>
            <StatusPill status={selectedStage.status} />
          </div>
          <div className="node-tab-flow">
            {selectedStage.nodes.map((node, index) => (
              <button
                className={selectedNode.id === node.id ? "selected" : ""}
                key={node.id}
                onClick={() => void dispatch("creator.node.select", { stageId: selectedStage.id, nodeId: node.id })}
              >
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div><strong>{node.name}</strong><small>{statusLabel(node.status)} · {node.product?.availableCount || 0} 份交付</small></div>
                <i className={"tone-" + statusTone(node.status)} />
              </button>
            ))}
          </div>
        </section>

        <section className="node-detail">
          <header className="node-detail-header">
            <div>
              <span className="eyebrow">{selectedStage.id} / {selectedNode.id}</span>
              <div className="run-title-line"><h1>{selectedNode.name}</h1><StatusPill status={selectedNode.status} /></div>
              <p>{selectedNode.description}</p>
            </div>
            <div className="node-header-actions">
              <button
                className="primary-button"
                disabled={busy || !canRunAction(selectedNode, "creator.node.run")}
                onClick={() => void dispatch("creator.node.run", nodeTarget)}
              ><Play size={15} />运行</button>
              <button
                className="secondary-button"
                disabled={busy || !canRunAction(selectedNode, "creator.node.retry")}
                onClick={() => void dispatch("creator.node.retry", nodeTarget)}
              ><RotateCcw size={15} />重试</button>
              <button
                className="danger-button"
                disabled={busy || !canRunAction(selectedNode, "creator.node.cancel")}
                onClick={() => void dispatch("creator.node.cancel", nodeTarget)}
              ><Square size={14} />取消</button>
              <button
                className="secondary-button"
                disabled={busy || !canRunAction(selectedNode, "creator.workflow.continue")}
                onClick={() => void dispatch("creator.workflow.continue", nodeTarget)}
              >下一节点<ArrowRight size={15} /></button>
            </div>
          </header>

          <ProductDeliveryCard node={selectedNode} openArtifact={openArtifact} />

          <ReviewWorkCard
            stage={selectedStage}
            node={selectedNode}
            dispatch={dispatch}
            busy={busy}
            fetchPreview={fetchPreview}
          />

          <nav className="workspace-tabs">
            {WORKSPACE_TABS.filter(([id]) => id !== "publish" || selectedStage.id === "publish").map(([id, label]) => (
              <button className={tab === id ? "selected" : ""} key={id} onClick={() => setTab(id)}>{label}</button>
            ))}
          </nav>

          <div className="workspace-panel">
            {tab === "status" && (
              <div className="status-panel-grid">
                <section className="workspace-card">
                  <div className="section-heading compact"><div><span>PROGRESS</span><h3>本节点进度</h3></div><Gauge size={18} /></div>
                  {selectedNode.staleReason && <div className="lineage-warning"><CircleAlert size={17} /><div><strong>上游版本已变化</strong><small>{selectedNode.staleReason} · {formatTime(selectedNode.staleAt)}</small></div></div>}
                  <div className={"readiness-banner " + (selectedNode.materialValidation.status === "ready" ? "ready" : "missing")}>
                    {selectedNode.materialValidation.status === "ready" ? <Check size={18} /> : <CircleAlert size={18} />}
                    <div><strong>{selectedNode.materialValidation.status === "ready" ? "素材已满足，可以运行" : "仍缺少前置素材"}</strong><small>{selectedNode.materialValidation.missing.map((item) => item.label).join("、") || "所有必需材料均已绑定"}</small></div>
                  </div>
                  <dl className="node-facts wide">
                    <div><dt>进度</dt><dd>{selectedNode.progress}%</dd></div>
                    <div><dt>执行次数</dt><dd>{selectedNode.attempt}</dd></div>
                    <div><dt>输入资料</dt><dd>{selectedNode.materials.length}</dd></div>
                    <div><dt>可审核产品</dt><dd>{selectedNode.product?.availableCount || productFiles(selectedNode).length}</dd></div>
                  </dl>
                </section>
                <section className="workspace-card">
                  <div className="section-heading compact"><div><span>DELIVERY</span><h3>审核与下一步</h3></div><ClipboardCheck size={18} /></div>
                  <div className="delivery-status-list">
                    {(selectedNode.product?.expected || []).map((item) => (
                      <div key={item.type} className={item.ready ? "ready" : "pending"}>
                        {item.ready ? <Check size={15} /> : <Clock3 size={15} />}
                        <span><strong>{item.label}</strong><small>{item.ready ? "已生成，可打开审核" : "等待当前节点生成"}</small></span>
                      </div>
                    ))}
                    {(selectedNode.product?.expected || []).length === 0 ? (
                      <div className="pending"><Clock3 size={15} /><span><strong>等待交付产品</strong><small>产品生成后会直接显示在上方</small></span></div>
                    ) : null}
                  </div>
                  <p className="next-step-note">{selectedNode.status === "waiting_user"
                    ? "当前需要你审核或选择；确认后系统会把结果自动转交下一节点。"
                    : selectedNode.status === "succeeded"
                      ? "本节点已完成，可查看上方产品或进入下一节点。"
                      : selectedNode.status === "running"
                        ? "系统正在生产，完成后会自动刷新交付产品。"
                        : "等待前置资料完成后即可运行。"}</p>
                </section>
              </div>
            )}

            {tab === "materials" && (
              <div className="split-panel">
                <section className="workspace-card">
                  <div className="section-heading compact"><div><span>BOUND MATERIALS</span><h3>已绑定素材</h3></div><Database size={18} /></div>
                  <div className="file-list">
                    {selectedNode.materials.length === 0 ? <p className="quiet-card">尚未绑定素材。</p> : selectedNode.materials.map((material, index) => (
                      <article key={material.path + String(index)}><FileUp size={16} /><div><strong>{material.label || material.type}</strong><small>{material.path}</small>{material.artifactId && <small>来源 {material.sourceStageId}/{material.sourceNodeId} · v{material.artifactVersion || 1} · {material.contentDigest?.slice(0, 10)}</small>}</div><StatusPill status={material.status || material.source || "manual"} /></article>
                    ))}
                  </div>
                </section>
                <form className="workspace-card action-form" onSubmit={(event) => void attachMaterial(event)}>
                  <div className="section-heading compact"><div><span>ADD MATERIAL</span><h3>补充素材</h3></div><PackagePlus size={18} /></div>
                  <label className="field"><span>素材类型</span><input value={materialType} onChange={(event) => setMaterialType(event.target.value)} placeholder="例如：scene_plan" required /></label>
                  <label className="field"><span>文件路径或 URL</span><input value={materialPath} onChange={(event) => setMaterialPath(event.target.value)} placeholder="/path/to/file.json" required /></label>
                  <button className="primary-button" disabled={busy || !canRunAction(selectedNode, "creator.material.attach")}>绑定到当前节点</button>
                </form>
              </div>
            )}

            {tab === "files" && (
              <section className="workspace-card stage-file-catalog">
                <div className="section-heading compact"><div><span>STAGE FILE CATALOG</span><h3>{selectedStage.name} · 全部生产文件</h3></div><Box size={18} /></div>
                <p className="catalog-intro">交付产品和参考资料优先展示；执行结果、会话文件和原始抓取数据默认收起。</p>
                <div className="file-list">
                  {userFiles.length === 0 ? <p className="quiet-card">本环节还没有可查看的生产文件。</p> : userFiles.map((file) => (
                    <article key={file.id} className="artifact-clickable" onClick={() => openArtifact?.(file.path, file.label)}>
                      <FileOutput size={16} />
                      <div><strong>{file.label}</strong><small>{file.name} · {file.nodeId ? selectedStage.nodes.find((node) => node.id === file.nodeId)?.name : "环节资料"}</small></div>
                      <span className={"file-role " + file.role}>{file.role === "primary" ? "交付" : "参考"}</span>
                    </article>
                  ))}
                </div>
                {backgroundFiles.length > 0 && (
                  <details className="background-file-catalog">
                    <summary>后台与原始文件（{backgroundFiles.length}）</summary>
                    <div className="file-list compact-files">
                      {backgroundFiles.map((file) => (
                        <article key={file.id} className="artifact-clickable" onClick={() => openArtifact?.(file.path, file.label)}>
                          <Database size={15} /><div><strong>{file.name}</strong><small>{file.relativePath}</small></div>
                          <span className={"file-role " + file.role}>{file.role === "raw" ? "原始" : "后台"}</span>
                        </article>
                      ))}
                    </div>
                  </details>
                )}
                <details className="manual-artifact-register">
                  <summary>登记外部生成的成品</summary>
                  <form className="action-form inline-register" onSubmit={(event) => void registerArtifact(event)}>
                    <label className="field"><span>产品类型</span><input value={artifactType} onChange={(event) => setArtifactType(event.target.value)} placeholder={selectedNode.outputs[0] || "artifact"} required /></label>
                    <label className="field"><span>文件路径</span><input value={artifactPath} onChange={(event) => setArtifactPath(event.target.value)} placeholder="/path/to/output" required /></label>
                    <button className="primary-button" disabled={busy || !canRunAction(selectedNode, "creator.artifact.register")}>登记成品</button>
                  </form>
                </details>
              </section>
            )}

            {tab === "parameters" && (
              <div className="status-panel-grid">
                <section className="workspace-card action-form">
                  <div className="section-heading compact"><div><span>PARAMETERS</span><h3>节点参数</h3></div><Settings2 size={18} /></div>
                  <label className="field"><span>JSON 配置</span><textarea value={parameterJson} onChange={(event) => setParameterJson(event.target.value)} rows={12} /></label>
                  {parameterError && <small className="field-error">{parameterError}</small>}
                  <button className="primary-button" disabled={busy || !canRunAction(selectedNode, "creator.node.configure")} onClick={() => void saveParameters()}>保存参数</button>
                </section>
                <section className="workspace-card">
                  <div className="section-heading compact"><div><span>REGISTERED ACTIONS</span><h3>节点操作</h3></div><Workflow size={18} /></div>
                  <div className="tag-cloud">{selectedNode.actions.map((action) => <span key={action}>{action}</span>)}</div>
                </section>
              </div>
            )}

            {tab === "feedback" && (
              <div className="split-panel">
                <section className="workspace-card">
                  <div className="section-heading compact"><div><span>FEEDBACK THREAD</span><h3>修改记录</h3></div><MessageSquareText size={18} /></div>
                  <div className="feedback-list">
                    {selectedNode.feedback.length === 0 ? <p className="quiet-card">暂无修改反馈。</p> : selectedNode.feedback.slice().reverse().map((item) => (
                      <article key={item.id}><p>{item.message}</p><small>{formatTime(item.createdAt)}</small></article>
                    ))}
                  </div>
                </section>
                <section className="workspace-card action-form">
                  <div className="section-heading compact"><div><span>REVIEW GATE</span><h3>审核与反馈</h3></div><ClipboardCheck size={18} /></div>
                  <label className="field"><span>反馈内容</span><textarea value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="说明需要修改的具体位置和判断标准" /></label>
                  <button className="secondary-button" disabled={busy || !feedback.trim() || !canRunAction(selectedNode, "creator.node.submit-feedback")} onClick={() => void submitFeedback("creator.node.submit-feedback")}>提交反馈</button>
                  <div className="button-row">
                    <button className="danger-button" disabled={busy || !canRunAction(selectedNode, "creator.node.request-changes")} onClick={() => void submitFeedback("creator.node.request-changes")}>退回修改</button>
                    <button className="primary-button" disabled={busy || !canRunAction(selectedNode, "creator.node.approve")} onClick={() => void dispatch("creator.node.approve", nodeTarget)}>审核通过</button>
                  </div>
                </section>
              </div>
            )}

            {tab === "publish" && selectedStage.id === "publish" && (
              <div className="publish-control-grid">
                <section className="workspace-card">
                  <div className="section-heading compact"><div><span>PREFLIGHT</span><h3>发布预检</h3></div><ClipboardCheck size={18} /></div>
                  <StatusPill status={publishState?.preflight?.nodeStatus || publishState?.preflight?.status || "pending"} />
                  <dl className="publish-metrics">
                    <div><dt>任务</dt><dd>{publishState?.preflight?.taskCount ?? 0}</dd></div>
                    <div><dt>阻塞</dt><dd>{publishState?.preflight?.blockers?.length ?? 0}</dd></div>
                    <div><dt>提醒</dt><dd>{publishState?.preflight?.warnings?.length ?? 0}</dd></div>
                  </dl>
                  <div className="publish-account-list">
                    {publishState?.preflight?.accountHealth?.accounts?.length
                      ? publishState.preflight.accountHealth.accounts.map((account, index) => (
                        <div key={`${account.channel}-${account.slot}-${index}`}><span>{account.label || `${account.channel}/${account.slot}`}</span><StatusPill status={account.status} /></div>
                      ))
                      : <p className="quiet-card">运行发布预检后显示账号健康。</p>}
                  </div>
                  {[...(publishState?.preflight?.blockers ?? []), ...(publishState?.preflight?.warnings ?? [])].map((issue, index) => (
                    <p className="publish-issue" key={`${publishIssueLabel(issue)}-${index}`}><CircleAlert size={14} />{publishIssueLabel(issue)}</p>
                  ))}
                </section>

                <section className="workspace-card action-form">
                  <div className="section-heading compact"><div><span>CONFIRMATION</span><h3>真实发布确认</h3></div><CircleAlert size={18} /></div>
                  <div className={`readiness-banner ${publishState?.confirmation?.confirmed && !publishState.confirmation.consumedByJobId ? "ready" : "missing"}`}>
                    {publishState?.confirmation?.confirmed && !publishState.confirmation.consumedByJobId ? <Check size={18} /> : <CircleAlert size={18} />}
                    <div>
                      <strong>{publishState?.confirmation?.confirmed && !publishState.confirmation.consumedByJobId ? "本次确认尚未消费" : publishState?.confirmation?.consumedByJobId ? "上次确认已消费" : "尚未确认真实发布"}</strong>
                      <small>{publishState?.confirmation?.confirmedAt ? formatTime(publishState.confirmation.confirmedAt) : "预检通过后再确认"}</small>
                    </div>
                  </div>
                  <p className="publish-safety-note">确认只允许执行一次；失败重试必须重新确认。</p>
                  <button className="danger-button" disabled={busy || !canRunAction(selectedNode, "creator.publish.confirm")} onClick={() => void confirmPublish()}>确认发布</button>
                </section>

                <section className="workspace-card">
                  <div className="section-heading compact"><div><span>EXECUTION</span><h3>执行结果</h3></div><Play size={18} /></div>
                  <StatusPill status={publishState?.execution?.nodeStatus || publishState?.execution?.status || "pending"} />
                  <dl className="publish-metrics">
                    <div><dt>成功</dt><dd>{publishState?.execution?.succeeded ?? 0}</dd></div>
                    <div><dt>失败</dt><dd>{publishState?.execution?.failed ?? 0}</dd></div>
                  </dl>
                  <p className="publish-path">{publishState?.execution?.receipts || "尚未生成平台回执"}</p>
                </section>

                <section className="workspace-card">
                  <div className="section-heading compact"><div><span>VERIFY</span><h3>回执验真</h3></div><Check size={18} /></div>
                  <StatusPill status={publishState?.verification?.nodeStatus || publishState?.verification?.status || "pending"} />
                  <dl className="publish-metrics">
                    <div><dt>验真报告</dt><dd>{publishState?.verification?.verificationCount ?? 0}</dd></div>
                    <div><dt>异常</dt><dd>{publishState?.verification?.failures?.length ?? 0}</dd></div>
                  </dl>
                  <p className="publish-path">{publishState?.verification?.postmortemHandoff || "尚未生成复盘交接"}</p>
                </section>
              </div>
            )}

            {tab === "editor" && (
              <div className="split-panel">
                <section className="workspace-card action-form">
                  <div className="section-heading compact"><div><span>HUMAN EDIT</span><h3>人工时间线</h3></div><Wrench size={18} /></div>
                  {!selectedNode.editorSession ? (
                    <p className="quiet-card">运行编辑节点后，系统会在这里创建可追踪的编辑会话。</p>
                  ) : (
                    <>
                      <StatusPill status={selectedNode.editorSession.status} />
                      <label className="field"><span>已注册编辑器</span><select value={selectedEditorId} onChange={(event) => setSelectedEditorId(event.target.value)}>
                        {selectedNode.editorSession.editors.map((editor) => (
                          <option value={editor.id} key={editor.id} disabled={editor.status !== "available" && editor.status !== "open"}>
                            {editor.name} · {editor.status}
                          </option>
                        ))}
                      </select></label>
                      {selectedNode.editorSession.editors.map((editor) => editor.reason ? <small key={editor.id} className="field-error">{editor.name}：{editor.reason}</small> : null)}
                      {selectedEditor?.projectPath && <small className="editor-runtime-path">{selectedEditor.projectPath}</small>}
                      {selectedEditorId === "openchatcut" && (
                        <label className="field">
                          <span>当前剪辑工程</span>
                          <input value={externalProjectInput} onChange={(event) => setExternalProjectInput(event.target.value)} placeholder="粘贴 OpenChatCut 工程链接；只有一个工程时可留空" />
                          <small>绑定一次后，人工时间线和侧边栏 Agent 会始终进入同一工程。</small>
                        </label>
                      )}
                      {projectBindingError && <small className="field-error">{projectBindingError}</small>}
                      <div className="button-row">
                        <button className="primary-button" disabled={busy || !selectedEditorId || !canRunAction(selectedNode, "creator.editor.launch")} onClick={() => void launchEditor()}><Play size={15} />进入人工剪辑</button>
                        <button className="secondary-button" disabled={busy || !canRunAction(selectedNode, "creator.editor.close")} onClick={() => void dispatch("creator.editor.close", { ...nodeTarget, sessionId: selectedNode.editorSession?.sessionId })}>关闭会话</button>
                      </div>
                      {selectedNode.editorSession.launch?.error && <small className="field-error">{selectedNode.editorSession.launch.error}</small>}
                    </>
                  )}
                </section>

                <section className="workspace-card action-form agent-edit-card">
                  <div className="section-heading compact"><div><span>AGENT EDIT</span><h3>侧边栏 Agent 剪辑</h3></div><MessageSquareText size={18} /></div>
                  {!selectedNode.editorSession ? <p className="quiet-card">先运行当前编辑节点。</p> : selectedEditor?.agentBridge?.endpoint ? (
                    <>
                      <div className="agent-bridge-state">
                        <span>同一时间线</span>
                        <strong>{selectedEditor.agentBridge.protocol || "OpenChatCut MCP"}</strong>
                        <small>{selectedEditor.agentBridge.endpoint}</small>
                      </div>
                      <ol className="agent-edit-flow">
                        <li>Agent 在隔离 Draft 中剪辑</li>
                        <li>生成修改提案，不碰正式时间线</li>
                        <li>你在编辑器审核后一次提交或拒绝</li>
                      </ol>
                      <label className="field"><span>本次剪辑要求</span><textarea rows={4} value={agentPrompt} onChange={(event) => setAgentPrompt(event.target.value)} /></label>
                      <button className="primary-button" disabled={busy || !canRunAction(selectedNode, "creator.editor.start-agent")} onClick={() => void startAgentEdit()}><MessageSquareText size={15} />打开编辑器与 Agent</button>
                    </>
                  ) : <p className="quiet-card">当前编辑器没有注册 Agent 协同接口，请选择 OpenChatCut。</p>}
                </section>

                {selectedNode.editorSession?.collaboration && (
                  <section className="workspace-card action-form proposal-card full">
                    <div className="section-heading compact"><div><span>EDIT PROPOSAL</span><h3>Agent 修改提案</h3></div><StatusPill status={selectedNode.editorSession.collaboration.status} /></div>
                    <div className="proposal-summary">
                      <strong>{selectedNode.editorSession.collaboration.proposal?.summary || "Agent 正在隔离草稿中工作"}</strong>
                      <small>
                        {selectedNode.editorSession.externalProject?.projectId ? `工程 ${selectedNode.editorSession.externalProject.projectId} · ` : ""}
                        {selectedNode.editorSession.collaboration.externalEditSessionId || "等待 OpenChatCut 返回编辑会话 ID"}
                        {selectedNode.editorSession.collaboration.proposal?.changeCount != null ? ` · ${selectedNode.editorSession.collaboration.proposal.changeCount} 项修改` : ""}
                      </small>
                      {reviewTime && <small>协同审核窗口：{reviewTime}</small>}
                    </div>
                    {selectedNode.editorSession.collaboration.status === "awaiting_review" && (
                      <div className="button-row">
                        <button className="primary-button" disabled={busy || !canRunAction(selectedNode, "creator.editor.review-proposal")} onClick={() => void reviewProposal("applied")}><Check size={15} />已在编辑器应用</button>
                        <button className="danger-button" disabled={busy || !canRunAction(selectedNode, "creator.editor.review-proposal")} onClick={() => void reviewProposal("rejected")}>已拒绝提案</button>
                      </div>
                    )}
                  </section>
                )}

                {selectedEditorId === "openchatcut" ? (
                  <form className="workspace-card action-form" onSubmit={(event) => void importEditorExport(event)}>
                    <div className="section-heading compact"><div><span>EXPORT CALLBACK</span><h3>导出并回写交付物</h3></div><FileOutput size={18} /></div>
                    <p className="quiet-card">Agent 完成导出时会自动回写；也可把 OpenChatCut 返回的导出地址粘贴到这里。</p>
                    <label className="field"><span>导出地址</span><input value={editorExportUrl} onChange={(event) => setEditorExportUrl(event.target.value)} placeholder="/media/uploads/xxx.mp4" required /></label>
                    <label className="field"><span>渲染任务 ID（可选）</span><input value={editorRenderId} onChange={(event) => setEditorRenderId(event.target.value)} placeholder="render id" /></label>
                    <button className="primary-button" disabled={busy || !canRunAction(selectedNode, "creator.editor.import-export")}>固化成片并完成节点</button>
                  </form>
                ) : (
                  <form className="workspace-card action-form" onSubmit={(event) => void saveEditor(event)}>
                    <div className="section-heading compact"><div><span>ARTIFACT CALLBACK</span><h3>保存并回写产物</h3></div><FileOutput size={18} /></div>
                    <label className="field"><span>产物类型</span><input value={editorOutputType} onChange={(event) => setEditorOutputType(event.target.value)} placeholder="edit_decisions" required /></label>
                    <label className="field"><span>产物路径</span><input value={editorOutputPath} onChange={(event) => setEditorOutputPath(event.target.value)} placeholder="/path/to/editor-output.json" required /></label>
                    <button className="primary-button" disabled={busy || !canRunAction(selectedNode, "creator.editor.save")}>保存并完成节点</button>
                  </form>
                )}

                <form className="workspace-card action-form" onSubmit={(event) => void saveEditorTemplate(event)}>
                  <div className="section-heading compact"><div><span>TEMPLATE LOOP</span><h3>跑通后保存为模板</h3></div><Store size={18} /></div>
                  <p className="quiet-card">先在 OpenChatCut 用 <code>manage_template save</code> 保存工程；Agent 可自动回写，也可手工填入返回的模板 ID。</p>
                  <label className="field"><span>模板名称</span><input value={templateName} onChange={(event) => setTemplateName(event.target.value)} required /></label>
                  <label className="field"><span>OpenChatCut 模板 ID</span><input value={templateId} onChange={(event) => setTemplateId(event.target.value)} placeholder="template id" required /></label>
                  <button className="secondary-button" disabled={busy || !canRunAction(selectedNode, "creator.editor.save-template")}>登记到创作超市</button>
                  {selectedNode.editorSession?.savedTemplates?.map((template) => <small key={template.templateId} className="saved-template-row">已登记：{template.name} · {template.templateId}</small>)}
                </form>
              </div>
            )}

            {tab === "logs" && (
              <section className="workspace-card log-card">
                <div className="section-heading compact"><div><span>RUN LOG</span><h3>节点运行日志</h3></div><Clock3 size={18} /></div>
                <div className="log-list">
                  {selectedNode.logs.length === 0 ? <p className="quiet-card">暂无运行日志。</p> : selectedNode.logs.slice().reverse().map((item, index) => (
                    <article key={item.at + String(index)}><time>{formatTime(item.at)}</time><i /><p>{item.message}</p></article>
                  ))}
                </div>
                <details className="technical-details">
                  <summary>技术执行详情</summary>
                  <dl>
                    <div><dt>执行器</dt><dd>{selectedNode.executor || "未注册"}</dd></div>
                    <div><dt>能力</dt><dd>{selectedNode.capabilities.join("、") || "无"}</dd></div>
                    <div><dt>输出类型</dt><dd>{selectedNode.outputs.join("、") || "无"}</dd></div>
                  </dl>
                </details>
              </section>
            )}

            {tab === "handoff" && (
              <div className="split-panel">
                <section className="workspace-card">
                  <div className="section-heading compact"><div><span>HANDOFF INPUT</span><h3>可转接交付物</h3></div><Layers3 size={18} /></div>
                  <div className="file-list">
                    {handoffArtifacts.map((artifact) => <article key={artifact.id}><Box size={16} /><div><strong>{artifact.label || artifact.type} · v{artifact.version || 1}</strong><small>{artifact.path}</small></div></article>)}
                    {handoffArtifacts.length === 0 && <p className="quiet-card">先登记或生成有效交付物，才能转接到下游节点。</p>}
                  </div>
                  <div className="lineage-handoff-list">
                    {outgoingHandoffs.map((handoff) => <div key={handoff.id}><span>{handoff.target.stageId} / {handoff.target.nodeId}<small>{handoff.artifactRefs?.map((item) => `v${item.version}`).join("、")}</small></span><StatusPill status={handoff.status} /></div>)}
                    {outgoingHandoffs.length === 0 && <small>当前节点还没有 Handoff 记录。</small>}
                  </div>
                </section>
                <section className="workspace-card action-form">
                  <div className="section-heading compact"><div><span>TARGET NODE</span><h3>选择目标节点</h3></div><ArrowRight size={18} /></div>
                  <label className="field"><span>转接目标</span><select value={target} onChange={(event) => setHandoffTarget(event.target.value)}>
                    {targetOptions.filter((item) => item.stageId !== selectedStage.id || item.nodeId !== selectedNode.id).map((item) => (
                      <option value={item.stageId + "." + item.nodeId} key={item.stageId + "." + item.nodeId}>{item.label}</option>
                    ))}
                  </select></label>
                  <button className="primary-button" disabled={busy || !target || !canRunAction(selectedNode, "creator.handoff.create")} onClick={() => void createHandoff()}>创建 Artifact Handoff</button>
                </section>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

type MarketplaceTab = "pipelines" | "projects" | "skills" | "templates";
type MarketplaceParameterRow = { key: string; value: string };

const marketplaceTabs: Array<{ id: MarketplaceTab; label: string; hint: string }> = [
  { id: "pipelines", label: "IP 模板", hint: "VOX、无头口播、真人口播等整套制式" },
  { id: "projects", label: "项目与仓库", hint: "来源与注册状态" },
  { id: "skills", label: "Skills 能力", hint: "按创作任务使用" },
  { id: "templates", label: "动画与剪辑组件", hint: "花字、转场、运镜、Remotion、PPT 等" },
];

function MarketplacePreview({ item, large = false }: { item: MarketplaceItem; large?: boolean }) {
  if (!item.preview) {
    if (item.kind === "pipeline") {
      return <div className={"market-preview pipeline-cover " + (large ? "large" : "")}>
        <span>NEWMA IP TEMPLATE</span><strong>{item.name}</strong>
        <div>{item.flow?.slice(0, 4).map((stage) => <i key={String(stage.id)}>{stage.name}</i>)}</div>
      </div>;
    }
    return <div className={"market-preview empty " + (large ? "large" : "")}><Box size={large ? 38 : 25} /><span>暂无预览</span></div>;
  }
  return (
    <div className={"market-preview " + (large ? "large" : "")}>
      {item.preview.kind === "video"
        ? <video src={item.preview.url} muted playsInline controls={large} preload="metadata" />
        : <img src={item.preview.url} alt={item.preview.alt || item.name} loading="lazy" />}
    </div>
  );
}

function MarketplaceCard({ item, active, onSelect }: { item: MarketplaceItem; active: boolean; onSelect(): void }) {
  const labels = item.capabilityLabels?.slice(0, 3) || item.stages?.slice(0, 3) || [];
  return (
    <button className={"market-card " + (active ? "selected" : "")} onClick={onSelect}>
      <MarketplacePreview item={item} />
      <div className="market-card-body">
        <div className="market-card-head">
          <span className="market-kind">{item.categoryLabel || item.category || item.kind}</span>
          <span className={"market-health tone-" + item.status.tone}>{item.status.label}</span>
        </div>
        <strong>{item.name}</strong>
        <p>{item.summary || "尚未补充用途说明。"}</p>
        {item.kind === "pipeline" && item.flow?.length ? (
          <div className="market-mini-flow">
            {item.flow.slice(0, 5).map((stage) => <span key={String(stage.id)}>{stage.name}</span>)}
          </div>
        ) : (
          <div className="market-chip-row">{labels.map((label) => <span key={label}>{label}</span>)}</div>
        )}
        <footer><small>{item.sourceProjectId || item.id}</small><span>查看详情 <ArrowRight size={13} /></span></footer>
      </div>
    </button>
  );
}

function MarketplaceDetail({
  item,
  compatibility,
  presets,
  versionsByPreset,
  snapshot,
  selectedStage,
  selectedNode,
  workflowTargets,
  targetKey,
  presetName,
  parameterRows,
  busyAction,
  onTargetChange,
  onPresetNameChange,
  onParameterChange,
  onAddParameter,
  onRemoveParameter,
  onCheck,
  onSave,
  onSaveAndApply,
  onUpdate,
  onLoadVersions,
  onApply,
}: {
  item: MarketplaceItem;
  compatibility?: MarketplaceCompatibility;
  presets: MarketplacePreset[];
  versionsByPreset: Record<string, MarketplacePreset[]>;
  snapshot?: CreatorSnapshot;
  selectedStage?: SnapshotStage;
  selectedNode?: SnapshotNode;
  workflowTargets: Array<{ key: string; label: string }>;
  targetKey: string;
  presetName: string;
  parameterRows: MarketplaceParameterRow[];
  busyAction: string;
  onTargetChange(value: string): void;
  onPresetNameChange(value: string): void;
  onParameterChange(index: number, field: keyof MarketplaceParameterRow, value: string): void;
  onAddParameter(): void;
  onRemoveParameter(index: number): void;
  onCheck(): void;
  onSave(): void;
  onSaveAndApply(): void;
  onUpdate(preset: MarketplacePreset): void;
  onLoadVersions(presetId: string): void;
  onApply(presetId: string, version?: number): void;
}) {
  const statusRows = [
    ["注册", item.status.registration === "workflow_registered" ? "已绑定工作流" : "已进入能力目录"],
    ["安装", item.status.installation === "installed" ? "已安装" : "未安装"],
    ["运行", item.status.label],
    ["兼容", item.status.compatibility === "compatible" ? "当前环境兼容" : "尚未检查"],
  ];
  const targetLabel = snapshot && selectedStage && selectedNode
    ? `${snapshot.run.title} / ${selectedStage.name} / ${selectedNode.name}`
    : "未选择任务节点";
  const demoUrl = compatibility?.demo.url
    || item.preview?.url
    || (item.source?.startsWith("http") ? item.source : undefined);
  const busy = busyAction.startsWith("creator.marketplace.");
  return (
    <aside className="market-detail">
      <MarketplacePreview item={item} large />
      {item.kind !== "pipeline" && <div className="market-detail-title">
        <div><span>{item.kind.toUpperCase()}</span><h2>{item.name}</h2></div>
        <span className={"market-health tone-" + item.status.tone}>{item.status.label}</span>
      </div>}
      {item.kind !== "pipeline" && <p className="market-detail-summary">{item.summary || "尚未补充用途说明。"}</p>}

      <section className="market-use-loop">
        <div className="market-loop-heading"><div><span>USE LOOP</span><h3>检查、收藏并绑定</h3></div><StatusPill status={compatibility?.status} /></div>
        <div className="market-target">
          <span>当前目标</span>
          {workflowTargets.length
            ? <select aria-label="目标工作流节点" value={targetKey} onChange={(event) => onTargetChange(event.target.value)}>
              <option value="">仅保存预设，不绑定节点</option>
              {workflowTargets.map((target) => <option value={target.key} key={target.key}>{target.label}</option>)}
            </select>
            : <strong>{targetLabel}</strong>}
        </div>
        <div className="market-loop-actions">
          <button className="secondary-button" disabled={busy} onClick={onCheck}>检查兼容性</button>
          {demoUrl
            ? <a className="secondary-button" href={demoUrl} target="_blank" rel="noreferrer">查看演示</a>
            : <button className="secondary-button" disabled>暂无演示</button>}
        </div>
        {compatibility && <div className="market-check-list">
          {compatibility.checks.map((check) => <div className={`check-${check.status}`} key={check.id}>
            {check.status === "pass" ? <Check size={13} /> : <CircleAlert size={13} />}
            <span>{check.label}</span>
          </div>)}
        </div>}
        <label className="field compact-field"><span>预设名称</span><input value={presetName} onChange={(event) => onPresetNameChange(event.target.value)} /></label>
        <div className="market-parameter-editor">
          <div className="market-loop-heading"><h3>节点参数</h3><button onClick={onAddParameter}>＋ 添加参数</button></div>
          {parameterRows.map((row, index) => <div className="market-parameter-row" key={String(index)}>
            <input aria-label={`参数名称 ${index + 1}`} value={row.key} placeholder="参数名称" onChange={(event) => onParameterChange(index, "key", event.target.value)} />
            <input aria-label={`参数值 ${index + 1}`} value={row.value} placeholder="参数值" onChange={(event) => onParameterChange(index, "value", event.target.value)} />
            <button aria-label={`删除参数 ${index + 1}`} disabled={parameterRows.length === 1} onClick={() => onRemoveParameter(index)}>×</button>
          </div>)}
          <small>数字、true/false 和 JSON 会自动转换，其余按文本保存。</small>
        </div>
        <div className="market-loop-actions">
          <button className="secondary-button" disabled={busy || compatibility?.canSave === false || !presetName.trim()} onClick={onSave}>收藏入库</button>
          <button className="primary-button" disabled={busy || !snapshot || !targetKey || compatibility?.canApply === false || !presetName.trim()} onClick={onSaveAndApply}>收藏并应用</button>
        </div>
      </section>

      <section className="market-preset-section">
        <div className="market-loop-heading"><h3>已保存预设</h3><small>{presets.length} 个预设</small></div>
        {presets.length ? <div className="market-preset-list">{presets.map((preset) => (
          <article key={preset.presetId}>
            <div className="market-preset-summary"><strong>{preset.name}</strong><small>当前 v{preset.version} · {preset.target ? `${preset.target.stageId}/${preset.target.nodeId}` : "未绑定节点"}</small></div>
            <div className="market-preset-actions">
              <button disabled={busy} onClick={() => onUpdate(preset)}>更新为 v{preset.version + 1}</button>
              <button disabled={busy} onClick={() => onLoadVersions(preset.presetId)}>版本</button>
              <button disabled={busy || !snapshot || !targetKey} onClick={() => onApply(preset.presetId)}>应用</button>
            </div>
            {versionsByPreset[preset.presetId] && <div className="market-version-list">
              {versionsByPreset[preset.presetId].map((version) => <div key={version.version}>
                <span><strong>v{version.version}</strong><small>{Object.keys(version.parameters).length} 个参数</small></span>
                <button disabled={busy || !snapshot || !targetKey} onClick={() => onApply(preset.presetId, version.version)}>应用此版本</button>
              </div>)}
            </div>}
          </article>
        ))}</div> : <p className="quiet-card">尚未保存该能力的预设。</p>}
      </section>

      {item.flow?.length ? <section><h3>流程示意</h3><div className="market-flow-list">{item.flow.map((stage, index) => (
        <div key={String(stage.id)}><i>{index + 1}</i><span><strong>{stage.name}</strong><small>{stage.description}</small></span></div>
      ))}</div></section> : null}

      <section><h3>注册与运行</h3><dl className="market-status-list">{statusRows.map(([label, value]) => (
        <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
      ))}</dl>{item.status.reasons?.map((reason) => <p className="market-reason" key={reason}>{reason}</p>)}</section>

      {(item.capabilityLabels?.length || item.useCases?.length) ? <section><h3>主要用途</h3><div className="market-chip-row detail">
        {[...(item.capabilityLabels || []), ...(item.useCases || [])].slice(0, 10).map((label) => <span key={label}>{label}</span>)}
      </div></section> : null}

      <section><h3>使用信息</h3><dl className="market-status-list">
        {item.sourceProjectId && <div><dt>所属项目</dt><dd>{item.sourceProjectId}</dd></div>}
        {item.stages?.length ? <div><dt>适用环节</dt><dd>{item.stages.join("、")}</dd></div> : null}
        {item.aspectRatios?.length ? <div><dt>支持画幅</dt><dd>{item.aspectRatios.join("、")}</dd></div> : null}
        {item.inputs?.length ? <div><dt>需要输入</dt><dd>{item.inputs.join("、")}</dd></div> : null}
        {item.outputs?.length ? <div><dt>主要输出</dt><dd>{item.outputs.join("、")}</dd></div> : null}
        {item.skillIds?.length ? <div><dt>关联 Skills</dt><dd>{item.skillIds.join("、")}</dd></div> : null}
        {item.version && <div><dt>版本</dt><dd>{item.version}</dd></div>}
        {item.license && <div><dt>许可</dt><dd>{item.license}</dd></div>}
      </dl></section>

    </aside>
  );
}

export function MarketplaceView({
  marketplace,
  presets,
  snapshot,
  selectedStage,
  selectedNode,
  loading,
  busyAction,
  dispatch,
}: {
  marketplace?: CreatorMarketplace;
  presets: MarketplacePreset[];
  snapshot?: CreatorSnapshot;
  selectedStage?: SnapshotStage;
  selectedNode?: SnapshotNode;
  loading: boolean;
  busyAction: string;
  dispatch: ActionDispatcher;
}) {
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<MarketplaceTab>("pipelines");
  const [selectedId, setSelectedId] = useState("");
  const [compatibility, setCompatibility] = useState<MarketplaceCompatibility>();
  const [presetName, setPresetName] = useState("");
  const [targetKey, setTargetKey] = useState("");
  const [parameterRows, setParameterRows] = useState<MarketplaceParameterRow[]>([{ key: "marketplaceItemId", value: "" }]);
  const [versionsByPreset, setVersionsByPreset] = useState<Record<string, MarketplacePreset[]>>({});
  const groups: Record<MarketplaceTab, MarketplaceItem[]> = {
    pipelines: marketplace?.pipelines || [],
    projects: marketplace?.projects || marketplace?.repositories || [],
    skills: marketplace?.skills || [],
    templates: marketplace?.templates || [],
  };
  const term = query.trim().toLowerCase();
  const items = groups[tab].filter((item) => !term || [
    item.name, item.id, item.summary, item.category, item.categoryLabel,
    ...(item.capabilityLabels || []), ...(item.stages || []), ...(item.tags || []),
  ].filter(Boolean).join(" ").toLowerCase().includes(term));
  const selected = items.find((item) => item.id === selectedId) || items[0];
  useEffect(() => {
    setCompatibility(undefined);
    setPresetName(selected ? `${selected.name} 预设` : "");
    const parameterKey = selected?.kind === "pipeline" ? "pipelineId"
      : selected?.kind === "template" ? "templateId"
      : selected?.kind === "skill" ? "skillId"
      : "projectId";
    setParameterRows([{ key: parameterKey, value: selected?.sourceTemplateId || selected?.id || "" }]);
  }, [selected?.id]);
  useEffect(() => {
    setTargetKey(selectedStage && selectedNode ? `${selectedStage.id}::${selectedNode.id}` : "");
  }, [snapshot?.run.runId, selectedStage?.id, selectedNode?.id]);
  const matchingPresets = presets.filter((preset) => selected
    && preset.itemId === selected.id
    && preset.itemKind === selected.kind);
  const workflowTargets = snapshot?.stages.flatMap((stage) => stage.nodes.map((node) => ({
    key: `${stage.id}::${node.id}`,
    label: `${snapshot.run.title} / ${stage.name} / ${node.name}`,
  }))) ?? [];
  const [targetStageId, targetNodeId] = targetKey ? targetKey.split("::", 2) : [undefined, undefined];
  const targetInput = targetStageId && targetNodeId ? { stageId: targetStageId, nodeId: targetNodeId } : {};
  const parameters = Object.fromEntries(parameterRows.flatMap((row) => {
    const key = row.key.trim();
    const value = row.value.trim();
    if (!key) return [];
    if (value === "true" || value === "false") return [[key, value === "true"]];
    if (value !== "" && !Number.isNaN(Number(value))) return [[key, Number(value)]];
    if ((value.startsWith("{") && value.endsWith("}")) || (value.startsWith("[") && value.endsWith("]"))) {
      try { return [[key, JSON.parse(value)]]; } catch { /* Save invalid JSON as text. */ }
    }
    return [[key, row.value]];
  }));
  const checkCompatibility = async () => {
    if (!selected) return undefined;
    const result = await dispatch("creator.marketplace.check-compatibility", {
      itemId: selected.id,
      itemKind: selected.kind,
      ...targetInput,
    }) as MarketplaceCompatibility;
    setCompatibility(result);
    return result;
  };
  const savePreset = async () => {
    if (!selected) return undefined;
    const checked = compatibility ?? await checkCompatibility();
    if (!checked?.canSave) return undefined;
    return await dispatch("creator.marketplace.save-preset", {
      name: presetName.trim(),
      itemId: selected.id,
      itemKind: selected.kind,
      ...targetInput,
      parameters,
    }) as MarketplacePreset;
  };
  const loadPresetVersions = async (presetId: string) => {
    const result = await dispatch("creator.marketplace.list-preset-versions", { presetId }) as { versions: MarketplacePreset[] };
    setVersionsByPreset((current) => ({ ...current, [presetId]: result.versions }));
    return result.versions;
  };
  const updatePreset = async (preset: MarketplacePreset) => {
    const checked = compatibility ?? await checkCompatibility();
    if (!checked?.canSave) return undefined;
    const updated = await dispatch("creator.marketplace.update-preset", {
      presetId: preset.presetId,
      expectedVersion: preset.version,
      name: presetName.trim(),
      ...targetInput,
      parameters,
    }) as MarketplacePreset;
    await loadPresetVersions(preset.presetId);
    return updated;
  };
  const applyPreset = async (presetId: string, presetVersion?: number) => {
    if (!targetStageId || !targetNodeId) return;
    await dispatch("creator.marketplace.apply-preset", {
      presetId,
      ...(presetVersion ? { presetVersion } : {}),
      stageId: targetStageId,
      nodeId: targetNodeId,
    });
  };
  const saveAndApply = async () => {
    const preset = await savePreset();
    if (preset) await applyPreset(preset.presetId);
  };
  const counts: Record<MarketplaceTab, number> = {
    pipelines: marketplace?.counts.pipelines ?? 0,
    projects: marketplace?.counts.projects ?? marketplace?.counts.repositories ?? 0,
    skills: marketplace?.counts.skills ?? 0,
    templates: marketplace?.counts.templates ?? 0,
  };
  return (
    <div className="marketplace-view">
      <section className="market-hero">
        <div data-mod-page-title><span className="eyebrow">CREATOR MARKET</span><h1>创作能力超市</h1><p>剪辑前收藏并绑定节点，剪辑中随时插入；跑通的工程可回到这里沉淀为模板。</p></div>
        <div className="market-counts">
          <article><strong>{marketplace?.counts.pipelines ?? 0}</strong><span>IP 模板</span></article>
          <article><strong>{marketplace?.counts.projects ?? marketplace?.counts.repositories ?? 0}</strong><span>项目</span></article>
          <article><strong>{marketplace?.counts.skills ?? 0}</strong><span>Skills</span></article>
          <article><strong>{marketplace?.counts.templates ?? 0}</strong><span>组件模板</span></article>
        </div>
      </section>
      <div className="market-toolbar">
        <div className="market-tabs">{marketplaceTabs.map((item) => <button
          className={tab === item.id ? "active" : ""}
          key={item.id}
          onClick={() => { setTab(item.id); setSelectedId(""); }}
        ><strong>{item.label}</strong><span>{item.hint} · {counts[item.id]}</span></button>)}</div>
        <label className="market-search"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索用途、阶段、项目或模板" /></label>
      </div>
      {loading ? <div className="loading-stage">正在编译能力目录…</div> : marketplace ? (
        items.length ? <div className="market-browser">
          <section className="market-gallery">
            <div className="section-heading compact"><div><span>CATALOG</span><h2>{marketplaceTabs.find((item) => item.id === tab)?.label}</h2></div><small>{items.length} 项</small></div>
            <div className={"market-grid " + (tab === "pipelines" ? "pipeline-grid" : "")}>{items.map((item) => (
              <MarketplaceCard item={item} active={selected?.id === item.id} onSelect={() => setSelectedId(item.id)} key={item.kind + item.id} />
            ))}</div>
          </section>
          {selected && <MarketplaceDetail
            item={selected}
            compatibility={compatibility}
            presets={matchingPresets}
            versionsByPreset={versionsByPreset}
            snapshot={snapshot}
            selectedStage={selectedStage}
            selectedNode={selectedNode}
            workflowTargets={workflowTargets}
            targetKey={targetKey}
            presetName={presetName}
            parameterRows={parameterRows}
            busyAction={busyAction}
            onTargetChange={(value) => { setTargetKey(value); setCompatibility(undefined); }}
            onPresetNameChange={setPresetName}
            onParameterChange={(index, field, value) => setParameterRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row))}
            onAddParameter={() => setParameterRows((current) => [...current, { key: "", value: "" }])}
            onRemoveParameter={(index) => setParameterRows((current) => current.filter((_, rowIndex) => rowIndex !== index))}
            onCheck={() => void checkCompatibility().catch(() => undefined)}
            onSave={() => void savePreset().catch(() => undefined)}
            onSaveAndApply={() => void saveAndApply().catch(() => undefined)}
            onUpdate={(preset) => void updatePreset(preset).catch(() => undefined)}
            onLoadVersions={(presetId) => void loadPresetVersions(presetId).catch(() => undefined)}
            onApply={(presetId, version) => void applyPreset(presetId, version).catch(() => undefined)}
          />}
        </div> : <p className="quiet-card">没有匹配的能力条目。</p>
      ) : <p className="quiet-card">能力目录暂时不可用。</p>}
    </div>
  );
}

export function SettingsView({
  system,
  capabilities,
  deskAgentPreferences,
  onSyncAgent,
  busy,
  dispatch,
}: {
  system?: Record<string, unknown>;
  capabilities?: CapabilityDetection;
  deskAgentPreferences?: DeskAgentPreferences;
  onSyncAgent?: (agentId: string) => Promise<void>;
  busy: boolean;
  dispatch: ActionDispatcher;
}) {
  const [selectedAgent, setSelectedAgent] = useState<string>(() =>
    typeof window !== "undefined" ? localStorage.getItem("newma.creator-studio.selected-agent") || "" : ""
  );
  const [binOverride, setBinOverride] = useState<string>(() =>
    typeof window !== "undefined" ? localStorage.getItem("newma.creator-studio.agent-bin-override") || "" : ""
  );
  const [testResults, setTestResults] = useState<Record<string, { status: string; msg: string; ms?: number }>>({});
  const [testingId, setTestingId] = useState<string>("");
  const [syncMessage, setSyncMessage] = useState<string>("");

  const deskAdapterToCreatorAgent: Record<string, string> = {
    "codex-cli": "codex",
    "claude-cli": "claude",
    "gemini-cli": "gemini",
    "hermes-webui": "hermes",
  };

  useEffect(() => {
    const deskAdapter = deskAgentPreferences?.profileTargets?.edit
      || deskAgentPreferences?.defaultAdapter
      || "";
    const mapped = deskAdapterToCreatorAgent[deskAdapter];
    if (!mapped || (selectedAgent && !deskAgentPreferences?.updatedAt)) return;
    setSelectedAgent(mapped);
    localStorage.setItem("newma.creator-studio.selected-agent", mapped);
  }, [deskAgentPreferences, selectedAgent]);

  const selectAgent = (agentId: string) => {
    setSelectedAgent(agentId);
    localStorage.setItem("newma.creator-studio.selected-agent", agentId);
    setSyncMessage("");
    if (!agentId || !onSyncAgent) return;
    void onSyncAgent(agentId)
      .then(() => setSyncMessage("已同步到 Desk Agent 的编码修改路由"))
      .catch((reason) => setSyncMessage(`本地选择已保存，Desk 同步失败：${reason instanceof Error ? reason.message : "未知错误"}`));
  };
  const updateBinOverride = (val: string) => {
    setBinOverride(val);
    if (val.trim()) localStorage.setItem("newma.creator-studio.agent-bin-override", val.trim());
    else localStorage.removeItem("newma.creator-studio.agent-bin-override");
  };
  const testAgent = async (agentId: string) => {
    setTestingId(agentId);
    try {
      const result = await dispatch("creator.agent.test", { agentId, binOverride }) as unknown as {
        status: string; stdout?: string; stderr?: string; duration_ms?: number;
      };
      const ok = result?.status === "succeeded" && (result?.stdout || "").includes("AGENT_TEST_OK");
      setTestResults((prev) => ({
        ...prev,
        [agentId]: {
          status: ok ? "ok" : "fail",
          msg: ok ? "测试通过" : (result?.stderr?.slice(0, 100) || result?.stdout?.slice(0, 100) || "未收到预期响应"),
          ms: result?.duration_ms,
        },
      }));
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [agentId]: { status: "fail", msg: err instanceof Error ? err.message.slice(0, 100) : "测试失败" },
      }));
    } finally {
      setTestingId("");
    }
  };

  useEffect(() => {
    if (!capabilities && !busy) {
      void dispatch("creator.capability.detect");
    }
  }, [busy, capabilities, dispatch]);

  return (
    <div className="settings-view">
      <section className="settings-hero">
        <div data-mod-page-title><span className="eyebrow">PROJECT CONTROL</span><h1>Creator Studio 设置</h1><p>选择默认 Agent CLI，所有节点执行将使用您指定的本地 Agent。</p></div>
        <button className="primary-button" disabled={busy} onClick={() => void dispatch("creator.capability.detect")}><Gauge size={16} />刷新检测</button>
      </section>

      <section className="capability-board agent-selector">
        <div className="section-heading"><div><span>DEFAULT AGENT</span><h2>选择工作流 Agent</h2></div><small>{selectedAgent ? `当前: ${selectedAgent}` : "未选择（将自动按优先级匹配）"}</small></div>
        {deskAgentPreferences && (
          <p className="agent-hint">Desk 当前编码路由：{deskAgentPreferences.profileTargets?.edit || deskAgentPreferences.defaultAdapter}。Creator 选择会同步到这里。</p>
        )}
        {syncMessage && <p className="agent-hint">{syncMessage}</p>}
        <p className="agent-hint">点击已安装的 Agent 设为默认。所有阶段的 CLI 调用将使用所选 Agent。未选择时按 qoder-cli → claude → codex → gemini 顺序自动匹配。<br />
          <span className="legend-inline"><span className="legend-dot legend-dot-green" /> 已安装可用</span>
          <span className="legend-inline"><span className="legend-dot legend-dot-yellow" /> 有问题</span>
          <span className="legend-inline"><span className="legend-dot legend-dot-red" /> 未安装</span>
        </p>
        <div className="capability-grid agent-grid">
          {capabilities?.capabilities.map((item) => {
            let status: "available" | "warning" | "unavailable";
            if (!item.available) {
              status = "unavailable";
            } else if (!item.version || !item.path || item.mode === "detect_only" || item.mode === "media_runtime") {
              status = "warning";
            } else {
              status = "available";
            }
            const canSelect = status === "available";
            return (
              <article
                className={`agent-status-${status} ${status === "available" ? "available" : status === "warning" ? "warning" : "unavailable"} ${selectedAgent === item.id ? "selected-agent" : ""}`}
                key={item.id}
                onClick={canSelect ? () => selectAgent(item.id) : undefined}
                style={canSelect ? { cursor: "pointer" } : undefined}
              >
                <div>
                  {selectedAgent === item.id
                    ? <Check size={16} className="status-icon status-icon-selected" />
                    : status === "available"
                      ? <CircleDot size={16} className="status-icon status-icon-green" />
                      : status === "warning"
                        ? <CircleAlert size={16} className="status-icon status-icon-yellow" />
                        : <CircleAlert size={16} className="status-icon status-icon-red" />}
                  <strong>{item.name}</strong>
                </div>
                <span>{item.mode}</span>
                <small>{item.version || (item.available ? "已检测（信息不全）" : "未安装")}</small>
                {item.path && <small className="agent-path">{item.path}</small>}
                {item.stages?.length ? <div className="agent-stages">{item.stages.slice(0, 4).map((s) => <span key={s}>{s}</span>)}</div> : null}
                {status === "available" && (
                  <div className="agent-test-row" onClick={(e) => e.stopPropagation()}>
                    <button
                      className="text-button agent-test-btn"
                      disabled={testingId === item.id}
                      onClick={(e) => { e.stopPropagation(); void testAgent(item.id); }}
                    >
                      {testingId === item.id ? "测试中…" : "测试"}
                    </button>
                    {testResults[item.id] && (
                      <span className={`agent-test-result agent-test-${testResults[item.id].status}`}>
                        {testResults[item.id].status === "ok" ? "✓" : "✗"} {testResults[item.id].msg}
                        {testResults[item.id].ms ? ` (${testResults[item.id].ms}ms)` : ""}
                      </span>
                    )}
                  </div>
                )}
              </article>
            );
          }) ?? <p className="quiet-card">正在检测本地 CLI…</p>}
        </div>
        {selectedAgent && (
          <button className="text-button" onClick={() => selectAgent("")}>清除选择（恢复自动匹配）</button>
        )}
        {selectedAgent && (
          <div className="agent-bin-override">
            <label>
              <small>自定义 binary 路径（可选，覆盖自动检测）</small>
              <input
                type="text"
                value={binOverride}
                onChange={(e) => updateBinOverride(e.target.value)}
                placeholder={`例: /usr/local/bin/${selectedAgent}`}
              />
            </label>
          </div>
        )}
      </section>

      <div className="settings-grid">
        <section className="workspace-card">
          <div className="section-heading compact"><div><span>SYSTEM</span><h3>运行来源</h3></div><Database size={18} /></div>
          <dl className="settings-list">
            <div><dt>产品</dt><dd>{String((system?.product as Record<string, unknown> | undefined)?.name || "Newma Creator Studio")}</dd></div>
            <div><dt>媒体工作区</dt><dd>{String(system?.workspace || "未连接")}</dd></div>
            <div><dt>注册表</dt><dd>{String(system?.registryPath || "未连接")}</dd></div>
            <div><dt>阶段数量</dt><dd>{String(system?.stageCount ?? "—")}</dd></div>
          </dl>
        </section>
        <section className="workspace-card">
          <div className="section-heading compact"><div><span>NAMESPACE</span><h3>{"命名策略"}</h3></div><Settings2 size={18} /></div>
          <div className="policy-stack">
            <p><Check size={15} />{" "}{"对外 ID 使用"} <strong>newma-*</strong></p>
            <p><Check size={15} />{" "}{"旧版运行时定位符已停用"}</p>
            <p><Check size={15} />{" "}{"Agent 不得绕过 Manifest Action"}</p>
          </div>
        </section>
      </div>
    </div>
  );
}
