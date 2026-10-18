import { useEffect, useRef, useState } from "react";
import type { MarketDataSource, SentimentHistory } from "../types";

export type HistoryState = { status: "loading" | "loaded" | "error"; data: SentimentHistory | null; error?: string };
const format = (value: number | null | undefined, suffix = "") => value == null ? "—" : `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${suffix}`;

export function SentimentHistoryPanel({ dataSource, refreshNonce, onChange }: {
  dataSource: Pick<MarketDataSource, "sentimentHistory">; refreshNonce: number; onChange: (state: HistoryState) => void;
}) {
  const [batch, setBatch] = useState(0);
  const lastRefresh = useRef(0);
  const [state, setState] = useState<HistoryState>({ status: "loading", data: null });
  useEffect(() => {
    let active = true;
    setState({ status: "loading", data: null });
    const refresh = refreshNonce !== lastRefresh.current;
    lastRefresh.current = refreshNonce;
    void dataSource.sentimentHistory(refresh).then(data => {
      if (active) setState({ status: "loaded", data });
    }).catch(error => {
      if (active) setState({ status: "error", data: null, error: error instanceof Error ? error.message : "历史读取失败" });
    });
    return () => { active = false; };
  }, [dataSource, refreshNonce, batch]);
  useEffect(() => onChange(state), [state, onChange]);
  const data = state.data, summary = data?.current ? data.summary : null;
  const points = data?.points || [];
  const x = (index: number) => 42 + index * 716 / Math.max(1, points.length - 1);
  const y = (value: number) => 166 - value * 1.4;
  const path = data?.current ? points.map((point, index) => `${index ? "L" : "M"}${x(index)},${y(point.upRatioPct!)}`).join(" ") : "";
  return <section className="sentiment-panel sentiment-history" aria-label="20交易日参与度趋势">
    <div className="workspace-section-title"><span>20交易日参与度 · 固定共同样本</span><small>{data ? `${data.completed} / ${data.expected} 日就绪` : state.status === "loading" ? "读取中" : "读取失败"}</small></div>
    {state.status === "loading" ? <p className="sentiment-note" role="status">正在读取或补齐历史，本次最多8个交易日；旧趋势已撤下。</p> : null}
    {state.status === "error" ? <p className="workspace-error-banner" role="alert">{state.error}；历史曲线与旧结论已撤下，不影响上方独立的日终统计。</p> : null}
    {data ? <>
      <div className="sentiment-history-metrics">
        <div><span>共同样本最新上涨占比</span><strong>{format(summary?.latestUpRatioPct, "%")}</strong><small>样本不同，可与上方单日值不同</small></div>
        <div><span>近5日均值 / 此前5日</span><strong>{format(summary?.mean5Pct, "%")} / {format(summary?.previous5Pct, "%")}</strong><small>均为每日上涨占比的均值</small></div>
        <div><span>五日均值变化</span><strong>{format(summary?.change5Pp, " 个百分点")}</strong><small>不是收益率变化</small></div>
        <div><span>上涨家数过半天数</span><strong>{format(summary?.aboveHalfDays)} / 20</strong><small>参考50%分界，不是交易信号</small></div>
      </div>
      {data.current ? <div className="sentiment-history-chart">
        <svg viewBox="0 0 800 200" role="img" aria-label="固定共同样本每日上涨占比，纵轴0至100%">
          {[0, 50, 100].map(value => <g key={value}><line x1="42" x2="758" y1={y(value)} y2={y(value)} className={value === 50 ? "midline" : "gridline"} /><text x="2" y={y(value) + 4}>{value}%</text></g>)}
          <path d={path} className="breadth-line" />
          {points.map((point, index) => <circle key={point.date} cx={x(index)} cy={y(point.upRatioPct!)} r="3"><title>{point.date}：{format(point.upRatioPct, "%")} · 固定样本 {data.commonCount} 只</title></circle>)}
          {[0, Math.floor(points.length / 2), points.length - 1].map(index => <text key={index} x={x(index)} y="191" textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"}>{points[index]?.date}</text>)}
        </svg>
      </div> : <p className="sentiment-note">{data.reason}；不跨缺口连线，不用剩余日期计算趋势均值。</p>}
      <p className="sentiment-note">{data.start || "待核验"} — {data.asOf || "待核验"} · 共同样本 {data.commonCount.toLocaleString()} 只 · {data.source} · 日终非实时</p>
      <details className="sentiment-method"><summary>逐日覆盖与统计口径{data.missingDates.length ? ` · 缺 ${data.missingDates.length} 日` : ""}</summary>
        <p>{data.note}</p>
        <div className="sentiment-history-table"><table><thead><tr><th>交易日</th><th>状态</th><th>当日有效样本</th><th>共同池外排除</th><th>上涨占比</th><th>涨跌幅中位数</th></tr></thead><tbody>{points.map(point => <tr key={point.date}>
          <td>{point.date}</td><td title={point.reason}>{point.status === "ready" ? "已取得" : "缺失"}</td><td>{format(point.sampleCount)}</td><td>{format(point.excludedCount)}</td><td>{format(point.upRatioPct, "%")}</td><td>{format(point.medianPct, "%")}</td>
        </tr>)}</tbody></table></div>
      </details>
    </> : null}
    {state.status !== "loading" && (!data || data.canContinue || data.failedDates.length > 0) ? <button type="button" className="workspace-button" onClick={() => setBatch(value => value + 1)}>{data?.canContinue ? "补齐下一批历史" : "重试历史数据"}</button> : null}
  </section>;
}
