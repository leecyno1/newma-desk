import {
  Activity,
  BarChart3,
  ChevronDown,
  CirclePlus,
  Eraser,
  Expand,
  LineChart,
  ListFilter,
  MoveDiagonal2,
  PencilLine,
  RefreshCw,
  Search,
  Star,
  Trash2,
  X,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import {
  connectModHost,
  createModBridge,
  type GatewayFetch,
  type ModBridge,
  type ModHostConnection,
} from "@newma-desk/mod-sdk";

import { createMarketDataSource, securityKey } from "./data";
import {
  createMarketAlertClient,
  useMarketAlerts,
  type MarketAlertClient,
  type PriceAlert,
} from "./alerts";
import { resolveParentOrigin } from "./lib/runtimeOrigin";
import { MarketAlertCenter } from "./MarketAlertCenter";
import {
  KLineChartPanel,
  type KLineChartPanelHandle,
} from "./KLineChartPanel";
import type {
  Adjustment,
  MarketDataSource,
  MarketFilter,
  MarketOverview,
  PrimaryIndicator,
  Quote,
  SearchResult,
  SecondaryIndicator,
  SecurityRef,
  Timeframe,
  TurnoverStock,
  WatchGroup,
} from "./types";
import {
  createWatchlistClient,
  readLocalWatchGroups,
  saveWatchGroups,
  type WatchlistClient,
  type WatchlistSnapshot,
} from "./watchlist";
import {
  securityFromWikiHandoff,
  wikiContextForSecurity,
} from "./wiki";

const MOD_ID = "market-daily";
const TIMEFRAMES: Array<{ id: Timeframe; label: string }> = [
  { id: "1m", label: "1分" },
  { id: "5m", label: "5分" },
  { id: "15m", label: "15分" },
  { id: "30m", label: "30分" },
  { id: "60m", label: "60分" },
  { id: "1d", label: "日K" },
  { id: "1w", label: "周K" },
  { id: "1M", label: "月K" },
];
const PRIMARY_INDICATORS: PrimaryIndicator[] = ["MA", "EMA", "BOLL"];
const SECONDARY_INDICATORS: SecondaryIndicator[] = ["VOL", "MACD", "RSI", "KDJ"];

type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;
type BottomTab = "overview" | "turnover" | "global";
type RailTab = "orderbook" | "metrics";

export interface MarketTerminalAppProps {
  bridge?: ModBridge;
  dataSource?: MarketDataSource;
  watchlistClient?: WatchlistClient | null;
  alertClient?: MarketAlertClient | null;
  fetch?: GatewayFetch;
  gatewayBaseUrl?: string;
  hostConnection?: EmbeddedHost;
  embedded?: boolean;
}

function configuredOrigin(name: "gateway" | "parent") {
  const value = name === "gateway"
    ? import.meta.env.VITE_GATEWAY_BASE_URL
    : import.meta.env.VITE_PARENT_ORIGIN;
  if (name === "parent") return resolveParentOrigin(value);
  return value?.trim() || window.location.origin;
}

function errorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : "市场数据暂时不可用";
}

function number(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function formatPrice(value: unknown, digits = 2) {
  const parsed = number(value);
  return parsed === undefined
    ? "—"
    : new Intl.NumberFormat("zh-CN", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(parsed);
}

function formatCompact(value: unknown) {
  const parsed = number(value);
  if (parsed === undefined) return "—";
  return new Intl.NumberFormat("zh-CN", {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(parsed);
}

function signed(value: unknown, suffix = "%") {
  const parsed = number(value);
  if (parsed === undefined) return "—";
  return `${parsed > 0 ? "+" : ""}${parsed.toFixed(2)}${suffix}`;
}

function movement(value: unknown) {
  const parsed = number(value);
  return parsed === undefined || parsed === 0 ? "flat" : parsed > 0 ? "up" : "down";
}

function allSymbols(groups: WatchGroup[]) {
  const map = new Map<string, SecurityRef>();
  for (const group of groups) {
    for (const symbol of group.symbols) map.set(securityKey(symbol), symbol);
  }
  return [...map.values()];
}

function quoteSummary(quote?: Quote) {
  if (!quote) return {};
  return {
    symbol: quote.symbol,
    name: quote.name,
    market: quote.market,
    price: quote.price ?? null,
    change: quote.change ?? null,
    changePct: quote.changePct ?? null,
    open: quote.open ?? null,
    high: quote.high ?? null,
    low: quote.low ?? null,
    volume: quote.volume ?? null,
    amount: quote.amount ?? null,
    pe: quote.pe ?? null,
    pb: quote.pb ?? null,
  };
}

export function buildMarketPageContext(input: {
  security: SecurityRef;
  quote?: Quote;
  timeframe: Timeframe;
  adjustment: Adjustment;
  primaryIndicator: PrimaryIndicator;
  secondaryIndicator: SecondaryIndicator;
  bottomTab: BottomTab;
  railTab: RailTab;
  source?: string;
  asOf?: string;
  visibleRange?: { from: number; to: number };
  alerts?: PriceAlert[];
}): ModPageContext {
  return {
    view: { id: MOD_ID, title: "行情" },
    visibleBlocks: [
      { id: "terminal-watchlist", type: "watchlist", title: "自选与分组" },
      { id: "terminal-chart", type: "klinechart", title: "K 线与指标" },
      { id: "terminal-market-rail", type: "market-data", title: "盘口与指标" },
      { id: "terminal-bottom-dock", type: "market-overview", title: "市场概览" },
    ],
    selection: {
      symbol: input.security.symbol,
      name: input.security.name,
      market: input.security.market,
      exchange: input.security.exchange ?? "",
      currency: input.security.currency ?? "",
    },
    filters: {
      timeframe: input.timeframe,
      adjustment: input.adjustment,
      primaryIndicator: input.primaryIndicator,
      secondaryIndicator: input.secondaryIndicator,
      bottomTab: input.bottomTab,
      railTab: input.railTab,
      ...(input.visibleRange ? { visibleRange: input.visibleRange } : {}),
    },
    data: {
      ...(input.asOf ? { asOf: input.asOf } : {}),
      source: input.source || "vibe-research-market-terminal",
      freshness: input.quote ? "live" : "unknown",
      summary: {
        ...quoteSummary(input.quote),
        alertCount: input.alerts?.length ?? 0,
        alerts: (input.alerts ?? []).slice(0, 8),
      },
    },
    actions: [
      { id: "market.refresh", label: "刷新行情数据", available: true, inputSchema: { type: "object", additionalProperties: false } },
      { id: "market.set-timeframe", label: "切换 K 线周期", available: true, inputSchema: { type: "object", required: ["timeframe"], properties: { timeframe: { enum: ["1m", "5m", "15m", "30m", "60m", "1d", "1w", "1M"] } }, additionalProperties: false } },
      { id: "chart.set-indicator", label: "设置图表指标", available: true, inputSchema: { type: "object", required: ["position", "indicator"], properties: { position: { enum: ["primary", "secondary"] }, indicator: { enum: ["MA", "EMA", "BOLL", "VOL", "MACD", "RSI", "KDJ"] } }, additionalProperties: false } },
      { id: "market.set-alert", label: "设置价格预警", available: true, inputSchema: { type: "object", required: ["direction", "price"], properties: { direction: { enum: ["above", "below"] }, price: { type: "number", exclusiveMinimum: 0 }, label: { type: "string", maxLength: 80 } }, additionalProperties: false } },
      { id: "workspace.save-layout", label: "保存当前布局", available: true, inputSchema: { type: "object", properties: { name: { type: "string", maxLength: 80 } }, additionalProperties: false } },
    ],
    wiki: wikiContextForSecurity({
      security: input.security,
      intent: "market.overview",
      timeframe: input.timeframe,
    }),
    tasks: [],
  };
}

function useDeskTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  });
  useEffect(() => {
    const root = document.documentElement;
    const update = () => {
      setTheme(root.dataset.theme === "dark" ? "dark" : "light");
    };
    const observer = new MutationObserver(update);
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return theme;
}

export function MarketTerminalApp({
  bridge: providedBridge,
  dataSource: providedDataSource,
  watchlistClient: providedWatchlistClient,
  alertClient: providedAlertClient,
  fetch: providedFetch,
  gatewayBaseUrl,
  hostConnection: providedHostConnection,
  embedded: embeddedProp,
}: MarketTerminalAppProps) {
  const embedded = embeddedProp ?? window.self !== window.top;
  const theme = useDeskTheme();
  const fetcher = useMemo(
    () => providedFetch ?? globalThis.fetch.bind(globalThis),
    [providedFetch],
  );
  const [gatewayOrigin, setGatewayOrigin] = useState(
    providedHostConnection ? new URL(providedHostConnection.config.gateways.data).origin : (gatewayBaseUrl || configuredOrigin("gateway")),
  );
  const [hostConnection, setHostConnection] = useState<EmbeddedHost | undefined>(providedHostConnection);
  const dataSource = useMemo(
    () => providedDataSource ?? createMarketDataSource({
      baseUrl: gatewayOrigin,
      fetch: fetcher,
      ...(hostConnection ? { invokeAction: hostConnection.invokeAction } : {}),
    }),
    [fetcher, gatewayOrigin, hostConnection, providedDataSource],
  );
  const [bridge] = useState(
    () => providedBridge ?? createModBridge({ modId: MOD_ID, parentOrigin: configuredOrigin("parent") }),
  );
  const ownsBridge = !providedBridge;
  const chartRef = useRef<KLineChartPanelHandle>(null);
  const bridgeCloseTimer = useRef<number | undefined>(undefined);
  const [hostIdentity, setHostIdentity] = useState<{
    userId: string;
    workspaceId: string;
  }>();
  const [localWatchlist] = useState(readLocalWatchGroups);
  const [groups, setGroups] = useState<WatchGroup[]>(localWatchlist.groups);
  const [activeGroupId, setActiveGroupId] = useState(
    () => localWatchlist.groups[0]?.id || "sample",
  );
  const [watchlistSync, setWatchlistSync] = useState<
    "local" | "loading" | "synced" | "error"
  >("local");
  const watchlistMutationRef = useRef<Promise<unknown>>(Promise.resolve());
  const watchlistMutationTokenRef = useRef(0);
  const initialSecurity = groups[0]?.symbols[0] ?? {
    symbol: "600519",
    name: "贵州茅台",
    market: "CN" as const,
  };
  const [security, setSecurity] = useState<SecurityRef>(initialSecurity);
  const [quote, setQuote] = useState<Quote>();
  const [watchQuotes, setWatchQuotes] = useState<Record<string, Quote>>({});
  const [timeframe, setTimeframe] = useState<Timeframe>("1d");
  const [adjustment, setAdjustment] = useState<Adjustment>("qfq");
  const [primaryIndicator, setPrimaryIndicator] = useState<PrimaryIndicator>("MA");
  const [secondaryIndicator, setSecondaryIndicator] = useState<SecondaryIndicator>("VOL");
  const [railTab, setRailTab] = useState<RailTab>("orderbook");
  const [bottomTab, setBottomTab] = useState<BottomTab>("overview");
  const [query, setQuery] = useState("");
  const [searchMarket, setSearchMarket] = useState<MarketFilter>("ALL");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [overview, setOverview] = useState<MarketOverview>();
  const [turnover, setTurnover] = useState<TurnoverStock[]>([]);
  const [indices, setIndices] = useState<Array<Record<string, unknown>>>([]);
  const [globalIndices, setGlobalIndices] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState<string>();
  const [chartState, setChartState] = useState<{ loading: boolean; error?: string }>({ loading: true });
  const [chartMeta, setChartMeta] = useState<{ source?: string; asOf?: string }>({});
  const [visibleRange, setVisibleRange] = useState<{ from: number; to: number }>();
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [groupEditor, setGroupEditor] = useState<{
    mode: "create" | "rename";
    value: string;
  }>();
  const [deleteConfirmId, setDeleteConfirmId] = useState("");
  const layoutStateRef = useRef({
    security,
    timeframe,
    adjustment,
    primaryIndicator,
    secondaryIndicator,
    bottomTab,
    railTab,
  });
  layoutStateRef.current = {
    security,
    timeframe,
    adjustment,
    primaryIndicator,
    secondaryIndicator,
    bottomTab,
    railTab,
  };

  const watchlistIdentity = hostIdentity ?? (
    hostConnection
      ? { userId: hostConnection.config.user.id, workspaceId: hostConnection.config.workspace.id }
      : window.self === window.top
        ? { userId: "local-user", workspaceId: "local-workspace" }
        : undefined
  );
  const sharedWatchlistClient = useMemo(() => {
    if (providedWatchlistClient === null) return undefined;
    if (providedWatchlistClient) return providedWatchlistClient;
    if (!watchlistIdentity) return undefined;
    return createWatchlistClient({
      baseUrl: gatewayOrigin,
      fetch: fetcher,
      ...watchlistIdentity,
    });
  }, [
    fetcher,
    gatewayOrigin,
    providedWatchlistClient,
    watchlistIdentity?.userId,
    watchlistIdentity?.workspaceId,
  ]);
  const sharedAlertClient = useMemo(() => {
    if (providedAlertClient === null) return undefined;
    if (providedAlertClient) return providedAlertClient;
    if (!watchlistIdentity) return undefined;
    return createMarketAlertClient({
      baseUrl: gatewayOrigin,
      fetch: fetcher,
      ...watchlistIdentity,
    });
  }, [
    fetcher,
    gatewayOrigin,
    providedAlertClient,
    watchlistIdentity?.userId,
    watchlistIdentity?.workspaceId,
  ]);
  const {
    alerts,
    status: alertStatus,
    createAlert,
    updateAlert,
    deleteAlert,
  } = useMarketAlerts(sharedAlertClient);

  const activeGroup = groups.find((group) => group.id === activeGroupId) ?? groups[0];
  const contextRef = useRef<ModPageContext>(
    buildMarketPageContext({
      security,
      quote,
      timeframe,
      adjustment,
      primaryIndicator,
      secondaryIndicator,
      bottomTab,
      railTab,
      source: chartMeta.source || quote?.source,
      asOf: chartMeta.asOf || quote?.asOf,
      visibleRange,
      alerts,
    }),
  );
  contextRef.current = buildMarketPageContext({
    security,
    quote,
    timeframe,
    adjustment,
    primaryIndicator,
    secondaryIndicator,
    bottomTab,
    railTab,
    source: chartMeta.source || quote?.source,
    asOf: chartMeta.asOf || quote?.asOf,
    visibleRange,
    alerts,
  });

  useEffect(() => saveWatchGroups(groups), [groups]);

  const applyWatchlistSnapshot = useCallback((snapshot: WatchlistSnapshot) => {
    setGroups(snapshot.groups);
    setActiveGroupId((current) =>
      snapshot.groups.some((group) => group.id === current)
        ? current
        : snapshot.groups[0]?.id || "sample",
    );
    saveWatchGroups(snapshot.groups);
  }, []);

  useEffect(() => {
    if (!sharedWatchlistClient) return;
    let active = true;
    setWatchlistSync("loading");
    void sharedWatchlistClient.load().then(async (remote) => {
      let snapshot = remote;
      if (remote.revision === 0 && localWatchlist.hasStoredValue) {
        try {
          snapshot = await sharedWatchlistClient.replace(
            remote.revision,
            localWatchlist.groups,
          );
        } catch {
          snapshot = await sharedWatchlistClient.load();
        }
      }
      if (!active) return;
      applyWatchlistSnapshot(snapshot);
      setWatchlistSync("synced");
    }).catch(() => {
      if (active) setWatchlistSync("error");
    });
    return () => {
      active = false;
    };
  }, [applyWatchlistSnapshot, localWatchlist, sharedWatchlistClient]);

  const queueWatchlistMutation = useCallback((
    operation: (client: WatchlistClient) => Promise<WatchlistSnapshot>,
  ) => {
    if (!sharedWatchlistClient) return;
    const token = ++watchlistMutationTokenRef.current;
    setWatchlistSync("loading");
    watchlistMutationRef.current = watchlistMutationRef.current
      .catch(() => undefined)
      .then(() => operation(sharedWatchlistClient))
      .then((snapshot) => {
        if (token === watchlistMutationTokenRef.current) {
          applyWatchlistSnapshot(snapshot);
          setWatchlistSync("synced");
        }
      })
      .catch(async () => {
        if (token !== watchlistMutationTokenRef.current) return;
        try {
          applyWatchlistSnapshot(await sharedWatchlistClient.load());
        } catch {
          // Keep the optimistic local copy available while the Desk API is offline.
        }
        setWatchlistSync("error");
      });
  }, [applyWatchlistSnapshot, sharedWatchlistClient]);

  useEffect(() => {
    if (providedHostConnection) {
      setHostConnection(providedHostConnection);
      setGatewayOrigin(new URL(providedHostConnection.config.gateways.data).origin);
      setHostIdentity({
        userId: providedHostConnection.config.user.id,
        workspaceId: providedHostConnection.config.workspace.id,
      });
      document.documentElement.dataset.theme = providedHostConnection.config.environment.theme;
      document.documentElement.lang = providedHostConnection.config.environment.locale;
      return;
    }
    if (providedBridge) return;
    const controller = new AbortController();
    let close: () => void = () => undefined;
    let unsubscribe: () => void = () => undefined;
    let removeContextProvider: () => void = () => undefined;
    const applyHostConfig = (config: EmbeddedHost["config"]) => {
      setGatewayOrigin(new URL(config.gateways.data).origin);
      setHostIdentity({
        userId: config.user.id,
        workspaceId: config.workspace.id,
      });
      document.documentElement.dataset.theme = config.environment.theme;
      document.documentElement.lang = config.environment.locale;
    };
    void connectModHost({
      modId: MOD_ID,
      parentOrigin: configuredOrigin("parent"),
      sdkVersion: "0.1.0",
      capabilities: ["events", "actions", "data", "context", "theme", "handoff"],
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
  }, [providedBridge, providedHostConnection]);

  useEffect(() => {
    hostConnection?.publishContext(contextRef.current);
  }, [
    hostConnection,
    security,
    quote,
    timeframe,
    adjustment,
    primaryIndicator,
    secondaryIndicator,
    bottomTab,
    railTab,
    chartMeta,
    visibleRange,
    alerts,
  ]);

  useEffect(
    () => hostConnection?.setContextProvider(() => contextRef.current),
    [hostConnection],
  );

  const selectSecurity = useCallback((next: SecurityRef, emit = true) => {
    setSecurity(next);
    setSearchOpen(false);
    setQuery("");
    if (emit) {
      bridge.emit("security.selected", {
        symbol: next.symbol,
        name: next.name,
        market: next.market,
        exchange: next.exchange ?? "",
      });
    }
  }, [bridge]);

  useEffect(() => hostConnection?.setHandoffHandler((handoff) => {
    const next = securityFromWikiHandoff(handoff);
    if (next.assetType === "fund") {
      throw new Error("行情暂不支持开放式基金交接");
    }
    selectSecurity(next, false);
    const requestedPeriod = handoff.parameters.period;
    if (requestedPeriod === "daily") setTimeframe("1d");
    else if (requestedPeriod === "weekly") setTimeframe("1w");
    else if (requestedPeriod === "monthly") setTimeframe("1M");
    return { selected: next.symbol };
  }), [hostConnection, selectSecurity]);

  useEffect(() => {
    if (bridgeCloseTimer.current !== undefined) {
      window.clearTimeout(bridgeCloseTimer.current);
      bridgeCloseTimer.current = undefined;
    }
    const unsubscribe = bridge.subscribe((event) => {
      if (event.event !== "security.selected") return;
      const { symbol, name, market, exchange } = event.payload;
      if (
        typeof symbol !== "string" ||
        (market !== "CN" && market !== "HK" && market !== "US")
      ) return;
      selectSecurity({
        symbol,
        name: typeof name === "string" ? name : symbol,
        market,
        ...(typeof exchange === "string" ? { exchange } : {}),
      }, false);
    });
    return () => {
      unsubscribe();
      if (ownsBridge) {
        bridgeCloseTimer.current = window.setTimeout(() => bridge.close(), 0);
      }
    };
  }, [bridge, ownsBridge, selectSecurity]);

  const loadQuote = useCallback(async () => {
    try {
      const next = await dataSource.quote(security);
      setQuote(next);
      setError(undefined);
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }, [dataSource, security]);

  const loadWatchQuotes = useCallback(async () => {
    try {
      const items = await dataSource.quotes(allSymbols(groups));
      setWatchQuotes(Object.fromEntries(items.map((item) => [securityKey(item), item])));
    } catch {
      // The selected quote and chart can remain usable when batch quotes fail.
    }
  }, [dataSource, groups]);

  const loadMarketOverview = useCallback(async () => {
    const results = await Promise.allSettled([
      dataSource.overview(),
      dataSource.turnoverTop(),
      dataSource.indices(),
      dataSource.globalIndices(),
    ]);
    if (results[0].status === "fulfilled") setOverview(results[0].value);
    if (results[1].status === "fulfilled") setTurnover(results[1].value);
    if (results[2].status === "fulfilled") setIndices(results[2].value);
    if (results[3].status === "fulfilled") setGlobalIndices(results[3].value);
  }, [dataSource]);

  useEffect(() => {
    void loadQuote();
    const timer = window.setInterval(() => void loadQuote(), 15_000);
    return () => window.clearInterval(timer);
  }, [loadQuote]);

  useEffect(() => {
    void loadWatchQuotes();
    const timer = window.setInterval(() => void loadWatchQuotes(), 30_000);
    return () => window.clearInterval(timer);
  }, [loadWatchQuotes]);

  useEffect(() => {
    void loadMarketOverview();
  }, [loadMarketOverview]);

  useEffect(() => {
    const clean = query.trim();
    if (!clean) {
      setSearchResults([]);
      setSearching(false);
      return;
    }
    const controller = new AbortController();
    setSearching(true);
    const timer = window.setTimeout(() => {
      void dataSource.search(clean, searchMarket).then((items) => {
        if (!controller.signal.aborted) {
          setSearchResults(items);
          setSearchOpen(true);
        }
      }).catch((reason) => {
        if (!controller.signal.aborted) setError(errorMessage(reason));
      }).finally(() => {
        if (!controller.signal.aborted) setSearching(false);
      });
    }, 220);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [dataSource, query, searchMarket]);

  const loadBars = useCallback(async () => {
    const result = await dataSource.ohlcv(security, timeframe, adjustment);
    setChartMeta({ source: result.source, asOf: result.asOf });
    return result.items;
  }, [adjustment, dataSource, security, timeframe]);

  const refreshAll = useCallback(() => {
    setRefreshNonce((value) => value + 1);
    void loadQuote();
    void loadWatchQuotes();
    void loadMarketOverview();
  }, [loadMarketOverview, loadQuote, loadWatchQuotes]);

  const handleUiAction = useCallback(async (actionId: string, input: Record<string, unknown>) => {
    if (actionId === "market.refresh") {
      refreshAll();
      return { refreshed: true };
    }
    if (actionId === "market.set-timeframe") {
      const next = String(input.timeframe) as Timeframe;
      if (!["1m", "5m", "15m", "30m", "60m", "1d", "1w", "1M"].includes(next)) throw new Error("不支持的周期");
      layoutStateRef.current = { ...layoutStateRef.current, timeframe: next };
      setTimeframe(next);
      return { timeframe: next };
    }
    if (actionId === "chart.set-indicator") {
      if (input.position === "primary" && ["MA", "EMA", "BOLL"].includes(String(input.indicator))) {
        const next = input.indicator as PrimaryIndicator;
        layoutStateRef.current = { ...layoutStateRef.current, primaryIndicator: next };
        setPrimaryIndicator(next);
        return { primaryIndicator: input.indicator };
      }
      if (input.position === "secondary" && ["VOL", "MACD", "RSI", "KDJ"].includes(String(input.indicator))) {
        const next = input.indicator as SecondaryIndicator;
        layoutStateRef.current = { ...layoutStateRef.current, secondaryIndicator: next };
        setSecondaryIndicator(next);
        return { secondaryIndicator: input.indicator };
      }
      throw new Error("指标与图层位置不匹配");
    }
    if (actionId === "market.set-alert") {
      const price = input.price;
      const direction = input.direction;
      if (typeof price !== "number" || !Number.isFinite(price) || price <= 0 || (direction !== "above" && direction !== "below")) throw new Error("价格预警参数无效");
      const alert = await createAlert({
        security,
        direction,
        price,
        label: typeof input.label === "string" ? input.label.slice(0, 80) : "",
      });
      return { alert };
    }
    if (actionId === "workspace.save-layout") {
      const key = "vibedesk.market-daily.layouts.v1";
      let layouts: unknown[] = [];
      try {
        const parsed = JSON.parse(window.localStorage.getItem(key) || "[]");
        if (Array.isArray(parsed)) layouts = parsed;
      } catch {
        layouts = [];
      }
      const layout = {
        id: globalThis.crypto?.randomUUID?.() ?? `layout-${Date.now()}`,
        name: typeof input.name === "string" && input.name.trim() ? input.name.trim().slice(0, 80) : "行情布局",
        savedAt: new Date().toISOString(),
        ...layoutStateRef.current,
      };
      window.localStorage.setItem(key, JSON.stringify([layout, ...layouts].slice(0, 20)));
      return { layout };
    }
    throw new Error(`行情不支持动作 ${actionId}`);
  }, [createAlert, refreshAll, security]);

  useEffect(() => hostConnection?.setUiActionHandler(handleUiAction), [handleUiAction, hostConnection]);

  const addToActiveGroup = useCallback((item: SecurityRef) => {
    const groupId = activeGroup?.id;
    if (!groupId) return;
    let changed = false;
    const next = groups.map((group) => {
      if (group.id !== groupId || group.symbols.some((row) => securityKey(row) === securityKey(item))) {
        return group;
      }
      changed = true;
      return { ...group, symbols: [...group.symbols, item] };
    });
    if (!changed) return;
    setGroups(next);
    queueWatchlistMutation((client) => client.addSecurity(groupId, item));
  }, [activeGroup?.id, groups, queueWatchlistMutation]);

  const removeFromActiveGroup = useCallback((item: SecurityRef) => {
    const groupId = activeGroup?.id;
    if (!groupId) return;
    const next = groups.map((group) => group.id === groupId
      ? { ...group, symbols: group.symbols.filter((row) => securityKey(row) !== securityKey(item)) }
      : group);
    setGroups(next);
    queueWatchlistMutation((client) => client.removeSecurity(groupId, item));
  }, [activeGroup?.id, groups, queueWatchlistMutation]);

  const saveGroupEditor = () => {
    const name = groupEditor?.value.trim();
    if (!groupEditor || !name) return;
    if (groupEditor.mode === "rename" && activeGroup) {
      setGroups(groups.map((group) => group.id === activeGroup.id
        ? { ...group, name }
        : group));
      queueWatchlistMutation((client) =>
        client.renameGroup(activeGroup.id, name),
      );
      setGroupEditor(undefined);
      return;
    }
    const id = `group-${Date.now()}`;
    setGroups([...groups, { id, name, symbols: [] }]);
    setActiveGroupId(id);
    queueWatchlistMutation((client) =>
      client.createGroup({ id, name }),
    );
    setGroupEditor(undefined);
  };

  const deleteGroup = () => {
    if (!activeGroup || groups.length <= 1) return;
    if (deleteConfirmId !== activeGroup.id) {
      setDeleteConfirmId(activeGroup.id);
      return;
    }
    const next = groups.filter((group) => group.id !== activeGroup.id);
    setGroups(next);
    setActiveGroupId(next[0]?.id || "");
    setDeleteConfirmId("");
    queueWatchlistMutation((client) => client.deleteGroup(activeGroup.id));
  };

  const requestFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void document.documentElement.requestFullscreen?.();
  };

  const adjustmentDisabled = security.market !== "CN" || timeframe.endsWith("m");
  const watchlistSyncLabel = watchlistSync === "synced"
    ? "Desk 已同步"
    : watchlistSync === "loading"
      ? "同步中"
      : watchlistSync === "error"
        ? "本地可用"
        : "本地";
  const currentMovement = movement(quote?.changePct);
  const orderBook = quote?.orderBook ?? { bids: [], asks: [] };
  const displayLevels = [...orderBook.asks].reverse().map((item, index) => ({
    ...item,
    label: `卖${orderBook.asks.length - index}`,
    side: "ask",
  })).concat(orderBook.bids.map((item, index) => ({
    ...item,
    label: `买${index + 1}`,
    side: "bid",
  })));

  return (
    <div className="terminal-root" data-embedded={embedded || undefined}>
      <header className="terminal-topbar">
        {!embedded ? <div className="terminal-brand" data-mod-page-title>
          <span className="terminal-brand-mark"><Activity size={15} /></span>
          <div>
            <strong>行情</strong>
            <span>KLineChart · Newma-Desk Data</span>
          </div>
        </div> : null}

        <div className="symbol-search-wrap">
          <div className="symbol-search">
            <Search size={15} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onFocus={() => query.trim() && setSearchOpen(true)}
              placeholder="搜索代码、公司或 ETF"
              aria-label="搜索证券"
            />
            <select
              aria-label="搜索市场"
              value={searchMarket}
              onChange={(event) => setSearchMarket(event.target.value as MarketFilter)}
            >
              <option value="ALL">全部</option>
              <option value="CN">A股</option>
              <option value="HK">港股</option>
              <option value="US">美股</option>
            </select>
            {searching ? <RefreshCw className="spin" size={14} /> : null}
          </div>
          {searchOpen ? (
            <div className="search-results" role="listbox">
              <div className="search-results-head">
                <span>搜索结果</span>
                <button type="button" onClick={() => setSearchOpen(false)} aria-label="关闭搜索结果"><X size={14} /></button>
              </div>
              {searchResults.length ? searchResults.map((item) => (
                <div className="search-result" key={securityKey(item)}>
                  <button type="button" className="search-result-main" onClick={() => selectSecurity(item)}>
                    <span className="market-badge">{item.market}</span>
                    <span><strong>{item.name}</strong><small>{item.symbol} · {item.exchange}</small></span>
                  </button>
                  <button type="button" className="icon-button" onClick={() => addToActiveGroup(item)} aria-label={`添加 ${item.name} 到自选`}><Star size={14} /></button>
                </div>
              )) : <p className="empty-copy">没有匹配标的</p>}
            </div>
          ) : null}
        </div>

        <div className="topbar-actions">
          <MarketAlertCenter
            alerts={alerts}
            security={security}
            quote={quote}
            available={alertStatus !== "unavailable"}
            onCreate={(input) => createAlert({ security, ...input })}
            onToggle={(alert) => updateAlert(alert.id, { enabled: !alert.enabled })}
            onDelete={(alert) => deleteAlert(alert.id)}
          />
          <button type="button" className="icon-button" onClick={refreshAll} aria-label="刷新行情"><RefreshCw size={15} /></button>
          <button type="button" className="icon-button" onClick={requestFullscreen} aria-label="全屏"><Expand size={15} /></button>
        </div>
      </header>

      <section className="quote-strip">
        <div className="quote-identity">
          <span className="market-badge">{security.market}</span>
          <div><strong>{quote?.name || security.name}</strong><span>{security.symbol} · {quote?.exchange || security.exchange || security.market}</span></div>
        </div>
        <div className={`quote-price ${currentMovement}`}>
          <strong>{formatPrice(quote?.price, security.market === "HK" ? 3 : 2)}</strong>
          <span>{signed(quote?.change, "")} · {signed(quote?.changePct)}</span>
        </div>
        <div className="quote-field"><span>今开</span><strong>{formatPrice(quote?.open)}</strong></div>
        <div className="quote-field"><span>最高</span><strong className="up">{formatPrice(quote?.high)}</strong></div>
        <div className="quote-field"><span>最低</span><strong className="down">{formatPrice(quote?.low)}</strong></div>
        <div className="quote-field"><span>成交额</span><strong>{formatCompact(quote?.amount)}</strong></div>
        <div className="quote-field"><span>换手率</span><strong>{signed(quote?.turnoverPct)}</strong></div>
        <div className="quote-source"><span className={quote ? "live-dot" : "idle-dot"} />{quote?.source || "等待行情"}</div>
      </section>

      {error ? <div className="terminal-alert" role="alert">{error}</div> : null}

      <div className="terminal-workspace">
        <aside className="watch-panel">
          <div className="panel-heading">
            <div><span>自选列表</span><small>{activeGroup?.symbols.length ?? 0} 个标的 · {watchlistSyncLabel}</small></div>
            <button type="button" className="icon-button" onClick={() => setGroupEditor({ mode: "create", value: "" })} aria-label="新建自选分组"><CirclePlus size={15} /></button>
          </div>
          <div className="group-toolbar">
            <label>
              <ListFilter size={14} />
              <select value={activeGroup?.id || ""} onChange={(event) => {
                setActiveGroupId(event.target.value);
                setDeleteConfirmId("");
                setGroupEditor(undefined);
              }} aria-label="自选分组">
                {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
              </select>
              <ChevronDown size={12} />
            </label>
            <button type="button" onClick={() => activeGroup && setGroupEditor({ mode: "rename", value: activeGroup.name })} aria-label="重命名分组"><PencilLine size={13} /></button>
            <button type="button" className={deleteConfirmId === activeGroup?.id ? "delete-armed" : ""} onClick={deleteGroup} disabled={groups.length <= 1} aria-label={deleteConfirmId === activeGroup?.id ? "确认删除分组" : "删除分组"}><Trash2 size={13} /></button>
          </div>
          {groupEditor ? (
            <div className="group-editor">
              <input
                autoFocus
                value={groupEditor.value}
                onChange={(event) => setGroupEditor({ ...groupEditor, value: event.target.value.slice(0, 80) })}
                onKeyDown={(event) => {
                  if (event.key === "Enter") saveGroupEditor();
                  if (event.key === "Escape") setGroupEditor(undefined);
                }}
                aria-label="自选分组名称"
                placeholder="分组名称"
              />
              <button type="button" onClick={saveGroupEditor} disabled={!groupEditor.value.trim()}>保存</button>
              <button type="button" onClick={() => setGroupEditor(undefined)}>取消</button>
            </div>
          ) : null}
          <div className="watch-columns"><span>名称 / 代码</span><span>最新</span><span>涨跌</span></div>
          <div className="watch-list">
            {activeGroup?.symbols.map((item) => {
              const itemQuote = watchQuotes[securityKey(item)];
              const active = securityKey(item) === securityKey(security);
              return (
                <div className={`watch-row ${active ? "active" : ""}`} key={securityKey(item)}>
                  <button type="button" className="watch-row-main" onClick={() => selectSecurity(item)}>
                    <span><strong>{itemQuote?.name || item.name}</strong><small>{item.market} · {item.symbol}</small></span>
                    <b>{formatPrice(itemQuote?.price, item.market === "HK" ? 3 : 2)}</b>
                    <em className={movement(itemQuote?.changePct)}>{signed(itemQuote?.changePct)}</em>
                  </button>
                  <button type="button" className="watch-remove" onClick={() => removeFromActiveGroup(item)} aria-label={`移除 ${item.name}`}><X size={12} /></button>
                </div>
              );
            })}
            {!activeGroup?.symbols.length ? (
              <div className="empty-watch"><Star size={18} /><p>当前分组为空</p><span>从顶部搜索后添加标的</span></div>
            ) : null}
          </div>
        </aside>

        <main className="chart-panel">
          <div className="chart-toolbar">
            <div className="timeframe-group" role="group" aria-label="K 线周期">
              {TIMEFRAMES.map((item) => (
                <button type="button" key={item.id} aria-pressed={timeframe === item.id} onClick={() => setTimeframe(item.id)}>{item.label}</button>
              ))}
            </div>
            <span className="toolbar-divider" />
            <label className="toolbar-select">复权
              <select value={adjustmentDisabled ? "none" : adjustment} disabled={adjustmentDisabled} onChange={(event) => setAdjustment(event.target.value as Adjustment)}>
                <option value="qfq">前复权</option>
                <option value="hfq">后复权</option>
                <option value="none">不复权</option>
              </select>
            </label>
            <label className="toolbar-select">主图
              <select value={primaryIndicator} onChange={(event) => setPrimaryIndicator(event.target.value as PrimaryIndicator)}>
                {PRIMARY_INDICATORS.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
            <label className="toolbar-select">副图
              <select value={secondaryIndicator} onChange={(event) => setSecondaryIndicator(event.target.value as SecondaryIndicator)}>
                {SECONDARY_INDICATORS.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
          </div>
          <div className="chart-stage">
            <div className="drawing-tools" aria-label="画线工具">
              <button type="button" onClick={() => chartRef.current?.draw("segment")} title="趋势线"><LineChart size={15} /></button>
              <button type="button" onClick={() => chartRef.current?.draw("horizontalStraightLine")} title="水平线"><BarChart3 size={15} /></button>
              <button type="button" onClick={() => chartRef.current?.draw("fibonacciLine")} title="斐波那契"><MoveDiagonal2 size={15} /></button>
              <button type="button" onClick={() => chartRef.current?.clearDrawings()} title="清除画线"><Eraser size={15} /></button>
            </div>
            <KLineChartPanel
              ref={chartRef}
              security={security}
              timeframe={timeframe}
              adjustment={adjustmentDisabled ? "none" : adjustment}
              primaryIndicator={primaryIndicator}
              secondaryIndicator={secondaryIndicator}
              theme={theme}
              refreshNonce={refreshNonce}
              loadBars={loadBars}
              onRangeChange={(range) => setVisibleRange({ from: range.from, to: range.to })}
              onLoadState={setChartState}
            />
            {chartState.loading ? <div className="chart-loading"><RefreshCw className="spin" size={16} />正在加载 {timeframe} 行情…</div> : null}
            {chartState.error ? <div className="chart-error">{chartState.error}</div> : null}
          </div>
          <div className="chart-statusbar">
            <span>{chartMeta.source || "行情源待连接"}</span>
            <span>{chartMeta.asOf ? new Date(chartMeta.asOf).toLocaleString("zh-CN") : "—"}</span>
            <span>{primaryIndicator} · {secondaryIndicator}</span>
          </div>
        </main>

        <aside className="market-rail">
          <div className="rail-tabs">
            <button type="button" aria-pressed={railTab === "orderbook"} onClick={() => setRailTab("orderbook")}>盘口</button>
            <button type="button" aria-pressed={railTab === "metrics"} onClick={() => setRailTab("metrics")}>指标</button>
          </div>
          {railTab === "orderbook" ? (
            <div className="order-book">
              <div className="order-head"><span>档位</span><span>价格</span><span>委托量</span></div>
              {displayLevels.length ? displayLevels.map((level) => (
                <div className="order-row" key={`${level.label}-${level.price}`}>
                  <span className={level.side}>{level.label}</span>
                  <strong className={level.side === "ask" ? "down" : "up"}>{formatPrice(level.price, security.market === "HK" ? 3 : 2)}</strong>
                  <span>{formatCompact(level.volume)}</span>
                </div>
              )) : (
                <div className="empty-rail"><BarChart3 size={20} /><p>当前数据源暂无逐档盘口</p><span>港美股仍可使用报价、K 线和核心指标</span></div>
              )}
            </div>
          ) : (
            <div className="metric-list">
              {[
                ["昨收", formatPrice(quote?.prevClose)],
                ["振幅", signed(quote?.amplitudePct)],
                ["量比", formatPrice(quote?.volumeRatio)],
                ["成交量", formatCompact(quote?.volume)],
                ["总市值", formatCompact(quote?.marketCap)],
                ["流通市值", formatCompact(quote?.floatMarketCap)],
                ["市盈率 TTM", formatPrice(quote?.pe)],
                ["市净率", formatPrice(quote?.pb)],
                ["涨停价", formatPrice(quote?.limitUp)],
                ["跌停价", formatPrice(quote?.limitDown)],
              ].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
            </div>
          )}
        </aside>
      </div>

      <section className="bottom-dock">
        <div className="bottom-tabs">
          <button type="button" aria-pressed={bottomTab === "overview"} onClick={() => setBottomTab("overview")}>市场概览</button>
          <button type="button" aria-pressed={bottomTab === "turnover"} onClick={() => setBottomTab("turnover")}>成交额榜</button>
          <button type="button" aria-pressed={bottomTab === "global"} onClick={() => setBottomTab("global")}>全球指数</button>
          <span>{overview?.updated || "实时数据"}</span>
        </div>
        {bottomTab === "overview" ? (
          <div className="overview-grid">
            <div className="breadth-card">
              <div><span>上涨</span><strong className="up">{overview?.sentiment?.up ?? "—"}</strong></div>
              <div><span>下跌</span><strong className="down">{overview?.sentiment?.down ?? "—"}</strong></div>
              <div><span>平盘</span><strong>{overview?.sentiment?.flat ?? "—"}</strong></div>
              <div><span>涨停 / 跌停</span><strong>{overview?.sentiment?.zt ?? "—"} / {overview?.sentiment?.dt ?? "—"}</strong></div>
              <div><span>市场宽度</span><strong>{overview?.sentiment?.breadth || "—"}</strong></div>
            </div>
            <div className="index-ticker-list">
              {indices.map((item, index) => {
                const name = String(item.name ?? item.symbol ?? `指数 ${index + 1}`);
                const changePct = number(item.change_pct ?? item.changePct);
                return <div key={`${name}-${index}`}><span>{name}</span><strong>{formatPrice(item.price)}</strong><em className={movement(changePct)}>{signed(changePct)}</em></div>;
              })}
              {!indices.length ? <p className="empty-copy">A 股指数数据加载中</p> : null}
            </div>
            <div className="sector-flow">
              <div className="section-caption">行业资金与涨跌</div>
              {(overview?.sectors ?? []).slice(0, 8).map((sector) => (
                <div key={sector.name}><span>{sector.name}</span><strong className={movement(sector.pct)}>{signed(sector.pct)}</strong><em>{formatCompact(sector.net)}</em></div>
              ))}
              {!overview?.sectors?.length ? <p className="empty-copy">行业资金数据暂不可用</p> : null}
            </div>
          </div>
        ) : null}
        {bottomTab === "turnover" ? (
          <div className="turnover-table">
            <div className="turnover-head"><span>排名</span><span>标的</span><span>最新</span><span>涨跌幅</span><span>成交额</span></div>
            {turnover.slice(0, 15).map((item, index) => {
              const symbol = String(item.code || item.symbol || "");
              return (
                <button type="button" key={`${symbol}-${index}`} onClick={() => symbol && selectSecurity({ symbol, name: item.name || symbol, market: "CN" })}>
                  <span>{index + 1}</span><span><strong>{item.name || symbol}</strong><small>{symbol}</small></span><span>{formatPrice(item.price)}</span><span className={movement(item.pct ?? item.change_pct)}>{signed(item.pct ?? item.change_pct)}</span><span>{formatCompact(item.amount)}</span>
                </button>
              );
            })}
            {!turnover.length ? <p className="empty-copy">成交额榜加载中</p> : null}
          </div>
        ) : null}
        {bottomTab === "global" ? (
          <div className="global-grid">
            {globalIndices.map((item, index) => {
              const name = String(item.name ?? item.symbol ?? `全球指数 ${index + 1}`);
              const pct = number(item.change_pct ?? item.changePct);
              return <div key={`${name}-${index}`}><span>{name}</span><strong>{formatPrice(item.price)}</strong><em className={movement(pct)}>{signed(pct)}</em><small>{String(item.market ?? item.source ?? "GLOBAL")}</small></div>;
            })}
            {!globalIndices.length ? <p className="empty-copy">全球指数数据加载中</p> : null}
          </div>
        ) : null}
      </section>
    </div>
  );
}

export const MarketPulseApp = MarketTerminalApp;
export const MarketDailyApp = MarketTerminalApp;
export type MarketPulseAppProps = MarketTerminalAppProps;
export type MarketDailyAppProps = MarketTerminalAppProps;
