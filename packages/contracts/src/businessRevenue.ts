import { z } from 'zod';

export const businessRevenueRowSchema = z.object({
  label: z.string().min(1).max(160), value: z.number().finite(),
  rawValue: z.string().min(1).max(80), rawUnit: z.enum(['元', '万元', '亿元']),
  excerpt: z.string().min(1).max(2000),
}).strict();

export const businessRevenueSchema = z.object({
  reportId: z.string().min(1), dimension: z.enum(['industry', 'product', 'region', 'channel']),
  title: z.string().min(1).max(160), scope: z.literal('main-business'),
  currency: z.literal('CNY'), unit: z.literal('亿元'),
  pdfPage: z.number().int().positive(), pdfPageCount: z.number().int().positive(),
  columnHeader: z.string().min(1).max(2000),
  rows: z.array(businessRevenueRowSchema).min(1).max(40),
  total: businessRevenueRowSchema.nullable(), skippedRows: z.number().int().min(0),
  confirmedAt: z.string().datetime(), contentOrigin: z.literal('pdf-text'),
}).strict().refine(value => value.pdfPage <= value.pdfPageCount && new Set(value.rows.map(row => row.label)).size === value.rows.length,
  '收入结构须保留物理页与不重复的项目');

export type BusinessRevenue = z.infer<typeof businessRevenueSchema>;

/** All ratios refer only to this one table, never to consolidated revenue. */
export function summarizeBusinessRevenue(group: BusinessRevenue) {
  const sum = group.rows.reduce((total, row) => total + row.value, 0);
  const denominator = group.total?.value ?? sum;
  const reason = group.rows.some(row => row.value < 0) ? '含负收入，不计算结构占比'
    : denominator <= 0 ? '分母非正数，不计算结构占比'
    : group.total && sum > denominator + Math.max(1e-8, Math.abs(denominator) * 1e-8) ? '项目合计超过原表合计，须核对口径'
    : !group.total && group.skippedRows > 0 ? '存在未识别行且无原表合计，不计算占比' : null;
  return {sum, denominator, denominatorLabel: group.total ? '原表合计' : '已采用项目合计（非公司总收入）', reason,
    rows: group.rows.map(row => ({...row, sharePct: reason ? null : row.value / denominator * 100}))};
}
