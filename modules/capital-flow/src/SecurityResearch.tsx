import { FlowBars } from "./FundingResearch";
import type { DragonTigerData, SecurityCoverage, SecurityResearchData, SecurityResearchPoint } from "./types";

const value = (v: number | null | undefined, digits = 2) => v == null ? "--" : v.toLocaleString("zh-CN", { maximumFractionDigits: digits });
const signed = (v: number | null | undefined) => v == null ? "--" : `${v > 0 ? "+" : ""}${value(v)}`;
const tone = (v: number | null | undefined) => v == null || v === 0 ? "" : v > 0 ? "positive-text" : "negative-text";

function PriceTrace({ points }: { points: SecurityResearchPoint[] }) {
  const first = points[0]?.adjustedValue;
  const values = points.map(point => first && point.adjustedValue != null ? point.adjustedValue / first * 100 : null);
  const known = values.filter((v): v is number => v !== null);
  const min = Math.min(99, ...known) - 1, max = Math.max(101, ...known) + 1;
  const coordinate = (v: number, index: number) => `${14 + index / Math.max(1, values.length - 1) * 732},${158 - (v - min) / (max - min) * 118}`;
  const segments: string[] = [];
  values.forEach((v, index) => { if (v == null) return; segments.push(`${index && values[index - 1] != null ? "L" : "M"}${coordinate(v, index)}`); });
  return <div className="research-chart security-price-trace"><svg viewBox="0 0 760 210" role="img" aria-label="复权价格指数历史">
    <text x="14" y="15">100 → {value(values.at(-1))}</text><text x="746" y="15" textAnchor="end">窗口首日=100 · 除权调整</text>
    <line x1="14" x2="746" y1={158 - (100 - min) / (max - min) * 118} y2={158 - (100 - min) / (max - min) * 118} className="research-zero" />
    <path d={segments.join(" ")} fill="none" stroke="var(--vibe-accent)" strokeWidth="2" />
    {points.map((point, index) => <g key={point.date}>
      <title>{point.date} · 复权指数 {value(values[index])}{point.factorChanged ? " · 复权因子变化" : ""}</title>
      {values[index] == null ? <text x={14 + index / Math.max(1, values.length - 1) * 732} y="174" textAnchor="middle">缺</text> : point.factorChanged ? <circle cx={coordinate(values[index]!, index).split(",")[0]} cy={coordinate(values[index]!, index).split(",")[1]} r="4" fill="var(--vibe-accent)" /> : null}
      {(index === 0 || index === points.length - 1 || index % 5 === 0) && <text x={14 + index / Math.max(1, values.length - 1) * 732} y="192" textAnchor="middle">{point.date.slice(5)}</text>}
    </g>)}
  </svg><small>{first ? "圆点标记复权因子变化；缺失断线，不跨日补值。" : "窗口首日价格或复权因子缺失，不生成基准指数；请核对来源。"}</small></div>;
}

export function dragonReview(data?: DragonTigerData, coverage?: SecurityCoverage) {
  if (!coverage) return "龙虎榜正在读取或未取得来源状态，暂不判断是否上榜。";
  if (coverage?.status === "unavailable") return "龙虎榜来源失败，不能判断是否上榜。";
  const records = data?.records ?? [];
  if (!records.length) return "近30自然日查询未返回记录；无记录不代表资金为零或低风险。";
  const days = new Set(records.map(row => row.date).filter(Boolean)).size;
  return `${days} 个披露日 / ${records.length} 条上榜理由；同日多理由及三日榜可能重叠，不累计净买额。机构专用席位不是基金持续持仓。`;
}

export function SecurityResearch({ data, loading, error, days, setDays, dragonTiger, dragonCoverage, disclosureReview }: {
  data: SecurityResearchData | null; loading: boolean; error: string; days: number; setDays: (days: number) => void;
  dragonTiger?: DragonTigerData; dragonCoverage?: SecurityCoverage;
  disclosureReview?: string;
}) {
  const points = data?.points.slice(-days) ?? [], latest = data?.points.at(-1);
  return <section className="funding-research security-research" aria-label="个股资金持续性研究">
    <div className="research-heading"><div><span>ORDER FLOW / LEVERAGE</span><h2>资金持续性与价格核验</h2></div><span>{data?.expectedDate ?? "等待交易日"} · 人民币亿元{loading ? " · 更新中" : ""}</span></div>
    {error && <p className="error-banner">{error}</p>}
    {!data ? <div className="table-empty">{loading ? "独立读取订单、融资和复权价格历史…" : "未取得个股历史，不能判断持续性"}</div> : <>
      {data.calendar.status !== "ready" && <p className="research-warning">交易日历待核验：{data.calendar.reason}</p>}
      {data.fallbackReason && <p className="research-warning">东财来源不可用：{data.fallbackReason}；以下改用 {data.source} 大额订单口径，不拼接旧来源。</p>}
      <div className="research-metrics">
        <div><span>5日大额订单净额</span><strong className={tone(data.order.net5dYi)}>{signed(data.order.net5dYi)}<small>亿元</small></strong><small>1日 {signed(data.order.net1dYi)} / 20日 {signed(data.order.net20dYi)}</small></div>
        <div><span>5日净额 / 同期成交额</span><strong className={tone(data.order.share5dPct)}>{signed(data.order.share5dPct)}<small>%</small></strong><small>{data.order.streak.direction === "in" ? "连续净买入" : data.order.streak.direction === "out" ? "连续净卖出" : "未形成连续方向"} {data.order.streak.days} 日 · 不是机构仓位</small></div>
        <div><span>5日复权价格变化</span><strong className={tone(data.price.change5dPct)}>{signed(data.price.change5dPct)}<small>%</small></strong><small>20日 {signed(data.price.change20dPct)}% · 因子变化 {data.price.factorChanges20d} 日</small></div>
        <div><span>5日融资买入减偿还</span><strong className={tone(data.leverage.net5dYi)}>{signed(data.leverage.net5dYi)}<small>亿元</small></strong><small>余额变化 {signed(data.leverage.balanceChange5dYi)} 亿元 · 不与订单相加</small></div>
      </div>
      <div className="security-research-observations">{data.observations.map(item => <div key={item.id}><strong>{item.title}</strong><span>{item.detail}</span></div>)}<div><strong>龙虎榜 · 事件核验</strong><span>{disclosureReview ?? dragonReview(dragonTiger, dragonCoverage)}</span></div></div>
      <div className="research-subhead"><h3>订单与价格 · 同一交易日窗口</h3><div className="research-period" aria-label="个股历史窗口">{[20, 60].map(period => <button type="button" key={period} aria-pressed={days === period} onClick={() => setDays(period)}>{period}日</button>)}</div></div>
      <div className="security-research-charts"><div><h4>每日大额订单净额</h4><FlowBars dates={points.map(point => point.date)} points={points.map(point => ({ ...point }))} field="net" label="个股大额订单净额历史" /></div><div><h4>复权价格指数</h4><PriceTrace points={points} /></div></div>
      <div className="research-readout"><span>订单净额前60日分位 {value(data.order.baseline.percentile, 1)}% · 样本 {data.order.baseline.samples}/{data.order.baseline.expected}</span><span>融资余额 {value(latest?.balanceYi)} 亿元 · 前60日分位 {value(data.leverage.baseline.percentile, 1)}%</span><span>5日融资买入/成交 {value(data.leverage.buyShare5dPct)}% · 非净额</span><span>融资勾稽 {data.leverage.reconciliationChecked}/20 日可查 · {data.leverage.reconciliationConflicts} 日有差异</span></div>
      <div className="security-feed-status">{Object.entries(data.feeds).map(([key, feed]) => <span key={key} className={feed.status !== "ready" || feed.asOf !== data.expectedDate ? "research-warning" : ""}><b>{feed.api}</b> · {feed.asOf ?? "未取得日期"} · {feed.usingSaved ? "更新失败，保留旧历史" : feed.status === "ready" ? "已取记录" : feed.status === "empty" ? "成功空结果，未确认覆盖" : feed.reason || "来源不可用"}</span>)}</div>
      <details className="research-details"><summary>同日订单、复权与融资勾稽明细</summary><div className="research-table-scroll"><table className="research-table"><thead><tr><th>日期</th><th>大额净额 亿元</th><th>净额/成交 %</th><th>未复权收盘</th><th>复权日变 %</th><th>融资余额</th><th>买入减偿还</th><th>余额变化</th><th>勾稽差额 元</th></tr></thead><tbody>{[...points].reverse().map(point => <tr key={point.date}><td>{point.date}</td><td className={tone(point.net)}>{signed(point.net)}</td><td>{signed(point.netSharePct)}</td><td>{value(point.close)}</td><td>{signed(point.adjustedPct)}{point.factorChanged ? " *" : ""}</td><td>{value(point.balanceYi)}</td><td>{signed(point.marginNetYi)}</td><td>{signed(point.balanceChangeYi)}</td><td>{value(point.marginResidualYuan)}</td></tr>)}</tbody></table></div></details>
      <details className="research-details"><summary>计算口径与数据边界</summary><p>{data.price.method}。固定1/5/20日指标不随图表窗口改变；历史分位不是风险概率。</p><ul>{data.notes.map(note => <li key={note}>{note}</li>)}</ul><div className="source-links"><a href="https://tushare.pro/document/2?doc_id=349" target="_blank" rel="noreferrer">东财订单口径 ↗</a><a href="https://tushare.pro/document/2?doc_id=59" target="_blank" rel="noreferrer">两融与勾稽 ↗</a><a href="https://tushare.pro/document/2?doc_id=28" target="_blank" rel="noreferrer">复权因子 ↗</a></div></details>
    </>}
  </section>;
}
