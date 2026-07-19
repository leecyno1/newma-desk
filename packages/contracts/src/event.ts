import { z } from "zod";

export const moduleEventNameSchema = z
  .string()
  .regex(/^[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*$/);

export const moduleEventSchema = z.object({
  version: z.literal("1.0"),
  event: moduleEventNameSchema,
  source: z.string().min(1),
  target: z.string().min(1).optional(),
  traceId: z.string().min(1),
  payload: z.record(z.unknown()),
}).strict();

export type ModuleEvent = z.infer<typeof moduleEventSchema>;
