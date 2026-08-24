import type { ModPageContext } from "@newma-desk/contracts";
import {
  Bot,
  ChevronDown,
  CircleAlert,
  Code2,
  ExternalLink,
  FileText,
  History,
  ListChecks,
  LoaderCircle,
  MessageSquareText,
  Network,
  Send,
  Settings2,
  Square,
  Zap,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  cancelAgentTask,
  createAgentTask,
  getAgentTask,
  loadAgentSettings,
  type AgentArtifact,
  type AgentAdapterDescription,
  type AgentPreferences,
  type AgentProfile,
  type AgentTask,
} from "../api/agents";
import {
  createModelResponse,
  loadModelProviders,
} from "../api/models";
import type { StoredMod } from "../api/modules";
import { type ModCopilotMode } from "../lib/modCopilotPrompts";
import {
  buildDeskReturnUrl,
  buildNumaHandoffUrl,
  loadModCopilotSessionMetadata,
  readDeskReturnHandoff,
  saveModCopilotSessionMetadata,
  stripDeskReturnHandoffFragment,
  type ModCopilotSessionMetadata,
  type ModCopilotSessionStatus,
} from "../lib/numaHandoff";

type ContextState = "idle" | "syncing" | "ready" | "fallback";
type CopilotRouteMode = "quick" | "research" | "batch" | "edit";

interface ConversationMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  mode?: ModCopilotMode;
  artifacts?: AgentArtifact[];
}

interface ModCopilotProps {
  module: StoredMod;
  open: boolean;
  userId: string;
  workspaceId: string;
  numaAgentUrl?: string;
  numaAllowedOrigins?: readonly string[];
  onClose: () => void;
  onEditCompleted?: () => void | Promise<void>;
  onOpenAgentSettings?: () => void;
  prefill?: {
    id: number;
    prompt: string;
    mode: "ask" | "edit";
  };
  requestContext: () => Promise<ModPageContext | undefined>;
  invokeUiAction?: (
    actionId: string,
    input?: Record<string, unknown>,
  ) => Promise<unknown>;
}

interface AgentRuntimeState {
  id?: string;
  label: string;
  available: boolean;
  loading: boolean;
}

const MESSAGE_STORAGE_PREFIX = "newma-desk.mod-copilot.messages.v1.";
const LEGACY_MESSAGE_STORAGE_PREFIX = "vibedesk.mod-copilot.messages.";
const MAX_MESSAGE_CHARS = 120_000;
const MAX_ARTIFACTS = 4;
const MAX_ARTIFACT_TITLE_CHARS = 120;
const MAX_ARTIFACT_SUMMARY_CHARS = 500;
const MAX_ARTIFACT_CONTENT_CHARS = 60_000;
const LONG_MESSAGE_CHARS = 1_600;
const LONG_MESSAGE_LINES = 18;
const ARTIFACT_ID = /^[0-9a-f]{32}$/;
const HTML_TAG = /<[a-zA-Z][^>]*>/;
const GRAPH_VIEW_URL = /^\/api\/artifacts\/[0-9a-f]{32}\/view$/;
const REPLAY_VIEW_URL =
  /^\/api\/artifacts\/replays\/[0-9a-f]{32}\/view$/;

function sessionStateKey(moduleId: string, workspaceId: string): string {
  return `${workspaceId}:${moduleId}`;
}

function messageStorageKey(moduleId: string, workspaceId: string): string {
  return `${MESSAGE_STORAGE_PREFIX}${encodeURIComponent(workspaceId)}.${encodeURIComponent(moduleId)}`;
}

function boundedText(
  value: unknown,
  limit: number,
  required = false,
): string | undefined {
  if (typeof value !== "string") return undefined;
  const text = value.trim();
  if ((required && !text) || text.length > limit || HTML_TAG.test(text)) {
    return undefined;
  }
  return text || undefined;
}

function parseArtifacts(value: unknown): AgentArtifact[] {
  if (!Array.isArray(value)) return [];
  const artifacts: AgentArtifact[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const candidate = item as Record<string, unknown>;
    const kind = candidate.kind;
    const id = candidate.id;
    const title = boundedText(
      candidate.title,
      MAX_ARTIFACT_TITLE_CHARS,
      true,
    );
    const summary = boundedText(
      candidate.summary,
      MAX_ARTIFACT_SUMMARY_CHARS,
    );
    if (
      (kind !== "report" && kind !== "graph" && kind !== "replay") ||
      typeof id !== "string" ||
      !ARTIFACT_ID.test(id) ||
      !title
    ) {
      continue;
    }
    if (kind === "report") {
      const content = boundedText(
        candidate.content,
        MAX_ARTIFACT_CONTENT_CHARS,
        true,
      );
      if (!content) continue;
      artifacts.push({ id, kind, title, summary, content });
    } else {
      const viewUrl = candidate.viewUrl;
      const safe =
        typeof viewUrl === "string" &&
        (kind === "graph"
          ? GRAPH_VIEW_URL.test(viewUrl)
          : REPLAY_VIEW_URL.test(viewUrl));
      if (!safe) continue;
      artifacts.push({ id, kind, title, summary, viewUrl });
    }
    if (artifacts.length >= MAX_ARTIFACTS) break;
  }
  return artifacts;
}

function parseMessages(raw: string | null): ConversationMessage[] | undefined {
  if (raw === null) return undefined;
  try {
    const value = JSON.parse(raw);
    if (!Array.isArray(value)) return undefined;
    return value
      .flatMap((item): ConversationMessage[] => {
        if (
          typeof item !== "object" ||
          item === null ||
          typeof item.id !== "string" ||
          item.id.length > 200 ||
          !["user", "assistant", "system"].includes(item.role) ||
          typeof item.content !== "string" ||
          item.content.length > MAX_MESSAGE_CHARS
        ) {
          return [];
        }
        const artifacts = parseArtifacts(item.artifacts);
        return [
          {
            id: item.id,
            role: item.role as ConversationMessage["role"],
            content: item.content,
            mode:
              item.mode === "ask" || item.mode === "edit"
                ? item.mode
                : undefined,
            artifacts: artifacts.length ? artifacts : undefined,
          },
        ];
      })
      .slice(-40);
  } catch {
    return undefined;
  }
}

function saveMessages(
  moduleId: string,
  workspaceId: string,
  messages: ConversationMessage[],
): boolean {
  try {
    window.localStorage.setItem(
      messageStorageKey(moduleId, workspaceId),
      JSON.stringify(messages.slice(-40)),
    );
    return true;
  } catch {
    // Blocked storage must not prevent the shared Agent drawer from working.
    return false;
  }
}

function loadMessages(
  moduleId: string,
  workspaceId: string,
): ConversationMessage[] {
  try {
    const scoped = parseMessages(
      window.localStorage.getItem(messageStorageKey(moduleId, workspaceId)),
    );
    if (scoped) return scoped;

    const legacyKey = `${LEGACY_MESSAGE_STORAGE_PREFIX}${moduleId}`;
    const legacy = parseMessages(window.localStorage.getItem(legacyKey));
    if (!legacy) return [];
    if (saveMessages(moduleId, workspaceId, legacy)) {
      window.localStorage.removeItem(legacyKey);
    }
    return legacy;
  } catch {
    return [];
  }
}

function moduleProjectId(module: StoredMod): string {
  return module.manifest.navigation?.project?.id ?? module.moduleId;
}

function messageId(): string {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `message-${Date.now()}-${Math.random().toString(16).slice(2)}`
  );
}

function taskAnswer(task: AgentTask): string {
  if (task.result?.answer) return task.result.answer;
  if (task.result?.message) return task.result.message;
  if (parseArtifacts(task.result?.artifacts).length) return "已生成以下内容。";
  if (task.result) return JSON.stringify(task.result, null, 2);
  return "Agent 已完成任务，但没有返回文本结果。";
}

function fallbackPageContext(module: StoredMod): Record<string, unknown> {
  return {
    view: {
      id: module.moduleId,
      title: module.manifest.name,
    },
    visibleBlocks: [],
    selection: {},
    filters: {},
    data: {
      freshness: "unknown",
      summary: {
        note: "当前 Mod 尚未提供结构化页面上下文，以下信息来自 Manifest。",
        entry: module.manifest.entry,
        category: module.manifest.category,
      },
    },
    actions: [],
    tasks: [],
  };
}

function contextLabel(state: ContextState): string {
  if (state === "syncing") return "正在同步页面";
  if (state === "ready") return "已同步当前页面";
  if (state === "fallback") return "使用 Mod 基础信息";
  return "发送时同步页面";
}

function routedAgentAdapter(
  adapters: AgentAdapterDescription[],
  preferredId: string | undefined,
  mode: Exclude<CopilotRouteMode, "quick">,
): AgentAdapterDescription | undefined {
  const capability =
    mode === "edit"
      ? "module.edit"
      : mode === "batch"
        ? "module.analyze"
        : "module.explain";
  const available = adapters.filter(
    (adapter) =>
      adapter.available !== false && adapter.capabilities.includes(capability),
  );
  const kind = mode === "research" ? "agent-gateway" : "local-cli";
  return (
    available.find((adapter) => adapter.id === preferredId) ??
    available.find((adapter) => adapter.kind === kind) ??
    (mode === "research"
      ? available.find((adapter) => adapter.id === preferredId) ?? available[0]
      : undefined)
  );
}

function profileTarget(
  preferences: AgentPreferences | undefined,
  moduleId: string,
  profile: "quick" | AgentProfile,
): string | undefined {
  return (
    preferences?.moduleProfileOverrides?.[moduleId]?.[profile] ??
    (profile === "deep" ? preferences?.moduleOverrides?.[moduleId] : undefined) ??
    preferences?.profileTargets?.[profile] ??
    (profile === "quick" ? undefined : preferences?.defaultAdapter)
  );
}

function messagePreview(content: string): string {
  const preview = content.split("\n").slice(0, 9).join("\n").slice(0, 900).trimEnd();
  return preview === content ? content : preview + "…";
}

function MessageText({ content, fold }: { content: string; fold: boolean }) {
  const long =
    fold &&
    (content.length > LONG_MESSAGE_CHARS ||
      content.split("\n").length > LONG_MESSAGE_LINES);
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <p className="copilot-message-body">
        {long && !expanded ? messagePreview(content) : content}
      </p>
      {long ? (
        <button
          type="button"
          className="copilot-message-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((current) => !current)}
        >
          <ChevronDown size={13} aria-hidden="true" />
          {expanded ? "收起完整回答" : "展开完整回答"}
        </button>
      ) : null}
    </>
  );
}

function currentArtifactTheme() {
  const root = document.documentElement;
  const styles = getComputedStyle(root);
  const cssVars: Record<string, string> = {};
  for (let index = 0; index < styles.length; index += 1) {
    const name = styles.item(index);
    if (!name.startsWith("--vibe-") && !name.startsWith("--newma-")) {
      continue;
    }
    const value = styles.getPropertyValue(name).trim();
    if (value) cssVars[name] = value;
  }
  const marker = root.dataset.theme ?? root.dataset.vibedeskTheme;
  return {
    mode:
      marker === "dark" ||
      root.classList.contains("dark") ||
      styles.colorScheme === "dark"
        ? "dark"
        : "light",
    cssVars,
  };
}

function ArtifactFrame({ artifact }: { artifact: AgentArtifact }) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const themedUrl = new URL(artifact.viewUrl!, window.location.origin);
  themedUrl.searchParams.set("newmaTheme", "1");
  const sendTheme = () => {
    frameRef.current?.contentWindow?.postMessage(
      { type: "newma:artifact-theme", ...currentArtifactTheme() },
      "*",
    );
  };

  useEffect(() => {
    const forwardTheme = () => sendTheme();
    window.addEventListener("newma:themechange", forwardTheme);
    window.addEventListener("vibedesk:theme", forwardTheme);
    return () => {
      window.removeEventListener("newma:themechange", forwardTheme);
      window.removeEventListener("vibedesk:theme", forwardTheme);
    };
  }, []);

  return (
    <iframe
      ref={frameRef}
      className="copilot-artifact-frame"
      src={themedUrl.toString()}
      title={artifact.title}
      sandbox="allow-scripts allow-downloads"
      loading="lazy"
      onLoad={sendTheme}
    />
  );
}

function ArtifactItem({ artifact }: { artifact: AgentArtifact }) {
  const [expanded, setExpanded] = useState(false);
  const Icon =
    artifact.kind === "report"
      ? FileText
      : artifact.kind === "graph"
        ? Network
        : History;
  const panelId = "copilot-artifact-" + artifact.id;
  return (
    <section className="copilot-artifact">
      <button
        type="button"
        className="copilot-artifact-toggle"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={() => setExpanded((current) => !current)}
      >
        <Icon size={16} aria-hidden="true" />
        <span>
          <strong>{artifact.title}</strong>
          {artifact.summary ? <small>{artifact.summary}</small> : null}
        </span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {expanded ? (
        <div id={panelId}>
          {artifact.kind === "report" ? (
            <div className="copilot-artifact-report">{artifact.content}</div>
          ) : (
            <ArtifactFrame artifact={artifact} />
          )}
          {artifact.viewUrl ? (
            <a
              className="copilot-artifact-open"
              href={artifact.viewUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              <ExternalLink size={12} aria-hidden="true" />
              独立打开
            </a>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export function ModCopilot({
  module,
  open,
  userId,
  workspaceId,
  numaAgentUrl,
  numaAllowedOrigins,
  onClose,
  onEditCompleted,
  onOpenAgentSettings,
  prefill,
  requestContext,
  invokeUiAction,
}: ModCopilotProps) {
  const [messagesByModule, setMessagesByModule] = useState<
    Record<string, ConversationMessage[]>
  >({});
  const [modeByModule, setModeByModule] = useState<
    Record<string, CopilotRouteMode>
  >({});
  const [inputByModule, setInputByModule] = useState<Record<string, string>>(
    {},
  );
  const [taskByModule, setTaskByModule] = useState<Record<string, string>>({});
  const [contextByModule, setContextByModule] = useState<
    Record<string, ContextState>
  >({});
  const [agentByModule, setAgentByModule] = useState<
    Record<string, AgentRuntimeState>
  >({});
  const [agentAdapters, setAgentAdapters] = useState<AgentAdapterDescription[]>([]);
  const [agentPreferences, setAgentPreferences] = useState<AgentPreferences>();
  const [modelProviders, setModelProviders] = useState<
    Awaited<ReturnType<typeof loadModelProviders>>
  >([]);
  const [modelRuntime, setModelRuntime] = useState<AgentRuntimeState>({
    label: "正在读取快速模型…",
    available: false,
    loading: true,
  });
  const [modelRunningByModule, setModelRunningByModule] = useState<
    Record<string, boolean>
  >({});
  const [sessionByModule, setSessionByModule] = useState<
    Record<string, ModCopilotSessionMetadata>
  >({});
  const mountedRef = useRef(true);
  const handledTasksRef = useRef(new Set<string>());
  const taskModesRef = useRef(new Map<string, ModCopilotMode>());
  const messageListRef = useRef<HTMLDivElement>(null);
  const moduleId = module.moduleId;
  const projectId = moduleProjectId(module);
  const currentSessionKey = sessionStateKey(moduleId, workspaceId);
  const messages = messagesByModule[currentSessionKey] ?? [];
  const mode = modeByModule[moduleId] ?? "research";
  const promptMode: ModCopilotMode = mode === "edit" ? "edit" : "ask";
  const input = inputByModule[moduleId] ?? "";
  const activeTaskId = taskByModule[moduleId];
  const contextState = contextByModule[moduleId] ?? "idle";
  const modelRunning = modelRunningByModule[moduleId] ?? false;
  const busy = Boolean(activeTaskId) || contextState === "syncing" || modelRunning;
  const sessionMetadata = sessionByModule[currentSessionKey];

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const list = messageListRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages.length, activeTaskId, open]);

  useEffect(() => {
    if (!prefill) return;
    setInputByModule((current) => ({
      ...current,
      [moduleId]: prefill.prompt,
    }));
    if (prefill.mode === "edit") {
      setModeByModule((current) => ({ ...current, [moduleId]: "edit" }));
    }
  }, [moduleId, prefill]);

  useEffect(() => {
    if (!open) return;
    const storedSession = loadModCopilotSessionMetadata(moduleId, workspaceId);
    const returnedHandoff = readDeskReturnHandoff(
      window.location.href,
      moduleId,
      workspaceId,
      projectId,
    );
    let cleanDeskUrl = window.location.href;
    if (returnedHandoff) {
      const stripped = stripDeskReturnHandoffFragment(window.location.href);
      if (stripped) {
        const cleanLocation = new URL(stripped);
        window.history.replaceState(
          window.history.state,
          "",
          `${cleanLocation.pathname}${cleanLocation.search}${cleanLocation.hash}`,
        );
        cleanDeskUrl = stripped;
      }
    }
    const restoredSession = returnedHandoff
      ? {
          ...(storedSession ?? {}),
          schemaVersion: 1 as const,
          moduleId,
          moduleName: module.manifest.name,
          workspaceId,
          projectId,
          mode: storedSession?.mode ?? ("ask" as const),
          status: "handed-off" as const,
          updatedAt: new Date().toISOString(),
          upstreamSessionId: returnedHandoff.upstreamSessionId,
          deskReturnUrl:
            buildDeskReturnUrl({
              deskUrl: cleanDeskUrl,
              moduleId,
              projectId,
              workspaceId,
              upstreamSessionId: returnedHandoff.upstreamSessionId,
            }) ?? storedSession?.deskReturnUrl,
        }
      : storedSession
        ? { ...storedSession, projectId: storedSession.projectId ?? projectId }
        : undefined;
    if (restoredSession) {
      saveModCopilotSessionMetadata(restoredSession);
      setSessionByModule((current) => ({
        ...current,
        [sessionStateKey(moduleId, workspaceId)]: restoredSession,
      }));
    }
    setMessagesByModule((current) =>
      current[currentSessionKey] === undefined
        ? {
            ...current,
            [currentSessionKey]: loadMessages(moduleId, workspaceId),
          }
        : current,
    );
    setAgentByModule((current) => ({
      ...current,
      [moduleId]: current[moduleId] ?? {
        label: "正在读取 Agent…",
        available: false,
        loading: true,
      },
    }));
    let active = true;
    void loadAgentSettings(userId).then(
      ({ adapters, preferences }) => {
        if (!active) return;
        setAgentAdapters(adapters);
        setAgentPreferences(preferences);
        const selectedId = profileTarget(preferences, moduleId, "deep");
        const selected = adapters.find((adapter) => adapter.id === selectedId);
        setAgentByModule((current) => ({
          ...current,
          [moduleId]: {
            id: selected?.id || selectedId,
            label: selected?.name || selected?.id || selectedId || "Agent 未配置",
            available: selected ? selected.available !== false : false,
            loading: false,
          },
        }));
      },
      () => {
        if (!active) return;
        setAgentAdapters([]);
        setAgentPreferences(undefined);
        setAgentByModule((current) => ({
          ...current,
          [moduleId]: {
            label: "Agent 配置不可用",
            available: false,
            loading: false,
          },
        }));
      },
    );
    setModelRuntime({
      label: "正在读取快速模型…",
      available: false,
      loading: true,
    });
    void loadModelProviders().then(
      (providers) => {
        if (!active) return;
        setModelProviders(providers);
        const selected =
          providers.find(
            (provider) => provider.default && provider.available !== false,
          ) ??
          providers.find((provider) => provider.available !== false) ??
          providers.find((provider) => provider.default) ??
          providers[0];
        setModelRuntime({
          id: selected?.id,
          label: selected?.name || selected?.id || "快速模型",
          available: selected ? selected.available !== false : false,
          loading: false,
        });
      },
      () => {
        if (!active) return;
        setModelProviders([]);
        setModelRuntime({
          label: "快速模型不可用",
          available: false,
          loading: false,
        });
      },
    );
    return () => {
      active = false;
    };
  }, [
    currentSessionKey,
    module,
    moduleId,
    open,
    projectId,
    userId,
    workspaceId,
  ]);

  const appendMessage = (
    targetModuleId: string,
    message: ConversationMessage,
  ) => {
    if (!mountedRef.current) return;
    const targetConversationKey = sessionStateKey(targetModuleId, workspaceId);
    setMessagesByModule((current) => {
      const nextMessages = [
        ...(current[targetConversationKey] ?? []),
        message,
      ].slice(-40);
      saveMessages(targetModuleId, workspaceId, nextMessages);
      return { ...current, [targetConversationKey]: nextMessages };
    });
  };

  const persistSession = (
    targetModule: StoredMod,
    update: Partial<ModCopilotSessionMetadata> & {
      mode: ModCopilotMode;
      status: ModCopilotSessionStatus;
    },
  ) => {
    const key = sessionStateKey(targetModule.moduleId, workspaceId);
    setSessionByModule((current) => {
      const previous =
        current[key] ??
        loadModCopilotSessionMetadata(targetModule.moduleId, workspaceId);
      const next: ModCopilotSessionMetadata = {
        ...previous,
        ...update,
        schemaVersion: 1,
        moduleId: targetModule.moduleId,
        moduleName: targetModule.manifest.name,
        workspaceId,
        projectId: moduleProjectId(targetModule),
        updatedAt: new Date().toISOString(),
      };
      saveModCopilotSessionMetadata(next);
      return { ...current, [key]: next };
    });
  };

  const finishTask = (
    targetModuleId: string,
    taskId: string,
    message?: ConversationMessage,
    editCompleted = false,
  ) => {
    if (handledTasksRef.current.has(taskId)) return;
    handledTasksRef.current.add(taskId);
    taskModesRef.current.delete(taskId);
    if (message) appendMessage(targetModuleId, message);
    if (editCompleted) {
      void Promise.resolve(onEditCompleted?.()).then(
        () =>
          appendMessage(targetModuleId, {
            id: messageId(),
            role: "system",
            content: "修改任务已完成，当前 Mod 已重新加载。",
          }),
        () =>
          appendMessage(targetModuleId, {
            id: messageId(),
            role: "system",
            content: "修改已完成，但自动重新加载失败，请手动刷新当前 Mod。",
          }),
      );
    }
    if (!mountedRef.current) return;
    setTaskByModule((current) => {
      if (current[targetModuleId] !== taskId) return current;
      const next = { ...current };
      delete next[targetModuleId];
      return next;
    });
  };

  const pollTask = async (targetModule: StoredMod, taskId: string) => {
    const targetModuleId = targetModule.moduleId;
    try {
      while (mountedRef.current && !handledTasksRef.current.has(taskId)) {
        const task = await getAgentTask(taskId);
        if (task.status === "completed") {
          const taskMode = taskModesRef.current.get(taskId) ?? "ask";
          const actionResults: string[] = [];
          for (const action of task.result?.actions ?? []) {
            if (!action || typeof action.actionId !== "string") continue;
            try {
              await invokeUiAction?.(action.actionId, action.input ?? {});
              actionResults.push(`已执行 ${action.actionId}`);
            } catch (reason) {
              actionResults.push(
                `${action.actionId} 执行失败：${reason instanceof Error ? reason.message : "未知错误"}`,
              );
            }
          }
          const answer = taskAnswer(task);
          const artifacts = parseArtifacts(task.result?.artifacts);
          const upstreamSessionId =
            typeof task.result?.upstreamSessionId === "string" &&
            task.result.upstreamSessionId.trim()
              ? task.result.upstreamSessionId.trim()
              : undefined;
          const deskReturnUrl = upstreamSessionId
            ? buildDeskReturnUrl({
                deskUrl: window.location.href,
                moduleId: targetModuleId,
                projectId: moduleProjectId(targetModule),
                workspaceId,
                upstreamSessionId,
              })
            : undefined;
          persistSession(targetModule, {
            mode: taskMode,
            status: "completed",
            taskId,
            adapterId:
              (typeof task.result?.agentId === "string" &&
              task.result.agentId.trim()
                ? task.result.agentId.trim()
                : undefined) ??
              (typeof task.request?.adapter === "string"
                ? task.request.adapter
                : undefined),
            upstreamSessionId,
            deskReturnUrl,
          });
          finishTask(
            targetModuleId,
            taskId,
            {
              id: messageId(),
              role: "assistant",
              content: actionResults.length
                ? `${answer}\n\n${actionResults.join("\n")}`
                : answer,
              artifacts: artifacts.length ? artifacts : undefined,
            },
            taskMode === "edit",
          );
          return;
        }
        if (task.status === "failed") {
          persistSession(targetModule, {
            mode: taskModesRef.current.get(taskId) ?? "ask",
            status: "failed",
            taskId,
          });
          finishTask(targetModuleId, taskId, {
            id: messageId(),
            role: "system",
            content: task.error || "Agent 任务失败。",
          });
          return;
        }
        if (task.status === "cancelled") {
          persistSession(targetModule, {
            mode: taskModesRef.current.get(taskId) ?? "ask",
            status: "cancelled",
            taskId,
          });
          finishTask(targetModuleId, taskId, {
            id: messageId(),
            role: "system",
            content: "任务已停止。",
          });
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 650));
      }
    } catch (reason) {
      persistSession(targetModule, {
        mode: taskModesRef.current.get(taskId) ?? "ask",
        status: "failed",
        taskId,
      });
      finishTask(targetModuleId, taskId, {
        id: messageId(),
        role: "system",
        content:
          reason instanceof Error ? reason.message : "读取 Agent 状态失败。",
      });
    }
  };

  const send = async () => {
    const prompt = input.trim();
    if (!prompt || busy) return;
    const targetModule = module;
    const targetModuleId = targetModule.moduleId;
    const targetRouteMode = mode;
    const targetPromptMode: ModCopilotMode =
      targetRouteMode === "edit" ? "edit" : "ask";
    setInputByModule((current) => ({ ...current, [targetModuleId]: "" }));
    appendMessage(targetModuleId, {
      id: messageId(),
      role: "user",
      content: prompt,
      mode: targetPromptMode,
    });
    if (targetRouteMode === "quick") {
      setModelRunningByModule((current) => ({
        ...current,
        [targetModuleId]: true,
      }));
    }
    setContextByModule((current) => ({
      ...current,
      [targetModuleId]: "syncing",
    }));

    try {
      const pageContext = await requestContext();
      if (!mountedRef.current) return;
      setContextByModule((current) => ({
        ...current,
        [targetModuleId]: pageContext ? "ready" : "fallback",
      }));
      const context = {
        vibedesk: {
          mode: targetPromptMode,
          source: pageContext ? "mod-bridge" : "manifest-fallback",
          mod: {
            id: targetModuleId,
            name: targetModule.manifest.name,
            version: targetModule.manifest.version,
            revision: targetModule.revision,
            manifest: targetModule.manifest,
          },
          page: pageContext ?? fallbackPageContext(targetModule),
        },
      };
      if (targetRouteMode === "quick") {
        const response = await createModelResponse({
          moduleId: targetModuleId,
          capability: "module.explain",
          prompt,
          context,
        }, { userId });
        appendMessage(targetModuleId, {
          id: messageId(),
          role: "assistant",
          content: response.answer,
        });
        return;
      }
      const adapter = routedAgentAdapter(
        agentAdapters,
        agentByModule[targetModuleId]?.id,
        targetRouteMode,
      );
      if (!adapter) {
        throw new Error(
          targetRouteMode === "edit"
            ? "没有可用的本地 CLI，请先安装并登录"
            : "没有可用的研究 Agent，请先连接 Hermes 或配置 Agent",
        );
      }
      const task = await createAgentTask(
        { userId, workspaceId },
        {
          moduleId: targetModuleId,
          capability:
            targetRouteMode === "edit"
              ? "module.edit"
              : targetRouteMode === "batch"
                ? "module.analyze"
                : "module.explain",
          profile:
            targetRouteMode === "research" ? "deep" : targetRouteMode,
          memoryScope:
            targetRouteMode === "batch" ? "task" : "user-agent-mod",
          prompt,
          context,
        },
      );
      if (!mountedRef.current) return;
      setTaskByModule((current) => ({
        ...current,
        [targetModuleId]: task.id,
      }));
      taskModesRef.current.set(task.id, targetPromptMode);
      persistSession(targetModule, {
        mode: targetPromptMode,
        status: task.status,
        taskId: task.id,
        adapterId:
          (typeof task.request?.adapter === "string"
            ? task.request.adapter
            : undefined) ?? adapter.id,
        lastPrompt: prompt,
      });
      void pollTask(targetModule, task.id);
    } catch (reason) {
      setContextByModule((current) => ({
        ...current,
        [targetModuleId]: "fallback",
      }));
      appendMessage(targetModuleId, {
        id: messageId(),
        role: "system",
        content: reason instanceof Error ? reason.message : "Agent 请求失败。",
      });
    } finally {
      if (targetRouteMode === "quick") {
        setModelRunningByModule((current) => ({
          ...current,
          [targetModuleId]: false,
        }));
      }
    }
  };

  const stop = async () => {
    if (!activeTaskId) return;
    const taskId = activeTaskId;
    try {
      await cancelAgentTask(taskId);
      persistSession(module, {
        mode: taskModesRef.current.get(taskId) ?? promptMode,
        status: "cancelled",
        taskId,
      });
      finishTask(moduleId, taskId, {
        id: messageId(),
        role: "system",
        content: "任务已停止。",
      });
    } catch (reason) {
      appendMessage(moduleId, {
        id: messageId(),
        role: "system",
        content: reason instanceof Error ? reason.message : "停止任务失败。",
      });
    }
  };

  const configuredAgentState = agentByModule[moduleId] ?? {
    label: "发送时选择 Agent",
    available: true,
    loading: true,
  };
  const routedAdapter =
    mode === "quick"
      ? undefined
      : routedAgentAdapter(
          agentAdapters,
          profileTarget(
            agentPreferences,
            moduleId,
            mode === "research" ? "deep" : mode,
          ) ?? configuredAgentState.id,
          mode,
        );
  const preferredModelId = profileTarget(agentPreferences, moduleId, "quick");
  const selectedModel =
    modelProviders.find(
      (provider) =>
        provider.id === preferredModelId && provider.available !== false,
    ) ??
    modelProviders.find(
      (provider) => provider.default && provider.available !== false,
    ) ??
    modelProviders.find((provider) => provider.available !== false);
  const quickRuntimeState = modelRuntime.loading
    ? modelRuntime
    : selectedModel
      ? {
          id: selectedModel.id,
          label: selectedModel.name || selectedModel.id,
          available: true,
          loading: false,
        }
      : modelRuntime;
  const runtimeState: AgentRuntimeState =
    mode === "quick"
      ? quickRuntimeState
      : configuredAgentState.loading
        ? configuredAgentState
        : routedAdapter
          ? {
              id: routedAdapter.id,
              label: routedAdapter.name || routedAdapter.id,
              available: true,
              loading: false,
            }
          : {
              label: mode === "edit" ? "本地 CLI 不可用" : "研究 Agent 不可用",
              available: false,
              loading: false,
            };
  const suggestionGroups = module.copilotPrompts?.[promptMode] ?? [];
  const handoffUrl = sessionMetadata?.upstreamSessionId
    ? buildNumaHandoffUrl({
        numaAgentUrl,
        numaAllowedOrigins,
        deskUrl: window.location.href,
        deskReturnUrl: sessionMetadata.deskReturnUrl,
        moduleId,
        projectId,
        workspaceId,
        upstreamSessionId: sessionMetadata.upstreamSessionId,
      })
    : undefined;

  return (
    <aside
      className={`mod-copilot${open ? " is-open" : ""}`}
      aria-label={`${module.manifest.name} Agent`}
      aria-hidden={!open}
      inert={!open}
    >
      <header className="mod-copilot-header">
        <div>
          <span>当前 Mod</span>
          <strong>{module.manifest.name}</strong>
          <small data-context-state={contextState}>
            {contextLabel(contextState)} · {runtimeState.label}
          </small>
        </div>
        <div className="mod-copilot-header-actions">
          {onOpenAgentSettings ? (
            <button
              type="button"
              aria-label="打开 Agent 设置"
              onClick={onOpenAgentSettings}
            >
              <Settings2 size={15} aria-hidden="true" />
            </button>
          ) : null}
          <button type="button" aria-label="关闭 Agent 侧栏" onClick={onClose}>
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className="mod-copilot-modes" aria-label="Agent 模式">
        <button
          type="button"
          aria-pressed={mode === "quick"}
          onClick={() =>
            setModeByModule((current) => ({ ...current, [moduleId]: "quick" }))
          }
        >
          <Zap size={14} aria-hidden="true" />
          快速
        </button>
        <button
          type="button"
          aria-pressed={mode === "research"}
          onClick={() =>
            setModeByModule((current) => ({
              ...current,
              [moduleId]: "research",
            }))
          }
        >
          <MessageSquareText size={14} aria-hidden="true" />
          研究
        </button>
        <button
          type="button"
          aria-pressed={mode === "batch"}
          onClick={() =>
            setModeByModule((current) => ({ ...current, [moduleId]: "batch" }))
          }
        >
          <ListChecks size={14} aria-hidden="true" />
          批量
        </button>
        <button
          type="button"
          aria-pressed={mode === "edit"}
          onClick={() =>
            setModeByModule((current) => ({ ...current, [moduleId]: "edit" }))
          }
        >
          <Code2 size={14} aria-hidden="true" />
          修改
        </button>
      </div>

      {mode === "edit" ? (
        <div className="mod-copilot-warning">
          <CircleAlert size={14} aria-hidden="true" />
          Agent 可修改当前 Mod 所属工程，并会返回改动文件与验证结果。
        </div>
      ) : null}

      {!runtimeState.loading && !runtimeState.available ? (
        <div className="mod-copilot-warning">
          <CircleAlert size={14} aria-hidden="true" />
          {mode === "quick"
            ? "快速模型未配置，请使用研究模式或完成模型设置。"
            : "当前执行入口不可用，请先在 Agent 设置中完成安装或连接。"}
        </div>
      ) : null}

      <div className="mod-copilot-messages" ref={messageListRef}>
        {messages.length === 0 ? (
          <div className="mod-copilot-empty">
            <Bot size={22} aria-hidden="true" />
            <strong>
              {mode === "edit"
                ? "修改当前 Mod"
                : mode === "batch"
                  ? "批量处理当前 Mod"
                  : "针对当前 Mod 提问"}
            </strong>
            <span>发送时同步当前页面，并按需补充长期行情、财务或消息。</span>
            {suggestionGroups.map((group) => (
              <div
                key={group.id}
                className="mod-copilot-suggestions"
                role="group"
                aria-label={group.label}
              >
                <span>{group.label}</span>
                {group.suggestions.map((suggestion) => (
                  <button
                    key={suggestion.id}
                    type="button"
                    onClick={() =>
                      setInputByModule((current) => ({
                        ...current,
                        [moduleId]: suggestion.prompt,
                      }))
                    }
                  >
                    {suggestion.label}
                  </button>
                ))}
              </div>
            ))}
          </div>
        ) : (
          messages.map((message) => (
            <article
              key={message.id}
              className={`copilot-message ${message.role}`}
            >
              <span>
                {message.role === "user"
                  ? message.mode === "edit"
                    ? "修改请求"
                    : "你"
                  : message.role === "assistant"
                    ? "Agent"
                    : "系统"}
              </span>
              <MessageText
                content={message.content}
                fold={message.role === "assistant"}
              />
              {message.artifacts?.map((artifact) => (
                <ArtifactItem key={artifact.id} artifact={artifact} />
              ))}
            </article>
          ))
        )}
        {busy ? (
          <div className="mod-copilot-running" role="status">
            <LoaderCircle className="spin" size={15} aria-hidden="true" />
            {modelRunning
              ? "快速模型正在回答…"
              : activeTaskId
                ? "Agent 正在处理当前 Mod…"
                : "正在同步当前页面…"}
          </div>
        ) : null}
      </div>

      <footer className="mod-copilot-composer">
        <textarea
          rows={3}
          value={input}
          onChange={(event) =>
            setInputByModule((current) => ({
              ...current,
              [moduleId]: event.target.value,
            }))
          }
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          placeholder={
            mode === "edit"
              ? "描述要修改的功能或问题…"
              : mode === "batch"
                ? "描述要批量处理的内容…"
              : mode === "quick"
                ? "快速询问当前页面…"
                : "就当前页面提问…"
          }
          disabled={busy}
        />
        {handoffUrl ? (
          <div>
            <span>当前会话可携带上下文继续</span>
            <a
              className="copilot-send"
              href={handoffUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="转到 Numa Agent 继续当前对话"
            >
              <ExternalLink size={13} aria-hidden="true" />
              转到 Numa
            </a>
          </div>
        ) : null}
        <div>
          <span>Enter 发送 · Shift+Enter 换行</span>
          {activeTaskId ? (
            <button
              type="button"
              className="copilot-stop"
              onClick={() => void stop()}
            >
              <Square size={13} aria-hidden="true" />
              停止
            </button>
          ) : (
            <button
              type="button"
              className="copilot-send"
              onClick={() => void send()}
              disabled={!input.trim() || busy || !runtimeState.available}
            >
              <Send size={14} aria-hidden="true" />
              发送
            </button>
          )}
        </div>
      </footer>
    </aside>
  );
}
