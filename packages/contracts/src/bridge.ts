import { z } from "zod";

import { wikiHandoffSchema, wikiPageContextSchema } from "./wiki";

const modIdSchema = z.string().regex(/^[a-z][a-z0-9-]{2,63}$/);
const actionIdSchema = z
  .string()
  .regex(/^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$/);
const requestIdSchema = z.string().min(1).max(128);
const instanceIdSchema = z.string().min(1).max(128);
const httpUrlSchema = z
  .string()
  .url()
  .refine((value) => {
    const protocol = new URL(value).protocol;
    return protocol === "http:" || protocol === "https:";
  });

export const bridgeProtocolVersionSchema = z.literal("1.0");

export const MAX_BRIDGE_VISUAL_CAPTURE_BYTES = 5 * 1024 * 1024;
export const MAX_BRIDGE_VISUAL_DATA_URL_CHARS = 7_100_000;

const pngDataUrlSchema = z
  .string()
  .min("data:image/png;base64,".length + 4)
  .max(MAX_BRIDGE_VISUAL_DATA_URL_CHARS)
  .refine((value) => {
    const prefix = "data:image/png;base64,";
    if (!value.startsWith(prefix)) return false;
    const payload = value.slice(prefix.length);
    return (
      payload.length % 4 === 0 &&
      /^[A-Za-z0-9+/]+={0,2}$/.test(payload)
    );
  }, "visual capture must be a base64 PNG data URL");

const cssVariableMapSchema = z
  .record(z.string().min(1).max(200))
  .superRefine((value, context) => {
    const entries = Object.entries(value);
    if (entries.length > 128) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "appearance.cssVars cannot contain more than 128 variables",
      });
    }
    for (const [name] of entries) {
      if (!/^--[a-z0-9-]{2,80}$/.test(name)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: `invalid CSS custom property name: ${name}`,
        });
      }
    }
  });

export const deskAppearanceSchema = z
  .object({
    contractVersion: z.literal("1.0"),
    mode: z.enum(["light", "dark"]),
    cssVars: cssVariableMapSchema,
    semantic: z
      .object({
        bg: z.string().min(1).max(80),
        surface: z.string().min(1).max(80),
        surfaceMuted: z.string().min(1).max(80),
        surfaceRaised: z.string().min(1).max(80),
        border: z.string().min(1).max(80),
        borderStrong: z.string().min(1).max(80),
        text: z.string().min(1).max(80),
        textSoft: z.string().min(1).max(80),
        textMuted: z.string().min(1).max(80),
        textFaint: z.string().min(1).max(80),
        accent: z.string().min(1).max(80),
        accentHover: z.string().min(1).max(80),
        accentSoft: z.string().min(1).max(80),
        accentSurface: z.string().min(1).max(80),
        accentContrast: z.string().min(1).max(80),
        positive: z.string().min(1).max(80),
        negative: z.string().min(1).max(80),
        warning: z.string().min(1).max(80),
        error: z.string().min(1).max(80),
        successText: z.string().min(1).max(80),
        successBg: z.string().min(1).max(80),
        successBorder: z.string().min(1).max(80),
        errorText: z.string().min(1).max(80),
        errorBg: z.string().min(1).max(80),
        errorBorder: z.string().min(1).max(80),
      })
      .strict(),
    charts: z
      .object({
        gridColor: z.string().min(1).max(80),
        textColor: z.string().min(1).max(80),
        axisColor: z.string().min(1).max(80),
        upColor: z.string().min(1).max(80),
        downColor: z.string().min(1).max(80),
        tooltipBg: z.string().min(1).max(80),
        tooltipBorder: z.string().min(1).max(80),
        tooltipText: z.string().min(1).max(80),
        series: z.array(z.string().min(1).max(80)).min(1).max(12),
      })
      .strict(),
  })
  .strict();

export const modHelloSchema = z
  .object({
    type: z.literal("vibedesk:hello"),
    modId: modIdSchema,
    protocolVersions: z.array(bridgeProtocolVersionSchema).min(1).max(5),
    sdkVersion: z.string().min(1).max(80).optional(),
    capabilities: z
      .array(
        z.enum([
          "events",
          "actions",
          "agent",
          "model",
          "data",
          "context",
          "storage",
          "theme",
          "handoff",
          "visual-context",
        ]),
      )
      .max(20)
      .default([]),
  })
  .strict();

export const deskInitSchema = z
  .object({
    type: z.literal("vibedesk:init"),
    protocolVersion: bridgeProtocolVersionSchema,
    instanceId: instanceIdSchema,
    modId: modIdSchema,
    user: z.object({ id: z.string().min(1).max(128) }).strict(),
    workspace: z.object({ id: z.string().min(1).max(128) }).strict(),
    environment: z
      .object({
        theme: z.enum(["light", "dark"]),
        locale: z.string().min(2).max(40),
        timezone: z.string().min(1).max(80),
      })
      .strict(),
    appearance: deskAppearanceSchema.optional(),
    gateways: z
      .object({
        actions: httpUrlSchema,
        agent: httpUrlSchema.optional(),
        model: httpUrlSchema.optional(),
        data: httpUrlSchema,
        storage: httpUrlSchema.optional(),
      })
      .strict(),
    runtime: z
      .union([
        z
          .object({
            owner: z.enum(["newma", "numa"]),
            aiExecution: z.literal("host"),
            requestMessage: z.literal("vibedesk:copilot-open"),
          })
          .strict(),
        z
          .object({
            owner: z.literal("desk"),
            aiExecution: z.literal("gateway"),
            requestMessage: z.literal("vibedesk:copilot-open"),
          })
          .strict(),
      ])
      .optional(),
    grants: z
      .object({
        permissions: z.array(z.string()).max(500),
        actions: z.array(z.string()).max(500),
      })
      .strict(),
    session: z
      .object({
        id: z.string().min(1).max(160),
        accessToken: z.string().min(1).max(16_384),
        expiresAt: z.string().datetime({ offset: true }),
      })
      .strict()
      .optional(),
  })
  .strict()
  .superRefine((value, context) => {
    if (value.appearance && value.appearance.mode !== value.environment.theme) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["appearance", "mode"],
        message: "appearance.mode must match environment.theme",
      });
    }
  });

export const modAckSchema = z
  .object({
    type: z.literal("vibedesk:ack"),
    protocolVersion: bridgeProtocolVersionSchema,
    instanceId: instanceIdSchema,
    modId: modIdSchema,
  })
  .strict();

export const modPageContextSchema = z
  .object({
    view: z
      .object({
        id: z.string().min(1).max(128),
        title: z.string().min(1).max(160),
      })
      .strict(),
    visibleBlocks: z
      .array(
        z
          .object({
            id: z.string().min(1).max(128),
            type: z.string().min(1).max(80),
            title: z.string().min(1).max(160).optional(),
          })
          .strict(),
      )
      .max(500)
      .default([]),
    selection: z.record(z.unknown()).default({}),
    filters: z.record(z.unknown()).default({}),
    data: z
      .object({
        asOf: z.string().min(1).max(80).optional(),
        source: z.string().min(1).max(160).optional(),
        freshness: z.enum(["live", "fresh", "stale", "unknown"]).optional(),
        summary: z.record(z.unknown()).optional(),
      })
      .strict()
      .default({}),
    actions: z
      .array(
        z
          .object({
            id: actionIdSchema,
            label: z.string().min(1).max(160).optional(),
            available: z.boolean().default(true),
            inputSchema: z.unknown().optional(),
          })
          .strict(),
      )
      .max(500)
      .default([]),
    tasks: z
      .array(
        z
          .object({
            id: z.string().min(1).max(160),
            status: z.string().min(1).max(80),
            actionId: actionIdSchema.optional(),
          })
          .strict(),
      )
      .max(200)
      .default([]),
    wiki: wikiPageContextSchema.optional(),
  })
  .strict();

export const deskContextRequestSchema = z
  .object({
    type: z.literal("vibedesk:context-request"),
    requestId: requestIdSchema,
    instanceId: instanceIdSchema,
    modId: modIdSchema,
    reason: z.enum(["initial", "agent", "refresh"]),
  })
  .strict();

export const modContextSchema = z
  .object({
    type: z.literal("vibedesk:context"),
    requestId: requestIdSchema,
    instanceId: instanceIdSchema,
    modId: modIdSchema,
    context: modPageContextSchema,
  })
  .strict();

export const deskVisualContextRequestSchema = z
  .object({
    type: z.literal("vibedesk:visual-context-request"),
    requestId: requestIdSchema,
    instanceId: instanceIdSchema,
    modId: modIdSchema,
    reason: z.enum(["agent", "refresh"]),
    maxBytes: z
      .number()
      .int()
      .min(64 * 1024)
      .max(MAX_BRIDGE_VISUAL_CAPTURE_BYTES),
    mediaTypes: z.tuple([z.literal("image/png")]),
  })
  .strict();

const modVisualContextBaseSchema = z.object({
  type: z.literal("vibedesk:visual-context"),
  requestId: requestIdSchema,
  instanceId: instanceIdSchema,
  modId: modIdSchema,
});

export const modVisualContextSchema = z.discriminatedUnion("ok", [
  modVisualContextBaseSchema
    .extend({
      ok: z.literal(true),
      capture: z
        .object({
          dataUrl: pngDataUrlSchema,
          width: z.number().int().min(1).max(8192),
          height: z.number().int().min(1).max(8192),
          capturedAt: z.string().datetime({ offset: true }),
          title: z.string().min(1).max(160).optional(),
        })
        .strict(),
    })
    .strict(),
  modVisualContextBaseSchema
    .extend({
      ok: z.literal(false),
      error: z
        .object({
          code: z.string().min(1).max(120),
          message: z.string().min(1).max(500),
        })
        .strict(),
    })
    .strict(),
]);

export const modActionRequestSchema = z
  .object({
    type: z.literal("vibedesk:action-request"),
    requestId: requestIdSchema,
    instanceId: instanceIdSchema,
    modId: modIdSchema,
    actionId: actionIdSchema,
    input: z.record(z.unknown()).default({}),
  })
  .strict();

export const modAgentRequestSchema = z
  .object({
    type: z.literal("vibedesk:copilot-open"),
    instanceId: instanceIdSchema,
    modId: modIdSchema,
    mode: z.enum(["ask", "edit"]).default("ask"),
    prompt: z.string().trim().min(1).max(8_000).optional(),
  })
  .strict();

const deskActionResultBaseSchema = z.object({
  type: z.literal("vibedesk:action-result"),
  requestId: requestIdSchema,
  instanceId: instanceIdSchema,
  modId: modIdSchema,
  actionId: actionIdSchema,
  status: z.number().int().min(100).max(599),
});

export const deskActionResultSchema = z.discriminatedUnion("ok", [
  deskActionResultBaseSchema
    .extend({ ok: z.literal(true), result: z.unknown() })
    .strict(),
  deskActionResultBaseSchema
    .extend({
      ok: z.literal(false),
      error: z
        .object({
          code: z.string().min(1).max(120),
          message: z.string().min(1).max(500),
        })
        .strict(),
    })
    .strict(),
]);

export const deskUiActionRequestSchema = z
  .object({
    type: z.literal("vibedesk:ui-action-request"),
    requestId: requestIdSchema,
    instanceId: instanceIdSchema,
    modId: modIdSchema,
    actionId: actionIdSchema,
    input: z.record(z.unknown()).default({}),
  })
  .strict();

const modUiActionResultBaseSchema = z.object({
  type: z.literal("vibedesk:ui-action-result"),
  requestId: requestIdSchema,
  instanceId: instanceIdSchema,
  modId: modIdSchema,
  actionId: actionIdSchema,
});

export const modUiActionResultSchema = z.discriminatedUnion("ok", [
  modUiActionResultBaseSchema
    .extend({ ok: z.literal(true), result: z.unknown() })
    .strict(),
  modUiActionResultBaseSchema
    .extend({
      ok: z.literal(false),
      error: z
        .object({
          code: z.string().min(1).max(120),
          message: z.string().min(1).max(500),
        })
        .strict(),
    })
    .strict(),
]);

export const deskHandoffSchema = z
  .object({
    type: z.literal("vibedesk:handoff"),
    requestId: requestIdSchema,
    instanceId: instanceIdSchema,
    modId: modIdSchema,
    handoff: wikiHandoffSchema,
  })
  .strict()
  .superRefine((message, context) => {
    if (message.handoff.targetModId !== message.modId) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["handoff", "targetModId"],
        message: "Wiki handoff target must match the receiving Mod",
      });
    }
  });

const modHandoffResultBaseSchema = z.object({
  type: z.literal("vibedesk:handoff-result"),
  requestId: requestIdSchema,
  instanceId: instanceIdSchema,
  modId: modIdSchema,
  handoffId: z.string().regex(/^hf_[A-Za-z0-9_-]{8,120}$/),
});

export const modHandoffResultSchema = z.discriminatedUnion("ok", [
  modHandoffResultBaseSchema
    .extend({ ok: z.literal(true), result: z.unknown() })
    .strict(),
  modHandoffResultBaseSchema
    .extend({
      ok: z.literal(false),
      error: z
        .object({
          code: z.string().min(1).max(120),
          message: z.string().min(1).max(500),
        })
        .strict(),
    })
    .strict(),
]);

export type ModHello = z.infer<typeof modHelloSchema>;
export type DeskAppearance = z.infer<typeof deskAppearanceSchema>;
export type DeskInit = z.infer<typeof deskInitSchema>;
export type ModAck = z.infer<typeof modAckSchema>;
export type ModPageContext = z.infer<typeof modPageContextSchema>;
export type DeskContextRequest = z.infer<typeof deskContextRequestSchema>;
export type ModContext = z.infer<typeof modContextSchema>;
export type DeskVisualContextRequest = z.infer<
  typeof deskVisualContextRequestSchema
>;
export type ModVisualContext = z.infer<typeof modVisualContextSchema>;
export type ModVisualCapturePayload = Extract<
  ModVisualContext,
  { ok: true }
>["capture"];
export type ModActionRequest = z.infer<typeof modActionRequestSchema>;
export type ModAgentRequest = z.infer<typeof modAgentRequestSchema>;
export type DeskActionResult = z.infer<typeof deskActionResultSchema>;
export type DeskUiActionRequest = z.infer<typeof deskUiActionRequestSchema>;
export type ModUiActionResult = z.infer<typeof modUiActionResultSchema>;
export type DeskHandoff = z.infer<typeof deskHandoffSchema>;
export type ModHandoffResult = z.infer<typeof modHandoffResultSchema>;
