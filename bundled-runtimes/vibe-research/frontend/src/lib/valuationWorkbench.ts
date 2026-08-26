import { waitForVibeDeskConfig, type VibeDeskConfig } from "@/lib/vibedesk";

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
}

export interface CapitalInputs {
  currentPrice: number | null;
  dilutedSharesM: number | null;
  totalDebtM: number | null;
  cashM: number | null;
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

interface StorageDocument {
  revision: number;
  value: unknown;
}

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
  if ([riskFreeRatePct, beta, equityRiskPremiumPct, preTaxCostDebtPct, taxRatePct, currentPrice, dilutedSharesM, totalDebtM].some((value) => value === null)) return null;
  const marketCap = (currentPrice ?? 0) * (dilutedSharesM ?? 0);
  const debt = Math.max(0, totalDebtM ?? 0);
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
  const baseRevenue = [...model.historicals].reverse().find((row) => typeof row.revenue === "number" && row.revenue > 0)?.revenue ?? null;
  const waccPct = waccOverride ?? scenario.waccPct;
  const terminalGrowthPct = terminalGrowthOverride ?? scenario.terminalGrowthPct;
  if (baseRevenue === null || waccPct <= terminalGrowthPct || waccPct <= 0) {
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
  const netDebt = model.capitalInputs.totalDebtM !== null && model.capitalInputs.cashM !== null
    ? model.capitalInputs.totalDebtM - model.capitalInputs.cashM
    : null;
  const equityValue = enterpriseValue !== null && netDebt !== null ? enterpriseValue - netDebt : null;
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
      equityValueM: equityValue === null ? null : round(equityValue),
      impliedPrice: impliedPrice === null ? null : round(impliedPrice, 4),
      currentPrice,
      impliedReturnPct: impliedPrice !== null && currentPrice !== null && currentPrice > 0 ? round((impliedPrice / currentPrice - 1) * 100, 4) : null,
      terminalValueSharePct: enterpriseValue !== null && enterpriseValue > 0 && pvTerminal !== null ? round(pvTerminal / enterpriseValue * 100, 4) : null,
    },
  };
}

function centeredAxis(base: number, step: number) {
  return [-2, -1, 0, 1, 2].map((offset) => round(base + offset * step, 4));
}

function buildAuditChecks(model: ValuationModel, scenarioRuns: Record<ValuationScenarioId, ScenarioRun>): AuditCheck[] {
  const selected = model.scenarios.find((item) => item.id === model.selectedScenario)!;
  const result = scenarioRuns[model.selectedScenario].result;
  const hasActual = model.historicals.some((row) => row.revenue !== null && row.revenue > 0);
  const hasSources = model.sourceMaterials.length > 0 && model.historicals.some((row) => row.sourceIds.length > 0);
  const hierarchy = ["bear", "base", "bull"].map((id) => {
    const projections = scenarioRuns[id as ValuationScenarioId].projections;
    return projections[projections.length - 1]?.unleveredFcf ?? null;
  });
  const hierarchyReady = hierarchy.every((value) => value !== null);
  const hierarchyPass = hierarchyReady && (hierarchy[0] ?? 0) <= (hierarchy[1] ?? 0) && (hierarchy[1] ?? 0) <= (hierarchy[2] ?? 0);
  return [
    { id: "historical-base", label: "历史基期", status: hasActual ? "pass" : "fail", message: hasActual ? "已提供收入基期" : "缺少可用于滚动预测的历史收入" },
    { id: "source-trace", label: "来源追溯", status: hasSources ? "pass" : "warning", message: hasSources ? "历史输入已关联来源" : "历史输入尚未完整关联 Evidence Ledger" },
    { id: "terminal-growth", label: "终值增长", status: selected.terminalGrowthPct < selected.waccPct ? "pass" : "fail", message: selected.terminalGrowthPct < selected.waccPct ? "终值增长低于 WACC" : "终值增长必须低于 WACC" },
    { id: "capital-bridge", label: "股权桥接", status: model.capitalInputs.dilutedSharesM && model.capitalInputs.totalDebtM !== null && model.capitalInputs.cashM !== null ? "pass" : "fail", message: result.impliedPrice !== null ? "EV、净债务与稀释股数已完成桥接" : "需要稀释股数、债务与现金才能得到每股价值" },
    { id: "terminal-share", label: "终值占比", status: result.terminalValueSharePct === null ? "warning" : result.terminalValueSharePct <= 75 ? "pass" : "warning", message: result.terminalValueSharePct === null ? "尚不能计算终值占比" : `终值占企业价值 ${result.terminalValueSharePct.toFixed(1)}%` },
    { id: "scenario-hierarchy", label: "情景层级", status: !hierarchyReady ? "warning" : hierarchyPass ? "pass" : "warning", message: !hierarchyReady ? "补齐基期后检查悲观/基准/乐观 FCF 层级" : hierarchyPass ? "乐观、基准、悲观的末期 FCF 层级一致" : "情景末期 FCF 层级异常，需要核验假设" },
  ];
}

export function calculateValuationModel(model: ValuationModel): ValuationModel {
  const scenarios = Object.fromEntries(model.scenarios.map((scenario) => [scenario.id, runScenario(model, scenario)])) as Record<ValuationScenarioId, ScenarioRun>;
  const selectedScenario = model.scenarios.find((scenario) => scenario.id === model.selectedScenario) ?? model.scenarios[1]!;
  const selected = scenarios[selectedScenario.id];
  const waccPct = centeredAxis(selectedScenario.waccPct, 0.5);
  const terminalGrowthPct = centeredAxis(selectedScenario.terminalGrowthPct, 0.5);
  const sensitivity: SensitivityGrid = {
    waccPct,
    terminalGrowthPct,
    impliedPrices: waccPct.map((wacc) => terminalGrowthPct.map((growth) =>
      wacc > growth ? runScenario(model, selectedScenario, wacc, growth).result.impliedPrice : null)),
    center: { row: 2, column: 2 },
  };
  const next = {
    ...model,
    projections: selected.projections,
    result: selected.result,
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
      dilutedSharesM: finiteOrNull(capital.dilutedSharesM),
      totalDebtM: finiteOrNull(capital.totalDebtM),
      cashM: finiteOrNull(capital.cashM),
      riskFreeRatePct: finiteOrNull(capital.riskFreeRatePct),
      beta: finiteOrNull(capital.beta),
      equityRiskPremiumPct: finiteOrNull(capital.equityRiskPremiumPct),
      preTaxCostDebtPct: finiteOrNull(capital.preTaxCostDebtPct),
      taxRatePct: finiteOrNull(capital.taxRatePct),
    },
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

export function loadLocalValuationWorkspace() {
  try {
    return normalizeWorkspace(JSON.parse(localStorage.getItem(LOCAL_KEY) || "null"));
  } catch {
    return emptyValuationWorkspace();
  }
}

function canRead(config: VibeDeskConfig | null): config is VibeDeskConfig & { accessToken: string; instanceId: string; storageGateway: string } {
  return Boolean(config?.accessToken && config.instanceId && config.storageGateway && config.permissions?.includes("storage.read"));
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

async function readRemote(config: VibeDeskConfig) {
  const response = await fetch(endpoint(config), { headers: headers(config) });
  if (response.status === 404) return { found: false, revision: 0, state: emptyValuationWorkspace() };
  if (!response.ok) throw new Error(`valuation workspace read failed: ${response.status}`);
  const document = await response.json() as StorageDocument;
  return { found: true, revision: Number(document.revision) || 0, state: normalizeWorkspace(document.value) };
}

export async function hydrateValuationWorkspace() {
  const local = loadLocalValuationWorkspace();
  const config = await waitForVibeDeskConfig();
  if (!canRead(config)) return local;
  try {
    const remote = await readRemote(config);
    return remote.found ? remote.state : local;
  } catch {
    return local;
  }
}

export async function persistValuationWorkspace(workspace: ValuationWorkspace) {
  const normalized = normalizeWorkspace(workspace);
  try {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(normalized));
  } catch {
    // Keep the current model usable when browser persistence is disabled.
  }
  const config = await waitForVibeDeskConfig();
  if (!canWrite(config)) return;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const current = await readRemote(config);
      const response = await fetch(endpoint(config), {
        method: "PUT",
        headers: headers(config, true),
        body: JSON.stringify({ expectedRevision: current.revision, value: normalized }),
      });
      if (response.status === 409 && attempt === 0) continue;
      if (!response.ok) throw new Error(`valuation workspace write failed: ${response.status}`);
      return;
    } catch {
      return;
    }
  }
}
