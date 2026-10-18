export interface CandidateCohortData {
  total: number; scope: string; method: string;
  windows: Array<{
    days: number; end: string | null; status: "empty" | "pending" | "ready" | "partial" | "missing";
    total: number; valid: number; missing: number; pending: number; coveragePct: number | null;
    up: number; flat: number; down: number; positivePct: number | null;
    medianPct: number | null; meanPct: number | null; p25Pct: number | null; p75Pct: number | null;
    minPct: number | null; maxPct: number | null;
  }>;
}

const pct = (value: number | null) => value == null ? "—" : `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}%`;
const statusLabel = { empty: "无候选", pending: "未到期", ready: "样本齐备", partial: "仅有效子样本", missing: "无有效行情" };

export function CandidateCohort({ data }: { data: CandidateCohortData }) {
  return <section className="candidate-cohort" aria-label="完整候选组统计">
    <div className="section-title"><h3>整组表现分布</h3><span>{data.total}只 · {data.scope}</span></div>
    <p className="research-source">信号日收盘后观察 · 日涨跌幅链式变化，非逐只复权核验。正收益比例不是交易胜率；整组分布本身不能确认选股有效。</p>
    <div className="research-table-scroll"><table className="research-table" aria-label="完整候选组表现分布">
      <thead><tr><th>观察期 / 截止</th><th>有效 / 全部</th><th>上涨 / 持平 / 下跌</th><th>正收益比例</th><th>中位数 / 均值</th><th>中间50%区间</th><th>最小 / 最大</th><th>缺失 / 未到期</th></tr></thead>
      <tbody>{data.windows.map(row => <tr key={row.days}>
        <td>后{row.days}日<small className="candidate-code">{row.end || statusLabel[row.status]}</small></td>
        <td>{row.valid}/{row.total}<small className="candidate-code">{statusLabel[row.status]}{row.coveragePct != null && ` · ${pct(row.coveragePct)}`}</small></td>
        <td>{row.valid ? `${row.up} / ${row.flat} / ${row.down}` : "—"}</td>
        <td>{pct(row.positivePct)}<small className="candidate-code">{row.valid ? `${row.up} / ${row.valid}只有效样本` : "无有效分母"}</small></td>
        <td>{pct(row.medianPct)} / {pct(row.meanPct)}</td>
        <td>{row.valid ? `${pct(row.p25Pct)} ～ ${pct(row.p75Pct)}` : "—"}</td>
        <td>{row.valid ? `${pct(row.minPct)} / ${pct(row.maxPct)}` : "—"}</td>
        <td>{row.missing} / {row.pending}</td>
      </tr>)}</tbody>
    </table></div>
    {data.windows.some(row => row.missing > 0) && <p className="turnover-warning">存在行情缺口，比例与分布仅覆盖有效子样本，不能视作整组完整结果；缺失股票未被当作零收益。</p>}
    {!data.total && <p>当前规则未命中候选，暂无可统计样本。</p>}
    <details className="research-details"><summary>统计口径与局限</summary><p>{data.method}</p></details>
  </section>;
}
