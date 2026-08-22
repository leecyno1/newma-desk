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
  modAckSchema,
  modActionRequestSchema,
  modContextSchema,
  modEventSchema,
  modHandoffResultSchema,
  modHelloSchema,
  modUiActionResultSchema,
  type DeskInit,
  type ModManifest,
  type ModPageContext,
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
  invokeModSessionAction,
  issueModSession,
  ModSessionRequestError,
  saveModContext,
  type ModSession,
  type ModSessionIssuerInput,
} from "../api/modSessions";
import { resolveModUrl } from "../lib/moduleUrl";

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
  locale?: string;
  timezone?: string;
  sessionIssuer?: (input: ModSessionIssuerInput) => Promise<ModSession>;
  actionInvoker?: typeof invokeModSessionAction;
  contextSaver?: typeof saveModContext;
  copilotOpen?: boolean;
  onToggleCopilot?: () => void;
  onRequestCopilotOpen?: () => void;
  onContextPublished?: (context: ModPageContext) => void;
  wikiSubjectName?: string;
  wikiLinks?: WikiLink[];
  wikiLoading?: boolean;
  wikiActiveLinkId?: string;
  wikiError?: string;
  onOpenWikiLink?: (link: WikiLink) => void;
}

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
  const saveContext = async (context: ModPageContext) => {
    let currentSession = await ensureSession();
    try {
      await input.contextSaver(currentSession, context);
    } catch (reason) {
      if (!isRecoverableSessionError(reason)) throw reason;
      currentSession = await ensureSession(true);
      await input.contextSaver(currentSession, context);
    }
  };
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
    setUiActionHandler(handler) {
      input.uiActionHandlerRef.current = handler;
      return () => {
        if (input.uiActionHandlerRef.current === handler) input.uiActionHandlerRef.current = undefined;
      };
    },
    publishContext(context) {
      input.latestContextRef.current = context;
      input.onContextPublished?.(context);
      void saveContext(context).catch(() => undefined);
    },
    invokeAction: async <T = unknown>(actionId: string, actionInput: Record<string, unknown> = {}): Promise<T> => {
      if (!declaredActionIds(input.manifest).includes(actionId)) {
        throw new Error(`Mod 未声明动作 ${actionId}`);
      }
      return invokeAction<T>(actionId, actionInput);
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
      subscribers.clear();
      for (const pending of queuedHandoffs) {
        window.clearTimeout(pending.timer);
        pending.reject(new Error("Mod frame was closed"));
      }
      queuedHandoffs.clear();
    },
    requestContext(reason = "agent") {
      if (input.latestContextRef.current) {
        return Promise.resolve(input.latestContextRef.current);
      }
      return Promise.resolve(input.contextProviderRef.current?.()).then((context) => {
        if (context) input.latestContextRef.current = context;
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
  reload(): void;
  invokeUiAction<T = unknown>(
    actionId: string,
    input?: Record<string, unknown>,
  ): Promise<T>;
  deliverHandoff(handoff: WikiHandoff): Promise<unknown>;
}

function createInstanceId(): string {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `mod-${Date.now()}-${Math.random().toString(16).slice(2)}`
  );
}

function declaredActionIds(manifest: ModManifest): string[] {
  return manifest.schemaVersion === "1.1"
    ? Object.keys(manifest.actions)
    : manifest.agentCapabilities;
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
      agent: `${origin}/api/agent`,
      model: `${origin}/api/model`,
      data: `${origin}/api/data-services`,
      storage: `${origin}/api/mods/${encodeURIComponent(manifest.id)}/storage`,
    },
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
      locale = globalThis.navigator?.language || "zh-CN",
      timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      sessionIssuer = issueModSession,
      actionInvoker = invokeModSessionAction,
      contextSaver = saveModContext,
      copilotOpen = false,
      onToggleCopilot,
      onRequestCopilotOpen,
      onContextPublished,
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
        src.pathname.startsWith("/mod-runtime/")
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
  const onRequestCopilotOpenRef = useRef(onRequestCopilotOpen);
  const onContextPublishedRef = useRef(onContextPublished);
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
  const invokeUiActionRef = useRef<
    <T = unknown>(actionId: string, input?: Record<string, unknown>) => Promise<T>
  >(undefined);
  const deliverHandoffRef = useRef<
    (handoff: WikiHandoff) => Promise<unknown>
  >(undefined);
  const [instanceId] = useState(createInstanceId);
  themeRef.current = theme;
  onRequestCopilotOpenRef.current = onRequestCopilotOpen;
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
      invokeUiActionRef.current = undefined;
      deliverHandoffRef.current = undefined;
      return;
    }
    setFrameState("loading");
    const frame = frameRef.current;
    if (!frame || !resolution.src) return;

    const expectedOrigin = new URL(resolution.src).origin;
    let registeredWindow: Window | null = null;
    const pendingContextRequests = new Map<
      string,
      {
        resolve(context?: ModPageContext): void;
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
          if (!latestContextRef.current) setContextState("missing");
          resolve(latestContextRef.current);
        }, 1_500);
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

      if (
        message.data &&
        typeof message.data === "object" &&
        message.data.type === "vibedesk:copilot-open"
      ) {
        onRequestCopilotOpenRef.current?.();
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
        void withSessionRecovery((session) =>
          contextSaver(session, context.data.context),
        )
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
        const synchronizeContext =
          actionDefinition?.binding.type === "agent"
            ? requestContext("agent")
            : Promise.resolve();
        void synchronizeContext
          .then(() =>
            withSessionRecovery((session) =>
              actionInvoker(
                session,
                actionRequest.data.actionId,
                actionRequest.data.input,
              ),
            ),
          )
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
      frame.removeEventListener("load", handleLoad);
      frame.removeEventListener("error", handleError);
      window.removeEventListener("message", handleMessage);
      for (const pending of pendingContextRequests.values()) {
        window.clearTimeout(pending.timer);
        pending.resolve(latestContextRef.current);
      }
      pendingContextRequests.clear();
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
    sessionIssuer,
    embeddedMarket,
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
  ]);

  if (resolution.error || !resolution.src) {
    return (
      <div className="frame-message frame-error" role="alert">
        <TriangleAlert size={20} aria-hidden="true" />
        <span>{resolution.error ?? "Mod 地址配置无效"}</span>
      </div>
    );
  }

  if (embeddedMarket) {
    if (
      !embeddedMarketHostRef.current ||
      embeddedMarketKeyRef.current !== embeddedMarket.key
    ) {
      embeddedMarketHostRef.current?.close();
      embeddedMarketKeyRef.current = embeddedMarket.key;
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
      >
        {!embedded ? (
          <FrameToolbar
            manifest={manifest}
            copilotOpen={copilotOpen}
            onToggleCopilot={onToggleCopilot}
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
    >
      {!embedded ? (
        <FrameToolbar
          manifest={manifest}
          copilotOpen={copilotOpen}
          onToggleCopilot={onToggleCopilot}
          externalUrl={resolution.src}
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
        allow="clipboard-read; clipboard-write; fullscreen"
      />
    </section>
  );
  },
);

// Compatibility export for code that still imports the former component name.
export const ModuleFrame = ModFrame;
