import { fmt, type Snapshot } from "./research";

export interface Operations {
  status: "ready" | "partial" | "unavailable";
  scope: string; periodEnd: string; sourceUrl: string; publishedAt: string; reason: string; boundary: string;
  rows: {name: string; inventoryDays: number | null; receivableDays: number | null;
    debtRatio: number | null; expensePer100Revenue: number | null;
    inventoryDaysYoyChange?: number | null; receivableDaysYoyChange?: number | null;
    raw: Record<string, string>}[];
}

export function OperationsPanel({data, industry}: {data: Snapshot; industry?: string}) {
  const evidence = data.operations;
  const national = evidence?.rows.find(row => row.name === "总计");
  const slower = national && [national.inventoryDaysYoyChange, national.receivableDaysYoyChange].some(value => value != null && value > 0);
  return <section className="operations-panel production-panel" aria-label="经营质量背景">
    <div className="section-title"><div><small>WORKING CAPITAL / CONTEXT</small><h2>库存与回款 · 经营质量背景</h2></div>
      <span>全国与三大门类 · 非细分行业数据</span></div>
    <p>{data.period} · 月末指标截至 {data.periodEnd} · 发布 {data.publishedAt}</p>
    {!evidence?.rows.length ? <p role="status">{evidence?.reason || "本报告未取得经营质量表"}；缺失不代表周转正常。</p> : <>
      {evidence.status === "partial" && <p role="status">{evidence.reason}</p>}
      <div className="operations-grid">{evidence.rows.map(row => <article key={row.name}>
        <h3>{row.name === "总计" ? "全国规模以上工业" : row.name}</h3><dl>
          <div><dt>产成品存货周转</dt><dd>{fmt(row.inventoryDays, " 天")}</dd></div>
          <div><dt>应收账款回收期</dt><dd>{fmt(row.receivableDays, " 天")}</dd></div>
          <div><dt>资产负债率</dt><dd>{fmt(row.debtRatio, "%")}</dd></div>
          <div><dt>累计每百元营收费用</dt><dd>{fmt(row.expensePer100Revenue, " 元", 2)}</dd></div>
        </dl>{row.name === "总计" && <p>较上年同期：库存周转 {fmt(row.inventoryDaysYoyChange, " 天")}；回款周期 {fmt(row.receivableDaysYoyChange, " 天")}。正值表示延长，— 表示未取得。</p>}
      </article>)}</div>
      <div className="production-reading"><h3>{slower ? "全国周转有放缓信号，利润增长仍需现金流验证" : "核验方向：利润能否转化为现金"}</h3>
        <p>{slower ? "官方同比天数显示，至少一项周转周期延长；这不是对任何细分行业的风险定级。" : "仅有本期天数不能判断改善或恶化；不能因未出现提示就认定没有风险。"}</p>
        <ol><li>库存：结合销量、订单及产品价格，区分主动备货与被动积压。</li>
          <li>回款：核对目标公司应收账龄、减值及经营现金流，不能仅凭利润增长认定回款健康。</li>
          <li>负债：结合债务期限与可用现金，不把负债率单独当作安全垫。</li></ol>
      </div><p><a href={evidence.sourceUrl} target="_blank" rel="noreferrer">经济效益指标原表及同比说明 ↗</a> · {evidence.boundary}</p>
    </>}
    <p className="caution">{industry ? `当前行业「${industry}」` : "当前筛选"}：尚无细分行业库存、回款及现金流证据；以上背景不参与该行业增长分类或诊断评级。</p>
  </section>;
}
