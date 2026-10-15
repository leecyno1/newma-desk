import type { AppetiteHorizon } from "./AppetiteResearch";
import type { AppetiteResearchData } from "./types";

type Target = "emotion" | "etf" | "liquidity" | "sectors";
const targets: Record<string, Target> = { price: "emotion", etf: "etf", margin: "emotion", dr007: "liquidity", spreadBp: "liquidity", credit: "liquidity" };
const format = (value: number | null) => value == null ? "--" : `${value > 0 ? "+" : ""}${value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;

export function overviewContext(data: AppetiteResearchData | null, days: AppetiteHorizon, pending: boolean) {
  return data ? { generatedAt: data.generatedAt, expectedDate: data.expectedDate, selectedWindow: data.windows[days],
    classification: data.breadth.classification, snapshotOnly: pending,
    timeScope: "权益按所选交易日；利率按观测日；信用按月度；行业排行榜仅为单日东财一级",
    interpretation: pending ? "更新中或失败，保留快照不代表本次确认" : "分别核对日期、来源与覆盖，不合成市场预测", notes: data.notes } : null;
}

export function OverviewBrief({ data, loading, error, days, setDays, open }: {
  data: AppetiteResearchData | null; loading: boolean; error: string; days: AppetiteHorizon;
  setDays: (value: AppetiteHorizon) => void; open: (view: Target) => void;
}) {
  const window = data?.windows[days], pending = loading || !!error;
  const classification = data?.breadth.classification;
  return <section className="overview-brief" aria-label="资金决策总览">
    <div className="liquidity-masthead"><span>CAPITAL / DECISION DESK</span><p>先看资金分歧，再沿证据深入<span>金额不混加 · 不生成综合分数</span></p></div>
    <div className="liquidity-toolbar"><span>权益观察 {window?.start ?? "--"} → {window?.end ?? "--"}</span><div className="research-period" aria-label="总览观察窗口">{([5, 20] as const).map(n => <button key={n} aria-pressed={days === n} onClick={() => setDays(n)}>{n}交易日</button>)}</div></div>
    {error && <p className="error-banner">{error}{data ? " · 保留上次快照，不代表更新成功" : ""}</p>}
    {!window ? <div className="table-empty">{loading ? "正在对齐配置、融资、资金价格和信用证据…" : "研究证据未取得，不用旧状态标签代替"}</div> : <>
      <div className="overview-relations">{window.relationships.map(row => <button key={row.id} type="button" onClick={() => open("emotion")}><span>{row.id === "price-etf" ? "价格 × ETF配置" : "价格 × 融资"}</span><strong>{row.title}</strong><small>{pending ? "历史快照 / 待更新" : row.status === "incomplete" ? "证据未齐" : row.status === "divergent" ? "存在背离" : "核对窗口内方向"} →</small></button>)}</div>
      <div className="overview-evidence">{window.evidence.map(row => <button type="button" key={row.id} data-overview-evidence={row.id} onClick={() => open(targets[row.id] ?? "emotion")} title={`${row.source}：${row.note}`}>
        <span>{row.name} <i>↗</i></span><strong>{format(row.value)}<small>{row.unit}</small></strong><small>{row.scope} · {row.asOf ?? "无日期"}</small>
        <em>{pending ? "快照待更新" : row.current ? "来源和窗口可用" : "未确认，不参与方向"}</em></button>)}</div>
      <div className="overview-sector-scope"><div><strong>行业排行仅使用东财一级 · {data?.breadth.asOf ?? "无日期"}{pending ? " · 保留快照待更新" : ""}</strong><span>{classification?.current ? `同日层级匹配 ${classification.matched}/${classification.total}；一级 ${classification.counts.L1 ?? 0} · 二级 ${classification.counts.L2 ?? 0} · 三级 ${classification.counts.L3 ?? 0} · 待核验 ${classification.counts.unknown ?? 0}` : `一级目录待核验：${classification?.reason || "来源或日期未齐"}，不以全层级替代`}</span><small>层级分开避免父子行业混计；成分交叉未独立核验，不汇总全市场净流。</small></div><button type="button" onClick={() => open("sectors")}>查看分层行业 →</button></div>
    </>}
  </section>;
}
