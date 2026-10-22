import type { ModPageContext } from "@newma-desk/contracts";
import type { ProductionEvidence } from "./production";
import type { PriceEvidence } from "./prices";
import type { Diagnosis } from "./diagnosis";
import type { Operations } from "./OperationsPanel";
import type { CapacityEvidence } from "./capacity";
import type { CompanyEvidence } from "./company";

export const STATES = { expansion: "营收利润双增", pressure: "增收不增利", repair: "缩收增利", contraction: "营收利润双降", boundary: "零增长边界", unknown: "同比不可比 / 缺失" };
export type State = keyof typeof STATES;
export interface Industry {
  name: string; revenue: number | null; revenueYoy: number | null; cost: number | null; costYoy: number | null;
  profit: number | null; profitYoy: number | null; profitMargin: number | null; costRatio: number | null;
  quadrant: State; raw: Record<string, string>;
}
export interface Snapshot {
  schemaVersion: string; title: string; sourceUrl: string; publisher: string; publishedAt: string;
  period: string; periodEnd: string; fetchedAt: string; taxonomy: string; unit: string;
  rows: Industry[]; total: Industry; operations?: Operations; coverage: {industries: number; comparable: number; expectedIndustries: number};
  limitations: string[]; freshness: "unknown" | "stale"; cached: boolean; discovery: string;
}
export interface History {
  publications: Snapshot[]; errors: {sourceUrl: string; reason: string}[];
  status: "complete" | "partial"; fetchedAt: string; cached: boolean; scope: string; discoveryPages: string[];
}
export function publicationsFor(latest: Snapshot | null, history: History | null): Snapshot[] {
  const publications = new Map((history?.publications ?? []).map(item => [item.sourceUrl, item]));
  // Keep the most recently fetched copy when the same URL was read twice.
  if (latest && (!publications.has(latest.sourceUrl) || latest.fetchedAt >= publications.get(latest.sourceUrl)!.fetchedAt)) publications.set(latest.sourceUrl, latest);
  return [...publications.values()].sort((a, b) => b.periodEnd.localeCompare(a.periodEnd) || b.publishedAt.localeCompare(a.publishedAt));
}
export function changeFor(current: Snapshot, publications: Snapshot[], name: string) {
  const year = Number(current.periodEnd.slice(0, 4)), month = Number(current.periodEnd.slice(5, 7));
  const previousPeriod = `${year}-${String(month - 1).padStart(2, "0")}`;
  const previous = publications.filter(item => item.periodEnd.startsWith(previousPeriod));
  const base = previous[0];
  let reason = "";
  if (month === 1 || !base) reason = "缺少同年相邻累计期，不跨月或跨年比较";
  else if (previous.length !== 1 || publications.filter(item => item.periodEnd === current.periodEnd).length > 1) reason = "同一统计期有多份发布，需人工核验版本";
  else if (base.taxonomy !== current.taxonomy || base.unit !== current.unit) reason = "分类或单位不一致";
  else if (base.publishedAt > current.publishedAt) reason = "前期报告在本期之后发布，需核验修订";
  const row = current.rows.find(item => item.name === name);
  const prior = !reason ? base?.rows.find(item => item.name === name) : undefined;
  if (!reason && (!row || !prior)) reason = "行业未匹配，不补零";
  const delta = (metric: "revenueYoy" | "profitYoy") => row?.[metric] != null && prior?.[metric] != null
    ? Math.round((row[metric]! - prior[metric]!) * 10000) / 10000 : null;
  return {revenueYoyPp: delta("revenueYoy"), profitYoyPp: delta("profitYoy"),
    previousSourceUrl: !reason ? base?.sourceUrl ?? null : null,
    reason: reason || (row?.revenueYoy == null || row?.profitYoy == null || prior?.revenueYoy == null || prior?.profitYoy == null ? "部分同比缺失或不可比，对应变化不计算" : "仅累计同比变化，企业样本仍可能调整")};
}
export function historyFor(publications: Snapshot[], name: string) {
  return publications.map(item => {
    const row = item.rows.find(row => row.name === name);
    return {period: item.period, periodEnd: item.periodEnd, sourceUrl: item.sourceUrl, publishedAt: item.publishedAt, fetchedAt: item.fetchedAt,
      revenueYoy: row?.revenueYoy ?? null, profitYoy: row?.profitYoy ?? null, change: changeFor(item, publications, name)};
  });
}
export const METRICS = { revenueYoy: "营收同比", profitYoy: "利润同比", profitMargin: "利润率", costRatio: "成本率", revenue: "营业收入", profit: "利润总额" };
export type Metric = keyof typeof METRICS;
export function rowsFor(data: Snapshot | null, query: string, state: string, sort: Metric): Industry[] {
  return (data?.rows ?? []).filter(row => row.name.includes(query.trim()) && (state === "all" || row.quadrant === state))
    .sort((a, b) => a[sort] === null ? b[sort] === null ? a.name.localeCompare(b.name) : 1 : b[sort] === null ? -1 : b[sort]! - a[sort]!);
}
export function fmt(value: number | null | undefined, suffix = "", digits = 1) {
  return value == null ? "—" : value.toLocaleString("zh-CN", {minimumFractionDigits: digits, maximumFractionDigits: digits}) + suffix;
}
export function growthCounts(rows: Industry[]) {
  return Object.fromEntries(Object.keys(STATES).map(state => [state, rows.filter(row => row.quadrant === state).length]));
}
export const CHANGE_STATES = {improving: "营收利润同步改善", weakening: "营收利润同步回落", mixed: "分化或单项变化", flat: "两项持平", unknown: "无法完整比较"};
export function migrationFor(current: Snapshot, publications: Snapshot[], scopeRows: Industry[]) {
  const rows = scopeRows.map(row => {
    const change = changeFor(current, publications, row.name);
    const prior = publications.find(item => item.sourceUrl === change.previousSourceUrl)?.rows.find(item => item.name === row.name);
    const {revenueYoyPp: revenue, profitYoyPp: profit} = change;
    const comparable = revenue != null && profit != null;
    const direction: keyof typeof CHANGE_STATES = !comparable ? "unknown" : revenue > 0 && profit > 0 ? "improving"
      : revenue < 0 && profit < 0 ? "weakening" : revenue === 0 && profit === 0 ? "flat" : "mixed";
    const wasExpansion = prior?.revenueYoy != null && prior?.profitYoy != null && prior.revenueYoy > 0 && prior.profitYoy > 0;
    const isExpansion = row.revenueYoy != null && row.profitYoy != null && row.revenueYoy > 0 && row.profitYoy > 0;
    return {name: row.name, ...change, direction, previousState: prior?.quadrant ?? null, currentState: row.quadrant,
      transition: comparable ? !wasExpansion && isExpansion ? "进入双增" : wasExpansion && !isExpansion ? "退出双增" : "未跨越双增边界" : "无法完整比较"};
  }).sort((a, b) => (b.profitYoyPp ?? -Infinity) - (a.profitYoyPp ?? -Infinity) || a.name.localeCompare(b.name));
  const base = publications.find(item => item.sourceUrl === rows.find(row => row.previousSourceUrl)?.previousSourceUrl);
  return {current: {period: current.period, sourceUrl: current.sourceUrl, publishedAt: current.publishedAt},
    previous: base ? {period: base.period, sourceUrl: base.sourceUrl, publishedAt: base.publishedAt} : null,
    scopeCount: rows.length, comparableCount: rows.filter(row => row.direction !== "unknown").length,
    counts: Object.fromEntries(Object.keys(CHANGE_STATES).map(state => [state, rows.filter(row => row.direction === state).length])),
    entered: rows.filter(row => row.transition === "进入双增").length, exited: rows.filter(row => row.transition === "退出双增").length, rows,
    boundary: "当前报告及搜索范围内全体行业，不随增长象限筛选缩小；仅同年相邻累计期、同名行业比较。行业等权计数，不是金额占比；同比变化不是单月增速或拐点，样本与网页修订仍可能影响可比性。"};
}
export function contextFor(data: Snapshot | null, rows: Industry[], selected: Industry | undefined, comparison: Industry[], filters: Record<string, unknown>, status: string, error: string,
  history: History | null = null, historyStatus = "idle", historyError = "", publications: Snapshot[] = [], production?: ProductionEvidence, prices?: PriceEvidence, diagnosis: Diagnosis = null, capacity?: CapacityEvidence, company?: {status: string; error: string; evidence: CompanyEvidence}, tracking?: {status: string; revision: number; entries: import("./tracking").ResearchEntry[]; boundary: string}): ModPageContext {
  const scopeRows = rowsFor(data, typeof filters.query === "string" ? filters.query : "", "all", "profitYoy");
  return {view: {id: "industry-prosperity", title: "行业景气"},
    visibleBlocks: [...(data && history && historyStatus === "ready" ? [{id: "industry-migration", type: "table", title: "行业景气变化"}] : []),
      {id: "industry-diagnosis", type: "evidence", title: "行业诊断"}, {id: "industry-growth", type: "chart", title: "增长结构"}, {id: "industry-matrix", type: "table", title: "行业比较"}, {id: "industry-detail", type: "evidence", title: "行业证据"}, {id: "industry-history", type: "table", title: "历史发布对照"}, {id: "industry-production", type: "evidence", title: "生产与盈利验证"}, {id: "industry-prices", type: "evidence", title: "行业价格验证"}, {id: "industry-operations", type: "evidence", title: "库存与回款 · 经营质量背景"}, {id: "industry-capacity", type: "evidence", title: "产能与需求核验"}, {id: "industry-company", type: "evidence", title: "行业到公司 · 财报核验"}, {id: "industry-tracking", type: "evidence", title: "研究假设与失效条件"}, {id: "tracking-overview", type: "table", title: "跨行业复核总览"}],
    selection: selected ? {...selected} : {}, filters,
    data: {source: "国家统计局原始行业表", freshness: data?.freshness ?? "unknown", ...(data ? {asOf: data.periodEnd} : {}),
      summary: {status, error: error || null, publication: data ? {title: data.title, url: data.sourceUrl, period: data.period,
        publishedAt: data.publishedAt, fetchedAt: data.fetchedAt, taxonomy: data.taxonomy, coverage: data.coverage, cached: data.cached} : null,
        visibleRows: rows, comparison, limitations: data?.limitations ?? [],
        growthStructure: data ? {scopeCount: scopeRows.length, counts: growthCounts(scopeRows),
          plottedCount: rows.filter(row => row.revenueYoy != null && row.profitYoy != null).length,
          scopeNote: "图例计数包含当前报告和搜索范围内全部增长分类；切换分类不缩放坐标轴；同比缺失不绘制为零。"} : null,
        migration: data && history && historyStatus === "ready" ? migrationFor(data, publications, scopeRows) : null,
        production: data ? production ?? null : null,
        prices: data ? prices ?? null : null,
        operations: data?.operations ?? null,
        capacity: data ? capacity ?? null : null,
        company: data ? company ?? null : null,
        tracking: data ? tracking ?? null : null,
        operationsInstruction: "operations仅为全国及工业三大门类背景，不能赋值给selection行业，不能用来修改该行业诊断。同比天数变化仅使用官方明示值，不以历史公告差额冒充同比；空缺不表示正常。",
        diagnosis: data && selected ? diagnosis : null,
        history: {status: data ? historyStatus : "idle", error: historyError || null, scope: data && history ? history.scope : null,
          errors: data && history ? history.errors : [], points: data && history && selected ? historyFor(publications, selected.name) : [],
          currentChange: data && history && selected ? changeFor(data, publications, selected.name) : null},
        instruction: "仅依据当前选定报告；历史报告不是最新数据。累计同比变化单位为百分点，不是单月趋势；PPI年内平均同比不是累计涨幅或现货价格，不用PPI与产量重构营收或归因利润。历史网页为本次读取，不是原始时点快照，不可无前视回测。行业大类不是半导体子行业，缺失不是零，不生成买卖指令。"}},
    actions: [], tasks: [],
  };
}
export function researchQuestions(name: string): string[] {
  if (name === "煤炭开采和洗选业") return ["煤价与销量分别贡献多少？长协和现货口径是否一致？", "电厂库存、日耗、进口与国内供给能否验证持续性？", "煤企成本、资本开支和现金分红是否支持股东回报？"];
  if (name === "计算机、通信和其他电子设备制造业") return ["总量增长来自哪个细分环节？不能直接外推为半导体景气。", "出货、产品价格、库存与产能利用率是否共同验证？", "上市公司收入结构及订单是否与大类数据一致？"];
  return ["增长来自销量、价格还是统计基数变化？", "订单、库存、产能利用率是否验证持续性？", "行业利润如何传导至目标公司的盈利与现金流？"];
}
