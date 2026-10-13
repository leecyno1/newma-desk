import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Database,
  Droplets,
  ExternalLink,
  GitBranch,
  RefreshCw,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { Disclaimer } from "@/components/ui/Disclaimer";
import { GlassCard } from "@/components/ui/GlassCard";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  api,
  type MacroCalendarEvent,
  type MacroIndicator,
  type MacroLiquidityIndicator,
  type MacroMonitorFeed,
  type MacroRegimeDimension,
} from "@/lib/api";
import { crucixEnergyObservations, crucixSourcesDegraded, loadCrucixSnapshot, type CrucixSnapshot } from "@/lib/crucix";
import { cn } from "@/lib/utils";
import {
  createVibeDeskSnapshotCache,
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  registerVibeDeskUiActionHandler,
  subscribeVibeDeskConfig,
  type VibeDeskPageContext,
} from "@/lib/vibedesk";

const SIGNAL_LABEL = {
  positive: "偏强",
  neutral: "平稳",
  negative: "偏弱",
  mixed: "分化",
  unknown: "待确认",
} as const;

const CATEGORY_LABEL = {
  growth: "增长",
  inflation: "价格",
  liquidity: "流动性",
  labour: "就业",
  trade: "贸易",
  rates: "利率",
} as const;

const IMPORTANCE_LABEL = { high: "高", medium: "中", low: "低", unknown: "未评级" } as const;

const SOURCE_STATUS_LABEL = {
  ok: "正常",
  partial: "部分可用",
  empty: "暂无数据",
  unavailable: "不可用",
  unsupported: "未配置",
} as const;

const GAP_LABELS: Record<string, string> = {
  "official-primary-source-verification": "聚合序列仍需回到官方原始发布复核",
  "primary-global-economic-calendar": "主日历源暂不可用，当前使用公开备用日程",
  "economic-calendar-horizon": "公开降级日历最多覆盖未来 14 天",
  "economic-calendar-date-coverage": "部分日期的经济日历源暂时不可用",
  "economic-calendar": "经济日历数据源暂时不可用",
};

function formatValue(value: number | null | undefined, unit = "") {
  if (value == null || !Number.isFinite(value)) return "—";
  const digits = Math.abs(value) >= 100 ? 1 : 2;
  return `${value.toFixed(digits)}${unit === "%" ? "%" : ""}`;
}

function formatChange(value: number | null | undefined, unit = "") {
  if (value == null || !Number.isFinite(value)) return "较前值 —";
  const suffix = unit === "%" ? " 个百分点" : unit ? ` ${unit}` : "";
  return `较前值 ${value > 0 ? "+" : ""}${value.toFixed(Math.abs(value) >= 10 ? 1 : 2)}${suffix}`;
}

function freshnessLabel(status: "fresh" | "stale" | "unknown") {
  if (status === "fresh") return "更新正常";
  if (status === "stale") return "更新滞后";
  return "更新时间未知";
}

function liquidityTone(item: MacroLiquidityIndicator) {
  if (item.change == null || item.change === 0) return "text-muted-foreground";
  const supportive = (item.effect === "supportive" && item.change > 0)
    || (item.effect === "supportive_inverse" && item.change < 0)
    || (item.effect === "restrictive" && item.change < 0)
    || (item.effect === "restrictive_inverse" && item.change > 0);
  return supportive ? "text-success" : "text-warning";
}

function eventSurprise(event: MacroCalendarEvent) {
  if (event.conflictFields?.length) return null;
  if (event.actual == null || event.forecast == null) return null;
  const difference = event.actual - event.forecast;
  if (Math.abs(difference) < 0.0001) return { label: "符合预期", className: "text-muted-foreground" };
  return {
    label: `较预期 ${difference > 0 ? "+" : ""}${difference.toFixed(Math.abs(difference) >= 10 ? 1 : 2)}`,
    className: difference > 0 ? "text-danger" : "text-success",
  };
}

function eventValueText(event: MacroCalendarEvent, field: "actual" | "forecast" | "previous") {
  return event.conflictFields?.includes(field) ? "待核验" : event[`${field}Text`] ?? formatValue(event[field]);
}

function EventRating({ event }: { event: MacroCalendarEvent }) {
  return <span title={event.importanceBasis?.reason} className={cn("rounded-full px-2 py-1 text-xs whitespace-nowrap",
    event.importance === "high" ? "bg-danger/12 text-danger" : event.importance === "unknown" ? "bg-muted text-muted-foreground" : "bg-warning/12 text-warning")}>
    {event.importanceBasis?.kind === "rule" ? "规则建议" : event.importanceBasis?.kind === "source" ? "来源评级" : "重要性"} {IMPORTANCE_LABEL[event.importance]}
  </span>;
}

function EventDetails({ event }: { event: MacroCalendarEvent }) {
  const records = event.records ?? [];
  const regionConflict = event.regionBasis?.kind === "conflict";
  if (!records.length && event.importanceBasis?.kind !== "rule" && !regionConflict) return null;
  return <details className="mt-2 text-xs text-muted-foreground">
    <summary className="cursor-pointer">{records.length ? `合并 ${event.recordCount ?? records.length} 条原始记录` : regionConflict ? "地区核验依据" : "评级依据"}{!!event.conflictFields?.length && <span className="ml-2 text-warning">记录有分歧，待核验</span>}</summary>
    {regionConflict && <p className="mt-2 text-warning">标题地区：{event.regionBasis?.titleRegion} · 来源地区：{event.regionBasis?.reportedRegion}。{event.regionBasis?.reason}</p>}
    {event.importanceBasis && <p className="mt-2">{event.importanceBasis.kind === "rule" ? "Desk 规则建议，非来源或官方评级：" : "评级依据："}{event.importanceBasis.reason}</p>}
    {!!records.length && <><p className="mt-2">主行选用信息较完整的一条记录，不拼接不同记录的数值。</p><ul className="mt-2 space-y-2">{records.map((record, index) => <li key={`${record.id}:${index}`}>
      <strong className="font-medium text-foreground">{record.title}</strong>
      <p>前值 {record.previousText ?? formatValue(record.previous)} · 预期 {record.forecastText ?? formatValue(record.forecast)} · 公布 {record.actualText ?? formatValue(record.actual)}</p>
      <p>{record.source.label}{record.source.reportedCountry && ` · 原地区字段 ${record.source.reportedCountry}`}{record.importanceBasis?.kind === "source" && ` · 来源评级 ${IMPORTANCE_LABEL[record.importance]}`}</p>
    </li>)}</ul></>}
  </details>;
}

function EventTime({ event }: { event: MacroCalendarEvent }) {
  return <span title={event.timeBasis?.note} className="font-medium">{event.time || "待定"}
    {event.timeBasis?.timeZone && <span className="block text-xs font-normal text-muted-foreground">{event.timeBasis.timeZone}</span>}
  </span>;
}

function EventRegion({ event }: { event: MacroCalendarEvent }) {
  return <span title={event.regionBasis?.reason} className={event.regionBasis?.kind === "conflict" ? "text-warning" : "text-muted-foreground"}>{event.region}</span>;
}

function eventRegion(event: MacroCalendarEvent) {
  if (event.regionGroup) return event.regionGroup;
  // Compatibility with older feeds: exact labels, never a substring that
  // turns 中国香港 into mainland China.
  const regions: Record<string, string> = { 中国: "CN", 中国内地: "CN", 中国香港: "HK", 香港: "HK", 中国澳门: "MO", 澳门: "MO", 中国台湾: "TW", 台湾: "TW", 美国: "US", 地区未注明: "UNKNOWN", 地区待核验: "UNKNOWN" };
  if (regions[event.region]) return regions[event.region];
  if (["欧元区", "德国", "法国", "意大利", "西班牙", "欧洲", "英国", "瑞士", "挪威", "瑞典", "丹麦", "芬兰", "荷兰", "比利时", "奥地利", "爱尔兰", "葡萄牙", "波兰", "俄罗斯", "土耳其"].includes(event.region)) return "EU";
  return "OTHER";
}

function signalTone(signal: MacroRegimeDimension["signal"]) {
  if (signal === "positive") return "border-success/35 bg-success/10 text-success";
  if (signal === "negative") return "border-danger/35 bg-danger/10 text-danger";
  if (signal === "mixed") return "border-warning/35 bg-warning/10 text-warning";
  return "border-border bg-muted/20 text-muted-foreground";
}

function Sparkline({ indicator }: { indicator: MacroIndicator }) {
  const values = indicator.history.map((item) => item.value);
  if (values.length < 2) return <div className="h-12" />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.01);
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * 100;
    const y = 42 - ((value - min) / range) * 34;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  return (
    <svg viewBox="0 0 100 48" preserveAspectRatio="none" className="h-12 w-full" aria-label={`${indicator.name}历史轨迹`}>
      <polyline points={points} fill="none" stroke="hsl(var(--primary))" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function sourceDate(value: string | null | undefined) {
  if (!value) return "时间未知";
  // Statistical months/dates are not instants and must not acquire a day or timezone shift.
  if (/^\d{4}-\d{2}(-\d{2})?$/.test(value)) return value;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(parsed);
}

function CrucixMacroEvidence({
  snapshot,
  loading,
  error,
}: {
  snapshot: CrucixSnapshot | null;
  loading: boolean;
  error: string;
}) {
  if (!snapshot) {
    return (
      <GlassCard className="mb-6 border-dashed p-4">
        <div className="flex items-center gap-2 text-sm font-semibold">
          {loading ? <RefreshCw className="h-4 w-4 animate-spin text-primary" /> : <AlertTriangle className="h-4 w-4 text-warning" />}
          全球供应链与能源旁证
        </div>
        <p className="mt-2 text-sm text-muted-foreground">{loading ? "正在读取 Crucix 首轮扫描…" : error || "当前仅在 Newma-Desk 集成模式下读取 Crucix。"}</p>
      </GlassCard>
    );
  }

  const gscpi = snapshot.macro.gscpi;
  const energy = snapshot.macro.energy;
  const observations = crucixEnergyObservations(energy);
  const gscpiState = gscpi?.value == null ? "待更新"
    : gscpi.value > 1 ? "供应链压力明显高于常态"
      : gscpi.value > 0.5 ? "供应链压力温和偏高"
        : gscpi.value < -1 ? "供应链压力明显低于常态"
          : gscpi.value < -0.5 ? "供应链压力温和偏低"
            : "供应链压力接近常态";
  const gscpiNote = gscpi?.value == null
    ? "纽约联储全球供应链压力指数尚未返回。"
    : gscpi.value > 0.5
      ? "该数据期指数高于历史均值，供应链压力偏高。"
      : gscpi.value < -0.5
        ? "该数据期指数低于历史均值，供应链压力偏低。"
        : "该数据期指数位于历史均值附近，供应链压力总体平稳。";
  const sourceDegraded = Boolean(error || crucixSourcesDegraded(snapshot) || snapshot.freshness.status !== "fresh");
  const sourceStatusLabels = { ok: "采集正常", partial: "部分可用", stale: "数据陈旧", error: "不可用", unknown: "待核验" };

  return (
    <section className="mb-6" aria-label="全球供应链与能源旁证">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">External evidence</p>
          <h2 className="mt-1 text-lg font-bold">全球供应链与能源旁证</h2>
        </div>
        <span className="text-sm text-muted-foreground">Crucix · 采集 {sourceDate(snapshot.asOf)} · 扫描{freshnessLabel(error ? "stale" : snapshot.freshness.status)}</span>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">采集更新不代表观测值最新；按每项数据期、报价时间和来源判断，现货与期货不混用。</p>
      {error && <p role="alert" className="mb-3 text-sm text-warning">全球旁证更新失败，保留上次数据：{error}</p>}
      <GlassCard className="overflow-hidden p-0">
        <div className="grid divide-y divide-border/60 lg:grid-cols-3 lg:divide-x lg:divide-y-0">
          <div className="p-5">
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2 text-sm font-semibold"><Activity className="h-4 w-4 text-primary" />全球供应链压力 GSCPI</span>
              <span className={cn("rounded-full px-2 py-1 text-xs", gscpi?.value != null && Math.abs(gscpi.value) > 0.5 ? "bg-warning/12 text-warning" : "bg-muted/50 text-muted-foreground")}>{gscpiState}</span>
            </div>
            <strong className="mt-5 block text-3xl font-bold tabular-nums">{formatValue(gscpi?.value)}</strong>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{gscpiNote}</p>
            <span className="mt-3 block text-xs text-muted-foreground">数据期 {sourceDate(gscpi?.period ?? gscpi?.date)} · {gscpi?.unit || "标准差"} · {freshnessLabel(error ? "stale" : gscpi?.freshness?.status ?? "unknown")}</span>
            {gscpi?.source && <a href={gscpi.source.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline">{gscpi.source.label}<ExternalLink className="h-3 w-3" /></a>}
          </div>

          <div className="p-5">
            <div className="flex items-center justify-between gap-3"><span className="flex items-center gap-2 text-sm font-semibold"><Droplets className="h-4 w-4 text-primary" />能源价格与库存</span></div>
            <div className="mt-5 grid grid-cols-2 gap-x-5 gap-y-4">
              {observations.map((item) => (
                <div key={item.id} aria-label={item.label}>
                  <span className="block text-sm" title={item.note}>{item.label}</span>
                  <div className="mt-1 flex flex-wrap items-baseline gap-x-2"><strong className="text-xl tabular-nums">{formatValue(item.value)}</strong><small className="text-xs text-muted-foreground">{item.unit || "单位待核验"}</small></div>
                  {item.value != null && <p className="mt-1 break-words text-xs text-muted-foreground">{item.observedAt ? `报价 ${item.observedAt}` : item.period ? `数据期 ${item.period}` : "数据时间未知"}</p>}
                  <p className={cn("mt-1 text-xs", item.freshness.status !== "fresh" ? "text-warning" : "text-muted-foreground")}>
                    {item.value == null ? "暂无数据" : freshnessLabel(error ? "stale" : item.freshness.status)}
                  </p>
                  {item.source?.url ? <a href={item.source.url} title={item.source.label} target="_blank" rel="noreferrer" className="mt-1 inline-flex text-xs text-primary hover:underline">{item.source.id === "EIA" ? "EIA" : item.source.label} · {item.source.seriesId}</a> : <span className="mt-1 block text-xs text-warning">来源待核验</span>}
                </div>
              ))}
            </div>
            <details className="mt-3 border-t border-border/60 pt-2 text-xs text-muted-foreground">
              <summary className="cursor-pointer">报价口径与缺口</summary>
              <ul className="mt-2 space-y-2">{observations.map((item) => <li key={item.id}>
                <p>{item.label}：{item.note}</p>
                {item.source?.originalSource && <p className="mt-1">原始统计：{item.source.originalUrl
                  ? <a href={item.source.originalUrl} target="_blank" rel="noreferrer" className="text-primary hover:underline">{item.source.originalSource}</a>
                  : item.source.originalSource} · {item.source.originalSeriesId}；当前序列：{item.source.seriesId}。</p>}
                {item.source?.fallbackReason && <p className="mt-1">{item.source.fallbackReason}</p>}
              </li>)}</ul>
            </details>
          </div>

          <div className="p-5" aria-label="Crucix 来源健康">
            <div className="flex items-center justify-between gap-3"><span className="flex items-center gap-2 text-sm font-semibold"><Database className="h-4 w-4 text-primary" />来源健康</span><span className={cn("rounded-full px-2 py-1 text-xs", sourceDegraded ? "bg-warning/12 text-warning" : "bg-success/12 text-success")}>{error ? "上次快照" : sourceDegraded ? "部分降级" : "采集正常"}</span></div>
            <div className="mt-5 flex items-end gap-3"><strong className="text-3xl tabular-nums">{snapshot.sourceHealth.ok}/{snapshot.sourceHealth.queried}</strong><span className="pb-1 text-sm text-muted-foreground">来源采集正常</span></div>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{snapshot.sourceHealth.failed} 不可用 · {snapshot.sourceHealth.partial ?? 0} 部分可用 · {snapshot.sourceHealth.stale ?? 0} 陈旧 · {snapshot.sourceHealth.unknown ?? 0} 待核验</p>
            <details className="mt-3 border-t border-border/60 pt-2 text-xs text-muted-foreground">
              <summary className="cursor-pointer">全部来源明细（{snapshot.sourceHealth.items.length}）</summary>
              <ul className="mt-2 max-h-64 space-y-2 overflow-y-auto">{snapshot.sourceHealth.items.map(item => <li key={item.source}>
                <span className={item.status === "ok" ? "" : "text-warning"}>{item.source} · {sourceStatusLabels[item.status]}</span>
                {item.reason && <p className="mt-1">{item.reason}</p>}
              </li>)}</ul>
              {snapshot.sourceHealth.queried > snapshot.sourceHealth.items.length && <p className="mt-2">旧快照缺少部分来源明细，计入待核验。</p>}
            </details>
            <p className="mt-3 text-xs text-muted-foreground">采集正常不代表数据实时或全量覆盖；各项观测按自己的数据期判断。</p>
          </div>
        </div>
      </GlassCard>
    </section>
  );
}

function macroContext(input: {
  feed: MacroMonitorFeed | null;
  crucix: CrucixSnapshot | null;
  events: MacroCalendarEvent[];
  eventLimit: number;
  days: number;
  region: string;
  importance: string;
  loading: boolean;
  error: string;
  crucixError: string;
}): VibeDeskPageContext {
  const indicators = [...(input.feed?.indicators ?? []), ...(input.feed?.liquidity?.indicators ?? [])];
  const freshnessStates = indicators.map((item) => item.freshness.status);
  const energyObservations = input.crucix ? crucixEnergyObservations(input.crucix.macro.energy) : [];
  if (input.crucix) {
    freshnessStates.push(input.crucix.freshness.status);
    if (input.crucix.macro.gscpi?.value != null) freshnessStates.push(input.crucix.macro.gscpi.freshness?.status ?? "unknown");
    freshnessStates.push(...energyObservations.filter((item) => item.value != null).map((item) => item.freshness.status));
  }
  const hasEvidence = Boolean(indicators.length || input.events.length || input.crucix?.asOf);
  const degraded = Boolean(input.error || input.crucixError
    || input.feed?.sources.some((source) => source.status === "partial" || source.status === "unavailable")
    || input.feed?.calendarCoverage?.status === "partial" || input.feed?.calendarCoverage?.status === "unavailable"
    || (input.crucix && crucixSourcesDegraded(input.crucix)));
  const freshness = input.loading || !hasEvidence ? "unknown"
    : input.error || input.crucixError || freshnessStates.includes("stale") ? "stale"
      : degraded || !freshnessStates.length || freshnessStates.includes("unknown") ? "unknown" : "fresh";
  return {
    view: { id: "macro-monitor", title: "宏观观察" },
    visibleBlocks: [
      ...(input.feed?.decisionReview ? [{ id: "macro-decision-review", type: "decision-evidence", title: "投资决策证据" }] : []),
      ...(input.feed?.regime ? [{ id: "macro-regime", type: "macro-regime", title: "增长、价格与流动性" }] : []),
      ...(input.feed?.liquidity ? [{ id: "macro-liquidity", type: "indicator-board", title: "流动性证据" }] : []),
      { id: "macro-indicators", type: "indicator-board", title: "核心宏观指标" },
      { id: "crucix-macro-evidence", type: "external-intelligence", title: "全球供应链与能源旁证" },
      { id: "economic-calendar", type: "economic-calendar", title: "经济事件日历" },
      { id: "macro-evidence", type: "evidence-sources", title: "来源与数据缺口" },
    ],
    selection: {},
    filters: {
      horizonDays: input.days,
      region: input.region,
      importance: input.importance,
    },
    data: {
      asOf: input.feed?.generatedAt || input.crucix?.asOf || undefined,
      source: input.feed?.schemaVersion || "newma-desk.macro-monitor.v1",
      freshness,
      summary: {
        loading: input.loading,
        error: input.error || null,
        crucixError: input.crucixError || null,
        degraded,
        horizon: input.feed?.horizon ?? null,
        calendarCoverage: input.feed?.calendarCoverage ?? null,
        filterScope: "地区、重要性和日历范围只筛选经济事件，不筛选宏观指标与全球旁证。",
        regime: input.feed?.regime || null,
        decisionReview: input.feed?.decisionReview || null,
        indicators: input.feed?.indicators || [],
        liquidity: input.feed?.liquidity || null,
        crucix: input.crucix ? {
          asOf: input.crucix.asOf,
          freshness: input.crucix.freshness,
          gscpi: input.crucix.macro.gscpi,
          energy: { observations: energyObservations,
            note: "采集时间不是数据时间；现货、期货、库存按各自来源与单位读取，不能直接混用或把旧快照标成实时。" },
          sourceHealth: input.crucix.sourceHealth,
        } : null,
        upcomingEvents: input.events.slice(0, input.eventLimit),
        visibleEventCount: Math.min(input.events.length, input.eventLimit),
        totalMatchingEvents: input.events.length,
        highImportanceEventCount: input.events.filter((event) => event.importance === "high").length,
        unratedEventCount: input.events.filter((event) => event.importance === "unknown").length,
        ruleRatedEventCount: input.events.filter((event) => event.importanceBasis?.kind === "rule").length,
        rawRecordCount: input.events.reduce((sum, event) => sum + (event.recordCount ?? 1), 0),
        conflictingEventCount: input.events.filter((event) => event.conflictFields?.length).length,
        unresolvedRegionEventCount: input.events.filter((event) => eventRegion(event) === "UNKNOWN").length,
        unconfirmedTimeZoneEventCount: input.events.filter((event) => event.time && event.timeBasis?.kind !== "explicit-offset").length,
        calendarInterpretation: "upcomingEvents 仅含页面当前展开的事件，全部筛选结果以 totalMatchingEvents 计。事件已保守去重；records 保留合并前记录，conflictFields 标记待核验字段。规则建议不是来源或官方评级。地区冲突不得强行归类；时区不明确时不能转成北京时间或推断已到期。",
        eventsTruncated: input.events.length > input.eventLimit,
        sources: input.feed?.sources || [],
        gaps: input.feed?.gaps || [],
      },
    },
    actions: [{ id: "macro.refresh", label: "刷新宏观数据", available: !input.loading }],
    tasks: input.loading ? [{ id: "macro-data-load", status: "running" }] : [],
  };
}

export function MacroMonitor() {
  const [days, setDays] = useState(7);
  const [region, setRegion] = useState("all");
  const [importance, setImportance] = useState("all");
  const [eventLimit, setEventLimit] = useState(12);
  const [cacheRevision, setCacheRevision] = useState(0);
  // v6 replaces the unsafe mixed-frequency forecast with observed assessment.
  const cache = useMemo(() => createVibeDeskSnapshotCache<MacroMonitorFeed>(`macro-monitor:${days}`, 6), [days]);
  const cacheKey = `macro-monitor:${days}:${cacheRevision}`;
  const [snapshot, setSnapshot] = useState<{ key: string; value: MacroMonitorFeed } | null>(null);
  const feed = snapshot?.key === cacheKey ? snapshot.value : null;
  const feedRef = useRef(feed);
  const requestRevision = useRef(0);
  const crucixRevision = useRef(0);
  const resourceKeyRef = useRef<string | undefined>(undefined);
  const configScopeRef = useRef("");
  feedRef.current = feed;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [crucix, setCrucix] = useState<CrucixSnapshot | null>(null);
  const [crucixLoading, setCrucixLoading] = useState(true);
  const [crucixError, setCrucixError] = useState("");

  const loadCrucix = useCallback(async () => {
    const revision = ++crucixRevision.current;
    setCrucixLoading(true);
    setCrucixError("");
    try {
      const next = await loadCrucixSnapshot();
      if (revision === crucixRevision.current) setCrucix(next);
    } catch (reason) {
      if (revision === crucixRevision.current) setCrucixError(reason instanceof Error ? reason.message : "Crucix 数据暂未就绪");
    } finally {
      if (revision === crucixRevision.current) setCrucixLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    const revision = ++requestRevision.current;
    setLoading(true);
    setError("");
    const cached = cache.read()?.value;
    const resourceChanged = resourceKeyRef.current !== cacheKey;
    resourceKeyRef.current = cacheKey;
    if (resourceChanged) setSnapshot(cached ? { key: cacheKey, value: cached } : null);
    try {
      const next = await api.macroMonitor(days);
      if (revision !== requestRevision.current) return;
      setSnapshot({ key: cacheKey, value: next });
      cache.write(next, next.generatedAt);
    } catch (reason) {
      if (revision !== requestRevision.current) return;
      setError(cached || (!resourceChanged && feedRef.current)
        ? "更新失败，当前为上次数据"
        : reason instanceof Error ? reason.message : "宏观数据暂时不可用");
    } finally {
      if (revision === requestRevision.current) setLoading(false);
    }
  }, [cache, cacheKey, days]);

  useEffect(() => {
    void refresh();
    return () => { requestRevision.current += 1; };
  }, [refresh]);
  useEffect(() => {
    void loadCrucix();
    return () => { crucixRevision.current += 1; };
  }, [loadCrucix]);
  useEffect(() => subscribeVibeDeskConfig((config) => {
    const scope = JSON.stringify([config.gatewayOrigin, config.userId, config.workspaceId, config.moduleId]);
    if (configScopeRef.current === scope) return;
    configScopeRef.current = scope;
    setCacheRevision((value) => value + 1);
    void loadCrucix();
  }), [loadCrucix]);

  const events = useMemo(() => (feed?.events || []).filter((event) => (
    (region === "all" || eventRegion(event) === region) &&
    (importance === "all" || event.importance === importance)
  )), [feed, importance, region]);
  const groupedEvents = useMemo(() => Object.entries(events.slice(0, eventLimit).reduce<Record<string, MacroCalendarEvent[]>>((result, event) => {
    (result[event.date] ||= []).push(event);
    return result;
  }, {})), [eventLimit, events]);

  const context = macroContext({ feed, crucix, events, eventLimit, days, region, importance, loading: loading || crucixLoading, error, crucixError });
  const contextRef = useRef<VibeDeskPageContext>(context);
  contextRef.current = context;
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => { void publishVibeDeskContext(); }, [crucix, crucixError, crucixLoading, days, error, eventLimit, events, feed, importance, loading, region]);
  useEffect(() => registerVibeDeskUiActionHandler(async (actionId) => {
    if (actionId !== "macro.refresh") throw new Error(`宏观观察不支持动作 ${actionId}`);
    if (!contextRef.current.actions[0]?.available) throw new Error("宏观数据正在更新，请等待完成");
    // Public macro sources can take longer than the Bridge response window.
    // Acknowledge the start; the context task reports the actual completion.
    void refresh();
    void loadCrucix();
    return { status: "running", horizonDays: days };
  }), [days, loadCrucix, refresh]);

  const regime = feed?.regime;
  const dimensions = [regime?.growth, regime?.inflation, regime?.liquidity]
    .filter((dimension): dimension is MacroRegimeDimension => Boolean(dimension?.label));
  const staleCount = feed?.indicators.filter((item) => item?.freshness?.status === "stale").length || 0;
  const indicatorByEvidence = useMemo(() => new Map((feed?.indicators || []).map((item) => [item.evidenceId, item])), [feed]);
  const highEventCount = events.filter((event) => event.importance === "high").length;
  const unratedCount = events.filter((event) => event.importance === "unknown").length;
  const ruleRatedCount = events.filter((event) => event.importanceBasis?.kind === "rule").length;
  const rawRecordCount = events.reduce((sum, event) => sum + (event.recordCount ?? 1), 0);
  const unresolvedRegions = events.filter((event) => eventRegion(event) === "UNKNOWN").length;
  const unconfirmedTimeZones = events.filter((event) => event.time && event.timeBasis?.kind !== "explicit-offset").length;
  const liquidity = feed?.liquidity;
  const calendarCoverage = feed?.calendarCoverage;
  const liquiditySignal = !liquidity?.assessment.complete ? "证据不足"
    : liquidity.assessment.signal === "supportive"
    ? "边际支持"
    : liquidity?.assessment.signal === "restrictive" ? "边际收紧" : "信号分化";

  return (
    <div>
      <PageHeader
        title="宏观观察"
        subtitle="把增长、价格、流动性与未来经济事件放入同一个可核验的研究视图。"
        actions={(
          <button type="button" className="rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground" onClick={() => { void refresh(); void loadCrucix(); }} disabled={loading || crucixLoading}>
            <RefreshCw className={cn("mr-1 inline h-3.5 w-3.5", (loading || crucixLoading) && "animate-spin")} />刷新
          </button>
        )}
      />

      <GlassCard className="mb-4 grid gap-3 p-4 sm:grid-cols-3">
        <label className="text-xs text-muted-foreground">日历范围
          <select aria-label="日历范围" className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" value={days} onChange={(event) => { setDays(Number(event.target.value)); setEventLimit(12); }}>
            <option value={7}>未来 7 天</option><option value={14}>未来 14 天</option><option value={30}>未来 30 天</option>
          </select>
        </label>
        <label className="text-xs text-muted-foreground">地区
          <select aria-label="地区" className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" value={region} onChange={(event) => { setRegion(event.target.value); setEventLimit(12); }}>
            <option value="all">全部</option><option value="CN">中国内地</option><option value="HK">中国香港</option><option value="MO">中国澳门</option><option value="TW">中国台湾</option><option value="US">美国</option><option value="EU">欧洲（含英国等）</option><option value="OTHER">其他及国际组织</option><option value="UNKNOWN">地区待核验</option>
          </select>
        </label>
        <label className="text-xs text-muted-foreground">重要性
          <select aria-label="重要性" className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" value={importance} onChange={(event) => { setImportance(event.target.value); setEventLimit(12); }}>
            <option value="all">全部</option><option value="high">高</option><option value="medium">中</option><option value="low">低</option><option value="unknown">未评级</option>
          </select>
        </label>
      </GlassCard>
      <p className="mb-4 text-sm text-muted-foreground">筛选仅作用于经济事件；宏观指标与全球旁证保持完整展示。</p>

      {error && <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">{error}</div>}
      <div role="status" className="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
        <span>{loading || crucixLoading ? "正在更新宏观数据…" : freshnessLabel(context.data.freshness as "fresh" | "stale" | "unknown")}</span>
        <span>页面生成 {sourceDate(feed?.generatedAt)}（非来源发布日期）</span>
        {context.data.summary?.degraded ? <span className="text-warning">来源或覆盖存在缺口，请查看下方说明</span> : null}
      </div>

      {regime && (
        <GlassCard className="mb-4 border-primary/30 bg-primary/5 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Macro regime</p>
              <h2 className="mt-1 text-xl font-bold">{regime.overall?.label || "宏观状态待确认"}</h2>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">{regime.overall?.summary || "宏观状态数据尚未完整返回。"}</p>
            </div>
            <span title={regime.confidence.rationale} className="rounded-full border border-border bg-background px-3 py-1 text-xs text-muted-foreground">有效期内指标 {Math.round(regime.confidence.score * 100)}% · 非判断概率</span>
          </div>
          {feed?.decisionReview && <div aria-label="投资决策证据" className="mt-4 border-t border-border/60 pt-4">
            <div className="flex flex-wrap items-center gap-3"><strong className="text-sm">采纳意见：{feed.decisionReview.adoption}</strong><span className="text-xs text-muted-foreground">{feed.decisionReview.scope}</span></div>
            <div className="mt-3 grid gap-4 text-sm md:grid-cols-3">
              <div><strong>支撑证据</strong><ul className="mt-2 space-y-1 text-muted-foreground">{feed.decisionReview.supportingEvidence.map((item) => <li key={item.dimension}>{item.dimension} · {SIGNAL_LABEL[item.signal]} · {item.evidenceIds.length} 条可追溯指标</li>)}</ul></div>
              <div><strong>反证与待补</strong><ul className="mt-2 space-y-1 text-muted-foreground">{[...feed.decisionReview.counterEvidence, ...feed.decisionReview.checks].map((item) => <li key={item}>{item}</li>)}</ul>{!feed.decisionReview.counterEvidence.length && !feed.decisionReview.checks.length && <p className="mt-2 text-muted-foreground">暂无已识别反证；仍需持续复核。</p>}</div>
              <div><strong>下次复议事件</strong><ul className="mt-2 space-y-1 text-muted-foreground">{feed.decisionReview.nextReviewEvents.map((event) => <li key={event.id}>{event.date} · {event.title}{event.ratingBasis === "rule" ? "（Desk 规则评级）" : event.importance !== "high" ? "（未获高重要性评级）" : ""}</li>)}</ul>{!feed.decisionReview.nextReviewEvents.length && <p className="mt-2 text-muted-foreground">当前日历没有可用事件，按下一次指标发布复核。</p>}</div>
            </div>
            <details className="mt-3 text-xs text-muted-foreground"><summary className="cursor-pointer">查看潜在传导路径（研究假设）</summary><div className="mt-2 grid gap-2 md:grid-cols-3">{(regime.transmission || []).map((item) => <div key={item.id} className="rounded border border-border/60 p-2"><span className="flex items-center gap-1 font-medium text-foreground"><GitBranch className="h-3 w-3" />{item.title}</span><p className="mt-1">{item.summary}</p><p className="mt-1">关注：{item.assets.join("、")}</p></div>)}</div></details>
          </div>}
        </GlassCard>
      )}

      <div className="mb-4 grid gap-3 md:grid-cols-3">
        {dimensions.map((dimension) => (
          <GlassCard key={dimension.label} className="p-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">{dimension.label}</span>
              <span className={cn("rounded-full border px-2 py-1 text-xs", signalTone(dimension.signal))}>{SIGNAL_LABEL[dimension.signal]}</span>
            </div>
            <p className="mt-4 text-sm font-medium leading-relaxed">{dimension.summary}</p>
            <div className="mt-4 space-y-2 border-t border-border/60 pt-3">
              {dimension.evidenceIds.length ? dimension.evidenceIds.map((evidenceId) => {
                const indicator = indicatorByEvidence.get(evidenceId);
                return indicator ? <div key={evidenceId} className="flex items-center justify-between gap-3 text-xs text-muted-foreground"><span>{indicator.name}</span><strong className="font-medium text-foreground">{formatValue(indicator.value, indicator.unit)}</strong></div> : null;
              }) : <p className="text-xs text-warning">当前维度缺少可核验指标</p>}
            </div>
          </GlassCard>
        ))}
      </div>

      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "核心指标", value: feed?.indicators.length || 0, Icon: Activity },
          { label: "高重要性事件", value: !highEventCount && unratedCount ? "待评级" : highEventCount, Icon: CalendarClock,
            note: [ruleRatedCount ? "含规则建议" : "", unratedCount ? `${unratedCount} 项未评级，尚不能完整统计` : ""].filter(Boolean).join(" · ") || undefined },
          { label: "陈旧指标", value: staleCount, Icon: AlertTriangle },
          { label: "流动性覆盖", value: liquidity ? `${liquidity.coverage.available}/${liquidity.coverage.total}` : "—", Icon: Droplets },
        ].map(({ label, value, Icon, note }) => (
          <GlassCard key={label} className="p-4"><Icon className="mb-3 h-4 w-4 text-primary" /><strong className="block text-2xl">{value}</strong><span className="text-xs text-muted-foreground">{label}</span>{note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}</GlassCard>
        ))}
      </div>

      <CrucixMacroEvidence snapshot={crucix} loading={crucixLoading} error={crucixError} />

      {liquidity && <section className="mb-6">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Liquidity monitor</p><h2 className="mt-1 text-lg font-bold">流动性证据</h2></div>
          <div className="text-right"><strong className={cn("block text-sm", liquidity.assessment.signal === "supportive" ? "text-success" : liquidity.assessment.signal === "restrictive" ? "text-warning" : "text-foreground")}>{liquiditySignal}</strong><span className="text-xs text-muted-foreground">{liquidity.assessment.observedCount} 项有效观测参与方向评估 · 非预测</span></div>
        </div>
        <div className="grid gap-3 lg:grid-cols-3">{liquidity.groups.map((group) => <GlassCard key={group.id} className="p-4">
          <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">{group.label}</h3><span className="text-xs text-muted-foreground">{group.indicators.length} 项</span></div>
          <div className="mt-3 divide-y divide-border/60">{group.indicators.map((item) => <div key={item.id} className="py-3 first:pt-0 last:pb-0">
            <div className="flex items-start justify-between gap-3"><div><strong className="text-sm font-medium">{item.name}</strong><div className="mt-1 text-xs text-muted-foreground">{item.period} · {freshnessLabel(item.freshness.status)}</div></div><div className="text-right"><strong className="block text-base">{formatValue(item.value, item.unit)}</strong><span className={cn("text-xs", liquidityTone(item))}>{formatChange(item.change, item.unit)}</span></div></div>
          </div>)}</div>
          {!group.indicators.length && <div className="mt-3 rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">当前分组暂无可用序列</div>}
        </GlassCard>)}</div>
        <GlassCard className="mt-3 flex flex-wrap items-center justify-between gap-3 p-4 text-sm"><div><strong>{liquidity.source}</strong><p className="mt-1 text-xs text-muted-foreground">{liquidity.assessment.method}</p></div><span className="text-xs text-muted-foreground">数据截至 {liquidity.coverage.asOf || "—"}</span></GlassCard>
      </section>}

      <section className="mb-6">
        <div className="mb-3 flex items-end justify-between gap-3">
          <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Macro indicators</p><h2 className="mt-1 text-lg font-bold">核心宏观指标</h2></div>
          <span className="text-xs text-muted-foreground">数据有效期覆盖 {regime ? Math.round(regime.confidence.score * 100) : 0}%</span>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(feed?.indicators || []).map((indicator) => (
            <GlassCard key={indicator.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div><span className="text-xs text-primary">{indicator.region} · {CATEGORY_LABEL[indicator.category]}</span><h3 className="mt-1 text-sm font-semibold">{indicator.name}</h3></div>
                {indicator.direction === "higher" ? <TrendingUp className="h-4 w-4 text-danger" /> : indicator.direction === "lower" ? <TrendingDown className="h-4 w-4 text-success" /> : <Activity className="h-4 w-4 text-muted-foreground" />}
              </div>
              <div className="mt-4 flex items-end gap-3"><strong className="text-3xl">{formatValue(indicator.value, indicator.unit)}</strong><span className="pb-1 text-xs text-muted-foreground">前值 {formatValue(indicator.previous, indicator.unit)}</span></div>
              <Sparkline indicator={indicator} />
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span>{indicator.dateBasis === "period" || indicator.dateBasis === "source-update" ? "数据期" : indicator.dateBasis === "release" ? "发布" : "来源日期"} {indicator.dateBasis === "source-update" ? indicator.period : indicator.releaseDate || indicator.period}</span>
                {indicator.dateBasis === "source-update" && indicator.releaseDate && <span>源更新 {indicator.releaseDate}</span>}
                {indicator.dateBasis === "period" && !indicator.releaseDate && <span>发布日期未核实</span>}
                {indicator.revisionStatus === "not-tracked" && <span>历史修订未跟踪</span>}
                {indicator.nextReleaseDate && <span>下次 {indicator.nextReleaseDate}</span>}
                <span className={indicator.freshness.status === "stale" ? "text-warning" : ""}>{freshnessLabel(indicator.freshness.status)}</span>
              </div>
              <a href={indicator.source.url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs text-primary hover:underline">{indicator.source.label}<ExternalLink className="h-3 w-3" /></a>
              {indicator.source.originalSource && <details className="mt-2 text-xs text-muted-foreground">
                <summary className="cursor-pointer">来源说明</summary>
                <p className="mt-2">原始统计：{indicator.source.originalSource} · {indicator.source.originalSeriesId}；当前序列：{indicator.source.seriesId}。</p>
                {indicator.source.calculation && <p className="mt-1">计算：{indicator.source.calculation}。</p>}
                <p className="mt-1">{indicator.source.fallbackReason}</p>
              </details>}
            </GlassCard>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-3"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Economic calendar</p><h2 className="mt-1 text-lg font-bold">未来经济事件</h2></div>
        {calendarCoverage && <div aria-label="经济日历覆盖" className="mb-3 space-y-1 text-sm text-muted-foreground">
          <p>{calendarCoverage.start} 至 {calendarCoverage.end} · 已查询 {calendarCoverage.queriedDays}/{calendarCoverage.requestedDays} 日（含今天） · {calendarCoverage.eventDays} 日有已收录事件</p>
          <p>{calendarCoverage.note}</p>
          {!!calendarCoverage.missingDates.length && <details className="text-warning"><summary>未覆盖 {calendarCoverage.missingDates.length} 日，不能判定为空日程</summary><p className="mt-1 break-words">{calendarCoverage.missingDates.join("、")}</p></details>}
        </div>}
        {events.some((event) => event.importance === "unknown") && <p className="mb-3 text-sm text-muted-foreground">部分事件来源未提供重要性评级；“未评级”不等于低重要性。</p>}
        {!!ruleRatedCount && <p className="mb-3 text-sm text-muted-foreground">{ruleRatedCount} 项采用 Desk 规则建议，非来源或官方评级；可展开查看依据。</p>}
        {!!events.length && <p className="mb-3 text-sm text-muted-foreground">当前筛选 {events.length} 项事件 · 已展示 {Math.min(eventLimit, events.length)} 项 · {rawRecordCount} 条来源记录{rawRecordCount > events.length ? ` · 合并 ${rawRecordCount - events.length} 条重复记录` : ""}</p>}
        {!!(unresolvedRegions || unconfirmedTimeZones) && <div aria-label="日历口径提示" className="mb-3 space-y-1 text-sm text-muted-foreground">
          {!!unconfirmedTimeZones && <p>{unconfirmedTimeZones} 项时区未注明，显示来源原时刻，不能直接视为北京时间。</p>}
          {!!unresolvedRegions && <p className="text-warning">{unresolvedRegions} 项地区缺失或冲突，已单列到“地区待核验”。</p>}
        </div>}
        <div className="space-y-4">
          {groupedEvents.map(([eventDate, rows]) => (
            <GlassCard key={eventDate} className="overflow-hidden p-0">
              <div className="border-b border-border/70 px-4 py-3"><strong className="text-sm">{eventDate}</strong><span className="ml-2 text-xs text-muted-foreground">{rows.length} 项</span></div>
              <div className="divide-y divide-border/60">
                {rows.map((event) => (
                  <div key={event.id} className="grid gap-2 px-4 py-3 text-sm md:grid-cols-[80px_96px_1fr_210px] md:items-center">
                    <EventTime event={event} />
                    <EventRegion event={event} />
                    <div><strong className="font-medium">{event.title}</strong><div className="mt-1 text-xs text-muted-foreground">前值 {eventValueText(event, "previous")} · 预期 {eventValueText(event, "forecast")} · 公布 {eventValueText(event, "actual")}</div><EventDetails event={event} /></div>
                    <div className="flex items-center justify-between gap-2"><EventRating event={event} />{eventSurprise(event) && <span className={cn("text-xs font-semibold", eventSurprise(event)?.className)}>{eventSurprise(event)?.label}</span>}<a href={event.source.url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">来源</a></div>
                  </div>
                ))}
              </div>
            </GlassCard>
          ))}
          {!loading && !groupedEvents.length && <GlassCard className="p-8 text-center text-sm text-muted-foreground">{!feed ? "经济事件数据暂不可用，请刷新重试。" : calendarCoverage?.missingDates.length ? "已查询范围暂无匹配事件；未覆盖日期不能判定为空。" : "当前筛选范围暂无已收录事件，不代表没有经济事件。"}</GlassCard>}
          {events.length > eventLimit && <button type="button" className="w-full rounded-lg border border-border px-4 py-2 text-sm text-primary hover:bg-muted/30" onClick={() => setEventLimit((value) => value + 20)}>再显示 20 项（剩余 {events.length - eventLimit}）</button>}
        </div>
      </section>

      {regime && (
        <section className="mt-6">
          <div className="mb-3"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Scenario watch</p><h2 className="mt-1 text-lg font-bold">情景观察</h2></div>
          <div className="grid gap-3 md:grid-cols-3">
            {regime.scenarios.map((scenario) => (
              <GlassCard key={scenario.id} className="p-4">
                <div className="flex items-center justify-between gap-2"><h3 className="text-sm font-semibold">{scenario.label}</h3><span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">{scenario.probability}</span></div>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{scenario.summary}</p>
                <div className="mt-3 space-y-2 text-xs text-muted-foreground">{scenario.triggers.map((trigger) => <div key={trigger} className="flex gap-2"><ArrowRight className="mt-0.5 h-3.5 w-3.5 flex-none text-primary" /><span>{trigger}</span></div>)}</div>
              </GlassCard>
            ))}
          </div>
        </section>
      )}

      <GlassCard className="mt-6 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><Database className="h-4 w-4 text-primary" />来源与数据缺口</div>
        <div className="grid gap-2 md:grid-cols-2">{(feed?.sources || []).map((source) => (
          <div key={source.id} className="rounded-lg border border-border px-3 py-2 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2"><CheckCircle2 className={cn("h-4 w-4", source.status === "ok" ? "text-success" : "text-warning")} />{source.label}</span>
              <span className="text-xs text-muted-foreground">{SOURCE_STATUS_LABEL[source.status]} · {source.count} 条</span>
            </div>
            {typeof source.coverage?.fresh === "number" && <p className="mt-2 text-sm text-muted-foreground">
              有效期内 {source.coverage.fresh} 项 · 陈旧 {Number(source.coverage.stale ?? 0)} 项 · 时间未知 {Number(source.coverage.unknown ?? 0)} 项
            </p>}
            {source.error && <p className="mt-2 break-words text-sm text-warning">{source.error}</p>}
          </div>
        ))}</div>
        {!!feed?.gaps.length && <div className="mt-4 rounded-lg border border-warning/30 bg-warning/5 p-3"><strong className="text-sm">仍需补齐</strong><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{feed.gaps.map((gap) => <li key={`${gap.capability}:${gap.reason}`}>{GAP_LABELS[gap.capability] || `${gap.capability}：${gap.reason.split("_").join(" ")}`}</li>)}</ul></div>}
      </GlassCard>
      <Disclaimer />
    </div>
  );
}
