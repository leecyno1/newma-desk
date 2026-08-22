import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  ModPageContext,
  PortfolioResearchCoverage,
  PortfolioResearchPosition,
  ResearchArchiveEntry,
} from "@newma-desk/contracts";
import {
  connectModHost,
  createModBridge,
  createModSnapshotCache,
  type ModHostConnection,
} from "@newma-desk/mod-sdk";

import { portfolioClient, type ActivityInput, type PortfolioIdentity } from "./api";
import {
  Activity,
  BadgeDollarSign,
  Banknote,
  ChartPie,
  CircleDollarSign,
  Gauge,
  Landmark,
  Layers3,
  LoaderCircle,
  NotebookTabs,
  Plus,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Trash2,
  WalletCards,
} from "./icons";
import type {
  ActivityType,
  Market,
  PortfolioDashboard,
  PortfolioOptimizationInput,
  PortfolioOptimizationObjective,
  PortfolioOptimizationResult,
  PortfolioPerformanceInput,
  PortfolioPerformanceResult,
  PortfolioPosition,
  PortfolioWorkspace,
} from "./types";

const WORKSPACES: Record<PortfolioWorkspace, { title: string; eyebrow: string; subtitle: string }> = {
  "portfolio-brief": {
    title: "组合资产中心",
    eyebrow: "PORTFOLIO LEDGER",
    subtitle: "把账户、交易、持仓和风险放在同一套可追溯账本里。",
  },
  "portfolio-activities": {
    title: "交易流水",
    eyebrow: "ACTIVITY JOURNAL",
    subtitle: "买卖、现金、分红与费用共同驱动持仓，不再手工维护结果。",
  },
  "portfolio-risk": {
    title: "组合风控",
    eyebrow: "RISK TOPOLOGY",
    subtitle: "先识别集中度、市场与币种暴露，再进入优化和压力测试。",
  },
  "portfolio-allocation": {
    title: "资产配置",
    eyebrow: "ALLOCATION STUDIO",
    subtitle: "以统一历史行情为依据，对当前持仓生成可解释、可约束的目标权重。",
  },
  "portfolio-scenarios": {
    title: "情景推演",
    eyebrow: "SCENARIO ANALYSIS",
    subtitle: "观察增长、通胀、流动性和风险冲击下的组合变化。",
  },
  "portfolio-performance": {
    title: "绩效归因",
    eyebrow: "PERFORMANCE LEDGER",
    subtitle: "按币种拆分已实现、未实现收益、现金收入与费用。",
  },
  "portfolio-settings": {
    title: "组合设置",
    eyebrow: "PORTFOLIO CONTROL",
    subtitle: "管理账户、旧持仓迁移和组合数据状态。",
  },
};

const ACTIVITY_LABELS: Record<ActivityType, string> = {
  buy: "买入",
  sell: "卖出",
  dividend: "分红",
  interest: "利息",
  fee: "费用",
  deposit: "入金",
  withdrawal: "出金",
  split: "拆并股",
};

type TradingSubview = "overview" | "entry" | "ledger" | "positions" | "cash" | "execution" | "reconciliation";
type RiskSubview = "overview" | "concentration" | "exposure" | "drawdown" | "liquidity" | "stress" | "alerts";

const TRADING_TABS: Array<{ id: TradingSubview; label: string }> = [
  { id: "overview", label: "总览" },
  { id: "entry", label: "成交录入" },
  { id: "ledger", label: "成交明细" },
  { id: "positions", label: "持仓" },
  { id: "cash", label: "资金账户" },
  { id: "execution", label: "执行质量" },
  { id: "reconciliation", label: "对账异常" },
];

const RISK_TABS: Array<{ id: RiskSubview; label: string }> = [
  { id: "overview", label: "风险总览" },
  { id: "concentration", label: "集中度" },
  { id: "exposure", label: "市场 / 币种暴露" },
  { id: "drawdown", label: "回撤与 VaR" },
  { id: "liquidity", label: "流动性" },
  { id: "stress", label: "压力测试" },
  { id: "alerts", label: "预警规则" },
];

const OPTIMIZATION_LABELS: Record<PortfolioOptimizationObjective, { name: string; note: string }> = {
  "risk-balanced": { name: "风险均衡", note: "降低单一高波动资产对组合的支配。" },
  "minimum-volatility": { name: "最低波动", note: "寻找历史协方差下更平稳的权重组合。" },
  "return-seeking": { name: "收益增强", note: "按历史风险调整后收益分配权重。" },
};

type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;
type LinkedSecurity = {
  symbol: string;
  name: string;
  market: Market;
  currency?: string;
};

function workspaceFromSearch(): PortfolioWorkspace {
  const candidate = new URLSearchParams(window.location.search).get("workspace") as PortfolioWorkspace | null;
  return candidate && candidate in WORKSPACES ? candidate : "portfolio-brief";
}

function subviewFromSearch(workspace: PortfolioWorkspace): TradingSubview | RiskSubview {
  const candidate = new URLSearchParams(window.location.search).get("view");
  if (workspace === "portfolio-activities" && TRADING_TABS.some((item) => item.id === candidate)) return candidate as TradingSubview;
  if (workspace === "portfolio-risk" && RISK_TABS.some((item) => item.id === candidate)) return candidate as RiskSubview;
  return "overview";
}

function activityNotional(activity: PortfolioDashboard["activities"][number]) {
  if (activity.type === "buy" || activity.type === "sell") {
    return Math.abs(Number(activity.quantity || 0) * Number(activity.unitPrice || 0));
  }
  return Math.abs(Number(activity.amount || 0));
}

function localDateKey(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function localDateTimeInputValue() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

type ReconciliationIssue = {
  id: string;
  severity: "high" | "medium" | "low";
  title: string;
  detail: string;
  activityId?: string;
};

function reconciliationIssues(dashboard: PortfolioDashboard): ReconciliationIssue[] {
  const accountIds = new Set(dashboard.accounts.map((account) => account.id));
  const issues: ReconciliationIssue[] = [];
  dashboard.activities.forEach((activity) => {
    const notional = activityNotional(activity);
    if (!accountIds.has(activity.accountId)) issues.push({ id: `${activity.id}:account`, severity: "high", title: "账户不存在", detail: `${activity.accountId} 不在当前账户清单中`, activityId: activity.id });
    if (["buy", "sell", "dividend", "split"].includes(activity.type) && (!activity.market || !activity.symbol)) issues.push({ id: `${activity.id}:security`, severity: "high", title: "证券信息不完整", detail: `${ACTIVITY_LABELS[activity.type]}缺少市场或代码`, activityId: activity.id });
    if (["buy", "sell"].includes(activity.type) && (!activity.quantity || !activity.unitPrice)) issues.push({ id: `${activity.id}:trade`, severity: "high", title: "成交要素不完整", detail: "买卖流水缺少数量或成交价", activityId: activity.id });
    if (activity.fee > notional && notional > 0) issues.push({ id: `${activity.id}:fee`, severity: "high", title: "费用高于成交额", detail: `${activity.currency} ${number(activity.fee)} / 成交额 ${number(notional)}`, activityId: activity.id });
    if (["buy", "sell"].includes(activity.type) && !activity.name) issues.push({ id: `${activity.id}:name`, severity: "low", title: "标的名称缺失", detail: `${activity.market}:${activity.symbol} 仅保存了代码`, activityId: activity.id });
  });
  dashboard.positions.filter((position) => position.price == null).forEach((position) => issues.push({ id: `quote:${position.accountId}:${position.market}:${position.symbol}`, severity: "medium", title: "持仓缺少行情", detail: `${position.name}（${position.symbol}）当前使用成本口径` }));
  dashboard.currencies.filter((item) => item.cash < -0.01).forEach((item) => issues.push({
    id: `cash:${item.currency}`,
    severity: "high",
    title: "现金余额为负",
    detail: `${item.currency} ${number(item.cash)}；若不是融资账户，应补录入金或核对历史成交。`,
  }));
  if (dashboard.currencies.length > 1) issues.push({ id: "portfolio:fx", severity: "medium", title: "跨币种尚未统一折算", detail: "组合集中度不能把 CNY、HKD、USD 名义金额直接相加，需接入汇率快照。" });
  return issues;
}

function riskAlertRules(dashboard: PortfolioDashboard) {
  const concentration = dashboard.analytics.concentration;
  const issues = reconciliationIssues(dashboard);
  const cashDeficits = dashboard.currencies.filter((item) => item.cash < -0.01);
  const otherHighIssues = issues.filter((item) => item.severity === "high" && !item.id.startsWith("cash:"));
  return [
    { id: "single", label: "单一持仓超过 30%", hit: concentration.topPositionWeight > 30, value: `${number(concentration.topPositionWeight)}%` },
    { id: "top3", label: "前三持仓超过 65%", hit: concentration.topThreeWeight > 65, value: `${number(concentration.topThreeWeight)}%` },
    { id: "count", label: "有效持仓数低于 5", hit: concentration.positionCount > 0 && concentration.effectivePositionCount < 5, value: number(concentration.effectivePositionCount) },
    { id: "quote", label: "存在成本口径持仓", hit: dashboard.positions.some((item) => item.price == null), value: `${dashboard.positions.filter((item) => item.price == null).length} 只` },
    { id: "fx", label: "跨币种未统一折算", hit: dashboard.currencies.length > 1, value: `${dashboard.currencies.length} 个币种` },
    { id: "cash", label: "现金余额为负", hit: cashDeficits.length > 0, value: cashDeficits.map((item) => `${item.currency} ${number(item.cash)}`).join(" / ") || "正常" },
    { id: "ledger", label: "其他高优先级账本异常", hit: otherHighIssues.length > 0, value: `${otherHighIssues.length} 项` },
  ];
}

function parentOrigin() {
  const configured = import.meta.env.VITE_PARENT_ORIGIN?.trim();
  if (configured) return configured;
  if (document.referrer) {
    try { return new URL(document.referrer).origin; } catch { /* ignore */ }
  }
  return "http://127.0.0.1:5888";
}

function number(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: digits }).format(value);
}

function signed(value: number | null | undefined, suffix = "") {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${number(value)}${suffix}`;
}

function formatDate(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-CN", { hour12: false });
}

function pnlClass(value: number | null | undefined) {
  return value && value > 0 ? "positive" : value && value < 0 ? "negative" : "neutral";
}

function workspaceBlocks(workspace: PortfolioWorkspace) {
  const shared = [{ id: "portfolio-header", type: "portfolio-summary", title: "组合账本状态" }];
  if (workspace === "portfolio-activities") return [...shared, { id: "activity-ledger", type: "portfolio-activities", title: "交易流水" }];
  if (workspace === "portfolio-risk") return [...shared, { id: "risk-map", type: "portfolio-risk", title: "集中度与暴露" }];
  if (workspace === "portfolio-allocation") return [...shared, { id: "allocation-studio", type: "portfolio-allocation", title: "资产配置与组合优化" }];
  if (workspace === "portfolio-performance") return [...shared, { id: "performance-ledger", type: "portfolio-performance", title: "绩效归因" }];
  if (workspace === "portfolio-settings") return [...shared, { id: "portfolio-settings", type: "settings", title: "账户与迁移" }];
  return [
    ...shared,
    { id: "portfolio-positions", type: "portfolio", title: "持仓与配置" },
    { id: "portfolio-research-coverage", type: "research-coverage", title: "持仓研究覆盖" },
  ];
}

function buildContext(
  workspace: PortfolioWorkspace,
  subview?: TradingSubview | RiskSubview,
  dashboard?: PortfolioDashboard,
  selected?: PortfolioPosition,
  linkedSecurity?: LinkedSecurity,
  optimization?: PortfolioOptimizationResult,
  performance?: PortfolioPerformanceResult,
  researchCoverage?: PortfolioResearchCoverage,
): ModPageContext {
  const config = WORKSPACES[workspace];
  const activeSecurity = selected || linkedSecurity;
  const selectedResearch = activeSecurity
    ? researchCoverage?.positions.find((item) =>
      item.market === activeSecurity.market &&
      item.symbol.toUpperCase() === activeSecurity.symbol.toUpperCase()
    )
    : undefined;
  return {
    view: { id: workspace, title: config.title },
    visibleBlocks: workspaceBlocks(workspace),
    selection: activeSecurity ? {
      symbol: activeSecurity.symbol,
      name: activeSecurity.name,
      market: activeSecurity.market,
      ...(activeSecurity.currency ? { currency: activeSecurity.currency } : {}),
      ...(selected ? { accountId: selected.accountId } : {}),
    } : {},
    filters: {
      workspace,
      ...(subview ? { subview } : {}),
      valuation: dashboard?.valuationStatus || "unknown",
      ...(optimization ? {
        optimizationObjective: optimization.objective,
        optimizationCurrency: optimization.currency,
      } : {}),
    },
    data: {
      asOf: dashboard?.updatedAt,
      source: "newma-desk-portfolio-ledger",
      freshness: dashboard ? (dashboard.valuationStatus === "live" ? "live" : "fresh") : "unknown",
      summary: dashboard ? {
        accountCount: dashboard.accounts.length,
        activityCount: dashboard.activities.length,
        positionCount: dashboard.positions.length,
        currencies: dashboard.currencies,
        concentration: dashboard.analytics.concentration,
        allocations: {
          byMarket: dashboard.analytics.byMarket,
          byCurrency: dashboard.analytics.byCurrency,
          byAccount: dashboard.analytics.byAccount,
        },
        selectedPosition: selected || {},
        linkedSecurity: linkedSecurity || {},
        optimization: optimization || {},
        historicalPerformance: performance || {},
        portfolioResearchCoverage: researchCoverage ? {
          schemaVersion: researchCoverage.schemaVersion,
          generatedAt: researchCoverage.generatedAt,
          summary: researchCoverage.summary,
          selectedPosition: selectedResearch || {},
          note: "组合研究覆盖只包含研究档案引用与派生缺口，不复制研究正文，也不构成持仓建议。",
        } : {},
      } : {},
    },
    actions: [
      { id: "portfolio.refresh", label: "刷新组合", available: true },
      { id: "portfolio.optimize", label: "生成资产配置方案", available: workspace === "portfolio-allocation" },
      { id: "portfolio.analyze-performance", label: "分析历史绩效", available: workspace === "portfolio-performance" },
      { id: "portfolio.import-legacy", label: "导入旧持仓", available: workspace === "portfolio-settings" },
    ],
    tasks: [],
  };
}

const RESEARCH_KIND_LABELS: Record<ResearchArchiveEntry["kind"], string> = {
  "uploaded-report": "上传研报",
  "research-record": "研究记录",
  thesis: "投资逻辑",
  earnings: "财报",
  "peer-comparison": "同业",
  valuation: "估值",
  "research-memo": "备忘录",
};

const COVERAGE_LABELS: Record<PortfolioResearchPosition["status"], string> = {
  complete: "覆盖完整",
  partial: "部分覆盖",
  missing: "尚未覆盖",
};

const MISSING_LABELS: Record<PortfolioResearchPosition["missingGroups"][number], string> = {
  "core-thesis-or-memo": "缺投资逻辑或研究备忘录",
  "supporting-analysis": "缺财报、同业或估值支持",
};

const ATTENTION_LABELS: Record<PortfolioResearchPosition["attentionReasons"][number], string> = {
  "review-overdue": "逻辑复核已到期",
  "stale-core-research": "核心备忘录待更新",
  "invalidated-thesis": "存在已证伪逻辑",
};

function researchSourceUrl(reference: ResearchArchiveEntry) {
  return `${parentOrigin()}/?mod=${encodeURIComponent(reference.sourceModId)}`;
}

function ResearchCoveragePanel({
  coverage,
  loading,
  selected,
  onSelect,
}: {
  coverage?: PortfolioResearchCoverage;
  loading: boolean;
  selected?: PortfolioPosition;
  onSelect(position: PortfolioResearchPosition): void;
}) {
  if (!coverage) return <section className="folio-panel research-coverage-panel">
    <div className="panel-title"><div><span>RESEARCH COVERAGE</span><h2>持仓研究覆盖</h2></div><NotebookTabs size={18} /></div>
    <div className="empty-copy">{loading ? "正在核对研究档案…" : "研究档案索引暂时不可用，持仓账本不受影响。"}</div>
  </section>;
  const selectedCoverage = selected
    ? coverage.positions.find((item) =>
      item.market === selected.market && item.symbol === selected.symbol
    )
    : undefined;
  return <section className="folio-panel research-coverage-panel">
    <div className="panel-title">
      <div><span>RESEARCH COVERAGE</span><h2>持仓研究覆盖</h2></div>
      <div className="coverage-summary" aria-label="研究覆盖摘要">
        <span><b>{coverage.summary.completeCount}</b>完整</span>
        <span><b>{coverage.summary.partialCount}</b>部分</span>
        <span><b>{coverage.summary.missingCount}</b>缺失</span>
        {coverage.summary.attentionCount > 0 && <span className="attention"><b>{coverage.summary.attentionCount}</b>需关注</span>}
      </div>
    </div>
    {coverage.positions.length === 0 ? <div className="empty-copy">当前没有持仓，建立持仓后自动核对研究档案。</div> : <div className="research-coverage-list">
      {coverage.positions.map((item) => {
        const focused = selectedCoverage?.market === item.market && selectedCoverage.symbol === item.symbol;
        return <article className={focused ? "selected" : ""} key={`${item.market}:${item.symbol}`} onClick={() => onSelect(item)}>
          <div className="coverage-position">
            <span>{item.market}</span>
            <div><strong>{item.name}</strong><small>{item.symbol} · {item.accountIds.join(" / ")}</small></div>
          </div>
          <div className={`coverage-state state-${item.status}`}><i />{COVERAGE_LABELS[item.status]}</div>
          <div className="coverage-references">
            {item.references.length === 0 ? <span className="coverage-gap">{item.missingGroups.map((gap) => MISSING_LABELS[gap]).join("；")}</span> : item.references.slice(0, 6).map((reference) => (
              <a key={reference.id} href={researchSourceUrl(reference)} target="_top" onClick={(event) => event.stopPropagation()} title={reference.title}>
                {RESEARCH_KIND_LABELS[reference.kind]}
              </a>
            ))}
          </div>
          <div className="coverage-meta">
            <span>{item.activeReferenceCount} 份有效引用</span>
            {item.latestUpdatedAt && <span>更新 {new Date(item.latestUpdatedAt).toLocaleDateString("zh-CN")}</span>}
            {item.attentionReasons.map((reason) => <b key={reason}>{ATTENTION_LABELS[reason]}</b>)}
          </div>
        </article>;
      })}
    </div>}
    <p className="method-note">覆盖表示研究档案是否齐备，只检查引用、状态与复核日期，不读取正文、不评判持仓。</p>
  </section>;
}

function CurrencyCards({ dashboard }: { dashboard: PortfolioDashboard }) {
  return <div className="currency-grid">
    {dashboard.currencies.length === 0 ? <div className="empty-panel">暂无资产流水</div> : dashboard.currencies.map((item) => (
      <article className="currency-card" key={item.currency}>
        <div className="currency-card-head"><span>{item.currency}</span><CircleDollarSign size={17} /></div>
        <strong>{number(item.marketValue ?? item.costValue)}</strong>
        <small>{item.marketValue == null ? "成本口径" : "当前市值"}</small>
        <div className="currency-card-foot">
          <span className={pnlClass(item.unrealizedPnl)}>浮动 {signed(item.unrealizedPnl)}</span>
          <span>现金 {number(item.cash)}</span>
        </div>
      </article>
    ))}
  </div>;
}

function AllocationBars({ title, items }: { title: string; items: PortfolioDashboard["analytics"]["byMarket"] }) {
  return <section className="folio-panel allocation-panel">
    <div className="panel-title"><div><span>EXPOSURE</span><h2>{title}</h2></div><Layers3 size={18} /></div>
    <div className="allocation-list">
      {items.length === 0 ? <div className="empty-copy">录入交易后显示资产暴露</div> : items.map((item) => (
        <div className="allocation-row" key={`${item.currency}:${item.key}`}>
          <div><strong>{item.label}</strong><span>{item.currency} · {number(item.value)}</span></div>
          <div className="allocation-track"><i style={{ width: `${Math.max(2, item.weight)}%` }} /></div>
          <b>{number(item.weight)}%</b>
        </div>
      ))}
    </div>
  </section>;
}

function PositionsTable({
  dashboard,
  selected,
  onSelect,
}: {
  dashboard: PortfolioDashboard;
  selected?: PortfolioPosition;
  onSelect(position: PortfolioPosition): void;
}) {
  return <section className="folio-panel positions-panel">
    <div className="panel-title"><div><span>LIVE POSITIONS</span><h2>当前持仓</h2></div><WalletCards size={18} /></div>
    {dashboard.positions.length === 0 ? <div className="empty-copy tall">还没有持仓。前往“交易流水”录入第一笔买入。</div> : (
      <div className="table-scroll"><table>
        <thead><tr><th>标的</th><th>数量</th><th>成本</th><th>现价</th><th>市值</th><th>浮动盈亏</th></tr></thead>
        <tbody>{dashboard.positions.map((position) => (
          <tr key={`${position.accountId}:${position.market}:${position.symbol}`} className={selected === position ? "selected" : ""} onClick={() => onSelect(position)}>
            <td><div className="security-cell"><span>{position.market}</span><div><strong>{position.name}</strong><small>{position.symbol} · {position.currency}</small></div></div></td>
            <td>{number(position.quantity, 6)}</td>
            <td>{number(position.averageCost, 6)}</td>
            <td>{number(position.price, 6)}</td>
            <td>{number(position.marketValue ?? position.costValue)}</td>
            <td className={pnlClass(position.unrealizedPnl)}>{signed(position.unrealizedPnl)}<small>{signed(position.unrealizedPnlPct, "%")}</small></td>
          </tr>
        ))}</tbody>
      </table></div>
    )}
  </section>;
}

function ActivityForm({ dashboard, onCreated }: { dashboard: PortfolioDashboard; onCreated(): void }) {
  const [type, setType] = useState<ActivityType>("buy");
  const [market, setMarket] = useState<Market>("CN");
  const [accountId, setAccountId] = useState(dashboard.accounts[0]?.id || "main");
  const [symbol, setSymbol] = useState("");
  const [name, setName] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unitPrice, setUnitPrice] = useState("");
  const [amount, setAmount] = useState("");
  const [fee, setFee] = useState("");
  const [currency, setCurrency] = useState("CNY");
  const [occurredAt, setOccurredAt] = useState(localDateTimeInputValue);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const identity = { userId: dashboard.userId, workspaceId: dashboard.workspaceId };
  const securityActivity = ["buy", "sell", "split", "dividend"].includes(type);
  const tradeActivity = type === "buy" || type === "sell";
  const estimatedNotional = tradeActivity ? Number(quantity || 0) * Number(unitPrice || 0) : Number(amount || 0);

  const submit = async () => {
    setSaving(true); setError("");
    try {
      const occurredDate = new Date(occurredAt);
      if (!dashboard.accounts.some((account) => account.id === accountId)) throw new Error("请先创建可用交易账户");
      if (!occurredAt || Number.isNaN(occurredDate.getTime())) throw new Error("请输入有效发生时间");
      if (securityActivity && !symbol.trim()) throw new Error("请输入证券代码");
      if ((tradeActivity || type === "split") && Number(quantity) <= 0) throw new Error(type === "split" ? "请输入有效拆并比例" : "请输入有效成交数量");
      if (tradeActivity && Number(unitPrice) <= 0) throw new Error("请输入有效成交价");
      if (Number(fee || 0) < 0) throw new Error("费用不能为负数");
      if (!tradeActivity && type !== "split" && (!Number.isFinite(Number(amount)) || Number(amount) <= 0)) throw new Error("请输入大于 0 的金额");
      if (!currency.trim()) throw new Error("请输入币种");
      const input: ActivityInput = {
        accountId,
        type,
        currency,
        occurredAt: occurredDate.toISOString(),
        ...(securityActivity ? { market, symbol: symbol.trim().toUpperCase(), ...(name.trim() ? { name: name.trim() } : {}) } : {}),
        ...(tradeActivity || type === "split" ? { quantity: Number(quantity) } : {}),
        ...(tradeActivity ? { unitPrice: Number(unitPrice), fee: Number(fee || 0) } : {}),
        ...(!tradeActivity && type !== "split" ? { amount: Number(amount) } : {}),
        ...(note.trim() ? { note: note.trim() } : {}),
      };
      await portfolioClient(identity).createActivity(input);
      setSymbol(""); setName(""); setQuantity(""); setUnitPrice(""); setAmount(""); setFee(""); setNote(""); setOccurredAt(localDateTimeInputValue());
      onCreated();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally { setSaving(false); }
  };

  return <section className="folio-panel journal-form">
    <div className="panel-title"><div><span>TRADE CAPTURE</span><h2>成交与资金录入</h2></div><Plus size={18} /></div>
    <div className="form-grid">
      <label><span>类型</span><select value={type} onChange={(event) => setType(event.target.value as ActivityType)}>{Object.entries(ACTIVITY_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label><span>账户</span><select value={accountId} onChange={(event) => setAccountId(event.target.value)}>{dashboard.accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
      <label><span>发生时间</span><input type="datetime-local" value={occurredAt} onChange={(event) => setOccurredAt(event.target.value)} /></label>
      {securityActivity && <label><span>市场</span><select value={market} onChange={(event) => { const next = event.target.value as Market; setMarket(next); setCurrency(next === "US" ? "USD" : next === "HK" ? "HKD" : "CNY"); }}><option>CN</option><option>HK</option><option>US</option></select></label>}
      {securityActivity && <label><span>标的</span><input value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="600519 / 00700 / AAPL" /></label>}
      {securityActivity && <label><span>标的名称</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="可选，便于对账" /></label>}
      {(tradeActivity || type === "split") && <label><span>{type === "split" ? "拆并比例" : "数量"}</span><input inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label>}
      {tradeActivity && <label><span>成交价</span><input inputMode="decimal" value={unitPrice} onChange={(event) => setUnitPrice(event.target.value)} /></label>}
      {tradeActivity && <label><span>费用</span><input inputMode="decimal" value={fee} onChange={(event) => setFee(event.target.value)} placeholder="0" /></label>}
      {!tradeActivity && type !== "split" && <label><span>金额</span><input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>}
      <label><span>币种</span><input value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} maxLength={12} /></label>
      <label className="form-wide"><span>备注 / 交易计划引用</span><input value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} placeholder="可记录计划编号、成交原因或券商回单号" /></label>
    </div>
    <div className="trade-entry-preview"><span>{tradeActivity ? "预计成交额" : "本次金额"}</span><strong>{currency} {number(estimatedNotional)}</strong><small>{tradeActivity ? `费用 ${number(Number(fee || 0))} · 合计 ${number(type === "buy" ? estimatedNotional + Number(fee || 0) : estimatedNotional - Number(fee || 0))}` : "写入后由账本派生现金与持仓"}</small></div>
    {error && <div className="inline-error">{error}</div>}
    <button className="primary-button" onClick={submit} disabled={saving || !dashboard.accounts.length}>{saving ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />}写入账本</button>
  </section>;
}

function ActivityLedger({ dashboard, onDeleted }: { dashboard: PortfolioDashboard; onDeleted(): void }) {
  const [typeFilter, setTypeFilter] = useState<"all" | ActivityType>("all");
  const [accountFilter, setAccountFilter] = useState("all");
  const [search, setSearch] = useState("");
  const remove = async (id: string) => {
    await portfolioClient({ userId: dashboard.userId, workspaceId: dashboard.workspaceId }).deleteActivity(id);
    onDeleted();
  };
  const rows = dashboard.activities.filter((item) => {
    if (typeFilter !== "all" && item.type !== typeFilter) return false;
    if (accountFilter !== "all" && item.accountId !== accountFilter) return false;
    const needle = search.trim().toLowerCase();
    return !needle || [item.symbol, item.name, item.note, item.accountId].some((value) => value?.toLowerCase().includes(needle));
  });
  return <section className="folio-panel ledger-panel">
    <div className="panel-title"><div><span>EXECUTION LEDGER</span><h2>成交与资金明细</h2></div><Activity size={18} /></div>
    <div className="ledger-filters">
      <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索代码、名称、备注或账户" />
      <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as "all" | ActivityType)}><option value="all">全部类型</option>{Object.entries(ACTIVITY_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
      <select value={accountFilter} onChange={(event) => setAccountFilter(event.target.value)}><option value="all">全部账户</option>{dashboard.accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select>
      <span>{rows.length} / {dashboard.activities.length} 笔</span>
    </div>
    {dashboard.activities.length === 0 ? <div className="empty-copy">账本是空的</div> : <div className="table-scroll ledger-table-wrap"><table className="ledger-table">
      <thead><tr><th>时间</th><th>类型</th><th>账户</th><th>标的 / 说明</th><th>数量</th><th>成交价</th><th>成交额</th><th>费用</th><th>来源</th><th /></tr></thead>
      <tbody>{rows.slice(0, 300).map((item) => <tr key={item.id}>
        <td>{formatDate(item.occurredAt)}</td>
        <td><span className={`ledger-type type-${item.type}`}>{ACTIVITY_LABELS[item.type]}</span></td>
        <td>{item.accountId}</td>
        <td><strong>{item.name || item.symbol || item.currency}</strong><small>{item.symbol ? `${item.market}:${item.symbol}` : item.note || "—"}</small></td>
        <td>{item.quantity == null ? "—" : number(item.quantity, 6)}</td>
        <td>{item.unitPrice == null ? "—" : number(item.unitPrice, 6)}</td>
        <td>{item.currency} {number(activityNotional(item))}</td>
        <td>{number(item.fee)}</td>
        <td>{item.source}</td>
        <td><button className="ghost-icon" onClick={() => void remove(item.id)} title="删除流水"><Trash2 size={14} /></button></td>
      </tr>)}</tbody>
    </table>{rows.length === 0 && <div className="empty-copy">当前筛选条件没有流水</div>}</div>}
  </section>;
}

function WorkspaceTabs({ items, value, onChange }: { items: Array<{ id: string; label: string }>; value: string; onChange(value: string): void }) {
  return <nav className="workspace-tabs" aria-label="工作台标签">{items.map((item) => <button key={item.id} className={value === item.id ? "active" : ""} onClick={() => onChange(item.id)}>{item.label}</button>)}</nav>;
}

function TradingOverview({ dashboard }: { dashboard: PortfolioDashboard }) {
  const today = localDateKey(new Date().toISOString());
  const todayRows = dashboard.activities.filter((item) => localDateKey(item.occurredAt) === today);
  const trades = dashboard.activities.filter((item) => item.type === "buy" || item.type === "sell");
  const issues = reconciliationIssues(dashboard);
  return <div className="workbench-stack">
    <section className="workbench-metrics">
      <article><span>今日流水</span><strong>{todayRows.length}</strong><small>买卖、现金与费用</small></article>
      <article><span>累计成交</span><strong>{trades.length}</strong><small>{dashboard.activities.length} 笔总流水</small></article>
      <article><span>当前持仓</span><strong>{dashboard.positions.length}</strong><small>{dashboard.accounts.length} 个账户</small></article>
      <article><span>待核对</span><strong className={issues.length ? "negative" : "positive"}>{issues.length}</strong><small>数据完整性与行情缺口</small></article>
    </section>
    <CurrencyCards dashboard={dashboard} />
    <section className="folio-panel">
      <div className="panel-title"><div><span>RECENT EXECUTIONS</span><h2>最近成交与资金动作</h2></div><Activity size={18} /></div>
      <div className="activity-list compact-activity-list">{dashboard.activities.slice(0, 8).map((item) => <article className="activity-row" key={item.id}>
        <div className={`activity-icon type-${item.type}`}>{item.type === "buy" || item.type === "deposit" ? "+" : "−"}</div>
        <div className="activity-main"><strong>{ACTIVITY_LABELS[item.type]} · {item.name || item.symbol || item.currency}</strong><span>{formatDate(item.occurredAt)} · {item.accountId}</span></div>
        <div className="activity-value"><strong>{item.currency} {number(activityNotional(item))}</strong><span>{item.source}</span></div>
      </article>)}</div>
      {!dashboard.activities.length && <div className="empty-copy">尚未录入成交或资金流水</div>}
    </section>
  </div>;
}

function TradeReadiness({ dashboard }: { dashboard: PortfolioDashboard }) {
  const cashDeficits = dashboard.currencies.filter((item) => item.cash < -0.01);
  return <section className="folio-panel trade-readiness">
    <div className="panel-title"><div><span>PRE-TRADE CHECK</span><h2>录入前检查</h2></div><ShieldCheck size={18} /></div>
    <dl>
      <div><dt>账户状态</dt><dd>{dashboard.accounts.length ? `${dashboard.accounts.length} 个可用` : "无可用账户"}</dd></div>
      <div><dt>估值口径</dt><dd>{dashboard.valuationStatus === "live" ? "实时行情" : dashboard.valuationStatus === "partial" ? "部分实时" : "成本口径"}</dd></div>
      <div><dt>账本规则</dt><dd>卖出不得超过持仓</dd></div>
      <div><dt>跨币种</dt><dd>{dashboard.currencies.length > 1 ? "分币种核算" : "单一币种"}</dd></div>
      <div><dt>现金状态</dt><dd>{cashDeficits.length ? cashDeficits.map((item) => `${item.currency} ${number(item.cash)} 待核对`).join(" / ") : "未发现负余额"}</dd></div>
    </dl>
    <div className="control-gap-list"><div><strong>尚未接入</strong><span>委托状态、订单编号、券商回单、到达价和成交基准价。</span></div><div><strong>当前保证</strong><span>每笔活动先通过账本校验，再派生现金、持仓与已实现盈亏。</span></div></div>
  </section>;
}

function CashAccountsView({ dashboard }: { dashboard: PortfolioDashboard }) {
  return <div className="workbench-stack"><CurrencyCards dashboard={dashboard} /><div className="content-grid">
    <section className="folio-panel"><div className="panel-title"><div><span>ACCOUNTS</span><h2>交易账户</h2></div><Landmark size={18} /></div><div className="account-list">{dashboard.accounts.map((account) => <article key={account.id}><div><strong>{account.name}</strong><span>{account.id} · {account.platform || account.accountType}</span></div><b>{account.currency}</b></article>)}</div></section>
    <section className="folio-panel"><div className="panel-title"><div><span>CASH MOVEMENT</span><h2>现金、收入与费用</h2></div><CircleDollarSign size={18} /></div><div className="cash-detail-list">{dashboard.currencies.map((item) => <article key={item.currency}><strong>{item.currency}</strong><span>现金 {number(item.cash)}</span><span>收入 {number(item.income)}</span><span>费用 {number(item.fees)}</span><span>已实现 {signed(item.realizedPnl)}</span></article>)}</div></section>
  </div></div>;
}

function ExecutionQualityView({ dashboard }: { dashboard: PortfolioDashboard }) {
  const trades = dashboard.activities.filter((item) => item.type === "buy" || item.type === "sell");
  const groups = new Map<string, { count: number; notional: number; fees: number; named: number; noted: number }>();
  trades.forEach((trade) => {
    const current = groups.get(trade.currency) || { count: 0, notional: 0, fees: 0, named: 0, noted: 0 };
    current.count += 1; current.notional += activityNotional(trade); current.fees += trade.fee; current.named += trade.name ? 1 : 0; current.noted += trade.note ? 1 : 0;
    groups.set(trade.currency, current);
  });
  return <div className="workbench-stack">
    <section className="folio-panel"><div className="panel-title"><div><span>EXECUTION QUALITY</span><h2>已具备的执行统计</h2></div><Gauge size={18} /></div><div className="execution-grid">{Array.from(groups.entries()).map(([currency, item]) => <article key={currency}><span>{currency}</span><strong>{item.count} 笔</strong><small>成交额 {number(item.notional)}</small><small>费用率 {item.notional ? number(item.fees / item.notional * 100, 4) : "—"}%</small><small>名称完整 {number(item.named / item.count * 100)}% · 备注 {number(item.noted / item.count * 100)}%</small></article>)}</div>{!groups.size && <div className="empty-copy">暂无买卖成交</div>}</section>
    <section className="folio-panel"><div className="panel-title"><div><span>DATA GAPS</span><h2>执行质量待接字段</h2></div><Settings2 size={18} /></div><div className="control-gap-list"><div><strong>成交偏差 / 滑点</strong><span>需要到达价、决策价或 VWAP 基准，目前不能凭成交价反推。</span></div><div><strong>成交率与撤单率</strong><span>需要原始委托量、成交量、撤单状态和订单生命周期。</span></div><div><strong>券商对账</strong><span>需要订单号、成交编号、券商回单和结算日期。</span></div></div></section>
  </div>;
}

function ReconciliationView({ dashboard }: { dashboard: PortfolioDashboard }) {
  const issues = reconciliationIssues(dashboard);
  return <section className="folio-panel reconciliation-panel"><div className="panel-title"><div><span>RECONCILIATION</span><h2>对账异常与数据缺口</h2></div><ShieldCheck size={18} /></div>
    <div className="reconciliation-summary"><strong>{issues.length}</strong><span>项待处理</span><small>{issues.filter((item) => item.severity === "high").length} 项高优先级</small></div>
    <div className="issue-list">{issues.map((issue) => <article key={issue.id} className={`severity-${issue.severity}`}><span>{issue.severity === "high" ? "高" : issue.severity === "medium" ? "中" : "低"}</span><div><strong>{issue.title}</strong><small>{issue.detail}</small></div>{issue.activityId && <code>{issue.activityId.slice(0, 8)}</code>}</article>)}</div>
    {!issues.length && <div className="empty-copy tall">当前账本未发现明显数据异常</div>}
  </section>;
}

function TradingWorkbench({ dashboard, view, onView, selected, onSelect, onRefresh }: { dashboard: PortfolioDashboard; view: TradingSubview; onView(view: TradingSubview): void; selected?: PortfolioPosition; onSelect(position: PortfolioPosition): void; onRefresh(): void }) {
  return <div className="workspace-shell"><WorkspaceTabs items={TRADING_TABS} value={view} onChange={(next) => onView(next as TradingSubview)} />
    {view === "overview" && <TradingOverview dashboard={dashboard} />}
    {view === "entry" && <div className="journal-grid"><ActivityForm dashboard={dashboard} onCreated={onRefresh} /><TradeReadiness dashboard={dashboard} /></div>}
    {view === "ledger" && <ActivityLedger dashboard={dashboard} onDeleted={onRefresh} />}
    {view === "positions" && <div className="workbench-stack"><PositionsTable dashboard={dashboard} selected={selected} onSelect={onSelect} /><div className="content-grid"><AllocationBars title="市场暴露" items={dashboard.analytics.byMarket} /><AllocationBars title="账户暴露" items={dashboard.analytics.byAccount} /></div></div>}
    {view === "cash" && <CashAccountsView dashboard={dashboard} />}
    {view === "execution" && <ExecutionQualityView dashboard={dashboard} />}
    {view === "reconciliation" && <ReconciliationView dashboard={dashboard} />}
  </div>;
}

function ConcentrationView({ dashboard }: { dashboard: PortfolioDashboard }) {
  const concentration = dashboard.analytics.concentration;
  const byCurrency = dashboard.currencies.map((currency) => {
    const positions = dashboard.positions.filter((position) => position.currency === currency.currency);
    const values = positions.map((position) => ({ position, value: Math.max(0, position.marketValue ?? position.costValue) }));
    const total = values.reduce((sum, item) => sum + item.value, 0);
    return { currency: currency.currency, rows: values.sort((a, b) => b.value - a.value).map((item) => ({ ...item.position, weight: total ? item.value / total * 100 : 0 })) };
  });
  return <div className="workbench-stack"><section className="folio-panel risk-hero"><div className="panel-title"><div><span>CONCENTRATION</span><h2>组合集中度</h2></div><Gauge size={18} /></div><div className="risk-score"><strong>{number(concentration.effectivePositionCount)}</strong><span>名义有效持仓数</span></div><div className="risk-stat-grid"><div><span>最大单一持仓</span><strong>{number(concentration.topPositionWeight)}%</strong></div><div><span>前三大持仓</span><strong>{number(concentration.topThreeWeight)}%</strong></div><div><span>HHI</span><strong>{number(concentration.herfindahlIndex, 6)}</strong></div><div><span>持仓数量</span><strong>{concentration.positionCount}</strong></div></div><p className="method-note">多币种组合的上方总值仅作名义提示；正式集中度以下方分币种权重为准，待汇率快照接入后再统一折算。</p></section>
    {byCurrency.map((group) => <section className="folio-panel" key={group.currency}><div className="panel-title"><div><span>{group.currency}</span><h2>分币种持仓权重</h2></div><span>{group.rows.length} 只</span></div><div className="allocation-list">{group.rows.map((item) => <div className="allocation-row" key={`${item.accountId}:${item.symbol}`}><div><strong>{item.name}</strong><span>{item.market}:{item.symbol}</span></div><div className="allocation-track"><i style={{ width: `${Math.max(2, item.weight)}%` }} /></div><b>{number(item.weight)}%</b></div>)}</div></section>)}
  </div>;
}

function RiskHistoryView({ dashboard, result, onResult }: { dashboard: PortfolioDashboard; result?: PortfolioPerformanceResult; onResult(result: PortfolioPerformanceResult): void }) {
  const currencies = Array.from(new Set(dashboard.positions.map((position) => position.currency)));
  const [currency, setCurrency] = useState(currencies[0] || "CNY");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const active = result?.currency === currency ? result : undefined;
  const run = async () => { setRunning(true); setError(""); try { onResult(await portfolioClient({ userId: dashboard.userId, workspaceId: dashboard.workspaceId }).analyzePerformance({ currency, lookbackWeeks: 156, riskFreeRatePct: 2 })); } catch (reason) { setError(reason instanceof Error ? reason.message : "风险历史分析不可用"); } finally { setRunning(false); } };
  return <div className="workbench-stack"><section className="folio-panel risk-analysis-control"><div className="panel-title"><div><span>HISTORICAL RISK</span><h2>回撤与尾部风险</h2></div><ChartPie size={18} /></div><div className="inline-controls"><label><span>分析币种</span><select value={currency} onChange={(event) => setCurrency(event.target.value)}>{currencies.length ? currencies.map((item) => <option key={item}>{item}</option>) : <option>CNY</option>}</select></label><button className="primary-button" onClick={() => void run()} disabled={running || !currencies.length}>{running ? <LoaderCircle className="spin" size={16} /> : <Gauge size={16} />}计算 3 年历史风险</button></div>{error && <div className="inline-error">{error}</div>}<p className="method-note">按当前持仓权重和周线历史计算；不同币种分别分析，不做无汇率依据的合并。</p></section>
    {active?.metrics ? <section className="workbench-metrics risk-history-metrics"><article><span>最大回撤</span><strong className="negative">{number(active.metrics.maxDrawdownPct)}%</strong><small>{active.metrics.maxDrawdownDurationWeeks} 周</small></article><article><span>95% VaR</span><strong>{number(active.metrics.valueAtRisk95Pct)}%</strong><small>周度历史分布</small></article><article><span>95% CVaR</span><strong>{number(active.metrics.conditionalValueAtRisk95Pct)}%</strong><small>尾部损失均值</small></article><article><span>年化波动</span><strong>{number(active.metrics.annualizedVolatilityPct)}%</strong><small>覆盖 {number(active.coverageWeightPct)}%</small></article></section> : <section className="folio-panel empty-copy tall">选择币种后生成回撤、VaR 与 CVaR</section>}
  </div>;
}

function LiquidityRiskView({ dashboard }: { dashboard: PortfolioDashboard }) {
  const quoted = dashboard.positions.filter((position) => position.price != null).length;
  const rows = dashboard.positions.map((position) => ({ ...position, status: position.price == null ? "行情缺口" : position.market === "CN" ? "T+1 交易约束" : position.market === "HK" ? "港股结算" : "美股结算" }));
  return <div className="workbench-stack"><section className="workbench-metrics"><article><span>行情覆盖</span><strong>{dashboard.positions.length ? number(quoted / dashboard.positions.length * 100) : "—"}%</strong><small>{quoted}/{dashboard.positions.length} 只</small></article><article><span>成本口径持仓</span><strong>{dashboard.positions.length - quoted}</strong><small>缺少实时估值</small></article><article><span>市场数量</span><strong>{new Set(dashboard.positions.map((item) => item.market)).size}</strong><small>结算规则需分市场</small></article><article><span>成交量覆盖</span><strong>0%</strong><small>尚未接入 ADV / 换手</small></article></section><section className="folio-panel"><div className="panel-title"><div><span>LIQUIDITY MAP</span><h2>持仓流动性检查</h2></div><Activity size={18} /></div><div className="liquidity-list">{rows.map((item) => <article key={`${item.accountId}:${item.symbol}`}><div><strong>{item.name}</strong><span>{item.market}:{item.symbol} · {item.currency}</span></div><b className={item.price == null ? "negative" : "neutral"}>{item.status}</b><small>{item.quoteAsOf ? `行情 ${formatDate(item.quoteAsOf)}` : "没有行情时间"}</small></article>)}</div><p className="method-note">正式流动性风险仍需日均成交额、盘口深度、持仓退出天数和停牌状态；当前不使用市值替代这些字段。</p></section></div>;
}

function StressTestView({ dashboard }: { dashboard: PortfolioDashboard }) {
  const scenarios = [
    { id: "broad", name: "全球权益回撤", note: "各市场同步下跌 10%", shocks: { CN: -10, HK: -10, US: -10 } },
    { id: "china", name: "中国风险偏好冲击", note: "A 股 -8%，港股 -12%，美股 -2%", shocks: { CN: -8, HK: -12, US: -2 } },
    { id: "us", name: "海外利率冲击", note: "美股 -12%，港股 -6%，A 股 -3%", shocks: { CN: -3, HK: -6, US: -12 } },
  ];
  const currencies = Array.from(new Set(dashboard.analytics.byMarket.map((item) => item.currency)));
  return <section className="folio-panel"><div className="panel-title"><div><span>STRESS TEST</span><h2>确定性市场冲击</h2></div><ShieldCheck size={18} /></div><div className="stress-grid">{scenarios.map((scenario) => <article key={scenario.id}><strong>{scenario.name}</strong><span>{scenario.note}</span>{currencies.map((currency) => { const impact = dashboard.analytics.byMarket.filter((item) => item.currency === currency).reduce((sum, item) => sum + item.weight / 100 * scenario.shocks[item.key as Market], 0); return <div key={currency}><b>{currency}</b><em className="negative">{number(impact)}%</em></div>; })}</article>)}</div><p className="method-note">这是按当前市场权重做的静态一阶冲击，不包含相关性变化、波动率跳升、汇率和流动性折价。</p></section>;
}

function AlertRulesView({ dashboard }: { dashboard: PortfolioDashboard }) {
  const rules = riskAlertRules(dashboard);
  return <section className="folio-panel"><div className="panel-title"><div><span>ALERT RULES</span><h2>基础预警规则</h2></div><ShieldCheck size={18} /></div><div className="alert-rule-list">{rules.map((rule) => <article key={rule.id} className={rule.hit ? "is-hit" : "is-normal"}><i /><div><strong>{rule.label}</strong><span>{rule.hit ? "已触发" : "正常"}</span></div><b>{rule.value}</b></article>)}</div><p className="method-note">当前规则只读本地账本，不自动卖出、不修改持仓。阈值后续可接入用户配置和通知渠道。</p></section>;
}

function RiskView({ dashboard, view, onView, result, onResult }: { dashboard: PortfolioDashboard; view: RiskSubview; onView(view: RiskSubview): void; result?: PortfolioPerformanceResult; onResult(result: PortfolioPerformanceResult): void }) {
  const issues = reconciliationIssues(dashboard);
  const triggeredRules = riskAlertRules(dashboard).filter((item) => item.hit);
  const concentration = dashboard.analytics.concentration;
  return <div className="workspace-shell"><WorkspaceTabs items={RISK_TABS} value={view} onChange={(next) => onView(next as RiskSubview)} />
    {view === "overview" && <div className="workbench-stack"><section className="workbench-metrics"><article><span>风险状态</span><strong className={triggeredRules.length ? "negative" : "positive"}>{triggeredRules.length ? "需关注" : "正常"}</strong><small>{triggeredRules.length} 项规则触发 · {issues.length} 项数据异常</small></article><article><span>最大持仓</span><strong>{number(concentration.topPositionWeight)}%</strong><small>阈值提示 30%</small></article><article><span>有效持仓数</span><strong>{number(concentration.effectivePositionCount)}</strong><small>实际 {concentration.positionCount} 只</small></article><article><span>估值状态</span><strong>{dashboard.valuationStatus === "live" ? "实时" : dashboard.valuationStatus === "partial" ? "部分实时" : "成本"}</strong><small>{dashboard.positions.filter((item) => item.price == null).length} 只缺行情</small></article></section><div className="content-grid risk-grid"><AllocationBars title="市场暴露" items={dashboard.analytics.byMarket} /><AllocationBars title="账户暴露" items={dashboard.analytics.byAccount} /><ReconciliationView dashboard={dashboard} /></div></div>}
    {view === "concentration" && <ConcentrationView dashboard={dashboard} />}
    {view === "exposure" && <div className="workbench-stack"><CurrencyCards dashboard={dashboard} /><div className="content-grid"><AllocationBars title="市场暴露（分币种）" items={dashboard.analytics.byMarket} /><AllocationBars title="账户暴露（分币种）" items={dashboard.analytics.byAccount} /></div><section className="folio-panel"><p className="method-note">币种卡片不做跨币种权重比较；汇率快照接入前，不把不同货币的名义金额相加作为真实风险贡献。</p></section></div>}
    {view === "drawdown" && <RiskHistoryView dashboard={dashboard} result={result} onResult={onResult} />}
    {view === "liquidity" && <LiquidityRiskView dashboard={dashboard} />}
    {view === "stress" && <StressTestView dashboard={dashboard} />}
    {view === "alerts" && <AlertRulesView dashboard={dashboard} />}
  </div>;
}

function AllocationView({
  dashboard,
  result,
  onResult,
}: {
  dashboard: PortfolioDashboard;
  result?: PortfolioOptimizationResult;
  onResult(result: PortfolioOptimizationResult): void;
}) {
  const currencies = useMemo(
    () => Array.from(new Set(dashboard.positions.map((position) => position.currency))),
    [dashboard.positions],
  );
  const [currency, setCurrency] = useState(currencies[0] || "CNY");
  const [objective, setObjective] = useState<PortfolioOptimizationObjective>("risk-balanced");
  const [lookbackWeeks, setLookbackWeeks] = useState(104);
  const [maxWeight, setMaxWeight] = useState(35);
  const [cashWeight, setCashWeight] = useState(0);
  const [riskFreeRate, setRiskFreeRate] = useState(2);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (currencies.length > 0 && !currencies.includes(currency)) setCurrency(currencies[0]);
  }, [currencies, currency]);

  const run = async () => {
    setRunning(true); setError("");
    try {
      const input: PortfolioOptimizationInput = {
        objective,
        currency,
        lookbackWeeks,
        maxWeight: maxWeight / 100,
        allowCash: cashWeight > 0,
        cashWeight: cashWeight / 100,
        riskFreeRatePct: riskFreeRate,
      };
      onResult(await portfolioClient({
        userId: dashboard.userId,
        workspaceId: dashboard.workspaceId,
      }).optimizeAllocation(input));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "资产配置计算暂时不可用");
    } finally { setRunning(false); }
  };

  const activeResult = result?.currency === currency ? result : undefined;
  return <div className="allocation-studio">
    <section className="folio-panel allocation-controls">
      <div className="panel-title"><div><span>CONSTRAINTS</span><h2>配置约束</h2></div><Settings2 size={18} /></div>
      <div className="objective-grid">
        {(Object.entries(OPTIMIZATION_LABELS) as Array<[PortfolioOptimizationObjective, { name: string; note: string }]>).map(([key, item]) => (
          <button key={key} className={objective === key ? "active" : ""} onClick={() => setObjective(key)}>
            <strong>{item.name}</strong><span>{item.note}</span>
          </button>
        ))}
      </div>
      <div className="allocation-form-grid">
        <label><span>分析币种</span><select value={currency} onChange={(event) => setCurrency(event.target.value)} disabled={currencies.length === 0}>{currencies.length ? currencies.map((item) => <option key={item}>{item}</option>) : <option>CNY</option>}</select></label>
        <label><span>历史窗口</span><select value={lookbackWeeks} onChange={(event) => setLookbackWeeks(Number(event.target.value))}><option value={52}>1 年 · 52 周</option><option value={104}>2 年 · 104 周</option><option value={156}>3 年 · 156 周</option><option value={260}>5 年 · 260 周</option></select></label>
        <label><span>单一资产上限</span><select value={maxWeight} onChange={(event) => setMaxWeight(Number(event.target.value))}><option value={20}>20%</option><option value={25}>25%</option><option value={35}>35%</option><option value={50}>50%</option><option value={100}>不限制</option></select></label>
        <label><span>现金储备</span><select value={cashWeight} onChange={(event) => setCashWeight(Number(event.target.value))}><option value={0}>不保留</option><option value={5}>5%</option><option value={10}>10%</option><option value={20}>20%</option></select></label>
        <label><span>现金年化参考</span><input inputMode="decimal" value={riskFreeRate} onChange={(event) => setRiskFreeRate(Number(event.target.value))} /></label>
      </div>
      {error && <div className="inline-error">{error}</div>}
      <button className="primary-button" onClick={() => void run()} disabled={running || currencies.length === 0}>{running ? <LoaderCircle className="spin" size={16} /> : <ChartPie size={16} />}生成目标配置</button>
      <p className="method-note">同一币种单独计算，历史行情统一由 Desk 数据接口提供；方案不会自动改写账本或执行交易。</p>
    </section>

    <div className="allocation-results">
      {!activeResult ? <section className="folio-panel allocation-empty">
        <ChartPie size={28} /><strong>等待生成配置方案</strong><span>选择目标与约束后，比较当前权重和目标权重。</span>
      </section> : <>
        <section className="allocation-metrics">
          <article><span>历史年化收益估计</span><strong className={pnlClass(activeResult.annualizedExpectedReturnPct)}>{signed(activeResult.annualizedExpectedReturnPct, "%")}</strong></article>
          <article><span>历史年化波动估计</span><strong>{number(activeResult.annualizedVolatilityPct)}%</strong></article>
          <article><span>目标集中度 HHI</span><strong>{number(activeResult.targetConcentration, 4)}</strong><small>当前 {number(activeResult.currentConcentration, 4)}</small></article>
          <article><span>有效周度样本</span><strong>{activeResult.observations}</strong><small>{activeResult.dataSources.join(" · ") || "统一行情"}</small></article>
        </section>
        <section className="folio-panel allocation-table-panel">
          <div className="panel-title"><div><span>TARGET WEIGHTS</span><h2>当前与目标权重</h2></div><span className={`optimization-status status-${activeResult.status}`}>{activeResult.status === "ready" ? "数据完整" : activeResult.status === "partial" ? "部分冻结" : "数据不足"}</span></div>
          <div className="allocation-comparison-list">{activeResult.allocations.map((item) => (
            <article key={`${item.market}:${item.symbol}`}>
              <div className="allocation-security"><span>{item.market}</span><div><strong>{item.name}</strong><small>{item.symbol}{item.frozen ? " · 历史不足，权重冻结" : ` · ${item.historyPoints} 周`}</small></div></div>
              <div className="weight-comparison">
                <div><span>当前</span><i style={{ width: `${Math.min(100, item.currentWeight)}%` }} /><b>{number(item.currentWeight)}%</b></div>
                <div className="target"><span>目标</span><i style={{ width: `${Math.min(100, item.targetWeight)}%` }} /><b>{number(item.targetWeight)}%</b></div>
              </div>
              <strong className={pnlClass(item.changeWeight)}>{signed(item.changeWeight, "%")}</strong>
            </article>
          ))}</div>
        </section>
        <section className="folio-panel allocation-evidence">
          <div className="panel-title"><div><span>MODEL NOTES</span><h2>方法与限制</h2></div><ShieldCheck size={18} /></div>
          <dl><div><dt>算法</dt><dd>{activeResult.method}</dd></div><div><dt>历史窗口</dt><dd>{activeResult.lookbackWeeks} 周 · 周线</dd></div><div><dt>数据截至</dt><dd>{activeResult.asOf || "—"}</dd></div></dl>
          <ul>{activeResult.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </section>
      </>}
    </div>
  </div>;
}

function PerformanceView({
  dashboard,
  result,
  onResult,
}: {
  dashboard: PortfolioDashboard;
  result?: PortfolioPerformanceResult;
  onResult(result: PortfolioPerformanceResult): void;
}) {
  const currencies = useMemo(
    () => Array.from(new Set(dashboard.positions.map((position) => position.currency))),
    [dashboard.positions],
  );
  const [currency, setCurrency] = useState(currencies[0] || "CNY");
  const [lookbackWeeks, setLookbackWeeks] = useState(156);
  const [riskFreeRate, setRiskFreeRate] = useState(2);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (currencies.length > 0 && !currencies.includes(currency)) setCurrency(currencies[0]);
  }, [currencies, currency]);
  const run = async () => {
    setRunning(true); setError("");
    try {
      const input: PortfolioPerformanceInput = { currency, lookbackWeeks, riskFreeRatePct: riskFreeRate };
      onResult(await portfolioClient({
        userId: dashboard.userId,
        workspaceId: dashboard.workspaceId,
      }).analyzePerformance(input));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "绩效分析暂时不可用");
    } finally { setRunning(false); }
  };
  const activeResult = result?.currency === currency ? result : undefined;
  const metrics = activeResult?.metrics;
  const curve = useMemo(() => {
    const values = activeResult?.series.map((point) => point.equity) || [];
    if (values.length < 2) return "";
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const span = Math.max(maximum - minimum, 0.0001);
    return values.map((value, index) => {
      const x = index / (values.length - 1) * 1000;
      const y = 215 - (value - minimum) / span * 175;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
  }, [activeResult]);

  return <div className="performance-stack">
    <CurrencyCards dashboard={dashboard} />
    <div className="performance-workbench">
      <section className="folio-panel performance-controls">
        <div className="panel-title"><div><span>HISTORICAL LENS</span><h2>当前持仓历史模拟</h2></div><ChartPie size={18} /></div>
        <div className="allocation-form-grid">
          <label><span>分析币种</span><select value={currency} onChange={(event) => setCurrency(event.target.value)} disabled={currencies.length === 0}>{currencies.length ? currencies.map((item) => <option key={item}>{item}</option>) : <option>CNY</option>}</select></label>
          <label><span>历史窗口</span><select value={lookbackWeeks} onChange={(event) => setLookbackWeeks(Number(event.target.value))}><option value={52}>1 年</option><option value={104}>2 年</option><option value={156}>3 年</option><option value={260}>5 年</option></select></label>
          <label><span>无风险年化参考</span><input inputMode="decimal" value={riskFreeRate} onChange={(event) => setRiskFreeRate(Number(event.target.value))} /></label>
        </div>
        {error && <div className="inline-error">{error}</div>}
        <button className="primary-button" onClick={() => void run()} disabled={running || currencies.length === 0}>{running ? <LoaderCircle className="spin" size={16} /> : <BadgeDollarSign size={16} />}计算绩效指标</button>
        <p className="method-note">按当前持仓权重回看历史周线，适合衡量组合结构；账本中的真实盈亏与现金收入仍在下方单独展示。</p>
      </section>

      {!metrics ? <section className="folio-panel performance-empty"><BadgeDollarSign size={28} /><strong>等待绩效分析</strong><span>生成收益、波动、回撤和尾部风险指标。</span></section> : <section className="folio-panel performance-analysis">
        <div className="panel-title"><div><span>QUANTSTATS CORE</span><h2>收益与风险画像</h2></div><span className={`optimization-status status-${activeResult?.status}`}>覆盖 {number(activeResult?.coverageWeightPct)}%</span></div>
        <div className="performance-metric-grid">
          <article><span>累计收益</span><strong className={pnlClass(metrics.totalReturnPct)}>{signed(metrics.totalReturnPct, "%")}</strong></article>
          <article><span>年化收益</span><strong className={pnlClass(metrics.annualizedReturnPct)}>{signed(metrics.annualizedReturnPct, "%")}</strong></article>
          <article><span>年化波动</span><strong>{number(metrics.annualizedVolatilityPct)}%</strong></article>
          <article><span>最大回撤</span><strong className="negative">{number(metrics.maxDrawdownPct)}%</strong><small>{metrics.maxDrawdownDurationWeeks} 周</small></article>
          <article><span>Sharpe</span><strong>{number(metrics.sharpe)}</strong></article>
          <article><span>Sortino</span><strong>{number(metrics.sortino)}</strong></article>
          <article><span>Calmar</span><strong>{number(metrics.calmar)}</strong></article>
          <article><span>周胜率</span><strong>{number(metrics.winRatePct)}%</strong></article>
        </div>
        <div className="performance-curve">
          <div><strong>净值曲线</strong><span>{activeResult?.observations} 周 · {activeResult?.dataSources.join(" · ") || "统一行情"}</span></div>
          {curve ? <svg viewBox="0 0 1000 240" preserveAspectRatio="none" role="img" aria-label="组合历史净值曲线"><line x1="0" y1="215" x2="1000" y2="215" /><polyline points={curve} /></svg> : <div className="empty-copy">样本不足</div>}
        </div>
        <div className="tail-risk-grid">
          <div><span>95% VaR / 周</span><strong>{number(metrics.valueAtRisk95Pct)}%</strong></div>
          <div><span>95% CVaR / 周</span><strong>{number(metrics.conditionalValueAtRisk95Pct)}%</strong></div>
          <div><span>最好一周</span><strong className="positive">{signed(metrics.bestWeekPct, "%")}</strong></div>
          <div><span>最差一周</span><strong className="negative">{signed(metrics.worstWeekPct, "%")}</strong></div>
        </div>
        <ul className="performance-warnings">{activeResult?.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      </section>}
    </div>
    <section className="folio-panel performance-ledger">
      <div className="panel-title"><div><span>ATTRIBUTION</span><h2>账本收益与费用归因</h2></div><BadgeDollarSign size={18} /></div>
      <div className="performance-grid">{dashboard.currencies.map((item) => (
        <article key={item.currency}><header><strong>{item.currency}</strong><span>{dashboard.valuationStatus}</span></header>
          <dl>
            <div><dt>浮动盈亏</dt><dd className={pnlClass(item.unrealizedPnl)}>{signed(item.unrealizedPnl)}</dd></div>
            <div><dt>已实现盈亏</dt><dd className={pnlClass(item.realizedPnl)}>{signed(item.realizedPnl)}</dd></div>
            <div><dt>分红与利息</dt><dd>{number(item.income)}</dd></div>
            <div><dt>累计费用</dt><dd>{number(item.fees)}</dd></div>
            <div><dt>现金余额</dt><dd>{number(item.cash)}</dd></div>
          </dl>
        </article>
      ))}</div>
    </section>
  </div>;
}

function SettingsView({ dashboard, onRefresh }: { dashboard: PortfolioDashboard; onRefresh(): void }) {
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [currency, setCurrency] = useState("CNY");
  const [message, setMessage] = useState("");
  const client = portfolioClient({ userId: dashboard.userId, workspaceId: dashboard.workspaceId });
  const create = async () => {
    try {
      await client.createAccount({ id, name, currency });
      setId(""); setName(""); setMessage("账户已建立"); onRefresh();
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "建立失败"); }
  };
  const migrate = async () => {
    const result = await client.importLegacy();
    setMessage(result.imported ? `已导入 ${result.activitiesCreated} 笔旧流水` : `未导入：${result.reason}`);
    onRefresh();
  };
  return <div className="settings-grid">
    <section className="folio-panel">
      <div className="panel-title"><div><span>ACCOUNTS</span><h2>账户</h2></div><Landmark size={18} /></div>
      <div className="account-list">{dashboard.accounts.map((account) => <article key={account.id}><div><strong>{account.name}</strong><span>{account.id} · {account.accountType}</span></div><b>{account.currency}</b></article>)}</div>
      <div className="compact-form"><input value={id} onChange={(event) => setId(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))} placeholder="账户 ID" /><input value={name} onChange={(event) => setName(event.target.value)} placeholder="账户名称" /><input value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} placeholder="CNY" /><button onClick={() => void create()}><Plus size={15} />新建</button></div>
    </section>
    <section className="folio-panel migration-panel">
      <div className="panel-title"><div><span>MIGRATION</span><h2>旧持仓迁移</h2></div><ShieldCheck size={18} /></div>
      <p>读取本机 <code>~/.vibe-research/portfolio.json</code>，转换成账户与流水。迁移具有幂等保护，不会重复导入。</p>
      <button className="secondary-button" onClick={() => void migrate()}>执行安全迁移</button>
      {message && <div className="status-message">{message}</div>}
    </section>
    <section className="folio-panel data-state-panel">
      <div className="panel-title"><div><span>DATA STATE</span><h2>数据状态</h2></div><Settings2 size={18} /></div>
      <dl><div><dt>估值状态</dt><dd>{dashboard.valuationStatus}</dd></div><div><dt>账户数</dt><dd>{dashboard.accounts.length}</dd></div><div><dt>流水数</dt><dd>{dashboard.activities.length}</dd></div><div><dt>更新时间</dt><dd>{formatDate(dashboard.updatedAt)}</dd></div></dl>
    </section>
  </div>;
}

export function PortfolioCenterApp() {
  const workspace = workspaceFromSearch();
  const [subview, setSubview] = useState<TradingSubview | RiskSubview>(() => subviewFromSearch(workspace));
  const embedded = window.self !== window.top;
  const config = WORKSPACES[workspace];
  const [identity, setIdentity] = useState<PortfolioIdentity | undefined>(() => (
    window.self === window.top
      ? { userId: "local-user", workspaceId: "local-workspace" }
      : undefined
  ));
  const [dashboard, setDashboard] = useState<PortfolioDashboard>();
  const [optimization, setOptimization] = useState<PortfolioOptimizationResult>();
  const [performance, setPerformance] = useState<PortfolioPerformanceResult>();
  const [researchCoverage, setResearchCoverage] = useState<PortfolioResearchCoverage>();
  const [researchCoverageLoading, setResearchCoverageLoading] = useState(false);
  const [selected, setSelected] = useState<PortfolioPosition>();
  const [linkedSecurity, setLinkedSecurity] = useState<LinkedSecurity>();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshingQuotes, setRefreshingQuotes] = useState(false);
  const [error, setError] = useState("");
  const [host, setHost] = useState<EmbeddedHost>();
  const contextRef = useRef<ModPageContext>(buildContext(workspace, subview));
  const identityRef = useRef<PortfolioIdentity | undefined>(identity);
  const dashboardRef = useRef(dashboard);
  const researchCoverageRef = useRef(researchCoverage);
  const loadRef = useRef<() => Promise<void>>(async () => undefined);
  const requestIdRef = useRef(0);
  const identityKeyRef = useRef<string | undefined>(undefined);
  const quoteControllerRef = useRef<AbortController | undefined>(undefined);
  const researchControllerRef = useRef<AbortController | undefined>(undefined);
  const bridge = useMemo(() => createModBridge({ modId: workspace, parentOrigin: parentOrigin() }), [workspace]);
  const dashboardCache = useMemo(() => identity ? createModSnapshotCache<PortfolioDashboard>({
    modId: workspace,
    ...identity,
    resourceKey: "dashboard",
    maxBytes: 2 * 1024 * 1024,
  }) : undefined, [identity?.userId, identity?.workspaceId, workspace]);
  const coverageCache = useMemo(() => identity ? createModSnapshotCache<PortfolioResearchCoverage>({
    modId: workspace,
    ...identity,
    resourceKey: "research-coverage",
    maxBytes: 1024 * 1024,
  }) : undefined, [identity?.userId, identity?.workspaceId, workspace]);
  const dashboardCacheKey = dashboardCache?.key;
  const coverageCacheKey = coverageCache?.key;

  const load = useCallback(async () => {
    if (!identity || !dashboardCache || !coverageCache) return;
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    quoteControllerRef.current?.abort();
    researchControllerRef.current?.abort();
    const cachedDashboard = dashboardCache.read()?.value;
    const cachedCoverage = coverageCache.read()?.value;
    const identityKey = `${identity.userId}:${identity.workspaceId}:${workspace}`;
    const identityChanged = identityKeyRef.current !== identityKey;
    identityKeyRef.current = identityKey;
    if (identityChanged) {
      setDashboard(cachedDashboard);
      dashboardRef.current = cachedDashboard;
      setResearchCoverage(cachedCoverage);
      researchCoverageRef.current = cachedCoverage;
      setOptimization(undefined);
      setPerformance(undefined);
      setSelected(undefined);
    }
    const currentDashboard = identityChanged ? cachedDashboard : dashboardRef.current;
    if (!currentDashboard && cachedDashboard) setDashboard(cachedDashboard);
    if (!researchCoverageRef.current && cachedCoverage) {
      setResearchCoverage(cachedCoverage);
      researchCoverageRef.current = cachedCoverage;
    }
    setResearchCoverageLoading(workspace === "portfolio-brief");
    setRefreshingQuotes(false);
    setLoading(!currentDashboard && !cachedDashboard);
    setRefreshing(Boolean(currentDashboard || cachedDashboard));
    setError("");
    const client = portfolioClient(identity);
    try {
      const costDashboard = await client.dashboard({ includeQuotes: false });
      if (requestIdRef.current !== requestId) return;
      setDashboard(costDashboard);
      dashboardRef.current = costDashboard;
      dashboardCache.write(costDashboard, costDashboard.updatedAt);
      setLoading(false);
      setRefreshing(false);
      if (workspace === "portfolio-brief") {
        const researchController = new AbortController();
        researchControllerRef.current = researchController;
        void client.researchCoverage({ signal: researchController.signal })
          .then((coverage) => {
            if (requestIdRef.current === requestId && !researchController.signal.aborted) {
              setResearchCoverage(coverage);
              researchCoverageRef.current = coverage;
              coverageCache.write(coverage, coverage.generatedAt);
            }
          })
          .catch(() => undefined)
          .finally(() => {
            if (requestIdRef.current === requestId) setResearchCoverageLoading(false);
          });
      }
      if (costDashboard.positions.length === 0) {
        setResearchCoverageLoading(false);
        return;
      }

      const controller = new AbortController();
      quoteControllerRef.current = controller;
      setRefreshingQuotes(true);
      void client.dashboard({ signal: controller.signal })
        .then((quotedDashboard) => {
          if (requestIdRef.current === requestId && !controller.signal.aborted) {
            setDashboard(quotedDashboard);
            dashboardRef.current = quotedDashboard;
            dashboardCache.write(quotedDashboard, quotedDashboard.updatedAt);
          }
        })
        .catch((reason) => {
          if (requestIdRef.current === requestId && reason instanceof Error && reason.name !== "AbortError") {
            setError("账本已加载，实时行情暂时不可用；当前显示成本口径。");
          }
        })
        .finally(() => {
          if (requestIdRef.current === requestId) setRefreshingQuotes(false);
        });
    } catch (reason) {
      if (requestIdRef.current !== requestId) return;
      setError(reason instanceof Error ? reason.message : "组合数据暂时不可用");
      setResearchCoverageLoading(false);
      setLoading(false);
      setRefreshing(false);
    }
  }, [coverageCacheKey, dashboardCacheKey, identity, workspace]);
  identityRef.current = identity;
  dashboardRef.current = dashboard;
  researchCoverageRef.current = researchCoverage;
  loadRef.current = load;

  useEffect(() => { if (identity) void load(); }, [identity, load]);

  useEffect(() => {
    let active = true;
    let connection: ModHostConnection | undefined;
    void connectModHost({ modId: workspace, parentOrigin: parentOrigin(), capabilities: ["events", "actions", "agent", "context", "theme"] })
      .then((next) => {
        if (!active) { next.close(); return; }
        connection = next;
        if (!next.embedded) return;
        setHost(next);
        setIdentity({ userId: next.config.user.id, workspaceId: next.config.workspace.id });
        document.documentElement.dataset.theme = next.config.environment.theme;
        next.subscribe((desk) => {
          document.documentElement.dataset.theme = desk.environment.theme;
          setIdentity({ userId: desk.user.id, workspaceId: desk.workspace.id });
        });
        next.setContextProvider(() => contextRef.current);
        next.setUiActionHandler(async (actionId) => {
          if (actionId === "portfolio.refresh") { await loadRef.current(); return { ok: true }; }
          if (actionId === "portfolio.optimize") {
            if (!identityRef.current) throw new Error("Desk 身份尚未就绪");
            const currency = dashboardRef.current?.positions[0]?.currency;
            if (!currency) throw new Error("当前组合没有可优化持仓");
            const result = await portfolioClient(identityRef.current).optimizeAllocation({
              objective: "risk-balanced",
              currency,
              lookbackWeeks: 104,
              maxWeight: 0.35,
              allowCash: false,
              cashWeight: 0,
              riskFreeRatePct: 2,
            });
            setOptimization(result);
            return result;
          }
          if (actionId === "portfolio.analyze-performance") {
            if (!identityRef.current) throw new Error("Desk 身份尚未就绪");
            const currency = dashboardRef.current?.positions[0]?.currency;
            if (!currency) throw new Error("当前组合没有可分析持仓");
            const result = await portfolioClient(identityRef.current).analyzePerformance({
              currency,
              lookbackWeeks: 156,
              riskFreeRatePct: 2,
            });
            setPerformance(result);
            return result;
          }
          if (actionId === "portfolio.import-legacy") {
            if (!identityRef.current) throw new Error("Desk 身份尚未就绪");
            const result = await portfolioClient(identityRef.current).importLegacy();
            await loadRef.current();
            return result;
          }
          throw new Error(`Unsupported action: ${actionId}`);
        });
      })
      .catch(() => undefined);
    return () => { active = false; connection?.close(); setHost(undefined); };
  }, [workspace]);

  useEffect(() => () => {
    quoteControllerRef.current?.abort();
    researchControllerRef.current?.abort();
    bridge.close();
  }, [bridge]);

  useEffect(() => bridge.subscribe((event) => {
    if (event.event !== "security.selected") return;
    const { symbol, name, market, currency } = event.payload;
    if (
      typeof symbol !== "string" ||
      (market !== "CN" && market !== "HK" && market !== "US")
    ) return;
    setLinkedSecurity({
      symbol,
      name: typeof name === "string" ? name : symbol,
      market,
      ...(typeof currency === "string" ? { currency } : {}),
    });
  }), [bridge]);

  useEffect(() => {
    if (!linkedSecurity || !dashboard) return;
    setSelected(dashboard.positions.find((position) =>
      position.market === linkedSecurity.market &&
      position.symbol.toUpperCase() === linkedSecurity.symbol.toUpperCase()
    ));
  }, [dashboard, linkedSecurity]);

  const changeSubview = (next: TradingSubview | RiskSubview) => {
    setSubview(next);
    const url = new URL(window.location.href);
    url.searchParams.set("view", next);
    window.history.replaceState({}, "", url);
  };

  contextRef.current = buildContext(workspace, subview, dashboard, selected, linkedSecurity, optimization, performance, researchCoverage);
  useEffect(() => { if (host) host.publishContext(contextRef.current); }, [dashboard, host, linkedSecurity, optimization, performance, researchCoverage, selected, subview, workspace]);

  const selectPosition = (position: PortfolioPosition) => {
    setSelected(position);
    setLinkedSecurity({
      symbol: position.symbol,
      name: position.name,
      market: position.market,
      currency: position.currency,
    });
    bridge.emit("security.selected", { symbol: position.symbol, name: position.name, market: position.market, currency: position.currency });
  };

  const selectResearchPosition = (item: PortfolioResearchPosition) => {
    const position = dashboard?.positions.find((candidate) =>
      candidate.market === item.market && candidate.symbol === item.symbol
    );
    if (position) selectPosition(position);
  };

  return <main className="portfolio-root" data-embedded={embedded || undefined}>
    <header className="folio-header">
      {!embedded ? <div data-mod-page-title><span className="folio-eyebrow">{config.eyebrow}</span><h1>{config.title}</h1><p>{config.subtitle}</p></div> : null}
      <div className="header-actions">
        {linkedSecurity && <span className="linked-security-pill">联动标的 {linkedSecurity.market}:{linkedSecurity.symbol}</span>}
        <span className={`valuation-pill state-${refreshingQuotes ? "loading" : dashboard?.valuationStatus || "loading"}`}><i />{refreshingQuotes ? "行情刷新中" : dashboard?.valuationStatus === "live" ? "实时估值" : dashboard?.valuationStatus === "partial" ? "部分实时" : "成本口径"}</span>
        <button className="refresh-button" onClick={() => void load()} disabled={loading || refreshing}>{loading || refreshing || refreshingQuotes ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}{refreshing ? "更新中" : "刷新"}</button>
      </div>
    </header>

    {error && <div className="error-banner">{error}</div>}
    {!dashboard && loading ? <div className="loading-stage"><LoaderCircle className="spin" /><span>正在整理组合账本…</span></div> : dashboard && <>
      {workspace === "portfolio-brief" && <div className="overview-stack"><CurrencyCards dashboard={dashboard} /><div className="content-grid"><PositionsTable dashboard={dashboard} selected={selected} onSelect={selectPosition} /><AllocationBars title="市场暴露" items={dashboard.analytics.byMarket} /></div><ResearchCoveragePanel coverage={researchCoverage} loading={researchCoverageLoading} selected={selected} onSelect={selectResearchPosition} /></div>}
      {workspace === "portfolio-activities" && <TradingWorkbench dashboard={dashboard} view={subview as TradingSubview} onView={changeSubview} selected={selected} onSelect={selectPosition} onRefresh={() => void load()} />}
      {workspace === "portfolio-risk" && <RiskView dashboard={dashboard} view={subview as RiskSubview} onView={changeSubview} result={performance} onResult={setPerformance} />}
      {workspace === "portfolio-allocation" && <AllocationView dashboard={dashboard} result={optimization} onResult={setOptimization} />}
      {workspace === "portfolio-performance" && <PerformanceView dashboard={dashboard} result={performance} onResult={setPerformance} />}
      {workspace === "portfolio-settings" && <SettingsView dashboard={dashboard} onRefresh={() => void load()} />}
    </>}

    <footer className="folio-footer"><Banknote size={14} /><span>本地账本 · 不预置标的 · 不构成投资建议</span></footer>
  </main>;
}
