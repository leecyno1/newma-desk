import type { TurnoverLeader, TurnoverSnapshot } from "./types";
import { TurnoverHistory, type useTurnoverHistory } from "./TurnoverHistory";

const fmt = (value: number | null | undefined, digits = 2) => value == null ? "--" : value.toLocaleString("zh-CN", { maximumFractionDigits: digits });

export function TurnoverPanel({ data, loading, select, history }: {
  data?: TurnoverSnapshot; loading: boolean; select: (row: TurnoverLeader) => void;
  history: ReturnType<typeof useTurnoverHistory>;
}) {
  const summary = data?.summary;
  return <section className="turnover-panel" aria-label="收盘成交活跃度">
    <div className="section-title"><h2>成交活跃度</h2><span>收盘快照 · 非净流入</span></div>
    <div className="turnover-stamp"><strong>{data?.asOf ?? "尚无行情日期"}</strong><span>{loading ? "正在更新" : data?.current ? "当日样本可用" : "未确认 / 保留快照"}</span></div>
    <div className="turnover-summary">
      <div><small>样本成交 · 亿元</small><strong>{fmt(summary?.sampleTurnoverYi)}</strong></div>
      <div><small>前20成交 · 亿元</small><strong>{fmt(summary?.top20TurnoverYi)}</strong></div>
      <div><small>前20占样本</small><strong>{fmt(summary?.top20SharePct)}{summary?.top20SharePct != null ? "%" : ""}</strong></div>
    </div>
    <p className="turnover-scope">{data?.coverage ? `${data.coverage.sampleCount.toLocaleString("zh-CN")} 只有效样本 · 名称匹配 ${data.coverage.namesMatched.toLocaleString("zh-CN")} 只` : "尚未取得样本覆盖"} · 非全市场总额</p>
    {data?.reason && <p className="turnover-warning">{data.reason}</p>}
    {data && !data.current && <p className="turnover-warning">目标交易日 {data.expectedDate ?? "未确认"}；以上数值不可作为本次已确认行情。</p>}
    <div className="turnover-venues">{data?.exchanges.map(row => <div key={row.id}><span>{row.name} · {row.count}只</span><b>{fmt(row.turnoverYi)} 亿</b></div>)}</div>
    <TurnoverHistory {...history} />
    <div className="section-title"><h2>样本成交额排行</h2><span>TOP {data?.leaders.length || 20} · 人民币亿元</span></div>
    {!data?.leaders.length ? <div className="table-empty compact">{loading ? "正在读取收盘成交榜…" : "成交榜暂无可核验记录"}</div> : null}
    <div className="turnover-list">{data?.leaders.map((row, index) => <button type="button" key={row.code ?? index} disabled={!row.code} onClick={() => select(row)}>
      <span>{index + 1}</span><strong>{row.name || row.code}</strong><small>{row.code} · {row.industry || "行业未匹配"}</small>
      <em>{fmt(row.amount == null ? null : row.amount / 1e8)}</em><b className={row.pct == null ? "" : row.pct >= 0 ? "positive-text" : "negative-text"}>{row.pct == null ? "--" : `${row.pct > 0 ? "+" : ""}${fmt(row.pct)}%`}</b>
    </button>)}</div>
    <details className="turnover-method"><summary>来源与统计边界</summary><p>{data?.source ?? "Tushare daily"} · 原始千元转人民币亿元。取昨日及以前最近交易日，不提供盘中行情。</p><p>{data?.note ?? "成交额不等于资金净流入"}</p><p>{data?.nameNote}</p><p>剔除错误日期/非目标股票 {data?.coverage?.rejected ?? "--"} 条；金额缺失/冲突 {data?.coverage?.invalid ?? "--"} 只。缺口存在时不计算合计和集中度；交易所未返回不补零。</p><a href="https://tushare.pro/document/2?doc_id=27" target="_blank" rel="noreferrer">Tushare 日线字段说明 ↗</a></details>
  </section>;
}
