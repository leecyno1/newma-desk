import { z } from "zod";

export const modEventNameSchema = z
  .string()
  .regex(/^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$/);

export const modEventSchema = z.object({
  version: z.literal("1.0"),
  event: modEventNameSchema,
  source: z.string().min(1),
  target: z.string().min(1).optional(),
  traceId: z.string().min(1),
  payload: z.record(z.unknown()),
}).strict();

export type ModEvent = z.infer<typeof modEventSchema>;

// Compatibility aliases for integrations that still use the former name.
export const moduleEventNameSchema = modEventNameSchema;
export const moduleEventSchema = modEventSchema;
export type ModuleEvent = ModEvent;
