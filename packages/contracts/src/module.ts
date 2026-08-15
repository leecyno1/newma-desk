import { z } from "zod";

import { modEventNameSchema } from "./event";
import { modWikiProfileSchema } from "./wiki";

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

const capabilityIdSchema = z
  .string()
  .regex(/^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$/);
const serviceIdSchema = z.string().regex(/^[a-z][a-z0-9-]{2,63}$/);
const schemaReferenceSchema = z.string().min(1).max(512);
const inlineJsonSchema = z.record(z.unknown());
export const schemaContractSchema = z.union([
  schemaReferenceSchema,
  inlineJsonSchema,
]);

export const modCompatibilitySchema = z
  .object({
    level: z.union([z.literal(1), z.literal(2), z.literal(3)]),
    bridgeProtocol: z.literal("1.0"),
    sdkVersion: z.string().min(1).max(80).optional(),
    viewSpecVersion: z.literal("1.0").optional(),
  })
  .strict();

export const modStorageNamespaceSchema = z
  .object({
    id: z.string().regex(/^[a-z][a-z0-9-]{1,47}$/),
    scope: z.literal("user-workspace").default("user-workspace"),
    schemaVersion: z.number().int().positive().max(10_000),
    quotaMb: z.number().int().positive().max(100),
    maxItemKb: z.number().int().positive().max(1024).default(256),
  })
  .strict();

const deskManagedStorageSchema = z
  .object({
    mode: z.literal("desk-managed"),
    namespaces: z
      .array(modStorageNamespaceSchema)
      .min(1)
      .max(32)
      .refine(
        (items) => new Set(items.map((item) => item.id)).size === items.length,
        { message: "Storage namespace IDs must be unique" },
      ),
  })
  .strict();

export const modStorageSchema = z.discriminatedUnion("mode", [
  z.object({ mode: z.literal("stateless") }).strict(),
  deskManagedStorageSchema,
  z
    .object({
      mode: z.literal("dedicated"),
      adapter: z.string().regex(/^[a-z][a-z0-9-]{1,63}$/),
    })
    .strict(),
  z.object({ mode: z.literal("artifact") }).strict(),
]);

const agentActionBindingSchema = z
  .object({
    type: z.literal("agent"),
    capability: capabilityIdSchema.optional(),
    memoryScope: z.enum([
      "user-agent-mod",
      "task",
    ]),
  })
  .strict();

const modelActionBindingSchema = z
  .object({
    type: z.literal("model"),
    capability: capabilityIdSchema.optional(),
  })
  .strict();

const dataActionBindingSchema = z
  .object({
    type: z.literal("data"),
    service: serviceIdSchema.optional(),
    capability: capabilityIdSchema.optional(),
  })
  .strict();

const localActionBindingSchema = z
  .object({
    type: z.literal("local"),
    capability: capabilityIdSchema.optional(),
  })
  .strict();

export const modActionBindingSchema = z.discriminatedUnion("type", [
  agentActionBindingSchema,
  modelActionBindingSchema,
  dataActionBindingSchema,
  localActionBindingSchema,
]);

export const modActionSchema = z
  .object({
    binding: modActionBindingSchema,
    execution: z.enum(["request", "task", "stream"]),
    permission: capabilityIdSchema,
    inputSchema: schemaContractSchema.optional(),
    outputSchema: schemaContractSchema.optional(),
    confirmation: z.enum(["none", "user", "strong"]).default("none"),
    timeoutSeconds: z.number().positive().max(300).optional(),
  })
  .strict();

const modNavigationIconSchema = z.enum([
  "today",
  "research",
  "market",
  "quant",
  "trading",
  "settings",
  "module",
]);

const projectLetterSchema = z.string().refine(
  (value) => {
    const length = Array.from(value).length;
    return value.trim() === value && length >= 1 && length <= 2;
  },
  { message: "Project logo text must contain one or two visible characters" },
);

export const modProjectLogoSchema = z.discriminatedUnion("type", [
  z
    .object({
      type: z.literal("icon"),
      name: modNavigationIconSchema,
    })
    .strict(),
  z
    .object({
      type: z.literal("letter"),
      text: projectLetterSchema,
    })
    .strict(),
  z
    .object({
      type: z.literal("image"),
      src: z.union([safeRelativeUrl, safeExternalUrl]),
      alt: z.string().min(1).max(80).optional(),
    })
    .strict(),
]);

export const modNavigationProjectSchema = z
  .object({
    id: z.string().regex(/^[a-z][a-z0-9-]{1,47}$/),
    name: z.string().min(1).max(80),
    order: z.number().int().nonnegative().default(100),
    description: z.string().min(1).max(240).optional(),
    logo: modProjectLogoSchema.optional(),
  })
  .strict();

export const modNavigationSchema = z
  .object({
    groupLabel: z.string().min(1).max(40),
    groupOrder: z.number().int().nonnegative().default(100),
    itemOrder: z.number().int().nonnegative().default(100),
    label: z.string().min(1).max(40).optional(),
    directory: z
      .object({
        id: z.string().regex(/^[a-z][a-z0-9-]{1,47}$/),
        label: z.string().min(1).max(40),
        order: z.number().int().nonnegative().default(100),
      })
      .strict()
      .optional(),
    project: modNavigationProjectSchema.optional(),
    icon: modNavigationIconSchema.default("module"),
    role: z.enum(["page", "settings"]).optional(),
  })
  .strict();

const modManifestV1Schema = z.object({
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

const modManifestV1_1Schema = z
  .object({
    schemaVersion: z.literal("1.1"),
    id: z.string().regex(/^[a-z][a-z0-9-]{2,63}$/),
    name: z.string().min(1).max(80),
    version: z.string().regex(/^\d+\.\d+\.\d+$/),
    category: z.string().regex(/^[a-z][a-z0-9-]{1,31}$/),
    navigation: modNavigationSchema.optional(),
    entry: modEntrySchema,
    icon: z.string().optional(),
    compatibility: modCompatibilitySchema,
    permissions: z.array(capabilityIdSchema).default([]),
    dataServices: z.array(serviceIdSchema).default([]),
    storage: modStorageSchema.optional(),
    wiki: modWikiProfileSchema.optional(),
    actions: z.record(capabilityIdSchema, modActionSchema).default({}),
    events: z
      .object({
        emits: z.array(modEventNameSchema).default([]),
        accepts: z.array(modEventNameSchema).default([]),
      })
      .strict()
      .default({}),
    refresh: refreshSchema.optional(),
  })
  .strict()
  .superRefine((manifest, context) => {
    if (
      manifest.compatibility.level === 3 &&
      manifest.compatibility.viewSpecVersion === undefined
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["compatibility", "viewSpecVersion"],
        message: "Level 3 Mods must declare a ViewSpec version",
      });
    }

    if (
      manifest.compatibility.level === 1 &&
      Object.keys(manifest.actions).length > 0
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["actions"],
        message: "Level 1 Mods cannot declare connected actions",
      });
    }

    const permissions = new Set(manifest.permissions);
    const dataServices = new Set(manifest.dataServices);
    if (manifest.storage?.mode === "desk-managed") {
      if (!permissions.has("storage.read")) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["permissions"],
          message: "Desk-managed storage requires storage.read permission",
        });
      }
      if (!permissions.has("storage.write")) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["permissions"],
          message: "Desk-managed storage requires storage.write permission",
        });
      }
    }
    for (const [actionId, action] of Object.entries(manifest.actions)) {
      if (!permissions.has(action.permission)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["actions", actionId, "permission"],
          message: "Action permission must be declared by the Mod",
        });
      }
      if (
        action.binding.type === "data" &&
        action.binding.service !== undefined &&
        !dataServices.has(action.binding.service)
      ) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["actions", actionId, "binding", "service"],
          message: "Data action service must be declared by the Mod",
        });
      }
      if (action.binding.type === "agent" && action.execution !== "task") {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["actions", actionId, "execution"],
          message: "Agent actions must use task execution",
        });
      }
      if (action.binding.type === "model" && action.execution !== "request") {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["actions", actionId, "execution"],
          message: "Model actions must use request execution",
        });
      }
      if (actionId === "trade.execute" && action.confirmation !== "strong") {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["actions", actionId, "confirmation"],
          message: "Trading actions require strong confirmation",
        });
      }
    }
  });

export const modManifestSchema = z.union([
  modManifestV1Schema,
  modManifestV1_1Schema,
]);

export type ModManifest = z.infer<typeof modManifestSchema>;
export type ModCompatibility = z.infer<typeof modCompatibilitySchema>;
export type ModStorage = z.infer<typeof modStorageSchema>;
export type ModStorageNamespace = z.infer<typeof modStorageNamespaceSchema>;
export type ModActionBinding = z.infer<typeof modActionBindingSchema>;
export type ModAction = z.infer<typeof modActionSchema>;
export type ModProjectLogo = z.infer<typeof modProjectLogoSchema>;
export type ModNavigationProject = z.infer<
  typeof modNavigationProjectSchema
>;

// Compatibility aliases for existing Vibe Research / Vibe Trading adapters.
// New Newma-Desk code should use the Mod names above.
export const moduleEntrySchema = modEntrySchema;
export const moduleNavigationSchema = modNavigationSchema;
export const moduleManifestSchema = modManifestSchema;
export type ModuleManifest = ModManifest;
