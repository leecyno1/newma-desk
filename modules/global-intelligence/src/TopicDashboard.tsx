import {
  Activity, ArrowRight, BookOpenCheck, ExternalLink, Gauge,
  GitCompareArrows, RefreshCw, SlidersHorizontal,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createModSnapshotCache, type GatewayFetch } from "@newma-desk/mod-sdk";

import { GLOBAL_TOPICS, TOPIC_BASELINE_WARNING, type GlobalTopicId } from "./topicContext";
import { buildMaritimeView, DEFAULT_MARITIME_FILTERS, MARITIME_SCOPES, TopicMaritime, type MaritimeEvidence, type MaritimeFilters } from "./TopicMaritime";
export type { GlobalTopicId } from "./topicContext";

interface TopicFactor {
  id: string; label: string; min: number; max: number; value: number;
}

interface TopicForecast {
  generatedAt: string;
  probabilities: Array<{ label: string; probability: number }>;
  dominantScenario: string;
  confidence: number;
  method: string;
  disclaimer: string;
}

export interface TopicSnapshot {
  topicId: GlobalTopicId;
  title: string;
  subtitle: string;
  question: string;
  accent: string;
  metrics: Array<{ label: string; value: string; change: string; unit?: string; date?: string; frequency?: string; dateBasis?: string; source?: string; sourceUrl?: string; status?: string }>;
  factors: TopicFactor[];
  series: Array<{ id: string; label: string; color: string }>;
  transmission: string[];
  sources: string[];
  observations: Array<{ seriesId: string; date: string; value: number; unit: string; source: string }>;
  events: Array<{ id: string; date: string; title: string; summary: string; source: string; sourceUrl: string; evidenceKey?: string; publishedAt?: string | null; collectedAt?: string | null; sourceStatus?: string; impact?: string; confidence?: number; evidenceType?: string; note?: string }>;
  eventCoverage?: { count: number; readySourceCount: number; staleSourceCount: number };
  forecast: TopicForecast;
  dataMode: string;
  dataWarning?: string;
  generatedAt?: string;
  freshness?: "fresh" | "stale" | "unknown";
  sourceStatus?: Array<{ id: string; label: string; status: string; url: string; collectedAt?: string; reason?: string }>;
  gaps?: string[];
  maritime?: MaritimeEvidence;
  factorSource?: string;
  updatedAt: string;
}

export function chartPath(rows: Array<{ date: string; value: number }>, width: number, height: number) {
  if (!rows.length) return "";
  const values = rows.map((row) => row.value);
  const min = Math.min(...values);
  const range = Math.max(...values) - min;
  const times = rows.map((row) => Date.parse(row.date));
  const first = Math.min(...times);
  const span = Math.max(...times) - first;
  return values.map((value, index) => {
    const x = span ? (((times[index] ?? first) - first) / span) * width : width / 2;
    const y = range ? height - ((value - min) / range) * height : height / 2;
    return (index ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
}

function collectedLabel(value?: string | null) {
  if (!value || !Number.isFinite(Date.parse(value))) return "采集时间未知";
  return `采集 ${new Date(value).toLocaleString("zh-CN", { hour12: false })}`;
}

function TopicChart({ snapshot }: { snapshot: TopicSnapshot }) {
  return (
    <section className="topic-panel topic-chart-panel">
      <header><span><Activity size={15} />核心变量</span><small>各图独立量程 · 按真实日期排列</small></header>
        {snapshot.series.map((series) => {
          const rows = snapshot.observations.filter((item) => item.seriesId === series.id && Number.isFinite(item.value) && Number.isFinite(Date.parse(item.date))).sort((a, b) => a.date.localeCompare(b.date));
          const latest = rows.at(-1);
          return <div className="topic-series-chart" key={series.id}>
            <div><strong style={{ color: series.color }}>{series.label}</strong><span>{latest ? `${latest.value.toFixed(2)} ${latest.unit} · ${latest.date}` : "暂无有效观测"}</span></div>
            {rows.length > 1 ? <>
              <svg viewBox="0 0 720 70" preserveAspectRatio="none" role="img" aria-label={`${series.label}趋势图`}>
                <path d={chartPath(rows, 720, 60)} transform="translate(0 5)" style={{ stroke: series.color }} />
              </svg>
              <div className="topic-chart-axis"><span>{rows[0]?.date}</span><span>范围 {Math.min(...rows.map((row) => row.value)).toFixed(2)}–{Math.max(...rows.map((row) => row.value)).toFixed(2)} {latest?.unit} · {rows.length} 个点</span><span>{latest?.date}</span></div>
            </> : <p>{rows.length ? "仅 1 个观测，暂无连续曲线" : "数据源尚未返回可用的历史序列"}</p>}
          </div>;
        })}
    </section>
  );
}

function ForecastPanel({ snapshot, factors, pending, running, loading, error, canForecast, onFactorChange, onRun }: {
  snapshot: TopicSnapshot;
  factors: Record<string, number>;
  pending: boolean;
  running: boolean;
  loading: boolean;
  error: string;
  canForecast: boolean;
  onFactorChange(id: string, value: number): void;
  onRun(): void;
}) {
  const forecast = snapshot.forecast;

  return (
    <section className="topic-panel topic-forecast">
      <header><span><SlidersHorizontal size={15} />情景推演</span><small>{forecast.method}</small></header>
      <p className="topic-question">{snapshot.question}</p>
      <p className="topic-disclaimer">手动假设参数 · 不代表实时指标，未与来源观测自动校准。</p>
      <div className="topic-factor-list">
        {snapshot.factors.map((factor) => (
          <label key={factor.id}>
            <span>{factor.label}<b>{Math.round(factors[factor.id] ?? factor.value)}</b></span>
            <input aria-label={factor.label} type="range" min={factor.min} max={factor.max} value={factors[factor.id] ?? factor.value} disabled={running || loading} onChange={(event) => onFactorChange(factor.id, Number(event.target.value))} />
          </label>
        ))}
      </div>
      <button className="topic-run-button" type="button" onClick={onRun} disabled={running || loading || !canForecast}><RefreshCw size={14} className={running ? "spin" : ""} />{running ? "计算中" : "重新推演"}</button>
      {!canForecast ? <p className="topic-notice" role="status">当前为只读授权，保存推演需要 storage.write 权限；请由宿主更新授权后重新加载。</p> : null}
      {pending ? <p className="topic-notice" role="status">参数已修改，当前结果仍对应上次参数；请重新推演。</p> : null}
      {error ? <p className="topic-notice" role="alert">{error}</p> : null}
      <p className="topic-disclaimer">以下百分比是手动参数产生的情景权重，不是事件发生概率。</p>
      <div className="topic-probabilities">
        {forecast.probabilities.map((item) => (
          <div key={item.label} className={item.label === forecast.dominantScenario ? "is-dominant" : ""}>
            <span>{item.label}<b>{item.probability}%</b></span>
            <i><em style={{ width: item.probability + "%" }} /></i>
          </div>
        ))}
      </div>
      <small className="topic-disclaimer">{forecast.disclaimer}</small>
    </section>
  );
}

interface TopicDashboardProps {
  topicId: GlobalTopicId;
  refreshNonce: number;
  gatewayBaseUrl?: string;
  request?: GatewayFetch;
  canForecast?: boolean;
  embedded?: boolean;
  cacheIdentity?: { userId: string; workspaceId: string };
  onContextChange?: (state: Record<string, unknown>) => void;
}

export function GlobalTopicDashboard(props: TopicDashboardProps) {
  return <TopicWorkspace key={JSON.stringify([props.topicId, props.cacheIdentity?.userId, props.cacheIdentity?.workspaceId])} {...props} />;
}

function TopicWorkspace({ topicId, refreshNonce, gatewayBaseUrl = window.location.origin, request = globalThis.fetch, canForecast = true, embedded = false, cacheIdentity, onContextChange }: TopicDashboardProps) {
  const [view, setView] = useState<{
    snapshot: TopicSnapshot;
    factors: Record<string, number>;
    forecastFactors: Record<string, number>;
  }>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [settledRequest, setSettledRequest] = useState<object | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const [running, setRunning] = useState(false);
  const [forecastError, setForecastError] = useState("");
  const maritimeCache = useMemo(() => topicId === "hormuz" && cacheIdentity ? createModSnapshotCache<MaritimeFilters>({
    modId: GLOBAL_TOPICS[topicId].id, ...cacheIdentity, resourceKey: "maritime-reading", schemaVersion: 1,
  }) : undefined, [topicId, cacheIdentity?.userId, cacheIdentity?.workspaceId]);
  const [maritimeFilters, setMaritimeFilters] = useState(() => {
    const saved = maritimeCache?.read()?.value;
    return saved && Object.hasOwn(MARITIME_SCOPES, saved.scope) && typeof saved.query === "string"
      && (saved.sort === "relevance" || saved.sort === "newest")
      && (saved.selectedId === null || typeof saved.selectedId === "string") ? saved : DEFAULT_MARITIME_FILTERS;
  });
  const forecastRequest = useRef<AbortController | null>(null);
  const snapshot = view?.snapshot;
  const maritimeView = useMemo(() => snapshot?.maritime ? buildMaritimeView(snapshot.maritime, maritimeFilters) : undefined, [snapshot?.maritime, maritimeFilters]);
  const forecastPending = Boolean(view && Object.keys(view.factors).some((id) => view.factors[id] !== view.forecastFactors[id]));
  const endpoint = new URL(`/api/global-topics/${topicId}`, gatewayBaseUrl).toString();
  const requestKey = useMemo(() => ({ endpoint, refreshNonce, retryNonce }), [endpoint, refreshNonce, retryNonce, request, canForecast]);

  useEffect(() => {
    // Persist reading controls, never source text or a claim of current validity.
    maritimeCache?.write(maritimeFilters);
  }, [maritimeCache, maritimeFilters]);

  useEffect(() => {
    const controller = new AbortController();
    forecastRequest.current?.abort();
    setRunning(false);
    setForecastError("");
    setLoading(true);
    setError("");
    void (async () => {
      try {
        const response = await request(endpoint, { signal: controller.signal });
        if (!response.ok) throw new Error("HTTP " + response.status);
        const next = await response.json() as TopicSnapshot;
        if (controller.signal.aborted) return;
        const factors = Object.fromEntries(next.factors.map((factor) => [factor.id, factor.value]));
        setView({ snapshot: next, factors, forecastFactors: factors });
        setMaritimeFilters((current) => current.selectedId && (!next.maritime || !buildMaritimeView(next.maritime, current).selectedWarning)
          ? { ...current, selectedId: null } : current);
      } catch {
        if (!controller.signal.aborted) setError("专题数据暂时不可用");
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          setSettledRequest(requestKey);
        }
      }
    })();
    return () => {
      controller.abort();
      forecastRequest.current?.abort();
    };
  }, [endpoint, refreshNonce, retryNonce, requestKey, request]);

  useEffect(() => {
    const dates = snapshot?.observations.map((item) => item.date).sort() ?? [];
    onContextChange?.({
      topicId, title: GLOBAL_TOPICS[topicId].title,
      refresh: { nonce: refreshNonce, status: settledRequest !== requestKey || loading ? "loading" : error ? "error" : "ready", error: error || null },
      loadState: loading ? "loading" : error ? "error" : "ready",
      refreshError: error || null,
      forecastWritable: canForecast,
      displayingPreviousData: Boolean(snapshot && error),
      ...(snapshot && view ? {
        metrics: snapshot.metrics, series: snapshot.series, observations: snapshot.observations,
        question: snapshot.question, events: snapshot.events, sources: snapshot.sources,
        transmission: snapshot.transmission,
        dataMode: snapshot.dataMode, dataWarning: snapshot.dataWarning ?? TOPIC_BASELINE_WARNING,
        eventCoverage: snapshot.eventCoverage ?? { count: snapshot.events.length, readySourceCount: 0, staleSourceCount: 0 },
        freshness: snapshot.freshness, sourceStatus: snapshot.sourceStatus, gaps: snapshot.gaps,
        maritime: snapshot.maritime,
        maritimeView,
        factorSource: snapshot.factorSource ?? "user-assumptions",
        generatedAt: snapshot.generatedAt ?? snapshot.updatedAt,
        timeRange: dates.length ? { start: dates[0], end: dates.at(-1) } : null,
        factors: view.factors, factorDefinitions: snapshot.factors,
        forecast: snapshot.forecast, forecastFactors: view.forecastFactors, forecastPending,
        forecastStatus: running ? "running" : forecastError ? "error" : "idle",
        forecastError: forecastError || null,
      } : {}),
    });
  }, [topicId, view, snapshot, loading, error, running, forecastError, forecastPending, maritimeView, onContextChange, refreshNonce, settledRequest, requestKey, canForecast]);

  const runForecast = async () => {
    if (!view || running || loading || !canForecast) return;
    const controller = new AbortController();
    forecastRequest.current = controller;
    const factors = { ...view.factors };
    setRunning(true);
    setForecastError("");
    try {
      const response = await request(`${endpoint}/forecast`, {
        method: "POST", signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ factors }),
      });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const next = await response.json() as TopicForecast;
      if (!controller.signal.aborted) setView((current) => current ? {
        ...current, snapshot: { ...current.snapshot, forecast: next }, forecastFactors: factors,
      } : current);
    } catch {
      if (!controller.signal.aborted) setForecastError("推演失败，已保留上次结果和当前参数，可重试。");
    } finally {
      if (!controller.signal.aborted) setRunning(false);
    }
  };

  if (!snapshot || !view) return error
    ? <div className="topic-state" role="alert"><Gauge size={20} />{error}<button type="button" onClick={() => setRetryNonce((value) => value + 1)} disabled={loading}>重试</button></div>
    : <div className="topic-state" role="status"><RefreshCw size={20} className="spin" />加载专题</div>;

  return (
    <div className="global-topic-root" data-accent={snapshot.accent} aria-busy={loading}>
      <section className="topic-heading" data-embedded={embedded || undefined}>
        {!embedded ? <div data-mod-page-title><span>GLOBAL THEMATIC RESEARCH</span><h1>{snapshot.title}</h1><p>{snapshot.subtitle}</p></div> : null}
        <div className="topic-data-badge"><i />{snapshot.dataMode === "reference-baseline" ? "内置示例 · 非实时数据" : snapshot.dataMode === "unavailable" ? "来源暂不可用" : `来源观测 · ${snapshot.events.length ? `${snapshot.events.length} 条事件` : "暂无相关事件"}`}</div>
        <button className="topic-refresh-button" type="button" onClick={() => setRetryNonce((value) => value + 1)} disabled={loading}><RefreshCw size={14} />{loading ? "刷新中" : "刷新专题"}</button>
      </section>
      <p className="topic-data-warning">{snapshot.dataWarning ?? TOPIC_BASELINE_WARNING}</p>
      {error ? <div className="topic-notice" role="alert">刷新失败，当前保留上次数据与参数。<button type="button" onClick={() => setRetryNonce((value) => value + 1)}>重试</button></div> : null}

      <section className="topic-metrics">
        {snapshot.metrics.map((metric) => <article key={metric.label}>
          <span>{metric.label}</span><strong>{metric.value}<em>{metric.unit}</em></strong>
          {metric.date ? <span>{metric.dateBasis === "query-time" ? "检索日" : "数据期"} {metric.date.slice(0, metric.frequency === "monthly" ? 7 : 10)}{metric.status === "stale" ? " · 旧数据" : ""}</span> : null}
          {metric.sourceUrl ? <a href={metric.sourceUrl} target="_blank" rel="noreferrer">{metric.source} ↗</a> : null}
          <small title={metric.change}>{metric.change}</small>
        </article>)}
      </section>

      {snapshot.maritime && maritimeView ? <TopicMaritime evidence={snapshot.maritime} view={maritimeView} onChange={setMaritimeFilters} /> : null}

      <div className="topic-primary-grid">
        <TopicChart snapshot={snapshot} />
        <ForecastPanel snapshot={snapshot} factors={view.factors} pending={forecastPending} running={running} loading={loading} error={forecastError} canForecast={canForecast} onRun={() => void runForecast()} onFactorChange={(id, value) => setView((current) => current ? { ...current, factors: { ...current.factors, [id]: value } } : current)} />
      </div>

      <section className="topic-panel topic-transmission">
        <header><span><GitCompareArrows size={15} />影响传导链</span><small>从事实信号到资产影响</small></header>
        <div>{snapshot.transmission.map((node, index) => <span key={node}><b>{index + 1}</b>{node}{index < snapshot.transmission.length - 1 ? <ArrowRight size={14} /> : null}</span>)}</div>
      </section>

      <div className="topic-secondary-grid">
        <section className="topic-panel topic-events">
          <header><span><BookOpenCheck size={15} />来源事件与文件</span><small>{snapshot.events.length} 条 · 发布日期不等于生效日期</small></header>
          {!snapshot.events.length ? <p className="topic-empty">当前来源未返回相关记录，不代表没有发生事件。</p> : null}
          {snapshot.events.map((event) => (
            <article key={event.id}>
              <time title={event.publishedAt || undefined}>{event.date || "日期未知"}</time>
              <div><strong>{event.title}</strong><p>{event.summary}</p><span>{event.source} · {snapshot.dataMode === "reference-baseline" ? "示例记录，待核验" : event.evidenceType === "news-report" ? "媒体报道，待核验" : event.evidenceType === "official-document" || event.evidenceType === "official-release" ? "官方原文" : "来源记录，待核验"} · {event.sourceStatus === "stale" ? "旧来源 · " : ""}{collectedLabel(event.collectedAt)}</span>{event.note ? <p>{event.note}</p> : null}</div>
              <a href={event.sourceUrl} target="_blank" rel="noreferrer" aria-label={"查看 " + event.title + " 来源"}><ExternalLink size={14} /></a>
            </article>
          ))}
        </section>
        <section className="topic-panel topic-sources">
          <header><span><Gauge size={15} />数据接入</span><small>专题数据库</small></header>
          {snapshot.sourceStatus ? snapshot.sourceStatus.map((source) => <div key={source.id} title={source.reason}>
            <i className={source.status === "ready" ? "is-reference" : ""} /><span>{source.label}<small className="topic-source-reason">{collectedLabel(source.collectedAt)}{source.reason ? ` · ${source.reason}` : ""}</small></span><small>{source.status === "ready" ? "已读取" : source.status === "stale" ? "旧缓存" : "不可用"}</small>
          </div>) : snapshot.sources.map((source) => <div key={source}><i /><span>{source}</span><small>待接入</small></div>)}
          {snapshot.gaps?.length ? <section className="topic-gaps"><strong>数据缺口与边界</strong><ul>{snapshot.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul></section> : null}
        </section>
      </div>
    </div>
  );
}
