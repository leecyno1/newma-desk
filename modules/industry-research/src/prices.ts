import type { ProductionEvidence } from "./production";
import type { Industry, Snapshot } from "./research";

export interface PriceMetric {
  name: string; monthMom: number | null; monthYoy: number | null; yearToDateAverageYoy: number | null; raw: Record<string, string>;
}
export interface Prices {
  title: string; sourceUrl: string; publisher: string; periodEnd: string; monthlyPeriod: string; averagePeriod: string;
  publishedAt: string; fetchedAt: string; cached: boolean; freshness: "unknown" | "stale"; unit: "%";
  metrics: PriceMetric[]; baseNotes: string[]; limitations: string[]; discovery: string; discoveryErrors: {sourceUrl: string; reason: string}[];
}
export function pricesFor(report: Snapshot | null, selected: Industry | undefined, source: Prices | null, status: string, error: string, production?: ProductionEvidence) {
  const matched = report && selected && source?.periodEnd === report.periodEnd ? source : null;
  const metric = matched?.metrics.find(row => row.name === selected?.name) ?? null;
  const productionMatches = Boolean(matched && production?.publication?.periodEnd === matched.periodEnd && production.industry === selected?.name);
  const quantities = productionMatches ? production!.metrics.filter(row => row.kind === "product" && row.monthYoy !== null) : [];
  const observations: string[] = [];
  if (metric) {
    if (metric.monthMom != null && metric.monthYoy != null && metric.monthMom * metric.monthYoy < 0) {
      observations.push("当月环比与同比方向不同：短期变动与同比基数需分开观察，不能仅凭环比确认价格趋势反转。");
    }
    if (metric.monthYoy != null && quantities.some(row => row.monthYoy! * metric.monthYoy! < 0)) {
      observations.push("当月行业出厂价格与部分相关产品产量同比方向相反，不宜概括为量价齐升；两者样本和覆盖不同。");
    } else if (metric.monthYoy != null && metric.monthYoy !== 0 && quantities.length && quantities.every(row => row.monthYoy! * metric.monthYoy! > 0)) {
      observations.push("当月价格与已加载产品产量同比同向变化；只是方向核验，不等于需求或利润贡献已确认。");
    }
    if (metric.yearToDateAverageYoy != null && selected?.profitYoy != null && selected.profitYoy > 0) {
      if (metric.yearToDateAverageYoy > 0) observations.push("累计利润增长与年内平均出厂价格上涨并存；价格可能是待验证因素，仍需成本、产品结构及基数证据，不能量化归因。");
      else if (metric.yearToDateAverageYoy < 0) observations.push("累计利润增长但年内平均出厂价格下降，不能以行业普遍涨价解释增利；需核验成本、结构与基数。");
    }
  }
  const missing = matched ? [
    ...(!metric ? ["原表没有当前行业的直接匹配项，不用全国PPI或相似名称行业替代"] : []),
    ...(metric && [metric.monthMom, metric.monthYoy, metric.yearToDateAverageYoy].some(value => value == null) ? ["部分价格口径缺失或不可比，不补零"] : []),
    ...(!quantities.length ? ["尚无已加载且可比的同期产品产量，未作量价方向对照"] : []),
    "现货、长协与公司实际售价、库存及订单仍待补证",
  ] : [];
  return {status: !report ? "idle" : source && !matched && selected ? "mismatch" : status, error,
    industry: selected?.name ?? null, metric, observations, missing,
    publication: matched ? {title: matched.title, sourceUrl: matched.sourceUrl, periodEnd: matched.periodEnd,
      monthlyPeriod: matched.monthlyPeriod, averagePeriod: matched.averagePeriod, publishedAt: matched.publishedAt,
      fetchedAt: matched.fetchedAt, cached: matched.cached, freshness: matched.freshness, industries: matched.metrics.length} : null,
    productionCheck: quantities.length ? {sourceUrl: production!.publication!.sourceUrl, periodEnd: production!.publication!.periodEnd,
      metrics: quantities.map(row => ({name: row.name, monthYoy: row.monthYoy}))} : null,
    financial: metric && selected ? {revenueYoy: selected.revenueYoy, profitYoy: selected.profitYoy} : null,
    baseNotes: matched?.baseNotes ?? [], limitations: matched?.limitations ?? [], discoveryErrors: matched?.discoveryErrors ?? [],
    timingNote: matched && report && matched.publishedAt > report.publishedAt ? "价格报告晚于财务报告发布，仅为现时补证，不是财务发布时已知信息。" : null};
}
export type PriceEvidence = ReturnType<typeof pricesFor>;
