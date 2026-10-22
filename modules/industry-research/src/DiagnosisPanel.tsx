import type { Diagnosis } from "./diagnosis";
import type { Industry } from "./research";

export function DiagnosisPanel({diagnosis, rows, select, load, loading}: {diagnosis: Diagnosis; rows: Industry[]; select(name: string): void; load(): void; loading: boolean}) {
  return <section className="diagnosis-panel" aria-label="行业诊断">
    <div className="section-title"><div><small>RESEARCH READOUT</small><h2>行业诊断</h2></div>
      <label>当前行业 <select aria-label="诊断行业" value={diagnosis?.industry ?? ""} onChange={e => select(e.target.value)} disabled={!rows.length}>
        {!rows.length && <option value="">无匹配行业</option>}{rows.map(row => <option key={row.name} value={row.name}>{row.name}</option>)}</select></label>
      <button disabled={!diagnosis || loading} onClick={load}>{loading ? "量价证据读取中…" : "载入 / 刷新量价证据"}</button>
    </div>
    {!diagnosis ? <p>当前筛选无匹配行业，请调整行业比较矩阵中的条件。</p> : <>
      <h3 className="diagnosis-headline">{diagnosis.headline}</h3>
      <p className="diagnosis-scope">{diagnosis.industry} · {diagnosis.period} · 量价同期核验，产能按季度参考，非实时景气</p>
      <div className="diagnosis-facts">{diagnosis.facts.map(fact => <article key={fact.label}>
        <header><h3>{fact.label}</h3><span>{fact.state}</span></header><p>{fact.text}</p>
        {fact.sourceUrl && <a href={fact.sourceUrl} target="_blank" rel="noreferrer">原始证据 ↗ · 发布 {fact.publishedAt}</a>}
      </article>)}</div>
      <div className="diagnosis-reading"><div><h3>交叉解读 · 非因果归因</h3>
        {diagnosis.observations.length ? <ul>{diagnosis.observations.map(line => <li key={line}>{line}</li>)}</ul> : <p>尚无可用交叉证据。先补齐量价，再核验持续性，不能以财务单点代替行业趋势。</p>}
      </div><div><h3>下一步核验 · 三个问题</h3><ol>{diagnosis.questions.map(line => <li key={line}>{line}</li>)}</ol></div></div>
      {diagnosis.timingNotes.map(note => <p className="caution" key={note}>{note}</p>)}
      <details><summary>研究缺口与判断边界</summary><ul>{diagnosis.gaps.map(line => <li key={line}>{line}</li>)}</ul><p>{diagnosis.boundary}</p></details>
    </>}
  </section>;
}
