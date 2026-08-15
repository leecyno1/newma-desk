import { Archive, ExternalLink, Pause, Play, RefreshCcw, SkipForward, TrendingDown, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { KLineChartPanel, type ChartAnnotation } from "@newma-desk/chart-kit";
import { createModSnapshotCache, type ArtifactClient, type ReplayArtifactRecord } from "@newma-desk/mod-sdk";

import type { Bar, MarketDataSource, SecurityRef, Timeframe } from "../types";
import { formatPrice, movement, signed } from "./shared";
import type { WorkspaceUiAction } from "./WorkspaceApp";

interface ReplayOrder {
  id: string;
  side: "buy" | "sell";
  index: number;
  timestamp: number;
  price: number;
}

function formatReplayDate(timestamp?: number) {
  if (!timestamp) return "等待行情";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp < 1_000_000_000_000 ? timestamp * 1000 : timestamp));
}

export function ReplayWorkspace({
  action,
  artifactClient,
  cacheIdentity,
  dataSource,
  security,
  theme,
  refreshNonce,
  onContextChange,
}: {
  action?: WorkspaceUiAction;
  artifactClient: ArtifactClient;
  cacheIdentity?: { userId: string; workspaceId: string };
  dataSource: MarketDataSource;
  security: SecurityRef;
  theme: "light" | "dark";
  refreshNonce: number;
  onContextChange: (value: Record<string, unknown>) => void;
}) {
  const [timeframe, setTimeframe] = useState<Timeframe>("1d");
  const [bars, setBars] = useState<Bar[]>([]);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<1 | 2 | 4>(1);
  const [primaryIndicator, setPrimaryIndicator] = useState<"MA" | "EMA" | "BOLL">("MA");
  const [secondaryIndicator, setSecondaryIndicator] = useState<"VOL" | "MACD" | "RSI" | "KDJ">("VOL");
  const [orders, setOrders] = useState<ReplayOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingArtifact, setSavingArtifact] = useState(false);
  const [savedArtifact, setSavedArtifact] = useState<ReplayArtifactRecord>();
  const [artifactError, setArtifactError] = useState("");
  const [dataError, setDataError] = useState("");
  const cache = useMemo(() => cacheIdentity ? createModSnapshotCache<Bar[]>({
    modId: "trading-replay",
    ...cacheIdentity,
    resourceKey: `bars:${security.market}:${security.symbol}:${timeframe}`,
    maxBytes: 2 * 1024 * 1024,
  }) : undefined, [cacheIdentity?.userId, cacheIdentity?.workspaceId, security.market, security.symbol, timeframe]);
  const cacheKey = cache?.key;
  const resourceKey = `bars:${security.market}:${security.symbol}:${timeframe}`;
  const resourceKeyRef = useRef<string | undefined>(undefined);
  const cacheKeyRef = useRef<string | undefined>(undefined);
  const barsRef = useRef(bars);
  barsRef.current = bars;

  useEffect(() => {
    if (!action) return;
    if (action.actionId === "market.set-timeframe") setTimeframe(action.input.timeframe as Timeframe);
    if (action.actionId === "chart.set-indicator") {
      if (action.input.position === "primary") setPrimaryIndicator(action.input.indicator as typeof primaryIndicator);
      if (action.input.position === "secondary") setSecondaryIndicator(action.input.indicator as typeof secondaryIndicator);
    }
  }, [action]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setDataError("");
    setPlaying(false);
    const cached = cache?.read()?.value;
    const resourceChanged = resourceKeyRef.current !== resourceKey;
    const cacheChanged = cacheKeyRef.current !== cacheKey;
    resourceKeyRef.current = resourceKey;
    cacheKeyRef.current = cacheKey;
    if (resourceChanged) {
      if (cached?.length) {
        setBars(cached);
        setCursor(Math.min(Math.max(60, Math.round(cached.length * 0.35)), cached.length));
      } else {
        setBars([]);
        setCursor(0);
      }
      setOrders([]);
    } else if (cacheChanged && cached?.length && barsRef.current.length === 0) {
      setBars(cached);
      setCursor(Math.min(Math.max(60, Math.round(cached.length * 0.35)), cached.length));
    }
    void dataSource.ohlcv(security, timeframe, security.market === "CN" && timeframe === "1d" ? "qfq" : "none")
      .then((result) => {
        if (!active) return;
        setBars(result.items);
        setCursor(Math.min(Math.max(60, Math.round(result.items.length * 0.35)), result.items.length));
        setOrders([]);
        cache?.write(result.items, result.asOf);
      })
      .catch(() => {
        if (!active) return;
        setDataError((cached?.length || (!resourceChanged && barsRef.current.length))
          ? "更新失败，当前为上次数据"
          : "历史行情暂不可用");
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [cacheKey, dataSource, refreshNonce, security.market, security.symbol, timeframe]);

  useEffect(() => {
    if (!playing || cursor >= bars.length) return;
    const timer = window.setInterval(() => {
      setCursor((value) => {
        const next = Math.min(value + 1, bars.length);
        if (next >= bars.length) setPlaying(false);
        return next;
      });
    }, 900 / speed);
    return () => window.clearInterval(timer);
  }, [bars.length, cursor, playing, speed]);

  const visibleBars = useMemo(() => bars.slice(0, cursor), [bars, cursor]);
  const currentBar = visibleBars.at(-1);
  const previousBar = visibleBars.at(-2);
  const currentChange = currentBar && previousBar && previousBar.close
    ? ((currentBar.close / previousBar.close) - 1) * 100
    : undefined;
  const position = orders.reduce((value, order) => value + (order.side === "buy" ? 1 : -1), 0);
  const cashFlow = orders.reduce((value, order) => value + (order.side === "buy" ? -order.price : order.price), 0);
  const equity = cashFlow + position * (currentBar?.close ?? 0);
  const loadBars = useCallback(async () => visibleBars, [visibleBars]);
  const annotations = useMemo<ChartAnnotation[]>(() => orders.map((order) => ({
    id: `replay-${order.id}`.replace(/[^A-Za-z0-9_-]/g, "-").slice(0, 64),
    timestamp: order.timestamp,
    value: order.price,
    label: order.side === "buy" ? "模拟买入" : "模拟卖出",
    tone: order.side === "buy" ? "positive" : "negative",
  })), [orders]);

  useEffect(() => {
    let active = true;
    void artifactClient.listReplays("trading-replay")
      .then((artifacts) => active && setSavedArtifact(artifacts[0]))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [artifactClient]);

  useEffect(() => {
    onContextChange({
      timeframe,
      replayCursor: cursor,
      totalBars: bars.length,
      hiddenFutureBars: Math.max(bars.length - cursor, 0),
      replayDate: currentBar?.timestamp ?? null,
      playing,
      speed,
      primaryIndicator,
      secondaryIndicator,
      simulatedPosition: position,
      simulatedPnl: Number(equity.toFixed(2)),
      orders: orders.slice(-12).map((order) => ({ side: order.side, timestamp: order.timestamp, price: order.price })),
      latestArtifact: savedArtifact ? {
        id: savedArtifact.id,
        title: savedArtifact.title,
        status: savedArtifact.status,
        viewUrl: artifactClient.viewUrl(savedArtifact),
      } : null,
    });
  }, [artifactClient, bars.length, currentBar?.timestamp, cursor, equity, onContextChange, orders, playing, position, primaryIndicator, savedArtifact, secondaryIndicator, speed, timeframe]);

  const recordOrder = (side: ReplayOrder["side"]) => {
    if (!currentBar || (side === "sell" && position <= 0)) return;
    setOrders((current) => [...current, {
      id: `${side}-${currentBar.timestamp}-${current.length}`,
      side,
      index: cursor,
      timestamp: currentBar.timestamp,
      price: currentBar.close,
    }]);
  };

  const reset = () => {
    setPlaying(false);
    setOrders([]);
    setCursor(Math.min(Math.max(60, Math.round(bars.length * 0.35)), bars.length));
  };

  const saveReplayArtifact = async () => {
    if (!currentBar || !bars.length || savingArtifact) return;
    setSavingArtifact(true);
    setArtifactError("");
    try {
      const artifact = await artifactClient.createReplay({
        moduleId: "trading-replay",
        title: `${security.name} ${timeframe === "1d" ? "日线" : timeframe} 回放 · ${formatReplayDate(currentBar.timestamp)}`,
        security: {
          symbol: security.symbol,
          name: security.name,
          market: security.market,
          ...(security.exchange ? { exchange: security.exchange } : {}),
        },
        timeframe,
        cursor,
        totalBars: bars.length,
        replayTimestamp: currentBar.timestamp,
        orders,
        metrics: {
          position,
          simulatedPnl: Number(equity.toFixed(4)),
          decisionCount: orders.length,
          hiddenFutureBars: Math.max(bars.length - cursor, 0),
        },
        metadata: { source: "market-data", simulationOnly: true },
      });
      setSavedArtifact(artifact);
    } catch (reason) {
      setArtifactError(reason instanceof Error ? reason.message : "回放沉淀失败");
    } finally {
      setSavingArtifact(false);
    }
  };

  return (
    <div className="replay-workspace">
      <section className="replay-chart-panel">
        <div className="replay-toolbar">
          <div className="workspace-segment" role="group" aria-label="回放周期">
            {(["5m", "15m", "60m", "1d"] as Timeframe[]).map((item) => (
              <button type="button" key={item} aria-pressed={timeframe === item} onClick={() => setTimeframe(item)}>{item === "1d" ? "日线" : item}</button>
            ))}
          </div>
          <button type="button" className="replay-play" disabled={!bars.length} onClick={() => setPlaying((value) => !value)}>
            {playing ? <Pause size={14} /> : <Play size={14} />}{playing ? "暂停" : "播放"}
          </button>
          <button type="button" disabled={cursor >= bars.length} onClick={() => setCursor((value) => Math.min(value + 1, bars.length))}><SkipForward size={14} />下一根</button>
          <button type="button" onClick={reset}><RefreshCcw size={14} />重置</button>
          <button type="button" disabled={!currentBar || savingArtifact} onClick={() => void saveReplayArtifact()}><Archive size={14} />{savingArtifact ? "沉淀中" : "沉淀回放"}</button>
          <div className="workspace-segment replay-speed" role="group" aria-label="回放速度">
            {([1, 2, 4] as const).map((item) => <button type="button" key={item} aria-pressed={speed === item} onClick={() => setSpeed(item)}>{item}×</button>)}
          </div>
          <span className="replay-date">{formatReplayDate(currentBar?.timestamp)}</span>
        </div>
        <div className="replay-chart-wrap">
          {loading && !bars.length ? <div className="workspace-chart-loading">正在准备历史行情…</div> : null}
          {loading && bars.length ? <div className="workspace-update-note"><RefreshCcw className="spin" size={13} />更新中，当前展示上次数据</div> : null}
          {!loading && dataError ? <div className="workspace-update-note workspace-error">{dataError}</div> : null}
          <KLineChartPanel
            security={security}
            timeframe={timeframe}
            adjustment={security.market === "CN" && timeframe === "1d" ? "qfq" : "none"}
            primaryIndicator={primaryIndicator}
            secondaryIndicator={secondaryIndicator}
            theme={theme}
            refreshNonce={refreshNonce + cursor}
            loadBars={loadBars}
            annotations={annotations}
            ariaLabel="交易回放 K 线图"
          />
          <div className="future-mask-label">未来数据已隐藏 · {Math.max(bars.length - cursor, 0)} 根</div>
        </div>
        <div className="replay-scrubber">
          <span>{cursor}</span>
          <input
            aria-label="回放进度"
            type="range"
            min={Math.min(20, bars.length)}
            max={Math.max(bars.length, 20)}
            value={Math.max(cursor, Math.min(20, bars.length))}
            onChange={(event) => {
              setPlaying(false);
              setCursor(Number(event.target.value));
            }}
          />
          <span>{bars.length}</span>
        </div>
      </section>
      <aside className="replay-ledger-panel">
        <div className="workspace-section-title"><span>模拟决策</span><small>每次 1 单位</small></div>
        <div className="replay-current">
          <span>当前收盘</span>
          <strong>{formatPrice(currentBar?.close)}</strong>
          <em className={movement(currentChange)}>{signed(currentChange)}</em>
        </div>
        <div className="replay-actions">
          <button type="button" className="replay-buy" disabled={!currentBar} onClick={() => recordOrder("buy")}><TrendingUp size={15} />模拟买入</button>
          <button type="button" className="replay-sell" disabled={!currentBar || position <= 0} onClick={() => recordOrder("sell")}><TrendingDown size={15} />模拟卖出</button>
        </div>
        <dl className="replay-stats">
          <div><dt>持仓单位</dt><dd>{position}</dd></div>
          <div><dt>模拟盈亏</dt><dd className={movement(equity)}>{equity > 0 ? "+" : ""}{formatPrice(equity)}</dd></div>
          <div><dt>决策次数</dt><dd>{orders.length}</dd></div>
        </dl>
        <div className="replay-orders">
          {savedArtifact ? (
            <a className="replay-artifact-link" href={artifactClient.viewUrl(savedArtifact)} target="_blank" rel="noreferrer"><Archive size={13} /><span><strong>最近沉淀</strong><small>{savedArtifact.title}</small></span><ExternalLink size={12} /></a>
          ) : null}
          {artifactError ? <div className="workspace-error replay-artifact-error">{artifactError}</div> : null}
          {orders.slice().reverse().map((order) => (
            <div key={order.id}>
              <i className={order.side === "buy" ? "up" : "down"}>{order.side === "buy" ? "买" : "卖"}</i>
              <span><strong>{formatPrice(order.price)}</strong><small>{formatReplayDate(order.timestamp)}</small></span>
            </div>
          ))}
          {!orders.length ? <div className="workspace-empty">逐根观察并记录你的第一笔模拟决策</div> : null}
        </div>
        <p className="workspace-help">回放仅用于训练和复盘，不产生真实订单，也不会连接交易执行权限。</p>
      </aside>
    </div>
  );
}
