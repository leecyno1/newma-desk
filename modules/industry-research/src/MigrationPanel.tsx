import { CHANGE_STATES, fmt, STATES, type migrationFor } from "./research";

export function MigrationPanel({evidence, select}: {evidence: ReturnType<typeof migrationFor>; select(name: string): void}) {
  return <section className="history-panel" aria-label="行业景气变化">
    <div className="section-title"><h2>行业景气变化</h2><span>累计同比变化 · pp = 百分点</span></div>
    <p>{evidence.previous ? <><a href={evidence.previous.sourceUrl} target="_blank" rel="noreferrer">{evidence.previous.period} ↗</a> → </> : "未取得可匹配的相邻报告 → "}
      <a href={evidence.current.sourceUrl} target="_blank" rel="noreferrer">{evidence.current.period} ↗</a> · 完整可比 {evidence.comparableCount} / {evidence.scopeCount} 个行业</p>
    <div className="history-controls">{Object.entries(CHANGE_STATES).map(([key, label]) => <span key={key}>{label} <b>{evidence.counts[key]}</b></span>)}
      <span>进入双增 <b>{evidence.entered}</b> · 退出双增 <b>{evidence.exited}</b></span></div>
    <p>{evidence.boundary} 按利润同比变化降序；改善可能仍是负增长，回落也可能仍处于双增。</p>
    {!evidence.rows.length ? <p>当前搜索范围没有行业，请调整搜索。</p> : <div className="table-scroll"><table><thead><tr>
      <th>行业 / 查看证据</th><th>营收变化 / pp</th><th>利润变化 / pp</th><th>变化方向</th><th>前期 → 本期</th><th>双增边界 / 比较说明</th>
    </tr></thead><tbody>{evidence.rows.map(row => <tr key={row.name}>
      <th><button onClick={() => select(row.name)}>{row.name}</button></th><td>{fmt(row.revenueYoyPp)}</td><td>{fmt(row.profitYoyPp)}</td>
      <td>{CHANGE_STATES[row.direction]}</td><td>{row.previousState ? STATES[row.previousState] : "—"} → {STATES[row.currentState]}</td>
      <td>{row.transition}<small>{row.reason}</small></td>
    </tr>)}</tbody></table></div>}
  </section>;
}
