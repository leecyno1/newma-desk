import {
  CalendarDays, Clock3, ExternalLink, FileSearch, Landmark, RefreshCw,
  Search, ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import { connectModHost, type ModHostConnection } from "@newma-desk/mod-sdk";

import { fetchPolicyDashboard } from "./api";
import type { PolicyDashboard, PolicyEvent, PolicyStatus } from "./types";

type View = "calendar" | "feed" | "sources";
type StatusFilter = "all" | PolicyStatus;
type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;

const LEVEL_LABELS = { 1: "执行级", 2: "行业级", 3: "战略级" } as const;
const STATUS_LABELS: Record<PolicyStatus, string> = {
  published: "已发布", scheduled: "待发布", "awaiting-verification": "待核验",
};
const CERTAINTY_LABELS = {
  official: "官方日期", "calendar-rule": "固定日历", "expected-window": "预期窗口",
} as const;
const COLLECTOR_LABELS: Record<string, string> = {
  ready: "实时采集正常", degraded: "部分渠道异常", unavailable: "采集不可用", "not-configured": "待配置采集器",
};

function parentOrigin() {
  if (document.referrer) {
    try { return new URL(document.referrer).origin; } catch { /* current origin */ }
  }
  return window.location.origin;
}

function dateLabel(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", weekday: "short" })
    .format(new Date(value + "T00:00:00"));
}

function monthLabel(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long" })
    .format(new Date(value + "-01T00:00:00"));
}

function buildContext(
  data: PolicyDashboard | null,
  selected: PolicyEvent | null,
  filters: Record<string, unknown>,
): ModPageContext {
  return {
    view: { id: "policy-analysis", title: "政策分析" },
    visibleBlocks: [
      { id: "policy-calendar", type: "event-calendar", title: "政策发布日程" },
      { id: "policy-assessment", type: "policy-assessment", title: "政策量级评估" },
      { id: "policy-sources", type: "source-registry", title: "官方政策渠道" },
    ],
    selection: selected ? { policyId: selected.id, title: selected.title, level: selected.level } : {},
    filters,
    data: {
      source: "official-policy-registry",
      freshness: data ? "fresh" : "unknown",
      ...(data ? { asOf: data.generatedAt, summary: data.summary } : {}),
    },
    actions: [{
      id: "policy.refresh", label: "刷新政策数据", available: true,
      inputSchema: { type: "object", additionalProperties: false },
    }],
    tasks: [],
  };
}

function PolicyRow({ event, active, onSelect }: {
  event: PolicyEvent; active: boolean; onSelect(): void;
}) {
  return (
    <button type="button" className={"policy-row" + (active ? " selected" : "")} onClick={onSelect}>
      <time>{dateLabel(event.date)}</time>
      <i className={"level-dot l" + event.level} />
      <span className="row-body">
        <span className="row-tags">
          <b className={"level-tag l" + event.level}>L{event.level} {LEVEL_LABELS[event.level]}</b>
          <em>{STATUS_LABELS[event.status]}</em><em>{CERTAINTY_LABELS[event.certainty]}</em>
        </span>
        <strong>{event.title}</strong><small>{event.institution} · {event.category}</small>
      </span>
    </button>
  );
}

export function PolicyAnalysisApp() {
  const [data, setData] = useState<PolicyDashboard | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [view, setView] = useState<View>("calendar");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [level, setLevel] = useState<0 | 1 | 2 | 3>(0);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [host, setHost] = useState<EmbeddedHost>();

  const filtered = useMemo(() => (data?.events ?? []).filter((event) => {
    if (status !== "all" && event.status !== status) return false;
    if (level && event.level !== level) return false;
    const needle = query.trim().toLowerCase();
    return !needle || [event.title, event.institution, event.category, ...event.marketScope]
      .join(" ").toLowerCase().includes(needle);
  }), [data, level, query, status]);

  const selected = useMemo(() => {
    const events = data?.events ?? [];
    return events.find((event) => event.id === selectedId) ?? filtered[0] ?? events[0] ?? null;
  }, [data, filtered, selectedId]);
  const filters = useMemo(() => ({ view, status, level, query }), [level, query, status, view]);
  const contextRef = useRef(buildContext(data, selected, filters));
  contextRef.current = buildContext(data, selected, filters);

  useEffect(() => {
    document.title = "政策分析 · Newma-Desk";
    if (!document.documentElement.dataset.theme) document.documentElement.dataset.theme = "dark";
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    void fetchPolicyDashboard(controller.signal).then((payload) => {
      setData(payload); setSelectedId((current) => current ?? payload.events[0]?.id ?? null);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "政策数据读取失败");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [refreshKey]);

  useEffect(() => {
    const controller = new AbortController();
    let close: () => void = () => undefined;
    let unsubscribe: () => void = () => undefined;
    void connectModHost({
      modId: "policy-analysis", parentOrigin: parentOrigin(), sdkVersion: "0.1.0",
      capabilities: ["actions", "context", "theme"], signal: controller.signal,
    }).then((connection) => {
      close = connection.close;
      if (!connection.embedded) return;
      setHost(connection);
      document.documentElement.dataset.theme = connection.config.environment.theme;
      unsubscribe = connection.subscribe((config) => {
        document.documentElement.dataset.theme = config.environment.theme;
      });
    }).catch(() => undefined);
    return () => { controller.abort(); unsubscribe(); close(); };
  }, []);

  useEffect(() => host?.setContextProvider(() => contextRef.current), [host]);
  useEffect(() => { host?.publishContext(contextRef.current); }, [data, filters, host, selected]);
  useEffect(() => host?.setUiActionHandler((actionId) => {
    if (actionId !== "policy.refresh") throw new Error("政策分析不支持动作 " + actionId);
    setRefreshKey((value) => value + 1); return { refreshed: true };
  }), [host]);

  const upcoming = data?.events.filter((event) => event.status === "scheduled") ?? [];
  const feedState = useMemo(() => new Map(
    (data?.collector.feeds ?? []).map((item) => [item.sourceId, item]),
  ), [data]);
  const healthyFeeds = data?.collector.feeds.filter((item) => item.status === "ok").length ?? 0;
  const collectedItems = data?.collector.feeds.reduce((sum, item) => sum + item.items, 0) ?? 0;
  const months = useMemo(() => {
    const grouped = new Map<string, PolicyEvent[]>();
    for (const event of filtered) {
      const key = event.date.slice(0, 7);
      grouped.set(key, [...(grouped.get(key) ?? []), event]);
    }
    return [...grouped.entries()].sort(([left], [right]) => right.localeCompare(left));
  }, [filtered]);

  return (
    <main className="policy-root">
      <header className="policy-header">
        <div><span>POLICY INTELLIGENCE</span><h1>政策分析</h1><p>历史复盘、发布日程与量级评估</p></div>
        <button type="button" onClick={() => setRefreshKey((value) => value + 1)} disabled={loading} title="刷新政策数据">
          <RefreshCw size={17} className={loading ? "spin" : ""} /><span>刷新</span>
        </button>
      </header>

      <section className="summary-strip" aria-label="政策监测摘要">
        <div><CalendarDays /><span>下一窗口</span><strong>{upcoming.at(-1)?.date.slice(5).replace("-", "/") ?? "--"}</strong><small>{upcoming.at(-1)?.title ?? "暂无日程"}</small></div>
        <div><ShieldCheck /><span>战略级政策</span><strong>{data?.summary.level3 ?? 0}</strong><small>三级量级</small></div>
        <div><Clock3 /><span>未来日程</span><strong>{data?.summary.upcoming ?? 0}</strong><small>含预期窗口</small></div>
        <div><Landmark /><span>官方渠道</span><strong>{data?.sources.length ?? 0}</strong><small>一手来源优先</small></div>
      </section>

      <section className="policy-toolbar">
        <div className="segmented" role="tablist">
          <button className={view === "calendar" ? "active" : ""} onClick={() => setView("calendar")}><CalendarDays />政策日历</button>
          <button className={view === "feed" ? "active" : ""} onClick={() => setView("feed")}><FileSearch />政策流</button>
          <button className={view === "sources" ? "active" : ""} onClick={() => setView("sources")}><Landmark />渠道</button>
        </div>
        <label className="search-box"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索政策、机构、行业" /></label>
        <select aria-label="政策状态" value={status} onChange={(event) => setStatus(event.target.value as StatusFilter)}>
          <option value="all">全部状态</option><option value="scheduled">待发布</option><option value="published">已发布</option><option value="awaiting-verification">待核验</option>
        </select>
        <div className="level-filter">
          {[0, 3, 2, 1].map((item) => <button key={item} className={level === item ? "active" : ""} onClick={() => setLevel(item as 0 | 1 | 2 | 3)}>{item === 0 ? "全部量级" : "L" + item}</button>)}
        </div>
      </section>

      {error ? <div className="error-banner">{error}</div> : null}
      {view === "sources" ? (
        <section className="source-view">
          <div className="section-heading"><div><span>OFFICIAL SOURCES</span><h2>政策渠道</h2></div><p>采集只作为发现入口，研究结论始终回链官方原文。</p></div>
          <div className="source-table">
            <div className="source-row head"><span>机构</span><span>覆盖范围</span><span>采集适配</span><span>入口</span></div>
            {data?.sources.map((source) => <div className="source-row" key={source.id}>
              <strong>{source.name}</strong><span>{source.categories.join(" · ")}</span>
              <span className="source-adapter"><code>{source.rssHubPath ?? "官方页面"}</code>{source.rssHubPath ? <em className={feedState.get(source.id)?.status === "ok" ? "ok" : "failed"}>{feedState.get(source.id)?.status === "ok" ? "实时" : data?.collector.status === "not-configured" ? "待配置" : "异常"}</em> : <em>官方页</em>}</span>
              <a href={source.url} target="_blank" rel="noreferrer">打开<ExternalLink /></a>
            </div>)}
          </div>
          <div className="collector-note"><ShieldCheck /><div><strong>{data?.collector.foundation} · {COLLECTOR_LABELS[data?.collector.status ?? ""] ?? data?.collector.status}</strong><span>{healthyFeeds}/{data?.collector.feeds.length ?? 0} 个采集渠道正常 · 本次合并 {collectedItems} 条官方动态</span></div><code>{data?.collector.revision.slice(0, 12)}</code></div>
        </section>
      ) : (
        <div className="policy-workspace">
          <section className="event-pane">
            <div className="section-heading"><div><span>{view === "calendar" ? "RELEASE CALENDAR" : "POLICY FEED"}</span><h2>{view === "calendar" ? "政策发布日程" : "政策动态"}</h2></div><p>{filtered.length} 条</p></div>
            {loading ? <div className="empty-state">正在读取政策数据</div> : months.length === 0 ? <div className="empty-state">没有匹配的政策</div> : months.map(([month, events]) => (
              <section className="month-group" key={month}><h3>{monthLabel(month)}</h3>{events.map((event) => <PolicyRow event={event} active={selected?.id === event.id} onSelect={() => setSelectedId(event.id)} key={event.id} />)}</section>
            ))}
          </section>
          <aside className="detail-pane">
            {selected ? <>
              <div className="detail-status"><span className={"level-tag l" + selected.level}>L{selected.level} {LEVEL_LABELS[selected.level]}</span><span>{STATUS_LABELS[selected.status]}</span><span>{CERTAINTY_LABELS[selected.certainty]}</span></div>
              <h2>{selected.title}</h2><p className="detail-summary">{selected.summary}</p>
              <dl><div><dt>日期</dt><dd>{selected.date}</dd></div><div><dt>发布机构</dt><dd>{selected.institution}</dd></div><div><dt>政策分类</dt><dd>{selected.category}</dd></div><div><dt>影响范围</dt><dd>{selected.marketScope.join("、")}</dd></div></dl>
              <section className="assessment-block"><h3>量级评估依据</h3><ul>{selected.rationale.map((item) => <li key={item}>{item}</li>)}</ul></section>
              <a className="source-link" href={selected.sourceUrl} target="_blank" rel="noreferrer"><ExternalLink />查看官方原文</a>
              <section className="level-guide"><h3>三级量级口径</h3>{data?.assessment.map((item) => <div key={item.level}><b className={"level-tag l" + item.level}>L{item.level}</b><span><strong>{item.label}</strong><small>{item.definition}</small></span></div>)}</section>
            </> : <div className="empty-state">选择一条政策查看详情</div>}
          </aside>
        </div>
      )}
    </main>
  );
}
