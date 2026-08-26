import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Bookmark,
  BookmarkCheck,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Database,
  ExternalLink,
  FolderPlus,
  Layers3,
  Plus,
  RefreshCw,
  Trash2,
  XCircle,
} from "lucide-react";

import { Disclaimer } from "@/components/ui/Disclaimer";
import { GlassCard } from "@/components/ui/GlassCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { api, type CatalystEvent, type CatalystFeed, type CatalystStatus, type CatalystType } from "@/lib/api";
import {
  hydrateCatalystTracker,
  loadLocalCatalystTracker,
  persistCatalystTracker,
  type CatalystTrackerState,
} from "@/lib/catalystTracker";
import { cn } from "@/lib/utils";
import {
  composeCatalystResearchGroups,
  createCatalystResearchGroup,
  loadLocalCatalystResearchGroups,
  loadWorkspacePortfolioResearchGroups,
  saveLocalCatalystResearchGroups,
  type CatalystResearchGroup,
} from "@/lib/researchGroups";
import { connectWorkspaceWatchlist, loadLocalWatchGroups } from "@/lib/watchlist";
import {
  createVibeDeskSnapshotCache,
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  subscribeVibeDeskConfig,
  type VibeDeskPageContext,
} from "@/lib/vibedesk";

const TYPE_LABEL: Record<CatalystType, string> = {
  earnings: "财报",
  corporate: "公司",
  industry: "行业",
  macro: "宏观",
  regulatory: "监管",
  lockup: "解禁",
  announcement: "公告",
  news: "新闻",
  research: "研报",
  custom: "自定义",
};

const STATUS_LABEL: Record<CatalystStatus, string> = {
  upcoming: "待发生",
  monitoring: "观察中",
  confirmed: "已确认",
  invalidated: "已证伪",
  expired: "已过期",
};

const IMPORTANCE_LABEL = { high: "高", medium: "中", low: "低" } as const;
const URGENCY_LABEL = { high: "高", medium: "中", low: "低" } as const;
const LEVEL_RANK = { high: 3, medium: 2, low: 1 } as const;
const DATE_BASIS_LABEL = {
  official: "官方日期",
  "announcement-derived": "公告观察窗",
  "model-window": "模型观察窗",
  "aggregated-calendar": "聚合日程 · 待复核",
  "signal-window": "主题信号窗",
  user: "自定义日期",
} as const;
const DATE_CHANGE_LABEL = { advanced: "日期提前", delayed: "日期延后", actual: "实际披露", unchanged: "日期未变" } as const;
const HORIZONS = [30, 90, 180, 365, 1095] as const;
type WorkView = "all" | "focus" | "tracked";

function eventBucket(event: CatalystEvent) {
  if (event.timePrecision === "window") return "window";
  if (event.dateBasis === "aggregated-calendar") return "scheduled";
  return "date";
}

function isFocusEvent(event: CatalystEvent) {
  if (event.dateChange && event.dateChange.direction !== "unchanged") return true;
  if (event.dateBasis === "aggregated-calendar") return event.importance === "high";
  if (event.dateBasis === "official") return event.importance === "high" || event.urgency === "high";
  if (event.dateBasis === "signal-window") return event.importance === "high" || event.urgency === "high";
  return event.importance === "high";
}

function groupScopeLabel(group?: CatalystResearchGroup) {
  if (!group) return "";
  const parts = [];
  if (group.symbols.length) parts.push(`${group.symbols.length} 个标的`);
  if (group.concepts.length) parts.push(`${group.concepts.length} 个概念`);
  if (group.includeMacro) parts.push("宏观日程");
  return parts.join(" · ") || "空范围";
}

function eventDate(event: CatalystEvent) {
  return event.date || event.windowEnd || event.windowStart || "9999-12-31";
}

function formatDate(value: string) {
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.valueOf())) return value;
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", weekday: "short" }).format(parsed);
}

function monthKey(value: string) {
  return value.slice(0, 7);
}

function applyTracker(feed: CatalystFeed | null, tracker: CatalystTrackerState) {
  const remote = feed?.items || [];
  return [...remote, ...tracker.customEvents]
    .map((event) => tracker.outcomes[event.id]
      ? { ...event, status: tracker.outcomes[event.id]!.status }
      : event)
    .sort((left, right) => eventDate(left).localeCompare(eventDate(right)));
}

function calendarContext(input: {
  feed: CatalystFeed | null;
  items: CatalystEvent[];
  selected?: CatalystEvent;
  groupName: string;
  groupSource: string;
  concepts: string[];
  includeMacro: boolean;
  horizon: number;
  type: CatalystType | "all";
  importance: CatalystEvent["importance"] | "all";
  workView: WorkView;
  trackedIds: string[];
  loading: boolean;
}): VibeDeskPageContext {
  return {
    view: { id: "catalyst-calendar", title: "催化剂日历" },
    visibleBlocks: [
      { id: "catalyst-preview", type: "weekly-preview", title: "近期催化预览" },
      { id: "catalyst-calendar", type: "catalyst-calendar", title: "催化剂日历" },
      { id: "catalyst-sources", type: "evidence-sources", title: "来源与缺口" },
    ],
    selection: {
      groupName: input.groupName,
      groupSource: input.groupSource,
      concepts: input.concepts,
      ...(input.selected ? { catalyst: input.selected } : {}),
    },
    filters: {
      horizonDays: input.horizon,
      type: input.type,
      importance: input.importance,
      workView: input.workView,
      includeMacro: input.includeMacro,
    },
    data: {
      asOf: input.feed?.generatedAt || new Date().toISOString(),
      source: input.feed?.schemaVersion || "newma-desk.catalyst-calendar.v1",
      freshness: input.loading ? "unknown" : "fresh",
      summary: {
        catalystCount: input.items.length,
        trackedCount: input.trackedIds.length,
        upcoming: input.items.slice(0, 30),
        sources: input.feed?.sources || [],
        gaps: input.feed?.gaps || [],
      },
    },
    actions: [
      { id: "catalyst.track", label: "跟踪催化剂", available: true },
      { id: "catalyst.add-custom", label: "添加自定义催化剂", available: true },
      { id: "catalyst.mark-outcome", label: "记录确认或证伪", available: true },
    ],
    tasks: [],
  };
}

export function CatalystCalendar() {
  const [customGroups, setCustomGroups] = useState(loadLocalCatalystResearchGroups);
  const [researchGroups, setResearchGroups] = useState(() => composeCatalystResearchGroups({
    watchGroups: loadLocalWatchGroups().groups,
    customGroups: loadLocalCatalystResearchGroups(),
  }));
  const [groupId, setGroupId] = useState(() => researchGroups[0]?.id || "system:macro-geopolitics");
  const [horizon, setHorizon] = useState<number>(180);
  const [type, setType] = useState<CatalystType | "all">("all");
  const [importance, setImportance] = useState<CatalystEvent["importance"] | "all">("all");
  const [workView, setWorkView] = useState<WorkView>("all");
  const [feed, setFeed] = useState<CatalystFeed | null>(null);
  const [tracker, setTracker] = useState(loadLocalCatalystTracker);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cacheRevision, setCacheRevision] = useState(0);
  const [showComposer, setShowComposer] = useState(false);
  const [showGroupComposer, setShowGroupComposer] = useState(false);
  const [groupError, setGroupError] = useState("");
  const [groupDraft, setGroupDraft] = useState({
    name: "",
    codes: "",
    concepts: "",
    includeMacro: true,
  });
  const [draft, setDraft] = useState({
    title: "",
    date: "",
    summary: "",
    importance: "medium" as CatalystEvent["importance"],
    confirmation: "",
    invalidation: "",
  });
  const activeGroup = researchGroups.find((group) => group.id === groupId) || researchGroups[0];
  const symbols = useMemo(() => Array.from(new Set(
    (activeGroup?.symbols || [])
      .filter((security) => security.market === "CN" && /^\d{6}$/.test(security.symbol))
      .map((security) => security.symbol),
  )).slice(0, 30), [activeGroup]);
  const concepts = useMemo(() => activeGroup?.concepts || [], [activeGroup]);
  const includeMacro = activeGroup?.includeMacro ?? true;
  const resourceKey = useMemo(() => [
    "catalyst-calendar",
    horizon,
    symbols.slice().sort().join(","),
    concepts.slice().sort().join(","),
    includeMacro ? "macro" : "company-only",
  ].join(":"), [concepts, horizon, includeMacro, symbols]);
  const cacheKey = `${resourceKey}:${cacheRevision}`;
  const cache = useMemo(() => createVibeDeskSnapshotCache<CatalystFeed>(resourceKey), [resourceKey]);
  const feedRef = useRef(feed);
  const resourceKeyRef = useRef<string | undefined>(undefined);
  feedRef.current = feed;

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    const cached = cache.read()?.value;
    const resourceChanged = resourceKeyRef.current !== cacheKey;
    resourceKeyRef.current = cacheKey;
    if (resourceChanged) setFeed(cached ?? null);
    try {
      const next = await api.catalysts(symbols, horizon, true, concepts, includeMacro);
      setFeed(next);
      cache.write(next, next.generatedAt);
    } catch (reason) {
      setError(cached || (!resourceChanged && feedRef.current)
        ? "更新失败，当前为上次数据"
        : reason instanceof Error ? reason.message : "催化剂数据暂时不可用");
    } finally {
      setLoading(false);
    }
  }, [cache, cacheKey, concepts, horizon, includeMacro, symbols]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => subscribeVibeDeskConfig(() => setCacheRevision((value) => value + 1)), []);
  useEffect(() => {
    let active = true;
    void Promise.allSettled([
      connectWorkspaceWatchlist().then((client) => client.load()),
      api.portfolio(),
      loadWorkspacePortfolioResearchGroups(),
    ]).then(([watchResult, localPortfolioResult, workspacePortfolioResult]) => {
      if (!active) return;
      const watchGroups = watchResult.status === "fulfilled"
        ? watchResult.value.groups
        : loadLocalWatchGroups().groups;
      const localPortfolio = localPortfolioResult.status === "fulfilled"
        ? localPortfolioResult.value
        : null;
      const workspacePortfolioGroups = workspacePortfolioResult.status === "fulfilled"
        ? workspacePortfolioResult.value
        : [];
      const next = composeCatalystResearchGroups({
        watchGroups,
        customGroups,
        localPortfolio,
        workspacePortfolioGroups,
      });
      setResearchGroups(next);
      setGroupId((current) => next.some((group) => group.id === current) ? current : next[0]?.id || "system:macro-geopolitics");
    });
    return () => { active = false; };
  }, [customGroups]);
  useEffect(() => {
    let active = true;
    void hydrateCatalystTracker().then((value) => active && setTracker(value));
    return () => { active = false; };
  }, []);

  const allItems = useMemo(() => applyTracker(feed, tracker), [feed, tracker]);
  const visibleItems = useMemo(() => allItems.filter((event) => (
    (type === "all" || event.type === type) &&
    (importance === "all" || event.importance === importance) &&
    (workView === "all" ||
      (workView === "tracked" && tracker.trackedIds.includes(event.id)) ||
      (workView === "focus" && isFocusEvent(event)))
  )), [allItems, importance, tracker.trackedIds, type, workView]);
  const selected = allItems.find((event) => event.id === selectedId);
  const grouped = useMemo(() => Object.entries(
    visibleItems.reduce<Record<string, CatalystEvent[]>>((result, event) => {
      const key = `${eventBucket(event)}:${monthKey(eventDate(event))}`;
      (result[key] ||= []).push(event);
      return result;
    }, {}),
  ).sort(([left], [right]) => {
    const [leftPrecision, leftMonth] = left.split(":");
    const [rightPrecision, rightMonth] = right.split(":");
    const rank = { date: 0, scheduled: 1, window: 2 } as const;
    if (leftPrecision !== rightPrecision) {
      return (rank[leftPrecision as keyof typeof rank] ?? 9) - (rank[rightPrecision as keyof typeof rank] ?? 9);
    }
    return leftMonth.localeCompare(rightMonth);
  }), [visibleItems]);
  const today = new Date().toISOString().slice(0, 10);
  const inDays = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
  const prioritySort = (left: CatalystEvent, right: CatalystEvent) => (
    LEVEL_RANK[right.importance] - LEVEL_RANK[left.importance] ||
    LEVEL_RANK[right.urgency || "low"] - LEVEL_RANK[left.urgency || "low"] ||
    eventDate(left).localeCompare(eventDate(right))
  );
  const thisWeek = visibleItems.filter((event) => eventDate(event) >= today && eventDate(event) <= inDays(7)).sort(prioritySort);
  const nextWeek = visibleItems.filter((event) => eventDate(event) > inDays(7) && eventDate(event) <= inDays(14)).sort(prioritySort);
  const contextRef = useRef<VibeDeskPageContext>(calendarContext({
    feed,
    items: visibleItems,
    selected,
    groupName: activeGroup?.name || "",
    groupSource: activeGroup?.sourceLabel || "",
    concepts,
    includeMacro,
    horizon,
    type,
    importance,
    workView,
    trackedIds: tracker.trackedIds,
    loading,
  }));
  contextRef.current = calendarContext({
    feed,
    items: visibleItems,
    selected,
    groupName: activeGroup?.name || "",
    groupSource: activeGroup?.sourceLabel || "",
    concepts,
    includeMacro,
    horizon,
    type,
    importance,
    workView,
    trackedIds: tracker.trackedIds,
    loading,
  });

  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => { void publishVibeDeskContext(); }, [concepts, feed, groupId, horizon, importance, includeMacro, loading, selectedId, tracker, type, visibleItems.length, workView]);

  const commit = (next: CatalystTrackerState) => {
    setTracker(next);
    void persistCatalystTracker(next);
  };

  const toggleTracked = (event: CatalystEvent) => {
    const tracked = new Set(tracker.trackedIds);
    if (tracked.has(event.id)) tracked.delete(event.id);
    else tracked.add(event.id);
    commit({ ...tracker, trackedIds: [...tracked] });
  };

  const markOutcome = (event: CatalystEvent, status: "confirmed" | "invalidated") => {
    commit({
      ...tracker,
      outcomes: { ...tracker.outcomes, [event.id]: { status, updatedAt: new Date().toISOString() } },
    });
  };

  const addCustom = () => {
    if (!draft.title.trim() || !draft.date) return;
    const createdAt = new Date().toISOString();
    const event: CatalystEvent = {
      id: `custom:${Date.now()}`,
      type: "custom",
      date: draft.date,
      timePrecision: "date",
      dateBasis: "user",
      urgency: draft.date <= inDays(7) ? "high" : (draft.date <= inDays(30) ? "medium" : "low"),
      dateConfidence: "medium",
      status: "upcoming",
      title: draft.title.trim(),
      summary: draft.summary.trim() || "用户自定义研究催化剂",
      source: { id: "user", label: "用户自定义" },
      evidenceIds: [],
      asOf: createdAt,
      freshness: { status: "fresh", ageDays: 0 },
      confidence: { level: "low", rationale: "用户自定义事件，需自行补充证据并核实" },
      impactedAssets: [],
      expectedDirection: "unknown",
      nextAction: "补充事件前准备事项并在临近时复核",
      confirmationConditions: draft.confirmation.trim() ? [draft.confirmation.trim()] : ["补充可核实的确认条件"],
      invalidationConditions: draft.invalidation.trim() ? [draft.invalidation.trim()] : ["补充可核实的失效条件"],
      importance: draft.importance,
    };
    commit({
      ...tracker,
      trackedIds: [...new Set([...tracker.trackedIds, event.id])],
      customEvents: [...tracker.customEvents, event],
    });
    setDraft({ title: "", date: "", summary: "", importance: "medium", confirmation: "", invalidation: "" });
    setShowComposer(false);
  };

  const removeCustom = (event: CatalystEvent) => {
    commit({
      ...tracker,
      customEvents: tracker.customEvents.filter((item) => item.id !== event.id),
      trackedIds: tracker.trackedIds.filter((id) => id !== event.id),
      outcomes: Object.fromEntries(Object.entries(tracker.outcomes).filter(([id]) => id !== event.id)),
    });
  };

  const addResearchGroup = () => {
    const group = createCatalystResearchGroup(groupDraft);
    if (!group) {
      setGroupError("请填写分组名称，并至少配置标的、概念或宏观日程。");
      return;
    }
    const next = [...customGroups, group];
    saveLocalCatalystResearchGroups(next);
    setCustomGroups(next);
    setGroupId(group.id);
    setGroupDraft({ name: "", codes: "", concepts: "", includeMacro: true });
    setGroupError("");
    setShowGroupComposer(false);
  };

  const removeResearchGroup = () => {
    if (!activeGroup?.editable) return;
    const next = customGroups.filter((group) => group.id !== activeGroup.id);
    saveLocalCatalystResearchGroups(next);
    setCustomGroups(next);
  };

  return (
    <div>
      <PageHeader
        title="催化剂日历"
        subtitle="区分官方确定日期与公告、模型观察窗口，持续跟踪日期变化、确认条件和数据覆盖缺口。"
        actions={(
          <>
            <button type="button" className="rounded-lg border border-border bg-card px-3 py-2 text-xs hover:border-primary/50" onClick={() => setShowGroupComposer((value) => !value)}>
              <FolderPlus className="mr-1 inline h-3.5 w-3.5" />新建分组
            </button>
            <button type="button" className="rounded-lg border border-border bg-card px-3 py-2 text-xs hover:border-primary/50" onClick={() => setShowComposer((value) => !value)}>
              <Plus className="mr-1 inline h-3.5 w-3.5" />添加事件
            </button>
            <button type="button" className="rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground" onClick={() => void refresh()} disabled={loading}>
              <RefreshCw className={cn("mr-1 inline h-3.5 w-3.5", loading && "animate-spin")} />刷新
            </button>
          </>
        )}
      />

      <GlassCard className="mb-4 grid gap-3 p-4 md:grid-cols-6">
        <label className="text-xs text-muted-foreground md:col-span-2">研究分组
          <select className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" value={groupId} onChange={(event) => setGroupId(event.target.value)}>
            {researchGroups.map((group) => <option key={group.id} value={group.id}>{group.name} · {group.sourceLabel}</option>)}
          </select>
          <span className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
            <Layers3 className="h-3 w-3" />{groupScopeLabel(activeGroup)}
            {activeGroup?.editable && <button type="button" className="ml-auto text-destructive" onClick={removeResearchGroup}>删除</button>}
          </span>
        </label>
        <label className="text-xs text-muted-foreground">时间范围
          <select className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" value={horizon} onChange={(event) => setHorizon(Number(event.target.value))}>
            {HORIZONS.map((days) => <option key={days} value={days}>未来 {days === 1095 ? "3 年" : `${days} 天`}</option>)}
          </select>
        </label>
        <label className="text-xs text-muted-foreground">事件类型
          <select className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" value={type} onChange={(event) => setType(event.target.value as CatalystType | "all")}>
            <option value="all">全部</option>
            {Object.entries(TYPE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="text-xs text-muted-foreground">影响程度
          <select className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" value={importance} onChange={(event) => setImportance(event.target.value as CatalystEvent["importance"] | "all")}>
            <option value="all">全部</option>
            <option value="high">高</option><option value="medium">中</option><option value="low">低</option>
          </select>
        </label>
        <label className="text-xs text-muted-foreground">工作视图
          <select className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" value={workView} onChange={(event) => setWorkView(event.target.value as WorkView)}>
            <option value="all">全部事件</option>
            <option value="focus">当前重点</option>
            <option value="tracked">仅已跟踪</option>
          </select>
        </label>
      </GlassCard>

      {showGroupComposer && (
        <GlassCard className="mb-4 p-4">
          <div className="mb-3">
            <strong className="text-sm">新建研究分组</strong>
            <p className="mt-1 text-xs text-muted-foreground">标的、概念和宏观日程可以自由组合；自选与组合中心账户会自动出现在分组列表。</p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <input className="rounded-lg border border-border bg-background px-3 py-2 text-sm" placeholder="分组名称，例如：AI 算力链" value={groupDraft.name} onChange={(event) => setGroupDraft({ ...groupDraft, name: event.target.value })} />
            <input className="rounded-lg border border-border bg-background px-3 py-2 text-sm" placeholder="A 股代码，可用逗号或空格分隔" value={groupDraft.codes} onChange={(event) => setGroupDraft({ ...groupDraft, codes: event.target.value })} />
            <input className="rounded-lg border border-border bg-background px-3 py-2 text-sm" placeholder="概念关键词，例如：人工智能、机器人" value={groupDraft.concepts} onChange={(event) => setGroupDraft({ ...groupDraft, concepts: event.target.value })} />
            <label className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground">
              <input type="checkbox" checked={groupDraft.includeMacro} onChange={(event) => setGroupDraft({ ...groupDraft, includeMacro: event.target.checked })} />
              同时纳入宏观与政策日程
            </label>
          </div>
          {groupError && <p className="mt-2 text-xs text-destructive">{groupError}</p>}
          <div className="mt-3 flex justify-end"><button type="button" className="rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground" onClick={addResearchGroup}>保存分组</button></div>
        </GlassCard>
      )}

      {showComposer && (
        <GlassCard className="mb-4 grid gap-3 p-4 md:grid-cols-2">
          <input className="rounded-lg border border-border bg-background px-3 py-2 text-sm" placeholder="事件标题" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
          <input className="rounded-lg border border-border bg-background px-3 py-2 text-sm" type="date" value={draft.date} onChange={(event) => setDraft({ ...draft, date: event.target.value })} />
          <input className="rounded-lg border border-border bg-background px-3 py-2 text-sm" placeholder="研究摘要（可选）" value={draft.summary} onChange={(event) => setDraft({ ...draft, summary: event.target.value })} />
          <select className="rounded-lg border border-border bg-background px-3 py-2 text-sm" value={draft.importance} onChange={(event) => setDraft({ ...draft, importance: event.target.value as CatalystEvent["importance"] })}>
            <option value="high">高影响</option><option value="medium">中影响</option><option value="low">低影响</option>
          </select>
          <input className="rounded-lg border border-border bg-background px-3 py-2 text-sm" placeholder="确认条件" value={draft.confirmation} onChange={(event) => setDraft({ ...draft, confirmation: event.target.value })} />
          <input className="rounded-lg border border-border bg-background px-3 py-2 text-sm" placeholder="失效条件" value={draft.invalidation} onChange={(event) => setDraft({ ...draft, invalidation: event.target.value })} />
          <div className="md:col-span-2 flex justify-end"><button type="button" className="rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground" onClick={addCustom}>保存并跟踪</button></div>
        </GlassCard>
      )}

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        {[
          { label: "范围内事件", value: visibleItems.length, Icon: CalendarDays },
          { label: "确定日期", value: visibleItems.filter((event) => eventBucket(event) === "date").length, Icon: CalendarDays },
          { label: "待复核日程", value: visibleItems.filter((event) => eventBucket(event) === "scheduled").length, Icon: Clock3 },
          { label: "观察窗口", value: visibleItems.filter((event) => event.timePrecision === "window").length, Icon: AlertTriangle },
          { label: "已跟踪", value: tracker.trackedIds.length, Icon: BookmarkCheck },
          { label: "覆盖缺口", value: feed?.gaps.length || 0, Icon: Database },
        ].map(({ label, value, Icon }) => (
          <GlassCard key={label} className="p-4"><Icon className="mb-3 h-4 w-4 text-primary" /><strong className="block text-2xl">{value}</strong><span className="text-xs text-muted-foreground">{label}</span></GlassCard>
        ))}
      </div>

      <div className="mb-5 grid gap-4 lg:grid-cols-2">
        {[{ label: "未来 7 天", items: thisWeek }, { label: "随后 7 天", items: nextWeek }].map((section) => (
          <GlassCard key={section.label} className="p-4">
            <div className="mb-3 flex items-center justify-between"><strong className="text-sm">{section.label}</strong><span className="text-xs text-muted-foreground">{section.items.length} 项</span></div>
            <div className="space-y-2">
              {section.items.slice(0, 5).map((event) => (
                <button key={event.id} type="button" className="flex w-full items-center gap-3 rounded-lg bg-muted/30 px-3 py-2 text-left hover:bg-muted/50" onClick={() => setSelectedId(event.id)}>
                  <Clock3 className="h-3.5 w-3.5 shrink-0 text-primary" /><span className="w-24 text-xs text-muted-foreground">{formatDate(eventDate(event))}</span>
                  <span className="min-w-0"><span className="block truncate text-sm">{event.title}</span>{event.nextAction && <span className="block truncate text-[11px] text-muted-foreground">下一步：{event.nextAction}</span>}</span>
                </button>
              ))}
              {!section.items.length && <p className="text-xs text-muted-foreground">暂无已验证事件。</p>}
            </div>
          </GlassCard>
        ))}
      </div>

      {error && <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}；已保留本地自定义与跟踪记录。</div>}

      <div className="space-y-6">
        {grouped.map(([groupKey, events]) => {
          const [precision, month] = groupKey.split(":");
          const precisionLabel = precision === "date" ? "确定日期" : (precision === "scheduled" ? "待复核日程" : "观察窗口");
          return (
          <section key={groupKey}>
            <div className="mb-2 flex items-center gap-2">
              <span className={cn("rounded-md px-2 py-1 text-xs font-semibold", precision === "date" ? "bg-primary/15 text-primary" : "bg-warning/15 text-warning")}>{precisionLabel}</span>
              <span className="text-xs font-semibold text-foreground">{month}</span>
              <span className="text-xs text-muted-foreground">{events.length} 项</span>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {events.map((event) => {
                const tracked = tracker.trackedIds.includes(event.id);
                return (
                  <GlassCard key={event.id} className={cn("p-4", selectedId === event.id && "border-primary/60")}>
                    <div className="flex items-start justify-between gap-3">
                      <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setSelectedId(event.id)}>
                        <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px]">
                          <span className="rounded bg-primary/15 px-2 py-0.5 text-primary">{TYPE_LABEL[event.type]}</span>
                          <span className="rounded bg-muted px-2 py-0.5 text-muted-foreground">{STATUS_LABEL[event.status]}</span>
                          <span className={cn("rounded px-2 py-0.5", event.importance === "high" ? "bg-warning/15 text-warning" : "bg-muted text-muted-foreground")}>影响 {IMPORTANCE_LABEL[event.importance]}</span>
                          {event.urgency && <span className={cn("rounded px-2 py-0.5", event.urgency === "high" ? "bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground")}>紧迫 {URGENCY_LABEL[event.urgency]}</span>}
                          {event.dateBasis && <span className="rounded bg-muted px-2 py-0.5 text-muted-foreground">{DATE_BASIS_LABEL[event.dateBasis]}</span>}
                          {event.dateChange && event.dateChange.direction !== "unchanged" && <span className="rounded bg-warning/15 px-2 py-0.5 text-warning">{DATE_CHANGE_LABEL[event.dateChange.direction]}{event.dateChange.changeCount ? ` · ${event.dateChange.changeCount} 次变更` : ""}</span>}
                          <span className="text-muted-foreground">{event.timePrecision === "window" ? `${event.windowStart} → ${event.windowEnd}` : formatDate(eventDate(event))}</span>
                        </div>
                        <strong className="block text-sm">{event.title}</strong>
                        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{event.summary}</p>
                        {event.nextAction && <p className="mt-2 rounded-md bg-primary/10 px-2 py-1.5 text-xs text-primary">下一步：{event.nextAction}</p>}
                      </button>
                      <button type="button" className="rounded-md border border-border p-2 text-muted-foreground hover:text-primary" aria-label={tracked ? "取消跟踪" : "跟踪"} onClick={() => toggleTracked(event)}>{tracked ? <BookmarkCheck className="h-4 w-4" /> : <Bookmark className="h-4 w-4" />}</button>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                      <span>证据置信度 {event.confidence.level} {event.confidence.score != null ? `${Math.round(event.confidence.score * 100)}%` : ""}</span>
                      {event.dateConfidence && <><span>·</span><span>日期可信度 {URGENCY_LABEL[event.dateConfidence]}</span></>}
                      <span>·</span><span>{event.source.label}</span><span>·</span><span>截至 {event.asOf.slice(0, 10)}</span>
                      {event.freshness.status === "stale" && <span className="text-warning">数据偏旧</span>}
                    </div>
                    {!!event.impactedAssets.length && <div className="mt-2 text-[11px] text-muted-foreground">影响标的：{event.impactedAssets.map((asset) => `${asset.name || asset.symbol}(${asset.market})`).join("、")}</div>}

                    <details className="mt-3 rounded-lg bg-muted/25 p-3 text-xs">
                      <summary className="cursor-pointer text-foreground">证据、确认条件与失效条件</summary>
                      <div className="mt-2 space-y-2 text-muted-foreground">
                        <p>置信说明：{event.confidence.rationale}</p>
                        <p>确认：{event.confirmationConditions.join("；")}</p>
                        <p>失效：{event.invalidationConditions.join("；")}</p>
                        <p>证据 ID：{event.evidenceIds.join("、") || "待补充"}</p>
                      </div>
                    </details>

                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button type="button" className="rounded-md border border-success/30 px-2 py-1 text-[11px] text-success" onClick={() => markOutcome(event, "confirmed")}><CheckCircle2 className="mr-1 inline h-3 w-3" />确认</button>
                      <button type="button" className="rounded-md border border-destructive/30 px-2 py-1 text-[11px] text-destructive" onClick={() => markOutcome(event, "invalidated")}><XCircle className="mr-1 inline h-3 w-3" />证伪</button>
                      {event.source.url && <a className="ml-auto inline-flex items-center gap-1 text-[11px] text-primary hover:underline" href={event.source.url} target="_blank" rel="noreferrer">来源 <ExternalLink className="h-3 w-3" /></a>}
                      {event.type === "custom" && <button type="button" className="ml-auto text-[11px] text-muted-foreground hover:text-destructive" onClick={() => removeCustom(event)}><Trash2 className="mr-1 inline h-3 w-3" />删除</button>}
                    </div>
                  </GlassCard>
                );
              })}
            </div>
          </section>
          );
        })}
        {!loading && !grouped.length && <GlassCard className="p-8 text-center text-sm text-muted-foreground">当前筛选范围没有催化剂；可以扩大时间范围或添加自定义事件。</GlassCard>}
      </div>

      <GlassCard className="mt-6 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><Database className="h-4 w-4 text-primary" />来源与数据缺口</div>
        <div className="flex flex-wrap gap-2">
          {(feed?.sources || []).map((source) => <span key={source.id} className="rounded-full border border-border px-3 py-1 text-[11px] text-muted-foreground">{source.label} · {source.status} · {source.count}</span>)}
        </div>
        {!!feed?.gaps.length && <ul className="mt-3 list-disc pl-5 text-xs text-muted-foreground">{feed.gaps.map((gap) => <li key={`${gap.capability}:${gap.reason}`}>{gap.capability}：{gap.reason}</li>)}</ul>}
      </GlassCard>
      <Disclaimer />
    </div>
  );
}
