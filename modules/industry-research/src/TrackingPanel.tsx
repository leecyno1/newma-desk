import { useState } from "react";
import type { Snapshot } from "./research";
import type { useIndustryTracking } from "./useIndustryTracking";
import { addReview, evidenceRef, IMPACTS, localDay, reviewState, validDay, type Impact } from "./tracking";

const displayTime = (value: string) => new Date(value).toLocaleString("zh-CN", {hour12: false});

export function TrackingPanel({tracker, report, industry}: {tracker: ReturnType<typeof useIndustryTracking>; report: Snapshot; industry: string}) {
  const [statement, setStatement] = useState("");
  const [supporting, setSupporting] = useState("");
  const [counter, setCounter] = useState("");
  const [invalidation, setInvalidation] = useState("");
  const [nextReview, setNextReview] = useState(localDay());
  const selected = tracker.selectedId, setSelected = tracker.select;
  const [note, setNote] = useState("");
  const [impact, setImpact] = useState<Impact>("pending");
  const [message, setMessage] = useState("");
  const source = evidenceRef(report);
  const entry = tracker.entries.find(row => row.id === selected);
  const ready = tracker.writable && tracker.status === "ready" && !tracker.busy && (!selected || !!entry);
  async function save() {
    setMessage("");
    const now = new Date().toISOString();
    try {
      const book = entry ? addReview(tracker.book, entry.id, {at: now, note: note.trim(), impact, nextReview, source})
        : {...tracker.book, entries: [...tracker.book.entries, {id: crypto.randomUUID(), industry, statement: statement.trim(), supporting: supporting.trim(), counter: counter.trim(), invalidation: invalidation.trim(), nextReview, createdAt: now, source, reviews: []}]};
      if (await tracker.save(book)) {setMessage("已保存到当前工作区。"); if (!entry) {setStatement(""); setSupporting(""); setCounter(""); setInvalidation("");} setNote("");}
    } catch (error) {setMessage(error instanceof Error ? error.message : "保存失败");}
  }
  return <section className="production-panel tracking-panel" aria-label="行业研究跟踪">
    <div className="section-title"><div><small>THESIS / REVIEW</small><h2>研究假设与失效条件</h2></div>
      <button disabled={!tracker.available || tracker.busy} onClick={() => {setMessage(""); void tracker.load();}}>{tracker.busy ? "处理中…" : "读取 / 刷新跟踪记录"}</button></div>
    <p>{industry} · {report.period}。只保存研究文字及来源引用，不复制原始财务表。</p>
    {!tracker.available && <p>请在 Desk 中保存，独立页不使用共享本地缓存。</p>}
    {tracker.error && <p role="alert" className="error">{tracker.error}</p>}
    {tracker.status === "ready" && <p role="status">当前行业 {tracker.entries.length} 条 · 工作区版本 {tracker.revision} · 不自动预警</p>}
    <div className="tracking-list">{tracker.entries.map(row => {
      const state = reviewState(row, source);
      return <button key={row.id} disabled={tracker.busy} aria-pressed={row.id === selected} onClick={() => {setSelected(row.id); setNote(""); setImpact("pending"); setMessage(""); setNextReview(row.reviews.at(-1)?.nextReview ?? row.nextReview);}}>
        <strong>{row.statement}</strong><span>{row.archivedAt ? "已归档 · " : ""}{IMPACTS[state.impact]}{!row.archivedAt && state.due ? " · 已到复核日" : ""}{state.reportChanged ? " · 报告已切换，待人工比较" : state.recollected ? " · 同报告重新采集，未确认修订" : ""}</span>
      </button>;
    })}</div>
    <fieldset className="company-controls" disabled={tracker.busy}>
      <button disabled={tracker.busy || !selected} onClick={() => {setSelected(""); setMessage(""); setNextReview(localDay());}}>新建研究假设</button>
      {entry ? <>
        <h3>{entry.statement}</h3><p>初始判断 · {displayTime(entry.createdAt)} · <a href={entry.source.url} target="_blank" rel="noreferrer">原始依据 {entry.source.periodEnd} ↗</a></p>
        <dl><dt>支持证据</dt><dd>{entry.supporting || "待补证"}</dd><dt>反方证据 / 缺口</dt><dd>{entry.counter || "待补证"}</dd><dt>失效条件</dt><dd>{entry.invalidation}</dd></dl>
        <ol>{entry.reviews.map((review, index) => <li key={index}>{displayTime(review.at)} · {IMPACTS[review.impact]} · {review.note} · <a href={review.source.url} target="_blank" rel="noreferrer">依据 {review.source.periodEnd} ↗</a></li>)}</ol>
        <label>本次复核结论<select value={impact} onChange={e => setImpact(e.target.value as Impact)}>{Object.entries(IMPACTS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>本次证据与判断依据<textarea aria-label="本次证据与判断依据" value={note} onChange={e => setNote(e.target.value)} maxLength={1200} rows={3}/></label>
      </> : <>
        <label>研究假设<textarea aria-label="研究假设" value={statement} onChange={e => setStatement(e.target.value)} rows={2} maxLength={500} placeholder="描述可验证的行业判断，不填写买卖指令。"/></label>
        <label>支持证据<textarea aria-label="支持证据" value={supporting} onChange={e => setSupporting(e.target.value)} rows={2} maxLength={1200} placeholder="指标、期间、来源；未取得可留空。"/></label>
        <label>反方证据 / 缺口<textarea aria-label="反方证据 / 缺口" value={counter} onChange={e => setCounter(e.target.value)} rows={2} maxLength={1200}/></label>
        <label>失效条件<textarea aria-label="失效条件" value={invalidation} onChange={e => setInvalidation(e.target.value)} rows={2} maxLength={800} placeholder="什么可观察的证据会推翻此判断？"/></label>
      </>}
      <label>下次复核日期<input type="date" value={nextReview} onChange={e => setNextReview(e.target.value)}/></label>
      <p>保存将引用当前报告（截至 {source.periodEnd}，发布 {source.publishedAt}）。复核追加记录，不改初始判断；切换行业或报告会清空未保存输入。</p>
      <button disabled={!ready || !validDay(nextReview) || (entry ? !!entry.archivedAt || !note.trim() || entry.reviews.length >= 20 : !statement.trim() || !invalidation.trim() || tracker.book.entries.length >= 30)} onClick={() => void save()}>{entry ? "确认追加复核" : "确认保存研究假设"}</button>
      {entry?.archivedAt && <p>此记录已归档；可在跨行业总览恢复后复核。</p>}
      {!ready && <p>{tracker.writable ? '请先成功读取当前工作区记录，再保存。' : '当前会话没有跟踪记录写入权限。'}</p>}
      {tracker.book.entries.length >= 30 && <p>已达30条记录上限，请导出留档。</p>}
      {entry && entry.reviews.length >= 20 && <p>已达20次复核上限，请导出后新建跟踪。</p>}
      {message && <p role="status">{message}</p>}
    </fieldset>
  </section>;
}
