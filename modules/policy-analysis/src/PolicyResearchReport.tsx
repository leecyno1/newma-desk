import type { PolicyInterpretation } from "./types";

export function PolicyResearchReport({ report }: { report: PolicyInterpretation }) {
  const comparison = report.transcriptComparison;
  return <div className="policy-research-detail">
    <section aria-label="投资传导与验证">
      <h3>条款 → 传导假设 → 验证</h3>
      <p className="muted-note">全部为未复核研究假设；不代表持仓已受影响，也不直接触发风控告警。</p>
      {report.transmission?.length ? report.transmission.map((item) => <article className="transmission-row" key={item.id}>
        <h4>{item.label}<span>待复核</span></h4>
        <details><summary>核验依据 · 正文第 {item.evidence.map((evidence) => evidence.paragraph).join("、")} 段</summary>{item.evidence.map((evidence) => <blockquote key={evidence.paragraph}><b>正文第 {evidence.paragraph} 段{evidence.excerpted ? "（节选）" : ""}</b>{evidence.quote}</blockquote>)}</details>
        <p>{item.mechanism}</p>
        <dl><div><dt>验证指标</dt><dd>{item.indicators.join(" · ")}</dd></div><div><dt>失效条件</dt><dd>{item.invalidation}</dd></div></dl>
        <a href={item.sourceUrl} target="_blank" rel="noreferrer">官方出处 · 正文记录 #{item.documentRevision}</a>
      </article>) : <p className="muted-note">暂无正文支持的传导链。请读取原文；未匹配规则不代表没有投资影响。</p>}
    </section>
    <section aria-label="官方正文差异">
      <h3>官方正文差异</h3><p className="muted-note">{comparison.note}</p>
      {comparison.status === "available" ? <>
        <p>基准：<a href={comparison.baseSourceUrl} target="_blank" rel="noreferrer">{comparison.baseTitle || "已保存正文"}</a> · #{comparison.baseRevision} → #{comparison.currentRevision} · {comparison.changeCount} 处差异</p>
        <p className="muted-note">基准采集 {comparison.baseFetchedAt} · 当前采集 {comparison.currentFetchedAt}</p>
        {comparison.displayLimited ? <p className="muted-note">以下差异为节选，不是完整对照稿；请结合两份官方原文核验。</p> : null}
        {comparison.changes?.map((change, index) => <div className="policy-text-diff" key={index}>
          <div className="before"><b>原正文 · 第 {change.beforeParagraph} 段</b>{change.before.length ? change.before.map((text, i) => <p key={i}>{text}</p>) : <p>无对应段落</p>}</div>
          <div className="after"><b>当前正文 · 第 {change.afterParagraph} 段</b>{change.after.length ? change.after.map((text, i) => <p key={i}>{text}</p>) : <p>无对应段落</p>}</div>
        </div>)}
        {comparison.changeCount === 0 ? <p>未检测到正文文字变化；不等于实施效果没有变化。</p> : null}
      </> : <p>没有可比较正文，不生成条款新增、删除或修订结论。</p>}
    </section>
  </div>;
}
