import { z } from "zod";

export const catalystTypeSchema = z.enum([
  "earnings",
  "corporate",
  "industry",
  "macro",
  "regulatory",
  "lockup",
  "announcement",
  "news",
  "research",
  "custom",
]);

export const catalystStatusSchema = z.enum([
  "upcoming",
  "monitoring",
  "confirmed",
  "invalidated",
  "expired",
]);

export const catalystEventSchema = z.object({
  id: z.string().min(1),
  type: catalystTypeSchema,
  date: z.string().date().optional(),
  windowStart: z.string().date().optional(),
  windowEnd: z.string().date().optional(),
  timePrecision: z.enum(["date", "window"]),
  status: catalystStatusSchema,
  title: z.string().min(1),
  summary: z.string(),
  source: z.object({
    id: z.string().min(1),
    label: z.string().min(1),
    url: z.string().url().optional(),
  }).strict(),
  evidenceIds: z.array(z.string()),
  asOf: z.string().min(1),
  freshness: z.object({
    status: z.enum(["live", "fresh", "stale", "unknown"]),
    ageDays: z.number().int().nonnegative().optional(),
  }).strict(),
  confidence: z.object({
    level: z.enum(["high", "medium", "low"]),
    score: z.number().min(0).max(1).optional(),
    rationale: z.string(),
  }).strict(),
  impactedAssets: z.array(z.object({
    market: z.enum(["CN", "HK", "US"]),
    symbol: z.string().min(1),
    name: z.string().optional(),
  }).strict()),
  expectedDirection: z.enum(["positive", "negative", "mixed", "unknown"]),
  confirmationConditions: z.array(z.string()),
  invalidationConditions: z.array(z.string()),
  importance: z.enum(["high", "medium", "low"]),
  cycleContext: z.record(z.unknown()).optional(),
}).strict().superRefine((value, context) => {
  if (value.timePrecision === "date" && !value.date) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "date precision requires date" });
  }
  if (value.timePrecision === "window" && (!value.windowStart || !value.windowEnd)) {
    context.addIssue({ code: z.ZodIssueCode.custom, message: "window precision requires start and end" });
  }
});

export const catalystSourceStatusSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  status: z.enum(["ok", "empty", "unavailable", "unsupported"]),
  count: z.number().int().nonnegative(),
  asOf: z.string().min(1),
  error: z.string().optional(),
}).strict();

export const catalystFeedSchema = z.object({
  schemaVersion: z.literal("newma-desk.catalyst-calendar.v1"),
  generatedAt: z.string().min(1),
  horizon: z.object({
    start: z.string().date(),
    end: z.string().date(),
    days: z.number().int().min(14).max(1095),
  }).strict(),
  coverage: z.object({
    markets: z.array(z.string()),
    symbols: z.array(z.string()),
  }).strict(),
  items: z.array(catalystEventSchema),
  sources: z.array(catalystSourceStatusSchema),
  gaps: z.array(z.object({ capability: z.string(), reason: z.string() }).strict()),
  disclaimer: z.string(),
}).strict();

export type CatalystType = z.infer<typeof catalystTypeSchema>;
export type CatalystStatus = z.infer<typeof catalystStatusSchema>;
export type CatalystEvent = z.infer<typeof catalystEventSchema>;
export type CatalystFeed = z.infer<typeof catalystFeedSchema>;
