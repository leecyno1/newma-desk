import {
  BrainCircuit, CalendarDays, Clock3, ExternalLink, FileSearch, Landmark, Link2, RefreshCw,
  Search, ShieldCheck, Sparkles, TextSearch,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import type { WikiPageContext, WikiSubjectRef } from "@newma-desk/contracts";
import { connectModHost, type ModHostConnection } from "@newma-desk/mod-sdk";

import { fetchPolicyDashboard, interpretPolicyEvent, refreshPolicyDashboard, reviewPolicyAssessment } from "./api";
import type {
  PolicyDashboard, PolicyDocumentType, PolicyEntity, PolicyEvent, PolicyInterpretation, PolicyLifecycleStage,
} from "./types";

type View = "calendar" | "feed" | "interpretation" | "sources";
type DocumentTypeFilter = "all" | PolicyDocumentType;
type LifecycleFilter = "all" | PolicyLifecycleStage;
type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;
type EventView = Exclude<View, "sources">;

const VIEW_META: Record<View, { title: string; description: string }> = {
  calendar: { title: "政策日历", description: "历史、当前与未来政策发布窗口" },
  feed: { title: "政策流", description: "官方政策发布、量级与生命周期" },
  interpretation: { title: "政策解读", description: "影响分析、历史推演与原文对比" },
  sources: { title: "政策渠道", description: "官方来源、采集状态与证据边界" },
};

const LEVEL_LABELS = { 1: "执行级", 2: "行业级", 3: "战略级" } as const;
const CERTAINTY_LABELS = {
  official: "官方日期", "calendar-rule": "固定日历", "expected-window": "预期窗口",
} as const;
const COLLECTOR_LABELS: Record<string, string> = {
  ready: "实时采集正常", degraded: "部分渠道异常", unavailable: "采集不可用", "not-configured": "待配置采集器",
};
const DOCUMENT_TYPE_LABELS: Record<PolicyDocumentType, string> = {
  "formal-policy": "正式政策", "policy-interpretation": "政策解读",
  "meeting-speech": "会议讲话", "implementation-update": "执行动态", "macro-data": "宏观数据",
};
const LIFECYCLE_LABELS: Record<PolicyLifecycleStage, string> = {
  scheduled: "待发布", solicitation: "征求意见", published: "正式发布", effective: "已生效",
  amended: "修订", adjusted: "调整", repealed: "废止", expired: "失效",
};
const ALL_LIFECYCLE_STAGES = Object.keys(LIFECYCLE_LABELS) as PolicyLifecycleStage[];
const VIEW_LIFECYCLE_STAGES: Record<EventView, readonly PolicyLifecycleStage[]> = {
  calendar: ["scheduled", "solicitation", "published", "effective"],
  feed: ["published", "amended", "adjusted", "repealed", "expired"],
  interpretation: ["published", "effective", "amended", "adjusted", "repealed", "expired"],
};
const VIEW_ALL_LABELS: Record<EventView, string> = {
  calendar: "全部日程", feed: "全部动态", interpretation: "全部政策",
};

function belongsToView(event: PolicyEvent, view: EventView) {
  if (!VIEW_LIFECYCLE_STAGES[view].includes(event.lifecycleStage)) return false;
  if (view === "calendar") return true;
  if (event.status !== "published") return false;
  return view !== "interpretation" || event.documentType === "formal-policy";
}

function parentOrigin() {
  const configured = import.meta.env.VITE_PARENT_ORIGIN?.trim();
  if (configured) return configured;
  const ancestors = (window.location as Location & { ancestorOrigins?: DOMStringList }).ancestorOrigins;
  if (ancestors?.[0]) {
    try { return new URL(ancestors[0]).origin; } catch { /* use referrer */ }
  }
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

function timestampLabel(value?: string | null) {
  if (!value) return "尚无成功记录";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}

function buildContext(
  data: PolicyDashboard | null,
  selected: PolicyEvent | null,
  filters: Record<string, unknown>,
  wikiEntity?: PolicyEntity,
): ModPageContext {
  const wiki = selected ? policyWikiContext(selected, wikiEntity) : undefined;
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
    ...(wiki ? { wiki } : {}),
    tasks: [],
  };
}

function wikiSubject(entity: PolicyEntity): WikiSubjectRef {
  return {
    type: entity.type, canonicalId: entity.canonicalId, displayName: entity.displayName,
    ...(entity.market ? { market: entity.market } : {}),
    ...(entity.symbol ? { symbol: entity.symbol } : {}),
    ...(entity.assetType ? { assetType: entity.assetType } : {}),
  };
}

function policyWikiContext(event: PolicyEvent, primaryEntity?: PolicyEntity): WikiPageContext {
  const primarySubject: WikiSubjectRef = primaryEntity ? wikiSubject(primaryEntity) : {
    type: "topic", canonicalId: `topic:policy:${event.id}`, displayName: event.title.slice(0, 160),
  };
  return {
    primarySubject,
    relatedSubjects: event.entities.filter((entity) => entity.canonicalId !== primarySubject.canonicalId).map(wikiSubject),
    conceptIds: event.entities.filter((entity) => entity.type === "concept").map((entity) => entity.canonicalId),
    intent: "policy.monitor", timeframe: "policy-lifecycle", snapshotId: `policy:${event.id}`,
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
          <em>{LIFECYCLE_LABELS[event.lifecycleStage]}</em>{LIFECYCLE_LABELS[event.lifecycleStage] !== DOCUMENT_TYPE_LABELS[event.documentType] ? <em>{DOCUMENT_TYPE_LABELS[event.documentType]}</em> : null}{event.status === "awaiting-verification" ? <em>待核验</em> : null}
        </span>
        <strong>{event.title}</strong><small>{event.institution} · {event.category}</small>
      </span>
    </button>
  );
}

function CalendarMonth({ month, events, selectedId, onSelect }: {
  month: string; events: PolicyEvent[]; selectedId: string | null; onSelect(id: string): void;
}) {
  const year = Number(month.slice(0, 4));
  const monthNumber = Number(month.slice(5, 7));
  const firstDay = new Date(year, monthNumber - 1, 1);
  const leading = (firstDay.getDay() + 6) % 7;
  const dayCount = new Date(year, monthNumber, 0).getDate();
  const byDay = new Map<number, PolicyEvent[]>();
  for (const event of events) {
    const day = Number(event.date.slice(8, 10));
    byDay.set(day, [...(byDay.get(day) ?? []), event]);
  }
  const cells = [
    ...Array.from({ length: leading }, () => null),
    ...Array.from({ length: dayCount }, (_, index) => index + 1),
  ];
  while (cells.length % 7) cells.push(null);

  return (
    <section className="calendar-month">
      <h3>{monthLabel(month)}</h3>
      <div className="calendar-weekdays">{["一", "二", "三", "四", "五", "六", "日"].map((day) => <span key={day}>{day}</span>)}</div>
      <div className="calendar-grid">{cells.map((day, index) => {
        const dayEvents = day ? byDay.get(day) ?? [] : [];
        return <div className={"calendar-day" + (dayEvents.length ? " has-event" : "")} key={`${month}-${index}`}>
          {day ? <time>{day}</time> : null}
          {dayEvents.map((event) => <button type="button" className={`calendar-event l${event.level}${selectedId === event.id ? " selected" : ""}`} onClick={() => onSelect(event.id)} key={event.id} title={event.title}>
            <b>L{event.level}</b><span>{event.title}</span>
          </button>)}
        </div>;
      })}</div>
    </section>
  );
}

function InterpretationReport({ report }: { report: PolicyInterpretation }) {
  return <div className="interpretation-report">
    <div className="interpretation-mode"><Sparkles /><strong>{report.mode === "ai" ? "AI 模型解析" : "规则分析"}</strong><span>{report.model ?? "模型未配置，已使用可审计规则"}</span></div>
    <section><h3><ShieldCheck />影响分析</h3><div className="analysis-columns"><div><b>事实</b>{report.impactAnalysis.facts.map((item) => <p key={item}>{item}</p>)}</div><div><b>影响推断</b>{report.impactAnalysis.inferences.map((item) => <p key={item}>{item}</p>)}</div><div><b>不确定性</b>{report.impactAnalysis.uncertainties.map((item) => <p key={item}>{item}</p>)}</div></div></section>
    <section><h3><Clock3 />同类政策历史对比推演</h3>{report.historicalComparison.matchedPolicies.length ? <div className="history-matches">{report.historicalComparison.matchedPolicies.map((item) => <span key={item.id}>{item.date} · {item.title}</span>)}</div> : <p className="muted-note">尚未识别到同系列历史政策。</p>}<div className="comparison-points"><div><b>新增</b>{report.historicalComparison.added.map((item) => <span key={item}>{item}</span>)}</div><div><b>减少</b>{report.historicalComparison.removed.map((item) => <span key={item}>{item}</span>)}</div><div><b>延续</b>{report.historicalComparison.shared.map((item) => <span key={item}>{item}</span>)}</div></div><small>{report.historicalComparison.note}</small></section>
    <section className={"transcript-status " + report.transcriptComparison.status}><h3><TextSearch />逐字稿对比</h3><strong>{report.transcriptComparison.status === "available" ? "正文对比已完成" : "缺少可比对的官方正文"}</strong><p>{report.transcriptComparison.note}</p></section>
    <a className="source-link" href={report.sourceUrl} target="_blank" rel="noreferrer"><ExternalLink />查看官方原文</a>
  </div>;
}

export function PolicyAnalysisApp() {
  const moduleParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const moduleId = moduleParams.get("mod") || "policy-analysis";
  const requestedView = moduleParams.get("view") as View | null;
  const defaultView: View = requestedView && ["calendar", "feed", "interpretation", "sources"].includes(requestedView) ? requestedView : "calendar";
  const embedded = window.parent !== window;
  const [data, setData] = useState<PolicyDashboard | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [view, setView] = useState<View>(defaultView);
  const [documentType, setDocumentType] = useState<DocumentTypeFilter>("all");
  const [lifecycle, setLifecycle] = useState<LifecycleFilter>("all");
  const [level, setLevel] = useState<0 | 1 | 2 | 3>(0);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [host, setHost] = useState<EmbeddedHost>();
  const [reviewing, setReviewing] = useState(false);
  const [interpreting, setInterpreting] = useState(false);
  const [interpretations, setInterpretations] = useState<Record<string, PolicyInterpretation>>({});
  const [wikiEntityId, setWikiEntityId] = useState<string | null>(null);

  const filteredByCommon = useMemo(() => (data?.events ?? []).filter((event) => {
    if (view === "sources" || !belongsToView(event, view)) return false;
    if (view !== "interpretation" && documentType !== "all" && event.documentType !== documentType) return false;
    if (level && event.level !== level) return false;
    const needle = query.trim().toLowerCase();
    return !needle || [event.title, event.institution, event.category, ...event.marketScope]
      .join(" ").toLowerCase().includes(needle);
  }), [data, documentType, level, query, view]);
  const filtered = useMemo(() => lifecycle === "all"
    ? filteredByCommon
    : filteredByCommon.filter((event) => event.lifecycleStage === lifecycle),
  [filteredByCommon, lifecycle]);
  const lifecycleCounts = useMemo(() => {
    const counts = Object.fromEntries(ALL_LIFECYCLE_STAGES.map((stage) => [stage, 0])) as Record<PolicyLifecycleStage, number>;
    for (const event of filteredByCommon) counts[event.lifecycleStage] += 1;
    return counts;
  }, [filteredByCommon]);

  const selected = useMemo(() => {
    return filtered.find((event) => event.id === selectedId) ?? filtered[0] ?? null;
  }, [filtered, selectedId]);
  const wikiEntity = selected?.entities.find((entity) => entity.canonicalId === wikiEntityId);
  const filters = useMemo(() => ({ view, documentType, lifecycle, level, query }), [documentType, level, lifecycle, query, view]);
  const contextRef = useRef(buildContext(data, selected, filters, wikiEntity));
  contextRef.current = buildContext(data, selected, filters, wikiEntity);

  useEffect(() => {
    document.title = VIEW_META[view].title + " · Newma-Desk";
    if (!document.documentElement.dataset.theme) document.documentElement.dataset.theme = "dark";
  }, [view]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    const request = refreshKey > 0 ? refreshPolicyDashboard : fetchPolicyDashboard;
    void request(controller.signal).then((payload) => {
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
      modId: moduleId, parentOrigin: parentOrigin(), sdkVersion: "0.1.0",
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
  }, [moduleId]);

  useEffect(() => host?.setContextProvider(() => contextRef.current), [host]);
  useEffect(() => { host?.publishContext(contextRef.current); }, [data, filters, host, selected, wikiEntity]);
  useEffect(() => host?.setUiActionHandler((actionId) => {
    if (actionId !== "policy.refresh") throw new Error("政策分析不支持动作 " + actionId);
    setRefreshKey((value) => value + 1); return { refreshed: true };
  }), [host]);

  const nextEvent = data?.summary.nextDate
    ? data.events.find((event) => event.date === data.summary.nextDate && event.status === "scheduled")
    : undefined;
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
    return [...grouped.entries()].sort(([left], [right]) => (view === "calendar" ? left.localeCompare(right) : right.localeCompare(left)));
  }, [filtered, view]);
  const relatedEvents = useMemo(() => selected ? (data?.events ?? []).filter(
    (event) => selected.relatedPolicyIds.includes(event.id),
  ).sort((left, right) => left.date.localeCompare(right.date)) : [], [data, selected]);
  const comparisonBase = selected?.comparison ? data?.events.find(
    (event) => event.id === selected.comparison?.basePolicyId,
  ) : undefined;
  const currentInterpretation = selected ? interpretations[selected.id] : undefined;
  const activeLifecycleStages = view === "sources" ? [] : VIEW_LIFECYCLE_STAGES[view];

  function changeView(nextView: View) {
    setView(nextView);
    setDocumentType("all");
    setLifecycle("all");
    setSelectedId(null);
    setWikiEntityId(null);
  }

  function openRelated(event: PolicyEvent) {
    setDocumentType("all"); setLifecycle("all"); setLevel(0); setQuery("");
    setView(belongsToView(event, "feed") ? "feed" : "calendar");
    setSelectedId(event.id);
    setWikiEntityId(null);
  }

  function selectLifecycle(stage: LifecycleFilter) {
    setLifecycle(stage);
  }

  async function confirmLevel(nextLevel: 1 | 2 | 3) {
    if (!selected || reviewing) return;
    setReviewing(true); setError("");
    try {
      const reviewed = await reviewPolicyAssessment(selected.id, nextLevel, "页面人工确认");
      setData((current) => current ? {
        ...current,
        events: current.events.map((event) => event.id === reviewed.id ? { ...event, ...reviewed } : event),
        summary: {
          ...current.summary,
          level3: current.events.reduce((total, event) => total + ((event.id === reviewed.id ? reviewed : event).level === 3 ? 1 : 0), 0),
        },
      } : current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "政策量级复核失败");
    } finally { setReviewing(false); }
  }

  async function generateInterpretation() {
    if (!selected || selected.status !== "published" || interpreting) return;
    setInterpreting(true); setError("");
    try {
      const result = await interpretPolicyEvent(selected.id);
      setInterpretations((current) => ({ ...current, [selected.id]: result }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "政策解读失败");
    } finally { setInterpreting(false); }
  }

  return (
    <main className="policy-root">
      <header className="policy-header" data-embedded={embedded || undefined}>
        {!embedded ? <div data-mod-page-title><span>POLICY INTELLIGENCE</span><h1>{VIEW_META[view].title}</h1><p>{VIEW_META[view].description}</p></div> : null}
        <button type="button" onClick={() => setRefreshKey((value) => value + 1)} disabled={loading} title="刷新政策数据">
          <RefreshCw size={17} className={loading ? "spin" : ""} /><span>刷新</span>
        </button>
      </header>

      <section className="summary-strip" aria-label="政策监测摘要">
        <div><CalendarDays /><span>下一窗口</span><strong>{nextEvent?.date.slice(5).replace("-", "/") ?? "--"}</strong><small>{nextEvent?.title ?? "暂无日程"}</small></div>
        <div><ShieldCheck /><span>战略级政策</span><strong>{data?.summary.level3 ?? 0}</strong><small>三级量级</small></div>
        <div><Clock3 /><span>未来日程</span><strong>{data?.summary.upcoming ?? 0}</strong><small>含预期窗口</small></div>
        <div><Landmark /><span>官方渠道</span><strong>{data?.sources.length ?? 0}</strong><small>一手来源优先</small></div>
      </section>

      {!embedded || view !== "sources" ? <section className="policy-toolbar">
        {!embedded ? <div className="segmented" role="tablist">
          <button className={view === "calendar" ? "active" : ""} onClick={() => changeView("calendar")}><CalendarDays />政策日历</button>
          <button className={view === "feed" ? "active" : ""} onClick={() => changeView("feed")}><FileSearch />政策流</button>
          <button className={view === "interpretation" ? "active" : ""} onClick={() => changeView("interpretation")}><BrainCircuit />政策解读</button>
          <button className={view === "sources" ? "active" : ""} onClick={() => changeView("sources")}><Landmark />渠道</button>
        </div> : null}
        {view !== "sources" ? <label className="search-box"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索政策、机构、行业" /></label> : null}
        {view !== "sources" && view !== "interpretation" ? <select aria-label="文档类型" value={documentType} onChange={(event) => setDocumentType(event.target.value as DocumentTypeFilter)}>
          <option value="all">全部类型</option>{Object.entries(DOCUMENT_TYPE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
        </select> : null}
        {view !== "sources" ? <div className="level-filter">
          {[0, 3, 2, 1].map((item) => <button key={item} className={level === item ? "active" : ""} onClick={() => setLevel(item as 0 | 1 | 2 | 3)}>{item === 0 ? "全部量级" : "L" + item}</button>)}
        </div> : null}
      </section> : null}
      {view !== "sources" && data ? <section className="lifecycle-strip" aria-label={`${VIEW_META[view].title}阶段筛选`}>
        <button type="button" className={lifecycle === "all" ? "active" : ""} onClick={() => selectLifecycle("all")}><span>{VIEW_ALL_LABELS[view]}</span><b>{filteredByCommon.length}</b></button>
        {activeLifecycleStages.map((stage) => <button type="button" className={lifecycle === stage ? "active" : ""} onClick={() => selectLifecycle(stage)} key={stage}><span>{LIFECYCLE_LABELS[stage]}</span><b>{lifecycleCounts[stage]}</b></button>)}
      </section> : null}

      {error ? <div className="error-banner">{error}</div> : null}
      {view === "sources" ? (
        <section className="source-view">
          <div className="section-heading"><div><span>OFFICIAL SOURCES</span><h2>政策渠道</h2></div><p>采集只作为发现入口，研究结论始终回链官方原文。</p></div>
          <div className="source-table">
            <div className="source-row head"><span>机构</span><span>覆盖范围</span><span>采集适配</span><span>入口</span></div>
            {data?.sources.map((source) => <div className="source-row" key={source.id}>
              <strong>{source.name}</strong><span>{source.categories.join(" · ")}</span>
              <span className="source-adapter"><span><code>{source.rssHubPath ?? "官方页面"}</code><small>{timestampLabel(feedState.get(source.id)?.lastSuccessAt)}</small></span>{source.rssHubPath ? <em className={feedState.get(source.id)?.status === "ok" ? "ok" : "failed"}>{feedState.get(source.id)?.status === "ok" ? "实时" : data?.collector.status === "not-configured" ? "历史" : "异常"}</em> : <em>官方页</em>}</span>
              <a href={source.url} target="_blank" rel="noreferrer">打开<ExternalLink /></a>
            </div>)}
          </div>
          <div className="collector-note"><ShieldCheck /><div><strong>{data?.collector.foundation} · {COLLECTOR_LABELS[data?.collector.status ?? ""] ?? data?.collector.status}</strong><span>{healthyFeeds}/{data?.collector.feeds.length ?? 0} 个采集渠道正常 · 本次合并 {collectedItems} 条官方动态</span></div><code>{data?.collector.revision.slice(0, 12)}</code></div>
        </section>
      ) : view === "interpretation" ? (
        <div className="interpretation-workspace">
          <section className="interpretation-list">
            <div className="section-heading"><div><span>AI POLICY RESEARCH</span><h2>已发布政策</h2></div><p>{filtered.length} 条</p></div>
            {loading ? <div className="empty-state">正在读取政策数据</div> : filtered.map((event) => <PolicyRow event={event} active={selected?.id === event.id} onSelect={() => setSelectedId(event.id)} key={event.id} />)}
          </section>
          <section className="interpretation-pane">
            {selected ? <>
              <header className="interpretation-header"><div><span className={"level-tag l" + selected.level}>L{selected.level}</span><h2>{selected.title}</h2><p>{selected.institution} · {selected.date}</p></div><button type="button" onClick={() => void generateInterpretation()} disabled={interpreting}>{interpreting ? <RefreshCw className="spin" /> : <Sparkles />}{currentInterpretation ? "重新解析" : "AI 解析"}</button></header>
              {currentInterpretation ? <InterpretationReport report={currentInterpretation} /> : <div className="interpretation-empty"><BrainCircuit /><strong>生成政策研究解读</strong><span>影响分析、同类政策历史对比推演与逐字稿对比条件检查。</span></div>}
            </> : <div className="empty-state">选择一条已发布政策</div>}
          </section>
        </div>
      ) : (
        <div className="policy-workspace">
          <section className="event-pane">
            <div className="section-heading"><div><span>{view === "calendar" ? "RELEASE CALENDAR" : "POLICY FEED"}</span><h2>{view === "calendar" ? "政策日历" : "政策流"}</h2></div><p>{filtered.length} 条</p></div>
            {loading ? <div className="empty-state">正在读取政策数据</div> : months.length === 0 ? <div className="empty-state">没有匹配的政策</div> : view === "calendar" ? months.map(([month, events]) => (
              <CalendarMonth month={month} events={events} selectedId={selected?.id ?? null} onSelect={setSelectedId} key={month} />
            )) : months.map(([month, events]) => (
              <section className="month-group" key={month}><h3>{monthLabel(month)}</h3>{events.map((event) => <PolicyRow event={event} active={selected?.id === event.id} onSelect={() => setSelectedId(event.id)} key={event.id} />)}</section>
            ))}
          </section>
          <aside className="detail-pane">
            {selected ? <>
              <div className="detail-status"><span className={"level-tag l" + selected.level}>L{selected.level} {LEVEL_LABELS[selected.level]}</span><span>{LIFECYCLE_LABELS[selected.lifecycleStage]}</span>{LIFECYCLE_LABELS[selected.lifecycleStage] !== DOCUMENT_TYPE_LABELS[selected.documentType] ? <span>{DOCUMENT_TYPE_LABELS[selected.documentType]}</span> : null}<span>{CERTAINTY_LABELS[selected.certainty]}</span></div>
              <h2>{selected.title}</h2><p className="detail-summary">{selected.summary}</p>
              <dl><div><dt>日期</dt><dd>{selected.date}</dd></div><div><dt>发布机构</dt><dd>{selected.institution}</dd></div><div><dt>政策分类</dt><dd>{selected.category}</dd></div><div><dt>影响范围</dt><dd>{selected.marketScope.join("、")}</dd></div></dl>
              {selected.entities.length ? <section className="entity-block"><h3>关联实体 <span>规则识别</span></h3><div><button type="button" className={!wikiEntity ? "active" : ""} onClick={() => setWikiEntityId(null)}>当前政策</button>{selected.entities.map((entity) => <button type="button" className={wikiEntity?.canonicalId === entity.canonicalId ? "active" : ""} onClick={() => setWikiEntityId(entity.canonicalId)} title={`证据：${entity.evidence} · 置信度 ${Math.round(entity.confidence * 100)}%`} key={entity.canonicalId}>{entity.displayName}<small>{entity.type === "industry" ? "行业" : entity.type === "concept" ? "概念" : entity.type === "etf" ? "ETF" : "股票"}</small></button>)}</div><p>点击标签会更新页面顶部的关联研究 Mod。</p></section> : null}
              <section className="assessment-block"><h3>量级评估依据</h3><p>{selected.assessmentStatus === "reviewed" ? "人工确认" : "规则初筛"} · 置信度 {Math.round(selected.assessmentConfidence * 100)}%</p><ul>{selected.rationale.map((item) => <li key={item}>{item}</li>)}</ul><div className="review-levels" aria-label="人工确认量级">{([1, 2, 3] as const).map((item) => <button type="button" disabled={reviewing} className={selected.level === item && selected.assessmentStatus === "reviewed" ? "active" : ""} onClick={() => void confirmLevel(item)} key={item}>确认 L{item}</button>)}</div></section>
              {relatedEvents.length ? <section className="policy-chain"><h3><Link2 />关联文件 · {relatedEvents.length + 1}</h3><button type="button" className="current"><time>{selected.date}</time><span>{LIFECYCLE_LABELS[selected.lifecycleStage]}</span><strong>{selected.title}</strong></button>{relatedEvents.map((event) => <button type="button" onClick={() => openRelated(event)} key={event.id}><time>{event.date}</time><span>{LIFECYCLE_LABELS[event.lifecycleStage]}</span><strong>{event.title}</strong></button>)}</section> : null}
              {selected.comparison && comparisonBase ? <section className="comparison-block"><h3>摘要要素差异</h3><p>对比：{comparisonBase.title}</p><div><section><b>新增</b>{selected.comparison.added.length ? selected.comparison.added.map((item) => <span className="added" key={item}>{item}</span>) : <small>无明显新增要素</small>}</section><section><b>减少</b>{selected.comparison.removed.length ? selected.comparison.removed.map((item) => <span className="removed" key={item}>{item}</span>) : <small>无明显减少要素</small>}</section><section><b>共同</b>{selected.comparison.shared.length ? selected.comparison.shared.map((item) => <span key={item}>{item}</span>) : <small>无共同结构化要素</small>}</section></div><small>{selected.comparison.note}</small></section> : null}
              <a className="source-link" href={selected.sourceUrl} target="_blank" rel="noreferrer"><ExternalLink />查看官方原文</a>
              <section className="level-guide"><h3>三级量级口径</h3>{data?.assessment.map((item) => <div key={item.level}><b className={"level-tag l" + item.level}>L{item.level}</b><span><strong>{item.label}</strong><small>{item.definition}</small></span></div>)}</section>
            </> : <div className="empty-state">选择一条政策查看详情</div>}
          </aside>
        </div>
      )}
    </main>
  );
}
