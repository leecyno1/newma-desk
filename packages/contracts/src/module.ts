import { z } from "zod";

const safeRelativeUrl = z
  .string()
  .refine((url) => url.startsWith("/") && !url.includes(".."));

const safeExternalUrl = z
  .string()
  .url()
  .refine((url) => {
    const protocol = new URL(url).protocol;
    return protocol === "http:" || protocol === "https:";
  });

export const moduleEntrySchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("structured"), url: safeRelativeUrl }),
  z.object({ type: z.literal("static"), url: safeRelativeUrl }),
  z.object({ type: z.literal("external"), url: safeExternalUrl }),
]);

export const moduleManifestSchema = z.object({
  schemaVersion: z.literal("1.0"),
  id: z.string().regex(/^[a-z][a-z0-9-]{2,63}$/),
  name: z.string().min(1).max(80),
  version: z.string().regex(/^\d+\.\d+\.\d+$/),
  category: z.string().regex(/^[a-z][a-z0-9-]{1,31}$/),
  entry: moduleEntrySchema,
  icon: z.string().optional(),
  permissions: z.array(z.string()).default([]),
  dataServices: z.array(z.string()).default([]),
  agentCapabilities: z.array(z.string()).default([]),
  events: z
    .object({
      emits: z.array(z.string()).default([]),
      accepts: z.array(z.string()).default([]),
    })
    .default({}),
  refresh: z
    .object({
      mode: z.enum(["manual", "schedule"]),
      cron: z.string().optional(),
    })
    .optional(),
});

export type ModuleManifest = z.infer<typeof moduleManifestSchema>;
