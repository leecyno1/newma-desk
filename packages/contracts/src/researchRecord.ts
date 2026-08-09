import { z } from "zod";

export const researchRecordSchema = z.object({
  id: z.string().min(1).max(160),
  kind: z.string().min(1).max(40),
  title: z.string().min(1).max(240),
  content: z.string().min(1).max(120_000),
  ts: z.number().int().nonnegative(),
}).strict();

export const researchRecordWorkspaceSchema = z.object({
  schemaVersion: z.literal("newma-desk.research-records.v1"),
  updatedAt: z.string().datetime(),
  records: z.array(researchRecordSchema).max(200),
}).strict();

export type ResearchRecord = z.infer<typeof researchRecordSchema>;
export type ResearchRecordWorkspace = z.infer<typeof researchRecordWorkspaceSchema>;
