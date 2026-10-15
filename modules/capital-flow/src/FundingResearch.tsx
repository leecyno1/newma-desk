import type { CapitalResearch, ETFResearch } from "./types";

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
  return <div className="research-table-scroll"><table className="research-table"><thead><tr>
    <th>ETF / 配置类别</th><th>份额 万份</th><th>NAV 元</th><th>1日估算 亿元</th><th>5日 亿元</th><th>20日 亿元</th><th>数据日期 / 状态</th>
  </tr></thead><tbody>{rows.map(row => <tr key={row.code} className={selected === row.code ? "selected" : ""}>
    <td><button type="button" onClick={() => select(row.code)} aria-pressed={selected === row.code}><strong>{row.name}</strong><small>{row.code} · {row.category}</small></button></td>
    <td>{value(row.latest.sharesWan, 2)}</td><td>{value(row.latest.nav, 4)}</td>
    <td className={tone(row.summary.flow1dYi)}>{signed(row.summary.flow1dYi)}</td>
    <td className={tone(row.summary.flow5dYi)}>{signed(row.summary.flow5dYi)}</td>
    <td className={tone(row.summary.flow20dYi)}>{signed(row.summary.flow20dYi)}</td>
    <td><span>{row.asOf ?? "--"}</span><small title={row.sourceNote || row.note}>{row.status === "ready" ? "份额 / 净值齐备" : row.usingSaved ? "保存历史 · 更新失败" : row.status === "partial" ? "部分缺失 / 待核验" : "未取得记录"}</small></td>
  </tr>)}</tbody></table></div>;
}

export function FundingResearch({ data, loading, error, mode, selected, select, days, setDays }: {
  data: CapitalResearch | null; loading: boolean; error: string;
  mode: "overview" | "etf" | "emotion"; selected: string; select: (code: string) => void;
  days: number; setDays: (days: number) => void;
}) {
  const etf = data?.etfs.find(row => row.code === selected) ?? data?.etfs[0];
  const leverage = data?.leverage;
  const dates = data?.calendar.dates.slice(-days) ?? [];
  const broad = data?.groups.find(group => group.category === "宽基");
  const period = <div className="research-period" aria-label="历史观察窗口">{[20, 60].map(period => <button key={period} type="button" aria-pressed={days === period} onClick={() => setDays(period)}>{period}日</button>)}</div>;
  return <section className="funding-research" aria-label="配置与杠杆研究">
    <div className="research-heading"><div><span>FUNDING RESEARCH</span><h2>{mode === "etf" ? "ETF 配置与申赎" : mode === "emotion" ? "融资变化与杠杆基线" : "配置资金与杠杆变化"}</h2></div><span>{data?.expectedDate ?? "等待交易日"} · 人民币口径{loading ? " · 更新中" : ""}</span></div>
    {error ? <p className="error-banner">{error}</p> : null}
    {!data ? <div className="table-empty">{loading ? "正在读取真实份额、净值和沪深北融资历史…" : "尚未取得配置与融资研究数据"}</div> : <>
      {data.calendar.status !== "ready" ? <p className="research-warning">交易日历不可用，日窗口结论需复核：{data.calendar.reason}</p> : null}
      {leverage?.usingSaved ? <p className="research-warning">融资更新失败，以下使用已保存历史：{leverage.sourceNote} · 数据截止 {leverage.asOf ?? "未知"}</p> : null}
      <div className="research-metrics">
        {mode !== "emotion" && <div><span>宽基观察池 · 5日申赎估算</span><strong className={tone(broad?.flow5dYi)}>{signed(broad?.flow5dYi)}<small>亿元</small></strong><small>{broad?.available ?? 0}/{broad?.count ?? 0} 只 · 不是全市场</small></div>}
        <div><span>沪深北融资余额</span><strong>{value(leverage?.latest.balanceYi)}<small>亿元</small></strong><small>{leverage?.asOf ?? "--"} · 三家交易所缺一不合计</small></div>
        <div><span>融资净增加 · 5日</span><strong className={tone(leverage?.summary.net5dYi)}>{signed(leverage?.summary.net5dYi)}<small>亿元</small></strong><small>融资买入减偿还，不是市场资金流入</small></div>
        <div><span>融资余额 · 历史分位</span><strong>{value(leverage?.summary.baseline.percentile, 1)}<small>%</small></strong><small>前60日可用样本 {leverage?.summary.baseline.samples ?? 0}/{leverage?.summary.baseline.expected ?? 0} · 非风险概率</small></div>
      </div>
      {mode === "etf" ? <>
        <div className="research-subhead"><h3>代表 ETF 观察池</h3><span>{data.coverage.etfAvailable}/{data.coverage.etfTotal} 只当日齐备 · 点击标的查看历史</span></div>
        <ETFTable rows={data.etfs} selected={etf?.code ?? selected} select={select} />
        <div className="research-subhead"><h3>{etf?.name} · 日申赎金额等值估算</h3>{period}</div>
        <FlowBars dates={dates} points={(etf?.points ?? []).map(point => ({ ...point }))} field="flowYi" label={`${etf?.name}申赎估算历史`} />
        <div className="research-readout"><strong>份额变化 {signed(etf?.latest.shareChangeWan)} 万份</strong><span>单位净值变化 {signed(etf?.latest.navChangePct)}%（非总回报）</span><span>20日申赎估算 {signed(etf?.summary.flow20dYi)} 亿元</span></div>
        <div className="research-readout"><span>当日申赎估算历史分位 {value(etf?.summary.baseline.percentile, 1)}%</span><span>前60日均值 {signed(etf?.summary.baseline.mean)} 亿元 · 有效样本 {etf?.summary.baseline.samples ?? 0}/{etf?.summary.baseline.expected ?? 0}</span><span>净值公告日 {etf?.latest.navAnnDate ?? "未提供"}</span></div>
        <p className="research-source">{etf?.source} · 数据 {etf?.asOf ?? "--"} · {etf?.sourceNote || etf?.note}</p>
      </> : <div className={mode === "overview" ? "research-dual" : "research-leverage"}>
        {mode === "overview" && <div><div className="research-subhead"><h3>配置方向 · 仅限代表池</h3><span>申赎估算 亿元</span></div><div className="research-table-scroll"><table className="research-table group-table"><thead><tr><th>类别 / 样本</th><th>1日</th><th>5日</th><th>20日</th></tr></thead><tbody>{data.groups.map(group => <tr key={group.category}><td>{group.category}<small>{group.available}/{group.count} 只齐备</small></td><td className={tone(group.flow1dYi)}>{signed(group.flow1dYi)}</td><td className={tone(group.flow5dYi)}>{signed(group.flow5dYi)}</td><td className={tone(group.flow20dYi)}>{signed(group.flow20dYi)}</td></tr>)}</tbody></table></div></div>}
        <div><div className="research-subhead"><h3>每日融资净增加</h3>{period}</div><FlowBars dates={dates} points={(leverage?.points ?? []).map(point => ({ ...point }))} field="netYi" label="沪深北融资净增加历史" /><p className="research-source">{leverage?.source} · {leverage?.sourceNote || leverage?.note}</p></div>
      </div>}
      {mode === "emotion" && <>
        <div className="research-readout"><strong>1日净增加 {signed(leverage?.summary.net1dYi)} 亿元</strong><span>20日净增加 {signed(leverage?.summary.net20dYi)} 亿元</span><span>融资买入 {value(leverage?.latest.buyYi)} / 偿还 {value(leverage?.latest.repayYi)} 亿元</span></div>
        <details className="research-details"><summary>融资原始日明细与交易所覆盖</summary><div className="research-table-scroll"><table className="research-table"><thead><tr><th>日期</th><th>融资余额 亿元</th><th>买入</th><th>偿还</th><th>净增加</th><th>交易所覆盖</th></tr></thead><tbody>{leverage?.points.slice(-20).reverse().map(point => <tr key={point.date}><td>{point.date}</td><td>{value(point.balanceYi)}</td><td>{value(point.buyYi)}</td><td>{value(point.repayYi)}</td><td className={tone(point.netYi)}>{signed(point.netYi)}</td><td>{point.exchanges.join(" / ")}{!point.complete && " · 不完整"}</td></tr>)}</tbody></table></div></details>
      </>}
      <details className="research-details"><summary>来源、计算边界与保存历史</summary>
        <p>{data.coverage.primaryStatus !== "ready" ? `${data.coverage.primaryReason || "新ETF接口不可用"}，已尝试旧份额与净值接口。` : "ETF使用每日份额规模接口。"} 数据请求独立于行业与成交榜，不等待它们成功。</p>
        <ul>{data.notes.map(note => <li key={note}>{note}</li>)}</ul>
        <p>净值变化不是资金变化；疑似份额折算暂停估算，仍需公告核验。融资扩张不等于行情看涨。</p>
        <div className="source-links"><a href="https://tushare.pro/document/2?doc_id=207" target="_blank" rel="noreferrer">基金份额口径</a><a href="https://tushare.pro/document/2?doc_id=119" target="_blank" rel="noreferrer">净值与公告日期</a><a href="https://tushare.pro/document/2?doc_id=58" target="_blank" rel="noreferrer">融资融券口径</a></div>
      </details>
    </>}
  </section>;
}
