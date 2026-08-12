import { z } from "zod";

export const valuationScenarioIdSchema = z.enum(["bear", "base", "bull"]);
export const valuationCheckStatusSchema = z.enum(["pass", "warning", "fail"]);

const nullableNumber = z.number().finite().nullable();

const valuationSecuritySchema = z.object({
  market: z.string().min(1),
  symbol: z.string().min(1),
  name: z.string().min(1),
  currency: z.string().min(1),
}).strict();

const historicalDriverSchema = z.object({
  period: z.string().min(1),
  revenue: nullableNumber,
  ebitMarginPct: nullableNumber,
  daPctRevenue: nullableNumber,
  capexPctRevenue: nullableNumber,
  nwcPctDeltaRevenue: nullableNumber,
  sourceIds: z.array(z.string().min(1)).max(20),
}).strict();

const forecastDriverSchema = z.object({
  year: z.number().int().min(1900).max(2200),
  revenueGrowthPct: z.number().finite(),
  ebitMarginPct: z.number().finite(),
  taxRatePct: z.number().min(0).max(100),
  daPctRevenue: z.number().min(0).max(100),
  capexPctRevenue: z.number().min(0).max(100),
  nwcPctDeltaRevenue: z.number().finite(),
}).strict();

const valuationScenarioSchema = z.object({
  id: valuationScenarioIdSchema,
  label: z.string().min(1),
  waccPct: z.number().positive().max(100),
  terminalGrowthPct: z.number().min(-20).max(20),
  rationale: z.string(),
  drivers: z.array(forecastDriverSchema).min(3).max(10),
}).strict().superRefine((scenario, context) => {
  if (scenario.terminalGrowthPct >= scenario.waccPct) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["terminalGrowthPct"],
      message: "terminal growth must be lower than WACC",
    });
  }
});

const capitalInputsSchema = z.object({
  currentPrice: nullableNumber,
  dilutedSharesM: nullableNumber,
  totalDebtM: nullableNumber,
  cashM: nullableNumber,
  riskFreeRatePct: nullableNumber,
  beta: nullableNumber,
  equityRiskPremiumPct: nullableNumber,
  preTaxCostDebtPct: nullableNumber,
  taxRatePct: nullableNumber,
}).strict();

const projectionRowSchema = z.object({
  year: z.number().int(),
  revenue: nullableNumber,
  revenueGrowthPct: z.number().finite(),
  ebit: nullableNumber,
  ebitMarginPct: z.number().finite(),
  nopat: nullableNumber,
  depreciationAmortization: nullableNumber,
  capex: nullableNumber,
  changeNwc: nullableNumber,
  unleveredFcf: nullableNumber,
  discountPeriod: z.number().positive(),
  discountFactor: nullableNumber,
  pvFcf: nullableNumber,
}).strict();

const valuationResultSchema = z.object({
  scenarioId: valuationScenarioIdSchema,
  pvExplicitFcfM: nullableNumber,
  terminalValueM: nullableNumber,
  pvTerminalValueM: nullableNumber,
  enterpriseValueM: nullableNumber,
  netDebtM: nullableNumber,
  equityValueM: nullableNumber,
  impliedPrice: nullableNumber,
  currentPrice: nullableNumber,
  impliedReturnPct: nullableNumber,
  terminalValueSharePct: nullableNumber,
}).strict();

const sensitivityGridSchema = z.object({
  waccPct: z.array(z.number().finite()).length(5),
  terminalGrowthPct: z.array(z.number().finite()).length(5),
  impliedPrices: z.array(z.array(nullableNumber).length(5)).length(5),
  center: z.object({ row: z.literal(2), column: z.literal(2) }).strict(),
}).strict();

const sourceReferenceSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  asOf: z.string().min(1),
  source: z.string().min(1),
  url: z.string().url().optional(),
  status: z.enum(["verified", "available", "stale", "unavailable"]),
}).strict();

const auditCheckSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  status: valuationCheckStatusSchema,
  message: z.string().min(1),
}).strict();

export const valuationModelSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  modelScope: z.literal("driver-based-dcf"),
  security: valuationSecuritySchema,
  asOf: z.string().min(1),
  unitScale: z.string().min(1),
  selectedScenario: valuationScenarioIdSchema,
  historicals: z.array(historicalDriverSchema).min(1).max(5),
  capitalInputs: capitalInputsSchema,
  scenarios: z.array(valuationScenarioSchema).length(3),
  projections: z.array(projectionRowSchema).max(10),
  result: valuationResultSchema,
  sensitivity: sensitivityGridSchema,
  auditChecks: z.array(auditCheckSchema).max(30),
  sourceMaterials: z.array(sourceReferenceSchema).max(100),
  gaps: z.array(z.string().min(1)).max(30),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
}).strict().superRefine((model, context) => {
  const scenarioIds = model.scenarios.map((scenario) => scenario.id);
  if (new Set(scenarioIds).size !== 3 || !["bear", "base", "bull"].every((id) => scenarioIds.includes(id as z.infer<typeof valuationScenarioIdSchema>))) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["scenarios"],
      message: "bear, base and bull scenarios are required exactly once",
    });
  }
});

export const valuationWorkspaceSchema = z.object({
  schemaVersion: z.literal("newma-desk.valuation-workbench.v1"),
  updatedAt: z.string().datetime(),
  models: z.array(valuationModelSchema).max(100),
}).strict();

export type ValuationScenarioId = z.infer<typeof valuationScenarioIdSchema>;
export type ValuationCheckStatus = z.infer<typeof valuationCheckStatusSchema>;
export type ValuationModel = z.infer<typeof valuationModelSchema>;
export type ValuationWorkspace = z.infer<typeof valuationWorkspaceSchema>;
