export interface VibeDeskConfig {
  gatewayOrigin: string;
  apiOrigin: string;
  moduleId: string;
  userId: string;
  workspaceId: string;
  theme: "light" | "dark";
  appearance?: VibeDeskAppearance;
  instanceId?: string;
  accessToken?: string;
  storageGateway?: string;
  permissions?: string[];
}

export interface VibeDeskAppearance {
  contractVersion: "1.0";
  mode: "light" | "dark";
  cssVars: Record<string, string>;
  semantic?: Record<string, unknown>;
  charts?: Record<string, unknown>;
}

export interface VibeDeskThemeChangeDetail {
  mode: "light" | "dark";
  appearance?: VibeDeskAppearance;
}

interface VibeDeskSnapshot<T> {
  schemaVersion: number;
  updatedAt: string;
  value: T;
}

export function createVibeDeskSnapshotCache<T>(
  resourceKey: string,
  schemaVersion = 1,
  maxBytes = 512 * 1024,
) {
  const key = () => {
    const config = getVibeDeskConfig();
    if (isVibeDeskEmbedded && !config) return undefined;
    return [
      "newma-desk.mod-cache.v1",
      encodeURIComponent(config?.userId || "local-user"),
      encodeURIComponent(config?.workspaceId || "local-workspace"),
      encodeURIComponent(config?.moduleId || "vibe-research"),
      encodeURIComponent(resourceKey),
    ].join(".");
  };
  return {
    read(): VibeDeskSnapshot<T> | undefined {
      try {
        const storageKey = key();
        if (!storageKey) return undefined;
        const raw = window.localStorage.getItem(storageKey);
        if (!raw) return undefined;
        const parsed = JSON.parse(raw) as VibeDeskSnapshot<T>;
        if (parsed.schemaVersion !== schemaVersion || typeof parsed.updatedAt !== "string") {
          window.localStorage.removeItem(storageKey);
          return undefined;
        }
        return parsed;
      } catch {
        return undefined;
      }
    },
    write(value: T, updatedAt = new Date().toISOString()) {
      try {
        const storageKey = key();
        if (!storageKey) return;
        const serialized = JSON.stringify({ schemaVersion, updatedAt, value });
        if (new TextEncoder().encode(serialized).byteLength > maxBytes) return;
        window.localStorage.setItem(storageKey, serialized);
      } catch {
        // A cache write must never block the page.
      }
    },
  };
}

export function subscribeVibeDeskConfig(listener: (config: VibeDeskConfig) => void) {
  const handler = (event: Event) => {
    listener((event as CustomEvent<VibeDeskConfig>).detail);
  };
  window.addEventListener("vibedesk:config", handler);
  return () => window.removeEventListener("vibedesk:config", handler);
}

export interface VibeDeskPageContext {
  view: { id: string; title: string };
  visibleBlocks: Array<{ id: string; type: string; title?: string }>;
  selection: Record<string, unknown>;
  filters: Record<string, unknown>;
  data: {
    asOf?: string;
    source?: string;
    freshness?: "live" | "fresh" | "stale" | "unknown";
    summary?: Record<string, unknown>;
  };
  actions: Array<{
    id: string;
    label?: string;
    available?: boolean;
    inputSchema?: unknown;
  }>;
  tasks: Array<{ id: string; status: string; actionId?: string }>;
  wiki?: VibeDeskWikiPageContext;
}

export interface VibeDeskWikiSubject {
  type: "security" | "etf" | "fund" | "company" | "industry" | "concept" | "event" | "topic";
  canonicalId: string;
  displayName: string;
  market?: "CN" | "HK" | "US";
  symbol?: string;
  assetType?: "stock" | "etf" | "fund" | "index" | "other";
}

export interface VibeDeskWikiPageContext {
  primarySubject: VibeDeskWikiSubject;
  relatedSubjects: VibeDeskWikiSubject[];
  conceptIds: string[];
  intent: string;
  timeframe?: string;
  snapshotId?: string;
}

export interface VibeDeskWikiHandoff {
  id: string;
  targetModId: string;
  subject: VibeDeskWikiSubject;
  relatedSubjects: VibeDeskWikiSubject[];
  conceptIds: string[];
  intent: string;
  timeframe?: string;
  parameters: Record<string, string | number | boolean>;
}

export interface VibeDeskEvent {
  version: "1.0";
  event: string;
  source: string;
  target?: string;
  traceId: string;
  payload: Record<string, unknown>;
}

type ContextProvider = () => VibeDeskPageContext | Promise<VibeDeskPageContext>;
type UiActionHandler = (
  actionId: string,
  input: Record<string, unknown>,
) => unknown | Promise<unknown>;
type HandoffHandler = (handoff: VibeDeskWikiHandoff) => unknown | Promise<unknown>;

let currentConfig: VibeDeskConfig | null = null;
let bridgeInstanceId: string | null = null;
let contextProvider: ContextProvider | null = null;
let uiActionHandler: UiActionHandler | null = null;
let handoffHandler: HandoffHandler | null = null;
const queuedHandoffs: Array<Record<string, unknown>> = [];
const waiters = new Set<(config: VibeDeskConfig) => void>();
const eventListeners = new Set<(event: VibeDeskEvent) => void>();
const latestEvents = new Map<string, VibeDeskEvent>();
const appliedAppearanceVariables = new Set<string>();
let embeddedThemeFallbackTimer: number | undefined;

export const isVibeDeskEmbedded = window.parent !== window;
document.documentElement.dataset.vibedeskEmbedded = isVibeDeskEmbedded ? "true" : "false";

function requestId(prefix: string) {
  return globalThis.crypto?.randomUUID?.() ??
    `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function requestVibeDeskConfig() {
  if (!isVibeDeskEmbedded) return;
  // This message contains no user data. The Shell validates the exact iframe
  // window and Mod origin before it responds with configuration.
  window.parent.postMessage({ type: "vibedesk:ready" }, "*");
}

function announceContextBridge(config: VibeDeskConfig) {
  window.parent.postMessage(
    {
      type: "vibedesk:hello",
      modId: config.moduleId,
      protocolVersions: ["1.0"],
      sdkVersion: "vibe-research-0.1.3",
      capabilities: ["events", "data", "context", "theme", "handoff"],
    },
    config.gatewayOrigin,
  );
}

function visiblePageContext(): VibeDeskPageContext {
  const headings = Array.from(
    document.querySelectorAll<HTMLElement>("h1, h2, h3"),
  )
    .map((heading, index) => ({
      id: (heading.id || `heading-${index + 1}`).slice(0, 128),
      type: heading.tagName.toLowerCase(),
      title: heading.innerText.trim().slice(0, 160),
    }))
    .filter((heading) => heading.title)
    .slice(0, 80);
  const visibleText = document.body.innerText
    .replace(/\n{3,}/g, "\n\n")
    .trim()
    .slice(0, 40_000);
  return {
    view: {
      id: `${currentConfig?.moduleId || "vibe-research"}:${window.location.pathname}`.slice(0, 128),
      title: (
        document.querySelector("h1")?.textContent?.trim() ||
        document.title ||
        "Vibe Research"
      ).slice(0, 160),
    },
    visibleBlocks: headings,
    selection: { path: `${window.location.pathname}${window.location.search}` },
    filters: {},
    data: {
      asOf: new Date().toISOString(),
      source: "vibe-research-rendered-page",
      freshness: "fresh",
      summary: { visibleText },
    },
    actions: [],
    tasks: [],
  };
}

function safeOrigin(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const parsed = new URL(value);
    if (!["http:", "https:"].includes(parsed.protocol)) return null;
    if (parsed.username || parsed.password || parsed.search || parsed.hash) return null;
    if (parsed.pathname !== "/") return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

function originFromUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.origin : null;
  } catch {
    return null;
  }
}

function gatewayUrl(value: unknown, expectedOrigin: string): string | undefined {
  if (typeof value !== "string") return undefined;
  try {
    const parsed = new URL(value);
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password ||
      parsed.origin !== expectedOrigin
    ) return undefined;
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return undefined;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function sanitizeAppearance(value: unknown): VibeDeskAppearance | undefined {
  if (!isRecord(value) || value.contractVersion !== "1.0") return undefined;
  if (value.mode !== "light" && value.mode !== "dark") return undefined;
  if (!isRecord(value.cssVars)) return undefined;

  const cssVars: Record<string, string> = {};
  for (const [name, cssValue] of Object.entries(value.cssVars).slice(0, 128)) {
    if (!/^--[a-z0-9-]{2,80}$/.test(name)) continue;
    if (typeof cssValue !== "string" || cssValue.length > 200) continue;
    cssVars[name] = cssValue;
  }

  return {
    contractVersion: "1.0",
    mode: value.mode,
    cssVars,
    ...(isRecord(value.semantic) ? { semantic: value.semantic } : {}),
    ...(isRecord(value.charts) ? { charts: value.charts } : {}),
  };
}

function applyEmbeddedTheme(
  theme: "light" | "dark",
  appearance?: VibeDeskAppearance,
) {
  const mode = theme;
  const compatibleAppearance = appearance?.mode === mode
    ? appearance
    : undefined;
  const nextVariables = new Set(
    Object.keys(compatibleAppearance?.cssVars ?? {}),
  );
  for (const name of appliedAppearanceVariables) {
    if (!nextVariables.has(name)) document.documentElement.style.removeProperty(name);
  }
  for (const [name, value] of Object.entries(compatibleAppearance?.cssVars ?? {})) {
    document.documentElement.style.setProperty(name, value);
  }
  appliedAppearanceVariables.clear();
  for (const name of nextVariables) appliedAppearanceVariables.add(name);

  document.documentElement.dataset.vibedeskTheme = mode;
  document.documentElement.dataset.theme = mode;
  document.documentElement.classList.toggle("dark", mode === "dark");
  document.documentElement.classList.toggle("light", mode === "light");
  document.documentElement.style.colorScheme = mode;
  delete document.documentElement.dataset.newmaThemePending;
  if (embeddedThemeFallbackTimer !== undefined) {
    window.clearTimeout(embeddedThemeFallbackTimer);
    embeddedThemeFallbackTimer = undefined;
  }
  document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
    ?.setAttribute("content", mode === "dark" ? "#0f1714" : "#f4efe3");
  const detail: VibeDeskThemeChangeDetail = {
    mode,
    ...(compatibleAppearance ? { appearance: compatibleAppearance } : {}),
  };
  window.dispatchEvent(new CustomEvent("newma:themechange", { detail }));
  window.dispatchEvent(
    new CustomEvent("vibedesk:theme", { detail: mode }),
  );
}

function notifyConfig(config: VibeDeskConfig) {
  for (const resolve of waiters) resolve(config);
  waiters.clear();
  window.dispatchEvent(
    new CustomEvent("vibedesk:config", { detail: config }),
  );
}

function isVibeDeskEvent(value: unknown): value is VibeDeskEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Record<string, unknown>;
  return (
    event.version === "1.0" &&
    typeof event.event === "string" &&
    /^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$/.test(event.event) &&
    typeof event.source === "string" &&
    typeof event.traceId === "string" &&
    typeof event.payload === "object" &&
    event.payload !== null &&
    !Array.isArray(event.payload)
  );
}

async function resolvePageContext() {
  if (!contextProvider) return visiblePageContext();
  try {
    return await contextProvider();
  } catch {
    return visiblePageContext();
  }
}

async function postPageContext(linkedRequestId?: string) {
  if (!currentConfig || !bridgeInstanceId) return false;
  window.parent.postMessage(
    {
      type: "vibedesk:context",
      requestId: linkedRequestId || requestId("context"),
      instanceId: bridgeInstanceId,
      modId: currentConfig.moduleId,
      context: await resolvePageContext(),
    },
    currentConfig.gatewayOrigin,
  );
  return true;
}

function handleHandoffRequest(data: Record<string, unknown>, origin: string) {
  const rawHandoff = data.handoff;
  if (
    !currentConfig ||
    !bridgeInstanceId ||
    origin !== currentConfig.gatewayOrigin ||
    data.modId !== currentConfig.moduleId ||
    data.instanceId !== bridgeInstanceId ||
    typeof data.requestId !== "string" ||
    !isRecord(rawHandoff) ||
    rawHandoff.targetModId !== currentConfig.moduleId ||
    typeof rawHandoff.id !== "string"
  ) return;
  if (!handoffHandler) {
    queuedHandoffs.push(data);
    return;
  }
  const config = currentConfig;
  const instanceId = bridgeInstanceId;
  const handoff = rawHandoff as unknown as VibeDeskWikiHandoff;
  const respond = (payload: Record<string, unknown>) => window.parent.postMessage(
    {
      type: "vibedesk:handoff-result",
      requestId: data.requestId,
      instanceId,
      modId: config.moduleId,
      handoffId: handoff.id,
      ...payload,
    },
    config.gatewayOrigin,
  );
  void Promise.resolve(handoffHandler(handoff)).then(
    (result) => respond({ ok: true, result: result ?? {} }),
    (reason: unknown) => respond({
      ok: false,
      error: {
        code: "handoff_failed",
        message: reason instanceof Error ? reason.message : "Wiki 交接失败",
      },
    }),
  );
}

if (isVibeDeskEmbedded) {
  embeddedThemeFallbackTimer = window.setTimeout(() => {
    applyEmbeddedTheme("light");
  }, 1_500);
  window.addEventListener("message", (event) => {
    if (event.source !== window.parent) return;
    const data = event.data;
    if (!data || typeof data !== "object") return;

    if (isVibeDeskEvent(data)) {
      if (!currentConfig || event.origin !== currentConfig.gatewayOrigin) return;
      latestEvents.set(data.event, data);
      for (const listener of eventListeners) listener(data);
      return;
    }

    if (data.type === "vibedesk:init") {
      if (
        !currentConfig ||
        event.origin !== currentConfig.gatewayOrigin ||
        data.modId !== currentConfig.moduleId ||
        typeof data.instanceId !== "string" ||
        typeof data.user?.id !== "string" ||
        typeof data.workspace?.id !== "string"
      ) return;
      const apiOrigin = originFromUrl(data.gateways?.data);
      const gatewayOrigin = safeOrigin(event.origin);
      if (!apiOrigin || !gatewayOrigin) return;
      const storageGateway = gatewayUrl(data.gateways?.storage, gatewayOrigin);
      const accessToken = typeof data.session?.accessToken === "string"
        ? data.session.accessToken
        : undefined;
      const permissions = Array.isArray(data.grants?.permissions)
        ? data.grants.permissions.filter(
            (permission: unknown): permission is string => typeof permission === "string",
          )
        : [];
      const theme = data.environment?.theme === "dark" ? "dark" : "light";
      const sanitizedAppearance = sanitizeAppearance(data.appearance);
      const appearance = sanitizedAppearance?.mode === theme
        ? sanitizedAppearance
        : undefined;
      bridgeInstanceId = data.instanceId;
      currentConfig = {
        ...currentConfig,
        gatewayOrigin,
        apiOrigin,
        userId: data.user.id,
        workspaceId: data.workspace.id,
        theme,
        appearance,
        instanceId: data.instanceId,
        accessToken,
        storageGateway,
        permissions,
      };
      applyEmbeddedTheme(theme, appearance);
      notifyConfig(currentConfig);
      window.parent.postMessage(
        {
          type: "vibedesk:ack",
          protocolVersion: "1.0",
          instanceId: bridgeInstanceId,
          modId: currentConfig.moduleId,
        },
        currentConfig.gatewayOrigin,
      );
      return;
    }
    if (data.type === "vibedesk:context-request") {
      if (
        !currentConfig ||
        !bridgeInstanceId ||
        event.origin !== currentConfig.gatewayOrigin ||
        data.modId !== currentConfig.moduleId ||
        data.instanceId !== bridgeInstanceId ||
        typeof data.requestId !== "string"
      ) return;
      void postPageContext(data.requestId);
      return;
    }
    if (data.type === "vibedesk:ui-action-request") {
      if (
        !currentConfig ||
        !bridgeInstanceId ||
        event.origin !== currentConfig.gatewayOrigin ||
        data.modId !== currentConfig.moduleId ||
        data.instanceId !== bridgeInstanceId ||
        typeof data.requestId !== "string" ||
        typeof data.actionId !== "string" ||
        !isRecord(data.input)
      ) return;
      const config = currentConfig;
      const instanceId = bridgeInstanceId;
      const respond = (payload: Record<string, unknown>) => window.parent.postMessage(
        {
          type: "vibedesk:ui-action-result",
          requestId: data.requestId,
          instanceId,
          modId: config.moduleId,
          actionId: data.actionId,
          ...payload,
        },
        config.gatewayOrigin,
      );
      if (!uiActionHandler) {
        respond({
          ok: false,
          error: { code: "handler_unavailable", message: "页面动作暂不可用" },
        });
        return;
      }
      void Promise.resolve(uiActionHandler(data.actionId, data.input)).then(
        (result) => respond({ ok: true, result: result ?? {} }),
        (reason: unknown) => respond({
          ok: false,
          error: {
            code: "action_failed",
            message: reason instanceof Error ? reason.message : "页面动作执行失败",
          },
        }),
      );
      return;
    }
    if (data.type === "vibedesk:handoff") {
      handleHandoffRequest(data, event.origin);
      return;
    }
    if (data.type !== "vibedesk:config") return;
    const gatewayOrigin = safeOrigin(data.gatewayOrigin);
    if (
      !gatewayOrigin ||
      typeof data.moduleId !== "string" ||
      typeof data.userId !== "string"
    ) {
      return;
    }
    const theme = data.theme === "dark" ? "dark" : "light";
    const sanitizedAppearance = sanitizeAppearance(data.appearance);
    const appearance = sanitizedAppearance?.mode === theme
      ? sanitizedAppearance
      : undefined;
    currentConfig = {
      gatewayOrigin,
      apiOrigin: gatewayOrigin,
      moduleId: data.moduleId,
      userId: data.userId,
      workspaceId:
        typeof data.workspaceId === "string" ? data.workspaceId : "local-workspace",
      theme,
      appearance,
    };
    applyEmbeddedTheme(theme, appearance);
    announceContextBridge(currentConfig);
    notifyConfig(currentConfig);
  });
  requestVibeDeskConfig();
}

export function getVibeDeskConfig(): VibeDeskConfig | null {
  return currentConfig;
}

export async function waitForVibeDeskConfig(
  timeoutMs = 2_000,
): Promise<VibeDeskConfig | null> {
  if (currentConfig) return currentConfig;
  if (!isVibeDeskEmbedded) return null;
  return new Promise((resolve) => {
    const finish = (config: VibeDeskConfig | null) => {
      window.clearTimeout(timer);
      waiters.delete(resolver);
      resolve(config);
    };
    const resolver = (config: VibeDeskConfig) => finish(config);
    const timer = window.setTimeout(() => finish(null), timeoutMs);
    waiters.add(resolver);
    requestVibeDeskConfig();
  });
}

export function registerVibeDeskContextProvider(provider: ContextProvider) {
  contextProvider = provider;
  return () => {
    if (contextProvider === provider) contextProvider = null;
  };
}

export function registerVibeDeskUiActionHandler(handler: UiActionHandler) {
  uiActionHandler = handler;
  return () => {
    if (uiActionHandler === handler) uiActionHandler = null;
  };
}

export function registerVibeDeskHandoffHandler(handler: HandoffHandler) {
  handoffHandler = handler;
  for (const handoff of queuedHandoffs.splice(0)) {
    handleHandoffRequest(handoff, currentConfig?.gatewayOrigin ?? "");
  }
  return () => {
    if (handoffHandler === handler) handoffHandler = null;
  };
}

export function publishVibeDeskContext() {
  return postPageContext();
}

export function emitVibeDeskEvent(
  event: string,
  payload: Record<string, unknown>,
  target?: string,
) {
  if (
    !currentConfig ||
    !/^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$/.test(event)
  ) return false;
  window.parent.postMessage(
    {
      version: "1.0",
      event,
      source: currentConfig.moduleId,
      ...(target ? { target } : {}),
      traceId: requestId("event"),
      payload,
    },
    currentConfig.gatewayOrigin,
  );
  return true;
}

export function subscribeVibeDeskEvent(
  listener: (event: VibeDeskEvent) => void,
) {
  eventListeners.add(listener);
  for (const event of latestEvents.values()) {
    queueMicrotask(() => {
      if (eventListeners.has(listener)) listener(event);
    });
  }
  return () => eventListeners.delete(listener);
}
