import {
  Activity, ArrowRight, BookOpenCheck, ExternalLink, Gauge,
  GitCompareArrows, RefreshCw, SlidersHorizontal,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createModSnapshotCache, type GatewayFetch, type ModSnapshotCache } from "@newma-desk/mod-sdk";

import { GLOBAL_TOPICS, TOPIC_BASELINE_WARNING, type GlobalTopicId } from "./topicContext";
import { buildMaritimeView, DEFAULT_MARITIME_FILTERS, MARITIME_SCOPES, TopicMaritime, type MaritimeEvidence, type MaritimeFilters } from "./TopicMaritime";
export type { GlobalTopicId } from "./topicContext";

interface TopicFactor {
  id: string; label: string; min: number; max: number; value: number;
  direction?: number;
}

interface TopicForecast {
  generatedAt: string;
  probabilities: Array<{ label: string; probability: number }>;
  dominantScenario: string;
  confidence: number;
  method: string;
  disclaimer: string;
}

function isForecastReceipt(value: unknown): value is TopicForecast {
  if (!value || typeof value !== "object") return false;
  const result = value as TopicForecast;
  return typeof result.generatedAt === "string" && Number.isFinite(Date.parse(result.generatedAt))
    && typeof result.dominantScenario === "string" && typeof result.method === "string"
    && typeof result.disclaimer === "string" && Number.isFinite(result.confidence)
    && Array.isArray(result.probabilities) && result.probabilities.every(item => item
      && typeof item.label === "string" && Number.isFinite(item.probability));
}

interface SupplyReceipt {
  vintage?: string | null;
  vintageBasis?: string;
  basisVerified?: boolean;
  rejected?: number | null;
  missing?: number | null;
  collectedAt?: string | null;
  sourceStatus?: string;
}

export interface TopicSnapshot {
  topicId: GlobalTopicId;
  title: string;
  subtitle: string;
  question: string;
  accent: string;
  metrics: Array<SupplyReceipt & { label: string; value: string; change: string; unit?: string | null; date?: string | null; frequency?: string; dateBasis?: string; source?: string; sourceUrl?: string; status?: string }>;
  factors: TopicFactor[];
  outcomes?: string[];
  series: Array<{ id: string; label: string; color: string }>;
  transmission: string[];
  sources: string[];
  observations: Array<SupplyReceipt & { seriesId: string; date: string; value: number; unit: string | null; source: string }>;
  events: Array<{ id: string; date: string; title: string; summary: string; source: string; sourceUrl: string; evidenceKey?: string; publishedAt?: string | null; collectedAt?: string | null; sourceStatus?: string; impact?: string; confidence?: number; evidenceType?: string; note?: string }>;
  eventCoverage?: { count: number; readySourceCount: number; staleSourceCount: number };
  forecast: TopicForecast;
  forecastOrigin?: "default" | "saved";
  forecastSavedAt?: string | null;
  dataMode: string;
  dataWarning?: string;
  generatedAt?: string;
  freshness?: "fresh" | "stale" | "unknown";
  sourceStatus?: Array<{ id: string; label: string; status: string; url: string; collectedAt?: string | null; reason?: string }>;
  gaps?: string[];
  maritime?: MaritimeEvidence;
  factorSource?: string;
  updatedAt: string;
}

function chartCoordinates(rows: Array<{ date: string; value: number }>, width: number, height: number) {
  if (!rows.length) return [];
  const values = rows.map((row) => row.value);
  const min = Math.min(...values);
  const range = Math.max(...values) - min;
  const times = rows.map((row) => Date.parse(row.date));
  const first = Math.min(...times);
  const span = Math.max(...times) - first;
  return values.map((value, index) => {
    const x = span ? (((times[index] ?? first) - first) / span) * width : width / 2;
    const y = range ? height - ((value - min) / range) * height : height / 2;
    return { x, y };
  });
}

export function chartPath(rows: Array<SupplyReceipt & { date: string; value: number }>, width: number, height: number) {
  return chartCoordinates(rows, width, height).map(({ x, y }, index) => {
    const row = rows[index]!;
    const previous = rows[index - 1];
    let connected = Boolean(previous);
    if (/^\d{4}-\d{2}$/.test(row.date)) {
      const monthIndex = (value: string) => Number(value.slice(0, 4)) * 12 + Number(value.slice(5, 7));
      connected = Boolean(previous && /^\d{4}-\d{2}$/.test(previous.date)
        && monthIndex(row.date) - monthIndex(previous.date) === 1
        && row.basisVerified && previous.basisVerified && row.vintage && row.vintage === previous.vintage);
    }
    return (connected ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
}

function sourceStatusLabel(value?: string) {
  return ({ ready: "已读取", partial: "部分覆盖", stale: "旧数据", unknown: "未核验", unavailable: "不可用" })[value ?? ""] ?? "未核验";
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
          const monthly = rows.some((row) => /^\d{4}-\d{2}$/.test(row.date));
          return <div className="topic-series-chart" key={series.id}>
            <div><strong style={{ color: series.color }}>{series.label}</strong><span>{latest ? `${latest.value.toFixed(2)} ${latest.unit ?? "单位未核验"} · ${latest.date}` : "暂无有效观测"}</span></div>
            {rows.length > 1 ? <>
              <svg viewBox="0 0 720 70" preserveAspectRatio="none" role="img" aria-label={`${series.label}趋势图`}>
                <path d={chartPath(rows, 720, 60)} transform="translate(0 5)" style={{ stroke: series.color }} />
                {monthly ? chartCoordinates(rows, 720, 60).map(({ x, y }, i) => <circle key={rows[i]!.date} cx={x} cy={y + 5} r="3" fill={series.color}>
                  <title>{rows[i]!.date} · {rows[i]!.value} · 修订列 {rows[i]!.vintage ?? "未知"}</title>
                </circle>) : null}
              </svg>
              <div className="topic-chart-axis"><span>{rows[0]?.date}</span><span>范围 {Math.min(...rows.map((row) => row.value)).toFixed(2)}–{Math.max(...rows.map((row) => row.value)).toFixed(2)} {latest?.unit} · {rows.length} 个点</span><span>{latest?.date}</span></div>
            </> : <p>{rows.length ? "仅 1 个观测，暂无连续曲线" : "数据源尚未返回可用的历史序列"}</p>}
            {monthly ? <>
              <p>月度观测 · 缺月断线；未核验或不同修订列不连线。修订列不是发布日期，也不是点时版本。</p>
              <details><summary>查看月度原值与修订列</summary>
                <table><thead><tr><th>月份</th><th>原值</th><th>单位</th><th>修订列</th><th>口径</th></tr></thead>
                  <tbody>{rows.map((row) => <tr key={row.date}><td>{row.date}</td><td>{row.value}</td><td>{row.unit ?? "未核验"}</td><td>{row.vintage ?? "未知"}</td><td>{row.basisVerified ? "已核口径" : "未核验"}</td></tr>)}</tbody>
                </table>
              </details>
            </> : null}
          </div>;
        })}
    </section>
  );
}

interface ForecastRecovery {
  id: string;
  startedAt: string;
  factors: Record<string, number>;
}

function readForecastRecovery(cache?: ModSnapshotCache<ForecastRecovery>): ForecastRecovery | null {
  const record = cache?.read()?.value;
  return record && typeof record.id === "string" && typeof record.startedAt === "string"
    && Number.isFinite(Date.parse(record.startedAt)) && record.factors && typeof record.factors === "object"
    && Object.values(record.factors).every(value => typeof value === "number" && Number.isFinite(value))
    ? record : null;
}

function ForecastPanel({ snapshot, factors, forecastFactors, pending, running, loading, error, recovery, canVerify, canForecast, onVerify, onFactorChange, onReset, onRun }: {
  snapshot: TopicSnapshot;
  factors: Record<string, number>;
  forecastFactors: Record<string, number>;
  pending: boolean;
  running: boolean;
  loading: boolean;
  error: string;
  recovery: ForecastRecovery | null;
  canVerify: boolean;
  canForecast: boolean;
  onVerify(): void;
  onFactorChange(id: string, value: number): void;
  onReset(): void;
  onRun(): void;
}) {
  const forecast = snapshot.forecast;

  return (
    <section className="topic-panel topic-forecast">
      <header><span><SlidersHorizontal size={15} />情景推演</span><small>{forecast.method}</small></header>
      <p className="topic-question">{snapshot.question}</p>
      <p className="topic-disclaimer">手动假设参数 · 不代表实时指标，未与来源观测自动校准。</p>
      <p className="topic-disclaimer">{snapshot.forecastOrigin === "saved"
        ? `已保存推演 · ${snapshot.forecastSavedAt ? new Date(snapshot.forecastSavedAt).toLocaleString("zh-CN", { hour12: false }) : "记录时间未知"} · 未按新观测自动重算`
        : "默认参数推演 · 尚未保存"}</p>
      <div className="topic-factor-list">
        {snapshot.factors.map((factor) => {
          const direction = factor.direction;
          const outcome = typeof direction === "number" && Number.isFinite(direction) && direction !== 0
            ? direction > 0 ? snapshot.outcomes?.at(-1) : snapshot.outcomes?.[0] : undefined;
          return <label key={factor.id}>
            <span>{factor.label}<b>{Math.round(factors[factor.id] ?? factor.value)}</b></span>
            <input aria-label={factor.label} type="range" min={factor.min} max={factor.max} value={factors[factor.id] ?? factor.value} disabled={running || loading} onChange={(event) => onFactorChange(factor.id, Number(event.target.value))} />
            <small>结果参数 {forecastFactors[factor.id] ?? factor.value} · 当前草稿 {factors[factor.id] ?? factor.value}</small>
            {outcome ? <small>模型设定：上调偏向「{outcome}」 · 系数 {direction! > 0 ? "+" : ""}{direction}</small> : null}
          </label>;
        })}
      </div>
      <p className="topic-disclaimer">系数是模型设定，不是来源观测、统计估计或因果证据。</p>
      {pending ? <button className="topic-reset-button" type="button" onClick={onReset} disabled={running || loading || Boolean(recovery)}>撤销未提交修改</button> : null}
      <button className="topic-run-button" type="button" onClick={onRun} disabled={running || loading || Boolean(recovery) || !canForecast}><RefreshCw size={14} className={running ? "spin" : ""} />{running ? "计算中" : "重新推演"}</button>
      {!canForecast ? <p className="topic-notice" role="status">当前为只读授权，保存推演需要 storage.write 权限；请由宿主更新授权后重新加载。</p> : null}
      {pending ? <p className="topic-notice" role="status">{recovery ? "参数与当前结果不同，请先核验待确认提交；不会自动重新推演。" : "参数已修改，当前结果仍对应上次参数；请重新推演。"}</p> : null}
      {error ? <p className="topic-notice" role="alert">{error}</p> : null}
      {recovery && !running ? <div className="topic-notice">
        <p>待核验提交时间：{new Date(recovery.startedAt).toLocaleString("zh-CN", { hour12: false })}</p>
        <p>本次提交参数：{Object.entries(recovery.factors).map(([id, value]) => `${snapshot.factors.find(factor => factor.id === id)?.label ?? id} ${value}`).join(" · ") || "默认参数"}</p>
        <p>请核对已保存结果和本次提交。刷新成功不代表原请求取消；以下操作仅解除保护，不重新提交，也不证明原操作成功。</p>
        <button type="button" onClick={onVerify} disabled={!canVerify}>已核对，恢复手动推演</button>
      </div> : null}
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

const FORECAST_UNCONFIRMED = "推演结果未确认，已保留本次提交参数；请求可能已保存，请先刷新专题核对，勿直接重复提交。";

export function GlobalTopicDashboard(props: TopicDashboardProps) {
  return <TopicWorkspace key={JSON.stringify([props.topicId, props.cacheIdentity?.userId, props.cacheIdentity?.workspaceId, props.gatewayBaseUrl ?? window.location.origin])} {...props} />;
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
  const endpoint = new URL(`/api/global-topics/${topicId}`, gatewayBaseUrl).toString();
  const recoveryCache = useMemo(() => cacheIdentity ? createModSnapshotCache<ForecastRecovery>({
    modId: GLOBAL_TOPICS[topicId].id, ...cacheIdentity, resourceKey: `forecast-pending:${endpoint}`,
    schemaVersion: 1, maxBytes: 8192,
  }) : undefined, [topicId, endpoint, cacheIdentity?.userId, cacheIdentity?.workspaceId]);
  const [recovery, setRecovery] = useState(() => readForecastRecovery(recoveryCache));
  const initialRecovery = useRef(recovery);
  const [recoveryError, setRecoveryError] = useState("");
  const [hasReadback, setHasReadback] = useState(false);
  const forecastError = recoveryError || (!running && recovery ? FORECAST_UNCONFIRMED : "");
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
  const requestKey = useMemo(() => ({ endpoint, refreshNonce, retryNonce }), [endpoint, refreshNonce, retryNonce, request, canForecast]);

  useEffect(() => {
    // Persist reading controls, never source text or a claim of current validity.
    maritimeCache?.write(maritimeFilters);
  }, [maritimeCache, maritimeFilters]);

  useEffect(() => {
    const controller = new AbortController();
    forecastRequest.current?.abort();
    forecastRequest.current = null;
    setRunning(false);
    setLoading(true);
    setHasReadback(false);
    setError("");
    void (async () => {
      try {
        const response = await request(endpoint, { signal: controller.signal });
        if (!response.ok) throw new Error("HTTP " + response.status);
        const next = await response.json() as TopicSnapshot;
        if (controller.signal.aborted) return;
        const factors = Object.fromEntries(next.factors.map((factor) => [factor.id, factor.value]));
        setHasReadback(true);
        // A snapshot read cannot confirm or cancel an earlier write.
        setView((current) => ({
          snapshot: next,
          // Refresh observations/results without discarding unsubmitted slider edits.
          factors: Object.fromEntries(Object.entries(factors).map(([id, value]) => [
            id, current && current.factors[id] !== undefined && current.factors[id] !== current.forecastFactors[id]
              ? current.factors[id] : !current ? initialRecovery.current?.factors[id] ?? value : value,
          ])),
          forecastFactors: factors,
        }));
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
      forecastStatus: running ? "running" : recovery ? "unconfirmed" : "idle",
      forecastError: forecastError || null,
      forecastRecovery: recovery ? { ...recovery, persistence: recoveryCache ? "browser-local" : "page-only", readbackReady: hasReadback && !loading && !error } : null,
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
        factors: view.factors, factorDefinitions: snapshot.factors, scenarioOrder: snapshot.outcomes ?? null,
        forecast: snapshot.forecast, forecastFactors: view.forecastFactors, forecastPending,
        forecastOrigin: snapshot.forecastOrigin ?? "default", forecastSavedAt: snapshot.forecastSavedAt ?? null,
      } : {}),
    });
  }, [topicId, view, snapshot, loading, error, running, forecastError, forecastPending, recovery, recoveryCache, hasReadback, maritimeView, onContextChange, refreshNonce, settledRequest, requestKey, canForecast]);

  const clearRecovery = (record: ForecastRecovery) => {
    if (!recoveryCache) return true;
    // Do not erase a different submission written by another page.
    if (readForecastRecovery(recoveryCache)?.id !== record.id) return false;
    recoveryCache.clear();
    return !recoveryCache.read();
  };

  const verifyForecast = () => {
    if (!recovery || !hasReadback || running || loading || error || !view) return;
    if (!clearRecovery(recovery)) {
      setRecoveryError("恢复记录未能清除或已变化，请重新打开专题核对；本次未重新提交。");
      return;
    }
    setRecovery(null);
    setRecoveryError("");
  };

  const runForecast = async () => {
    if (!view || running || loading || recovery || !canForecast) return;
    const existing = readForecastRecovery(recoveryCache);
    if (existing) { setRecovery(existing); setRecoveryError(""); setHasReadback(false); return; }
    const factors = { ...view.factors };
    const submission: ForecastRecovery = { id: crypto.randomUUID(), startedAt: new Date().toISOString(), factors };
    if (recoveryCache) {
      recoveryCache.write(submission);
      // The SDK cache is best-effort; verify durable readback before sending a write.
      if (readForecastRecovery(recoveryCache)?.id !== submission.id) {
        setRecoveryError("无法保存推演恢复记录，本次未提交。请允许浏览器本地存储后重试。");
        return;
      }
    }
    const controller = new AbortController();
    forecastRequest.current = controller;
    setRecovery(submission);
    setHasReadback(false);
    setRunning(true);
    setRecoveryError("");
    try {
      const response = await request(`${endpoint}/forecast`, {
        method: "POST", signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ factors }),
      });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const next: unknown = await response.json();
      if (!isForecastReceipt(next)) throw new Error("Invalid forecast receipt");
      if (!controller.signal.aborted) {
        setView((current) => current ? {
          ...current, snapshot: { ...current.snapshot, forecast: next, forecastOrigin: "saved", forecastSavedAt: next.generatedAt }, forecastFactors: factors,
        } : current);
        if (clearRecovery(submission)) setRecovery(null);
        else setRecoveryError("推演已保存，但恢复记录未能清除或已变化；请刷新专题核对。");
      }
    } catch {
      // Retain the pre-submit record even when observation is aborted or the receipt is lost.
    } finally {
      if (forecastRequest.current === controller) forecastRequest.current = null;
      if (!controller.signal.aborted) setRunning(false);
    }
  };

  if (!snapshot || !view) return <>
    {error ? <div className="topic-state" role="alert"><Gauge size={20} />{error}<button type="button" onClick={() => setRetryNonce((value) => value + 1)} disabled={loading}>重试</button></div>
      : <div className="topic-state" role="status"><RefreshCw size={20} className="spin" />加载专题</div>}
    {forecastError ? <p className="topic-notice" role="alert">{forecastError}</p> : null}
  </>;

  return (
    <div className="global-topic-root" data-accent={snapshot.accent} aria-busy={loading}>
      <section className="topic-heading" data-embedded={embedded || undefined}>
        {!embedded ? <div data-mod-page-title><span>GLOBAL THEMATIC RESEARCH</span><h1>{snapshot.title}</h1><p>{snapshot.subtitle}</p></div> : null}
        <div className="topic-data-badge"><i />{snapshot.dataMode === "reference-baseline" ? "内置示例 · 非实时数据" : snapshot.dataMode === "unavailable" ? "来源暂不可用" : `来源观测 · ${snapshot.events.length ? `${snapshot.events.length} 条事件` : "暂无相关事件"}`}</div>
        <button className="topic-refresh-button" type="button" onClick={() => setRetryNonce((value) => value + 1)} disabled={loading || running}><RefreshCw size={14} />{loading ? "刷新中" : "刷新专题"}</button>
      </section>
      <p className="topic-data-warning">{snapshot.dataWarning ?? TOPIC_BASELINE_WARNING}</p>
      {error ? <div className="topic-notice" role="alert">刷新失败，当前保留上次数据与参数。<button type="button" onClick={() => setRetryNonce((value) => value + 1)} disabled={loading || running}>重试</button></div> : null}

      <section className="topic-metrics">
        {snapshot.metrics.map((metric) => <article key={metric.label}>
          <span>{metric.label}</span><strong>{metric.value}<em>{metric.unit}</em></strong>
          {metric.date ? <span>{metric.dateBasis === "query-time" ? "检索日" : "数据期"} {metric.date.slice(0, metric.frequency === "monthly" ? 7 : 10)} · {sourceStatusLabel(metric.status)}</span> : null}
          {"vintage" in metric ? <>
            <span>修订列 {metric.vintage ?? "未知"} · {metric.basisVerified ? "已核口径" : "口径未核验"}</span>
            <span>缺失 {metric.missing ?? "未知"} · 拒绝 {metric.rejected ?? "未知"}</span>
            <span>{collectedLabel(metric.collectedAt)}{metric.unit == null ? " · 单位未核验" : ""}</span>
          </> : null}
          {metric.sourceUrl ? <a href={metric.sourceUrl} target="_blank" rel="noreferrer">{metric.source} ↗</a> : null}
          <small title={metric.change}>{metric.change}</small>
        </article>)}
      </section>

      {snapshot.maritime && maritimeView ? <TopicMaritime evidence={snapshot.maritime} view={maritimeView} onChange={setMaritimeFilters} /> : null}

      <div className="topic-primary-grid">
        <TopicChart snapshot={snapshot} />
        <ForecastPanel snapshot={snapshot} factors={view.factors} forecastFactors={view.forecastFactors} pending={forecastPending} running={running} loading={loading} error={forecastError} recovery={recovery} canVerify={hasReadback && !running && !loading && !error} onVerify={verifyForecast} canForecast={canForecast} onRun={() => void runForecast()} onFactorChange={(id, value) => setView((current) => current ? { ...current, factors: { ...current.factors, [id]: value } } : current)} onReset={() => {
          if (!running && !loading && !recovery) setView(current => current ? { ...current, factors: { ...current.forecastFactors } } : current);
        }} />
      </div>

      <section className="topic-panel topic-transmission">
        <header><span><GitCompareArrows size={15} />影响传导链</span><small>机制示意 · 非已证实因果</small></header>
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
            <i className={source.status === "ready" ? "is-reference" : ""} /><span>{source.label}<small className="topic-source-reason">{collectedLabel(source.collectedAt)}{source.reason ? ` · ${source.reason}` : ""}</small></span><small>{sourceStatusLabel(source.status)}</small>
          </div>) : snapshot.sources.map((source) => <div key={source}><i /><span>{source}</span><small>待接入</small></div>)}
          {snapshot.gaps?.length ? <section className="topic-gaps"><strong>数据缺口与边界</strong><ul>{snapshot.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul></section> : null}
        </section>
      </div>
    </div>
  );
}
