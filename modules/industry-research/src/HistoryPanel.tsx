import { fmt, historyFor, type History, type Snapshot } from "./research";

export function HistoryPanel({data, publications, history, status, error, selected, load, select}: {
  data: Snapshot; publications: Snapshot[]; history: History | null; status: string; error: string; selected?: string;
  load(): void; select(url: string): void;
}) {
  const points = history && selected ? historyFor(publications, selected) : [];
  return <section className="history-panel" aria-label="历史发布对照">
    <div className="section-title"><div><small>RELEASE HISTORY</small><h2>历史发布对照</h2></div>
      <button disabled={status === "loading"} onClick={load}>{status === "loading" ? "读取历史原文…" : history ? "刷新历史" : "载入最近历史"}</button></div>
    <p>载入后可查看全行业景气变化及所选行业序列；不将累计金额相减推算单月，不据此确认景气拐点。</p>
    {error && <p role="alert" className="error">{error}。历史证据已撤下，已读最新报告仍可使用。</p>}
    {history && <>
      <div className="history-controls"><label>当前报告 <select aria-label="当前报告" value={data.sourceUrl} onChange={e => select(e.target.value)}>
        {publications.map(item => <option key={item.sourceUrl} value={item.sourceUrl}>{item.period} · 发布 {item.publishedAt}</option>)}
      </select></label><span>{history.status === "partial" ? "部分读取成功" : "本次发现的报告已读取"} · {history.publications.length} 份原文 · {history.cached ? "缓存采集" : "本次采集"}</span></div>
      <h3>{selected ?? "请先选择行业"} · 累计同比序列</h3>
      {points.length > 0 && <div className="table-scroll"><table><thead><tr><th>累计统计期 / 原文</th><th>营收同比 %</th><th>较前期变化 / pp</th><th>利润同比 %</th><th>较前期变化 / pp</th><th>比较说明</th></tr></thead>
        <tbody>{points.map(point => <tr key={point.sourceUrl} className={point.sourceUrl === data.sourceUrl ? "selected" : ""}>
          <th><a href={point.sourceUrl} target="_blank" rel="noreferrer">{point.period} ↗</a><small>发布 {point.publishedAt}</small></th>
          <td>{fmt(point.revenueYoy)}</td><td>{fmt(point.change.revenueYoyPp)}</td><td>{fmt(point.profitYoy)}</td><td>{fmt(point.change.profitYoyPp)}</td><td>{point.change.reason}</td>
        </tr>)}</tbody></table></div>}
      {history.errors.length > 0 && <ul className="caution">{history.errors.map(item => <li key={item.sourceUrl}>{item.reason} · <a href={item.sourceUrl} target="_blank" rel="noreferrer">核验来源 ↗</a></li>)}</ul>}
      <p className="caution">{history.scope} 采集时间：{new Date(history.fetchedAt).toLocaleString("zh-CN")}。pp = 百分点；同名行业仍可能存在企业样本调整。</p>
    </>}
  </section>;
}
