import { useEffect, useMemo, useRef, useState } from "react";
import { fmt, growthCounts, STATES, type Industry } from "./research";
import { scatterLayout } from "./scatter";

export function Scatter({rows, scopeRows, selected, select, growthFilter, filter, query, period, clearFilters}: {
  rows: Industry[]; scopeRows: Industry[]; selected?: string; select(name: string): void;
  growthFilter: string; filter(state: string): void; query: string; period: string; clearFilters(): void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1000);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => {if (entry) setWidth(Math.max(640, Math.floor(entry.contentRect.width)));});
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const height = width < 800 ? 680 : 520;
  const chart = useMemo(() => scatterLayout(rows, width, height, scopeRows), [rows, width, height, scopeRows]);
  const {bounds: b, centerX: cx, centerY: cy, extentX, extentY, points} = chart;
  const current = rows.find(row => row.name === selected);
  const counts = growthCounts(scopeRows);
  return <><ul className="scatter-legend" aria-label="增长结构颜色图例">
    <li><button aria-pressed={growthFilter === "all"} onClick={() => filter("all")}>全部增长结构 <b>{scopeRows.length}</b></button></li>
    {Object.entries(STATES).map(([state, label]) => <li key={state} data-growth={state}>
      <button aria-pressed={growthFilter === state} onClick={() => filter(growthFilter === state ? "all" : state)}><i aria-hidden="true"/>{label} <b>{counts[state]}</b></button>
    </li>)}
    <li className="selection-key"><i aria-hidden="true"/>外圈及边框表示选中</li>
  </ul><div className="scatter-filter-note"><span>{query.trim() ? `搜索「${query.trim()}」范围` : "本期全部行业"}：{scopeRows.length} 个；当前绘制 {points.length} 个。点击图例筛选，再点取消；切换分类不缩放坐标轴。</span>
    {(query || growthFilter !== "all") && <button onClick={clearFilters}>清除全部筛选</button>}</div>
  <div className="scatter-readout" role="status" aria-label="图中选中行业" aria-live="polite">
    {current ? <><div><small>{period} · 累计口径</small><strong>{current.name}</strong><span>{STATES[current.quadrant]}</span></div>
      <dl><div><dt>营收同比</dt><dd>{fmt(current.revenueYoy, "%")}</dd></div><div><dt>利润同比</dt><dd>{fmt(current.profitYoy, "%")}</dd></div></dl></>
      : <span>当前筛选无匹配行业，可清除筛选恢复查看。</span>}
  </div><div className="scatter-scroll" ref={container} role="region" aria-label="增长结构图，可横向滚动" tabIndex={0}>
    {points.length ? <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="group" aria-label="营收与利润同比增长象限">
      <rect x={b.left} y={b.top} width={b.right - b.left} height={b.bottom - b.top} fill="var(--vibe-surface-muted)"/>
      <path d={`M${cx} ${b.top}V${b.bottom} M${b.left} ${cy}H${b.right}`} stroke="var(--vibe-border-strong)"/>
      <g className="quadrant-label"><text data-growth="repair" x={b.left} y="38">缩收增利 · 需核验基数</text><text data-growth="expansion" x={b.right} y="38" textAnchor="end">营收利润双增</text>
        <text data-growth="contraction" x={b.left} y={height - 18}>营收利润双降</text><text data-growth="pressure" x={b.right} y={height - 18} textAnchor="end">增收不增利</text></g>
      <text x={cx} y={height - 6} textAnchor="middle">营收累计同比 %</text><text x={b.left} y="16">利润累计同比 %</text>
      {[-1, 0, 1].map(tick => <g key={tick}><text x={cx + tick * (b.right - b.left) / 2} y={b.bottom + 18} textAnchor="middle">{fmt(tick * extentX)}</text>
        <text x={b.left - 8} y={cy - tick * (b.bottom - b.top) / 2 + 4} textAnchor="end">{fmt(tick * extentY, "", 0)}</text></g>)}
      <g className="scatter-connectors" aria-hidden="true">{points.map(point => point.labelBox && <line key={point.row.name} data-growth={point.row.quadrant} className={point.row.name === selected ? "active" : ""}
        x1={point.x} y1={point.y} x2={Math.max(point.labelBox.x, Math.min(point.x, point.labelBox.x + point.labelBox.width))} y2={point.labelBox.y + 12}/>)}</g>
      {points.map(point => <g key={point.row.name} data-growth={point.row.quadrant} className={`scatter-point ${point.row.name === selected ? "active" : ""}`} role="button" tabIndex={0} aria-pressed={point.row.name === selected}
        aria-label={`${point.row.name}，${STATES[point.row.quadrant]}，营收同比${point.row.revenueYoy}%，利润同比${point.row.profitYoy}%`}
        onClick={() => select(point.row.name)} onKeyDown={e => {if (e.key === "Enter" || e.key === " ") {e.preventDefault(); select(point.row.name);}}}>
        <title>{point.row.name} · {STATES[point.row.quadrant]} · 营收 {fmt(point.row.revenueYoy, "%")} / 利润 {fmt(point.row.profitYoy, "%")}</title>
        <circle className={`dot ${point.row.quadrant}${point.row.name === selected ? " active" : ""}`} cx={point.x} cy={point.y} r={point.row.name === selected ? 6 : 4}/>
        {point.labelBox && <g className="scatter-label"><rect x={point.labelBox.x} y={point.labelBox.y} width={point.labelBox.width} height={24} rx={3}/>
          <text x={point.labelBox.x + 5} y={point.labelBox.y + 16}>{point.label}</text></g>}
      </g>)}
    </svg> : <p className="scatter-empty">{rows.length ? "当前行业同比缺失或不可比，不绘制为零；原始数值仍保留在下方矩阵。" : "当前条件下没有可绘制行业。"}</p>}
  </div><p>简称直接标注，引线对应原始坐标；点击简称可联动行业诊断，悬停查看全名，支持键盘选择。窄屏可横向滚动。</p>
  {points.some(point => !point.labelBox) && <div className="scatter-overflow">密集标签补充：{points.filter(point => !point.labelBox).map(point => <button key={point.row.name} onClick={() => select(point.row.name)}>{point.row.name} · 营收 {fmt(point.row.revenueYoy, "%")} / 利润 {fmt(point.row.profitYoy, "%")}</button>)}</div>}
  </>;
}
