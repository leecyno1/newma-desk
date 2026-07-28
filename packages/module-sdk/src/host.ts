import {
  deskActionResultSchema,
  deskContextRequestSchema,
  deskInitSchema,
  deskUiActionRequestSchema,
  modActionRequestSchema,
  modContextSchema,
  modHelloSchema,
  modUiActionResultSchema,
  modPageContextSchema,
  type DeskContextRequest,
  type DeskInit,
  type ModPageContext,
} from "@newma-desk/contracts";

export interface ModHostConfig {
  modId: string;
  parentOrigin: string;
  sdkVersion?: string;
  capabilities?: Array<
    "events" | "actions" | "agent" | "model" | "data" | "context" | "theme"
  >;
  timeoutMs?: number;
  requestTimeoutMs?: number;
  signal?: AbortSignal;
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

export type ModHostConnection =
  | { embedded: false; close(): void }
  | {
      embedded: true;
      config: DeskInit;
      subscribe(handler: (config: DeskInit) => void): () => void;
      setContextProvider(provider: ModContextProvider): () => void;
      setUiActionHandler(handler: ModUiActionHandler): () => void;
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

export function connectModHost(
  config: ModHostConfig,
  runtime: ModHostRuntime = defaultRuntime(),
): Promise<ModHostConnection> {
  const parentOrigin = exactHttpOrigin(config.parentOrigin);
  const timeoutMs = config.timeoutMs ?? 5_000;
  const requestTimeoutMs = config.requestTimeoutMs ?? 30_000;
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
    return Promise.resolve({ embedded: false, close() {} });
  }

  return new Promise((resolve, reject) => {
    let settled = false;
    let closed = false;
    let activeConfig: DeskInit | undefined;
    let contextProvider: ModContextProvider | undefined;
    let uiActionHandler: ModUiActionHandler | undefined;
    const queuedContextRequests: DeskContextRequest[] = [];
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
      uiActionHandler = undefined;
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
