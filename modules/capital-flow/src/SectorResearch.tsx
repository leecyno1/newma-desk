import { useMemo, type ReactNode } from "react";
import { FlowBars } from "./FundingResearch";
import type { SectorCategory, SectorLevel, SectorResearchData } from "./types";

export const SECTOR_LEVELS: Record<SectorLevel, string> = { L1: "东财一级", L2: "东财二级", L3: "东财三级", all: "全部层级", unknown: "待核验" };

const CATEGORIES: Record<SectorCategory, string> = { industry: "行业及子行业", concept: "概念", region: "地域" };
function value(amount: number | null | undefined, signed = false) {
  return amount == null ? "--" : `${signed && amount > 0 ? "+" : ""}${amount.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
}
function tone(amount: number | null | undefined) {
  return amount == null || amount === 0 ? "" : amount > 0 ? "positive-text" : "negative-text";
}

export function SectorResearchPanel({ data, loading, error, category, setCategory, level, setLevel, select, sort, setSort, days, setDays, query, setQuery, quadrant }: {
  data: SectorResearchData | null; loading: boolean; error: string;
  category: SectorCategory; setCategory: (category: SectorCategory) => void; select: (code: string) => void;
  level: SectorLevel; setLevel: (level: SectorLevel) => void;
  sort: "strength" | "net" | "pct"; setSort: (sort: "strength" | "net" | "pct") => void;
  days: number; setDays: (days: number) => void; query: string; setQuery: (query: string) => void; quadrant: ReactNode;
}) {
  const boards = useMemo(() => (data?.boards ?? []).filter(row => `${row.name} ${row.code}`.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => (sort === "net" ? b.net ?? -Infinity : sort === "pct" ? b.pct ?? -Infinity : b.netSharePct ?? -Infinity)
      - (sort === "net" ? a.net ?? -Infinity : sort === "pct" ? a.pct ?? -Infinity : a.netSharePct ?? -Infinity)), [data, query, sort]);
  const selected = data?.selected;
  const summary = selected?.summary;
  const net = summary?.net5dYi, price = summary?.price5dPct;
  const pattern = loading || error || selected?.fetchStatus !== "ready" || selected?.usingSaved || data?.calendar.status !== "ready" || selected?.asOf !== data?.expectedDate ? "来源或日期待核验，保留历史，不确认当前方向"
    : net == null || price == null ? "5日证据不完整，暂不判断共振或背离"
    : net === 0 || price === 0 ? "5日净额或价格无方向，保持观察"
    : net > 0 && price > 0 ? "5日资金与价格同向走强"
    : net < 0 && price > 0 ? "5日价格上涨但大额订单净流出"
    : net > 0 && price < 0 ? "5日价格下跌但大额订单净流入"
    : "5日资金与价格同向走弱";
  return <section className="sector-research" aria-label="板块持续性研究">
    <div className="sector-research-controls">
      <div className="sector-sort" aria-label="板块分类">{(Object.keys(CATEGORIES) as SectorCategory[]).map(key => <button type="button" key={key} className={key === category ? "active" : ""} aria-pressed={key === category} onClick={() => setCategory(key)}>{CATEGORIES[key]}</button>)}</div>
      <input aria-label="板块名称或代码" placeholder="筛选名称或板块代码" value={query} onChange={event => setQuery(event.target.value)} />
      <span>{data?.asOf ?? "等待交易日"}{loading ? " · 更新中" : ""}</span>
    </div>
    {category === "industry" && <div className="sector-level-controls"><div className="research-period" aria-label="行业层级">{(Object.keys(SECTOR_LEVELS) as SectorLevel[]).map(key => <button key={key} type="button" aria-pressed={level === key} onClick={() => setLevel(key)}>{SECTOR_LEVELS[key]}</button>)}</div>
      <small>同日目录匹配 {data?.classification?.matched ?? 0}/{data?.classification?.total ?? 0} · 层级未齐不混入一级</small></div>}
    {category === "industry" && data?.classification && (!data.classification.current || (data.classification.counts.unknown ?? 0) > 0) && <p className="research-warning">行业层级待核验：{data.classification.reason || "存在日期不齐、缺失或冲突"}；{data.classification.counts.unknown} 个归入待核验，不用旧层级补齐当前一级。</p>}
    {error ? <p className="error-banner">{error}</p> : null}
    {data?.coverage.status !== "ready" ? data && <p className="research-warning">{data.coverage.reason}{data.coverage.usingSaved && "；使用已保存排名，不代表最新行情"}</p> : null}
    {data?.calendar.status !== "ready" ? data && <p className="research-warning">交易日历更新异常：{data.calendar.reason}</p> : null}
    {data?.coverage.selectedNotFound ? <p className="research-warning">当前分类/层级没有该板块；未把其他范围的数据接入。</p> : null}
    {!data ? <div className="table-empty">{loading ? "正在读取分分类板块与历史…" : "未取得板块研究数据"}</div> : <>
      <div className="sector-research-grid"><div>{quadrant}<small className="research-source">四象限观察当前分类/层级完整板块池，未应用名称筛选。</small></div><section>
        <div className="sector-ranking-head"><strong>{boards.length}/{data.boards.length} 个板块 · 点击研究</strong><div className="sector-sort" aria-label="行业排序">{(["strength", "net", "pct"] as const).map(key => <button type="button" key={key} className={sort === key ? "active" : ""} onClick={() => setSort(key)}>{key === "strength" ? "净占比" : key === "net" ? "净流" : "涨跌"}</button>)}</div></div>
        <div className="research-table-scroll sector-research-ranking"><table className="research-table"><thead><tr><th>板块 / 代码</th><th>涨跌 %</th><th>净额 亿元</th><th>净占比 %</th></tr></thead><tbody>{boards.map(board => <tr key={board.code} className={board.code === selected?.code ? "selected" : ""}>
          <td><button type="button" onClick={() => select(board.code!)} aria-pressed={board.code === selected?.code}><strong>{board.name}</strong><small>{board.code}{category === "industry" ? ` · ${SECTOR_LEVELS[board.level ?? "unknown"]}` : ""}</small></button></td>
          <td className={tone(board.pct)}>{value(board.pct, true)}</td><td className={tone(board.net)}>{value(board.net, true)}</td><td>{value(board.netSharePct, true)}</td>
        </tr>)}</tbody></table></div>
      </section></div>
      <div className="research-source">{data.source} · 同代码去重 {data.coverage.duplicatesRemoved} 条 · {category === "industry" ? `${SECTOR_LEVELS[level]} · ${data.classification?.current ? "层级按同日目录匹配" : "层级待核验"}` : CATEGORIES[category]}；成分交叉未核验，不合计全市场。</div>
      {selected ? <section className="sector-history" aria-label="所选板块历史">
        <div className="research-subhead"><h3>{selected.name} · 大额订单历史</h3><div className="research-period">{[20, 60].map(period => <button type="button" aria-pressed={days === period} key={period} onClick={() => setDays(period)}>{period}日</button>)}</div></div>
        {selected.fetchStatus !== "ready" && <p className="research-warning">{selected.sourceNote}{selected.usingSaved && "；使用保存历史"}</p>}
        <div className="research-metrics">
          <div><span>1 / 5 / 20日净额 · 亿元</span><strong>{value(summary?.net1dYi, true)} / {value(summary?.net5dYi, true)}</strong><small>20日 {value(summary?.net20dYi, true)} · 缺失不补零</small></div>
          <div><span>连续净流 · 严格交易日</span><strong>{summary?.streak.direction === "in" ? "流入" : summary?.streak.direction === "out" ? "流出" : summary?.streak.direction === "flat" ? "持平" : "缺失"} {summary?.streak.days ?? 0}<small>日</small></strong><small>遇缺失或方向改变即中断</small></div>
          <div><span>当日净额 · 历史分位</span><strong>{value(summary?.baseline.percentile)}<small>%</small></strong><small>前60日有效样本 {summary?.baseline.samples}/{summary?.baseline.expected} · 非概率</small></div>
          <div><span>5 / 20日指数价格变化</span><strong>{value(summary?.price5dPct, true)}<small>%</small></strong><small>20日 {value(summary?.price20dPct, true)}% · 复合日涨跌</small></div>
        </div>
        <p className="sector-pattern">{pattern}<small>只描述历史交易代理，不代表机构持仓变化或买卖建议。数据截止 {selected.asOf ?? "未知"}</small></p>
        <FlowBars dates={data.calendar.dates.slice(-days)} points={selected.points.map(point => ({ ...point }))} field="net" label={`${selected.name}大额订单净额历史`} />
        <details className="research-details"><summary>历史日明细</summary><div className="research-table-scroll"><table className="research-table"><thead><tr><th>日期</th><th>净额 亿元</th><th>超大单净额</th><th>大单净额</th><th>净占比 %</th><th>指数涨跌 %</th></tr></thead><tbody>{selected.points.slice(-days).reverse().map(point => <tr key={point.date}><td>{point.date}</td><td className={tone(point.net)}>{value(point.net, true)}</td><td>{value(point.superNetYi, true)}</td><td>{value(point.largeNetYi, true)}</td><td>{value(point.netSharePct, true)}</td><td>{value(point.pct, true)}</td></tr>)}</tbody></table></div></details>
      </section> : <p className="research-source">没有可研究的板块，不能解释为资金为零。</p>}
      <details className="research-details"><summary>分类与历史口径</summary><ul>{data.notes.map(note => <li key={note}>{note}</li>)}</ul><a href="https://tushare.pro/document/2?doc_id=344" target="_blank" rel="noreferrer">资金来源字段说明</a>{data.classification && <p><a href={data.classification.url} target="_blank" rel="noreferrer">同日目录与层级字段说明</a> · {data.classification.asOf ?? "无日期"} · {data.classification.note}</p>}</details>
    </>}
  </section>;
}
