import { fmt } from "./research";
import type { CapacityEvidence } from "./capacity";

export function CapacityPanel({evidence, load}: {evidence: CapacityEvidence; load(): void}) {
  const {publication, metric} = evidence;
  return <section className="production-panel capacity-panel" aria-label="产能与需求核验">
    <div className="section-title"><div><small>CAPACITY / DEMAND CHECK</small><h2>产能与需求核验</h2></div>
      <button onClick={load} disabled={evidence.status === "loading"}>{evidence.status === "loading" ? "读取季度产能原表…" : publication ? "刷新季度产能" : "载入季度产能"}</button></div>
    <p>{evidence.timingNote}</p>
    {evidence.error && <p className="error" role="alert">{evidence.error}。旧产能证据已撤下。</p>}
    {publication && <>
      <div className="production-meta"><strong>{evidence.industry ?? "未选择行业"}</strong><span>{publication.quarterPeriod} · 发布 {publication.publishedAt}</span>
        <a href={publication.sourceUrl} target="_blank" rel="noreferrer">季度产能原表 ↗</a><span>原表覆盖 {publication.coverage} 个细分行业</span></div>
      {metric ? <div className="facts">
        <div><span>{publication.quarterPeriod}利用率</span><b>{fmt(metric.quarterRate, "%")}</b></div>
        <div><span>该季度同比变化 / 百分点</span><b>{fmt(metric.quarterYoyPp)}</b></div>
        <div><span>{publication.yearToDatePeriod}利用率</span><b>{fmt(metric.yearToDateRate, "%")}</b></div>
        <div><span>年内累计同比变化 / 百分点</span><b>{fmt(metric.yearToDateYoyPp)}</b></div>
      </div> : <p role="status">原表未列出当前行业，不以全国、制造业或名称相近行业替代。</p>}
      {metric && <div className="production-reading"><h3>核验提示 · 不是需求结论</h3>
        <p>{evidence.observations.join(" ") || "利用率同比变化缺失，无法判断改善或恶化。"}</p>
        <p>下一步核对该行业新增产能及检修、目标公司订单与产销。利用率与利润报告区间不同，不据二者增速差归因利润变化。</p></div>}
      {evidence.publicationNote && <p className="caution">{evidence.publicationNote}</p>}
      <details><summary>季度口径、来源与局限</summary><ul>{evidence.limitations.map(text => <li key={text}>{text}</li>)}</ul>
        {evidence.discoveryErrors.map(item => <p key={item.sourceUrl}>{item.reason} · <a href={item.sourceUrl} target="_blank" rel="noreferrer">核验列表 ↗</a></p>)}
        <p>采集 {new Date(publication.fetchedAt).toLocaleString("zh-CN")} · {publication.cached ? "15分钟内采集缓存" : "本次采集"} · 以所选财务期定位季度，并非最新季度实时看板。</p>
      </details>
    </>}
    <p className="caution">尚未取得细分行业订单及产销率。下方全国产品销售率只作背景；利用率上升不等于终端需求增长或投资价值提升。</p>
  </section>;
}
