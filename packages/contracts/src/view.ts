import { z } from "zod";

const identifierSchema = z.string().min(1);
const dataPathSchema = z.string().min(1);
const valueFormatSchema = z.enum(["number", "percent", "currency", "text"]);

export const metricItemSchema = z
  .object({
    label: z.string().min(1),
    valuePath: dataPathSchema,
    format: valueFormatSchema.optional(),
  })
  .strict();

export const metricsBlockSchema = z
  .object({
    id: identifierSchema,
    type: z.literal("metrics"),
    title: z.string().min(1).optional(),
    items: z.array(metricItemSchema),
  })
  .strict();

export const tableColumnSchema = z
  .object({
    key: z.string().min(1),
    label: z.string().min(1),
    format: valueFormatSchema.optional(),
    sortable: z.boolean().optional(),
  })
  .strict();

export const tableBlockSchema = z
  .object({
    id: identifierSchema,
    type: z.literal("table"),
    title: z.string().min(1).optional(),
    rowsPath: dataPathSchema,
    columns: z.array(tableColumnSchema).max(50),
    emptyText: z.string().optional(),
  })
  .strict();

export const chartBlockSchema = z
  .object({
    id: identifierSchema,
    type: z.literal("chart"),
    title: z.string().min(1).optional(),
    optionPath: dataPathSchema,
    height: z.number().positive().optional(),
  })
  .strict();

export const markdownBlockSchema = z
  .object({
    id: identifierSchema,
    type: z.literal("markdown"),
    title: z.string().min(1).optional(),
    contentPath: dataPathSchema,
  })
  .strict();

export const filterOptionSchema = z
  .object({
    label: z.string().min(1),
    value: z.string(),
  })
  .strict();

const plainFilterFieldSchema = z
  .object({
    key: z.string().min(1),
    label: z.string().min(1),
    input: z.enum(["text", "date"]),
  })
  .strict();

const selectFilterFieldSchema = z
  .object({
    key: z.string().min(1),
    label: z.string().min(1),
    input: z.literal("select"),
    options: z.array(filterOptionSchema).max(500).optional(),
  })
  .strict();

export const filterFieldSchema = z.union([
  plainFilterFieldSchema,
  selectFilterFieldSchema,
]);

export const filtersBlockSchema = z
  .object({
    id: identifierSchema,
    type: z.literal("filters"),
    fields: z.array(filterFieldSchema),
  })
  .strict();

export const actionItemSchema = z
  .object({
    id: identifierSchema,
    label: z.string().min(1),
    capability: z.string().min(1),
    confirmation: z.string().min(1).optional(),
  })
  .strict();

export const actionsBlockSchema = z
  .object({
    id: identifierSchema,
    type: z.literal("actions"),
    items: z.array(actionItemSchema),
  })
  .strict();

export const viewBlockSchema = z.discriminatedUnion("type", [
  metricsBlockSchema,
  tableBlockSchema,
  chartBlockSchema,
  markdownBlockSchema,
  filtersBlockSchema,
  actionsBlockSchema,
]);

export const viewSchema = z
  .object({
    version: z.literal("1.0"),
    title: z.string().min(1),
    blocks: z.array(viewBlockSchema).max(100),
  })
  .strict();

export type MetricItem = z.infer<typeof metricItemSchema>;
export type MetricsBlock = z.infer<typeof metricsBlockSchema>;
export type TableColumn = z.infer<typeof tableColumnSchema>;
export type TableBlock = z.infer<typeof tableBlockSchema>;
export type ChartBlock = z.infer<typeof chartBlockSchema>;
export type MarkdownBlock = z.infer<typeof markdownBlockSchema>;
export type FilterOption = z.infer<typeof filterOptionSchema>;
export type FilterField = z.infer<typeof filterFieldSchema>;
export type FiltersBlock = z.infer<typeof filtersBlockSchema>;
export type ActionItem = z.infer<typeof actionItemSchema>;
export type ActionsBlock = z.infer<typeof actionsBlockSchema>;
export type ViewBlock = z.infer<typeof viewBlockSchema>;
export type View = z.infer<typeof viewSchema>;
