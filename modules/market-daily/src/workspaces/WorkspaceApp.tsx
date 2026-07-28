import { BellRing, CircleCheck, Database, RefreshCw } from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import {
  connectModHost,
  createArtifactClient,
  createModBridge,
  type ArtifactClient,
  type GatewayFetch,
  type ModBridge,
  type ModHostConnection,
} from "@newma-desk/mod-sdk";

import { createMarketDataSource, securityKey } from "../data";
import { resolveParentOrigin } from "../lib/runtimeOrigin";
import type { MarketDataSource, Quote, SecurityRef } from "../types";
import { EventTimelineWorkspace } from "./EventTimelineWorkspace";
import { MultiTimeframeWorkspace } from "./MultiTimeframeWorkspace";
import { RelativeStrengthWorkspace } from "./RelativeStrengthWorkspace";
import { ReplayWorkspace } from "./ReplayWorkspace";
import { ScannerWorkspace } from "./ScannerWorkspace";
import type { MarketWorkspaceConfig } from "./config";
import {
  SecuritySearch,
  WORKSPACE_SECURITIES,
  formatPrice,
  movement,
  quoteSummary,
  signed,
  useDeskTheme,
  useStoredSecurity,
} from "./shared";

type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;

export interface MarketWorkspaceAppProps {
  config: MarketWorkspaceConfig;
  bridge?: ModBridge;
  dataSource?: MarketDataSource;
  fetch?: GatewayFetch;
  gatewayBaseUrl?: string;
  artifactClient?: ArtifactClient;
}

export interface WorkspaceUiAction {
  sequence: number;
  actionId: string;
  input: Record<string, unknown>;
}

interface PriceAlert {
  id: string;
  symbol: string;
  market: SecurityRef["market"];
  direction: "above" | "below";
  price: number;
  label: string;
  createdAt: string;
}

function configuredOrigin(name: "gateway" | "parent") {
  const value = name === "gateway"
    ? import.meta.env.VITE_GATEWAY_BASE_URL
    : import.meta.env.VITE_PARENT_ORIGIN;
  if (name === "parent") return resolveParentOrigin(value);
  return value?.trim() || window.location.origin;
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : "市场工作区暂时不可用";
}

export function buildWorkspacePageContext(input: {
  config: MarketWorkspaceConfig;
  security: SecurityRef;
  quote?: Quote;
  workspaceState: Record<string, unknown>;
}): ModPageContext {
  return {
    view: { id: input.config.modId, title: input.config.title },
    visibleBlocks: input.config.blocks,
    selection: {
      symbol: input.security.symbol,
      name: input.security.name,
      market: input.security.market,
      exchange: input.security.exchange ?? "",
    },
    filters: {
      workspace: input.config.kind,
      ...input.workspaceState,
    },
    data: {
      source: "market-data",
      freshness: input.quote ? "live" : "unknown",
      ...(input.quote?.asOf ? { asOf: input.quote.asOf } : {}),
      summary: {
        quote: quoteSummary(input.quote),
        workspace: input.workspaceState,
      },
    },
    actions: [
      { id: "market.refresh", label: "刷新当前工作区", available: true, inputSchema: { type: "object", additionalProperties: false } },
      ...(input.config.kind === "multi-timeframe" || input.config.kind === "trading-replay"
        ? [{ id: "market.set-timeframe", label: "切换周期", available: true, inputSchema: { type: "object", required: ["timeframe"], properties: { timeframe: { enum: ["5m", "15m", "60m", "1d"] } }, additionalProperties: false } }]
        : []),
      ...(input.config.kind === "multi-timeframe" || input.config.kind === "event-timeline" || input.config.kind === "trading-replay"
        ? [{ id: "chart.set-indicator", label: "设置图表指标", available: true, inputSchema: { type: "object", required: ["position", "indicator"], properties: { position: { enum: ["primary", "secondary"] }, indicator: { enum: ["MA", "EMA", "BOLL", "VOL", "MACD", "RSI", "KDJ"] } }, additionalProperties: false } }]
        : []),
      { id: "market.set-alert", label: "设置价格预警", available: true, inputSchema: { type: "object", required: ["direction", "price"], properties: { direction: { enum: ["above", "below"] }, price: { type: "number", exclusiveMinimum: 0 }, label: { type: "string", maxLength: 80 } }, additionalProperties: false } },
      { id: "workspace.save-layout", label: "保存当前布局", available: true, inputSchema: { type: "object", properties: { name: { type: "string", maxLength: 80 } }, additionalProperties: false } },
    ],
    tasks: [],
  };
}

export function MarketWorkspaceApp({
  config,
  bridge: providedBridge,
  dataSource: providedDataSource,
  fetch: providedFetch,
  gatewayBaseUrl,
  artifactClient: providedArtifactClient,
}: MarketWorkspaceAppProps) {
  const theme = useDeskTheme();
  const initialSecurity = useStoredSecurity(config.modId);
  const fetcher = useMemo(() => providedFetch ?? globalThis.fetch.bind(globalThis), [providedFetch]);
  const [gatewayOrigin, setGatewayOrigin] = useState(gatewayBaseUrl || configuredOrigin("gateway"));
  const [hostConnection, setHostConnection] = useState<EmbeddedHost>();
  const dataSource = useMemo(
    () => providedDataSource ?? createMarketDataSource({
      baseUrl: gatewayOrigin,
      fetch: fetcher,
      ...(hostConnection ? { invokeAction: hostConnection.invokeAction } : {}),
    }),
    [fetcher, gatewayOrigin, hostConnection, providedDataSource],
  );
  const artifactClient = useMemo<ArtifactClient>(
    () => providedArtifactClient ?? createArtifactClient({ baseUrl: gatewayOrigin, fetch: fetcher }),
    [fetcher, gatewayOrigin, providedArtifactClient],
  );
  const [bridge] = useState(() => providedBridge ?? createModBridge({ modId: config.modId, parentOrigin: configuredOrigin("parent") }));
  const ownsBridge = !providedBridge;
  const closeTimer = useRef<number | undefined>(undefined);
  const [security, setSecurity] = useState<SecurityRef>(initialSecurity);
  const [quote, setQuote] = useState<Quote>();
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [workspaceState, setWorkspaceState] = useState<Record<string, unknown>>({});
  const [workspaceAction, setWorkspaceAction] = useState<WorkspaceUiAction>();
  const [alerts, setAlerts] = useState<PriceAlert[]>(() => {
    try {
      const value = JSON.parse(window.localStorage.getItem(`vibedesk.${config.modId}.alerts.v1`) || "[]");
      return Array.isArray(value) ? value : [];
    } catch {
      return [];
    }
  });
  const [lastSavedLayout, setLastSavedLayout] = useState<{ name: string; savedAt: string }>();
  const [error, setError] = useState("");
  const layoutStateRef = useRef<Record<string, unknown>>({ security, ...workspaceState });

  const updateWorkspaceState = useCallback((next: Record<string, unknown>) => {
    layoutStateRef.current = { security, ...next };
    setWorkspaceState((current) => JSON.stringify(current) === JSON.stringify(next) ? current : next);
  }, [security]);
  layoutStateRef.current = { ...layoutStateRef.current, security };

  const contextualWorkspaceState = {
    ...workspaceState,
    alertCount: alerts.length,
    alerts: alerts.slice(0, 8),
    lastSavedLayout: lastSavedLayout ?? null,
  };
  const contextRef = useRef<ModPageContext>(buildWorkspacePageContext({ config, security, quote, workspaceState: contextualWorkspaceState }));
  contextRef.current = buildWorkspacePageContext({ config, security, quote, workspaceState: contextualWorkspaceState });

  useEffect(() => {
    document.title = `${config.title} · Newma-Desk`;
  }, [config.title]);

  useEffect(() => {
    if (providedBridge) return;
    const controller = new AbortController();
    let close: () => void = () => undefined;
    let unsubscribe: () => void = () => undefined;
    let removeContextProvider: () => void = () => undefined;
    const applyHostConfig = (hostConfig: EmbeddedHost["config"]) => {
      setGatewayOrigin(new URL(hostConfig.gateways.data).origin);
      document.documentElement.dataset.theme = hostConfig.environment.theme;
      document.documentElement.lang = hostConfig.environment.locale;
    };
    void connectModHost({
      modId: config.modId,
      parentOrigin: configuredOrigin("parent"),
      sdkVersion: "0.1.0",
      capabilities: ["events", "actions", "data", "context", "theme"],
      signal: controller.signal,
    }).then((connection) => {
      close = connection.close;
      if (!connection.embedded) return;
      setHostConnection(connection);
      applyHostConfig(connection.config);
      unsubscribe = connection.subscribe(applyHostConfig);
      removeContextProvider = connection.setContextProvider(() => contextRef.current);
    }).catch((reason) => {
      if (!controller.signal.aborted) setError(errorMessage(reason));
    });
    return () => {
      controller.abort();
      unsubscribe();
      removeContextProvider();
      close();
    };
  }, [config.modId, providedBridge]);

  useEffect(() => {
    hostConnection?.publishContext(contextRef.current);
  }, [alerts, hostConnection, lastSavedLayout, quote, security, workspaceState]);

  const handleUiAction = useCallback((actionId: string, input: Record<string, unknown>) => {
    if (actionId === "market.refresh") {
      setRefreshNonce((value) => value + 1);
      return { refreshed: true };
    }
    if (actionId === "market.set-alert") {
      const price = input.price;
      const direction = input.direction;
      if (typeof price !== "number" || !Number.isFinite(price) || price <= 0) throw new Error("预警价格必须大于 0");
      if (direction !== "above" && direction !== "below") throw new Error("预警方向必须是 above 或 below");
      const alert: PriceAlert = {
        id: globalThis.crypto?.randomUUID?.() ?? `alert-${Date.now()}`,
        symbol: security.symbol,
        market: security.market,
        direction,
        price,
        label: typeof input.label === "string" && input.label.trim() ? input.label.trim().slice(0, 80) : `${security.name} ${direction === "above" ? "上穿" : "下穿"} ${price}`,
        createdAt: new Date().toISOString(),
      };
      setAlerts((current) => {
        const next = [alert, ...current].slice(0, 50);
        window.localStorage.setItem(`vibedesk.${config.modId}.alerts.v1`, JSON.stringify(next));
        return next;
      });
      return { alert };
    }
    if (actionId === "workspace.save-layout") {
      const savedAt = new Date().toISOString();
      const name = typeof input.name === "string" && input.name.trim()
        ? input.name.trim().slice(0, 80)
        : `${config.title} ${new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date())}`;
      const key = `vibedesk.${config.modId}.layouts.v1`;
      let current: unknown[] = [];
      try {
        const parsed = JSON.parse(window.localStorage.getItem(key) || "[]");
        if (Array.isArray(parsed)) current = parsed;
      } catch {
        current = [];
      }
      const record = { id: globalThis.crypto?.randomUUID?.() ?? `layout-${Date.now()}`, name, savedAt, ...layoutStateRef.current };
      window.localStorage.setItem(key, JSON.stringify([record, ...current].slice(0, 20)));
      setLastSavedLayout({ name, savedAt });
      return { layout: record };
    }
    if (actionId === "market.set-timeframe") {
      if (!["5m", "15m", "60m", "1d"].includes(String(input.timeframe))) throw new Error("不支持的周期");
      layoutStateRef.current = { ...layoutStateRef.current, timeframe: input.timeframe };
    } else if (actionId === "chart.set-indicator") {
      const position = input.position;
      const indicator = input.indicator;
      const allowed = position === "primary" ? ["MA", "EMA", "BOLL"] : ["VOL", "MACD", "RSI", "KDJ"];
      if ((position !== "primary" && position !== "secondary") || !allowed.includes(String(indicator))) throw new Error("指标与图层位置不匹配");
      layoutStateRef.current = {
        ...layoutStateRef.current,
        [position === "primary" ? "primaryIndicator" : "secondaryIndicator"]: indicator,
      };
    } else {
      throw new Error(`当前工作区不支持动作 ${actionId}`);
    }
    const action = { sequence: Date.now(), actionId, input };
    setWorkspaceAction(action);
    return { accepted: true, action };
  }, [config.modId, config.title, security, workspaceState]);

  useEffect(() => hostConnection?.setUiActionHandler(handleUiAction), [handleUiAction, hostConnection]);

  const selectSecurity = useCallback((next: SecurityRef, emit = true) => {
    setSecurity(next);
    window.localStorage.setItem(`vibedesk.${config.modId}.security.v1`, JSON.stringify(next));
    if (emit) {
      bridge.emit("security.selected", {
        symbol: next.symbol,
        name: next.name,
        market: next.market,
        exchange: next.exchange ?? "",
      });
    }
  }, [bridge, config.modId]);

  useEffect(() => {
    if (closeTimer.current !== undefined) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = undefined;
    }
    const unsubscribe = bridge.subscribe((event) => {
      if (event.event !== "security.selected") return;
      const { symbol, name, market, exchange } = event.payload;
      if (typeof symbol !== "string" || (market !== "CN" && market !== "HK" && market !== "US")) return;
      selectSecurity({
        symbol,
        name: typeof name === "string" ? name : symbol,
        market,
        ...(typeof exchange === "string" ? { exchange } : {}),
      }, false);
    });
    return () => {
      unsubscribe();
      if (ownsBridge) closeTimer.current = window.setTimeout(() => bridge.close(), 0);
    };
  }, [bridge, ownsBridge, selectSecurity]);

  useEffect(() => {
    let active = true;
    void dataSource.quote(security).then((next) => {
      if (!active) return;
      setQuote(next);
      setError("");
    }).catch((reason) => active && setError(errorMessage(reason)));
    return () => {
      active = false;
    };
  }, [dataSource, refreshNonce, security]);

  const content = config.kind === "scanner"
    ? <ScannerWorkspace dataSource={dataSource} security={security} onSelectSecurity={selectSecurity} refreshNonce={refreshNonce} onContextChange={updateWorkspaceState} />
    : config.kind === "multi-timeframe"
      ? <MultiTimeframeWorkspace action={workspaceAction} dataSource={dataSource} security={security} quote={quote} theme={theme} refreshNonce={refreshNonce} onContextChange={updateWorkspaceState} />
      : config.kind === "relative-strength"
        ? <RelativeStrengthWorkspace dataSource={dataSource} security={security} onSelectSecurity={selectSecurity} refreshNonce={refreshNonce} onContextChange={updateWorkspaceState} />
        : config.kind === "event-timeline"
          ? <EventTimelineWorkspace action={workspaceAction} dataSource={dataSource} security={security} theme={theme} refreshNonce={refreshNonce} onContextChange={updateWorkspaceState} />
          : <ReplayWorkspace action={workspaceAction} artifactClient={artifactClient} dataSource={dataSource} security={security} theme={theme} refreshNonce={refreshNonce} onContextChange={updateWorkspaceState} />;

  return (
    <main className={`market-workspace-root${error ? " has-error" : ""}`} style={{ "--workspace-accent": config.accent } as CSSProperties}>
      <header className="workspace-topbar">
        <div className="workspace-title">
          <strong>{config.title}</strong>
          <span>{config.description}</span>
        </div>
        <SecuritySearch dataSource={dataSource} onSelect={selectSecurity} />
        <button type="button" className="workspace-refresh" onClick={() => setRefreshNonce((value) => value + 1)}><RefreshCw size={14} />刷新</button>
      </header>
      <section className="workspace-quote-strip">
        <div className="workspace-current-security">
          <i>{security.market}</i>
          <span><strong>{quote?.name || security.name}</strong><small>{security.symbol} · {quote?.exchange || security.exchange || security.market}</small></span>
        </div>
        <div className={`workspace-current-price ${movement(quote?.changePct)}`}>
          <strong>{formatPrice(quote?.price, security.market === "HK" ? 3 : 2)}</strong>
          <span>{signed(quote?.changePct)}</span>
        </div>
        <div className="workspace-security-shortcuts" role="group" aria-label="快速切换标的">
          {WORKSPACE_SECURITIES.slice(0, 6).map((item) => (
            <button type="button" key={securityKey(item)} aria-pressed={securityKey(item) === securityKey(security)} onClick={() => selectSecurity(item)}>{item.name}</button>
          ))}
        </div>
        <div className="workspace-data-status"><CircleCheck size={13} /><span>Agent 上下文已同步</span><Database size={13} /><span>market-data</span><BellRing size={13} /><span>{alerts.length} 个预警</span></div>
      </section>
      {error ? <div className="workspace-error-banner" role="alert">{error}</div> : null}
      <div className="workspace-content">{content}</div>
      <footer className="workspace-statusbar">
        <span><i />{config.modId}</span>
        <span>当前标的事件：security.selected · {security.market}:{security.symbol}</span>
        <span>{lastSavedLayout ? `最近布局：${lastSavedLayout.name}` : "右侧 Desk Agent 可读取并操作本页"}</span>
      </footer>
    </main>
  );
}
