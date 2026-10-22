import { changeFor, fmt, researchQuestions, type Industry, type Snapshot } from "./research";
import type { ProductionEvidence } from "./production";
import type { PriceEvidence } from "./prices";
import { capacityPeriodEnd, type CapacityEvidence } from "./capacity";

export function diagnosisFor(report: Snapshot | null, selected: Industry | undefined, production: ProductionEvidence, prices: PriceEvidence, publications: Snapshot[], historyStatus: string, capacity?: CapacityEvidence) {
  if (!report || !selected) return null;
  const usable = (e: ProductionEvidence | PriceEvidence) => e.status === "ready" && e.industry === selected.name && e.publication?.periodEnd === report.periodEnd;
  const p = usable(production) ? production : null;
  const price = usable(prices) ? prices : null;
  const c = capacity?.status === "ready" && capacity.industry === selected.name && capacity.financialPeriodEnd === report.periodEnd && capacity.publication?.periodEnd === capacityPeriodEnd(report.periodEnd) ? capacity : null;
  const metric = price?.metric;
  const products = p?.metrics.filter(row => row.kind === "product") ?? [];
  const quantities = products.filter(row => row.monthYoy != null);
  const productSplit = quantities.some(row => row.monthYoy! > 0) && quantities.some(row => row.monthYoy! < 0);
  const priceSplit = metric?.monthYoy != null && quantities.some(row => row.monthYoy! * metric.monthYoy! < 0);
  const profitSplit = selected.profitYoy != null && products.some(row => row.cumulativeYoy != null && row.cumulativeYoy * selected.profitYoy! < 0);
  const growth = selected.profitYoy == null ? "利润同比缺失或不可比" : selected.profitYoy > 0 ? "累计利润增长" : selected.profitYoy < 0 ? "累计利润下降" : "累计利润零增长";
  const hasProduction = p?.metrics.some(row => row.monthYoy != null || row.cumulativeYoy != null);
  const hasPrice = metric && [metric.monthMom, metric.monthYoy, metric.yearToDateAverageYoy].some(value => value != null);
  const headline = `${growth}；${productSplit ? "细分产品产量分化" : priceSplit ? "当月量价方向分化" : profitSplit ? "累计产量与盈利方向分化" : !hasProduction || !hasPrice ? "量价证据尚待补齐" : "已有量价补证，持续性仍待验证"}`;
  const unavailable = (status: string) => ({idle: "未载入", loading: "读取中", failed: "读取失败", mismatch: "期间不匹配"}[status] ?? "无直接匹配项");
  const financialComplete = selected.revenueYoy != null && selected.profitYoy != null;
  const productionValues = p?.metrics.flatMap(row => [row.monthYoy, row.cumulativeYoy]) ?? [];
  const priceValues = metric ? [metric.monthMom, metric.monthYoy, metric.yearToDateAverageYoy] : [];
  const coverage = (values: (number | null)[]) => !values.length ? "无直接匹配项" : values.every(v => v != null) ? "已取得" : values.every(v => v == null) ? "同比缺失 / 不可比" : "部分口径缺失";
  const change = historyStatus === "ready" ? changeFor(report, publications, selected.name) : null;
  const previous = change?.previousSourceUrl ? publications.find(item => item.sourceUrl === change.previousSourceUrl) : null;
  const facts = [
    {label: "财务 · 累计", state: financialComplete ? "已取得" : "同比缺失 / 不可比",
      text: `${report.period}：营收同比 ${fmt(selected.revenueYoy, "%")}；利润同比 ${fmt(selected.profitYoy, "%")}。`,
      sourceUrl: report.sourceUrl, publishedAt: report.publishedAt},
    {label: "生产 · 实际增加值 / 产品产量", state: p ? coverage(productionValues) : unavailable(production.status),
      text: p?.metrics.length ? p.metrics.map(row => `${row.name}${row.kind === "valueAdded" ? "增加值" : "产量"}：当月同比 ${fmt(row.monthYoy, "%")} / 累计同比 ${fmt(row.cumulativeYoy, "%")}`).join("；") : production.error || "未取得当前行业同期间生产指标，不以全国总量替代。",
      sourceUrl: p?.publication?.sourceUrl ?? null, publishedAt: p?.publication?.publishedAt ?? null},
    {label: "价格 · 行业 PPI", state: price ? coverage(priceValues) : unavailable(prices.status),
      text: metric ? `${price!.publication!.monthlyPeriod}：环比 ${fmt(metric.monthMom, "%")} / 同比 ${fmt(metric.monthYoy, "%")}；年内平均同比 ${fmt(metric.yearToDateAverageYoy, "%")}。` : prices.error || "未取得当前行业同期间价格，不以全国PPI替代。",
      sourceUrl: price?.publication?.sourceUrl ?? null, publishedAt: price?.publication?.publishedAt ?? null},
    {label: "变化 · 相邻累计期", state: change ? change.revenueYoyPp == null && change.profitYoyPp == null ? "不可比较" : "已取得" : unavailable(historyStatus),
      text: change ? `营收同比变化 ${fmt(change.revenueYoyPp)} 个百分点；利润同比变化 ${fmt(change.profitYoyPp)} 个百分点。${change.reason}。` : "尚未载入历史对照；不据单期报告确认趋势。",
      sourceUrl: previous?.sourceUrl ?? null, publishedAt: previous?.publishedAt ?? null},
    {label: "产能 · 季度参考", state: c?.metric ? coverage([c.metric.quarterRate, c.metric.quarterYoyPp]) : unavailable(capacity?.status ?? "idle"),
      text: c?.metric ? `${c.publication!.quarterPeriod}利用率 ${fmt(c.metric.quarterRate, "%")}；同比变化 ${fmt(c.metric.quarterYoyPp)} 个百分点。${c.timingNote}` : capacity?.error || "未取得当前行业季度产能证据；不以全国或制造业替代。",
      sourceUrl: c?.metric ? c.publication!.sourceUrl : null, publishedAt: c?.metric ? c.publication!.publishedAt : null},
  ] as const;
  const observations = [...new Set([...(hasProduction ? p?.observations ?? [] : []), ...(hasPrice ? price?.observations ?? [] : []), ...(c?.metric ? c.observations : [])])];
  const gaps = [...new Set([...(p?.missing ?? []), ...(price?.missing ?? []), ...(!c?.metric ? ["当前行业季度产能证据未取得"] : []), "细分行业库存、订单、产销率及估值仍待补证；全国背景不能代替行业证据。不能据此判断买卖时点，也不能重构营收或量化利润归因。追踪利润质量还需目标公司现金流。"] )];
  return {industry: selected.name, period: report.period, periodEnd: report.periodEnd, headline, facts, observations, gaps,
    questions: researchQuestions(selected.name),
    timingNotes: [p?.timingNote, price?.timingNote, c?.publicationNote].filter((note): note is string => Boolean(note)),
    boundary: "规则诊断，不是预测或综合评分。生产与价格仅使用同统计期证据；当月与累计不混算。产能使用财务截止时最近已结束季度，不外推后续月份或据此判断订单。历史网页为现时读取，不代表当时可知。"};
}
export type Diagnosis = ReturnType<typeof diagnosisFor>;
