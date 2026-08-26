export interface VibeDeskConfig {
  gatewayOrigin: string;
  moduleId: string;
  userId: string;
  workspaceId: string;
  theme: "light" | "dark";
}

export interface VibeDeskModSession {
  accessToken: string;
  expiresAt: string;
  instanceId: string;
}

let currentConfig: VibeDeskConfig | null = null;
let currentSession: VibeDeskModSession | null = null;
let bridgeInstanceId: string | null = null;
let contextSummaryProvider: (() => Record<string, unknown>) | null = null;
const waiters = new Set<(config: VibeDeskConfig) => void>();
const sessionWaiters = new Set<(session: VibeDeskModSession) => void>();
const appliedAppearanceVariables = new Set<string>();

export const isVibeDeskEmbedded = window.parent !== window;
document.documentElement.dataset.vibedeskEmbedded = isVibeDeskEmbedded ? "true" : "false";

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
    if (isVibeDeskEmbedded && !currentConfig) return undefined;
    return [
      "newma-desk.mod-cache.v1",
      encodeURIComponent(currentConfig?.userId || "local-user"),
      encodeURIComponent(currentConfig?.workspaceId || "local-workspace"),
      encodeURIComponent(currentConfig?.moduleId || "vibe-trading"),
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
        // Display continuity must not block the page.
      }
    },
  };
}

export function subscribeVibeDeskConfig(listener: (config: VibeDeskConfig) => void) {
  const handler = (event: Event) => listener((event as CustomEvent<VibeDeskConfig>).detail);
  window.addEventListener("vibedesk:config", handler);
  return () => window.removeEventListener("vibedesk:config", handler);
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
      sdkVersion: "vibe-trading-0.1.11",
      capabilities: ["context", "theme"],
    },
    config.gatewayOrigin,
  );
}

function visiblePageContext() {
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
  let structuredSummary: Record<string, unknown> = {};
  try {
    structuredSummary = contextSummaryProvider?.() ?? {};
  } catch {
    structuredSummary = {};
  }
  return {
    view: {
      id: `${currentConfig?.moduleId || "vibe-trading"}:${window.location.pathname}`.slice(0, 128),
      title: (
        document.querySelector("h1")?.textContent?.trim() ||
        document.title ||
        "Vibe Trading"
      ).slice(0, 160),
    },
    visibleBlocks: headings,
    selection: { path: `${window.location.pathname}${window.location.search}` },
    filters: {},
    data: {
      asOf: new Date().toISOString(),
      source: "vibe-trading-rendered-page",
      freshness: "fresh",
      summary: { visibleText, ...structuredSummary },
    },
    actions: [],
    tasks: [],
  };
}

export function registerVibeDeskContextSummary(
  provider: () => Record<string, unknown>,
): () => void {
  contextSummaryProvider = provider;
  return () => {
    if (contextSummaryProvider === provider) contextSummaryProvider = null;
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

function hexToHslChannels(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const match = /^#([\da-f]{6})$/i.exec(value.trim());
  if (!match) return null;
  const hex = match[1];
  const red = Number.parseInt(hex.slice(0, 2), 16) / 255;
  const green = Number.parseInt(hex.slice(2, 4), 16) / 255;
  const blue = Number.parseInt(hex.slice(4, 6), 16) / 255;
  const max = Math.max(red, green, blue);
  const min = Math.min(red, green, blue);
  const delta = max - min;
  const lightness = (max + min) / 2;
  let hue = 0;
  if (delta > 0) {
    if (max === red) hue = 60 * (((green - blue) / delta) % 6);
    else if (max === green) hue = 60 * ((blue - red) / delta + 2);
    else hue = 60 * ((red - green) / delta + 4);
  }
  if (hue < 0) hue += 360;
  const saturation = delta === 0
    ? 0
    : delta / (1 - Math.abs(2 * lightness - 1));
  return `${Math.round(hue)} ${Math.round(saturation * 100)}% ${Math.round(lightness * 100)}%`;
}

function recordValue(record: unknown, key: string): string | undefined {
  if (!record || typeof record !== "object") return undefined;
  const value = (record as Record<string, unknown>)[key];
  return typeof value === "string" ? value : undefined;
}

function applyAppearanceVariables(appearance: unknown) {
  const root = document.documentElement;
  for (const name of appliedAppearanceVariables) root.style.removeProperty(name);
  appliedAppearanceVariables.clear();
  if (!appearance || typeof appearance !== "object") return;

  const set = (name: string, value: string | undefined) => {
    if (!value) return;
    root.style.setProperty(name, value);
    appliedAppearanceVariables.add(name);
  };
  const setHsl = (name: string, value: string | undefined) => {
    const channels = hexToHslChannels(value);
    if (channels) set(name, channels);
  };

  const raw = appearance as Record<string, unknown>;
  const cssVars = raw.cssVars;
  if (cssVars && typeof cssVars === "object") {
    for (const [name, value] of Object.entries(cssVars)) {
      if (
        /^--[a-z0-9-]{2,80}$/.test(name) &&
        typeof value === "string" &&
        value.length <= 200
      ) {
        set(name, value);
      }
    }
  }

  const semantic = raw.semantic;
  setHsl("--background", recordValue(semantic, "bg"));
  setHsl("--foreground", recordValue(semantic, "text"));
  setHsl("--card", recordValue(semantic, "surface"));
  setHsl("--card-foreground", recordValue(semantic, "text"));
  setHsl("--popover", recordValue(semantic, "surfaceRaised"));
  setHsl("--popover-foreground", recordValue(semantic, "text"));
  setHsl("--primary", recordValue(semantic, "accent"));
  setHsl("--primary-foreground", recordValue(semantic, "accentContrast"));
  setHsl("--muted", recordValue(semantic, "surfaceMuted"));
  setHsl("--muted-foreground", recordValue(semantic, "textMuted"));
  setHsl("--border", recordValue(semantic, "border"));
  setHsl("--destructive", recordValue(semantic, "error"));
  setHsl("--destructive-foreground", recordValue(semantic, "surfaceRaised"));
  setHsl("--success", recordValue(semantic, "negative"));
  setHsl("--danger", recordValue(semantic, "positive"));
  setHsl("--warning", recordValue(semantic, "warning"));
  setHsl("--info", recordValue(semantic, "textSoft"));
  set("--financial-positive", recordValue(semantic, "positive"));
  set("--financial-negative", recordValue(semantic, "negative"));

  const charts = raw.charts;
  setHsl("--chart-grid", recordValue(charts, "gridColor"));
  setHsl("--chart-text", recordValue(charts, "textColor"));
  setHsl("--chart-axis", recordValue(charts, "axisColor"));
  set("--chart-tooltip-bg", recordValue(charts, "tooltipBg"));
  set("--chart-tooltip-border", recordValue(charts, "tooltipBorder"));
  set("--chart-tooltip-text", recordValue(charts, "tooltipText"));
  const series = charts && typeof charts === "object"
    ? (charts as Record<string, unknown>).series
    : undefined;
  if (Array.isArray(series)) {
    series.slice(0, 12).forEach((value, index) => {
      if (typeof value === "string") set(`--chart-series-${index + 1}`, value);
    });
    if (typeof series[0] === "string") set("--chart-compare-a", series[0]);
    if (typeof series[1] === "string") set("--chart-compare-b", series[1]);
  }
}

function applyEmbeddedTheme(theme: "light" | "dark", appearance?: unknown) {
  const root = document.documentElement;
  const appearanceMode = recordValue(appearance, "mode");
  const mode = theme;
  const compatibleAppearance = appearanceMode === mode ? appearance : undefined;
  root.dataset.theme = mode;
  root.dataset.vibedeskTheme = mode;
  root.classList.toggle("dark", mode === "dark");
  root.classList.toggle("light", mode === "light");
  root.style.colorScheme = mode;
  document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
    ?.setAttribute("content", mode === "dark" ? "#0f1714" : "#f4efe3");
  applyAppearanceVariables(compatibleAppearance);
  window.dispatchEvent(
    new CustomEvent("vibedesk:theme", { detail: mode }),
  );
  window.dispatchEvent(
    new CustomEvent("newma:themechange", {
      detail: {
        mode,
        ...(compatibleAppearance ? { appearance: compatibleAppearance } : {}),
      },
    }),
  );
}

if (isVibeDeskEmbedded) {
  window.addEventListener("message", (event) => {
    if (event.source !== window.parent) return;
    const data = event.data;
    if (!data || typeof data !== "object") return;
    if (data.type === "vibedesk:init") {
      if (
        !currentConfig ||
        event.origin !== currentConfig.gatewayOrigin ||
        data.modId !== currentConfig.moduleId ||
        typeof data.instanceId !== "string"
      ) return;
      const initTheme = data.environment?.theme === "dark" ? "dark" : "light";
      currentConfig.theme = initTheme;
      applyEmbeddedTheme(initTheme, data.appearance);
      if (
        !data.session ||
        typeof data.session.accessToken !== "string" ||
        typeof data.session.expiresAt !== "string"
      ) return;
      bridgeInstanceId = data.instanceId;
      currentSession = {
        accessToken: data.session.accessToken,
        expiresAt: data.session.expiresAt,
        instanceId: data.instanceId,
      };
      for (const resolve of sessionWaiters) resolve(currentSession);
      sessionWaiters.clear();
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
      window.parent.postMessage(
        {
          type: "vibedesk:context",
          requestId: data.requestId,
          instanceId: bridgeInstanceId,
          modId: currentConfig.moduleId,
          context: visiblePageContext(),
        },
        currentConfig.gatewayOrigin,
      );
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
    currentConfig = {
      gatewayOrigin,
      moduleId: data.moduleId,
      userId: data.userId,
      workspaceId: typeof data.workspaceId === "string" ? data.workspaceId : "local-workspace",
      theme,
    };
    currentSession = null;
    bridgeInstanceId = null;
    applyEmbeddedTheme(theme, data.appearance);
    announceContextBridge(currentConfig);
    window.dispatchEvent(new CustomEvent("vibedesk:config", { detail: currentConfig }));
    for (const resolve of waiters) resolve(currentConfig);
    waiters.clear();
  });
  requestVibeDeskConfig();
}

export async function waitForVibeDeskConfig(
  timeoutMs = 2_000,
): Promise<VibeDeskConfig | null> {
  if (currentConfig) return currentConfig;
  if (!isVibeDeskEmbedded) return null;
  return new Promise((resolve) => {
    const resolver = (config: VibeDeskConfig) => {
      window.clearTimeout(timer);
      waiters.delete(resolver);
      resolve(config);
    };
    const timer = window.setTimeout(() => {
      waiters.delete(resolver);
      resolve(null);
    }, timeoutMs);
    waiters.add(resolver);
    requestVibeDeskConfig();
  });
}

export function getVibeDeskModSession(): VibeDeskModSession | null {
  if (!currentSession) return null;
  if (Date.parse(currentSession.expiresAt) <= Date.now() + 5_000) {
    currentSession = null;
    return null;
  }
  return currentSession;
}

export async function waitForVibeDeskModSession(
  timeoutMs = 3_000,
): Promise<VibeDeskModSession | null> {
  const current = getVibeDeskModSession();
  if (current) return current;
  if (!isVibeDeskEmbedded) return null;
  return new Promise((resolve) => {
    const resolver = (session: VibeDeskModSession) => {
      window.clearTimeout(timer);
      sessionWaiters.delete(resolver);
      resolve(session);
    };
    const timer = window.setTimeout(() => {
      sessionWaiters.delete(resolver);
      resolve(null);
    }, timeoutMs);
    sessionWaiters.add(resolver);
    requestVibeDeskConfig();
  });
}

export async function openVibeDeskCopilot(): Promise<boolean> {
  if (!isVibeDeskEmbedded) return false;
  const config = await waitForVibeDeskConfig();
  if (!config) return false;
  window.parent.postMessage({ type: "vibedesk:copilot-open" }, config.gatewayOrigin);
  return true;
}
