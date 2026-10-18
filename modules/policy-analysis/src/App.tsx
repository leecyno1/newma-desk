import {
  BrainCircuit, CalendarDays, Clock3, ExternalLink, FileSearch, Landmark, Link2, RefreshCw,
  Search, ShieldCheck, Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { DeskInit, ModPageContext } from "@newma-desk/contracts";
import type { WikiPageContext, WikiSubjectRef } from "@newma-desk/contracts";
import { connectModHost, type ModHostConnection } from "@newma-desk/mod-sdk";

import { fetchPolicyDashboard, importOfficialPolicy, interpretPolicyEvent, policyDocument, refreshPolicyDashboard, reviewPolicyAssessment } from "./api";
import { PolicyDocumentPanel } from "./PolicyDocumentPanel";
import { PolicyResearchReport } from "./PolicyResearchReport";
import { PolicyCalendar } from "./PolicyCalendar";
import { policyCalendarEntries, type CalendarBasis } from "./calendar";
import { sourceCoverage, withinPolicyWindow } from "./research";
import { PolicyNotebook, type PolicyNotebookContext } from "./PolicyNotebook";
import type {
  PolicyDashboard, PolicyDocument, PolicyDocumentType, PolicyEntity, PolicyEvent, PolicyInterpretation, PolicyLifecycleStage,
} from "./types";

type View = "calendar" | "feed" | "interpretation" | "sources";
type DocumentTypeFilter = "all" | PolicyDocumentType;
type LifecycleFilter = "all" | PolicyLifecycleStage;
type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;
type EventView = Exclude<View, "sources">;

const VIEW_META: Record<View, { title: string; description: string }> = {
  calendar: { title: "政策日历", description: "发布、明确施行与滚动预期日程" },
  feed: { title: "政策流", description: "官方政策发布、量级与生命周期" },
  interpretation: { title: "政策解读", description: "影响分析、历史推演与原文对比" },
  sources: { title: "政策渠道", description: "官方来源、采集状态与证据边界" },
};

const LEVEL_LABELS = { 1: "执行级", 2: "行业级", 3: "战略级" } as const;
const CERTAINTY_LABELS = {
  official: "官方日期", "calendar-rule": "固定日历", "expected-window": "预期窗口",
} as const;
const COLLECTOR_LABELS: Record<string, string> = {
  ready: "最近采集成功", degraded: "部分渠道异常", unavailable: "采集不可用", "not-configured": "待配置采集器",
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
  calendar: ["scheduled", "solicitation", "published", "effective", "amended", "adjusted"],
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
  moduleId: string,
  data: PolicyDashboard | null,
  selected: PolicyEvent | null,
  filters: Record<string, unknown>,
  wikiEntity?: PolicyEntity,
  interpretation?: PolicyInterpretation,
  document?: PolicyDocument,
  documentReadError?: string,
  documentReading = false,
  notebook?: PolicyNotebookContext,
): ModPageContext {
  const currentView = filters.view as View;
  const wiki = selected ? policyWikiContext(selected, wikiEntity) : undefined;
  const relatedPolicies = selected
    ? (data?.events ?? [])
      .filter((event) => selected.relatedPolicyIds.includes(event.id))
      .map((event) => ({
        id: event.id,
        title: event.title,
        date: event.date,
        summary: event.summary,
        sourceUrl: event.sourceUrl,
      }))
    : [];
  const visibleBlocks = currentView === "interpretation"
    ? [
        { id: "selected-policy", type: "policy-document", title: "当前政策" },
        { id: "official-document", type: "policy-evidence", title: "官方正文证据" },
        { id: "research-followup", type: "policy-followup", title: "研究跟踪" },
        ...(interpretation ? [
          { id: "rule-baseline", type: "policy-interpretation", title: "证据研究底稿" },
          { id: "transmission", type: "policy-hypotheses", title: "投资传导与验证" },
          { id: "official-text-comparison", type: "policy-comparison", title: "官方正文差异" },
        ] : []),
      ]
    : currentView === "sources"
      ? [{ id: "policy-sources", type: "source-registry", title: "官方政策渠道" }]
      : [
          {
            id: currentView === "calendar" ? "policy-calendar" : "policy-feed",
            type: currentView === "calendar" ? "event-calendar" : "policy-feed",
            title: currentView === "calendar" ? "发布与施行日程" : "政策流",
          },
          { id: "policy-assessment", type: "policy-assessment", title: "政策量级评估" },
        ];
  return {
    view: { id: moduleId, title: VIEW_META[currentView].title },
    visibleBlocks,
    selection: selected ? {
      policyId: selected.id,
      title: selected.title,
      date: selected.date,
      institution: selected.institution,
      category: selected.category,
      level: selected.level,
      lifecycleStage: selected.lifecycleStage,
      documentType: selected.documentType,
      summary: selected.summary,
      rationale: selected.rationale,
      marketScope: selected.marketScope,
      sourceUrl: selected.sourceUrl,
      documentEvidence: selected.documentEvidence ?? null,
      lifecycleBasis: selected.lifecycleBasis ?? "title-rule",
    } : {},
    filters,
    data: {
      source: "official-policy-registry",
      freshness: data?.collector.status === "ready" && data.collector.feeds.every((feed) =>
        feed.lastSuccessAt && Date.now() - Date.parse(feed.lastSuccessAt) < 24 * 3600_000,
      ) ? "fresh" : data?.collector.collectedAt ? "stale" : "unknown",
      ...(data ? {
        ...(data.collector.collectedAt ? { asOf: data.collector.collectedAt } : {}),
        summary: {
          dashboard: data.summary,
          pageGeneratedAt: data.generatedAt,
          relatedPolicies,
          collector: data.collector,
          documentRead: { status: documentReading ? "running" : documentReadError ? "failed" : document?.status || "missing", error: documentReadError || null },
          ...(document ? { officialDocument: { ...document, paragraphs: undefined } } : {}),
          ...(interpretation ? { ruleAnalysis: { ...interpretation, document: undefined,
            documentRevision: interpretation.document?.revision, sourceDocumentFetchedAt: interpretation.document?.fetchedAt,
            bodyVersionMismatch: Boolean(document?.revision && interpretation.document?.revision && document.revision !== interpretation.document.revision),
          } } : {}),
          ...(notebook?.policyId === selected?.id ? { researchFollowup: notebook } : {}),
        },
      } : {}),
    },
    actions: [
      {
        id: "policy.refresh", label: "刷新政策数据", available: true,
        inputSchema: { type: "object", additionalProperties: false },
      },
      ...(moduleId === "policy-interpretation" ? [{
        id: "policy.interpret",
        label: "交给配置的 Agent 深入解读",
        available: selected?.status === "published",
      }] : []),
    ],
    ...(wiki ? { wiki } : {}),
    tasks: [],
  };
}

function policyAgentPrompt(event: PolicyEvent): string {
  return [
    `请用快速、轻量的方式深入解读当前政策《${event.title}》。`,
    "先读取当前「政策解读」Mod 的结构化页面上下文；以 selection、relatedPolicies、ruleAnalysis 和官方链接为证据。",
    "输出核心结论、已知事实、影响推断、历史差异、关键不确定性和最需要关注的三件事。",
    "优先引用 officialDocument 中的正文与日期；区分网页发布、成文、施行、采集时间。政策量级理由是判断，不是官方事实。",
    "不得把摘要当作政策全文；没有两份官方正文时，明确说明不能进行逐条对比，不要补造数据。",
    "researchFollowup 是用户研究草稿/跟踪记录，跟踪状态不是投资验证结论。若 bodyVersionMismatch 为真，明确指出底稿与当前正文版本不一致。",
  ].join("\n");
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
          {event.status === "published" ? <em className={event.documentEvidence?.status === "available" ? "evidence-ready" : "evidence-missing"}>{event.documentEvidence?.status === "available" ? `正文 v${event.documentEvidence.revision}` : "正文待读取"}</em> : null}
        </span>
        <strong>{event.title}</strong><small>{event.institution} · {event.category}</small>
      </span>
    </button>
  );
}

function InterpretationReport({ report }: { report: PolicyInterpretation }) {
  return <div className="interpretation-report">
    <div className="interpretation-mode"><ShieldCheck /><strong>证据研究底稿</strong><span>事实与推断分开；AI 分析使用 Desk 当前配置的 Agent</span></div>
    <PolicyResearchReport report={report} />
    <section><h3><ShieldCheck />证据分层</h3><div className="analysis-columns"><div><b>{report.impactAnalysis.basis === "official-text-excerpts" ? "官方正文节选" : "采集摘要（非全文）"}</b>{report.impactAnalysis.facts.map((item) => <p key={item}>{item}</p>)}</div><div><b>量级判断（非官方事实）</b>{report.assessment?.rationale.map((item) => <p key={item}>{item}</p>)}</div><div><b>不确定性</b>{report.impactAnalysis.uncertainties.map((item) => <p key={item}>{item}</p>)}</div></div></section>
    <section><h3><Clock3 />历史摘要参考</h3>{report.historicalComparison.matchedPolicies.length ? <div className="history-matches">{report.historicalComparison.matchedPolicies.map((item) => <span key={item.id}>{item.date} · {item.title}</span>)}</div> : <p className="muted-note">尚未识别到更早的同系列正式文件。</p>}<div className="comparison-points"><div><b>新增要素</b>{report.historicalComparison.added.map((item) => <span key={item}>{item}</span>)}</div><div><b>缺少要素</b>{report.historicalComparison.removed.map((item) => <span key={item}>{item}</span>)}</div><div><b>共同要素</b>{report.historicalComparison.shared.map((item) => <span key={item}>{item}</span>)}</div></div><small>{report.historicalComparison.note}</small></section>
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
  const [selectedId, setSelectedId] = useState<string | null>(moduleParams.get("policy"));
  const [host, setHost] = useState<EmbeddedHost>();
  const [hostConfig, setHostConfig] = useState<DeskInit>();
  const [notebookContext, setNotebookContext] = useState<PolicyNotebookContext>();
  const [reviewing, setReviewing] = useState(false);
  const [interpreting, setInterpreting] = useState(false);
  const [interpretations, setInterpretations] = useState<Record<string, PolicyInterpretation>>({});
  const [wikiEntityId, setWikiEntityId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<Record<string, PolicyDocument>>({});
  const [readingId, setReadingId] = useState<string | null>(null);
  const [documentErrors, setDocumentErrors] = useState<Record<string, string>>({});
  const [importUrl, setImportUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [calendarMonth, setCalendarMonth] = useState("");
  const [calendarBasis, setCalendarBasis] = useState<CalendarBasis>("all");
  const [calendarMode, setCalendarMode] = useState<"month" | "agenda">("month");
  const [selectedCalendarId, setSelectedCalendarId] = useState<string | null>(null);
  const [institution, setInstitution] = useState("all");
  const [evidenceOnly, setEvidenceOnly] = useState(false);
  const [feedDays, setFeedDays] = useState(moduleParams.has("policy") ? 0 : 90);
  const [sourceAnomalies, setSourceAnomalies] = useState(false);
  const institutions = useMemo(() => [...new Set((data?.events ?? []).filter((event) => event.status === "published").map((event) => event.institution))].sort(), [data]);

  const filteredByCommon = useMemo(() => (data?.events ?? []).filter((event) => {
    if (view === "sources" || !belongsToView(event, view)) return false;
    if (view !== "interpretation" && documentType !== "all" && event.documentType !== documentType) return false;
    if (level && event.level !== level) return false;
    if (view !== "calendar" && institution !== "all" && event.institution !== institution) return false;
    if (view !== "calendar" && evidenceOnly && event.documentEvidence?.status !== "available") return false;
    if (view === "feed" && data && !withinPolicyWindow(event, data.today, feedDays)) return false;
    const needle = query.trim().toLowerCase();
    return !needle || [event.title, event.institution, event.category, ...event.marketScope]
      .join(" ").toLowerCase().includes(needle);
  }).sort((a, b) => b.date.localeCompare(a.date) || a.id.localeCompare(b.id)), [data, documentType, level, query, view, institution, evidenceOnly, feedDays]);
  const filtered = useMemo(() => lifecycle === "all"
    ? filteredByCommon
    : filteredByCommon.filter((event) => event.lifecycleStage === lifecycle),
  [filteredByCommon, lifecycle]);
  const lifecycleCounts = useMemo(() => {
    const counts = Object.fromEntries(ALL_LIFECYCLE_STAGES.map((stage) => [stage, 0])) as Record<PolicyLifecycleStage, number>;
    for (const event of filteredByCommon) counts[event.lifecycleStage] += 1;
    return counts;
  }, [filteredByCommon]);

  const activeMonth = calendarMonth || data?.today.slice(0, 7) || new Date().toISOString().slice(0, 7);
  const calendarEntries = useMemo(() => policyCalendarEntries(filtered).filter((entry) =>
    entry.date.startsWith(activeMonth) && (calendarBasis === "all" || entry.kind === calendarBasis)),
  [filtered, activeMonth, calendarBasis]);
  const selectedCalendarEntry = calendarEntries.find((entry) => entry.id === selectedCalendarId)
    ?? calendarEntries.find((entry) => entry.event.id === selectedId) ?? calendarEntries[0];
  const selected = view === "calendar" ? selectedCalendarEntry?.event ?? null
    : filtered.find((event) => event.id === selectedId) ?? filtered[0] ?? null;
  const currentInterpretation = selected ? interpretations[selected.id] : undefined;
  const currentDocument = selected ? documents[selected.id] : undefined;
  const currentDocumentError = selected ? documentErrors[selected.id] : undefined;
  const currentDocumentReading = readingId !== null && readingId === selected?.id;
  const wikiEntity = selected?.entities.find((entity) => entity.canonicalId === wikiEntityId);
  const filters = useMemo(() => ({ view, documentType, lifecycle, level, query,
    ...(view === "feed" || view === "interpretation" ? { institution, evidenceOnly, ...(view === "feed" ? { days: feedDays } : {}), visiblePolicyIds: filtered.map((event) => event.id) } : {}),
    ...(view === "sources" ? { anomaliesOnly: sourceAnomalies, visibleSources: (data?.sources ?? [])
      .filter((source) => !sourceAnomalies || data?.collector.feeds.find((feed) => feed.sourceId === source.id)?.status !== "ok")
      .map((source) => ({ id: source.id, name: source.name, ...sourceCoverage(source, data?.events ?? []) })) } : {}),
    ...(view === "calendar" ? { month: activeMonth, dateBasis: calendarBasis, calendarMode,
      selectedDate: selectedCalendarEntry ? { date: selectedCalendarEntry.date, kind: selectedCalendarEntry.kind } : null,
      visibleDates: calendarEntries.map((entry) => ({ id: entry.id, policyId: entry.event.id, title: entry.event.title, date: entry.date, kind: entry.kind, label: entry.label })),
    } : {}),
  }), [documentType, level, lifecycle, query, view, activeMonth, calendarBasis, calendarMode, calendarEntries, selectedCalendarEntry, institution, evidenceOnly, feedDays, filtered, sourceAnomalies]);
  const contextRef = useRef(buildContext(moduleId, data, selected, filters, wikiEntity, currentInterpretation, currentDocument, currentDocumentError, currentDocumentReading));
  const scopedNotebook = hostConfig && notebookContext?.userId === hostConfig.user.id
    && notebookContext?.workspaceId === hostConfig.workspace.id ? notebookContext : undefined;
  contextRef.current = buildContext(moduleId, data, selected, filters, wikiEntity, currentInterpretation, currentDocument, currentDocumentError, currentDocumentReading, scopedNotebook);

  useEffect(() => {
    if (!selected || selected.status !== "published") return;
    const id = selected.id;
    const controller = new AbortController();
    void policyDocument(id, false, controller.signal).then((document) => {
      if (controller.signal.aborted) return;
      setDocuments((current) => current[id]?.status === "available" && (
        document.status !== "available" || (current[id].revision ?? 0) > (document.revision ?? 0)
      ) ? current : { ...current, [id]: document });
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setDocumentErrors((current) => ({ ...current, [id]: reason instanceof Error ? reason.message : "正文记录读取失败" }));
    });
    return () => controller.abort();
  }, [selected?.id]);

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
      capabilities: ["actions", "agent", "context", "theme", "storage"], signal: controller.signal,
    }).then((connection) => {
      close = connection.close;
      if (!connection.embedded) return;
      setHost(connection);
      setHostConfig(connection.config);
      document.documentElement.dataset.theme = connection.config.environment.theme;
      unsubscribe = connection.subscribe((config) => {
        document.documentElement.dataset.theme = config.environment.theme;
        setHostConfig(config);
      });
    }).catch(() => undefined);
    return () => { controller.abort(); unsubscribe(); close(); };
  }, [moduleId]);

  useEffect(() => host?.setContextProvider(() => contextRef.current), [host]);
  useEffect(() => { host?.publishContext(contextRef.current); }, [data, filters, host, selected, wikiEntity, currentDocument, currentInterpretation, currentDocumentError, currentDocumentReading, scopedNotebook]);
  useEffect(() => host?.setUiActionHandler((actionId) => {
    if (actionId !== "policy.refresh") throw new Error("政策分析不支持动作 " + actionId);
    setRefreshKey((value) => value + 1); return { refreshed: true };
  }), [host]);

  const upcomingDates = useMemo(() => policyCalendarEntries(data?.events ?? []).filter((entry) =>
    entry.date >= (data?.today ?? "") && entry.kind !== "publication"), [data]);
  const nextEvent = upcomingDates[0];
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
  const configuredAgentAvailable = Boolean(host);
  const activeLifecycleStages = view === "sources" ? [] : VIEW_LIFECYCLE_STAGES[view];

  function changeView(nextView: View) {
    setView(nextView);
    setDocumentType("all");
    setLifecycle("all");
    setSelectedId(null);
    setWikiEntityId(null);
    setInstitution("all"); setEvidenceOnly(false);
  }

  function openRelated(event: PolicyEvent) {
    setDocumentType("all"); setLifecycle("all"); setLevel(0); setQuery("");
    setInstitution("all"); setEvidenceOnly(false); setFeedDays(0);
    setView(belongsToView(event, "feed") ? "feed" : "calendar");
    setSelectedId(event.id);
    setCalendarMonth(event.date.slice(0, 7)); setSelectedCalendarId(null);
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

  async function readDocument() {
    if (!selected || readingId || interpreting || importing) return;
    const id = selected.id;
    setReadingId(id); setDocumentErrors((current) => ({ ...current, [id]: "" }));
    try {
      const document = await policyDocument(id, true);
      setDocuments((current) => ({ ...current, [id]: document }));
      setInterpretations((current) => { const next = { ...current }; delete next[id]; return next; });
      setData((current) => current ? { ...current, events: current.events.map((event) => event.id === id
        ? { ...event, documentEvidence: { ...document, text: undefined, paragraphs: undefined, attachments: undefined } }
        : event) } : current);
    } catch (reason) {
      setDocumentErrors((current) => ({ ...current, [id]: reason instanceof Error ? reason.message : "官方正文读取失败" }));
    } finally { setReadingId(null); }
  }

  async function importPolicy() {
    if (!importUrl.trim() || importing) return;
    setImporting(true); setError("");
    try {
      const result = await importOfficialPolicy(importUrl);
      const payload = await fetchPolicyDashboard();
      setData(payload); setDocuments((current) => ({ ...current, [result.event.id]: result.document }));
      setLevel(0); setQuery(""); setDocumentType("all"); setLifecycle("all");
      setInstitution("all"); setEvidenceOnly(false); setFeedDays(0);
      if (!embedded || view === "interpretation") setView(result.event.documentType === "formal-policy" ? "interpretation" : "feed");
      setSelectedId(result.event.id); setImportUrl("");
      setCalendarMonth(result.event.date.slice(0, 7)); setSelectedCalendarId(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "官方政策导入失败");
    } finally { setImporting(false); }
  }

  function exportResearch() {
    if (!selected || !currentInterpretation) return;
    const artifact = {
      ...currentInterpretation,
      schemaVersion: "newma-desk.policy-research.v1", policyDate: selected.date,
      reviewStatus: "unreviewed",
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(artifact, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `policy-research-${selected.id}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <main className="policy-root" data-view={view}>
      {!embedded ? <header className="policy-header">
        {!embedded ? <div data-mod-page-title><span>POLICY INTELLIGENCE</span><h1>{VIEW_META[view].title}</h1><p>{VIEW_META[view].description}</p></div> : null}
        <button type="button" onClick={() => setRefreshKey((value) => value + 1)} disabled={loading} title="刷新政策数据">
          <RefreshCw size={17} className={loading ? "spin" : ""} /><span>刷新</span>
        </button>
      </header> : null}

      <section className="summary-strip" aria-label="政策监测摘要">
        <div><CalendarDays /><span>下一日期</span><strong>{nextEvent?.date.slice(5).replace("-", "/") ?? "--"}</strong><small>{nextEvent ? `${nextEvent.label} · ${nextEvent.event.title}` : "暂无已载入日程"}</small></div>
        <div><ShieldCheck /><span>战略级政策</span><strong>{data?.summary.level3 ?? 0}</strong><small>三级量级</small></div>
        <div><Clock3 /><span>未来日期</span><strong>{upcomingDates.length}</strong><small>明确施行＋日程窗口</small></div>
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
        {view === "feed" || view === "interpretation" ? <select aria-label="发布机构" value={institution} onChange={(event) => setInstitution(event.target.value)}><option value="all">全部机构</option>{institutions.map((name) => <option key={name}>{name}</option>)}</select> : null}
        {view === "feed" ? <select aria-label="发布范围" value={feedDays} onChange={(event) => setFeedDays(Number(event.target.value))}><option value={30}>近 30 天</option><option value={90}>近 90 天</option><option value={0}>全部历史</option></select> : null}
        {view === "feed" || view === "interpretation" ? <label className="evidence-filter"><input type="checkbox" checked={evidenceOnly} onChange={(event) => setEvidenceOnly(event.target.checked)} />已有正文</label> : null}
        {view !== "sources" ? <div className="level-filter">
          {[0, 3, 2, 1].map((item) => <button key={item} className={level === item ? "active" : ""} onClick={() => setLevel(item as 0 | 1 | 2 | 3)}>{item === 0 ? "全部量级" : "L" + item}</button>)}
        </div> : null}
      </section> : null}
      {view !== "sources" && data ? <section className="lifecycle-strip" aria-label={`${VIEW_META[view].title}阶段筛选`}>
        <button type="button" className={lifecycle === "all" ? "active" : ""} onClick={() => selectLifecycle("all")}><span>{VIEW_ALL_LABELS[view]}</span><b>{filteredByCommon.length}</b></button>
        {activeLifecycleStages.map((stage) => <button type="button" className={lifecycle === stage ? "active" : ""} onClick={() => selectLifecycle(stage)} key={stage}><span>{LIFECYCLE_LABELS[stage]}</span><b>{lifecycleCounts[stage]}</b></button>)}
      </section> : null}

      {error ? <div className="error-banner">{error}</div> : null}
      {view !== "sources" ? <form className="official-import" onSubmit={(event) => { event.preventDefault(); void importPolicy(); }}>
        <input aria-label="官方政策链接" type="url" value={importUrl} onChange={(event) => setImportUrl(event.target.value)} placeholder="粘贴官方政策正文链接，不接受媒体转述" />
        <button disabled={importing || !importUrl.trim()}>{importing ? "正在导入…" : "导入官方政策"}</button>
      </form> : null}
      {data ? <div className="collection-health" role="status"><span className={`health-light ${data.collector.status}`} /><span>{COLLECTOR_LABELS[data.collector.status] || "采集状态未知"} · 最近记录 {healthyFeeds}/{data.collector.feeds.length} 个渠道成功 · 最近尝试 {data.collector.collectedAt ? timestampLabel(data.collector.collectedAt) : "未知"} · 刷新页面不代表政策已更新</span>{embedded ? <button type="button" onClick={() => setRefreshKey((value) => value + 1)} disabled={loading}><RefreshCw size={14} className={loading ? "spin" : ""} />刷新</button> : null}</div> : null}
      {view === "sources" ? (
        <section className="source-view">
          <div className="section-heading"><div><span>OFFICIAL SOURCES</span><h2>官方来源与采集状态</h2></div><p>采集只作为发现入口，研究结论始终回链官方原文。</p></div>
          <div className="source-coverage-heading"><label><input type="checkbox" checked={sourceAnomalies} onChange={(event) => setSourceAnomalies(event.target.checked)} />只看异常或未配置渠道</label><span>正文覆盖仅统计本地已载入记录，不代表官方完整文库。</span></div>
          <div className="source-table">
            <div className="source-row head"><span>机构 / 研究范围</span><span>正文覆盖</span><span>采集状态 / 最近成功</span><span>入口</span></div>
            {data?.sources.filter((source) => !sourceAnomalies || feedState.get(source.id)?.status !== "ok").map((source) => <div className="source-row" key={source.id}>
              <div className="source-identity"><strong>{source.name}</strong><small>{source.categories.join(" · ")}</small></div><div className="source-coverage"><b>{sourceCoverage(source, data.events).readable} / {sourceCoverage(source, data.events).discovered}</b><small>正文可读 / 已载入</small></div>
              <div className="source-adapter"><div><code>{source.rssHubPath ?? "官方页面"}</code><small>最后成功：{timestampLabel(feedState.get(source.id)?.lastSuccessAt)}</small><small>最近尝试：{timestampLabel(feedState.get(source.id)?.lastAttemptAt)}</small>{feedState.get(source.id)?.reason ? <details><summary>查看失败原因</summary><p>{feedState.get(source.id)?.reason}</p></details> : null}</div>{source.rssHubPath ? <em className={feedState.get(source.id)?.status === "ok" ? "ok" : "failed"}>{feedState.get(source.id)?.status === "ok" ? "上次成功" : data?.collector.status === "not-configured" ? "未配置" : "异常"}</em> : <em>官方页</em>}</div>
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
              <header className="interpretation-header"><div><span className={"level-tag l" + selected.level}>L{selected.level} · {selected.assessmentStatus === "reviewed" ? "人工确认" : "规则初筛"}</span><h2>{selected.title}</h2><p>{selected.institution} · 发布记录 {selected.date}</p></div><div className="interpretation-actions"><button type="button" onClick={() => void generateInterpretation()} disabled={interpreting || !!readingId}>{interpreting ? <RefreshCw className="spin" /> : <ShieldCheck />}{interpreting ? "正在生成…" : "生成研究底稿"}</button>{currentInterpretation ? <button type="button" onClick={exportResearch}>导出研究底稿</button> : null}{configuredAgentAvailable ? <button type="button" onClick={() => { host?.publishContext(contextRef.current); host?.requestAgent({ mode: "ask", prompt: policyAgentPrompt(selected) }); }}><Sparkles />问 Agent</button> : null}</div></header>
              <PolicyDocumentPanel document={currentDocument} reading={readingId === selected.id} error={documentErrors[selected.id]} disabled={!!readingId || interpreting || importing} onRead={() => void readDocument()} />
              {currentInterpretation?.document?.revision && currentDocument?.revision && currentInterpretation.document.revision !== currentDocument.revision ? <p className="document-error">当前底稿引用正文 #{currentInterpretation.document.revision}，最新正文为 #{currentDocument.revision}。请重新生成并复核，旧底稿未自动更新。</p> : null}
              {currentInterpretation ? <InterpretationReport report={currentInterpretation} /> : <div className="interpretation-empty"><BrainCircuit /><strong>先核验正文，再判断投资影响</strong><span>研究底稿不依赖模型；AI 分析使用 Desk 配置的 Newma、本地 CLI 或 Copilot，不强制连接 Newma。</span></div>}
              <PolicyNotebook key={`${selected.id}:${hostConfig?.user.id}:${hostConfig?.workspace.id}`}
                config={hostConfig} policyId={selected.id} report={currentInterpretation}
                documentRevision={currentDocument?.revision}
                onContext={setNotebookContext}
                onRestore={(report) => setInterpretations((current) => ({ ...current, [selected.id]: report }))} />
            </> : <div className="empty-state">选择一条已发布政策</div>}
          </section>
        </div>
      ) : (
        <div className="policy-workspace">
          <section className="event-pane">
            <div className="section-heading"><div><span>{view === "calendar" ? "POLICY TIMELINE" : "POLICY FEED"}</span><h2>{view === "calendar" ? "发布与施行日程" : "官方发布研究清单"}</h2></div><p>{filtered.length} 条 · {filtered.filter((event) => event.documentEvidence?.status === "available").length} 份正文</p></div>
            {loading ? <div className="empty-state">正在读取政策数据</div> : view === "calendar" ? <PolicyCalendar
              month={activeMonth} today={data?.today ?? ""} basis={calendarBasis} mode={calendarMode}
              entries={calendarEntries} selectedId={selectedCalendarEntry?.id ?? null}
              onMonth={setCalendarMonth} onBasis={setCalendarBasis} onMode={setCalendarMode}
              onSelect={(entry) => { setSelectedCalendarId(entry.id); setSelectedId(entry.event.id); }}
            /> : !months.length ? <div className="empty-state">没有匹配的政策</div> : months.map(([month, events]) => (
              <section className="month-group" key={month}><h3>{monthLabel(month)}</h3>{events.map((event) => <PolicyRow event={event} active={selected?.id === event.id} onSelect={() => setSelectedId(event.id)} key={event.id} />)}</section>
            ))}
          </section>
          <aside className="detail-pane">
            {selected ? <>
              <div className="detail-status"><span className={"level-tag l" + selected.level}>L{selected.level} {LEVEL_LABELS[selected.level]}</span><span>{LIFECYCLE_LABELS[selected.lifecycleStage]}</span><span>{selected.lifecycleBasis === "official-effective-date" ? "施行条款已识别" : "状态按标题初筛"}</span>{LIFECYCLE_LABELS[selected.lifecycleStage] !== DOCUMENT_TYPE_LABELS[selected.documentType] ? <span>{DOCUMENT_TYPE_LABELS[selected.documentType]}</span> : null}<span>{CERTAINTY_LABELS[selected.certainty]}</span></div>
              <h2>{selected.title}</h2><p className="detail-summary">{selected.summary}</p>
              <dl>{view === "calendar" && selectedCalendarEntry?.kind === "effective" ? <div><dt>{selectedCalendarEntry.label}</dt><dd>{selectedCalendarEntry.date}</dd></div> : null}<div><dt>{selected.status === "published" ? "发布记录" : "日程窗口"}</dt><dd>{selected.date}</dd></div><div><dt>发布机构</dt><dd>{selected.institution}</dd></div><div><dt>政策分类</dt><dd>{selected.category}</dd></div><div><dt>影响范围</dt><dd>{selected.marketScope.join("、")}</dd></div></dl>
              {selected.status === "published" ? <PolicyDocumentPanel document={currentDocument} reading={readingId === selected.id} error={documentErrors[selected.id]} disabled={!!readingId || interpreting || importing} onRead={() => void readDocument()} /> : null}
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
