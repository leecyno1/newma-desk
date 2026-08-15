import {
  Activity, ArrowDownRight, ArrowUpRight, BarChart3, Database,
  ExternalLink, RefreshCw, Search, WalletCards,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ModPageContext } from "@newma-desk/contracts";
import { connectModHost, type ModHostConnection } from "@newma-desk/mod-sdk";

import { fetchCapitalFlow } from "./api";
import type { CapitalFlowDashboard, CapitalFlowDimension, SectorFlow } from "./types";

type View = "overview" | "dimensions" | "security";
type EmbeddedHost = Extract<ModHostConnection, { embedded: true }>;

const STATUS_LABEL = {
  ready: "已接入", degraded: "部分异常", "on-demand": "按需查询", planned: "待接入",
} as const;

function parentOrigin() {
  if (document.referrer) {
    try { return new URL(document.referrer).origin; } catch { /* current origin */ }
  }
  return window.location.origin;
}

function number(value: unknown, digits = 2) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toLocaleString("zh-CN", { maximumFractionDigits: digits }) : "--";
}

function unknownRows(value: unknown): Record<string, unknown>[] {
  if (Array.isArray(value)) return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
  if (!value || typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  for (const key of ["data", "items", "records", "list"]) {
    if (Array.isArray(record[key])) return unknownRows(record[key]);
  }
  return [record];
}

const FIELD_LABELS: Record<string, string> = {
  date: "日期", main_net: "主力净流", main_inflow: "主力流入", main_outflow: "主力流出",
  rzye: "融资余额", rzmre: "融资买入", rzche: "融资偿还", rqye: "融券余额",
  rqmcl: "融券卖出", rzrqye: "两融余额",
};

function SecurityTable({ rows, empty }: { rows: Record<string, unknown>[]; empty: string }) {
  if (!rows.length) return <div className="table-empty">{empty}</div>;
  const fields = Object.keys(rows[0]!).slice(0, 7);
  return <div className="data-table"><div className="data-row head">
    {fields.map((field) => <span key={field}>{FIELD_LABELS[field] ?? field}</span>)}
  </div>{rows.slice(0, 15).map((row, index) => <div className="data-row" key={String(row.date ?? index)}>
    {fields.map((field) => <span key={field}>{typeof row[field] === "number" && field !== "date" ? number(Number(row[field]) / 100000000) + " 亿" : String(row[field] ?? "--")}</span>)}
  </div>)}</div>;
}

function buildContext(data: CapitalFlowDashboard | null, view: View, code: string): ModPageContext {
  return {
    view: { id: "capital-flow", title: "资金面" },
    visibleBlocks: [
      { id: "sector-flow", type: "capital-flow", title: "行业资金" },
      { id: "turnover", type: "market-liquidity", title: "市场成交" },
      { id: "dimensions", type: "data-status", title: "资金维度" },
    ],
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

function DimensionRow({ item }: { item: CapitalFlowDimension }) {
  return <div className="dimension-row">
    <div><strong>{item.name}</strong><span>{item.source}</span></div>
    <em className={"status " + item.status}>{STATUS_LABEL[item.status]}</em>
    <span>{item.frequency}</span><span>{item.lag}</span><small>{item.note ?? "口径按主数据源披露执行"}</small>
  </div>;
}

export function CapitalFlowApp() {
  const [data, setData] = useState<CapitalFlowDashboard | null>(null);
  const [view, setView] = useState<View>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [input, setInput] = useState("");
  const [code, setCode] = useState("");
  const [host, setHost] = useState<EmbeddedHost>();

  const inflows = useMemo(() => (data?.sectors ?? []).filter((item) => Number(item.net) > 0).slice(0, 10), [data]);
  const outflows = useMemo(() => [...(data?.sectors ?? [])].filter((item) => Number(item.net) < 0).sort((a, b) => Number(a.net) - Number(b.net)).slice(0, 10), [data]);
  const contextRef = useRef(buildContext(data, view, code));
  contextRef.current = buildContext(data, view, code);

  useEffect(() => { document.title = "资金面 · Newma-Desk"; if (!document.documentElement.dataset.theme) document.documentElement.dataset.theme = "dark"; }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    void fetchCapitalFlow(code || null, controller.signal).then(setData).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "资金数据读取失败");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [code, refreshKey]);

  useEffect(() => {
    const controller = new AbortController(); let close: () => void = () => undefined;
    void connectModHost({ modId: "capital-flow", parentOrigin: parentOrigin(), sdkVersion: "0.1.0", capabilities: ["actions", "context", "theme"], signal: controller.signal })
      .then((connection) => { if (!connection.embedded) { close = connection.close; return; } setHost(connection); close = connection.close; })
      .catch(() => undefined);
    return () => { controller.abort(); close(); };
  }, []);
  useEffect(() => host?.setContextProvider(() => contextRef.current), [host]);
  useEffect(() => { host?.publishContext(contextRef.current); }, [code, data, host, view]);
  useEffect(() => host?.setUiActionHandler((actionId) => { if (actionId !== "capital-flow.refresh") throw new Error("资金面不支持动作 " + actionId); setRefreshKey((value) => value + 1); return { refreshed: true }; }), [host]);

  const submitCode = () => {
    const normalized = input.trim();
    if (!/^\d{6}$/.test(normalized)) { setError("请输入 6 位股票代码"); return; }
    setError(""); setCode(normalized); setView("security");
  };
  const fundRows = unknownRows(data?.security?.fundFlow);
  const marginRows = unknownRows(data?.security?.margin);

  return <main className="capital-root">
    <header className="capital-header"><div><span>CAPITAL FLOW</span><h1>资金面</h1><p>市场成交、行业轮动、跨境资金与杠杆流动</p></div>
      <button onClick={() => setRefreshKey((value) => value + 1)} disabled={loading} title="刷新资金数据"><RefreshCw className={loading ? "spin" : ""} /><span>刷新</span></button>
    </header>
    <section className="summary-strip" aria-label="资金面摘要">
      <div><Activity /><span>行业净流</span><strong className={(data?.summary.sectorNetYi ?? 0) >= 0 ? "positive-text" : "negative-text"}>{number(data?.summary.sectorNetYi)} 亿</strong><small>{data?.marketDate?.slice(0, 10) ?? "等待交易数据"}</small></div>
      <div><ArrowUpRight /><span>行业流入</span><strong>{number(data?.summary.sectorInflowYi)} 亿</strong><small>行业主动买入汇总</small></div>
      <div><ArrowDownRight /><span>行业流出</span><strong>{number(data?.summary.sectorOutflowYi)} 亿</strong><small>行业主动卖出汇总</small></div>
      <div><WalletCards /><span>成交额 TOP20</span><strong>{number(data?.summary.top20TurnoverYi)} 亿</strong><small>活跃度 {String(data?.summary.active ?? "--")}</small></div>
    </section>
    <nav className="capital-tabs">
      <button className={view === "overview" ? "active" : ""} onClick={() => setView("overview")}><BarChart3 />资金总览</button>
      <button className={view === "dimensions" ? "active" : ""} onClick={() => setView("dimensions")}><Database />维度与口径</button>
      <button className={view === "security" ? "active" : ""} onClick={() => setView("security")}><Search />个股资金</button>
      <span className={"upstream " + (data?.upstream.status ?? "degraded")}>{data?.upstream.status === "ready" ? "数据已更新" : "上游部分异常"}</span>
    </nav>
    {error ? <div className="error-banner">{error}</div> : null}
    {view === "overview" ? <section className="overview-grid">
      <FlowList title="净流入排行" rows={inflows} /><FlowList title="净流出排行" rows={outflows} />
      <section className="turnover-panel"><div className="section-title"><h2>成交额排行</h2><span>TOP 20</span></div><div className="turnover-list">{data?.turnoverLeaders.slice(0, 12).map((item, index) => <div key={item.code ?? index}><span>{index + 1}</span><strong>{item.name}</strong><small>{item.code} · {item.industry}</small><em>{number(Number(item.amount ?? 0) / 100000000)} 亿</em><b className={Number(item.pct) >= 0 ? "positive-text" : "negative-text"}>{Number(item.pct) > 0 ? "+" : ""}{number(item.pct)}%</b></div>)}</div></section>
    </section> : null}
    {view === "dimensions" ? <section className="dimensions-view"><div className="section-heading"><div><span>DATA CONTRACT</span><h2>资金维度与统计口径</h2></div><p>不同频率与含义的数据分开观察，不合并成一个“总资金”数字。</p></div><div className="dimensions-table"><div className="dimension-row head"><span>维度 / 来源</span><span>状态</span><span>频率</span><span>滞后</span><span>口径说明</span></div>{data?.dimensions.map((item) => <DimensionRow item={item} key={item.id} />)}</div><div className="source-links">{data?.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.name}<ExternalLink /></a>)}</div></section> : null}
    {view === "security" ? <section className="security-view"><div className="security-search"><div><span>SECURITY FLOW</span><h2>个股资金与融资融券</h2></div><label><Search /><input inputMode="numeric" maxLength={6} value={input} onChange={(event) => setInput(event.target.value.replace(/\D/g, ""))} onKeyDown={(event) => { if (event.key === "Enter") submitCode(); }} placeholder="输入 6 位股票代码" /><button onClick={submitCode}>查询</button></label></div>
      {!code ? <div className="empty-state">输入股票代码，按日查看资金流与两融数据。</div> : <div className="security-grid"><section><div className="section-title"><h2>{code} 个股资金</h2><span>{fundRows.length} 条</span></div><SecurityTable rows={fundRows} empty="当前数据源没有返回个股资金记录" /></section><section><div className="section-title"><h2>融资融券</h2><span>{marginRows.length} 条</span></div><SecurityTable rows={marginRows} empty="当前数据源没有返回两融记录" /></section></div>}
    </section> : null}
  </main>;
}
