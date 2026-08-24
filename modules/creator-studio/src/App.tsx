import {
  Bell,
  ChevronDown,
  Command,
  LoaderCircle,
  PackagePlus,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import {
  connectModHost,
  type ModHostConnection,
} from "@newma-desk/mod-sdk";

import { creatorClient, type DeskAgentPreferences } from "./api";
import { buildCreatorContext } from "./context";
import { CreateRunDialog } from "./CreateRunDialog";
import { ArtifactPreviewModal } from "./ArtifactPreviewModal";
import { formatTime, statusLabel, statusTone } from "./presenters";
import { isCreatorStage } from "./types";
import type {
  CapabilityDetection,
  CreatorMarketplace,
  CreatorMaterial,
  CreatorRegistry,
  CreatorRunSummary,
  CreatorSnapshot,
  CreatorWorkspace,
  Identity,
  MarketplacePreset,
  SnapshotStage,
} from "./types";
import {
  DashboardView,
  MarketplaceView,
  SettingsView,
  WorkbenchView,
  type ActionDispatcher,
} from "./views";

const MOD_IDS: Record<CreatorWorkspace, string> = {
  dashboard: "creator-dashboard",
  intake: "creator-workbench",
  brief: "creator-brief",
  draft: "creator-draft",
  transwrite: "creator-transwrite",
  publish: "creator-publish",
  postmortem: "creator-postmortem",
  marketplace: "creator-marketplace",
  settings: "creator-settings",
};

type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;

function workspaceFromSearch(): CreatorWorkspace {
  const value = new URLSearchParams(window.location.search).get("workspace") || "";
  if (isCreatorStage(value)) return value;
  return value === "marketplace" || value === "settings" ? value : "dashboard";
}

function parentOrigin() {
  const configured = import.meta.env.VITE_PARENT_ORIGIN?.trim();
  if (configured) return configured;
  if (document.referrer) {
    try {
      return new URL(document.referrer).origin;
    } catch {
      // Use the local Desk default.
    }
  }
  return "http://127.0.0.1:5888";
}

function runStorageKey(identity: Identity) {
  return "newma.creator-studio.current-run." + identity.userId + "." + identity.workspaceId;
}

function preferredNode(stage: SnapshotStage | undefined, activeNodeId?: string) {
  if (!stage) return undefined;
  const active = stage.nodes.find((node) => node.id === activeNodeId);
  if (active) return active;
  return stage.nodes.find((node) => ["waiting_user", "changes_requested", "blocked", "failed"].includes(node.status))
    ?? stage.nodes.slice().reverse().find((node) => ["running", "queued", "succeeded"].includes(node.status))
    ?? stage.nodes.find((node) => node.status !== "skipped")
    ?? stage.nodes[0];
}

function StudioHeader({
  runs,
  snapshot,
  busy,
  notificationOpen,
  onNotificationToggle,
  onCreate,
  dispatch,
}: {
  runs: CreatorRunSummary[];
  snapshot?: CreatorSnapshot;
  busy: boolean;
  notificationOpen: boolean;
  onNotificationToggle(): void;
  onCreate(): void;
  dispatch: ActionDispatcher;
}) {
  const notificationCount = snapshot
    ? snapshot.counters.waitingReview + snapshot.counters.newArtifacts + snapshot.counters.blockedNodes
    : 0;
  return (
    <header className="studio-header">
      <div className="header-center">
        <label className="run-picker">
          <select
            aria-label="当前任务"
            value={snapshot?.run.runId || ""}
            disabled={!runs.length}
            onChange={(event) => void dispatch("creator.run.select", { runId: event.target.value })}
          >
            {!runs.length && <option value="">暂无任务</option>}
            {runs.map((run) => <option value={run.runId} key={run.runId}>{run.title}</option>)}
          </select>
          <ChevronDown size={14} />
        </label>
      </div>
      <div className="header-actions">
        {snapshot && <span className={"status-pill tone-" + statusTone(snapshot.run.status)}><i />{statusLabel(snapshot.run.status)}</span>}
        <button className="icon-button" onClick={() => void dispatch("creator.run.refresh")} disabled={busy || !snapshot} title="刷新任务">
          <RefreshCw size={17} className={busy ? "spin" : ""} />
        </button>
        <div className="notification-anchor">
          <button className="icon-button" onClick={onNotificationToggle} title="消息">
            <Bell size={17} />
            {notificationCount > 0 && <b>{notificationCount > 99 ? "99+" : notificationCount}</b>}
          </button>
          {notificationOpen && (
            <div className="notification-popover">
              <header><strong>消息与待办</strong><small>{notificationCount} 条</small></header>
              {snapshot?.notifications.length ? snapshot.notifications.slice(-8).reverse().map((item) => (
                <button key={item.id} onClick={() => void dispatch("creator.node.select", { stageId: item.stageId, nodeId: item.nodeId })}>
                  <i className={"kind-" + item.kind} />
                  <span><strong>{item.title}</strong><small>{item.stageId} / {item.nodeId}</small></span>
                </button>
              )) : <p>当前没有待处理消息。</p>}
            </div>
          )}
        </div>
        <button className="primary-button compact-button" onClick={onCreate}><PackagePlus size={15} />新建任务</button>
      </div>
    </header>
  );
}

export function CreatorStudioApp() {
  const workspace = workspaceFromSearch();
  const fixedStageId = isCreatorStage(workspace) ? workspace : "";
  const modId = MOD_IDS[workspace];
  const [identity, setIdentity] = useState<Identity | undefined>(() => (
    window.self === window.top
      ? { userId: "local-user", workspaceId: "local-workspace" }
      : undefined
  ));
  const [registry, setRegistry] = useState<CreatorRegistry>();
  const [runs, setRuns] = useState<CreatorRunSummary[]>([]);
  const [snapshot, setSnapshot] = useState<CreatorSnapshot>();
  const [currentRunId, setCurrentRunId] = useState("");
  const [selectedStageId, setSelectedStageId] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [marketplace, setMarketplace] = useState<CreatorMarketplace>();
  const [marketplacePresets, setMarketplacePresets] = useState<MarketplacePreset[]>([]);
  const [capabilities, setCapabilities] = useState<CapabilityDetection>();
  const [system, setSystem] = useState<Record<string, unknown>>();
  const [deskAgentPreferences, setDeskAgentPreferences] = useState<DeskAgentPreferences>();
  const [loading, setLoading] = useState(true);
  const [marketLoading, setMarketLoading] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [previewArtifact, setPreviewArtifact] = useState<{ path: string; label?: string } | null>(null);
  useEffect(() => {
    (window as unknown as { __creatorStudioOpenArtifact?: (path: string, label?: string) => void }).__creatorStudioOpenArtifact = (path: string, label?: string) => {
      if (path) setPreviewArtifact({ path, label });
    };
    return () => {
      delete (window as unknown as { __creatorStudioOpenArtifact?: unknown }).__creatorStudioOpenArtifact;
    };
  }, []);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [host, setHost] = useState<EmbeddedHost>();
  const client = useMemo(() => identity ? creatorClient(identity) : undefined, [identity]);
  const contextRef = useRef<ModPageContext>(buildCreatorContext({ workspace, runs: [] }));
  const actionRef = useRef<ActionDispatcher>(async () => ({}));
  const lastEventSequenceRef = useRef(0);

  const selectedStage = useMemo(() => (
    snapshot?.stages.find((stage) => stage.id === fixedStageId)
      ?? snapshot?.stages.find((stage) => stage.id === selectedStageId)
      ?? snapshot?.stages.find((stage) => stage.id === snapshot.run.activeStageId)
      ?? snapshot?.stages[0]
  ), [fixedStageId, selectedStageId, snapshot]);
  const selectedNode = useMemo(() => (
    selectedStage?.nodes.find((node) => node.id === selectedNodeId)
      ?? preferredNode(selectedStage, snapshot?.run.activeNodeId)
  ), [selectedNodeId, selectedStage, snapshot?.run.activeNodeId]);

  // 稳定引用：ReviewWorkCard 的 effect 依赖 fetchPreview，内联箭头函数会导致每次渲染重跑并重置选中状态
  const fetchArtifactPreview = useCallback(
    (path: string) => {
      if (!client) return Promise.reject(new Error("client 未就绪"));
      return client.previewArtifact(path);
    },
    [client],
  );

  const refreshRuns = useCallback(async () => {
    if (!client || !identity) return [];
    const next = await client.runs();
    setRuns(next.runs);
    if (!currentRunId && next.runs.length) {
      const stored = window.localStorage.getItem(runStorageKey(identity));
      const selected = next.runs.find((run) => run.runId === stored) ?? next.runs[0];
      setCurrentRunId(selected.runId);
    }
    return next.runs;
  }, [client, currentRunId, identity]);

  const loadSnapshot = useCallback(async (runId = currentRunId) => {
    if (!client || !runId) {
      setSnapshot(undefined);
      return undefined;
    }
    const next = await client.run(runId);
    setSnapshot(next);
    lastEventSequenceRef.current = next.lastEventSequence;
    setSelectedStageId((current) => fixedStageId || (current && next.stages.some((stage) => stage.id === current)
      ? current
      : next.run.activeStageId || next.stages[0]?.id || ""));
    const activeStage = next.stages.find((stage) => stage.id === (fixedStageId || next.run.activeStageId)) ?? next.stages[0];
    setSelectedNodeId((current) => activeStage?.nodes.some((node) => node.id === current)
      ? current
      : preferredNode(activeStage, next.run.activeNodeId)?.id || "");
    return next;
  }, [client, currentRunId, fixedStageId]);

  useEffect(() => {
    if (!client || !identity) return;
    let active = true;
    setLoading(true);
    setError("");
    setSnapshot(undefined);
    setCurrentRunId("");
    Promise.all([client.registry(), client.runs()])
      .then(([nextRegistry, nextRuns]) => {
        if (!active) return;
        setRegistry(nextRegistry);
        setRuns(nextRuns.runs);
        const stored = window.localStorage.getItem(runStorageKey(identity));
        const selected = nextRuns.runs.find((run) => run.runId === stored) ?? nextRuns.runs[0];
        if (selected) setCurrentRunId(selected.runId);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Creator Studio 暂时不可用");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [client, identity]);

  useEffect(() => {
    if (!currentRunId || !identity) {
      setSnapshot(undefined);
      return;
    }
    window.localStorage.setItem(runStorageKey(identity), currentRunId);
    void loadSnapshot(currentRunId).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "任务快照加载失败");
    });
  }, [currentRunId, identity, loadSnapshot]);

  useEffect(() => {
    if (!client || !currentRunId || !snapshot) return;
    let polling = false;
    const timer = window.setInterval(() => {
      if (polling) return;
      polling = true;
      void client.events(currentRunId, lastEventSequenceRef.current)
        .then(async (result) => {
          lastEventSequenceRef.current = result.lastSequence;
          if (result.events.length) await loadSnapshot(currentRunId);
        })
        .catch(() => undefined)
        .finally(() => { polling = false; });
    }, 1_800);
    return () => window.clearInterval(timer);
  }, [client, currentRunId, loadSnapshot, snapshot?.run.runId]);

  useEffect(() => {
    if (!client) return;
    const timer = window.setInterval(() => void refreshRuns().catch(() => undefined), 6_000);
    return () => window.clearInterval(timer);
  }, [client, refreshRuns]);

  useEffect(() => {
    if (!client || workspace !== "marketplace" || marketplace) return;
    setMarketLoading(true);
    void Promise.all([client.marketplace(), client.marketplacePresets()])
      .then(([catalog, presetList]) => {
        setMarketplace(catalog);
        setMarketplacePresets(presetList.presets);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "能力目录加载失败"))
      .finally(() => setMarketLoading(false));
  }, [client, marketplace, workspace]);

  useEffect(() => {
    if (!client || workspace !== "settings") return;
    if (!system) void client.system().then(setSystem).catch(() => undefined);
    if (!deskAgentPreferences) {
      void client.agentPreferences().then(setDeskAgentPreferences).catch(() => undefined);
    }
  }, [client, deskAgentPreferences, system, workspace]);

  const syncCreatorAgent = useCallback(async (agentId: string) => {
    const adapterMap: Record<string, string> = {
      codex: "codex-cli",
      claude: "claude-cli",
      gemini: "gemini-cli",
      hermes: "hermes-webui",
    };
    const adapter = adapterMap[agentId];
    if (!adapter) throw new Error("该 CLI 暂未接入统一 Desk Agent，保留 Creator 本地选择");
    if (!client) throw new Error("Desk Agent 服务尚未连接");
    const current = deskAgentPreferences || await client.agentPreferences();
    const next = await client.saveAgentPreferences({
      defaultAdapter: current.defaultAdapter,
      moduleOverrides: current.moduleOverrides,
      profileTargets: { ...current.profileTargets, edit: adapter },
      moduleProfileOverrides: current.moduleProfileOverrides,
    });
    setDeskAgentPreferences(next);
  }, [client, deskAgentPreferences]);

  const dispatchAction = useCallback<ActionDispatcher>(async (actionId, input = {}) => {
    if (!client) throw new Error("Desk 身份尚未就绪");
    setBusyAction(actionId);
    setError("");
    try {
      if (actionId === "creator.run.create") {
        const title = String(input.title || "").trim();
        const stageId = String(input.stageId || "");
        const nodeId = String(input.nodeId || "");
        const materials = Array.isArray(input.materials) ? input.materials as CreatorMaterial[] : [];
        const next = await client.createRun({ title, stageId, nodeId, materials });
        setSnapshot(next);
        setCurrentRunId(next.run.runId);
        setSelectedStageId(fixedStageId || next.run.activeStageId || stageId);
        setSelectedNodeId(next.run.activeNodeId || nodeId);
        setCreateOpen(false);
        await refreshRuns();
        return next;
      }
      if (actionId === "creator.run.select") {
        const runId = String(input.runId || "");
        if (!runId) throw new Error("runId 不能为空");
        setCurrentRunId(runId);
        return await loadSnapshot(runId);
      }
      if (actionId === "creator.node.select") {
        const stageId = String(input.stageId || "");
        const nodeId = String(input.nodeId || "");
        if (!snapshot?.stages.some((stage) => stage.id === stageId && stage.nodes.some((node) => node.id === nodeId))) {
          throw new Error("目标节点不存在于当前工作流");
        }
        if (fixedStageId && stageId !== fixedStageId) {
          throw new Error("请在 Desk 二级面板打开目标阶段");
        }
        setSelectedStageId(stageId);
        setSelectedNodeId(nodeId);
        return { ok: true, stageId, nodeId };
      }
      if (actionId === "creator.capability.detect") {
        const result = await client.detectCapabilities();
        setCapabilities(result);
        return result;
      }
      if (actionId === "creator.agent.test") {
        return await client.testAgent(
          String(input.agentId || ""),
          String(input.binOverride || ""),
        );
      }
      if (actionId === "creator.marketplace.check-compatibility") {
        return await client.marketplaceCompatibility({
          itemId: String(input.itemId || ""),
          itemKind: String(input.itemKind || "") as "project" | "skill" | "pipeline" | "template",
          stageId: typeof input.stageId === "string" && input.stageId ? input.stageId : undefined,
          nodeId: typeof input.nodeId === "string" && input.nodeId ? input.nodeId : undefined,
        });
      }
      if (actionId === "creator.marketplace.save-preset") {
        const preset = await client.saveMarketplacePreset({
          name: String(input.name || "").trim(),
          itemId: String(input.itemId || ""),
          itemKind: String(input.itemKind || "") as "project" | "skill" | "pipeline" | "template",
          stageId: typeof input.stageId === "string" && input.stageId ? input.stageId : undefined,
          nodeId: typeof input.nodeId === "string" && input.nodeId ? input.nodeId : undefined,
          parameters: typeof input.parameters === "object" && input.parameters && !Array.isArray(input.parameters)
            ? input.parameters as Record<string, unknown>
            : {},
        });
        setMarketplacePresets((current) => [preset, ...current]);
        return preset;
      }
      if (actionId === "creator.marketplace.list-preset-versions") {
        return await client.marketplacePresetVersions(String(input.presetId || ""));
      }
      if (actionId === "creator.marketplace.update-preset") {
        const presetId = String(input.presetId || "");
        const preset = await client.updateMarketplacePreset(presetId, {
          name: String(input.name || "").trim(),
          stageId: typeof input.stageId === "string" && input.stageId ? input.stageId : undefined,
          nodeId: typeof input.nodeId === "string" && input.nodeId ? input.nodeId : undefined,
          parameters: typeof input.parameters === "object" && input.parameters && !Array.isArray(input.parameters)
            ? input.parameters as Record<string, unknown>
            : {},
          expectedVersion: Number(input.expectedVersion),
        });
        setMarketplacePresets((current) => current.map((item) => item.presetId === presetId ? preset : item));
        return preset;
      }
      if (actionId === "creator.run.refresh") {
        return await loadSnapshot();
      }
      if (!snapshot || !currentRunId) throw new Error("请先选择创作任务");
      const stageId = typeof input.stageId === "string" ? input.stageId : selectedStage?.id;
      const nodeId = typeof input.nodeId === "string" ? input.nodeId : selectedNode?.id;
      const { stageId: _stageId, nodeId: _nodeId, ...commandInput } = input;
      const next = await client.command(currentRunId, {
        actionId,
        stageId,
        nodeId,
        input: commandInput,
        expectedRevision: snapshot.run.revision,
      });
      setSnapshot(next);
      if (actionId === "creator.editor.save-template") {
        const presetList = await client.marketplacePresets();
        setMarketplacePresets(presetList.presets);
      }
      lastEventSequenceRef.current = next.lastEventSequence;
      if (actionId === "creator.workflow.continue") {
        setSelectedStageId(fixedStageId || next.run.activeStageId || stageId || "");
        setSelectedNodeId(
          fixedStageId && next.run.activeStageId !== fixedStageId
            ? selectedNode?.id || ""
            : next.run.activeNodeId || nodeId || "",
        );
      } else {
        if (stageId) setSelectedStageId(stageId);
        if (nodeId) setSelectedNodeId(nodeId);
      }
      await refreshRuns();
      return next;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Creator Studio 操作失败";
      setError(message);
      if (message.includes("revision") || message.includes("版本")) {
        await loadSnapshot().catch(() => undefined);
      }
      throw reason;
    } finally {
      setBusyAction("");
    }
  }, [client, currentRunId, fixedStageId, loadSnapshot, refreshRuns, selectedNode?.id, selectedStage?.id, snapshot]);
  actionRef.current = dispatchAction;

  useEffect(() => {
    let active = true;
    let connection: ModHostConnection | undefined;
    void connectModHost({
      modId,
      parentOrigin: parentOrigin(),
      capabilities: ["actions", "agent", "context", "theme"],
    })
      .then((next) => {
        if (!active) {
          next.close();
          return;
        }
        connection = next;
        if (!next.embedded) return;
        setHost(next);
        setIdentity({ userId: next.config.user.id, workspaceId: next.config.workspace.id });
        next.subscribe((desk) => {
          setIdentity({ userId: desk.user.id, workspaceId: desk.workspace.id });
        });
        next.setContextProvider(() => contextRef.current);
        next.setUiActionHandler((actionId, input) => actionRef.current(actionId, input));
      })
      .catch(() => undefined);
    return () => {
      active = false;
      connection?.close();
      setHost(undefined);
    };
  }, [modId]);

  contextRef.current = buildCreatorContext({
    workspace,
    registry,
    runs,
    marketplace,
    marketplacePresets,
    snapshot,
    selectedStage,
    selectedNode,
  });
  useEffect(() => {
    if (host) host.publishContext(contextRef.current);
  }, [host, marketplace, marketplacePresets, registry, runs, selectedNode, selectedStage, snapshot, workspace]);

  if (!identity || loading) {
    return <div className="loading-stage"><LoaderCircle className="spin" size={22} /><span>正在连接 Creator Studio Run Control…</span></div>;
  }

  const isStandalone = window.self === window.top;

  return (
    <div className={isStandalone ? "creator-standalone-layout" : ""}>
      {isStandalone && (
        <nav className="creator-sidebar">
          <div className="creator-sidebar-header">
            <strong>Newma Creator Studio</strong>
            <small>独立开发模式</small>
          </div>
          <ul className="creator-sidebar-nav">
            {([
              ["dashboard", "状态看板"],
              ["intake", "内容采集"],
              ["brief", "选题 Brief"],
              ["draft", "初稿生产"],
              ["transwrite", "多通路转写"],
              ["publish", "发布"],
              ["postmortem", "复盘"],
              ["marketplace", "超市项目"],
              ["settings", "模组设置"],
            ] as [string, string][]).map(([key, label]) => (
              <li key={key} className={workspace === key ? "active" : ""}>
                <a href={`/mod-runtime/creator-studio/?workspace=${key}`}>{label}</a>
              </li>
            ))}
          </ul>
        </nav>
      )}
      <div className="creator-root">
      <StudioHeader
        runs={runs}
        snapshot={snapshot}
        busy={Boolean(busyAction)}
        notificationOpen={notificationOpen}
        onNotificationToggle={() => setNotificationOpen((current) => !current)}
        onCreate={() => setCreateOpen(true)}
        dispatch={dispatchAction}
      />

      {error && <div className="creator-error"><Command size={16} /><span>{error}</span><button onClick={() => setError("")}>关闭</button></div>}

      <div className="creator-page">
        {workspace === "dashboard" && (
          <DashboardView
            snapshot={snapshot}
            selectedStage={selectedStage}
            selectedNode={selectedNode}
            onCreate={() => setCreateOpen(true)}
            dispatch={dispatchAction}
            runs={runs}
            onSelectRun={(runId) => {
              if (runId && runId !== currentRunId) setCurrentRunId(runId);
            }}
          />
        )}
        {isCreatorStage(workspace) && (
          <WorkbenchView
            key={(selectedStage?.id || "") + "." + (selectedNode?.id || "")}
            snapshot={snapshot}
            selectedStage={selectedStage}
            selectedNode={selectedNode}
            dispatch={dispatchAction}
            busy={Boolean(busyAction)}
            onCreate={() => setCreateOpen(true)}
            fetchPreview={fetchArtifactPreview}
            openArtifact={(path: string, label?: string) => {
              if (path) setPreviewArtifact({ path, label });
            }}
          />
        )}
        {workspace === "marketplace" && <MarketplaceView
          marketplace={marketplace}
          presets={marketplacePresets}
          snapshot={snapshot}
          selectedStage={selectedStage}
          selectedNode={selectedNode}
          loading={marketLoading}
          busyAction={busyAction}
          dispatch={dispatchAction}
        />}
        {workspace === "settings" && (
          <SettingsView
            system={system}
            capabilities={capabilities}
            deskAgentPreferences={deskAgentPreferences}
            onSyncAgent={syncCreatorAgent}
            busy={Boolean(busyAction)}
            dispatch={dispatchAction}
          />
        )}
      </div>

      {createOpen && registry && (
        <CreateRunDialog
          registry={registry}
          busy={busyAction === "creator.run.create"}
          onClose={() => setCreateOpen(false)}
          onCreate={(input) => dispatchAction("creator.run.create", input)}
        />
      )}

      {previewArtifact && client && (
        <ArtifactPreviewModal
          path={previewArtifact.path}
          label={previewArtifact.label}
          onClose={() => setPreviewArtifact(null)}
          fetchPreview={fetchArtifactPreview}
        />
      )}

      <footer className="studio-statusbar">
        <span><i className="live-dot" />共享状态已连接</span>
        <span>{snapshot ? "Revision " + snapshot.run.revision : "等待任务"}</span>
        <span>{snapshot ? "同步 " + formatTime(snapshot.generatedAt) : "Newma-Desk Level 3 Mod"}</span>
      </footer>
    </div>
    </div>
  );
}
