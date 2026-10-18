import { useState } from "react";
import type { useCandidateArchive } from "./useCandidateArchive";

const fmt = (value: number | null | undefined, suffix = "") => value == null ? "—" : `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${suffix}`;
const captured = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "未保存时间";
const sources: Record<string, string> = { "scheduled-close": "收盘任务", "page-observation": "页面观察", legacy: "早期记录 · 来源未标注" };
const runStatus: Record<string, string> = { recorded: "已有首次归档", closed: "已确认休市", "waiting-data": "等待行情补齐", failed: "采集失败", unavailable: "数据源未配置", "outside-window": "窗口外跳过" };

export function CandidateArchive({ archive }: { archive: ReturnType<typeof useCandidateArchive> }) {
  const [start, setStart] = useState(archive.state?.range.start ?? ""), [end, setEnd] = useState(archive.state?.range.end ?? "");
  const state = archive.state, list = state?.list, detail = state?.detail, data = detail?.data;
  const collection = list?.data?.collection;
  return <section className="candidate-cohort" aria-label="首次信号归档">
    <div className="section-title"><h3>首次信号归档</h3><button type="button" aria-expanded={!!state} onClick={archive.toggle}>{state ? "收起归档" : "浏览历史归档"}</button></div>
    {state && <>
      <p className="research-source">只读查看首次保存的名单与规则；不受最近6日限制，不补写历史、不重算收益。未记录的日期不等于没有信号。</p>
      <form className="liquidity-toolbar" onSubmit={event => { event.preventDefault(); if (!start || !end || start <= end) archive.filter(start, end); }}>
        <label>开始日期 <input aria-label="归档开始日期" type="date" value={start} max={end || undefined} onChange={event => setStart(event.target.value)} /></label>
        <label>结束日期 <input aria-label="归档结束日期" type="date" value={end} min={start || undefined} onChange={event => setEnd(event.target.value)} /></label>
        <button type="submit">查询归档</button><button type="button" onClick={() => { setStart(""); setEnd(""); archive.filter("", ""); }}>全部日期</button>
        <button type="button" onClick={archive.refresh} disabled={list?.loading || detail?.loading}>刷新归档</button>
      </form>
      {list?.loading && <p role="status">正在读取已保存归档…</p>}
      {list?.error && <p role="alert">{list.error}；旧列表已撤下，请刷新重试。</p>}
      {collection && <section aria-label="收盘归档运行状态">
        <div className="section-title"><h4>收盘归档任务</h4><span>{!collection.enabled ? "未启用" : !collection.tokenReady ? "已启用 · 缺行情凭证" : "已启用"}</span></div>
        <p className="research-source">{collection.schedule}；仅Desk后端运行期间执行。</p>
        <p>任务状态：{!collection.enabled ? "已关闭" : collection.job?.status === "running" ? "正在检查" : collection.job?.status === "failed" ? "上次任务失败" : collection.job ? "等待下次检查" : "等待调度注册"} · 下次检查：{collection.enabled && collection.job ? captured(collection.job.next_run_at) : "—"}</p>
        <p>最近检查：{collection.lastCheck ? `${captured(collection.lastCheck.checkedAt)} · ${runStatus[collection.lastCheck.status] || "待核验"} · ${collection.lastCheck.reason}` : "尚无检查记录"}</p>
        {collection.job?.last_error && <p className="turnover-warning">{collection.job.last_error}</p>}
        {collection.lastCheck?.missingDates?.length ? <p className="turnover-warning">待补行情：{collection.lastCheck.missingDates.join("、")}</p> : null}
        <p className="research-source">已缓存往日交易日{collection.knownSessionCount}日 · 未归档{collection.missingDates.length}日{collection.missingDates.length ? `：${collection.missingDates.join("、")}` : ""}</p>
        <p className="research-source">{collection.note}</p>
      </section>}
      {list?.data && <>
        <p className="research-source">当前范围：{state.range.start || "不限起始"} → {state.range.end || "不限结束"} · 共{list.data.total}个已记录信号日</p>
        {!list.data.total ? <p>此范围没有首次观察归档；不会用事后重算填充。</p> : <div className="research-table-scroll"><table className="research-table" aria-label="首次信号归档列表">
          <thead><tr><th>信号日</th><th>首次保存（北京时间）</th><th>候选 / 可比较</th><th>冻结对照</th><th>验证状态</th></tr></thead>
          <tbody>{list.data.rows.map(row => <tr key={row.signalDate}><td><button type="button" aria-label={`打开${row.signalDate}归档`} onClick={() => archive.inspect(row.signalDate)}>{row.signalDate} ↗</button></td><td>{captured(row.capturedAt)}</td><td>{row.candidateCount} / {row.eligibleCount ?? "—"}</td><td>{row.controlStatus === "saved" ? `已保存 · ${row.controlCount}只` : "旧记录缺对照"}</td><td>仅存档 · 未在此核验收益</td></tr>)}</tbody>
        </table></div>}
        <nav className="candidate-pagination" aria-label="信号归档分页"><span>第{list.data.page}/{list.data.pageCount}页</span><button type="button" disabled={list.data.page === 1} onClick={() => archive.selectPage(list.data!.page - 1)}>上一页</button><button type="button" disabled={list.data.page === list.data.pageCount} onClick={() => archive.selectPage(list.data!.page + 1)}>下一页</button></nav>
      </>}
      {state.selectedDate && <section aria-label="冻结信号详情">
        <div className="section-title"><h4>{state.selectedDate} · 冻结信号详情</h4><button type="button" onClick={archive.closeDetail}>关闭归档详情</button></div>
        {detail?.loading && <p role="status">正在读取冻结名单；旧明细已撤下…</p>}
        {detail?.error && <p role="alert">{detail.error}；请刷新归档重试。</p>}
        {data && <>
          <p>首次保存：{captured(data.capturedAt)} · {sources[data.captureSource || "legacy"] || "来源待核验"} · 基线 {data.baselineStart ?? "—"} → {data.baselineEnd ?? "—"} · 市场中位倍数 {fmt(data.marketMedianRatio, "×")}</p>
          <p className="research-source">{data.rules ? `冻结规则 ${data.rules.id}：前${data.rules.baselineDays}日基线；当日≥${data.rules.minAmountYi}亿元，自身≥${data.rules.minOwnRatio}倍，市场相对≥${data.rules.minMarketAdjustedRatio}倍。` : "旧记录缺少规则参数，不能按当前规则推定。"}证券代码为原始记录，不使用当前名称回填历史。</p>
          <div className="research-table-scroll"><table className="research-table" aria-label="冻结候选名单"><thead><tr><th>证券代码</th><th>成交额 / 基线（亿）</th><th>自身 / 市场倍数</th><th>信号日涨跌</th></tr></thead><tbody>{data.candidates.map(row => <tr key={row.code}><td>{row.code}</td><td>{fmt(row.amountYi)} / {fmt(row.baselineYi)}</td><td>{fmt(row.ownRatio, "×")} / {fmt(row.marketAdjustedRatio, "×")}</td><td>{fmt(row.signalPct, "%")}</td></tr>)}</tbody></table></div>
          {!data.candidateCount && <p>当时已完成筛选，但没有命中候选；这是一条有效的空名单记录。</p>}
          <nav className="candidate-pagination" aria-label="冻结名单分页"><span>第{data.page}/{data.pageCount}页 · 共{data.candidateCount}只</span><button type="button" disabled={data.page === 1} onClick={() => archive.selectDetailPage(data.page - 1)}>上一页</button><button type="button" disabled={data.page === data.pageCount} onClick={() => archive.selectDetailPage(data.page + 1)}>下一页</button></nav>
          <p className="research-source">{data.note}</p>
        </>}
      </section>}
    </>}
  </section>;
}
