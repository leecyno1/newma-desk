import { Bookmark, BookmarkCheck, CalendarRange, ExternalLink, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { KLineChartPanel, type ChartAnnotation } from "@newma-dock/chart-kit";

import type {
  Bar,
  MarketDataSource,
  MarketEventFeed,
  MarketEvidenceEvent,
  MarketEvidenceEventType,
  SecurityRef,
} from "../types";
import { formatCompact, movement, signed } from "./shared";
import type { WorkspaceUiAction } from "./WorkspaceApp";

export type DerivedMarketEventType = "price" | "volume" | "breakout";

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

function eventDate(timestamp: number) {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(
    new Date(timestamp < 1_000_000_000_000 ? timestamp * 1000 : timestamp),
  );
}

export function deriveMarketEvents(bars: Bar[]): DerivedMarketEvent[] {
  const result: DerivedMarketEvent[] = [];
  let rollingHigh = -Infinity;
  const recentVolumes: number[] = [];
  for (let index = 1; index < bars.length; index += 1) {
    const bar = bars[index];
    const previous = bars[index - 1];
    if (!bar || !previous) continue;
    const changePct = previous.close ? ((bar.close / previous.close) - 1) * 100 : 0;
    const averageVolume = recentVolumes.length
      ? recentVolumes.reduce((sum, value) => sum + value, 0) / recentVolumes.length
      : 0;
    if (Math.abs(changePct) >= 3) {
      result.push({
        id: `price-${bar.timestamp}`,
        timestamp: bar.timestamp,
        type: "price",
        title: changePct > 0 ? "价格快速上行" : "价格快速回落",
        detail: `当期涨跌幅 ${signed(changePct)}`,
        score: Math.abs(changePct),
      });
    }
    if ((bar.volume ?? 0) > 0 && averageVolume > 0 && (bar.volume ?? 0) / averageVolume >= 1.8) {
      const ratio = (bar.volume ?? 0) / averageVolume;
      result.push({
        id: `volume-${bar.timestamp}`,
        timestamp: bar.timestamp,
        type: "volume",
        title: "成交量显著放大",
        detail: `约为近 20 期均量的 ${ratio.toFixed(1)} 倍`,
        score: ratio * 2,
      });
    }
    if (rollingHigh > 0 && bar.close > rollingHigh && index >= 20) {
      result.push({
        id: `breakout-${bar.timestamp}`,
        timestamp: bar.timestamp,
        type: "breakout",
        title: "收盘价创阶段新高",
        detail: `突破此前阶段高点，收于 ${bar.close.toFixed(2)}`,
        score: 4,
      });
    }
    rollingHigh = Math.max(rollingHigh, bar.high);
    recentVolumes.push(bar.volume ?? 0);
    if (recentVolumes.length > 20) recentVolumes.shift();
  }
  return [...result]
    .sort((left, right) => right.score - left.score)
    .slice(0, 24)
    .sort((left, right) => right.timestamp - left.timestamp);
}

export function EventTimelineWorkspace({
  action,
  dataSource,
  security,
  theme,
  refreshNonce,
  onContextChange,
}: {
  action?: WorkspaceUiAction;
  dataSource: MarketDataSource;
  security: SecurityRef;
  theme: "light" | "dark";
  refreshNonce: number;
  onContextChange: (value: Record<string, unknown>) => void;
}) {
  const [bars, setBars] = useState<Bar[]>([]);
  const [feed, setFeed] = useState<MarketEventFeed>(EMPTY_EVENT_FEED);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<EventFilter>("all");
  const [selectedEventId, setSelectedEventId] = useState("");
  const [primaryIndicator, setPrimaryIndicator] = useState<"MA" | "EMA" | "BOLL">("MA");
  const [secondaryIndicator, setSecondaryIndicator] = useState<"VOL" | "MACD" | "RSI" | "KDJ">("VOL");
  const storageKey = `vibedesk.event-timeline.saved.${security.market}.${security.symbol}.v1`;
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
    void Promise.allSettled([
      dataSource.ohlcv(security, "1d", security.market === "CN" ? "qfq" : "none"),
      dataSource.events(security),
    ])
      .then(([barResult, eventResult]) => {
        if (!active) return;
        setBars(barResult.status === "fulfilled" ? barResult.value.items : []);
        setFeed(eventResult.status === "fulfilled" ? eventResult.value : EMPTY_EVENT_FEED);
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [dataSource, refreshNonce, security]);

  useEffect(() => {
    try {
      const values = JSON.parse(window.localStorage.getItem(storageKey) || "[]") as string[];
      setSaved(new Set(values));
    } catch {
      setSaved(new Set());
    }
  }, [storageKey]);

  useEffect(() => {
    if (action?.actionId !== "chart.set-indicator") return;
    if (action.input.position === "primary") setPrimaryIndicator(action.input.indicator as typeof primaryIndicator);
    if (action.input.position === "secondary") setSecondaryIndicator(action.input.indicator as typeof secondaryIndicator);
  }, [action]);

  const events = useMemo<TimelineEvent[]>(() => {
    const derived = deriveMarketEvents(bars).map((event) => ({
      ...event,
      origin: "derived" as const,
      source: "OHLCV 规则引擎",
      evidenceId: `ohlcv:${event.id}`,
    }));
    const evidence = feed.items.map((event) => ({ ...event, origin: "evidence" as const, score: 10 }));
    return [...evidence, ...derived].sort((left, right) => right.timestamp - left.timestamp);
  }, [bars, feed.items]);
  const visibleEvents = filter === "all"
    ? events
    : filter === "derived"
      ? events.filter((event) => event.origin === "derived")
      : events.filter((event) => event.type === filter);
  const selectedEvent = events.find((event) => event.id === selectedEventId);
  const chartEvents = useMemo(
    () => selectChartTimelineEvents(visibleEvents, selectedEventId),
    [selectedEventId, visibleEvents],
  );
  const loadBars = useCallback(async () => bars, [bars]);
  const annotations = useMemo<ChartAnnotation[]>(() => chartEvents.flatMap((event) => {
    if (!bars.length) return [];
    const nearest = bars.reduce((best, bar) => (
      Math.abs(bar.timestamp - event.timestamp) < Math.abs(best.timestamp - event.timestamp) ? bar : best
    ), bars[0]!);
    const fullLabel = event.origin === "derived" ? event.title : `${event.source} · ${event.title}`;
    return [{
      id: `event-${event.id}`.replace(/[^A-Za-z0-9_-]/g, "-").slice(0, 64),
      timestamp: nearest.timestamp,
      value: nearest.high,
      label: fullLabel.length > 26 ? `${fullLabel.slice(0, 25)}…` : fullLabel,
      tone: event.type === "price"
        ? (event.title.includes("回落") ? "negative" : "positive")
        : event.type === "earnings" || event.type === "announcement"
          ? "warning"
          : "info",
    }];
  }), [bars, chartEvents]);

  useEffect(() => {
    onContextChange({
      timeframe: "1d",
      primaryIndicator,
      secondaryIndicator,
      filter,
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
      sources: feed.sources,
    });
  }, [feed.sources, filter, onContextChange, primaryIndicator, saved.size, secondaryIndicator, selectedEvent, visibleEvents]);

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
          <span><CalendarRange size={14} />日线事件图层</span>
          <small>{bars.length ? `${bars.length} 个交易周期` : "等待数据"}</small>
        </div>
        {loading ? <div className="workspace-chart-loading"><RefreshCw className="spin" size={16} />正在生成事件时间轴…</div> : null}
        <KLineChartPanel
          security={security}
          timeframe="1d"
          adjustment={security.market === "CN" ? "qfq" : "none"}
          primaryIndicator={primaryIndicator}
          secondaryIndicator={secondaryIndicator}
          theme={theme}
          refreshNonce={refreshNonce + bars.length}
          loadBars={loadBars}
          annotations={annotations}
          ariaLabel="事件时间轴 K 线图"
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
        <div className="workspace-section-title"><span>事件列表</span><small>{visibleEvents.length} 条</small></div>
        <div className="workspace-segment event-filters" role="group" aria-label="事件筛选">
          {(["all", "announcement", "earnings", "news", "research", "derived"] as const).map((id) => (
            <button type="button" key={id} aria-pressed={filter === id} onClick={() => setFilter(id)}>
              {{ all: "全部", announcement: "公告", earnings: "财报", news: "新闻", research: "研报", derived: "量价" }[id]}
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
          <strong>证据源状态</strong>
          <span>{security.market === "CN" ? "公告、研报和新闻保留来源与证据 ID；量价事件由真实 OHLCV 推导。" : "当前海外标的仅显示 OHLCV 量价事件，公告与新闻源尚未启用。"}</span>
          <div className="event-source-statuses">
            {feed.sources.map((source) => <i key={source.id} data-status={source.status}>{source.label} {source.count}</i>)}
          </div>
          <small>累计成交量 {formatCompact(bars.reduce((sum, bar) => sum + (bar.volume ?? 0), 0))}</small>
        </div>
      </aside>
    </div>
  );
}
