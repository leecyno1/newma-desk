import { z } from "zod";

export const researchArchiveKindSchema = z.enum([
  "uploaded-report",
  "research-record",
  "thesis",
  "earnings",
  "peer-comparison",
  "valuation",
  "research-memo",
]);

export const researchArchiveStatusSchema = z.enum([
  "active",
  "draft",
  "archived",
  "invalidated",
  "stale",
  "unknown",
]);

export const researchArchiveSecuritySchema = z.object({
  market: z.string().min(1).max(24),
  symbol: z.string().min(1).max(32),
  name: z.string().min(1).max(160),
}).strict();

export const researchArchiveEntrySchema = z.object({
  id: z.string().min(1).max(320),
  kind: researchArchiveKindSchema,
  sourceModId: z.string().min(1).max(64),
  artifactId: z.string().min(1).max(240),
  title: z.string().min(1).max(320),
  status: researchArchiveStatusSchema,
  security: researchArchiveSecuritySchema.optional(),
  asOf: z.string().min(1).max(80).optional(),
  updatedAt: z.string().datetime(),
  tags: z.array(z.string().min(1).max(80)).max(16),
  sourceRevision: z.number().int().positive().optional(),
}).strict();

export const researchArchiveIndexSchema = z.object({
  schemaVersion: z.literal("newma-desk.research-archive.v1"),
  userId: z.string().min(1).max(128),
  workspaceId: z.string().min(1).max(128),
  generatedAt: z.string().datetime(),
  entries: z.array(researchArchiveEntrySchema).max(1000),
}).strict().superRefine((index, context) => {
  const ids = new Set<string>();
  index.entries.forEach((entry, entryIndex) => {
    if (ids.has(entry.id)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["entries", entryIndex, "id"],
        message: "research archive entry ids must be unique",
      });
    }
    ids.add(entry.id);
  });
});

export type ResearchArchiveKind = z.infer<typeof researchArchiveKindSchema>;
export type ResearchArchiveStatus = z.infer<typeof researchArchiveStatusSchema>;
export type ResearchArchiveSecurity = z.infer<typeof researchArchiveSecuritySchema>;
export type ResearchArchiveEntry = z.infer<typeof researchArchiveEntrySchema>;
export type ResearchArchiveIndex = z.infer<typeof researchArchiveIndexSchema>;
