import postgres from 'postgres'
import { hasValidSalesRuleSourceIdentityEvidence } from '@/lib/sales-rule-source-evidence'

export type SalesRule = {
  windCode: string
  platform: string
  purchaseStatus: 'open' | 'closed' | 'limited' | 'unknown'
  purchaseStatusLabel: string
  purchaseStatusSourceBacked?: boolean
  minPurchaseAmount: number | null
  minPurchaseSourceBacked?: boolean
  minSipAmount: number | null
  minSipSourceBacked?: boolean
  dailyLimitAmount: number | null
  dailyLimitSourceBacked?: boolean
  purchaseFeeRate: number | null
  purchaseFeeSourceBacked?: boolean
  redemptionFeeRules: Array<{ holdingDays: number | null; feeRate: number; label: string }>
  redemptionFeeSourceUrl?: string | null
  redemptionFeeSourceUpdatedAt?: string | null
  redemptionFeePlatform?: string | null
  redemptionFeeNotes?: string | null
  salesServiceFeeRate: number | null
  salesServiceFeeSourceBacked?: boolean
  riskLevel: string | null
  supportsSip: boolean | null
  supportsSipSourceBacked?: boolean
  sourceUrl: string | null
  sourceUpdatedAt: string | null
  notes: string | null
  updatedAt: string | null
}

export type SalesRuleInput = Partial<Omit<SalesRule, 'updatedAt' | 'redemptionFeeRules'>> & {
  redemptionFeeRules?: SalesRule['redemptionFeeRules']
}

let sqlClient: postgres.Sql | null = null
let tableReady: Promise<void> | null = null

function sql() {
  if (!sqlClient) {
    const databaseUrl = process.env.DATABASE_URL
    if (!databaseUrl) throw new Error('DATABASE_URL 未配置，无法读取销售规则')
    sqlClient = postgres(databaseUrl, {
      max: 3,
      idle_timeout: 20,
      connect_timeout: 10,
    })
  }
  return sqlClient
}

async function ensureSalesRulesTable() {
  if (!tableReady) {
    tableReady = sql()`CREATE TABLE IF NOT EXISTS fund_sales_rules (
      wind_code text NOT NULL,
      platform text NOT NULL DEFAULT 'manual',
      purchase_status text NOT NULL DEFAULT 'unknown',
      purchase_status_label text NOT NULL DEFAULT '申购待核',
      min_purchase_amount numeric,
      min_sip_amount numeric,
      daily_limit_amount numeric,
      purchase_fee_rate numeric,
      redemption_fee_rules jsonb NOT NULL DEFAULT '[]'::jsonb,
      sales_service_fee_rate numeric,
      risk_level text,
      supports_sip boolean,
      source_url text,
      source_updated_at date,
      notes text,
      created_at timestamp without time zone NOT NULL DEFAULT now(),
      updated_at timestamp without time zone NOT NULL DEFAULT now(),
      PRIMARY KEY (wind_code, platform)
    )`.then(async () => {
      await sql()`CREATE INDEX IF NOT EXISTS fund_sales_rules_wind_code_idx ON fund_sales_rules (wind_code)`
    }).then(() => undefined)
  }
  return tableReady
}

function numberOrNull(value: unknown) {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function boolOrNull(value: unknown) {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'boolean') return value
  if (value === 'true') return true
  if (value === 'false') return false
  return null
}

function normalizeRedemptionRules(value: unknown): SalesRule['redemptionFeeRules'] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      const row = item as Record<string, unknown>
      const feeRate = numberOrNull(row.feeRate ?? row.fee_rate)
      if (feeRate === null) return null
      return {
        holdingDays: numberOrNull(row.holdingDays ?? row.holding_days),
        feeRate,
        label: String(row.label || '赎回费率'),
      }
    })
    .filter((item): item is SalesRule['redemptionFeeRules'][number] => item !== null)
}

function isFreshSalesRuleSourceDate(value: string | null) {
  if (!value) return false
  const sourceDate = new Date(`${value.slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(sourceDate.getTime())) return false
  const currentDate = new Date()
  currentDate.setUTCHours(0, 0, 0, 0)
  const ageDays = Math.floor((currentDate.getTime() - sourceDate.getTime()) / 86_400_000)
  return ageDays >= 0 && ageDays <= 30
}

function hasSalesRuleSourceEvidence(row: Record<string, unknown>, sourceUpdatedAt: string | null) {
  if (!isFreshSalesRuleSourceDate(sourceUpdatedAt)) return false
  const platform = String(row.platform || '').trim()
  const sourceUrl = String(row.source_url || '').trim()
  const notes = String(row.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function mapRow(row: Record<string, unknown>): SalesRule {
  const sourceUpdatedAt = row.source_updated_at instanceof Date
    ? row.source_updated_at.toISOString().slice(0, 10)
    : row.source_updated_at ? String(row.source_updated_at).slice(0, 10) : null
  const updatedAt = row.updated_at instanceof Date
    ? row.updated_at.toISOString()
    : row.updated_at ? new Date(String(row.updated_at)).toISOString() : null
  const redemptionFeeRules = normalizeRedemptionRules(row.redemption_fee_rules)
  const sourceBacked = hasSalesRuleSourceEvidence(row, sourceUpdatedAt)
  const purchaseStatus = ['open', 'closed', 'limited', 'unknown'].includes(String(row.purchase_status)) ? String(row.purchase_status) as SalesRule['purchaseStatus'] : 'unknown'
  const minPurchaseAmount = numberOrNull(row.min_purchase_amount)
  const minSipAmount = numberOrNull(row.min_sip_amount)
  const dailyLimitAmount = numberOrNull(row.daily_limit_amount)
  const purchaseFeeRate = numberOrNull(row.purchase_fee_rate)
  const salesServiceFeeRate = numberOrNull(row.sales_service_fee_rate)
  const supportsSip = boolOrNull(row.supports_sip)

  return {
    windCode: String(row.wind_code || ''),
    platform: String(row.platform || 'manual'),
    purchaseStatus,
    purchaseStatusLabel: String(row.purchase_status_label || '申购待核'),
    purchaseStatusSourceBacked: purchaseStatus !== 'unknown' && sourceBacked,
    minPurchaseAmount,
    minPurchaseSourceBacked: minPurchaseAmount !== null && sourceBacked,
    minSipAmount,
    minSipSourceBacked: minSipAmount !== null && sourceBacked,
    dailyLimitAmount,
    dailyLimitSourceBacked: dailyLimitAmount !== null && sourceBacked,
    purchaseFeeRate,
    purchaseFeeSourceBacked: purchaseFeeRate !== null && sourceBacked,
    redemptionFeeRules,
    redemptionFeeSourceUrl: redemptionFeeRules.length ? (row.source_url == null ? null : String(row.source_url)) : null,
    redemptionFeeSourceUpdatedAt: redemptionFeeRules.length ? sourceUpdatedAt : null,
    redemptionFeePlatform: redemptionFeeRules.length ? String(row.platform || 'manual') : null,
    redemptionFeeNotes: redemptionFeeRules.length ? (row.notes == null ? null : String(row.notes)) : null,
    salesServiceFeeRate,
    salesServiceFeeSourceBacked: salesServiceFeeRate !== null && sourceBacked,
    riskLevel: row.risk_level == null ? null : String(row.risk_level),
    supportsSip,
    supportsSipSourceBacked: supportsSip !== null && sourceBacked,
    sourceUrl: row.source_url == null ? null : String(row.source_url),
    sourceUpdatedAt,
    notes: row.notes == null ? null : String(row.notes),
    updatedAt,
  }
}

export async function getSalesRule(windCode: string, platform = 'manual') {
  await ensureSalesRulesTable()
  const rows = await sql()`
    SELECT *
    FROM fund_sales_rules
    WHERE wind_code = ${windCode} AND platform = ${platform}
    LIMIT 1
  `
  return rows[0] ? mapRow(rows[0]) : null
}

export async function getSalesRulesByWindCodes(windCodes: string[], platform = 'manual') {
  const uniqueCodes = Array.from(new Set(windCodes.filter(Boolean)))
  if (uniqueCodes.length === 0) return new Map<string, SalesRule>()
  await ensureSalesRulesTable()
  const rows = await sql()`
    SELECT *
    FROM fund_sales_rules
    WHERE platform = ${platform} AND wind_code IN ${sql()(uniqueCodes)}
  `
  return new Map(rows.map((row) => [row.wind_code, mapRow(row)]))
}

function sourceRank(rule: SalesRule) {
  if (rule.platform === 'manual') return 0
  if (rule.platform.includes('sales')) return 1
  if (rule.platform.includes('tushare')) return 2
  return 3
}

function pickFirst<T>(rules: SalesRule[], picker: (rule: SalesRule) => T | null | undefined) {
  for (const rule of rules) {
    const value = picker(rule)
    if (value !== null && value !== undefined && value !== '') return value
  }
  return null
}

function pickRule(rules: SalesRule[], predicate: (rule: SalesRule) => boolean) {
  return rules.find(predicate) || null
}

function pickSourceBackedRule(
  rules: SalesRule[],
  valuePredicate: (rule: SalesRule) => boolean,
  sourcePredicate: (rule: SalesRule) => boolean | undefined,
) {
  return pickRule(rules, (rule) => valuePredicate(rule) && Boolean(sourcePredicate(rule)))
    || pickRule(rules, valuePredicate)
}

function hasValidRiskLevel(rule: SalesRule) {
  return typeof rule.riskLevel === 'string' && /^R[1-5]$/i.test(rule.riskLevel.trim())
}

function isTushareRiskSource(rule: SalesRule) {
  return rule.platform.toLowerCase().includes('tushare')
    || String(rule.sourceUrl || '').toLowerCase().includes('tushare.fund_basic')
}

function hasRiskLevelSourceEvidenceOnSameRule(rule: SalesRule) {
  if (!hasValidRiskLevel(rule)) return false
  if (isTushareRiskSource(rule)) return false
  return Boolean(rule.sourceUpdatedAt && hasValidSalesRuleSourceIdentityEvidence({
    platform: rule.platform,
    sourceUrl: rule.sourceUrl,
    notes: rule.notes,
  }))
}

function hasSourceBackedRedemptionFeeRule(rule: SalesRule) {
  if (!rule.redemptionFeeRules.length) return false
  const sourceUpdatedAt = rule.redemptionFeeSourceUpdatedAt || rule.sourceUpdatedAt
  if (!isFreshSalesRuleSourceDate(sourceUpdatedAt || null)) return false
  return hasValidSalesRuleSourceIdentityEvidence({
    platform: rule.redemptionFeePlatform || rule.platform,
    sourceUrl: rule.redemptionFeeSourceUrl || rule.sourceUrl,
    notes: rule.redemptionFeeNotes || rule.notes,
  })
}

function mergeSalesRules(windCode: string, rules: SalesRule[]) {
  if (rules.length === 0) return null
  const orderedRules = [...rules].sort((left, right) => sourceRank(left) - sourceRank(right))
  const statusRule = pickSourceBackedRule(
    orderedRules,
    (rule) => rule.purchaseStatus !== 'unknown',
    (rule) => rule.purchaseStatusSourceBacked,
  )
  const minPurchaseRule = pickSourceBackedRule(
    orderedRules,
    (rule) => rule.minPurchaseAmount !== null,
    (rule) => rule.minPurchaseSourceBacked,
  )
  const minSipRule = pickSourceBackedRule(
    orderedRules,
    (rule) => rule.minSipAmount !== null,
    (rule) => rule.minSipSourceBacked,
  )
  const dailyLimitRule = pickSourceBackedRule(
    orderedRules,
    (rule) => rule.dailyLimitAmount !== null,
    (rule) => rule.dailyLimitSourceBacked,
  )
  const purchaseFeeRule = pickSourceBackedRule(
    orderedRules,
    (rule) => rule.purchaseFeeRate !== null,
    (rule) => rule.purchaseFeeSourceBacked,
  )
  const salesServiceFeeRule = pickSourceBackedRule(
    orderedRules,
    (rule) => rule.salesServiceFeeRate !== null,
    (rule) => rule.salesServiceFeeSourceBacked,
  )
  const supportsSipRule = pickSourceBackedRule(
    orderedRules,
    (rule) => rule.supportsSip !== null,
    (rule) => rule.supportsSipSourceBacked,
  )
  const redemptionFeeRule = pickSourceBackedRule(
    orderedRules,
    (rule) => rule.redemptionFeeRules.length > 0,
    hasSourceBackedRedemptionFeeRule,
  )
  const riskLevelRule = orderedRules.find(hasRiskLevelSourceEvidenceOnSameRule)
    || orderedRules.find((rule) => hasValidRiskLevel(rule) && !isTushareRiskSource(rule))
    || orderedRules.find(hasValidRiskLevel)
  const sourceDates = orderedRules
    .map((rule) => rule.sourceUpdatedAt)
    .filter((value): value is string => Boolean(value))
    .sort((left, right) => right.localeCompare(left))
  const mergedNotes = riskLevelRule?.riskLevel
    ? riskLevelRule.notes || null
    : orderedRules
      .map((rule) => rule.notes ? `[${rule.platform}] ${rule.notes}` : '')
      .filter(Boolean)
      .join('\n') || null

  return {
    windCode,
    platform: Array.from(new Set(orderedRules.map((rule) => rule.platform))).join('+'),
    purchaseStatus: statusRule?.purchaseStatus || 'unknown',
    purchaseStatusLabel: statusRule?.purchaseStatusLabel || '申购待核',
    purchaseStatusSourceBacked: Boolean(statusRule?.purchaseStatusSourceBacked),
    minPurchaseAmount: minPurchaseRule?.minPurchaseAmount ?? null,
    minPurchaseSourceBacked: Boolean(minPurchaseRule?.minPurchaseSourceBacked),
    minSipAmount: minSipRule?.minSipAmount ?? null,
    minSipSourceBacked: Boolean(minSipRule?.minSipSourceBacked),
    dailyLimitAmount: dailyLimitRule?.dailyLimitAmount ?? null,
    dailyLimitSourceBacked: Boolean(dailyLimitRule?.dailyLimitSourceBacked),
    purchaseFeeRate: purchaseFeeRule?.purchaseFeeRate ?? null,
    purchaseFeeSourceBacked: Boolean(purchaseFeeRule?.purchaseFeeSourceBacked),
    redemptionFeeRules: redemptionFeeRule?.redemptionFeeRules || [],
    redemptionFeeSourceUrl: redemptionFeeRule?.sourceUrl || null,
    redemptionFeeSourceUpdatedAt: redemptionFeeRule?.sourceUpdatedAt || null,
    redemptionFeePlatform: redemptionFeeRule?.platform || null,
    redemptionFeeNotes: redemptionFeeRule?.notes || null,
    salesServiceFeeRate: salesServiceFeeRule?.salesServiceFeeRate ?? null,
    salesServiceFeeSourceBacked: Boolean(salesServiceFeeRule?.salesServiceFeeSourceBacked),
    riskLevel: riskLevelRule?.riskLevel || null,
    supportsSip: supportsSipRule?.supportsSip ?? null,
    supportsSipSourceBacked: Boolean(supportsSipRule?.supportsSipSourceBacked),
    sourceUrl: riskLevelRule?.riskLevel ? riskLevelRule.sourceUrl : pickFirst(orderedRules, (rule) => rule.sourceUrl),
    sourceUpdatedAt: riskLevelRule?.riskLevel ? riskLevelRule.sourceUpdatedAt : sourceDates[0] || null,
    notes: mergedNotes,
    updatedAt: orderedRules
      .map((rule) => rule.updatedAt)
      .filter((value): value is string => Boolean(value))
      .sort((left, right) => right.localeCompare(left))[0] || null,
  } satisfies SalesRule
}

export async function getMergedSalesRulesByWindCodes(windCodes: string[]) {
  const uniqueCodes = Array.from(new Set(windCodes.filter(Boolean)))
  if (uniqueCodes.length === 0) return new Map<string, SalesRule>()
  await ensureSalesRulesTable()
  const rows = await sql()`
    SELECT *
    FROM fund_sales_rules
    WHERE wind_code IN ${sql()(uniqueCodes)}
    ORDER BY wind_code ASC, platform ASC, updated_at DESC
  `
  const grouped = rows.reduce((accumulator: Map<string, SalesRule[]>, row) => {
    const windCode = String(row.wind_code || '')
    if (!accumulator.has(windCode)) accumulator.set(windCode, [])
    accumulator.get(windCode)?.push(mapRow(row))
    return accumulator
  }, new Map<string, SalesRule[]>())

  const merged = new Map<string, SalesRule>()
  for (const windCode of uniqueCodes) {
    const rule = mergeSalesRules(windCode, grouped.get(windCode) || [])
    if (rule) merged.set(windCode, rule)
  }
  return merged
}

export async function getMergedSalesRule(windCode: string) {
  const rules = await getMergedSalesRulesByWindCodes([windCode])
  return rules.get(windCode) || null
}

export async function upsertSalesRule(windCode: string, input: SalesRuleInput, platform = input.platform || 'manual') {
  await ensureSalesRulesTable()
  const purchaseStatus = input.purchaseStatus || 'unknown'
  const purchaseStatusLabel = input.purchaseStatusLabel || '申购待核'
  const redemptionFeeRules = normalizeRedemptionRules(input.redemptionFeeRules)
  const rows = await sql()`
    INSERT INTO fund_sales_rules (
      wind_code, platform, purchase_status, purchase_status_label,
      min_purchase_amount, min_sip_amount, daily_limit_amount,
      purchase_fee_rate, redemption_fee_rules, sales_service_fee_rate,
      risk_level, supports_sip, source_url, source_updated_at, notes, updated_at
    ) VALUES (
      ${windCode}, ${platform}, ${purchaseStatus}, ${purchaseStatusLabel},
      ${numberOrNull(input.minPurchaseAmount)}, ${numberOrNull(input.minSipAmount)}, ${numberOrNull(input.dailyLimitAmount)},
      ${numberOrNull(input.purchaseFeeRate)}, ${sql().json(redemptionFeeRules)}, ${numberOrNull(input.salesServiceFeeRate)},
      ${input.riskLevel || null}, ${boolOrNull(input.supportsSip)}, ${input.sourceUrl || null}, ${input.sourceUpdatedAt || null}, ${input.notes || null}, now()
    )
    ON CONFLICT (wind_code, platform) DO UPDATE SET
      purchase_status = CASE
        WHEN EXCLUDED.purchase_status = 'unknown' THEN fund_sales_rules.purchase_status
        ELSE EXCLUDED.purchase_status
      END,
      purchase_status_label = CASE
        WHEN EXCLUDED.purchase_status = 'unknown' THEN fund_sales_rules.purchase_status_label
        ELSE EXCLUDED.purchase_status_label
      END,
      min_purchase_amount = COALESCE(EXCLUDED.min_purchase_amount, fund_sales_rules.min_purchase_amount),
      min_sip_amount = COALESCE(EXCLUDED.min_sip_amount, fund_sales_rules.min_sip_amount),
      daily_limit_amount = COALESCE(EXCLUDED.daily_limit_amount, fund_sales_rules.daily_limit_amount),
      purchase_fee_rate = COALESCE(EXCLUDED.purchase_fee_rate, fund_sales_rules.purchase_fee_rate),
      redemption_fee_rules = CASE
        WHEN jsonb_array_length(EXCLUDED.redemption_fee_rules) = 0 THEN fund_sales_rules.redemption_fee_rules
        ELSE EXCLUDED.redemption_fee_rules
      END,
      sales_service_fee_rate = COALESCE(EXCLUDED.sales_service_fee_rate, fund_sales_rules.sales_service_fee_rate),
      risk_level = COALESCE(EXCLUDED.risk_level, fund_sales_rules.risk_level),
      supports_sip = COALESCE(EXCLUDED.supports_sip, fund_sales_rules.supports_sip),
      source_url = COALESCE(EXCLUDED.source_url, fund_sales_rules.source_url),
      source_updated_at = COALESCE(EXCLUDED.source_updated_at, fund_sales_rules.source_updated_at),
      notes = concat_ws(E'\n', fund_sales_rules.notes, EXCLUDED.notes),
      updated_at = now()
    RETURNING *
  `
  return mapRow(rows[0])
}

export async function listSalesRules(limit = 100, platform?: string) {
  await ensureSalesRulesTable()
  const safeLimit = Math.max(1, Math.min(Number(limit) || 100, 500))
  const rows = platform
    ? await sql()`
        SELECT *
        FROM fund_sales_rules
        WHERE platform = ${platform}
        ORDER BY updated_at DESC
        LIMIT ${safeLimit}
      `
    : await sql()`
        SELECT *
        FROM fund_sales_rules
        ORDER BY updated_at DESC
        LIMIT ${safeLimit}
      `
  return rows.map(mapRow)
}

export async function countSalesRules(platform?: string) {
  await ensureSalesRulesTable()
  const rows = platform
    ? await sql()`SELECT COUNT(*)::int AS count FROM fund_sales_rules WHERE platform = ${platform}`
    : await sql()`SELECT COUNT(*)::int AS count FROM fund_sales_rules`
  return Number(rows[0]?.count || 0)
}
