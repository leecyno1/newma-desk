import { z } from "zod";
import { businessRevenueSchema } from './businessRevenue';

export const earningsResearchModeSchema = z.enum(["preview", "reported"]);
export const earningsBasisSchema = z.enum(['ytd', 'quarter', 'annual', 'ttm']);
const metricBasisSchema = z.union([earningsBasisSchema, z.literal('instant')]);
export const earningsVerificationStatusSchema = z.enum([
  "verified",
  "partial",
  "unverified",
]);
export const earningsImpactSchema = z.enum([
  "strengthened",
  "weakened",
  "neutral",
  "invalidated",
]);

const sourceReferenceSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  kind: z.enum(["filing", "company", "consensus", "research", "news", "derived", "user"]),
  url: z.string().url().optional(),
  asOf: z.string().min(1).optional(),
  periodEnd: z.string().date().optional(),
  retrievedAt: z.string().datetime().optional(),
  basis: metricBasisSchema.optional(),
  status: z.enum(["verified", "available", "stale", "unavailable"]),
  businessRevenue: businessRevenueSchema.optional(),
  capitalNote: z.object({
    reportId: z.string().min(1), title: z.string().min(1).max(240), text: z.string().min(1).max(6000),
    topics: z.array(z.string().min(1)).max(5),
    pdfPage: z.number().int().positive(), pdfPageCount: z.number().int().positive(),
    readPages: z.array(z.number().int().positive()).max(200),
    truncated: z.boolean(), confirmedAt: z.string().datetime(), contentOrigin: z.literal('pdf-text'),
  }).strict().refine(value => value.pdfPage <= value.pdfPageCount && value.readPages.includes(value.pdfPage),
    '资本附注须保留已读取的 PDF 物理页').optional(),
  discussion: z.object({
    reportId: z.string().min(1), text: z.string().min(1).max(6000),
    topics: z.array(z.string().min(1)).max(5),
    pdfPage: z.number().int().positive(), pdfPageCount: z.number().int().positive(),
    readPages: z.array(z.number().int().positive()).max(30),
    truncated: z.boolean(), confirmedAt: z.string().datetime(), contentOrigin: z.literal('pdf-text'),
  }).strict().refine(value => value.pdfPage <= value.pdfPageCount && value.readPages.includes(value.pdfPage),
    '经营讨论须保留已读取的 PDF 物理页').optional(),
  importedReport: z.object({
    reportId: z.string().min(1), rawValue: z.string().min(1), rawUnit: z.string().min(1),
    columnHeader: z.string().min(1), confirmedAt: z.string().datetime(),
    scope: z.literal('consolidated').optional(),
  }).strict().optional(),
  correction: z.object({
    before: z.number().nullable(), after: z.number(), reason: z.string().min(1).max(2000),
    adoptedAt: z.string().datetime(), evidenceSourceId: z.string().min(1),
    previousSourceIds: z.array(z.string()).max(20),
    amountInput: z.object({
      value: z.string().min(1).max(100),
      unit: z.enum(['元', '万元', '亿元']),
      currency: z.literal('CNY'),
    }).strict().optional(),
  }).strict().optional(),
  excerpt: z.object({
    text: z.string().min(1).max(2000),
    segment: z.number().int().min(1).max(1000).optional(),
    pdfPage: z.number().int().min(1).max(1000).optional(),
    pdfPageCount: z.number().int().min(1).optional(),
    pdfUrl: z.string().url().optional(),
    metricId: z.string().min(1),
    reportedValue: z.number().nullable(),
    unit: z.string().min(1),
    contentOrigin: z.enum(['provider-transcription', 'pdf-text']),
    association: z.literal('user-linked'),
  }).strict().refine(value => value.contentOrigin === 'provider-transcription'
    ? value.segment !== undefined && value.pdfPage === undefined
    : value.pdfPage !== undefined && value.pdfPageCount !== undefined && value.pdfPage <= value.pdfPageCount && value.pdfUrl !== undefined && value.segment === undefined,
  '摘录须保留转录分段或 PDF 物理页定位').optional(),
}).strict();

const comparisonMetricSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  category: z.enum(["financial", "operating", "guidance", "valuation"]),
  unit: z.string().min(1),
  reported: z.number().nullable(),
  internalEstimate: z.number().nullable(),
  consensus: z.number().nullable(),
  varianceVsConsensus: z.object({
    amount: z.number().nullable(),
    percent: z.number().nullable(),
    bps: z.number().nullable(),
  }).strict(),
  sourceIds: z.array(z.string()).max(20),
  asOf: z.string().min(1).optional(),
  periodEnd: z.string().date().optional(),
  reportedCurrency: z.string().min(1).optional(),
  reportedOrigin: z.enum(['provider', 'manual']).optional(),
  reportedBasis: metricBasisSchema.optional(),
  consensusBasis: metricBasisSchema.optional(),
  consensusPeriodEnd: z.string().date().optional(),
  note: z.string().optional(),
}).strict();

const guidanceComparisonSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  period: z.string().min(1),
  unit: z.string().min(1),
  priorLow: z.number().nullable(),
  priorHigh: z.number().nullable(),
  currentLow: z.number().nullable(),
  currentHigh: z.number().nullable(),
  sourceIds: z.array(z.string()).max(20),
  asOf: z.string().min(1).optional(),
  note: z.string().optional(),
}).strict();

const conditionalScenarioSchema = z.object({
  id: z.string().min(1),
  type: z.enum(["above", "inline", "below"]),
  condition: z.string().min(1),
  operatingPath: z.string().min(1),
  researchResponse: z.string().min(1),
  indicators: z.array(z.string().min(1)).max(20),
}).strict();

const estimateRevisionSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  period: z.string().min(1),
  unit: z.string().min(1),
  previous: z.number().nullable(),
  current: z.number().nullable(),
  reason: z.string().min(1),
  sourceIds: z.array(z.string()).max(20),
}).strict();

const thesisImpactSchema = z.object({
  id: z.string().min(1),
  pillarId: z.string().min(1).optional(),
  impact: earningsImpactSchema,
  summary: z.string().min(1),
  evidenceIds: z.array(z.string()).max(20),
}).strict();

export const earningsResearchWorkbookSchema = z.object({
  id: z.string().min(1),
  security: z.object({
    market: z.string().min(1),
    symbol: z.string().min(1),
    name: z.string().min(1),
    exchange: z.string().optional(),
    currency: z.string().min(1),
  }).strict(),
  mode: earningsResearchModeSchema,
  fiscalPeriod: z.object({
    label: z.string().min(1),
    basis: earningsBasisSchema.optional(),
    periodEnd: z.string().date().optional(),
    reportingDate: z.string().date().optional(),
    reportingTime: z.enum(["before-open", "after-close", "during-session", "unknown"]),
  }).strict(),
  verification: z.object({
    status: earningsVerificationStatusSchema,
    latestPeriodChecked: z.boolean(),
    checkedAt: z.string().datetime().optional(),
    primarySourceIds: z.array(z.string()).max(20),
  }).strict(),
  headline: z.string(),
  metrics: z.array(comparisonMetricSchema).max(50),
  operatingMetrics: z.array(comparisonMetricSchema).max(50),
  guidance: z.array(guidanceComparisonSchema).max(30),
  scenarios: z.array(conditionalScenarioSchema).length(3),
  estimateRevisions: z.array(estimateRevisionSchema).max(30),
  thesisImpacts: z.array(thesisImpactSchema).max(30),
  sourceMaterials: z.array(sourceReferenceSchema).max(100),
  gaps: z.array(z.string().min(1)).max(30),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
}).strict();

export const earningsResearchWorkspaceSchema = z.object({
  schemaVersion: z.literal("newma-desk.earnings-research.v1"),
  updatedAt: z.string().datetime(),
  workbooks: z.array(earningsResearchWorkbookSchema).max(100),
}).strict();

export type EarningsResearchMode = z.infer<typeof earningsResearchModeSchema>;
export type EarningsVerificationStatus = z.infer<typeof earningsVerificationStatusSchema>;
export type EarningsImpact = z.infer<typeof earningsImpactSchema>;
export type EarningsResearchWorkbook = z.infer<typeof earningsResearchWorkbookSchema>;
export type EarningsResearchWorkspace = z.infer<typeof earningsResearchWorkspaceSchema>;
