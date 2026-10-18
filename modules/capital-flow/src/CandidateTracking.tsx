export interface CandidateTrackingData {
  recordedDays: number; retrospectiveDays: number; forwardCompleteDays: Record<string, number>; note: string;
  rows: Array<{ signalDate: string; mode: "recorded" | "retrospective"; timing: string; capturedAt: string | null;
    nextSession: string | null; candidateCount: number | null; current: boolean;
    windows: Array<{ days: number; end: string | null; candidateValid: number | null; medianGapPp: number | null; forwardEligible: boolean; reason: string }> }>;
}
const timingLabels: Record<string, string> = { "before-open": "入场前记录", late: "晚于次日开盘", "pending-calendar": "待下一交易日确认", unknown: "记录时点待核验", retrospective: "事后重算" };
const reasonLabel = (reason: string) => reason.includes("旧快照") ? "缺冻结对照" : reason.includes("未到期") ? "未到期" : reason.includes("样本未齐") ? "样本未齐" : reason.includes("无样本") ? "无样本" : "数据待核验";

export function CandidateTracking({ data, selectedDate, selectDate }: { data: CandidateTrackingData; selectedDate: string | null; selectDate: (day: string) => void }) {
  return <section className="candidate-cohort" aria-label="多日期信号追踪">
    <div className="section-title"><h3>多日期追踪 · 最近{data.rows.length}个信号日</h3><span>已保存{data.recordedDays}日 · 事后重算{data.retrospectiveDays}日</span></div>
    <p className="research-source">入场前记录且完整可比较：后1日 {data.forwardCompleteDays["1"]}期 / 后3日 {data.forwardCompleteDays["3"]}期 / 后5日 {data.forwardCompleteDays["5"]}期。仅说明时间与数据条件，不代表有效策略。</p>
    <div className="research-table-scroll"><table className="research-table" aria-label="多日期信号记录与后续对照">
      <thead><tr><th>信号日 / 查看</th><th>记录性质</th><th>首次保存（北京时间）</th><th>候选数</th><th>后1日中位差</th><th>后3日中位差</th><th>后5日中位差</th></tr></thead>
      <tbody>{data.rows.map(row => <tr key={row.signalDate} aria-current={row.signalDate === selectedDate ? "date" : undefined}>
        <td><button type="button" disabled={row.signalDate === selectedDate} aria-label={`查看${row.signalDate}候选`} onClick={() => selectDate(row.signalDate)}>{row.signalDate}{row.signalDate === selectedDate ? " · 当前" : " ↗"}</button></td>
        <td>{timingLabels[row.timing] || "待核验"}<small className="candidate-code">{row.mode === "recorded" ? "首次记录已保存" : "未存当时记录"}</small></td>
        <td>{row.capturedAt ? new Date(row.capturedAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "—"}</td>
        <td>{row.candidateCount ?? "—"}</td>
        {row.windows.map(window => <td key={window.days} title={window.reason || `截至${window.end}，候选减非候选中位变化的百分点差`}>{window.medianGapPp == null ? "—" : `${window.medianGapPp.toFixed(2)}pp`}<small className="candidate-code">{window.reason ? reasonLabel(window.reason) : window.forwardEligible ? "入场前记录 · 完整" : "仅历史描述"}</small></td>)}
      </tr>)}</tbody>
    </table></div>
    <details className="research-details"><summary>记录时点与前向边界</summary><p>{data.note}</p></details>
  </section>;
}
