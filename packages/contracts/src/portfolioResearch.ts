import { z } from "zod";

import { researchArchiveEntrySchema } from "./researchArchive";

export const portfolioResearchCoverageStatusSchema = z.enum([
  "complete",
  "partial",
  "missing",
]);

export const portfolioResearchMissingGroupSchema = z.enum([
  "core-thesis-or-memo",
  "supporting-analysis",
]);

export const portfolioResearchAttentionReasonSchema = z.enum([
  "review-overdue",
  "stale-core-research",
  "invalidated-thesis",
]);

export const portfolioResearchPositionSchema = z.object({
  market: z.enum(["CN", "HK", "US"]),
  symbol: z.string().min(1).max(32),
  name: z.string().min(1).max(160),
  accountIds: z.array(z.string().min(1).max(64)).min(1).max(64),
  status: portfolioResearchCoverageStatusSchema,
  referenceCount: z.number().int().nonnegative(),
  activeReferenceCount: z.number().int().nonnegative(),
  coreKinds: z.array(z.enum(["thesis", "research-memo"])).max(2),
  supportingKinds: z.array(z.enum([
    "earnings",
    "peer-comparison",
    "valuation",
  ])).max(3),
  missingGroups: z.array(portfolioResearchMissingGroupSchema).max(2),
  attentionReasons: z.array(portfolioResearchAttentionReasonSchema).max(3),
  latestUpdatedAt: z.string().datetime().optional(),
  references: z.array(researchArchiveEntrySchema).max(50),
}).strict();

export const portfolioResearchCoverageSchema = z.object({
  schemaVersion: z.literal("newma-desk.portfolio-research-coverage.v1"),
  userId: z.string().min(1).max(128),
  workspaceId: z.string().min(1).max(128),
  generatedAt: z.string().datetime(),
  summary: z.object({
    positionCount: z.number().int().nonnegative(),
    completeCount: z.number().int().nonnegative(),
    partialCount: z.number().int().nonnegative(),
    missingCount: z.number().int().nonnegative(),
    attentionCount: z.number().int().nonnegative(),
    activeReferenceCount: z.number().int().nonnegative(),
  }).strict(),
  positions: z.array(portfolioResearchPositionSchema).max(500),
}).strict().superRefine((coverage, context) => {
  const unique = new Set<string>();
  coverage.positions.forEach((position, index) => {
    const identity = `${position.market}:${position.symbol.toUpperCase()}`;
    if (unique.has(identity)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["positions", index, "symbol"],
        message: "portfolio research coverage securities must be unique",
      });
    }
    unique.add(identity);
  });
});

export type PortfolioResearchCoverageStatus = z.infer<typeof portfolioResearchCoverageStatusSchema>;
export type PortfolioResearchMissingGroup = z.infer<typeof portfolioResearchMissingGroupSchema>;
export type PortfolioResearchAttentionReason = z.infer<typeof portfolioResearchAttentionReasonSchema>;
export type PortfolioResearchPosition = z.infer<typeof portfolioResearchPositionSchema>;
export type PortfolioResearchCoverage = z.infer<typeof portfolioResearchCoverageSchema>;
