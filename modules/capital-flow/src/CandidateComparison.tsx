import type { CandidateCohortData } from "./CandidateCohort";

export interface CandidateComparisonData {
  status: "ready" | "unavailable"; reason: string; eligibleCount?: number; method?: string;
  control: CandidateCohortData | null;
  windows: Array<{ days: number; end: string | null; status: string; reason: string;
    positiveGapPp: number | null; medianGapPp: number | null; meanGapPp: number | null }>;
}
const fmt = (value: number | null, unit = "%") => value == null ? "—" : `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${unit}`;

export function CandidateComparison({ data, cohort }: { data: CandidateComparisonData; cohort: CandidateCohortData }) {
  return <section className="candidate-cohort" aria-label="同日非候选对照">
    <div className="section-title"><h3>候选 vs 非候选</h3><span>同日同窗口 · 非行业／市值匹配</span></div>
    {data.reason && <p className="turnover-warning">{data.reason}</p>}
    {data.control && <>
      <p className="research-source">信号日可比较 {data.eligibleCount}只 = 候选 {cohort.total}只 + 未入选 {data.control.total}只。均具备前20日及信号日正成交额；缺失不剔除成分。</p>
      <div className="research-table-scroll"><table className="research-table" aria-label="候选与非候选同期比较">
        <thead><tr><th>期限 / 截止</th><th>候选有效 / 总数</th><th>对照有效 / 总数</th><th>正收益比例<br />候选 / 对照</th><th>比例差</th><th>中位变化<br />候选 / 对照</th><th>中位差 / 均值差</th><th>对照缺失 / 未到期</th></tr></thead>
        <tbody>{data.windows.map(row => {
          const candidate = cohort.windows.find(item => item.days === row.days)!;
          const control = data.control!.windows.find(item => item.days === row.days)!;
          return <tr key={row.days}>
            <td>后{row.days}日<small className="candidate-code">{row.end || "未到期"}</small></td>
            <td>{candidate.valid}/{candidate.total}</td><td>{control.valid}/{control.total}<small className="candidate-code">覆盖 {fmt(control.coveragePct)}</small></td>
            <td>{fmt(candidate.positivePct)} / {fmt(control.positivePct)}</td><td>{fmt(row.positiveGapPp, "pp")}</td>
            <td>{fmt(candidate.medianPct)} / {fmt(control.medianPct)}</td><td>{fmt(row.medianGapPp, "pp")} / {fmt(row.meanGapPp, "pp")}</td>
            <td>{control.missing} / {control.pending}{row.reason && <small className="candidate-code">{row.reason}</small>}</td>
          </tr>;
        })}</tbody>
      </table></div>
      <p className="research-source">差值＝候选−对照，仅两组样本完整时计算。组内比例仍按各自有效样本；对照不是全市场指数，差值不代表可交易超额收益或因果关系。</p>
      <details className="research-details"><summary>对照范围与局限</summary><p>{data.method}</p><p>{data.control.method}</p></details>
    </>}
  </section>;
}
