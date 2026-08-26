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
import { loadCrucixSnapshot, type CrucixSnapshot } from "@/lib/crucix";
import { cn } from "@/lib/utils";
import {
  createVibeDeskSnapshotCache,
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
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

const IMPORTANCE_LABEL = { high: "高", medium: "中", low: "低" } as const;

const SOURCE_STATUS_LABEL = {
  ok: "正常",
  partial: "部分可用",
  empty: "暂无数据",
  unavailable: "不可用",
  unsupported: "未配置",
} as const;

const GAP_LABELS: Record<string, string> = {
  "official-primary-source-verification": "聚合序列仍需回到官方原始发布复核",
  "primary-global-economic-calendar": "全球经济日历主数据源未配置",
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
  if (event.actual == null || event.forecast == null) return null;
  const difference = event.actual - event.forecast;
  if (Math.abs(difference) < 0.0001) return { label: "符合预期", className: "text-muted-foreground" };
  return {
    label: `较预期 ${difference > 0 ? "+" : ""}${difference.toFixed(Math.abs(difference) >= 10 ? 1 : 2)}`,
    className: difference > 0 ? "text-danger" : "text-success",
  };
}

function eventRegion(event: MacroCalendarEvent) {
  if (event.region.includes("中国")) return "CN";
  if (event.region.includes("美国")) return "US";
  if (["欧元", "德国", "法国", "意大利", "西班牙", "欧洲"].some((token) => event.region.includes(token))) return "EU";
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
  const gscpiState = gscpi?.value == null ? "待更新"
    : gscpi.value > 1 ? "供应链压力明显高于常态"
      : gscpi.value > 0.5 ? "供应链压力温和偏高"
        : gscpi.value < -1 ? "供应链压力明显低于常态"
          : gscpi.value < -0.5 ? "供应链压力温和偏低"
            : "供应链压力接近常态";
  const gscpiNote = gscpi?.value == null
    ? "纽约联储全球供应链压力指数尚未返回。"
    : gscpi.value > 0.5
      ? "指数高于历史均值，全球供应链压力仍偏高。"
      : gscpi.value < -0.5
        ? "指数低于历史均值，全球供应链压力偏低。"
        : "指数位于历史均值附近，供应链压力总体平稳。";
  const sourceIssues = snapshot.sourceHealth.items.filter((item) => item.status !== "ok");

  return (
    <section className="mb-6">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">External evidence</p>
          <h2 className="mt-1 text-lg font-bold">全球供应链与能源旁证</h2>
        </div>
        <span className="text-sm text-muted-foreground">Crucix · 外部公开源 · {sourceDate(snapshot.asOf)}</span>
      </div>
      <GlassCard className="overflow-hidden p-0">
        <div className="grid divide-y divide-border/60 lg:grid-cols-3 lg:divide-x lg:divide-y-0">
          <div className="p-5">
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2 text-sm font-semibold"><Activity className="h-4 w-4 text-primary" />全球供应链压力 GSCPI</span>
              <span className={cn("rounded-full px-2 py-1 text-xs", gscpi?.value != null && Math.abs(gscpi.value) > 0.5 ? "bg-warning/12 text-warning" : "bg-muted/50 text-muted-foreground")}>{gscpiState}</span>
            </div>
            <strong className="mt-5 block text-3xl font-bold tabular-nums">{formatValue(gscpi?.value)}</strong>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{gscpiNote}</p>
            <span className="mt-3 block text-xs text-muted-foreground">数据期 {sourceDate(gscpi?.date)}</span>
          </div>

          <div className="p-5">
            <div className="flex items-center justify-between gap-3"><span className="flex items-center gap-2 text-sm font-semibold"><Droplets className="h-4 w-4 text-primary" />能源价格截面</span><span className="text-xs text-muted-foreground">EIA 等公开源</span></div>
            <div className="mt-5 grid grid-cols-2 gap-x-5 gap-y-4">
              {[
                ["WTI", energy.wti, "美元/桶"],
                ["Brent", energy.brent, "美元/桶"],
                ["天然气", energy.naturalGas, "公开报价"],
                ["原油库存", energy.crudeStocks, "源口径"],
              ].map(([label, value, unit]) => (
                <div key={String(label)}><span className="block text-xs text-muted-foreground">{label}</span><strong className="mt-1 block text-xl tabular-nums">{formatValue(value as number | null)}</strong><small className="text-xs text-muted-foreground">{unit}</small></div>
              ))}
            </div>
            {!!energy.signals.length && <p className="mt-4 border-t border-border/60 pt-3 text-sm leading-relaxed text-muted-foreground">{energy.signals[0]}</p>}
          </div>

          <div className="p-5">
            <div className="flex items-center justify-between gap-3"><span className="flex items-center gap-2 text-sm font-semibold"><Database className="h-4 w-4 text-primary" />来源健康</span><span className={cn("rounded-full px-2 py-1 text-xs", snapshot.sourceHealth.failed ? "bg-warning/12 text-warning" : "bg-success/12 text-success")}>{snapshot.sourceHealth.failed ? "部分降级" : "运行正常"}</span></div>
            <div className="mt-5 flex items-end gap-3"><strong className="text-3xl tabular-nums">{snapshot.sourceHealth.ok}/{snapshot.sourceHealth.queried}</strong><span className="pb-1 text-sm text-muted-foreground">来源可用</span></div>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{sourceIssues.length ? `异常或陈旧：${sourceIssues.slice(0, 5).map((item) => item.source).join("、")}` : "当前扫描未发现来源异常。"}</p>
            <p className="mt-3 text-xs text-muted-foreground">这组数据只作全球旁证，不替代各国官方统计发布。</p>
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
  region: string;
  importance: string;
  loading: boolean;
}): VibeDeskPageContext {
  return {
    view: { id: "macro-monitor", title: "宏观观察" },
    visibleBlocks: [
      { id: "macro-regime", type: "macro-regime", title: "增长、价格与流动性" },
      { id: "macro-liquidity", type: "indicator-board", title: "流动性证据" },
      { id: "macro-indicators", type: "indicator-board", title: "核心宏观指标" },
      { id: "crucix-macro-evidence", type: "external-intelligence", title: "全球供应链与能源旁证" },
      { id: "economic-calendar", type: "economic-calendar", title: "经济事件日历" },
      { id: "macro-evidence", type: "evidence-sources", title: "来源与数据缺口" },
    ],
    selection: {},
    filters: {
      horizonDays: input.feed?.horizon.days || 7,
      region: input.region,
      importance: input.importance,
    },
    data: {
      asOf: input.feed?.generatedAt || new Date().toISOString(),
      source: input.feed?.schemaVersion || "newma-desk.macro-monitor.v1",
      freshness: input.loading ? "unknown" : "fresh",
      summary: {
        regime: input.feed?.regime || null,
        indicators: input.feed?.indicators || [],
        liquidity: input.feed?.liquidity || null,
        crucix: input.crucix ? {
          asOf: input.crucix.asOf,
          gscpi: input.crucix.macro.gscpi,
          energy: input.crucix.macro.energy,
          sourceHealth: input.crucix.sourceHealth,
        } : null,
        upcomingEvents: input.events.slice(0, 40),
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
  const [cacheRevision, setCacheRevision] = useState(0);
  // Regime fields were expanded in v2; invalidate snapshots written by the
  // older page so an incomplete cached regime cannot crash the first render.
  const cache = useMemo(() => createVibeDeskSnapshotCache<MacroMonitorFeed>(`macro-monitor:${days}`, 2), [days]);
  const cacheKey = `macro-monitor:${days}:${cacheRevision}`;
  const [feed, setFeed] = useState<MacroMonitorFeed | null>(null);
  const feedRef = useRef(feed);
  const resourceKeyRef = useRef<string | undefined>(undefined);
  feedRef.current = feed;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [crucix, setCrucix] = useState<CrucixSnapshot | null>(null);
  const [crucixLoading, setCrucixLoading] = useState(true);
  const [crucixError, setCrucixError] = useState("");

  const loadCrucix = useCallback(async () => {
    setCrucixLoading(true);
    setCrucixError("");
    try {
      setCrucix(await loadCrucixSnapshot());
    } catch (reason) {
      setCrucixError(reason instanceof Error ? reason.message : "Crucix 数据暂未就绪");
    } finally {
      setCrucixLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    const cached = cache.read()?.value;
    const resourceChanged = resourceKeyRef.current !== cacheKey;
    resourceKeyRef.current = cacheKey;
    if (resourceChanged) setFeed(cached ?? null);
    try {
      const next = await api.macroMonitor(days);
      setFeed(next);
      cache.write(next, next.generatedAt);
    } catch (reason) {
      setError(cached || (!resourceChanged && feedRef.current)
        ? "更新失败，当前为上次数据"
        : reason instanceof Error ? reason.message : "宏观数据暂时不可用");
    } finally {
      setLoading(false);
    }
  }, [cacheKey]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { void loadCrucix(); }, [loadCrucix]);
  useEffect(() => subscribeVibeDeskConfig(() => {
    setCacheRevision((value) => value + 1);
    void loadCrucix();
  }), [loadCrucix]);

  const events = useMemo(() => (feed?.events || []).filter((event) => (
    (region === "all" || eventRegion(event) === region) &&
    (importance === "all" || event.importance === importance)
  )), [feed, importance, region]);
  const groupedEvents = useMemo(() => Object.entries(events.reduce<Record<string, MacroCalendarEvent[]>>((result, event) => {
    (result[event.date] ||= []).push(event);
    return result;
  }, {})), [events]);

  const contextRef = useRef<VibeDeskPageContext>(macroContext({ feed, crucix, events, region, importance, loading: loading || crucixLoading }));
  contextRef.current = macroContext({ feed, crucix, events, region, importance, loading: loading || crucixLoading });
  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => { void publishVibeDeskContext(); }, [crucix, crucixLoading, events.length, feed, importance, loading, region]);

  const regime = feed?.regime;
  const dimensions = [regime?.growth, regime?.inflation, regime?.liquidity]
    .filter((dimension): dimension is MacroRegimeDimension => Boolean(dimension?.label));
  const staleCount = feed?.indicators.filter((item) => item?.freshness?.status === "stale").length || 0;
  const indicatorByEvidence = useMemo(() => new Map(
    (feed?.indicators || []).map((item) => [item.evidenceId, item]),
  ), [feed]);
  const keyEvents = useMemo(() => events.filter((event) => event.importance === "high").slice(0, 6), [events]);
  const liquidity = feed?.liquidity;
  const liquiditySignal = liquidity?.forecast.signal === "supportive"
    ? "边际支持"
    : liquidity?.forecast.signal === "restrictive" ? "边际收紧" : "信号分化";

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
          <select className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" value={days} onChange={(event) => setDays(Number(event.target.value))}>
            <option value={7}>未来 7 天</option><option value={14}>未来 14 天</option><option value={30}>未来 30 天</option>
          </select>
        </label>
        <label className="text-xs text-muted-foreground">地区
          <select className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" value={region} onChange={(event) => setRegion(event.target.value)}>
            <option value="all">全部</option><option value="CN">中国</option><option value="US">美国</option><option value="EU">欧洲</option><option value="OTHER">其他</option>
          </select>
        </label>
        <label className="text-xs text-muted-foreground">重要性
          <select className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground" value={importance} onChange={(event) => setImportance(event.target.value)}>
            <option value="all">全部</option><option value="high">高</option><option value="medium">中</option><option value="low">低</option>
          </select>
        </label>
      </GlassCard>

      {error && <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">{error}</div>}

      {regime && (
        <GlassCard className="mb-4 border-primary/30 bg-primary/5 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Macro regime</p>
              <h2 className="mt-1 text-xl font-bold">{regime.overall?.label || "宏观状态待确认"}</h2>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">{regime.overall?.summary || "宏观状态数据尚未完整返回。"}</p>
            </div>
            <span className="rounded-full border border-border bg-background px-3 py-1 text-xs text-muted-foreground">置信度 {Math.round(regime.confidence.score * 100)}%</span>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {(regime.transmission || []).map((item) => (
              <div key={item.id} className="rounded-lg border border-border/70 bg-background/70 p-3">
                <div className="flex items-center justify-between gap-2 text-sm font-semibold"><span className="flex items-center gap-2"><GitBranch className="h-4 w-4 text-primary" />{item.title}</span><span className="text-xs font-normal text-muted-foreground">{item.evidenceIds.length} 条证据</span></div>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{item.summary}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">{item.assets.map((asset) => <span key={asset} className="rounded bg-muted/50 px-2 py-1 text-xs text-muted-foreground">{asset}</span>)}</div>
              </div>
            ))}
          </div>
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
          { label: "高重要性事件", value: keyEvents.length, Icon: CalendarClock },
          { label: "陈旧指标", value: staleCount, Icon: AlertTriangle },
          { label: "流动性覆盖", value: liquidity ? `${liquidity.coverage.available}/${liquidity.coverage.total}` : "—", Icon: Droplets },
        ].map(({ label, value, Icon }) => (
          <GlassCard key={label} className="p-4"><Icon className="mb-3 h-4 w-4 text-primary" /><strong className="block text-2xl">{value}</strong><span className="text-xs text-muted-foreground">{label}</span></GlassCard>
        ))}
      </div>

      <CrucixMacroEvidence snapshot={crucix} loading={crucixLoading} error={crucixError} />

      {!!keyEvents.length && <section className="mb-6">
        <div className="mb-3 flex items-end justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Key events</p><h2 className="mt-1 text-lg font-bold">本周关键事件</h2></div><span className="text-xs text-muted-foreground">优先展示高重要性事件与公布偏差</span></div>
        <GlassCard className="overflow-hidden p-0">
          <div className="divide-y divide-border/60">{keyEvents.map((event) => {
            const surprise = eventSurprise(event);
            return <div key={event.id} className="grid gap-2 px-4 py-3 text-sm md:grid-cols-[110px_92px_1fr_auto] md:items-center">
              <div><strong>{event.date}</strong><span className="ml-2 text-xs text-muted-foreground">{event.time || "待定"}</span></div>
              <span className="text-muted-foreground">{event.region}</span>
              <div><strong className="font-medium">{event.title}</strong><div className="mt-1 text-xs text-muted-foreground">前值 {formatValue(event.previous)} · 预期 {formatValue(event.forecast)} · 公布 {formatValue(event.actual)}</div></div>
              <div className="flex min-w-24 items-center justify-end gap-2">{surprise && <span className={cn("text-xs font-semibold", surprise.className)}>{surprise.label}</span>}<a href={event.source.url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">来源</a></div>
            </div>;
          })}</div>
        </GlassCard>
      </section>}

      {liquidity && <section className="mb-6">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Liquidity monitor</p><h2 className="mt-1 text-lg font-bold">流动性证据</h2></div>
          <div className="text-right"><strong className={cn("block text-sm", liquidity.forecast.signal === "supportive" ? "text-success" : liquidity.forecast.signal === "restrictive" ? "text-warning" : "text-foreground")}>{liquiditySignal}</strong><span className="text-xs text-muted-foreground">{liquidity.forecast.horizonDays} 日趋势基线 · 置信度 {Math.round(liquidity.forecast.confidence * 100)}%</span></div>
        </div>
        <div className="grid gap-3 lg:grid-cols-3">{liquidity.groups.map((group) => <GlassCard key={group.id} className="p-4">
          <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">{group.label}</h3><span className="text-xs text-muted-foreground">{group.indicators.length} 项</span></div>
          <div className="mt-3 divide-y divide-border/60">{group.indicators.map((item) => <div key={item.id} className="py-3 first:pt-0 last:pb-0">
            <div className="flex items-start justify-between gap-3"><div><strong className="text-sm font-medium">{item.name}</strong><div className="mt-1 text-xs text-muted-foreground">{item.period} · {freshnessLabel(item.freshness.status)}</div></div><div className="text-right"><strong className="block text-base">{formatValue(item.value, item.unit)}</strong><span className={cn("text-xs", liquidityTone(item))}>{formatChange(item.change, item.unit)}</span></div></div>
          </div>)}</div>
          {!group.indicators.length && <div className="mt-3 rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">当前分组暂无可用序列</div>}
        </GlassCard>)}</div>
        <GlassCard className="mt-3 flex flex-wrap items-center justify-between gap-3 p-4 text-sm"><div><strong>{liquidity.source}</strong><p className="mt-1 text-xs text-muted-foreground">{liquidity.note}</p></div><span className="text-xs text-muted-foreground">数据截至 {liquidity.coverage.asOf || "—"}</span></GlassCard>
      </section>}

      <section className="mb-6">
        <div className="mb-3 flex items-end justify-between gap-3">
          <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Macro indicators</p><h2 className="mt-1 text-lg font-bold">核心宏观指标</h2></div>
          <span className="text-xs text-muted-foreground">状态置信度 {regime ? Math.round(regime.confidence.score * 100) : 0}%</span>
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
                <span>{indicator.dateBasis === "period" || indicator.dateBasis === "source-update" ? "数据期" : "发布"} {indicator.dateBasis === "source-update" ? indicator.period : indicator.releaseDate || indicator.period}</span>
                {indicator.dateBasis === "source-update" && indicator.releaseDate && <span>源更新 {indicator.releaseDate}</span>}
                {indicator.nextReleaseDate && <span>下次 {indicator.nextReleaseDate}</span>}
                <span className={indicator.freshness.status === "stale" ? "text-warning" : ""}>{freshnessLabel(indicator.freshness.status)}</span>
              </div>
              <a href={indicator.source.url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs text-primary hover:underline">{indicator.source.label}<ExternalLink className="h-3 w-3" /></a>
            </GlassCard>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-3"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Economic calendar</p><h2 className="mt-1 text-lg font-bold">未来经济事件</h2></div>
        <div className="space-y-4">
          {groupedEvents.map(([eventDate, rows]) => (
            <GlassCard key={eventDate} className="overflow-hidden p-0">
              <div className="border-b border-border/70 px-4 py-3"><strong className="text-sm">{eventDate}</strong><span className="ml-2 text-xs text-muted-foreground">{rows.length} 项</span></div>
              <div className="divide-y divide-border/60">
                {rows.map((event) => (
                  <div key={event.id} className="grid gap-2 px-4 py-3 text-sm md:grid-cols-[64px_72px_1fr_210px] md:items-center">
                    <span className="font-medium">{event.time || "待定"}</span>
                    <span className="text-muted-foreground">{event.region}</span>
                    <div><strong className="font-medium">{event.title}</strong><div className="mt-1 text-xs text-muted-foreground">前值 {formatValue(event.previous)} · 预期 {formatValue(event.forecast)} · 公布 {formatValue(event.actual)}</div></div>
                    <div className="flex items-center justify-between gap-2"><span className={cn("rounded-full px-2 py-1 text-xs", event.importance === "high" ? "bg-danger/12 text-danger" : "bg-warning/12 text-warning")}>重要性 {IMPORTANCE_LABEL[event.importance]}</span>{eventSurprise(event) && <span className={cn("text-xs font-semibold", eventSurprise(event)?.className)}>{eventSurprise(event)?.label}</span>}<a href={event.source.url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">来源</a></div>
                  </div>
                ))}
              </div>
            </GlassCard>
          ))}
          {!loading && !groupedEvents.length && <GlassCard className="p-8 text-center text-sm text-muted-foreground">当前筛选范围没有中高重要性经济事件。</GlassCard>}
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
        <div className="grid gap-2 md:grid-cols-2">{(feed?.sources || []).map((source) => <div key={source.id} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 text-sm"><span className="flex items-center gap-2"><CheckCircle2 className={cn("h-4 w-4", source.status === "ok" ? "text-success" : "text-warning")} />{source.label}</span><span className="text-xs text-muted-foreground">{SOURCE_STATUS_LABEL[source.status]} · {source.count} 条</span></div>)}</div>
        {!!feed?.gaps.length && <div className="mt-4 rounded-lg border border-warning/30 bg-warning/5 p-3"><strong className="text-sm">仍需补齐</strong><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{feed.gaps.map((gap) => <li key={`${gap.capability}:${gap.reason}`}>{GAP_LABELS[gap.capability] || `${gap.capability}：${gap.reason.split("_").join(" ")}`}</li>)}</ul></div>}
      </GlassCard>
      <Disclaimer />
    </div>
  );
}
