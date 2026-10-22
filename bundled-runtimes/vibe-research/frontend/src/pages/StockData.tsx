import { useCallback, useEffect, useRef, useState } from "react";
import {
  Search, FileText, Newspaper, Loader2, AlertCircle, LineChart, BarChart3, Megaphone,
  Wallet, Trophy, CalendarClock, Boxes, MessageSquare,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { EarningsSnapshot } from "@/components/ui/EarningsSnapshot";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { EquityResearchFramework } from "@/components/equity/EquityResearchFramework";
import { EquityPeerComparison } from "@/components/equity/EquityPeerComparison";
import {
  api, ApiError, type Valuation, type Report, type NewsItem, type ValPercentile, type ValMetric,
  type Financials, type Announcement, type MarginRow, type BlockTradeRow, type HolderRow,
  type DividendRow, type FundFlowRow, type DragonTiger, type Lockup, type Blocks, type HotConcept, type QaRow,
  type EquityResearchSnapshot, type GlobalStock,
  type EquityResearchHistoryItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { recentFundFlow } from "@/lib/fundFlowWindow";
import {
  loadEquityResearchHistory,
  persistEquityResearchHistory,
} from "@/lib/researchHistory";
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
import { conceptIdsForLabels } from "@/lib/wiki";

interface StockDataSnapshot {
  code: string;
  val: Valuation | null;
  reports: Report[];
  news: NewsItem[];
  pctl: ValPercentile | null;
  fin: Financials | null;
  anns: Announcement[];
  margin: MarginRow[];
  blockT: BlockTradeRow[];
  holders: HolderRow[];
  dividend: DividendRow[];
  fundFlow: FundFlowRow[];
  dt: DragonTiger | null;
  lockup: Lockup | null;
  blocks: Blocks | null;
  hotCon: HotConcept[];
  qa: QaRow[];
  gstock: GlobalStock | null;
  research: EquityResearchSnapshot | null;
  researchFailureHistory: EquityResearchHistoryItem[];
  sourceStates: Partial<Record<StockSource, SourceState>>;
}

const sourceLabels = {
  val: "行情与估值", reports: "机构研报", news: "个股新闻", pctl: "估值历史分位", fin: "财务摘要", anns: "公司公告",
  margin: "融资融券", blockT: "大宗交易", holders: "股东户数", dividend: "分红方案", fundFlow: "资金流向",
  dt: "龙虎榜", lockup: "限售解禁", blocks: "板块归属", hotCon: "热门概念", qa: "投资者互动",
  gstock: "海外行情与财务", research: "跨市场研究框架",
} as const;
type StockSource = keyof typeof sourceLabels;
interface SourceState {
  status: "loading" | "available" | "empty" | "failed";
  retained: boolean;
  lastSuccessAt: string | null;
  error?: string;
}

// 仅表示当前接口是否返回可用内容，不表示该来源完整覆盖或数据新鲜。
function hasSourceData<K extends StockSource>(key: K, value: StockDataSnapshot[K]): boolean {
  if (value == null) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (key === "dt") {
    const dt = value as DragonTiger;
    return Boolean(dt.records.length || dt.seats.buy.length || dt.seats.sell.length);
  }
  if (key === "lockup") {
    const lockup = value as Lockup;
    return Boolean(lockup.history.length || lockup.upcoming.length);
  }
  if (key === "blocks") {
    const blocks = value as Blocks;
    return Boolean(blocks.boards.length || blocks.concept_tags.length);
  }
  if (key === "pctl") return Object.values((value as ValPercentile).metrics).some(Boolean);
  if (key === "fin") return Object.entries(value).some(([field, v]) => field !== "period" && field !== "basis" && v != null && v !== "");
  return true;
}

function sourceFailure(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) return "访问未获授权，请检查数据接入权限";
    if (error.status === 501) return "所需数据能力未安装或未启用";
    if (error.status === 429) return "数据源请求受限，请稍后手动查询";
    if (error.status === 504) return "数据源响应超时，本次结果未确认";
    if (error.status === 400 || error.status === 422) return "查询条件未被接受，请检查证券代码";
  }
  return "数据源暂不可用，本次结果未确认";
}

function sourceStatusText(state?: SourceState): string {
  if (!state) return "尚未查询";
  const text = { loading: "加载中", available: "已返回", empty: "空结果（仅限本次查询范围）", failed: "查询失败" }[state.status];
  return `${text}${state.retained ? " · 保留上次结果，待更新" : ""}`;
}

function marketForCode(code: string) {
  return /^\d{6}$/.test(code) ? "CN" : /^\d{5}$/.test(code) ? "HK" : /\.(KS|KQ)$/.test(code) ? "KR" : "US";
}

function emptyStockDataSnapshot(code: string): StockDataSnapshot {
  return {
    code,
    val: null,
    reports: [],
    news: [],
    pctl: null,
    fin: null,
    anns: [],
    margin: [],
    blockT: [],
    holders: [],
    dividend: [],
    fundFlow: [],
    dt: null,
    lockup: null,
    blocks: null,
    hotCon: [],
    qa: [],
    gstock: null,
    research: null,
    researchFailureHistory: [],
    sourceStates: {},
  };
}

function hasStockData(snapshot: StockDataSnapshot) {
  return (Object.keys(sourceLabels) as StockSource[]).some(key => hasSourceData(key, snapshot[key]));
}

// 金额格式化（后端资金单位：元 / 万元）
const yi = (v: number | null | undefined) => v == null || !Number.isFinite(v) ? "—" : `${(v / 1e8).toFixed(2)} 亿`;

const fmt = (v: number | null | undefined, suffix = "") =>
  v === null || v === undefined ? "—" : `${v}${suffix}`;

// A股红涨绿跌（中国平台看美港股也用此惯例）
const pctColor = (p: number | null | undefined) =>
  p != null && p > 0 ? "text-danger" : p != null && p < 0 ? "text-success" : "text-muted-foreground";
const pctStr = (p: number | null | undefined) => (p == null ? "—" : `${p > 0 ? "+" : ""}${p}%`);
// 美/港股金额（原生币种）
const curOf = (market: string) => (market === "HK" ? "港元" : market === "KR" ? "韩元" : "美元");
const mktName = (m: string) => (m === "HK" ? "港股" : m === "KR" ? "韩股" : "美股");
const bigMoney = (v: number | null, market: string) =>
  v == null ? "—" : v >= 1e12 ? `${(v / 1e12).toFixed(2)} 万亿${curOf(market)}` : `${(v / 1e8).toFixed(0)} 亿${curOf(market)}`;
const round2 = (v: number | null | undefined, suffix = "") =>
  v == null ? "—" : `${Math.round(v * 100) / 100}${suffix}`;

// 百分比：后端偶发给 null/缺字段时显示 —，不出现 "NaN%" / 误导性 "0.00%"
const pct = (v: number | null | undefined) =>
  v === null || v === undefined || !Number.isFinite(Number(v)) ? "—" : `${Number(v).toFixed(2)}%`;

// 小指标块（复用于资金面/筹码卡）
function Metric({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div className="rounded-lg bg-muted/30 p-3">
      <p className="text-xs text-muted-foreground">{k}</p>
      <p className="mt-0.5 font-mono text-base font-bold">{v}</p>
      {sub && <p className="text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

// 估值历史分位带（理杏仁式）：绿=低估区 / 灰=合理区 / 红=高估区；只给位置，不划买卖。
function ValBand({ label, m }: { label: string; m: ValMetric }) {
  const span = Math.max(m.max - m.min, 1e-6);
  const pos = (v: number) => Math.min(100, Math.max(0, ((v - m.min) / span) * 100));
  const p20 = pos(m.p20), p80 = pos(m.p80), cur = pos(m.current);
  const zoneColor = m.percentile < 20 ? "text-success" : m.percentile > 80 ? "text-danger" : "text-muted-foreground";
  const zoneLabel = m.percentile < 20 ? "低估区" : m.percentile > 80 ? "高估区" : "合理区";
  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-1 text-sm">
        <span className="font-medium">{label} <span className="text-xs text-muted-foreground/60">{m.n} 点</span></span>
        <span className="text-muted-foreground">当前 <b className="font-mono text-foreground">{m.current}</b> · 近5年 <b className={cn("font-mono", zoneColor)}>{m.percentile}%</b> 分位（<span className={zoneColor}>{zoneLabel}</span>）</span>
      </div>
      <div className="relative h-2.5 w-full overflow-hidden rounded-full">
        <div className="absolute inset-0 flex">
          <div className="bg-success/35" style={{ width: `${p20}%` }} />
          <div className="bg-muted" style={{ width: `${p80 - p20}%` }} />
          <div className="flex-1 bg-danger/35" />
        </div>
        <div className="absolute top-1/2 h-4 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded bg-foreground shadow" style={{ left: `${cur}%` }} />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground/60">
        <span>低 {m.min}</span><span>20% {m.p20}</span><span>中 {m.p50}</span><span>80% {m.p80}</span><span>高 {m.max}</span>
      </div>
    </div>
  );
}

export function StockData() {
  const [code, setCode] = useState("");
  const [linkedName, setLinkedName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState(() => emptyStockDataSnapshot(""));
  const {
    code: activeCode, val, reports, news, pctl, fin, anns, margin, blockT, holders, dividend, fundFlow,
    dt, lockup, blocks, hotCon, qa, gstock, research, researchFailureHistory, sourceStates,
  } = snapshot;
  const sourceEntries = Object.entries(sourceStates) as [StockSource, SourceState][];
  const loading = sourceEntries.some(([, state]) => state.status === "loading");
  const researchLoading = sourceStates.research?.status === "loading";
  const researchError = sourceStates.research?.error;
  const fundWindow = recentFundFlow(fundFlow);
  const runIdRef = useRef(0);
  const activeCodeRef = useRef("");
  const snapshotRef = useRef<StockDataSnapshot>(emptyStockDataSnapshot(""));
  const contextRef = useRef<VibeDeskPageContext>({
    view: { id: "stock-research", title: "个股数据" },
    visibleBlocks: [],
    selection: {},
    filters: {},
    data: { source: "vibe-research-stock-data", freshness: "unknown" },
    actions: [],
    tasks: [],
  });

  const execute = useCallback(async (
    requestedCode: string,
    shouldEmit = true,
    requestedName = "",
  ) => {
    const c = requestedCode.trim().toUpperCase();
    if (!c) { setErr("请输入代码"); return; }
    setCode(c);
    setLinkedName(requestedName);
    if (shouldEmit) {
      const market = marketForCode(c);
      emitVibeDeskEvent("security.selected", {
        symbol: c,
        name: c,
        market,
      });
    }
    const cache = createVibeDeskSnapshotCache<StockDataSnapshot>(`stock-data:${c}`, 1, 2 * 1024 * 1024);
    const cached = cache.read()?.value;
    const resourceChanged = activeCodeRef.current !== c;
    activeCodeRef.current = c;
    const rid = ++runIdRef.current;
    if (resourceChanged) snapshotRef.current = cached ?? emptyStockDataSnapshot(c);
    else if (cached && !hasStockData(snapshotRef.current)) snapshotRef.current = cached;
    const commitSnapshot = (patch: Partial<StockDataSnapshot>) => {
      if (rid !== runIdRef.current) return;
      snapshotRef.current = { ...snapshotRef.current, ...patch, code: c };
      setSnapshot(snapshotRef.current);
      cache.write(snapshotRef.current);
    };
    setErr(null);
    const aShare = /^\d{6}$/.test(c);
    const keys = (Object.keys(sourceLabels) as StockSource[]).filter(key =>
      aShare ? key !== "gstock" : key === "gstock" || key === "research");
    commitSnapshot({ sourceStates: Object.fromEntries(keys.map(key => [key, {
      status: "loading", retained: hasSourceData(key, snapshotRef.current[key]),
      lastSuccessAt: snapshotRef.current.sourceStates?.[key]?.lastSuccessAt ?? null,
    }])) });

    // 每个来源独立提交数据与状态；失败不写空值，换证券/卸载后的迟到结果不再回填。
    const load = async <K extends StockSource>(key: K, request: () => Promise<StockDataSnapshot[K]>) => {
      try {
        const value = await request();
        if (rid !== runIdRef.current) return;
        commitSnapshot({ [key]: value, sourceStates: {
          ...snapshotRef.current.sourceStates,
          [key]: { status: hasSourceData(key, value) ? "available" : "empty", retained: false, lastSuccessAt: new Date().toISOString() },
        } });
        return value;
      } catch (error) {
        if (rid !== runIdRef.current) return;
        commitSnapshot({ sourceStates: { ...snapshotRef.current.sourceStates, [key]: {
          ...snapshotRef.current.sourceStates[key], status: "failed",
          retained: hasSourceData(key, snapshotRef.current[key]), error: sourceFailure(error),
        } } });
      }
    };
    const researchRequest = load("research", () => api.equityResearch(c)).then(async (result) => {
      if (rid !== runIdRef.current) return;
      if (result) {
        const hydrated = await persistEquityResearchHistory(result);
        commitSnapshot({ research: hydrated, researchFailureHistory: [] });
      } else {
        const history = await loadEquityResearchHistory(c);
        commitSnapshot({ researchFailureHistory: history });
      }
    });
    await Promise.all([
      researchRequest,
      ...(aShare ? [
        load("val", () => api.valuation(c)), load("reports", () => api.reports(c)),
        load("news", () => api.news(c)), load("pctl", () => api.percentile(c)),
        load("fin", () => api.financials(c)), load("anns", () => api.announcements(c)),
        load("margin", () => api.margin(c)), load("blockT", () => api.blockTrade(c)),
        load("holders", () => api.holders(c)), load("dividend", () => api.dividend(c)),
        load("fundFlow", () => api.fundFlow(c)), load("dt", () => api.dragonTiger(c)),
        load("lockup", () => api.lockup(c)), load("blocks", () => api.blocks(c)),
        load("hotCon", () => api.hotConcepts(c)), load("qa", () => api.investorQa(c)),
      ] : [load("gstock", () => api.globalStock(c))]),
    ]);
  }, []);

  const run = () => { if (!loading || code.trim() !== activeCode) void execute(code); };

  const selectedMarket = marketForCode(activeCode);
  const selectedName = val?.name || gstock?.name || linkedName || activeCode;
  const conceptIds = conceptIdsForLabels([
    ...(blocks?.concept_tags ?? []),
    ...hotCon.map((item) => item.concept),
  ]);

  contextRef.current = {
    view: { id: "stock-research", title: "个股数据" },
    visibleBlocks: [
      { id: "stock-search", type: "security-search", title: "证券查询" },
      ...(activeCode ? [{ id: "stock-sources", type: "table", title: "数据源覆盖" }] : []),
      ...(val || gstock
        ? [{ id: "stock-overview", type: "security-overview", title: "个股数据总览" }]
        : []),
      ...(research
        ? [{ id: "equity-research-framework", type: "evidence-ledger", title: "跨市场研究框架" }]
        : []),
      ...(fundFlow.length || margin.length || holders.length || blockT.length || dividend.length
        ? [{ id: "stock-capital", type: "evidence-ledger", title: "资金面与筹码" }]
        : []),
      ...(lockup && (lockup.upcoming.length || lockup.history.length)
        ? [{ id: "stock-lockup", type: "evidence-ledger", title: "限售解禁" }] : []),
      ...(reports.length ? [{ id: "stock-reports", type: "table", title: "近期研报" }] : []),
      ...(anns.length ? [{ id: "stock-announcements", type: "table", title: "近期公告" }] : []),
      ...(news.length ? [{ id: "stock-news", type: "table", title: "个股新闻" }] : []),
      ...(fin && hasSourceData("fin", fin) ? [{ id: "stock-financials", type: "metrics", title: "财务关键指标" }] : []),
    ],
    selection: activeCode
      ? {
          symbol: activeCode,
          name: selectedName,
          market: selectedMarket,
        }
      : {},
    filters: {},
    data: {
      source: gstock
        ? (gstock.data_sources || gstock.quote.sources || ["global-stock-data"]).join(" -> ")
        : "vibe-research-stock-data",
      freshness: sourceEntries.some(([, state]) => state.retained) ? "stale" : "unknown",
      summary: {
        loading,
        error: err || "",
        sourceStates: Object.fromEntries(sourceEntries.map(([key, state]) => [key, { ...state, label: sourceLabels[key] }])),
        sourceBasis: "已返回只表示接口返回内容，不保证覆盖完整；空结果只限本次查询范围，不等于没有风险。retained为上次结果；lastSuccessAt是接口获取时间，不是业务日期。研究框架另有内部来源覆盖与缺口。",
        timeBasis: "页面包含不同业务日期的数据，不以查询时间代替数据时间；详见各指标日期",
        reports: reports.slice(0, 12), announcements: anns.slice(0, 12), news: news.slice(0, 10),
        financials: fin, valuationPercentile: pctl,
        ...(fundFlow.length ? {fundFlowWindow: {...fundWindow, unit: "CNY", windowSize: 20,
          basis: "最近20个有记录日期，不保证交易日连续；缺失或冲突不填零",
          sources: [...new Set(fundFlow.map(row => row.source).filter(Boolean))]}} : {}),
        ...(margin[0] ? {margin: {asOf: margin[0].date, financingBalanceCny: margin[0].rzye,
          lendingBalanceCny: margin[0].rqye}} : {}),
        ...(holders[0] ? {holders: holders[0]} : {}),
        ...(blockT.length ? {blockTrades: blockT.slice(0, 5)} : {}),
        ...(dividend.length ? {dividendPlans: dividend.slice(0, 2), dividendBasis: "每10股税前方案，进度/披露日/除权日分开，不代表现金已到账"} : {}),
        ...(lockup ? {lockup, lockupBasis: "数量为万股，占比为占流通股本的小数；披露日未核验，解禁不代表实际减持"} : {}),
        ...(val
          ? {
              quote: {
                symbol: val.code,
                name: val.name,
                price: val.price,
                peTtm: val.pe_ttm,
                pb: val.pb,
                marketCapYi: val.mcap_yi,
              },
              reportCount: reports.length,
              announcementCount: anns.length,
              newsCount: news.length,
            }
          : {}),
        ...(gstock
          ? {
              quote: {
                symbol: gstock.code,
                name: gstock.name,
                market: gstock.market,
                price: gstock.quote.price,
                changePct: gstock.quote.change_pct,
                marketCap: gstock.quote.mcap,
              },
            }
          : {}),
        ...(research
          ? {
              researchFramework: {
                frameworkVersion: research.frameworkVersion,
                coverage: research.coverage,
                sections: research.sections,
                analytics: research.analytics,
                scorecard: research.scorecard,
                comparisonProfile: research.comparisonProfile,
                derivedEvidence: research.derivedEvidence,
                workflow: research.workflow,
                reportHistory: research.reportHistory,
                evidenceLedger: research.evidenceLedger,
                gaps: research.gaps,
              },
            }
          : {}),
        ...(researchError
          ? {
              researchFailure: researchError,
              previousResearch: researchFailureHistory.slice(0, 3),
            }
          : {}),
      },
    },
    actions: [],
    ...(activeCode && selectedMarket !== "KR" ? {
      wiki: {
        primarySubject: {
          type: "security",
          canonicalId: `security:${selectedMarket}:${activeCode}`,
          displayName: selectedName,
          market: selectedMarket,
          symbol: activeCode,
          assetType: "stock",
        },
        relatedSubjects: [],
        conceptIds,
        intent: "equity.research",
        snapshotId: `stock-research:${selectedMarket}:${activeCode}:${research?.generatedAt ?? "current"}`,
      },
    } : {}),
    tasks: researchLoading
      ? [{ id: `equity-research:${activeCode}`, status: "running", actionId: "research.equity-snapshot" }]
      : researchError
        ? [{ id: `equity-research:${activeCode}`, status: "failed", actionId: "research.equity-snapshot" }]
        : research?.workflow
          ? [{
              id: research.workflow.task.id,
              status: research.workflow.task.status,
              actionId: "research.equity-snapshot",
            }]
          : [],
  };

  useEffect(() => {
    const unregisterContext = registerVibeDeskContextProvider(() => contextRef.current);
    const unsubscribeConfig = subscribeVibeDeskConfig(() => {
      if (!activeCodeRef.current) return;
      const currentCode = activeCodeRef.current;
      activeCodeRef.current = "";
      void execute(currentCode, false);
    });
    const unsubscribeEvent = subscribeVibeDeskEvent((event) => {
      if (event.event !== "security.selected") return;
      const symbol = event.payload.symbol;
      if (typeof symbol !== "string") return;
      void execute(symbol, false);
    });
    const unregisterHandoff = registerVibeDeskHandoffHandler((handoff) => {
      if (
        handoff.subject.type !== "security" ||
        !handoff.subject.symbol ||
        !handoff.subject.market
      ) {
        throw new Error("个股研究只支持股票 Wiki 对象");
      }
      void execute(
        handoff.subject.symbol,
        false,
        handoff.subject.displayName,
      );
      return { selected: handoff.subject.canonicalId };
    });
    return () => {
      runIdRef.current += 1;
      unregisterContext();
      unregisterHandoff();
      unsubscribeConfig();
      unsubscribeEvent();
    };
  }, [execute]);

  useEffect(() => {
    void publishVibeDeskContext();
  }, [snapshot, linkedName, err]);

  const sourceNotice = (...keys: StockSource[]) => {
    const notes = keys.filter(key => sourceStates[key]?.status === "failed" || sourceStates[key]?.retained);
    return notes.length ? <p className="mb-2 text-xs text-warning">{notes.map(key => `${sourceLabels[key]}：${sourceStatusText(sourceStates[key])}`).join("；")}</p> : null;
  };

  const metrics = val ? [
    { k: "现价", v: fmt(val.price) },
    { k: "PE(TTM)", v: fmt(val.pe_ttm) },
    { k: "PB", v: fmt(val.pb) },
    { k: "总市值", v: fmt(val.mcap_yi, " 亿") },
    { k: "26E EPS", v: fmt(val.eps_26e) },
    { k: "前向PE", v: fmt(val.pe_26e) },
    { k: "PEG", v: fmt(val.peg) },
    { k: "消化年数", v: fmt(val.digest_years, " 年") },
  ] : [];

  const researchPanels = (
    <>
      {researchLoading && !research && (
        <GlassCard className="mb-4">
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            正在采集证据、计算指标并检查数据质量…
          </p>
        </GlassCard>
      )}
      {researchError && (
        <GlassCard className="mb-4 border-warning/30 bg-warning/5">
          <p className="flex items-center gap-2 text-xs font-medium text-warning">
            <AlertCircle className="h-3.5 w-3.5" /> 研究流程未完成
          </p>
          <p className="mt-1.5 text-[11px] leading-5 text-muted-foreground">
            {researchError}。已有结果仍可查看；重新查询后会再次尝试，不会用空数据覆盖最近一次有效研究记录。
          </p>
          {researchFailureHistory[0] && (
            <p className="mt-1.5 border-t border-warning/15 pt-1.5 text-[10px] text-muted-foreground">
              Desk 中最近记录：{new Date(researchFailureHistory[0].createdAt).toLocaleString("zh-CN", { hour12: false })}
              {` · 质量 ${researchFailureHistory[0].qualityScore}/100 · 覆盖 ${Math.round(researchFailureHistory[0].coverageRatio * 100)}%`}
            </p>
          )}
        </GlassCard>
      )}
      {!researchError && sourceNotice("research")}
      {research && <EquityResearchFramework snapshot={research} />}
      {research && <EquityPeerComparison currentSymbol={research.identity.symbol} />}
    </>
  );

  return (
    <div>
      <PageHeader
        title="个股数据"
        subtitle="行情 · 估值 · 研报 · 新闻 —— 客观数据配齐，判断交给你的 AI"
      />

      {/* 查询框 */}
      <div className="mb-3 flex gap-2">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/[^a-zA-Z0-9.]/g, "").toUpperCase().slice(0, 12))}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="A 股 6 位代码，或美股/港股/韩股（AAPL / 00700 / 005930.KS）"
          aria-label="证券代码"
          className="min-w-0 flex-1 sm:max-w-80 rounded-lg border border-border bg-card/80 px-3 py-2 text-sm outline-none placeholder:text-muted-foreground/70 focus:border-primary/50"
        />
        <button
          onClick={run}
          disabled={loading && code.trim() === activeCode}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-4 py-2 text-sm font-medium text-primary shadow-glow hover:bg-primary/25 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          查询
        </button>
      </div>
      {activeCode && <p className="mb-3 text-xs text-muted-foreground">当前研究：{selectedName} · {activeCode} · {selectedMarket}{code.trim() !== activeCode ? "；输入框已修改，提交查询后才切换对象" : ""}</p>}

      {activeCode && (
        <section aria-label="数据源覆盖" id="stock-sources" className="mb-4 rounded-lg border border-border bg-card/80 p-3">
          <h2 className="text-sm font-semibold">数据源覆盖</h2>
          <p className="mt-1 text-xs text-muted-foreground" role="status">
            已返回 {sourceEntries.filter(([, s]) => s.status === "available").length} · 空结果 {sourceEntries.filter(([, s]) => s.status === "empty").length} · 失败 {sourceEntries.filter(([, s]) => s.status === "failed").length} · 加载中 {sourceEntries.filter(([, s]) => s.status === "loading").length}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">空结果不等于没有风险；失败不覆盖上次结果。接口返回不保证数据完整或实时，研究框架内部缺口另列。</p>
          <details className="mt-2">
            <summary className="cursor-pointer text-xs text-primary">查看各来源状态与获取时间</summary>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead><tr className="text-muted-foreground"><th className="py-2 pr-3">来源</th><th className="py-2 pr-3">本次状态</th><th className="py-2">最近成功获取（非业务日期）</th></tr></thead>
                <tbody>{sourceEntries.map(([key, state]) => <tr key={key} className="border-t border-border/40">
                  <th className="py-2 pr-3 font-normal">{sourceLabels[key]}</th>
                  <td className={cn("py-2 pr-3", state.status === "failed" || state.retained ? "text-warning" : "text-muted-foreground")}>{sourceStatusText(state)}{state.error && <p className="mt-1">{state.error}</p>}</td>
                  <td className="py-2 text-muted-foreground">{state.lastSuccessAt ? new Date(state.lastSuccessAt).toLocaleString("zh-CN", { hour12: false }) : "未知"}</td>
                </tr>)}</tbody>
              </table>
            </div>
          </details>
        </section>
      )}

      {err && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" /> {err}
        </div>
      )}

      {/* 美股 / 港股视图（global-stock-data Skill 多源回退） */}
      {sourceNotice("gstock")}
      {gstock && (
        <>
          <GlassCard glow className="mb-4">
            <div className="mb-4 flex items-baseline gap-2">
              <h2 className="text-xl font-bold">{gstock.name}</h2>
              <span className="font-mono text-sm text-muted-foreground">{gstock.code}</span>
              <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] text-primary">{gstock.market}</span>
              <span className="ml-auto text-xs text-muted-foreground">{mktName(gstock.market)}</span>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { k: "现价", v: fmt(gstock.quote.price), cls: pctColor(gstock.quote.change_pct) },
                { k: "涨跌幅", v: pctStr(gstock.quote.change_pct), cls: pctColor(gstock.quote.change_pct) },
                { k: "总市值", v: bigMoney(gstock.quote.mcap, gstock.market), cls: "" },
                { k: "成交额", v: bigMoney(gstock.quote.amount, gstock.market), cls: "" },
                { k: "开盘", v: fmt(gstock.quote.open), cls: "" },
                { k: "最高", v: fmt(gstock.quote.high), cls: "" },
                { k: "最低", v: fmt(gstock.quote.low), cls: "" },
                { k: "昨收", v: fmt(gstock.quote.prev_close), cls: "" },
              ].map((m) => (
                <div key={m.k} className="rounded-lg bg-muted/30 p-3">
                  <p className="text-xs text-muted-foreground">{m.k}</p>
                  <p className={cn("mt-0.5 font-mono text-base font-bold", m.cls)}>{m.v}</p>
                </div>
              ))}
            </div>
          </GlassCard>

          {gstock.metrics && (
            <GlassCard className="mb-4">
              <h3 className="mb-1 flex items-center gap-1.5 text-sm font-semibold">
                <BarChart3 className="h-4 w-4 text-primary" /> 关键财务指标
                <span className="text-xs font-normal text-muted-foreground/60">· {gstock.metrics.report_date}</span>
              </h3>
              <p className="mb-3 text-[11px] text-muted-foreground/60">东财 GMAININDICATOR，最新报告期。金额为原生币种。</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  { k: "营业收入", v: bigMoney(gstock.metrics.revenue, gstock.market), yoy: gstock.metrics.revenue_yoy != null ? round2(gstock.metrics.revenue_yoy, "%") : "" },
                  { k: "归母净利", v: bigMoney(gstock.metrics.net_profit, gstock.market), yoy: "" },
                  { k: "每股收益 EPS", v: round2(gstock.metrics.eps), yoy: "" },
                  { k: "ROE", v: round2(gstock.metrics.roe, "%"), yoy: "" },
                  { k: "毛利率", v: round2(gstock.metrics.gross_margin, "%"), yoy: "" },
                  { k: "净利率", v: round2(gstock.metrics.net_margin, "%"), yoy: "" },
                  { k: "资产负债率", v: round2(gstock.metrics.debt_ratio, "%"), yoy: "" },
                ].map((m) => (
                  <div key={m.k} className="rounded-lg bg-muted/30 p-3">
                    <p className="text-xs text-muted-foreground">{m.k}</p>
                    <p className="mt-0.5 font-mono text-base font-bold">{m.v}</p>
                    {m.yoy && <p className="text-[11px] text-muted-foreground">同比 {m.yoy}</p>}
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          <p className="mb-4 text-xs text-muted-foreground/60">
            美股 / 港股数据直接使用 <a href="https://github.com/simonlin1212/global-stock-data" target="_blank" rel="noreferrer" className="hover:text-primary">global-stock-data</a> Skill
            （{(gstock.data_sources || gstock.quote.sources || []).join(" → ") || "公开数据源"}）· 金额为原生币种 · 仅客观数据，不含买卖建议。
          </p>
        </>
      )}

      {val && (
        <>
          {sourceNotice("val")}
          <GlassCard glow className="mb-4">
            <div className="mb-4 flex items-baseline gap-2">
              <h2 className="text-xl font-bold">{val.name}</h2>
              <span className="font-mono text-sm text-muted-foreground">{val.code}</span>
              {val.analyst_count > 0 && (
                <span className="ml-auto text-xs text-muted-foreground">机构覆盖 {val.analyst_count} 家</span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {metrics.map((m) => (
                <div key={m.k} className="rounded-lg bg-muted/30 p-3">
                  <p className="text-xs text-muted-foreground">{m.k}</p>
                  <p className="mt-0.5 font-mono text-lg font-bold">{m.v}</p>
                </div>
              ))}
            </div>
            {val.forecast_note && (
              <p className="mt-3 text-xs text-warning">{val.forecast_note}</p>
            )}
          </GlassCard>

          {/* 财报速览（结论先行摘要，借鉴 equity-research 的结构纪律，剔除评级/目标价） */}
          {sourceNotice("fin", "pctl")}
          <EarningsSnapshot val={val} fin={fin} pctl={pctl} />
        </>
      )}
      {researchPanels}

      {selectedMarket === "CN" && activeCode && (
        <>
          {sourceNotice("pctl")}

          {pctl && (pctl.metrics.pe_ttm || pctl.metrics.pb) && (
            <GlassCard glow className="mb-4">
              <h3 className="mb-1 flex items-center gap-1.5 text-sm font-semibold"><LineChart className="h-4 w-4 text-primary" /> 估值历史分位 · {pctl.period}</h3>
              <p className="mb-4 text-[11px] text-muted-foreground/60">绿=低估区 / 灰=合理区 / 红=高估区。只显示当前处于历史什么位置，不构成买卖建议。</p>
              <div className="space-y-4">
                {pctl.metrics.pe_ttm && <ValBand label="PE-TTM" m={pctl.metrics.pe_ttm} />}
                {pctl.metrics.pb && <ValBand label="市净率 PB" m={pctl.metrics.pb} />}
              </div>
            </GlassCard>
          )}

          {sourceNotice("fin")}
          {fin && hasSourceData("fin", fin) && (
            <GlassCard className="mb-4">
              <h3 className="mb-1 flex items-center gap-1.5 text-sm font-semibold"><BarChart3 className="h-4 w-4 text-primary" /> 财务关键指标{fin.period && <span className="text-xs font-normal text-muted-foreground/60">· {fin.period}</span>}</h3>
              <p className="mb-3 text-[11px] text-muted-foreground/60">同花顺财务摘要,最新报告期。</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  { k: "营业总收入", v: fin.revenue, yoy: fin.revenue_yoy },
                  { k: "归母净利润", v: fin.net_profit, yoy: fin.net_profit_yoy },
                  { k: "每股收益", v: fin.eps },
                  { k: "ROE", v: fin.roe },
                  { k: "销售毛利率", v: fin.gross_margin },
                  { k: "销售净利率", v: fin.net_margin },
                  { k: "每股净资产", v: fin.bvps },
                  { k: "每股经营现金流", v: fin.op_cf_ps },
                ].map((m) => (
                  <div key={m.k} className="rounded-lg bg-muted/30 p-3">
                    <p className="text-xs text-muted-foreground">{m.k}</p>
                    <p className="mt-0.5 font-mono text-base font-bold">{m.v ?? "—"}</p>
                    {m.yoy && <p className="text-[11px] text-muted-foreground">同比 {m.yoy}</p>}
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {sourceNotice("reports")}
          {reports.length > 0 && (
            <GlassCard className="mb-4">
              <h3 className="mb-3 flex items-center gap-1.5 text-sm font-semibold"><FileText className="h-4 w-4 text-primary" /> 近期研报（{reports.length}）</h3>
              <div className="space-y-2">
                {reports.slice(0, 12).map((r, i) => (
                  <div key={i} className="flex items-center gap-3 border-b border-border/40 pb-2 text-sm last:border-0">
                    <span className="w-20 shrink-0 font-mono text-xs text-muted-foreground">{(r.publishDate || "").slice(0, 10)}</span>
                    <span className="w-24 shrink-0 truncate text-xs text-muted-foreground">{r.orgSName}</span>
                    {r.pdfUrl ? (
                      <a href={r.pdfUrl} target="_blank" rel="noreferrer" className="flex-1 truncate hover:text-primary">{r.title}</a>
                    ) : (
                      <span className="flex-1 truncate">{r.title}</span>
                    )}
                    {r.emRatingName && <span className="shrink-0 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">{r.emRatingName}</span>}
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {sourceNotice("anns")}
          {anns.length > 0 && (
            <GlassCard className="mb-4">
              <h3 className="mb-3 flex items-center gap-1.5 text-sm font-semibold"><Megaphone className="h-4 w-4 text-primary" /> 近期公告（{anns.length}）</h3>
              <div className="space-y-2">
                {anns.slice(0, 12).map((a, i) => (
                  <div key={i} className="flex items-center gap-3 border-b border-border/40 pb-2 text-sm last:border-0">
                    <span className="w-20 shrink-0 font-mono text-xs text-muted-foreground">{a.date}</span>
                    {a.type && <span className="w-24 shrink-0 truncate text-xs text-muted-foreground">{a.type}</span>}
                    {a.url ? (
                      <a href={a.url} target="_blank" rel="noreferrer" className="flex-1 truncate hover:text-primary">{a.title.replace(/^[^:：]*[:：]/, "")}</a>
                    ) : (
                      <span className="flex-1 truncate">{a.title}</span>
                    )}
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          <GlassCard className="mb-4">
            <h3 className="mb-3 flex items-center gap-1.5 text-sm font-semibold"><Newspaper className="h-4 w-4 text-primary" /> 个股新闻</h3>
            {sourceNotice("news")}
            {news.length === 0 ? (
              <p className="text-xs text-muted-foreground">{sourceStates.news?.status === "failed" ? sourceStates.news.error : sourceStatusText(sourceStates.news)}</p>
            ) : (
              <div className="space-y-2">
                {news.slice(0, 10).map((n, i) => (
                  <div key={i} className="flex items-center gap-3 border-b border-border/40 pb-2 text-sm last:border-0">
                    <span className="w-28 shrink-0 font-mono text-xs text-muted-foreground">{(n.发布时间 || "").slice(0, 16)}</span>
                    {n.新闻链接 ? (
                      <a href={n.新闻链接} target="_blank" rel="noreferrer" className="flex-1 truncate hover:text-primary">{n.新闻标题}</a>
                    ) : (
                      <span className="flex-1 truncate">{n.新闻标题}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </GlassCard>

          {/* 资金面 · 筹码（融资融券 / 股东户数 / 主力资金流 / 分红 / 大宗交易） */}
          {sourceNotice("margin", "holders", "fundFlow", "dividend", "blockT")}
          {(margin.length > 0 || holders.length > 0 || fundFlow.length > 0 || dividend.length > 0 || blockT.length > 0) && (
            <GlassCard className="mb-4">
              <h3 className="mb-3 flex items-center gap-1.5 text-sm font-semibold"><Wallet className="h-4 w-4 text-primary" /> 资金面 · 筹码</h3>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {margin[0] && <Metric k="融资余额" v={yi(margin[0].rzye)} sub={margin[0].date} />}
                {margin[0] && <Metric k="融券余额" v={yi(margin[0].rqye)} />}
                {holders[0] && <Metric k="股东户数" v={holders[0].holder_num == null ? "—" : holders[0].holder_num.toLocaleString()} sub={`环比 ${pct(holders[0].change_ratio)} · 统计期 ${holders[0].date} · 披露 ${holders[0].published_at || "未知"}`} />}
                {fundFlow.length > 0 && <Metric k="最近20条日记录主力净额" v={yi(fundWindow.total)} sub={`${fundWindow.start || "—"} 至 ${fundWindow.end || "—"} · 有效 ${fundWindow.validCount}/20 条（返回 ${fundWindow.records} 条）${fundWindow.total == null ? " · 待核验" : ""}`} />}
                {dividend[0] && <Metric k={`最近分红方案 · ${dividend[0].plan || "进度未知"}`} v={`每10股派 ${fmt(dividend[0].bonus_rmb, " 元")}`} sub={`转增 ${fmt(dividend[0].transfer_ratio, " 股")} · 送 ${fmt(dividend[0].bonus_ratio, " 股")}；披露 ${dividend[0].published_at || "待核验"} · 除权 ${dividend[0].date || "未定"}；不代表现金已到账`} />}
              </div>
              {blockT.length > 0 && (
                <div className="mt-3 border-t border-border/40 pt-3">
                  <p className="mb-2 text-xs text-muted-foreground">近期大宗交易（{blockT.length}）</p>
                  <div className="space-y-1.5">
                    {blockT.slice(0, 5).map((b, i) => (
                      <div key={i} className="flex items-center gap-3 text-xs">
                        <span className="w-20 shrink-0 font-mono text-muted-foreground">{b.date}</span>
                        <span className="w-14 shrink-0">{round2(b.price, " 元")}</span>
                        <span className={cn("w-20 shrink-0", pctColor(b.premium_pct))}>折溢 {pct(b.premium_pct)}</span>
                        <span className="flex-1 truncate text-muted-foreground">买 {b.buyer} · 卖 {b.seller}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <p className="mt-3 text-[11px] text-muted-foreground/60">资金窗口按有记录日期去重，未核验交易日连续性；缺失不按零累计。资金/筹码数据不构成买卖建议。</p>
            </GlassCard>
          )}

          {/* 龙虎榜 */}
          {sourceNotice("dt")}
          {dt && dt.records.length > 0 && (
            <GlassCard className="mb-4">
              <h3 className="mb-3 flex items-center gap-1.5 text-sm font-semibold"><Trophy className="h-4 w-4 text-primary" /> 龙虎榜（近30日 {dt.records.length} 次）</h3>
              <div className="space-y-2">
                {dt.records.slice(0, 6).map((r, i) => (
                  <div key={i} className="flex items-center gap-3 border-b border-border/40 pb-2 text-sm last:border-0">
                    <span className="w-20 shrink-0 font-mono text-xs text-muted-foreground">{r.date}</span>
                    <span className="flex-1 truncate">{r.reason}</span>
                    <span className={cn("shrink-0 font-mono text-xs", r.net_buy >= 0 ? "text-danger" : "text-success")}>净买 {r.net_buy} 万</span>
                  </div>
                ))}
              </div>
              {(dt.seats.buy.length > 0 || dt.seats.sell.length > 0) && (
                <div className="mt-3 grid gap-4 border-t border-border/40 pt-3 sm:grid-cols-2">
                  <div>
                    <p className="mb-1.5 text-xs font-medium text-danger">买入席位 TOP</p>
                    {dt.seats.buy.map((s, i) => (
                      <div key={i} className="flex justify-between gap-2 text-xs text-muted-foreground"><span className="truncate">{s.name}</span><span className="shrink-0 font-mono">净{s.net}万</span></div>
                    ))}
                  </div>
                  <div>
                    <p className="mb-1.5 text-xs font-medium text-success">卖出席位 TOP</p>
                    {dt.seats.sell.map((s, i) => (
                      <div key={i} className="flex justify-between gap-2 text-xs text-muted-foreground"><span className="truncate">{s.name}</span><span className="shrink-0 font-mono">净{s.net}万</span></div>
                    ))}
                  </div>
                </div>
              )}
            </GlassCard>
          )}

          {/* 限售解禁 */}
          {sourceNotice("lockup")}
          {lockup && (lockup.upcoming.length > 0 || lockup.history.length > 0) && (
            <GlassCard className="mb-4">
              <h3 className="mb-3 flex items-center gap-1.5 text-sm font-semibold"><CalendarClock className="h-4 w-4 text-primary" /> 限售解禁</h3>
              {lockup.upcoming.length > 0 ? (
                <div className="mb-3 rounded-lg border border-warning/30 bg-warning/5 p-3">
                  <p className="mb-1.5 text-xs font-medium text-warning">当日及未来 90 天解禁计划（{lockup.upcoming.length}）</p>
                  {lockup.upcoming.slice(0, 4).map((h, i) => (
                    <div key={i} className="flex flex-wrap items-center gap-3 text-xs"><span className="w-20 shrink-0 font-mono text-muted-foreground">{h.date}</span><span className="flex-1 truncate">{h.type}</span><span className="text-muted-foreground">可流通 {round2(h.able_shares, " 万股")} · 占流通股本 {pct(h.ratio == null ? null : h.ratio * 100)}</span></div>
                  ))}
                </div>
              ) : (
                <p className="mb-2 text-xs text-muted-foreground/70">当前来源未返回当日及未来90天记录，不代表已排除所有解禁风险。</p>
              )}
              {lockup.history.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs text-muted-foreground">历史解禁（近 {Math.min(lockup.history.length, 5)}）</p>
                  {lockup.history.slice(0, 5).map((h, i) => (
                    <div key={i} className="flex flex-wrap items-center gap-3 text-xs"><span className="w-20 shrink-0 font-mono text-muted-foreground">{h.date}</span><span className="flex-1 truncate text-muted-foreground">{h.type}</span><span className="text-muted-foreground">可流通 {round2(h.able_shares, " 万股")} · 占流通股本 {pct(h.ratio == null ? null : h.ratio * 100)}</span></div>
                  ))}
                </div>
              )}
              <p className="mt-2 text-xs text-muted-foreground">当前来源披露日未核验；解禁不代表实际减持。</p>
            </GlassCard>
          )}

          {/* 板块归属 · 概念 */}
          {sourceNotice("blocks", "hotCon")}
          {((blocks && blocks.concept_tags.length > 0) || hotCon.length > 0) && (
            <GlassCard className="mb-4">
              <h3 className="mb-3 flex items-center gap-1.5 text-sm font-semibold"><Boxes className="h-4 w-4 text-primary" /> 板块归属 · 概念</h3>
              {blocks && blocks.concept_tags.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-1.5">
                  {blocks.concept_tags.slice(0, 24).map((t, i) => (
                    <span key={i} className="rounded-full border border-border/70 px-2 py-0.5 text-xs text-muted-foreground">{t}</span>
                  ))}
                </div>
              )}
              {hotCon.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs text-muted-foreground">当下热门概念命中</p>
                  <div className="flex flex-wrap gap-1.5">
                    {hotCon.slice(0, 12).map((h, i) => (
                      <span key={i} className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{h.concept}</span>
                    ))}
                  </div>
                </div>
              )}
            </GlassCard>
          )}

          {/* 投资者互动（互动易） */}
          {sourceNotice("qa")}
          {qa.filter((q) => q.answer).length > 0 && (
            <GlassCard className="mb-4">
              <h3 className="mb-3 flex items-center gap-1.5 text-sm font-semibold"><MessageSquare className="h-4 w-4 text-primary" /> 投资者互动（互动易）</h3>
              <div className="space-y-3">
                {qa.filter((q) => q.answer).slice(0, 5).map((q, i) => (
                  <div key={i} className="border-b border-border/40 pb-3 text-sm last:border-0">
                    <p className="text-muted-foreground"><span className="mr-1.5 rounded bg-muted/50 px-1.5 py-0.5 text-[10px]">问</span>{q.question}</p>
                    <p className="mt-1"><span className="mr-1.5 rounded bg-primary/15 px-1.5 py-0.5 text-[10px] text-primary">答</span>{q.answer}</p>
                    <p className="mt-1 text-[11px] text-muted-foreground/60">{q.ask_time}</p>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}
        </>
      )}

      {!activeCode && !err && (
        <GlassCard>
          <div className="py-10 text-center text-sm text-muted-foreground">
            输入一个 6 位股票代码，拉取它的行情、估值、研报与新闻。<br />
            <span className="text-xs text-muted-foreground/60">数据来自公开源（腾讯行情 / 东财研报 / akshare）；Newma-Trading 不预置任何标的、不做推荐。</span>
          </div>
        </GlassCard>
      )}

      <Disclaimer />
    </div>
  );
}
