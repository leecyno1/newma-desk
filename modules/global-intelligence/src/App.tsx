import { Globe2, Radio, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import {
  connectModHost,
  type ModHostConnection,
} from "@newma-desk/mod-sdk";

import { GlobalIntelligenceDashboard } from "./Dashboard";
import { GlobalTopicDashboard, type GlobalTopicId } from "./TopicDashboard";
import {
  createGlobalIntelDataSource,
  type GlobalIntelDataSource,
} from "./data";

type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;

function parentOrigin() {
  const configured = import.meta.env.VITE_PARENT_ORIGIN?.trim();
  if (configured) return configured;
  if (document.referrer) {
    try {
      return new URL(document.referrer).origin;
    } catch {
      // Continue with the current origin.
    }
  }
  return window.location.origin;
}

function initialTheme(): "light" | "dark" {
  const value = document.documentElement.dataset.theme;
  if (value === "light" || value === "dark") return value;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function buildGlobalIntelligenceContext(
  state: Record<string, unknown>,
): ModPageContext {
  return {
    view: { id: "global-situation", title: "全球情报" },
    visibleBlocks: [
      { id: "global-intelligence-map", type: "geospatial-map", title: "全球综合态势" },
      { id: "global-intelligence-events", type: "event-stream", title: "实时事件流" },
      { id: "global-intelligence-sources", type: "source-health", title: "来源健康" },
      { id: "global-intelligence-dossier", type: "event-detail", title: "事件详情" },
    ],
    selection: {},
    filters: state.filters && typeof state.filters === "object"
      ? state.filters as Record<string, unknown>
      : {},
    data: {
      source: "world-intel-mcp",
      freshness: state.streamStatus === "live" ? "live" : "unknown",
      ...(typeof state.lastUpdate === "string" ? { asOf: state.lastUpdate } : {}),
      summary: state,
    },
    actions: [
      { id: "global-intel.refresh", label: "刷新全球情报", available: true, inputSchema: { type: "object", additionalProperties: false } },
      { id: "workspace.save-layout", label: "保存当前视图", available: true, inputSchema: { type: "object", properties: { name: { type: "string", maxLength: 80 } }, additionalProperties: false } },
    ],
    tasks: [],
  };
}

export function GlobalIntelligenceApp({
  hostConnection: providedHostConnection,
  dataSource: providedDataSource,
  gatewayBaseUrl = window.location.origin,
  embedded = false,
  topicId: providedTopicId,
}: {
  hostConnection?: EmbeddedHost;
  dataSource?: GlobalIntelDataSource;
  gatewayBaseUrl?: string;
  embedded?: boolean;
  topicId?: GlobalTopicId;
}) {
  const topicId = providedTopicId ?? (new URLSearchParams(window.location.search).get("topic") as GlobalTopicId | null);
  const runtimeModId = topicId === "fed-rates" ? "fed-rates" : topicId === "hormuz" ? "hormuz-conflict" : topicId === "us-china-trade" ? "us-china-trade" : "global-situation";
  const [hostConnection, setHostConnection] = useState(providedHostConnection);
  const [gatewayOrigin, setGatewayOrigin] = useState(gatewayBaseUrl);
  const [theme, setTheme] = useState<"light" | "dark">(
    providedHostConnection?.config.environment.theme ?? initialTheme(),
  );
  const [cacheIdentity, setCacheIdentity] = useState(() => providedHostConnection
    ? {
        userId: providedHostConnection.config.user.id,
        workspaceId: providedHostConnection.config.workspace.id,
      }
    : embedded
      ? undefined
      : { userId: "local-user", workspaceId: "local-workspace" });
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [dashboardState, setDashboardState] = useState<Record<string, unknown>>({});
  const contextRef = useRef(buildGlobalIntelligenceContext(dashboardState));
  contextRef.current = buildGlobalIntelligenceContext(dashboardState);

  const dataSource = useMemo(
    () => providedDataSource ?? createGlobalIntelDataSource({
      baseUrl: gatewayOrigin,
      fetch: window.fetch.bind(window),
    }),
    [gatewayOrigin, providedDataSource],
  );

  useEffect(() => {
    const topicTitle = topicId === "fed-rates" ? "联储加息" : topicId === "hormuz" ? "美伊战争" : topicId === "us-china-trade" ? "中美贸易" : "全球情报";
    document.title = topicTitle + " · Newma-Desk";
  }, [topicId]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  useEffect(() => {
    if (providedHostConnection || embedded) return;
    const controller = new AbortController();
    let close: () => void = () => undefined;
    let unsubscribe: () => void = () => undefined;
    let removeContextProvider: () => void = () => undefined;
    void connectModHost({
      modId: runtimeModId,
      parentOrigin: parentOrigin(),
      sdkVersion: "0.1.0",
      capabilities: ["actions", "data", "context", "theme"],
      signal: controller.signal,
    }).then((connection) => {
      close = connection.close;
      if (!connection.embedded) return;
      setHostConnection(connection);
      setGatewayOrigin(new URL(connection.config.gateways.data).origin);
      setTheme(connection.config.environment.theme);
      setCacheIdentity({
        userId: connection.config.user.id,
        workspaceId: connection.config.workspace.id,
      });
      unsubscribe = connection.subscribe((config) => {
        setGatewayOrigin(new URL(config.gateways.data).origin);
        setTheme(config.environment.theme);
        setCacheIdentity({ userId: config.user.id, workspaceId: config.workspace.id });
      });
      removeContextProvider = connection.setContextProvider(() => contextRef.current);
    }).catch(() => undefined);
    return () => {
      controller.abort();
      unsubscribe();
      removeContextProvider();
      close();
    };
  }, [embedded, providedHostConnection, runtimeModId]);

  useEffect(() => {
    if (!providedHostConnection) return;
    setTheme(providedHostConnection.config.environment.theme);
    setCacheIdentity({
      userId: providedHostConnection.config.user.id,
      workspaceId: providedHostConnection.config.workspace.id,
    });
    return providedHostConnection.subscribe((config) => {
      setGatewayOrigin(new URL(config.gateways.data).origin);
      setTheme(config.environment.theme);
      setCacheIdentity({ userId: config.user.id, workspaceId: config.workspace.id });
    });
  }, [providedHostConnection]);

  useEffect(() => hostConnection?.setContextProvider(() => contextRef.current), [hostConnection]);

  useEffect(() => {
    hostConnection?.publishContext(contextRef.current);
  }, [dashboardState, hostConnection]);

  const handleUiAction = useCallback((actionId: string, input: Record<string, unknown>) => {
    if (actionId === "global-intel.refresh") {
      setRefreshNonce((value) => value + 1);
      return { refreshed: true };
    }
    if (actionId === "workspace.save-layout") {
      const name = typeof input.name === "string" && input.name.trim()
        ? input.name.trim().slice(0, 80)
        : "全球情报视图";
      const record = { id: crypto.randomUUID(), name, savedAt: new Date().toISOString(), state: dashboardState };
      const key = "newma-desk.global-intelligence.layouts.v1";
      const current = JSON.parse(localStorage.getItem(key) || "[]") as unknown;
      const layouts = Array.isArray(current) ? current : [];
      localStorage.setItem(key, JSON.stringify([record, ...layouts].slice(0, 20)));
      return { layout: record };
    }
    throw new Error(`全球情报不支持动作 ${actionId}`);
  }, [dashboardState]);

  useEffect(() => hostConnection?.setUiActionHandler(handleUiAction), [handleUiAction, hostConnection]);

  return (
    <main className="global-intelligence-root" data-embedded={embedded}>
      {!embedded ? (
        <header className="global-intelligence-topbar">
          <div className="global-intelligence-identity">
            <i><Globe2 size={18} /></i>
            <span><strong>全球情报</strong><small>GLOBAL INTELLIGENCE OPERATIONS</small></span>
          </div>
          <div className="global-intelligence-runtime"><Radio size={13} />World Intelligence MCP · 实时数据平面</div>
          <button type="button" onClick={() => setRefreshNonce((value) => value + 1)}><RefreshCw size={14} />刷新情报</button>
        </header>
      ) : null}
      {topicId ? (
        <GlobalTopicDashboard topicId={topicId} refreshNonce={refreshNonce} embedded={embedded} onContextChange={setDashboardState} />
      ) : <GlobalIntelligenceDashboard
        key={cacheIdentity ? `${cacheIdentity.userId}:${cacheIdentity.workspaceId}` : "pending-host"}
        dataSource={dataSource}
        theme={theme}
        refreshNonce={refreshNonce}
        cacheIdentity={cacheIdentity}
        onRefresh={() => setRefreshNonce((value) => value + 1)}
        onContextChange={setDashboardState}
      />}
      {!embedded ? (
        <footer className="global-intelligence-statusbar">
          <span><i />GLOBAL-SITUATION</span>
          <span>情报数据合同：newma-desk.global-intelligence.v1</span>
          <span>MAPLIBRE GL · DECK.GL</span>
        </footer>
      ) : null}
    </main>
  );
}
