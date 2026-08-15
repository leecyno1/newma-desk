import { z } from "zod";

const modIdSchema = z.string().regex(/^[a-z][a-z0-9-]{2,63}$/);
const entrypointIdSchema = z.string().regex(/^[a-z][a-z0-9-]{1,63}$/);

export const wikiSubjectTypeSchema = z.enum([
  "security",
  "etf",
  "fund",
  "company",
  "industry",
  "concept",
  "event",
  "topic",
]);

export const wikiIntentIdSchema = z
  .string()
  .regex(/^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$/);

export const wikiConceptTagSchema = z
  .string()
  .regex(/^[a-z][a-z0-9-]{1,63}$/);

export const wikiCanonicalIdSchema = z
  .string()
  .min(3)
  .max(240)
  .refine((value) => !/\s/.test(value), {
    message: "Wiki canonical IDs cannot contain whitespace",
  });

export const wikiSubjectRefSchema = z
  .object({
    type: wikiSubjectTypeSchema,
    canonicalId: wikiCanonicalIdSchema,
    displayName: z.string().min(1).max(160),
    market: z.enum(["CN", "HK", "US"]).optional(),
    symbol: z.string().min(1).max(40).optional(),
    assetType: z.enum(["stock", "etf", "fund", "index", "other"]).optional(),
  })
  .strict()
  .superRefine((subject, context) => {
    if (!subject.canonicalId.startsWith(`${subject.type}:`)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["canonicalId"],
        message: "Wiki canonical ID prefix must match the subject type",
      });
    }
    if (
      ["security", "etf", "fund"].includes(subject.type) &&
      (!subject.market || !subject.symbol)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Tradable Wiki subjects require market and symbol",
      });
    }
    if (subject.type === "etf" && subject.assetType && subject.assetType !== "etf") {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["assetType"],
        message: "ETF subjects must use the ETF asset type",
      });
    }
    if (subject.type === "fund" && subject.assetType && subject.assetType !== "fund") {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["assetType"],
        message: "Fund subjects must use the fund asset type",
      });
    }
  });

const wikiParameterValueSchema = z.union([
  z.string().max(500),
  z.number().finite(),
  z.boolean(),
]);

export const wikiParameterMapSchema = z
  .record(wikiParameterValueSchema)
  .superRefine((parameters, context) => {
    if (Object.keys(parameters).length > 32) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Wiki parameters cannot contain more than 32 entries",
      });
    }
  });

export const modWikiEntrypointSchema = z
  .object({
    id: entrypointIdSchema,
    intent: wikiIntentIdSchema,
    label: z.string().min(1).max(80),
    contextContract: z.literal("newma.wiki.subject.v1"),
    defaults: wikiParameterMapSchema.default({}),
  })
  .strict();

export const modWikiProfileSchema = z
  .object({
    contractVersion: z.literal("1.0"),
    subjectTypes: z
      .array(wikiSubjectTypeSchema)
      .min(1)
      .max(16)
      .refine((items) => new Set(items).size === items.length, {
        message: "Wiki subject types must be unique",
      }),
    concepts: z
      .array(wikiConceptTagSchema)
      .max(50)
      .default([])
      .refine((items) => new Set(items).size === items.length, {
        message: "Wiki concepts must be unique",
      }),
    entrypoints: z
      .array(modWikiEntrypointSchema)
      .min(1)
      .max(20)
      .refine(
        (items) => new Set(items.map((item) => item.id)).size === items.length,
        { message: "Wiki entrypoint IDs must be unique" },
      ),
  })
  .strict();

const relatedSubjectsSchema = z
  .array(wikiSubjectRefSchema)
  .max(20)
  .default([])
  .refine(
    (items) => new Set(items.map((item) => item.canonicalId)).size === items.length,
    { message: "Related Wiki subjects must be unique" },
  );

const conceptIdsSchema = z
  .array(wikiCanonicalIdSchema)
  .max(50)
  .default([])
  .refine((items) => new Set(items).size === items.length, {
    message: "Wiki concept IDs must be unique",
  });

export const wikiPageContextSchema = z
  .object({
    primarySubject: wikiSubjectRefSchema,
    relatedSubjects: relatedSubjectsSchema,
    conceptIds: conceptIdsSchema,
    intent: wikiIntentIdSchema,
    timeframe: z.string().min(1).max(40).optional(),
    snapshotId: z.string().min(1).max(160).optional(),
  })
  .strict();

export const wikiLinkMatchSchema = z
  .object({
    subjectType: wikiSubjectTypeSchema,
    intentScore: z.number().int().min(0).max(25),
    concepts: z.array(z.string().min(1).max(240)).default([]),
    dataCapabilities: z.array(z.string().min(1).max(160)).default([]),
  })
  .strict();

export const wikiLinkSchema = z
  .object({
    id: z.string().min(3).max(140),
    targetModId: modIdSchema,
    targetRevision: z.number().int().positive(),
    entrypointId: entrypointIdSchema,
    intent: wikiIntentIdSchema,
    label: z.string().min(1).max(80),
    reason: z.string().min(1).max(240),
    score: z.number().int().min(0).max(100),
    match: wikiLinkMatchSchema,
  })
  .strict();

export const wikiLinkResolutionResponseSchema = z
  .object({
    sourceModId: modIdSchema,
    subject: wikiSubjectRefSchema,
    links: z.array(wikiLinkSchema).max(20),
    generatedAt: z.string().datetime({ offset: true }),
  })
  .strict();

export const wikiSubjectMatchSchema = z
  .object({
    subject: wikiSubjectRefSchema,
    aliases: z.array(z.string().min(1).max(160)).max(20).default([]),
    conceptIds: conceptIdsSchema,
    source: z.string().min(1).max(120),
    matchedBy: z.enum(["canonical", "symbol", "name", "alias", "upstream"]),
    confidence: z.number().min(0).max(1),
  })
  .strict();

export const wikiHandoffSchema = z
  .object({
    version: z.literal(1),
    id: z.string().regex(/^hf_[A-Za-z0-9_-]{8,120}$/),
    sourceModId: modIdSchema,
    sourceSnapshotId: z.string().min(1).max(160).optional(),
    targetModId: modIdSchema,
    entrypointId: entrypointIdSchema,
    subject: wikiSubjectRefSchema,
    relatedSubjects: relatedSubjectsSchema,
    conceptIds: conceptIdsSchema,
    intent: wikiIntentIdSchema,
    timeframe: z.string().min(1).max(40).optional(),
    parameters: wikiParameterMapSchema.default({}),
    createdAt: z.string().datetime({ offset: true }),
    expiresAt: z.string().datetime({ offset: true }),
  })
  .strict()
  .superRefine((handoff, context) => {
    if (Date.parse(handoff.expiresAt) <= Date.parse(handoff.createdAt)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["expiresAt"],
        message: "Wiki handoff expiry must be after creation",
      });
    }
  });

export type WikiSubjectType = z.infer<typeof wikiSubjectTypeSchema>;
export type WikiSubjectRef = z.infer<typeof wikiSubjectRefSchema>;
export type WikiPageContext = z.infer<typeof wikiPageContextSchema>;
export type WikiLinkMatch = z.infer<typeof wikiLinkMatchSchema>;
export type WikiLink = z.infer<typeof wikiLinkSchema>;
export type WikiLinkResolutionResponse = z.infer<
  typeof wikiLinkResolutionResponseSchema
>;
export type WikiSubjectMatch = z.infer<typeof wikiSubjectMatchSchema>;
export type WikiHandoff = z.infer<typeof wikiHandoffSchema>;
export type ModWikiEntrypoint = z.infer<typeof modWikiEntrypointSchema>;
export type ModWikiProfile = z.infer<typeof modWikiProfileSchema>;
