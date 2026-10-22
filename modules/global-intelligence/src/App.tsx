import { Globe2, Radio, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import {
  connectModHost,
  type ModHostConnection,
} from "@newma-desk/mod-sdk";

import { GlobalIntelligenceDashboard } from "./Dashboard";
import { GlobalTopicDashboard, type GlobalTopicId } from "./TopicDashboard";
import { buildGlobalTopicContext, GLOBAL_TOPICS } from "./topicContext";
import { globalRequest } from "./request";
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
  topicId?: GlobalTopicId,
): ModPageContext {
  if (topicId) return buildGlobalTopicContext(topicId, state);
  const selectedEvent = state.selectedEvent && typeof state.selectedEvent === "object"
    ? state.selectedEvent as Record<string, unknown> : undefined;
  const selectedPoint = state.selectedPoint && typeof state.selectedPoint === "object" ? state.selectedPoint as Record<string, unknown> : undefined;
  const selectedRoute = state.selectedRoute && typeof state.selectedRoute === "object" ? state.selectedRoute as Record<string, unknown> : undefined;
  const selectedRecord = selectedEvent ?? selectedPoint;
  const presentation = state.presentation as Record<string, boolean> | undefined;
  const asOf = selectedRecord ? selectedRecord.collectedAt : selectedRoute ? undefined : state.lastUpdate;
  const visibleEvents = Array.isArray(state.events) ? state.events as Array<Record<string, unknown>> : [];
  const freshness = selectedRecord ? selectedRecord.sourceFreshness ?? "unknown" : selectedRoute ? "unknown"
    : (visibleEvents.some((event) => event.sourceFreshness === "stale") ? "stale"
      : visibleEvents.length && visibleEvents.every((event) => event.sourceFreshness === "fresh") ? "fresh" : "unknown");
  return {
    view: { id: "global-situation", title: "全球情报" },
    visibleBlocks: [
      { id: "global-intelligence-map", type: "geospatial-map", title: "全球综合态势" },
      ...(!presentation?.mapExpanded ? [{ id: "global-intelligence-events", type: "event-stream", title: "实时事件流" }] : []),
      ...(presentation?.healthPanelOpen ? [{ id: "global-intelligence-sources", type: "source-health", title: "来源健康" }] : []),
      ...(selectedRecord || selectedRoute ? [{ id: "global-intelligence-dossier", type: "event-detail", title: "事件详情" }] : []),
      ...(state.investmentResearch ? [{ id: "global-intelligence-investment", type: "transmission-chain", title: "投资传导研究" }] : []),
    ],
    selection: { ...(selectedEvent ? { event: selectedEvent } : {}), ...(selectedPoint ? { point: selectedPoint } : {}), ...(selectedRoute ? { route: selectedRoute } : {}) },
    filters: state.filters && typeof state.filters === "object"
      ? state.filters as Record<string, unknown>
      : {},
    data: {
      source: "world-intel-mcp",
      freshness: freshness === "stale" || freshness === "fresh" ? freshness : "unknown",
      ...(typeof asOf === "string" ? { asOf } : {}),
      summary: state,
    },
    actions: [
      { id: "global-intel.refresh", label: "刷新全球情报", available: Boolean(state.refresh) && (state.refresh as Record<string, unknown>).status !== "loading", inputSchema: { type: "object", additionalProperties: false } },
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
  const requestedTopic = providedTopicId ?? new URLSearchParams(window.location.search).get("topic");
  const topicId = requestedTopic && Object.hasOwn(GLOBAL_TOPICS, requestedTopic) ? requestedTopic as GlobalTopicId : undefined;
  const topicTitle = topicId ? GLOBAL_TOPICS[topicId].title : "全球情报";
  const runtimeModId = topicId ? GLOBAL_TOPICS[topicId].id : "global-situation";
  const [hostConnection, setHostConnection] = useState(providedHostConnection);
  const [hostConfig, setHostConfig] = useState(providedHostConnection?.config);
  const [gatewayOrigin, setGatewayOrigin] = useState(providedHostConnection
    ? new URL(providedHostConnection.config.gateways.data).origin : gatewayBaseUrl);
  const [theme, setTheme] = useState<"light" | "dark">(
    providedHostConnection?.config.environment.theme ?? initialTheme(),
  );
  const [cacheIdentity, setCacheIdentity] = useState(() => providedHostConnection
    ? {
        userId: providedHostConnection.config.user.id,
        workspaceId: providedHostConnection.config.workspace.id,
      }
    : embedded || window.parent !== window
      ? undefined
      : { userId: "local-user", workspaceId: "local-workspace" });
  const [refreshNonce, setRefreshNonce] = useState(0);
  const refreshSequence = useRef(0);
  const pendingRefresh = useRef<{
    nonce: number; resolve(value: unknown): void; reject(error: Error): void;
  } | undefined>(undefined);
  const [dashboardState, setDashboardState] = useState<Record<string, unknown>>({});
  const contextRef = useRef(buildGlobalIntelligenceContext(dashboardState, topicId));
  contextRef.current = buildGlobalIntelligenceContext(dashboardState, topicId);

  const dataSource = useMemo(
    () => providedDataSource ?? createGlobalIntelDataSource({
      baseUrl: gatewayOrigin,
      fetch: window.fetch.bind(window),
      requireSession: embedded || window.parent !== window || Boolean(hostConfig),
      session: hostConfig?.session ? {
        accessToken: hostConfig.session.accessToken,
        instanceId: hostConfig.instanceId,
        canRead: hostConfig.grants.permissions.includes("market.read"),
      } : undefined,
    }),
    [gatewayOrigin, providedDataSource, embedded, hostConfig?.session?.accessToken, hostConfig?.instanceId, hostConfig?.grants?.permissions],
  );
  const requireSession = embedded || window.parent !== window || Boolean(hostConfig);
  const canForecast = !requireSession || Boolean(hostConfig?.session && hostConfig.grants.permissions.includes("storage.write"));
  const topicRequest = useMemo(() => globalRequest({
    requireSession,
    session: hostConfig?.session ? {
      accessToken: hostConfig.session.accessToken, instanceId: hostConfig.instanceId,
      canRead: hostConfig.grants.permissions.includes("market.read"),
      canWrite: hostConfig.grants.permissions.includes("storage.write"),
    } : undefined,
  }), [requireSession, hostConfig?.session?.accessToken, hostConfig?.instanceId, hostConfig?.grants?.permissions]);

  useEffect(() => {
    document.title = topicTitle + " · Newma-Desk";
  }, [topicTitle]);

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
      setHostConfig(connection.config);
      setGatewayOrigin(new URL(connection.config.gateways.data).origin);
      setTheme(connection.config.environment.theme);
      setCacheIdentity({
        userId: connection.config.user.id,
        workspaceId: connection.config.workspace.id,
      });
      unsubscribe = connection.subscribe((config) => {
        setHostConfig(config);
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
    setHostConnection(providedHostConnection);
    setHostConfig(providedHostConnection.config);
    setTheme(providedHostConnection.config.environment.theme);
    setCacheIdentity({
      userId: providedHostConnection.config.user.id,
      workspaceId: providedHostConnection.config.workspace.id,
    });
    return providedHostConnection.subscribe((config) => {
      setHostConfig(config);
      setGatewayOrigin(new URL(config.gateways.data).origin);
      setTheme(config.environment.theme);
      setCacheIdentity({ userId: config.user.id, workspaceId: config.workspace.id });
    });
  }, [providedHostConnection]);

  useEffect(() => hostConnection?.setContextProvider(() => contextRef.current), [hostConnection]);

  useEffect(() => {
    hostConnection?.publishContext(contextRef.current);
  }, [dashboardState, hostConnection, topicId]);

  useEffect(() => {
    const pending = pendingRefresh.current;
    const refresh = dashboardState.refresh as Record<string, unknown> | undefined;
    if (!pending || refresh?.nonce !== pending.nonce || refresh.status === "loading") return;
    pendingRefresh.current = undefined;
    if (refresh.status === "error") {
      pending.reject(new Error(typeof refresh.error === "string" ? refresh.error : "刷新失败，未取得本次有效数据；旧数据显示不代表更新成功。"));
    } else {
      const coverage = dashboardState.dataAvailability as Record<string, unknown> | undefined;
      pending.resolve({ refreshed: true, status: coverage?.status === "partial" ? "partial" : refresh.status, context: contextRef.current });
    }
  }, [dashboardState]);

  useEffect(() => () => {
    pendingRefresh.current?.reject(new Error("页面或工作区已切换，未确认刷新结果；不会自动重试。"));
    pendingRefresh.current = undefined;
  }, [runtimeModId, cacheIdentity?.userId, cacheIdentity?.workspaceId, hostConfig?.session?.accessToken]);

  const refreshPage = useCallback(() => {
    pendingRefresh.current?.reject(new Error("用户已重新刷新，前次动作结果未确认。"));
    pendingRefresh.current = undefined;
    setRefreshNonce(++refreshSequence.current);
  }, []);

  const handleUiAction = useCallback((actionId: string, input: Record<string, unknown>) => {
    if (actionId === "global-intel.refresh") {
      if (pendingRefresh.current) return Promise.reject(new Error("刷新正在进行，请等待本次结果。"));
      const nonce = ++refreshSequence.current;
      return new Promise((resolve, reject) => {
        pendingRefresh.current = { nonce, resolve, reject };
        setRefreshNonce(nonce);
      });
    }
    if (actionId === "workspace.save-layout") {
      if (!cacheIdentity) throw new Error("工作区身份尚未就绪，不能保存视图。");
      const name = typeof input.name === "string" && input.name.trim()
        ? input.name.trim().slice(0, 80)
        : `${topicTitle}视图`;
      const record = { id: crypto.randomUUID(), name, savedAt: new Date().toISOString(), state: dashboardState };
      const key = "newma-desk.global-intelligence.layouts.v1:" + JSON.stringify([cacheIdentity.userId, cacheIdentity.workspaceId, runtimeModId]);
      const current = JSON.parse(localStorage.getItem(key) || "[]") as unknown;
      const layouts = Array.isArray(current) ? current : [];
      localStorage.setItem(key, JSON.stringify([record, ...layouts].slice(0, 20)));
      return { layout: record };
    }
    throw new Error(`全球情报不支持动作 ${actionId}`);
  }, [dashboardState, topicTitle, cacheIdentity?.userId, cacheIdentity?.workspaceId, runtimeModId]);

  useEffect(() => hostConnection?.setUiActionHandler(handleUiAction), [handleUiAction, hostConnection]);

  return (
    <main className="global-intelligence-root" data-embedded={embedded}>
      {!embedded ? (
        <header className="global-intelligence-topbar">
          <div className="global-intelligence-identity">
            <i><Globe2 size={18} /></i>
            <span><strong>{topicTitle}</strong><small>{topicId ? "GLOBAL THEMATIC RESEARCH" : "GLOBAL INTELLIGENCE OPERATIONS"}</small></span>
          </div>
          <div className="global-intelligence-runtime"><Radio size={13} />{topicId ? "专题研究 · 来源观测与手动推演" : "World Intelligence MCP · 实时数据平面"}</div>
          <button type="button" onClick={refreshPage}><RefreshCw size={14} />刷新情报</button>
        </header>
      ) : null}
      {topicId ? (
        <GlobalTopicDashboard topicId={topicId} gatewayBaseUrl={gatewayOrigin} request={topicRequest} canForecast={canForecast} refreshNonce={refreshNonce} cacheIdentity={cacheIdentity} embedded onContextChange={setDashboardState} />
      ) : <GlobalIntelligenceDashboard
        key={cacheIdentity ? `${cacheIdentity.userId}:${cacheIdentity.workspaceId}` : "pending-host"}
        dataSource={dataSource}
        theme={theme}
        refreshNonce={refreshNonce}
        cacheIdentity={cacheIdentity}
        onRefresh={refreshPage}
        onContextChange={setDashboardState}
      />}
      {!embedded ? (
        <footer className="global-intelligence-statusbar">
          <span><i />{runtimeModId.toUpperCase()}</span>
          <span>情报数据合同：{topicId ? "newma-desk.global-topic.v1" : "newma-desk.global-intelligence.v1"}</span>
          <span>{topicId ? "来源观测 · 手动情景" : "MAPLIBRE GL · DECK.GL"}</span>
        </footer>
      ) : null}
    </main>
  );
}
