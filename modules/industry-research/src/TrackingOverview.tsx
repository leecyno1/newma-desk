import { useState } from "react";
import { archiveEntry, IMPACTS, trackingOverview, type TrackingFilter } from "./tracking";
import type { useIndustryTracking } from "./useIndustryTracking";

export function TrackingOverview({tracker, industries, open}: {tracker: ReturnType<typeof useIndustryTracking>; industries: string[]; open: (industry: string, id: string) => void}) {
  const [filter, setFilter] = useState<TrackingFilter>("due");
  const [confirmation, setConfirmation] = useState<{id: string; revision: number; archive: boolean} | null>(null);
  const [message, setMessage] = useState("");
  const ready = tracker.status === "ready";
  const overview = trackingOverview(tracker.book, filter);
  const target = confirmation && confirmation.revision === tracker.revision ? tracker.book.entries.find(r => r.id === confirmation.id) : undefined;
  const labels = {active: "跟踪中", due: "到期复核", attention: "削弱 / 失效", archived: "已归档"};
  async function confirm() {
    if (!target || !confirmation || !ready || !tracker.writable) return;
    if (await tracker.save(archiveEntry(tracker.book, target.id, confirmation.archive ? new Date().toISOString() : null))) {
      setConfirmation(null); setMessage("已保存；原始判断和复核历史均保留。");
    }
  }
  function exportAll() {
    if (!ready) return;
    const blob = new Blob([JSON.stringify({scope: "current-workspace-all-industries", exportedAt: new Date().toISOString(), revision: tracker.revision, book: tracker.book}, null, 2)], {type: "application/json"});
    const url = URL.createObjectURL(blob); const a = document.createElement("a");
    a.href = url; a.download = "industry-tracking-all.json"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section className="production-panel tracking-overview" aria-label="跨行业复核总览">
    <div className="section-title"><div><small>REVIEW / WORKSPACE</small><h2>跨行业复核总览</h2></div><div>
      <button disabled={!tracker.available || tracker.busy} onClick={() => {setConfirmation(null); setMessage(""); void tracker.load();}}>读取工作区跟踪</button>{" "}
      <button disabled={!ready} onClick={exportAll}>导出全部跟踪记录</button></div></div>
    <p>当前工作区全部行业，不受搜索和增长分类筛选影响。到期按本地日期；不是市场风险评分，也不发送后台提醒。</p>
    {tracker.error && <p role="alert" className="error">{tracker.error}</p>}
    {!ready ? <p role="status">{tracker.busy ? "正在处理，请稍候。" : "请先读取工作区记录；读取失败时不显示旧队列。"}</p> : <>
      <div className="tracking-tabs" role="group" aria-label="跟踪队列筛选">{Object.entries(labels).map(([key, label]) => <button key={key} aria-pressed={filter === key} onClick={() => {setFilter(key as TrackingFilter); setConfirmation(null); setMessage("");}}>{label} {overview.counts[key as TrackingFilter]}</button>)}</div>
      <p className="tracking-scroll-note">横向滑动表格查看日期与操作 →</p>
      {overview.rows.length ? <div className="table-scroll" tabIndex={0} aria-label="复核记录横向滚动区"><table><thead><tr><th>行业 / 假设</th><th>用户判断</th><th>复核日期</th><th>证据截至</th><th>操作</th></tr></thead><tbody>{overview.rows.map(row => <tr key={row.id}>
        <th>{row.industry}<small>{row.statement}</small></th><td>{IMPACTS[row.impact]}{row.due ? " · 已到期" : ""}</td><td>{row.nextReview}</td><td>{row.periodEnd}</td>
        <td><button disabled={!industries.includes(row.industry)} onClick={() => {open(row.industry, row.id); setMessage("");}}>打开复核</button>{" "}
          <button disabled={!tracker.writable} onClick={() => {setConfirmation({id: row.id, revision: tracker.revision, archive: !row.archivedAt}); setMessage("");}}>{row.archivedAt ? "恢复跟踪" : "归档"}</button>
          {!industries.includes(row.industry) && <small>当前报告未覆盖，不自动匹配</small>}</td>
      </tr>)}</tbody></table></div> : <p role="status">此队列暂无记录；不代表行业没有风险。</p>}
      {target && confirmation && <div className="tracking-confirm" role="group" aria-label="确认跟踪状态变更"><p>{confirmation.archive ? "归档后退出到期队列，历史保留并可恢复。" : "恢复后按原复核日期重新进入队列，不改变原判断。"}<br/>{target.industry} · {target.statement}</p>
        <button disabled={!tracker.writable} onClick={() => void confirm()}>{confirmation.archive ? "确认归档" : "确认恢复"}</button>{" "}<button onClick={() => setConfirmation(null)}>取消</button></div>}
      <p>归档不删除记录、不释放文档额度；全量导出包含已归档历史。刷新后重新确认状态变更。</p>
    </>}
    {message && <p role="status">{message}</p>}
  </section>;
}
