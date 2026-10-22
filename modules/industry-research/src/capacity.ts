import { fmt, type Industry, type Snapshot } from "./research";

export interface CapacityMetric {
  name: string; scope: "industry" | "group"; quarterRate: number | null; quarterYoyPp: number | null;
  yearToDateRate: number | null; yearToDateYoyPp: number | null; raw: Record<string, string>;
}
export interface Capacity {
  title: string; sourceUrl: string; publisher: string; publishedAt: string; periodEnd: string;
  quarterPeriod: string; yearToDatePeriod: string; metrics: CapacityMetric[]; coverage: number;
  limitations: string[]; fetchedAt: string; cached: boolean; discovery: string;
  discoveryErrors: {sourceUrl: string; reason: string}[];
}

// Financial snapshots are month-end observations: use the last completed quarter,
// never the quarter containing an as-yet unfinished month.
export function capacityPeriodEnd(periodEnd?: string): string | undefined {
  if (!periodEnd) return undefined;
  const [year, month] = periodEnd.split("-").map(Number);
  return new Date(Date.UTC(year!, Math.floor(month! / 3) * 3, 0)).toISOString().slice(0, 10);
}

export function capacityFor(report: Snapshot | null, selected: Industry | undefined, source: Capacity | null, status: string, error: string) {
  const expected = capacityPeriodEnd(report?.periodEnd);
  const matched = report && source && status === "ready" && source.periodEnd === expected ? source : null;
  const metric = selected && matched?.metrics.find(row => row.scope === "industry" && row.name === selected.name) || null;
  const observations: string[] = [];
  if (metric?.quarterYoyPp != null) {
    observations.push(metric.quarterYoyPp < 0
      ? `该季度利用率较上年同期下降 ${fmt(Math.abs(metric.quarterYoyPp))} 个百分点；应核验新增产能、检修与需求，不直接判定订单下滑。`
      : metric.quarterYoyPp > 0
        ? `该季度利用率较上年同期提高 ${fmt(metric.quarterYoyPp)} 个百分点；仍需订单、产销及现金流验证，不直接确认需求复苏。`
        : "该季度利用率与上年同期持平；不等于产能、订单或盈利没有变化。");
  }
  return {status: !report ? "idle" : source && status === "ready" && !matched ? "mismatch" : status, error,
    industry: selected?.name ?? null, financialPeriodEnd: report?.periodEnd ?? null, expectedPeriodEnd: expected ?? null,
    publication: matched ? {title: matched.title, sourceUrl: matched.sourceUrl, periodEnd: matched.periodEnd,
      quarterPeriod: matched.quarterPeriod, yearToDatePeriod: matched.yearToDatePeriod, publishedAt: matched.publishedAt,
      fetchedAt: matched.fetchedAt, cached: matched.cached, coverage: matched.coverage} : null,
    metric, observations, limitations: matched?.limitations ?? [], discoveryErrors: matched?.discoveryErrors ?? [],
    timingNote: report && expected ? `财务累计期截至 ${report.periodEnd}；产能参考季度截至 ${expected}。${expected === report.periodEnd ? "截至日期一致，但当季与年内累计仍须分开。" : "这是滞后季度参考，不代表财务截止月的产能或需求。"}` : null,
    publicationNote: matched && report && matched.publishedAt > report.publishedAt ? "产能报告发布晚于财务报告，仅作现时补证，不能当作财务发布时已知信息。" : null};
}
export type CapacityEvidence = ReturnType<typeof capacityFor>;
