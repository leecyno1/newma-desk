import type { Industry, Snapshot } from "./research";
import { businessRevenueSchema, summarizeBusinessRevenue, type BusinessRevenue } from '@newma-desk/contracts/business-revenue';

export interface CompanyMetric {
  id: string; label: string; unit: string; reported: number | null; periodEnd?: string;
  reportedBasis?: string; reportedCurrency?: string; sourceIds: string[];
}
export interface CompanySource {
  id: string; label: string; kind: string; url?: string; periodEnd?: string; basis?: string; status: string;
  excerpt?: {metricId: string; reportedValue: number | null; unit: string; contentOrigin: string; pdfPage?: number};
  importedReport?: {confirmedAt?: string; scope?: string}; correction?: {after: number};
  businessRevenue?: BusinessRevenue;
}
export interface CompanyWorkbook {
  id: string; updatedAt: string; security: {name: string; symbol: string; market: string; currency: string};
  fiscalPeriod: {label: string; periodEnd?: string; basis?: string}; mode: string;
  metrics: CompanyMetric[]; sourceMaterials: CompanySource[];
}
export interface CompanyInputs {revision: number; workbooks: CompanyWorkbook[]}
export const COMPANY_FIELDS = {revenue: "营业收入", "revenue-yoy": "营收同比", "net-profit": "净利润（沿用底稿口径）", "net-profit-yoy": "净利润同比", "operating-cash-flow": "经营现金流净额", "op-cf-ps": "每股经营现金流", "capital-inventory": "存货（期末账面价值）", "capital-accounts-receivable": "应收账款（期末账面价值）"};
export const BASES: Record<string, string> = {annual: "完整年度", ytd: "年初至今累计", quarter: "单季度", ttm: "滚动十二个月", instant: "期末余额"};
export function safeSourceUrl(url?: string) {
  try {const parsed = new URL(url ?? ""); return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null;} catch {return null;}
}

export function companyRevenueGroups(workbook: CompanyWorkbook) {
  const period = workbook.fiscalPeriod?.periodEnd;
  const basis = workbook.fiscalPeriod?.basis;
  return workbook.sourceMaterials.filter(source=>source.businessRevenue).map(source=>{
    const parsed=businessRevenueSchema.safeParse(source.businessRevenue);
    const valid=parsed.success && workbook.mode==='reported' && basis==='annual' && source.basis===basis && !!period
      && source.periodEnd===period && source.kind==='filing' && ['available','verified'].includes(source.status)
      && parsed.data.currency===workbook.security.currency;
    const group=valid&&parsed.success?parsed.data:null;
    return {sourceId:source.id, label:source.label, url:safeSourceUrl(source.url), periodEnd:source.periodEnd,
      group, summary:group?summarizeBusinessRevenue(group):null, issue:group?null:'收入结构的原文、期间、币种或已采用状态待核对'};
  });
}
export function companyFor(report: Snapshot | null, industry: Industry | undefined, workbook: CompanyWorkbook | undefined, reason: string, revision: number) {
  if (!report || !industry || !workbook || !reason.trim()) return null;
  const period = workbook.fiscalPeriod?.periodEnd;
  const basis = workbook.fiscalPeriod?.basis;
  const periodAligned = period === report.periodEnd && (basis === "ytd" || basis === "annual" && period?.endsWith("-12-31"));
  const revenueGroups = companyRevenueGroups(workbook);
  const rows = Object.entries(COMPANY_FIELDS).map(([id, label]) => {
    const balance = id === "capital-inventory" || id === "capital-accounts-receivable";
    const metricBasis = balance ? "instant" : basis;
    const matches = workbook.metrics.filter(item => item.id === id);
    const metric = matches.length === 1 ? matches[0] : undefined;
    const hasValue = typeof metric?.reported === "number" && Number.isFinite(metric.reported);
    const sources = workbook.sourceMaterials.filter(source => metric?.sourceIds?.includes(source.id));
    const issues = [
      ...(workbook.mode !== "reported" ? ["预期底稿，不能作为实际业绩"] : []),
      ...(!hasValue ? ["实际值缺失或重复"] : []),
      ...(hasValue ? [
      ...(!period || !basis || metric?.periodEnd !== period || metric?.reportedBasis !== metricBasis ? ["期间或口径不符"] : []),
      ...(!workbook.security?.currency || metric?.reportedCurrency !== workbook.security.currency ? ["币种未确认"] : []),
      ...(!(id.endsWith("-yoy") ? ["%"] : id === "op-cf-ps" ? ["元"] : ["元", "万元", "亿元", "百万元"]).includes(metric?.unit ?? "") ? ["单位未确认"] : []),
      ] : []),
    ];
    const linked = sources.filter(source => ["available", "verified"].includes(source.status) && source.periodEnd === period && source.basis === metricBasis);
    if (hasValue && !linked.length) issues.push("缺少同口径来源");
    const adopted = linked.find(source => source.kind === "filing" && source.excerpt?.contentOrigin === "pdf-text"
      && source.excerpt.metricId === id && source.excerpt.unit === metric?.unit && source.excerpt.reportedValue === metric?.reported
      && (source.importedReport?.confirmedAt || source.correction?.after === metric?.reported));
    if (balance && hasValue && adopted?.importedReport?.scope !== "consolidated") issues.push("缺少已确认合并报表原文");
    return {id, label, unit: metric?.unit ?? "", value: issues.length ? null : metric!.reported,
      basis: BASES[metricBasis ?? ""] ?? "口径未确认", periodEnd: period ?? null, currency: workbook.security?.currency ?? null,
      state: issues.length ? "待核验" : adopted ? "已采用PDF证据，非审计确认" : "底稿记录，待核对原文", issues,
      sources: linked.map(source => ({id: source.id, label: source.label, url: safeSourceUrl(source.url), pdfPage: source.excerpt?.pdfPage ?? null}))};
  });
  return {workbookId: workbook.id, security: workbook.security, savedAt: workbook.updatedAt, sourceRevision: revision,
    industry: industry.name, industryPeriodEnd: report.periodEnd, companyPeriodEnd: period ?? null,
    relation: {status: "user-confirmed-research-link", reason: reason.trim(), boundary: "人工关联，不是官方分类或收入占比"},
    periodAligned, timingNote: periodAligned ? "累计截止日一致，企业样本和利润定义仍不同。" : "公司与行业期间不同，仅供参考，不计算增速差或传导贡献。",
    rows, revenueGroups, gaps: [revenueGroups.some(item=>item.group)?"主营业务结构≠会计报告分部；组内占比不是公司总收入占比，跨维度不能相加。":"主营业务收入结构待补证；缺失不代表零。", "期末存货/应收是存量，不直接推算周转天数；应收账款不含票据、融资及其他应收。", "公司净利润≠行业利润总额；每股现金流≠总额。", "同向增长不证明传导，不作评级。", "保存日≠披露日，未确认最新财报。当前核验仅本次会话；关联依据须另行保存，重载后重新确认。"]};
}
export type CompanyEvidence = ReturnType<typeof companyFor>;
