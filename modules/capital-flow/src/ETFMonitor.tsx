import type { CapitalResearch } from "./types";

export function etfMonitorContext(research: CapitalResearch | null | undefined, loading: boolean, error: string) {
  const available = !loading && !error && research?.calendar.status === "ready" && !!research.monitor;
  return { status: loading ? "loading" : error ? "error" : available ? "loaded" : "unavailable",
    message: loading ? "正在更新，上一批监控线索已撤下" : error ? "更新失败，上一批监控线索已撤下" : !available ? "监控数据或交易日历未确认，请刷新研究数据" : "",
    data: available ? research.monitor! : null };
}

const num = (value: number | null | undefined, suffix = "") => value == null ? "—" : `${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}${suffix}`;
export function ETFMonitorPanel({ context }: { context: ReturnType<typeof etfMonitorContext> }) {
  const data = context.data, cohort = data?.cohort;
  return <section className="etf-monitor" aria-label="ETF大额申赎监控">
    <div className="research-subhead"><h3>大额申赎线索</h3><span>{data?.asOf ?? "等待核验"} · 日频研究，不识别资金身份</span></div>
    {context.message ? <p role="status" className="research-warning">{context.message}</p> : null}
    {data && cohort ? <>
      <div className="research-readout"><span>{cohort.name} · 同日有效 <strong>{cohort.available}/{cohort.expected}</strong></span>
        <span>申购 / 赎回 <strong>{num(cohort.inflowCount)} / {num(cohort.outflowCount)} 只</strong></span>
        <span>同向度 <strong>{num(cohort.sameDirectionPct, "%")}</strong></span>
        <span>合计申赎等值 <strong>{num(cohort.flowYi)} 亿元</strong></span>
        <span>异常标的 <strong>{num(cohort.abnormalCount)} 只</strong></span></div>
      {!cohort.current && <p className="research-warning">观察组不完整，不计算同向度和合计。缺少有效数据：{cohort.missingCodes.join("、")}。可在“管理ETF观察池”补入四只沪深300ETF。</p>}
      <div className="research-table-scroll" tabIndex={0}><table className="research-table"><thead><tr><th>观察标的</th><th>日申赎等值（亿元）</th><th>份额变化率</th><th>异常度 Z / 基准</th><th>近5日同向</th><th>研究提示</th></tr></thead>
        <tbody>{data.rows.map(row => <tr key={row.code} data-etf-monitor-code={row.code} data-flagged={row.flagged}>
          <td>{row.name}<small>{row.code}</small></td><td>{num(row.flowYi)}</td><td>{num(row.shareChangePct, "%")}</td>
          <td>{num(row.robustZ)}<small>{row.baselineSamples}/{row.baselineExpected} 日</small></td><td>{num(row.sameDirection5d)} / 5 日</td>
          <td>{row.label}<small>{row.reason}</small></td></tr>)}</tbody></table></div>
      <p className="research-source">{data.boundary}</p>
      <details className="research-details"><summary>异常、同向与持续性的计算方法</summary><p>{data.method}</p>
        <p>同向度=四只中较多方向的只数÷4；真实零变化不计入任一方向。只有四只同日有效才计算，不把缺失标的当成零。四只为固定研究组，并不证明其当前规模排名。</p>
        <p>年报/半年报持有人披露可用于事后交叉验证，但不能据此确定每一日的交易主体；未建立持有人校准前，不输出“汇金金额”或识别准确率。</p>
        <a href="https://www.xiaohongshu.com/explore/6aa2ef470000000028037467" target="_blank" rel="noreferrer">设计参考：ETF资金监控思路（第三方观点，非模型验证）</a>
      </details>
    </> : null}
  </section>;
}
