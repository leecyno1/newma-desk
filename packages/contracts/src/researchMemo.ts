import { z } from "zod";

export const researchMemoStatusSchema = z.enum([
  "draft",
  "current",
  "superseded",
  "archived",
]);

export const researchBiasSchema = z.enum([
  "constructive",
  "neutral",
  "cautious",
  "watch",
]);

export const researchConvictionSchema = z.enum(["high", "medium", "low"]);
export const researchScenarioIdSchema = z.enum(["bear", "base", "bull"]);

const securitySchema = z.object({
  market: z.string().min(1),
  symbol: z.string().min(1),
  name: z.string().min(1),
  exchange: z.string().optional(),
  currency: z.string().min(1),
}).strict();

export const researchArtifactReferenceSchema = z.object({
  id: z.string().min(1),
  kind: z.enum([
    "thesis",
    "earnings",
    "peer-comparison",
    "valuation",
    "catalyst",
    "industry-chain",
    "macro",
    "news",
    "other",
  ]),
  sourceModId: z.string().min(1),
  artifactId: z.string().min(1),
  title: z.string().min(1),
  asOf: z.string().min(1).optional(),
  status: z.enum(["linked", "stale", "missing"]),
  note: z.string().optional(),
}).strict();

const keyDriverSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  whyItMatters: z.string().min(1),
  currentView: z.string().min(1),
  monitorMetric: z.string().min(1),
  confirmationCondition: z.string().min(1),
  falsificationCondition: z.string().min(1),
  sourceIds: z.array(z.string().min(1)).max(30),
}).strict();

const scenarioSchema = z.object({
  id: researchScenarioIdSchema,
  label: z.string().min(1),
  probabilityPct: z.number().min(0).max(100),
  operatingPath: z.string().min(1),
  valuationReference: z.string(),
  triggerConditions: z.array(z.string().min(1)).max(20),
  evidenceIds: z.array(z.string().min(1)).max(30),
}).strict();

const catalystSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  window: z.string().min(1),
  expectedPath: z.string().min(1),
  confirmationConditions: z.array(z.string().min(1)).max(20),
  invalidationConditions: z.array(z.string().min(1)).max(20),
  artifactReferenceId: z.string().min(1).optional(),
}).strict();

const researchRiskSchema = z.object({
  id: z.string().min(1),
  type: z.enum([
    "fundamental",
    "valuation",
    "competition",
    "cycle",
    "regulation",
    "technology",
    "execution",
    "accounting",
    "macro",
    "other",
  ]),
  statement: z.string().min(1),
  severity: z.enum(["high", "medium", "low"]),
  likelihood: z.enum(["high", "medium", "low", "unknown"]),
  earlyWarnings: z.array(z.string().min(1)).max(20),
  breakCondition: z.string().min(1),
  sourceIds: z.array(z.string().min(1)).max(30),
}).strict();

const monitoringItemSchema = z.object({
  id: z.string().min(1),
  metric: z.string().min(1),
  latest: z.string(),
  trend: z.enum(["improving", "stable", "deteriorating", "unknown"]),
  threshold: z.string().min(1),
  frequency: z.string().min(1),
  nextReviewAt: z.string().date().optional(),
  sourceIds: z.array(z.string().min(1)).max(30),
}).strict();

export const researchMemoSourceSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  kind: z.enum([
    "filing",
    "company",
    "consensus",
    "research",
    "news",
    "derived",
    "user",
  ]),
  claimType: z.enum(["reported", "guidance", "consensus", "inference"]),
  asOf: z.string().min(1),
  status: z.enum(["verified", "available", "stale", "unavailable"]),
  url: z.string().url().optional(),
  note: z.string().optional(),
}).strict();

const memoVersionSchema = z.object({
  version: z.number().int().positive(),
  createdAt: z.string().datetime(),
  summary: z.string().min(1),
  changedSections: z.array(z.string().min(1)).max(30),
}).strict();

export const researchMemoSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  status: researchMemoStatusSchema,
  security: securitySchema,
  boundary: z.object({
    asOf: z.string().date(),
    horizon: z.string().min(1),
    fiscalYear: z.string().min(1),
    reportingCurrency: z.string().min(1),
    scope: z.string().min(1),
    disclosureLimits: z.array(z.string().min(1)).max(30),
  }).strict(),
  executiveView: z.object({
    bias: researchBiasSchema,
    conviction: researchConvictionSchema,
    conclusion: z.string().min(1),
    coreThesis: z.string().min(1),
    keyDebate: z.string().min(1),
    variantPerception: z.string().min(1),
    whatMayBeMissing: z.string().min(1),
    breakpoint: z.string().min(1),
  }).strict(),
  linkedArtifacts: z.array(researchArtifactReferenceSchema).max(50),
  keyDrivers: z.array(keyDriverSchema).min(3).max(7),
  scenarios: z.array(scenarioSchema).length(3),
  catalysts: z.array(catalystSchema).max(20),
  risks: z.array(researchRiskSchema).min(3).max(12),
  monitoring: z.array(monitoringItemSchema).min(3).max(20),
  sources: z.array(researchMemoSourceSchema).max(150),
  gaps: z.array(z.string().min(1)).max(40),
  nextReviewAt: z.string().date(),
  versions: z.array(memoVersionSchema).min(1).max(100),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
}).strict().superRefine((memo, context) => {
  const scenarioIds = memo.scenarios.map((scenario) => scenario.id);
  if (
    new Set(scenarioIds).size !== 3 ||
    !["bear", "base", "bull"].every((id) => scenarioIds.includes(id as z.infer<typeof researchScenarioIdSchema>))
  ) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["scenarios"],
      message: "bear, base and bull scenarios are required exactly once",
    });
  }
  const probability = memo.scenarios.reduce((sum, scenario) => sum + scenario.probabilityPct, 0);
  if (Math.abs(probability - 100) > 0.01) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["scenarios"],
      message: "scenario probabilities must sum to 100",
    });
  }
});

export const researchMemoWorkspaceSchema = z.object({
  schemaVersion: z.literal("newma-desk.research-memo.v1"),
  updatedAt: z.string().datetime(),
  memos: z.array(researchMemoSchema).max(100),
}).strict();

export type ResearchMemoStatus = z.infer<typeof researchMemoStatusSchema>;
export type ResearchBias = z.infer<typeof researchBiasSchema>;
export type ResearchConviction = z.infer<typeof researchConvictionSchema>;
export type ResearchScenarioId = z.infer<typeof researchScenarioIdSchema>;
export type ResearchArtifactReference = z.infer<typeof researchArtifactReferenceSchema>;
export type ResearchMemoSource = z.infer<typeof researchMemoSourceSchema>;
export type ResearchMemo = z.infer<typeof researchMemoSchema>;
export type ResearchMemoWorkspace = z.infer<typeof researchMemoWorkspaceSchema>;
