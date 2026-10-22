import { fmt } from "./research";
import type { ProductionEvidence } from "./production";

export function ProductionPanel({evidence, load}: {evidence: ProductionEvidence; load(): void}) {
  const {publication, metrics} = evidence;
  return <section className="production-panel" aria-label="生产与盈利验证">
    <div className="section-title"><div><small>PRODUCTION × EARNINGS</small><h2>生产与盈利验证</h2></div>
      <button onClick={load} disabled={evidence.status === "loading"}>{evidence.status === "loading" ? "读取同期间生产原表…" : publication ? "刷新生产证据" : "载入生产证据"}</button></div>
    <p>按所选财务统计期匹配官方原表。行业增加值与相关产品产量用于交叉验证，不当作需求、价格或盈利的替代指标。</p>
    {evidence.error && <p role="alert" className="error">{evidence.error}。旧生产证据已撤下，财务原表仍可查看。</p>}
    {publication && <>
      <div className="production-meta"><strong>{evidence.industry}</strong><span>{publication.cumulativePeriod} · 发布 {publication.publishedAt}</span>
        <a href={publication.sourceUrl} target="_blank" rel="noreferrer">生产原文 ↗</a></div>
      <div className="production-finance">同期间行业名义营收同比 <b>{fmt(evidence.financial?.revenueYoy, "%")}</b> · 利润同比 <b>{fmt(evidence.financial?.profitYoy, "%")}</b><span>不与实物量相减推算价格</span></div>
      {metrics.length ? <div className="table-scroll"><table><thead><tr><th>验证指标 / 口径</th><th>单位</th><th>{publication.monthlyPeriod}量</th><th>当月同比 %</th><th>{publication.cumulativePeriod}量</th><th>累计同比 %</th></tr></thead>
        <tbody>{metrics.map(item => <tr key={`${item.kind}:${item.name}`}><th>{item.kind === "valueAdded" ? "行业增加值" : item.name}<small>{item.kind === "valueAdded" ? "扣除价格因素的实际增长" : "相关产品生产量 · 非销量"}</small></th>
          <td>{item.unit ?? "仅增速"}</td>{(["monthValue", "monthYoy", "cumulativeValue", "cumulativeYoy"] as const).map(field => <td key={field} title={`官方原值：${item.raw[field] ?? "—"}`}>{fmt(item[field])}</td>)}</tr>)}</tbody></table></div>
        : <p>原表没有当前行业的直接匹配项，不用全国总量或其他行业替代。</p>}
      {evidence.observations.length > 0 && <div className="production-reading"><h3>交叉验证提示 · 不是因果结论</h3><ul>{evidence.observations.map(text => <li key={text}>{text}</li>)}</ul></div>}
      <div className="national-sales" aria-label="全国产销衔接背景"><h3>全国产品销售率 · 非当前行业需求</h3>
        {evidence.nationalSales ? <><div className="facts">
          <div><span>{publication.monthlyPeriod}销售率</span><b>{fmt(evidence.nationalSales.monthRate, "%")}</b></div>
          <div><span>当月同比变化 / 百分点</span><b>{fmt(evidence.nationalSales.monthYoyPp)}</b></div>
          <div><span>{publication.cumulativePeriod}销售率</span><b>{fmt(evidence.nationalSales.cumulativeRate, "%")}</b></div>
          <div><span>累计同比变化 / 百分点</span><b>{fmt(evidence.nationalSales.cumulativeYoyPp)}</b></div>
        </div><p>销售产值 ÷ 工业总产值，反映全国产销衔接；不是实物销量、终端订单或回款率，不能据此计算库存增幅或当前行业需求。</p></>
          : <p>本报告未取得全国产品销售率，不用产量增速替代。</p>}</div>
      <p className="caution">待补证：{evidence.missing.join("；")}。</p>
      {evidence.timingNote && <p className="caution">{evidence.timingNote}</p>}
      <details><summary>统计口径与来源完整性</summary><ul>{evidence.limitations.map(text => <li key={text}>{text}</li>)}</ul>
        {evidence.discoveryErrors.map(item => <p key={item.sourceUrl}>{item.reason} · <a href={item.sourceUrl} target="_blank" rel="noreferrer">核验列表 ↗</a></p>)}
        <p>采集 {new Date(publication.fetchedAt).toLocaleString("zh-CN")} · {publication.cached ? "15分钟内采集缓存" : "本次采集"} · {publication.freshness === "stale" ? "发布已超过45天，需核验更新" : "月度滞后数据，非实时"}</p>
      </details>
    </>}
  </section>;
}
