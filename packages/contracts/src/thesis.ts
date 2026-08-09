import { z } from "zod";

export const thesisStatusSchema = z.enum([
  "draft",
  "active",
  "watch",
  "invalidated",
  "archived",
]);

export const thesisConvictionSchema = z.enum(["high", "medium", "low"]);
export const thesisImpactSchema = z.enum([
  "strengthened",
  "weakened",
  "neutral",
  "invalidated",
]);
export const thesisTrendSchema = z.enum([
  "improving",
  "stable",
  "deteriorating",
  "pending",
]);

const thesisSourceSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  url: z.string().url().optional(),
}).strict();

const thesisFreshnessSchema = z.object({
  status: z.enum(["live", "fresh", "stale", "unknown"]),
  ageDays: z.number().int().nonnegative().optional(),
}).strict();

const thesisConfidenceSchema = z.object({
  level: thesisConvictionSchema,
  score: z.number().min(0).max(1).optional(),
  rationale: z.string().min(1),
}).strict();

export const thesisPillarSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  expectation: z.string().min(1),
  currentStatus: z.string().min(1),
  trend: thesisTrendSchema,
  evidenceIds: z.array(z.string()).max(100),
}).strict();

export const thesisInvalidationRiskSchema = z.object({
  id: z.string().min(1),
  statement: z.string().min(1),
  invalidationCondition: z.string().min(1),
  status: z.enum(["monitoring", "triggered", "cleared"]),
  evidenceIds: z.array(z.string()).max(100),
}).strict();

export const thesisEvidenceSchema = z.object({
  id: z.string().min(1),
  source: thesisSourceSchema,
  summary: z.string().min(1),
  asOf: z.string().min(1),
  freshness: thesisFreshnessSchema,
  confidence: thesisConfidenceSchema,
  impact: thesisImpactSchema,
  pillarId: z.string().min(1).optional(),
  createdAt: z.string().datetime(),
}).strict();

export const thesisUpdateSchema = z.object({
  id: z.string().min(1),
  date: z.string().date(),
  dataPoint: z.string().min(1),
  impact: thesisImpactSchema,
  pillarId: z.string().min(1).optional(),
  evidenceIds: z.array(z.string()).max(20),
  conviction: thesisConvictionSchema,
  note: z.string().optional(),
}).strict();

export const investmentThesisSchema = z.object({
  id: z.string().min(1),
  security: z.object({
    market: z.string().min(1),
    symbol: z.string().min(1),
    name: z.string().min(1),
    exchange: z.string().optional(),
  }).strict(),
  title: z.string().min(1),
  statement: z.string().min(1),
  status: thesisStatusSchema,
  conviction: thesisConvictionSchema,
  pillars: z.array(thesisPillarSchema).min(3).max(5),
  invalidationRisks: z.array(thesisInvalidationRiskSchema).min(3).max(5),
  linkedCatalysts: z.array(z.object({
    id: z.string().min(1),
    title: z.string().min(1),
    date: z.string().date().optional(),
    status: z.string().optional(),
  }).strict()).max(20),
  evidence: z.array(thesisEvidenceSchema).max(100),
  updates: z.array(thesisUpdateSchema).max(100),
  valuation: z.object({
    method: z.string().min(1),
    referenceValue: z.number().nullable(),
    currency: z.string().min(1),
    asOf: z.string().date().optional(),
    assumptions: z.array(z.string().min(1)).max(20),
  }).strict().optional(),
  nextReviewAt: z.string().date(),
  gaps: z.array(z.string().min(1)).max(20),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
}).strict();

export const investmentThesisPortfolioSchema = z.object({
  schemaVersion: z.literal("newma-desk.investment-thesis.v1"),
  updatedAt: z.string().datetime(),
  theses: z.array(investmentThesisSchema).max(100),
}).strict();

export type ThesisStatus = z.infer<typeof thesisStatusSchema>;
export type ThesisConviction = z.infer<typeof thesisConvictionSchema>;
export type ThesisImpact = z.infer<typeof thesisImpactSchema>;
export type ThesisTrend = z.infer<typeof thesisTrendSchema>;
export type ThesisPillar = z.infer<typeof thesisPillarSchema>;
export type ThesisInvalidationRisk = z.infer<typeof thesisInvalidationRiskSchema>;
export type ThesisEvidence = z.infer<typeof thesisEvidenceSchema>;
export type ThesisUpdate = z.infer<typeof thesisUpdateSchema>;
export type InvestmentThesis = z.infer<typeof investmentThesisSchema>;
export type InvestmentThesisPortfolio = z.infer<typeof investmentThesisPortfolioSchema>;
