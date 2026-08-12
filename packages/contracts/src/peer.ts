import { z } from "zod";

export const peerResearchQuestionSchema = z.enum([
  "valuation",
  "growth",
  "quality",
  "efficiency",
  "competitive-positioning",
]);

const peerSecuritySchema = z.object({
  market: z.string().min(1),
  symbol: z.string().min(1),
  name: z.string().min(1),
  currency: z.string().min(1),
}).strict();

const peerMemberSchema = z.object({
  security: peerSecuritySchema,
  role: z.enum(["target", "direct", "adjacent", "emerging"]),
  included: z.boolean(),
  rationale: z.string().min(1),
  exceptions: z.array(z.string().min(1)).max(10),
}).strict();

const peerMetricSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  category: z.enum(["operating", "valuation", "quality", "industry"]),
  unit: z.string().min(1),
  higherIsBetter: z.boolean().nullable(),
}).strict();

const peerRowSchema = z.object({
  security: peerSecuritySchema,
  isTarget: z.boolean(),
  period: z.string().min(1),
  coverageRatio: z.number().min(0).max(1),
  values: z.record(z.string(), z.number().nullable()),
  scores: z.record(z.string(), z.number().nullable()),
  sourceIds: z.array(z.string()).max(30),
  warnings: z.array(z.string().min(1)).max(20),
}).strict();

const metricStatisticsSchema = z.object({
  max: z.number().nullable(),
  q75: z.number().nullable(),
  median: z.number().nullable(),
  q25: z.number().nullable(),
  min: z.number().nullable(),
}).strict();

const strategicDimensionSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  moat: z.enum(["network-effects", "switching-costs", "scale-economies", "intangible-assets", "other"]),
  targetAssessment: z.string().min(1),
  peerObservation: z.string().min(1),
  trajectory: z.enum(["improving", "stable", "deteriorating", "unknown"]),
  sourceIds: z.array(z.string()).max(20),
}).strict();

const peerSourceSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  symbol: z.string().min(1).optional(),
  asOf: z.string().min(1),
  url: z.string().url().optional(),
  status: z.enum(["verified", "available", "stale", "unavailable"]),
}).strict();

export const peerComparisonCaseSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  researchQuestion: peerResearchQuestionSchema,
  target: peerSecuritySchema,
  members: z.array(peerMemberSchema).min(2).max(8),
  period: z.object({
    label: z.string().min(1),
    asOf: z.string().min(1),
    fiscalAlignment: z.enum(["aligned", "mixed", "unknown"]),
    unitScale: z.string().min(1),
  }).strict(),
  metrics: z.array(peerMetricSchema).min(3).max(15),
  rows: z.array(peerRowSchema).max(8),
  statistics: z.record(z.string(), metricStatisticsSchema),
  strategicDimensions: z.array(strategicDimensionSchema).max(10),
  sourceMaterials: z.array(peerSourceSchema).max(100),
  synthesis: z.object({
    durableAdvantages: z.array(z.string().min(1)).max(10),
    structuralVulnerabilities: z.array(z.string().min(1)).max(10),
    currentVsTrajectory: z.string(),
  }).strict(),
  gaps: z.array(z.string().min(1)).max(30),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
}).strict();

export const peerComparisonWorkspaceSchema = z.object({
  schemaVersion: z.literal("newma-desk.peer-comparison.v1"),
  updatedAt: z.string().datetime(),
  cases: z.array(peerComparisonCaseSchema).max(100),
}).strict();

export type PeerResearchQuestion = z.infer<typeof peerResearchQuestionSchema>;
export type PeerComparisonCase = z.infer<typeof peerComparisonCaseSchema>;
export type PeerComparisonWorkspace = z.infer<typeof peerComparisonWorkspaceSchema>;
