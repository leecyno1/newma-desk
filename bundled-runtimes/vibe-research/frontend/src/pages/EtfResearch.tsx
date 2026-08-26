import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  BarChart3,
  Database,
  Loader2,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { GlassCard } from "@/components/ui/GlassCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { api } from "@/lib/api";
import {
  calculateEtfMetrics,
  correlation,
  etfKey,
  normalizedSeries,
  parseEtfSecurity,
  type EtfMarket,
  type EtfMetrics,
  type EtfSecurity,
  type FundInstrumentType,
} from "@/lib/etfResearch";
import {
  createVibeDeskSnapshotCache,
  emitVibeDeskEvent,
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  registerVibeDeskHandoffHandler,
  subscribeVibeDeskEvent,
  subscribeVibeDeskConfig,
  type VibeDeskPageContext,
} from "@/lib/vibedesk";
import { cn } from "@/lib/utils";

const STORE_KEY = "newma-desk.etf-research.universe.v1";
const DEFAULT_UNIVERSE: EtfSecurity[] = [
  { market: "CN", symbol: "510300", assetType: "etf", name: "沪深300ETF" },
  { market: "CN", symbol: "510500", assetType: "etf", name: "中证500ETF" },
  { market: "CN", symbol: "159915", assetType: "etf", name: "创业板ETF" },
];
const COLORS = [
  "hsl(var(--primary))",
  "hsl(var(--success))",
  "hsl(var(--warning))",
  "hsl(var(--info))",
  "hsl(var(--danger))",
  "hsl(var(--foreground))",
];

function loadUniverse(): EtfSecurity[] {
  try {
    const value = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
    if (!Array.isArray(value)) return DEFAULT_UNIVERSE;
    const items = value.flatMap((item): EtfSecurity[] => {
      if (!item || typeof item !== "object") return [];
      const market = (item as { market?: unknown }).market;
      const symbol = (item as { symbol?: unknown }).symbol;
      const assetType = (item as { assetType?: unknown }).assetType;
      if (!["CN", "HK", "US"].includes(String(market)) || typeof symbol !== "string") return [];
      const normalizedAssetType = assetType === "fund" ? "fund" : "etf";
      if (normalizedAssetType === "fund" && market !== "CN") return [];
      return [{
        market: market as EtfMarket,
        symbol: symbol.slice(0, 24),
        assetType: normalizedAssetType,
        name: typeof (item as { name?: unknown }).name === "string"
          ? (item as { name: string }).name.slice(0, 80)
          : undefined,
      }];
    });
    return items.length ? items.slice(0, 6) : DEFAULT_UNIVERSE;
  } catch {
    return DEFAULT_UNIVERSE;
  }
}

const formatPercent = (value: number | null, signed = false) => value == null || !Number.isFinite(value)
  ? "—"
  : `${signed && value > 0 ? "+" : ""}${value.toFixed(2)}%`;

const formatNumber = (value: number | null | undefined, digits = 2) =>
  value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);

const valueTone = (value: number | null) => value == null
  ? "text-muted-foreground"
  : value > 0
    ? "text-danger"
    : value < 0
      ? "text-success"
      : "text-muted-foreground";

function chartPath(values: Array<{ timestamp: number; value: number }>, min: number, max: number) {
  if (!values.length) return "";
  const range = Math.max(max - min, 1);
  return values.map((point, index) => {
    const x = values.length === 1 ? 50 : (index / (values.length - 1)) * 100;
    const y = 92 - ((point.value - min) / range) * 84;
    return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
}

function researchContext(
  metrics: EtfMetrics[],
  selectedKey: string,
  loading: boolean,
  errors: string[],
): VibeDeskPageContext {
  const selected = metrics.find((item) => etfKey(item.security) === selectedKey);
  return {
    view: { id: "etf-research", title: "基金与 ETF 研究" },
    visibleBlocks: [
      { id: "etf-performance", type: "relative-performance", title: "相对收益轨迹" },
      { id: "etf-metrics", type: "comparison-table", title: "风险收益对比" },
      { id: "etf-correlation", type: "correlation-matrix", title: "相关性矩阵" },
      { id: "etf-data-gaps", type: "evidence-gaps", title: "待补数据" },
    ],
    selection: selected ? {
      symbol: selected.security.symbol,
      name: selected.security.name || selected.security.symbol,
      market: selected.security.market,
      assetType: selected.security.assetType,
    } : {},
    filters: { timeframe: "1d", lookback: 320, universeSize: metrics.length },
    data: {
      asOf: new Date().toISOString(),
      source: "newma-desk-market-data",
      freshness: loading ? "unknown" : "fresh",
      summary: {
        instruments: metrics.map((item) => ({
          symbol: item.security.symbol,
          name: item.security.name || item.security.symbol,
          market: item.security.market,
          price: item.quote?.price ?? null,
          return20d: item.return20d,
          return60d: item.return60d,
          return252d: item.return252d,
          annualizedVolatility: item.annualizedVolatility,
          maxDrawdown: item.maxDrawdown,
          returnVolatilityRatio: item.returnVolatilityRatio,
          riskBand: item.riskBand,
          source: item.source,
        })),
        dataGaps: [
          "基金费率与申赎规则",
          "ETF 净值、折溢价与跟踪误差",
          "基金持仓穿透与行业暴露",
          "跨币种比较尚未做汇率归一",
        ],
        errors,
      },
    },
    actions: [
      { id: "etf.refresh", label: "刷新研究数据", available: !loading },
      { id: "security.select", label: "聚焦当前基金工具", available: Boolean(selected) },
    ],
    ...(selected ? {
      wiki: {
        primarySubject: {
          type: selected.security.assetType,
          canonicalId: `${selected.security.assetType}:${selected.security.market}:${selected.security.symbol}`,
          displayName: selected.security.name || selected.security.symbol,
          market: selected.security.market,
          symbol: selected.security.symbol,
          assetType: selected.security.assetType,
        },
        relatedSubjects: [],
        conceptIds: [],
        intent: "fund.research",
        timeframe: "daily",
        snapshotId: `etf-research:${selected.security.assetType}:${selected.security.market}:${selected.security.symbol}`,
      },
    } : {}),
    tasks: loading ? [{ id: "etf-data-load", status: "running" }] : [],
  };
}

function PerformanceChart({ metrics }: { metrics: EtfMetrics[] }) {
  const series = metrics.map((item) => ({ item, values: normalizedSeries(item) }));
  const allValues = series.flatMap((item) => item.values.map((point) => point.value));
  const min = allValues.length ? Math.min(...allValues, 0) : -1;
  const max = allValues.length ? Math.max(...allValues, 0) : 1;
  const zeroY = 92 - ((0 - min) / Math.max(max - min, 1)) * 84;

  return (
    <GlassCard className="relative overflow-hidden p-0" glow>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-5 py-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Relative path</p>
          <h2 className="mt-1 text-lg font-bold">近 120 个交易日相对收益</h2>
        </div>
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          {series.map(({ item }, index) => (
            <span key={etfKey(item.security)} className="inline-flex items-center gap-1.5">
              <i className="h-2 w-2 rounded-full" style={{ background: COLORS[index % COLORS.length] }} />
              {item.security.name || item.security.symbol}
            </span>
          ))}
        </div>
      </div>
      <div className="relative h-64 px-5 py-4">
        {!allValues.length ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">等待历史行情</div>
        ) : (
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full overflow-visible" aria-label="ETF 相对收益曲线">
            {[8, 29, 50, 71, 92].map((y) => (
              <line key={y} x1="0" x2="100" y1={y} y2={y} stroke="hsl(var(--border))" strokeWidth="0.35" vectorEffect="non-scaling-stroke" />
            ))}
            <line x1="0" x2="100" y1={zeroY} y2={zeroY} stroke="hsl(var(--muted-foreground))" strokeDasharray="2 2" strokeWidth="0.45" vectorEffect="non-scaling-stroke" />
            {series.map(({ item, values }, index) => (
              <path
                key={etfKey(item.security)}
                d={chartPath(values, min, max)}
                fill="none"
                stroke={COLORS[index % COLORS.length]}
                strokeWidth="1.45"
                vectorEffect="non-scaling-stroke"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            ))}
          </svg>
        )}
        <span className="absolute left-5 top-3 text-[10px] text-muted-foreground">{formatPercent(max, true)}</span>
        <span className="absolute bottom-3 left-5 text-[10px] text-muted-foreground">{formatPercent(min, true)}</span>
      </div>
    </GlassCard>
  );
}

export function EtfResearch() {
  const [securities, setSecurities] = useState<EtfSecurity[]>(loadUniverse);
  const [metrics, setMetrics] = useState<EtfMetrics[]>([]);
  const [selectedKey, setSelectedKey] = useState(() => etfKey(DEFAULT_UNIVERSE[0]));
  const [market, setMarket] = useState<EtfMarket>("CN");
  const [instrumentType, setInstrumentType] = useState<FundInstrumentType>("etf");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [hint, setHint] = useState("支持交易所 ETF，也支持输入 6 位开放式基金代码读取单位净值。");
  const [refreshRevision, setRefreshRevision] = useState(0);
  const [cacheRevision, setCacheRevision] = useState(0);
  const securityIds = securities.map(etfKey).join(",");
  const resourceKey = `etf-research:${securityIds}`;
  const cache = useMemo(() => createVibeDeskSnapshotCache<{
    metrics: EtfMetrics[];
    errors: string[];
  }>(resourceKey, 1, 2 * 1024 * 1024), [resourceKey]);
  const cacheKey = `${resourceKey}:${cacheRevision}`;
  const resourceKeyRef = useRef<string | undefined>(undefined);
  const metricsRef = useRef(metrics);
  metricsRef.current = metrics;
  const contextRef = useRef<VibeDeskPageContext>(researchContext([], selectedKey, true, []));
  contextRef.current = researchContext(metrics, selectedKey, loading, errors);

  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(securities));
    } catch {
      // The comparison still works when browser storage is unavailable.
    }
  }, [securities]);

  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => subscribeVibeDeskConfig(() => setCacheRevision((value) => value + 1)), []);

  useEffect(() => {
    const unsubscribe = subscribeVibeDeskEvent((event) => {
      if (
        event.event !== "security.selected" ||
        !["etf", "fund"].includes(String(event.payload.assetType))
      ) return;
      const marketValue = event.payload.market;
      const symbolValue = event.payload.symbol;
      if (!["CN", "HK", "US"].includes(String(marketValue)) || typeof symbolValue !== "string") return;
      const security: EtfSecurity = {
        market: marketValue as EtfMarket,
        symbol: symbolValue.slice(0, 24).toUpperCase(),
        assetType: event.payload.assetType as FundInstrumentType,
        name: typeof event.payload.name === "string" ? event.payload.name.slice(0, 80) : undefined,
      };
      const key = etfKey(security);
      setSecurities((current) => current.some((item) => etfKey(item) === key)
        ? current
        : current.length < 6 ? [...current, security] : current);
      setSelectedKey(key);
    });
    return () => {
      unsubscribe();
    };
  }, []);

  useEffect(() => registerVibeDeskHandoffHandler((handoff) => {
    if (
      !["etf", "fund"].includes(handoff.subject.type) ||
      !handoff.subject.symbol ||
      !handoff.subject.market
    ) {
      throw new Error("基金与 ETF 研究只支持 ETF 或开放式基金 Wiki 对象");
    }
    const security: EtfSecurity = {
      market: handoff.subject.market,
      symbol: handoff.subject.symbol.slice(0, 24).toUpperCase(),
      assetType: handoff.subject.type as FundInstrumentType,
      name: handoff.subject.displayName.slice(0, 80),
    };
    const key = etfKey(security);
    setSecurities((current) => current.some((item) => etfKey(item) === key)
      ? current
      : current.length < 6 ? [...current, security] : [...current.slice(1), security]);
    setSelectedKey(key);
    setMarket(security.market);
    setInstrumentType(security.assetType);
    return { selected: handoff.subject.canonicalId };
  }), []);

  useEffect(() => {
    void publishVibeDeskContext();
  }, [metrics, selectedKey, loading, errors]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      if (!securities.length) {
        resourceKeyRef.current = cacheKey;
        setMetrics([]);
        setLoading(false);
        return;
      }
      setLoading(true);
      const cached = cache.read()?.value;
      const resourceChanged = resourceKeyRef.current !== cacheKey;
      resourceKeyRef.current = cacheKey;
      const previous = cached?.metrics ?? (!resourceChanged ? metricsRef.current : []);
      if (resourceChanged) {
        setMetrics(cached?.metrics ?? []);
        setErrors(cached?.errors ?? []);
      } else {
        setErrors([]);
      }
      const histories = await Promise.allSettled(securities.map(async (security) => ({
        security,
        quote: await api.terminalQuote(
          security.symbol,
          security.market,
          security.assetType,
        ).catch(() => undefined),
        history: await api.terminalOhlcv(
          security.symbol,
          security.market,
          320,
          security.assetType,
        ),
      })));
      if (!active) return;
      const failures: string[] = [];
      const next = histories.map((result, index) => {
        const security = securities[index];
        if (result.status === "rejected") {
          failures.push(`${etfKey(security)} 历史行情暂时不可用`);
          return previous.find((item) => etfKey(item.security) === etfKey(security))
            ?? calculateEtfMetrics(security, [], "unavailable");
        }
        return calculateEtfMetrics(
          security,
          result.value.history.items,
          result.value.history.source,
          result.value.quote,
        );
      });
      setMetrics(next);
      setErrors(failures);
      if (histories.some((result) => result.status === "fulfilled")) {
        cache.write({ metrics: next, errors: failures });
      }
      setLoading(false);
      if (!selectedKey || !next.some((item) => etfKey(item.security) === selectedKey)) {
        setSelectedKey(next[0] ? etfKey(next[0].security) : "");
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [cacheKey, refreshRevision]);

  const addSecurity = () => {
    const parsed = parseEtfSecurity(input, market, instrumentType);
    if (!parsed) {
      setHint(instrumentType === "fund"
        ? "开放式基金目前支持 6 位中国基金代码。"
        : "代码格式无法识别，请输入 6 位 A 股 ETF、HK:02800 或 US:SPY。");
      return;
    }
    if (securities.some((security) => etfKey(security) === etfKey(parsed))) {
      setHint(`${etfKey(parsed)} 已在对比池中。`);
      return;
    }
    if (securities.length >= 6) {
      setHint("轻量对比池最多保留 6 只，避免重复拉取过多历史数据。");
      return;
    }
    setSecurities((current) => [...current, parsed]);
    setSelectedKey(etfKey(parsed));
    setInput("");
    setHint(`已加入 ${etfKey(parsed)}；名称与历史数据将在刷新后补齐。`);
  };

  const removeSecurity = (security: EtfSecurity) => {
    const key = etfKey(security);
    const next = securities.filter((item) => etfKey(item) !== key);
    setSecurities(next);
    if (selectedKey === key) setSelectedKey(next[0] ? etfKey(next[0]) : "");
  };

  const selectSecurity = (item: EtfMetrics) => {
    const key = etfKey(item.security);
    setSelectedKey(key);
    emitVibeDeskEvent("security.selected", {
      symbol: item.security.symbol,
      name: item.security.name || item.security.symbol,
      market: item.security.market,
      assetType: item.security.assetType,
      researchModule: "etf-research",
    });
  };

  const correlationRows = useMemo(() => metrics.map((left) => metrics.map((right) =>
    correlation(left, right))), [metrics]);
  const selected = metrics.find((item) => etfKey(item.security) === selectedKey);

  return (
    <div>
      <PageHeader
        title="基金与 ETF 研究"
        subtitle="把资产配置落到具体工具：先比较收益、波动、回撤与相关性，再补充费率、跟踪误差和持仓证据。"
        actions={(
          <button
            type="button"
            onClick={() => setRefreshRevision((value) => value + 1)}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg border border-primary/25 bg-primary/10 px-3 py-2 text-sm font-semibold text-primary transition hover:bg-primary/15 disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            刷新
          </button>
        )}
      />

      <GlassCard className="mb-5 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-28 text-xs font-semibold text-muted-foreground">
            工具类型
            <select
              value={instrumentType}
              onChange={(event) => {
                const next = event.target.value as FundInstrumentType;
                setInstrumentType(next);
                if (next === "fund") setMarket("CN");
              }}
              className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary/60"
            >
              <option value="etf">ETF</option>
              <option value="fund">开放式基金</option>
            </select>
          </label>
          <label className="min-w-24 text-xs font-semibold text-muted-foreground">
            市场
            <select
              value={market}
              onChange={(event) => setMarket(event.target.value as EtfMarket)}
              disabled={instrumentType === "fund"}
              className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary/60"
            >
              <option value="CN">A 股</option>
              <option value="HK">港股</option>
              <option value="US">美股</option>
            </select>
          </label>
          <label className="min-w-64 flex-1 text-xs font-semibold text-muted-foreground">
            {instrumentType === "fund" ? "开放式基金代码" : "ETF 代码"}
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") addSecurity();
              }}
              placeholder={instrumentType === "fund" ? "例如 110022" : market === "CN" ? "例如 510300" : market === "HK" ? "例如 02800" : "例如 SPY"}
              className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-primary/60"
            />
          </label>
          <button
            type="button"
            onClick={addSecurity}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-primary-foreground transition hover:brightness-105"
          >
            <Plus className="h-4 w-4" />
            加入对比
          </button>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">{hint}</p>
      </GlassCard>

      <div className="mb-5 grid gap-3 md:grid-cols-3">
        <GlassCard className="p-4">
          <div className="flex items-center gap-2 text-primary"><BarChart3 className="h-4 w-4" /><span className="text-xs font-bold uppercase tracking-wider">Compare</span></div>
          <p className="mt-3 text-2xl font-black">{metrics.length}</p>
          <p className="text-xs text-muted-foreground">当前工具池 · 最多 6 只</p>
        </GlassCard>
        <GlassCard className="p-4">
          <div className="flex items-center gap-2 text-success"><ShieldCheck className="h-4 w-4" /><span className="text-xs font-bold uppercase tracking-wider">Risk lens</span></div>
          <p className="mt-3 text-2xl font-black">{selected?.riskBand || "—"}</p>
          <p className="text-xs text-muted-foreground">当前聚焦工具的历史风险带</p>
        </GlassCard>
        <GlassCard className="p-4">
          <div className="flex items-center gap-2 text-warning"><Database className="h-4 w-4" /><span className="text-xs font-bold uppercase tracking-wider">Evidence</span></div>
          <p className="mt-3 text-2xl font-black">4</p>
          <p className="text-xs text-muted-foreground">下一阶段待补的基金专属数据块</p>
        </GlassCard>
      </div>

      <PerformanceChart metrics={metrics.filter((item) => item.bars.length > 0)} />

      <GlassCard className="mt-5 overflow-hidden p-0">
        <div className="flex items-center justify-between border-b border-border/70 px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Risk / return</p>
            <h2 className="mt-1 text-lg font-bold">风险收益对比</h2>
          </div>
          {loading && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="bg-muted/35 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-5 py-3">工具</th>
                <th className="px-3 py-3">现价</th>
                <th className="px-3 py-3">20 日</th>
                <th className="px-3 py-3">60 日</th>
                <th className="px-3 py-3">252 日</th>
                <th className="px-3 py-3">年化波动</th>
                <th className="px-3 py-3">最大回撤</th>
                <th className="px-3 py-3">收益波动比</th>
                <th className="px-3 py-3">风险带</th>
                <th className="px-3 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {metrics.map((item) => {
                const key = etfKey(item.security);
                return (
                  <tr
                    key={key}
                    onClick={() => selectSecurity(item)}
                    className={cn(
                      "cursor-pointer transition hover:bg-primary/5",
                      selectedKey === key && "bg-primary/8",
                    )}
                  >
                    <td className="px-5 py-4">
                      <p className="font-bold">
                        {item.security.name || item.security.symbol}
                        <span className="ml-2 text-[10px] font-semibold text-muted-foreground">
                          {item.security.assetType === "fund" ? "开放式基金" : "ETF"}
                        </span>
                      </p>
                      <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{key} · {item.source}</p>
                    </td>
                    <td className="px-3 py-4 font-mono">{formatNumber(item.quote?.price)}</td>
                    <td className={cn("px-3 py-4 font-mono", valueTone(item.return20d))}>{formatPercent(item.return20d, true)}</td>
                    <td className={cn("px-3 py-4 font-mono", valueTone(item.return60d))}>{formatPercent(item.return60d, true)}</td>
                    <td className={cn("px-3 py-4 font-mono", valueTone(item.return252d))}>{formatPercent(item.return252d, true)}</td>
                    <td className="px-3 py-4 font-mono">{formatPercent(item.annualizedVolatility)}</td>
                    <td className="px-3 py-4 font-mono text-success">{formatPercent(item.maxDrawdown)}</td>
                    <td className="px-3 py-4 font-mono">{formatNumber(item.returnVolatilityRatio)}</td>
                    <td className="px-3 py-4"><span className="rounded-full border border-border bg-muted/40 px-2 py-1 text-xs">{item.riskBand}</span></td>
                    <td className="px-3 py-4">
                      <button
                        type="button"
                        aria-label={`移除 ${item.security.name || item.security.symbol}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          removeSecurity(item.security);
                        }}
                        className="rounded-md p-1.5 text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </GlassCard>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.2fr_.8fr]">
        <GlassCard className="overflow-hidden p-0">
          <div className="border-b border-border/70 px-5 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Diversification</p>
            <h2 className="mt-1 text-lg font-bold">日收益相关性矩阵</h2>
          </div>
          <div className="overflow-x-auto p-4">
            <table className="w-full min-w-[520px] text-center text-xs">
              <thead>
                <tr>
                  <th className="p-2 text-left text-muted-foreground">代码</th>
                  {metrics.map((item) => <th key={etfKey(item.security)} className="p-2 font-mono text-muted-foreground">{item.security.symbol}</th>)}
                </tr>
              </thead>
              <tbody>
                {metrics.map((left, rowIndex) => (
                  <tr key={etfKey(left.security)}>
                    <th className="p-2 text-left font-mono">{left.security.symbol}</th>
                    {correlationRows[rowIndex]?.map((value, columnIndex) => (
                      <td key={etfKey(metrics[columnIndex].security)} className="p-1.5">
                        <span
                          className="block rounded-md border border-border/60 px-2 py-2 font-mono"
                          style={{ background: value == null ? undefined : `hsl(var(--primary) / ${Math.max(Math.abs(value) * 0.2, 0.03)})` }}
                        >
                          {value == null ? "—" : value.toFixed(2)}
                        </span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>

        <GlassCard className="p-5" glow>
          <div className="flex items-center gap-2 text-warning">
            <Activity className="h-4 w-4" />
            <p className="text-xs font-bold uppercase tracking-[0.18em]">Next evidence</p>
          </div>
          <h2 className="mt-2 text-lg font-bold">基金专属数据仍需补齐</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            当前版本先把统一行情转成可比较的风险收益证据，不用模型常识填补基金事实。以下四类数据进入下一阶段统一接口。
          </p>
          <ol className="mt-4 space-y-3 text-sm">
            {[
              ["费率与申赎", "管理费、托管费、申购赎回与交易成本"],
              ["跟踪质量", "净值、折溢价、跟踪误差与跟踪差异"],
              ["持仓穿透", "前十大持仓、行业、地区与集中度"],
              ["组合适配", "与现有持仓的重合度、边际风险和再平衡影响"],
            ].map(([title, description], index) => (
              <li key={title} className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-primary/30 bg-primary/10 font-mono text-xs text-primary">{index + 1}</span>
                <span><b>{title}</b><small className="mt-0.5 block text-xs leading-5 text-muted-foreground">{description}</small></span>
              </li>
            ))}
          </ol>
          {errors.length > 0 && (
            <div className="mt-4 rounded-lg border border-warning/25 bg-warning/5 p-3 text-xs text-warning">
              {errors.join("；")}
            </div>
          )}
        </GlassCard>
      </div>

      <Disclaimer compact />
    </div>
  );
}
