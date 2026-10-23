import { z } from "zod";

/** Metadata only; never include messages, workspaces, credentials or tool output. */
export const sessionBoardSnapshotSchema = z.object({
  source: z.literal("newma-hermes"), scope: z.string().min(1).max(300), fetchedAt: z.string().datetime(),
  truncated: z.boolean(), sessions: z.array(z.object({
    id: z.string().min(1).max(256), title: z.string().max(300), projectId: z.string().max(128),
    projectName: z.string().max(200), model: z.string().max(160),
    status: z.enum(["attention", "running", "queued", "idle", "unknown"]),
    attention: z.string().max(120), pinned: z.boolean(), readOnly: z.boolean(),
    updatedAt: z.string().datetime().nullable(), url: z.string().url().max(2048),
  })).max(500),
});
export type SessionBoardSnapshot = z.infer<typeof sessionBoardSnapshotSchema>;
