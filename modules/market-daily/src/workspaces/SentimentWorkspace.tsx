import { Activity, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { MarketDataSource, MarketOverview } from "../types";
import { SentimentHistoryPanel, type HistoryState } from "./SentimentHistoryPanel";
import { LimitBoardsPanel, type BoardState } from "./LimitBoardsPanel";

type LoadState = { status: "loading" | "loaded" | "error"; data?: MarketOverview; error?: string };
const count = (value: unknown): number | null => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
const numeric = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const display = (value: number | null, suffix = "") => value === null ? "—" : `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${suffix}`;

export function sentimentEvidence(state: LoadState) {
  const source = state.status === "loaded" ? state.data : undefined;
  const sentiment = source?.sentiment;
  const up = count(sentiment?.up), down = count(sentiment?.down), flat = count(sentiment?.flat);
  const zt = count(sentiment?.zt), dt = count(sentiment?.dt);
  const total = up !== null && down !== null && flat !== null ? up + down + flat : null;
  const limitTotal = zt !== null && dt !== null ? zt + dt : null;
  const reasons: string[] = [];
  for (const [key, feed] of Object.entries(source?.sources || {})) {
    if (feed.status !== "ready") reasons.push(`${key === "sentiment" ? "涨跌统计" : "行业截面"}：${feed.reason}`);
  }
  if (total === null) reasons.push("上涨、下跌或平盘家数缺失／无效，不补零");
  else if (total === 0) reasons.push("涨跌平样本合计为零，不能计算参与率");
  if (!source?.sample && limitTotal === null) reasons.push("涨停或跌停家数缺失／无效，不补中性值");
  else if (!source?.sample && limitTotal === 0) reasons.push("来源报告涨跌停均为零，涨停占比无分母");
  const inconsistent = (zt !== null && up !== null && zt > up) || (dt !== null && down !== null && dt > down);
  if (inconsistent) reasons.push("涨跌停家数超过对应涨跌家数，统计口径待核验");
  const rawDate = sentiment?.date?.trim() || "";
  const match = rawDate.match(/^(\d{4})[-/](\d{2})[-/](\d{2})(?:\s|T|$)/);
  const date = match ? `${match[1]}-${match[2]}-${match[3]}` : null;
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const dateValid = date && Number.isFinite(Date.parse(date)) && new Date(date).toISOString().slice(0, 10) === date && date <= today;
  const asOf = dateValid ? date : null;
  const currentSession = Boolean(asOf && source?.session?.current && source.session.calendarStatus === "ready" && !source.session.usingSaved && source.session.expectedDate === asOf);
  if (!asOf) reasons.push("来源统计日期缺失／无效；接口获取时间不能代替行情日期");
  const sectors = (source?.sectors || []).slice(0, 12).map(item => ({
    name: item.name, pct: numeric(item.pct), netYi: item.metric === "large-order-net" ? numeric(item.net) : null,
    asOf: item.asOf || null, source: item.source || null,
  }));
  return {
    workspace: "sentiment", market: "CN", status: state.status === "loaded" ? reasons.length ? "partial" : "available" : state.status,
    error: state.error || "", source: sentiment?.source || "market.overview · 来源未标注",
    scope: sentiment?.scope || "来源返回的A股样本，覆盖范围待核验", asOf, retrievedAt: source?.updated || null,
    freshness: currentSession ? "fresh" as const : asOf && asOf < today ? "stale" as const : "unknown" as const,
    freshnessNote: currentSession ? "已核对昨日及以前最近交易日；日终样本，非盘中实时" : asOf && asOf < today ? "历史日期统计；未确认目标交易日，不代表当前盘中状态" : "未确认目标交易日，不标记为实时",
    sample: source?.sample || null, coverage: source?.coverage || null, session: source?.session || null,
    breadth: { up, down, flat, total, upRatioPct: total && !inconsistent ? up! / total * 100 : null },
    limitBoard: { up: zt, down: dt, total: limitTotal, upSharePct: limitTotal && !inconsistent ? zt! / limitTotal * 100 : null },
    sectors, reasons,
    sources: source?.sources || {},
    method: "上涨占比=上涨/(上涨+下跌+平盘)；涨停占比=涨停/(涨停+跌停)，不是封板率。不再计算70/30混合情绪分数。",
    sectorNote: "仅展示来源排序前12项，不代表行业扩散全貌；大单净额为供应商划单口径，不是新增资金，不汇总。",
  };
}

export function SentimentWorkspace({ dataSource, refreshNonce, onContextChange }: {
  dataSource: Pick<MarketDataSource, "sentiment" | "sentimentHistory" | "limitBoards">; refreshNonce: number; onContextChange: (state: Record<string, unknown>) => void;
}) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [history, setHistory] = useState<HistoryState>({ status: "loading", data: null });
  const [boards, setBoards] = useState<BoardState>({ status: "loading", data: null, selectedPool: "U" });
  useEffect(() => {
    let active = true;
    setState({ status: "loading" });
    void dataSource.sentiment(refreshNonce > 0).then(data => {
      if (active) setState({ status: "loaded", data });
    }).catch(reason => {
      if (active) setState({ status: "error", error: reason instanceof Error ? reason.message : "市场统计读取失败" });
    });
    return () => { active = false; };
  }, [dataSource, refreshNonce]);
  const evidence = useMemo(() => sentimentEvidence(state), [state]);
  useEffect(() => onContextChange({ ...evidence, history, boards }), [evidence, history, boards, onContextChange]);
  const { breadth, limitBoard } = evidence;
  return <div className="sentiment-workspace" aria-label="市场情绪研究">
    <section className="sentiment-hero">
      <div className="workspace-section-title"><span><Activity size={15} />A股市场参与度</span><small>{evidence.status === "loading" ? "读取中" : evidence.status === "error" ? "读取失败" : evidence.status === "partial" ? "证据不完整" : "已取得来源统计"}</small></div>
      <div className="sentiment-evidence-metrics">
        <div><span>上涨占比 · 含平盘分母</span><strong>{display(breadth.upRatioPct, "%")}</strong><small>上涨 / 涨跌平合计</small></div>
        {evidence.sample ? <div><span>样本涨跌幅中位数</span><strong>{display(numeric(evidence.sample.medianPct), "%")}</strong><small>不是指数收益率或资金净流入</small></div> : <div><span>涨停占涨跌停比例</span><strong>{display(limitBoard.upSharePct, "%")}</strong><small>不是封板率，也不是胜率</small></div>}
        <div><span>涨跌平样本合计</span><strong>{display(breadth.total)}</strong><small>来源覆盖，不宣称交易所全集</small></div>
      </div>
      <p className="sentiment-note">统计日：{evidence.asOf || "未核验"} · 接口获取：{evidence.retrievedAt || "未取得"}<br />{evidence.source} · {evidence.freshnessNote}</p>
      {state.status === "loading" ? <p className="sentiment-note" role="status"><RefreshCw size={14} />正在读取市场统计；上一批数据已撤下。</p> : null}
      {state.status === "error" ? <p className="workspace-error-banner" role="alert">{evidence.error}；旧数据与旧判断已撤下，请刷新重试。</p> : null}
      {state.status === "loaded" && evidence.reasons.length > 0 ? <ul className="sentiment-evidence-gaps">{evidence.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul> : null}
    </section>
    <section className="sentiment-grid">
      <div className="sentiment-panel">
        <div className="workspace-section-title"><span>涨跌家数 · 有效行情样本</span></div>
        <div className="sentiment-stats">
          <div><span>上涨</span><strong>{display(breadth.up)}</strong></div>
          <div><span>下跌</span><strong>{display(breadth.down)}</strong></div>
          <div><span>平盘</span><strong>{display(breadth.flat)}</strong></div>
          {evidence.sample ? <div><span>缺涨跌幅</span><strong>{display(count(evidence.sample.missingPctCount))}</strong></div> : <div><span>涨停 / 跌停</span><strong>{display(limitBoard.up)} / {display(limitBoard.down)}</strong></div>}
        </div>
        <p className="sentiment-note">{evidence.scope}</p>
        {evidence.sample ? <p className="sentiment-note">收到 {display(count(evidence.coverage?.received))} 条 · 有效涨跌样本 {display(count(evidence.sample.validCount))} 只<br />零成交或无效价格排除 {display(count(evidence.sample.inactiveCount))} 只 · 缺涨跌幅 {display(count(evidence.sample.missingPctCount))} 只 · 日期／代码异常 {display(count(evidence.coverage?.rejected))} 条 · 金额异常／冲突 {display(count(evidence.coverage?.invalid))} 只</p> : null}
      </div>
      <div className="sentiment-panel">
        <div className="workspace-section-title"><span>涨跌分布 · 同日同样本</span><small>不按涨幅推断涨跌停</small></div>
        <div className="sentiment-distribution" aria-label="样本涨跌分布">{evidence.sample?.buckets.map(bucket => <div key={bucket.label}>
          <span>{bucket.label}</span><meter min={0} max={breadth.total || 1} value={bucket.count} aria-label={bucket.label} /><strong>{display(count(bucket.count))}</strong>
        </div>)}{!evidence.sample ? <p>涨跌分布未取得，不以零替代。</p> : null}</div>
        <p className="sentiment-note">仅支持日终参与度判断。上涨占比高不等于买入信号；行业资金与ETF大额申赎在资金模块交叉核验。涨跌停缺数不补零，也不是封板率。</p>
      </div>
    </section>
    <SentimentHistoryPanel dataSource={dataSource} refreshNonce={refreshNonce} onChange={setHistory} />
    <LimitBoardsPanel dataSource={dataSource} refreshNonce={refreshNonce} onChange={setBoards} />
    <details className="sentiment-method"><summary>统计口径与使用边界</summary><p>{evidence.method}</p><p>行业资金与ETF申赎沿用资金模块，不将不同样本、不同日期的数据拼成情绪分数。</p></details>
  </div>;
}
