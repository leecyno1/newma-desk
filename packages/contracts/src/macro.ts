import { z } from "zod";

const sourceSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  url: z.string().url(),
}).passthrough();

const freshnessSchema = z.object({
  status: z.enum(["fresh", "stale", "unknown"]),
  ageDays: z.number().int().nonnegative().optional(),
}).strict();

const confidenceSchema = z.object({
  level: z.enum(["high", "medium", "low"]),
  score: z.number().min(0).max(1),
  rationale: z.string().min(1),
}).strict();

export const macroIndicatorSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  region: z.string().min(1),
  category: z.enum(["growth", "inflation", "liquidity", "labour", "trade", "rates"]),
  unit: z.string().min(1),
  period: z.string().min(1),
  releaseDate: z.string().date().nullable(),
  nextReleaseDate: z.string().date().optional(),
  value: z.number(),
  forecast: z.number().nullable(),
  previous: z.number().nullable(),
  change: z.number().nullable(),
  direction: z.enum(["higher", "lower", "flat"]),
  source: sourceSchema,
  evidenceId: z.string().min(1),
  asOf: z.string().min(1),
  freshness: freshnessSchema,
  confidence: confidenceSchema,
  history: z.array(z.object({
    period: z.string().min(1),
    value: z.number(),
  }).strict()).max(24),
}).passthrough();

export const macroCalendarEventSchema = z.object({
  id: z.string().min(1),
  date: z.string().date(),
  time: z.string().nullable(),
  region: z.string().min(1),
  currency: z.string().nullable(),
  title: z.string().min(1),
  importance: z.enum(["high", "medium", "low", "unknown"]),
  status: z.enum(["scheduled", "released"]),
  actual: z.number().nullable(),
  forecast: z.number().nullable(),
  previous: z.number().nullable(),
  source: sourceSchema,
  evidenceId: z.string().min(1),
  asOf: z.string().min(1),
}).passthrough();

const regimeDimensionSchema = z.object({
  label: z.string().min(1),
  signal: z.enum(["positive", "neutral", "negative", "mixed", "unknown"]),
  summary: z.string().min(1),
  evidenceIds: z.array(z.string()),
}).strict();

export const macroMonitorFeedSchema = z.object({
  schemaVersion: z.literal("newma-desk.macro-monitor.v1"),
  generatedAt: z.string().min(1),
  horizon: z.object({
    start: z.string().date(),
    end: z.string().date(),
    days: z.number().int().min(1).max(30),
  }).strict(),
  regime: z.object({
    overall: z.object({ label: z.string(), summary: z.string(), signals: z.array(z.string()), evidenceIds: z.array(z.string()) }).optional(),
    growth: regimeDimensionSchema,
    inflation: regimeDimensionSchema,
    liquidity: regimeDimensionSchema,
    confidence: confidenceSchema,
  }).passthrough(),
  decisionReview: z.object({
    adoption: z.string().min(1),
    thesis: z.string().min(1),
    scope: z.string().min(1),
    supportingEvidence: z.array(z.object({ dimension: z.string(), signal: z.enum(["positive", "neutral", "negative", "mixed", "unknown"]), summary: z.string(), evidenceIds: z.array(z.string()) })),
    counterEvidence: z.array(z.string()),
    checks: z.array(z.string()),
    nextReviewEvents: z.array(z.object({ id: z.string(), date: z.string().date(), title: z.string(), importance: z.enum(["high", "medium", "low", "unknown"]), ratingBasis: z.enum(["source", "rule", "unknown"]).optional(), evidenceId: z.string() })),
  }).optional(),
  liquidity: z.object({
    assessment: z.object({
      signal: z.enum(["supportive", "restrictive", "mixed"]),
      complete: z.boolean(),
      supportiveCount: z.number().int().nonnegative(),
      restrictiveCount: z.number().int().nonnegative(),
      observedCount: z.number().int().nonnegative(),
      method: z.string().min(1),
      items: z.array(z.object({ id: z.string(), name: z.string(), period: z.string(), change: z.number(), unit: z.string(), vote: z.enum(["supportive", "restrictive", "flat"]) })),
    }),
  }).passthrough().optional(),
  indicators: z.array(macroIndicatorSchema),
  events: z.array(macroCalendarEventSchema),
  sources: z.array(z.object({
    id: z.string().min(1),
    label: z.string().min(1),
    status: z.enum(["ok", "partial", "empty", "unavailable", "unsupported"]),
    count: z.number().int().nonnegative(),
    asOf: z.string().min(1),
    coverage: z.record(z.unknown()).optional(),
    error: z.string().optional(),
  }).strict()),
  gaps: z.array(z.object({
    capability: z.string().min(1),
    reason: z.string().min(1),
  }).strict()),
  disclaimer: z.string().min(1),
}).passthrough();

export type MacroIndicator = z.infer<typeof macroIndicatorSchema>;
export type MacroCalendarEvent = z.infer<typeof macroCalendarEventSchema>;
export type MacroMonitorFeed = z.infer<typeof macroMonitorFeedSchema>;
