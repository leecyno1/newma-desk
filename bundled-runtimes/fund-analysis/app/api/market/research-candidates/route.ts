import { NextResponse } from 'next/server'
import { backendApiBaseUrl, toCamelFund } from '@/lib/backend-api'
import { researchEvidenceTool, type ResearchEvidenceToolOutput } from '@/lib/research-platform/tools'
import { getSalesRuleGapsForCodes, type SalesRuleExecutionAmountGate } from '@/lib/sales-rule-gaps'
import { getSalesRuleImpact } from '@/lib/sales-rule-impact'
import { getMergedSalesRulesByWindCodes } from '@/lib/sales-rules'
import { fetchActiveSalesRuleEvidenceAlertsForCodes, type ActiveSalesRuleEvidenceAlert } from '@/lib/sales-rule-review-alerts'
import { salesRuleEvidenceCopyForPlan, salesRuleFoundationManualFieldsForPlan } from '@/lib/sales-rule-purchase-plan-copy'
import { hasValidSalesRuleSourceIdentityEvidence } from '@/lib/sales-rule-source-evidence'
import { materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type RiskProfile = 'conservative' | 'balanced' | 'aggressive'
type SelectionLens = 'score' | 'stable' | 'return' | 'evidence' | 'peer' | 'experience' | 'manager' | 'cost'
type InvestmentHorizon = 'lt1y' | '1to3y' | 'gt3y'
type PurchasePlan = 'lump_sum' | 'sip'
type EvidenceGrade = 'A' | 'B' | 'C' | 'D'
type CandidateSelectionUniverse = {
  key: string
  sortBy: string
  sortOrder: 'asc' | 'desc'
  strictSalesRule?: boolean
}

type InvestorPreferences = {
  horizon: InvestmentHorizon
  horizonLabel: string
  purchasePlan: PurchasePlan
  purchasePlanLabel: string
  plannedAmount: number
  maxDrawdownTolerance: number | null
}

type RedemptionFeeRule = {
  holdingDays?: number | null
  feeRate?: number | null
  label?: string
}

type NormalizedRedemptionRule = {
  holdingDays: number | null
  feeRate: number
  label: string
}

type HoldingExposureEvidence = {
  status: 'available' | 'unavailable'
  windCode?: string
  quarter?: string
  holdings?: Array<{
    stockCode?: string
    stockName?: string
    industry?: string
    weight?: number | null
  }>
  industryBuckets?: Array<{ industry: string; weight: number }>
  totalWeight?: number | null
  checkedQuarters?: string[]
  rejectedMockLikeQuarters?: string[]
  source?: string
  note?: string
}

const typeFit: Record<RiskProfile, Record<string, number>> = {
  conservative: { 债券型: 18, 货币型: 18, 混合型: 10, 指数型: 8, 股票型: 4, QDII: 4 },
  balanced: { 混合型: 18, 指数型: 15, 债券型: 12, 股票型: 10, QDII: 8, 货币型: 6 },
  aggressive: { 股票型: 18, 指数型: 16, QDII: 14, 混合型: 12, 债券型: 6, 货币型: 2 },
}

const profileLabel: Record<RiskProfile, string> = {
  conservative: '稳健型',
  balanced: '均衡型',
  aggressive: '进取型',
}

const horizonLabel: Record<InvestmentHorizon, string> = {
  lt1y: '1年以内',
  '1to3y': '1-3年',
  gt3y: '3年以上',
}

const purchasePlanLabel: Record<PurchasePlan, string> = {
  lump_sum: '一次性配置',
  sip: '每月定投',
}

const BACKEND_PAGE_SIZE = 100
const MAX_SOURCE_LIMIT = 500
const EVIDENCE_FRESH_DAYS = 30
const DEFAULT_PLANNED_AMOUNT = 10000
const MIN_PLANNED_AMOUNT = 1
const MAX_PLANNED_AMOUNT = 1_000_000

const profileMaxRiskLevel: Record<RiskProfile, number> = {
  conservative: 2,
  balanced: 3,
  aggressive: 5,
}

function clamp(value: number, min = 0, max = 100) {
  return Math.max(min, Math.min(max, value))
}

function uniqueText(items: string[]) {
  return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)))
}

function marketResearchChecklistStatus(fund: any) {
  const checklist = fund?.marketResearchChecklist
  const status = String(checklist?.status || '').trim()
  if (status === 'complete') return '体检通过'
  if (status === 'repair') return '待补证'
  if (status === 'blocked') return '阻断'
  return '体检待核'
}

function marketResearchChecklistPrimaryGap(fund: any) {
  const checklist = fund?.marketResearchChecklist
  return String(checklist?.primaryGap || checklist?.primary_gap || '').trim()
}

function evidenceItemText(item: any) {
  if (!item) return ''
  if (typeof item === 'string') return item
  if (typeof item === 'number') return String(item)
  return item.label || item.title || item.name || item.reason || ''
}

function uniqueFundsByWindCode<T extends { windCode?: string | null }>(funds: T[]) {
  const fundMap = new Map<string, T>()
  funds.forEach((fund) => {
    const windCode = fund.windCode?.trim().toUpperCase()
    if (windCode && !fundMap.has(windCode)) fundMap.set(windCode, fund)
  })
  return Array.from(fundMap.values())
}

function asNumber(value: unknown) {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function boundedInteger(value: string | null, fallback: number, min: number, max: number) {
  if (value === null || value.trim() === '') return fallback
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return fallback
  return Math.max(min, Math.min(max, Math.floor(parsed)))
}

function boundedAmount(value: string | null, fallback = DEFAULT_PLANNED_AMOUNT) {
  const parsed = asNumber(value)
  if (parsed === null) return fallback
  return Math.max(MIN_PLANNED_AMOUNT, Math.min(MAX_PLANNED_AMOUNT, Math.round(parsed)))
}

function defaultPlannedAmountForPlan(purchasePlan: PurchasePlan) {
  return purchasePlan === 'sip' ? 1000 : 10000
}

function plannedAmountSearchParams(preferences: Pick<InvestorPreferences, 'purchasePlan' | 'plannedAmount'>) {
  const amount = String(preferences.plannedAmount)
  return {
    plannedAmount: amount,
    [preferences.purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount']: amount,
  }
}

function plannedAmountQuery(preferences: Pick<InvestorPreferences, 'purchasePlan' | 'plannedAmount'>) {
  return new URLSearchParams(plannedAmountSearchParams(preferences)).toString()
}

function amountGateRank(gate: SalesRuleExecutionAmountGate | null | undefined) {
  if (gate?.status === 'pass') return 0
  if (gate?.status === 'unknown' || !gate) return 1
  return 2
}

function ageDaysFromDateText(value: string | null | undefined) {
  if (!value) return null
  const date = new Date(`${String(value).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return null
  const currentDate = new Date()
  currentDate.setUTCHours(0, 0, 0, 0)
  return Math.floor((currentDate.getTime() - date.getTime()) / 86_400_000)
}

function metric(source: Record<string, any>, keys: string[]) {
  for (const key of keys) {
    const value = asNumber(source?.[key])
    if (value !== null) return value
  }
  return null
}

function salesRulesHrefForCodes(
  codes: string | string[],
  purchasePlan: PurchasePlan,
  plannedAmount: number = DEFAULT_PLANNED_AMOUNT,
  returnTo?: string,
) {
  const normalizedCodes = (Array.isArray(codes) ? codes : [codes])
    .map((code) => String(code || '').trim().toUpperCase())
    .filter(Boolean)
  const params = new URLSearchParams({ purchasePlan })
  params.set('plannedAmount', String(plannedAmount))
  params.set(purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(plannedAmount))
  if (normalizedCodes.length) params.set('codes', normalizedCodes.join(','))
  if (returnTo) params.set('returnTo', returnTo)
  return materialEvidenceHref(params)
}

function scoreReturn(annualReturn: number | null, profile: RiskProfile) {
  if (annualReturn === null) return 0
  const target = profile === 'conservative' ? 0.035 : profile === 'balanced' ? 0.08 : 0.12
  return clamp((annualReturn / target) * 30, 0, 35)
}

function scoreRisk(maxDrawdown: number | null, volatility: number | null, profile: RiskProfile, riskBudget: number) {
  const drawdown = maxDrawdown === null ? null : Math.abs(maxDrawdown)
  const volLimit = profile === 'conservative' ? 0.08 : profile === 'balanced' ? 0.18 : 0.32
  const ddScore = drawdown === null ? 0 : clamp((1 - drawdown / riskBudget) * 28, 0, 28)
  const volScore = volatility === null ? 0 : clamp((1 - volatility / volLimit) * 18, 0, 18)
  return ddScore + volScore
}

function resolveRiskBudget(profile: RiskProfile, preferences: InvestorPreferences) {
  if (preferences.maxDrawdownTolerance !== null) return clamp(preferences.maxDrawdownTolerance, 0.03, 0.4)
  return drawdownLimit(profile)
}

function horizonTypeAdjustment(fundType: string | null | undefined, preferences: InvestorPreferences) {
  const type = fundType || ''
  if (preferences.horizon === 'lt1y') {
    if (type === '货币型') return 6
    if (type === '债券型') return 4
    if (type === '混合型') return -5
    if (type === '股票型' || type === '指数型' || type === 'QDII') return -8
  }
  if (preferences.horizon === '1to3y') {
    if (type === '债券型' || type === '混合型') return 3
    if (type === '指数型') return 1
  }
  if (preferences.horizon === 'gt3y') {
    if (type === '指数型' || type === '股票型') return 4
    if (type === '混合型') return 3
    if (type === '货币型') return -6
  }
  return 0
}

function horizonWarnings(fundType: string | null | undefined, preferences: InvestorPreferences) {
  const type = fundType || ''
  const warnings: string[] = []
  if (preferences.horizon === 'lt1y' && ['股票型', '指数型', 'QDII', '混合型'].includes(type)) {
    warnings.push('计划持有期不足一年，与该类基金净值波动和赎回费规则可能不匹配')
  }
  if (preferences.horizon === 'gt3y' && type === '货币型') {
    warnings.push('长期资金使用货币型基金时，需评估收益弹性不足的问题')
  }
  return warnings
}

function typeHorizonFit(fundType: string | null | undefined, preferences: InvestorPreferences, profile: RiskProfile) {
  const type = fundType || '未分类'
  const warnings = horizonWarnings(type, preferences)
  const baseScore = typeFit[profile][type] ?? 6
  const adjustment = horizonTypeAdjustment(type, preferences)
  const score = Math.round(clamp(baseScore + adjustment, 0, 24))
  const shortMoneyHighVolatility = preferences.horizon === 'lt1y' && ['股票型', '指数型', 'QDII', '混合型'].includes(type)
  const longMoneyTooDefensive = preferences.horizon === 'gt3y' && ['货币型'].includes(type)
  const status = shortMoneyHighVolatility || longMoneyTooDefensive
    ? 'mismatch'
    : warnings.length || score < 12
      ? 'explain'
      : 'fit'
  const rule = shortMoneyHighVolatility
    ? '短期资金优先排除高波动权益/混合类，除非有明确赎回费、回撤预算和替代横评证据。'
    : longMoneyTooDefensive
      ? '长期资金若只看货币型，需解释收益弹性不足和机会成本。'
      : preferences.horizon === 'lt1y'
        ? '1年以内更重视流动性、低回撤、赎回规则和销售端状态。'
        : preferences.horizon === 'gt3y'
          ? '3年以上可提高权益/指数/混合样本权重，但仍需压力测试和销售规则完整。'
          : '1-3年需要同时比较回撤、收益弹性、经理样本和申赎成本。'
  return {
    status,
    label: status === 'fit' ? '类型期限匹配' : status === 'explain' ? '需要解释适配' : '类型期限错配',
    score,
    rule,
    warnings,
    action: status === 'fit'
      ? '可进入同类横评和研究证据复核。'
      : status === 'explain'
        ? '先补充为什么该类型适合当前持有期，再进入正式候选。'
        : '默认不进入正式候选，除非横评和补证能推翻错配。'
  }
}

function scoreScale(totalAsset: number | null) {
  if (totalAsset === null || totalAsset <= 0) return 4
  if (totalAsset >= 30 && totalAsset <= 300) return 12
  if (totalAsset > 300) return 9
  if (totalAsset >= 5) return 8
  return 4
}

function dataCompleteness(fund: ReturnType<typeof toCamelFund>, annualReturn: number | null, maxDrawdown: number | null) {
  let score = 0
  if (fund.nav !== null) score += 3
  if (fund.navDate) score += 2
  if (fund.establishmentDate) score += 2
  if (annualReturn !== null) score += 2
  if (maxDrawdown !== null) score += 2
  if ((fund.operationStatus as any)?.status && (fund.operationStatus as any).status !== 'unknown') score += 2
  if (hasFeeEvidence(fund)) score += 1
  if (managerEvidence(fund).status !== 'missing') score += 1
  return score
}

function managerEvidence(fund: ReturnType<typeof toCamelFund>) {
  const managers = ((fund as any).managers || []) as Array<{ name?: string; managementYears?: number | null; education?: string }>
  if (!managers.length) {
    return {
      status: 'missing' as const,
      score: 0,
      label: '经理待补',
      note: '基金经理明细缺失，无法判断现任经理样本。',
      managerNames: [] as string[],
      maxTenureYears: null as number | null,
    }
  }
  const managerNames = managers.map((manager) => manager.name || '姓名待补')
  const tenures = managers
    .map((manager) => asNumber(manager.managementYears))
    .filter((value): value is number => value !== null)
  const maxTenure = tenures.length ? Math.max(...tenures) : null
  const named = managers.filter((manager) => manager.name).length
  const score = maxTenure === null
    ? 1
    : maxTenure >= 5
      ? 5
      : maxTenure >= 3
        ? 4
        : maxTenure >= 1
          ? 3
          : 1
  const label = maxTenure === null ? '经理已知' : maxTenure >= 3 ? '经理样本较足' : maxTenure >= 1 ? '经理样本偏短' : '经理任期过短'
  return {
    status: maxTenure !== null && maxTenure < 1 ? 'short' as const : 'available' as const,
    score: named ? score : Math.max(1, score - 1),
    label,
    managerNames,
    maxTenureYears: maxTenure,
    note: maxTenure === null
      ? `${managerNames.join(' / ')}；任期待核`
      : `${managerNames.join(' / ')}；最长管理年限约 ${maxTenure.toFixed(1)} 年`,
  }
}

function hasFeeEvidence(fund: ReturnType<typeof toCamelFund>) {
  const feeInfo = fund.feeInfo as { management_fee?: number | null; managementFee?: number | null; custodian_fee?: number | null; custodianFee?: number | null } | null
  return feeInfo?.management_fee != null || feeInfo?.managementFee != null || feeInfo?.custodian_fee != null || feeInfo?.custodianFee != null
}

function feeEvidenceNote(fund: ReturnType<typeof toCamelFund>) {
  const feeInfo = fund.feeInfo as { management_fee?: number | null; managementFee?: number | null; custodian_fee?: number | null; custodianFee?: number | null } | null
  const managementFee = asNumber(feeInfo?.management_fee ?? feeInfo?.managementFee)
  const custodianFee = asNumber(feeInfo?.custodian_fee ?? feeInfo?.custodianFee)
  const parts = []
  if (managementFee !== null) parts.push(`管理费 ${managementFee.toFixed(2)}%`)
  if (custodianFee !== null) parts.push(`托管费 ${custodianFee.toFixed(2)}%`)
  return parts.length ? `${parts.join('，')}；申购/赎回费仍需销售平台确认` : '待接入申购费、赎回费、销售服务费和限购信息'
}

function costEvidence(fund: ReturnType<typeof toCamelFund>, preferences: InvestorPreferences) {
  const feeInfo = fund.feeInfo as {
    management_fee?: number | null
    managementFee?: number | null
    custodian_fee?: number | null
    custodianFee?: number | null
  } | null
  const salesRule = (fund as any).salesRule as {
    purchaseFeeRate?: number | null
    purchaseFeeSourceBacked?: boolean
    minPurchaseAmount?: number | null
    minPurchaseSourceBacked?: boolean
    minSipAmount?: number | null
    minSipSourceBacked?: boolean
    dailyLimitAmount?: number | null
    dailyLimitSourceBacked?: boolean
    redemptionFeeRules?: Array<{ feeRate?: number | null; label?: string }>
    redemptionFeeSourceUrl?: string | null
    redemptionFeeSourceUpdatedAt?: string | null
    redemptionFeePlatform?: string | null
    redemptionFeeNotes?: string | null
    salesServiceFeeRate?: number | null
    salesServiceFeeSourceBacked?: boolean
    supportsSip?: boolean | null
    supportsSipSourceBacked?: boolean
    purchaseStatusLabel?: string | null
    purchaseStatusSourceBacked?: boolean
    sourceUpdatedAt?: string | null
    sourceUrl?: string | null
    platform?: string | null
    notes?: string | null
  } | null
  const managementFee = asNumber(feeInfo?.management_fee ?? feeInfo?.managementFee)
  const custodianFee = asNumber(feeInfo?.custodian_fee ?? feeInfo?.custodianFee)
  const purchaseFeeRate = asNumber(salesRule?.purchaseFeeRate)
  const salesServiceFeeRate = asNumber(salesRule?.salesServiceFeeRate)
  const minPurchaseAmount = asNumber(salesRule?.minPurchaseAmount)
  const minSipAmount = asNumber(salesRule?.minSipAmount)
  const dailyLimitAmount = asNumber(salesRule?.dailyLimitAmount)
  const redemptionRules = Array.isArray(salesRule?.redemptionFeeRules) ? salesRule.redemptionFeeRules : []
  const hasRedemptionRules = hasSourceBackedRedemptionRules(salesRule, redemptionRules)
  const supportsSip = salesRule?.supportsSip
  const purchaseFeeSourceBacked = hasSourceBackedSalesRuleField(salesRule, 'purchaseFeeSourceBacked', purchaseFeeRate)
  const minPurchaseSourceBacked = hasSourceBackedSalesRuleField(salesRule, 'minPurchaseSourceBacked', minPurchaseAmount)
  const minSipSourceBacked = hasSourceBackedSalesRuleField(salesRule, 'minSipSourceBacked', minSipAmount)
  const dailyLimitSourceBacked = hasSourceBackedSalesRuleField(salesRule, 'dailyLimitSourceBacked', dailyLimitAmount)
  const salesServiceFeeSourceBacked = hasSourceBackedSalesRuleField(salesRule, 'salesServiceFeeSourceBacked', salesServiceFeeRate)
  const supportsSipSourceBacked = hasSourceBackedSalesRuleField(salesRule, 'supportsSipSourceBacked', supportsSip)
  const effectivePurchaseFeeRate = purchaseFeeSourceBacked ? purchaseFeeRate : null
  const effectiveSalesServiceFeeRate = salesServiceFeeSourceBacked ? salesServiceFeeRate : null
  const effectiveMinPurchaseAmount = minPurchaseSourceBacked ? minPurchaseAmount : null
  const effectiveMinSipAmount = minSipSourceBacked ? minSipAmount : null
  const effectiveDailyLimitAmount = dailyLimitSourceBacked ? dailyLimitAmount : null
  const effectiveSupportsSip = supportsSipSourceBacked ? supportsSip : null
  const totalAnnualFee = [managementFee, custodianFee, effectiveSalesServiceFeeRate].reduce<number>((sum, value) => sum + (value ?? 0), 0)

  let score = 0
  if (managementFee !== null) score += managementFee <= 0.5 ? 2 : managementFee <= 1.2 ? 1.5 : 0.8
  if (custodianFee !== null) score += custodianFee <= 0.15 ? 1.5 : custodianFee <= 0.25 ? 1 : 0.5
  if (effectivePurchaseFeeRate !== null) score += effectivePurchaseFeeRate <= 0.15 ? 2 : effectivePurchaseFeeRate <= 0.6 ? 1.2 : 0.5
  if (hasRedemptionRules) score += 1.5
  if (preferences.purchasePlan === 'sip') {
    if (effectiveSupportsSip === true) score += 1.2
    if (effectiveMinSipAmount !== null && effectiveMinSipAmount <= 100) score += 0.8
  } else if (effectiveMinPurchaseAmount !== null && effectiveMinPurchaseAmount <= 1000) {
    score += 1
  }
  if (effectiveDailyLimitAmount !== null) score += 0.5

  const missing = [
    purchaseFeeSourceBacked ? '' : '申购费/折扣（30天来源背书）',
    hasRedemptionRules ? '' : '赎回费/持有期',
    preferences.purchasePlan === 'sip' && !supportsSipSourceBacked ? '定投支持（30天来源背书）' : '',
    preferences.purchasePlan === 'sip' && effectiveSupportsSip === true && !minSipSourceBacked ? '定投起点（30天来源背书）' : '',
    preferences.purchasePlan === 'lump_sum' && !minPurchaseSourceBacked ? '起购金额（30天来源背书）' : '',
    dailyLimitSourceBacked ? '' : '限购金额（30天来源背书）',
    salesServiceFeeRate !== null && !salesServiceFeeSourceBacked ? '销售服务费（30天来源背书）' : '',
  ].filter(Boolean)
  const label = score >= 7.5 && missing.length <= 2 ? '成本证据较优' : score >= 5 ? '成本可比较' : '成本待补'
  const status = missing.length >= 4 ? 'thin' as const : missing.length > 0 ? 'partial' as const : 'strong' as const

  return {
    status,
    score: Math.round(clamp(score, 0, 10) * 10) / 10,
    label,
    totalAnnualFee,
    managementFee,
    custodianFee,
    purchaseFeeRate: effectivePurchaseFeeRate,
    purchaseFeeSourceBacked,
    salesServiceFeeRate: effectiveSalesServiceFeeRate,
    salesServiceFeeSourceBacked,
    minPurchaseAmount: effectiveMinPurchaseAmount,
    minPurchaseSourceBacked,
    minSipAmount: effectiveMinSipAmount,
    minSipSourceBacked,
    dailyLimitAmount: effectiveDailyLimitAmount,
    dailyLimitSourceBacked,
    supportsSip: effectiveSupportsSip,
    supportsSipSourceBacked,
    hasRedemptionRules,
    missing,
    note: `管理费 ${managementFee === null ? '待补' : `${managementFee.toFixed(2)}%`}，托管费 ${custodianFee === null ? '待补' : `${custodianFee.toFixed(2)}%`}；${missing.length ? `仍缺 ${missing.join('、')}` : '销售端规则已覆盖'}`,
  }
}

function parseRiskLevel(value: unknown) {
  if (!value) return null
  const match = String(value).toUpperCase().match(/R?([1-5])/)
  return match ? Number(match[1]) : null
}

function isSalesRuleSourceDateStale(value: unknown) {
  if (!value) return false
  const sourceDate = new Date(`${String(value).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(sourceDate.getTime())) return true
  const currentDate = new Date()
  currentDate.setUTCHours(0, 0, 0, 0)
  const ageDays = Math.floor((currentDate.getTime() - sourceDate.getTime()) / 86_400_000)
  return ageDays > 30 || ageDays < 0
}

function hasSourceBackedSalesRuleField(
  salesRule: {
    sourceUpdatedAt?: string | null
    sourceUrl?: string | null
    platform?: string | null
    notes?: string | null
    [key: string]: unknown
  } | null,
  sourceFlag: string,
  value: unknown,
) {
  if (value === null || value === undefined || value === '') return false
  const explicitFlag = salesRule?.[sourceFlag]
  if (explicitFlag === true) return true
  if (explicitFlag === false) return false
  if (!salesRule?.sourceUpdatedAt || isSalesRuleSourceDateStale(salesRule.sourceUpdatedAt)) return false
  const platform = String(salesRule.platform || '').trim()
  const sourceUrl = String(salesRule.sourceUrl || '').trim()
  const notes = String(salesRule.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function hasSourceBackedRedemptionRules(salesRule: {
  redemptionFeeSourceUpdatedAt?: string | null
  redemptionFeeSourceUrl?: string | null
  redemptionFeePlatform?: string | null
  redemptionFeeNotes?: string | null
  sourceUpdatedAt?: string | null
  sourceUrl?: string | null
  platform?: string | null
  notes?: string | null
} | null, redemptionRules: unknown[]) {
  if (!redemptionRules.length) return false
  const sourceUpdatedAt = salesRule?.redemptionFeeSourceUpdatedAt || salesRule?.sourceUpdatedAt || null
  if (!sourceUpdatedAt || isSalesRuleSourceDateStale(sourceUpdatedAt)) return false
  const platform = String(salesRule?.redemptionFeePlatform || salesRule?.platform || '').trim()
  const sourceUrl = String(salesRule?.redemptionFeeSourceUrl || salesRule?.sourceUrl || '').trim()
  const notes = String(salesRule?.redemptionFeeNotes || salesRule?.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function salesRiskLevelEvidence(salesRule: {
  riskLevel?: string | null
  sourceUpdatedAt?: string | null
  sourceUrl?: string | null
  notes?: string | null
} | null) {
  const riskLevel = String(salesRule?.riskLevel || '').trim().toUpperCase()
  if (!/^R[1-5]$/.test(riskLevel)) {
    return {
      riskLevel,
      sourceBacked: false,
      status: 'missing' as const,
      label: 'R1-R5 待补',
      detail: '未取得销售平台或基金合同风险等级，不能用于适当性匹配。',
    }
  }
  if (!salesRule?.sourceUpdatedAt) {
    return {
      riskLevel,
      sourceBacked: false,
      status: 'unsourced' as const,
      label: `${riskLevel} 缺来源日期`,
      detail: '已填写风险等级，但缺少可追溯来源日期，仍按风险等级待补处理。',
    }
  }
  if (isSalesRuleSourceDateStale(salesRule.sourceUpdatedAt)) {
    return {
      riskLevel,
      sourceBacked: false,
      status: 'stale' as const,
      label: `${riskLevel} 来源过旧`,
      detail: '风险等级来源日期已超过 30 天研究复核窗口，需重新核验。',
    }
  }
  const sourceUrl = String(salesRule.sourceUrl || '').trim()
  const platform = String((salesRule as { platform?: string | null } | null)?.platform || '').trim()
  const notes = String(salesRule.notes || '').trim()
  const sourceBacked = hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
  return {
    riskLevel,
    sourceBacked,
    status: sourceBacked ? 'verified' as const : 'unsourced' as const,
    label: sourceBacked ? `${riskLevel} 有来源` : `${riskLevel} 缺来源背书`,
    detail: sourceBacked
      ? '风险等级具备来源日期与销售平台/基金合同来源背书；研究复核仍需复核实时状态。'
      : '已填写风险等级但缺少销售平台/基金合同来源证据，不能用于适当性匹配。',
  }
}

function riskSuitability(fund: ReturnType<typeof toCamelFund>, profile: RiskProfile) {
  const salesRule = (fund as any).salesRule as {
    riskLevel?: string | null
    sourceUpdatedAt?: string | null
    sourceUrl?: string | null
    notes?: string | null
  } | null
  const rawRiskLevel = salesRule?.riskLevel || null
  const fundRiskLevel = parseRiskLevel(rawRiskLevel)
  const riskEvidence = salesRiskLevelEvidence(salesRule)
  const investorMaxRiskLevel = profileMaxRiskLevel[profile]
  const investorLabel = `${profileLabel[profile]}（最高 R${investorMaxRiskLevel}）`

  if (fundRiskLevel === null) {
    return {
      status: 'missing' as const,
      fundRiskLevel: null,
      investorMaxRiskLevel,
      label: '风险等级待补',
      note: `未录入销售平台风险等级，无法完成 ${investorLabel} 的适当性匹配。`,
      riskLevelSourceBacked: false,
      riskLevelEvidenceStatus: riskEvidence.status,
      riskLevelEvidenceLabel: riskEvidence.label,
      riskLevelEvidenceDetail: riskEvidence.detail,
    }
  }

  if (!riskEvidence.sourceBacked) {
    return {
      status: 'missing' as const,
      fundRiskLevel,
      investorMaxRiskLevel,
      label: '风险等级缺来源背书',
      note: `${riskEvidence.detail} 无法完成 ${investorLabel} 的适当性匹配。`,
      riskLevelSourceBacked: false,
      riskLevelEvidenceStatus: riskEvidence.status,
      riskLevelEvidenceLabel: riskEvidence.label,
      riskLevelEvidenceDetail: riskEvidence.detail,
    }
  }

  if (fundRiskLevel > investorMaxRiskLevel) {
    return {
      status: 'mismatch' as const,
      fundRiskLevel,
      investorMaxRiskLevel,
      label: `风险等级不匹配 R${fundRiskLevel}>R${investorMaxRiskLevel}`,
      note: `基金销售风险等级 R${fundRiskLevel} 高于当前 ${investorLabel} 上限，不能作为研究候选。`,
      riskLevelSourceBacked: true,
      riskLevelEvidenceStatus: riskEvidence.status,
      riskLevelEvidenceLabel: riskEvidence.label,
      riskLevelEvidenceDetail: riskEvidence.detail,
    }
  }

  return {
    status: 'matched' as const,
    fundRiskLevel,
    investorMaxRiskLevel,
    label: `风险等级匹配 R${fundRiskLevel}`,
    note: `基金风险等级 R${fundRiskLevel} 未超过 ${investorLabel} 上限。`,
    riskLevelSourceBacked: true,
    riskLevelEvidenceStatus: riskEvidence.status,
    riskLevelEvidenceLabel: riskEvidence.label,
    riskLevelEvidenceDetail: riskEvidence.detail,
  }
}

function fundAgeDays(establishmentDate: string | null) {
  if (!establishmentDate) return null
  const startedAt = new Date(establishmentDate).getTime()
  if (!Number.isFinite(startedAt)) return null
  return Math.max(0, Math.floor((Date.now() - startedAt) / 86_400_000))
}

function drawdownLimit(profile: RiskProfile) {
  return profile === 'conservative' ? 0.06 : profile === 'balanced' ? 0.15 : 0.28
}

function volatilityLimit(profile: RiskProfile) {
  return profile === 'conservative' ? 0.08 : profile === 'balanced' ? 0.18 : 0.32
}

function checklistStatus(passed: boolean, pending = false) {
  if (pending) return 'pending'
  return passed ? 'pass' : 'warn'
}

function riskLabel(maxDrawdown: number | null, volatility: number | null) {
  const drawdown = maxDrawdown === null ? null : Math.abs(maxDrawdown)
  if ((drawdown !== null && drawdown > 0.25) || (volatility !== null && volatility > 0.28)) return '高波动'
  if ((drawdown !== null && drawdown > 0.12) || (volatility !== null && volatility > 0.16)) return '中高波动'
  if ((drawdown !== null && drawdown > 0.05) || (volatility !== null && volatility > 0.08)) return '中低波动'
  return '低波动'
}

function tradabilityStatus(fund: ReturnType<typeof toCamelFund>) {
  const status = fund.operationStatus as { status?: string; label?: string; reason?: string } | null
  if (status?.status === 'blocked') {
    return {
      status: 'blocked',
      label: status.label || '不可申购',
      note: status.reason || '存在退市、清算或终止信号，不能作为研究候选。',
    }
  }
  if (status?.status === 'watch') {
    return {
      status: 'watch',
      label: status.label || '状态待核',
      note: status.reason || '需复核销售端开放申购状态。',
    }
  }
  return {
    status: 'unknown',
    label: status?.label || '申购待核',
    note: status?.reason || '待接入销售端申购状态与费率。',
  }
}

function evidenceGrade(evidenceScore: number, dataGaps: string[]) {
  if (evidenceScore >= 9 && dataGaps.length <= 2) return 'A'
  if (evidenceScore >= 7 && dataGaps.length <= 4) return 'B'
  if (evidenceScore >= 5) return 'C'
  return 'D'
}

const evidenceGradeRank: Record<EvidenceGrade, number> = {
  A: 4,
  B: 3,
  C: 2,
  D: 1,
}

function parseEvidenceGrade(value: string | null): EvidenceGrade {
  return value === 'A' || value === 'B' || value === 'C' || value === 'D' ? value : 'D'
}

function passesEvidenceGrade(actual: EvidenceGrade, minimum: EvidenceGrade) {
  return evidenceGradeRank[actual] >= evidenceGradeRank[minimum]
}

function buildPurchaseGate({
  tradability,
  suitability,
  score,
  evidenceScore,
  dataGaps,
  drawdown,
  riskBudget,
  totalAsset,
  ageDays,
  preferences,
}: {
  tradability: ReturnType<typeof tradabilityStatus>
  suitability: ReturnType<typeof riskSuitability>
  score: number
  evidenceScore: number
  dataGaps: string[]
  drawdown: number | null
  riskBudget: number
  totalAsset: number | null
  ageDays: number | null
  preferences: InvestorPreferences
}) {
  const hardBlocks: string[] = []
  const cautionFlags: string[] = []
  const mustVerifyBeforeBuy = [
    '销售平台是否开放申购/定投',
    '申购费、赎回费、销售服务费与持有期规则',
    '基金合同、最新季报与风险等级是否匹配本人适当性',
  ]

  if (tradability.status === 'blocked') hardBlocks.push(tradability.note)
  if (suitability.status === 'mismatch') hardBlocks.push(suitability.note)
  if (drawdown !== null && drawdown > riskBudget) hardBlocks.push(`最大回撤 ${formatPercent(-drawdown)} 超过当前画像预算 ${formatPercent(-riskBudget)}`)
  if (totalAsset !== null && totalAsset < 2) hardBlocks.push('基金规模低于 2 亿，清盘和流动性风险需先排除')

  if (tradability.status === 'unknown') cautionFlags.push('缺少销售端申购/赎回开放状态')
  if (suitability.status === 'missing') cautionFlags.push('缺少销售平台风险等级，无法完成适当性匹配')
  if (dataGaps.includes('销售费率/限购')) cautionFlags.push('缺少申购/赎回费与限购信息')
  if (dataGaps.includes('持仓明细')) cautionFlags.push('缺少持仓明细，暂不能解释行业/个股暴露')
  if (ageDays !== null && ageDays < 365) cautionFlags.push('成立不足一年，样本期偏短')
  if (evidenceScore < 6) cautionFlags.push('关键证据不足，需补齐净值、规模或回撤字段')
  if (preferences.horizon === 'lt1y') cautionFlags.push('计划持有期较短，必须复核赎回费和最短持有期规则')
  if (preferences.purchasePlan === 'sip') mustVerifyBeforeBuy.push('定投起点、扣款周期和销售平台是否支持定投')
  if (suitability.status !== 'matched') mustVerifyBeforeBuy.push('销售平台风险等级与本人风险承受能力匹配')

  const grade = evidenceGrade(evidenceScore, dataGaps)
  const level =
    hardBlocks.length > 0
      ? 'blocked'
      : suitability.status === 'missing'
        ? 'verify_first'
      : grade === 'D' || cautionFlags.length >= 4
        ? 'verify_first'
        : score >= 82 && grade !== 'C'
          ? 'research_ready'
          : 'watchlist'

  const labelMap = {
    blocked: '不可纳入研究候选',
    verify_first: '先补证再比较',
    research_ready: '可进入重点研究',
    watchlist: '可放入观察池',
  } as const

  const descriptionMap = {
    blocked: '存在硬性阻断或风险预算不匹配，当前不能进入研究候选。',
    verify_first: '基础匹配尚可，但费用、状态或证据缺口较多，需先补齐再比较。',
    research_ready: '风险画像、收益风险和证据强度相对更好，可进入报告复核与同类对比。',
    watchlist: '可继续观察，但仍需结合报告、同类分位和销售端信息复核。',
  } as const

  return {
    level,
    label: labelMap[level],
    description: descriptionMap[level],
    evidenceGrade: grade,
    hardBlocks,
    cautionFlags,
    mustVerifyBeforeBuy,
  }
}

function formatPercent(value: number | null) {
  return value === null ? '缺失' : `${(value * 100).toFixed(2)}%`
}

function formatPercentPointDelta(value: number | null) {
  if (value === null) return '待补'
  const sign = value > 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(2)}pct`
}

function metricNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function buildPeerWinLossLines(fund: any, alternatives: any[], preferences: InvestorPreferences) {
  const challengers = alternatives
    .filter((item) => item.windCode !== fund.windCode)
    .filter((item) => (item.type || '未分类') === (fund.type || '未分类'))
    .slice(0, 3)
  const fallbackChallengers = alternatives
    .filter((item) => item.windCode !== fund.windCode)
    .slice(0, 3)
  const selectedChallengers = challengers.length ? challengers : fallbackChallengers

  return selectedChallengers.map((alternative) => {
    const returnDelta = metricNumber(fund.annualReturn) !== null && metricNumber(alternative.annualReturn) !== null
      ? metricNumber(fund.annualReturn)! - metricNumber(alternative.annualReturn)!
      : null
    const drawdownDelta = metricNumber(fund.maxDrawdown) !== null && metricNumber(alternative.maxDrawdown) !== null
      ? Math.abs(metricNumber(fund.maxDrawdown)!) - Math.abs(metricNumber(alternative.maxDrawdown)!)
      : null
    const volatilityDelta = metricNumber(fund.volatility) !== null && metricNumber(alternative.volatility) !== null
      ? metricNumber(fund.volatility)! - metricNumber(alternative.volatility)!
      : null
    const feeDelta = metricNumber(fund.costEvidence?.totalAnnualFee) !== null && metricNumber(alternative.costEvidence?.totalAnnualFee) !== null
      ? metricNumber(fund.costEvidence?.totalAnnualFee)! - metricNumber(alternative.costEvidence?.totalAnnualFee)!
      : null
    const scoreDelta = metricNumber(fund.investorScore) !== null && metricNumber(alternative.investorScore) !== null
      ? metricNumber(fund.investorScore)! - metricNumber(alternative.investorScore)!
      : null
    const managerDelta = metricNumber(fund.managerEvidence?.maxTenureYears) !== null && metricNumber(alternative.managerEvidence?.maxTenureYears) !== null
      ? metricNumber(fund.managerEvidence?.maxTenureYears)! - metricNumber(alternative.managerEvidence?.maxTenureYears)!
      : null
    const evidencePass = passesEvidenceGrade(fund.purchaseGate?.evidenceGrade || 'D', alternative.purchaseGate?.evidenceGrade || 'D')
    const riskWin = drawdownDelta !== null && drawdownDelta <= 0.02 && (volatilityDelta === null || volatilityDelta <= 0.02)
    const returnWin = returnDelta !== null && returnDelta >= -0.01
    const costWin = feeDelta === null || feeDelta <= 0.003 || preferences.purchasePlan === 'sip'
    const managerWin = managerDelta === null || managerDelta >= -1
    const scoreWin = scoreDelta !== null && scoreDelta >= 0
    const salesRuleReady = fund.currentSalesRuleGate?.status !== 'blocked' && alternative.currentSalesRuleGate?.status !== 'blocked'
    const passedChecks = [riskWin, returnWin, costWin, managerWin, scoreWin, evidencePass, salesRuleReady].filter(Boolean).length
    const status = !salesRuleReady
      ? 'rules_pending'
      : passedChecks >= 6
      ? 'win'
      : passedChecks >= 4
        ? 'close'
        : 'lose'

    return {
      challengerCode: alternative.windCode,
      challengerName: alternative.name,
      challengerType: alternative.type || '未分类',
      status,
      label: status === 'win' ? '胜出' : status === 'close' ? '接近' : status === 'rules_pending' ? '规则待补' : '未胜出',
      summary: `${alternative.name}：选基分差 ${scoreDelta === null ? '待补' : scoreDelta >= 0 ? `+${scoreDelta}` : String(scoreDelta)}；收益差 ${formatPercentPointDelta(returnDelta)}；回撤差 ${formatPercentPointDelta(drawdownDelta)}；费率差 ${formatPercentPointDelta(feeDelta)}`,
      thresholds: [
        {
          key: 'sales_rules',
          label: '销售规则',
          passed: salesRuleReady,
          detail: salesRuleReady
            ? '两只基金均未见销售规则硬缺口，可进入正式横评复核。'
            : `任一基金销售规则未补齐，只能作为研究态横评；当前 ${fund.name} 缺 ${fund.currentSalesRuleGate?.missingCount || 0} 项，${alternative.name} 缺 ${alternative.currentSalesRuleGate?.missingCount || 0} 项。`,
        },
        {
          key: 'risk',
          label: '回撤/波动',
          passed: riskWin,
          detail: `回撤不能比替代高 2pct 以上，波动不能高 2pct 以上；当前回撤差 ${formatPercentPointDelta(drawdownDelta)}、波动差 ${formatPercentPointDelta(volatilityDelta)}`,
        },
        {
          key: 'return',
          label: '收益弹性',
          passed: returnWin,
          detail: `近一年收益不能落后替代 1pct 以上；当前差 ${formatPercentPointDelta(returnDelta)}`,
        },
        {
          key: 'score',
          label: '选基总分',
          passed: scoreWin,
          detail: `画像匹配总分不能低于替代；当前差 ${scoreDelta === null ? '待补' : scoreDelta >= 0 ? `+${scoreDelta}` : String(scoreDelta)}`,
        },
        {
          key: 'cost',
          label: '费用口径',
          passed: costWin,
          detail: `总年费率不能高出替代 0.30pct 以上；当前差 ${formatPercentPointDelta(feeDelta)}`,
        },
        {
          key: 'manager',
          label: '经理样本',
          passed: managerWin,
          detail: `现任经理任期不能比替代少 1 年以上；当前差 ${managerDelta === null ? '待补' : `${managerDelta.toFixed(1)}年`}`,
        },
        {
          key: 'evidence',
          label: '证据等级',
          passed: evidencePass,
          detail: `证据等级不能低于替代；当前 ${fund.purchaseGate?.evidenceGrade || 'D'} vs ${alternative.purchaseGate?.evidenceGrade || 'D'}`,
        },
      ],
      passedChecks,
      totalChecks: 7,
      actionHref: `/analysis/comparison?${new URLSearchParams({
        codes: [fund.windCode, alternative.windCode].join(','),
        horizon: preferences.horizon,
        purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
        autoReplay: '1',
      }).toString()}`,
    }
  })
}

function buildCandidateChallenge({
  fund,
  alternatives,
  safeProfile,
  preferences,
}: {
  fund: any
  alternatives: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  const alternativeFunds = alternatives
    .filter((item) => item.windCode !== fund.windCode && item.type === fund.type)
    .filter((item) => item.currentSalesRuleGate?.status !== 'blocked' && item.purchaseGate?.level !== 'blocked')
    .slice(0, 3)
  const broaderAlternatives = alternatives
    .filter((item) => item.windCode !== fund.windCode)
    .filter((item) => item.currentSalesRuleGate?.status !== 'blocked' && item.purchaseGate?.level !== 'blocked')
    .slice(0, 3)
  const comparisonCodes = [fund, ...(alternativeFunds.length ? alternativeFunds : broaderAlternatives)]
    .slice(0, 4)
    .map((item) => item.windCode)
  const comparisonHref = comparisonCodes.length >= 2
    ? `/analysis/comparison?${new URLSearchParams({
      codes: comparisonCodes.join(','),
      profile: safeProfile,
      horizon: preferences.horizon,
      purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
      autoReplay: '1',
    }).toString()}`
    : ''
  const riskBudget = resolveRiskBudget(safeProfile, preferences)
  const drawdown = fund.maxDrawdown === null ? null : Math.abs(fund.maxDrawdown)
  const rebuttals = uniqueText([
    ...(fund.purchaseGate?.hardBlocks || []),
    ...(fund.purchaseGate?.cautionFlags || []),
    ...(fund.holdingExperience?.warnings || []),
    ...(fund.peerPercentiles?.weaknessLabels || []),
    fund.currentSalesRuleGate?.status === 'blocked'
      ? `销售规则仍缺 ${fund.currentSalesRuleGate?.missingCount || 0} 项：${(fund.currentSalesRuleGate?.missingItems || []).slice(0, 3).join('、') || '销售端硬字段'}`
      : '',
    drawdown !== null && drawdown > riskBudget
      ? `最大回撤 ${formatPercent(-drawdown)} 超过当前预算 ${formatPercent(-riskBudget)}`
      : '',
    fund.costEvidence?.status === 'thin' ? '费用、起购/定投或赎回费证据偏薄，不能只看收益排序。' : '',
  ]).slice(0, 5)
  const mustBeat = [
    '同类替代基金的回撤、费用、经理任期和销售规则完整度',
    preferences.purchasePlan === 'sip' ? '定投起点、定投支持和最短持有成本' : '一次性配置起点、申购费和短期赎回费',
    '近一年收益是否只是阶段行情，需用滚动窗口和压力体验复核',
  ]
  const giveUpLines = uniqueText([
    fund.currentSalesRuleGate?.status === 'blocked' ? '销售规则硬缺口补不齐：不进入正式候选。' : '',
    fund.purchaseGate?.level === 'blocked' ? '研究证据闸门仍为硬阻断：只保留为排除样本。' : '',
    fund.purchaseGate?.evidenceGrade === 'D' ? '关键净值、回撤、经理或费用证据无法补齐：不保存正式报告。' : '',
    drawdown !== null && drawdown > riskBudget ? '回撤超过画像预算且无法用定投/持有期解释：放弃。' : '',
    fund.peerPercentiles?.peerScore !== null && fund.peerPercentiles?.peerScore < 45 ? '同类综合长期低于中位数：除非有明确反转证据，否则不推进。' : '',
  ]).slice(0, 4)
  const alternativeItems = (alternativeFunds.length ? alternativeFunds : broaderAlternatives).map((item) => ({
    windCode: item.windCode,
    name: item.name,
    type: item.type,
    investorScore: item.investorScore,
    peerScore: item.peerPercentiles?.peerScore ?? null,
    purchaseGateLabel: item.purchaseGate?.label || '待复核',
    actionHref: `/funds/${encodeURIComponent(item.id || item.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
  }))
  const winLossLines = buildPeerWinLossLines(fund, alternatives, preferences)

  return {
    windCode: fund.windCode,
    name: fund.name,
    title: `研究反证：为什么可能不选 ${fund.name}`,
    rebuttals: rebuttals.length ? rebuttals : ['暂无硬性反证，但仍需用同类替代、销售规则和压力体验复核，不能只看综合分。'],
    mustBeat,
    winLossLines,
    giveUpLines: giveUpLines.length ? giveUpLines : ['若同类横评中收益/回撤/费用/证据没有明显优势，则不进入正式候选。'],
    alternatives: alternativeItems,
    comparisonHref,
  }
}

function buildDoNotBuyDecisionBoard({
  ranked,
  candidateChallenges,
  buyBeforeLandmineBoard,
  evidenceClosureQueue,
  reportReadinessRadar,
  preferences,
  safeProfile,
}: {
  ranked: any[]
  candidateChallenges: ReturnType<typeof buildCandidateChallenge>[]
  buyBeforeLandmineBoard: any[]
  evidenceClosureQueue: any[]
  reportReadinessRadar: any[]
  preferences: InvestorPreferences
  safeProfile: RiskProfile
}) {
  const challengeMap = new Map(candidateChallenges.map((item) => [item.windCode, item]))
  const landmineMap = new Map(buyBeforeLandmineBoard.map((item: any) => [item.windCode, item]))
  const closureMap = new Map(evidenceClosureQueue.map((item: any) => [item.windCode, item]))
  const readinessMap = new Map(reportReadinessRadar.map((item: any) => [item.windCode, item]))
  const riskBudget = resolveRiskBudget(safeProfile, preferences)

  return uniqueFundsByWindCode(ranked.slice(0, 12))
    .map((fund: any) => {
      const challenge = challengeMap.get(fund.windCode)
      const landmine = landmineMap.get(fund.windCode)
      const closure = closureMap.get(fund.windCode)
      const readiness = readinessMap.get(fund.windCode)
      const drawdown = fund.maxDrawdown === null ? null : Math.abs(fund.maxDrawdown)
      const hardBlocks = uniqueText([
        ...(fund.purchaseGate?.hardBlocks || []),
        fund.currentSalesRuleGate?.status === 'blocked'
          ? `销售规则硬缺口：${(fund.currentSalesRuleGate?.missingItems || []).slice(0, 3).join('、') || '销售端字段待补'}`
          : '',
        fund.executionAmountGate?.status === 'blocked' ? fund.executionAmountGate.detail || fund.executionAmountGate.label : '',
        fund.riskSuitability?.status === 'mismatch' ? fund.riskSuitability.note || fund.riskSuitability.label : '',
      ]).slice(0, 4)
      const evidenceGaps = uniqueText([
        ...(fund.purchaseGate?.cautionFlags || []),
        ...(fund.dataGaps || []),
        ...(fund.costEvidence?.missing || []).map((item: string) => `成本证据：${item}`),
        closure && closure.status !== 'ready' ? `证据闭环停在“${closure.stageLabel}”` : '',
        readiness && !readiness.canGenerateFormalReport ? `正式报告未就绪：${readiness.nextAction}` : '',
      ]).slice(0, 5)
      const riskFlags = uniqueText([
        drawdown !== null && drawdown > riskBudget
          ? `最大回撤 ${formatPercent(-drawdown)} 超过画像预算 ${formatPercent(-riskBudget)}`
          : '',
        ...(fund.holdingExperience?.warnings || []),
        ...(landmine?.warningItems || []).map((item: any) => `${item.label}：${item.detail}`),
      ]).slice(0, 5)
      const alternativeDisadvantages = uniqueText([
        ...(challenge?.winLossLines || [])
          .filter((line) => line.status === 'lose' || line.status === 'close')
          .map((line) => `对 ${line.challengerName}：${line.label}；${line.summary}`),
        ...(challenge?.alternatives || []).slice(0, 2).map((item) => `可先横评替代：${item.name}（${item.investorScore}分，${item.purchaseGateLabel}）`),
      ]).slice(0, 4)
      const giveUpLines = challenge?.giveUpLines || []
      const severityScore = hardBlocks.length * 30
        + evidenceGaps.length * 10
        + riskFlags.length * 12
        + alternativeDisadvantages.length * 8
        + (landmine?.level === 'red' ? 35 : landmine?.level === 'orange' ? 22 : 0)
      const level = hardBlocks.length || landmine?.level === 'red'
        ? 'do_not_buy'
        : evidenceGaps.length >= 3 || riskFlags.length >= 2 || landmine?.level === 'orange'
          ? 'pause'
          : alternativeDisadvantages.length
            ? 'challenge'
            : 'watch'
      const label = level === 'do_not_buy'
        ? '暂不买：硬阻断'
        : level === 'pause'
          ? '先别买：证据/风险未过'
          : level === 'challenge'
            ? '先横评：替代未打败'
            : '观察：继续留样本'
      const primaryReason = hardBlocks[0] || riskFlags[0] || evidenceGaps[0] || alternativeDisadvantages[0] || giveUpLines[0] || '未形成明确研究优势，继续观察。'
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type,
        investorScore: fund.investorScore,
        level: level as 'do_not_buy' | 'pause' | 'challenge' | 'watch',
        label,
        severityScore: Math.round(clamp(severityScore, 0, 100)),
        primaryReason,
        hardBlocks,
        evidenceGaps,
        riskFlags,
        alternativeDisadvantages,
        giveUpLines,
        actionLabel: hardBlocks.length
          ? '查看阻断并补证'
          : alternativeDisadvantages.length
            ? '打开横评验证'
            : '打开详情复核',
        actionHref: challenge?.comparisonHref || `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
      }
    })
    .filter((item) => item.level !== 'watch' || item.severityScore > 0)
    .sort((left, right) => {
      const rank: Record<'do_not_buy' | 'pause' | 'challenge' | 'watch', number> = { do_not_buy: 0, pause: 1, challenge: 2, watch: 3 }
      return rank[left.level] - rank[right.level] || right.severityScore - left.severityScore || right.investorScore - left.investorScore
    })
    .slice(0, 8)
}

function buildShareClassDecisionQueue({
  ranked,
  shareClassUniverse,
  salesRuleAmountGateMap,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  shareClassUniverse?: any[]
  salesRuleAmountGateMap?: Map<string, SalesRuleExecutionAmountGate>
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  const seenGroups = new Set<string>()
  return ranked
    .filter((fund: any) => fund.shareClassInfo?.siblingCount > 1)
    .map((fund: any) => {
      const info = fund.shareClassInfo
      const groupKey = `${info.baseName}::${fund.type || ''}`
      const groupFunds = (shareClassUniverse || ranked).filter((item: any) => item.shareClassInfo
        && `${item.shareClassInfo.baseName}::${item.type || ''}` === groupKey)
      const comparisonCodes = Array.from(new Set([fund.windCode, ...(info.siblingCodes || [])])).slice(0, 4)
      const currentIsBestCost = info.siblingBestCostCode
        ? info.siblingBestCostCode === fund.windCode
        : false
      const costComparisons = groupFunds
        .map((item: any) => estimateShareClassOneYearCost(item, preferences.plannedAmount, salesRuleAmountGateMap?.get(String(item.windCode || '').toUpperCase()) || null))
        .sort((left: any, right: any) => {
          const amountGateDiff = amountGateRank(left.executionAmountGate) - amountGateRank(right.executionAmountGate)
          if (amountGateDiff !== 0) return amountGateDiff
          if (left.oneYearKnownCost === null && right.oneYearKnownCost === null) return left.windCode.localeCompare(right.windCode)
          if (left.oneYearKnownCost === null) return 1
          if (right.oneYearKnownCost === null) return -1
          return left.oneYearKnownCost - right.oneYearKnownCost
        })
      const currentCost = costComparisons.find((item: any) => item.windCode === fund.windCode) || null
      const bestKnownCost = costComparisons.find((item: any) => item.oneYearKnownCost !== null) || null
      const executableBestKnownCost = costComparisons.find((item: any) => item.executionAmountGate?.status !== 'blocked' && item.oneYearKnownCost !== null) || null
      const amountBlockedCount = costComparisons.filter((item: any) => item.executionAmountGate?.status === 'blocked').length
      const amountUnknownCount = costComparisons.filter((item: any) => item.executionAmountGate?.status === 'unknown' || !item.executionAmountGate).length
      const costDeltaToBest = currentCost?.oneYearKnownCost !== null && currentCost?.oneYearKnownCost !== undefined && bestKnownCost?.oneYearKnownCost !== null && bestKnownCost?.oneYearKnownCost !== undefined
        ? currentCost.oneYearKnownCost - bestKnownCost.oneYearKnownCost
        : null
      const currentAmountGate = currentCost?.executionAmountGate || null
      const amountGateLabel = currentAmountGate?.label || '金额门槛待补'
      const amountGateDetail = currentAmountGate?.detail || '未取得当前份额销售规则金额门禁，不能把该份额作为正式推荐。'
      const amountGateAdvice = currentAmountGate?.advice || '先补销售平台起购、定投起点和限购金额，再判断当前计划金额是否可执行。'
      return {
        groupKey,
        baseName: info.baseName,
        current: {
          windCode: fund.windCode,
          name: fund.name,
          classType: info.classType,
          investorScore: fund.investorScore,
          costScore: fund.costEvidence?.score ?? 0,
          totalAnnualFee: fund.costEvidence?.totalAnnualFee ?? null,
          purchaseFeeRate: fund.costEvidence?.purchaseFeeRate ?? null,
          salesServiceFeeRate: fund.costEvidence?.salesServiceFeeRate ?? null,
        },
        siblingCount: info.siblingCount,
        siblingCodes: info.siblingCodes || [],
        bestCostCode: info.siblingBestCostCode,
        bestCostLabel: info.siblingBestCostLabel,
        currentIsBestCost,
        plannedAmount: preferences.plannedAmount,
        currentOneYearKnownCost: currentCost?.oneYearKnownCost ?? null,
        bestOneYearKnownCost: bestKnownCost?.oneYearKnownCost ?? null,
        bestKnownCostCode: bestKnownCost?.windCode ?? null,
        executableBestKnownCost: executableBestKnownCost?.oneYearKnownCost ?? null,
        executableBestKnownCostCode: executableBestKnownCost?.windCode ?? null,
        costDeltaToBest,
        amountGateStatus: currentAmountGate?.status || 'unknown',
        amountGateLabel,
        amountGateDetail,
        amountGateAdvice,
        amountGateActionLabel: currentAmountGate?.actionLabel || '补金额规则',
        amountGateShortfallAmount: currentAmountGate?.shortfallAmount ?? null,
        amountGateSuggestedAmount: currentAmountGate?.suggestedAmount ?? null,
        amountBlockedCount,
        amountUnknownCount,
        costComparisons: costComparisons.slice(0, 4),
        decision: currentAmountGate?.status === 'blocked'
          ? `当前份额金额不匹配：${amountGateDetail} 不能作为正式推荐，先调整计划金额或换可执行份额。`
          : currentAmountGate?.status !== 'pass'
            ? `当前份额金额门禁待补：${amountGateDetail} 不能把低成本排序当成正式推荐。`
            : currentIsBestCost
              ? `当前样本成本证据暂优且计划金额可执行；按 ${preferences.plannedAmount.toLocaleString('zh-CN')} 元估算，仍需核对销售平台实时申购费、销售服务费和赎回费。`
              : costDeltaToBest !== null && costDeltaToBest > 0
                ? `按 ${preferences.plannedAmount.toLocaleString('zh-CN')} 元计划金额估算，当前份额一年已知成本比最低份额高约 ${costDeltaToBest} 元，先做同基金份额对比。`
                : '当前样本不是成本证据最优份额，且费用字段仍可能缺失；不能直接进入正式候选，先做同基金份额对比。',
        mustVerify: uniqueText([
          amountBlockedCount ? `${amountBlockedCount} 个份额未通过当前计划金额门禁，不能作为正式推荐` : '',
          amountUnknownCount ? `${amountUnknownCount} 个份额金额门槛待补，需先补起购/定投/限购` : '',
          'A/C/I 等份额申购费、销售服务费和赎回费差异',
          preferences.purchasePlan === 'sip' ? '定投是否支持、定投起点和长期销售服务费' : '一次性配置申购费折扣和持有期赎回费',
          '销售平台实时限购、起购金额和风险等级是否一致',
          ...(info.warnings || []),
        ]).slice(0, 5),
        comparisonHref: comparisonCodes.length >= 2
          ? `/analysis/comparison?${new URLSearchParams({
            codes: comparisonCodes.join(','),
            profile: safeProfile,
            horizon: preferences.horizon,
            purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
            autoReplay: '1',
          }).toString()}`
          : '',
      }
    })
    .filter((item: any) => {
      if (seenGroups.has(item.groupKey)) return false
      seenGroups.add(item.groupKey)
      return true
    })
    .sort((left: any, right: any) => Number(left.currentIsBestCost) - Number(right.currentIsBestCost)
      || right.current.investorScore - left.current.investorScore)
    .slice(0, 4)
}

function buildShareClassEvidenceGapQueue({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  return ranked
    .slice(0, 16)
    .map((fund: any) => {
      const info = fund.shareClassInfo || {}
      const classType = info.classType || '未识别'
      const salesBlocked = fund.currentSalesRuleGate?.status === 'blocked'
      const missing = uniqueText([
        classType === '未识别' ? '份额类别未识别，不能判断 A/C/I 成本差异' : '',
        (info.siblingCount || 1) < 2 ? '当前样本未发现同基金其他份额，需核对销售平台/基金合同是否存在 A/C/I/I类等份额' : '',
        fund.costEvidence?.purchaseFeeRate === null || fund.costEvidence?.purchaseFeeRate === undefined ? '申购费率待补' : '',
        fund.costEvidence?.salesServiceFeeRate === null || fund.costEvidence?.salesServiceFeeRate === undefined ? '销售服务费待补' : '',
        salesBlocked ? '销售规则硬缺口未清零，份额选择不能进入正式结论' : '',
      ])
      const checks = uniqueText([
        '核对基金全称、份额类别和同基金全部份额代码',
        preferences.purchasePlan === 'sip' ? '核对定投支持、定投起点和 C 类销售服务费' : '核对一次性配置申购费折扣和起购金额',
        '核对赎回费阶梯、最短持有期和销售平台实时限购',
        '把同基金份额放入横评后再比较费后成本',
      ])
      const status = classType === '未识别'
        ? 'unrecognized'
        : salesBlocked
          ? 'sales_rule_blocked'
          : (info.siblingCount || 1) < 2
            ? 'single_sample'
            : 'cost_gap'

      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type || '未分类',
        investorScore: fund.investorScore,
        baseName: info.baseName || normalizeShareClassBaseName(fund.name) || fund.name,
        classType,
        siblingCount: info.siblingCount || 1,
        siblingCodes: info.siblingCodes || [],
        status,
        label: status === 'unrecognized'
          ? '份额类别待识别'
          : status === 'sales_rule_blocked'
            ? '销售规则阻断份额判断'
            : status === 'single_sample'
              ? '同基金份额待核'
              : '成本字段待补',
        hint: info.hint || '份额证据未闭环，不能直接按当前样本做份额选择。',
        missing,
        checks,
        actionHref: `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
      }
    })
    .filter((item: any) => item.missing.length)
    .sort((left: any, right: any) => {
      const rank: Record<string, number> = { unrecognized: 0, sales_rule_blocked: 1, single_sample: 2, cost_gap: 3 }
      return rank[left.status] - rank[right.status] || right.investorScore - left.investorScore
    })
    .slice(0, 6)
}

function costAmountByRate(amount: number, rate: number | null | undefined) {
  const value = asNumber(rate)
  return value === null ? null : Math.round(amount * value / 100)
}

function estimateShareClassOneYearCost(fund: any, amount: number, executionAmountGate: SalesRuleExecutionAmountGate | null = null) {
  const cost = fund.costEvidence || {}
  const annualFeeAmount = costAmountByRate(amount, cost.totalAnnualFee)
  const purchaseFeeAmount = costAmountByRate(amount, cost.purchaseFeeRate)
  const knownParts = [annualFeeAmount, purchaseFeeAmount]
    .filter((value): value is number => value !== null)
  const missing = uniqueText([
    cost.totalAnnualFee === null || cost.totalAnnualFee === undefined ? '年化费率' : '',
    cost.purchaseFeeRate === null || cost.purchaseFeeRate === undefined ? '申购费' : '',
    cost.hasRedemptionRules ? '' : '赎回费/持有期',
  ])
  return {
    windCode: fund.windCode,
    name: fund.name,
    classType: inferShareClass(fund.name) || '未知',
    amount,
    annualFeeAmount,
    purchaseFeeAmount,
    oneYearKnownCost: knownParts.length ? knownParts.reduce((sum, value) => sum + value, 0) : null,
    missing,
    executionAmountGate,
    amountGateStatus: executionAmountGate?.status || 'unknown',
    amountGateLabel: executionAmountGate?.label || '金额门槛待补',
    amountGateDetail: executionAmountGate?.detail || '未取得销售规则金额门禁，不能判断当前计划金额是否可执行。',
    amountGateAdvice: executionAmountGate?.advice || '先补销售平台起购、定投起点和限购金额，再判断当前计划金额是否可执行。',
    amountGateActionLabel: executionAmountGate?.actionLabel || '补金额规则',
    amountGateShortfallAmount: executionAmountGate?.shortfallAmount ?? null,
    amountGateSuggestedAmount: executionAmountGate?.suggestedAmount ?? null,
  }
}

function buildCostDragQueue({
  ranked,
  preferences,
}: {
  ranked: any[]
  preferences: InvestorPreferences
}) {
  const amount = preferences.plannedAmount
  return ranked
    .filter((fund: any) => fund.purchaseGate?.level !== 'blocked')
    .slice(0, 8)
    .map((fund: any) => {
      const cost = fund.costEvidence || {}
      const executionAmountGate = fund.executionAmountGate || fund.currentSalesRuleGate?.executionAmountGate || null
      const annualFeeAmount = costAmountByRate(amount, cost.totalAnnualFee)
      const purchaseFeeAmount = costAmountByRate(amount, cost.purchaseFeeRate)
      const salesServiceFeeAmount = costAmountByRate(amount, cost.salesServiceFeeRate)
      const knownCostParts = [annualFeeAmount, purchaseFeeAmount, salesServiceFeeAmount]
        .filter((value): value is number => value !== null)
      const oneYearKnownCost = knownCostParts.length
        ? knownCostParts.reduce<number>((sum, value) => sum + value, 0)
        : null
      const missing = cost.missing || []
      const coverage = missing.length === 0
        ? 'full'
        : missing.length <= 2
          ? 'partial'
        : 'thin'
      const explainLines = uniqueText([
        executionAmountGate ? `计划金额门禁：${executionAmountGate.label}；${executionAmountGate.detail}` : '计划金额门禁待扫描；不能把成本排序当成正式研究结论。',
        `按计划金额 ${amount.toLocaleString('zh-CN')} 元估算：年化管理/托管/销售服务费约 ${annualFeeAmount === null ? '待补' : `${annualFeeAmount} 元`}。`,
        `申购费约 ${purchaseFeeAmount === null ? '待补' : `${purchaseFeeAmount} 元`}；赎回费需结合持有期规则复核。`,
        preferences.purchasePlan === 'sip'
          ? `定投口径：${cost.supportsSip === true ? `支持，起点 ${cost.minSipAmount ?? '待补'} 元` : '定投支持待补或不支持'}。`
          : `一次性配置口径：起购 ${cost.minPurchaseAmount ?? '待补'} 元，限购 ${cost.dailyLimitAmount ?? '待补'} 元。`,
      ])
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type,
        investorScore: fund.investorScore,
        costScore: cost.score ?? 0,
        costLabel: cost.label || '成本待补',
        amount,
        annualFeeAmount,
        purchaseFeeAmount,
        salesServiceFeeAmount,
        oneYearKnownCost,
        knownCostPartCount: knownCostParts.length,
        coverage,
        executionAmountGate,
        amountGateStatus: executionAmountGate?.status || 'unknown',
        amountGateLabel: executionAmountGate?.label || '金额门槛待补',
        amountGateDetail: executionAmountGate?.detail || '未取得销售规则金额门禁，不能判断当前计划金额是否可执行。',
        amountGateAdvice: executionAmountGate?.advice || '先补销售平台起购、定投起点和限购金额，再判断当前计划金额是否可执行。',
        amountGateActionLabel: executionAmountGate?.actionLabel || '补金额规则',
        amountGateShortfallAmount: executionAmountGate?.shortfallAmount ?? null,
        amountGateSuggestedAmount: executionAmountGate?.suggestedAmount ?? null,
        missing,
        explainLines,
        actionHref: `/funds/${encodeURIComponent(fund.id || fund.windCode)}?horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
      }
    })
    .sort((left: any, right: any) => {
      const coverageRank: Record<string, number> = { full: 0, partial: 1, thin: 2 }
      return amountGateRank(left.executionAmountGate) - amountGateRank(right.executionAmountGate)
        || coverageRank[left.coverage] - coverageRank[right.coverage]
        || (left.oneYearKnownCost ?? 999999) - (right.oneYearKnownCost ?? 999999)
        || right.investorScore - left.investorScore
    })
    .slice(0, 4)
}

function buildPressureTestQueue({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  const amount = preferences.plannedAmount
  const riskBudget = resolveRiskBudget(safeProfile, preferences)
  const budgetLossAmount = Math.round(amount * riskBudget)
  return ranked
    .filter((fund: any) => fund.purchaseGate?.level !== 'blocked')
    .slice(0, 8)
    .map((fund: any) => {
      const drawdown = fund.maxDrawdown === null ? null : Math.abs(fund.maxDrawdown)
      const historicalLossAmount = drawdown === null ? null : Math.round(amount * drawdown)
      const excessLossAmount = historicalLossAmount === null ? null : Math.max(0, historicalLossAmount - budgetLossAmount)
      const recoveryReturnRequired = drawdown === null || drawdown >= 1 ? null : drawdown / (1 - drawdown)
      const stressRatio = drawdown === null ? null : Math.round(clamp((drawdown / riskBudget) * 100, 0, 200))
      const status = drawdown === null
        ? 'missing'
        : drawdown <= riskBudget * 0.7
          ? 'within'
          : drawdown <= riskBudget
            ? 'near'
            : 'over'
      const recoveryDifficulty = recoveryReturnRequired === null
        ? 'missing'
        : recoveryReturnRequired <= 0.08
          ? 'easy'
          : recoveryReturnRequired <= 0.18
            ? 'moderate'
            : recoveryReturnRequired <= 0.35
              ? 'hard'
              : 'severe'
      const recoveryLabel = recoveryDifficulty === 'missing'
        ? '回本待补'
        : recoveryDifficulty === 'easy'
          ? '回本压力低'
          : recoveryDifficulty === 'moderate'
            ? '回本压力中等'
            : recoveryDifficulty === 'hard'
              ? '回本压力高'
              : '回本压力极高'
      const recoveryWarning = recoveryReturnRequired === null
        ? '缺少最大回撤，无法估算回本所需涨幅。'
        : `若经历该历史回撤，回本所需涨幅为 ${formatPercent(recoveryReturnRequired)}。`
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type,
        investorScore: fund.investorScore,
        amount,
        maxDrawdown: fund.maxDrawdown,
        historicalLossAmount,
        budgetLossAmount,
        excessLossAmount,
        recoveryReturnRequired,
        recoveryDifficulty,
        recoveryLabel,
        recoveryWarning,
        stressRatio,
        status,
        label: status === 'within'
          ? '低于预算'
          : status === 'near'
            ? '接近预算'
            : status === 'over'
              ? '超过预算'
              : '回撤待补',
        note: drawdown === null
          ? `最大回撤缺失，不能估算 ${amount.toLocaleString('zh-CN')} 元计划金额的潜在浮亏。`
          : `历史最大回撤按 ${amount.toLocaleString('zh-CN')} 元计划金额约 ${historicalLossAmount} 元浮亏，当前画像预算约 ${budgetLossAmount} 元；${recoveryWarning}`,
        actionHref: `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
      }
    })
    .sort((left: any, right: any) => {
      const statusRank: Record<string, number> = { over: 0, near: 1, missing: 2, within: 3 }
      return statusRank[left.status] - statusRank[right.status]
        || (right.historicalLossAmount ?? -1) - (left.historicalLossAmount ?? -1)
        || right.investorScore - left.investorScore
    })
    .slice(0, 4)
}

function horizonDaysFor(preferences: InvestorPreferences) {
  if (preferences.horizon === 'lt1y') return 180
  if (preferences.horizon === '1to3y') return 365
  return 1095
}

function normalizeRedemptionRules(rules: RedemptionFeeRule[]): NormalizedRedemptionRule[] {
  return rules
    .map((rule) => ({
      holdingDays: asNumber(rule.holdingDays),
      feeRate: asNumber(rule.feeRate),
      label: rule.label || '赎回费率',
    }))
    .filter((rule): rule is NormalizedRedemptionRule => rule.feeRate !== null)
    .sort((left, right) => (left.holdingDays ?? 0) - (right.holdingDays ?? 0))
}

function redemptionRuleAtHorizon(rules: RedemptionFeeRule[], horizonDays: number) {
  const normalizedRules = normalizeRedemptionRules(rules)
  if (!normalizedRules.length) return null
  return normalizedRules.find((rule) => rule.holdingDays === null || horizonDays <= rule.holdingDays)
    || normalizedRules[normalizedRules.length - 1]
}

function buildRedemptionFeeLadder(rules: RedemptionFeeRule[], horizonDays: number, amount: number) {
  const normalizedRules = normalizeRedemptionRules(rules)
  const currentRule = redemptionRuleAtHorizon(rules, horizonDays)
  return normalizedRules.map((rule) => ({
    holdingDays: rule.holdingDays,
    feeRate: rule.feeRate,
    label: rule.label,
    feeAmount: costAmountByRate(amount, rule.feeRate),
    isCurrent: Boolean(currentRule && currentRule.holdingDays === rule.holdingDays && currentRule.feeRate === rule.feeRate && currentRule.label === rule.label),
    daysUntilEffective: rule.holdingDays === null ? null : Math.max(0, rule.holdingDays - horizonDays),
    unlockLabel: rule.holdingDays === null
      ? rule.label
      : horizonDays <= rule.holdingDays
        ? `当前约 ${horizonDays} 天命中`
        : `已超过 ${rule.holdingDays} 天节点`,
  }))
}

function nextRedemptionFeeCut(rules: RedemptionFeeRule[], horizonDays: number, amount: number) {
  const currentRule = redemptionRuleAtHorizon(rules, horizonDays)
  if (!currentRule) return null
  const nextRule = normalizeRedemptionRules(rules)
    .filter((rule) => rule.holdingDays !== null && rule.holdingDays > horizonDays && rule.feeRate < currentRule.feeRate)
    .sort((left, right) => (left.holdingDays ?? 0) - (right.holdingDays ?? 0))[0]
  if (!nextRule || nextRule.holdingDays === null) return null
  const currentFeeAmount = costAmountByRate(amount, currentRule.feeRate)
  const nextFeeAmount = costAmountByRate(amount, nextRule.feeRate)
  return {
    nextFeeCutDays: nextRule.holdingDays,
    nextFeeCutFeeRate: nextRule.feeRate,
    nextFeeCutFeeAmount: nextFeeAmount,
    nextFeeCutSavingAmount: Math.max(0, Math.round(((currentFeeAmount ?? 0) - (nextFeeAmount ?? 0)) * 100) / 100),
    nextFeeCutLabel: nextRule.label,
  }
}

function buildRedemptionHoldingRiskQueue({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  const amount = preferences.plannedAmount
  const horizonDays = horizonDaysFor(preferences)
  return ranked
    .filter((fund: any) => fund.purchaseGate?.level !== 'blocked')
    .slice(0, 10)
    .map((fund: any) => {
      const salesRule = fund.salesRule || {}
      const rawRules = Array.isArray(salesRule.redemptionFeeRules) ? salesRule.redemptionFeeRules : []
      const rules = hasSourceBackedRedemptionRules(salesRule, rawRules) ? rawRules : []
      const rule = redemptionRuleAtHorizon(rules, horizonDays)
      const redemptionFeeAmount = rule ? costAmountByRate(amount, rule.feeRate) : null
      const redemptionFeeLadder = buildRedemptionFeeLadder(rules, horizonDays, amount)
      const feeCut = nextRedemptionFeeCut(rules, horizonDays, amount)
      const redeemStatus = fund.operationStatus?.redeem_status || fund.operationStatus?.redeemStatus || salesRule.redeemStatus || null
      const hasRules = rules.length > 0
      const missing = uniqueText([
        hasRules ? '' : '赎回费/持有期',
        redeemStatus ? '' : '赎回开放状态',
        fund.currentSalesRuleGate?.missingItems?.some((item: string) => item.includes('来源日期')) ? '销售规则来源日期' : '',
      ])
      const hardBlocks = uniqueText([
        fund.currentSalesRuleGate?.status === 'blocked' ? '销售规则硬缺口未清零' : '',
        typeof redeemStatus === 'string' && /暂停|关闭|不可|停止/.test(redeemStatus) ? `赎回状态异常：${redeemStatus}` : '',
      ])
      const status = hardBlocks.length
        ? 'blocked'
        : missing.length
          ? 'pending'
          : rule && rule.feeRate > 0.5 && preferences.horizon === 'lt1y'
            ? 'costly'
            : 'ready'
      const checks = uniqueText([
        `计划持有期：${preferences.horizonLabel}，按约 ${horizonDays} 天做赎回规则压力检查`,
        rule ? `匹配规则：${rule.label}，费率 ${rule.feeRate.toFixed(2)}%` : '赎回费率与持有天数规则待补',
        redemptionFeeAmount === null ? `计划金额 ${amount.toLocaleString('zh-CN')} 元赎回成本待补` : `计划金额 ${amount.toLocaleString('zh-CN')} 元赎回成本约 ${redemptionFeeAmount} 元`,
        feeCut ? `再持有到 ${feeCut.nextFeeCutDays} 天，赎回费可能降至 ${feeCut.nextFeeCutFeeRate.toFixed(2)}%，计划金额可少付 ${feeCut.nextFeeCutSavingAmount} 元；需以销售平台实时规则为准。` : rule && rule.feeRate === 0 ? '当前计划持有期下赎回费率为 0%，仍需核销售平台实时规则。' : hasRules ? '未发现更低费率阶梯；继续补合同/销售平台规则。' : '',
        redeemStatus ? `赎回开放状态：${redeemStatus}` : '赎回开放状态待补',
      ])
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type,
        investorScore: fund.investorScore,
        status,
        label: status === 'ready'
          ? '赎回规则可复核'
          : status === 'costly'
            ? '短持成本偏高'
            : status === 'pending'
              ? '赎回规则待补'
              : '赎回硬阻断',
        horizonDays,
        amount,
        redemptionFeeRate: rule?.feeRate ?? null,
        redemptionFeeAmount,
        redemptionRuleLabel: rule?.label || null,
        redemptionFeeLadder,
        nextFeeCutDays: feeCut?.nextFeeCutDays ?? null,
        nextFeeCutFeeRate: feeCut?.nextFeeCutFeeRate ?? null,
        nextFeeCutFeeAmount: feeCut?.nextFeeCutFeeAmount ?? null,
        nextFeeCutSavingAmount: feeCut?.nextFeeCutSavingAmount ?? null,
        nextFeeCutLabel: feeCut?.nextFeeCutLabel ?? null,
        redeemStatus,
        missing,
        hardBlocks,
        checks,
        actionHref: status === 'ready' || status === 'costly'
          ? `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`
          : salesRulesHrefForCodes(fund.windCode, preferences.purchasePlan, preferences.plannedAmount, `/market?source=research-candidates&profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}&eligibleOnly=true&requireSalesRule=true`),
      }
    })
    .sort((left: any, right: any) => {
      const rank: Record<string, number> = { blocked: 0, pending: 1, costly: 2, ready: 3 }
      return rank[left.status] - rank[right.status]
        || (right.redemptionFeeAmount ?? -1) - (left.redemptionFeeAmount ?? -1)
        || right.investorScore - left.investorScore
    })
    .slice(0, 4)
}

function buildTypeHorizonFitQueue({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  return ranked
    .filter((fund: any) => fund.purchaseGate?.level !== 'blocked')
    .slice(0, 12)
    .map((fund: any) => {
      const fit = typeHorizonFit(fund.type, preferences, safeProfile)
      const issues = uniqueText([
        ...fit.warnings,
        fit.status === 'mismatch' ? fit.rule : '',
        fund.currentSalesRuleGate?.status === 'blocked' ? '销售规则硬缺口未清零，适配解释只能作为观察证据。' : '',
      ])
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type || '未分类',
        investorScore: fund.investorScore,
        status: fit.status,
        label: fit.label,
        fitScore: fit.score,
        horizonLabel: preferences.horizonLabel,
        profileLabel: profileLabel[safeProfile],
        rule: fit.rule,
        action: fit.action,
        issues,
        actionHref: fit.status === 'fit' && fund.currentSalesRuleGate?.status !== 'blocked'
          ? `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`
          : `/analysis/comparison?${new URLSearchParams({
            codes: ranked
              .filter((item: any) => item.windCode !== fund.windCode && (item.type || '未分类') === (fund.type || '未分类'))
              .slice(0, 3)
              .map((item: any) => item.windCode)
              .concat(fund.windCode)
              .slice(0, 4)
              .join(','),
            profile: safeProfile,
            horizon: preferences.horizon,
            purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
            autoReplay: '1',
          }).toString()}`,
      }
    })
    .sort((left: any, right: any) => {
      const rank: Record<string, number> = { mismatch: 0, explain: 1, fit: 2 }
      return rank[left.status] - rank[right.status]
        || left.fitScore - right.fitScore
        || right.investorScore - left.investorScore
    })
    .slice(0, 4)
}

function scaleLiquidityRisk(totalAsset: number | null, fundType: string | null | undefined) {
  const type = fundType || '未分类'
  if (totalAsset === null || totalAsset <= 0) {
    return {
      status: 'missing' as const,
      label: '规模待补',
      score: 0,
      hardBlocks: [] as string[],
      warnings: ['基金规模缺失，无法判断容量、流动性和清盘风险。'],
      rule: '研究复核必须补基金规模；缺规模时不能把收益排名当作研究依据。',
    }
  }
  if (totalAsset < 2) {
    return {
      status: 'blocked' as const,
      label: '清盘风险先排除',
      score: 10,
      hardBlocks: ['基金规模低于 2 亿，清盘和流动性风险需先排除。'],
      warnings: [`当前规模 ${totalAsset.toFixed(2)} 亿，低于研究硬门槛。`],
      rule: '规模低于 2 亿默认不进入正式研究候选，除非有明确规模回升、机构支持和替代横评证据。',
    }
  }
  if (totalAsset < 5) {
    return {
      status: 'thin' as const,
      label: '小微规模谨慎',
      score: 45,
      hardBlocks: [] as string[],
      warnings: [`当前规模 ${totalAsset.toFixed(2)} 亿，需关注清盘线、赎回冲击和持有人结构。`],
      rule: '2-5 亿基金只适合作观察或小额验证，正式研究复核需补规模趋势、持有人集中度和同类替代。',
    }
  }
  if (totalAsset > 300 && ['主动权益', '混合型', '股票型'].some((keyword) => type.includes(keyword))) {
    return {
      status: 'capacity' as const,
      label: '超大规模看容量',
      score: 70,
      hardBlocks: [] as string[],
      warnings: [`当前规模 ${totalAsset.toFixed(2)} 亿，主动管理需复核策略容量和超额收益衰减。`],
      rule: '超大规模主动基金不能只看历史收益，要检查超额收益、换手、持仓集中度和同类大规模替代。',
    }
  }
  return {
    status: 'healthy' as const,
    label: '规模相对健康',
    score: totalAsset >= 30 && totalAsset <= 300 ? 90 : 75,
    hardBlocks: [] as string[],
    warnings: [] as string[],
    rule: '规模处于可研究区间；仍需结合申赎状态、持有人结构和同类容量比较。',
  }
}

function buildScaleLiquidityRiskQueue({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  return ranked
    .slice(0, 12)
    .map((fund: any) => {
      const totalAsset = asNumber(fund.totalAsset)
      const risk = scaleLiquidityRisk(totalAsset, fund.type)
      const salesBlocked = fund.currentSalesRuleGate?.status === 'blocked'
      const actionHref = risk.status === 'blocked' || risk.status === 'missing' || salesBlocked
        ? `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`
        : `/analysis/comparison?${new URLSearchParams({
          codes: uniqueText([
            fund.windCode,
            ...ranked
              .filter((item: any) => item.windCode !== fund.windCode && (item.type || '未分类') === (fund.type || '未分类'))
              .slice(0, 3)
              .map((item: any) => item.windCode),
          ]).slice(0, 4).join(','),
          profile: safeProfile,
          horizon: preferences.horizon,
          purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
          autoReplay: '1',
        }).toString()}`

      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type || '未分类',
        investorScore: fund.investorScore,
        totalAsset,
        status: risk.status,
        label: risk.label,
        riskScore: risk.score,
        hardBlocks: risk.hardBlocks,
        warnings: uniqueText([
          ...risk.warnings,
          salesBlocked ? '销售规则硬缺口未清零，规模判断只能作为研究风险提示。' : '',
        ]),
        rule: risk.rule,
        nextAction: risk.status === 'blocked'
          ? '先排除或补规模趋势证据，不进入正式研究候选。'
          : risk.status === 'missing'
            ? '先补基金规模字段，再判断是否存在清盘/流动性风险。'
            : risk.status === 'thin'
              ? '补规模趋势、机构持有人和同类替代后再决定是否推进。'
              : risk.status === 'capacity'
                ? '做同类大规模基金横评，确认规模没有拖累超额收益。'
                : '可进入同类横评和详情复核，但研究复核仍需确认实时申赎状态。',
        actionHref,
      }
    })
    .sort((left: any, right: any) => {
      const rank: Record<string, number> = { blocked: 0, missing: 1, thin: 2, capacity: 3, healthy: 4 }
      return rank[left.status] - rank[right.status]
        || left.riskScore - right.riskScore
        || right.investorScore - left.investorScore
    })
    .slice(0, 4)
}

async function fetchHoldingExposureMap(funds: any[], origin: string) {
  const codes = Array.from(new Set(
    funds
      .map((fund: any) => String(fund.windCode || '').trim().toUpperCase())
      .filter(Boolean),
  )).slice(0, 8)
  const entries = await Promise.all(codes.map(async (windCode) => {
    try {
      const response = await fetch(`${origin}/api/funds/${encodeURIComponent(windCode)}/holdings`, {
        cache: 'no-store',
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        return [windCode, {
          status: 'unavailable',
          windCode,
          holdings: [],
          industryBuckets: [],
          totalWeight: null,
          note: payload.detail || payload.error || '读取持仓失败',
        } satisfies HoldingExposureEvidence] as const
      }
      return [windCode, payload as HoldingExposureEvidence] as const
    } catch (error) {
      return [windCode, {
        status: 'unavailable',
        windCode,
        holdings: [],
        industryBuckets: [],
        totalWeight: null,
        note: error instanceof Error ? error.message : '读取持仓失败',
      } satisfies HoldingExposureEvidence] as const
    }
  }))
  return new Map(entries)
}

function buildHoldingExposureDecision(
  holdingEvidence: HoldingExposureEvidence | null | undefined,
  safeProfile: RiskProfile,
) {
  const concentrationBudget = safeProfile === 'conservative' ? 0.45 : safeProfile === 'balanced' ? 0.6 : 0.75
  const industryBudget = safeProfile === 'conservative' ? 0.3 : safeProfile === 'balanced' ? 0.4 : 0.5
  if (!holdingEvidence || holdingEvidence.status !== 'available') {
    return {
      status: 'missing' as const,
      label: '持仓暴露待补',
      score: 20,
      topTenWeight: null,
      topIndustryWeight: null,
      topIndustry: '行业待补',
      topStock: '重仓待补',
      primaryRisk: '缺少可信季报持仓，不能解释行业/个股暴露',
      nextAction: '补齐最新季报持仓后，再判断集中度和风格暴露是否支持研究结论。',
      reasons: [
        holdingEvidence?.note || '未取得可验证持仓，暂不做行业/个股暴露判断。',
        `已检查季度：${holdingEvidence?.checkedQuarters?.join(' / ') || '待补'}`,
        `已拦截疑似样例季度：${holdingEvidence?.rejectedMockLikeQuarters?.length || 0}`,
      ],
      hardBlocks: [] as string[],
      warnings: ['持仓缺失时不能把行业分散度、重仓风险或风格一致性默认为正常。'],
    }
  }

  const topTenWeight = holdingEvidence.totalWeight ?? null
  const sortedIndustries = [...(holdingEvidence.industryBuckets || [])].sort((left, right) => right.weight - left.weight)
  const topIndustry = sortedIndustries[0] || null
  const topIndustryWeight = topIndustry?.weight ?? null
  const topStock = (holdingEvidence.holdings || []).slice().sort((left, right) => (right.weight ?? 0) - (left.weight ?? 0))[0] || null
  const topTenRisk = topTenWeight !== null && topTenWeight > concentrationBudget
  const industryRisk = topIndustryWeight !== null && topIndustryWeight > industryBudget
  const thinHoldings = (holdingEvidence.holdings || []).length < 10
  const thinIndustries = (holdingEvidence.industryBuckets || []).length < 3
  const score = Math.round(clamp(
    82
      - (topTenRisk ? 22 : topTenWeight !== null && topTenWeight > concentrationBudget * 0.8 ? 10 : 0)
      - (industryRisk ? 18 : topIndustryWeight !== null && topIndustryWeight > industryBudget * 0.85 ? 8 : 0)
      - (thinHoldings ? 10 : 0)
      - (thinIndustries ? 8 : 0),
    0,
    100,
  ))
  const hardBlocks = uniqueText([
    topTenRisk ? `前十大权重 ${formatPercent(topTenWeight)} 超过${profileLabel[safeProfile]}集中度预算 ${formatPercent(concentrationBudget)}` : '',
    industryRisk ? `${topIndustry?.industry || '第一行业'}权重 ${formatPercent(topIndustryWeight)} 超过行业预算 ${formatPercent(industryBudget)}` : '',
  ])
  const warnings = uniqueText([
    thinHoldings ? '持仓数量不足 10 条，前十大集中度解释可能不完整。' : '',
    thinIndustries ? '行业桶少于 3 个，需确认是否主题基金或行业过度集中。' : '',
    topTenWeight !== null && topTenWeight > concentrationBudget * 0.8 && !topTenRisk ? '前十大权重接近当前画像预算。' : '',
    topIndustryWeight !== null && topIndustryWeight > industryBudget * 0.85 && !industryRisk ? '第一行业权重接近当前画像预算。' : '',
  ])
  const status = hardBlocks.length ? 'concentrated' as const : warnings.length ? 'watch' as const : 'usable' as const
  const label = hardBlocks.length
    ? '暴露集中，先解释风险来源'
    : score >= 72
      ? '持仓暴露可用于研究判断'
      : '持仓暴露可观察'
  const primaryRisk = hardBlocks.length ? hardBlocks.join('；') : '未发现超出当前画像预算的集中度信号'

  return {
    status,
    label,
    score,
    topTenWeight,
    topIndustryWeight,
    topIndustry: topIndustry?.industry || '行业待补',
    topStock: topStock?.stockName || topStock?.stockCode || '重仓待补',
    primaryRisk,
    nextAction: hardBlocks.length
      ? '先解释重仓行业/个股风险，再进入研究清单、横向比较或研究复核报告。'
      : '复核最新季报是否延续当前暴露，再与同类基金横向比较。',
    reasons: [
      `持仓季度 ${holdingEvidence.quarter || '待补'}，前十大合计 ${formatPercent(topTenWeight)}`,
      `第一行业 ${topIndustry?.industry || '待补'} ${formatPercent(topIndustryWeight)}，行业桶 ${(holdingEvidence.industryBuckets || []).length} 个`,
      topStock ? `第一重仓 ${topStock.stockName || topStock.stockCode || '名称待补'} ${formatPercent(topStock.weight ?? null)}` : '第一重仓待补',
      `可信过滤来源：${holdingEvidence.source || 'backend.tushare.fund_portfolio.filtered'}`,
    ],
    hardBlocks,
    warnings,
  }
}

function buildHoldingExposureRiskQueue({
  ranked,
  holdingExposureMap,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  holdingExposureMap: Awaited<ReturnType<typeof fetchHoldingExposureMap>>
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  return ranked
    .slice(0, 8)
    .map((fund: any) => {
      const evidence = holdingExposureMap.get(String(fund.windCode || '').toUpperCase()) || null
      const decision = buildHoldingExposureDecision(evidence, safeProfile)
      const comparisonCodes = uniqueText([
        fund.windCode,
        ...ranked
          .filter((item: any) => item.windCode !== fund.windCode && (item.type || '未分类') === (fund.type || '未分类'))
          .slice(0, 3)
          .map((item: any) => item.windCode),
      ]).slice(0, 4)
      const comparisonHref = comparisonCodes.length >= 2
        ? `/analysis/comparison?${new URLSearchParams({
          codes: comparisonCodes.join(','),
          profile: safeProfile,
          horizon: preferences.horizon,
          purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
          autoReplay: '1',
        }).toString()}`
        : ''
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type || '未分类',
        investorScore: fund.investorScore,
        holdingStatus: evidence?.status || 'unavailable',
        quarter: evidence?.quarter || null,
        label: decision.label,
        status: decision.status,
        score: decision.score,
        topTenWeight: decision.topTenWeight,
        topIndustryWeight: decision.topIndustryWeight,
        topIndustry: decision.topIndustry,
        topStock: decision.topStock,
        primaryRisk: decision.primaryRisk,
        nextAction: decision.nextAction,
        reasons: decision.reasons,
        hardBlocks: decision.hardBlocks,
        warnings: decision.warnings,
        actionHref: decision.status === 'missing'
          ? `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`
          : comparisonHref || `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
        comparisonHref,
      }
    })
    .sort((left: any, right: any) => {
      const rank: Record<string, number> = { concentrated: 0, missing: 1, watch: 2, usable: 3 }
      return rank[left.status] - rank[right.status]
        || left.score - right.score
        || right.investorScore - left.investorScore
    })
    .slice(0, 4)
}

function buildStrictCandidateUnlockBoard({
  ranked,
  salesRuleUnlockPreview,
  managerAttributionQueue,
  redemptionHoldingRiskQueue,
  typeHorizonFitQueue,
  executionFeasibilityQueue,
  evidenceFreshnessQueue,
  costDragQueue,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  salesRuleUnlockPreview: {
    nearPurchasableQueue?: Array<{ windCode: string; name: string; missingCount: number; missingItems: string[]; investorScore: number; actionHref: string }>
    bulkSalesRulesHref?: string
    strictReviewHref?: string
    unlockableCount?: number
  }
  managerAttributionQueue: any[]
  redemptionHoldingRiskQueue: any[]
  typeHorizonFitQueue: any[]
  executionFeasibilityQueue: any[]
  evidenceFreshnessQueue: any[]
  costDragQueue: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  const salesRuleEvidenceCopy = salesRuleEvidenceCopyForPlan(preferences.purchasePlan)
  const salesRuleItems = salesRuleUnlockPreview.nearPurchasableQueue || []
  const evidenceItems = evidenceFreshnessQueue.filter((item: any) => item.status !== 'fresh')
  const executionItems = executionFeasibilityQueue.filter((item: any) => item.status !== 'ready')
  const managerItems = managerAttributionQueue.filter((item: any) => item.status !== 'stable')
  const redemptionItems = redemptionHoldingRiskQueue.filter((item: any) => item.status !== 'ready')
  const typeFitItems = typeHorizonFitQueue.filter((item: any) => item.status !== 'fit')
  const costItems = costDragQueue.filter((item: any) => item.coverage !== 'full')
  const salesRulesHref = salesRuleUnlockPreview.bulkSalesRulesHref || materialEvidenceHref()
  const strictReviewHref = salesRuleUnlockPreview.strictReviewHref || `/market?source=research-candidates&${new URLSearchParams({
    profile: safeProfile,
    horizon: preferences.horizon,
    purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
    eligibleOnly: 'true',
    requireSalesRule: 'true',
    minEvidenceGrade: 'B',
  }).toString()}`
  const lanes = [
    {
      key: 'sales_rules',
      label: '先补销售规则',
      priority: 1,
      count: salesRuleItems.length,
      blocker: salesRuleItems[0]
        ? `${salesRuleItems[0].name || salesRuleItems[0].windCode} 缺 ${salesRuleItems[0].missingCount || 0} 项：${(salesRuleItems[0].missingItems || []).slice(0, 3).join('、') || '销售端硬字段'}`
        : '当前销售规则近可解锁队列为空',
      nextAction: `批量补齐${salesRuleEvidenceCopy.fields}，补完后严格重评。`,
      actionHref: salesRulesHref,
      sampleCodes: salesRuleItems.slice(0, 4).map((item: any) => item.windCode),
    },
    {
      key: 'evidence',
      label: '再核证据时效',
      priority: 2,
      count: evidenceItems.length,
      blocker: evidenceItems[0]
        ? `${evidenceItems[0].name}：${evidenceItems[0].issues.slice(0, 3).join('、') || evidenceItems[0].label}`
        : '净值日期、销售规则来源日期和研究证据未见首要缺口',
      nextAction: '把过旧或缺失来源更新到 30 天内，避免旧证据进入正式研究复核报告。',
      actionHref: evidenceItems[0]?.actionHref || strictReviewHref,
      sampleCodes: evidenceItems.slice(0, 4).map((item: any) => item.windCode),
    },
    {
      key: 'execution',
      label: '确认申赎规则',
      priority: 3,
      count: executionItems.length,
      blocker: executionItems[0]
        ? `${executionItems[0].name}：${executionItems[0].hardBlocks?.[0] || executionItems[0].pendingItems?.slice(0, 3).join('、') || executionItems[0].label}`
        : salesRuleEvidenceCopy.executionCleanDetail,
      nextAction: `${salesRuleEvidenceCopy.executionGoal}不可执行则只保留研究观察。`,
      actionHref: executionItems[0]?.actionHref || strictReviewHref,
      sampleCodes: executionItems.slice(0, 4).map((item: any) => item.windCode),
    },
    {
      key: 'manager',
      label: '复核经理归因',
      priority: 4,
      count: managerItems.length,
      blocker: managerItems[0]
        ? `${managerItems[0].name}：${managerItems[0].checks.slice(0, 2).join('；')}`
        : '现任经理和任期样本未见首要缺口',
      nextAction: '短任期、任期待补或经理缺失时，不把老业绩归因给现任经理。',
      actionHref: managerItems[0]?.actionHref || strictReviewHref,
      sampleCodes: managerItems.slice(0, 4).map((item: any) => item.windCode),
    },
    {
      key: 'cost',
      label: '补齐成本口径',
      priority: 5,
      count: costItems.length,
      blocker: costItems[0]
        ? `${costItems[0].name}：仍缺 ${(costItems[0].missing || []).slice(0, 3).join('、') || '费用字段'}`
        : '管理费、申购费、销售服务费等成本证据未见首要缺口',
      nextAction: '补申购费、赎回费、销售服务费和计划金额成本，防止费后排序失真。',
      actionHref: costItems[0]?.actionHref || strictReviewHref,
      sampleCodes: costItems.slice(0, 4).map((item: any) => item.windCode),
    },
    {
      key: 'redemption',
      label: '核赎回持有',
      priority: 6,
      count: redemptionItems.length,
      blocker: redemptionItems[0]
        ? `${redemptionItems[0].name}：${redemptionItems[0].hardBlocks?.[0] || redemptionItems[0].missing?.slice(0, 3).join('、') || redemptionItems[0].label}`
        : '赎回费、最短持有期和赎回开放状态未见首要缺口',
      nextAction: '短持前核赎回费和开放状态，不能用净值收益替代真实可卖出成本。',
      actionHref: redemptionItems[0]?.actionHref || strictReviewHref,
      sampleCodes: redemptionItems.slice(0, 4).map((item: any) => item.windCode),
    },
    {
      key: 'type_fit',
      label: '解释类型适配',
      priority: 7,
      count: typeFitItems.length,
      blocker: typeFitItems[0]
        ? `${typeFitItems[0].name}：${typeFitItems[0].label}，${typeFitItems[0].rule}`
        : '基金类型与当前持有期未见首要错配',
      nextAction: '短钱不买高波动、长钱不只看低收益；错配样本需先横评反证。',
      actionHref: typeFitItems[0]?.actionHref || strictReviewHref,
      sampleCodes: typeFitItems.slice(0, 4).map((item: any) => item.windCode),
    },
  ]
  const activeLanes = lanes
    .filter((lane) => lane.count > 0)
    .sort((left, right) => left.priority - right.priority)
  const primaryLane = activeLanes[0] || lanes[0]
  const formalCandidateCount = ranked.filter((fund: any) => fund.currentSalesRuleGate?.status !== 'blocked' && ['research_ready', 'watchlist'].includes(fund.purchaseGate?.level)).length

  return {
    title: formalCandidateCount ? '严格候选已有样本' : '严格候选解锁看板',
    status: formalCandidateCount ? 'has_candidates' : activeLanes.length ? 'blocked' : 'empty',
    formalCandidateCount,
    unlockableCount: salesRuleUnlockPreview.unlockableCount || 0,
    primaryLane,
    lanes,
    strictReviewHref,
    hardBoundary: '销售规则硬缺口未清零前，不能进入正式研究候选、不能保存正式研究复核报告。',
  }
}

function buildBuyBeforeLandmineBoard({
  ranked,
  returnRiskQuadrantQueue,
  performanceQualityQueue,
  scaleLiquidityRiskQueue,
  holdingExposureRiskQueue,
  managerAttributionQueue,
  redemptionHoldingRiskQueue,
  preferences,
}: {
  ranked: any[]
  returnRiskQuadrantQueue: any[]
  performanceQualityQueue: any[]
  scaleLiquidityRiskQueue: any[]
  holdingExposureRiskQueue: any[]
  managerAttributionQueue: any[]
  redemptionHoldingRiskQueue: any[]
  preferences: InvestorPreferences
}) {
  const byCode = <T extends { windCode?: string }>(items: T[]) => new Map(items.map((item) => [item.windCode, item]))
  const quadrantMap = byCode(returnRiskQuadrantQueue)
  const qualityMap = byCode(performanceQualityQueue)
  const scaleMap = byCode(scaleLiquidityRiskQueue)
  const holdingMap = byCode(holdingExposureRiskQueue)
  const managerMap = byCode(managerAttributionQueue)
  const redemptionMap = byCode(redemptionHoldingRiskQueue)

  const items = ranked.slice(0, 12).map((fund: any) => {
    const quadrant = quadrantMap.get(fund.windCode)
    const quality = qualityMap.get(fund.windCode)
    const scale = scaleMap.get(fund.windCode)
    const holding = holdingMap.get(fund.windCode)
    const manager = managerMap.get(fund.windCode)
    const redemption = redemptionMap.get(fund.windCode)
    const warningItems = [
      fund.currentSalesRuleGate?.status === 'blocked' ? {
        key: 'sales_rules',
        severity: 30,
        label: `销售规则缺 ${fund.currentSalesRuleGate?.missingCount || 0} 项`,
        detail: (fund.currentSalesRuleGate?.missingItems || []).slice(0, 3).join('、') || '申购/赎回/风险等级待补',
      } : null,
      quadrant?.quadrant === 'hot_but_volatile' || quadrant?.quadrant === 'inefficient' ? {
        key: 'return_risk',
        severity: quadrant.quadrant === 'inefficient' ? 24 : 20,
        label: quadrant.label,
        detail: quadrant.primaryRead,
      } : null,
      quality && ['blocked', 'weak', 'missing'].includes(quality.status) ? {
        key: 'quality',
        severity: quality.status === 'blocked' ? 22 : 14,
        label: quality.label,
        detail: quality.primaryRisk,
      } : null,
      scale && ['blocked', 'missing', 'thin', 'capacity'].includes(scale.status) ? {
        key: 'scale',
        severity: scale.status === 'blocked' ? 24 : 12,
        label: scale.label,
        detail: scale.hardBlocks?.[0] || scale.warnings?.[0] || scale.rule,
      } : null,
      holding && ['missing', 'concentrated'].includes(holding.status) ? {
        key: 'holding',
        severity: holding.status === 'concentrated' ? 18 : 10,
        label: holding.label,
        detail: holding.primaryRisk,
      } : null,
      manager && ['missing', 'unknown', 'short'].includes(manager.status) ? {
        key: 'manager',
        severity: manager.status === 'missing' ? 14 : 10,
        label: manager.label,
        detail: manager.checks?.slice(0, 2).join('；') || '经理归因待补',
      } : null,
      redemption && ['blocked', 'costly', 'pending'].includes(redemption.status) ? {
        key: 'redemption',
        severity: redemption.status === 'blocked' ? 18 : 10,
        label: redemption.label,
        detail: redemption.hardBlocks?.[0] || redemption.missing?.slice(0, 2).join('、') || '赎回/持有期待核',
      } : null,
    ].filter(Boolean) as Array<{ key: string; severity: number; label: string; detail: string }>
    const landmineScore = Math.round(clamp(warningItems.reduce((sum, item) => sum + item.severity, 0), 0, 100))
    const level = landmineScore >= 60
      ? 'red'
      : landmineScore >= 35
        ? 'orange'
        : landmineScore > 0
          ? 'yellow'
          : 'clear'
    const label = level === 'red'
      ? '高危排雷'
      : level === 'orange'
        ? '重点排雷'
        : level === 'yellow'
          ? '轻度排雷'
          : '暂未发现主要雷点'
    return {
      windCode: fund.windCode,
      name: fund.name,
      type: fund.type || '未分类',
      investorScore: fund.investorScore,
      landmineScore,
      level,
      label,
      warningItems: warningItems.sort((left, right) => right.severity - left.severity).slice(0, 5),
      topWarning: warningItems.sort((left, right) => right.severity - left.severity)[0]?.label || '暂未发现主要雷点',
      nextAction: level === 'clear'
        ? '仍需完成销售规则、同类横评和正式报告复核。'
        : '先处理排雷项；红/橙级排雷未消除前，不进入正式研究候选。',
      actionHref: fund.currentSalesRuleGate?.status === 'blocked'
        ? salesRulesHrefForCodes(fund.windCode, preferences.purchasePlan, preferences.plannedAmount)
        : `/funds/${encodeURIComponent(fund.id || fund.windCode)}?horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
    }
  })

  return items
    .filter((item) => item.landmineScore > 0)
    .sort((left, right) => right.landmineScore - left.landmineScore || right.investorScore - left.investorScore)
    .slice(0, 6)
}

function buildSuitabilityNarrative({
  fund,
  preferences,
  safeProfile,
  landmine,
  quadrant,
}: {
  fund: any | null
  preferences: InvestorPreferences
  safeProfile: RiskProfile
  landmine?: any
  quadrant?: any
}) {
  if (!fund) return null
  const fitFor = uniqueText([
    fund.purchaseGate?.level === 'research_ready' || fund.purchaseGate?.level === 'watchlist'
      ? `适合${profileLabel[safeProfile]}、计划${preferences.horizonLabel}持有、愿意先做横评和研究复核的研究场景`
      : '',
    preferences.purchasePlan === 'sip' && fund.holdingExperience?.sipFriendlyScore >= 70
      ? `适合用${preferences.purchasePlanLabel}分散进场，而不是一次性追高`
      : '',
    quadrant?.quadrant === 'defensive' || quadrant?.quadrant === 'balanced'
      ? '适合把风险体验和收益弹性一起看的用户'
      : '',
  ])
  const notFor = uniqueText([
    fund.currentSalesRuleGate?.status === 'blocked'
      ? '不适合直接形成研究结论：销售规则硬缺口未清零'
      : '',
    landmine?.level === 'red' || landmine?.level === 'orange'
      ? `不适合跳过排雷进入正式研究候选：${landmine.topWarning}`
      : '',
    quadrant?.quadrant === 'hot_but_volatile'
      ? '不适合只看近一年收益排名、无法承受大幅波动的用户'
      : '',
    quadrant?.quadrant === 'inefficient'
      ? '不适合追求收益效率的用户，除非能解释低收益高风险的反转条件'
      : '',
    fund.riskSuitability?.status === 'mismatch'
      ? fund.riskSuitability.note
      : '',
  ])
  const proofNeeded = uniqueText([
    fund.currentSalesRuleGate?.status === 'blocked'
      ? `补销售规则：${(fund.currentSalesRuleGate?.missingItems || []).slice(0, 4).join('、')}`
      : '',
    passesEvidenceGrade(fund.purchaseGate?.evidenceGrade || 'D', 'B') ? '' : `证据等级从 ${fund.purchaseGate?.evidenceGrade || 'D'} 提升到 B`,
    fund.costEvidence?.missing?.length ? `补申赎成本：${fund.costEvidence.missing.slice(0, 4).join('、')}` : '',
    (landmine?.warningItems || []).some((item: any) => item.key === 'holding') ? '补可信季报持仓，确认行业/个股暴露' : '',
    '至少与 2-3 只同类型基金横评收益、回撤、费用和经理样本',
  ])
  const verdict = notFor.length
    ? '当前更适合观察和补证，不适合直接作为研究结论'
    : '可进入研究复核候选，但仍不是研究结论'
  return {
    windCode: fund.windCode,
    name: fund.name,
    verdict,
    fitFor: fitFor.length ? fitFor : [`适合${profileLabel[safeProfile]}在${preferences.horizonLabel}内做基金研究观察`],
    notFor: notFor.length ? notFor : ['不适合跳过销售平台适当性、费率和赎回规则复核后进入正式研究候选'],
    proofNeeded,
    actionHref: fund.currentSalesRuleGate?.status === 'blocked'
      ? salesRulesHrefForCodes(fund.windCode, preferences.purchasePlan, preferences.plannedAmount)
      : `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
  }
}

function buildNextActionRouter({
  primaryAction,
  buyBeforeLandmineBoard,
  evidenceClosureQueue,
  reportReadinessRadar,
  comparisonHref,
  salesRulesHref,
  strictReviewHref,
  preferences,
}: {
  primaryAction: { kind: string; label: string; href: string; description: string }
  buyBeforeLandmineBoard: any[]
  evidenceClosureQueue: any[]
  reportReadinessRadar: any[]
  comparisonHref: string
  salesRulesHref: string
  strictReviewHref: string
  preferences: InvestorPreferences
}) {
  const salesRuleEvidenceCopy = salesRuleEvidenceCopyForPlan(preferences.purchasePlan)
  const actions = [
    {
      kind: primaryAction.kind,
      priority: 1,
      label: primaryAction.label,
      href: primaryAction.href,
      reason: primaryAction.description,
      status: primaryAction.kind === 'sales_rules' ? 'must_do' : 'recommended',
    },
    buyBeforeLandmineBoard[0] ? {
      kind: 'landmine',
      priority: 2,
      label: `先排雷：${buyBeforeLandmineBoard[0].name}`,
      href: buyBeforeLandmineBoard[0].actionHref,
      reason: `${buyBeforeLandmineBoard[0].label}，首要雷点：${buyBeforeLandmineBoard[0].topWarning}`,
      status: buyBeforeLandmineBoard[0].level === 'red' || buyBeforeLandmineBoard[0].level === 'orange' ? 'must_do' : 'recommended',
    } : null,
    evidenceClosureQueue[0] ? {
      kind: 'evidence_closure',
      priority: 3,
      label: `补证闭环：${evidenceClosureQueue[0].name}`,
      href: evidenceClosureQueue[0].actionHref,
      reason: `${evidenceClosureQueue[0].stageLabel}；${evidenceClosureQueue[0].nextAction}`,
      status: evidenceClosureQueue[0].status === 'blocked' ? 'must_do' : 'recommended',
    } : null,
    comparisonHref ? {
      kind: 'compare',
      priority: 4,
      label: '打开同类横评',
      href: comparisonHref,
      reason: '至少同屏比较 2-4 只同类型基金，确认首选能打败替代。',
      status: 'recommended',
    } : null,
    reportReadinessRadar[0] ? {
      kind: 'report_ready',
      priority: 5,
      label: `报告复核：${reportReadinessRadar[0].name}`,
      href: reportReadinessRadar[0].actionHref,
      reason: `${reportReadinessRadar[0].label}，就绪度 ${reportReadinessRadar[0].totalScore}/100；${reportReadinessRadar[0].nextAction}`,
      status: reportReadinessRadar[0].canGenerateFormalReport ? 'ready' : 'wait',
    } : null,
    salesRulesHref ? {
      kind: 'sales_rules_queue',
      priority: 6,
      label: '销售规则补证',
      href: salesRulesHref,
      reason: `补齐${salesRuleEvidenceCopy.fields}后再严格重评。`,
      status: 'must_do',
    } : null,
    strictReviewHref ? {
      kind: 'strict_review',
      priority: 7,
      label: '严格模式重评',
      href: strictReviewHref,
      reason: '补证完成后只看可进入正式研究候选的样本。',
      status: 'wait',
    } : null,
  ].filter(Boolean) as Array<{ kind: string; priority: number; label: string; href: string; reason: string; status: string }>

  const seen = new Set<string>()
  return actions
    .filter((action) => {
      const key = `${action.kind}:${action.href}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .sort((left, right) => left.priority - right.priority)
    .slice(0, 5)
}

function buildDecisionConfidenceMeter({
  topFund,
  buyBeforeLandmineBoard,
  evidenceClosureQueue,
  reportReadinessRadar,
  nextActionRouter,
}: {
  topFund: any | null
  buyBeforeLandmineBoard: any[]
  evidenceClosureQueue: any[]
  reportReadinessRadar: any[]
  nextActionRouter: Array<{ status: string }>
}) {
  const topLandmine = topFund ? buyBeforeLandmineBoard.find((item: any) => item.windCode === topFund.windCode) : buyBeforeLandmineBoard[0]
  const topClosure = topFund ? evidenceClosureQueue.find((item: any) => item.windCode === topFund.windCode) : evidenceClosureQueue[0]
  const topReadiness = topFund ? reportReadinessRadar.find((item: any) => item.windCode === topFund.windCode) : reportReadinessRadar[0]
  const salesRuleMissing = topFund?.currentSalesRuleGate?.status === 'blocked'
  const mustDoCount = nextActionRouter.filter((action) => action.status === 'must_do').length
  const evidenceGrade = topFund?.purchaseGate?.evidenceGrade || 'D'
  const baseScore = topReadiness?.totalScore ?? 35
  const deductions = uniqueText([
    salesRuleMissing ? '销售规则硬缺口未清零' : '',
    topLandmine && topLandmine.landmineScore >= 60 ? `排雷分 ${topLandmine.landmineScore}/100` : '',
    topClosure && topClosure.status !== 'ready' ? `证据闭环停在“${topClosure.stageLabel}”` : '',
    passesEvidenceGrade(evidenceGrade, 'B') ? '' : `证据等级 ${evidenceGrade} 未达 B`,
    mustDoCount ? `${mustDoCount} 个必做动作未完成` : '',
  ])
  const score = Math.round(clamp(
    baseScore
      - (salesRuleMissing ? 25 : 0)
      - (topLandmine ? Math.min(25, Math.round(topLandmine.landmineScore / 4)) : 0)
      - (topClosure && topClosure.status !== 'ready' ? 12 : 0)
      - (passesEvidenceGrade(evidenceGrade, 'B') ? 0 : 10)
      - mustDoCount * 6,
    0,
    100,
  ))
  const level = score >= 80 ? 'high' : score >= 60 ? 'medium' : score >= 40 ? 'low' : 'blocked'
  const label = level === 'high'
    ? '结论可信度高'
    : level === 'medium'
      ? '结论可信度中等'
      : level === 'low'
        ? '结论可信度偏低'
        : '结论暂不可采信'
  return {
    score,
    level,
    label,
    baseReadinessScore: baseScore,
    deductions,
    positiveEvidence: uniqueText([
      topReadiness ? `报告就绪度 ${topReadiness.totalScore}/100` : '',
      topFund?.investorScore ? `选基分 ${topFund.investorScore}` : '',
      topFund?.managerEvidence?.status !== 'missing' ? topFund?.managerEvidence?.note || '' : '',
    ]).slice(0, 4),
    conclusion: level === 'high'
      ? '可进入正式研究复核报告复核，但仍不是研究结论。'
      : level === 'medium'
        ? '只能作为研究候选，需完成动作路由中的待办后再重评。'
        : '当前结论只适合观察/排雷，不能作为研究依据。',
  }
}

function buildLeaderStabilityCheck({
  ranked,
  topFund,
  comparisonHref,
}: {
  ranked: any[]
  topFund: any | null
  comparisonHref: string
}) {
  const candidates = ranked.slice(0, 5)
  const runnerUp = candidates.find((fund: any) => fund.windCode !== topFund?.windCode) || null
  const topScore = asNumber(topFund?.investorScore) ?? 0
  const runnerUpScore = asNumber(runnerUp?.investorScore) ?? 0
  const scoreGap = Math.round(Math.max(0, topScore - runnerUpScore))
  const blockedTopCount = candidates.filter((fund: any) => fund.currentSalesRuleGate?.status === 'blocked' || fund.purchaseGate?.level === 'blocked').length
  const tightRaceCount = candidates.filter((fund: any) => Math.abs(topScore - (asNumber(fund.investorScore) ?? 0)) <= 5).length
  const evidenceWeakCount = candidates.filter((fund: any) => !passesEvidenceGrade(fund.purchaseGate?.evidenceGrade || 'D', 'B')).length
  const comparableCount = candidates.filter((fund: any) => fund.purchaseGate?.level !== 'blocked').length
  const stabilityScore = Math.round(clamp(
    45
      + Math.min(25, scoreGap * 4)
      + Math.min(15, comparableCount * 3)
      - blockedTopCount * 12
      - Math.max(0, tightRaceCount - 1) * 8
      - evidenceWeakCount * 5,
    0,
    100,
  ))
  const level = blockedTopCount > 0 && scoreGap <= 8
    ? 'unstable'
    : stabilityScore >= 75
      ? 'stable'
      : stabilityScore >= 55
        ? 'needs_compare'
        : 'unstable'
  const label = level === 'stable'
    ? '首选相对稳定'
    : level === 'needs_compare'
      ? '首选需横评确认'
      : '榜单结论不稳定'
  const reasons = uniqueText([
    runnerUp ? `第一名领先第二名 ${scoreGap} 分` : '缺少第二名，不能判断领先幅度',
    tightRaceCount >= 2 ? `前五名中有 ${tightRaceCount} 只与首选分差不超过 5 分` : '',
    blockedTopCount ? `前五名有 ${blockedTopCount} 只仍有硬门禁/销售规则阻断` : '',
    evidenceWeakCount ? `前五名有 ${evidenceWeakCount} 只证据等级未达 B` : '',
    comparableCount >= 2 ? `可进入横评样本 ${comparableCount} 只` : '可横评样本不足，需先补证扩样',
  ])
  return {
    level,
    label,
    stabilityScore,
    scoreGap,
    tightRaceCount,
    blockedTopCount,
    evidenceWeakCount,
    runnerUp: runnerUp ? {
      windCode: runnerUp.windCode,
      name: runnerUp.name,
      investorScore: runnerUp.investorScore,
      purchaseGateLabel: runnerUp.purchaseGate?.label,
    } : null,
    reasons,
    nextAction: level === 'stable'
      ? '仍需用同类横评和正式报告复核确认，不直接输出研究结论。'
      : '先打开同类横评，确认首选是否真的打败第二名、低成本份额和同类替代。',
    comparisonHref,
  }
}

function buildHeadToHeadChallenge({
  topFund,
  ranked,
  preferences,
  safeProfile,
}: {
  topFund: any | null
  ranked: any[]
  preferences: InvestorPreferences
  safeProfile: RiskProfile
}) {
  if (!topFund) return null
  const challenger = ranked.find((fund: any) => fund.windCode !== topFund.windCode) || null
  if (!challenger) return null
  const riskBudget = resolveRiskBudget(safeProfile, preferences)
  const comparisonHref = `/analysis/comparison?${new URLSearchParams({
    codes: uniqueText([topFund.windCode, challenger.windCode]).join(','),
    profile: safeProfile,
    horizon: preferences.horizon,
    purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
    autoReplay: '1',
  }).toString()}`
  const topDrawdown = topFund.maxDrawdown === null ? null : Math.abs(topFund.maxDrawdown)
  const challengerDrawdown = challenger.maxDrawdown === null ? null : Math.abs(challenger.maxDrawdown)
  const returnGap = (asNumber(topFund.return1y) ?? 0) - (asNumber(challenger.return1y) ?? 0)
  const drawdownGap = topDrawdown !== null && challengerDrawdown !== null ? challengerDrawdown - topDrawdown : null
  const scoreGap = Math.round((asNumber(topFund.investorScore) ?? 0) - (asNumber(challenger.investorScore) ?? 0))
  const topWeakness = uniqueText([
    topFund.currentSalesRuleGate?.status === 'blocked' ? `销售规则缺 ${topFund.currentSalesRuleGate?.missingCount || 0} 项` : '',
    topDrawdown !== null && topDrawdown > riskBudget ? `最大回撤 ${formatPercent(-topDrawdown)} 超预算` : '',
    passesEvidenceGrade(topFund.purchaseGate?.evidenceGrade || 'D', 'B') ? '' : `证据等级 ${topFund.purchaseGate?.evidenceGrade || 'D'} 未达 B`,
    topFund.costEvidence?.missing?.length ? `成本缺 ${topFund.costEvidence.missing.slice(0, 2).join('、')}` : '',
  ])
  const challengerThreats = uniqueText([
    scoreGap <= 5 ? `综合分只落后 ${scoreGap} 分，可能不是显著差距` : '',
    drawdownGap !== null && drawdownGap > 0 ? `回撤少 ${formatPercent(drawdownGap)}，持有体验可能更稳` : '',
    returnGap < 0 ? `近一年收益高出 ${formatPercent(Math.abs(returnGap))}` : '',
    (challenger.currentSalesRuleGate?.missingCount || 0) < (topFund.currentSalesRuleGate?.missingCount || 0)
      ? '销售规则缺口更少，可能更快进入严格候选'
      : '',
    challenger.managerEvidence?.maxTenureYears > topFund.managerEvidence?.maxTenureYears
      ? `经理样本更长：${challenger.managerEvidence.maxTenureYears.toFixed(1)} 年`
      : '',
  ])
  const decisionLine = topWeakness.length || challengerThreats.length
    ? '首选还没有赢到可以跳过横评；必须证明它在风险、费用、证据和替代比较中仍占优。'
    : '首选暂时领先，但仍需横评确认优势不是由短期收益或缺失数据造成。'
  return {
    leader: {
      windCode: topFund.windCode,
      name: topFund.name,
      investorScore: topFund.investorScore,
      return1y: topFund.return1y,
      maxDrawdown: topFund.maxDrawdown,
      evidenceGrade: topFund.purchaseGate?.evidenceGrade || 'D',
      salesRuleMissingCount: topFund.currentSalesRuleGate?.missingCount || 0,
    },
    challenger: {
      windCode: challenger.windCode,
      name: challenger.name,
      investorScore: challenger.investorScore,
      return1y: challenger.return1y,
      maxDrawdown: challenger.maxDrawdown,
      evidenceGrade: challenger.purchaseGate?.evidenceGrade || 'D',
      salesRuleMissingCount: challenger.currentSalesRuleGate?.missingCount || 0,
    },
    scoreGap,
    returnGap,
    drawdownGap,
    topWeakness,
    challengerThreats,
    decisionLine,
    comparisonHref,
  }
}

function buildPrePurchaseChecklist({
  topFund,
  decisionConfidenceMeter,
  leaderStabilityCheck,
  headToHeadChallenge,
  reportReadinessRadar,
  holdingExposureRiskQueue,
  preferences,
  safeProfile,
}: {
  topFund: any | null
  decisionConfidenceMeter: ReturnType<typeof buildDecisionConfidenceMeter>
  leaderStabilityCheck: ReturnType<typeof buildLeaderStabilityCheck>
  headToHeadChallenge: ReturnType<typeof buildHeadToHeadChallenge>
  reportReadinessRadar: any[]
  holdingExposureRiskQueue: any[]
  preferences: InvestorPreferences
  safeProfile: RiskProfile
}) {
  if (!topFund) return null
  const salesRuleEvidenceCopy = salesRuleEvidenceCopyForPlan(preferences.purchasePlan)
  const checklistScope = '销售规则、适当性、执行、回撤、证据、成本、经理持仓、横评报告'
  const readiness = reportReadinessRadar.find((item: any) => item.windCode === topFund.windCode) || null
  const holding = holdingExposureRiskQueue.find((item: any) => item.windCode === topFund.windCode) || null
  const riskBudget = resolveRiskBudget(safeProfile, preferences)
  const drawdown = topFund.maxDrawdown === null ? null : Math.abs(topFund.maxDrawdown)
  const executionAmountGate = topFund.executionAmountGate || topFund.currentSalesRuleGate?.executionAmountGate || null
  const checklistItems = [
    {
      key: 'sales_rules',
      label: '销售规则',
      status: topFund.currentSalesRuleGate?.status === 'blocked' ? 'blocked' : 'pass',
      detail: topFund.currentSalesRuleGate?.status === 'blocked'
        ? `仍缺 ${topFund.currentSalesRuleGate?.missingCount || 0} 项：${(topFund.currentSalesRuleGate?.missingItems || []).slice(0, 4).join('、') || '销售端硬字段'}`
        : salesRuleEvidenceCopy.cleanDetail,
      action: topFund.currentSalesRuleGate?.status === 'blocked' ? '先补销售规则，不进入正式候选' : '进入下一项复核',
    },
    {
      key: 'suitability',
      label: '适当性匹配',
      status: topFund.riskSuitability?.status === 'mismatch' ? 'blocked' : topFund.riskSuitability?.status === 'missing' ? 'pending' : 'pass',
      detail: topFund.riskSuitability?.note || '销售风险等级待核',
      action: topFund.riskSuitability?.status === 'matched' ? '风险等级可继续复核' : '补销售平台风险等级并匹配本人画像',
    },
    {
      key: 'execution',
      label: '申赎规则',
      status: topFund.tradability?.status === 'blocked' || executionAmountGate?.status === 'blocked'
        ? 'blocked'
        : topFund.tradability?.status === 'unknown' || executionAmountGate?.status === 'unknown' || !executionAmountGate
          ? 'pending'
          : 'pass',
      detail: uniqueText([
        topFund.tradability?.note || '申购/赎回状态待补',
        executionAmountGate ? `计划金额门禁：${executionAmountGate.label}；${executionAmountGate.detail}` : '计划金额门禁待扫描，不能判断起购/定投/限购是否满足。',
      ]).join('；'),
      action: topFund.tradability?.status === 'open' && executionAmountGate?.status === 'pass' ? '执行和计划金额可继续复核' : salesRuleEvidenceCopy.executionChecklistAction,
    },
    {
      key: 'risk_budget',
      label: '回撤预算',
      status: drawdown === null ? 'pending' : drawdown > riskBudget ? 'blocked' : 'pass',
      detail: drawdown === null ? '最大回撤待补' : `历史最大回撤 ${formatPercent(-drawdown)}，当前画像预算 ${formatPercent(-riskBudget)}`,
      action: drawdown !== null && drawdown <= riskBudget ? '风险预算内，可继续横评' : '超预算时只能观察或调整画像后重评',
    },
    {
      key: 'evidence',
      label: '证据等级',
      status: passesEvidenceGrade(topFund.purchaseGate?.evidenceGrade || 'D', 'B') ? 'pass' : 'pending',
      detail: `当前证据 ${topFund.purchaseGate?.evidenceGrade || 'D'}，正式研究候选建议至少 B；完整度 ${topFund.buyEvidence?.completenessScore ?? 0}`,
      action: passesEvidenceGrade(topFund.purchaseGate?.evidenceGrade || 'D', 'B') ? '证据等级达标' : '补净值、规模、经理、销售和持仓证据',
    },
    {
      key: 'cost',
      label: '费用成本',
      status: (topFund.costEvidence?.missing || []).length >= 4 ? 'pending' : 'pass',
      detail: (topFund.costEvidence?.missing || []).length
        ? `仍缺 ${(topFund.costEvidence?.missing || []).slice(0, 4).join('、')}`
        : topFund.costEvidence?.note || '费用证据可比较',
      action: (topFund.costEvidence?.missing || []).length ? '补申购费、赎回费、销售服务费和计划金额成本' : '可进入费后横评',
    },
    {
      key: 'manager_holding',
      label: '经理/持仓',
      status: topFund.managerEvidence?.status === 'missing' || !holding || holding.status === 'missing' ? 'pending' : holding.status === 'concentrated' ? 'blocked' : 'pass',
      detail: uniqueText([
        topFund.managerEvidence?.note || '经理证据待补',
        holding ? holding.primaryRisk : '持仓明细待补',
      ]).join('；'),
      action: topFund.managerEvidence?.status === 'available' && holding && holding.status !== 'missing' ? '可继续解释业绩来源和暴露' : '补经理任期、季报持仓和行业/个股暴露',
    },
    {
      key: 'comparison_report',
      label: '横评/报告',
      status: decisionConfidenceMeter.level === 'high' && leaderStabilityCheck.level === 'stable' && readiness?.canGenerateFormalReport ? 'pass' : 'pending',
      detail: uniqueText([
        `结论可信度 ${decisionConfidenceMeter.score}/100`,
        `首选稳定性 ${leaderStabilityCheck.stabilityScore}/100`,
        readiness ? `报告就绪 ${readiness.totalScore}/100` : '报告就绪待补',
        headToHeadChallenge ? `首选对第二名分差 ${headToHeadChallenge.scoreGap}` : '',
      ]).join('；'),
      action: '完成双基金横评、同类替代和正式报告复核后，才允许进入正式候选。',
    },
  ]
  const blockedCount = checklistItems.filter((item) => item.status === 'blocked').length
  const pendingCount = checklistItems.filter((item) => item.status === 'pending').length
  const passCount = checklistItems.filter((item) => item.status === 'pass').length
  const overallStatus = blockedCount ? 'blocked' : pendingCount ? 'pending' : 'ready'
  return {
    windCode: topFund.windCode,
    name: topFund.name,
    overallStatus,
    label: overallStatus === 'ready' ? '八项核查通过' : overallStatus === 'pending' ? '八项核查待补' : '八项核查阻断',
    passCount,
    pendingCount,
    blockedCount,
    checklistScope,
    items: checklistItems,
    conclusion: overallStatus === 'ready'
      ? '可进入正式研究复核报告复核，但仍不是研究结论。'
      : overallStatus === 'pending'
        ? '仍需补证或横评，不能直接作为研究依据。'
        : '存在硬阻断，不能进入正式研究候选。',
    actionHref: blockedCount || pendingCount
      ? salesRulesHrefForCodes(topFund.windCode, preferences.purchasePlan, preferences.plannedAmount)
      : `/funds/${encodeURIComponent(topFund.id || topFund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
  }
}

function buildBuyReadinessTrafficLight({
  prePurchaseChecklist,
  decisionConfidenceMeter,
  primaryAction,
}: {
  prePurchaseChecklist: ReturnType<typeof buildPrePurchaseChecklist>
  decisionConfidenceMeter: ReturnType<typeof buildDecisionConfidenceMeter>
  primaryAction: { kind: string; label: string; href: string; description: string }
}) {
  if (!prePurchaseChecklist) return null
  const firstBlocked = prePurchaseChecklist.items.find((item) => item.status === 'blocked') || null
  const firstPending = prePurchaseChecklist.items.find((item) => item.status === 'pending') || null
  const signal = prePurchaseChecklist.blockedCount > 0 || decisionConfidenceMeter.level === 'blocked'
    ? 'red'
    : prePurchaseChecklist.pendingCount > 0 || decisionConfidenceMeter.level !== 'high'
      ? 'yellow'
      : 'green'
  const label = signal === 'green'
    ? '绿灯：可进入正式研究复核'
    : signal === 'yellow'
      ? '黄灯：补证后再判断'
      : '红灯：暂不能作为研究候选'
  const headline = signal === 'green'
    ? '八项核查未见阻断，但仍需正式报告复核，不输出研究结论。'
    : signal === 'yellow'
      ? '没有硬阻断但证据还没闭环，先补待核项再重评。'
      : '存在硬阻断或可信度不可采信，不能把当前首选当作研究结论。'
  const primaryBlocker = firstBlocked || firstPending
  return {
    signal,
    label,
    headline,
    confidenceScore: decisionConfidenceMeter.score,
    passCount: prePurchaseChecklist.passCount,
    pendingCount: prePurchaseChecklist.pendingCount,
    blockedCount: prePurchaseChecklist.blockedCount,
    primaryBlocker: primaryBlocker ? {
      label: primaryBlocker.label,
      status: primaryBlocker.status,
      detail: primaryBlocker.detail,
      action: primaryBlocker.action,
    } : null,
    nextActionLabel: primaryBlocker ? primaryBlocker.action : primaryAction.label,
    actionHref: prePurchaseChecklist.actionHref || primaryAction.href,
    hardBoundary: '红灯或黄灯状态下，本系统只允许研究、补证、横评和报告复核，不输出研究结论。',
  }
}

function buildGreenLightUnlockPath({
  prePurchaseChecklist,
  buyReadinessTrafficLight,
  strictReviewHref,
  comparisonHref,
  reportReadinessRadar,
  topFund,
  preferences,
}: {
  prePurchaseChecklist: ReturnType<typeof buildPrePurchaseChecklist>
  buyReadinessTrafficLight: ReturnType<typeof buildBuyReadinessTrafficLight>
  strictReviewHref: string
  comparisonHref: string
  reportReadinessRadar: any[]
  topFund: any | null
  preferences: InvestorPreferences
}) {
  if (!prePurchaseChecklist || !buyReadinessTrafficLight) return null
  const salesRuleEvidenceCopy = salesRuleEvidenceCopyForPlan(preferences.purchasePlan)
  const reviewHref = strictReviewHref || '/market?source=research-candidates&eligibleOnly=true&requireSalesRule=true&minEvidenceGrade=B'
  const detailHref = topFund
    ? `/funds/${encodeURIComponent(topFund.id || topFund.windCode)}`
    : reviewHref
  const reportHref = topFund
    ? `/funds/${encodeURIComponent(topFund.id || topFund.windCode)}?prePurchaseReport=1`
    : reviewHref
  const failedItems = prePurchaseChecklist.items.filter((item) => item.status !== 'pass')
  const routeMap: Record<string, { label: string; href: string; goal: string }> = {
    sales_rules: { label: '补销售规则硬字段', href: prePurchaseChecklist.actionHref, goal: `补齐${salesRuleEvidenceCopy.fields}。` },
    suitability: { label: '补适当性风险等级', href: prePurchaseChecklist.actionHref, goal: '确认销售平台风险等级与当前画像匹配。' },
    execution: { label: '确认申赎规则可行', href: detailHref, goal: salesRuleEvidenceCopy.executionGoal },
    risk_budget: { label: '复核回撤预算', href: comparisonHref || detailHref, goal: '确认历史回撤没有超过当前画像预算。' },
    evidence: { label: '补研究证据等级', href: detailHref, goal: '把证据等级提升到 B 以上，不用缺证样本做结论。' },
    cost: { label: '补费用成本口径', href: prePurchaseChecklist.actionHref, goal: '补申购费、赎回费、销售服务费和计划金额成本。' },
    manager_holding: { label: '补经理和持仓解释', href: detailHref, goal: '确认经理任期、季报持仓、行业和个股暴露。' },
    comparison_report: { label: '做横评和报告复核', href: comparisonHref || reportHref, goal: '完成同类替代、双基金横评和正式研究复核报告。' },
  }
  const steps = failedItems
    .map((item, index) => {
      const route = routeMap[item.key] || { label: item.label, href: prePurchaseChecklist.actionHref, goal: item.action }
      return {
        step: index + 1,
        key: item.key,
        label: route.label,
        status: item.status,
        reason: item.detail,
        goal: route.goal,
        href: route.href,
      }
    })
    .slice(0, 5)
  const finalStep = {
    step: steps.length + 1,
    key: 'strict_review',
    label: '回到严格研究候选复核',
    status: 'pending',
    reason: reportReadinessRadar[0] ? `当前报告就绪度 ${reportReadinessRadar[0].totalScore}/100` : '补完后只看证据和销售规则过关样本。',
    goal: '只看证据 B 以上且销售规则覆盖的正式研究候选。',
    href: reviewHref,
  }
  return {
    signal: buyReadinessTrafficLight.signal,
    title: buyReadinessTrafficLight.signal === 'green' ? '绿灯维持路线' : '绿灯解锁路线',
    summary: buyReadinessTrafficLight.signal === 'green'
      ? '当前可进入正式研究复核，仍需按报告流程留痕。'
      : `距离绿灯还差 ${prePurchaseChecklist.pendingCount + prePurchaseChecklist.blockedCount} 项；按顺序处理，不跳过硬门禁。`,
    steps: [...steps, finalStep].slice(0, 6),
    strictReviewHref: reviewHref,
    hardBoundary: '未完成路线图前，不保存正式研究复核报告，不输出研究结论。',
  }
}

function buildCandidatePromotionMatrix({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  return ranked
    .slice(0, 8)
    .map((fund: any) => {
      const typeFitResult = typeHorizonFit(fund.type, preferences, safeProfile)
      const costMissing = fund.costEvidence?.missing || []
      const promotionChecks = [
        {
          key: 'sales_rules',
          label: '销售规则',
          status: fund.currentSalesRuleGate?.status === 'blocked' ? 'blocked' : 'pass',
          detail: fund.currentSalesRuleGate?.status === 'blocked'
            ? `缺 ${fund.currentSalesRuleGate?.missingCount || 0} 项：${(fund.currentSalesRuleGate?.missingItems || []).slice(0, 4).join('、') || '销售端硬字段'}`
            : '销售规则硬缺口未见阻断',
        },
        {
          key: 'purchase_gate',
          label: '研究证据闸门',
          status: fund.purchaseGate?.level === 'blocked' ? 'blocked' : fund.purchaseGate?.level === 'verify_first' ? 'pending' : 'pass',
          detail: fund.purchaseGate?.hardBlocks?.[0] || fund.purchaseGate?.cautionFlags?.[0] || fund.purchaseGate?.label || '待复核',
        },
        {
          key: 'evidence',
          label: '证据等级',
          status: passesEvidenceGrade(fund.purchaseGate?.evidenceGrade || 'D', 'B') ? 'pass' : 'pending',
          detail: `当前 ${fund.purchaseGate?.evidenceGrade || 'D'}；正式候选建议至少 B，研究证据完整度 ${fund.buyEvidence?.completenessScore ?? 0}`,
        },
        {
          key: 'execution',
          label: '执行可行性',
          status: fund.tradability?.status === 'blocked' ? 'blocked' : fund.tradability?.status === 'unknown' ? 'pending' : 'pass',
          detail: fund.tradability?.note || '申购/赎回状态待复核',
        },
        {
          key: 'manager',
          label: '经理归因',
          status: fund.managerEvidence?.status === 'missing' ? 'pending' : fund.managerEvidence?.status === 'short' ? 'pending' : 'pass',
          detail: fund.managerEvidence?.note || '经理任期待补',
        },
        {
          key: 'cost',
          label: '成本证据',
          status: costMissing.length >= 4 ? 'pending' : 'pass',
          detail: costMissing.length ? `仍缺 ${costMissing.slice(0, 4).join('、')}` : fund.costEvidence?.note || '成本证据可比较',
        },
        {
          key: 'type_fit',
          label: '类型期限',
          status: typeFitResult.status === 'mismatch' ? 'blocked' : typeFitResult.status === 'explain' ? 'pending' : 'pass',
          detail: typeFitResult.rule,
        },
      ]
      const blocked = promotionChecks.filter((check) => check.status === 'blocked')
      const pending = promotionChecks.filter((check) => check.status === 'pending')
      const status = blocked.length
        ? 'blocked'
        : pending.length
          ? 'pending'
          : 'ready'
      const nextAction = blocked.length
        ? `先处理硬阻断：${blocked[0].label}。`
        : pending.length
          ? `补齐待核证据：${pending.slice(0, 3).map((item) => item.label).join('、')}。`
          : '可进入正式研究候选，但保存报告前仍需复核实时销售规则。'
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type || '未分类',
        investorScore: fund.investorScore,
        purchaseGateLabel: fund.purchaseGate?.label || '待复核',
        status,
        label: status === 'ready' ? '可转正式候选' : status === 'pending' ? '补证后可转正' : '硬阻断未解',
        checks: promotionChecks,
        blockedCount: blocked.length,
        pendingCount: pending.length,
        nextAction,
        actionHref: status === 'ready'
          ? `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`
          : salesRulesHrefForCodes(fund.windCode, preferences.purchasePlan, preferences.plannedAmount, `/market?source=research-candidates&profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}&eligibleOnly=true&requireSalesRule=true`),
      }
    })
    .sort((left: any, right: any) => {
      const rank: Record<string, number> = { blocked: 0, pending: 1, ready: 2 }
      return rank[left.status] - rank[right.status]
        || left.blockedCount - right.blockedCount
        || left.pendingCount - right.pendingCount
        || right.investorScore - left.investorScore
    })
    .slice(0, 5)
}

function buildEvidenceClosureQueue({
  ranked,
  safeProfile,
  preferences,
  strictReviewHref,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
  strictReviewHref: string
}) {
  const salesRuleEvidenceCopy = salesRuleEvidenceCopyForPlan(preferences.purchasePlan)
  return ranked
    .slice(0, 10)
    .map((fund: any) => {
      const salesMissing = fund.currentSalesRuleGate?.status === 'blocked'
        ? (fund.currentSalesRuleGate?.missingItems || [])
        : []
      const evidenceMissing = uniqueText([
        ...(fund.buyEvidence?.missingItems || []).map(evidenceItemText),
        fund.purchaseGate?.evidenceGrade && passesEvidenceGrade(fund.purchaseGate.evidenceGrade, 'B') ? '' : `证据等级 ${fund.purchaseGate?.evidenceGrade || 'D'} 未达 B`,
      ])
      const executionMissing = uniqueText([
        fund.tradability?.status === 'unknown' ? '申购/赎回实时状态' : '',
        ...(fund.costEvidence?.missing || []),
      ])
      const comparisonCodes = uniqueText([
        fund.windCode,
        ...ranked
          .filter((item: any) => item.windCode !== fund.windCode && (item.type || '未分类') === (fund.type || '未分类'))
          .slice(0, 3)
          .map((item: any) => item.windCode),
      ]).slice(0, 4)
      const comparisonHref = comparisonCodes.length >= 2
        ? `/analysis/comparison?${new URLSearchParams({
          codes: comparisonCodes.join(','),
          profile: safeProfile,
          horizon: preferences.horizon,
          purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
          autoReplay: '1',
        }).toString()}`
        : ''

      const hasHardSalesGap = salesMissing.length > 0
      const hasEvidenceGap = evidenceMissing.length > 0
      const hasExecutionGap = executionMissing.length > 0 || fund.tradability?.status === 'blocked'
      const stage = hasHardSalesGap
        ? 'sales_rules'
        : hasEvidenceGap
          ? 'evidence'
          : hasExecutionGap
            ? 'execution'
            : comparisonHref
              ? 'compare'
              : 'ready'
      const status = stage === 'sales_rules'
        ? 'blocked'
        : stage === 'ready'
          ? 'ready'
          : stage === 'compare'
            ? 'review'
            : 'pending'
      const stageLabel = stage === 'sales_rules'
        ? '先补销售规则'
        : stage === 'evidence'
          ? '补研究证据'
          : stage === 'execution'
            ? '核申赎规则'
            : stage === 'compare'
              ? '进入同类横评'
              : '可做正式报告复核'
      const missingItems = uniqueText([
        ...salesMissing,
        ...(stage === 'sales_rules' ? [] : evidenceMissing),
        ...(stage === 'sales_rules' || stage === 'evidence' ? [] : executionMissing),
      ])
      const requiredActions = uniqueText([
        hasHardSalesGap ? `补齐销售规则：${salesMissing.slice(0, 4).join('、')}` : '',
        hasEvidenceGap ? `补齐研究证据：${evidenceMissing.slice(0, 4).join('、')}` : '',
        hasExecutionGap ? `确认执行规则：${executionMissing.slice(0, 4).join('、')}` : '',
        comparisonHref ? '完成同类替代横评和持有回放' : '',
        '严格模式重评后再判断是否保存正式研究复核报告',
      ])
      const actionHref = stage === 'sales_rules' || stage === 'execution'
        ? salesRulesHrefForCodes(fund.windCode, preferences.purchasePlan, preferences.plannedAmount, strictReviewHref)
        : stage === 'compare' && comparisonHref
          ? comparisonHref
          : `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`
      const canSaveFormalReport = status === 'ready' || (status === 'review' && !hasHardSalesGap && !hasEvidenceGap && !hasExecutionGap)

      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type || '未分类',
        investorScore: fund.investorScore,
        stage,
        stageLabel,
        status,
        priority: status === 'blocked' ? 1 : status === 'pending' ? 2 : status === 'review' ? 3 : 4,
        missingItems,
        requiredActions,
        nextAction: stage === 'sales_rules'
          ? '先补销售平台硬字段，补齐前只保留研究观察。'
          : stage === 'evidence'
            ? '把证据等级、来源日期和必补字段补到研究复核可用状态。'
            : stage === 'execution'
              ? salesRuleEvidenceCopy.executionAction
              : stage === 'compare'
                ? '先和同类替代基金横评，确认不是单只高分误选。'
                : '进入详情页生成正式研究复核报告前，再复核实时销售平台状态。',
        actionHref,
        strictReviewHref,
        comparisonHref,
        canSaveFormalReport,
        gateSummary: canSaveFormalReport
          ? '销售规则与核心证据当前未见硬缺口，可进入正式报告前复核。'
          : '销售规则、证据或执行缺口未闭环，不能保存正式研究复核报告。',
      }
    })
    .sort((left: any, right: any) => left.priority - right.priority
      || left.missingItems.length - right.missingItems.length
      || right.investorScore - left.investorScore)
    .slice(0, 6)
}


function buildReportReadinessRadar({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  return ranked
    .slice(0, 8)
    .map((fund: any) => {
      const executionAmountGate = fund.executionAmountGate || fund.currentSalesRuleGate?.executionAmountGate || null
      const salesScore = fund.currentSalesRuleGate?.status === 'blocked'
        ? Math.max(0, 25 - (fund.currentSalesRuleGate?.missingCount || 0) * 4)
        : 25
      const evidenceScore = passesEvidenceGrade(fund.purchaseGate?.evidenceGrade || 'D', 'B')
        ? 20
        : passesEvidenceGrade(fund.purchaseGate?.evidenceGrade || 'D', 'C')
          ? 12
          : 6
      const executionScore = fund.tradability?.status === 'blocked'
        ? 0
        : executionAmountGate?.status === 'blocked'
          ? 0
        : fund.tradability?.status === 'unknown' || executionAmountGate?.status === 'unknown' || !executionAmountGate
          ? 8
          : 15
      const managerScore = fund.managerEvidence?.status === 'available'
        ? 12
        : fund.managerEvidence?.status === 'short'
          ? 6
          : 3
      const costScore = Math.min(12, Math.max(0, Math.round((fund.costEvidence?.score || 0) / 10 * 12)))
      const comparisonScore = fund.peerPercentiles?.peerScore !== null && fund.peerPercentiles?.peerScore !== undefined ? 8 : 0
      const totalScore = clamp(salesScore + evidenceScore + executionScore + managerScore + costScore + comparisonScore, 0, 100)
      const blockers = uniqueText([
        fund.currentSalesRuleGate?.status === 'blocked' ? `销售规则缺 ${fund.currentSalesRuleGate?.missingCount || 0} 项` : '',
        fund.purchaseGate?.level === 'blocked' ? fund.purchaseGate?.hardBlocks?.[0] || '研究证据闸门阻断' : '',
        fund.tradability?.status === 'blocked' ? fund.tradability?.note || '申购执行阻断' : '',
        executionAmountGate?.status === 'blocked' ? `计划金额不可执行：${executionAmountGate.detail}` : '',
      ])
      const pending = uniqueText([
        fund.currentSalesRuleGate?.status === 'blocked' ? (fund.currentSalesRuleGate?.missingItems || []).slice(0, 3).join('、') : '',
        executionAmountGate?.status === 'unknown' || !executionAmountGate ? '计划金额门禁待扫描' : '',
        passesEvidenceGrade(fund.purchaseGate?.evidenceGrade || 'D', 'B') ? '' : `证据等级需从 ${fund.purchaseGate?.evidenceGrade || 'D'} 提升到 B`,
        fund.costEvidence?.missing?.length ? `成本待补：${fund.costEvidence.missing.slice(0, 3).join('、')}` : '',
        fund.managerEvidence?.status === 'missing' ? '经理任职证据待补' : '',
        fund.peerPercentiles?.peerScore === null || fund.peerPercentiles?.peerScore === undefined ? '同类横评证据待补' : '',
      ])
      const amountGateReady = executionAmountGate?.status === 'pass'
      const status = blockers.length
        ? 'blocked'
        : amountGateReady && totalScore >= 80 && pending.length <= 1
          ? 'ready'
          : totalScore >= 60
            ? 'near'
            : 'thin'
      const label = status === 'ready'
        ? '报告复核就绪'
        : status === 'near'
          ? '接近就绪'
          : status === 'thin'
            ? '证据偏薄'
            : '硬门禁未过'
      const actionHref = blockers.some((item) => item.includes('销售规则')) || executionAmountGate?.status !== 'pass'
        ? salesRulesHrefForCodes(fund.windCode, preferences.purchasePlan, preferences.plannedAmount, `/market?source=research-candidates&profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}&eligibleOnly=true&requireSalesRule=true`)
        : `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type || '未分类',
        investorScore: fund.investorScore,
        totalScore,
        status,
        label,
        canGenerateFormalReport: status === 'ready',
        components: [
          { key: 'sales_rules', label: '销售规则', score: salesScore, max: 25 },
          { key: 'evidence', label: '研究证据', score: evidenceScore, max: 20 },
          { key: 'execution', label: '执行可行性', score: executionScore, max: 15 },
          { key: 'manager', label: '经理归因', score: managerScore, max: 12 },
          { key: 'cost', label: '成本口径', score: costScore, max: 12 },
          { key: 'peer', label: '同类横评', score: comparisonScore, max: 8 },
        ],
        blockers,
        pending,
        executionAmountGate,
        nextAction: status === 'ready'
          ? '可进入详情页做正式研究复核报告前复核；仍需确认销售平台实时规则。'
          : blockers.length
            ? '先处理硬门禁，尤其是销售规则、计划金额、适当性和申购执行阻断。'
            : '补齐待补证据后，用严格模式重评并再做同类横评。',
        actionHref,
      }
    })
    .sort((left: any, right: any) => {
      const rank: Record<string, number> = { blocked: 0, thin: 1, near: 2, ready: 3 }
      return rank[left.status] - rank[right.status]
        || right.totalScore - left.totalScore
        || right.investorScore - left.investorScore
    })
    .slice(0, 6)
}

function classifySupplementTaskField(label: string, purchasePlan: PurchasePlan) {
  const text = label || '销售规则硬字段'
  if (text.includes('风险')) {
    return {
      fieldKey: 'risk_level',
      fieldLabel: '销售风险等级',
      group: '适当性硬字段',
      priority: 1,
      reason: '适当性等级缺失时，不能判断研究画像是否匹配基金销售风险。',
    }
  }
  if (text.includes('申购状态') || text.includes('开放') || text.includes('暂停')) {
    return {
      fieldKey: 'purchase_status',
      fieldLabel: '申购状态',
      group: '申赎状态硬字段',
      priority: 2,
      reason: '申购状态缺失时，不能确认当前申购规则是否可执行。',
    }
  }
  if (text.includes('赎回') || text.includes('持有')) {
    return {
      fieldKey: 'redemption_holding',
      fieldLabel: '赎回/持有规则',
      group: '退出成本硬字段',
      priority: 3,
      reason: '赎回费和持有期缺失时，不能估算真实退出成本。',
    }
  }
  if (text.includes('申购费') || text.includes('认购费') || text.includes('销售服务费') || text.includes('管理费') || text.includes('托管费') || text.includes('费用')) {
    return {
      fieldKey: 'fee_rates',
      fieldLabel: '费用费率',
      group: '成本口径硬字段',
      priority: 4,
      reason: '费用字段缺失会让费后排序和份额选择失真。',
    }
  }
  if (text.includes('起购') || text.includes('最低申购')) {
    return {
      fieldKey: 'min_purchase',
      fieldLabel: '起购金额',
      group: '执行门槛硬字段',
      priority: purchasePlan === 'lump_sum' ? 5 : 7,
      reason: '起购金额缺失时，计划金额能否执行无法判断。',
    }
  }
  if (text.includes('定投')) {
    return {
      fieldKey: 'sip_rule',
      fieldLabel: '定投规则',
      group: '定投执行硬字段',
      priority: purchasePlan === 'sip' ? 5 : 9,
      reason: purchasePlan === 'sip'
        ? '定投计划下，是否支持定投和定投起点是硬门禁。'
        : '当前是一次性配置，定投字段只作为补充证据，不阻断一次性计划。',
    }
  }
  if (text.includes('限购') || text.includes('上限')) {
    return {
      fieldKey: 'purchase_limit',
      fieldLabel: '限购金额',
      group: '执行上限硬字段',
      priority: 6,
      reason: '限购金额缺失时，不能确认计划金额是否超过销售端上限。',
    }
  }
  if (text.includes('来源') || text.includes('日期') || text.includes('更新时间')) {
    return {
      fieldKey: 'source_date',
      fieldLabel: '来源日期',
      group: '证据时效硬字段',
      priority: 8,
      reason: '来源日期缺失时，销售规则证据无法证明足够新。',
    }
  }
  return {
    fieldKey: text,
    fieldLabel: text,
    group: '其他销售规则字段',
    priority: 10,
    reason: '该字段缺失会降低研究规则证据完整度。',
  }
}

function isTushareFoundationFillableGapItem(item: string, ruleSourceUpdatedAt?: string | null) {
  const text = item || ''
  return text.includes('整条')
    || text.includes('来源日期')
    || (text.includes('申购状态') && !ruleSourceUpdatedAt)
}

function foundationFillableItemLabel(item: string) {
  const text = item || ''
  if (text.includes('整条')) return '基础建档'
  if (text.includes('申购状态')) return '申购状态'
  if (text.includes('来源日期')) return '来源日期'
  return text
}

function manualVerificationSpecForGapItem(item: string, purchasePlan: PurchasePlan) {
  const field = classifySupplementTaskField(item, purchasePlan)
  const base = {
    fieldKey: field.fieldKey,
    fieldLabel: field.fieldLabel,
    group: field.group,
    rawMissingItem: item,
  }
  switch (field.fieldKey) {
    case 'risk_level':
      return {
        ...base,
        evidenceSource: '销售平台风险等级页 / 基金合同风险揭示条款',
        inputFields: 'riskLevel, sourceUrl, sourceUpdatedAt, notes',
        buyBeforeUse: '判断研究画像是否匹配，风险等级缺失时不得放入正式研究候选。',
      }
    case 'fee_rates':
      return {
        ...base,
        evidenceSource: '销售平台费率页 / 基金合同费用条款',
        inputFields: 'purchaseFeeRate, salesServiceFeeRate, redemptionFeeRules, sourceUrl, sourceUpdatedAt',
        buyBeforeUse: '估算计划金额的费后成本，避免低费率排序和份额选择失真。',
      }
    case 'redemption_holding':
      return {
        ...base,
        evidenceSource: '销售平台赎回费页 / 基金合同赎回费与持有期条款',
        inputFields: 'redemptionFeeRules, minHoldDays, sourceUrl, sourceUpdatedAt',
        buyBeforeUse: '评估退出成本、最短持有期和压力情景下的可赎回性。',
      }
    case 'min_purchase':
      return {
        ...base,
        evidenceSource: '销售平台申赎规则页',
        inputFields: 'minPurchaseAmount, sourceUrl, sourceUpdatedAt',
        buyBeforeUse: '确认计划金额是否达到一次性配置门槛。',
      }
    case 'sip_rule':
      return {
        ...base,
        evidenceSource: '销售平台定投规则页',
        inputFields: 'supportsSip, minSipAmount, sourceUrl, sourceUpdatedAt',
        buyBeforeUse: '确认定投计划是否可执行，定投起点是否匹配现金流安排。',
      }
    case 'purchase_limit':
      return {
        ...base,
        evidenceSource: '销售平台限购/大额申购规则页',
        inputFields: 'dailyLimitAmount, sourceUrl, sourceUpdatedAt',
        buyBeforeUse: '判断计划金额是否超过销售端限购上限。',
      }
    case 'purchase_status':
      return {
        ...base,
        evidenceSource: '销售平台申购状态页 / Tushare fund_basic 仅可作基础状态辅助',
        inputFields: 'purchaseStatus, purchaseStatusLabel, sourceUrl, sourceUpdatedAt',
        buyBeforeUse: '确认当前是否开放申购；Tushare 基础状态不能替代销售平台实时状态。',
      }
    default:
      return {
        ...base,
        evidenceSource: '销售平台规则页 / 基金合同对应条款',
        inputFields: 'sourceUrl, sourceUpdatedAt, notes',
        buyBeforeUse: '补齐研究销售规则证据，避免缺失字段被当作研究依据。',
      }
  }
}

function buildFieldSupplementTaskBasket({
  ranked,
  salesRuleUnlockPreview,
  preferences,
  strictReviewHref,
}: {
  ranked: any[]
  salesRuleUnlockPreview: {
    nearPurchasableQueue?: Array<{ windCode: string; name: string; missingCount: number; missingItems: string[]; investorScore: number; actionHref: string }>
    bulkSalesRulesHref?: string
  }
  preferences: InvestorPreferences
  strictReviewHref: string
}) {
  const candidates = uniqueFundsByWindCode([
    ...ranked
      .filter((fund: any) => fund.currentSalesRuleGate?.status === 'blocked')
      .sort((left: any, right: any) => right.investorScore - left.investorScore
        || (left.currentSalesRuleGate?.missingCount || 0) - (right.currentSalesRuleGate?.missingCount || 0))
      .slice(0, 12)
      .map((fund: any) => ({
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type || '未分类',
        investorScore: fund.investorScore,
        missingCount: fund.currentSalesRuleGate?.missingCount || 0,
        missingItems: fund.currentSalesRuleGate?.missingItems || [],
        ruleSourceUpdatedAt: fund.currentSalesRuleGate?.ruleSourceUpdatedAt || null,
      })),
    ...(salesRuleUnlockPreview.nearPurchasableQueue || []).map((item: any) => ({
      windCode: item.windCode,
      name: item.name,
      type: item.type || '未分类',
      investorScore: item.investorScore,
      missingCount: item.missingCount || 0,
      missingItems: item.missingItems || [],
      ruleSourceUpdatedAt: item.ruleSourceUpdatedAt || null,
      unlockRank: item.unlockRank || null,
      unlockStage: item.unlockStage || '',
      unlockReason: item.reason || '',
      unlockAction: item.unlockAction || '',
      unlockReadiness: item.unlockReadiness || null,
      formalCandidateAfterSalesRule: Boolean(item.formalCandidateAfterSalesRule),
    })),
  ]).slice(0, 12)

  const foundationHydrationRows = candidates.map((fund: any) => {
    const missingItems = uniqueText(fund.missingItems || [])
    const fillableItems = missingItems.filter((item) => isTushareFoundationFillableGapItem(item, fund.ruleSourceUpdatedAt))
    const manualItems = missingItems.filter((item) => !isTushareFoundationFillableGapItem(item, fund.ruleSourceUpdatedAt))
    return {
      windCode: fund.windCode,
      name: fund.name,
      investorScore: fund.investorScore,
      fillableItems,
      manualItems,
    }
  })
  const foundationHydrationPlan = {
    title: 'Tushare 基础状态可先自动补',
    source: 'backend.tushare.fund_basic_to_local_sales_rules',
    fillableFundCount: foundationHydrationRows.filter((row) => row.fillableItems.length > 0).length,
    fillableMissingFields: foundationHydrationRows.reduce((sum, row) => sum + row.fillableItems.length, 0),
    manualFundCount: foundationHydrationRows.filter((row) => row.manualItems.length > 0).length,
    manualMissingFields: foundationHydrationRows.reduce((sum, row) => sum + row.manualItems.length, 0),
    fillableCodes: foundationHydrationRows
      .filter((row) => row.fillableItems.length > 0)
      .map((row) => row.windCode)
      .slice(0, 100),
    manualOnlyCodes: foundationHydrationRows
      .filter((row) => row.manualItems.length > 0 && row.fillableItems.length === 0)
      .map((row) => row.windCode)
      .slice(0, 100),
    fillableFields: uniqueText(foundationHydrationRows.flatMap((row) => row.fillableItems.map(foundationFillableItemLabel))).slice(0, 6),
    manualFields: uniqueText(foundationHydrationRows.flatMap((row) => row.manualItems)).slice(0, 8),
    summary: `Tushare 只能先补基础申赎状态、基础建档和来源日期；${salesRuleFoundationManualFieldsForPlan(preferences.purchasePlan)}仍必须来自销售平台或基金合同人工核验。`,
    hardBoundary: '自动补基础状态不等于销售规则闭环；人工硬字段未补齐前，仍不能转为正式研究候选。',
  }
  const manualLedgerRows = foundationHydrationRows.flatMap((row) =>
    row.manualItems.map((manualItem) => {
      const spec = manualVerificationSpecForGapItem(manualItem, preferences.purchasePlan)
      return {
        windCode: row.windCode,
        name: row.name,
        investorScore: row.investorScore,
        fieldKey: spec.fieldKey,
        fieldLabel: spec.fieldLabel,
        group: spec.group,
        rawMissingItem: spec.rawMissingItem,
        evidenceSource: spec.evidenceSource,
        inputFields: spec.inputFields,
        buyBeforeUse: spec.buyBeforeUse,
        purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
        plannedAmount: preferences.plannedAmount,
      }
    }),
  ).slice(0, 120)
  const manualLedgerHeaders = ['基金代码', '基金名称', '选基分', '字段组', '缺失字段', '原始缺口', '核验证据来源', '需录入字段', '研究用途', '研究方式', '计划金额']
  const manualLedgerTsv = [
    manualLedgerHeaders.join('\t'),
    ...manualLedgerRows.map((row) => [
      row.windCode,
      row.name,
      String(row.investorScore),
      row.group,
      row.fieldLabel,
      row.rawMissingItem,
      row.evidenceSource,
      row.inputFields,
      row.buyBeforeUse,
      row.purchasePlan,
      String(row.plannedAmount),
    ].join('\t')),
  ].join('\n')
  const manualVerificationLedger = {
    title: '人工核验台账',
    scope: 'manual_sales_rule_verification',
    rowCount: manualLedgerRows.length,
    fundCount: Array.from(new Set(manualLedgerRows.map((row) => row.windCode))).length,
    headers: manualLedgerHeaders,
    rows: manualLedgerRows,
    tsv: manualLedgerTsv,
    summary: manualLedgerRows.length
      ? `已生成 ${manualLedgerRows.length} 条人工核验任务，覆盖 ${Array.from(new Set(manualLedgerRows.map((row) => row.windCode))).length} 只基金；可复制到表格逐项查销售平台或基金合同。`
      : '当前没有需要人工核验的销售规则字段。',
    hardBoundary: '人工台账只用于补证执行；核验证据未录入本地销售规则前，相关基金仍不得进入正式研究候选。',
  }
  const unlockByCode = new Map((salesRuleUnlockPreview.nearPurchasableQueue || []).map((item: any) => [item.windCode, item]))
  const manualRowsByCode = manualLedgerRows.reduce((map, row) => {
    const rows = map.get(row.windCode) || []
    rows.push(row)
    map.set(row.windCode, rows)
    return map
  }, new Map<string, typeof manualLedgerRows>())
  const manualVerificationSprintPlan = {
    title: '人工补证冲刺计划',
    scope: 'manual_sales_rule_sprint',
    summary: manualLedgerRows.length
      ? `优先补 ${Math.min(5, manualRowsByCode.size)} 只最接近严格候选的基金；按单只基金闭环补完字段，再回到严格重评。`
      : '当前没有人工补证冲刺任务。',
    fundCount: manualRowsByCode.size,
    totalRows: manualLedgerRows.length,
    sprints: Array.from(manualRowsByCode.entries())
      .map(([windCode, rows]) => {
        const candidate = candidates.find((fund: any) => fund.windCode === windCode) || rows[0]
        const unlock = unlockByCode.get(windCode) as any
        const fieldLabels = uniqueText(rows.map((row) => row.fieldLabel))
        const evidenceSources = uniqueText(rows.map((row) => row.evidenceSource))
        const rowCount = rows.length
        return {
          windCode,
          name: rows[0]?.name || candidate?.name || windCode,
          investorScore: rows[0]?.investorScore || candidate?.investorScore || 0,
          rowCount,
          fields: fieldLabels.slice(0, 8),
          evidenceSources: evidenceSources.slice(0, 4),
          batchType: unlock?.unlockStage || (rowCount <= 3 ? '临门一脚' : rowCount <= 6 ? '单只集中补证' : '重补规则'),
          expectedOutcome: unlock?.unlockReadiness?.nextStep || unlock?.unlockAction || '补完人工硬字段后，重新跑严格筛选确认是否具备研究候选资格。',
          canStrictReviewAfterFill: Boolean(unlock?.formalCandidateAfterSalesRule || unlock?.unlockReadiness?.formalCandidateAfterSalesRule),
          reason: unlock?.reason || `选基分 ${rows[0]?.investorScore || candidate?.investorScore || 0}；当前缺 ${rowCount} 条人工核验任务。`,
          actionHref: salesRulesHrefForCodes(windCode, preferences.purchasePlan, preferences.plannedAmount, strictReviewHref),
          strictReviewHref,
          tsv: [
            manualLedgerHeaders.join('\t'),
            ...rows.map((row) => [
              row.windCode,
              row.name,
              String(row.investorScore),
              row.group,
              row.fieldLabel,
              row.rawMissingItem,
              row.evidenceSource,
              row.inputFields,
              row.buyBeforeUse,
              row.purchasePlan,
              String(row.plannedAmount),
            ].join('\t')),
          ].join('\n'),
        }
      })
      .sort((left, right) =>
        Number(right.canStrictReviewAfterFill) - Number(left.canStrictReviewAfterFill)
        || right.investorScore - left.investorScore
        || left.rowCount - right.rowCount
        || left.windCode.localeCompare(right.windCode),
      )
      .slice(0, 8),
    hardBoundary: '冲刺计划只决定补证顺序；补完且严格重评通过前，不输出研究结论。',
  }

  const taskMap = new Map<string, {
    fieldKey: string
    fieldLabel: string
    group: string
    priority: number
    reason: string
    funds: Array<{ windCode: string; name: string; investorScore: number; missingCount: number }>
  }>()

  candidates.forEach((fund: any) => {
    const missingItems = uniqueText(fund.missingItems || [])
    missingItems.forEach((missingItem) => {
      const field = classifySupplementTaskField(missingItem, preferences.purchasePlan)
      const existing = taskMap.get(field.fieldKey) || { ...field, funds: [] }
      if (!existing.funds.some((item) => item.windCode === fund.windCode)) {
        existing.funds.push({
          windCode: fund.windCode,
          name: fund.name,
          investorScore: fund.investorScore,
          missingCount: fund.missingCount || missingItems.length,
        })
      }
      taskMap.set(field.fieldKey, existing)
    })
  })

  const tasks = Array.from(taskMap.values())
    .map((task) => {
      const codes = task.funds.slice(0, 8).map((fund) => fund.windCode)
      return {
        ...task,
        fundCount: task.funds.length,
        sampleCodes: codes,
        topFunds: task.funds
          .sort((left, right) => right.investorScore - left.investorScore || left.missingCount - right.missingCount)
          .slice(0, 4),
        actionHref: codes.length
          ? salesRulesHrefForCodes(codes, preferences.purchasePlan, preferences.plannedAmount, strictReviewHref)
          : salesRuleUnlockPreview.bulkSalesRulesHref || salesRulesHrefForCodes([], preferences.purchasePlan, preferences.plannedAmount, strictReviewHref),
        status: 'must_fill',
        nextAction: `补齐“${task.fieldLabel}”后，回到严格模式重评；未补齐前相关基金只能留在研究观察。`,
      }
    })
    .sort((left, right) => left.priority - right.priority
      || right.fundCount - left.fundCount
      || left.fieldLabel.localeCompare(right.fieldLabel, 'zh-CN'))
    .slice(0, 8)

  const totalMissingFields = tasks.reduce((sum, task) => sum + task.fundCount, 0)
  const topTask = tasks[0] || null

  return {
    title: '字段级补证任务篮',
    scope: 'sales_rule_field_supplement',
    summary: topTask
      ? `优先补“${topTask.fieldLabel}”，涉及 ${topTask.fundCount} 只；字段补齐前不进入正式研究候选。`
      : '当前没有可聚合的销售规则字段缺口。',
    taskCount: tasks.length,
    fundCount: candidates.length,
    totalMissingFields,
    tasks,
    foundationHydrationPlan,
    manualVerificationLedger,
    manualVerificationSprintPlan,
    strictReviewHref,
    bulkActionHref: salesRuleUnlockPreview.bulkSalesRulesHref || (candidates.length
      ? salesRulesHrefForCodes(candidates.map((fund: any) => fund.windCode).slice(0, 8), preferences.purchasePlan, preferences.plannedAmount, strictReviewHref)
      : salesRulesHrefForCodes([], preferences.purchasePlan, preferences.plannedAmount, strictReviewHref)),
    hardBoundary: '字段级任务未清零前，只能做基金研究、补证、横评和报告复核，不输出研究结论。',
  }
}

function buildExecutionFeasibilityQueue({
  ranked,
  preferences,
  safeProfile,
}: {
  ranked: any[]
  preferences: InvestorPreferences
  safeProfile: RiskProfile
}) {
  return ranked
    .filter((fund: any) => fund.purchaseGate?.level !== 'blocked')
    .slice(0, 8)
    .map((fund: any) => {
      const cost = fund.costEvidence || {}
      const missing = cost.missing || []
      const plannedAmount = preferences.plannedAmount
      const minAmount = preferences.purchasePlan === 'sip' ? asNumber(cost.minSipAmount) : asNumber(cost.minPurchaseAmount)
      const dailyLimitAmount = asNumber(cost.dailyLimitAmount)
      const amountBelowMinimum = minAmount !== null && plannedAmount < minAmount
      const amountAboveLimit = dailyLimitAmount !== null && plannedAmount > dailyLimitAmount
      const planChecks = preferences.purchasePlan === 'sip'
        ? [
          cost.supportsSip === true ? '定投支持已确认' : '定投支持待补/不支持',
          cost.minSipAmount !== null && cost.minSipAmount !== undefined ? `定投起点 ${cost.minSipAmount} 元` : '定投起点待补',
          `计划每次 ${plannedAmount.toLocaleString('zh-CN')} 元`,
        ]
        : [
          cost.minPurchaseAmount !== null && cost.minPurchaseAmount !== undefined ? `起购金额 ${cost.minPurchaseAmount} 元` : '起购金额待补',
          `计划配置 ${plannedAmount.toLocaleString('zh-CN')} 元`,
        ]
      const hardBlocks = uniqueText([
        fund.currentSalesRuleGate?.status === 'blocked' ? '销售规则硬缺口未清零' : '',
        preferences.purchasePlan === 'sip' && cost.supportsSip === false ? '当前销售规则显示不支持定投' : '',
        fund.tradability?.status === 'blocked' ? fund.tradability.note || '申购状态阻断' : '',
        amountBelowMinimum ? `计划金额低于${preferences.purchasePlan === 'sip' ? '定投起点' : '起购金额'}：${plannedAmount.toLocaleString('zh-CN')} < ${minAmount?.toLocaleString('zh-CN')} 元` : '',
        amountAboveLimit ? `计划金额超过限购金额：${plannedAmount.toLocaleString('zh-CN')} > ${dailyLimitAmount?.toLocaleString('zh-CN')} 元` : '',
      ])
      const pendingItems = uniqueText([
        fund.tradability?.status === 'unknown' ? '申购状态' : '',
        ...missing,
        cost.dailyLimitAmount === null || cost.dailyLimitAmount === undefined ? '限购金额' : '',
      ])
      const status = hardBlocks.length
        ? 'blocked'
        : pendingItems.length
          ? 'pending'
          : 'ready'
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type,
        investorScore: fund.investorScore,
        purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
        plannedAmount,
        minExecutableAmount: minAmount,
        status,
        label: status === 'ready' ? '按计划可执行' : status === 'pending' ? '执行前待补' : '暂不可执行',
        planChecks,
        hardBlocks,
        pendingItems,
        tradabilityLabel: fund.tradability?.label || '申购待核',
        dailyLimitAmount,
        actionHref: status === 'pending' || status === 'blocked'
          ? salesRulesHrefForCodes(fund.windCode, preferences.purchasePlan, preferences.plannedAmount, `/market?source=research-candidates&profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}&eligibleOnly=true&requireSalesRule=true`)
          : `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
      }
    })
    .sort((left: any, right: any) => {
      const rank: Record<string, number> = { blocked: 0, pending: 1, ready: 2 }
      return rank[left.status] - rank[right.status]
        || right.investorScore - left.investorScore
    })
    .slice(0, 4)
}

function buildPurchasePlanFitQueue({
  ranked,
  preferences,
  safeProfile,
}: {
  ranked: any[]
  preferences: InvestorPreferences
  safeProfile: RiskProfile
}) {
  return ranked
    .filter((fund: any) => fund.purchaseGate?.level !== 'blocked')
    .slice(0, 10)
    .map((fund: any) => {
      const cost = fund.costEvidence || {}
      const experience = fund.holdingExperience || {}
      const drawdownStress = asNumber(experience.drawdownStress)
      const volatility = asNumber(fund.volatility)
      const annualReturn = asNumber(fund.annualReturn)
      const plannedAmount = preferences.plannedAmount
      const minPurchaseAmount = asNumber(cost.minPurchaseAmount)
      const minSipAmount = asNumber(cost.minSipAmount)
      const dailyLimitAmount = asNumber(cost.dailyLimitAmount)
      const sipSupported = cost.supportsSip === true
      const sipBlocked = cost.supportsSip === false
      const amountBelowSip = minSipAmount !== null && plannedAmount < minSipAmount
      const amountBelowLumpSum = minPurchaseAmount !== null && plannedAmount < minPurchaseAmount
      const amountAboveLimit = dailyLimitAmount !== null && plannedAmount > dailyLimitAmount
      const highPressure = drawdownStress !== null && drawdownStress >= 90
      const mediumPressure = drawdownStress !== null && drawdownStress >= 65
      const highVolatility = volatility !== null && volatility >= volatilityLimit(safeProfile) * 0.85
      const poorRecentReturn = annualReturn !== null && annualReturn < 0
      const salesBlocked = fund.currentSalesRuleGate?.status === 'blocked'
      const currentPlanHardBlocks = uniqueText([
        salesBlocked ? '销售规则硬缺口未清零' : '',
        preferences.purchasePlan === 'sip' && sipBlocked ? '销售规则显示不支持定投' : '',
        preferences.purchasePlan === 'sip' && amountBelowSip ? `计划金额低于定投起点：${plannedAmount.toLocaleString('zh-CN')} < ${minSipAmount?.toLocaleString('zh-CN')} 元` : '',
        preferences.purchasePlan === 'lump_sum' && amountBelowLumpSum ? `计划金额低于起购金额：${plannedAmount.toLocaleString('zh-CN')} < ${minPurchaseAmount?.toLocaleString('zh-CN')} 元` : '',
        amountAboveLimit ? `计划金额超过限购金额：${plannedAmount.toLocaleString('zh-CN')} > ${dailyLimitAmount?.toLocaleString('zh-CN')} 元` : '',
      ])
      const evidenceGaps = uniqueText([
        cost.purchaseFeeRate == null ? '申购费率' : '',
        cost.hasRedemptionRules ? '' : '赎回费/持有期',
        preferences.purchasePlan === 'sip' && cost.supportsSip == null ? '定投支持' : '',
        preferences.purchasePlan === 'sip' && minSipAmount === null ? '定投起点' : '',
        preferences.purchasePlan === 'lump_sum' && minPurchaseAmount === null ? '起购金额' : '',
        dailyLimitAmount === null ? '限购金额' : '',
        drawdownStress === null ? '回撤压力' : '',
      ])
      const currentFitScore = Math.round(clamp(
        100
          - (currentPlanHardBlocks.length * 28)
          - (evidenceGaps.length * 7)
          - (preferences.purchasePlan === 'lump_sum' && highPressure ? 24 : 0)
          - (preferences.purchasePlan === 'lump_sum' && highVolatility ? 14 : 0)
          - (preferences.purchasePlan === 'sip' && sipBlocked ? 30 : 0)
          - (preferences.purchasePlan === 'sip' && poorRecentReturn ? 8 : 0)
          + (preferences.purchasePlan === 'sip' && sipSupported ? 8 : 0)
          + (preferences.purchasePlan === 'sip' && mediumPressure ? 6 : 0),
        0,
        100,
      ))
      const shouldSwitchToSip = preferences.purchasePlan === 'lump_sum'
        && !sipBlocked
        && (highPressure || highVolatility)
        && !amountAboveLimit
      const shouldSwitchToLumpSum = preferences.purchasePlan === 'sip'
        && (sipBlocked || amountBelowSip)
        && !amountBelowLumpSum
      const recommendedPlan: PurchasePlan = shouldSwitchToSip
        ? 'sip'
        : shouldSwitchToLumpSum
          ? 'lump_sum'
          : preferences.purchasePlan
      const recommendation = currentPlanHardBlocks.length
        ? '先补执行证据'
        : shouldSwitchToSip
          ? '建议改成定投分批'
          : shouldSwitchToLumpSum
            ? '建议改成一次性口径'
            : currentFitScore >= 80
              ? '当前研究方式较匹配'
              : '当前方式需谨慎复核'
      const reasons = uniqueText([
        highPressure ? `回撤压力约 ${drawdownStress}% 画像预算` : drawdownStress === null ? '回撤压力待补' : `回撤压力约 ${drawdownStress}% 画像预算`,
        highVolatility ? `波动率 ${formatPercent(volatility)} 接近或超过当前画像预算` : volatility === null ? '波动率待补' : `波动率 ${formatPercent(volatility)}`,
        preferences.purchasePlan === 'sip'
          ? sipSupported ? '销售规则已确认支持定投' : sipBlocked ? '销售规则显示不支持定投' : '定投支持待补'
          : minPurchaseAmount === null ? '一次性起购金额待补' : `起购金额 ${minPurchaseAmount.toLocaleString('zh-CN')} 元`,
        cost.purchaseFeeRate === null ? '申购费率待补，无法确认一次性成本' : `申购费率 ${cost.purchaseFeeRate.toFixed(2)}%`,
      ])
      const switchHref = `/market?source=research-candidates&${new URLSearchParams({
        profile: safeProfile,
        horizon: preferences.horizon,
        purchasePlan: recommendedPlan,
        plannedAmount: String(preferences.plannedAmount),
        eligibleOnly: 'false',
        requireSalesRule: 'false',
        minEvidenceGrade: 'D',
        minScore: '0',
        keyword: fund.windCode,
      }).toString()}`
      const actionHref = currentPlanHardBlocks.length || evidenceGaps.length
        ? salesRulesHrefForCodes(fund.windCode, preferences.purchasePlan, preferences.plannedAmount, switchHref)
        : switchHref

      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type,
        investorScore: fund.investorScore,
        currentPlan: preferences.purchasePlan,
        currentPlanLabel: preferences.purchasePlanLabel,
        recommendedPlan,
        recommendedPlanLabel: purchasePlanLabel[recommendedPlan],
        plannedAmount,
        currentFitScore,
        recommendation,
        label: recommendation,
        reasons,
        hardBlocks: currentPlanHardBlocks,
        evidenceGaps,
        drawdownStress,
        volatility,
        sipFriendlyScore: experience.sipFriendlyScore ?? null,
        supportsSip: cost.supportsSip ?? null,
        minPurchaseAmount,
        minSipAmount,
        dailyLimitAmount,
        actionHref,
        switchHref,
      }
    })
    .sort((left: any, right: any) => {
      const rank = (item: any) => item.hardBlocks.length ? 0 : item.recommendedPlan !== item.currentPlan ? 1 : item.evidenceGaps.length ? 2 : 3
      return rank(left) - rank(right)
        || left.currentFitScore - right.currentFitScore
        || right.investorScore - left.investorScore
    })
    .slice(0, 4)
}

function buildEvidenceFreshnessQueue({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  return ranked
    .slice(0, 8)
    .map((fund: any) => {
      const navAgeDays = ageDaysFromDateText(fund.navDate)
      const sourceDate = fund.salesRule?.sourceUpdatedAt || fund.currentSalesRuleGate?.ruleSourceUpdatedAt || null
      const salesRuleAgeDays = ageDaysFromDateText(sourceDate)
      const freshnessIssues = uniqueText([
        navAgeDays === null ? '净值日期缺失' : navAgeDays > EVIDENCE_FRESH_DAYS ? `净值日期 ${navAgeDays} 天前` : '',
        sourceDate
          ? salesRuleAgeDays === null
            ? '销售规则来源日期无效'
            : salesRuleAgeDays > EVIDENCE_FRESH_DAYS
              ? `销售规则来源 ${salesRuleAgeDays} 天前`
              : ''
          : '销售规则来源日期缺失',
      ])
      const evidenceGapIssues = uniqueText([
        fund.buyEvidence?.requiredMissingCount > 0 ? `研究证据仍缺 ${fund.buyEvidence.requiredMissingCount} 项` : '',
      ])
      const issues = uniqueText([...freshnessIssues, ...evidenceGapIssues])
      const status = freshnessIssues.length === 0 && evidenceGapIssues.length === 0
        ? 'fresh'
        : freshnessIssues.some((item) => item.includes('缺失') || item.includes('无效')) || evidenceGapIssues.length > 0
          ? 'missing'
          : 'stale'
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type,
        investorScore: fund.investorScore,
        status,
        label: status === 'fresh' ? '证据较新' : status === 'stale' ? '证据过旧' : '来源待补',
        navDate: fund.navDate || null,
        navAgeDays,
        salesRuleSourceUpdatedAt: sourceDate,
        salesRuleAgeDays,
        issues,
        freshnessIssues,
        evidenceGapIssues,
        actionHref: status === 'fresh'
          ? `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`
          : salesRulesHrefForCodes(fund.windCode, preferences.purchasePlan, preferences.plannedAmount, `/market?source=research-candidates&profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}&eligibleOnly=true&requireSalesRule=true`),
      }
    })
    .sort((left: any, right: any) => {
      const rank: Record<string, number> = { missing: 0, stale: 1, fresh: 2 }
      return rank[left.status] - rank[right.status]
        || right.investorScore - left.investorScore
    })
    .slice(0, 4)
}

function buildPeerAlternativePools({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  const anchors = ranked
    .filter((fund: any) => fund.purchaseGate?.level !== 'blocked')
    .slice(0, 3)
  return anchors
    .map((anchor: any) => {
      const alternatives = ranked
        .filter((fund: any) => fund.windCode !== anchor.windCode)
        .filter((fund: any) => (fund.type || '未分类') === (anchor.type || '未分类'))
        .filter((fund: any) => fund.purchaseGate?.level !== 'blocked')
        .sort((left: any, right: any) => (right.peerPercentiles?.peerScore ?? -1) - (left.peerPercentiles?.peerScore ?? -1)
          || right.investorScore - left.investorScore)
        .slice(0, 3)
      const comparisonCodes = [anchor, ...alternatives].map((fund: any) => fund.windCode)
      return {
        anchor: {
          windCode: anchor.windCode,
          name: anchor.name,
          type: anchor.type,
          investorScore: anchor.investorScore,
          peerScore: anchor.peerPercentiles?.peerScore ?? null,
          purchaseGateLabel: anchor.purchaseGate?.label || '待复核',
        },
        peerGroup: anchor.peerPercentiles?.peerGroup || `${anchor.type || '未分类'}同类池`,
        alternatives: alternatives.map((fund: any) => ({
          windCode: fund.windCode,
          name: fund.name,
          type: fund.type,
          investorScore: fund.investorScore,
          peerScore: fund.peerPercentiles?.peerScore ?? null,
          purchaseGateLabel: fund.purchaseGate?.label || '待复核',
          reason: [
            fund.peerPercentiles?.strengthLabels?.[0] || '',
            `选基分 ${fund.investorScore}`,
            fund.costEvidence?.label ? `成本 ${fund.costEvidence.label}` : '',
          ].filter(Boolean).join(' · '),
          actionHref: `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
        })),
        comparisonHref: comparisonCodes.length >= 2
          ? `/analysis/comparison?${new URLSearchParams({
            codes: comparisonCodes.join(','),
            profile: safeProfile,
            horizon: preferences.horizon,
            purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
            autoReplay: '1',
          }).toString()}`
          : '',
        rule: '同类型基金至少比较 2-4 只；若首选不能打败同类替代，不进入正式候选。',
      }
    })
    .filter((pool: any) => pool.alternatives.length > 0)
    .slice(0, 3)
}

function buildAmountGateAlternativeQueue({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  const anchors = ranked
    .filter((fund: any) => {
      const gate = fund.executionAmountGate || fund.currentSalesRuleGate?.executionAmountGate || null
      return gate?.status === 'blocked' || gate?.status === 'unknown' || !gate
    })
    .filter((fund: any) => fund.purchaseGate?.level !== 'blocked')
    .slice(0, 4)

  return anchors
    .map((anchor: any) => {
      const anchorGate = anchor.executionAmountGate || anchor.currentSalesRuleGate?.executionAmountGate || null
      const alternatives = ranked
        .filter((fund: any) => fund.windCode !== anchor.windCode)
        .filter((fund: any) => (fund.type || '未分类') === (anchor.type || '未分类'))
        .filter((fund: any) => fund.purchaseGate?.level !== 'blocked')
        .map((fund: any) => ({
          fund,
          gate: fund.executionAmountGate || fund.currentSalesRuleGate?.executionAmountGate || null,
        }))
        .filter((item: any) => item.gate?.status === 'pass' || item.gate?.status === 'unknown' || !item.gate)
        .sort((left: any, right: any) => amountGateRank(left.gate) - amountGateRank(right.gate)
          || (right.fund.peerPercentiles?.peerScore ?? -1) - (left.fund.peerPercentiles?.peerScore ?? -1)
          || right.fund.investorScore - left.fund.investorScore)
        .slice(0, 3)

      const comparisonCodes = [anchor.windCode, ...alternatives.map((item: any) => item.fund.windCode)]
      const comparisonHref = comparisonCodes.length >= 2
        ? `/analysis/comparison?${new URLSearchParams({
          codes: comparisonCodes.join(','),
          profile: safeProfile,
          horizon: preferences.horizon,
          purchasePlan: preferences.purchasePlan,
          ...plannedAmountSearchParams(preferences),
          autoReplay: '1',
        }).toString()}`
        : ''

      return {
        anchor: {
          windCode: anchor.windCode,
          name: anchor.name,
          type: anchor.type || '未分类',
          investorScore: anchor.investorScore,
          amountGateStatus: anchorGate?.status || 'unknown',
          amountGateLabel: anchorGate?.label || '金额门槛待补',
          amountGateDetail: anchorGate?.detail || '未取得销售规则金额门禁，不能判断当前计划金额是否可执行。',
          amountGateAdvice: anchorGate?.advice || '先补销售平台起购、定投起点和限购金额，再判断当前计划金额是否可执行。',
          amountGateActionLabel: anchorGate?.actionLabel || '补金额规则',
          amountGateSuggestedAmount: anchorGate?.suggestedAmount ?? null,
        },
        alternatives: alternatives.map((item: any) => ({
          windCode: item.fund.windCode,
          name: item.fund.name,
          type: item.fund.type || '未分类',
          investorScore: item.fund.investorScore,
          peerScore: item.fund.peerPercentiles?.peerScore ?? null,
          amountGateStatus: item.gate?.status || 'unknown',
          amountGateLabel: item.gate?.label || '金额门槛待补',
          amountGateDetail: item.gate?.detail || '未取得销售规则金额门禁，不能判断当前计划金额是否可执行。',
          reason: uniqueText([
            item.gate?.status === 'pass' ? '当前计划金额可执行' : '金额门禁待补但未见金额硬阻断',
            item.fund.peerPercentiles?.strengthLabels?.[0] || '',
            item.fund.costEvidence?.label ? `成本 ${item.fund.costEvidence.label}` : '',
            `选基分 ${item.fund.investorScore}`,
          ]).join(' · '),
          actionHref: `/funds/${encodeURIComponent(item.fund.id || item.fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
        })),
        comparisonHref,
        rule: '当前基金金额门禁未通过或待补时，只能转向同类型、同计划金额下金额不被硬阻断的替代基金做研究横评；这不是研究结论。',
      }
    })
    .filter((item: any) => item.alternatives.length > 0)
    .slice(0, 4)
}

function buildManagerAttributionQueue({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  const attributionWindowYears = preferences.horizon === 'gt3y' ? 3 : 1
  return ranked
    .filter((fund: any) => fund.purchaseGate?.level !== 'blocked')
    .slice(0, 10)
    .map((fund: any) => {
      const manager = fund.managerEvidence || {}
      const maxTenureYears = manager.maxTenureYears ?? null
      const attributionCoverageRatio = maxTenureYears === null
        ? null
        : Math.round(clamp(maxTenureYears / attributionWindowYears, 0, 1) * 100)
      const attributionCredibility = attributionCoverageRatio === null
        ? 'unknown'
        : attributionCoverageRatio >= 100
          ? 'covered'
          : attributionCoverageRatio >= 60
            ? 'partial'
            : 'weak'
      const riskLevel = manager.status === 'missing'
        ? 'missing'
        : maxTenureYears === null
          ? 'unknown'
          : maxTenureYears < 1
            ? 'short'
            : attributionCredibility !== 'covered'
              ? 'watch'
              : 'stable'
      const checks = uniqueText([
        manager.managerNames?.length ? `现任经理：${manager.managerNames.join(' / ')}` : '现任经理待补',
        maxTenureYears === null ? '任期样本待补' : `最长任期约 ${maxTenureYears.toFixed(1)} 年`,
        attributionCoverageRatio === null ? `${attributionWindowYears}年业绩归因覆盖率待补` : `${attributionWindowYears}年业绩归因覆盖率 ${attributionCoverageRatio}%`,
        riskLevel === 'short' ? '任期不足一年，历史收益不宜直接归因给现任经理' : '',
        riskLevel === 'watch' ? `任期未完整覆盖${attributionWindowYears}年观察窗口，需复核上任前后业绩差异` : '',
        riskLevel === 'missing' ? '经理明细缺失，不能保存正式研究复核报告' : '',
      ])
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type,
        investorScore: fund.investorScore,
        status: riskLevel,
        label: riskLevel === 'stable'
          ? '经理样本较足'
          : riskLevel === 'watch'
            ? '经理样本需观察'
            : riskLevel === 'short'
              ? '经理任期过短'
              : riskLevel === 'unknown'
                ? '任期待核'
                : '经理待补',
        managerNames: manager.managerNames || [],
        maxTenureYears,
        attributionWindowYears,
        attributionCoverageRatio,
        attributionCredibility,
        score: manager.score ?? 0,
        checks,
        actionHref: `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
      }
    })
    .sort((left: any, right: any) => {
      const rank: Record<string, number> = { missing: 0, unknown: 1, short: 2, watch: 3, stable: 4 }
      return rank[left.status] - rank[right.status]
        || right.investorScore - left.investorScore
    })
    .slice(0, 4)
}

function buildHoldingExperience({
  annualReturn,
  maxDrawdown,
  volatility,
  ageDays,
  profile,
  buyEvidence,
  riskBudget,
  purchasePlan,
}: {
  annualReturn: number | null
  maxDrawdown: number | null
  volatility: number | null
  ageDays: number | null
  profile: RiskProfile
  buyEvidence: ResearchEvidenceToolOutput
  riskBudget: number
  purchasePlan: PurchasePlan
}) {
  const drawdown = maxDrawdown === null ? null : Math.abs(maxDrawdown)
  const volBudget = volatilityLimit(profile)
  const drawdownScore = drawdown === null ? 0 : clamp((1 - drawdown / riskBudget) * 34, 0, 34)
  const volatilityScore = volatility === null ? 0 : clamp((1 - volatility / volBudget) * 24, 0, 24)
  const returnScore = annualReturn === null ? 0 : annualReturn >= 0.08 ? 15 : annualReturn >= 0.03 ? 12 : annualReturn >= 0 ? 9 : 4
  const sampleScore = ageDays === null ? 0 : ageDays >= 1095 ? 12 : ageDays >= 365 ? 10 : ageDays >= 180 ? 7 : 4
  const evidenceScore = clamp((buyEvidence.completenessScore || 0) / 100 * 15, 0, 15)
  const score = Math.round(clamp(drawdownScore + volatilityScore + returnScore + sampleScore + evidenceScore))
  const sipFriendlyScore = Math.round(clamp(
    score
      + (drawdown !== null && drawdown <= riskBudget * 0.45 ? 6 : 0)
      + (volatility !== null && volatility <= volBudget * 0.5 ? 4 : 0)
      + (purchasePlan === 'sip' ? 4 : 0)
      - (annualReturn !== null && annualReturn < 0 ? 6 : 0)
      - (ageDays !== null && ageDays < 365 ? 8 : 0),
  ))
  const drawdownStress = drawdown === null ? null : Math.round(clamp((drawdown / riskBudget) * 100, 0, 200))
  const level =
    score >= 80
      ? 'comfortable'
      : score >= 65
        ? 'watchable'
        : score >= 45
          ? 'bumpy'
          : 'stressful'
  const labelMap = {
    comfortable: '持有体验较稳',
    watchable: '可观察持有',
    bumpy: '波动需适应',
    stressful: '持有压力较高',
  } as const

  const reasons = [
    drawdown === null
      ? '回撤数据缺失，体验评分已降权'
      : `最大回撤占当前画像预算约 ${drawdownStress}%`,
    volatility === null
      ? '波动率缺失，需补齐净值序列复核'
      : `年化波动率 ${formatPercent(volatility)}`,
    annualReturn === null
      ? '收益样本缺失'
      : `近一年收益 ${formatPercent(annualReturn)}`,
  ]
  const warnings = [
    ageDays !== null && ageDays < 365 ? '成立不足一年，持有体验样本偏短' : '',
    drawdown !== null && drawdown > riskBudget ? '历史回撤超过当前画像预算' : '',
    buyEvidence.requiredMissingCount > 0 ? `研究申赎证据仍有 ${buyEvidence.requiredMissingCount} 项必补` : '',
  ].filter(Boolean)

  return {
    score,
    label: labelMap[level],
    level,
    sipFriendlyScore,
    drawdownStress,
    sampleStatus: ageDays === null ? 'unknown' : ageDays >= 365 ? 'usable' : 'short',
    sampleNote: ageDays === null ? '成立日期缺失' : ageDays >= 365 ? `样本约 ${Math.round(ageDays / 30)} 个月` : `短样本：约 ${Math.round(ageDays / 30)} 个月`,
    reasons,
    warnings,
    disclaimer: `持有体验基于历史收益、回撤、波动、样本长度、证据完整度和${purchasePlanLabel[purchasePlan]}参数估算，不代表未来收益或真实申赎成本。`,
  }
}

function buildPerformanceQualityDecision(fund: any, preferences: InvestorPreferences, safeProfile: RiskProfile) {
  const annualReturn = asNumber(fund.annualReturn)
  const drawdown = fund.maxDrawdown === null || fund.maxDrawdown === undefined ? null : Math.abs(Number(fund.maxDrawdown))
  const volatility = asNumber(fund.volatility)
  const ageDays = asNumber(fund.ageDays)
  const peerMetrics = fund.peerPercentiles?.metrics || {}
  const returnPercentile = asNumber(peerMetrics.annualReturn?.percentile)
  const drawdownPercentile = asNumber(peerMetrics.maxDrawdown?.percentile)
  const volatilityPercentile = asNumber(peerMetrics.volatility?.percentile)
  const peerScore = asNumber(fund.peerPercentiles?.peerScore)
  const sampleMonths = ageDays === null ? null : Math.round(ageDays / 30)
  const returnScore = annualReturn === null
    ? 0
    : annualReturn >= 0.12
      ? 26
      : annualReturn >= 0.08
        ? 22
        : annualReturn >= 0.03
          ? 16
          : annualReturn >= 0
            ? 10
            : 2
  const drawdownBudget = resolveRiskBudget(safeProfile, preferences)
  const drawdownScore = drawdown === null ? 0 : clamp((1 - drawdown / drawdownBudget) * 22, 0, 22)
  const volatilityScore = volatility === null ? 0 : clamp((1 - volatility / volatilityLimit(safeProfile)) * 14, 0, 14)
  const peerQualityScore = peerScore === null ? 0 : clamp(peerScore / 100 * 18, 0, 18)
  const sampleScore = ageDays === null ? 0 : ageDays >= 1095 ? 12 : ageDays >= 730 ? 10 : ageDays >= 365 ? 7 : 2
  const evidenceScore = [annualReturn, drawdown, volatility, peerScore, ageDays].filter((value) => value !== null).length * 2
  const qualityScore = Math.round(clamp(returnScore + drawdownScore + volatilityScore + peerQualityScore + sampleScore + evidenceScore, 0, 100))
  const evidenceGaps = uniqueText([
    annualReturn === null ? '近一年收益' : '',
    drawdown === null ? '最大回撤' : '',
    volatility === null ? '波动率' : '',
    peerScore === null ? '同类分位' : '',
    ageDays === null ? '成立日期/样本长度' : '',
  ])
  const hardBlocks = uniqueText([
    evidenceGaps.length >= 3 ? '收益质量证据不足，不能用近期收益作研究依据' : '',
    ageDays !== null && ageDays < 365 ? '成立不足一年，不能确认业绩持续性' : '',
    annualReturn !== null && annualReturn > 0.18 && (drawdown === null || volatility === null) ? '高收益但风险证据缺失，禁止直接晋级' : '',
  ])
  const warnings = uniqueText([
    annualReturn !== null && annualReturn < 0 ? '近一年收益为负，需确认是否只是短期逆风还是长期失效' : '',
    returnPercentile !== null && returnPercentile >= 80 && (drawdownPercentile === null || drawdownPercentile < 45) ? '收益靠前但回撤控制未同步靠前，可能是高风险换收益' : '',
    volatilityPercentile !== null && volatilityPercentile < 35 ? '同类波动控制靠后，持有体验可能较差' : '',
    drawdown !== null && drawdown > drawdownBudget ? '最大回撤超过当前画像预算' : '',
    peerScore !== null && peerScore < 45 ? '同类综合低于中位数，除非有反转证据否则不进入正式候选' : '',
    ageDays !== null && ageDays < 1095 ? '样本不足三年，持续性只能弱判断' : '',
  ])
  const status = hardBlocks.length
    ? 'blocked'
    : qualityScore >= 78 && warnings.length <= 1
      ? 'durable'
      : qualityScore >= 58
        ? 'watch'
        : evidenceGaps.length
          ? 'missing'
          : 'weak'
  const label = status === 'durable'
    ? '收益质量较稳'
    : status === 'watch'
      ? '收益质量待观察'
      : status === 'blocked'
        ? '禁止收益驱动晋级'
        : status === 'missing'
          ? '收益证据待补'
          : '收益质量偏弱'
  const primaryRisk = hardBlocks[0] || warnings[0] || '收益、回撤、波动、同类分位和样本长度暂未见明显冲突。'
  return {
    status,
    label,
    qualityScore,
    annualReturn,
    drawdown,
    volatility,
    peerScore,
    returnPercentile,
    drawdownPercentile,
    volatilityPercentile,
    sampleMonths,
    evidenceGaps,
    hardBlocks,
    warnings,
    primaryRisk,
    rule: '不能只看近一年收益；必须同时看回撤、波动、同类分位和样本长度，缺失字段不加分。',
    nextAction: status === 'durable'
      ? '可进入同类横评和研究复核报告，但仍需检查销售规则硬门禁。'
      : hardBlocks.length
        ? '先补净值/风险/同类分位证据，补齐前不能作为正式研究候选。'
        : '放入观察队列，用同类替代和更长样本验证收益是否可持续。',
  }
}

function buildPerformanceQualityQueue({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  return ranked
    .slice(0, 12)
    .map((fund: any) => {
      const decision = buildPerformanceQualityDecision(fund, preferences, safeProfile)
      const comparisonCodes = ranked
        .filter((item: any) => item.windCode !== fund.windCode && (item.type || '未分类') === (fund.type || '未分类'))
        .slice(0, 3)
        .map((item: any) => item.windCode)
      const comparisonHref = comparisonCodes.length
        ? `/analysis/comparison?${new URLSearchParams({
          codes: [fund.windCode, ...comparisonCodes].join(','),
          profile: safeProfile,
          horizon: preferences.horizon,
          purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
          autoReplay: '1',
        }).toString()}`
        : ''
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type || '未分类',
        investorScore: fund.investorScore,
        ...decision,
        actionHref: comparisonHref || `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
        comparisonHref,
      }
    })
    .sort((left: any, right: any) => {
      const rank: Record<string, number> = { blocked: 0, missing: 1, weak: 2, watch: 3, durable: 4 }
      return rank[left.status] - rank[right.status]
        || left.qualityScore - right.qualityScore
        || right.investorScore - left.investorScore
    })
    .slice(0, 4)
}

function returnRiskQuadrant(fund: any, safeProfile: RiskProfile, preferences: InvestorPreferences) {
  const annualReturn = asNumber(fund.annualReturn)
  const drawdown = fund.maxDrawdown === null || fund.maxDrawdown === undefined ? null : Math.abs(Number(fund.maxDrawdown))
  const volatility = asNumber(fund.volatility)
  const riskBudget = resolveRiskBudget(safeProfile, preferences)
  const returnTarget = safeProfile === 'conservative' ? 0.035 : safeProfile === 'balanced' ? 0.08 : 0.12
  const highReturn = annualReturn !== null && annualReturn >= returnTarget
  const lowReturn = annualReturn !== null && annualReturn < returnTarget * 0.5
  const highRisk = (drawdown !== null && drawdown > riskBudget) || (volatility !== null && volatility > volatilityLimit(safeProfile))
  const lowRisk = (drawdown !== null && drawdown <= riskBudget * 0.7) && (volatility === null || volatility <= volatilityLimit(safeProfile) * 0.75)
  const evidenceGaps = uniqueText([
    annualReturn === null ? '收益' : '',
    drawdown === null ? '回撤' : '',
    volatility === null ? '波动' : '',
  ])
  const quadrant = evidenceGaps.length >= 2
    ? 'evidence_missing'
    : highReturn && lowRisk
      ? 'efficient'
      : highReturn && highRisk
        ? 'hot_but_volatile'
        : lowReturn && highRisk
          ? 'inefficient'
          : lowReturn && lowRisk
            ? 'defensive'
            : 'balanced'
  const labelMap: Record<string, string> = {
    efficient: '高收益低风险',
    hot_but_volatile: '高收益高波动',
    inefficient: '低收益高风险',
    defensive: '低收益低风险',
    balanced: '收益风险均衡',
    evidence_missing: '象限证据待补',
  }
  const actionMap: Record<string, string> = {
    efficient: '可进入同类横评验证是否稳定领先，并继续检查销售规则硬门禁。',
    hot_but_volatile: '不能只因收益高晋级；先做回撤、回本和同类替代横评。',
    inefficient: '优先作为排除样本，除非存在明确风格逆风后的反转证据。',
    defensive: '适合低波动观察，但需确认收益是否满足当前持有期目标。',
    balanced: '继续用同类横评、经理归因和费用证据判断是否值得推进。',
    evidence_missing: '补齐收益、回撤和波动字段后再进入正式筛选。',
  }
  const riskFlag = highRisk ? '风险超预算' : lowRisk ? '风险较低' : '风险中性'
  const returnFlag = highReturn ? '收益达标' : lowReturn ? '收益不足' : '收益中性'
  return {
    quadrant,
    label: labelMap[quadrant],
    annualReturn,
    returnTarget,
    drawdown,
    riskBudget,
    volatility,
    riskFlag,
    returnFlag,
    evidenceGaps,
    primaryRead: `${returnFlag} / ${riskFlag}`,
    rule: '收益-风险象限只使用真实收益、回撤和波动字段；证据缺失时不把基金放入优势象限。',
    nextAction: actionMap[quadrant],
  }
}

function buildReturnRiskQuadrantQueue({
  ranked,
  safeProfile,
  preferences,
}: {
  ranked: any[]
  safeProfile: RiskProfile
  preferences: InvestorPreferences
}) {
  return ranked
    .slice(0, 12)
    .map((fund: any) => {
      const decision = returnRiskQuadrant(fund, safeProfile, preferences)
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type || '未分类',
        investorScore: fund.investorScore,
        peerScore: fund.peerPercentiles?.peerScore ?? null,
        ...decision,
        actionHref: `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
      }
    })
    .sort((left: any, right: any) => {
      const rank: Record<string, number> = {
        hot_but_volatile: 0,
        inefficient: 1,
        evidence_missing: 2,
        defensive: 3,
        balanced: 4,
        efficient: 5,
      }
      return rank[left.quadrant] - rank[right.quadrant]
        || right.investorScore - left.investorScore
    })
    .slice(0, 4)
}

type PeerMetric = {
  label: string
  value: number | null
  percentile: number | null
  rank: number | null
  peerCount: number
  unit: 'percent' | 'score'
  direction: 'higher' | 'lower'
}

function percentileMetric({
  peers,
  target,
  getter,
  label,
  unit,
  higherIsBetter,
}: {
  peers: any[]
  target: any
  getter: (fund: any) => number | null
  label: string
  unit: PeerMetric['unit']
  higherIsBetter: boolean
}): PeerMetric {
  const valid = peers
    .map((fund) => ({ fund, value: getter(fund) }))
    .filter((item): item is { fund: any; value: number } => item.value !== null)
  const targetValue = getter(target)
  if (targetValue === null) {
    return {
      label,
      value: null,
      percentile: null,
      rank: null,
      peerCount: valid.length,
      unit,
      direction: higherIsBetter ? 'higher' : 'lower',
    }
  }
  const sorted = valid.sort((left, right) => higherIsBetter ? right.value - left.value : left.value - right.value)
  const rank = sorted.findIndex((item) => item.fund.windCode === target.windCode) + 1
  const peerCount = sorted.length
  const percentile = peerCount <= 1 || rank <= 0 ? 100 : Math.round(((peerCount - rank) / (peerCount - 1)) * 100)
  return {
    label,
    value: targetValue,
    percentile,
    rank: rank > 0 ? rank : null,
    peerCount,
    unit,
    direction: higherIsBetter ? 'higher' : 'lower',
  }
}

function attachPeerPercentiles(funds: any[]) {
  const groups = funds.reduce((acc: Record<string, any[]>, fund: any) => {
    const key = fund.type || '未分类'
    acc[key] = acc[key] || []
    acc[key].push(fund)
    return acc
  }, {})

  return funds.map((fund: any) => {
    const peers = groups[fund.type || '未分类'] || [fund]
    const metrics = {
      annualReturn: percentileMetric({
        peers,
        target: fund,
        getter: (item) => item.annualReturn,
        label: '同类 1Y 收益',
        unit: 'percent',
        higherIsBetter: true,
      }),
      maxDrawdown: percentileMetric({
        peers,
        target: fund,
        getter: (item) => item.maxDrawdown === null ? null : Math.abs(item.maxDrawdown),
        label: '同类回撤控制',
        unit: 'percent',
        higherIsBetter: false,
      }),
      volatility: percentileMetric({
        peers,
        target: fund,
        getter: (item) => item.volatility,
        label: '同类波动控制',
        unit: 'percent',
        higherIsBetter: false,
      }),
      investorScore: percentileMetric({
        peers,
        target: fund,
        getter: (item) => item.investorScore,
        label: '同类选基分',
        unit: 'score',
        higherIsBetter: true,
      }),
    }
    const validPercentiles = Object.values(metrics)
      .map((metric) => metric.percentile)
      .filter((value): value is number => value !== null)
    const peerScore = validPercentiles.length
      ? Math.round(validPercentiles.reduce((sum, value) => sum + value, 0) / validPercentiles.length)
      : null
    const strengthLabels = Object.values(metrics)
      .filter((metric) => metric.percentile !== null && metric.percentile >= 70)
      .map((metric) => `${metric.label}前列`)
    const weaknessLabels = Object.values(metrics)
      .filter((metric) => metric.percentile !== null && metric.percentile <= 30)
      .map((metric) => `${metric.label}靠后`)

    return {
      ...fund,
      peerPercentiles: {
        peerGroup: `${fund.type || '未分类'}同类池`,
        peerCount: peers.length,
        source: 'investor_selection_type_peer_group',
        peerScore,
        metrics,
        strengthLabels,
        weaknessLabels,
      },
    }
  })
}

async function fetchCandidateFunds({
  type,
  keyword,
  sourceLimit,
  purchasePlan,
  plannedAmount,
  requireSalesRule,
  eligibleOnly,
  researchChecklistStatus,
  safeProfile,
}: {
  type: string
  keyword: string
  sourceLimit: number
  purchasePlan: PurchasePlan
  plannedAmount: number
  requireSalesRule: boolean
  eligibleOnly: boolean
  researchChecklistStatus: string
  safeProfile: RiskProfile
}) {
  const fundMap = new Map<string, Record<string, unknown>>()
  let backendTotal = 0
  let source = 'backend'
  let fetchedPages = 0
  const baseSelectionUniverses: CandidateSelectionUniverse[] = [
    { key: 'screening_score', sortBy: 'screening_score', sortOrder: 'desc' },
    { key: 'return', sortBy: 'return', sortOrder: 'desc' },
    { key: 'risk', sortBy: 'risk', sortOrder: 'asc' },
    { key: 'sharpe', sortBy: 'sharpe', sortOrder: 'desc' },
    { key: 'total_asset', sortBy: 'total_asset', sortOrder: 'desc' },
    { key: 'updated_at', sortBy: 'updated_at', sortOrder: 'desc' },
  ]
  const strictSelectionUniverses: CandidateSelectionUniverse[] = requireSalesRule || eligibleOnly
    ? [
        { key: 'strict_screening_score', sortBy: 'screening_score', sortOrder: 'desc', strictSalesRule: true },
        { key: 'strict_sharpe', sortBy: 'sharpe', sortOrder: 'desc', strictSalesRule: true },
      ]
    : []
  const selectionUniverses = [...baseSelectionUniverses, ...strictSelectionUniverses]
  const perUniverseLimit = Math.max(20, Math.ceil(sourceLimit / selectionUniverses.length))
  const universeDiagnostics: Array<{ key: string; requested: number; received: number }> = []

  for (const universe of selectionUniverses) {
    const backendParams = new URLSearchParams({
      page: '1',
      page_size: String(perUniverseLimit),
      sort_by: universe.sortBy,
      sort_order: universe.sortOrder,
      tradable_only: 'true',
    })
    if (type) backendParams.set('fund_type', type)
    if (keyword) backendParams.set('keyword', keyword)
    if (researchChecklistStatus) backendParams.set('research_checklist_status', researchChecklistStatus)
    if (universe.strictSalesRule) {
      backendParams.set('sales_rule_complete', 'true')
      backendParams.set('purchase_plan', purchasePlan)
      backendParams.set('planned_amount', String(plannedAmount))
      backendParams.set('sales_risk_filter', 'matched')
      backendParams.set('max_sales_risk_level', String(profileMaxRiskLevel[safeProfile]))
    }

    const response = await fetch(`${backendApiBaseUrl}/api/funds?${backendParams.toString()}`, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || '读取基金列表失败')
    }

    const pageFunds = Array.isArray(payload.funds) ? payload.funds : []
    backendTotal = Number(payload.total || backendTotal || pageFunds.length)
    source = payload.source || source
    fetchedPages += 1
    universeDiagnostics.push({
      key: universe.key,
      requested: perUniverseLimit,
      received: pageFunds.length,
    })
    for (const fund of pageFunds) {
      const windCode = String(fund.wind_code || fund.windCode || '').trim().toUpperCase()
      if (windCode && !fundMap.has(windCode) && fundMap.size < sourceLimit) {
        fundMap.set(windCode, fund)
      }
    }
  }

  return {
    rawFunds: Array.from(fundMap.values()),
    backendTotal,
    fetchedPages,
    source,
    candidateSource: 'multi_factor_database_prefilter',
    universeDiagnostics,
  }
}

async function fetchSalesRuleGapMap(windCodes: string[], purchasePlan: PurchasePlan, plannedAmount: number) {
  const uniqueCodes = Array.from(new Set(windCodes.map((code) => String(code || '').trim().toUpperCase()).filter(Boolean)))
  const gapMap = new Map<string, Awaited<ReturnType<typeof getSalesRuleGapsForCodes>>['gaps'][number]>()
  const amountGateMap = new Map<string, SalesRuleExecutionAmountGate>()
  const chunkSize = 300
  for (let index = 0; index < uniqueCodes.length; index += chunkSize) {
    const chunk = uniqueCodes.slice(index, index + chunkSize)
    if (!chunk.length) continue
    const payload = await getSalesRuleGapsForCodes(chunk, chunk.length, { purchasePlan, plannedAmount })
    for (const rule of payload.rules || []) {
      amountGateMap.set(rule.windCode.toUpperCase(), rule.executionAmountGate)
    }
    for (const gap of payload.gaps || []) {
      gapMap.set(gap.windCode.toUpperCase(), gap)
    }
  }
  return { gapMap, amountGateMap }
}

function attachCurrentSalesRuleGate(
  funds: any[],
  salesRuleGapMap: Awaited<ReturnType<typeof fetchSalesRuleGapMap>>['gapMap'],
  salesRuleAmountGateMap: Awaited<ReturnType<typeof fetchSalesRuleGapMap>>['amountGateMap'],
  activeSalesRuleEvidenceAlertsByCode: Map<string, ActiveSalesRuleEvidenceAlert[]>,
  purchasePlan: PurchasePlan,
  plannedAmount: number,
) {
  return funds.map((fund) => {
    const windCode = String(fund.windCode || '').toUpperCase()
    const gap = salesRuleGapMap.get(windCode) || null
    const activeAlerts = activeSalesRuleEvidenceAlertsByCode.get(windCode) || []
    const alertMissingItems = activeAlerts.map((alert) => `复查队列未解决：${alert.title}${alert.message ? `（${alert.message}）` : ''}`)
    const executionAmountGate = salesRuleAmountGateMap.get(windCode) || null
    if (!gap && !activeAlerts.length) {
      return {
        ...fund,
        salesRuleGap: null,
        executionAmountGate,
        currentSalesRuleGate: {
          status: 'ready',
          missingCount: 0,
          missingItems: [],
          executionAmountGate,
          source: 'explicit_codes_plus_local_sales_rules',
        },
      }
    }

    const missingItems = uniqueText([
      ...(gap?.missingItems || []),
      ...alertMissingItems,
    ])
    const missingCount = (gap?.missingCount || 0) + activeAlerts.length
    const priority = gap?.priority || 'high'
    const gateActionHref = salesRulesHrefForCodes(windCode, purchasePlan, plannedAmount)
    const gapSummary = activeAlerts.length
      ? `销售规则/R1-R5 复查队列未清零：${missingItems.slice(0, 4).join('、')}`
      : `销售规则硬缺口 ${missingCount} 项：${missingItems.slice(0, 4).join('、')}`
    const originalGate = fund.purchaseGate || {}
    return {
      ...fund,
      salesRuleGap: {
        windCode: gap?.windCode || windCode,
        fundName: gap?.fundName || fund.name,
        priority,
        missingCount,
        missingItems,
        nextAction: activeAlerts.length ? '先处理复查队列中的销售规则/R1-R5证据事件' : gap?.nextAction,
        ruleSourceUpdatedAt: gap?.ruleSourceUpdatedAt || null,
        executionAmountGate: gap?.executionAmountGate || executionAmountGate,
      },
      executionAmountGate: gap?.executionAmountGate || executionAmountGate,
      currentSalesRuleGate: {
        status: 'blocked',
        missingCount,
        missingItems,
        priority,
        actionHref: gateActionHref,
        alertsHref: reviewEventsHref(),
        ruleSourceUpdatedAt: gap?.ruleSourceUpdatedAt || null,
        executionAmountGate: gap?.executionAmountGate || executionAmountGate,
        source: activeAlerts.length
          ? 'explicit_codes_plus_local_sales_rules+local.alert_events.sales_rule_evidence'
          : 'explicit_codes_plus_local_sales_rules',
      },
      purchaseGate: {
        ...originalGate,
        level: originalGate.level === 'blocked' ? 'blocked' : 'verify_first',
        label: originalGate.level === 'blocked' ? originalGate.label : '先补销售规则',
        description: originalGate.level === 'blocked'
          ? originalGate.description
          : '当前销售规则硬缺口未清零，不能作为研究候选进入后续横比或报告保存。',
        cautionFlags: uniqueText([
          ...(originalGate.cautionFlags || []),
          gapSummary,
        ]),
        mustVerifyBeforeBuy: uniqueText([
          gapSummary,
          ...(originalGate.mustVerifyBeforeBuy || []),
        ]),
      },
    }
  })
}

function buildSalesRuleUnlockReadiness(fund: any, minimumEvidenceGrade: EvidenceGrade) {
  const originalGate = fund.purchaseGate || {}
  const hardBlocks = (originalGate.hardBlocks || []) as string[]
  const nonSalesHardBlocks = hardBlocks.filter((item) => !String(item).includes('销售规则'))
  const evidenceGradeValue = (originalGate.evidenceGrade || 'D') as EvidenceGrade
  const evidenceReady = passesEvidenceGrade(evidenceGradeValue, minimumEvidenceGrade)
  const formalCandidateAfterSalesRule = nonSalesHardBlocks.length === 0
    && originalGate.level !== 'blocked'
    && evidenceReady
  const missingCount = fund.salesRuleGap?.missingCount || fund.currentSalesRuleGate?.missingCount || 0
  const missingItems = fund.salesRuleGap?.missingItems || fund.currentSalesRuleGate?.missingItems || []
  const label = formalCandidateAfterSalesRule
    ? '补完销售规则可严格重评'
    : nonSalesHardBlocks.length
      ? '补销售规则后仍有硬阻断'
      : !evidenceReady
        ? `补销售规则后仍需证据达 ${minimumEvidenceGrade}`
        : '补完后仍需复核'
  const nextStep = formalCandidateAfterSalesRule
    ? '销售规则硬缺口清零后，回到严格筛选判断是否转为正式研究候选。'
    : nonSalesHardBlocks.length
      ? `先处理非销售硬阻断：${nonSalesHardBlocks.slice(0, 2).join('；')}`
      : !evidenceReady
        ? `销售规则之外，还要把证据等级从 ${evidenceGradeValue} 提升到 ${minimumEvidenceGrade}。`
        : '补完销售规则后仍需重新跑严格筛选确认。'

  return {
    formalCandidateAfterSalesRule,
    label,
    nextStep,
    evidenceReady,
    evidenceGrade: evidenceGradeValue,
    minEvidenceGrade: minimumEvidenceGrade,
    nonSalesHardBlockCount: nonSalesHardBlocks.length,
    nonSalesHardBlocks: nonSalesHardBlocks.slice(0, 4),
    missingCount,
    missingItems,
  }
}

function buildStrictBlockerDiagnostics({
  filterStats,
  rawEvaluated,
  minScore,
  minEvidenceGrade,
  minManagerYears,
  minCostScore,
  strictReviewHref,
  salesRulesHref,
  purchasePlan,
  plannedAmount,
}: {
  filterStats: Record<string, number>
  rawEvaluated: any[]
  minScore: number
  minEvidenceGrade: EvidenceGrade
  minManagerYears: number
  minCostScore: number
  strictReviewHref: string
  salesRulesHref: string
  purchasePlan: PurchasePlan
  plannedAmount: number
}) {
  const salesRuleEvidenceCopy = salesRuleEvidenceCopyForPlan(purchasePlan)
  const salesRuleFieldBuckets = Object.entries(
    rawEvaluated
      .filter((fund) => fund.currentSalesRuleGate?.status === 'blocked')
      .flatMap((fund) => fund.salesRuleGap?.missingItems || fund.currentSalesRuleGate?.missingItems || [])
      .reduce((bucket: Record<string, number>, item: string) => {
        bucket[item] = (bucket[item] || 0) + 1
        return bucket
      }, {}),
  )
    .map(([label, count]) => ({ label, count: Number(count) }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, 'zh-CN'))
    .slice(0, 8)
  const salesRuleBlockedSampleCodes = rawEvaluated
    .filter((fund) => fund.currentSalesRuleGate?.status === 'blocked')
    .sort((left, right) => right.investorScore - left.investorScore
      || (left.currentSalesRuleGate?.missingCount || 0) - (right.currentSalesRuleGate?.missingCount || 0))
    .slice(0, 8)
    .map((fund) => fund.windCode)
    .filter(Boolean)
  const salesRuleFieldActionHref = salesRuleBlockedSampleCodes.length
    ? salesRulesHrefForCodes(salesRuleBlockedSampleCodes, purchasePlan, plannedAmount, strictReviewHref)
    : salesRulesHref
  const totalBlocked = Object.entries(filterStats)
    .filter(([key]) => key !== 'included')
    .reduce((sum, [, count]) => sum + Number(count || 0), 0)
  const sampleCode = (predicate: (fund: any) => boolean) =>
    rawEvaluated.find(predicate)?.windCode || ''
  const diagnostics = [
    {
      key: 'sales_rule_gap_blocked',
      label: '销售规则硬缺口',
      count: filterStats.sales_rule_gap_blocked || filterStats.sales_rule_incomplete || filterStats.sales_rule_missing || 0,
      severity: 'hard',
      detail: salesRuleEvidenceCopy.hardGapDetail,
      nextAction: salesRuleFieldBuckets.length
        ? `先补字段：${salesRuleFieldBuckets.slice(0, 4).map((item) => `${item.label}(${item.count})`).join('、')}；补完后回到严格选基重评。`
        : '先批量补销售规则，补完后回到严格选基重评。',
      href: salesRuleFieldActionHref,
      sampleCode: sampleCode((fund) => fund.currentSalesRuleGate?.status === 'blocked'),
      fieldBuckets: salesRuleFieldBuckets,
      sampleCodes: salesRuleBlockedSampleCodes,
    },
    {
      key: 'not_purchase_candidate',
      label: '非研究候选',
      count: filterStats.not_purchase_candidate || 0,
      severity: 'hard',
      detail: '基金仍处于验证优先、暂缓、不可申购、风险不匹配或证据不足状态。',
      nextAction: '进入研究样本模式查看被拦截基金，逐项补净值、申赎、风险和持仓证据。',
      href: '/market?source=research-candidates&eligibleOnly=false&requireSalesRule=false',
      sampleCode: sampleCode((fund) => !['research_ready', 'watchlist'].includes(fund.purchaseGate?.level)),
    },
    {
      key: 'evidence_below_threshold',
      label: '证据等级不足',
      count: filterStats.evidence_below_threshold || 0,
      severity: 'evidence',
      detail: `当前要求证据等级不低于 ${minEvidenceGrade}，净值、回撤、规模、经理或销售端证据不足会被排除。`,
      nextAction: '先降低证据等级查看样本，或补齐净值/风险/销售端字段后再重评。',
      href: strictReviewHref.replace(/minEvidenceGrade=[A-D]/, 'minEvidenceGrade=D'),
      sampleCode: sampleCode((fund) => !passesEvidenceGrade(fund.purchaseGate?.evidenceGrade, minEvidenceGrade)),
    },
    {
      key: 'score_below_threshold',
      label: '选基分不足',
      count: filterStats.score_below_threshold || 0,
      severity: 'soft',
      detail: `当前最低选基分为 ${minScore}，收益、回撤、类型适配、经理、成本和证据共同影响得分。`,
      nextAction: '降低分数阈值或切换低回撤/成本/同类优势视角重新观察。',
      href: strictReviewHref.replace(/minScore=\d+/, 'minScore=0'),
      sampleCode: sampleCode((fund) => fund.investorScore < minScore),
    },
    {
      key: 'manager_tenure_below_threshold',
      label: '经理任期不足',
      count: filterStats.manager_tenure_below_threshold || 0,
      severity: 'evidence',
      detail: `当前要求经理任期不少于 ${minManagerYears} 年；经理缺失或任期过短会影响业绩归因可靠性。`,
      nextAction: '取消经理任期硬过滤，或先补基金经理任职关系和任期样本。',
      href: strictReviewHref.replace(/&?minManagerYears=\d+(\.\d+)?/, ''),
      sampleCode: sampleCode((fund) => (fund.managerEvidence?.maxTenureYears ?? -1) < minManagerYears),
    },
    {
      key: 'cost_below_threshold',
      label: '成本证据不足',
      count: filterStats.cost_below_threshold || 0,
      severity: 'evidence',
      detail: `当前要求成本证据至少 ${minCostScore} 分；${salesRuleEvidenceCopy.costFilterFields}缺失会被排除。`,
      nextAction: '补销售平台费率与申赎规则，或暂时取消成本硬过滤观察样本。',
      href: strictReviewHref.replace(/&?minCostScore=\d+(\.\d+)?/, ''),
      sampleCode: sampleCode((fund) => (fund.costEvidence?.score ?? -1) < minCostScore),
    },
  ]
    .filter((item) => item.count > 0)
    .sort((left, right) => {
      const severityWeight: Record<string, number> = { hard: 3, evidence: 2, soft: 1 }
      return (severityWeight[right.severity] || 0) - (severityWeight[left.severity] || 0)
        || right.count - left.count
    })
  const includedCount = filterStats.included || 0
  const primary = diagnostics[0] || null
  const fieldBlockers = salesRuleFieldBuckets
  const sampleFunds = rawEvaluated
    .filter((fund) => fund.currentSalesRuleGate?.status === 'blocked')
    .sort((left, right) => right.investorScore - left.investorScore
      || (left.currentSalesRuleGate?.missingCount || 0) - (right.currentSalesRuleGate?.missingCount || 0))
    .slice(0, 5)
    .map((fund) => ({
      windCode: fund.windCode,
      name: fund.name,
      investorScore: fund.investorScore,
      missingCount: fund.currentSalesRuleGate?.missingCount || fund.salesRuleGap?.missingCount || 0,
      primaryMissing: (fund.salesRuleGap?.missingItems || fund.currentSalesRuleGate?.missingItems || [])[0] || '销售规则字段待补',
      href: `/funds/${encodeURIComponent(fund.id || fund.windCode)}`,
    }))
  const unlockSequence = [
    primary ? {
      step: 1,
      label: `先处理：${primary.label}`,
      detail: primary.nextAction,
      href: primary.href,
    } : null,
    fieldBlockers.length ? {
      step: 2,
      label: '按字段批量补证',
      detail: `不按基金逐只盲补，优先补 ${fieldBlockers.slice(0, 3).map((item) => item.label).join('、')}。`,
      href: salesRuleFieldActionHref,
    } : null,
    {
      step: fieldBlockers.length ? 3 : 2,
      label: '补完后严格重评',
      detail: '销售规则、证据等级、分数和经理/成本硬过滤全部过关后，才允许进入正式研究候选。',
      href: strictReviewHref,
    },
  ].filter(Boolean)

  return {
    totalBlocked,
    hasStrictFilters: true,
    primary,
    diagnostics,
    fieldBlockers,
    sampleCodes: salesRuleBlockedSampleCodes,
    salesRulesHref: salesRuleFieldActionHref,
    strictReevaluationExplanation: {
      title: includedCount === 0 ? '严格重评为什么没有结果' : '严格重评放行解释',
      verdict: includedCount === 0
        ? '这不是“没有值得研究的基金”，而是当前样本没有基金同时通过正式研究硬门槛。'
        : `当前严格模式已有 ${includedCount} 只通过硬门槛，仍需逐只复核报告证据。`,
      strictResultCount: includedCount,
      sourceEvaluatedCount: rawEvaluated.length,
      blockedCount: totalBlocked,
      primaryBlocker: primary ? {
        key: primary.key,
        label: primary.label,
        count: primary.count,
        detail: primary.detail,
        nextAction: primary.nextAction,
        href: primary.href,
      } : null,
      fieldBlockers: fieldBlockers.slice(0, 6),
      sampleFunds,
      unlockSequence,
      researchFallbackHref: '/market?source=research-candidates&eligibleOnly=false&requireSalesRule=false&minEvidenceGrade=D',
      strictReviewHref,
      salesRulesHref: salesRuleFieldActionHref,
      hardBoundary: '严格重评为零只表示正式研究候选门禁未通过；不能据此输出研究结论，也不能把待补样本保存为正式研究复核报告。',
    },
    message: diagnostics.length
      ? `严格模式当前主要卡在：${diagnostics.slice(0, 3).map((item) => `${item.label} ${item.count} 只`).join('、')}。`
      : '当前严格模式没有识别到额外阻断；如结果为空，请扩大样本范围或放宽基金类型。'
  }
}

function hrefWithPurchaseContext(href: string, purchasePlan: PurchasePlan, plannedAmount: number) {
  const [path, rawQuery = ''] = href.split('?')
  const params = new URLSearchParams(rawQuery)
  params.set('purchasePlan', purchasePlan)
  params.set('plannedAmount', String(plannedAmount))
  params.set(purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(plannedAmount))
  const returnTo = params.get('returnTo')
  if (returnTo?.startsWith('/')) {
    params.set('returnTo', hrefWithPurchaseContext(returnTo, purchasePlan, plannedAmount))
  }
  return `${path}?${params.toString()}`
}

function buildSuitabilityCoverageHealth({
  impact,
  safeProfile,
  purchasePlan,
  plannedAmount,
}: {
  impact: Awaited<ReturnType<typeof getSalesRuleImpact>>
  safeProfile: RiskProfile
  purchasePlan: PurchasePlan
  plannedAmount: number
}) {
  const profileImpact = impact.profiles.find((profile) => profile.key === safeProfile) || impact.profiles[0] || null
  const coverage = impact.summary.riskLevelCoverage || 0
  const status = impact.summary.riskLevelMissingCount > 0
    ? coverage < 50
      ? 'blocked'
      : 'thin'
    : 'ready'
  const primaryAction = impact.nextActions.find((action) => action.priority === 'high') || impact.nextActions[0] || null
  const candidateAction = impact.nextActions.find((action) => action.href.includes('candidate_missing_risk')) || null
  return {
    title: '全市场适当性覆盖健康',
    scope: 'sales_risk_suitability_coverage',
    status,
    statusLabel: status === 'ready' ? '适当性覆盖可用' : status === 'thin' ? '适当性覆盖偏薄' : '适当性硬门禁阻断',
    coverage,
    knownCount: impact.summary.riskLevelKnownCount,
    missingCount: impact.summary.riskLevelMissingCount,
    totalFunds: impact.totalFunds,
    profile: profileImpact ? {
      key: profileImpact.key,
      label: profileImpact.label,
      maxSalesRiskLevel: profileImpact.maxSalesRiskLevel,
      matchedCount: profileImpact.matchedCount,
      mismatchCount: profileImpact.mismatchCount,
      missingRiskCount: profileImpact.missingRiskCount,
      actionHref: hrefWithPurchaseContext(profileImpact.actionHref, purchasePlan, plannedAmount),
      sampleFunds: profileImpact.sampleFunds,
    } : null,
    primaryAction: primaryAction ? { ...primaryAction, href: hrefWithPurchaseContext(primaryAction.href, purchasePlan, plannedAmount) } : null,
    candidateAction: candidateAction ? { ...candidateAction, href: hrefWithPurchaseContext(candidateAction.href, purchasePlan, plannedAmount) } : null,
    summary: impact.summary.riskLevelMissingCount > 0
      ? `全市场 ${impact.summary.riskLevelMissingCount} 只基金缺销售风险等级，${profileLabel[safeProfile]}画像无法完整判断 R1-R5 适当性匹配。`
      : '全市场销售风险等级已覆盖，可用画像风险等级筛选匹配池。',
    hardBoundary: '销售风险等级缺失时，适当性匹配不能被推断为通过；正式研究候选和报告必须等待 R1-R5 证据补齐。',
  }
}

function normalizeShareClassBaseName(name: string | null | undefined) {
  return String(name || '')
    .trim()
    .replace(/[（(]\s*(A|B|C|D|E|I|Y|H|人民币|美元现汇|美元现钞)\s*[）)]$/iu, '')
    .replace(/\s*(A|B|C|D|E|I|Y|H)类?$/iu, '')
    .replace(/\s*(人民币|美元现汇|美元现钞)$/u, '')
    .replace(/\s+/gu, '')
}

function inferShareClass(name: string | null | undefined) {
  const text = String(name || '').trim()
  const bracketMatch = text.match(/[（(]\s*(A|B|C|D|E|I|Y|H|人民币|美元现汇|美元现钞)\s*[）)]$/iu)
  if (bracketMatch) return bracketMatch[1].toUpperCase()
  const classMatch = text.match(/\s*(A|B|C|D|E|I|Y|H)类?$/iu)
  if (classMatch) return classMatch[1].toUpperCase()
  const currencyMatch = text.match(/\s*(人民币|美元现汇|美元现钞)$/u)
  if (currencyMatch) return currencyMatch[1]
  return ''
}

function shareClassCostRank(fund: any) {
  const cost = fund.costEvidence || {}
  const totalAnnualFee = asNumber(cost.totalAnnualFee)
  const purchaseFeeRate = asNumber(cost.purchaseFeeRate)
  const salesServiceFeeRate = asNumber(cost.salesServiceFeeRate)
  return {
    score: asNumber(cost.score) ?? 0,
    totalAnnualFee: totalAnnualFee ?? 99,
    purchaseFeeRate: purchaseFeeRate ?? 99,
    salesServiceFeeRate: salesServiceFeeRate ?? 99,
  }
}

function attachShareClassInfo(funds: any[]) {
  const groups = funds.reduce((acc: Record<string, any[]>, fund: any) => {
    const baseName = normalizeShareClassBaseName(fund.name)
    if (!baseName || baseName === String(fund.name || '').trim()) return acc
    const key = `${baseName}::${fund.type || ''}`
    acc[key] = acc[key] || []
    acc[key].push(fund)
    return acc
  }, {})

  return funds.map((fund) => {
    const baseName = normalizeShareClassBaseName(fund.name)
    const classType = inferShareClass(fund.name)
    const group = groups[`${baseName}::${fund.type || ''}`] || []
    if (!classType || group.length < 2) {
      return {
        ...fund,
        shareClassInfo: {
          baseName: baseName || fund.name,
          classType: classType || '未识别',
          siblingCount: group.length || 1,
          siblingCodes: [],
          siblingNames: [],
          siblingBestCostCode: null,
          siblingBestCostLabel: null,
          hint: classType ? '当前样本中暂未发现同基金其他份额，仍需在详情页核对是否存在 A/C/I 等份额差异。' : '份额类别未识别，按单一基金样本处理。',
          warnings: [] as string[],
        },
      }
    }

    const siblings = group
      .filter((item: any) => item.windCode !== fund.windCode)
      .sort((left: any, right: any) => left.windCode.localeCompare(right.windCode))
    const bestCostFund = [...group].sort((left: any, right: any) => {
      const leftCost = shareClassCostRank(left)
      const rightCost = shareClassCostRank(right)
      return rightCost.score - leftCost.score
        || leftCost.totalAnnualFee - rightCost.totalAnnualFee
        || leftCost.purchaseFeeRate - rightCost.purchaseFeeRate
        || leftCost.salesServiceFeeRate - rightCost.salesServiceFeeRate
    })[0]
    const warnings = [
      `同一基金存在 ${group.length} 个份额样本，不能只按收益分独立比较`,
      classType === 'C' ? 'C类通常更依赖销售服务费和持有期，短持/定投前需核总成本' : '',
      classType === 'A' ? 'A类通常需重点核申购费折扣和赎回持有期，长持前需核总成本' : '',
    ].filter(Boolean)

    return {
      ...fund,
      tags: uniqueText([...(fund.tags || []), '同基金多份额']),
      warnings: uniqueText([...(fund.warnings || []), ...warnings]),
      shareClassInfo: {
        baseName,
        classType,
        siblingCount: group.length,
        siblingCodes: siblings.map((item: any) => item.windCode),
        siblingNames: siblings.map((item: any) => item.name),
        siblingBestCostCode: bestCostFund?.windCode || null,
        siblingBestCostLabel: bestCostFund
          ? `${bestCostFund.name} · 成本 ${bestCostFund.costEvidence?.score ?? 0}/10`
          : null,
        hint: `先把 ${group.map((item: any) => `${inferShareClass(item.name) || '未知'}类 ${item.windCode}`).join('、')} 放在同一基金份额框架下比较，再结合持有期、申购费、销售服务费和赎回费判断。`,
        warnings,
      },
    }
  })
}

function buildSelectionDecisionPackage({
  ranked,
  rawEvaluated,
  safeProfile,
  safeLens,
  preferences,
  minScore,
  minEvidenceGrade,
  salesRuleUnlockPreview,
  salesRuleAmountGateMap,
  holdingExposureRiskQueue,
}: {
  ranked: any[]
  rawEvaluated: any[]
  safeProfile: RiskProfile
  safeLens: SelectionLens
  preferences: InvestorPreferences
  minScore: number
  minEvidenceGrade: EvidenceGrade
  salesRuleUnlockPreview: {
    nearPurchasableQueue?: Array<{ windCode: string; name: string; missingCount: number; missingItems: string[]; investorScore: number; actionHref: string }>
    bulkSalesRulesHref?: string
    strictReviewHref?: string
    unlockableCount?: number
  }
  salesRuleAmountGateMap?: Map<string, SalesRuleExecutionAmountGate>
  holdingExposureRiskQueue: ReturnType<typeof buildHoldingExposureRiskQueue>
}) {
  const formalCandidates = ranked
    .filter((fund: any) => fund.currentSalesRuleGate?.status !== 'blocked' && ['research_ready', 'watchlist'].includes(fund.purchaseGate?.level))
    .slice(0, 6)
  const salesRuleCandidates = ranked
    .filter((fund: any) => fund.currentSalesRuleGate?.status === 'blocked')
    .sort((left: any, right: any) => right.investorScore - left.investorScore
      || (left.currentSalesRuleGate?.missingCount || 0) - (right.currentSalesRuleGate?.missingCount || 0))
    .slice(0, 8)
  const evidenceCandidates = ranked
    .filter((fund: any) => fund.currentSalesRuleGate?.status !== 'blocked' && fund.purchaseGate?.level === 'verify_first')
    .slice(0, 6)
  const blockedCandidates = ranked
    .filter((fund: any) => fund.purchaseGate?.level === 'blocked')
    .slice(0, 6)
  const topFund = formalCandidates[0] || salesRuleCandidates[0] || evidenceCandidates[0] || ranked[0] || null
  const formalCodes = formalCandidates.slice(0, 4).map((fund: any) => fund.windCode)
  const salesRuleCodes = (salesRuleCandidates.length
    ? salesRuleCandidates
    : salesRuleUnlockPreview.nearPurchasableQueue || [])
    .slice(0, 8)
    .map((item: any) => item.windCode)
    .filter(Boolean)
  const compareCodes = (formalCodes.length >= 2 ? formalCodes : ranked
    .filter((fund: any) => fund.purchaseGate?.level !== 'blocked')
    .slice(0, 4)
    .map((fund: any) => fund.windCode))
  const comparisonHref = compareCodes.length >= 2
    ? `/analysis/comparison?${new URLSearchParams({
      codes: compareCodes.join(','),
      profile: safeProfile,
      horizon: preferences.horizon,
      purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
      autoReplay: '1',
    }).toString()}`
    : ''
  const strictReviewHref = salesRuleUnlockPreview.strictReviewHref || `/market?source=research-candidates&${new URLSearchParams({
    profile: safeProfile,
    lens: safeLens,
    horizon: preferences.horizon,
    purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
    eligibleOnly: 'true',
    requireSalesRule: 'true',
    minScore: String(minScore),
    minEvidenceGrade,
  }).toString()}`
  const salesRulesHref = salesRuleCodes.length
    ? salesRulesHrefForCodes(salesRuleCodes, preferences.purchasePlan, preferences.plannedAmount, strictReviewHref)
    : salesRuleUnlockPreview.bulkSalesRulesHref || salesRulesHrefForCodes([], preferences.purchasePlan, preferences.plannedAmount)
  const primaryAction = formalCandidates.length >= 2
    ? {
      kind: 'compare',
      label: '先横向比较可研究候选',
      href: comparisonHref,
      description: `当前有 ${formalCandidates.length} 只未见销售规则硬缺口的可研究样本，先同屏比较收益、回撤、经理、费用和持有回放。`,
    }
    : formalCandidates.length === 1
      ? {
        kind: 'detail',
        label: '打开首只可研究基金',
        href: `/funds/${encodeURIComponent(formalCandidates[0].id || formalCandidates[0].windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
        description: '当前只有 1 只可研究样本，先做单基金研究复核一页纸，再扩大同类替代样本。',
      }
      : salesRuleCandidates.length || salesRuleUnlockPreview.nearPurchasableQueue?.length
        ? {
          kind: 'sales_rules',
          label: '先批量补销售规则',
          href: salesRulesHref,
          description: `当前高分样本主要卡在销售规则硬缺口；补齐前不能进入正式研究候选、不能保存正式研究复核报告。`,
        }
        : {
          kind: 'relax_filters',
          label: '放宽条件重筛',
          href: '/market?source=research-candidates&eligibleOnly=false&requireSalesRule=false&minEvidenceGrade=D&minScore=0',
          description: '当前筛选没有形成可推进对象，先回到研究样本模式扩大样本。',
        }
  const challengeTargets = uniqueFundsByWindCode(formalCandidates.length
    ? formalCandidates
    : [topFund, ...evidenceCandidates, ...salesRuleCandidates].filter(Boolean))
    .slice(0, 3)
  const candidateChallenges = challengeTargets.map((fund: any) => buildCandidateChallenge({
    fund,
    alternatives: ranked,
    safeProfile,
    preferences,
  }))
  const shareClassDecisions = buildShareClassDecisionQueue({ ranked, shareClassUniverse: rawEvaluated, salesRuleAmountGateMap, safeProfile, preferences })
  const shareClassEvidenceGapQueue = buildShareClassEvidenceGapQueue({ ranked, safeProfile, preferences })
  const costDragQueue = buildCostDragQueue({ ranked, preferences })
  const pressureTestQueue = buildPressureTestQueue({ ranked, safeProfile, preferences })
  const executionFeasibilityQueue = buildExecutionFeasibilityQueue({ ranked, preferences, safeProfile })
  const purchasePlanFitQueue = buildPurchasePlanFitQueue({ ranked, preferences, safeProfile })
  const performanceQualityQueue = buildPerformanceQualityQueue({ ranked, safeProfile, preferences })
  const returnRiskQuadrantQueue = buildReturnRiskQuadrantQueue({ ranked, safeProfile, preferences })
  const evidenceFreshnessQueue = buildEvidenceFreshnessQueue({ ranked, safeProfile, preferences })
  const peerAlternativePools = buildPeerAlternativePools({ ranked, safeProfile, preferences })
  const amountGateAlternativeQueue = buildAmountGateAlternativeQueue({ ranked, safeProfile, preferences })
  const managerAttributionQueue = buildManagerAttributionQueue({ ranked, safeProfile, preferences })
  const redemptionHoldingRiskQueue = buildRedemptionHoldingRiskQueue({ ranked, safeProfile, preferences })
  const typeHorizonFitQueue = buildTypeHorizonFitQueue({ ranked, safeProfile, preferences })
  const scaleLiquidityRiskQueue = buildScaleLiquidityRiskQueue({ ranked, safeProfile, preferences })
  const candidatePromotionMatrix = buildCandidatePromotionMatrix({ ranked, safeProfile, preferences })
  const evidenceClosureQueue = buildEvidenceClosureQueue({ ranked, safeProfile, preferences, strictReviewHref })
  const reportReadinessRadar = buildReportReadinessRadar({ ranked, safeProfile, preferences })
  const buyBeforeLandmineBoard = buildBuyBeforeLandmineBoard({
    ranked,
    returnRiskQuadrantQueue,
    performanceQualityQueue,
    scaleLiquidityRiskQueue,
    holdingExposureRiskQueue,
    managerAttributionQueue,
    redemptionHoldingRiskQueue,
    preferences,
  })
  const doNotBuyDecisionBoard = buildDoNotBuyDecisionBoard({
    ranked,
    candidateChallenges,
    buyBeforeLandmineBoard,
    evidenceClosureQueue,
    reportReadinessRadar,
    preferences,
    safeProfile,
  })
  const suitabilityNarrative = buildSuitabilityNarrative({
    fund: topFund,
    preferences,
    safeProfile,
    landmine: buyBeforeLandmineBoard.find((item: any) => item.windCode === topFund?.windCode),
    quadrant: returnRiskQuadrantQueue.find((item: any) => item.windCode === topFund?.windCode),
  })
  const strictCandidateUnlockBoard = buildStrictCandidateUnlockBoard({
    ranked,
    salesRuleUnlockPreview,
    managerAttributionQueue,
    redemptionHoldingRiskQueue,
    typeHorizonFitQueue,
    executionFeasibilityQueue,
    evidenceFreshnessQueue,
    costDragQueue,
    safeProfile,
    preferences,
  })
  const nextActionRouter = buildNextActionRouter({
    primaryAction,
    buyBeforeLandmineBoard,
    evidenceClosureQueue,
    reportReadinessRadar,
    comparisonHref,
    salesRulesHref,
    strictReviewHref,
    preferences,
  })
  const decisionConfidenceMeter = buildDecisionConfidenceMeter({
    topFund,
    buyBeforeLandmineBoard,
    evidenceClosureQueue,
    reportReadinessRadar,
    nextActionRouter,
  })
  const leaderStabilityCheck = buildLeaderStabilityCheck({
    ranked,
    topFund,
    comparisonHref,
  })
  const headToHeadChallenge = buildHeadToHeadChallenge({
    topFund,
    ranked,
    preferences,
    safeProfile,
  })
  const prePurchaseChecklist = buildPrePurchaseChecklist({
    topFund,
    decisionConfidenceMeter,
    leaderStabilityCheck,
    headToHeadChallenge,
    reportReadinessRadar,
    holdingExposureRiskQueue,
    preferences,
    safeProfile,
  })
  const buyReadinessTrafficLight = buildBuyReadinessTrafficLight({
    prePurchaseChecklist,
    decisionConfidenceMeter,
    primaryAction,
  })
  const greenLightUnlockPath = buildGreenLightUnlockPath({
    prePurchaseChecklist,
    buyReadinessTrafficLight,
    strictReviewHref,
    comparisonHref,
    reportReadinessRadar,
    topFund,
    preferences,
  })
  const fieldSupplementTaskBasket = buildFieldSupplementTaskBasket({
    ranked,
    salesRuleUnlockPreview,
    preferences,
    strictReviewHref,
  })
  const salesRuleEvidenceCopy = salesRuleEvidenceCopyForPlan(preferences.purchasePlan)
  const whyThisOrder = [
    formalCandidates.length
      ? `先看 ${formalCandidates.length} 只无销售规则硬缺口样本，因为它们可以进入详情复核和横评。`
      : '当前没有无销售规则硬缺口的正式研究候选，不能把高分基金直接当作研究结论。',
    salesRuleCandidates.length
      ? `${salesRuleCandidates.length} 只当前榜单样本只适合补证观察，补齐${salesRuleEvidenceCopy.fields}后再严格重评。`
      : '',
    evidenceCandidates.length
      ? `${evidenceCandidates.length} 只未被销售规则拦截但证据边界偏薄，应先看详情页和同类替代。`
      : '',
    blockedCandidates.length
      ? `${blockedCandidates.length} 只存在风险预算、申购状态或适当性阻断，只用于排除误买。`
      : '',
  ].filter(Boolean)

  return {
    title: formalCandidates.length ? '研究候选已形成' : '先补证，不给研究结论',
    scope: 'fund_research_buy_before_selection',
    profile: safeProfile,
    profileLabel: profileLabel[safeProfile],
    lens: safeLens,
    contextLabel: `${profileLabel[safeProfile]} · ${preferences.horizonLabel} · ${preferences.purchasePlanLabel} · 计划 ${preferences.plannedAmount.toLocaleString('zh-CN')} 元`,
    primaryAction,
    focusFund: topFund
      ? {
        windCode: topFund.windCode,
        name: topFund.name,
        type: topFund.type,
        investorScore: topFund.investorScore,
        purchaseGateLabel: topFund.purchaseGate?.label,
        salesRuleMissingCount: topFund.currentSalesRuleGate?.missingCount || 0,
      }
      : null,
    cohorts: {
      formalCandidates: formalCandidates.map((fund: any) => ({
        windCode: fund.windCode,
        name: fund.name,
        investorScore: fund.investorScore,
        purchaseGateLabel: fund.purchaseGate?.label,
        actionHref: `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
      })),
      salesRuleQueue: (salesRuleCandidates.length ? salesRuleCandidates : salesRuleUnlockPreview.nearPurchasableQueue || []).slice(0, 6).map((item: any) => ({
        windCode: item.windCode,
        name: item.name,
        investorScore: item.investorScore,
        missingCount: item.currentSalesRuleGate?.missingCount || item.missingCount || 0,
        missingItems: item.currentSalesRuleGate?.missingItems || item.missingItems || [],
        actionHref: salesRulesHrefForCodes(item.windCode, preferences.purchasePlan, preferences.plannedAmount),
      })),
      evidenceReview: evidenceCandidates.map((fund: any) => ({
        windCode: fund.windCode,
        name: fund.name,
        investorScore: fund.investorScore,
        reason: fund.purchaseGate?.cautionFlags?.[0] || fund.buyEvidence?.conclusion || '证据边界待复核',
        actionHref: `/funds/${encodeURIComponent(fund.id || fund.windCode)}?profile=${safeProfile}&horizon=${preferences.horizon}&purchasePlan=${preferences.purchasePlan}&plannedAmount=${preferences.plannedAmount}`,
      })),
      blocked: blockedCandidates.map((fund: any) => ({
        windCode: fund.windCode,
        name: fund.name,
        investorScore: fund.investorScore,
        reason: fund.purchaseGate?.hardBlocks?.[0] || fund.purchaseGate?.description || '存在硬阻断',
      })),
    },
    candidateChallenges,
    shareClassDecisions,
    shareClassEvidenceGapQueue,
    costDragQueue,
    pressureTestQueue,
    executionFeasibilityQueue,
    purchasePlanFitQueue,
    performanceQualityQueue,
    returnRiskQuadrantQueue,
    evidenceFreshnessQueue,
    suitabilityNarrative,
    peerAlternativePools,
    amountGateAlternativeQueue,
    managerAttributionQueue,
    redemptionHoldingRiskQueue,
    typeHorizonFitQueue,
    scaleLiquidityRiskQueue,
    holdingExposureRiskQueue,
    buyBeforeLandmineBoard,
    doNotBuyDecisionBoard,
    doNotBuyDecisionPolicy: '硬阻断、证据缺口、风险错配和替代劣势必须先被解释或消除；没有说清暂不买理由的基金，不进入正式候选。',
    candidatePromotionMatrix,
    evidenceClosureQueue,
    reportReadinessRadar,
    strictCandidateUnlockBoard,
    nextActionRouter,
    decisionConfidenceMeter,
    leaderStabilityCheck,
    headToHeadChallenge,
    prePurchaseChecklist,
    buyReadinessTrafficLight,
    greenLightUnlockPath,
    fieldSupplementTaskBasket,
    counts: {
      sourceEvaluated: rawEvaluated.length,
      returned: ranked.length,
      formalCandidates: formalCandidates.length,
      salesRuleQueue: salesRuleCandidates.length || salesRuleUnlockPreview.nearPurchasableQueue?.length || 0,
      evidenceReview: evidenceCandidates.length,
      blocked: blockedCandidates.length,
      unlockable: salesRuleUnlockPreview.unlockableCount || 0,
    },
    whyThisOrder,
    nextSteps: [
      primaryAction,
      comparisonHref ? {
        kind: 'compare',
        label: '打开横向比较',
        href: comparisonHref,
        description: '用同一画像、同一持有期和研究方式比较收益、回撤、压力体验和费用证据。',
      } : null,
      salesRuleCodes.length ? {
        kind: 'sales_rules',
        label: '打开销售规则补证队列',
        href: salesRulesHref,
        description: '批量补齐销售平台硬字段，补完回到严格研究候选模式。',
      } : null,
      strictReviewHref ? {
        kind: 'strict_review',
        label: '补完后严格重评',
        href: strictReviewHref,
        description: '只看证据等级和销售规则过关的正式研究候选。',
      } : null,
    ].filter(Boolean),
    memoText: [
      '【基金研究筛选决策包】',
      `画像：${profileLabel[safeProfile]} · ${preferences.horizonLabel} · ${preferences.purchasePlanLabel} · 计划金额 ${preferences.plannedAmount.toLocaleString('zh-CN')} 元`,
      `结论：${formalCandidates.length ? `已有 ${formalCandidates.length} 只可进入研究候选` : '当前不输出研究结论，先补销售规则和证据'}`,
      topFund ? `首要样本：${topFund.name}（${topFund.windCode}），选基分 ${topFund.investorScore}，闸门 ${topFund.purchaseGate?.label}` : '',
      suitabilityNarrative ? `适合/不适合：${suitabilityNarrative.name}——${suitabilityNarrative.verdict}；不适合：${suitabilityNarrative.notFor.slice(0, 2).join('；')}` : '',
      `下一步：${primaryAction.label}。${primaryAction.description}`,
      candidateChallenges[0] ? `反证：${candidateChallenges[0].rebuttals[0]}` : '',
      candidateChallenges[0] ? `必须打败：${candidateChallenges[0].mustBeat.join('；')}` : '',
      candidateChallenges[0] ? `放弃线：${candidateChallenges[0].giveUpLines.join('；')}` : '',
      shareClassDecisions[0] ? `份额选择：${shareClassDecisions[0].baseName} 当前 ${shareClassDecisions[0].current.classType}类；${shareClassDecisions[0].decision}` : '',
      costDragQueue[0] ? `计划金额成本：${costDragQueue[0].name} 按 ${preferences.plannedAmount.toLocaleString('zh-CN')} 元估算，已知一年成本约 ${costDragQueue[0].oneYearKnownCost === null ? '待补' : `${costDragQueue[0].oneYearKnownCost} 元`}；${costDragQueue[0].missing.length ? `仍缺 ${costDragQueue[0].missing.join('、')}` : '费用证据完整'}` : '',
      pressureTestQueue[0] ? `计划金额压力：${pressureTestQueue[0].name} 按 ${preferences.plannedAmount.toLocaleString('zh-CN')} 元估算，历史回撤浮亏约 ${pressureTestQueue[0].historicalLossAmount === null ? '待补' : `${pressureTestQueue[0].historicalLossAmount} 元`}，画像预算约 ${pressureTestQueue[0].budgetLossAmount} 元。` : '',
      executionFeasibilityQueue[0] ? `执行可行性：${executionFeasibilityQueue[0].name} 为“${executionFeasibilityQueue[0].label}”；${executionFeasibilityQueue[0].pendingItems.length ? `待补 ${executionFeasibilityQueue[0].pendingItems.join('、')}` : executionFeasibilityQueue[0].hardBlocks.join('、') || '当前未见执行缺口'}` : '',
      purchasePlanFitQueue[0] ? `研究方式：${purchasePlanFitQueue[0].name} 当前为“${purchasePlanFitQueue[0].currentPlanLabel}”，建议“${purchasePlanFitQueue[0].recommendation}”；适配分 ${purchasePlanFitQueue[0].currentFitScore}/100。` : '',
      performanceQualityQueue[0] ? `收益质量：${performanceQualityQueue[0].name} 为“${performanceQualityQueue[0].label}”；质量分 ${performanceQualityQueue[0].qualityScore}/100；${performanceQualityQueue[0].primaryRisk}` : '',
      returnRiskQuadrantQueue[0] ? `收益风险象限：${returnRiskQuadrantQueue[0].name} 位于“${returnRiskQuadrantQueue[0].label}”；${returnRiskQuadrantQueue[0].primaryRead}。` : '',
      buyBeforeLandmineBoard[0] ? `研究排雷：${buyBeforeLandmineBoard[0].name} 为“${buyBeforeLandmineBoard[0].label}”，雷点分 ${buyBeforeLandmineBoard[0].landmineScore}/100；首要雷点：${buyBeforeLandmineBoard[0].topWarning}。` : '',
      doNotBuyDecisionBoard[0] ? `暂不买理由：${doNotBuyDecisionBoard[0].name} 为“${doNotBuyDecisionBoard[0].label}”；${doNotBuyDecisionBoard[0].primaryReason}` : '',
      nextActionRouter[0] ? `动作路由：优先“${nextActionRouter[0].label}”；${nextActionRouter[0].reason}` : '',
      leaderStabilityCheck ? `首选稳定性：${leaderStabilityCheck.label}，稳定分 ${leaderStabilityCheck.stabilityScore}/100；${leaderStabilityCheck.nextAction}` : '',
      headToHeadChallenge ? `首选对照：${headToHeadChallenge.leader.name} 对 ${headToHeadChallenge.challenger.name}，分差 ${headToHeadChallenge.scoreGap}；${headToHeadChallenge.decisionLine}` : '',
      prePurchaseChecklist ? `八项核查：${prePurchaseChecklist.label}，覆盖${prePurchaseChecklist.checklistScope}；通过 ${prePurchaseChecklist.passCount}/8，待补 ${prePurchaseChecklist.pendingCount}，阻断 ${prePurchaseChecklist.blockedCount}；${prePurchaseChecklist.conclusion}` : '',
      buyReadinessTrafficLight ? `研究复核红绿灯：${buyReadinessTrafficLight.label}；${buyReadinessTrafficLight.headline} 首要处理：${buyReadinessTrafficLight.nextActionLabel}` : '',
      greenLightUnlockPath ? `绿灯解锁路线：${greenLightUnlockPath.summary} 首步：${greenLightUnlockPath.steps[0]?.label || '严格复核'}。` : '',
      fieldSupplementTaskBasket.tasks[0] ? `字段补证任务篮：${fieldSupplementTaskBasket.summary} 首项涉及 ${fieldSupplementTaskBasket.tasks[0].sampleCodes.slice(0, 4).join('、')}。` : '',
      decisionConfidenceMeter ? `结论可信度：${decisionConfidenceMeter.label}，${decisionConfidenceMeter.score}/100；${decisionConfidenceMeter.conclusion}` : '',
      evidenceFreshnessQueue[0] ? `证据时效：${evidenceFreshnessQueue[0].name} 为“${evidenceFreshnessQueue[0].label}”；${evidenceFreshnessQueue[0].issues.length ? evidenceFreshnessQueue[0].issues.join('、') : '30 天内证据较新'}` : '',
      peerAlternativePools[0] ? `同类替代：${peerAlternativePools[0].anchor.name} 必须与 ${peerAlternativePools[0].alternatives.map((item: any) => item.name).slice(0, 3).join('、')} 横评。` : '',
      managerAttributionQueue[0] ? `经理归因：${managerAttributionQueue[0].name} 为“${managerAttributionQueue[0].label}”；${managerAttributionQueue[0].checks.slice(0, 2).join('；')}` : '',
      redemptionHoldingRiskQueue[0] ? `赎回持有：${redemptionHoldingRiskQueue[0].name} 为“${redemptionHoldingRiskQueue[0].label}”；计划金额赎回成本 ${redemptionHoldingRiskQueue[0].redemptionFeeAmount === null ? '待补' : `${redemptionHoldingRiskQueue[0].redemptionFeeAmount} 元`}` : '',
      typeHorizonFitQueue[0] ? `类型适配：${typeHorizonFitQueue[0].name} 为“${typeHorizonFitQueue[0].label}”；${typeHorizonFitQueue[0].rule}` : '',
      scaleLiquidityRiskQueue[0] ? `规模流动性：${scaleLiquidityRiskQueue[0].name} 为“${scaleLiquidityRiskQueue[0].label}”；规模 ${scaleLiquidityRiskQueue[0].totalAsset === null ? '待补' : `${scaleLiquidityRiskQueue[0].totalAsset} 亿`}。` : '',
      holdingExposureRiskQueue[0] ? `持仓暴露：${holdingExposureRiskQueue[0].name} 为“${holdingExposureRiskQueue[0].label}”；${holdingExposureRiskQueue[0].primaryRisk}` : '',
      strictCandidateUnlockBoard.primaryLane ? `严格解锁：优先处理“${strictCandidateUnlockBoard.primaryLane.label}”；${strictCandidateUnlockBoard.primaryLane.nextAction}` : '',
      candidatePromotionMatrix[0] ? `转正矩阵：${candidatePromotionMatrix[0].name} 为“${candidatePromotionMatrix[0].label}”；${candidatePromotionMatrix[0].nextAction}` : '',
      evidenceClosureQueue[0] ? `证据闭环：${evidenceClosureQueue[0].name} 当前到“${evidenceClosureQueue[0].stageLabel}”；${evidenceClosureQueue[0].nextAction}` : '',
      reportReadinessRadar[0] ? `报告就绪：${reportReadinessRadar[0].name} 为“${reportReadinessRadar[0].label}”，就绪度 ${reportReadinessRadar[0].totalScore}/100；${reportReadinessRadar[0].nextAction}` : '',
      candidateChallenges[0]?.winLossLines?.[0] ? `胜负线：${candidateChallenges[0].name} 对 ${candidateChallenges[0].winLossLines[0].challengerName} 为“${candidateChallenges[0].winLossLines[0].label}”；${candidateChallenges[0].winLossLines[0].summary}` : '',
      comparisonHref ? `横评入口：${comparisonHref}` : '',
      salesRulesHref ? `补证入口：${salesRulesHref}` : '',
      `硬边界：销售规则硬缺口未清零前，不能进入正式研究候选、不能保存正式研究复核报告。`,
    ].filter(Boolean).join('\n'),
  }
}

function evaluateFund(fund: ReturnType<typeof toCamelFund>, profile: RiskProfile, preferences: InvestorPreferences) {
  const buyEvidence = researchEvidenceTool.run({
    fund,
    reviewMode: preferences.purchasePlan,
    plannedAmount: preferences.plannedAmount,
  }).data
  if (!buyEvidence) throw new Error('研究证据计算未返回结果')
  const performance = fund.performanceData || {}
  const risk = fund.riskMetrics || {}
  const annualReturn = metric(performance, ['annualized_return_1y', 'return_1y', 'annual_return'])
  const maxDrawdown = metric(risk, ['max_drawdown', 'max_drawdown_1y', 'max_drawdown_2y'])
  const volatility = metric(risk, ['volatility', 'annualized_volatility_1y', 'annualized_volatility_2y'])
  const totalAsset = asNumber(fund.totalAsset)
  const typeScore = Math.round(clamp((typeFit[profile][fund.type || ''] ?? 6) + horizonTypeAdjustment(fund.type, preferences), 0, 24))
  const returnScore = Math.round(scoreReturn(annualReturn, profile))
  const riskBudget = resolveRiskBudget(profile, preferences)
  const riskScore = Math.round(scoreRisk(maxDrawdown, volatility, profile, riskBudget))
  const scaleScore = Math.round(scoreScale(totalAsset))
  const evidenceScore = dataCompleteness(fund, annualReturn, maxDrawdown)
  const manager = managerEvidence(fund)
  const ageDays = fundAgeDays(fund.establishmentDate)
  const drawdown = maxDrawdown === null ? null : Math.abs(maxDrawdown)
  const tradability = tradabilityStatus(fund)
  const tradabilityBlocked = tradability.status === 'blocked'
  const suitability = riskSuitability(fund, profile)
  const suitabilityBlocked = suitability.status === 'mismatch'
  const suitabilityMissing = suitability.status === 'missing'
  const holdingExperience = buildHoldingExperience({
    annualReturn,
    maxDrawdown,
    volatility,
    ageDays,
    profile,
    buyEvidence,
    riskBudget,
    purchasePlan: preferences.purchasePlan,
        ...plannedAmountSearchParams(preferences),
  })
  const cost = costEvidence(fund, preferences)

  const baseScore = Math.round(
    returnScore
      + riskScore
      + scaleScore
      + evidenceScore
      + typeScore
      + manager.score
      + cost.score,
  )
  const score = tradabilityBlocked || suitabilityBlocked
    ? 0
    : suitabilityMissing
      ? Math.max(0, Math.min(baseScore - 12, 68))
      : Math.max(0, baseScore)

  const reasons = [
    `${profileLabel[profile]} / ${preferences.horizonLabel} / ${preferences.purchasePlanLabel}：${fund.type || '未分类'}类型得分 ${typeScore}`,
    `收益观察：近一年 ${formatPercent(annualReturn)}`,
    `风险观察：最大回撤 ${formatPercent(maxDrawdown)}，波动率 ${formatPercent(volatility)}`,
  ]

  const warnings = [...horizonWarnings(fund.type, preferences)]
  if (annualReturn === null || maxDrawdown === null) warnings.push('关键收益/回撤字段不完整，需要补齐净值序列后复核')
  if (totalAsset === null) warnings.push('基金规模缺失，无法判断流动性和清盘风险')
  if (totalAsset !== null && totalAsset < 5) warnings.push('规模偏小，需关注流动性和清盘风险')
  if (maxDrawdown !== null && Math.abs(maxDrawdown) > 0.2) warnings.push('历史回撤偏高，不适合低风险偏好直接纳入')
  if (!fund.establishmentDate) warnings.push('成立日期缺失，无法判断样本长度')
  if (ageDays !== null && ageDays < 365) warnings.push('成立不足一年，收益和风险统计样本偏短')
  if (tradabilityBlocked) warnings.push(tradability.note)
  if (suitability.status !== 'matched') warnings.push(suitability.note)
  if (manager.status === 'missing') warnings.push('基金经理明细缺失，研究复核需同步现任经理与任期')
  if (manager.status === 'short') warnings.push('现任基金经理任期不足一年，历史业绩归因需要谨慎')
  if (cost.status === 'thin') warnings.push('申赎成本证据不足，研究复核需补齐申购费、赎回费、起购/定投和限购规则')

  const dataGaps = [
    fund.nav === null ? '最新净值' : '',
    fund.navDate ? '' : '净值日期',
    totalAsset === null ? '基金规模' : '',
    annualReturn === null ? '近一年收益' : '',
    maxDrawdown === null ? '最大回撤' : '',
    tradability.status === 'unknown' ? '申购状态' : '',
    suitability.status === 'missing' ? '销售平台风险等级' : '',
    suitability.status === 'mismatch' ? '风险适当性不匹配' : '',
    hasFeeEvidence(fund) ? '' : '销售费率/限购',
    cost.missing.length ? `成本证据：${cost.missing.slice(0, 3).join('/')}` : '',
    manager.status === 'missing' ? '基金经理明细' : '',
    '持仓明细',
  ].filter(Boolean)

  const checklist = [
    {
      label: '风险画像匹配',
      status: suitability.status === 'mismatch' ? 'warn' : checklistStatus(typeScore >= 10 && (drawdown === null || drawdown <= riskBudget), suitability.status === 'missing'),
      note: `${profileLabel[profile]} / ${preferences.horizonLabel}预算：最大回撤约 ${formatPercent(-riskBudget)}；${suitability.note}`,
    },
    {
      label: '回撤可承受',
      status: checklistStatus(drawdown !== null && drawdown <= riskBudget, drawdown === null),
      note: `当前最大回撤：${formatPercent(maxDrawdown)}`,
    },
    {
      label: '收益有观察价值',
      status: checklistStatus(annualReturn !== null && returnScore >= 12, annualReturn === null),
      note: `近一年收益：${formatPercent(annualReturn)}`,
    },
    {
      label: '规模流动性',
      status: checklistStatus(totalAsset !== null && scaleScore >= 8, totalAsset === null),
      note: totalAsset === null ? '规模缺失' : `规模评分：${scaleScore}/12`,
    },
    {
      label: '样本长度',
      status: checklistStatus(ageDays !== null && ageDays >= 365, ageDays === null),
      note: ageDays === null ? '成立日期缺失' : `成立约 ${Math.round(ageDays / 30)} 个月`,
    },
    {
      label: '销售风险等级',
      status: suitability.status === 'matched' ? 'pass' : suitability.status === 'mismatch' ? 'warn' : 'pending',
      note: suitability.note,
    },
    {
      label: '经理任期样本',
      status: manager.status === 'missing' ? 'pending' : manager.status === 'short' ? 'warn' : 'pass',
      note: manager.note,
    },
    {
      label: '申购/存续状态',
      status: tradability.status === 'blocked' ? 'warn' : tradability.status === 'unknown' ? 'pending' : 'pass',
      note: tradability.note,
    },
    {
      label: '费率结构',
      status: hasFeeEvidence(fund) ? 'pass' : 'pending',
      note: feeEvidenceNote(fund),
    },
    {
      label: '申赎成本友好',
      status: cost.status === 'thin' ? 'pending' : cost.score >= 5 ? 'pass' : 'warn',
      note: cost.note,
    },
  ]

  const hardWarnings = checklist.filter((item) => item.status === 'warn').length
  const readiness =
    tradabilityBlocked || suitabilityBlocked
      ? { level: 'caution', label: '不可纳入', description: '存在申购/存续阻断或风险等级不匹配，不能作为研究候选。' }
      : suitabilityMissing
        ? { level: 'review', label: '先补风险等级', description: '销售平台风险等级缺失，不能作为研究候选；补 R1-R5 后再重评。' }
      : score >= 82 && hardWarnings <= 1 && evidenceScore >= 6
      ? { level: 'focus', label: '重点研究', description: '匹配度较高，可进入报告复核和同类对比。' }
      : score >= 70
        ? { level: 'review', label: '对比复核', description: '具备候选价值，但需补齐风险或数据证据。' }
        : { level: 'caution', label: '暂缓纳入', description: '匹配度或证据不足，先补数据再判断。' }

  const purchaseGate = buildPurchaseGate({
    tradability,
    suitability,
    score,
    evidenceScore,
    dataGaps,
    drawdown,
    riskBudget,
    totalAsset,
    ageDays,
    preferences,
  })
  const scoreBreakdown = [
    {
      key: 'return',
      label: '收益',
      score: returnScore,
      maxScore: 35,
      note: annualReturn === null ? '近一年收益待补，收益项降权' : `近一年 ${formatPercent(annualReturn)}，按${profileLabel[profile]}收益目标折算`,
    },
    {
      key: 'risk',
      label: '风险',
      score: riskScore,
      maxScore: 46,
      note: `最大回撤 ${formatPercent(maxDrawdown)}，波动率 ${formatPercent(volatility)}，预算 ${formatPercent(-riskBudget)}`,
    },
    {
      key: 'scale',
      label: '规模',
      score: scaleScore,
      maxScore: 12,
      note: totalAsset === null ? '规模待补，规模项降权' : `规模 ${Number(totalAsset).toFixed(2)} 亿`,
    },
    {
      key: 'typeFit',
      label: '类型适配',
      score: typeScore,
      maxScore: 24,
      note: `${fund.type || '未分类'} 与 ${profileLabel[profile]} / ${preferences.horizonLabel} 的匹配度`,
    },
    {
      key: 'evidence',
      label: '证据',
      score: evidenceScore,
      maxScore: 15,
      note: `基础数据完整度 ${evidenceScore}/15，研究证据 ${buyEvidence.completenessScore ?? 0}`,
    },
    {
      key: 'manager',
      label: '经理',
      score: manager.score,
      maxScore: 5,
      note: manager.note,
    },
    {
      key: 'cost',
      label: '成本',
      score: cost.score,
      maxScore: 10,
      note: cost.note,
    },
  ]
  const scorePenalty = [
    tradabilityBlocked ? '申购/存续状态阻断，最终分归零' : '',
    suitabilityBlocked ? '风险等级不匹配，最终分归零' : '',
    suitabilityMissing && !tradabilityBlocked && !suitabilityBlocked ? '销售风险等级缺失，最终分封顶 68 且研究门禁强制先补证' : '',
  ].filter(Boolean)

  const tags = [
    drawdown !== null && drawdown <= 0.05 ? '低回撤' : '',
    annualReturn !== null && annualReturn >= 0.08 ? '收益弹性' : '',
    volatility !== null && volatility <= 0.05 ? '低波动' : '',
    ageDays !== null && ageDays < 365 ? '短样本' : '',
    dataGaps.length >= 3 ? '待补证' : '',
    tradabilityBlocked ? '申购阻断' : '',
    suitabilityBlocked ? '风险不匹配' : '',
    suitabilityMissing ? '风险等级待补' : '',
    suitability.status === 'matched' ? '风险适配' : '',
    tradability.status === 'unknown' ? '申购待核' : '',
    preferences.purchasePlan === 'sip' && holdingExperience.sipFriendlyScore >= 75 ? '定投友好' : '',
    holdingExperience.level === 'comfortable' ? '持有体验稳' : '',
    preferences.horizon === 'lt1y' ? '短期持有' : '',
    preferences.purchasePlan === 'sip' ? '定投方案' : '一次性方案',
  ].filter(Boolean)

	  return {
	    ...fund,
	    researchScore: clamp(score),
	    researchRating: score >= 82 ? 'A' : score >= 70 ? 'B' : score >= 58 ? 'C' : 'D',
	    investorScore: clamp(score),
	    investorRating: score >= 82 ? 'A' : score >= 70 ? 'B' : score >= 58 ? 'C' : 'D',
    riskLabel: riskLabel(maxDrawdown, volatility),
    riskSuitability: suitability,
    tradability,
    annualReturn,
    maxDrawdown,
    volatility,
    ageDays,
    dimensionScores: {
      return: returnScore,
      risk: riskScore,
      scale: scaleScore,
      typeFit: typeScore,
      evidence: evidenceScore,
      manager: manager.score,
      cost: cost.score,
      horizon: Math.round(clamp(typeScore - (typeFit[profile][fund.type || ''] ?? 6) + 12, 0, 18)),
    },
    scoreBreakdown,
    scorePenalty,
    marketResearchChecklist: (fund as any).marketResearchChecklist || null,
	    managerEvidence: manager,
	    costEvidence: cost,
	    researchPreferences: preferences,
	    investorPreferences: preferences,
	    readiness,
	    researchGate: purchaseGate,
	    purchaseGate,
	    researchEvidence: buyEvidence,
	    buyEvidence,
    holdingExperience,
    checklist,
    dataGaps,
    tags,
    reasons,
    warnings,
	    nextActions: [
	      '查看基金研究报告与同类分位',
	      '查看历史净值回放并调整观察场景',
	      '加入研究清单并设置复核日期',
	      '与同类基金做矩阵对比',
	    ],
  }
}

export async function GET(request: Request) {
  try {
    const requestUrl = new URL(request.url)
    const origin = requestUrl.origin
    const { searchParams } = requestUrl
    const profile = (searchParams.get('profile') || 'balanced') as RiskProfile
    const safeProfile: RiskProfile = ['conservative', 'balanced', 'aggressive'].includes(profile) ? profile : 'balanced'
    const type = searchParams.get('type') || ''
    const keyword = searchParams.get('keyword') || ''
    const minScore = Number(searchParams.get('minScore') || '0')
    const limit = boundedInteger(searchParams.get('limit'), 80, 1, 100)
    const sourceLimitFallback = Math.min(MAX_SOURCE_LIMIT, Math.max(BACKEND_PAGE_SIZE, limit * 5))
    const sourceLimit = boundedInteger(searchParams.get('sourceLimit'), sourceLimitFallback, BACKEND_PAGE_SIZE, MAX_SOURCE_LIMIT)
    const lens = (searchParams.get('lens') || 'score') as SelectionLens
    const safeLens: SelectionLens = ['score', 'stable', 'return', 'evidence', 'peer', 'experience', 'manager', 'cost'].includes(lens) ? lens : 'score'
    const horizon = (searchParams.get('horizon') || '1to3y') as InvestmentHorizon
    const safeHorizon: InvestmentHorizon = ['lt1y', '1to3y', 'gt3y'].includes(horizon) ? horizon : '1to3y'
    const purchasePlan = (searchParams.get('purchasePlan') || 'sip') as PurchasePlan
    const safePurchasePlan: PurchasePlan = ['lump_sum', 'sip'].includes(purchasePlan) ? purchasePlan : 'sip'
    const maxDrawdownTolerance = asNumber(searchParams.get('maxDrawdownTolerance'))
    const eligibleOnly = searchParams.get('eligibleOnly') === 'true'
    const requireSalesRule = searchParams.get('requireSalesRule') === 'true'
    const researchChecklistStatus = ['complete', 'repair', 'blocked'].includes(searchParams.get('researchChecklistStatus') || '')
      ? searchParams.get('researchChecklistStatus') || ''
      : ''
    const minEvidenceGrade = parseEvidenceGrade(searchParams.get('minEvidenceGrade'))
    const minManagerYears = Math.max(0, asNumber(searchParams.get('minManagerYears')) ?? 0)
    const minCostScore = Math.max(0, asNumber(searchParams.get('minCostScore')) ?? 0)
    const preferences: InvestorPreferences = {
      horizon: safeHorizon,
      horizonLabel: horizonLabel[safeHorizon],
      purchasePlan: safePurchasePlan,
      purchasePlanLabel: purchasePlanLabel[safePurchasePlan],
      plannedAmount: boundedAmount(searchParams.get('plannedAmount'), defaultPlannedAmountForPlan(safePurchasePlan)),
      maxDrawdownTolerance: maxDrawdownTolerance === null ? null : clamp(maxDrawdownTolerance, 0.03, 0.4),
    }

    const candidateResult = await fetchCandidateFunds({
      type,
      keyword,
      sourceLimit,
      purchasePlan: safePurchasePlan,
      plannedAmount: preferences.plannedAmount,
      requireSalesRule,
      eligibleOnly,
      researchChecklistStatus,
      safeProfile,
    })
    const rawFunds = candidateResult.rawFunds
    const camelFunds = rawFunds.map((fund) => toCamelFund(fund))
    const typeFilteredFunds = type
      ? camelFunds.filter((fund) => fund.type === type)
      : camelFunds
    const salesRules = await getMergedSalesRulesByWindCodes(typeFilteredFunds.map((fund) => fund.windCode))

    const rawEvaluatedWithoutSalesGate = attachPeerPercentiles(typeFilteredFunds
      .map((fund: ReturnType<typeof toCamelFund>) => {
        const salesRule = salesRules.get(fund.windCode) || null
        return evaluateFund({ ...fund, salesRule } as ReturnType<typeof toCamelFund>, safeProfile, preferences)
      }))
    const salesRuleGateScan = await fetchSalesRuleGapMap(rawEvaluatedWithoutSalesGate.map((fund: any) => fund.windCode), safePurchasePlan, preferences.plannedAmount)
    const activeSalesRuleEvidenceAlertsByCode = await fetchActiveSalesRuleEvidenceAlertsForCodes(rawEvaluatedWithoutSalesGate.map((fund: any) => fund.windCode))
    const rawEvaluated = attachShareClassInfo(attachCurrentSalesRuleGate(rawEvaluatedWithoutSalesGate, salesRuleGateScan.gapMap, salesRuleGateScan.amountGateMap, activeSalesRuleEvidenceAlertsByCode, safePurchasePlan, preferences.plannedAmount))

    const filterStats = rawEvaluated.reduce((acc: Record<string, number>, fund: any) => {
      const reason =
        fund.investorScore < minScore
          ? 'score_below_threshold'
          : !passesEvidenceGrade(fund.purchaseGate.evidenceGrade, minEvidenceGrade)
            ? 'evidence_below_threshold'
            : eligibleOnly && fund.currentSalesRuleGate?.status === 'blocked'
              ? 'sales_rule_gap_blocked'
              : eligibleOnly && !['research_ready', 'watchlist'].includes(fund.purchaseGate.level)
                ? 'not_purchase_candidate'
                : requireSalesRule && (!fund.salesRule || fund.currentSalesRuleGate?.status === 'blocked')
                  ? fund.salesRule ? 'sales_rule_incomplete' : 'sales_rule_missing'
                  : minManagerYears > 0 && ((fund.managerEvidence?.maxTenureYears ?? -1) < minManagerYears)
                    ? 'manager_tenure_below_threshold'
                    : minCostScore > 0 && ((fund.costEvidence?.score ?? -1) < minCostScore)
                      ? 'cost_below_threshold'
                      : 'included'
      acc[reason] = (acc[reason] || 0) + 1
      return acc
    }, {})

    const evaluated = rawEvaluated.filter((fund: any) => {
      if (fund.investorScore < minScore) return false
      if (!passesEvidenceGrade(fund.purchaseGate.evidenceGrade, minEvidenceGrade)) return false
      if (eligibleOnly && fund.currentSalesRuleGate?.status === 'blocked') return false
      if (eligibleOnly && !['research_ready', 'watchlist'].includes(fund.purchaseGate.level)) return false
      if (requireSalesRule && (!fund.salesRule || fund.currentSalesRuleGate?.status === 'blocked')) return false
      if (minManagerYears > 0 && ((fund.managerEvidence?.maxTenureYears ?? -1) < minManagerYears)) return false
      if (minCostScore > 0 && ((fund.costEvidence?.score ?? -1) < minCostScore)) return false
      return true
    })
    const salesRuleBlockedSamples = rawEvaluated
      .filter((fund: any) => {
        if (fund.investorScore < minScore) return false
        if (!passesEvidenceGrade(fund.purchaseGate.evidenceGrade, minEvidenceGrade)) return false
        return fund.currentSalesRuleGate?.status === 'blocked'
      })
      .map((fund: any) => ({
        ...fund,
        salesRuleUnlockReadiness: buildSalesRuleUnlockReadiness(fund, minEvidenceGrade),
      }))
      .filter((fund: any) => fund.salesRuleUnlockReadiness.formalCandidateAfterSalesRule)
      .sort((left: any, right: any) => {
        const leftMissing = left.salesRuleGap?.missingCount || left.currentSalesRuleGate?.missingCount || 0
        const rightMissing = right.salesRuleGap?.missingCount || right.currentSalesRuleGate?.missingCount || 0
        return right.investorScore - left.investorScore
          || leftMissing - rightMissing
      })
      .slice(0, 20)
      .map((fund: any) => ({
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type,
        investorScore: fund.investorScore,
        evidenceGrade: fund.purchaseGate?.evidenceGrade || null,
        missingCount: fund.salesRuleGap?.missingCount || fund.currentSalesRuleGate?.missingCount || 0,
        missingItems: fund.salesRuleGap?.missingItems || fund.currentSalesRuleGate?.missingItems || [],
        priority: fund.salesRuleGap?.priority || fund.currentSalesRuleGate?.priority || 'high',
        nextAction: fund.salesRuleGap?.nextAction || '补齐销售规则硬证据',
        actionHref: fund.currentSalesRuleGate?.actionHref || salesRulesHrefForCodes(fund.windCode, preferences.purchasePlan, preferences.plannedAmount),
        alertsHref: fund.currentSalesRuleGate?.alertsHref || null,
        gateSource: fund.currentSalesRuleGate?.source || null,
        riskLevelSourceBacked: Boolean(fund.riskSuitability?.riskLevelSourceBacked),
        riskLevelEvidenceStatus: fund.riskSuitability?.riskLevelEvidenceStatus || 'missing',
        riskLevelEvidenceLabel: fund.riskSuitability?.riskLevelEvidenceLabel || 'R1-R5 待补',
        riskLevelEvidenceDetail: fund.riskSuitability?.riskLevelEvidenceDetail || '未取得销售平台或基金合同风险等级，不能用于适当性匹配。',
        unlockReadiness: fund.salesRuleUnlockReadiness,
        formalCandidateAfterSalesRule: fund.salesRuleUnlockReadiness.formalCandidateAfterSalesRule,
      }))
    const nearPurchasableUnlockQueue = salesRuleBlockedSamples
      .map((sample: any, index: number) => {
        const criticalMissing = (sample.missingItems || []).filter((item: string) =>
          ['销售风险等级', '申购状态', '来源日期', '申购费', '赎回费'].some((keyword) => item.includes(keyword)),
        )
        const unlockStage = sample.missingCount <= 3
          ? '少量补证'
          : sample.missingCount <= 5
            ? '集中补证'
            : '重补规则'
        return {
          ...sample,
          unlockRank: index + 1,
          unlockStage,
          criticalMissing,
          batchKey: sample.missingItems.slice(0, 2).join('+') || 'sales-rule',
          reason: `选基分 ${sample.investorScore}、证据 ${sample.evidenceGrade || '待定'}，当前只因销售规则硬缺口未进入严格候选。`,
          unlockAction: sample.missingCount <= 3
            ? '先补少量硬字段，补完回到严格筛选确认是否转为正式研究候选。'
            : '先按字段批量补证，再回到严格筛选确认是否转为正式研究候选。',
        }
      })
    const nearPurchasableTopCodes = nearPurchasableUnlockQueue.slice(0, 8).map((item: any) => item.windCode)
    const nearPurchasableReviewHref = `/market?source=research-candidates&${new URLSearchParams({
      profile: safeProfile,
      lens: safeLens,
      horizon: safeHorizon,
      purchasePlan: safePurchasePlan,
      eligibleOnly: 'true',
      requireSalesRule: 'true',
      minScore: String(minScore),
      minEvidenceGrade,
      sourceLimit: String(sourceLimit),
      ...(type ? { type } : {}),
      ...(keyword ? { keyword } : {}),
      ...(maxDrawdownTolerance === null ? {} : { maxDrawdownTolerance: String(maxDrawdownTolerance) }),
      plannedAmount: String(preferences.plannedAmount),
      ...(minManagerYears > 0 ? { minManagerYears: String(minManagerYears) } : {}),
      ...(minCostScore > 0 ? { minCostScore: String(minCostScore) } : {}),
    }).toString()}`
    const nearPurchasableBulkHref = nearPurchasableTopCodes.length
      ? salesRulesHrefForCodes(nearPurchasableTopCodes, safePurchasePlan, preferences.plannedAmount, nearPurchasableReviewHref)
      : salesRulesHrefForCodes([], safePurchasePlan, preferences.plannedAmount)
    const salesRuleUnlockPreview = {
      unlockableCount: salesRuleBlockedSamples.length,
      topScore: salesRuleBlockedSamples[0]?.investorScore ?? null,
      averageScore: salesRuleBlockedSamples.length
        ? Math.round(salesRuleBlockedSamples.reduce((sum: number, item: any) => sum + item.investorScore, 0) / salesRuleBlockedSamples.length)
        : 0,
      topCodes: salesRuleBlockedSamples.slice(0, 8).map((item: any) => item.windCode),
      missingItemBuckets: Object.entries(
        salesRuleBlockedSamples.flatMap((item: any) => item.missingItems || []).reduce((acc: Record<string, number>, item: string) => {
          acc[item] = (acc[item] || 0) + 1
          return acc
        }, {}),
      )
        .map(([label, count]) => ({ label, count: Number(count) }))
        .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, 'zh-CN'))
        .slice(0, 8),
      message: salesRuleBlockedSamples.length
        ? `这 ${salesRuleBlockedSamples.length} 只已通过当前分数、证据等级和非销售硬阻断检查，补齐销售规则后可回到严格研究候选重评。`
        : '当前没有只因销售规则硬缺口被过滤的基金。',
      nearPurchasableQueue: nearPurchasableUnlockQueue.slice(0, 8),
      bulkSalesRulesHref: nearPurchasableBulkHref,
      strictReviewHref: nearPurchasableReviewHref,
      queueLabel: nearPurchasableUnlockQueue.length
        ? `近研究候选补证队列 TOP ${Math.min(8, nearPurchasableUnlockQueue.length)}`
        : '近研究候选补证队列为空',
    }
    const strictBlockerDiagnostics = buildStrictBlockerDiagnostics({
      filterStats,
      rawEvaluated,
      minScore,
      minEvidenceGrade,
      minManagerYears,
      minCostScore,
      strictReviewHref: nearPurchasableReviewHref,
      salesRulesHref: nearPurchasableBulkHref,
      purchasePlan: safePurchasePlan,
      plannedAmount: preferences.plannedAmount,
    })
    const salesRuleImpact = await getSalesRuleImpact(safePurchasePlan, preferences.plannedAmount)
    const suitabilityCoverageHealth = buildSuitabilityCoverageHealth({
      impact: salesRuleImpact,
      safeProfile,
      purchasePlan: safePurchasePlan,
      plannedAmount: preferences.plannedAmount,
    })

    const sorters: Record<SelectionLens, (left: any, right: any) => number> = {
      score: (left, right) => right.investorScore - left.investorScore,
      stable: (left, right) => (Math.abs(left.maxDrawdown ?? 1) - Math.abs(right.maxDrawdown ?? 1)) || right.investorScore - left.investorScore,
      return: (left, right) => (right.annualReturn ?? -1) - (left.annualReturn ?? -1) || right.investorScore - left.investorScore,
      evidence: (left, right) => right.dimensionScores.evidence - left.dimensionScores.evidence || right.investorScore - left.investorScore,
      peer: (left, right) => (right.peerPercentiles?.peerScore ?? -1) - (left.peerPercentiles?.peerScore ?? -1) || right.investorScore - left.investorScore,
      experience: (left, right) => (right.holdingExperience?.score ?? -1) - (left.holdingExperience?.score ?? -1) || (right.holdingExperience?.sipFriendlyScore ?? -1) - (left.holdingExperience?.sipFriendlyScore ?? -1),
      manager: (left, right) => (right.managerEvidence?.score ?? -1) - (left.managerEvidence?.score ?? -1) || (right.managerEvidence?.maxTenureYears ?? -1) - (left.managerEvidence?.maxTenureYears ?? -1) || right.investorScore - left.investorScore,
      cost: (left, right) => (right.costEvidence?.score ?? -1) - (left.costEvidence?.score ?? -1) || (left.costEvidence?.totalAnnualFee ?? 99) - (right.costEvidence?.totalAnnualFee ?? 99) || right.investorScore - left.investorScore,
    }
    evaluated.sort(sorters[safeLens])

    const ranked = evaluated.map((fund: any, index: number) => ({
      ...fund,
      selectionRank: index + 1,
      selectionPercentile: evaluated.length <= 1 ? 100 : Math.round((1 - index / (evaluated.length - 1)) * 100),
    }))
    const holdingExposureMap = await fetchHoldingExposureMap(ranked, origin)
    const holdingExposureRiskQueue = buildHoldingExposureRiskQueue({
      ranked,
      holdingExposureMap,
      safeProfile,
      preferences,
    })
    const selectionDecisionPackage = buildSelectionDecisionPackage({
      ranked,
      rawEvaluated,
      safeProfile,
      safeLens,
      preferences,
      minScore,
      minEvidenceGrade,
      salesRuleUnlockPreview,
      salesRuleAmountGateMap: salesRuleGateScan.amountGateMap,
      holdingExposureRiskQueue,
    })

    const typeBuckets = evaluated.reduce((acc: Record<string, number>, fund: any) => {
      const key = fund.type || '未分类'
      acc[key] = (acc[key] || 0) + 1
      return acc
    }, {})

    return NextResponse.json({
      profile: safeProfile,
      profileLabel: profileLabel[safeProfile],
      lens: safeLens,
      preferences,
      filters: {
        minScore,
        eligibleOnly,
        minEvidenceGrade,
        requireSalesRule,
        researchChecklistStatus,
        minManagerYears,
        minCostScore,
        sourceTotal: rawEvaluated.length,
        backendTotal: candidateResult.backendTotal,
        sourceLimit,
        fetchedPages: candidateResult.fetchedPages,
        source: candidateResult.source,
        candidateSource: candidateResult.candidateSource,
        universeDiagnostics: candidateResult.universeDiagnostics,
        filterStats,
        salesRuleBlockedSamples,
        salesRuleUnlockPreview,
        strictBlockerDiagnostics,
        suitabilityCoverageHealth,
      },
      total: ranked.length,
	      summary: {
	        averageResearchScore: ranked.length ? Math.round(ranked.reduce((sum: number, fund: any) => sum + fund.researchScore, 0) / ranked.length) : 0,
	        averageScore: ranked.length ? Math.round(ranked.reduce((sum: number, fund: any) => sum + fund.investorScore, 0) / ranked.length) : 0,
	        typeBuckets,
        readinessBuckets: ranked.reduce((acc: Record<string, number>, fund: any) => {
          acc[fund.readiness.label] = (acc[fund.readiness.label] || 0) + 1
          return acc
        }, {}),
	        purchaseGateBuckets: ranked.reduce((acc: Record<string, number>, fund: any) => {
	          acc[fund.purchaseGate.label] = (acc[fund.purchaseGate.label] || 0) + 1
	          return acc
	        }, {}),
	        researchGateBuckets: ranked.reduce((acc: Record<string, number>, fund: any) => {
	          acc[fund.researchGate.label] = (acc[fund.researchGate.label] || 0) + 1
	          return acc
	        }, {}),
        researchChecklistBuckets: ranked.reduce((acc: Record<string, number>, fund: any) => {
          const label = marketResearchChecklistStatus(fund)
          acc[label] = (acc[label] || 0) + 1
          return acc
        }, {}),
        researchChecklistPrimaryGaps: Object.entries(
          ranked.reduce((acc: Record<string, number>, fund: any) => {
            const gap = marketResearchChecklistPrimaryGap(fund)
            if (gap) acc[gap] = (acc[gap] || 0) + 1
            return acc
          }, {}),
        ).sort((left, right) => Number(right[1]) - Number(left[1])).slice(0, 5),
        salesRuleGateBuckets: rawEvaluated.reduce((acc: Record<string, number>, fund: any) => {
          const label = fund.currentSalesRuleGate?.status === 'blocked' ? '销售规则待补' : '销售规则无硬缺口'
          acc[label] = (acc[label] || 0) + 1
          return acc
        }, {}),
        salesRuleGapCount: rawEvaluated.filter((fund: any) => fund.currentSalesRuleGate?.status === 'blocked').length,
        riskSuitabilityBuckets: ranked.reduce((acc: Record<string, number>, fund: any) => {
          acc[fund.riskSuitability.label] = (acc[fund.riskSuitability.label] || 0) + 1
          return acc
        }, {}),
        holdingExperienceBuckets: ranked.reduce((acc: Record<string, number>, fund: any) => {
          acc[fund.holdingExperience.label] = (acc[fund.holdingExperience.label] || 0) + 1
          return acc
        }, {}),
        topRiskLabels: Array.from(new Set(ranked.slice(0, 8).map((fund: any) => fund.riskLabel))),
        commonDataGaps: Object.entries(
          ranked.flatMap((fund: any) => fund.dataGaps).reduce((acc: Record<string, number>, gap: string) => {
            acc[gap] = (acc[gap] || 0) + 1
            return acc
          }, {}),
        ).sort((left, right) => Number(right[1]) - Number(left[1])).slice(0, 5),
        peerLeaders: [...ranked]
          .filter((fund: any) => fund.peerPercentiles?.peerScore !== null)
          .sort((left: any, right: any) => (right.peerPercentiles.peerScore ?? -1) - (left.peerPercentiles.peerScore ?? -1))
          .slice(0, 5)
          .map((fund: any) => ({
            windCode: fund.windCode,
            name: fund.name,
            type: fund.type,
            peerScore: fund.peerPercentiles.peerScore,
            peerCount: fund.peerPercentiles.peerCount,
          })),
        experienceLeaders: [...ranked]
          .sort((left: any, right: any) => (right.holdingExperience?.score ?? -1) - (left.holdingExperience?.score ?? -1))
          .slice(0, 5)
          .map((fund: any) => ({
            windCode: fund.windCode,
            name: fund.name,
            type: fund.type,
            score: fund.holdingExperience.score,
            sipFriendlyScore: fund.holdingExperience.sipFriendlyScore,
            label: fund.holdingExperience.label,
          })),
        managerLeaders: [...ranked]
          .filter((fund: any) => fund.managerEvidence?.status !== 'missing')
          .sort((left: any, right: any) => (right.managerEvidence?.score ?? -1) - (left.managerEvidence?.score ?? -1) || (right.managerEvidence?.maxTenureYears ?? -1) - (left.managerEvidence?.maxTenureYears ?? -1))
          .slice(0, 5)
          .map((fund: any) => ({
            windCode: fund.windCode,
            name: fund.name,
            type: fund.type,
            label: fund.managerEvidence.label,
            score: fund.managerEvidence.score,
            maxTenureYears: fund.managerEvidence.maxTenureYears,
            managerNames: fund.managerEvidence.managerNames,
          })),
        costLeaders: [...ranked]
          .sort((left: any, right: any) => (right.costEvidence?.score ?? -1) - (left.costEvidence?.score ?? -1) || (left.costEvidence?.totalAnnualFee ?? 99) - (right.costEvidence?.totalAnnualFee ?? 99))
          .slice(0, 5)
          .map((fund: any) => ({
            windCode: fund.windCode,
            name: fund.name,
            type: fund.type,
            label: fund.costEvidence.label,
            score: fund.costEvidence.score,
            totalAnnualFee: fund.costEvidence.totalAnnualFee,
            purchaseFeeRate: fund.costEvidence.purchaseFeeRate,
            missing: fund.costEvidence.missing,
          })),
      },
      selectionDecisionPackage,
      funds: ranked.slice(0, limit),
      methodology: [
        '收益：近一年年化收益相对风险偏好目标打分',
        '风险：最大回撤和波动率约束打分',
        '适配：基金类型与风险画像、计划持有期限匹配度打分',
        '可信度：净值、日期、收益、回撤字段完整度打分',
	        '同类分位：按基金类型横向比较收益、回撤、波动和选基分',
	        '持有体验：结合历史回撤、波动率、样本长度、收益和研究证据估算观察压力',
	        '研究候选过滤：可按证据等级、材料门槛和销售规则覆盖度过滤，避免基础库空数据进入候选榜',
	        '风险适当性：销售平台风险等级高于研究场景上限时硬阻断，缺失时标记为研究必补证据',
	        '基金经理证据：识别现任经理是否明确、任期是否足够，防止把老业绩误归因给新经理',
	        '费用证据：基于管理费、托管费和销售规则覆盖度识别成本可比性与研究缺口',
	        `候选范围：从综合分、收益、回撤、夏普、规模和最新同步六个基础数据库研究样本去重；严格模式会额外追加销售规则完整且 R1-R5 匹配当前画像的数据库研究样本，共取得 ${rawEvaluated.length}/${candidateResult.backendTotal || rawEvaluated.length} 只后再统一评分和过滤`,
	      ],
	      disclaimer: '本页仅用于基金研究候选筛选和风险适配，不提供申赎指令或收益承诺。',
	    })
  } catch (error) {
    console.error('基金研究筛选失败:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '基金研究筛选失败' },
      { status: 500 },
    )
  }
}
