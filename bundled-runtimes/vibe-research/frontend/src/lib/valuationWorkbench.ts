import { getVibeDeskConfig, isVibeDeskEmbedded, waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";
import { normalizeCapitalEvidence, normalizeCapitalDrafts, normalizeReviewStamp, valuationReadiness, eligibleCash, priceComparisonIssue, latestValuationHistorical, type CapitalEvidence, type CapitalEvidenceDraft, type CapitalField, type ReviewStamp } from './valuationReview';

export type ValuationScenarioId = "bear" | "base" | "bull";
export type ValuationCheckStatus = "pass" | "warning" | "fail";

export interface ValuationSecurity {
  market: string;
  symbol: string;
  name: string;
  currency: string;
}

export interface HistoricalDriver {
  period: string;
  revenue: number | null;
  ebitMarginPct: number | null;
  daPctRevenue: number | null;
  capexPctRevenue: number | null;
  nwcPctDeltaRevenue: number | null;
  sourceIds: string[];
}

export interface ForecastDriver {
  year: number;
  revenueGrowthPct: number;
  ebitMarginPct: number;
  taxRatePct: number;
  daPctRevenue: number;
  capexPctRevenue: number;
  nwcPctDeltaRevenue: number;
}

export interface ValuationScenario {
  id: ValuationScenarioId;
  label: string;
  waccPct: number;
  terminalGrowthPct: number;
  rationale: string;
  drivers: ForecastDriver[];
  review?: ReviewStamp;
}

export interface CapitalInputs {
  currentPrice: number | null;
  currentPriceAsOf?: string;
  dilutedSharesM: number | null;
  totalDebtM: number | null;
  cashM: number | null;
  cashBasis?: 'adjusted' | 'gross';
  excludedCashM?: number | null;
  nonOperatingAssetsM?: number | null;
  minorityInterestM?: number | null;
  otherClaimsM?: number | null;
  riskFreeRatePct: number | null;
  beta: number | null;
  equityRiskPremiumPct: number | null;
  preTaxCostDebtPct: number | null;
  taxRatePct: number | null;
}

export interface ProjectionRow extends ForecastDriver {
  revenue: number | null;
  ebit: number | null;
  nopat: number | null;
  depreciationAmortization: number | null;
  capex: number | null;
  changeNwc: number | null;
  unleveredFcf: number | null;
  discountPeriod: number;
  discountFactor: number | null;
  pvFcf: number | null;
}

export interface ValuationResult {
  scenarioId: ValuationScenarioId;
  pvExplicitFcfM: number | null;
  terminalValueM: number | null;
  pvTerminalValueM: number | null;
  enterpriseValueM: number | null;
  netDebtM: number | null;
  eligibleCashM?: number | null;
  equityAdjustmentsM?: number | null;
  equityValueM: number | null;
  impliedPrice: number | null;
  currentPrice: number | null;
  impliedReturnPct: number | null;
  terminalValueSharePct: number | null;
}

export interface SensitivityGrid {
  waccPct: number[];
  terminalGrowthPct: number[];
  impliedPrices: Array<Array<number | null>>;
  center: { row: 2; column: 2 };
}

export interface ValuationSource {
  id: string;
  label: string;
  asOf: string;
  source: string;
  url?: string;
  status: "verified" | "available" | "stale" | "unavailable";
}

export interface AuditCheck {
  id: string;
  label: string;
  status: ValuationCheckStatus;
  message: string;
}

export interface ValuationModel {
  id: string;
  name: string;
  modelScope: "driver-based-dcf";
  security: ValuationSecurity;
  asOf: string;
  unitScale: string;
  selectedScenario: ValuationScenarioId;
  historicals: HistoricalDriver[];
  capitalInputs: CapitalInputs;
  capitalEvidence: Partial<Record<CapitalField, CapitalEvidence>>;
  capitalEvidenceDrafts?: Partial<Record<CapitalField, CapitalEvidenceDraft>>;
  scenarios: ValuationScenario[];
  projections: ProjectionRow[];
  result: ValuationResult;
  sensitivity: SensitivityGrid;
  auditChecks: AuditCheck[];
  sourceMaterials: ValuationSource[];
  gaps: string[];
  createdAt: string;
  updatedAt: string;
}

export interface ValuationWorkspace {
  schemaVersion: "newma-desk.valuation-workbench.v1";
  updatedAt: string;
  models: ValuationModel[];
}

export interface ValuationSession {
  workspace: ValuationWorkspace;
  mode: "local" | "desk";
  scope: string;
  revision: number;
  localVersion?: string | null;
  writable: boolean;
}

export class ValuationStorageError extends Error {}

const LOCAL_KEY = "newma-desk.valuation-workbench.v1";
const NAMESPACE = "valuation-workbench";
const DOCUMENT_KEY = "models";

function now() {
  return new Date().toISOString();
}

function makeId(prefix: string) {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${suffix}`;
}

function round(value: number, digits = 4) {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

function finiteOrNull(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function scenarioDrivers(id: ValuationScenarioId, firstYear: number): ForecastDriver[] {
  const settings = {
    bear: { growth: [4, 3, 3, 2.5, 2.5], margin: [13, 13, 13.5, 14, 14] },
    base: { growth: [10, 9, 8, 7, 6], margin: [17, 17.5, 18, 18.5, 19] },
    bull: { growth: [15, 13, 11, 9, 8], margin: [20, 21, 22, 22.5, 23] },
  }[id];
  return settings.growth.map((growth, index) => ({
    year: firstYear + index,
    revenueGrowthPct: growth,
    ebitMarginPct: settings.margin[index] ?? settings.margin[settings.margin.length - 1] ?? 0,
    taxRatePct: 25,
    daPctRevenue: 3,
    capexPctRevenue: id === "bear" ? 5 : id === "base" ? 4 : 3.5,
    nwcPctDeltaRevenue: 5,
  }));
}

function blankResult(scenarioId: ValuationScenarioId): ValuationResult {
  return {
    scenarioId,
    pvExplicitFcfM: null,
    terminalValueM: null,
    pvTerminalValueM: null,
    enterpriseValueM: null,
    netDebtM: null,
    eligibleCashM: null,
    equityAdjustmentsM: null,
    equityValueM: null,
    impliedPrice: null,
    currentPrice: null,
    impliedReturnPct: null,
    terminalValueSharePct: null,
  };
}

function blankSensitivity(): SensitivityGrid {
  return {
    waccPct: [7, 7.5, 8, 8.5, 9],
    terminalGrowthPct: [1.5, 2, 2.5, 3, 3.5],
    impliedPrices: Array.from({ length: 5 }, () => Array<number | null>(5).fill(null)),
    center: { row: 2, column: 2 },
  };
}

export function blankValuationModel(): ValuationModel {
  const timestamp = now();
  const firstYear = new Date().getFullYear() + 1;
  return {
    id: makeId("valuation"),
    name: "",
    modelScope: "driver-based-dcf",
    security: { market: "CN", symbol: "", name: "", currency: "CNY" },
    asOf: timestamp.slice(0, 10),
    unitScale: "百万元",
    selectedScenario: "base",
    capitalEvidence: {},
    historicals: [{
      period: `${firstYear - 1}A`,
      revenue: null,
      ebitMarginPct: null,
      daPctRevenue: null,
      capexPctRevenue: null,
      nwcPctDeltaRevenue: null,
      sourceIds: [],
    }],
    capitalInputs: {
      currentPrice: null,
      dilutedSharesM: null,
      totalDebtM: null,
      cashM: null,
      cashBasis: 'adjusted',
      excludedCashM: null,
      nonOperatingAssetsM: null,
      minorityInterestM: null,
      otherClaimsM: null,
      riskFreeRatePct: 2,
      beta: 1,
      equityRiskPremiumPct: 6,
      preTaxCostDebtPct: 4,
      taxRatePct: 25,
    },
    scenarios: [
      { id: "bear", label: "悲观", waccPct: 11, terminalGrowthPct: 2, rationale: "增长与利润率低于基准，风险溢价上升", drivers: scenarioDrivers("bear", firstYear) },
      { id: "base", label: "基准", waccPct: 9, terminalGrowthPct: 2.5, rationale: "收入增速逐步回归稳态，利润率温和改善", drivers: scenarioDrivers("base", firstYear) },
      { id: "bull", label: "乐观", waccPct: 8, terminalGrowthPct: 3, rationale: "需求和经营杠杆优于基准，风险溢价下降", drivers: scenarioDrivers("bull", firstYear) },
    ],
    projections: [],
    result: blankResult("base"),
    sensitivity: blankSensitivity(),
    auditChecks: [],
    sourceMaterials: [],
    gaps: ["历史 EBIT、折旧摊销、资本开支与营运资本口径需要核验"],
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}

export function emptyValuationWorkspace(): ValuationWorkspace {
  return { schemaVersion: "newma-desk.valuation-workbench.v1", updatedAt: now(), models: [] };
}

export function calculateWacc(inputs: CapitalInputs) {
  const { riskFreeRatePct, beta, equityRiskPremiumPct, preTaxCostDebtPct, taxRatePct, currentPrice, dilutedSharesM, totalDebtM } = inputs;
  if ([riskFreeRatePct, beta, equityRiskPremiumPct, currentPrice, dilutedSharesM, totalDebtM].some((value) => value === null || !Number.isFinite(value))) return null;
  if (currentPrice! <= 0 || dilutedSharesM! <= 0 || totalDebtM! < 0) return null;
  if (totalDebtM! > 0 && (preTaxCostDebtPct === null || taxRatePct === null || !Number.isFinite(preTaxCostDebtPct) || !Number.isFinite(taxRatePct) || preTaxCostDebtPct < 0 || taxRatePct < 0 || taxRatePct > 100)) return null;
  const marketCap = (currentPrice ?? 0) * (dilutedSharesM ?? 0);
  const debt = totalDebtM!;
  const capital = marketCap + debt;
  if (marketCap <= 0 || capital <= 0) return null;
  const costEquity = (riskFreeRatePct ?? 0) + (beta ?? 0) * (equityRiskPremiumPct ?? 0);
  const afterTaxDebt = (preTaxCostDebtPct ?? 0) * (1 - (taxRatePct ?? 0) / 100);
  return round(costEquity * marketCap / capital + afterTaxDebt * debt / capital, 4);
}

interface ScenarioRun {
  projections: ProjectionRow[];
  result: ValuationResult;
}

function runScenario(model: ValuationModel, scenario: ValuationScenario, waccOverride?: number, terminalGrowthOverride?: number): ScenarioRun {
  const baseRevenue = latestValuationHistorical(model)?.revenue ?? null;
  const waccPct = waccOverride ?? scenario.waccPct;
  const terminalGrowthPct = terminalGrowthOverride ?? scenario.terminalGrowthPct;
  if (model.unitScale !== "百万元" || baseRevenue === null || waccPct <= terminalGrowthPct || waccPct <= 0) {
    return { projections: [], result: { ...blankResult(scenario.id), currentPrice: model.capitalInputs.currentPrice } };
  }
  let previousRevenue = baseRevenue;
  const projections = scenario.drivers.map((driver, index) => {
    const revenue = previousRevenue * (1 + driver.revenueGrowthPct / 100);
    const ebit = revenue * driver.ebitMarginPct / 100;
    const taxes = Math.max(0, ebit * driver.taxRatePct / 100);
    const nopat = ebit - taxes;
    const depreciationAmortization = revenue * driver.daPctRevenue / 100;
    const capex = revenue * driver.capexPctRevenue / 100;
    const changeNwc = (revenue - previousRevenue) * driver.nwcPctDeltaRevenue / 100;
    const unleveredFcf = nopat + depreciationAmortization - capex - changeNwc;
    const discountPeriod = index + 0.5;
    const discountFactor = 1 / (1 + waccPct / 100) ** discountPeriod;
    const row: ProjectionRow = {
      ...driver,
      revenue: round(revenue),
      ebit: round(ebit),
      nopat: round(nopat),
      depreciationAmortization: round(depreciationAmortization),
      capex: round(capex),
      changeNwc: round(changeNwc),
      unleveredFcf: round(unleveredFcf),
      discountPeriod,
      discountFactor: round(discountFactor, 6),
      pvFcf: round(unleveredFcf * discountFactor),
    };
    previousRevenue = revenue;
    return row;
  });
  const finalFcf = projections[projections.length - 1]?.unleveredFcf ?? null;
  const pvExplicit = projections.reduce((total, row) => total + (row.pvFcf ?? 0), 0);
  const terminalValue = finalFcf === null ? null : finalFcf * (1 + terminalGrowthPct / 100) / ((waccPct - terminalGrowthPct) / 100);
  const terminalDiscountPeriod = Math.max(0.5, projections.length - 0.5);
  const pvTerminal = terminalValue === null ? null : terminalValue / (1 + waccPct / 100) ** terminalDiscountPeriod;
  const enterpriseValue = pvTerminal === null ? null : pvExplicit + pvTerminal;
  const cash = eligibleCash(model);
  const netDebt = model.capitalInputs.totalDebtM !== null && Number.isFinite(model.capitalInputs.totalDebtM) && model.capitalInputs.totalDebtM >= 0 && cash !== null
    ? model.capitalInputs.totalDebtM - cash
    : null;
  const {nonOperatingAssetsM, minorityInterestM, otherClaimsM} = model.capitalInputs;
  const equityAdjustments = [nonOperatingAssetsM,minorityInterestM,otherClaimsM].every(value => typeof value === 'number' && Number.isFinite(value) && value >= 0)
    ? nonOperatingAssetsM! - minorityInterestM! - otherClaimsM! : null;
  const equityValue = enterpriseValue !== null && netDebt !== null && equityAdjustments !== null ? enterpriseValue - netDebt + equityAdjustments : null;
  const shares = model.capitalInputs.dilutedSharesM;
  const impliedPrice = equityValue !== null && shares !== null && shares > 0 ? equityValue / shares : null;
  const currentPrice = model.capitalInputs.currentPrice;
  return {
    projections,
    result: {
      scenarioId: scenario.id,
      pvExplicitFcfM: round(pvExplicit),
      terminalValueM: terminalValue === null ? null : round(terminalValue),
      pvTerminalValueM: pvTerminal === null ? null : round(pvTerminal),
      enterpriseValueM: enterpriseValue === null ? null : round(enterpriseValue),
      netDebtM: netDebt === null ? null : round(netDebt),
      eligibleCashM: cash === null ? null : round(cash),
      equityAdjustmentsM: equityAdjustments === null ? null : round(equityAdjustments),
      equityValueM: equityValue === null ? null : round(equityValue),
      impliedPrice: impliedPrice === null ? null : round(impliedPrice, 4),
      currentPrice,
      impliedReturnPct: impliedPrice !== null && !priceComparisonIssue(model) && currentPrice !== null && currentPrice > 0 ? round((impliedPrice / currentPrice - 1) * 100, 4) : null,
      terminalValueSharePct: enterpriseValue !== null && enterpriseValue > 0 && pvTerminal !== null ? round(pvTerminal / enterpriseValue * 100, 4) : null,
    },
  };
}

function centeredAxis(base: number, step: number) {
  return [-2, -1, 0, 1, 2].map((offset) => round(base + offset * step, 4));
}

function buildAuditChecks(model: ValuationModel, scenarioRuns: Record<ValuationScenarioId, ScenarioRun>): AuditCheck[] {
  const readiness = valuationReadiness(model);
  const selected = model.scenarios.find((item) => item.id === model.selectedScenario)!;
  const result = scenarioRuns[model.selectedScenario].result;
  const hasActual = model.historicals.some((row) => row.revenue !== null && row.revenue > 0);
  const actualRows = model.historicals.filter(row => row.revenue !== null);
  const hasSources = actualRows.length > 0 && actualRows.every(row => row.sourceIds.length > 0
    && row.sourceIds.every(id => model.sourceMaterials.some(source => source.id === id && ["available", "verified"].includes(source.status))));
  const hierarchy = ["bear", "base", "bull"].map((id) => {
    const projections = scenarioRuns[id as ValuationScenarioId].projections;
    return projections[projections.length - 1]?.unleveredFcf ?? null;
  });
  const hierarchyReady = hierarchy.every((value) => value !== null);
  const hierarchyPass = hierarchyReady && (hierarchy[0] ?? 0) <= (hierarchy[1] ?? 0) && (hierarchy[1] ?? 0) <= (hierarchy[2] ?? 0);
  return [
    { id: 'price-date', label: '股价与估值时点', status: priceComparisonIssue(model) ? 'warning' : 'pass', message: priceComparisonIssue(model) || '股价日期与估值基期末一致；模型差异不是未来收益预测' },
    { id: 'scenario-review', label: '当前情景确认', status: readiness.assumptionsConfirmed ? 'pass' : 'warning', message: readiness.assumptionsConfirmed ? '用户已确认当前基期和情景假设；不代表独立审计' : '模板或已修改的假设待确认；每股价值暂不输出' },
    { id: 'capital-evidence', label: '资本来源与口径', status: readiness.capital.every(row => !row.issue) ? 'pass' : 'warning', message: readiness.capital.filter(row => row.issue).map(row => `${row.label}：${row.issue}`).join('；') || '适用资本输入及股权调整已人工关联原文；并非机器审计结论' },
    { id: "amount-unit", label: "金额单位", status: model.unitScale === "百万元" ? "pass" : "fail", message: model.unitScale === "百万元" ? "金额按百万元、股数按百万股；股价不缩放" : "旧模型金额单位不受支持，请核对并以百万元新建，已暂停计算" },
    { id: "historical-base", label: "历史基期", status: hasActual ? "pass" : "fail", message: hasActual ? "已提供收入基期" : "缺少可用于滚动预测的历史收入" },
    { id: "source-trace", label: "来源追溯", status: hasSources ? "pass" : "warning", message: hasSources ? "历史输入已关联来源" : "历史输入尚未完整关联 Evidence Ledger" },
    { id: "terminal-growth", label: "终值增长", status: selected.terminalGrowthPct < selected.waccPct ? "pass" : "fail", message: selected.terminalGrowthPct < selected.waccPct ? "终值增长低于 WACC" : "终值增长必须低于 WACC" },
    { id: "capital-bridge", label: "股权桥接", status: result.impliedPrice !== null ? "pass" : "fail", message: result.impliedPrice !== null ? "已按可用现金、非经营资产、少数股东及其他优先权益桥接；仍须核验估值与现金流范围" : "需要股数、债务、可用现金、三项股权调整及有效预测；缺失调整项不默认零" },
    { id: "terminal-share", label: "终值占比", status: result.terminalValueSharePct === null ? "warning" : result.terminalValueSharePct <= 75 ? "pass" : "warning", message: result.terminalValueSharePct === null ? "尚不能计算终值占比" : `终值占企业价值 ${result.terminalValueSharePct.toFixed(1)}%` },
    { id: "scenario-hierarchy", label: "情景层级", status: !hierarchyReady ? "warning" : hierarchyPass ? "pass" : "warning", message: !hierarchyReady ? "补齐基期后检查悲观/基准/乐观 FCF 层级" : hierarchyPass ? "乐观、基准、悲观的末期 FCF 层级一致" : "情景末期 FCF 层级异常，需要核验假设" },
  ];
}

export function calculateValuationModel(model: ValuationModel): ValuationModel {
  const ready = valuationReadiness(model).ready;
  const scenarios = Object.fromEntries(model.scenarios.map((scenario) => [scenario.id, runScenario(model, scenario)])) as Record<ValuationScenarioId, ScenarioRun>;
  const selectedScenario = model.scenarios.find((scenario) => scenario.id === model.selectedScenario) ?? model.scenarios[1]!;
  const selected = scenarios[selectedScenario.id];
  const waccPct = centeredAxis(selectedScenario.waccPct, 0.5);
  const terminalGrowthPct = centeredAxis(selectedScenario.terminalGrowthPct, 0.5);
  const sensitivity: SensitivityGrid = {
    waccPct,
    terminalGrowthPct,
    impliedPrices: waccPct.map((wacc) => terminalGrowthPct.map((growth) =>
      ready && wacc > growth ? runScenario(model, selectedScenario, wacc, growth).result.impliedPrice : null)),
    center: { row: 2, column: 2 },
  };
  const next = {
    ...model,
    projections: selected.projections,
    result: ready ? selected.result : { ...selected.result, impliedPrice: null, impliedReturnPct: null },
    sensitivity,
  };
  return { ...next, auditChecks: buildAuditChecks(next, scenarios) };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function textValue(value: unknown, fallback = "", limit = 8_000) {
  return typeof value === "string" ? value.slice(0, limit) : fallback;
}

function stringList(value: unknown, limit: number) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())).slice(0, limit) : [];
}

function normalizeDriver(value: unknown, fallback: ForecastDriver): ForecastDriver {
  const row = isRecord(value) ? value : {};
  return {
    year: typeof row.year === "number" ? Math.trunc(row.year) : fallback.year,
    revenueGrowthPct: finiteOrNull(row.revenueGrowthPct) ?? fallback.revenueGrowthPct,
    ebitMarginPct: finiteOrNull(row.ebitMarginPct) ?? fallback.ebitMarginPct,
    taxRatePct: finiteOrNull(row.taxRatePct) ?? fallback.taxRatePct,
    daPctRevenue: finiteOrNull(row.daPctRevenue) ?? fallback.daPctRevenue,
    capexPctRevenue: finiteOrNull(row.capexPctRevenue) ?? fallback.capexPctRevenue,
    nwcPctDeltaRevenue: finiteOrNull(row.nwcPctDeltaRevenue) ?? fallback.nwcPctDeltaRevenue,
  };
}

function normalizeModel(value: unknown): ValuationModel | null {
  if (!isRecord(value)) return null;
  const fallback = blankValuationModel();
  const security = isRecord(value.security) ? value.security : {};
  const symbol = textValue(security.symbol, "", 40);
  const name = textValue(security.name, "", 120);
  if (!symbol || !name) return null;
  const historicals = (Array.isArray(value.historicals) ? value.historicals : fallback.historicals).flatMap((item) => {
    if (!isRecord(item)) return [];
    return [{
      period: textValue(item.period, "待核验", 80),
      revenue: finiteOrNull(item.revenue),
      ebitMarginPct: finiteOrNull(item.ebitMarginPct),
      daPctRevenue: finiteOrNull(item.daPctRevenue),
      capexPctRevenue: finiteOrNull(item.capexPctRevenue),
      nwcPctDeltaRevenue: finiteOrNull(item.nwcPctDeltaRevenue),
      sourceIds: stringList(item.sourceIds, 20),
    }];
  }).slice(0, 5);
  const storedScenarios = new Map((Array.isArray(value.scenarios) ? value.scenarios : []).flatMap((item) => {
    if (!isRecord(item) || !["bear", "base", "bull"].includes(String(item.id))) return [];
    return [[item.id as ValuationScenarioId, item] as const];
  }));
  const scenarios = fallback.scenarios.map((base) => {
    const item = storedScenarios.get(base.id);
    if (!item) return base;
    const drivers = (Array.isArray(item.drivers) ? item.drivers : base.drivers).map((driver, index) => normalizeDriver(driver, base.drivers[index] ?? base.drivers[base.drivers.length - 1]!)).slice(0, 10);
    return {
      id: base.id,
      label: textValue(item.label, base.label, 40),
      waccPct: finiteOrNull(item.waccPct) ?? base.waccPct,
      terminalGrowthPct: finiteOrNull(item.terminalGrowthPct) ?? base.terminalGrowthPct,
      rationale: textValue(item.rationale, base.rationale, 2_000),
      drivers: drivers.length >= 3 ? drivers : base.drivers,
      ...(normalizeReviewStamp(item.review) ? { review: normalizeReviewStamp(item.review) } : {}),
    };
  });
  const capital = isRecord(value.capitalInputs) ? value.capitalInputs : {};
  const sources = (Array.isArray(value.sourceMaterials) ? value.sourceMaterials : []).flatMap((item) => {
    if (!isRecord(item)) return [];
    const id = textValue(item.id, "", 160);
    if (!id) return [];
    return [{
      id,
      label: textValue(item.label, id, 240),
      asOf: textValue(item.asOf, "待核验", 80),
      source: textValue(item.source, "用户输入", 240),
      ...(typeof item.url === "string" ? { url: item.url.slice(0, 2_000) } : {}),
      status: ["verified", "available", "stale", "unavailable"].includes(String(item.status)) ? item.status as ValuationSource["status"] : "available",
    }];
  }).slice(0, 100);
  const createdAt = textValue(value.createdAt, now(), 64);
  return calculateValuationModel({
    ...fallback,
    id: textValue(value.id, makeId("valuation"), 160),
    name: textValue(value.name, `${name} 预测与估值`, 240),
    security: {
      market: textValue(security.market, "CN", 20),
      symbol,
      name,
      currency: textValue(security.currency, "CNY", 20),
    },
    asOf: textValue(value.asOf, now().slice(0, 10), 64),
    unitScale: textValue(value.unitScale, "百万元", 40),
    selectedScenario: ["bear", "base", "bull"].includes(String(value.selectedScenario)) ? value.selectedScenario as ValuationScenarioId : "base",
    historicals: historicals.length ? historicals : fallback.historicals,
    capitalInputs: {
      currentPrice: finiteOrNull(capital.currentPrice),
      currentPriceAsOf: typeof capital.currentPriceAsOf === 'string' ? capital.currentPriceAsOf.slice(0,10) : '',
      dilutedSharesM: finiteOrNull(capital.dilutedSharesM),
      totalDebtM: finiteOrNull(capital.totalDebtM),
      cashM: finiteOrNull(capital.cashM),
      cashBasis: capital.cashBasis === 'gross' ? 'gross' : 'adjusted',
      excludedCashM: finiteOrNull(capital.excludedCashM),
      nonOperatingAssetsM: finiteOrNull(capital.nonOperatingAssetsM),
      minorityInterestM: finiteOrNull(capital.minorityInterestM),
      otherClaimsM: finiteOrNull(capital.otherClaimsM),
      riskFreeRatePct: finiteOrNull(capital.riskFreeRatePct),
      beta: finiteOrNull(capital.beta),
      equityRiskPremiumPct: finiteOrNull(capital.equityRiskPremiumPct),
      preTaxCostDebtPct: finiteOrNull(capital.preTaxCostDebtPct),
      taxRatePct: finiteOrNull(capital.taxRatePct),
    },
    capitalEvidence: normalizeCapitalEvidence(value.capitalEvidence),
    capitalEvidenceDrafts: normalizeCapitalDrafts(value.capitalEvidenceDrafts),
    scenarios,
    sourceMaterials: sources,
    gaps: stringList(value.gaps, 30),
    createdAt,
    updatedAt: textValue(value.updatedAt, createdAt, 64),
  });
}

function normalizeWorkspace(value: unknown): ValuationWorkspace {
  if (!isRecord(value)) return emptyValuationWorkspace();
  return {
    schemaVersion: "newma-desk.valuation-workbench.v1",
    updatedAt: textValue(value.updatedAt, now(), 64),
    models: (Array.isArray(value.models) ? value.models : []).map(normalizeModel).filter((item): item is ValuationModel => item !== null).slice(0, 100),
  };
}

export function valuationScope(config = getVibeDeskConfig()) {
  return config ? JSON.stringify([config.apiOrigin, config.storageGateway, config.userId, config.workspaceId,
    config.moduleId, config.instanceId, Boolean(config.accessToken),
    Boolean(config.permissions?.includes("storage.read")), Boolean(config.permissions?.includes("storage.write"))])
    : isVibeDeskEmbedded ? "unconnected" : "local";
}

function assertScope(scope: string, signal?: AbortSignal) {
  signal?.throwIfAborted();
  if (scope !== valuationScope()) throw new ValuationStorageError("工作区或权限已变化，请重新读取；旧模型未转存到新工作区。");
}

function checkedWorkspace(value: unknown): ValuationWorkspace {
  if (!isRecord(value) || value.schemaVersion !== "newma-desk.valuation-workbench.v1" || !Array.isArray(value.models) || value.models.length > 100) {
    throw new ValuationStorageError("估值档案格式异常或超过 100 份，未按空库处理，也未覆盖原记录。");
  }
  const workspace = normalizeWorkspace(value);
  if (workspace.models.length !== value.models.length || new Set(workspace.models.map(model => model.id)).size !== workspace.models.length
    || value.models.some((model, index) => !isRecord(model) || !model.id || !isRecord(model.capitalInputs)
      || !Array.isArray(model.historicals) || model.historicals.length !== workspace.models[index]?.historicals.length
      || !Array.isArray(model.sourceMaterials) || model.sourceMaterials.length !== workspace.models[index]?.sourceMaterials.length
      || !Array.isArray(model.scenarios) || model.scenarios.length !== 3
      || new Set(model.scenarios.map(scenario => isRecord(scenario) ? scenario.id : null)).size !== 3
      || model.scenarios.some(scenario => !isRecord(scenario) || !["bear", "base", "bull"].includes(String(scenario.id))
        || !Array.isArray(scenario.drivers) || scenario.drivers.length < 3 || scenario.drivers.length > 10))) {
    throw new ValuationStorageError("估值模型、情景或来源不完整，未丢弃记录；请先核对原数据。");
  }
  return workspace;
}

function checkedDocument(value: unknown, minimumRevision = 1) {
  if (!isRecord(value) || !Number.isInteger(value.revision) || Number(value.revision) < minimumRevision) {
    throw new ValuationStorageError("存储回执或修订号异常，请保留草稿并重新读取核对。");
  }
  return { revision: value.revision as number, workspace: checkedWorkspace(value.value) };
}

function requestSignal(signal?: AbortSignal) {
  return signal ? AbortSignal.any([signal, AbortSignal.timeout(15_000)]) : AbortSignal.timeout(15_000);
}

function canRead(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
  return Boolean(config?.moduleId === "valuation-workbench" && config.userId && config.workspaceId
    && config.accessToken && config.instanceId && config.storageGateway && config.permissions?.includes("storage.read"));
}

function canWrite(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
  return canRead(config) && Boolean(config.permissions?.includes("storage.write"));
}

function endpoint(config: VibeDeskConfig) {
  return `${config.storageGateway}/${NAMESPACE}/${DOCUMENT_KEY}`;
}

function headers(config: VibeDeskConfig, json = false) {
  return {
    Authorization: `Bearer ${config.accessToken}`,
    "X-Newma-Desk-Instance-Id": config.instanceId || "",
    ...(json ? { "Content-Type": "application/json" } : {}),
  };
}

export async function hydrateValuationWorkspace(signal?: AbortSignal): Promise<ValuationSession> {
  const scope = valuationScope();
  const config = await waitForVibeDeskConfig();
  assertScope(scope, signal);
  if (!config && !isVibeDeskEmbedded) {
    try {
      const raw = localStorage.getItem(LOCAL_KEY);
      return { workspace: raw === null ? emptyValuationWorkspace() : checkedWorkspace(JSON.parse(raw)), mode: "local", scope, revision: 0, localVersion: raw, writable: true };
    } catch (error) {
      if (error instanceof ValuationStorageError) throw error;
      throw new ValuationStorageError("本机估值读取失败，原记录未改动；请检查浏览器存储后重试。");
    }
  }
  if (!canRead(config)) throw new ValuationStorageError("尚未连接已授权的 Desk 存储，不会使用本机或其他工作区的旧模型。");
  try {
    const response = await fetch(endpoint(config), { headers: headers(config), cache: "no-store", signal: requestSignal(signal) });
    assertScope(scope, signal);
    const document = response.status === 404 ? { revision: 0, workspace: emptyValuationWorkspace() }
      : response.ok ? checkedDocument(await response.json()) : null;
    if (!document) throw new ValuationStorageError(`Desk 读取失败（HTTP ${response.status}），未使用本机旧模型替代。`);
    assertScope(scope, signal);
    return { ...document, mode: "desk", scope, writable: canWrite(config) };
  } catch (error) {
    if (error instanceof ValuationStorageError) throw error;
    throw new ValuationStorageError("Desk 读取未确认，请检查连接后重试；原记录未改动。");
  }
}

export async function persistValuationWorkspace(workspace: ValuationWorkspace, session: ValuationSession, signal?: AbortSignal): Promise<ValuationSession> {
  assertScope(session.scope, signal);
  const normalized = checkedWorkspace(workspace);
  if (session.mode === "local") {
    try {
      if (localStorage.getItem(LOCAL_KEY) !== session.localVersion) throw new ValuationStorageError("保存冲突：其他窗口已更新本机估值。草稿保留，请先导出再重新读取核对。");
      const raw = JSON.stringify(normalized);
      localStorage.setItem(LOCAL_KEY, raw);
      if (localStorage.getItem(LOCAL_KEY) !== raw) throw new ValuationStorageError("本机保存未确认，请保留草稿并重新读取核对。");
      return { ...session, workspace: normalized, localVersion: raw };
    } catch (error) {
      if (error instanceof ValuationStorageError) throw error;
      throw new ValuationStorageError("本机保存失败，草稿仍在；刷新或关闭前请先导出草稿。");
    }
  }
  const config = getVibeDeskConfig();
  if (!canWrite(config) || !session.writable) throw new ValuationStorageError("当前工作区没有保存权限；请先导出草稿。");
  try {
    const response = await fetch(endpoint(config), {
      method: "PUT", headers: headers(config, true), signal: requestSignal(signal),
      body: JSON.stringify({ expectedRevision: session.revision, value: normalized }),
    });
    assertScope(session.scope, signal);
    if (response.status === 409) throw new ValuationStorageError("保存冲突：其他窗口已更新。草稿保留，请先导出再重新读取核对；未覆盖对方版本。");
    if (!response.ok) throw new ValuationStorageError(`Desk 保存未确认（HTTP ${response.status}），草稿仍在；请重新读取核对，勿重复提交。`);
    const result = checkedDocument(await response.json(), session.revision + 1);
    assertScope(session.scope, signal);
    return { ...session, ...result };
  } catch (error) {
    if (error instanceof ValuationStorageError) throw error;
    throw new ValuationStorageError("Desk 保存未确认，可能已写入；请保留草稿并重新读取核对，勿重复提交。");
  }
}
