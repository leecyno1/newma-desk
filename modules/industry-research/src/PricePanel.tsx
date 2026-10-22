import { fmt } from "./research";
import type { PriceEvidence } from "./prices";

export function PricePanel({evidence, load}: {evidence: PriceEvidence; load(): void}) {
  const {publication, metric} = evidence;
  return <section className="production-panel" aria-label="行业价格验证">
    <div className="section-title"><div><small>PRICES × VOLUME × EARNINGS</small><h2>行业价格验证</h2></div>
      <button onClick={load} disabled={evidence.status === "loading"}>{evidence.status === "loading" ? "读取同期间价格原表…" : publication ? "刷新价格证据" : "载入价格证据"}</button></div>
    <p>按所选财务统计期读取行业出厂价格，不以更晚月份替代。年内平均同比 ≠ 累计涨幅；PPI ≠ 现货或合同报价。</p>
    {evidence.error && <p role="alert" className="error">{evidence.error}。旧价格证据已撤下，其他已读资料仍可使用。</p>}
    {publication && <>
      <div className="production-meta"><strong>{evidence.industry}</strong><span>{publication.monthlyPeriod} · 发布 {publication.publishedAt}</span><a href={publication.sourceUrl} target="_blank" rel="noreferrer">价格原文 ↗</a></div>
      {metric && <>
        <div className="table-scroll"><table><thead><tr><th>行业出厂价格 / %</th><th>当月环比</th><th>当月同比</th><th>{publication.averagePeriod}同比</th></tr></thead>
          <tbody><tr><th>官方价格指数变化<small>不是价格金额；不自行累计或复利计算</small></th>{(["monthMom", "monthYoy", "yearToDateAverageYoy"] as const).map(key => <td key={key} title={`官方原值：${metric.raw[key] ?? "—"}`}>{fmt(metric[key])}</td>)}</tr></tbody></table></div>
        <div className="production-finance">同期名义营收累计同比 <b>{fmt(evidence.financial?.revenueYoy, "%")}</b> · 利润累计同比 <b>{fmt(evidence.financial?.profitYoy, "%")}</b></div>
        {evidence.productionCheck && <p>已加载的同月产品产量同比：{evidence.productionCheck.metrics.map(row => `${row.name} ${fmt(row.monthYoy, "%")}`).join("；")}。与行业价格并非同一产品篮子。</p>}
      </>}
      {evidence.observations.length > 0 && <div className="production-reading"><h3>量价与盈利核验 · 不作贡献归因</h3><ul>{evidence.observations.map(text => <li key={text}>{text}</li>)}</ul></div>}
      <p className="caution">{evidence.missing.join("；")}。</p>
      {evidence.timingNote && <p className="caution">{evidence.timingNote}</p>}
      <details><summary>统计口径、基期与来源</summary><p>原表列出 {publication.industries} 个主要行业，只作同名匹配，不代表全部行业均已覆盖。</p>
        <ul>{evidence.limitations.map(text => <li key={text}>{text}</li>)}</ul>
        {evidence.baseNotes.length ? evidence.baseNotes.map(text => <p key={text}>官方基期说明：{text}</p>) : <p>原文未提取到基期说明，请核验原文。</p>}
        {evidence.discoveryErrors.map(item => <p key={item.sourceUrl}>{item.reason} · <a href={item.sourceUrl} target="_blank" rel="noreferrer">核验列表 ↗</a></p>)}
        <p>采集 {new Date(publication.fetchedAt).toLocaleString("zh-CN")} · {publication.cached ? "15分钟内采集缓存" : "本次采集"} · {publication.freshness === "stale" ? "发布已超过45天，需核验更新" : "月度滞后数据，非实时"}</p>
      </details>
    </>}
  </section>;
}
