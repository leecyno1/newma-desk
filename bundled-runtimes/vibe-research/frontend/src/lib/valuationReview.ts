import type { ValuationModel, ValuationScenario } from './valuationWorkbench';
import {normalizeCapitalLines, summarizeCapitalLines, type CapitalLineItem} from './valuationCapitalLines';

export const CAPITAL_FIELDS = ['dilutedSharesM', 'totalDebtM', 'cashM', 'excludedCashM', 'nonOperatingAssetsM', 'minorityInterestM', 'otherClaimsM'] as const;
export type CapitalField = typeof CAPITAL_FIELDS[number];
export const CAPITAL_LABELS: Record<CapitalField, string> = {
  dilutedSharesM: '稀释股数', totalDebtM: '有息债务', cashM: '现金及口径',
  excludedCashM: '需剔除现金', nonOperatingAssetsM: '非经营性资产', minorityInterestM: '少数股东权益调整', otherClaimsM: '其他优先权益',
};
export function activeCapitalFields(model: ValuationModel) {
  return CAPITAL_FIELDS.filter(field => field !== 'excludedCashM' || model.capitalInputs.cashBasis === 'gross');
}
export function eligibleCash(model: ValuationModel): number | null {
  const { cashM, cashBasis, excludedCashM } = model.capitalInputs;
  if (cashM === null || !Number.isFinite(cashM) || cashM < 0) return null;
  if (cashBasis !== 'gross') return cashM;
  if (typeof excludedCashM !== 'number' || !Number.isFinite(excludedCashM) || excludedCashM < 0 || excludedCashM > cashM) return null;
  return cashM - excludedCashM;
}
export interface ReviewStamp { confirmedAt: string; inputSnapshot: string }
export interface CapitalEvidence extends ReviewStamp {
  sourceId: string; locator: string; excerpt: string; method: string;
  lineItems?: CapitalLineItem[];
}
export interface CapitalEvidenceInput {
  title: string; url: string; locator: string; excerpt: string; method: string;
  lineItems?: CapitalLineItem[];
}
export interface CapitalEvidenceDraft {
  input: CapitalEvidenceInput;
  savedAt: string;
  inputSnapshot: string;
}

export function stageCapitalEvidence(model: ValuationModel, field: CapitalField, input: CapitalEvidenceInput): ValuationModel {
  return {...model,capitalEvidenceDrafts:{...model.capitalEvidenceDrafts,[field]:{
    input:{...input,...(input.lineItems!==undefined?{lineItems:input.lineItems.map(row=>({...row}))}:{})},
    savedAt:new Date().toISOString(),inputSnapshot:capitalSnapshot(model,field),
  }}};
}

export function capitalDraftIssue(model: ValuationModel, field: CapitalField): string|null {
  const draft=model.capitalEvidenceDrafts?.[field];
  return draft && draft.inputSnapshot!==capitalSnapshot(model,field)
    ? '暂存后数值、证券、币种、基期或现金口径已变化，请逐项重新核对；未自动换算或采用。' : null;
}

// Store the actual reviewed inputs, not an opaque hash. Calculation checks the
// snapshot as well as UI invalidation so stale saved reviews cannot pass.
function identity(model: ValuationModel) {
  return { market: model.security.market, symbol: model.security.symbol, currency: model.security.currency, asOf: model.asOf, unitScale: model.unitScale };
}
function capitalSnapshot(model: ValuationModel, field: CapitalField, lineItems?: CapitalLineItem[]) {
  return JSON.stringify({ ...identity(model), field, value: model.capitalInputs[field],
    ...(lineItems !== undefined ? {lineItems} : {}),
    ...(['cashM','excludedCashM'].includes(field) ? {cashBasis:model.capitalInputs.cashBasis || 'adjusted'} : {}) });
}
function scenarioSnapshot(model: ValuationModel, scenario: ValuationScenario) {
  return JSON.stringify({ ...identity(model), historicals: model.historicals,
    id: scenario.id, rationale: scenario.rationale, waccPct: scenario.waccPct, terminalGrowthPct: scenario.terminalGrowthPct, drivers: scenario.drivers });
}
function historicalDate(period: string) {
  const date = /^\d{4}A?$/.test(period) ? `${period.slice(0, 4)}-12-31` : period;
  return /^\d{4}-\d{2}-\d{2}$/.test(date) && Number.isFinite(Date.parse(date)) && new Date(date).toISOString().slice(0, 10) === date ? date : null;
}
export function latestValuationHistorical(model: ValuationModel) {
  const rows = model.historicals.filter(row => row.revenue !== null && row.revenue > 0);
  if (rows.some(row => !historicalDate(row.period))) return undefined;
  rows.sort((a,b) => historicalDate(b.period)!.localeCompare(historicalDate(a.period)!));
  // Two forms of the same date must not silently select different revenues.
  if (rows[0] && rows.some(row => historicalDate(row.period) === historicalDate(rows[0]!.period) && row.revenue !== rows[0]!.revenue)) return undefined;
  return rows[0];
}
export function valuationBasePeriod(model: ValuationModel) {
  return historicalDate(latestValuationHistorical(model)?.period ?? '');
}
export function priceComparisonIssue(model: ValuationModel): string | null {
  if (!model.capitalInputs.currentPrice || model.capitalInputs.currentPrice <= 0) return '缺少有效股价，不比较模型差异';
  const date = model.capitalInputs.currentPriceAsOf;
  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date) || historicalDate(date) !== date) return '股价日期未核验，不比较模型差异';
  if (date !== model.asOf) return `股价日期 ${date} 与估值基期末 ${model.asOf} 不同；本模型未滚动至行情日，不显示上涨空间`;
  return null;
}
export function alignValuationYears(model: ValuationModel): ValuationModel {
  const period = valuationBasePeriod(model);
  if (!period) throw new Error('历史期间请使用 YYYY-MM-DD 或 YYYYA，并录入正数收入');
  return { ...model, asOf: period, scenarios: model.scenarios.map(scenario => ({ ...scenario, review: undefined,
    drivers: scenario.drivers.map((driver, index) => ({ ...driver, year: Number(period.slice(0, 4)) + 1 + index })),
  })) };
}
export function scenarioReviewIssue(model: ValuationModel, scenario: ValuationScenario): string | null {
  if (!model.security.symbol.trim() || !model.security.market.trim() || !model.security.currency.trim()) return '请先补齐证券、市场和币种';
  if (model.unitScale !== '百万元' || !/^\d{4}-\d{2}-\d{2}$/.test(model.asOf) || !Number.isFinite(Date.parse(model.asOf))) return '请核对金额单位与估值基期末日期';
  if (!model.historicals.some(row => row.revenue !== null && row.revenue > 0)) return '请先录入正数年度收入基期';
  const period = valuationBasePeriod(model);
  if (!period || model.asOf !== period || scenario.drivers[0]?.year !== Number(period.slice(0, 4)) + 1) return '请按历史基期对齐估值时点和预测年度；本版尚不支持滚动至今日的估值';
  if (!scenario.rationale.trim() || scenario.rationale.includes('模板假设') || scenario.rationale === DEFAULT_RATIONALES[scenario.id]) return '请将模板情景依据改为自己的研究依据，再确认';
  if (!Number.isFinite(scenario.waccPct) || !Number.isFinite(scenario.terminalGrowthPct) || scenario.waccPct <= Math.max(0, scenario.terminalGrowthPct)) return 'WACC 必须为正且大于终值增长';
  if (scenario.drivers.length < 3 || scenario.drivers.some((driver, index) =>
    Object.values(driver).some(value => !Number.isFinite(value)) || driver.revenueGrowthPct <= -100
    || driver.taxRatePct < 0 || driver.taxRatePct > 100 || driver.daPctRevenue < 0 || driver.capexPctRevenue < 0
    || !Number.isInteger(driver.year) || (index > 0 && driver.year !== scenario.drivers[index - 1]!.year + 1))) return '请核对连续预测年度、增速、税率和资本开支等输入';
  return null;
}
const DEFAULT_RATIONALES = {
  bear: '增长与利润率低于基准，风险溢价上升',
  base: '收入增速逐步回归稳态，利润率温和改善',
  bull: '需求和经营杠杆优于基准，风险溢价下降',
};
export function isScenarioReviewed(model: ValuationModel, scenario: ValuationScenario) {
  return !scenarioReviewIssue(model, scenario) && Boolean(scenario.review?.confirmedAt)
    && scenario.review?.inputSnapshot === scenarioSnapshot(model, scenario);
}
export function confirmScenario(model: ValuationModel, scenarioId = model.selectedScenario): ValuationModel {
  const scenario = model.scenarios.find(row => row.id === scenarioId)!;
  const issue = scenarioReviewIssue(model, scenario);
  if (issue) throw new Error(issue);
  return { ...model, scenarios: model.scenarios.map(row => row.id !== scenarioId ? row : {
    ...row, review: { confirmedAt: new Date().toISOString(), inputSnapshot: scenarioSnapshot(model, row) },
  }) };
}

function capitalInputIssue(model: ValuationModel, field: CapitalField): string | null {
  const value = model.capitalInputs[field];
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || (field === 'dilutedSharesM' && value === 0)) return '先填写有效数值；缺失不等于零';
  if (field === 'excludedCashM' && (model.capitalInputs.cashBasis !== 'gross' || eligibleCash(model) === null)) return '剔除额仅用于原始余额口径，且不得超过现金余额';
  return null;
}
export function capitalEvidenceIssue(model: ValuationModel, field: CapitalField): string | null {
  const issue = capitalInputIssue(model,field);
  if (issue) return issue;
  const evidence = model.capitalEvidence[field];
  if (!evidence) return '未关联原文依据';
  if (evidence.lineItems !== undefined) {
    const summary = summarizeCapitalLines(evidence.lineItems,field,model.capitalInputs.cashBasis);
    if (summary.issues.length) return summary.issues[0]!;
    if (Math.abs(summary.total!-Number(model.capitalInputs[field])) > 1e-8) return '明细合计与当前数值不一致，需重新核对';
  }
  if (evidence.inputSnapshot !== capitalSnapshot(model, field,evidence.lineItems)) return '数值、证券或基期已变化，需重新确认';
  const source = model.sourceMaterials.find(row => row.id === evidence.sourceId);
  if (!source || !['available', 'verified'].includes(source.status) || source.asOf !== model.asOf) return '来源缺失、失效或基期不一致';
  if (!evidence.confirmedAt || !evidence.locator.trim() || !evidence.excerpt.trim() || !evidence.method.trim()) return '原文定位或口径说明不完整';
  return null;
}
export function attachCapitalEvidence(model: ValuationModel, field: CapitalField, input: CapitalEvidenceInput): ValuationModel {
  if (input.lineItems !== undefined) {
    const summary = summarizeCapitalLines(input.lineItems,field,model.capitalInputs.cashBasis);
    if (summary.issues.length) throw new Error(summary.issues.join('；'));
    model = {...model,capitalInputs:{...model.capitalInputs,[field]:summary.total}};
  }
  const issue = capitalInputIssue(model,field);
  if (issue) throw new Error(`请先录入有效资本数值：${issue}`);
  if (!model.security.symbol.trim() || !model.security.market.trim() || !model.security.currency.trim() || model.unitScale !== '百万元'
    || !/^\d{4}-\d{2}-\d{2}$/.test(model.asOf) || !Number.isFinite(Date.parse(model.asOf))) throw new Error('请先核对证券、币种、基期末和金额单位');
  if (![input.title, input.locator, input.excerpt, input.method].every(value => value.trim())) throw new Error('请填写来源标题、页码或附注、原文摘录及口径说明');
  if (input.url && !/^https?:\/\//i.test(input.url)) throw new Error('来源链接仅支持 HTTP 或 HTTPS；纸质资料可不填链接');
  const sourceId = `capital:${field}`;
  const capitalEvidenceDrafts={...model.capitalEvidenceDrafts};
  delete capitalEvidenceDrafts[field];
  return { ...model,
    capitalEvidenceDrafts,
    capitalEvidence: { ...model.capitalEvidence, [field]: {
      sourceId, locator: input.locator.trim(), excerpt: input.excerpt.trim(), method: input.method.trim(),
      ...(input.lineItems !== undefined ? {lineItems:input.lineItems.map(row=>({...row}))} : {}),
      confirmedAt: new Date().toISOString(), inputSnapshot: capitalSnapshot(model, field,input.lineItems),
    } },
    sourceMaterials: [...model.sourceMaterials.filter(row => row.id !== sourceId), {
      id: sourceId, label: input.title.trim(), asOf: model.asOf, source: '用户关联原文（未自动审计）', status: 'available',
      ...(input.url.trim() ? { url: input.url.trim() } : {}),
    }],
  };
}
export function valuationReadiness(model: ValuationModel) {
  const scenario = model.scenarios.find(row => row.id === model.selectedScenario)!;
  const capital = activeCapitalFields(model).map(field => ({ field, label: CAPITAL_LABELS[field], issue: capitalEvidenceIssue(model, field) }));
  const assumptionsConfirmed = isScenarioReviewed(model, scenario);
  return { assumptionsConfirmed, capital, ready: assumptionsConfirmed && capital.every(row => !row.issue) };
}

export function normalizeReviewStamp(value: unknown): ReviewStamp | undefined {
  if (!value || typeof value !== 'object') return;
  const row = value as Record<string, unknown>;
  if (typeof row.confirmedAt !== 'string' || !Number.isFinite(Date.parse(row.confirmedAt)) || typeof row.inputSnapshot !== 'string' || row.inputSnapshot.length > 16000) return;
  return { confirmedAt: row.confirmedAt, inputSnapshot: row.inputSnapshot };
}
export function normalizeCapitalEvidence(value: unknown): Partial<Record<CapitalField, CapitalEvidence>> {
  if (!value || typeof value !== 'object') return {};
  return Object.fromEntries(CAPITAL_FIELDS.flatMap(field => {
    const raw = (value as Record<string, unknown>)[field];
    const stamp = normalizeReviewStamp(raw);
    if (!stamp || !raw || typeof raw !== 'object') return [];
    const row = raw as Record<string, unknown>;
    if (!['sourceId', 'locator', 'excerpt', 'method'].every(key => typeof row[key] === 'string')) return [];
    return [[field, { ...stamp, sourceId: String(row.sourceId).slice(0, 160), locator: String(row.locator).slice(0, 240), excerpt: String(row.excerpt).slice(0, 3000), method: String(row.method).slice(0, 2000),
      ...(row.lineItems !== undefined ? {lineItems:normalizeCapitalLines(row.lineItems)} : {}) }]];
  }));
}

export function normalizeCapitalDrafts(value: unknown): Partial<Record<CapitalField, CapitalEvidenceDraft>> {
  if (!value || typeof value!=='object') return {};
  return Object.fromEntries(CAPITAL_FIELDS.flatMap(field=>{
    const row=(value as Record<string,CapitalEvidenceDraft>)[field];
    if (!row || typeof row.savedAt!=='string' || !Number.isFinite(Date.parse(row.savedAt)) || typeof row.inputSnapshot!=='string'
      || !row.input || !['title','url','locator','excerpt','method'].every(key=>typeof (row.input as unknown as Record<string,unknown>)[key]==='string')) return [];
    return [[field,{savedAt:row.savedAt,inputSnapshot:row.inputSnapshot,input:{
      title:row.input.title.slice(0,240),url:row.input.url.slice(0,2000),locator:row.input.locator.slice(0,240),
      excerpt:row.input.excerpt.slice(0,3000),method:row.input.method.slice(0,2000),
      ...(row.input.lineItems!==undefined?{lineItems:normalizeCapitalLines(row.input.lineItems)}:{}),
    }}]];
  }));
}
