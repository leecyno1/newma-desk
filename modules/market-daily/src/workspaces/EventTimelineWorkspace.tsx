import { Bookmark, BookmarkCheck, CalendarRange, ExternalLink, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { KLineChartPanel, type ChartAnnotation } from "@newma-desk/chart-kit";
import { createModSnapshotCache } from "@newma-desk/mod-sdk";

import { marketEvidenceToCatalyst } from "../catalysts";
import { isEtfSecurity, isOpenFundSecurity } from "../data";
import type {
  Bar,
  MarketDataSource,
  MarketEventFeed,
  MarketEvidenceEvent,
  MarketEvidenceEventType,
  Quote,
  SecurityRef,
} from "../types";
import { formatCompact, formatPrice, signed } from "./shared";
import type { WorkspaceUiAction } from "./WorkspaceApp";

export type DerivedMarketEventType = "price" | "volume" | "breakout" | "distribution";

export interface DerivedMarketEvent {
  id: string;
  timestamp: number;
  type: DerivedMarketEventType;
  title: string;
  detail: string;
  score: number;
}

type EventFilter = "all" | "derived" | MarketEvidenceEventType;
type TimelineEvent = (DerivedMarketEvent & { origin: "derived"; source: string; evidenceId: string })
  | (MarketEvidenceEvent & { origin: "evidence"; score: number });

const STOCK_FILTERS: ReadonlyArray<{ id: EventFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "announcement", label: "公告" },
  { id: "earnings", label: "财报" },
  { id: "news", label: "新闻" },
  { id: "research", label: "研报" },
  { id: "derived", label: "量价" },
];

const ETF_FILTERS: ReadonlyArray<{ id: EventFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "announcement", label: "基金公告" },
  { id: "news", label: "ETF资讯" },
  { id: "derived", label: "量价" },
];

const FUND_FILTERS: ReadonlyArray<{ id: EventFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "announcement", label: "基金公告" },
  { id: "derived", label: "净值" },
];

const EMPTY_EVENT_FEED: MarketEventFeed = { items: [], sources: [], asOf: "" };

export function selectChartTimelineEvents<
  T extends { id: string; timestamp: number; type: string },
>(events: T[], selectedId = "", limit = 8): T[] {
  const selected = events.find((event) => event.id === selectedId);
  const result: T[] = selected ? [selected] : [];
  const seen = new Set<string>();
  if (selected) {
    const timestamp = selected.timestamp < 1_000_000_000_000
      ? selected.timestamp * 1000
      : selected.timestamp;
    seen.add(new Date(timestamp).toISOString().slice(0, 10));
  }
  for (const event of events) {
    if (result.length >= limit) break;
    if (event.id === selectedId) continue;
    const timestamp = event.timestamp < 1_000_000_000_000
      ? event.timestamp * 1000
      : event.timestamp;
    const key = new Date(timestamp).toISOString().slice(0, 10);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(event);
  }
  return result;
}

export function selectFundChartTimelineEvents<
  T extends { id: string; timestamp: number; type: string; origin?: string; score?: number },
>(events: T[], selectedId = "", limit = 5): T[] {
  const result: T[] = [];
  const seenDays = new Set<string>();
  const add = (event?: T) => {
    if (!event || result.length >= limit || result.some((item) => item.id === event.id)) return false;
    const timestamp = event.timestamp < 1_000_000_000_000 ? event.timestamp * 1000 : event.timestamp;
    const day = new Date(timestamp).toISOString().slice(0, 10);
    if (seenDays.has(day)) return false;
    seenDays.add(day);
    result.push(event);
    return true;
  };

  add(events.find((event) => event.id === selectedId));
  add([...events]
    .filter((event) => event.type === "distribution")
    .sort((left, right) => right.timestamp - left.timestamp)[0]);

  let evidenceCount = 0;
  for (const event of [...events]
    .filter((item) => item.origin === "evidence" || item.type === "announcement")
    .sort((left, right) => right.timestamp - left.timestamp)) {
    if (add(event)) evidenceCount += 1;
    if (evidenceCount >= 2 || result.length >= limit) break;
  }

  for (const event of [...events]
    .filter((item) => item.origin === "derived" && item.type !== "distribution")
    .sort((left, right) => (right.score ?? 0) - (left.score ?? 0) || right.timestamp - left.timestamp)) {
    add(event);
    if (result.length >= limit) break;
  }

  for (const event of [...events].sort((left, right) => right.timestamp - left.timestamp)) {
    add(event);
    if (result.length >= limit) break;
  }
  return result.sort((left, right) => right.timestamp - left.timestamp);
}

function eventDate(timestamp: number) {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(
    new Date(timestamp < 1_000_000_000_000 ? timestamp * 1000 : timestamp),
  );
}

function fundAnnotationLabel(event: TimelineEvent) {
  if (event.type === "distribution") return "分红 / 拆分";
  if (event.type === "announcement") {
    return `公告 · ${event.title.length > 12 ? `${event.title.slice(0, 12)}…` : event.title}`;
  }
  if (event.type === "price") return `净值 ${event.detail.replace(/^当日涨跌幅\s*/, "")}`;
  if (event.type === "breakout") return "净值阶段新高";
  return event.title;
}

export function deriveMarketEvents(
  bars: Bar[],
  priceThresholdPct = 3,
  options: { includeVolume?: boolean; priceLabel?: string } = {},
): DerivedMarketEvent[] {
  const result: DerivedMarketEvent[] = [];
  let rollingHigh = -Infinity;
  const recentVolumes: number[] = [];
  const includeVolume = options.includeVolume ?? true;
  const priceLabel = options.priceLabel ?? "价格";
  for (let index = 0; index < bars.length; index += 1) {
    const bar = bars[index];
    const previous = bars[index - 1];
    if (!bar) continue;
    if (bar.navEvent) {
      result.push({
        id: `distribution-${bar.timestamp}`,
        timestamp: bar.timestamp,
        type: "distribution",
        title: "基金分红 / 拆分",
        detail: bar.navEvent,
        score: 8,
      });
    }
    if (!previous) {
      rollingHigh = Math.max(rollingHigh, bar.high);
      if (includeVolume) recentVolumes.push(bar.volume ?? 0);
      continue;
    }
    const changePct = previous.close ? ((bar.close / previous.close) - 1) * 100 : 0;
    const averageVolume = recentVolumes.length
      ? recentVolumes.reduce((sum, value) => sum + value, 0) / recentVolumes.length
      : 0;
    if (Math.abs(changePct) >= priceThresholdPct) {
      result.push({
        id: `price-${bar.timestamp}`,
        timestamp: bar.timestamp,
        type: "price",
        title: changePct > 0 ? `${priceLabel}快速上行` : `${priceLabel}快速回落`,
        detail: `当日涨跌幅 ${signed(changePct)}`,
        score: Math.abs(changePct),
      });
    }
    if (includeVolume && (bar.volume ?? 0) > 0 && averageVolume > 0 && (bar.volume ?? 0) / averageVolume >= 1.8) {
      const ratio = (bar.volume ?? 0) / averageVolume;
      result.push({
        id: `volume-${bar.timestamp}`,
        timestamp: bar.timestamp,
        type: "volume",
        title: "成交量显著放大",
        detail: `约为近 20 日均量的 ${ratio.toFixed(1)} 倍`,
        score: ratio * 2,
      });
    }
    if (rollingHigh > 0 && bar.close > rollingHigh && index >= 20) {
      result.push({
        id: `breakout-${bar.timestamp}`,
        timestamp: bar.timestamp,
        type: "breakout",
        title: `${priceLabel}创阶段新高`,
        detail: `突破此前阶段高点，收于 ${bar.close.toFixed(priceLabel === "单位净值" ? 4 : 2)}`,
        score: 4,
      });
    }
    rollingHigh = Math.max(rollingHigh, bar.high);
    if (includeVolume) {
      recentVolumes.push(bar.volume ?? 0);
      if (recentVolumes.length > 20) recentVolumes.shift();
    }
  }
  return [...result]
    .sort((left, right) => right.score - left.score)
    .slice(0, 24)
    .sort((left, right) => right.timestamp - left.timestamp);
}

export function EventTimelineWorkspace({
  action,
  cacheIdentity,
  dataSource,
  security,
  quote,
  theme,
  refreshNonce,
  onContextChange,
}: {
  action?: WorkspaceUiAction;
  cacheIdentity?: { userId: string; workspaceId: string };
  dataSource: MarketDataSource;
  security: SecurityRef;
  quote?: Quote;
  theme: "light" | "dark";
  refreshNonce: number;
  onContextChange: (value: Record<string, unknown>) => void;
}) {
  const isEtf = isEtfSecurity(security);
  const isFund = isOpenFundSecurity(security);
  const assetKind = isFund ? "fund" : isEtf ? "etf" : (security.assetType || "stock");
  const filters = isFund ? FUND_FILTERS : isEtf ? ETF_FILTERS : STOCK_FILTERS;
  const [bars, setBars] = useState<Bar[]>([]);
  const [feed, setFeed] = useState<MarketEventFeed>(EMPTY_EVENT_FEED);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<EventFilter>("all");
  const [selectedEventId, setSelectedEventId] = useState("");
  const [primaryIndicator, setPrimaryIndicator] = useState<"MA" | "EMA" | "BOLL">("MA");
  const [secondaryIndicator, setSecondaryIndicator] = useState<"VOL" | "MACD" | "RSI" | "KDJ">("VOL");
  const barsCache = useMemo(() => cacheIdentity ? createModSnapshotCache<Bar[]>({
    modId: "event-timeline",
    ...cacheIdentity,
    resourceKey: `bars:${assetKind}:${security.market}:${security.symbol}`,
    maxBytes: 2 * 1024 * 1024,
  }) : undefined, [assetKind, cacheIdentity?.userId, cacheIdentity?.workspaceId, security.market, security.symbol]);
  const feedCache = useMemo(() => cacheIdentity ? createModSnapshotCache<MarketEventFeed>({
    modId: "event-timeline",
    ...cacheIdentity,
    resourceKey: `events:${assetKind}:${security.market}:${security.symbol}`,
    maxBytes: 1024 * 1024,
  }) : undefined, [assetKind, cacheIdentity?.userId, cacheIdentity?.workspaceId, security.market, security.symbol]);
  const barsCacheKey = barsCache?.key;
  const feedCacheKey = feedCache?.key;
  const resourceKeyRef = useRef<string | undefined>(undefined);
  const cacheKeyRef = useRef<string | undefined>(undefined);
  const barsRef = useRef(bars);
  const feedRef = useRef(feed);
  barsRef.current = bars;
  feedRef.current = feed;
  const storageKey = `vibedesk.event-timeline.saved.${assetKind}.${security.market}.${security.symbol}.v1`;
  const [saved, setSaved] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(window.localStorage.getItem(storageKey) || "[]") as string[]);
    } catch {
      return new Set();
    }
  });

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const cachedBars = barsCache?.read()?.value;
    const cachedFeed = feedCache?.read()?.value;
    const resourceKey = `${assetKind}:${security.market}:${security.symbol}`;
    const cacheKey = `${barsCacheKey ?? "no-bars-cache"}|${feedCacheKey ?? "no-feed-cache"}`;
    const resourceChanged = resourceKeyRef.current !== resourceKey;
    const cacheChanged = cacheKeyRef.current !== cacheKey;
    resourceKeyRef.current = resourceKey;
    cacheKeyRef.current = cacheKey;
    if (resourceChanged) {
      setBars(cachedBars ?? []);
      setFeed(cachedFeed ?? EMPTY_EVENT_FEED);
      setSelectedEventId("");
    } else if (cacheChanged) {
      if (cachedBars?.length && barsRef.current.length === 0) setBars(cachedBars);
      if (cachedFeed?.items.length && feedRef.current.items.length === 0) setFeed(cachedFeed);
    }
    void Promise.allSettled([
      dataSource.ohlcv(security, "1d", isFund ? "none" : security.market === "CN" ? "qfq" : "none"),
      dataSource.events(security),
    ])
      .then(([barResult, eventResult]) => {
        if (!active) return;
        if (barResult.status === "fulfilled") {
          setBars(barResult.value.items);
          if (barResult.value.items.length) barsCache?.write(barResult.value.items, barResult.value.asOf);
        }
        if (eventResult.status === "fulfilled") {
          setFeed(eventResult.value);
          feedCache?.write(eventResult.value, eventResult.value.asOf);
        }
        if (barResult.status === "rejected" || barResult.value.items.length === 0 || eventResult.status === "rejected") {
          const hasLastData = Boolean(
            (barResult.status === "fulfilled" ? barResult.value.items.length : cachedBars?.length || (!resourceChanged && barsRef.current.length))
            || (eventResult.status === "fulfilled" ? eventResult.value.items.length : cachedFeed?.items.length || (!resourceChanged && feedRef.current.items.length)),
          );
          setError(hasLastData ? "部分更新失败，当前保留上次数据" : "日线时间轴数据暂不可用");
        }
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [assetKind, barsCacheKey, dataSource, feedCacheKey, isFund, refreshNonce, security.market, security.symbol]);

  useEffect(() => {
    try {
      const values = JSON.parse(window.localStorage.getItem(storageKey) || "[]") as string[];
      setSaved(new Set(values));
    } catch {
      setSaved(new Set());
    }
  }, [storageKey]);

  useEffect(() => {
    if (!filters.some((item) => item.id === filter)) setFilter("all");
  }, [filter, filters]);

  useEffect(() => {
    if (isFund && secondaryIndicator === "VOL") setSecondaryIndicator("MACD");
  }, [isFund, secondaryIndicator]);

  useEffect(() => {
    if (action?.actionId !== "chart.set-indicator") return;
    if (action.input.position === "primary") setPrimaryIndicator(action.input.indicator as typeof primaryIndicator);
    if (action.input.position === "secondary") setSecondaryIndicator(action.input.indicator as typeof secondaryIndicator);
  }, [action]);

  const events = useMemo<TimelineEvent[]>(() => {
    const derived = deriveMarketEvents(
      bars,
      isFund ? 1 : isEtf ? 1.5 : 3,
      isFund ? { includeVolume: false, priceLabel: "单位净值" } : {},
    ).map((event) => ({
      ...event,
      origin: "derived" as const,
      source: isFund ? "基金净值规则" : "OHLCV 规则引擎",
      evidenceId: `${isFund ? "nav" : "ohlcv"}:${event.id}`,
    }));
    const evidence = feed.items.map((event) => ({ ...event, origin: "evidence" as const, score: 10 }));
    return [...evidence, ...derived].sort((left, right) => right.timestamp - left.timestamp);
  }, [bars, feed.items, isEtf, isFund]);
  const visibleEvents = filter === "all"
    ? events
    : filter === "derived"
      ? events.filter((event) => event.origin === "derived")
      : events.filter((event) => event.type === filter);
  const selectedEvent = events.find((event) => event.id === selectedEventId);
  const chartEvents = useMemo(
    () => isFund
      ? selectFundChartTimelineEvents(visibleEvents, selectedEventId)
      : selectChartTimelineEvents(visibleEvents, selectedEventId),
    [isFund, selectedEventId, visibleEvents],
  );
  const loadBars = useCallback(async () => bars, [bars]);
  const annotations = useMemo<ChartAnnotation[]>(() => chartEvents.flatMap((event) => {
    if (!bars.length) return [];
    const nearest = bars.reduce((best, bar) => (
      Math.abs(bar.timestamp - event.timestamp) < Math.abs(best.timestamp - event.timestamp) ? bar : best
    ), bars[0]!);
    const fullLabel = isFund
      ? fundAnnotationLabel(event)
      : event.origin === "derived" ? event.title : `${event.source} · ${event.title}`;
    return [{
      id: `event-${event.id}`.replace(/[^A-Za-z0-9_-]/g, "-").slice(0, 64),
      timestamp: nearest.timestamp,
      value: isFund ? nearest.close : nearest.high,
      label: fullLabel.length > 26 ? `${fullLabel.slice(0, 25)}…` : fullLabel,
      tone: event.type === "price"
        ? (event.title.includes("回落") ? "negative" : "positive")
        : event.type === "earnings" || event.type === "announcement"
          ? "warning"
          : "info",
    }];
  }), [bars, chartEvents, isFund]);

  useEffect(() => {
    onContextChange({
      timeframe: "1d",
      timelineMode: "daily",
      assetType: assetKind,
      primaryIndicator,
      secondaryIndicator,
      filter,
      ...(isFund ? {
        fundProfile: {
          type: quote?.fundType || security.securityType || "开放式基金",
          company: quote?.fundCompany || "",
          manager: quote?.fundManager || "",
          navDate: quote?.navDate || "",
          subscribeStatus: quote?.subscribeStatus || "",
          redeemStatus: quote?.redeemStatus || "",
        },
      } : {}),
      selectedEvent: selectedEvent ? {
        origin: selectedEvent.origin,
        type: selectedEvent.type,
        title: selectedEvent.title,
        detail: selectedEvent.detail,
        timestamp: selectedEvent.timestamp,
        source: selectedEvent.source,
        evidenceId: selectedEvent.evidenceId,
      } : null,
      eventCount: visibleEvents.length,
      savedCount: saved.size,
      events: visibleEvents.slice(0, 12).map((event) => ({
        origin: event.origin,
        type: event.type,
        title: event.title,
        timestamp: event.timestamp,
        detail: event.detail,
        source: event.source,
        evidenceId: event.evidenceId,
        ...(event.origin === "evidence" && event.url ? { url: event.url } : {}),
      })),
      catalystContract: "newma-desk.catalyst-calendar.v1",
      catalysts: visibleEvents
        .filter((event): event is TimelineEvent & { origin: "evidence" } => event.origin === "evidence")
        .slice(0, 12)
        .map((event) => marketEvidenceToCatalyst(event, security)),
      sources: feed.sources,
    });
  }, [assetKind, feed.sources, filter, isFund, onContextChange, primaryIndicator, quote, saved.size, secondaryIndicator, security, selectedEvent, visibleEvents]);

  const toggleSaved = (event: TimelineEvent) => {
    setSaved((current) => {
      const next = new Set(current);
      if (next.has(event.id)) next.delete(event.id);
      else next.add(event.id);
      window.localStorage.setItem(storageKey, JSON.stringify([...next]));
      return next;
    });
  };

  return (
    <div className="event-workspace">
      <section className="event-chart-panel">
        <div className="workspace-section-title">
          <span><CalendarRange size={14} />日线时间轴</span>
          <small>{bars.length ? `${isFund ? "开放式基金 · " : isEtf ? "ETF · " : ""}${bars.length} 个${isFund ? "净值日" : "交易日"}` : "等待数据"}</small>
        </div>
        {loading && !bars.length ? <div className="workspace-chart-loading"><RefreshCw className="spin" size={16} />正在生成日线时间轴…</div> : null}
        {loading && bars.length ? <div className="workspace-update-note"><RefreshCw className="spin" size={13} />更新中，当前展示上次数据</div> : null}
        {!loading && error ? <div className="workspace-update-note workspace-error">{error}</div> : null}
        <KLineChartPanel
          key={`${assetKind}:${security.market}:${security.symbol}`}
          security={security}
          timeframe="1d"
          adjustment={isFund ? "none" : security.market === "CN" ? "qfq" : "none"}
          variant={isFund ? "nav" : "candlestick"}
          primaryIndicator={primaryIndicator}
          secondaryIndicator={secondaryIndicator}
          theme={theme}
          refreshNonce={refreshNonce + bars.length}
          loadBars={loadBars}
          annotations={annotations}
          ariaLabel={isFund ? "基金净值日线图" : "日线时间轴 K 线图"}
        />
        <div className="event-marker-strip" aria-label="事件日期标记">
          {chartEvents.slice().reverse().map((event) => (
            <button
              type="button"
              key={event.id}
              className={`event-marker event-${event.type}`}
              aria-pressed={event.id === selectedEventId}
              title={`${eventDate(event.timestamp)} ${event.title}`}
              onClick={() => setSelectedEventId(event.id)}
            >
              <i />{eventDate(event.timestamp)}
            </button>
          ))}
        </div>
      </section>
      <aside className="event-list-panel">
        <div className="workspace-section-title"><span>{isFund ? "基金净值事件" : isEtf ? "ETF 日线事件" : "日线事件"}</span><small>{visibleEvents.length} 条</small></div>
        <div className="workspace-segment event-filters" role="group" aria-label="事件筛选">
          {filters.map(({ id, label }) => (
            <button type="button" key={id} aria-pressed={filter === id} onClick={() => setFilter(id)}>
              {label}
            </button>
          ))}
        </div>
        <div className="event-list">
          {visibleEvents.map((event) => (
            <article key={event.id} data-selected={event.id === selectedEventId}>
              <button type="button" className="event-main" onClick={() => setSelectedEventId(event.id)}>
                <span><i className={`event-dot event-${event.type}`} />{eventDate(event.timestamp)}</span>
                <strong>{event.title}</strong>
                <small>{event.detail}</small>
                <em>{event.source} · #{event.evidenceId}</em>
              </button>
              {event.origin === "evidence" && event.url ? (
                <a className="event-source-link" href={event.url} target="_blank" rel="noreferrer" aria-label={`打开证据来源 ${event.title}`}><ExternalLink size={13} /></a>
              ) : null}
              <button type="button" className="event-save" aria-label={`${saved.has(event.id) ? "取消沉淀" : "沉淀"} ${event.title}`} onClick={() => toggleSaved(event)}>
                {saved.has(event.id) ? <BookmarkCheck size={14} /> : <Bookmark size={14} />}
              </button>
            </article>
          ))}
          {!loading && visibleEvents.length === 0 ? <div className="workspace-empty">当前区间没有匹配事件</div> : null}
        </div>
        <div className="event-summary">
          <strong>{isFund ? "基金时间轴构成" : isEtf ? "ETF 时间轴构成" : "证据源状态"}</strong>
          <span>{isFund
            ? "单位净值、净值异动、阶段新高、分红拆分与基金公告按交易日对齐。"
            : isEtf
              ? "基金公告与 ETF 资讯按交易日对齐；涨跌、放量和突破事件由真实日线 OHLCV 推导。"
            : security.market === "CN"
              ? "公告、研报和新闻保留来源与证据 ID；量价事件由真实日线 OHLCV 推导。"
              : "当前海外标的仅显示日线 OHLCV 量价事件，公告与新闻源尚未启用。"}</span>
          {isEtf || isFund ? (
            <div className="event-source-statuses" aria-label={isFund ? "基金时间轴构成" : "ETF 时间轴构成"}>
              {(isFund
                ? ["单位净值", "±1% 净值异动", "阶段新高", "分红 / 拆分", "基金公告"]
                : ["日 K", "±1.5% 异动", "成交量", "阶段突破", "基金公告", "ETF资讯"]
              ).map((item) => <i key={item}>{item}</i>)}
            </div>
          ) : null}
          <div className="event-source-statuses">
            {feed.sources.map((source) => <i key={source.id} data-status={source.status}>{source.label} {source.count}</i>)}
          </div>
          {isFund ? (
            <>
              <div className="event-fund-profile">
                <i>{quote?.fundType || security.securityType || "开放式基金"}</i>
                {quote?.fundCompany ? <i>{quote.fundCompany}</i> : null}
                {quote?.fundManager ? <i>经理 {quote.fundManager}</i> : null}
              </div>
              <small>净值日 {quote?.navDate || "—"} · {quote?.subscribeStatus || "申购状态待更新"} · {quote?.redeemStatus || "赎回状态待更新"}</small>
              <small>单位净值 {formatPrice(bars.at(-1)?.close, 4)} · 累计净值 {formatPrice(bars.at(-1)?.cumulativeNav, 4)}</small>
            </>
          ) : <small>累计成交量 {formatCompact(bars.reduce((sum, bar) => sum + (bar.volume ?? 0), 0))}</small>}
        </div>
      </aside>
    </div>
  );
}
