import { z } from "zod";

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
          "theme",
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
    gateways: z
      .object({
        actions: httpUrlSchema,
        agent: httpUrlSchema,
        model: httpUrlSchema,
        data: httpUrlSchema,
      })
      .strict(),
    grants: z
      .object({
        permissions: z.array(z.string()).max(500),
        actions: z.array(z.string()).max(500),
      })
      .strict(),
    session: z
      .object({
        id: z.string().min(1).max(160),
        expiresAt: z.string().datetime({ offset: true }),
      })
      .strict()
      .optional(),
  })
  .strict();

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

export type ModHello = z.infer<typeof modHelloSchema>;
export type DeskInit = z.infer<typeof deskInitSchema>;
export type ModAck = z.infer<typeof modAckSchema>;
export type ModPageContext = z.infer<typeof modPageContextSchema>;
export type DeskContextRequest = z.infer<typeof deskContextRequestSchema>;
export type ModContext = z.infer<typeof modContextSchema>;
export type ModActionRequest = z.infer<typeof modActionRequestSchema>;
export type DeskActionResult = z.infer<typeof deskActionResultSchema>;
export type DeskUiActionRequest = z.infer<typeof deskUiActionRequestSchema>;
export type ModUiActionResult = z.infer<typeof modUiActionResultSchema>;
