import {
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
  deskUiActionRequestSchema,
  modAckSchema,
  modActionRequestSchema,
  modContextSchema,
  modEventSchema,
  modHelloSchema,
  modUiActionResultSchema,
  type DeskInit,
  type ModManifest,
  type ModPageContext,
} from "@newma-desk/contracts";
import { createNewmaDeskAppearance } from "@newma-desk/desk-ui/theme";
import type {
  ModBridge,
  ModContextProvider,
  ModHostConnection,
  ModUiActionHandler,
} from "@newma-desk/mod-sdk";

import type { ShellEventBus } from "../events/ShellEventBus";
import {
  invokeModSessionAction,
  issueModSession,
  saveModContext,
  type ModSession,
  type ModSessionIssuerInput,
} from "../api/modSessions";
import { resolveModUrl } from "../lib/moduleUrl";

const EmbeddedMarketFrame = lazy(() => import("./EmbeddedMarketFrame"));

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
}

function embeddedMarketMod(manifest: ModManifest) {
  if (manifest.entry.type === "external") return undefined;
  try {
    const url = new URL(manifest.entry.url, window.location.origin);
    if (url.pathname !== "/mods/market-daily/") return undefined;
    return {
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
    reason?: "agent" | "refresh",
  ): Promise<ModPageContext | undefined>;
  invokeUiAction<T = unknown>(
    actionId: string,
    input?: Record<string, unknown>,
  ): Promise<T>;
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
  onContextPublished?: (context: ModPageContext) => void;
}): LocalEmbeddedMarketHost {
  const config = createDeskInit(
    input.manifest,
    createInstanceId(),
    input.userId,
    input.workspaceId,
    input.theme,
    input.locale,
    input.timezone,
  );
  const noop = () => () => undefined;
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
  return {
    embedded: true,
    config,
    subscribe: noop,
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
      void ensureSession().then((currentSession) => input.contextSaver(currentSession, context)).catch(() => undefined);
    },
    invokeAction: async <T = unknown>(actionId: string, actionInput: Record<string, unknown> = {}): Promise<T> => {
      if (!declaredActionIds(input.manifest).includes(actionId)) {
        throw new Error(`Mod 未声明动作 ${actionId}`);
      }
      const currentSession = await ensureSession();
      const result = await input.actionInvoker(currentSession, actionId, actionInput);
      return result.body as T;
    },
    close() {},
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
    reason?: "agent" | "refresh",
  ): Promise<ModPageContext | undefined>;
  reload(): void;
  invokeUiAction<T = unknown>(
    actionId: string,
    input?: Record<string, unknown>,
  ): Promise<T>;
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
      return { src: resolveModUrl(manifest.entry), error: undefined };
    } catch (error) {
      return {
        src: undefined,
        error: error instanceof Error ? error.message : "Mod 地址配置无效",
      };
    }
  }, [embeddedMarket, manifest.entry]);
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
  const handshakeRef = useRef(false);
  const acknowledgedRef = useRef(false);
  const sessionRef = useRef<ModSession | undefined>(undefined);
  const sessionPromiseRef = useRef<Promise<ModSession> | undefined>(undefined);
  const latestContextRef = useRef<ModPageContext | undefined>(undefined);
  const embeddedContextProviderRef = useRef<ModContextProvider | undefined>(undefined);
  const embeddedUiActionHandlerRef = useRef<ModUiActionHandler | undefined>(undefined);
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
  const [instanceId] = useState(createInstanceId);
  themeRef.current = theme;
  onRequestCopilotOpenRef.current = onRequestCopilotOpen;

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
    }),
    [resolution.src],
  );

  useLayoutEffect(() => {
    if (embeddedMarket) {
      requestContextRef.current = undefined;
      invokeUiActionRef.current = undefined;
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
      const pending = sessionIssuer({
        modId: manifest.id,
        instanceId,
        userId,
        workspaceId,
      }).then((session) => {
        sessionRef.current = session;
        sessionPromiseRef.current = undefined;
        return session;
      }, (error) => {
        sessionPromiseRef.current = undefined;
        throw error;
      });
      sessionPromiseRef.current = pending;
      return pending;
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
        void ensureSession()
          .then((session) => contextSaver(session, context.data.context))
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
          .then(() => ensureSession())
          .then((session) =>
            actionInvoker(
              session,
              actionRequest.data.actionId,
              actionRequest.data.input,
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
      requestContextRef.current = undefined;
      invokeUiActionRef.current = undefined;
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
        onContextPublished: () => setContextState("received"),
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
        {!embedded && onToggleCopilot ? (
          <header className="frame-toolbar embedded-market-toolbar">
            <div>
              <strong>{manifest.name}</strong>
              <span>{manifest.version}</span>
            </div>
            <div className="frame-toolbar-actions">
              <button
                type="button"
                className="frame-copilot-button"
                aria-pressed={copilotOpen}
                onClick={onToggleCopilot}
              >
                <MessageSquareText size={14} aria-hidden="true" />
                问当前 Mod
              </button>
            </div>
          </header>
        ) : null}
        <Suspense
          fallback={(
            <div className="frame-status" role="status">
              <LoaderCircle className="spin" size={18} aria-hidden="true" />
              正在加载市场工作区…
            </div>
          )}
        >
          <EmbeddedMarketFrame
            search={embeddedMarket.search}
            hostConnection={hostConnection}
            bridge={embeddedMarketBridge}
          />
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
        <header className="frame-toolbar">
          <div>
            <strong>{manifest.name}</strong>
            <span>{manifest.version}</span>
          </div>
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
            <a href={resolution.src} target="_blank" rel="noreferrer">
              独立打开
              <ExternalLink size={14} aria-hidden="true" />
            </a>
          </div>
        </header>
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
        sandbox="allow-scripts allow-forms allow-downloads allow-popups allow-same-origin"
        referrerPolicy="no-referrer"
        allow="clipboard-read; clipboard-write; fullscreen"
      />
    </section>
  );
  },
);

// Compatibility export for code that still imports the former component name.
export const ModuleFrame = ModFrame;
