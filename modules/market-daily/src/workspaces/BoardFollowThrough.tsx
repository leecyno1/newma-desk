import type { LimitBoards } from "../types";

const tierName = (boards: number | null) => boards == null ? "层级未知" : boards === 1 ? "首板" : `${boards}板`;
const outcomes = { U: "今日续封", Z: "今日炸板", D: "今日跌停", absent: "未入三池" };
const quoteLabels = { unavailable: "行情未确认", no_trade: "无有效成交", conflict: "来源冲突", traded: "有成交 · 涨停价待核验", at_limit: "收于涨停价", below_limit: "有成交 · 未封涨停" };
const number = (value: number | null | undefined, suffix = "") => value == null ? "—" : `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${suffix}`;

export function BoardFollowThrough({ tracking }: { tracking: LimitBoards["tracking"] }) {
  if (!tracking?.ready || !tracking.summary) return <p className="sentiment-note">{tracking?.reason || "尚未取得两日逐股核对结果，请刷新。"}</p>;
  const summary = tracking.summary;
  const verification = tracking.quoteVerification;
  const quotes = new Map(verification?.rows.map(row => [row.code, row]));
  return <div aria-label="昨日涨停去向研究">
    <p className="sentiment-note">昨日 {summary.total} 只 → 续封 {summary.U} · 炸板 {summary.Z} · 跌停 {summary.D} · 未入三池 {summary.absent}（名单分类，另见行情核验）</p>
    {verification ? <section aria-label="同日行情核验" className="sentiment-history-metrics">
      <div><span>可用行情 / 昨日涨停</span><strong>{verification.summary.priced} / {verification.summary.total}</strong><small>{verification.asOf} · 无冲突且有成交</small></div>
      <div><span>收于涨停 / 未封涨停</span><strong>{verification.summary.atLimit} / {verification.summary.belowLimit}</strong><small>逐股核对来源涨跌停价</small></div>
      <div><span>冲突 / 尚待核验</span><strong>{verification.summary.conflicts} / {verification.summary.unresolved}</strong><small>不改写原始名单分类</small></div>
      <div><span>同日涨跌幅中位数</span><strong>{number(verification.summary.medianPct, "%")}</strong><small>仅 {verification.summary.returnCount} 只有效样本，非策略收益</small></div>
    </section> : <p className="sentiment-note">尚无同日行情核验结果；未入三池仍待核查，不直接认定断板。</p>}
    <div className="sentiment-history-table"><table aria-label="昨日梯队承接"><thead><tr><th>昨日层级</th><th>样本</th><th>续封</th><th>炸板</th><th>跌停</th><th>未入三池</th><th>续封占比</th></tr></thead><tbody>
      {tracking.tiers.map(tier => <tr key={tier.boards ?? "unknown"}><td>{tierName(tier.boards)}</td><td>{tier.total}</td><td>{tier.U}</td><td>{tier.Z}</td><td>{tier.D}</td><td>{tier.absent}</td><td>{tier.retentionRatePct.toFixed(1)}%</td></tr>)}
    </tbody></table></div>
    <p className="sentiment-note">{tracking.note}</p>
    {summary.mismatches > 0 ? <p className="sentiment-note">连板数不一致 {summary.mismatches} 只：虽在两日涨停池，但今日连板数不等于昨日+1，保留来源值待核查。</p> : null}
    {tracking.unmatchedContinuations.length > 0 ? <p className="sentiment-note">今日标注连板但未匹配昨日涨停池：{tracking.unmatchedContinuations.map(row => `${row.name}（${row.code}，${row.boards}板）`).join("、")}。可能涉及来源统计或样本进出，不能纳入昨日续封分子。</p> : null}
    <div className="sentiment-history-table limit-board-table"><table aria-label="昨日涨停逐股核对"><thead><tr><th>证券 / 代码</th><th>昨日 → 今日连板</th><th>名单去向</th><th>日涨跌幅</th><th>收盘 / 涨停价</th><th>行情核验</th></tr></thead><tbody>
      {tracking.rows.map(row => { const quote = quotes.get(row.code); return <tr key={row.code}><td>{row.name}<small>{row.code} · {row.industry}</small></td><td>{row.previousBoards ?? "—"} → {row.currentBoards ?? "—"}<small>{row.progression === "matched" ? "与昨日+1一致" : row.progression === "mismatch" ? "不一致 · 待核查" : "不可比较"}</small></td><td>{outcomes[row.outcome]}</td><td>{number(quote?.pct, "%")}</td><td>{number(quote?.close)} / {number(quote?.upLimit)}<small>成交额 {number(quote?.amountYi)} 亿元</small></td><td>{quote ? quoteLabels[quote.status] : "待核验"}{quote?.reason ? <small>{quote.reason}</small> : null}</td></tr>; })}
    </tbody></table>{!tracking.rows.length ? <p className="sentiment-note">昨日已核验名单中无涨停股，不计算续封比例。</p> : null}</div>
    {verification ? <details className="sentiment-method"><summary>行情核验来源与边界</summary><p>{verification.source} · {verification.asOf} · 获取 {verification.receivedAt}</p><p>日线：{verification.dailyStatus === "ready" ? "请求成功，逐股覆盖见表" : "请求失败"}；涨跌停价：{verification.limitsStatus === "ready" ? "请求成功，逐股覆盖见表" : "请求失败"}</p><p>{verification.note}</p></details> : null}
  </div>;
}
