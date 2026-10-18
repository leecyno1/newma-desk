import type { CapitalResearch, ETFResearch } from "./types";
import { ETFMonitorPanel, etfMonitorContext } from "./ETFMonitor";
import { etfPoolCoverage, sortedETFs, withETFStrengthState, type ETFStrengthDays, type ETFStrengthSort } from "./etfStrength";
import { ETFPriceFlow, priceFlowContext, type ETFPriceState } from "./ETFPriceFlow";

function value(number: number | null | undefined, digits = 2) {
  return number == null ? "--" : number.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function signed(number: number | null | undefined) {
  return number == null ? "--" : `${number > 0 ? "+" : ""}${value(number)}`;
}

function tone(number: number | null | undefined) {
  return number == null || number === 0 ? "" : number > 0 ? "positive-text" : "negative-text";
}

export function FlowBars({ dates, points, field, label }: { dates: string[]; points: Array<{ date: string; [key: string]: unknown }>; field: string; label: string }) {
  const indexed = new Map(points.map(point => [point.date, point]));
  const rows = dates.map(date => ({ date, amount: indexed.get(date)?.[field] as number | null | undefined }));
  const max = Math.max(1, ...rows.map(row => Math.abs(row.amount ?? 0)));
  const width = 760, height = 210, left = 12, step = (width - 24) / Math.max(1, rows.length);
  return <div className="research-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
    <line x1="12" x2="748" y1="92" y2="92" className="research-zero" />
    <text x="748" y="14" textAnchor="end">±{value(max)} 亿元 · 零轴居中</text>
    {rows.map((row, index) => {
      const x = left + step * index, size = Math.abs(row.amount ?? 0) / max * 66;
      return <g key={row.date}><title>{row.date} · {signed(row.amount)} 亿元</title>
        {row.amount == null ? <text x={x + step / 2} y="98" textAnchor="middle">缺</text>
          : <rect data-flow-bar={row.date} className={(row.amount ?? 0) >= 0 ? "flow-positive" : "flow-negative"} x={x + 2} y={row.amount >= 0 ? 92 - size : 92} width={Math.max(1, step - 4)} height={Math.max(.8, size)} />}
        {(index === 0 || index === rows.length - 1 || index % 5 === 0) && <text x={x + step / 2} y="184" textAnchor="middle">{row.date.slice(5)}</text>}
      </g>;
    })}
  </svg><small>红正绿负；缺失留空，不补零。此图是历史观察，不是未来预测。</small></div>;
}

function ETFTable({ rows, selected, select }: { rows: ETFResearch[]; selected: string; select: (code: string) => void }) {
  return <div className="research-table-scroll etf-pool-table" tabIndex={0} role="region" aria-label="ETF观察池比较"><table className="research-table"><thead><tr>
    <th>ETF / 研究分组</th><th>份额 万份</th><th>NAV 元</th><th>1日金额 / 强度</th><th>5日金额 / 强度</th><th>20日金额 / 强度</th><th>数据日期 / 状态</th>
  </tr></thead><tbody>{rows.map(row => <tr key={row.code} className={selected === row.code ? "selected" : ""}>
    <td><button type="button" onClick={() => select(row.code)} aria-pressed={selected === row.code}><strong>{row.name}</strong><small>{row.code} · {row.category}</small></button></td>
    <td>{value(row.latest.sharesWan, 2)}</td><td>{value(row.latest.nav, 4)}</td>
    {([1, 5, 20] as const).map(days => { const window = row.summary.strength?.[days]; const amount = row.summary[`flow${days}dYi`]; return <td key={days} data-strength-days={days}>
      <span className={tone(amount)}>{signed(amount)} 亿</span><small className={window?.current ? tone(window.strengthPct) : ""} title={window?.reason || "申赎等值估算 / 期初规模估算；不是收益率"}>{signed(window?.strengthPct)}%{!window?.current && " · 未确认"}</small>
    </td>; })}
    <td><span>{row.asOf ?? "--"}</span><small title={row.sourceNote || row.note}>{row.status === "ready" ? "份额 / 净值齐备" : row.usingSaved ? "保存历史 · 更新失败" : row.status === "partial" ? "部分缺失 / 待核验" : "未取得记录"}</small></td>
  </tr>)}</tbody></table></div>;
}

export function FundingResearch({ data, loading, error, selected, select, days, setDays, strengthDays, setStrengthDays, strengthSort, setStrengthSort, priceState }: {
  data: CapitalResearch | null; loading: boolean; error: string;
  selected: string; select: (code: string) => void;
  days: number; setDays: (days: number) => void;
  strengthDays: ETFStrengthDays; setStrengthDays: (days: ETFStrengthDays) => void;
  strengthSort: ETFStrengthSort; setStrengthSort: (sort: ETFStrengthSort) => void;
  priceState: ETFPriceState;
}) {
  const rows = sortedETFs((data?.etfs ?? []).map(row => withETFStrengthState(row, !loading && !error && data?.calendar.status === "ready")), strengthDays, strengthSort);
  const etf = rows.find(row => row.code === selected) ?? rows[0];
  const strength = etf?.summary.strength?.[strengthDays];
  const coverage = etfPoolCoverage(rows, strengthDays);
  const price = priceFlowContext(etf, priceState, strengthDays);
  const dates = data?.calendar.dates.slice(-days) ?? [];
  const period = <div className="research-period" aria-label="历史观察窗口">{[20, 60].map(period => <button key={period} type="button" aria-pressed={days === period} onClick={() => setDays(period)}>{period}日</button>)}</div>;
  return <section className="funding-research" aria-label="ETF申赎研究台" aria-busy={loading}>
    {error ? <p className="error-banner">{error}</p> : null}
    {!data ? <div className="table-empty">{loading ? "正在读取观察池份额与净值历史…" : "尚未取得 ETF 研究数据"}</div> : <>
      {data.calendar.status !== "ready" ? <p className="research-warning">交易日历不可用，日窗口结论需复核：{data.calendar.reason}</p> : null}
      <ETFMonitorPanel context={etfMonitorContext(data, loading, error)} />
      <div className="etf-pool-summary" role="group" aria-label="ETF观察池窗口覆盖">
        <div><span>{strengthDays}日窗口可确认</span><strong>{coverage.confirmed}<small> / {coverage.total} 只</small></strong></div>
        <div><span>净申购标的</span><strong className="positive-text">{coverage.inflow}<small>只</small></strong></div>
        <div><span>净赎回标的</span><strong className="negative-text">{coverage.outflow}<small>只</small></strong></div>
        <div data-incomplete={coverage.unconfirmed > 0}><span>待核验窗口</span><strong>{coverage.unconfirmed}<small>只 · 不计方向</small></strong></div>
      </div>
        <div className="research-subhead"><h3>观察池比较</h3><span>{data.expectedDate ?? "日期待核验"} · 仅限自选样本，不代表全市场</span></div>
        <div className="etf-strength-controls"><div className="research-period" aria-label="申赎强度比较窗口">{([1, 5, 20] as const).map(period => <button key={period} type="button" aria-pressed={strengthDays === period} onClick={() => setStrengthDays(period)}>{period}日强度</button>)}</div>
          <label>比较排序 <select aria-label="ETF强度排序" value={strengthSort} onChange={event => setStrengthSort(event.target.value as ETFStrengthSort)}><option value="pool">观察池顺序</option><option value="inflow">净申购强度优先</option><option value="outflow">净赎回强度优先</option></select></label>
          <span>点击标的查看证据 · 未确认不参与强度排序</span></div>
        <ETFTable rows={rows} selected={etf?.code ?? selected} select={select} />
        <div className="etf-selected-strip" role="group" aria-label="所选ETF研究摘要">
          <div><span>当前研究 · {etf?.code ?? "--"}</span><strong>{etf?.name ?? "尚无标的"}</strong><small>{etf?.category} · 数据 {etf?.asOf ?? "--"}</small></div>
          <div><span>{strengthDays}日申赎等值估算</span><strong className={strength?.current ? tone(strength.flowYi) : ""}>{signed(strength?.flowYi)}<small>亿元</small></strong><small>{strength?.current ? "窗口完整" : "未确认 · 数字仅供参考"}</small></div>
          <div><span>价格 × 申赎 · {strengthDays}日</span><strong className={price?.selected.divergence ? "etf-divergence" : ""}>{price?.selected.phase ?? "未确认"}</strong><small>{price?.selected.current ? "仅为复核线索，不是买卖指令" : price?.selected.reason || "等待价格与份额证据"}</small></div>
        </div>
        <div className="etf-evidence-grid">
        <section className="etf-history" aria-label="ETF申赎历史">
          <div className="research-subhead"><h3>日申赎金额等值估算</h3>{period}</div>
          <FlowBars dates={dates} points={(etf?.points ?? []).map(point => ({ ...point }))} field="flowYi" label={`${etf?.name}申赎估算历史`} />
          <div className="research-readout"><span>当日份额变化 <strong>{signed(etf?.latest.shareChangeWan)} 万份</strong></span><span>净值变化 {signed(etf?.latest.navChangePct)}%（非总回报）</span></div>
          <div className="research-readout"><span>当日申赎历史分位 {value(etf?.summary.baseline.percentile, 1)}%</span><span>前60日均值 {signed(etf?.summary.baseline.mean)} 亿元 · 样本 {etf?.summary.baseline.samples ?? 0}/{etf?.summary.baseline.expected ?? 0}</span></div>
        </section>
        <section className="etf-strength-detail" aria-label="所选ETF申赎强度">
          <div className="research-subhead"><h3>{strengthDays}日申赎强度 · 计算依据</h3><strong className={strength?.current ? tone(strength.strengthPct) : ""}>{signed(strength?.strengthPct)}%{!strength?.current && " · 未确认"}</strong></div>
          <div className="research-readout"><span>窗口 {strength?.start ?? "--"} → {strength?.end ?? "--"}</span><span>分子：申赎估算 {signed(strength?.flowYi)} 亿元</span><span>分母：{strength?.baseDate ?? "--"} 规模估算 {value(strength?.baseAssetsYi, 4)} 亿元</span><span>有效日 {strength?.available ?? 0}/{strengthDays}</span></div>
          {!strength?.current && <p className="research-warning">{strength?.reason || "尚未取得完整窗口强度，请刷新研究数据"}{!!strength?.missingDates.length && `；缺口：${strength.missingDates.join("、")}`}</p>}
          <p className="research-source">申赎等值估算 ÷ 期初规模估算。非收益率、非官方AUM、非外部现金流。</p>
        </section>
        </div>
        <ETFPriceFlow context={price} />
        <p className="research-source">{etf?.source} · 数据 {etf?.asOf ?? "--"} · 净值公告日 {etf?.latest.navAnnDate ?? "未提供"} · {etf?.sourceNote || etf?.note}</p>
      <details className="research-details"><summary>来源、计算边界与保存历史</summary>
        <p>{data.coverage.primaryStatus !== "ready" ? `${data.coverage.primaryReason || "新ETF接口不可用"}，已尝试旧份额与净值接口。` : "ETF使用每日份额规模接口。"} 数据请求独立于行业与成交榜，不等待它们成功。</p>
        <ul>{data.notes.map(note => <li key={note}>{note}</li>)}</ul>
        <p>强度 = 累计 Σ(当日份额变化 × 当日净值) ÷ 窗口前一交易日(份额 × 净值) × 100%。小规模ETF更敏感；跨类别比较需结合套利、流动性及份额折算。净值变化不是资金变化；疑似份额折算暂停估算，仍需公告核验。</p>
        <div className="source-links"><a href="https://tushare.pro/document/2?doc_id=207" target="_blank" rel="noreferrer">基金份额口径</a><a href="https://tushare.pro/document/2?doc_id=119" target="_blank" rel="noreferrer">净值与公告日期</a></div>
      </details>
    </>}
  </section>;
}
