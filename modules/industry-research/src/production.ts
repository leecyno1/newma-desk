import type { Industry, Snapshot } from "./research";

export interface ProductionMetric {
  name: string; kind: "valueAdded" | "product"; unit: string | null;
  monthValue: number | null; monthYoy: number | null; cumulativeValue: number | null; cumulativeYoy: number | null;
  raw: Record<string, string>;
}
export interface Production {
  title: string; sourceUrl: string; publisher: string; periodEnd: string; monthlyPeriod: string; cumulativePeriod: string;
  publishedAt: string; fetchedAt: string; cached: boolean; freshness: "unknown" | "stale";
  metrics: ProductionMetric[]; limitations: string[]; discovery: string; discoveryErrors: {sourceUrl: string; reason: string}[];
  nationalSales?: {scope: string; monthRate: number | null; monthYoyPp: number | null; cumulativeRate: number | null; cumulativeYoyPp: number | null; raw: Record<string, string>} | null;
}
const RELATED_PRODUCTS: Record<string, string[]> = {
  "煤炭开采和洗选业": ["原煤"],
  "计算机、通信和其他电子设备制造业": ["集成电路", "微型计算机设备", "移动通信手持机"],
};

export function productionFor(report: Snapshot | null, selected: Industry | undefined, source: Production | null, status: string, error: string) {
  const matched = report && selected && source?.periodEnd === report.periodEnd ? source : null;
  const products = RELATED_PRODUCTS[selected?.name ?? ""] ?? [];
  const metrics = matched?.metrics.filter(item => item.kind === "valueAdded" ? item.name === selected?.name : products.includes(item.name)) ?? [];
  const observations: string[] = [];
  if (matched && selected) {
    const valueAdded = metrics.find(item => item.kind === "valueAdded");
    if (valueAdded?.cumulativeYoy != null && selected.revenueYoy != null && valueAdded.cumulativeYoy * selected.revenueYoy < 0) {
      observations.push("行业累计营收与实际增加值同比方向不同：先核验价格、产品结构及样本差异，不将差值当作价格涨幅。");
    }
    const quantities = metrics.filter(item => item.kind === "product" && item.cumulativeYoy != null);
    if (selected.profitYoy != null && quantities.some(item => item.cumulativeYoy! * selected.profitYoy! < 0)) {
      observations.push("行业累计利润与部分相关产品产量方向分化：需核验价格、成本及基数；样本不同，不能直接归因于需求变化。");
    }
    if (quantities.some(item => item.cumulativeYoy! > 0) && quantities.some(item => item.cumulativeYoy! < 0)) {
      observations.push("主要产品产量走势分化，不宜把行业总量增长外推到所有细分业务。");
    }
    if (!observations.length && metrics.length) observations.push("已取得同统计期的生产证据；即使方向一致，也不代表终端需求或盈利持续性已验证。");
    if (products.includes("集成电路")) observations.push("集成电路为数量口径，不能代表产品价值、先进制程占比或整个半导体行业盈利。");
  }
  const missing = matched ? [
    ...(!metrics.some(item => item.kind === "valueAdded") ? ["原表未列出可直接匹配的行业增加值"] : []),
    ...products.filter(name => !metrics.some(item => item.kind === "product" && item.name === name)).map(name => `${name}产量未取得`),
    ...metrics.filter(item => item.monthYoy == null || item.cumulativeYoy == null).map(item => `${item.name}部分同比不可比或缺失`),
    ...(!products.length ? ["本轮尚未建立该行业的产品验证关系"] : []),
    "细分行业库存与订单仍待补证；产能请另查看季度核验，价格请另查看行业PPI，不能代替现货或长协价",
  ] : [];
  return {status: !report ? "idle" : source && !matched && selected ? "mismatch" : status, error,
    industry: selected?.name ?? null,
    publication: matched ? {title: matched.title, sourceUrl: matched.sourceUrl, periodEnd: matched.periodEnd,
      monthlyPeriod: matched.monthlyPeriod, cumulativePeriod: matched.cumulativePeriod, publishedAt: matched.publishedAt,
      fetchedAt: matched.fetchedAt, cached: matched.cached, freshness: matched.freshness} : null,
    financial: matched && selected ? {revenueYoy: selected.revenueYoy, profitYoy: selected.profitYoy} : null,
    metrics, observations, missing, nationalSales: matched?.nationalSales ?? null,
    limitations: matched?.limitations ?? [], discoveryErrors: matched?.discoveryErrors ?? [],
    timingNote: matched && report && matched.publishedAt > report.publishedAt ? "生产报告发布晚于财务报告；仅为现时补证，不能当作财务发布时已知信息。" : null};
}
export type ProductionEvidence = ReturnType<typeof productionFor>;
