import {
  ArrowRightLeft,
  ExternalLink,
  LoaderCircle,
  MessageSquareText,
  TriangleAlert,
} from "lucide-react";
import {
  forwardRef,
  lazy,
  Suspense,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  deskActionResultSchema,
  deskContextRequestSchema,
  deskHandoffSchema,
  deskUiActionRequestSchema,
  deskVisualContextRequestSchema,
  MAX_BRIDGE_VISUAL_CAPTURE_BYTES,
  modAckSchema,
  modActionRequestSchema,
  modAgentRequestSchema,
  modContextSchema,
  modEventSchema,
  modHandoffResultSchema,
  modHelloSchema,
  modUiActionResultSchema,
  modVisualContextSchema,
  type DeskInit,
  type ModManifest,
  type ModPageContext,
  type ModVisualCapturePayload,
  type WikiHandoff,
  type WikiLink,
} from "@newma-desk/contracts";
import { createNewmaDeskAppearance } from "@newma-desk/desk-ui/theme";
import type {
  ModBridge,
  ModContextProvider,
  ModHandoffHandler,
  ModHostConnection,
  ModUiActionHandler,
} from "@newma-desk/mod-sdk";

import type { ShellEventBus } from "../events/ShellEventBus";
import {
  captureModVisualContext,
  invokeModSessionAction,
  issueModSession,
  ModSessionRequestError,
  saveModContext,
  saveModVisualContext,
  type ModSession,
  type ModSessionIssuerInput,
  type SavedModVisualContext,
} from "../api/modSessions";
import { resolveModUrl } from "../lib/moduleUrl";
import { createContextWriter } from "../lib/contextWriter";
import type {
  AgentRuntimeBinding,
  AgentRuntimeMode,
  AgentRuntimeRequest,
} from "../lib/agentRuntime";

import { readNewmaSessions } from "../lib/hostSessions";

const EmbeddedMarketFrame = lazy(() => import("./EmbeddedMarketFrame"));
const EmbeddedIntelligenceFrame = import.meta.env.DEV
  ? lazy(() => import("./EmbeddedIntelligenceFrame"))
  : undefined;

interface ModFrameProps {
  manifest: ModManifest;
  eventBus: ShellEventBus;
  theme: "light" | "dark";
  embedded?: boolean;
  userId?: string;
  workspaceId?: string;
  instanceId?: string;
  locale?: string;
  timezone?: string;
  sessionIssuer?: (input: ModSessionIssuerInput) => Promise<ModSession>;
  actionInvoker?: typeof invokeModSessionAction;
  contextSaver?: typeof saveModContext;
  visualContextSaver?: typeof saveModVisualContext;
  visualContextCapturer?: typeof captureModVisualContext;
  agentRuntime?: AgentRuntimeBinding;
  copilotOpen?: boolean;
  onToggleCopilot?: () => void;
  onContextPublished?: (context: ModPageContext) => void;
  onNavigate?: (targetModId: string, search: string) => void;
  wikiSubjectName?: string;
  wikiLinks?: WikiLink[];
  wikiLoading?: boolean;
  wikiActiveLinkId?: string;
  wikiError?: string;
  onOpenWikiLink?: (link: WikiLink) => void;
}

export type CopilotOpenRequest = AgentRuntimeRequest;

function embeddedMarketMod(manifest: ModManifest) {
  if (manifest.entry.type === "external") return undefined;
  try {
    const url = new URL(manifest.entry.url, window.location.origin);
    const kind: "market" | "intelligence" | undefined = url.pathname === "/mods/market-daily/"
      ? "market"
      : import.meta.env.DEV && url.pathname === "/mods/global-intelligence/"
        ? "intelligence"
        : undefined;
    if (!kind) return undefined;
    return {
      kind,
      key: `${url.pathname}${url.search}`,
      src: url.toString(),
      search: url.search,
    };
  } catch {
    return undefined;
  }
}

type EmbeddedMarketTerminalHost = Extract<ModHostConnection, { embedded: true }>;

type LocalEmbeddedMarketHost = EmbeddedMarketTerminalHost & {
  requestContext(
    reason?: "initial" | "agent" | "refresh",
  ): Promise<ModPageContext | undefined>;
  invokeUiAction<T = unknown>(
    actionId: string,
    input?: Record<string, unknown>,
  ): Promise<T>;
  deliverHandoff(handoff: WikiHandoff): Promise<unknown>;
  updateTheme(theme: "light" | "dark"): void;
};

function createEmbeddedMarketHost(input: {
  manifest: ModManifest;
  userId: string;
  workspaceId: string;
  theme: "light" | "dark";
  locale: string;
  timezone: string;
  sessionIssuer: (input: ModSessionIssuerInput) => Promise<ModSession>;
  actionInvoker: typeof invokeModSessionAction;
  contextSaver: typeof saveModContext;
  latestContextRef: { current: ModPageContext | undefined };
  contextProviderRef: { current: ModContextProvider | undefined };
  uiActionHandlerRef: { current: ModUiActionHandler | undefined };
  handoffHandlerRef: { current: ModHandoffHandler | undefined };
  runtimeMode?: AgentRuntimeMode;
  requestAgent(request?: CopilotOpenRequest): void;
  onContextPublished?: (context: ModPageContext) => void;
}): LocalEmbeddedMarketHost {
  let config = createDeskInit(
    input.manifest,
    createInstanceId(),
    input.userId,
    input.workspaceId,
    input.theme,
    input.locale,
    input.timezone,
    input.runtimeMode,
  );
  const subscribers = new Set<(config: DeskInit) => void>();
  const queuedHandoffs = new Set<{
    handoff: WikiHandoff;
    resolve(value: unknown): void;
    reject(reason: unknown): void;
    timer: number;
  }>();
  let sessionPromise: Promise<ModSession> | undefined;
  let session: ModSession | undefined;
  const ensureSession = (force = false) => {
    if (!force && session && new Date(session.expiresAt).getTime() > Date.now() + 30_000) {
      return Promise.resolve(session);
    }
    if (!force && sessionPromise) return sessionPromise;
    sessionPromise = input.sessionIssuer({
      modId: input.manifest.id,
      instanceId: config.instanceId,
      userId: input.userId,
      workspaceId: input.workspaceId,
    }).then((next) => {
      session = next;
      sessionPromise = undefined;
      return next;
    }, (error) => {
      sessionPromise = undefined;
      throw error;
    });
    return sessionPromise;
  };
  const contextWriter = createContextWriter(async (context) => {
    let currentSession = await ensureSession();
    try {
      await input.contextSaver(currentSession, context);
    } catch (reason) {
      if (!isRecoverableSessionError(reason)) throw reason;
      currentSession = await ensureSession(true);
      await input.contextSaver(currentSession, context);
    }
  });
  const invokeAction = async <T = unknown>(
    actionId: string,
    actionInput: Record<string, unknown>,
  ): Promise<T> => {
    let currentSession = await ensureSession();
    try {
      const result = await input.actionInvoker(currentSession, actionId, actionInput);
      return result.body as T;
    } catch (reason) {
      if (!isRecoverableSessionError(reason)) throw reason;
      currentSession = await ensureSession(true);
      const result = await input.actionInvoker(currentSession, actionId, actionInput);
      return result.body as T;
    }
  };
  return {
    embedded: true,
    get config() {
      return config;
    },
    subscribe(handler) {
      subscribers.add(handler);
      return () => subscribers.delete(handler);
    },
    setContextProvider(provider) {
      input.contextProviderRef.current = provider;
      return () => {
        if (input.contextProviderRef.current === provider) input.contextProviderRef.current = undefined;
      };
    },
    setVisualCaptureProvider() {
      return () => undefined;
    },
    setUiActionHandler(handler) {
      input.uiActionHandlerRef.current = handler;
      return () => {
        if (input.uiActionHandlerRef.current === handler) input.uiActionHandlerRef.current = undefined;
      };
    },
    publishContext(context) {
      input.latestContextRef.current = context;
      input.onContextPublished?.(context);
      void contextWriter.write(context).catch(() => undefined);
    },
    invokeAction: async <T = unknown>(actionId: string, actionInput: Record<string, unknown> = {}): Promise<T> => {
      if (!declaredActionIds(input.manifest).includes(actionId)) {
        throw new Error(`Mod 未声明动作 ${actionId}`);
      }
      return invokeAction<T>(actionId, actionInput);
    },
    requestAgent(request = {}) {
      if (!input.runtimeMode) {
        throw new Error("Agent Runtime is unavailable");
      }
      input.requestAgent(request);
    },
    setHandoffHandler(handler) {
      input.handoffHandlerRef.current = handler;
      for (const pending of [...queuedHandoffs]) {
        queuedHandoffs.delete(pending);
        window.clearTimeout(pending.timer);
        void Promise.resolve(handler(pending.handoff)).then(
          pending.resolve,
          pending.reject,
        );
      }
      return () => {
        if (input.handoffHandlerRef.current === handler) {
          input.handoffHandlerRef.current = undefined;
        }
      };
    },
    close() {
      contextWriter.close();
      subscribers.clear();
      for (const pending of queuedHandoffs) {
        window.clearTimeout(pending.timer);
        pending.reject(new Error("Mod frame was closed"));
      }
      queuedHandoffs.clear();
    },
    requestContext(reason = "agent") {
      return Promise.resolve(input.contextProviderRef.current?.()).then((context) => {
        input.latestContextRef.current = context;
        return context;
      });
    },
    invokeUiAction<T = unknown>(actionId: string, actionInput: Record<string, unknown> = {}) {
      if (!declaredActionIds(input.manifest).includes(actionId)) {
        return Promise.reject(new Error(`Mod 未声明动作 ${actionId}`));
      }
      const handler = input.uiActionHandlerRef.current;
      if (!handler) {
        return Promise.reject(new Error("Mod UI action bridge is unavailable"));
      }
      return Promise.resolve(handler(actionId, actionInput)) as Promise<T>;
    },
    deliverHandoff(handoff) {
      if (handoff.targetModId !== input.manifest.id) {
        return Promise.reject(new Error("Wiki 交接目标与当前 Mod 不一致"));
      }
      const handler = input.handoffHandlerRef.current;
      if (handler) return Promise.resolve(handler(handoff));
      return new Promise((resolve, reject) => {
        const pending = {
          handoff,
          resolve,
          reject,
          timer: window.setTimeout(() => {
            queuedHandoffs.delete(pending);
            reject(new Error("Mod 未及时接收 Wiki 交接"));
          }, 10_000),
        };
        queuedHandoffs.add(pending);
      });
    },
    updateTheme(theme) {
      if (config.environment.theme === theme) return;
      config = createDeskInit(
        input.manifest,
        config.instanceId,
        input.userId,
        input.workspaceId,
        theme,
        input.locale,
        input.timezone,
        input.runtimeMode,
      );
      for (const subscriber of subscribers) subscriber(config);
    },
  };
}

function createEmbeddedMarketBridge(eventBus: ShellEventBus, manifest: ModManifest): ModBridge {
  return {
    emit(event, payload, target) {
      const envelope = modEventSchema.parse({
        version: "1.0",
        event,
        source: manifest.id,
        ...(target ? { target } : {}),
        traceId: createInstanceId(),
        payload,
      });
      eventBus.route(envelope);
      return envelope;
    },
    subscribe(handler) {
      return eventBus.subscribe(handler, {
        moduleId: manifest.id,
        accepts: manifest.events.accepts,
      });
    },
    close() {},
  };
}

export interface ModFrameHandle {
  requestContext(
    reason?: "initial" | "agent" | "refresh",
  ): Promise<ModPageContext | undefined>;
  requestVisualContext(
    reason?: "agent" | "refresh",
  ): Promise<SavedModVisualContext | undefined>;
  requestVisualCapture(
    reason?: "agent" | "refresh",
  ): Promise<ModVisualCapturePayload | undefined>;
  requestAgentEvidence(
    reason?: "agent" | "refresh",
  ): Promise<ModAgentEvidence>;
  reload(): void;
  invokeUiAction<T = unknown>(
    actionId: string,
    input?: Record<string, unknown>,
  ): Promise<T>;
  deliverHandoff(handoff: WikiHandoff): Promise<unknown>;
}

export type ModAgentEvidenceSource =
  | "structured"
  | "dom-html"
  | "visual"
  | "manifest";

export interface ModAgentEvidence {
  page?: ModPageContext;
  source: ModAgentEvidenceSource;
  visual?: SavedModVisualContext;
  freshness: "live" | "fresh" | "stale" | "unknown";
  warnings: string[];
}

function createInstanceId(): string {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `mod-${Date.now()}-${Math.random().toString(16).slice(2)}`
  );
}

function redactLocalFilesystemPaths(value: string): string {
  return value
    .replace(
      /(?:\/(?:Users|Volumes|home|opt|private|tmp)\/|\/var\/folders\/)[^<>"'\n\r]*/g,
      "[local-path]",
    )
    .replace(
      /[A-Za-z]:\\Users\\[^<>"'\n\r]*/g,
      "[local-path]",
    );
}

function declaredActionIds(manifest: ModManifest): string[] {
  return manifest.schemaVersion === "1.1"
    ? Object.keys(manifest.actions)
    : manifest.agentCapabilities;
}

function runtimeActionPrompt(
  manifest: ModManifest,
  actionId: string,
  input: Record<string, unknown>,
): string {
  const prompt = typeof input.prompt === "string" ? input.prompt.trim() : "";
  const parameters = Object.fromEntries(
    Object.entries(input).filter(([key]) => key !== "prompt"),
  );
  const parameterText = Object.keys(parameters).length
    ? `\n\n动作：${actionId}\n参数：${JSON.stringify(parameters)}`
    : `\n\n动作：${actionId}`;
  return `${prompt || `请处理当前「${manifest.name}」页面的 AI 动作。`}${parameterText}`;
}

function isRecoverableSessionError(reason: unknown): boolean {
  return (
    reason instanceof ModSessionRequestError &&
    reason.status === 401
  );
}

function createDeskInit(
  manifest: ModManifest,
  instanceId: string,
  userId: string,
  workspaceId: string,
  theme: "light" | "dark",
  locale: string,
  timezone: string,
  runtimeMode?: AgentRuntimeMode,
  session?: ModSession,
): DeskInit {
  const origin = window.location.origin;
  return {
    type: "vibedesk:init",
    protocolVersion: "1.0",
    instanceId,
    modId: manifest.id,
    user: { id: userId },
    workspace: { id: workspaceId },
    environment: { theme, locale, timezone },
    appearance: createNewmaDeskAppearance(theme),
    gateways: {
      actions: `${origin}/api/mods/${encodeURIComponent(manifest.id)}/actions`,
      ...(runtimeMode === "local"
        ? {
            agent: `${origin}/api/agent`,
            model: `${origin}/api/model`,
          }
        : {}),
      data: `${origin}/api/data-services`,
      storage: `${origin}/api/mods/${encodeURIComponent(manifest.id)}/storage`,
    },
    ...(runtimeMode === "newma"
      ? {
          runtime: {
            owner: "newma" as const,
            aiExecution: "host" as const,
            requestMessage: "vibedesk:copilot-open" as const,
          },
        }
      : runtimeMode === "local"
        ? {
            runtime: {
              owner: "desk" as const,
              aiExecution: "gateway" as const,
              requestMessage: "vibedesk:copilot-open" as const,
            },
          }
        : {}),
    grants: {
      permissions: session?.grants.permissions ?? manifest.permissions,
      actions: session?.grants.actions ?? declaredActionIds(manifest),
    },
    ...(session
      ? {
          session: {
            id: session.sessionId,
            accessToken: session.accessToken,
            expiresAt: session.expiresAt,
          },
        }
      : {}),
  };
}

function logIgnoredMessage(reason: string) {
  if (import.meta.env.DEV && import.meta.env.MODE !== "test") {
    console.debug(`[ModFrame] ignored Mod message: ${reason}`);
  }
}

function sameOriginFrameContext(
  frame: HTMLIFrameElement,
  manifest: ModManifest,
): ModPageContext | undefined {
  try {
    const document = frame.contentDocument;
    const target = frame.contentWindow;
    if (!document || !target) return undefined;
    const contentRoot = document.querySelector<HTMLElement>("main")
      ?? document.querySelector<HTMLElement>("#root")
      ?? document.body;
    if (!contentRoot) return undefined;
    const compact = (value: unknown, limit: number) =>
      typeof value === "string"
        ? value.replace(/\s+/g, " ").trim().slice(0, limit)
        : "";
    const viewId = compact(`${manifest.id}:${target.location.pathname}`.replace(/[^a-zA-Z0-9:_-]+/g, "-"), 128)
      || manifest.id;
    const title = compact(
      contentRoot.querySelector("h1")?.textContent ?? document.title,
      160,
    ) || manifest.name;
    const clone = contentRoot.cloneNode(true) as HTMLElement;
    const visualElementCount = Array.from(
      contentRoot.querySelectorAll<HTMLElement>(
        "canvas, svg, img, video, [role=img], [data-visual-context]",
      ),
    ).filter((element) => {
      if (element instanceof HTMLCanvasElement || element instanceof HTMLVideoElement) {
        return true;
      }
      const rect = element.getBoundingClientRect();
      return rect.width >= 240 && rect.height >= 120;
    }).length;
    clone.querySelectorAll("script, style, noscript, template, svg, canvas, input[type=password], input[type=hidden]")
      .forEach((element) => element.remove());
    clone.querySelectorAll<HTMLElement>("[style]")
      .forEach((element) => element.removeAttribute("style"));
    return {
      view: { id: viewId, title },
      visibleBlocks: Array.from(
        contentRoot.querySelectorAll<HTMLElement>("h1, h2, h3, [role=heading]"),
      ).map((heading, index) => ({
        id: compact(heading.id || `${viewId}-heading-${index + 1}`, 128),
        type: heading.tagName.toLowerCase().slice(0, 80),
        title: compact(heading.textContent, 160),
      })).filter((block) => block.title).slice(0, 80),
      selection: {
        location: compact(
          `${target.location.pathname}${target.location.search}${target.location.hash}`,
          1_000,
        ),
      },
      filters: {},
      data: {
        source: "newma-desk-same-origin-dom",
        freshness: "unknown",
        summary: {
          contextSource: "dom-html-fallback",
          visibleText: redactLocalFilesystemPaths(compact(contentRoot.innerText, 16_000)),
          renderedHtml: redactLocalFilesystemPaths(compact(clone.outerHTML, 24_000)),
          visualElementCount,
          warning: "Mod 未返回结构化上下文，Desk 已读取当前同源页面的渲染 DOM/HTML。",
        },
      },
      actions: [],
      tasks: [],
    };
  } catch {
    return undefined;
  }
}

function pageContextSource(
  context?: ModPageContext,
): "structured" | "dom-html" | "visual" | undefined {
  if (!context) return undefined;
  const summary = context.data.summary;
  if (summary?.contextSource === "server-playwright-dom") return "visual";
  return summary?.contextSource === "dom-html-fallback"
    ? "dom-html"
    : "structured";
}

function pageNeedsVisualEvidence(context?: ModPageContext): boolean {
  if (!context) return true;
  if (pageContextSource(context) !== "dom-html") return false;
  const summary = context.data.summary;
  return typeof summary?.visualElementCount === "number"
    ? summary.visualElementCount > 0
    : true;
}

function pageContextFromVisual(
  visual: SavedModVisualContext,
  manifest: ModManifest,
): ModPageContext | undefined {
  const text = visual.dom?.text.trim();
  const html = visual.dom?.html.trim();
  if (!text && !html) return undefined;
  return {
    view: {
      id: `${manifest.id}:visual`,
      title: visual.title ?? manifest.name,
    },
    visibleBlocks: [],
    selection: {},
    filters: {},
    data: {
      asOf: visual.capturedAt,
      source: "newma-desk-server-playwright",
      freshness: "fresh",
      summary: {
        contextSource: "server-playwright-dom",
        visibleText: text ?? "",
        renderedHtml: html ?? "",
        textTruncated: Boolean(visual.dom?.textTruncated),
        htmlTruncated: Boolean(visual.dom?.htmlTruncated),
        warning: "Mod 未提供结构化上下文，Desk 已重新打开同一 Mod 入口并保存视觉证据；瞬时筛选与未保存状态可能未保留。",
      },
    },
    actions: [],
    tasks: [],
  };
}

const ENGLISH_TITLE_TOKENS: Record<string, string> = {
  ai: "AI",
  cn: "CN",
  czsc: "CZSC",
  etf: "ETF",
  hk: "HK",
  llm: "LLM",
  newma: "Newma",
  us: "US",
};

function fallbackEnglishName(modId: string) {
  return modId
    .split("-")
    .map((token) => ENGLISH_TITLE_TOKENS[token] ?? `${token[0]?.toUpperCase() ?? ""}${token.slice(1)}`)
    .join(" ");
}

function deskStandaloneUrl(modId: string): string | undefined {
  const url = new URL(window.location.href);
  if (
    url.searchParams.get("standalone") === "1" &&
    url.searchParams.get("mod") === modId
  ) {
    return undefined;
  }
  for (const key of [
    "preview",
    "module",
    "view",
    "directory",
    "handoff",
    "host",
    "project",
    "parentOrigin",
  ]) {
    url.searchParams.delete(key);
  }
  url.searchParams.set("mod", modId);
  url.searchParams.delete("copilot");
  url.searchParams.set("standalone", "1");
  return url.toString();
}

function FrameToolbar({
  manifest,
  copilotOpen,
  onToggleCopilot,
  externalUrl,
  wikiSubjectName,
  wikiLinks,
  wikiLoading,
  wikiActiveLinkId,
  wikiError,
  onOpenWikiLink,
}: {
  manifest: ModManifest;
  copilotOpen: boolean;
  onToggleCopilot?: () => void;
  externalUrl?: string;
  wikiSubjectName?: string;
  wikiLinks: WikiLink[];
  wikiLoading: boolean;
  wikiActiveLinkId?: string;
  wikiError?: string;
  onOpenWikiLink?: (link: WikiLink) => void;
}) {
  const showWiki = Boolean(
    wikiSubjectName || wikiLinks.length || wikiLoading || wikiError,
  );
  const englishName = manifest.presentation?.englishName ?? fallbackEnglishName(manifest.id);
  const description = manifest.presentation?.description
    ?? manifest.navigation?.project?.description
    ?? `在 Newma-Desk 中查看并操作${manifest.name}。`;
  return (
    <header className="frame-toolbar">
      <div className="frame-toolbar-title">
        <div className="frame-toolbar-heading">
          <h1>{manifest.name}</h1>
          <span className="frame-toolbar-english">{englishName}</span>
          <span className="frame-toolbar-version">{manifest.version}</span>
        </div>
        <p>{description}</p>
      </div>
      {showWiki ? (
        <nav className="frame-wiki-links" aria-label="关联研究 Mod">
          <span className="frame-wiki-subject">
            关联{wikiSubjectName ? ` · ${wikiSubjectName}` : "研究"}
          </span>
          {wikiLoading && wikiLinks.length === 0 ? (
            <span className="frame-wiki-state">
              <LoaderCircle className="spin" size={12} aria-hidden="true" />
              匹配中
            </span>
          ) : null}
          {wikiLinks.map((link) => {
            const active = wikiActiveLinkId === link.id;
            return (
              <button
                key={link.id}
                type="button"
                title={link.reason}
                aria-label={`用 ${link.label} 查看 ${wikiSubjectName ?? "当前对象"}`}
                disabled={active}
                onClick={() => onOpenWikiLink?.(link)}
              >
                {active ? (
                  <LoaderCircle className="spin" size={12} aria-hidden="true" />
                ) : (
                  <ArrowRightLeft size={12} aria-hidden="true" />
                )}
                {link.label}
              </button>
            );
          })}
          {wikiError ? (
            <span className="frame-wiki-error" role="status">{wikiError}</span>
          ) : null}
        </nav>
      ) : <span className="frame-toolbar-spacer" aria-hidden="true" />}
      <div className="frame-toolbar-actions">
        {onToggleCopilot ? (
          <button
            type="button"
            className="frame-copilot-button"
            aria-pressed={copilotOpen}
            onClick={onToggleCopilot}
          >
            <MessageSquareText size={14} aria-hidden="true" />
            问当前 Mod
          </button>
        ) : null}
        {externalUrl ? (
          <a href={externalUrl} target="_blank" rel="noreferrer">
            独立打开
            <ExternalLink size={14} aria-hidden="true" />
          </a>
        ) : null}
      </div>
    </header>
  );
}

export const ModFrame = forwardRef<ModFrameHandle, ModFrameProps>(
  function ModFrame(
    {
      manifest,
      eventBus,
      theme,
      embedded = false,
      userId = "local-user",
      workspaceId = "local-workspace",
      instanceId: providedInstanceId,
      locale = globalThis.navigator?.language || "zh-CN",
      timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      sessionIssuer = issueModSession,
      actionInvoker = invokeModSessionAction,
      contextSaver = saveModContext,
      visualContextSaver = saveModVisualContext,
      visualContextCapturer = captureModVisualContext,
      agentRuntime,
      copilotOpen = false,
      onToggleCopilot,
      onContextPublished,
      onNavigate,
      wikiSubjectName,
      wikiLinks = [],
      wikiLoading = false,
      wikiActiveLinkId,
      wikiError,
      onOpenWikiLink,
    },
    ref,
  ) {
  const embeddedMarket = useMemo(() => embeddedMarketMod(manifest), [manifest]);
  const embeddedMarketBridge = useMemo(
    () => embeddedMarket
      ? createEmbeddedMarketBridge(eventBus, manifest)
      : undefined,
    [embeddedMarket, eventBus, manifest],
  );
  const resolution = useMemo(() => {
    if (embeddedMarket) return { src: embeddedMarket.src, error: undefined };
    try {
      const src = new URL(resolveModUrl(manifest.entry));
      if (
        manifest.entry.type !== "external" ||
        src.pathname.startsWith("/mod-runtime/") ||
        src.hostname === "localhost" ||
        src.hostname.startsWith("127.")
      ) {
        src.searchParams.set("__newma_mod_version", manifest.version);
      }
      return { src: src.toString(), error: undefined };
    } catch (error) {
      return {
        src: undefined,
        error: error instanceof Error ? error.message : "Mod 地址配置无效",
      };
    }
  }, [embeddedMarket, manifest.entry, manifest.version]);
  const standaloneUrl = useMemo(
    () => embedded ? undefined : deskStandaloneUrl(manifest.id),
    [embedded, manifest.id],
  );
  const [frameState, setFrameState] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [bridgeState, setBridgeState] = useState<
    "pending" | "hello" | "acknowledged" | "legacy" | "error"
  >("pending");
  const [contextState, setContextState] = useState<
    "pending" | "received" | "missing"
  >("pending");
  const frameRef = useRef<HTMLIFrameElement>(null);
  const themeRef = useRef(theme);
  const agentRuntimeRef = useRef(agentRuntime);
  const onContextPublishedRef = useRef(onContextPublished);
  const onNavigateRef = useRef(onNavigate);
  onNavigateRef.current = onNavigate;
  const handshakeRef = useRef(false);
  const acknowledgedRef = useRef(false);
  const sessionRef = useRef<ModSession | undefined>(undefined);
  const sessionPromiseRef = useRef<Promise<ModSession> | undefined>(undefined);
  const latestContextRef = useRef<ModPageContext | undefined>(undefined);
  const embeddedContextProviderRef = useRef<ModContextProvider | undefined>(undefined);
  const embeddedUiActionHandlerRef = useRef<ModUiActionHandler | undefined>(undefined);
  const embeddedHandoffHandlerRef = useRef<ModHandoffHandler | undefined>(undefined);
  const embeddedMarketHostRef = useRef<LocalEmbeddedMarketHost | undefined>(undefined);
  const embeddedMarketKeyRef = useRef<string | undefined>(undefined);
  const requestContextRef = useRef<
    (
      reason: "initial" | "agent" | "refresh",
    ) => Promise<ModPageContext | undefined>
  >(undefined);
  const requestVisualContextRef = useRef<
    (
      reason: "agent" | "refresh",
    ) => Promise<SavedModVisualContext | undefined>
  >(undefined);
  const requestVisualCaptureRef = useRef<
    (
      reason: "agent" | "refresh",
    ) => Promise<ModVisualCapturePayload | undefined>
  >(undefined);
  const requestAgentEvidenceRef = useRef<
    (reason: "agent" | "refresh") => Promise<ModAgentEvidence>
  >(undefined);
  const invokeUiActionRef = useRef<
    <T = unknown>(actionId: string, input?: Record<string, unknown>) => Promise<T>
  >(undefined);
  const deliverHandoffRef = useRef<
    (handoff: WikiHandoff) => Promise<unknown>
  >(undefined);
  const [generatedInstanceId] = useState(createInstanceId);
  const instanceId = providedInstanceId ?? generatedInstanceId;
  const agentRuntimeMode = agentRuntime?.mode;
  themeRef.current = theme;
  agentRuntimeRef.current = agentRuntime;
  onContextPublishedRef.current = onContextPublished;

  useEffect(() => {
    if (!embedded) document.title = `${manifest.name} · Newma-Desk`;
  }, [embedded, manifest.name]);

  useEffect(() => {
    embeddedMarketHostRef.current?.updateTheme(theme);
  }, [theme]);

  useImperativeHandle(
    ref,
    () => ({
      requestContext(reason = "agent") {
        if (embeddedMarketHostRef.current) {
          return embeddedMarketHostRef.current.requestContext(reason);
        }
        return requestContextRef.current?.(reason) ?? Promise.resolve(undefined);
      },
      requestVisualContext(reason = "agent") {
        if (embeddedMarketHostRef.current) return Promise.resolve(undefined);
        return requestVisualContextRef.current?.(reason)
          ?? Promise.resolve(undefined);
      },
      requestVisualCapture(reason = "agent") {
        if (embeddedMarketHostRef.current) return Promise.resolve(undefined);
        return requestVisualCaptureRef.current?.(reason)
          ?? Promise.resolve(undefined);
      },
      requestAgentEvidence(reason = "agent") {
        if (embeddedMarketHostRef.current) {
          return embeddedMarketHostRef.current.requestContext(reason).then((page) => ({
            page,
            source: page ? "structured" : "manifest",
            freshness: page?.data.freshness ?? "unknown",
            warnings: page ? [] : ["当前嵌入式 Mod 未返回页面上下文。"],
          }));
        }
        return requestAgentEvidenceRef.current?.(reason)
          ?? Promise.resolve({
            source: "manifest",
            freshness: "unknown",
            warnings: ["当前 Mod 取证通道尚未就绪。"],
          });
      },
      reload() {
        if (embeddedMarketHostRef.current) return;
        const frame = frameRef.current;
        if (!frame || !resolution.src) return;
        setFrameState("loading");
        frame.src = resolution.src;
      },
      invokeUiAction<T = unknown>(actionId: string, input: Record<string, unknown> = {}) {
        if (embeddedMarketHostRef.current) {
          return embeddedMarketHostRef.current.invokeUiAction<T>(actionId, input);
        }
        const invoke = invokeUiActionRef.current;
        return invoke
          ? invoke<T>(actionId, input)
          : Promise.reject(new Error("Mod UI action bridge is unavailable"));
      },
      deliverHandoff(handoff) {
        if (embeddedMarketHostRef.current) {
          return embeddedMarketHostRef.current.deliverHandoff(handoff);
        }
        const deliver = deliverHandoffRef.current;
        return deliver
          ? deliver(handoff)
          : Promise.reject(new Error("Mod Wiki 交接通道不可用"));
      },
    }),
    [resolution.src],
  );

  useLayoutEffect(() => {
    if (embeddedMarket) {
      requestContextRef.current = undefined;
      requestVisualContextRef.current = undefined;
      requestVisualCaptureRef.current = undefined;
      requestAgentEvidenceRef.current = undefined;
      invokeUiActionRef.current = undefined;
      deliverHandoffRef.current = undefined;
      return;
    }
    setFrameState("loading");
    const frame = frameRef.current;
    if (!frame || !resolution.src) return;

    const expectedOrigin = new URL(resolution.src).origin;
    let active = true;
    let registeredWindow: Window | null = null;
    const pendingContextRequests = new Map<
      string,
      {
        resolve(context?: ModPageContext): void;
        timer: number;
      }
    >();
    const pendingVisualContextRequests = new Map<
      string,
      {
        resolve(capture?: ModVisualCapturePayload): void;
        timer: number;
      }
    >();
    const pendingUiActions = new Map<
      string,
      {
        resolve(value: unknown): void;
        reject(reason: unknown): void;
        timer: number;
      }
    >();
    const pendingHandoffs = new Map<
      string,
      {
        handoff: WikiHandoff;
        resolve(value: unknown): void;
        reject(reason: unknown): void;
        timer: number;
        sent: boolean;
      }
    >();
    let helloCapabilities = new Set<string>();
    handshakeRef.current = false;
    acknowledgedRef.current = false;
    setBridgeState("pending");
    setContextState("pending");
    sessionRef.current = undefined;
    sessionPromiseRef.current = undefined;
    latestContextRef.current = undefined;

    const postLegacyConfig = () => {
      frame.contentWindow?.postMessage(
        {
          type: "vibedesk:config",
          gatewayOrigin: window.location.origin,
          moduleId: manifest.id,
          userId,
          workspaceId,
          theme: themeRef.current,
          appearance: createNewmaDeskAppearance(themeRef.current),
        },
        expectedOrigin,
      );
    };

    const postSessionInit = (session: ModSession) => {
      if (!handshakeRef.current) return;
      frame.contentWindow?.postMessage(
        createDeskInit(
          manifest,
          instanceId,
          userId,
          workspaceId,
          themeRef.current,
          locale,
          timezone,
          agentRuntimeMode,
          session,
        ),
        expectedOrigin,
      );
    };

    const ensureSession = (force = false): Promise<ModSession> => {
      const current = sessionRef.current;
      if (
        !force &&
        current &&
        new Date(current.expiresAt).getTime() > Date.now() + 30_000
      ) {
        return Promise.resolve(current);
      }
      if (!force && sessionPromiseRef.current) return sessionPromiseRef.current;
      const isRenewal = current !== undefined;
      const pending = sessionIssuer({
        modId: manifest.id,
        instanceId,
        userId,
        workspaceId,
      }).then((session) => {
        sessionRef.current = session;
        sessionPromiseRef.current = undefined;
        if (isRenewal) postSessionInit(session);
        return session;
      }, (error) => {
        sessionPromiseRef.current = undefined;
        throw error;
      });
      sessionPromiseRef.current = pending;
      return pending;
    };

    const refreshSession = async (): Promise<ModSession> => {
      return ensureSession(true);
    };

    const withSessionRecovery = async <T,>(
      operation: (session: ModSession) => Promise<T>,
    ): Promise<T> => {
      let session = await ensureSession();
      try {
        return await operation(session);
      } catch (reason) {
        if (!isRecoverableSessionError(reason)) throw reason;
        session = await refreshSession();
        return operation(session);
      }
    };

    const contextWriter = createContextWriter((context) =>
      withSessionRecovery((session) => contextSaver(session, context)),
    );

    const postInit = async () => {
      const session =
        manifest.schemaVersion === "1.1" ? await ensureSession() : undefined;
      frame.contentWindow?.postMessage(
        createDeskInit(
          manifest,
          instanceId,
          userId,
          workspaceId,
          themeRef.current,
          locale,
          timezone,
          agentRuntimeMode,
          session,
        ),
        expectedOrigin,
      );
    };

    const requestContext = (
      reason: "initial" | "agent" | "refresh",
    ): Promise<ModPageContext | undefined> => {
      const requestId = createInstanceId();
      return new Promise((resolve) => {
        const timer = window.setTimeout(() => {
          pendingContextRequests.delete(requestId);
          const fallback = sameOriginFrameContext(frame, manifest);
          latestContextRef.current = fallback;
          if (fallback) {
            setContextState("received");
            onContextPublishedRef.current?.(fallback);
          } else {
            setContextState("missing");
          }
          resolve(fallback);
        }, reason === "initial" ? 2_500 : 5_000);
        pendingContextRequests.set(requestId, { resolve, timer });
        frame.contentWindow?.postMessage(
          deskContextRequestSchema.parse({
            type: "vibedesk:context-request",
            requestId,
            instanceId,
            modId: manifest.id,
            reason,
          }),
          expectedOrigin,
        );
      });
    };
    requestContextRef.current = requestContext;

    const requestVisualCapture = (
      reason: "agent" | "refresh",
    ): Promise<ModVisualCapturePayload | undefined> => {
      if (
        !acknowledgedRef.current ||
        !helloCapabilities.has("visual-context")
      ) {
        return Promise.resolve(undefined);
      }
      const requestId = createInstanceId();
      return new Promise((resolve) => {
        const timer = window.setTimeout(() => {
          pendingVisualContextRequests.delete(requestId);
          resolve(undefined);
        }, 8_000);
        pendingVisualContextRequests.set(requestId, { resolve, timer });
        frame.contentWindow?.postMessage(
          deskVisualContextRequestSchema.parse({
            type: "vibedesk:visual-context-request",
            requestId,
            instanceId,
            modId: manifest.id,
            reason,
            maxBytes: MAX_BRIDGE_VISUAL_CAPTURE_BYTES,
            mediaTypes: ["image/png"],
          }),
          expectedOrigin,
        );
      });
    };
    requestVisualCaptureRef.current = requestVisualCapture;

    const requestVisualContext = async (
      reason: "agent" | "refresh",
    ): Promise<SavedModVisualContext | undefined> => {
      const capture = await requestVisualCapture(reason);
      if (capture) {
        const saved = await withSessionRecovery((session) =>
          visualContextSaver(session, capture),
        ).catch(() => undefined);
        if (saved) return saved;
      }
      return withSessionRecovery((session) =>
        visualContextCapturer(session),
      ).catch(() => undefined);
    };
    requestVisualContextRef.current = requestVisualContext;

    const requestAgentEvidence = async (
      reason: "agent" | "refresh",
    ): Promise<ModAgentEvidence> => {
      const eagerVisual = helloCapabilities.has("visual-context")
        ? requestVisualContext(reason)
        : undefined;
      let page = await requestContext(reason);
      const warnings: string[] = [];
      let visual: SavedModVisualContext | undefined;
      if (
        pageNeedsVisualEvidence(page) ||
        helloCapabilities.has("visual-context")
      ) {
        visual = await (eagerVisual ?? requestVisualContext(reason));
        if (!visual) {
          warnings.push("当前页面没有可交付给 Agent 的视觉快照。");
        } else if (!page) {
          page = pageContextFromVisual(visual, manifest);
        }
        if (visual?.source === "server-playwright") {
          warnings.push("服务端视觉兜底会重新打开同一 Mod，瞬时筛选与未保存状态可能未保留。");
        }
      }
      const source = pageContextSource(page)
        ?? (visual ? "visual" : "manifest");
      if (source === "dom-html") {
        warnings.push("当前 Mod 使用渲染 DOM/HTML 兜底，未提供完整结构化字段。");
      } else if (source === "visual") {
        warnings.push("当前 Mod 仅提供页面截图与渲染文本，没有结构化业务上下文。");
      } else if (source === "manifest") {
        warnings.push("当前 Mod 未返回页面证据，只能使用 Manifest 基础信息。");
      }
      return {
        page,
        source,
        visual,
        freshness: page?.data.freshness ?? "unknown",
        warnings,
      };
    };
    requestAgentEvidenceRef.current = requestAgentEvidence;

    const invokeUiAction = <T = unknown>(
      actionId: string,
      input: Record<string, unknown> = {},
    ): Promise<T> => {
      if (!acknowledgedRef.current) {
        return Promise.reject(new Error("Mod 尚未完成动作协议握手"));
      }
      if (!declaredActionIds(manifest).includes(actionId)) {
        return Promise.reject(new Error(`Mod 未声明动作 ${actionId}`));
      }
      const requestId = createInstanceId();
      return new Promise<T>((resolve, reject) => {
        const timer = window.setTimeout(() => {
          pendingUiActions.delete(requestId);
          reject(new Error("Mod UI action timed out"));
        }, 8_000);
        pendingUiActions.set(requestId, {
          resolve: (value) => resolve(value as T),
          reject,
          timer,
        });
        frame.contentWindow?.postMessage(
          deskUiActionRequestSchema.parse({
            type: "vibedesk:ui-action-request",
            requestId,
            instanceId,
            modId: manifest.id,
            actionId,
            input,
          }),
          expectedOrigin,
        );
      });
    };
    invokeUiActionRef.current = invokeUiAction;

    const flushHandoffs = () => {
      if (!acknowledgedRef.current) return;
      for (const [requestId, pending] of pendingHandoffs) {
        if (pending.sent) continue;
        if (!helloCapabilities.has("handoff")) {
          pendingHandoffs.delete(requestId);
          window.clearTimeout(pending.timer);
          pending.reject(new Error("目标 Mod 尚未接入 Wiki 交接"));
          continue;
        }
        pending.sent = true;
        frame.contentWindow?.postMessage(
          deskHandoffSchema.parse({
            type: "vibedesk:handoff",
            requestId,
            instanceId,
            modId: manifest.id,
            handoff: pending.handoff,
          }),
          expectedOrigin,
        );
      }
    };

    const deliverHandoff = (handoff: WikiHandoff): Promise<unknown> => {
      if (handoff.targetModId !== manifest.id) {
        return Promise.reject(new Error("Wiki 交接目标与当前 Mod 不一致"));
      }
      const requestId = createInstanceId();
      return new Promise((resolve, reject) => {
        const timer = window.setTimeout(() => {
          pendingHandoffs.delete(requestId);
          reject(new Error("Mod Wiki 交接超时"));
        }, 10_000);
        pendingHandoffs.set(requestId, {
          handoff,
          resolve,
          reject,
          timer,
          sent: false,
        });
        flushHandoffs();
      });
    };
    deliverHandoffRef.current = deliverHandoff;

    const finishContextRequest = (
      requestId: string,
      context?: ModPageContext,
    ) => {
      const pending = pendingContextRequests.get(requestId);
      if (!pending) return;
      pendingContextRequests.delete(requestId);
      window.clearTimeout(pending.timer);
      pending.resolve(context);
    };

    const registerCurrentWindow = () => {
      if (registeredWindow) eventBus.unregister(registeredWindow);
      registeredWindow = frame.contentWindow;
      if (!registeredWindow) return;
      eventBus.register({
        moduleId: manifest.id,
        manifest,
        target: registeredWindow,
        origin: expectedOrigin,
      });
    };

    const forwardAgentRequest = (request: CopilotOpenRequest) => {
      const runtime = agentRuntimeRef.current;
      if (!runtime) {
        logIgnoredMessage("Agent Runtime is unavailable");
        return;
      }
      void requestContext("agent")
        .catch(() => undefined)
        .then(() => runtime.request(request));
    };

    const handleLoad = () => {
      setFrameState("ready");
      registerCurrentWindow();
      postLegacyConfig();
    };
    // Browser iframe error reporting is incomplete; this remains a
    // best-effort navigation hint rather than a module health protocol.
    const handleError = () => {
      setFrameState("error");
      setBridgeState("error");
    };
    const handleMessage = (message: MessageEvent) => {
      const currentWindow = frame.contentWindow;
      if (!currentWindow || message.source !== currentWindow) {
        logIgnoredMessage("unexpected source window");
        return;
      }
      if (message.origin !== expectedOrigin) {
        logIgnoredMessage("unexpected origin");
        return;
      }

      const hello = modHelloSchema.safeParse(message.data);
      if (message.data?.type === 'vibedesk:navigate') {
        if (acknowledgedRef.current && message.data.modId === manifest.id &&
          message.data.instanceId === instanceId && typeof message.data.targetModId === 'string' &&
          typeof message.data.search === 'string' && message.data.search.length <= 4096) {
          onNavigateRef.current?.(message.data.targetModId, message.data.search);
        }
        return;
      }
      if (hello.success) {
        if (hello.data.modId !== manifest.id) {
          logIgnoredMessage("hello Mod id mismatch");
          return;
        }
        handshakeRef.current = true;
        helloCapabilities = new Set(hello.data.capabilities);
        setBridgeState("hello");
        if (registeredWindow !== currentWindow) registerCurrentWindow();
        void postInit().catch(() => {
          setFrameState("error");
          setBridgeState("error");
        });
        return;
      }

      const acknowledgement = modAckSchema.safeParse(message.data);
      if (acknowledgement.success) {
        if (
          acknowledgement.data.modId !== manifest.id ||
          acknowledgement.data.instanceId !== instanceId
        ) {
          logIgnoredMessage("handshake acknowledgement mismatch");
          return;
        }
        handshakeRef.current = true;
        acknowledgedRef.current = true;
        setBridgeState("acknowledged");
        flushHandoffs();
        void requestContext("initial");
        return;
      }

      // Manifest 1.0 Mods use the original ready/config exchange. Keep it
      // available while new Mods adopt hello/init/ack.
      if (
        message.data &&
        typeof message.data === "object" &&
        message.data.type === "vibedesk:ready"
      ) {
        setBridgeState("legacy");
        if (registeredWindow !== currentWindow) registerCurrentWindow();
        postLegacyConfig();
        return;
      }

      const agentRequest = modAgentRequestSchema.safeParse(message.data);
      if (agentRequest.success) {
        if (
          !acknowledgedRef.current ||
          !helloCapabilities.has("agent") ||
          agentRequest.data.modId !== manifest.id ||
          agentRequest.data.instanceId !== instanceId
        ) {
          logIgnoredMessage("Agent request handshake mismatch");
          return;
        }
        forwardAgentRequest({
          prompt: agentRequest.data.prompt,
          mode: agentRequest.data.mode,
        });
        return;
      }

      if (!registeredWindow || currentWindow !== registeredWindow) {
        logIgnoredMessage("source Mod is not registered");
        return;
      }

      const context = modContextSchema.safeParse(message.data);
      if (context.success) {
        if (
          !acknowledgedRef.current ||
          context.data.modId !== manifest.id ||
          context.data.instanceId !== instanceId
        ) {
          logIgnoredMessage("context handshake mismatch");
          return;
        }
        latestContextRef.current = context.data.context;
        setContextState("received");
        onContextPublishedRef.current?.(context.data.context);
        void contextWriter.write(context.data.context)
          .then(
            () =>
              finishContextRequest(
                context.data.requestId,
                context.data.context,
              ),
            () => {
              logIgnoredMessage("context persistence failed");
              finishContextRequest(
                context.data.requestId,
                context.data.context,
              );
            },
          );
        return;
      }

      const visualContext = modVisualContextSchema.safeParse(message.data);
      if (visualContext.success) {
        if (
          !acknowledgedRef.current ||
          visualContext.data.modId !== manifest.id ||
          visualContext.data.instanceId !== instanceId
        ) {
          logIgnoredMessage("visual context handshake mismatch");
          return;
        }
        const pending = pendingVisualContextRequests.get(
          visualContext.data.requestId,
        );
        if (!pending) return;
        pendingVisualContextRequests.delete(visualContext.data.requestId);
        window.clearTimeout(pending.timer);
        const capture = visualContext.data.ok
          ? visualContext.data.capture
          : undefined;
        if (!capture) {
          pending.resolve(undefined);
          return;
        }
        pending.resolve(capture);
        return;
      }

      const uiActionResult = modUiActionResultSchema.safeParse(message.data);
      if (uiActionResult.success) {
        if (
          !acknowledgedRef.current ||
          uiActionResult.data.modId !== manifest.id ||
          uiActionResult.data.instanceId !== instanceId
        ) {
          logIgnoredMessage("UI action result handshake mismatch");
          return;
        }
        const pending = pendingUiActions.get(uiActionResult.data.requestId);
        if (!pending) return;
        pendingUiActions.delete(uiActionResult.data.requestId);
        window.clearTimeout(pending.timer);
        if (uiActionResult.data.ok) pending.resolve(uiActionResult.data.result);
        else pending.reject(new Error(uiActionResult.data.error.message));
        return;
      }

      const handoffResult = modHandoffResultSchema.safeParse(message.data);
      if (handoffResult.success) {
        if (
          !acknowledgedRef.current ||
          handoffResult.data.modId !== manifest.id ||
          handoffResult.data.instanceId !== instanceId
        ) {
          logIgnoredMessage("handoff result handshake mismatch");
          return;
        }
        const pending = pendingHandoffs.get(handoffResult.data.requestId);
        if (!pending || pending.handoff.id !== handoffResult.data.handoffId) return;
        pendingHandoffs.delete(handoffResult.data.requestId);
        window.clearTimeout(pending.timer);
        if (handoffResult.data.ok) pending.resolve(handoffResult.data.result);
        else pending.reject(new Error(handoffResult.data.error.message));
        return;
      }

      const actionRequest = modActionRequestSchema.safeParse(message.data);
      if (actionRequest.success) {
        if (
          !acknowledgedRef.current ||
          actionRequest.data.modId !== manifest.id ||
          actionRequest.data.instanceId !== instanceId ||
          !declaredActionIds(manifest).includes(actionRequest.data.actionId)
        ) {
          logIgnoredMessage("action request is not granted");
          return;
        }
        const actionDefinition =
          manifest.schemaVersion === "1.1"
            ? manifest.actions[actionRequest.data.actionId]
            : undefined;
        const runtimeBinding =
          manifest.schemaVersion === "1.0" ||
          actionDefinition?.binding.type === "agent" ||
          actionDefinition?.binding.type === "model";
        const synchronizeContext =
          runtimeBinding
            ? requestContext("agent")
            : Promise.resolve();
        void synchronizeContext
          .then(() => {
            if (runtimeBinding && agentRuntimeRef.current) {
              agentRuntimeRef.current.request({
                mode:
                  actionDefinition?.binding.type === "agent" &&
                  actionDefinition.binding.profile === "edit"
                    ? "edit"
                    : "ask",
                prompt: runtimeActionPrompt(
                  manifest,
                  actionRequest.data.actionId,
                  actionRequest.data.input,
                ),
              });
              return {
                status: 202,
                body: {
                  status: "runtime_handoff",
                  runtime: agentRuntimeMode,
                  actionId: actionRequest.data.actionId,
                },
              };
            }
            if (manifest.id === "workflow-sessions" && actionRequest.data.actionId === "sessions.snapshot") {
              return withSessionRecovery(async (session) => {
                if (actionDefinition?.binding.type !== "local" || actionDefinition.permission !== "sessions.read"
                  || !session.grants.permissions.includes("sessions.read")
                  || !session.grants.actions.includes("sessions.snapshot")
                  || Object.keys(actionRequest.data.input).length !== 0) {
                  throw new Error("当前看板没有读取会话的授权。");
                }
                const body = await readNewmaSessions({ isCurrent: () => active });
                return { status: 200, body };
              });
            }
            return withSessionRecovery((session) =>
              actionInvoker(
                session,
                actionRequest.data.actionId,
                actionRequest.data.input,
              ),
            );
          })
          .then(({ status, body }) => {
            currentWindow.postMessage(
              deskActionResultSchema.parse({
                type: "vibedesk:action-result",
                requestId: actionRequest.data.requestId,
                instanceId,
                modId: manifest.id,
                actionId: actionRequest.data.actionId,
                status,
                ok: true,
                result: body,
              }),
              expectedOrigin,
            );
          })
          .catch((reason: unknown) => {
            const status =
              typeof reason === "object" &&
              reason !== null &&
              "status" in reason &&
              typeof reason.status === "number"
                ? reason.status
                : 502;
            const message =
              reason instanceof Error ? reason.message : "Mod action failed";
            currentWindow.postMessage(
              deskActionResultSchema.parse({
                type: "vibedesk:action-result",
                requestId: actionRequest.data.requestId,
                instanceId,
                modId: manifest.id,
                actionId: actionRequest.data.actionId,
                status,
                ok: false,
                error: { code: "action_failed", message },
              }),
              expectedOrigin,
            );
          });
        return;
      }

      const parsed = modEventSchema.safeParse(message.data);
      if (!parsed.success) {
        logIgnoredMessage("invalid envelope");
        return;
      }
      if (parsed.data.source !== manifest.id) {
        logIgnoredMessage("source Mod mismatch");
        return;
      }
      if (!manifest.events.emits.includes(parsed.data.event)) {
        logIgnoredMessage("undeclared emitted event");
        return;
      }

      eventBus.route(parsed.data, currentWindow ?? undefined);
    };

    frame.addEventListener("load", handleLoad);
    frame.addEventListener("error", handleError);
    window.addEventListener("message", handleMessage);
    return () => {
      active = false;
      contextWriter.close();
      frame.removeEventListener("load", handleLoad);
      frame.removeEventListener("error", handleError);
      window.removeEventListener("message", handleMessage);
      for (const pending of pendingContextRequests.values()) {
        window.clearTimeout(pending.timer);
        pending.resolve(undefined);
      }
      pendingContextRequests.clear();
      for (const pending of pendingVisualContextRequests.values()) {
        window.clearTimeout(pending.timer);
        pending.resolve(undefined);
      }
      pendingVisualContextRequests.clear();
      for (const pending of pendingUiActions.values()) {
        window.clearTimeout(pending.timer);
        pending.reject(new Error("Mod frame was closed"));
      }
      pendingUiActions.clear();
      for (const pending of pendingHandoffs.values()) {
        window.clearTimeout(pending.timer);
        pending.reject(new Error("Mod frame was closed"));
      }
      pendingHandoffs.clear();
      requestContextRef.current = undefined;
      requestVisualContextRef.current = undefined;
      requestVisualCaptureRef.current = undefined;
      requestAgentEvidenceRef.current = undefined;
      invokeUiActionRef.current = undefined;
      deliverHandoffRef.current = undefined;
      if (registeredWindow) eventBus.unregister(registeredWindow);
    };
  }, [
    eventBus,
    instanceId,
    locale,
    manifest,
    resolution.src,
    timezone,
    userId,
    workspaceId,
    actionInvoker,
    contextSaver,
    visualContextSaver,
    visualContextCapturer,
    sessionIssuer,
    embeddedMarket,
    agentRuntimeMode,
  ]);

  useEffect(() => {
    if (embeddedMarket) return;
    if (!resolution.src || frameState !== "ready") return;
    const target = frameRef.current?.contentWindow;
    if (!target) return;
    const origin = new URL(resolution.src).origin;
    target.postMessage(
      {
        type: "vibedesk:config",
        gatewayOrigin: window.location.origin,
        moduleId: manifest.id,
        userId,
        workspaceId,
        theme,
        appearance: createNewmaDeskAppearance(theme),
      },
      origin,
    );
    if (handshakeRef.current) {
      const session = sessionRef.current;
      if (manifest.schemaVersion === "1.0" || session) {
        target.postMessage(
          createDeskInit(
            manifest,
            instanceId,
            userId,
            workspaceId,
            theme,
            locale,
            timezone,
            agentRuntimeMode,
            session,
          ),
          origin,
        );
      }
    }
  }, [
    instanceId,
    locale,
    manifest,
    resolution.src,
    frameState,
    theme,
    timezone,
    userId,
    workspaceId,
    embeddedMarket,
    agentRuntimeMode,
  ]);

  if (resolution.error || !resolution.src) {
    return (
      <div className="frame-message frame-error" role="alert">
        <TriangleAlert size={20} aria-hidden="true" />
        <span>{resolution.error ?? "Mod 地址配置无效"}</span>
      </div>
    );
  }

  const chrome = manifest.presentation?.chrome ?? "standard";
  const showToolbar = !embedded && chrome === "standard";

  if (embeddedMarket) {
    const embeddedHostKey = `${embeddedMarket.key}:${agentRuntimeMode ?? "none"}`;
    if (
      !embeddedMarketHostRef.current ||
      embeddedMarketKeyRef.current !== embeddedHostKey
    ) {
      embeddedMarketHostRef.current?.close();
      embeddedMarketKeyRef.current = embeddedHostKey;
      latestContextRef.current = undefined;
      embeddedContextProviderRef.current = undefined;
      embeddedUiActionHandlerRef.current = undefined;
      embeddedHandoffHandlerRef.current = undefined;
      embeddedMarketHostRef.current = createEmbeddedMarketHost({
        manifest,
        userId,
        workspaceId,
        theme,
        locale,
        timezone,
        sessionIssuer,
        actionInvoker,
        contextSaver,
        latestContextRef,
        contextProviderRef: embeddedContextProviderRef,
        uiActionHandlerRef: embeddedUiActionHandlerRef,
        handoffHandlerRef: embeddedHandoffHandlerRef,
        runtimeMode: agentRuntimeMode,
        requestAgent: (request) => {
          const runtime = agentRuntimeRef.current;
          if (!runtime) throw new Error("Agent Runtime is unavailable");
          runtime.request(request ?? {});
        },
        onContextPublished: (context) => {
          setContextState("received");
          onContextPublishedRef.current?.(context);
        },
      });
    }
    const hostConnection = embeddedMarketHostRef.current;
    return (
      <section
        className="module-frame"
        aria-busy={false}
        data-vibedesk-mod-id={manifest.id}
        data-vibedesk-frame-state="ready"
        data-vibedesk-bridge-state="acknowledged"
        data-vibedesk-context-state={contextState}
        data-vibedesk-embedded={embedded || undefined}
        data-vibedesk-chrome={chrome}
      >
        {showToolbar ? (
          <FrameToolbar
            manifest={manifest}
            copilotOpen={copilotOpen}
            onToggleCopilot={onToggleCopilot}
            externalUrl={standaloneUrl}
            wikiSubjectName={wikiSubjectName}
            wikiLinks={wikiLinks}
            wikiLoading={wikiLoading}
            wikiActiveLinkId={wikiActiveLinkId}
            wikiError={wikiError}
            onOpenWikiLink={onOpenWikiLink}
          />
        ) : null}
        <Suspense
          fallback={(
            <div className="frame-status" role="status">
              <LoaderCircle className="spin" size={18} aria-hidden="true" />
              正在加载市场工作区…
            </div>
          )}
        >
          {embeddedMarket.kind === "intelligence" && EmbeddedIntelligenceFrame ? (
            <EmbeddedIntelligenceFrame hostConnection={hostConnection} search={embeddedMarket.search} />
          ) : (
            <EmbeddedMarketFrame
              search={embeddedMarket.search}
              hostConnection={hostConnection}
              bridge={embeddedMarketBridge}
            />
          )}
        </Suspense>
      </section>
    );
  }

  return (
    <section
      className="module-frame"
      aria-busy={frameState === "loading"}
      data-vibedesk-mod-id={manifest.id}
      data-vibedesk-frame-state={frameState}
      data-vibedesk-bridge-state={bridgeState}
      data-vibedesk-context-state={contextState}
      data-vibedesk-embedded={embedded || undefined}
      data-vibedesk-chrome={chrome}
    >
      {showToolbar ? (
        <FrameToolbar
          manifest={manifest}
          copilotOpen={copilotOpen}
          onToggleCopilot={onToggleCopilot}
          externalUrl={standaloneUrl}
          wikiSubjectName={wikiSubjectName}
          wikiLinks={wikiLinks}
          wikiLoading={wikiLoading}
          wikiActiveLinkId={wikiActiveLinkId}
          wikiError={wikiError}
          onOpenWikiLink={onOpenWikiLink}
        />
      ) : null}
      {frameState === "loading" ? (
        <div className="frame-status" role="status">
          <LoaderCircle className="spin" size={18} aria-hidden="true" />
          正在加载 Mod…
        </div>
      ) : null}
      {frameState === "error" ? (
        <div className="frame-message frame-error" role="alert">
          <TriangleAlert size={18} aria-hidden="true" />
          Mod 页面可能未能加载，请尝试独立打开。
        </div>
      ) : null}
      <iframe
        ref={frameRef}
        title={manifest.name}
        src={resolution.src}
        onLoad={() => setFrameState("ready")}
        onError={() => setFrameState("error")}
        sandbox="allow-scripts allow-forms allow-downloads allow-popups allow-top-navigation-by-user-activation allow-same-origin"
        referrerPolicy="no-referrer"
        allow={manifest.category === "deepsee" && resolution.src.includes("/embed/minutes-agg")
          ? "clipboard-read; clipboard-write; fullscreen; microphone"
          : "clipboard-read; clipboard-write; fullscreen"}
      />
    </section>
  );
  },
);

// Compatibility export for code that still imports the former component name.
export const ModuleFrame = ModFrame;
