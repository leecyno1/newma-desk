import {
  Activity,
  ArrowDownToLine,
  ArrowUpFromLine,
  BadgeDollarSign,
  Banknote,
  CircleDollarSign,
  Gauge,
  Landmark,
  Layers3,
  LoaderCircle,
  Plus,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Trash2,
  WalletCards,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import {
  connectModHost,
  createModBridge,
  type ModHostConnection,
} from "@newma-desk/mod-sdk";

import { portfolioClient, type ActivityInput, type PortfolioIdentity } from "./api";
import type {
  ActivityType,
  Market,
  PortfolioDashboard,
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
  if (workspace === "portfolio-performance") return [...shared, { id: "performance-ledger", type: "portfolio-performance", title: "绩效归因" }];
  if (workspace === "portfolio-settings") return [...shared, { id: "portfolio-settings", type: "settings", title: "账户与迁移" }];
  return [...shared, { id: "portfolio-positions", type: "portfolio", title: "持仓与配置" }];
}

function buildContext(
  workspace: PortfolioWorkspace,
  dashboard?: PortfolioDashboard,
  selected?: PortfolioPosition,
  linkedSecurity?: LinkedSecurity,
): ModPageContext {
  const config = WORKSPACES[workspace];
  const activeSecurity = selected || linkedSecurity;
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
    filters: { workspace, valuation: dashboard?.valuationStatus || "unknown" },
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
      } : {},
    },
    actions: [
      { id: "portfolio.refresh", label: "刷新组合", available: true },
      { id: "portfolio.import-legacy", label: "导入旧持仓", available: workspace === "portfolio-settings" },
    ],
    tasks: [],
  };
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
  const [quantity, setQuantity] = useState("");
  const [unitPrice, setUnitPrice] = useState("");
  const [amount, setAmount] = useState("");
  const [fee, setFee] = useState("");
  const [currency, setCurrency] = useState("CNY");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const identity = { userId: dashboard.userId, workspaceId: dashboard.workspaceId };
  const securityActivity = ["buy", "sell", "split", "dividend"].includes(type);
  const tradeActivity = type === "buy" || type === "sell";

  const submit = async () => {
    setSaving(true); setError("");
    try {
      const input: ActivityInput = {
        accountId,
        type,
        currency,
        occurredAt: new Date().toISOString(),
        ...(securityActivity ? { market, symbol: symbol.trim().toUpperCase() } : {}),
        ...(tradeActivity || type === "split" ? { quantity: Number(quantity) } : {}),
        ...(tradeActivity ? { unitPrice: Number(unitPrice), fee: Number(fee || 0) } : {}),
        ...(!tradeActivity && type !== "split" ? { amount: Number(amount) } : {}),
      };
      await portfolioClient(identity).createActivity(input);
      setSymbol(""); setQuantity(""); setUnitPrice(""); setAmount(""); setFee("");
      onCreated();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally { setSaving(false); }
  };

  return <section className="folio-panel journal-form">
    <div className="panel-title"><div><span>NEW ENTRY</span><h2>记录一笔流水</h2></div><Plus size={18} /></div>
    <div className="form-grid">
      <label><span>类型</span><select value={type} onChange={(event) => setType(event.target.value as ActivityType)}>{Object.entries(ACTIVITY_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label><span>账户</span><select value={accountId} onChange={(event) => setAccountId(event.target.value)}>{dashboard.accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
      {securityActivity && <label><span>市场</span><select value={market} onChange={(event) => { const next = event.target.value as Market; setMarket(next); setCurrency(next === "US" ? "USD" : next === "HK" ? "HKD" : "CNY"); }}><option>CN</option><option>HK</option><option>US</option></select></label>}
      {securityActivity && <label><span>标的</span><input value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="600519 / 00700 / AAPL" /></label>}
      {(tradeActivity || type === "split") && <label><span>{type === "split" ? "拆并比例" : "数量"}</span><input inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label>}
      {tradeActivity && <label><span>成交价</span><input inputMode="decimal" value={unitPrice} onChange={(event) => setUnitPrice(event.target.value)} /></label>}
      {tradeActivity && <label><span>费用</span><input inputMode="decimal" value={fee} onChange={(event) => setFee(event.target.value)} placeholder="0" /></label>}
      {!tradeActivity && type !== "split" && <label><span>金额</span><input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>}
      <label><span>币种</span><input value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} maxLength={12} /></label>
    </div>
    {error && <div className="inline-error">{error}</div>}
    <button className="primary-button" onClick={submit} disabled={saving}>{saving ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />}写入账本</button>
  </section>;
}

function ActivityLedger({ dashboard, onDeleted }: { dashboard: PortfolioDashboard; onDeleted(): void }) {
  const remove = async (id: string) => {
    await portfolioClient({ userId: dashboard.userId, workspaceId: dashboard.workspaceId }).deleteActivity(id);
    onDeleted();
  };
  return <section className="folio-panel ledger-panel">
    <div className="panel-title"><div><span>LEDGER</span><h2>最近流水</h2></div><Activity size={18} /></div>
    <div className="activity-list">{dashboard.activities.length === 0 ? <div className="empty-copy">账本是空的</div> : dashboard.activities.slice(0, 120).map((item) => (
      <article className="activity-row" key={item.id}>
        <div className={`activity-icon type-${item.type}`}>{item.type === "buy" || item.type === "deposit" ? <ArrowDownToLine size={16} /> : <ArrowUpFromLine size={16} />}</div>
        <div className="activity-main"><strong>{ACTIVITY_LABELS[item.type]} · {item.name || item.symbol || item.currency}</strong><span>{formatDate(item.occurredAt)} · {item.accountId} · {item.source}</span></div>
        <div className="activity-value"><strong>{item.quantity ? `${number(item.quantity, 6)} × ${number(item.unitPrice, 6)}` : number(item.amount)}</strong><span>{item.currency}{item.fee ? ` · 费用 ${number(item.fee)}` : ""}</span></div>
        <button className="ghost-icon" onClick={() => void remove(item.id)} title="删除流水"><Trash2 size={14} /></button>
      </article>
    ))}</div>
  </section>;
}

function RiskView({ dashboard }: { dashboard: PortfolioDashboard }) {
  const concentration = dashboard.analytics.concentration;
  return <div className="content-grid risk-grid">
    <section className="folio-panel risk-hero">
      <div className="panel-title"><div><span>CONCENTRATION</span><h2>组合集中度</h2></div><Gauge size={18} /></div>
      <div className="risk-score"><strong>{number(concentration.effectivePositionCount)}</strong><span>有效持仓数</span></div>
      <div className="risk-stat-grid">
        <div><span>最大单一持仓</span><strong>{number(concentration.topPositionWeight)}%</strong></div>
        <div><span>前三大持仓</span><strong>{number(concentration.topThreeWeight)}%</strong></div>
        <div><span>HHI</span><strong>{number(concentration.herfindahlIndex, 6)}</strong></div>
        <div><span>持仓数量</span><strong>{concentration.positionCount}</strong></div>
      </div>
      <p className="method-note">当前为账本集中度与暴露分析。Riskfolio 优化、CVaR 和压力测试将通过独立分析 Adapter 接入，不改变账本数据。</p>
    </section>
    <AllocationBars title="市场暴露" items={dashboard.analytics.byMarket} />
    <AllocationBars title="账户暴露" items={dashboard.analytics.byAccount} />
  </div>;
}

function PerformanceView({ dashboard }: { dashboard: PortfolioDashboard }) {
  return <div className="performance-stack">
    <CurrencyCards dashboard={dashboard} />
    <section className="folio-panel performance-ledger">
      <div className="panel-title"><div><span>ATTRIBUTION</span><h2>收益与费用归因</h2></div><BadgeDollarSign size={18} /></div>
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
  const config = WORKSPACES[workspace];
  const [identity, setIdentity] = useState<PortfolioIdentity>({ userId: "local-user", workspaceId: "local-workspace" });
  const [dashboard, setDashboard] = useState<PortfolioDashboard>();
  const [selected, setSelected] = useState<PortfolioPosition>();
  const [linkedSecurity, setLinkedSecurity] = useState<LinkedSecurity>();
  const [loading, setLoading] = useState(true);
  const [refreshingQuotes, setRefreshingQuotes] = useState(false);
  const [error, setError] = useState("");
  const [host, setHost] = useState<EmbeddedHost>();
  const contextRef = useRef<ModPageContext>(buildContext(workspace));
  const identityRef = useRef(identity);
  const loadRef = useRef<() => Promise<void>>(async () => undefined);
  const requestIdRef = useRef(0);
  const quoteControllerRef = useRef<AbortController | undefined>(undefined);
  const bridge = useMemo(() => createModBridge({ modId: workspace, parentOrigin: parentOrigin() }), [workspace]);

  const load = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    quoteControllerRef.current?.abort();
    setRefreshingQuotes(false);
    setLoading(true);
    setError("");
    const client = portfolioClient(identity);
    try {
      const costDashboard = await client.dashboard({ includeQuotes: false });
      if (requestIdRef.current !== requestId) return;
      setDashboard(costDashboard);
      setLoading(false);
      if (costDashboard.positions.length === 0) return;

      const controller = new AbortController();
      quoteControllerRef.current = controller;
      setRefreshingQuotes(true);
      void client.dashboard({ signal: controller.signal })
        .then((quotedDashboard) => {
          if (requestIdRef.current === requestId && !controller.signal.aborted) {
            setDashboard(quotedDashboard);
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
      setLoading(false);
    }
  }, [identity]);
  identityRef.current = identity;
  loadRef.current = load;

  useEffect(() => { void load(); }, [load]);

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
          if (actionId === "portfolio.import-legacy") {
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

  contextRef.current = buildContext(workspace, dashboard, selected, linkedSecurity);
  useEffect(() => { if (host) host.publishContext(contextRef.current); }, [dashboard, host, linkedSecurity, selected, workspace]);

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

  return <main className="portfolio-root">
    <header className="folio-header">
      <div><span className="folio-eyebrow">{config.eyebrow}</span><h1>{config.title}</h1><p>{config.subtitle}</p></div>
      <div className="header-actions">
        {linkedSecurity && <span className="linked-security-pill">联动标的 {linkedSecurity.market}:{linkedSecurity.symbol}</span>}
        <span className={`valuation-pill state-${refreshingQuotes ? "loading" : dashboard?.valuationStatus || "loading"}`}><i />{refreshingQuotes ? "行情刷新中" : dashboard?.valuationStatus === "live" ? "实时估值" : dashboard?.valuationStatus === "partial" ? "部分实时" : "成本口径"}</span>
        <button className="refresh-button" onClick={() => void load()} disabled={loading}>{loading || refreshingQuotes ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}刷新</button>
      </div>
    </header>

    {error && <div className="error-banner">{error}</div>}
    {!dashboard && loading ? <div className="loading-stage"><LoaderCircle className="spin" /><span>正在整理组合账本…</span></div> : dashboard && <>
      {workspace === "portfolio-brief" && <div className="overview-stack"><CurrencyCards dashboard={dashboard} /><div className="content-grid"><PositionsTable dashboard={dashboard} selected={selected} onSelect={selectPosition} /><AllocationBars title="市场暴露" items={dashboard.analytics.byMarket} /></div></div>}
      {workspace === "portfolio-activities" && <div className="journal-grid"><ActivityForm dashboard={dashboard} onCreated={() => void load()} /><ActivityLedger dashboard={dashboard} onDeleted={() => void load()} /></div>}
      {workspace === "portfolio-risk" && <RiskView dashboard={dashboard} />}
      {workspace === "portfolio-performance" && <PerformanceView dashboard={dashboard} />}
      {workspace === "portfolio-settings" && <SettingsView dashboard={dashboard} onRefresh={() => void load()} />}
    </>}

    <footer className="folio-footer"><Banknote size={14} /><span>本地账本 · 不预置标的 · 不构成投资建议</span></footer>
  </main>;
}
