import {
  Activity, ArrowDownRight, ArrowUpRight,
  ExternalLink, RefreshCw, Search, WalletCards,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import { connectModHost, type ModHostConnection } from "@newma-desk/mod-sdk";

import { fetchCapitalFlow, searchCapitalFlowSecurities } from "./api";
import type {
  CapitalFlowDashboard, CapitalFlowDimension, CapitalRiskDriver, DragonTigerData,
  FundFlowRow, MarginRow, NorthboundHistory, SectorFlow, SecuritySearchItem,
} from "./types";

type View = "overview" | "sectors" | "cross-border" | "liquidity" | "etf" | "emotion" | "security" | "dimensions";
type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;

const VIEW_META: Record<View, { title: string; description: string }> = {
  overview: { title: "资金总览", description: "成交、行业轮动与跨市场资金温度" },
  sectors: { title: "行业轮动", description: "观察行业资金净流与价格扩散" },
  "cross-border": { title: "跨境资金", description: "沪深港通官方快照与成交额历史" },
  liquidity: { title: "流动性", description: "货币信用、资金价格与市场传导" },
  etf: { title: "ETF 资金", description: "成交、份额、申赎与折溢价数据状态" },
  emotion: { title: "风险偏好", description: "行业、跨境与流动性驱动项" },
  security: { title: "个股资金", description: "主力资金、两融与龙虎榜" },
  dimensions: { title: "数据口径", description: "来源、频率、时滞与覆盖边界" },
};

const STATUS_LABEL = {
  ready: "已接入", degraded: "部分异常", "on-demand": "按需查询", planned: "待接入",
} as const;
const VIEW_BLOCKS: Record<View, ModPageContext["visibleBlocks"]> = {
  overview: [
    { id: "sector-flow", type: "capital-flow", title: "行业资金汇总" },
    { id: "turnover", type: "market-liquidity", title: "市场成交" },
  ],
  sectors: [
    { id: "sector-quadrant", type: "sector-rotation", title: "行业资金与价格轮动" },
    { id: "sector-ranking", type: "sector-ranking", title: "行业轮动明细" },
  ],
  "cross-border": [{ id: "cross-border", type: "cross-border-flow", title: "跨境资金" }],
  liquidity: [{ id: "liquidity", type: "macro-liquidity", title: "宏观流动性" }],
  etf: [{ id: "etf-flow", type: "etf-flow", title: "ETF 资金" }],
  emotion: [{ id: "capital-risk-appetite", type: "capital-risk-appetite", title: "资金风险偏好" }],
  security: [{ id: "security-flow", type: "security-flow", title: "个股资金" }],
  dimensions: [{ id: "dimensions", type: "data-status", title: "资金数据口径" }],
};

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

function number(value: unknown, digits = 2) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toLocaleString("zh-CN", { maximumFractionDigits: digits }) : "--";
}

function money(value: unknown) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "--";
  const absolute = Math.abs(parsed);
  if (absolute >= 100_000_000) return `${parsed < 0 ? "-" : ""}${number(absolute / 100_000_000)} 亿`;
  if (absolute >= 10_000) return `${parsed < 0 ? "-" : ""}${number(absolute / 10_000)} 万`;
  return number(parsed, 0);
}

function FundFlowTable({ rows }: { rows: FundFlowRow[] }) {
  if (!rows.length) return <div className="table-empty">主数据源与新浪回退源均未返回记录</div>;
  const sorted = [...rows].sort((left, right) => String(right.date ?? "").localeCompare(String(left.date ?? "")));
  return <div className="data-table fund-flow-table"><div className="data-row head">
    <span>日期</span><span>主力净流</span><span>超大单</span><span>大单</span><span>收盘</span><span>涨跌</span>
  </div>{sorted.slice(0, 20).map((row, index) => <div className="data-row" key={row.date ?? index}>
    <span>{row.date ?? "--"}</span>
    <span className={Number(row.main_net ?? 0) >= 0 ? "positive-text" : "negative-text"}>{money(row.main_net)}</span>
    <span>{row.super_net == null ? "--" : money(row.super_net)}</span>
    <span>{row.large_net == null ? "--" : money(row.large_net)}</span>
    <span>{row.close == null ? "--" : number(row.close)}</span>
    <span className={Number(row.change_pct ?? 0) >= 0 ? "positive-text" : "negative-text"}>{row.change_pct == null ? "--" : `${Number(row.change_pct) > 0 ? "+" : ""}${number(row.change_pct)}%`}</span>
  </div>)}</div>;
}

function MarginTable({ rows }: { rows: MarginRow[] }) {
  if (!rows.length) return <div className="table-empty">当前标的没有返回融资融券记录</div>;
  return <div className="data-table margin-table"><div className="data-row head">
    <span>日期</span><span>融资余额</span><span>融资买入</span><span>融资偿还</span><span>融券余额</span><span>两融余额</span>
  </div>{rows.slice(0, 20).map((row, index) => <div className="data-row" key={row.date ?? index}>
    <span>{row.date ?? "--"}</span><span>{money(row.rzye)}</span><span>{money(row.rzmre)}</span><span>{money(row.rzche)}</span><span>{money(row.rqye)}</span><span>{money(row.rzrqye)}</span>
  </div>)}</div>;
}

function DragonTigerPanel({ data }: { data?: DragonTigerData }) {
  const records = data?.records ?? [];
  const buySeats = data?.seats?.buy ?? [];
  const sellSeats = data?.seats?.sell ?? [];
  const institution = data?.institution;
  if (!records.length) return <div className="table-empty">近 30 日没有上榜记录；这不代表接口异常</div>;
  const seatList = (title: string, rows: typeof buySeats) => <div className="seat-list"><strong>{title}</strong>{rows.map((row, index) => <div key={`${row.name}-${index}`}><span>{row.name || "未命名席位"}</span><em className={Number(row.net ?? 0) >= 0 ? "positive-text" : "negative-text"}>{number(row.net, 0)} 万</em></div>)}</div>;
  return <div className="dragon-tiger-panel">
    <div className="institution-strip"><span>最近上榜 {records[0]?.date ?? "--"}</span><span>机构买入 <b>{number(institution?.buy_amt, 0)} 万</b></span><span>机构卖出 <b>{number(institution?.sell_amt, 0)} 万</b></span><span>机构净额 <b className={Number(institution?.net_amt ?? 0) >= 0 ? "positive-text" : "negative-text"}>{number(institution?.net_amt, 0)} 万</b></span></div>
    <div className="dt-records"><div className="dt-record head"><span>日期</span><span>上榜原因</span><span>净买额</span><span>换手</span></div>{records.map((row, index) => <div className="dt-record" key={`${row.date}-${index}`}><span>{row.date ?? "--"}</span><span title={row.reason}>{row.reason || "--"}</span><span className={Number(row.net_buy ?? 0) >= 0 ? "positive-text" : "negative-text"}>{number(row.net_buy, 0)} 万</span><span>{number(row.turnover)}%</span></div>)}</div>
    <div className="seat-grid">{seatList("买入席位 TOP5", buySeats)}{seatList("卖出席位 TOP5", sellSeats)}</div>
  </div>;
}

function buildContext(data: CapitalFlowDashboard | null, view: View, code: string, modId = "capital-flow"): ModPageContext {
  return {
    view: { id: modId, title: "资金面" },
    visibleBlocks: VIEW_BLOCKS[view],
    selection: code ? { securityCode: code } : {},
    filters: { view },
    data: { source: "vibe-research/a-stock-data", freshness: data?.upstream.status === "ready" ? "fresh" : "stale", ...(data ? { asOf: data.generatedAt, summary: data.summary } : {}) },
    actions: [{ id: "capital-flow.refresh", label: "刷新资金数据", available: true, inputSchema: { type: "object", additionalProperties: false } }],
    tasks: [],
  };
}

function FlowList({ title, rows }: { title: string; rows: SectorFlow[] }) {
  const scale = Math.max(...rows.map((item) => Math.abs(Number(item.net ?? 0))), 1);
  return <section className="flow-panel"><div className="section-title"><h2>{title}</h2><span>亿元</span></div>
    <div className="flow-list">{rows.map((item, index) => {
      const value = Number(item.net ?? 0);
      return <div className="flow-row" key={(item.name ?? "sector") + index}>
        <span className="rank">{String(index + 1).padStart(2, "0")}</span>
        <strong>{item.name ?? item.sector ?? item.industry ?? "未知行业"}</strong>
        <div className="flow-track"><i className={value >= 0 ? "positive" : "negative"} style={{ width: Math.max(6, Math.abs(value) / scale * 100) + "%" }} /></div>
        <em className={value >= 0 ? "positive-text" : "negative-text"}>{value > 0 ? "+" : ""}{number(value)}</em>
      </div>;
    })}</div>
  </section>;
}

type SectorSort = "net" | "pct" | "strength";

function sectorStrength(item: SectorFlow) {
  const gross = Math.abs(Number(item.inflow ?? 0)) + Math.abs(Number(item.outflow ?? 0));
  return gross ? Number(item.net ?? 0) / gross * 100 : 0;
}

function sectorPhase(item: SectorFlow) {
  const net = Number(item.net ?? 0);
  const pct = Number(item.pct ?? 0);
  if (net >= 0 && pct >= 0) return { id: "resonance", label: "资金价格共振" };
  if (net < 0 && pct >= 0) return { id: "distribution", label: "上涨但流出" };
  if (net >= 0 && pct < 0) return { id: "absorption", label: "下跌有承接" };
  return { id: "weakening", label: "资金价格走弱" };
}

function SectorQuadrant({ rows }: { rows: SectorFlow[] }) {
  const points = rows.filter((item) => Number.isFinite(Number(item.net)) && Number.isFinite(Number(item.pct)));
  if (!points.length) return <div className="table-empty">行业轮动数据暂不可用</div>;
  const width = 820;
  const height = 340;
  const padding = 38;
  const netScale = (value: number) => Math.sign(value) * Math.log10(1 + Math.abs(value));
  const maxX = Math.max(...points.map((item) => Math.abs(Number(item.pct))), 1);
  const maxY = Math.max(...points.map((item) => Math.abs(netScale(Number(item.net)))), 1);
  const x = (value: number) => width / 2 + value / maxX * (width / 2 - padding);
  const y = (value: number) => height / 2 - netScale(value) / maxY * (height / 2 - padding);
  const labeled = new Set([...points].sort((left, right) => Math.abs(Number(right.net)) - Math.abs(Number(left.net))).slice(0, 4));
  return <section className="sector-quadrant"><div className="section-title"><h2>资金 / 价格四象限</h2><span>纵轴净流为对数尺度</span></div>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="行业资金净流与涨跌幅四象限">
      <rect x={width / 2} y="0" width={width / 2} height={height / 2} className="quadrant resonance" />
      <rect x="0" y="0" width={width / 2} height={height / 2} className="quadrant absorption" />
      <rect x={width / 2} y={height / 2} width={width / 2} height={height / 2} className="quadrant distribution" />
      <rect x="0" y={height / 2} width={width / 2} height={height / 2} className="quadrant weakening" />
      <line x1={width / 2} x2={width / 2} y1="0" y2={height} />
      <line x1="0" x2={width} y1={height / 2} y2={height / 2} />
      <text x={width - 12} y={height / 2 - 10} textAnchor="end">涨幅 +</text>
      <text x="12" y={height / 2 - 10}>涨幅 -</text>
      <text x={width / 2 + 10} y="18">净流入 +</text>
      <text x={width / 2 + 10} y={height - 10}>净流出 -</text>
      {points.map((item, index) => {
        const phase = sectorPhase(item);
        const cx = x(Number(item.pct));
        const cy = y(Number(item.net));
        return <g key={(item.name ?? "sector") + index} className={`sector-point ${phase.id}`}>
          <circle cx={cx} cy={cy} r={labeled.has(item) ? 5 : 3.5}><title>{item.name} · {number(item.pct)}% · {number(item.net)} 亿 · {phase.label}</title></circle>
          {labeled.has(item) ? <text x={cx + 7} y={cy - 7}>{item.name}</text> : null}
        </g>;
      })}
    </svg>
    <div className="quadrant-legend"><span className="resonance">资金价格共振</span><span className="distribution">上涨但流出</span><span className="absorption">下跌有承接</span><span className="weakening">资金价格走弱</span></div>
  </section>;
}

function IndustryRotationView({ data }: { data: CapitalFlowDashboard }) {
  const [sort, setSort] = useState<SectorSort>("strength");
  const rows = useMemo(() => [...data.sectors].sort((left, right) => {
    if (sort === "pct") return Number(right.pct ?? 0) - Number(left.pct ?? 0);
    if (sort === "strength") return sectorStrength(right) - sectorStrength(left);
    return Number(right.net ?? 0) - Number(left.net ?? 0);
  }), [data.sectors, sort]);
  return <section className="capital-subview"><div className="section-heading"><div><span>SECTOR ROTATION</span><h2>资金与价格轮动</h2></div><p>{data.marketDate?.slice(0, 10) ?? "等待交易日"} · 行业板块口径</p></div>
    <div className="sector-analysis-grid"><SectorQuadrant rows={data.sectors} /><section className="sector-ranking"><div className="sector-ranking-head"><div><strong>轮动明细</strong><span>{rows.length} 个行业</span></div><div className="sector-sort" aria-label="行业排序">{(["strength", "net", "pct"] as SectorSort[]).map((item) => <button type="button" className={sort === item ? "active" : ""} onClick={() => setSort(item)} key={item}>{item === "strength" ? "资金强度" : item === "net" ? "净流" : "涨跌"}</button>)}</div></div>
      <div className="sector-table"><div className="sector-table-row head"><span>行业</span><span>涨跌</span><span>净流</span><span>强度</span><span>状态</span></div>{rows.map((item, index) => { const phase = sectorPhase(item); const strength = sectorStrength(item); return <div className="sector-table-row" key={(item.name ?? "sector") + index}><strong>{item.name ?? "未知行业"}<small>{number(item.firms, 0)} 家</small></strong><span className={Number(item.pct ?? 0) >= 0 ? "positive-text" : "negative-text"}>{Number(item.pct ?? 0) > 0 ? "+" : ""}{number(item.pct)}%</span><span className={Number(item.net ?? 0) >= 0 ? "positive-text" : "negative-text"}>{Number(item.net ?? 0) > 0 ? "+" : ""}{number(item.net)} 亿</span><span>{strength > 0 ? "+" : ""}{number(strength)}%</span><em className={`sector-phase ${phase.id}`}>{phase.label}</em></div>; })}</div>
    </section></div>
    <div className="evidence-note">行业分类沿用当前数据源板块口径，不等同于申万 2021 一级行业。资金强度 = 净流入 ÷（流入 + 流出），用于比较不同规模行业的资金方向。</div>
  </section>;
}

function DimensionRow({ item }: { item: CapitalFlowDimension }) {
  return <div className="dimension-row">
    <div><strong>{item.name}</strong><span>{item.source}</span></div>
    <em className={"status " + item.status}>{STATUS_LABEL[item.status]}</em>
    <span>{item.frequency}</span><span>{item.lag}</span><small>{item.note ?? "口径按主数据源披露执行"}</small>
  </div>;
}

function ConnectCard({ title, item }: { title: string; item: { turnoverYi?: number | null; buyYi?: number | null; sellYi?: number | null; netBuyYi?: number | null; etfTurnoverYi?: number | null; market?: string; unit?: string } }) {
  const unit = item.unit ?? "亿元";
  return <section className="connect-card"><div className="section-title"><h2>{title}</h2><span>{item.market ?? "HKEX"} · {unit}</span></div>
    <div className="connect-metrics"><div><small>总成交额</small><strong>{item.turnoverYi == null ? "--" : `${number(item.turnoverYi)} ${unit}`}</strong></div><div><small>ETF 成交额</small><strong>{item.etfTurnoverYi == null ? "--" : `${number(item.etfTurnoverYi)} ${unit}`}</strong></div><div><small>买入 / 卖出</small><strong>{item.buyYi == null || item.sellYi == null ? "官方未披露" : `${number(item.buyYi)} / ${number(item.sellYi)} ${unit}`}</strong></div><div><small>净买入</small><strong className={(item.netBuyYi ?? 0) >= 0 ? "positive-text" : "negative-text"}>{item.netBuyYi == null ? "不可计算" : `${item.netBuyYi > 0 ? "+" : ""}${number(item.netBuyYi)} ${unit}`}</strong></div></div>
  </section>;
}

function OfficialTurnoverBars({ history, unit = "人民币亿元" }: { history?: NorthboundHistory; unit?: string }) {
  const rows = (history?.points ?? []).slice(-20);
  if (!rows.length) return <div className="table-empty compact">{history?.reason ?? "官方成交额历史暂不可用"}</div>;
  const totals = rows.map((row) => Number(row.northTurnoverYi ?? 0));
  const max = Math.max(...totals, 1);
  const latest = rows.at(-1)!;
  const previous = rows.at(-2);
  const change = previous?.northTurnoverYi ? (Number(latest.northTurnoverYi ?? 0) / Number(previous.northTurnoverYi) - 1) * 100 : null;
  return <section className="turnover-history"><div className="section-title"><h2>北向成交额 · 近 20 个交易日</h2><span>{unit} · 非净流入</span></div>
    <div className="turnover-kpis"><div><small>最新成交额</small><strong>{number(latest.northTurnoverYi)} {unit}</strong></div><div><small>较前一日</small><strong className={(change ?? 0) >= 0 ? "positive-text" : "negative-text"}>{change == null ? "--" : `${change > 0 ? "+" : ""}${number(change)}%`}</strong></div><div><small>沪 / 深占比</small><strong>{number(Number(latest.sseTurnoverYi ?? 0) / Math.max(Number(latest.northTurnoverYi ?? 0), 1) * 100, 0)}% / {number(Number(latest.szseTurnoverYi ?? 0) / Math.max(Number(latest.northTurnoverYi ?? 0), 1) * 100, 0)}%</strong></div></div>
    <div className="turnover-bars" role="img" aria-label="北向成交额历史柱状图">{rows.map((row, index) => {
      const total = Number(row.northTurnoverYi ?? 0);
      const sse = Math.max(Number(row.sseTurnoverYi ?? 0), 0);
      const szse = Math.max(Number(row.szseTurnoverYi ?? 0), 0);
      return <div className="turnover-column" key={row.date} title={`${row.date} · ${number(total)} ${unit}`}><div className="turnover-bar" style={{ height: `${Math.max(total / max * 100, 2)}%` }}><i className="szse" style={{ flexGrow: szse }} /><i className="sse" style={{ flexGrow: sse }} /></div><span>{index % 5 === 0 || index === rows.length - 1 ? row.date.slice(5) : ""}</span></div>;
    })}</div>
    <div className="chart-legend"><span><i className="sse" />沪股通成交额</span><span><i className="szse" />深股通成交额</span><small>{rows[0]?.date} - {latest.date}</small></div>
  </section>;
}

function CrossBorderView({ data }: { data: CapitalFlowDashboard }) {
  const north = data.crossBorder?.northbound;
  const south = data.crossBorder?.southbound;
  const history = north?.history;
  const validation = history?.validation;
  const validationNote = validation?.status === "verified"
    ? `历史线已用 ${validation.date ?? north?.date ?? "同日"} HKEX 总成交额校验，偏差 ${number(validation.differencePct, 4)}%。`
    : history?.reason ?? "历史线尚未完成 HKEX 同日校验。";
  return <section className="capital-subview"><div className="section-heading"><div><span>CROSS-BORDER FLOW</span><h2>沪深港通成交结构</h2></div><p>{north?.date ?? data.marketDate?.slice(0, 10) ?? "等待交易日"} · 官方日成交口径</p></div>
    <div className="connect-grid"><ConnectCard title="沪股通 · 北向" item={north?.sse ?? {}} /><ConnectCard title="深股通 · 北向" item={north?.szse ?? {}} /><ConnectCard title="港股通沪 · 南向" item={south?.sse ?? {}} /><ConnectCard title="港股通深 · 南向" item={south?.szse ?? {}} /></div>
    <OfficialTurnoverBars history={history} unit={history?.unit ?? north?.unit} />
    <div className="evidence-note">快照来源：{north?.source ?? "HKEX 官方每日统计"}；历史来源：{history?.source ?? "Tushare moneyflow_hsgt"}。{validationNote} 北向按人民币亿元，南向按港元亿元。这里展示的是成交额，不是净流入；官方未披露买入/卖出拆分时，页面不会反推“净买入”。</div>
  </section>;
}

function LiquidityView({ data }: { data: CapitalFlowDashboard }) {
  const regime = data.liquidity?.regime;
  const rows = data.liquidity?.indicators ?? [];
  const groups = data.liquidity?.groups?.length
    ? data.liquidity.groups
    : [{ id: "liquidity", label: "流动性指标", indicators: rows }];
  const forecast = data.liquidity?.forecast;
  const signalLabel = { positive: "偏宽松", negative: "偏收紧", neutral: "中性", mixed: "分化", unknown: "未知" } as Record<string, string>;
  const forecastLabel = { supportive: "趋向宽松", restrictive: "趋向收紧", mixed: "方向分化" } as Record<string, string>;
  const sourceLabel = (row: Record<string, unknown>) => {
    const source = row.sourceLabel ?? row.source;
    if (typeof source === "string") return source;
    if (source && typeof source === "object") {
      const item = source as Record<string, unknown>;
      return String(item.label ?? item.id ?? "公开宏观数据");
    }
    return "公开宏观数据";
  };
  return <section className="capital-subview"><div className="section-heading"><div><span>MACRO LIQUIDITY</span><h2>流动性条件</h2></div><p>{data.liquidity?.source ?? "宏观监测"}</p></div>
    <div className="liquidity-regime"><strong>流动性状态</strong><b>{signalLabel[String(regime?.signal ?? "unknown")] ?? "未知"}</b><span>{String(regime?.summary ?? "等待指标更新")}</span></div>
    <div className="liquidity-kpis"><div><small>可用指标</small><strong>{data.liquidity?.coverage?.available ?? rows.length}/{data.liquidity?.coverage?.total ?? rows.length}</strong></div><div><small>5 日趋势基线</small><strong>{forecastLabel[String(forecast?.signal ?? "mixed")] ?? "待确认"}</strong></div><div><small>置信度</small><strong>{forecast?.confidence == null ? "--" : `${Math.round(Number(forecast.confidence) * 100)}%`}</strong></div><span>{forecast?.method ?? "样本不足，暂不外推"}</span></div>
    <div className="liquidity-groups">{groups.map((group) => <section className="liquidity-group" key={group.id}><div className="section-title"><h2>{group.label}</h2><span>{group.indicators.length} 项</span></div><div className="liquidity-table"><div className="liquidity-row head"><span>指标</span><span>最新值</span><span>变化</span><span>更新时间</span><span>来源</span></div>{group.indicators.map((row, index) => <div className="liquidity-row" key={String(row.id ?? index)}><strong>{String(row.name ?? row.id ?? "指标")}</strong><span>{row.value == null ? "--" : `${number(row.value)} ${String(row.unit ?? "")}`}</span><span className={Number(row.change ?? 0) >= 0 ? "positive-text" : "negative-text"}>{row.change == null ? "--" : number(row.change)}</span><span>{String(row.asOf ?? row.date ?? "--")}</span><small>{sourceLabel(row)} · {row.freshness && typeof row.freshness === "object" && (row.freshness as Record<string, unknown>).status === "fresh" ? "新鲜" : "需复核"}</small></div>)}</div></section>)}</div>
    <div className="evidence-note">{data.liquidity?.note ?? "数量、价格和市场传导分开统计，不合成为一个虚假总分。"}</div>
  </section>;
}

function driverLabel(signal: CapitalRiskDriver["signal"]) {
  return { supportive: "偏支持", restrained: "偏收紧", mixed: "分化", observed: "仅观测", unavailable: "未接入" }[signal];
}

function RiskAppetiteView({ data }: { data: CapitalFlowDashboard }) {
  const drivers = data.riskAppetite?.drivers ?? [];
  const available = data.riskAppetite?.available ?? 0;
  const total = data.riskAppetite?.total ?? drivers.length;
  return <section className="capital-subview"><div className="section-heading"><div><span>CAPITAL RISK APPETITE</span><h2>资金风险偏好</h2></div><p>{data.marketDate ?? "等待交易日"} · 只展示驱动项，不合成为预测分数</p></div>
    <div className="appetite-summary"><strong>{available}/{total}</strong><span>个资金驱动项可用</span><small>支持、收紧与分化状态来自各自数据口径</small></div>
    <div className="appetite-grid">{drivers.map((driver) => <article className={"appetite-driver " + driver.signal} key={driver.id}>
      <div className="appetite-driver-head"><span>{driver.name}</span><b>{driverLabel(driver.signal)}</b></div>
      <strong>{driver.value ?? "--"}</strong>
      <p>{driver.detail}</p>
      <small>{driver.source}{driver.asOf ? ` · ${driver.asOf}` : ""}</small>
    </article>)}</div>
    {!drivers.length ? <div className="table-empty">资金驱动数据暂不可用</div> : null}
    <div className="evidence-note">资金风险偏好不等于市场涨跌预测。行业资金、北向成交额、南向净买入、宏观流动性和成交活跃度必须分别核对来源与更新时间；ETF 申赎、全市场两融等尚未接入的维度不会用估算值补齐。</div>
  </section>;
}

export function CapitalFlowApp() {
  const moduleParams = useMemo(() => new URLSearchParams(window.location.search), []);
  const moduleId = moduleParams.get("mod") || "capital-flow";
  const requestedView = moduleParams.get("view") as View | null;
  const defaultView: View = requestedView && ["overview", "sectors", "cross-border", "liquidity", "etf", "emotion", "security", "dimensions"].includes(requestedView) ? requestedView : "overview";
  const embedded = window.parent !== window;
  const [data, setData] = useState<CapitalFlowDashboard | null>(null);
  const [view, setView] = useState<View>(defaultView);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [input, setInput] = useState("");
  const [code, setCode] = useState("");
  const [selectedSecurity, setSelectedSecurity] = useState<SecuritySearchItem | null>(null);
  const [suggestions, setSuggestions] = useState<SecuritySearchItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [host, setHost] = useState<EmbeddedHost>();

  const inflows = useMemo(() => (data?.sectors ?? []).filter((item) => Number(item.net) > 0).slice(0, 10), [data]);
  const outflows = useMemo(() => [...(data?.sectors ?? [])].filter((item) => Number(item.net) < 0).sort((a, b) => Number(a.net) - Number(b.net)).slice(0, 10), [data]);
  const contextRef = useRef(buildContext(data, view, code, moduleId));
  contextRef.current = buildContext(data, view, code, moduleId);

  useEffect(() => { document.title = VIEW_META[view].title + " · Newma-Desk"; if (!document.documentElement.dataset.theme) document.documentElement.dataset.theme = "dark"; }, [view]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    void fetchCapitalFlow(code || null, controller.signal).then(setData).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "资金数据读取失败");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [code, refreshKey]);

  useEffect(() => {
    const query = input.trim();
    if (query.length < 2 || query === selectedSecurity?.name) {
      setSuggestions([]);
      setSearching(false);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setSearching(true);
      void searchCapitalFlowSecurities(query, controller.signal)
        .then(setSuggestions)
        .catch(() => { if (!controller.signal.aborted) setSuggestions([]); })
        .finally(() => { if (!controller.signal.aborted) setSearching(false); });
    }, 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [input, selectedSecurity?.name]);

  useEffect(() => {
    const controller = new AbortController(); let close: () => void = () => undefined;
    void connectModHost({ modId: moduleId, parentOrigin: parentOrigin(), sdkVersion: "0.1.0", capabilities: ["actions", "context", "theme"], signal: controller.signal })
      .then((connection) => { if (!connection.embedded) { close = connection.close; return; } setHost(connection); close = connection.close; })
      .catch(() => undefined);
    return () => { controller.abort(); close(); };
  }, [moduleId]);
  useEffect(() => host?.setContextProvider(() => contextRef.current), [host]);
  useEffect(() => { host?.publishContext(contextRef.current); }, [code, data, host, view]);
  useEffect(() => host?.setUiActionHandler((actionId) => { if (actionId !== "capital-flow.refresh") throw new Error("资金面不支持动作 " + actionId); setRefreshKey((value) => value + 1); return { refreshed: true }; }), [host]);

  const selectSecurity = (item: SecuritySearchItem) => {
    setSelectedSecurity(item); setInput(item.name); setSuggestions([]); setError(""); setCode(item.symbol); setView("security");
  };
  const submitCode = async () => {
    const normalized = input.trim();
    if (/^\d{6}$/.test(normalized)) {
      const match = suggestions.find((item) => item.symbol === normalized);
      if (match) selectSecurity(match);
      else { setSelectedSecurity(null); setSuggestions([]); setError(""); setCode(normalized); setView("security"); }
      return;
    }
    const first = suggestions[0] ?? (await searchCapitalFlowSecurities(normalized).then((items) => items[0]).catch(() => undefined));
    if (!first) { setError("没有找到对应 A 股，请输入名称或 6 位代码"); return; }
    selectSecurity(first);
  };
  const fundRows = data?.security?.fundFlow ?? [];
  const marginRows = data?.security?.margin ?? [];
  const dragonTiger = data?.security?.dragonTiger;

  return <main className="capital-root">
    <header className="capital-header" data-embedded={embedded || undefined}>{!embedded ? <div data-mod-page-title><span>CAPITAL INTELLIGENCE</span><h1>{VIEW_META[view].title}</h1><p>{VIEW_META[view].description}</p></div> : null}
      <button onClick={() => setRefreshKey((value) => value + 1)} disabled={loading} title="刷新资金数据"><RefreshCw className={loading ? "spin" : ""} /><span>刷新</span></button>
    </header>
    {view === "overview" ? <section className="summary-strip" aria-label="资金面摘要">
      <div><Activity /><span>行业净流</span><strong className={(data?.summary.sectorNetYi ?? 0) >= 0 ? "positive-text" : "negative-text"}>{number(data?.summary.sectorNetYi)} 亿</strong><small>{data?.marketDate?.slice(0, 10) ?? "等待交易数据"}</small></div>
      <div><ArrowUpRight /><span>行业流入</span><strong>{number(data?.summary.sectorInflowYi)} 亿</strong><small>行业主动买入汇总</small></div>
      <div><ArrowDownRight /><span>行业流出</span><strong>{number(data?.summary.sectorOutflowYi)} 亿</strong><small>行业主动卖出汇总</small></div>
      <div><WalletCards /><span>成交额 TOP20</span><strong>{number(data?.summary.top20TurnoverYi)} 亿</strong><small>活跃度 {String(data?.summary.active ?? "--")}</small></div>
    </section> : null}
    {error ? <div className="error-banner">{error}</div> : null}
    {view === "overview" ? <section className="overview-grid">
      <FlowList title="净流入排行" rows={inflows} /><FlowList title="净流出排行" rows={outflows} />
      <section className="turnover-panel"><div className="section-title"><h2>成交额排行</h2><span>TOP 20</span></div><div className="turnover-list">{data?.turnoverLeaders.slice(0, 12).map((item, index) => <div key={item.code ?? index}><span>{index + 1}</span><strong>{item.name}</strong><small>{item.code} · {item.industry}</small><em>{number(Number(item.amount ?? 0) / 100000000)} 亿</em><b className={Number(item.pct) >= 0 ? "positive-text" : "negative-text"}>{Number(item.pct) > 0 ? "+" : ""}{number(item.pct)}%</b></div>)}</div></section>
    </section> : null}
    {view === "sectors" && data ? <IndustryRotationView data={data} /> : null}
    {view === "cross-border" && data ? <CrossBorderView data={data} /> : null}
    {view === "liquidity" && data ? <LiquidityView data={data} /> : null}
    {view === "etf" && data ? <section className="capital-subview"><div className="section-heading"><div><span>ETF FLOW</span><h2>ETF 数据覆盖</h2></div><p>份额申赎需基金公告或专用份额源，未接入时不展示估算值。</p></div><div className="etf-grid"><div className="evidence-note">当前可用：沪深港通 ETF 成交额已纳入跨境快照。</div><div className="dimensions-table">{data.dimensions.filter((item) => item.id === "etf").map((item) => <DimensionRow item={item} key={item.id} />)}</div></div></section> : null}
    {view === "emotion" && data ? <RiskAppetiteView data={data} /> : null}
    {view === "dimensions" ? <section className="dimensions-view"><div className="section-heading"><div><span>DATA CONTRACT</span><h2>资金数据口径</h2></div><p>不同频率与含义的数据分开观察，不合并成一个“总资金”数字。</p></div><div className="dimensions-table"><div className="dimension-row head"><span>维度 / 来源</span><span>状态</span><span>频率</span><span>滞后</span><span>口径说明</span></div>{data?.dimensions.map((item) => <DimensionRow item={item} key={item.id} />)}</div><div className="source-links">{data?.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.name}<ExternalLink /></a>)}</div></section> : null}
    {view === "security" ? <section className="security-view"><div className="security-search"><div><span>SECURITY FLOW</span><h2>标的查询</h2></div><div className="security-query"><label><Search /><input value={input} onChange={(event) => { setInput(event.target.value); setSelectedSecurity(null); }} onKeyDown={(event) => { if (event.key === "Enter") void submitCode(); }} placeholder="输入股票名称、简称或 6 位代码" /><button onClick={() => void submitCode()}>{searching ? "搜索中" : "查询"}</button></label>{suggestions.length ? <div className="security-suggestions">{suggestions.map((item) => <button type="button" key={`${item.market}-${item.symbol}`} onClick={() => selectSecurity(item)}><strong>{item.name}</strong><span>{item.symbol} · {item.exchange ?? "CN"}{item.industry ? ` · ${item.industry}` : ""}</span></button>)}</div> : null}</div></div>
      {!code ? <div className="empty-state">输入股票名称或代码，查看主力资金、融资融券与龙虎榜席位。</div> : <><div className="selected-security"><div><strong>{selectedSecurity?.name ?? code}</strong><span>{code}{selectedSecurity?.industry ? ` · ${selectedSecurity.industry}` : ""}</span></div><small>主力资金优先东财，空数据自动回退新浪；龙虎榜仅在上榜时有记录。</small></div><div className="security-grid"><section><div className="section-title"><h2>主力资金</h2><span>{fundRows.length} 条 · {fundRows[0]?.source === "sina-money-flow" ? "新浪回退" : "东财"}</span></div><FundFlowTable rows={fundRows} /></section><section><div className="section-title"><h2>融资融券</h2><span>{marginRows.length} 条</span></div><MarginTable rows={marginRows} /></section><section className="dragon-tiger-section"><div className="section-title"><h2>龙虎榜</h2><span>{dragonTiger?.records?.length ?? 0} 次上榜 · 东财席位</span></div><DragonTigerPanel data={dragonTiger} /></section></div></>}
    </section> : null}
  </main>;
}
