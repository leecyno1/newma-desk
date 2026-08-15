import {
  deskActionResultSchema,
  deskContextRequestSchema,
  deskHandoffSchema,
  deskInitSchema,
  deskUiActionRequestSchema,
  modActionRequestSchema,
  modContextSchema,
  modHelloSchema,
  modHandoffResultSchema,
  modUiActionResultSchema,
  modPageContextSchema,
  type DeskContextRequest,
  type DeskHandoff,
  type DeskInit,
  type ModPageContext,
  type WikiHandoff,
} from "@newma-desk/contracts";

export interface ModHostConfig {
  modId: string;
  parentOrigin: string;
  sdkVersion?: string;
  capabilities?: Array<
    | "events"
    | "actions"
    | "agent"
    | "model"
    | "data"
    | "context"
    | "storage"
    | "theme"
    | "handoff"
  >;
  timeoutMs?: number;
  requestTimeoutMs?: number;
  /** Applies the Desk theme contract to document.documentElement. Defaults to true. */
  applyAppearance?: boolean;
  signal?: AbortSignal;
}

export interface DeskAppearanceInput {
  environment: { theme: "light" | "dark" };
  appearance?: DeskInit["appearance"];
}

export interface DeskThemeChangeDetail {
  mode: "light" | "dark";
  appearance?: DeskInit["appearance"];
}

const appliedAppearanceVariables = new WeakMap<HTMLElement, Set<string>>();

/**
 * Applies the standard Newma theme contract to a Mod document.
 *
 * This helper intentionally operates only on the Mod's own document. It never
 * reaches across iframe origins. connectModHost calls it automatically for
 * the first init and every live theme update unless applyAppearance is false.
 */
export function applyDeskAppearance(
  config: DeskAppearanceInput,
  root: HTMLElement | undefined = globalThis.document?.documentElement,
): void {
  if (!root) return;
  const mode = config.environment.theme;
  const appearance = config.appearance?.mode === mode
    ? config.appearance
    : undefined;
  root.dataset.theme = mode;
  root.dataset.vibedeskTheme = mode;
  root.dataset.bsTheme = mode;
  root.classList.toggle("light", mode === "light");
  root.classList.toggle("dark", mode === "dark");
  root.style.colorScheme = mode;
  const themeColor = root.ownerDocument?.querySelector?.(
    'meta[name="theme-color"]',
  ) as HTMLMetaElement | null | undefined;
  themeColor?.setAttribute(
    "content",
    appearance?.semantic.bg ?? (mode === "dark" ? "#0f1714" : "#f4efe3"),
  );

  const variables = appearance?.cssVars ?? {};
  const previousVariables = appliedAppearanceVariables.get(root) ?? new Set();
  const nextVariables = new Set(Object.keys(variables));
  for (const name of previousVariables) {
    if (!nextVariables.has(name)) root.style.removeProperty(name);
  }
  for (const [name, value] of Object.entries(variables)) {
    root.style.setProperty(name, value);
  }
  appliedAppearanceVariables.set(root, nextVariables);

  const view = root.ownerDocument?.defaultView;
  if (!view) return;
  const detail: DeskThemeChangeDetail = {
    mode,
    ...(appearance ? { appearance } : {}),
  };
  view.dispatchEvent(new view.CustomEvent<DeskThemeChangeDetail>(
    "newma:themechange",
    { detail },
  ));
}

export class ModHostActionError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ModHostActionError";
    this.status = status;
    this.code = code;
  }
}

export type ModContextProvider = () =>
  | ModPageContext
  | Promise<ModPageContext>;

export type ModUiActionHandler = (
  actionId: string,
  input: Record<string, unknown>,
) => unknown | Promise<unknown>;

export type ModHandoffHandler = (
  handoff: WikiHandoff,
) => unknown | Promise<unknown>;

export type ModHostConnection =
  | { embedded: false; close(): void }
  | {
      embedded: true;
      config: DeskInit;
      subscribe(handler: (config: DeskInit) => void): () => void;
      setContextProvider(provider: ModContextProvider): () => void;
      setUiActionHandler(handler: ModUiActionHandler): () => void;
      setHandoffHandler(handler: ModHandoffHandler): () => void;
      publishContext(context: ModPageContext): void;
      invokeAction<T = unknown>(
        actionId: string,
        input?: Record<string, unknown>,
      ): Promise<T>;
      close(): void;
    };

export interface ModHostRuntime {
  window: Window;
  setTimeout(
    handler: () => void,
    timeoutMs: number,
  ): ReturnType<typeof globalThis.setTimeout>;
  clearTimeout(handle: ReturnType<typeof globalThis.setTimeout>): void;
  randomUUID?: () => string;
}

function fallbackRequestId(): string {
  return `request-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function defaultRuntime(): ModHostRuntime {
  return {
    window,
    setTimeout: globalThis.setTimeout.bind(globalThis),
    clearTimeout: globalThis.clearTimeout.bind(globalThis),
    randomUUID: () => globalThis.crypto?.randomUUID?.() ?? fallbackRequestId(),
  };
}

function exactHttpOrigin(value: string): string {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error("parentOrigin must be an HTTP(S) origin");
  }
  if (
    (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
    parsed.origin !== value
  ) {
    throw new Error("parentOrigin must be an HTTP(S) origin");
  }
  return value;
}

function standaloneThemeMode(root: HTMLElement): "light" | "dark" {
  if (root.dataset.theme === "light" || root.dataset.theme === "dark") {
    return root.dataset.theme;
  }
  if (
    root.dataset.vibedeskTheme === "light" ||
    root.dataset.vibedeskTheme === "dark"
  ) {
    return root.dataset.vibedeskTheme;
  }
  if (root.dataset.bsTheme === "light" || root.dataset.bsTheme === "dark") {
    return root.dataset.bsTheme;
  }
  if (root.classList.contains("dark")) return "dark";
  return "light";
}

export function connectModHost(
  config: ModHostConfig,
  runtime: ModHostRuntime = defaultRuntime(),
): Promise<ModHostConnection> {
  const parentOrigin = exactHttpOrigin(config.parentOrigin);
  const timeoutMs = config.timeoutMs ?? 5_000;
  const requestTimeoutMs = config.requestTimeoutMs ?? 30_000;
  const shouldApplyAppearance = config.applyAppearance ?? true;
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > 60_000) {
    throw new Error("timeoutMs must be between 1 and 60000");
  }
  if (
    !Number.isFinite(requestTimeoutMs) ||
    requestTimeoutMs <= 0 ||
    requestTimeoutMs > 300_000
  ) {
    throw new Error("requestTimeoutMs must be between 1 and 300000");
  }
  const hello = modHelloSchema.parse({
    type: "vibedesk:hello",
    modId: config.modId,
    protocolVersions: ["1.0"],
    ...(config.sdkVersion === undefined
      ? {}
      : { sdkVersion: config.sdkVersion }),
    capabilities: config.capabilities ?? [],
  });

  if (runtime.window.parent === runtime.window) {
    const root = runtime.window.document?.documentElement;
    if (shouldApplyAppearance && root) {
      applyDeskAppearance(
        { environment: { theme: standaloneThemeMode(root) } },
        root,
      );
    }
    return Promise.resolve({
      embedded: false,
      close() {},
    });
  }

  return new Promise((resolve, reject) => {
    let settled = false;
    let closed = false;
    let activeConfig: DeskInit | undefined;
    let contextProvider: ModContextProvider | undefined;
    let uiActionHandler: ModUiActionHandler | undefined;
    let handoffHandler: ModHandoffHandler | undefined;
    const queuedContextRequests: DeskContextRequest[] = [];
    const queuedHandoffs: DeskHandoff[] = [];
    const subscriptions = new Set<(config: DeskInit) => void>();
    const pendingActions = new Map<
      string,
      {
        resolve(value: unknown): void;
        reject(reason: unknown): void;
        timer: ReturnType<typeof globalThis.setTimeout>;
      }
    >();
    const requestId = () => runtime.randomUUID?.() ?? fallbackRequestId();
    const post = (message: unknown) => {
      runtime.window.parent.postMessage(message, parentOrigin);
    };
    const cleanup = () => {
      if (closed) return;
      closed = true;
      runtime.clearTimeout(handshakeTimer);
      runtime.window.removeEventListener("message", handleMessage);
      config.signal?.removeEventListener("abort", handleAbort);
      subscriptions.clear();
      queuedContextRequests.length = 0;
      queuedHandoffs.length = 0;
      uiActionHandler = undefined;
      handoffHandler = undefined;
      for (const pending of pendingActions.values()) {
        runtime.clearTimeout(pending.timer);
        pending.reject(new Error("Newma-Desk host connection is closed"));
      }
      pendingActions.clear();
    };
    const handleAbort = () => {
      cleanup();
      if (!settled) {
        settled = true;
        reject(new Error("Newma-Desk host handshake was aborted"));
      }
    };
    const publishContext = (context: ModPageContext, linkedRequestId?: string) => {
      if (!activeConfig) throw new Error("Newma-Desk host is not initialized");
      post(
        modContextSchema.parse({
          type: "vibedesk:context",
          requestId: linkedRequestId ?? requestId(),
          instanceId: activeConfig.instanceId,
          modId: activeConfig.modId,
          context: modPageContextSchema.parse(context),
        }),
      );
    };
    const respondWithContext = async (contextRequest: DeskContextRequest) => {
      if (!contextProvider) {
        queuedContextRequests.splice(0, queuedContextRequests.length, contextRequest);
        return;
      }
      try {
        publishContext(await contextProvider(), contextRequest.requestId);
      } catch {
        // A failed provider must not leak application errors across origins.
      }
    };
    const respondToHandoff = async (request: DeskHandoff) => {
      if (!handoffHandler) {
        queuedHandoffs.push(request);
        return;
      }
      try {
        const result = await handoffHandler(request.handoff);
        post(modHandoffResultSchema.parse({
          type: "vibedesk:handoff-result",
          requestId: request.requestId,
          instanceId: request.instanceId,
          modId: request.modId,
          handoffId: request.handoff.id,
          ok: true,
          result: result ?? {},
        }));
      } catch (reason) {
        post(modHandoffResultSchema.parse({
          type: "vibedesk:handoff-result",
          requestId: request.requestId,
          instanceId: request.instanceId,
          modId: request.modId,
          handoffId: request.handoff.id,
          ok: false,
          error: {
            code: "handoff_failed",
            message: reason instanceof Error ? reason.message : "Wiki handoff failed",
          },
        }));
      }
    };
    const connection = () => {
      if (!activeConfig) throw new Error("Newma-Desk host is not initialized");
      const initialConfig = activeConfig;
      return {
        embedded: true as const,
        config: initialConfig,
        subscribe(handler: (next: DeskInit) => void) {
          if (closed) throw new Error("Newma-Desk host connection is closed");
          subscriptions.add(handler);
          return () => subscriptions.delete(handler);
        },
        setContextProvider(provider: ModContextProvider) {
          if (closed) throw new Error("Newma-Desk host connection is closed");
          contextProvider = provider;
          const queued = queuedContextRequests.splice(0);
          for (const request of queued) void respondWithContext(request);
          return () => {
            if (contextProvider === provider) contextProvider = undefined;
          };
        },
        setUiActionHandler(handler: ModUiActionHandler) {
          if (closed) throw new Error("Newma-Desk host connection is closed");
          uiActionHandler = handler;
          return () => {
            if (uiActionHandler === handler) uiActionHandler = undefined;
          };
        },
        setHandoffHandler(handler: ModHandoffHandler) {
          if (closed) throw new Error("Newma-Desk host connection is closed");
          handoffHandler = handler;
          const queued = queuedHandoffs.splice(0);
          for (const request of queued) void respondToHandoff(request);
          return () => {
            if (handoffHandler === handler) handoffHandler = undefined;
          };
        },
        publishContext(context: ModPageContext) {
          if (closed) throw new Error("Newma-Desk host connection is closed");
          publishContext(context);
        },
        invokeAction<T = unknown>(
          actionId: string,
          input: Record<string, unknown> = {},
        ): Promise<T> {
          if (closed) {
            return Promise.reject(new Error("Newma-Desk host connection is closed"));
          }
          if (!activeConfig?.grants.actions.includes(actionId)) {
            return Promise.reject(
              new ModHostActionError(403, "action_not_granted", "Action is not granted"),
            );
          }
          const requestConfig = activeConfig;
          const id = requestId();
          return new Promise<T>((resolveAction, rejectAction) => {
            const timer = runtime.setTimeout(() => {
              pendingActions.delete(id);
              rejectAction(new Error("Newma-Desk action request timed out"));
            }, requestTimeoutMs);
            pendingActions.set(id, {
              resolve: (value) => resolveAction(value as T),
              reject: rejectAction,
              timer,
            });
            post(
              modActionRequestSchema.parse({
                type: "vibedesk:action-request",
                requestId: id,
                instanceId: requestConfig.instanceId,
                modId: requestConfig.modId,
                actionId,
                input,
              }),
            );
          });
        },
        close: cleanup,
      };
    };
    const handleMessage = (message: MessageEvent) => {
      if (closed) return;
      if (
        message.origin !== parentOrigin ||
        message.source !== runtime.window.parent
      ) {
        return;
      }
      const init = deskInitSchema.safeParse(message.data);
      if (init.success && init.data.modId === config.modId) {
        activeConfig = init.data;
        if (shouldApplyAppearance) {
          applyDeskAppearance(
            init.data,
            runtime.window.document?.documentElement,
          );
        }
        post({
          type: "vibedesk:ack",
          protocolVersion: init.data.protocolVersion,
          instanceId: init.data.instanceId,
          modId: init.data.modId,
        });
        if (!settled) {
          settled = true;
          runtime.clearTimeout(handshakeTimer);
          resolve(connection());
          return;
        }
        for (const handler of subscriptions) handler(init.data);
        return;
      }

      const contextRequest = deskContextRequestSchema.safeParse(message.data);
      if (
        contextRequest.success &&
        activeConfig &&
        contextRequest.data.modId === activeConfig.modId &&
        contextRequest.data.instanceId === activeConfig.instanceId
      ) {
        void respondWithContext(contextRequest.data);
        return;
      }

      const uiActionRequest = deskUiActionRequestSchema.safeParse(message.data);
      if (
        uiActionRequest.success &&
        activeConfig &&
        uiActionRequest.data.modId === activeConfig.modId &&
        uiActionRequest.data.instanceId === activeConfig.instanceId
      ) {
        const request = uiActionRequest.data;
        if (!activeConfig.grants.actions.includes(request.actionId)) {
          post(modUiActionResultSchema.parse({
            type: "vibedesk:ui-action-result",
            requestId: request.requestId,
            instanceId: request.instanceId,
            modId: request.modId,
            actionId: request.actionId,
            ok: false,
            error: { code: "action_not_granted", message: "UI action is not granted" },
          }));
          return;
        }
        if (!uiActionHandler) {
          post(modUiActionResultSchema.parse({
            type: "vibedesk:ui-action-result",
            requestId: request.requestId,
            instanceId: request.instanceId,
            modId: request.modId,
            actionId: request.actionId,
            ok: false,
            error: { code: "handler_unavailable", message: "Mod UI action handler is unavailable" },
          }));
          return;
        }
        void Promise.resolve(uiActionHandler(request.actionId, request.input)).then(
          (result) => post(modUiActionResultSchema.parse({
            type: "vibedesk:ui-action-result",
            requestId: request.requestId,
            instanceId: request.instanceId,
            modId: request.modId,
            actionId: request.actionId,
            ok: true,
            result: result ?? {},
          })),
          (reason: unknown) => post(modUiActionResultSchema.parse({
            type: "vibedesk:ui-action-result",
            requestId: request.requestId,
            instanceId: request.instanceId,
            modId: request.modId,
            actionId: request.actionId,
            ok: false,
            error: {
              code: "action_failed",
              message: reason instanceof Error ? reason.message : "Mod UI action failed",
            },
          })),
        );
        return;
      }

      const handoffRequest = deskHandoffSchema.safeParse(message.data);
      if (
        handoffRequest.success &&
        activeConfig &&
        handoffRequest.data.modId === activeConfig.modId &&
        handoffRequest.data.instanceId === activeConfig.instanceId
      ) {
        if (!config.capabilities?.includes("handoff")) {
          post(modHandoffResultSchema.parse({
            type: "vibedesk:handoff-result",
            requestId: handoffRequest.data.requestId,
            instanceId: handoffRequest.data.instanceId,
            modId: handoffRequest.data.modId,
            handoffId: handoffRequest.data.handoff.id,
            ok: false,
            error: {
              code: "handoff_not_supported",
              message: "Mod did not advertise the handoff capability",
            },
          }));
          return;
        }
        void respondToHandoff(handoffRequest.data);
        return;
      }

      const actionResult = deskActionResultSchema.safeParse(message.data);
      if (
        !actionResult.success ||
        !activeConfig ||
        actionResult.data.modId !== activeConfig.modId ||
        actionResult.data.instanceId !== activeConfig.instanceId
      ) {
        return;
      }
      const pending = pendingActions.get(actionResult.data.requestId);
      if (!pending) return;
      pendingActions.delete(actionResult.data.requestId);
      runtime.clearTimeout(pending.timer);
      if (actionResult.data.ok) {
        pending.resolve(actionResult.data.result);
      } else {
        pending.reject(
          new ModHostActionError(
            actionResult.data.status,
            actionResult.data.error.code,
            actionResult.data.error.message,
          ),
        );
      }
    };
    const handshakeTimer = runtime.setTimeout(() => {
      cleanup();
      if (!settled) {
        settled = true;
        reject(new Error("Newma-Desk host handshake timed out"));
      }
    }, timeoutMs);
    runtime.window.addEventListener("message", handleMessage);
    if (config.signal?.aborted) {
      handleAbort();
      return;
    }
    config.signal?.addEventListener("abort", handleAbort, { once: true });
    post(hello);
  });
}
