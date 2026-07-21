import { z } from "zod";

import { modEventNameSchema } from "./event";

const LOCAL_URL_ORIGIN = "https://module.local";

function fullyDecode(value: string): string | undefined {
  let decoded = value;

  for (let pass = 0; pass < 10; pass += 1) {
    try {
      const next = decodeURIComponent(decoded);
      if (next === decoded) return decoded;
      decoded = next;
    } catch {
      return undefined;
    }
  }

  return undefined;
}

function isSafeRelativeUrl(url: string): boolean {
  if (
    !url.startsWith("/") ||
    url.startsWith("//") ||
    url.includes("\\") ||
    url.includes("..")
  ) {
    return false;
  }

  const pathEnd = url.search(/[?#]/);
  const encodedPath = pathEnd === -1 ? url : url.slice(0, pathEnd);
  const decodedPath = fullyDecode(encodedPath);

  if (
    decodedPath === undefined ||
    !decodedPath.startsWith("/") ||
    decodedPath.startsWith("//") ||
    decodedPath.includes("\\") ||
    decodedPath.includes("..") ||
    decodedPath.split("/").includes(".")
  ) {
    return false;
  }

  try {
    return new URL(url, LOCAL_URL_ORIGIN).origin === LOCAL_URL_ORIGIN;
  } catch {
    return false;
  }
}

const safeRelativeUrl = z
  .string()
  .refine(isSafeRelativeUrl);

const safeExternalUrl = z
  .string()
  .url()
  .refine((url) => {
    const protocol = new URL(url).protocol;
    return protocol === "http:" || protocol === "https:";
  });

export const modEntrySchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("structured"), url: safeRelativeUrl }).strict(),
  z.object({ type: z.literal("static"), url: safeRelativeUrl }).strict(),
  z.object({ type: z.literal("external"), url: safeExternalUrl }).strict(),
]);

const refreshSchema = z.discriminatedUnion("mode", [
  z.object({ mode: z.literal("manual") }).strict(),
  z
    .object({ mode: z.literal("schedule"), cron: z.string().min(1) })
    .strict(),
]);

export const modNavigationSchema = z
  .object({
    groupLabel: z.string().min(1).max(40),
    groupOrder: z.number().int().nonnegative().default(100),
    itemOrder: z.number().int().nonnegative().default(100),
    icon: z
      .enum(["research", "market", "quant", "module"])
      .default("module"),
  })
  .strict();

export const modManifestSchema = z.object({
  schemaVersion: z.literal("1.0"),
  id: z.string().regex(/^[a-z][a-z0-9-]{2,63}$/),
  name: z.string().min(1).max(80),
  version: z.string().regex(/^\d+\.\d+\.\d+$/),
  category: z.string().regex(/^[a-z][a-z0-9-]{1,31}$/),
  navigation: modNavigationSchema.optional(),
  entry: modEntrySchema,
  icon: z.string().optional(),
  permissions: z.array(z.string()).default([]),
  dataServices: z.array(z.string()).default([]),
  agentCapabilities: z.array(z.string()).default([]),
  events: z
    .object({
      emits: z.array(modEventNameSchema).default([]),
      accepts: z.array(modEventNameSchema).default([]),
    })
    .strict()
    .default({}),
  refresh: refreshSchema.optional(),
}).strict();

export type ModManifest = z.infer<typeof modManifestSchema>;

// Compatibility aliases for existing Vibe Research / Vibe Trading adapters.
// New VibeDesk code should use the Mod names above.
export const moduleEntrySchema = modEntrySchema;
export const moduleNavigationSchema = modNavigationSchema;
export const moduleManifestSchema = modManifestSchema;
export type ModuleManifest = ModManifest;
