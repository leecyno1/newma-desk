'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Calendar, TrendingUp, DollarSign, AlertCircle, Sparkles, ShieldCheck, ClipboardCheck, BarChart3, Copy, UserCheck, Download, Save } from 'lucide-react'
import NavChart from '@/components/charts/NavChart'
import { buildBuyBeforeEvidenceQueue } from '@/lib/report-buy-before-evidence-queue'
import { buildShareClassInfoByCode, inferShareClass, normalizeShareClassBaseName } from '@/lib/share-class'
import { salesRuleFoundationManualFieldsForPlan } from '@/lib/sales-rule-purchase-plan-copy'
import { hasValidSalesRuleSourceIdentityEvidence } from '@/lib/sales-rule-source-evidence'
import type { ReportRiskLevelGatePolicy } from '@/lib/report-risk-level-gate-policy'
import { canonicalResearchHref, materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'
import { methodologyConfigTool, type MethodologyDimension } from '@/lib/research-platform/tools'

interface Fund {
  id: string
  windCode: string
  name: string
  type: string
  nav: number | null
  navDate: string | null
  totalAsset: number | null
  establishmentDate: string | null
  operationStatus?: {
    status?: 'blocked' | 'watch' | 'unknown'
    label?: string
    reason?: string
    purchase_start_date?: string | null
    redeem_start_date?: string | null
  } | null
  salesStatus?: {
    purchase_start_date?: string | null
    redeem_start_date?: string | null
    status?: string | null
  } | null
  feeInfo?: {
    management_fee?: number | null
    managementFee?: number | null
    custodian_fee?: number | null
    custodianFee?: number | null
  } | null
  salesRule?: {
    platform?: string
    purchaseStatus?: 'open' | 'closed' | 'limited' | 'unknown'
    purchaseStatusLabel?: string
    purchaseStatusSourceBacked?: boolean
    minPurchaseAmount?: number | null
    minPurchaseSourceBacked?: boolean
    minSipAmount?: number | null
    minSipSourceBacked?: boolean
    dailyLimitAmount?: number | null
    dailyLimitSourceBacked?: boolean
    purchaseFeeRate?: number | null
    purchaseFeeSourceBacked?: boolean
    redemptionFeeRules?: Array<{ label: string; feeRate: number; holdingDays: number | null }>
    redemptionFeeSourceUrl?: string | null
    redemptionFeeSourceUpdatedAt?: string | null
    redemptionFeePlatform?: string | null
    redemptionFeeNotes?: string | null
    salesServiceFeeRate?: number | null
    salesServiceFeeSourceBacked?: boolean
    riskLevel?: string | null
    supportsSip?: boolean | null
    supportsSipSourceBacked?: boolean
    sourceUpdatedAt?: string | null
    sourceUrl?: string | null
    notes?: string | null
  } | null
  benchmark?: string | null
  peerPercentiles?: {
    target_id?: string
    fund_type?: string
    peer_group?: string | null
    primary_benchmark?: string | null
    peer_group_source?: string
    peer_count?: number
    minimum_valid_peer_count?: number
    usable_metric_count?: number
    insufficient_metric_count?: number
    peer_metric_gap?: {
      required_more_funds?: number
      blocking_metrics?: Array<{
        metric_name?: string
        label?: string
        peer_count?: number
        missing_count?: number
      }>
      suggested_sync_codes?: string[]
      suggested_sync_funds?: Array<{
        wind_code?: string
        name?: string
        missing_metric_count?: number
        missing_metrics?: string[]
      }>
      next_action?: string
    }
    sample_status?: string
    metric_window?: string
    metrics?: Record<string, {
      metric_name?: string
      label?: string
      value?: number | null
      percentile?: number | null
      rank?: number | null
      peer_count?: number
      minimum_peer_count?: number
      sample_status?: string
      unit?: string
      direction?: string
    }>
  } | null
  buyEvidence?: {
    purchasePlan?: InvestorPurchasePlan
    plannedAmount?: number | null
    executionAmountGate?: {
      plannedAmount: number | null
      status: 'pass' | 'blocked' | 'unknown'
      label: string
      detail: string
      minPurchaseAmount: number | null
      minSipAmount: number | null
      dailyLimitAmount: number | null
    }
    completenessScore?: number
    completenessLevel?: 'strong' | 'partial' | 'thin'
    conclusion?: string
    knownItems?: Array<{
      label: string
      value: string
      source: string
      confidence: 'high' | 'medium' | 'low'
    }>
    missingItems?: Array<{
      label: string
      severity: 'high' | 'medium' | 'low'
      reason: string
      requiredBeforeBuy: boolean
    }>
    requiredMissingCount?: number
    mustVerifyBeforeBuy?: string[]
  } | null
  performanceData: Record<string, unknown>
  riskMetrics: Record<string, unknown>
  holdingCount?: number | null
  managerIds: string[]
  managers?: Array<{
    managerId?: string
    windCode?: string
    name?: string
    company?: string
    education?: string
    workYears?: number | null
    managementYears?: number | null
    currentFunds?: string[]
    beginDate?: string | null
    endDate?: string | null
    source?: string
  }>
  scores: Array<Record<string, unknown>>
  aiReports: Array<Record<string, unknown>>
  activeSalesRuleEvidenceAlert?: {
    id?: string
    fundCode?: string
    severity?: string
    title?: string
    message?: string
  } | null
  researchProfile?: {
    primaryBenchmark?: string
    secondaryBenchmark?: string | null
    peerGroup?: string
    styleLabel?: string
    strategyTags?: string[]
    managerTenureStart?: string | null
    capacityNotes?: string | null
    dataQualityNotes?: string | null
    evidence?: Record<string, unknown> | null
  } | null
  rollingMetrics?: Record<string, Record<string, string | number | null | undefined>>
  dataQuality?: {
    score?: number
    status?: string
    summary?: string
    issues?: string[]
    checks?: Record<string, { passed?: boolean; message?: string }>
  } | null
  professionalScoring?: {
    overall_score?: number
    overall_grade?: string
    fund_type_profile?: string
    peer_group?: string
    primary_benchmark?: string
    dimension_scores?: Record<string, { score?: number; weight?: number; evidence?: string[] }>
    positive_factors?: string[]
    negative_factors?: string[]
    calculation_method?: string
  } | null
  trust?: {
    dataAsOf?: string | null
    syncedAt?: string | null
    scoreAsOf?: string | null
    scoreCount?: number
    reportCount?: number
    dataQualityStatus?: string
    dataQualityScore?: number
    dataQualityIssues?: string[]
  }
}

interface FundDetailClientProps {
  fundId: string
  initialFund?: Fund | null
  initialReturnTo?: string
  initialInvestorContext?: {
    profile?: InvestorRiskProfile
    horizon?: InvestorHorizon
    purchasePlan?: InvestorPurchasePlan
    months?: string
    lumpSumAmount?: string
    monthlyAmount?: string
  }
}

type PurchaseSimulation = {
  source: string
  period: {
    startDate: string
    endDate: string
    observations: number
  }
  assumptions: {
    lumpSumAmount: number
    monthlyAmount: number
    sipFrequency: string
    feeIncluded: boolean
  }
  lumpSum: {
    totalInvested: number
    endingValue: number
    profit: number
    returnRate: number
    maxDrawdown: number
  }
  sip: {
    totalInvested: number
    endingValue: number
    profit: number
    returnRate: number | null
    contributionCount: number
    averageCost: number | null
    maxAccountDrawdown: number
  }
  feeAdjusted?: {
    coverage: 'none' | 'partial' | 'full'
    missingItems: string[]
    assumptions: {
      purchaseFeeRate: number | null
      redemptionFeeRules: Array<{ label: string; feeRate: number; holdingDays: number | null }>
      salesRulePlatform: string | null
    }
    lumpSum: null | {
      totalInvested: number
      purchaseFee: number
      redemptionFee: number
      totalFee: number
      endingValue: number
      profit: number
      returnRate: number
      holdingDays: number | null
      redemptionRule?: { label: string; feeRate: number; holdingDays: number | null } | null
      redemptionFeeLadder?: Array<{
        label: string
        feeRate: number
        holdingDays: number | null
        isCurrent: boolean
        daysUntilEffective: number | null
      }>
    }
    sip: null | {
      monthlyAmount: number
      contributionCount: number
      totalInvested: number
      purchaseFee: number
      redemptionFee: number
      totalFee: number
      endingValue: number
      profit: number
      returnRate: number | null
      redemptionRuleBuckets?: Array<{
        label: string
        feeRate: number
        holdingDays: number | null
        lotCount: number
        redemptionFee: number
      }>
    }
  }
  monthlyExperience: {
    months: number
    positiveMonths: number
    positiveRatio: number | null
    bestMonth?: { month: string; returnRate: number } | null
    worstMonth?: { month: string; returnRate: number } | null
  }
  stressExperience?: {
    label: string
    stressLevel: 'comfortable' | 'watchable' | 'bumpy' | 'stressful'
    stressScore: number
    worstDrawdown: number
    troughDate: string
    recoveryDays: number | null
    longestUnderwaterDays: number
    longestLosingStreakMonths: number
    worstThreeMonthReturn: {
      startMonth: string
      endMonth: string
      returnRate: number
    } | null
    interpretation: string
  }
  disclaimer: string
}

type AlternativeFund = {
  id: string
  windCode: string
  name: string
  type: string
  investorScore: number
  investorRating: 'A' | 'B' | 'C' | 'D'
  annualReturn: number | null
  maxDrawdown: number | null
  totalAsset: number | null
  purchaseGate?: {
    level: 'blocked' | 'verify_first' | 'research_ready' | 'watchlist'
    label: string
    evidenceGrade: 'A' | 'B' | 'C' | 'D'
    hardBlocks: string[]
    cautionFlags: string[]
  }
  riskSuitability?: {
    status: 'matched' | 'mismatch' | 'missing'
    label: string
  }
  reasons?: string[]
  warnings?: string[]
}

type AlternativeSearchMeta = {
  note: string
  attempts: string[]
  total: number
  source: string
}

type ShareClassFund = {
  id: string
  windCode: string
  name: string
  type: string
  nav: number | null
  totalAsset: number | null
  screeningScore?: number | null
  feeInfo?: {
    management_fee?: number | null
    managementFee?: number | null
    custodian_fee?: number | null
    custodianFee?: number | null
  } | null
  salesRule?: Fund['salesRule']
  executionAmountGate?: SalesRuleGapEvidence['executionAmountGate'] | null
  salesRuleMissingItems?: string[]
  salesRuleMissingCount?: number
}

type ShareClassInfoState = {
  baseName: string
  classType: string
  siblingCount: number
  siblingCodes: string[]
  siblingNames: string[]
  hint: string
  warnings: string[]
}

type CandidatePoolMember = {
  id: string
  fund_id?: string | null
  fund_wind_code?: string | null
  fund_name?: string | null
  status: string
}

type HoldingEvidence = {
  status: 'available' | 'unavailable'
  windCode: string
  quarter?: string
  holdings: Array<{
    stockCode: string
    stockName: string
    industry: string
    weight: number | null
  }>
  industryBuckets: Array<{ industry: string; weight: number }>
  totalWeight: number | null
  checkedQuarters: string[]
  rejectedMockLikeQuarters: string[]
  source: string
  note: string
}

type SalesRuleGapEvidence = {
  windCode: string
  fundName: string
  fundType: string
  totalAsset: number | string | null
  priority: 'high' | 'medium' | 'low'
  missingItems: string[]
  missingCount: number
  evidenceMissingCount: number
  evidenceScore: number | null
  purchaseGateLabel: string
  ruleUpdatedAt: string | null
  ruleSourceUpdatedAt: string | null
  riskLevel: string | null
  riskLevelSourceBacked: boolean
  riskLevelEvidenceStatus: 'verified' | 'missing' | 'unsourced' | 'stale'
  riskLevelEvidenceLabel: string
  riskLevelEvidenceDetail: string
  executionAmountGate?: {
    plannedAmount: number | null
    status: 'pass' | 'blocked' | 'unknown'
    label: string
    detail: string
    minPurchaseAmount: number | null
    minSipAmount: number | null
    dailyLimitAmount: number | null
  } | null
  nextAction: string
}

type SalesRuleFormState = {
  purchaseStatus: 'open' | 'closed' | 'limited' | 'unknown'
  minPurchaseAmount: string
  minSipAmount: string
  dailyLimitAmount: string
  purchaseFeeRate: string
  redemptionHoldingDays: string
  redemptionFeeRate: string
  salesServiceFeeRate: string
  riskLevel: string
  supportsSip: 'true' | 'false' | ''
  sourceUpdatedAt: string
  sourceUrl: string
  notes: string
}

type SimulationFormState = {
  months: string
  lumpSumAmount: string
  monthlyAmount: string
}

type InvestorRiskProfile = 'conservative' | 'balanced' | 'aggressive'
type InvestorHorizon = 'lt1y' | '1to3y' | 'gt3y'
type InvestorPurchasePlan = 'lump_sum' | 'sip'

function riskLevelPolicyBadgeClass(tone: ReportRiskLevelGatePolicy['tone']) {
  if (tone === 'emerald') return 'bg-emerald-100 text-emerald-800'
  if (tone === 'amber') return 'bg-amber-100 text-amber-800'
  return 'bg-slate-100 text-slate-700'
}

const purchaseStatusLabelMap: Record<SalesRuleFormState['purchaseStatus'], string> = {
  open: '开放申购',
  closed: '暂停申购',
  limited: '限额申购',
  unknown: '申购待核',
}

function salesRuleToForm(fund: Fund | null): SalesRuleFormState {
  const rule = fund?.salesRule
  const redemptionRule = rule?.redemptionFeeRules?.[0]
  return {
    purchaseStatus: rule?.purchaseStatus || (rule?.purchaseStatusLabel === '开放申购'
      ? 'open'
      : rule?.purchaseStatusLabel === '暂停申购'
        ? 'closed'
        : rule?.purchaseStatusLabel === '限额申购'
          ? 'limited'
          : 'unknown'),
    minPurchaseAmount: rule?.minPurchaseAmount == null ? '' : String(rule.minPurchaseAmount),
    minSipAmount: rule?.minSipAmount == null ? '' : String(rule.minSipAmount),
    dailyLimitAmount: rule?.dailyLimitAmount == null ? '' : String(rule.dailyLimitAmount),
    purchaseFeeRate: rule?.purchaseFeeRate == null ? '' : String(rule.purchaseFeeRate),
    redemptionHoldingDays: redemptionRule?.holdingDays == null ? '' : String(redemptionRule.holdingDays),
    redemptionFeeRate: redemptionRule?.feeRate == null ? '' : String(redemptionRule.feeRate),
    salesServiceFeeRate: rule?.salesServiceFeeRate == null ? '' : String(rule.salesServiceFeeRate),
    riskLevel: rule?.riskLevel || '',
    supportsSip: rule?.supportsSip == null ? '' : rule.supportsSip ? 'true' : 'false',
    sourceUpdatedAt: rule?.sourceUpdatedAt || new Date().toISOString().slice(0, 10),
    sourceUrl: rule?.sourceUrl || '',
    notes: rule?.notes || '',
  }
}

const defaultSimulationForm: SimulationFormState = {
  months: '12',
  lumpSumAmount: '10000',
  monthlyAmount: '1000',
}

function formatDateText(value?: string | null) {
  if (!value) return '-'
  const rawValue = String(value).trim()
  if (!rawValue) return '-'

  const normalizedDate = rawValue.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/)
  if (normalizedDate) {
    const [, year, month, day] = normalizedDate
    return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`
  }

  const compactDate = rawValue.match(/^(\d{4})(\d{2})(\d{2})$/)
  if (compactDate) {
    const [, year, month, day] = compactDate
    return `${year}-${month}-${day}`
  }

  const parsedDate = new Date(rawValue)
  if (Number.isNaN(parsedDate.getTime())) return rawValue

  const year = parsedDate.getUTCFullYear()
  const month = String(parsedDate.getUTCMonth() + 1).padStart(2, '0')
  const day = String(parsedDate.getUTCDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatDateTimeText(value?: string | null) {
  if (!value) return '-'
  const rawValue = String(value).trim()
  if (!rawValue) return '-'

  const parsedDate = new Date(rawValue)
  if (Number.isNaN(parsedDate.getTime())) return rawValue

  const year = parsedDate.getUTCFullYear()
  const month = String(parsedDate.getUTCMonth() + 1).padStart(2, '0')
  const day = String(parsedDate.getUTCDate()).padStart(2, '0')
  const hours = String(parsedDate.getUTCHours()).padStart(2, '0')
  const minutes = String(parsedDate.getUTCMinutes()).padStart(2, '0')
  const seconds = String(parsedDate.getUTCSeconds()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}

function parseEvidenceDate(value?: string | null) {
  const normalized = formatDateText(value)
  if (!normalized || normalized === '-') return null
  const parsed = new Date(`${normalized}T00:00:00Z`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function evidenceAgeDays(value?: string | null) {
  const parsed = parseEvidenceDate(value)
  if (!parsed) return null
  return Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 86_400_000))
}

function isFreshSalesRuleSourceDate(value?: string | null) {
  const parsed = parseEvidenceDate(value)
  if (!parsed) return false
  const currentDate = new Date()
  currentDate.setUTCHours(0, 0, 0, 0)
  const ageDays = Math.floor((currentDate.getTime() - parsed.getTime()) / 86_400_000)
  return ageDays >= 0 && ageDays <= 30
}

function hasSourceBackedRedemptionRules(rule?: Fund['salesRule']) {
  if (!rule?.redemptionFeeRules?.length) return false
  const sourceUpdatedAt = rule.redemptionFeeSourceUpdatedAt || rule.sourceUpdatedAt
  if (!isFreshSalesRuleSourceDate(sourceUpdatedAt)) return false
  const platform = String(rule.redemptionFeePlatform || rule.platform || '').trim()
  const sourceUrl = String(rule.redemptionFeeSourceUrl || rule.sourceUrl || '').trim()
  const notes = String(rule.redemptionFeeNotes || rule.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function hasSourceBackedSalesRuleField(rule: Fund['salesRule'] | undefined | null, sourceFlag: keyof NonNullable<Fund['salesRule']>, value: unknown) {
  if (value === null || value === undefined || value === '') return false
  const explicitFlag = rule?.[sourceFlag]
  if (explicitFlag === true) return true
  if (explicitFlag === false) return false
  if (!isFreshSalesRuleSourceDate(rule?.sourceUpdatedAt)) return false
  const platform = String(rule?.platform || '').trim()
  const sourceUrl = String(rule?.sourceUrl || '').trim()
  const notes = String(rule?.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function evidenceFreshnessStatus(ageDays: number | null, warnDays: number, staleDays: number) {
  if (ageDays === null) return 'missing' as const
  if (ageDays > staleDays) return 'stale' as const
  if (ageDays > warnDays) return 'watch' as const
  return 'fresh' as const
}

const investorRiskProfiles: Record<InvestorRiskProfile, {
  label: string
  note: string
  maxDrawdownTolerance: number
  maxSalesRiskLevel: number
}> = {
  conservative: {
    label: '稳健型',
    note: '优先控制回撤和销售风险等级',
    maxDrawdownTolerance: 0.08,
    maxSalesRiskLevel: 2,
  },
  balanced: {
    label: '均衡型',
    note: '兼顾收益弹性、回撤和证据完整度',
    maxDrawdownTolerance: 0.15,
    maxSalesRiskLevel: 3,
  },
  aggressive: {
    label: '进取型',
    note: '可接受更高波动，但仍不能跳过研究复核证据',
    maxDrawdownTolerance: 0.28,
    maxSalesRiskLevel: 5,
  },
}

const investorHorizons: Record<InvestorHorizon, { label: string; minSampleMonths: number; note: string }> = {
  lt1y: { label: '1年以内', minSampleMonths: 6, note: '短持有期更看重回撤、赎回规则和流动性' },
  '1to3y': { label: '1-3年', minSampleMonths: 12, note: '需要至少一年净值样本观察持有体验' },
  gt3y: { label: '3年以上', minSampleMonths: 36, note: '更重视跨周期收益、经理任期和风格稳定' },
}

const investorPurchasePlans: Record<InvestorPurchasePlan, { label: string; note: string }> = {
  lump_sum: { label: '一次性配置假设', note: '重点核查限购、申购费和短期回撤压力' },
  sip: { label: '定投', note: '重点核查是否支持定投、定投起点和月度胜率' },
}

function salesRuleEvidenceCopyForPlan(purchasePlan: InvestorPurchasePlan) {
  if (purchasePlan === 'lump_sum') {
    return {
      formalFields: '申购费、赎回费、销售服务费、起购金额、限购和风险等级',
      recheckFields: '申购费、赎回费、销售服务费、起购金额、限购和风险等级',
      scanDescription: '当前还不知道申购状态、费率、赎回、起购金额、限购、风险等级和来源日期是否完整。',
      primaryNextAction: '先补主基金申购、费率、赎回、起购金额、限购、风险等级和来源日期',
      gateWhy: '销售规则决定真实申购成本、赎回成本、起购门槛、限购额度和适当性匹配。',
    }
  }
  return {
    formalFields: '申购费、赎回费、销售服务费、定投规则、限购和风险等级',
    recheckFields: '申购费、赎回费、销售服务费、定投起点、限购和风险等级',
    scanDescription: '当前还不知道申购状态、费率、赎回、定投、限购、风险等级和来源日期是否完整。',
    primaryNextAction: '先补主基金申购、费率、赎回、定投、限购、风险等级和来源日期',
    gateWhy: '销售规则决定真实申购成本、赎回成本、定投/起购门槛、限购额度和适当性匹配。',
  }
}

const poolStatusLabels: Record<string, string> = {
  candidate: '候选',
  watch: '观察',
  core: '核心跟踪',
  rejected: '淘汰',
}

function appendReturnTo(href: string, returnTo: string) {
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`
}

function safeReturnPath(returnTo: string | undefined) {
  return returnTo?.startsWith('/') && !returnTo.startsWith('//') ? returnTo : '/funds'
}

function buildFundDetailMethodologyFocus(fund: Fund) {
  const availableEvidence = Array.from(new Set([
    fund.type ? 'asset_class' : '',
    fund.type ? 'strategy_type' : '',
    fund.totalAsset != null ? 'aum' : '',
    fund.nav != null ? 'tracking_difference' : '',
    fund.holdingCount ? 'top_holdings' : '',
    fund.holdingCount ? 'holding_count' : '',
    fund.performanceData ? 'excess_return' : '',
    fund.riskMetrics ? 'tracking_error' : '',
    fund.researchProfile?.primaryBenchmark || fund.benchmark ? 'benchmark_mapping' : '',
    fund.peerPercentiles?.peer_group || fund.researchProfile?.peerGroup ? 'peer_group_policy' : '',
    fund.researchProfile?.styleLabel ? 'style_exposure' : '',
    fund.researchProfile?.strategyTags?.length ? 'style_tags' : '',
    fund.managers?.length ? 'tenure_slice' : '',
    fund.managers?.length ? 'representative_fund' : '',
    fund.feeInfo || fund.salesRule ? 'fee_rate' : '',
  ].filter(Boolean)))
  const result = methodologyConfigTool.run({
    fundType: fund.type,
    assetClass: fund.type,
    strategyFamilyKey: fund.researchProfile?.strategyTags?.[0] || fund.researchProfile?.styleLabel || fund.type,
    availableEvidence,
  })
  const data = result.data
  const dimensions = (data?.dimensions || []).slice(0, 6)
  return {
    templateName: data?.templateName || '基金分类待确认',
    templateKey: data?.templateKey || 'unclassified',
    matchRationale: data?.matchRationale || '基金分类证据待补，暂不选择评价模板。',
    dimensions,
    hardGateDimensions: data?.hardGateDimensions || [],
    methodologyMissingEvidenceFields: data?.missingEvidenceFields || [],
    readyForFormalReview: Boolean(data?.readyForFormalReview),
    hardBlocks: result.hardBlocks,
    boundary: '方法论模板只决定研究口径；证据不完整时只能输出补证方向，不输出申赎执行、资产配置或审批动作。',
    tsvRows: [
      ['研究模板', data?.templateName || '基金分类待确认', data?.templateKey || 'unclassified', data?.matchRationale || '基金分类证据待补'],
      ...dimensions.map((dimension: MethodologyDimension) => [
        '核心研究维度',
        dimension.name,
        `权重 ${dimension.weight}`,
        dimension.reason,
      ]),
      ['方法论缺口', data?.missingEvidenceFields?.join('、') || '无', '', '缺口未补齐前只进入研究观察。'],
    ],
  }
}

export default function FundDetailClient({ fundId, initialFund = null, initialInvestorContext, initialReturnTo = '/funds' }: FundDetailClientProps) {
  const sourceReturnHref = safeReturnPath(initialReturnTo)
  const [renderNow] = useState(() => Date.now())
  const [fund, setFund] = useState<Fund | null>(initialFund)
  const [purchaseSimulation, setPurchaseSimulation] = useState<PurchaseSimulation | null>(null)
  const [holdingEvidence, setHoldingEvidence] = useState<HoldingEvidence | null>(null)
  const [salesRuleGap, setSalesRuleGap] = useState<SalesRuleGapEvidence | null>(null)
  const [salesRuleGapCheckedCode, setSalesRuleGapCheckedCode] = useState<string | null>(null)
  const [alternativeFunds, setAlternativeFunds] = useState<AlternativeFund[]>([])
  const [alternativeSearchMeta, setAlternativeSearchMeta] = useState<AlternativeSearchMeta | null>(null)
  const [alternativeSalesRuleGaps, setAlternativeSalesRuleGaps] = useState<Record<string, SalesRuleGapEvidence>>({})
  const [alternativeSalesRuleGapError, setAlternativeSalesRuleGapError] = useState<string | null>(null)
  const [shareClassFunds, setShareClassFunds] = useState<ShareClassFund[]>([])
  const [shareClassInfo, setShareClassInfo] = useState<ShareClassInfoState | null>(null)
  const [shareClassLoading, setShareClassLoading] = useState(false)
  const [shareClassError, setShareClassError] = useState<string | null>(null)
  const [holdingLoading, setHoldingLoading] = useState(false)
  const [salesRuleGapLoading, setSalesRuleGapLoading] = useState(false)
  const [salesRuleGapError, setSalesRuleGapError] = useState<string | null>(null)
  const [foundationHydrating, setFoundationHydrating] = useState(false)
  const [alternativesLoading, setAlternativesLoading] = useState(false)
  const [alternativeSalesRuleGapsLoading, setAlternativeSalesRuleGapsLoading] = useState(false)
  const [simulationForm, setSimulationForm] = useState<SimulationFormState>(() => ({
    months: initialInvestorContext?.months || defaultSimulationForm.months,
    lumpSumAmount: initialInvestorContext?.lumpSumAmount || defaultSimulationForm.lumpSumAmount,
    monthlyAmount: initialInvestorContext?.monthlyAmount || defaultSimulationForm.monthlyAmount,
  }))
  const [investorRiskProfile, setInvestorRiskProfile] = useState<InvestorRiskProfile>(initialInvestorContext?.profile || 'balanced')
  const [investorHorizon, setInvestorHorizon] = useState<InvestorHorizon>(initialInvestorContext?.horizon || '1to3y')
  const [investorPurchasePlan, setInvestorPurchasePlan] = useState<InvestorPurchasePlan>(initialInvestorContext?.purchasePlan || 'sip')
  const [simulationLoading, setSimulationLoading] = useState(false)
  const [salesRuleSaving, setSalesRuleSaving] = useState(false)
  const [salesRuleForm, setSalesRuleForm] = useState<SalesRuleFormState>(() => salesRuleToForm(initialFund))
  const [loading, setLoading] = useState(!initialFund)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [bannerMessage, setBannerMessage] = useState<string | null>(null)
  const [addingToPool, setAddingToPool] = useState(false)
  const [candidatePoolId, setCandidatePoolId] = useState('')
  const [candidatePoolMembers, setCandidatePoolMembers] = useState<CandidatePoolMember[]>([])
  const [candidatePoolLoading, setCandidatePoolLoading] = useState(false)
  const [summaryCopied, setSummaryCopied] = useState(false)
  const [reportGenerating, setReportGenerating] = useState(false)
  const [reportSaving, setReportSaving] = useState(false)
  const [savedReportId, setSavedReportId] = useState<string | null>(null)
  const fetchFundDetailRef = useRef<() => Promise<void>>(async () => {})
  const fetchPurchaseSimulationRef = useRef<(code: string) => Promise<void>>(async () => {})
  const fetchHoldingEvidenceRef = useRef<(code: string) => Promise<void>>(async () => {})
  const fetchShareClassFundsRef = useRef<(target: Fund) => Promise<void>>(async () => {})

  const formatPercent = (value: string | number | null | undefined) => {
    if (value == null || value === '') return '-'
    const numberValue = Number(value)
    if (Number.isNaN(numberValue)) return '-'
    return `${(numberValue * 100).toFixed(2)}%`
  }

  const formatRatio = (value: string | number | null | undefined) => {
    if (value == null || value === '') return '-'
    const numberValue = Number(value)
    if (Number.isNaN(numberValue)) return '-'
    return numberValue.toFixed(2)
  }

  const formatMoney = (value: number | null | undefined) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
    return `¥${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
  }

  const formatPeerMetricValue = (value: number | null | undefined, unit?: string) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '缺失'
    if (unit === 'percent') return `${(Number(value) * 100).toFixed(2)}%`
    if (unit === 'score') return Number(value).toFixed(1)
    return Number(value).toFixed(2)
  }

  const peerPercentileClass = (value: number | null | undefined) => {
    if (value === null || value === undefined) return 'bg-slate-100 text-slate-600'
    if (value >= 70) return 'bg-emerald-100 text-emerald-800'
    if (value >= 45) return 'bg-blue-100 text-blue-800'
    if (value >= 25) return 'bg-amber-100 text-amber-800'
    return 'bg-rose-100 text-rose-800'
  }

  const peerVerdictClass = (tone: 'emerald' | 'blue' | 'amber' | 'rose' | 'slate') => {
    if (tone === 'emerald') return 'border-emerald-100 bg-emerald-50 text-emerald-900'
    if (tone === 'blue') return 'border-blue-100 bg-blue-50 text-blue-900'
    if (tone === 'amber') return 'border-amber-100 bg-amber-50 text-amber-900'
    if (tone === 'rose') return 'border-rose-100 bg-rose-50 text-rose-900'
    return 'border-slate-100 bg-slate-50 text-slate-900'
  }

  const buyEvidenceClass = (level?: string) => {
    if (level === 'strong') return 'bg-emerald-100 text-emerald-800'
    if (level === 'partial') return 'bg-amber-100 text-amber-800'
    return 'bg-rose-100 text-rose-800'
  }

  const workflowStatusClass = (status: 'done' | 'verify' | 'blocked' | 'pending') => {
    if (status === 'done') return 'border-emerald-100 bg-emerald-50 text-emerald-900'
    if (status === 'blocked') return 'border-rose-100 bg-rose-50 text-rose-900'
    if (status === 'verify') return 'border-amber-100 bg-amber-50 text-amber-900'
    return 'border-slate-100 bg-slate-50 text-slate-800'
  }

  const asNumber = (value: unknown) => {
    if (value === null || value === undefined || value === '') return null
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }

  const asPositiveNumber = (value: unknown, fallback: number) => {
    const parsed = asNumber(value)
    return parsed !== null && parsed > 0 ? parsed : fallback
  }

  const currentPlannedAmount = () => investorPurchasePlan === 'lump_sum'
    ? asPositiveNumber(simulationForm.lumpSumAmount, 10000)
    : asPositiveNumber(simulationForm.monthlyAmount, 1000)

  const totalFee = (target: { feeInfo?: ShareClassFund['feeInfo'] | Fund['feeInfo'] }) => {
    const managementFee = asNumber(target.feeInfo?.management_fee ?? target.feeInfo?.managementFee)
    const custodianFee = asNumber(target.feeInfo?.custodian_fee ?? target.feeInfo?.custodianFee)
    return managementFee === null || custodianFee === null ? null : managementFee + custodianFee
  }

  const amountByRate = (amount: number, rate: number | null | undefined) => {
    const value = asNumber(rate)
    return value === null ? null : Math.round(amount * value / 100)
  }

  const shareClassAnnualBaseFeeAmount = (target: ShareClassFund) => amountByRate(currentPlannedAmount(), totalFee(target))

  const shareClassCurrentSalesRuleCost = (target: ShareClassFund) => {
    const isCurrentFund = fund?.windCode && target.windCode.toUpperCase() === fund.windCode.toUpperCase()
    const salesRule = target.salesRule || (isCurrentFund ? fund.salesRule : null)
    const annualBaseFeeAmount = shareClassAnnualBaseFeeAmount(target)
    const purchaseFeeRate = hasSourceBackedSalesRuleField(salesRule, 'purchaseFeeSourceBacked', salesRule?.purchaseFeeRate) ? salesRule?.purchaseFeeRate : null
    const salesServiceFeeRate = hasSourceBackedSalesRuleField(salesRule, 'salesServiceFeeSourceBacked', salesRule?.salesServiceFeeRate) ? salesRule?.salesServiceFeeRate : null
    const purchaseFeeAmount = amountByRate(currentPlannedAmount(), purchaseFeeRate)
    const salesServiceFeeAmount = amountByRate(currentPlannedAmount(), salesServiceFeeRate)
    const knownParts = [annualBaseFeeAmount, purchaseFeeAmount, salesServiceFeeAmount]
      .filter((value): value is number => value !== null)
    const missing = [
      !salesRule ? '兄弟份额销售规则待补' : '',
      annualBaseFeeAmount === null ? '管理/托管费' : '',
      purchaseFeeAmount === null ? '申购费（30天来源背书）' : '',
      hasSourceBackedRedemptionRules(salesRule) ? '' : '赎回费/持有期',
      salesServiceFeeAmount === null ? '销售服务费（30天来源背书）' : '',
      ...(target.salesRuleMissingItems || []).filter((item) => item.startsWith('计划金额执行门禁')),
    ].filter(Boolean)
    return {
      purchaseFeeAmount,
      salesServiceFeeAmount,
      knownCost: knownParts.length ? knownParts.reduce((sum, value) => sum + value, 0) : null,
      missing,
    }
  }

  const formatScoreDiff = (value: number | null | undefined, suffix = '') => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
    const numberValue = Number(value)
    return `${numberValue > 0 ? '+' : ''}${numberValue.toFixed(1)}${suffix}`
  }

  const parseSalesRiskLevel = (value: string | null | undefined) => {
    const match = String(value || '').trim().match(/R?([1-5])/i)
    return match ? Number(match[1]) : null
  }

  const metric = (source: Record<string, unknown>, keys: string[]) => {
    for (const key of keys) {
      const value = asNumber(source?.[key])
      if (value !== null) return value
    }
    return null
  }

  const fundAgeDays = (establishmentDate: string | null) => {
    if (!establishmentDate) return null
    const startedAt = new Date(establishmentDate).getTime()
    if (!Number.isFinite(startedAt)) return null
    return Math.max(0, Math.floor((renderNow - startedAt) / 86_400_000))
  }

  const buildDetailGate = (
    target: Fund,
    context: {
      profile?: InvestorRiskProfile
      horizon?: InvestorHorizon
      purchasePlan?: InvestorPurchasePlan
    } = {},
  ) => {
    const contextProfile = context.profile || investorRiskProfile
    const contextHorizon = context.horizon || investorHorizon
    const contextPurchasePlan = context.purchasePlan || investorPurchasePlan
    const profileConfig = investorRiskProfiles[contextProfile]
    const horizonConfig = investorHorizons[contextHorizon]
    const purchasePlanConfig = investorPurchasePlans[contextPurchasePlan]
    const annualReturn = metric(target.performanceData || {}, ['annualized_return_1y', 'return_1y', 'annual_return'])
    const maxDrawdown = metric(target.riskMetrics || {}, ['max_drawdown_1y', 'max_drawdown', 'max_drawdown_2y'])
    const volatility = metric(target.riskMetrics || {}, ['annualized_volatility_1y', 'volatility', 'annualized_volatility_2y'])
    const totalAsset = asNumber(target.totalAsset)
    const ageDays = fundAgeDays(target.establishmentDate)
    const drawdown = maxDrawdown === null ? null : Math.abs(maxDrawdown)
    const riskBudget = profileConfig.maxDrawdownTolerance
    const operationStatus = target.operationStatus
    const salesRiskLevel = parseSalesRiskLevel(target.salesRule?.riskLevel)
    const lumpSumAmount = asPositiveNumber(simulationForm.lumpSumAmount, 10000)
    const monthlyAmount = asPositiveNumber(simulationForm.monthlyAmount, 1000)
    const rawMinPurchaseAmount = asNumber(target.salesRule?.minPurchaseAmount)
    const rawMinSipAmount = asNumber(target.salesRule?.minSipAmount)
    const rawDailyLimitAmount = asNumber(target.salesRule?.dailyLimitAmount)
    const minPurchaseAmount = hasSourceBackedSalesRuleField(target.salesRule, 'minPurchaseSourceBacked', rawMinPurchaseAmount) ? rawMinPurchaseAmount : null
    const minSipAmount = hasSourceBackedSalesRuleField(target.salesRule, 'minSipSourceBacked', rawMinSipAmount) ? rawMinSipAmount : null
    const dailyLimitAmount = hasSourceBackedSalesRuleField(target.salesRule, 'dailyLimitSourceBacked', rawDailyLimitAmount) ? rawDailyLimitAmount : null
    const supportsSip = hasSourceBackedSalesRuleField(target.salesRule, 'supportsSipSourceBacked', target.salesRule?.supportsSip) ? target.salesRule?.supportsSip : null
    const hasFeeEvidence =
      target.feeInfo?.management_fee != null ||
      target.feeInfo?.managementFee != null ||
      target.feeInfo?.custodian_fee != null ||
      target.feeInfo?.custodianFee != null
    const managementFee = asNumber(target.feeInfo?.management_fee ?? target.feeInfo?.managementFee)
    const custodianFee = asNumber(target.feeInfo?.custodian_fee ?? target.feeInfo?.custodianFee)
    const feeSummary = [
      managementFee !== null ? `管理费 ${managementFee.toFixed(2)}%` : '',
      custodianFee !== null ? `托管费 ${custodianFee.toFixed(2)}%` : '',
    ].filter(Boolean).join('，') || '待补'
    const hasVerifiedHoldings = holdingEvidence?.status === 'available'
    const normalizedCode = target.windCode.toUpperCase()
    const salesRuleGapReady = salesRuleGapCheckedCode === normalizedCode
    const salesRuleHardGapCount = salesRuleGapReady ? salesRuleGap?.missingCount ?? 0 : null

    const dataGaps = [
      target.nav === null ? '最新净值' : '',
      target.navDate ? '' : '净值日期',
      totalAsset === null ? '基金规模' : '',
      annualReturn === null ? '近一年收益' : '',
      maxDrawdown === null ? '最大回撤' : '',
      operationStatus?.status === 'unknown' || !operationStatus ? '申购状态' : '',
      hasFeeEvidence ? '' : '销售费率/限购',
      salesRuleHardGapCount === null ? '销售规则硬缺口待扫描' : salesRuleHardGapCount > 0 ? `销售规则硬缺口 ${salesRuleHardGapCount} 项` : '',
      hasVerifiedHoldings ? '' : '持仓明细',
    ].filter(Boolean)

    const evidenceScore = [
      target.nav !== null,
      Boolean(target.navDate),
      Boolean(target.establishmentDate),
      annualReturn !== null,
      maxDrawdown !== null,
      totalAsset !== null,
      operationStatus?.status && operationStatus.status !== 'unknown',
      hasFeeEvidence,
      salesRuleHardGapCount === 0,
      hasVerifiedHoldings,
    ].filter(Boolean).length

    const evidenceGrade = evidenceScore >= 7 && dataGaps.length <= 3 ? 'B' : evidenceScore >= 5 ? 'C' : 'D'
    const hardBlocks: string[] = []
    const cautionFlags: string[] = []
    const suitabilityNotes: string[] = []

    if (operationStatus?.status === 'blocked') hardBlocks.push(operationStatus.reason || '存在退市、清算或终止信号')
    if (drawdown !== null && drawdown > riskBudget) hardBlocks.push(`最大回撤 ${formatPercent(-drawdown)} 超过${profileConfig.label}预算 ${formatPercent(-riskBudget)}`)
    if (totalAsset !== null && totalAsset < 2) hardBlocks.push('基金规模低于 2 亿，清盘和流动性风险需先排除')
    if (salesRiskLevel !== null && salesRiskLevel > profileConfig.maxSalesRiskLevel) hardBlocks.push(`销售风险等级 R${salesRiskLevel} 超过${profileConfig.label}可接受等级 R${profileConfig.maxSalesRiskLevel}`)
	    if (contextPurchasePlan === 'sip' && supportsSip === false) hardBlocks.push('本地销售规则显示不支持定投，和当前研究方式假设不匹配')
    if (salesRuleGapCheckedCode === normalizedCode && salesRuleGap?.executionAmountGate?.status === 'blocked') hardBlocks.push(salesRuleGap.executionAmountGate.detail)
    if (contextPurchasePlan === 'sip' && minSipAmount !== null && monthlyAmount < minSipAmount) hardBlocks.push(`每月定投金额低于平台定投起点 ${formatMoney(minSipAmount)}`)
    if (contextPurchasePlan === 'lump_sum' && minPurchaseAmount !== null && lumpSumAmount < minPurchaseAmount) hardBlocks.push(`一次性计划金额低于平台起购金额 ${formatMoney(minPurchaseAmount)}`)
    if (contextPurchasePlan === 'lump_sum' && dailyLimitAmount !== null && lumpSumAmount > dailyLimitAmount) hardBlocks.push(`一次性计划金额超过本地记录限购金额 ${formatMoney(dailyLimitAmount)}`)

    if (!operationStatus || operationStatus.status === 'unknown') cautionFlags.push('缺少销售端申购/赎回开放状态')
    if (totalAsset === null) cautionFlags.push('基金规模缺失，无法判断容量和清盘风险')
    if (ageDays !== null && ageDays < 365) cautionFlags.push('成立不足一年，收益风险样本偏短')
    if (dataGaps.includes('销售费率/限购')) cautionFlags.push('缺少申购费、赎回费、销售服务费和限购信息')
    if (salesRuleHardGapCount === null) cautionFlags.push('销售规则硬缺口尚未扫描')
    if (salesRuleHardGapCount !== null && salesRuleHardGapCount > 0) cautionFlags.push(`销售规则硬缺口 ${salesRuleHardGapCount} 项：${salesRuleGap?.missingItems.slice(0, 3).join('、')}`)
    if (dataGaps.includes('持仓明细')) cautionFlags.push('缺少持仓明细，暂不能解释行业/个股暴露')
    if (salesRiskLevel === null) cautionFlags.push('销售平台风险等级待补，适当性匹配不完整')
	    if (contextPurchasePlan === 'sip' && supportsSip == null) cautionFlags.push('定投支持状态待补或缺少30天来源背书，无法确认当前研究方式假设可执行')
    if (contextHorizon === 'gt3y' && rollingMetricRows.every((item) => item.window !== '3y')) cautionFlags.push('缺少三年滚动指标，长期持有稳定性证据不足')
    if (purchaseSimulation && purchaseSimulation.monthlyExperience.months < horizonConfig.minSampleMonths) cautionFlags.push(`${horizonConfig.label}至少需要 ${horizonConfig.minSampleMonths} 个月回放样本，当前样本偏短`)

    suitabilityNotes.push(profileConfig.note)
    suitabilityNotes.push(horizonConfig.note)
    suitabilityNotes.push(purchasePlanConfig.note)
    if (salesRiskLevel !== null) suitabilityNotes.push(`销售风险等级 R${salesRiskLevel}，当前画像最高接受 R${profileConfig.maxSalesRiskLevel}`)
    if (drawdown !== null) suitabilityNotes.push(`历史最大回撤 ${formatPercent(-drawdown)}，当前画像预算 ${formatPercent(-riskBudget)}`)

    const level = hardBlocks.length
      ? 'blocked'
      : evidenceGrade === 'D' || cautionFlags.length >= 4
        ? 'verify_first'
        : 'watchlist'

    const label = level === 'blocked' ? '不可纳入研究候选' : level === 'verify_first' ? '先补证再比较' : '可放入观察清单'
    const className = level === 'blocked' ? 'bg-rose-100 text-rose-800' : level === 'verify_first' ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-700'

    return {
      annualReturn,
      maxDrawdown,
      volatility,
      totalAsset,
      operationLabel: operationStatus?.label || '申购待核',
      feeSummary,
      dataGaps,
      evidenceGrade,
      hardBlocks,
      cautionFlags,
      suitabilityNotes,
      profileLabel: profileConfig.label,
      horizonLabel: horizonConfig.label,
      purchasePlanLabel: purchasePlanConfig.label,
      riskBudget,
      maxSalesRiskLevel: profileConfig.maxSalesRiskLevel,
      salesRiskLevel,
      level,
      label,
      className,
      mustVerifyBeforeBuy: [
        '销售平台是否开放申购/定投',
        ...(salesRuleGapReady && salesRuleGap?.missingItems?.length ? [`销售规则硬缺口：${salesRuleGap.missingItems.slice(0, 5).join('、')}`] : []),
        hasFeeEvidence ? '销售平台申购/赎回费、限购与持有期规则' : '申购费、赎回费、销售服务费与持有期规则',
        '基金合同、最新季报与风险等级是否匹配本人适当性',
      ],
    }
  }

  const rollingWindowLabels: Record<string, string> = {
    '3m': '3M',
    '6m': '6M',
    '1y': '1Y',
    '3y': '3Y',
    manager_tenure: '任期',
  }

  const rollingMetricRows = ['3m', '6m', '1y', '3y', 'manager_tenure']
    .map((window) => ({ window, label: rollingWindowLabels[window] || window.toUpperCase(), metrics: fund?.rollingMetrics?.[window] }))
    .filter((item) => item.metrics)

  const dimensionLabels: Record<string, string> = {
    return: '收益能力',
    risk: '风险控制',
    risk_adjusted: '风险调整收益',
    consistency: '持续性',
    manager_tenure: '现任经理任期',
    data_quality: '数据质量',
  }

  const fetchFundDetail = async () => {
    setLoading(true)
    setErrorMessage(null)
    try {
      const params = new URLSearchParams({ purchasePlan: investorPurchasePlan, plannedAmount: String(currentPlannedAmount()) })
      const response = await fetch(`/api/funds/${fundId}?${params.toString()}`)
      if (response.ok) {
        const data = await response.json()
        setFund(data)
        setSalesRuleForm(salesRuleToForm(data))
      } else {
        setFund(null)
        setErrorMessage('基金详情不存在或暂时不可用')
      }
    } catch (error) {
      console.error('获取基金详情失败:', error)
      setFund(null)
      setErrorMessage('获取基金详情失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  const fetchPurchaseSimulation = async (code: string, form: SimulationFormState = simulationForm) => {
    setSimulationLoading(true)
    try {
      const params = new URLSearchParams({
        months: String(Math.max(3, Math.min(60, Math.round(asPositiveNumber(form.months, 12))))),
        lumpSumAmount: String(Math.max(1, asPositiveNumber(form.lumpSumAmount, 10000))),
        monthlyAmount: String(Math.max(1, asPositiveNumber(form.monthlyAmount, 1000))),
        purchasePlan: investorPurchasePlan,
      })
      const response = await fetch(`/api/funds/${encodeURIComponent(code)}/historical-nav-replay?${params.toString()}`)
      const payload = await response.json().catch(() => ({}))
      if (response.ok) {
        setPurchaseSimulation(payload)
      } else {
        setPurchaseSimulation(null)
      }
    } catch (error) {
      console.error('持有体验回放失败:', error)
      setPurchaseSimulation(null)
    } finally {
      setSimulationLoading(false)
    }
  }

  const fetchHoldingEvidence = async (code: string) => {
    setHoldingLoading(true)
    try {
      const response = await fetch(`/api/funds/${encodeURIComponent(code)}/holdings`)
      const payload = await response.json().catch(() => ({}))
      if (response.ok) {
        setHoldingEvidence(payload)
      } else {
        setHoldingEvidence(null)
      }
    } catch (error) {
      console.error('读取持仓证据失败:', error)
      setHoldingEvidence(null)
    } finally {
      setHoldingLoading(false)
    }
  }

  const fetchSalesRuleGap = useCallback(async (code: string) => {
    const normalizedCode = code.trim().toUpperCase()
    if (!normalizedCode) return
    setSalesRuleGapLoading(true)
    setSalesRuleGapError(null)
    try {
      const params = new URLSearchParams({
        codes: normalizedCode,
        limit: '1',
        purchasePlan: investorPurchasePlan,
        plannedAmount: String(currentPlannedAmount()),
      })
      const response = await fetch(`/api/evidence-coverage/materials/gaps?${params.toString()}`, { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.error || payload.detail || '读取销售规则硬缺口失败')
      }
      const rule = (payload.rules || [])[0]
      const gap = (payload.gaps || [])[0]
      setSalesRuleGap(gap
        ? { ...gap, executionAmountGate: gap.executionAmountGate || rule?.executionAmountGate || null }
        : rule
          ? {
              windCode: String(rule.windCode || normalizedCode),
              fundName: fund?.name || normalizedCode,
              fundType: fund?.type || '',
              totalAsset: fund?.totalAsset ?? null,
              priority: 'low',
              missingItems: rule.missingItems || [],
              missingCount: Number(rule.missingCount || 0),
              evidenceMissingCount: Number(rule.missingCount || 0),
              evidenceScore: null,
              purchaseGateLabel: Number(rule.missingCount || 0) > 0 ? '代码级研究复核证据待补' : '销售规则相对完整',
              ruleUpdatedAt: rule.ruleUpdatedAt || null,
              ruleSourceUpdatedAt: rule.ruleSourceUpdatedAt || null,
              riskLevel: rule.riskLevel || null,
              riskLevelSourceBacked: Boolean(rule.riskLevelSourceBacked),
              riskLevelEvidenceStatus: rule.riskLevelEvidenceStatus || 'missing',
              riskLevelEvidenceLabel: rule.riskLevelEvidenceLabel || 'R1-R5 待补',
              riskLevelEvidenceDetail: rule.riskLevelEvidenceDetail || '未取得销售平台或基金合同风险等级，不能用于适当性匹配。',
              executionAmountGate: rule.executionAmountGate || null,
              nextAction: Number(rule.missingCount || 0) > 0
                ? `补齐 ${(rule.missingItems || []).slice(0, 3).join('、')}`
                : '销售规则相对完整，研究复核实时状态',
            }
          : null)
      setSalesRuleGapCheckedCode(normalizedCode)
    } catch (error) {
      console.error('读取销售规则硬缺口失败:', error)
      setSalesRuleGap(null)
      setSalesRuleGapCheckedCode(null)
      setSalesRuleGapError(error instanceof Error ? error.message : '读取销售规则硬缺口失败')
    } finally {
      setSalesRuleGapLoading(false)
    }
  }, [fund?.name, fund?.totalAsset, fund?.type, investorPurchasePlan, simulationForm.lumpSumAmount, simulationForm.monthlyAmount])

  const fetchShareClassFunds = useCallback(async (target: Fund) => {
    const baseName = normalizeShareClassBaseName(target.name)
    const classType = inferShareClass(target.name)
    if (!target.windCode || !baseName || !classType) {
      setShareClassFunds([])
      setShareClassInfo(null)
      setShareClassError('当前基金名称未识别出 A/C/I/H 等份额类别；研究复核仍需核对销售平台份额列表。')
      return
    }

    setShareClassLoading(true)
    setShareClassError(null)
    try {
      const params = new URLSearchParams({
        page: '1',
        limit: '50',
        search: baseName,
        sortBy: 'name',
        sortOrder: 'asc',
      })
      const response = await fetch(`/api/funds?${params.toString()}`, { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.error || payload.detail || '读取同基金份额失败')
      }

      const siblings = ((payload.data || []) as ShareClassFund[])
        .filter((item) => normalizeShareClassBaseName(item.name) === baseName)
        .filter((item) => !target.type || !item.type || item.type === target.type)
      const currentInList = siblings.some((item) => item.windCode.toUpperCase() === target.windCode.toUpperCase())
      const funds = currentInList
        ? siblings
        : [{
          id: target.id,
          windCode: target.windCode,
          name: target.name,
          type: target.type,
          nav: target.nav,
          totalAsset: target.totalAsset,
          screeningScore: null,
          feeInfo: target.feeInfo,
        }, ...siblings]
      const shareClassCodes = Array.from(new Set(funds.map((item) => item.windCode.trim().toUpperCase()).filter(Boolean)))
      const [salesRulesPayload, salesRuleGapsPayload] = shareClassCodes.length
        ? await Promise.all([
            fetch(`/api/evidence-coverage/materials?codes=${encodeURIComponent(shareClassCodes.join(','))}`, { cache: 'no-store' })
              .then(async (salesRulesResponse) => {
                const salesRulesBody = await salesRulesResponse.json().catch(() => ({}))
                if (!salesRulesResponse.ok) {
                  throw new Error(salesRulesBody.error || salesRulesBody.detail || '读取份额销售规则失败')
                }
                return salesRulesBody
              }),
            fetch(`/api/evidence-coverage/materials/gaps?${new URLSearchParams({
              codes: shareClassCodes.join(','),
              limit: String(shareClassCodes.length),
              purchasePlan: investorPurchasePlan,
              plannedAmount: String(currentPlannedAmount()),
            }).toString()}`, { cache: 'no-store' })
              .then(async (salesRuleGapsResponse) => {
                const salesRuleGapsBody = await salesRuleGapsResponse.json().catch(() => ({}))
                if (!salesRuleGapsResponse.ok) {
                  throw new Error(salesRuleGapsBody.error || salesRuleGapsBody.detail || '读取份额销售规则金额门禁失败')
                }
                return salesRuleGapsBody
              }),
          ])
        : [{ rules: [] }, { rules: [] }]
      const salesRuleByCode = ((salesRulesPayload.rules || []) as Array<NonNullable<Fund['salesRule']> & { windCode?: string }>)
        .reduce((accumulator: Record<string, Fund['salesRule']>, rule) => {
          if (rule.windCode) accumulator[rule.windCode.toUpperCase()] = rule
          return accumulator
        }, {})
      const salesRuleGapSummaryByCode = ((salesRuleGapsPayload.rules || []) as Array<{
        windCode?: string
        missingItems?: string[]
        missingCount?: number
        executionAmountGate?: SalesRuleGapEvidence['executionAmountGate'] | null
      }>).reduce((accumulator: Record<string, { missingItems: string[]; missingCount: number; executionAmountGate: SalesRuleGapEvidence['executionAmountGate'] | null }>, rule) => {
        if (rule.windCode) {
          accumulator[rule.windCode.toUpperCase()] = {
            missingItems: rule.missingItems || [],
            missingCount: Number(rule.missingCount || 0),
            executionAmountGate: rule.executionAmountGate || null,
          }
        }
        return accumulator
      }, {})
      const fundsWithRules = funds.map((item) => {
        const normalizedCode = item.windCode.toUpperCase()
        const gapSummary = salesRuleGapSummaryByCode[normalizedCode]
        return {
          ...item,
          salesRule: salesRuleByCode[normalizedCode] || (normalizedCode === target.windCode.toUpperCase() ? target.salesRule : null),
          executionAmountGate: gapSummary?.executionAmountGate || null,
          salesRuleMissingItems: gapSummary?.missingItems || (salesRuleByCode[normalizedCode] ? [] : ['销售规则整条待补']),
          salesRuleMissingCount: gapSummary?.missingCount ?? (salesRuleByCode[normalizedCode] ? 0 : 1),
        }
      })

      const infoByCode = buildShareClassInfoByCode(fundsWithRules)
      setShareClassFunds(fundsWithRules)
      setShareClassInfo(infoByCode.get(target.windCode.toUpperCase()) || null)
    } catch (error) {
      console.error('读取同基金份额失败:', error)
      setShareClassFunds([])
      setShareClassInfo(null)
      setShareClassError(error instanceof Error ? error.message : '读取同基金份额失败')
    } finally {
      setShareClassLoading(false)
    }
  }, [investorPurchasePlan, simulationForm.lumpSumAmount, simulationForm.monthlyAmount])

  const fetchAlternativeSalesRuleGaps = useCallback(async (codes: string[]) => {
    const uniqueCodes = Array.from(new Set(codes.map((code) => code.trim().toUpperCase()).filter(Boolean)))
    if (!uniqueCodes.length) {
      setAlternativeSalesRuleGaps({})
      setAlternativeSalesRuleGapError(null)
      return
    }

    setAlternativeSalesRuleGapsLoading(true)
    setAlternativeSalesRuleGapError(null)
    try {
      const params = new URLSearchParams({
        codes: uniqueCodes.join(','),
        limit: String(uniqueCodes.length),
        purchasePlan: investorPurchasePlan,
      })
      const response = await fetch(`/api/evidence-coverage/materials/gaps?${params.toString()}`, { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.error || payload.detail || '读取替代候选销售规则缺口失败')
      }
      const gapMap = (payload.gaps || []).reduce((accumulator: Record<string, SalesRuleGapEvidence>, gap: SalesRuleGapEvidence) => {
        accumulator[gap.windCode.toUpperCase()] = gap
        return accumulator
      }, {})
      setAlternativeSalesRuleGaps(gapMap)
    } catch (error) {
      console.error('读取替代候选销售规则缺口失败:', error)
      setAlternativeSalesRuleGaps({})
      setAlternativeSalesRuleGapError(error instanceof Error ? error.message : '读取替代候选销售规则缺口失败')
    } finally {
      setAlternativeSalesRuleGapsLoading(false)
    }
  }, [investorPurchasePlan])

  const fetchAlternativeFunds = useCallback(async (target: Fund) => {
    if (!target.windCode) return
    setAlternativesLoading(true)
    setAlternativeSearchMeta(null)
    setAlternativeSalesRuleGaps({})
    setAlternativeSalesRuleGapError(null)
    try {
      const attempts = [
        {
          label: target.type ? `同类型 ${target.type} · 研究候选 · 证据B+` : '同类型待补 · 研究候选 · 证据B+',
          type: target.type || '',
          eligibleOnly: 'true',
          minEvidenceGrade: 'B',
          limit: '16',
        },
        {
          label: target.type ? `同类型 ${target.type} · 放宽证据到C` : '同类型待补 · 放宽证据到C',
          type: target.type || '',
          eligibleOnly: 'false',
          minEvidenceGrade: 'C',
          limit: '24',
        },
        {
          label: '全类型 · 研究候选 · 证据B+',
          type: '',
          eligibleOnly: 'true',
          minEvidenceGrade: 'B',
          limit: '24',
        },
      ]
      const attemptedLabels: string[] = []
      let selectedAlternatives: AlternativeFund[] = []
      let selectedPayload: { total?: number; source?: string } = {}
      let selectedLabel = ''

      for (const attempt of attempts) {
        attemptedLabels.push(attempt.label)
        const params = new URLSearchParams({
          profile: investorRiskProfile,
          horizon: investorHorizon,
          purchasePlan: investorPurchasePlan,
          lens: 'score',
          eligibleOnly: attempt.eligibleOnly,
          minEvidenceGrade: attempt.minEvidenceGrade,
          limit: attempt.limit,
        })
        if (attempt.type) params.set('type', attempt.type)
        const response = await fetch(`/api/market/research-candidates?${params.toString()}`)
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) continue

        const alternatives = ((payload.funds || []) as AlternativeFund[])
          .filter((item) => item.windCode !== target.windCode)
          .filter((item) => item.purchaseGate?.level !== 'blocked')
          .slice(0, 4)

        if (alternatives.length > 0) {
          selectedAlternatives = alternatives
          selectedPayload = payload
          selectedLabel = attempt.label
          break
        }
      }
      setAlternativeFunds(selectedAlternatives)
      await fetchAlternativeSalesRuleGaps(selectedAlternatives.map((item) => item.windCode))
      setAlternativeSearchMeta({
        note: selectedAlternatives.length
          ? `采用：${selectedLabel}；返回 ${selectedAlternatives.length} 只替代候选。`
          : '当前画像下未找到可比较替代候选；建议回到选基页放宽画像、证据等级或基金类型。',
        attempts: attemptedLabels,
        total: Number(selectedPayload.total || 0),
        source: selectedPayload.source || 'market-research-candidates',
      })
    } catch (error) {
      console.error('读取替代候选失败:', error)
      setAlternativeFunds([])
      setAlternativeSalesRuleGaps({})
      setAlternativeSearchMeta({
        note: '替代候选读取失败，需稍后重试或回到研究筛选页手动筛选。',
        attempts: [],
        total: 0,
        source: 'market-research-candidates',
      })
    } finally {
      setAlternativesLoading(false)
    }
  }, [fetchAlternativeSalesRuleGaps, investorHorizon, investorPurchasePlan, investorRiskProfile])

  const loadCandidatePoolContext = useCallback(async () => {
    try {
      setCandidatePoolLoading(true)
      const poolResponse = await fetch('/api/market/research-lists', { cache: 'no-store' })
      const poolPayload = await poolResponse.json().catch(() => ({}))
      if (!poolResponse.ok) {
        throw new Error(poolPayload.detail || poolPayload.error || '读取研究清单状态失败')
      }

      const poolId = poolPayload.pools?.[0]?.id as string | undefined
      setCandidatePoolId(poolId || '')
      if (!poolId) {
        setCandidatePoolMembers([])
        return
      }

      const membersResponse = await fetch(`/api/market/research-lists/${poolId}/members`, { cache: 'no-store' })
      const membersPayload = await membersResponse.json().catch(() => ({}))
      if (!membersResponse.ok) {
        throw new Error(membersPayload.detail || membersPayload.error || '读取研究清单成员失败')
      }
      setCandidatePoolMembers(membersPayload.members || [])
    } catch (error) {
      console.error('读取研究清单状态失败:', error)
      setCandidatePoolId('')
      setCandidatePoolMembers([])
    } finally {
      setCandidatePoolLoading(false)
    }
  }, [])

  const findCandidatePoolMember = (target: Fund) => candidatePoolMembers.find((member) =>
    (member.fund_wind_code && member.fund_wind_code.toUpperCase() === target.windCode.toUpperCase()) ||
    (member.fund_id && member.fund_id === target.id)
  ) || null

  const canEnterCandidatePool = (target: Fund) => {
    const normalizedCode = target.windCode.toUpperCase()
    const targetSalesRuleGapCount = salesRuleGapCheckedCode === normalizedCode ? salesRuleGap?.missingCount ?? 0 : null
    const reviewAlertReason = target.activeSalesRuleEvidenceAlert
      ? `复查队列仍有未解决销售规则/R1-R5事件：${target.activeSalesRuleEvidenceAlert.title || '销售规则/R1-R5证据待补'}`
      : ''
    const salesRuleGatePassed = !salesRuleGapLoading && !salesRuleGapError && targetSalesRuleGapCount === 0 && !reviewAlertReason
    const gate = buildDetailGate(target)
    const formalGate = buildFormalReportGate({
      detailGate: gate,
      salesRuleBlocked: !salesRuleGatePassed,
      salesRuleBlockReason: reviewAlertReason || (
        targetSalesRuleGapCount === null
          ? '销售规则硬缺口尚未完成扫描'
          : targetSalesRuleGapCount > 0
            ? `销售规则仍缺 ${targetSalesRuleGapCount} 项：${(salesRuleGap?.missingItems || []).slice(0, 5).join('、')}`
            : ''
      ),
    })
    return target.operationStatus?.status !== 'blocked' && gate.level !== 'blocked' && salesRuleGatePassed && !formalGate.blocked
  }

  const buildFormalReportGate = ({
    detailGate,
    salesRuleBlocked,
    salesRuleBlockReason,
  }: {
    detailGate: ReturnType<typeof buildDetailGate>
    salesRuleBlocked: boolean
    salesRuleBlockReason: string
  }) => {
    const reasons = [
      salesRuleBlocked ? salesRuleBlockReason : '',
      !purchaseSimulation ? '真实净值回放未完成，不能验证持有体验、回撤和压力测试' : '',
      purchaseSimulation && purchaseSimulation.monthlyExperience.months < investorHorizons[investorHorizon].minSampleMonths
        ? `${investorHorizons[investorHorizon].label}至少需要 ${investorHorizons[investorHorizon].minSampleMonths} 个月回放，当前 ${purchaseSimulation.monthlyExperience.months} 个月`
        : '',
      detailGate.evidenceGrade === 'D' ? '证据等级为 D，关键研究证据不足' : '',
      detailGate.level === 'blocked' ? '当前存在材料核验、风险预算或基础研究硬阻断，不能保存为正式研究复核报告' : '',
      detailGate.level === 'verify_first' ? '当前仍是“先补证再比较”，不能保存为正式研究复核报告' : '',
    ].filter(Boolean)
    return {
      blocked: reasons.length > 0,
      reasons,
      primaryReason: reasons[0] || '',
      summary: reasons.join('；'),
    }
  }

  const buildHoldingExperienceEvidence = () => {
    if (!purchaseSimulation) {
      return {
        label: '持有体验待回放',
        score: 0,
        sipFriendlyScore: 0,
        drawdownStress: null,
        sampleStatus: 'unknown',
      }
    }

    const lumpSumDrawdown = Math.abs(purchaseSimulation.lumpSum.maxDrawdown ?? 0)
    const sipDrawdown = Math.abs(purchaseSimulation.sip.maxAccountDrawdown ?? 0)
    const positiveRatio = purchaseSimulation.monthlyExperience.positiveRatio ?? 0
    const lumpSumReturn = purchaseSimulation.lumpSum.returnRate ?? 0
    const sipReturn = purchaseSimulation.sip.returnRate ?? 0
    const score = Math.round(Math.max(0, Math.min(100, 55 + positiveRatio * 25 + Math.max(lumpSumReturn, sipReturn) * 80 - Math.max(lumpSumDrawdown, sipDrawdown) * 120)))
    const sipFriendlyScore = Math.round(Math.max(0, Math.min(100, 55 + positiveRatio * 25 + sipReturn * 80 - sipDrawdown * 120)))
    const drawdownStress = investorPurchasePlan === 'sip' ? sipDrawdown : lumpSumDrawdown
    const label = score >= 75 ? '持有体验较稳' : score >= 60 ? '持有体验可观察' : score >= 45 ? '持有体验偏颠簸' : '持有体验压力较大'
    return {
      label,
      score,
      sipFriendlyScore,
      drawdownStress,
      sampleStatus: purchaseSimulation.period.observations >= 60 ? 'usable' : 'short',
    }
  }

  const buildHoldingExposureDecision = () => {
    if (!holdingEvidence || holdingEvidence.status !== 'available') {
      return {
        label: '持仓暴露待补',
        status: 'verify' as const,
        score: 35,
        topTenWeight: null as number | null,
        topIndustryWeight: null as number | null,
        topIndustry: '行业待补',
        primaryRisk: '缺少可信季报持仓，不能解释行业/个股暴露',
        nextAction: '补齐最新季报持仓后，再判断集中度和风格暴露是否支持研究复核结论',
        reasons: [
          holdingEvidence?.note || '未取得可验证持仓，暂不做行业/个股暴露判断。',
          `已检查季度：${holdingEvidence?.checkedQuarters?.join(' / ') || '待补'}`,
          `已拦截疑似样例季度：${holdingEvidence?.rejectedMockLikeQuarters?.length || 0}`,
        ],
        reverseTriggers: [
          '可信持仓补齐后，若前十大或单一行业集中度过高，结论会转为更谨慎。',
          '若持仓行业与基金名称、基准或研究画像明显不一致，需要重新做同类比较。',
        ],
      }
    }

    const topTenWeight = holdingEvidence.totalWeight ?? null
    const sortedIndustries = [...holdingEvidence.industryBuckets].sort((left, right) => right.weight - left.weight)
    const topIndustry = sortedIndustries[0] || null
    const topIndustryWeight = topIndustry?.weight ?? null
    const topStock = holdingEvidence.holdings.slice().sort((left, right) => (right.weight ?? 0) - (left.weight ?? 0))[0] || null
    const concentrationBudget = investorRiskProfile === 'conservative' ? 0.45 : investorRiskProfile === 'balanced' ? 0.6 : 0.75
    const industryBudget = investorRiskProfile === 'conservative' ? 0.3 : investorRiskProfile === 'balanced' ? 0.4 : 0.5
    const topTenRisk = topTenWeight !== null && topTenWeight > concentrationBudget
    const industryRisk = topIndustryWeight !== null && topIndustryWeight > industryBudget
    const score = Math.round(Math.max(0, Math.min(100,
      82
      - (topTenRisk ? 22 : topTenWeight !== null && topTenWeight > concentrationBudget * 0.8 ? 10 : 0)
      - (industryRisk ? 18 : topIndustryWeight !== null && topIndustryWeight > industryBudget * 0.85 ? 8 : 0)
      - (holdingEvidence.holdings.length < 10 ? 10 : 0)
      - (holdingEvidence.industryBuckets.length < 3 ? 8 : 0),
    )))
    const status = topTenRisk || industryRisk ? 'verify' as const : score >= 72 ? 'done' as const : 'verify' as const
    const label = topTenRisk || industryRisk
      ? '暴露集中，先解释风险来源'
      : score >= 72
        ? '持仓暴露可用于研究判断'
        : '持仓暴露可观察'
    const primaryRisk = [
      topTenRisk ? `前十大权重 ${formatPercent(topTenWeight)} 超过${investorRiskProfiles[investorRiskProfile].label}集中度预算 ${formatPercent(concentrationBudget)}` : '',
      industryRisk ? `${topIndustry?.industry || '第一行业'}权重 ${formatPercent(topIndustryWeight)} 超过行业预算 ${formatPercent(industryBudget)}` : '',
    ].filter(Boolean).join('；') || '未发现超出当前画像预算的集中度信号'

    return {
      label,
      status,
      score,
      topTenWeight,
      topIndustryWeight,
      topIndustry: topIndustry?.industry || '行业待补',
      primaryRisk,
      nextAction: topTenRisk || industryRisk
        ? '先解释重仓行业/个股风险，再进入研究清单、横向比较或研究复核报告'
        : '复核最新季报是否延续当前暴露，再与同类基金横向比较',
      reasons: [
        `持仓季度 ${holdingEvidence.quarter || '待补'}，前十大合计 ${formatPercent(topTenWeight)}`,
        `第一行业 ${topIndustry?.industry || '待补'} ${formatPercent(topIndustryWeight)}，行业桶 ${holdingEvidence.industryBuckets.length} 个`,
        topStock ? `第一重仓 ${topStock.stockName || topStock.stockCode || '名称待补'} ${formatPercent(topStock.weight)}` : '第一重仓待补',
        `可信过滤来源：${holdingEvidence.source}`,
      ],
      reverseTriggers: [
        topTenRisk || industryRisk
          ? '若后续季报显示集中度下降且同类回撤不劣于替代候选，可重新提高研究优先级。'
          : '若后续季报显示前十大或第一行业集中度明显升高，当前结论会转为更谨慎。',
        '若重仓行业与基金基准、名称或同类分组不一致，需要重新确认同类比较口径。',
      ],
    }
  }

  const addToCandidatePool = async () => {
    if (!fund) return
    const gate = buildDetailGate(fund)
    const normalizedCode = fund.windCode.toUpperCase()
    const targetSalesRuleGapCount = salesRuleGapCheckedCode === normalizedCode ? salesRuleGap?.missingCount ?? 0 : null
    if (salesRuleGapLoading || salesRuleGapError || targetSalesRuleGapCount !== 0) {
      const reason = salesRuleGapError
        ? salesRuleGapError
        : targetSalesRuleGapCount === null
          ? '销售规则硬缺口尚未完成扫描'
          : `销售规则仍缺 ${targetSalesRuleGapCount} 项：${(salesRuleGap?.missingItems || []).slice(0, 5).join('、')}`
      setErrorMessage(`${fund.name} ${reason}，补齐前不能加入研究清单。`)
      return
    }
    if (!canEnterCandidatePool(fund)) {
      const reviewAlertReason = fund.activeSalesRuleEvidenceAlert
        ? `复查队列仍有未解决销售规则/R1-R5事件：${fund.activeSalesRuleEvidenceAlert.title || '销售规则/R1-R5证据待补'}`
        : ''
      const formalGate = buildFormalReportGate({
        detailGate: gate,
        salesRuleBlocked: Boolean(reviewAlertReason),
        salesRuleBlockReason: reviewAlertReason,
      })
      setErrorMessage(`${fund.name} ${formalGate.summary || '未通过研究门禁'}，不能加入研究清单。`)
      return
    }
    const existingMember = findCandidatePoolMember(fund)
    if (existingMember) {
      setBannerMessage(`${fund.name} 已在研究清单（${poolStatusLabels[existingMember.status] || existingMember.status}），无需重复加入。`)
      return
    }
    const reason = `基金详情研究复核诊断：${gate.profileLabel} · ${gate.horizonLabel} · ${gate.purchasePlanLabel}；${gate.label}；证据 ${gate.evidenceGrade}`

    try {
      setAddingToPool(true)
      setBannerMessage(null)
      setErrorMessage(null)
      let poolId: string | undefined = candidatePoolId || undefined

      if (!poolId) {
        const poolResponse = await fetch('/api/market/research-lists')
        const poolPayload = await poolResponse.json().catch(() => ({}))
        if (!poolResponse.ok) {
          throw new Error(poolPayload.detail || poolPayload.error || '读取默认研究清单失败')
        }
        poolId = poolPayload.pools?.[0]?.id as string | undefined

        if (!poolId) {
          const createResponse = await fetch('/api/market/research-lists', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: '默认研究清单',
              description: '由基金详情页自动创建',
              createdBy: 'fund-detail-ui',
              isDefault: true,
            }),
          })
          const createdPayload = await createResponse.json().catch(() => ({}))
          if (!createResponse.ok || !createdPayload.id) {
            throw new Error(createdPayload.detail || createdPayload.error || '创建默认研究清单失败')
          }
          poolId = createdPayload.id
        }
        setCandidatePoolId(poolId || '')
      }

      const response = await fetch(`/api/market/research-lists/${poolId}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fundId: fund.id,
          status: 'candidate',
          reason,
          latestConclusion: gate.level === 'verify_first'
            ? '先补销售规则、适当性证据和持有体验证据后再进入研究复核。'
            : '可进入研究清单继续做研究复核一页纸、同类对比和销售规则复核。',
          evidence: {
            source: 'fund-detail',
            addedAt: new Date().toISOString(),
            investorContext: {
              profile: investorRiskProfile,
              profileLabel: gate.profileLabel,
              horizon: investorHorizon,
              horizonLabel: gate.horizonLabel,
              purchasePlan: investorPurchasePlan,
              purchasePlanLabel: gate.purchasePlanLabel,
              plannedAmount: currentPlannedAmount(),
              plannedAmountLabel: investorPurchasePlan === 'sip'
                ? `计划月扣款 ${currentPlannedAmount()} 元`
                : `计划配置 ${currentPlannedAmount()} 元`,
              maxDrawdownTolerance: gate.riskBudget,
            },
            purchaseGate: {
              level: gate.level,
              label: gate.label,
              evidenceGrade: gate.evidenceGrade,
              hardBlocks: gate.hardBlocks,
              cautionFlags: gate.cautionFlags,
              mustVerifyBeforeBuy: gate.mustVerifyBeforeBuy,
              suitabilityNotes: gate.suitabilityNotes,
            },
            formalReportGate: {
              blocked: false,
              reasons: [],
              checkedAt: new Date().toISOString(),
              source: 'fund-detail-ui',
              requiredFor: ['candidate', 'core'],
              replay: purchaseSimulation ? {
                months: purchaseSimulation.monthlyExperience.months,
                observations: purchaseSimulation.period.observations,
                startDate: purchaseSimulation.period.startDate,
                endDate: purchaseSimulation.period.endDate,
              } : null,
            },
            buyEvidence: fund.buyEvidence
              ? {
                  completenessScore: fund.buyEvidence.completenessScore,
                  completenessLevel: fund.buyEvidence.completenessLevel,
                  requiredMissingCount: fund.buyEvidence.requiredMissingCount,
                  plannedAmount: fund.buyEvidence.plannedAmount ?? currentPlannedAmount(),
                  executionAmountGate: fund.buyEvidence.executionAmountGate ?? null,
                  conclusion: fund.buyEvidence.conclusion,
                }
              : null,
            salesRuleGap: salesRuleGapCheckedCode === fund.windCode.toUpperCase()
              ? {
                  checkedCode: salesRuleGapCheckedCode,
                  missingCount: salesRuleGap?.missingCount ?? 0,
                  missingItems: salesRuleGap?.missingItems || [],
                  priority: salesRuleGap?.priority || null,
                  nextAction: salesRuleGap?.nextAction || '销售规则相对完整，研究复核实时状态',
                  ruleUpdatedAt: salesRuleGap?.ruleUpdatedAt || null,
                  ruleSourceUpdatedAt: salesRuleGap?.ruleSourceUpdatedAt || null,
                  riskLevel: salesRuleGap?.riskLevel || null,
                  riskLevelSourceBacked: Boolean(salesRuleGap?.riskLevelSourceBacked),
                  riskLevelEvidenceStatus: salesRuleGap?.riskLevelEvidenceStatus || 'missing',
                  riskLevelEvidenceLabel: salesRuleGap?.riskLevelEvidenceLabel || 'R1-R5 待补',
                  riskLevelEvidenceDetail: salesRuleGap?.riskLevelEvidenceDetail || '未取得销售平台或基金合同风险等级，不能用于适当性匹配。',
                  executionAmountGate: salesRuleGap?.executionAmountGate || null,
                }
              : {
                  checkedCode: null,
                  missingCount: null,
                  missingItems: [],
                  priority: null,
                  nextAction: '销售规则硬缺口尚未扫描',
                  ruleUpdatedAt: null,
                  ruleSourceUpdatedAt: null,
                },
            holdingExperience: buildHoldingExperienceEvidence(),
            holdingExposure: buildHoldingExposureDecision(),
          },
          createdBy: 'fund-detail-ui',
        }),
      })

      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail || payload.error || '加入研究清单失败')
      }

      setBannerMessage(`已将 ${fund.name} 加入研究清单，可前往研究清单继续维护。`)
      await loadCandidatePoolContext()
    } catch (error) {
      console.error('加入研究清单失败:', error)
      setErrorMessage(error instanceof Error ? error.message : '加入研究清单失败')
    } finally {
      setAddingToPool(false)
    }
  }

  const saveSalesRule = async () => {
    if (!fund?.windCode) return
    const redemptionFeeRate = asNumber(salesRuleForm.redemptionFeeRate)
    const redemptionHoldingDays = asNumber(salesRuleForm.redemptionHoldingDays)
    const redemptionFeeRules = redemptionFeeRate === null
      ? []
      : [{
          holdingDays: redemptionHoldingDays,
          feeRate: redemptionFeeRate,
          label: redemptionHoldingDays === null ? `赎回费 ${redemptionFeeRate.toFixed(2)}%` : `持有满 ${redemptionHoldingDays} 天赎回费 ${redemptionFeeRate.toFixed(2)}%`,
        }]

    try {
      setSalesRuleSaving(true)
      setBannerMessage(null)
      setErrorMessage(null)
      const response = await fetch(`/api/funds/${encodeURIComponent(fund.windCode)}/materials`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform: 'manual',
          purchaseStatus: salesRuleForm.purchaseStatus,
          purchaseStatusLabel: purchaseStatusLabelMap[salesRuleForm.purchaseStatus],
          minPurchaseAmount: asNumber(salesRuleForm.minPurchaseAmount),
          minSipAmount: asNumber(salesRuleForm.minSipAmount),
          dailyLimitAmount: asNumber(salesRuleForm.dailyLimitAmount),
          purchaseFeeRate: asNumber(salesRuleForm.purchaseFeeRate),
          redemptionFeeRules,
          salesServiceFeeRate: asNumber(salesRuleForm.salesServiceFeeRate),
          riskLevel: salesRuleForm.riskLevel || null,
          supportsSip: salesRuleForm.supportsSip === '' ? null : salesRuleForm.supportsSip === 'true',
          sourceUpdatedAt: salesRuleForm.sourceUpdatedAt || new Date().toISOString().slice(0, 10),
          sourceUrl: salesRuleForm.sourceUrl || null,
          notes: salesRuleForm.notes || null,
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.error || payload.detail || '保存销售规则失败')
      }
      setBannerMessage('销售平台规则已保存，研究复核一页纸和申赎证据已刷新。')
      await fetchFundDetail()
      await fetchSalesRuleGap(fund.windCode)
    } catch (error) {
      console.error('保存销售规则失败:', error)
      setErrorMessage(error instanceof Error ? error.message : '保存销售规则失败')
    } finally {
      setSalesRuleSaving(false)
    }
  }

  const salesRuleGapCanUseTushareFoundation = Boolean(
    fund?.windCode
      && salesRuleGapCheckedCode === fund.windCode.toUpperCase()
      && salesRuleGap?.missingItems.some((item) =>
        item.includes('销售规则整条待补')
          || item.includes('来源日期')
          || (item.includes('申购状态') && !salesRuleGap.ruleSourceUpdatedAt),
      ),
  )

  const importTushareFoundationForFund = async () => {
    if (!fund?.windCode) return
    if (!salesRuleGapCanUseTushareFoundation) {
      setBannerMessage(null)
      setErrorMessage('当前基金没有可由 Tushare fund_basic 先补的基础申赎状态缺口。')
      return
    }

    try {
      setFoundationHydrating(true)
      setBannerMessage(null)
      setErrorMessage(null)
      const response = await fetch('/api/evidence-coverage/materials/tushare-foundation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codes: [fund.windCode], purchasePlan: investorPurchasePlan, plannedAmount: currentPlannedAmount() }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.error || payload.detail || '导入 Tushare 基础申赎状态失败')
      }
      await fetchFundDetail()
      await fetchSalesRuleGap(fund.windCode)
      setBannerMessage(`已从 Tushare fund_basic 导入 ${fund.name} 的基础申赎状态；${foundationManualFields}仍需销售平台核验。`)
      if (payload.failedCount) {
        const failedPreview = Array.isArray(payload.failed)
          ? payload.failed.slice(0, 2).map((item: { windCode?: string; error?: string }) => `${item.windCode || '未知基金'}：${item.error || '原因待查'}`).join('；')
          : ''
        setErrorMessage(`基础状态导入存在失败${failedPreview ? `：${failedPreview}` : '。'}`)
      }
    } catch (error) {
      console.error('导入单基金 Tushare 基础状态失败:', error)
      setErrorMessage(error instanceof Error ? error.message : '导入 Tushare 基础申赎状态失败')
    } finally {
      setFoundationHydrating(false)
    }
  }

  useEffect(() => {
    fetchFundDetailRef.current = fetchFundDetail
    fetchPurchaseSimulationRef.current = (code: string) => fetchPurchaseSimulation(code)
    fetchHoldingEvidenceRef.current = fetchHoldingEvidence
    fetchShareClassFundsRef.current = fetchShareClassFunds
  })

  useEffect(() => {
    if (!initialFund) {
      const timeoutId = window.setTimeout(() => {
        void fetchFundDetailRef.current()
      }, 0)
      return () => window.clearTimeout(timeoutId)
    }
  }, [fundId, initialFund])

  useEffect(() => {
    if (!fund || (fund.buyEvidence?.purchasePlan === investorPurchasePlan && Number(fund.buyEvidence?.plannedAmount || 0) === currentPlannedAmount())) return
    const timeoutId = window.setTimeout(() => {
      void fetchFundDetailRef.current()
    }, 0)
    return () => window.clearTimeout(timeoutId)
  }, [currentPlannedAmount, fund, investorPurchasePlan])

  useEffect(() => {
    if (fund?.windCode) {
      const code = fund.windCode
      const timeoutId = window.setTimeout(() => {
        void fetchPurchaseSimulationRef.current(code)
        void fetchHoldingEvidenceRef.current(code)
        void fetchSalesRuleGap(code)
        void fetchShareClassFundsRef.current(fund)
      }, 0)
      return () => window.clearTimeout(timeoutId)
    }
  }, [fetchSalesRuleGap, fund])

  useEffect(() => {
    if (fund?.windCode) {
      const timeoutId = window.setTimeout(() => {
        void fetchAlternativeFunds(fund)
      }, 0)
      return () => window.clearTimeout(timeoutId)
    }
  }, [fetchAlternativeFunds, fund])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadCandidatePoolContext()
    }, 0)
    return () => window.clearTimeout(timeoutId)
  }, [loadCandidatePoolContext])

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-gray-500">加载中...</div>
      </div>
    )
  }

  if (!fund) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center">
        <div className="mb-4 text-gray-500">{errorMessage || '基金不存在'}</div>
        <div className="flex gap-3">
          <Link href={sourceReturnHref} className="text-blue-600 hover:text-blue-800">返回列表</Link>
          <button onClick={() => void fetchFundDetail()} className="text-gray-700 hover:text-gray-900">重试加载</button>
        </div>
      </div>
    )
  }

  const detailGate = buildDetailGate(fund)
  const salesRuleEvidenceCopy = salesRuleEvidenceCopyForPlan(investorPurchasePlan)
  const foundationManualFields = salesRuleFoundationManualFieldsForPlan(investorPurchasePlan)
  const candidatePoolMember = findCandidatePoolMember(fund)
  const simulationPurchaseFeeRate = asNumber(fund.salesRule?.purchaseFeeRate)
  const simulationFeeEstimate = purchaseSimulation
    ? {
        lumpSumPurchaseFee: simulationPurchaseFeeRate === null ? null : purchaseSimulation.lumpSum.totalInvested * simulationPurchaseFeeRate / 100,
        sipPurchaseFee: simulationPurchaseFeeRate === null ? null : purchaseSimulation.sip.totalInvested * simulationPurchaseFeeRate / 100,
      }
    : null
  const lumpSumEstimatedCost = simulationFeeEstimate
    ? (simulationFeeEstimate.lumpSumPurchaseFee ?? 0)
    : null
  const sipEstimatedCost = simulationFeeEstimate
    ? (simulationFeeEstimate.sipPurchaseFee ?? 0)
    : null
  const lumpSumNetProfit = purchaseSimulation && lumpSumEstimatedCost !== null
    ? purchaseSimulation.lumpSum.profit - lumpSumEstimatedCost
    : null
  const sipNetProfit = purchaseSimulation && sipEstimatedCost !== null
    ? purchaseSimulation.sip.profit - sipEstimatedCost
    : null
  const lumpSumNetReturn = purchaseSimulation && lumpSumNetProfit !== null && purchaseSimulation.lumpSum.totalInvested > 0
    ? lumpSumNetProfit / purchaseSimulation.lumpSum.totalInvested
    : null
  const sipNetReturn = purchaseSimulation && sipNetProfit !== null && purchaseSimulation.sip.totalInvested > 0
    ? sipNetProfit / purchaseSimulation.sip.totalInvested
    : null
  const feeAdjusted = purchaseSimulation?.feeAdjusted || null
  const feeAdjustedCoverageLabel = feeAdjusted?.coverage === 'full'
    ? '费用证据完整'
    : feeAdjusted?.coverage === 'partial'
      ? '费用证据部分覆盖'
      : '费用证据待补'
  const feeAdjustedMissingText = feeAdjusted?.missingItems?.length
    ? `缺：${feeAdjusted.missingItems.join('、')}`
    : '申购费与赎回费规则均已用于本次回放'
  const lumpSumFeeAdjustedReturn = feeAdjusted?.lumpSum?.returnRate ?? lumpSumNetReturn
  const sipFeeAdjustedReturn = feeAdjusted?.sip?.returnRate ?? sipNetReturn
  const lumpSumFeeAdjustedCost = feeAdjusted?.lumpSum?.totalFee ?? lumpSumEstimatedCost
  const sipFeeAdjustedCost = feeAdjusted?.sip?.totalFee ?? sipEstimatedCost
  const lumpSumFeeAdjustedEndingValue = feeAdjusted?.lumpSum?.endingValue ?? null
  const sipFeeAdjustedEndingValue = feeAdjusted?.sip?.endingValue ?? null
  const lumpSumFeeAdjustedProfit = feeAdjusted?.lumpSum?.profit ?? null
  const sipFeeAdjustedProfit = feeAdjusted?.sip?.profit ?? null
  const lumpSumRedemptionRule = feeAdjusted?.lumpSum?.redemptionRule ?? null
  const lumpSumRedemptionLadder = feeAdjusted?.lumpSum?.redemptionFeeLadder || []
  const sipRedemptionRuleBuckets = feeAdjusted?.sip?.redemptionRuleBuckets || []
  const redemptionRuleSummary = fund.salesRule?.redemptionFeeRules?.length
    ? fund.salesRule.redemptionFeeRules
      .slice()
      .sort((left, right) => (left.holdingDays ?? Number.MAX_SAFE_INTEGER) - (right.holdingDays ?? Number.MAX_SAFE_INTEGER))
      .slice(0, 3)
      .map((rule) => `${rule.label || (rule.holdingDays === null ? '开放持有期' : `${rule.holdingDays}天节点`)}：${formatPercent(rule.feeRate)}`)
      .join('；')
    : ''
  const managerSummary = fund.managers?.length
    ? fund.managers.map((manager) => {
      const tenure = manager.managementYears == null ? '任期待核' : `${manager.managementYears.toFixed(1)}年`
      const since = manager.beginDate ? `任职起点 ${manager.beginDate}` : '任职起点待补'
      return `${manager.name || manager.managerId || '姓名待补'}（${tenure}，${since}）`
    }).join('；')
    : '经理明细待同步'
  const buyEvidence = fund.buyEvidence
  const requiredMissingItems = (buyEvidence?.missingItems || []).filter((item) => item.requiredBeforeBuy)
  const salesRuleGapReady = salesRuleGapCheckedCode === fund.windCode.toUpperCase()
  const salesRuleHardGapCount = salesRuleGapReady ? salesRuleGap?.missingCount ?? 0 : null
  const salesRuleGapMissingItems = salesRuleGapReady ? salesRuleGap?.missingItems || [] : []
  const riskLevelEvidenceLabel = salesRuleGapReady ? salesRuleGap?.riskLevelEvidenceLabel : null
  const riskLevelEvidenceDetail = salesRuleGapReady ? salesRuleGap?.riskLevelEvidenceDetail : null
  const riskLevelSourceBacked = salesRuleGapReady ? Boolean(salesRuleGap?.riskLevelSourceBacked) : false
  const executionAmountGate = salesRuleGapReady ? salesRuleGap?.executionAmountGate || null : null
  const executionAmountBlocked = executionAmountGate?.status === 'blocked'
  const activeSalesRuleEvidenceAlert = fund.activeSalesRuleEvidenceAlert || null
  const activeSalesRuleEvidenceBlocked = Boolean(activeSalesRuleEvidenceAlert)
  const activeSalesRuleEvidenceReason = activeSalesRuleEvidenceAlert
    ? `复查队列仍有未解决销售规则/R1-R5事件：${activeSalesRuleEvidenceAlert.title || '销售规则/R1-R5证据待补'}${activeSalesRuleEvidenceAlert.message ? `（${activeSalesRuleEvidenceAlert.message}）` : ''}`
    : ''
  const primarySalesRuleBlocked = salesRuleHardGapCount !== null && salesRuleHardGapCount > 0
  const salesRuleScanPending = salesRuleGapLoading || salesRuleHardGapCount === null
  const reportSalesRuleBlocked = activeSalesRuleEvidenceBlocked || salesRuleScanPending || primarySalesRuleBlocked || executionAmountBlocked
  const reportBlockReason = activeSalesRuleEvidenceReason || (
    salesRuleScanPending
      ? '销售规则硬缺口尚未完成扫描'
      : primarySalesRuleBlocked
        ? `销售规则仍缺 ${salesRuleHardGapCount} 项：${salesRuleGapMissingItems.slice(0, 5).join('、')}`
        : executionAmountBlocked
          ? executionAmountGate?.detail || '计划金额未通过销售平台起购/定投起点/限购门禁'
          : ''
  )
  const formalReportGate = buildFormalReportGate({
    detailGate,
    salesRuleBlocked: reportSalesRuleBlocked,
    salesRuleBlockReason: reportBlockReason,
  })
  const formalReportBlockReasons = formalReportGate.reasons
  const formalReportBlocked = formalReportGate.blocked
  const formalReportBlockReason = formalReportGate.primaryReason
  const formalReportBlockSummary = formalReportGate.summary
  const candidatePoolBlockReason = formalReportBlocked
    ? `${formalReportBlockSummary}；补齐前不能加入研究清单。`
    : reportSalesRuleBlocked
    ? `${reportBlockReason}；补齐前不能加入研究清单。`
    : detailGate.level === 'blocked'
      ? `${fund.name} 未通过适当性或基础研究门禁。`
      : ''
  const alternativeReadyFunds = alternativeFunds.filter((item) => {
    const gap = alternativeSalesRuleGaps[item.windCode.toUpperCase()]
    return !alternativeSalesRuleGapError && !alternativeSalesRuleGapsLoading && (!gap || gap.missingCount === 0)
  })
  const alternativeGapFunds = alternativeFunds.filter((item) => {
    const gap = alternativeSalesRuleGaps[item.windCode.toUpperCase()]
    return Boolean(gap && gap.missingCount > 0)
  })
  const alternativeGapCodes = alternativeGapFunds.map((item) => item.windCode)
  const detailContextQuery = new URLSearchParams({
    profile: investorRiskProfile,
    horizon: investorHorizon,
    purchasePlan: investorPurchasePlan,
    plannedAmount: String(currentPlannedAmount()),
    months: simulationForm.months || defaultSimulationForm.months,
    lumpSumAmount: simulationForm.lumpSumAmount || defaultSimulationForm.lumpSumAmount,
    monthlyAmount: simulationForm.monthlyAmount || defaultSimulationForm.monthlyAmount,
  }).toString()
  const detailReturnHref = `/funds/${encodeURIComponent(fund.id || fund.windCode)}?${detailContextQuery}`
  const salesRulesHrefForCodes = (codes: string[]) => {
    const normalizedCodes = Array.from(new Set(codes.map((code) => code.trim().toUpperCase()).filter(Boolean)))
    const params = new URLSearchParams({
      purchasePlan: investorPurchasePlan,
      plannedAmount: String(currentPlannedAmount()),
    })
    if (normalizedCodes.length) params.set('codes', normalizedCodes.join(','))
    return appendReturnTo(materialEvidenceHref(params), detailReturnHref)
  }
  const buyBeforeActionHrefForDetail = (href: string) => {
    const [path, query = ''] = canonicalResearchHref(href).split('?')
    const params = new URLSearchParams(query)
    params.set('purchasePlan', investorPurchasePlan)
    params.set('plannedAmount', String(currentPlannedAmount()))
    params.set('profile', investorRiskProfile)
    params.set('horizon', investorHorizon)
    params.set('returnTo', detailReturnHref)
    if (path === '/reports') return detailReturnHref
    return `${path}?${params.toString()}`
  }
  const salesRulesHrefForFund = (code = fund.windCode) => salesRulesHrefForCodes([code])
  const riskLevelSourceAuditHref = appendReturnTo(
    materialEvidenceHref(new URLSearchParams({
      scope: 'market',
      focus: 'risk_level',
      queueMode: 'candidate_missing_risk',
      codes: fund.windCode.trim().toUpperCase(),
      purchasePlan: investorPurchasePlan,
      plannedAmount: String(currentPlannedAmount()),
    })),
    detailReturnHref,
  )
  const redemptionRuleBackfillHref = appendReturnTo(
    materialEvidenceHref(new URLSearchParams({
      scope: 'market',
      focus: 'redemption',
      codes: fund.windCode.trim().toUpperCase(),
      purchasePlan: investorPurchasePlan,
      plannedAmount: String(currentPlannedAmount()),
    })),
    detailReturnHref,
  )
  const alternativeCompareCodes = [
    fund.windCode,
    ...alternativeReadyFunds.slice(0, 3).map((item) => item.windCode),
  ].filter(Boolean)
  const alternativeComparisonHref = !reportSalesRuleBlocked && alternativeCompareCodes.length >= 2
    ? `/analysis/comparison?codes=${encodeURIComponent(alternativeCompareCodes.join(','))}&profile=${investorRiskProfile}&horizon=${investorHorizon}&purchasePlan=${investorPurchasePlan}&plannedAmount=${encodeURIComponent(String(currentPlannedAmount()))}&${investorPurchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount'}=${encodeURIComponent(String(currentPlannedAmount()))}&autoReplay=1`
    : ''
  const shareClassCompareCodes = shareClassInfo
    ? Array.from(new Set([fund.windCode, ...shareClassInfo.siblingCodes].filter(Boolean))).slice(0, 6)
    : []
  const shareClassComparisonHref = shareClassCompareCodes.length >= 2
    ? `/analysis/comparison?codes=${encodeURIComponent(shareClassCompareCodes.join(','))}&profile=${investorRiskProfile}&horizon=${investorHorizon}&purchasePlan=${investorPurchasePlan}&plannedAmount=${encodeURIComponent(String(currentPlannedAmount()))}&${investorPurchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount'}=${encodeURIComponent(String(currentPlannedAmount()))}&autoReplay=1`
    : ''
  const shareClassRows = shareClassFunds
    .filter((item) => shareClassInfo ? [fund.windCode, ...shareClassInfo.siblingCodes].includes(item.windCode) : item.windCode === fund.windCode)
    .sort((left, right) => {
      const gateRank = (item: ShareClassFund) => {
        if (item.executionAmountGate?.status === 'pass') return 0
        if (item.executionAmountGate?.status === 'unknown' || !item.executionAmountGate) return 1
        return 2
      }
      const leftGateRank = gateRank(left)
      const rightGateRank = gateRank(right)
      if (leftGateRank !== rightGateRank) return leftGateRank - rightGateRank
      const leftCost = shareClassCurrentSalesRuleCost(left).knownCost
      const rightCost = shareClassCurrentSalesRuleCost(right).knownCost
      if (leftCost !== rightCost) return (leftCost ?? 999999) - (rightCost ?? 999999)
      const leftFee = totalFee(left)
      const rightFee = totalFee(right)
      if (leftFee !== rightFee) return (leftFee ?? 99) - (rightFee ?? 99)
      return left.windCode.localeCompare(right.windCode)
    })
  const currentShareClass = inferShareClass(fund.name) || '待识别'
  const bestCostShareClass = shareClassRows[0] || null
  const shareClassPurchaseAdvice = (() => {
    if (!shareClassRows.length) {
      return {
        title: '份额选择待补证',
        recommendedCode: '',
        recommendedName: '',
        recommendedClass: '',
        confidence: 'low' as const,
        reasons: ['本地暂未形成同基金多份额样本，需先核对销售平台 A/C/I/H 份额列表。'],
        warnings: ['不能只看当前份额收益或名称后缀做研究决定。'],
      }
    }

    const rows = shareClassRows.map((item) => ({
      fund: item,
      classType: inferShareClass(item.name) || '未知',
      fee: totalFee(item),
      cost: shareClassCurrentSalesRuleCost(item),
    }))
    const executableRows = rows.filter((item) => item.fund.executionAmountGate?.status !== 'blocked')
    const knownCostRows = executableRows.filter((item) => item.cost.knownCost !== null)
    const lowestCostRow = knownCostRows.slice().sort((left, right) => (left.cost.knownCost ?? 999999) - (right.cost.knownCost ?? 999999))[0] || rows[0]
    const classPriority = investorHorizon === 'lt1y' || investorPurchasePlan === 'sip'
      ? ['C', 'A', 'I', 'H', '未知']
      : ['A', 'I', 'C', 'H', '未知']
    const classMatchedRow = rows
      .slice()
      .sort((left, right) => {
        const leftRank = classPriority.includes(left.classType) ? classPriority.indexOf(left.classType) : classPriority.length
        const rightRank = classPriority.includes(right.classType) ? classPriority.indexOf(right.classType) : classPriority.length
        if (leftRank !== rightRank) return leftRank - rightRank
        if (left.cost.knownCost !== right.cost.knownCost) return (left.cost.knownCost ?? 999999) - (right.cost.knownCost ?? 999999)
        return (left.fee ?? 99) - (right.fee ?? 99)
      })[0]
    const recommended = knownCostRows.length ? lowestCostRow : classMatchedRow
    const costMissingCount = rows.reduce((sum, item) => sum + item.cost.missing.length, 0)
    const blockedAmountRows = rows.filter((item) => item.fund.executionAmountGate?.status === 'blocked')
    const unknownAmountRows = rows.filter((item) => item.fund.executionAmountGate?.status === 'unknown' || !item.fund.executionAmountGate)
    const isCurrentRecommended = recommended?.fund.windCode.toUpperCase() === fund.windCode.toUpperCase()
    const reasons = [
      investorHorizon === 'lt1y'
        ? '当前持有期为 1 年以内，优先避免申购/赎回和销售服务费造成的短持成本误判。'
        : investorHorizon === 'gt3y'
          ? '当前持有期为 3 年以上，长期总费率和申购费折扣更关键。'
          : '当前持有期为 1-3 年，需要同时比较申购费、销售服务费、赎回费和管理/托管费。',
      investorPurchasePlan === 'sip'
        ? '当前研究方式假设为定投，需要重点核对定投起点、定投费率和 C 类销售服务费。'
        : '当前研究方式假设为一次性配置假设，需要重点核对申购费折扣和赎回持有期。',
      knownCostRows.length
        ? `按计划金额 ${currentPlannedAmount().toLocaleString('zh-CN')} 元估算，${recommended.classType}类 ${recommended.fund.windCode} 当前已知一年成本较低（${formatMoney(recommended.cost.knownCost)}）。`
        : `本地费率证据不足，暂按 ${recommended.classType} 类份额特征作为核查优先级。`,
      isCurrentRecommended
        ? '当前打开的份额暂列推荐核查对象。'
        : `当前打开的是 ${currentShareClass} 类，建议优先核查 ${recommended.classType} 类 ${recommended.fund.windCode} 是否更适合。`,
    ]
    const warnings = [
      costMissingCount > 0 ? `仍有 ${costMissingCount} 项份额成本证据待补，结论只能作为核查顺序。` : '',
      blockedAmountRows.length ? `${blockedAmountRows.length} 个份额未通过当前计划金额门禁，不能作为正式推荐。` : '',
      unknownAmountRows.length ? `${unknownAmountRows.length} 个份额金额门禁待补，需先补起购/定投/限购。` : '',
      `正式选择前仍必须补齐${salesRuleEvidenceCopy.formalFields}。`,
      shareClassInfo ? '同基金多份额必须先完成份额成本比较，再进入跨基金横评或研究清单。' : '',
    ].filter(Boolean)

    return {
      title: knownCostRows.length ? '暂定低成本核查对象' : '暂定份额核查顺序',
      recommendedCode: recommended?.fund.windCode || '',
      recommendedName: recommended?.fund.name || '',
      recommendedClass: recommended?.classType || '',
      confidence: costMissingCount === 0 && shareClassInfo ? 'medium' as const : 'low' as const,
      reasons,
      warnings,
    }
  })()
  const shareClassDecisionLabel = shareClassLoading
    ? '正在识别份额'
    : shareClassInfo
      ? `同基金 ${shareClassInfo.siblingCount} 个份额`
      : '份额待核'
  const shareClassDecisionDetail = shareClassInfo
    ? shareClassInfo.hint
    : shareClassError || '当前本地样本未形成同基金多份额比较，研究复核仍需在销售平台核对 A/C/I/H 等份额列表、费率和持有期。'
  const salesRuleBlockedCompareCodes = Array.from(new Set([
    primarySalesRuleBlocked ? fund.windCode : '',
    ...alternativeGapCodes,
  ].filter(Boolean)))
  const alternativeSalesRulesHref = salesRuleBlockedCompareCodes.length
    ? salesRulesHrefForCodes(salesRuleBlockedCompareCodes)
    : alternativeCompareCodes.length
      ? salesRulesHrefForCodes(alternativeCompareCodes)
    : salesRulesHrefForFund()
  const alternativeScanPending = alternativesLoading || alternativeSalesRuleGapsLoading
  const comparableAlternativeCount = formalReportBlocked ? 0 : alternativeReadyFunds.length
  const blockedAlternativeCount = alternativeGapFunds.length + (primarySalesRuleBlocked ? 1 : 0)
  const alternativeWorkflowStatus = alternativeScanPending
    ? 'pending' as const
    : alternativeSalesRuleGapError
      ? 'verify' as const
      : comparableAlternativeCount > 0
        ? 'done' as const
        : alternativeFunds.length || blockedAlternativeCount
          ? 'verify' as const
          : 'verify' as const
  const alternativeWorkflowLabel = alternativeScanPending
    ? '正在筛选与扫描'
    : alternativeSalesRuleGapError
      ? '销售规则扫描失败'
      : alternativeFunds.length
        ? `可比替代 ${comparableAlternativeCount} 只 / 待补规则 ${blockedAlternativeCount || alternativeGapFunds.length} 只`
        : '缺少可比候选'
  const alternativeWorkflowDescription = alternativeScanPending
    ? '正在从研究筛选引擎拉取同画像样本，并扫描销售规则硬缺口。'
    : alternativeSalesRuleGapError
      ? `${alternativeSalesRuleGapError}；不能把替代候选视为已可比。`
      : comparableAlternativeCount > 0
        ? `已找到 ${alternativeReadyFunds.slice(0, 3).map((item) => item.name).join('、')} 等可比替代；仍需补规则 ${blockedAlternativeCount || 0} 只。`
        : alternativeFunds.length
          ? `已找到 ${alternativeFunds.length} 只同画像候选，但当前主基金或替代候选销售规则未清零，应先补规则再横比。`
          : '单基金结论不能替代同类比较；建议回到研究筛选或放宽同类范围。'
  const alternativeWorkflowActionLabel = alternativeComparisonHref
    ? '打开横向比较'
    : alternativeFunds.length || reportSalesRuleBlocked
      ? '先补销售规则'
      : '打开完整选基'
  const alternativeWorkflowActionHref = alternativeComparisonHref || (
    alternativeFunds.length || reportSalesRuleBlocked
      ? alternativeSalesRulesHref
      : canonicalResearchHref(`/investor-selection?profile=${investorRiskProfile}&horizon=${investorHorizon}&purchasePlan=${investorPurchasePlan}&type=${encodeURIComponent(fund.type || '')}`)
  )
  const peerMetricEntries = fund.peerPercentiles?.metrics ? Object.entries(fund.peerPercentiles.metrics) : []
  const peerStrengths = peerMetricEntries
    .filter(([, metricItem]) => typeof metricItem.percentile === 'number' && metricItem.percentile >= 70)
    .sort((left, right) => Number(right[1].percentile ?? 0) - Number(left[1].percentile ?? 0))
    .map(([metricName, metricItem]) => ({
      key: metricName,
      label: metricItem.label || metricName,
      percentile: Number(metricItem.percentile),
      rank: metricItem.rank,
      peerCount: metricItem.peer_count,
      value: formatPeerMetricValue(metricItem.value, metricItem.unit),
    }))
  const peerWeaknesses = peerMetricEntries
    .filter(([, metricItem]) => typeof metricItem.percentile === 'number' && metricItem.percentile < 30)
    .sort((left, right) => Number(left[1].percentile ?? 100) - Number(right[1].percentile ?? 100))
    .map(([metricName, metricItem]) => ({
      key: metricName,
      label: metricItem.label || metricName,
      percentile: Number(metricItem.percentile),
      rank: metricItem.rank,
      peerCount: metricItem.peer_count,
      value: formatPeerMetricValue(metricItem.value, metricItem.unit),
    }))
  const peerProfessionalPercentile = asNumber(fund.peerPercentiles?.metrics?.professional_score?.percentile)
  const peerReturnPercentile = asNumber(fund.peerPercentiles?.metrics?.annualized_return?.percentile)
  const peerDrawdownPercentile = asNumber(fund.peerPercentiles?.metrics?.max_drawdown?.percentile)
  const peerVolatilityPercentile = asNumber(fund.peerPercentiles?.metrics?.annualized_volatility?.percentile)
  const peerAdvantageInputs = [
    peerProfessionalPercentile,
    peerReturnPercentile,
    peerDrawdownPercentile,
    peerVolatilityPercentile,
  ].filter((value): value is number => value !== null)
  const peerAdvantageScore = peerAdvantageInputs.length
    ? Math.round(peerAdvantageInputs.reduce((sum, value) => sum + value, 0) / peerAdvantageInputs.length)
    : null
  const peerLensHref = canonicalResearchHref(`/investor-selection?profile=${investorRiskProfile}&lens=peer&horizon=${investorHorizon}&purchasePlan=${investorPurchasePlan}&type=${encodeURIComponent(fund.type || '')}`)
  const peerSampleStatus = fund.peerPercentiles?.sample_status
  const peerMinimumSample = fund.peerPercentiles?.minimum_valid_peer_count || 5
  const peerUsableMetricCount = fund.peerPercentiles?.usable_metric_count ?? peerAdvantageInputs.length
  const peerInsufficientMetricCount = fund.peerPercentiles?.insufficient_metric_count ?? 0
  const peerRequiredMoreFunds = fund.peerPercentiles?.peer_metric_gap?.required_more_funds ?? 0
  const peerSuggestedSyncCodes = fund.peerPercentiles?.peer_metric_gap?.suggested_sync_codes || []
  const peerMetricSyncHref = peerSuggestedSyncCodes.length
    ? `/evidence-coverage?codes=${encodeURIComponent(peerSuggestedSyncCodes.join(','))}`
    : peerLensHref
  const peerSampleInsufficient = peerSampleStatus === 'insufficient_peer_sample'
    || (!!fund.peerPercentiles?.metrics && peerMetricEntries.every(([, metricItem]) => metricItem.sample_status === 'insufficient_peer_sample'))
  const peerEvidenceThin = !peerSampleInsufficient && !!fund.peerPercentiles?.metrics && peerUsableMetricCount < 2
  const peerInterpretation = (() => {
    if (!fund.peerPercentiles?.metrics) {
      return {
        tone: 'slate' as const,
        title: '同类解释待补',
        verdict: '缺同类分位，不用单只收益下判断',
        detail: '当前没有可用同类分位，建议先同步滚动指标或回到同类优势榜筛选。',
        actionLabel: '去同类优势榜',
        actionHref: peerLensHref,
      }
    }
    if (peerSampleInsufficient) {
      return {
        tone: 'amber' as const,
        title: '同类样本不足',
        verdict: '不输出同类优势结论',
        detail: `有效同类样本少于 ${peerMinimumSample} 只，分位数容易失真；当前只能作为观察线索，不能用于正式研究排序。${reportSalesRuleBlocked ? ` ${reportBlockReason}。` : ''}`,
        actionLabel: peerSuggestedSyncCodes.length ? '同步同类指标' : '去同类优势榜',
        actionHref: peerMetricSyncHref,
      }
    }
    if (peerEvidenceThin) {
      return {
        tone: 'amber' as const,
        title: '同类证据不完整',
        verdict: '不能单独用于研究排序',
        detail: `当前只有 ${peerUsableMetricCount} 个同类指标形成有效分位，另有 ${peerInsufficientMetricCount} 个指标缺少足够样本；至少还要补 ${peerRequiredMoreFunds} 只同类基金的净值与滚动指标，再判断同类优势。${reportSalesRuleBlocked ? ` ${reportBlockReason}。` : ''}`,
        actionLabel: peerSuggestedSyncCodes.length ? '同步同类指标' : '去同类优势榜',
        actionHref: peerMetricSyncHref,
      }
    }
    if (reportSalesRuleBlocked) {
      return {
        tone: 'amber' as const,
        title: '先补规则，再解释同类优势',
        verdict: '同类表现只能作研究观察',
        detail: `${reportBlockReason}；即便同类分位领先，也不能绕过销售规则门禁进入正式研究候选。`,
        actionLabel: '先补销售规则',
        actionHref: salesRulesHrefForFund(),
      }
    }
    if (peerStrengths.length >= 2 && peerWeaknesses.length === 0) {
      return {
        tone: 'emerald' as const,
        title: '同类优势较清晰',
        verdict: '可进入横向比较和研究复核报告',
        detail: `同类池中 ${peerStrengths.slice(0, 2).map((item) => `${item.label}分位${item.percentile}`).join('、')} 靠前，且暂无尾部分位短板。`,
        actionLabel: alternativeComparisonHref ? '打开横向比较' : '找同类替代',
        actionHref: alternativeComparisonHref || peerLensHref,
      }
    }
    if (peerStrengths.length && peerWeaknesses.length) {
      return {
        tone: 'blue' as const,
        title: '同类优势与短板并存',
        verdict: '必须同屏比较替代基金',
        detail: `${peerStrengths[0].label}靠前，但 ${peerWeaknesses[0].label} 落在尾部；不能只凭单一亮点继续研究复核。`,
        actionLabel: alternativeComparisonHref ? '打开横向比较' : '找同类替代',
        actionHref: alternativeComparisonHref || peerLensHref,
      }
    }
    if (peerWeaknesses.length >= 2) {
      return {
        tone: 'rose' as const,
        title: '同类短板明显',
        verdict: '先找替代，不进研究候选',
        detail: `${peerWeaknesses.slice(0, 2).map((item) => `${item.label}分位${item.percentile}`).join('、')} 靠后；除非有持仓或经理证据解释，否则优先找同类替代。`,
        actionLabel: '去同类优势榜',
        actionHref: peerLensHref,
      }
    }
    return {
      tone: 'slate' as const,
      title: '同类优势不突出',
      verdict: '作为观察样本，不单独推进',
      detail: '当前同类分位没有形成强优势；建议与同画像候选一起比较收益、回撤、费用和证据完整度。',
      actionLabel: alternativeComparisonHref ? '打开横向比较' : '找同类替代',
      actionHref: alternativeComparisonHref || peerLensHref,
    }
  })()
  const alternativePrioritySummary = (() => {
    if (alternativeScanPending) {
      return {
        tone: 'slate' as const,
        title: '正在生成替代比较优先级',
        detail: '正在读取同画像候选和销售规则硬缺口，完成后再判断先比较还是先补证。',
        actionLabel: '等待扫描',
        actionHref: '',
        chips: ['同画像', fund.type || '同类型', detailGate.purchasePlanLabel],
      }
    }
    if (reportSalesRuleBlocked) {
      return {
        tone: 'amber' as const,
        title: '先补主基金规则，再谈替代优劣',
        detail: `${reportBlockReason}；主基金自身不可进入研究候选时，替代比较只能用于研究观察，不能形成研究复核选择。`,
        actionLabel: '补主基金规则',
        actionHref: salesRulesHrefForFund(),
        chips: salesRuleGapMissingItems.slice(0, 5),
      }
    }
    if (alternativeReadyFunds.length >= 2) {
      return {
        tone: 'emerald' as const,
        title: '优先横向比较可比替代',
        detail: `已找到 ${alternativeReadyFunds.length} 只销售规则未见硬缺口的替代候选，先比较 ${alternativeReadyFunds.slice(0, 3).map((item) => item.name).join('、')} 与本基金。`,
        actionLabel: '打开横向比较',
        actionHref: alternativeComparisonHref,
        chips: alternativeReadyFunds.slice(0, 4).map((item) => item.windCode),
      }
    }
    if (alternativeReadyFunds.length === 1) {
      return {
        tone: 'blue' as const,
        title: '先做一对一替代比较',
        detail: `当前只有 ${alternativeReadyFunds[0].name} 可直接比较；如果差异不明显，再回到选基页扩大样本。`,
        actionLabel: '一对一对比',
        actionHref: alternativeComparisonHref,
        chips: [fund.windCode, alternativeReadyFunds[0].windCode],
      }
    }
    if (alternativeGapFunds.length) {
      return {
        tone: 'amber' as const,
        title: '替代候选也要先补规则',
        detail: `找到 ${alternativeFunds.length} 只替代候选，但 ${alternativeGapFunds.length} 只仍有销售规则硬缺口；横比前先补可执行证据。`,
        actionLabel: '补替代规则',
        actionHref: alternativeSalesRulesHref,
        chips: alternativeGapCodes.slice(0, 5),
      }
    }
    return {
      tone: 'slate' as const,
      title: '暂缺可靠替代候选',
      detail: '当前画像和类型下缺少可比较样本，建议回到完整选基页放宽证据等级或扩大基金类型。',
      actionLabel: '打开完整选基',
      actionHref: canonicalResearchHref(`/investor-selection?profile=${investorRiskProfile}&horizon=${investorHorizon}&purchasePlan=${investorPurchasePlan}&type=${encodeURIComponent(fund.type || '')}`),
      chips: [detailGate.profileLabel, detailGate.horizonLabel, detailGate.purchasePlanLabel],
    }
  })()
  const alternativeDecisionBrief = (() => {
    if (alternativeScanPending) {
      return {
        tone: 'slate' as const,
        title: '替代结论生成中',
        verdict: '等待同画像候选和销售规则扫描完成',
        detail: '当前还不能判断本基金是否比替代候选更值得继续研究。',
        primary: '主基金：销售规则与持有体验同步扫描中',
        alternative: '替代候选：等待研究清单返回',
        next: '扫描完成后再决定横向比较或补证',
      }
    }
    if (reportSalesRuleBlocked) {
      return {
        tone: 'amber' as const,
        title: '暂不比较收益，先补主基金规则',
        verdict: '主基金自身未过研究复核销售规则门禁',
        detail: `${reportBlockReason}。在主基金销售规则硬缺口清零前，替代候选只能作为研究观察，不进入研究选择。`,
        primary: `主基金：${salesRuleHardGapCount ?? '待扫描'} 项硬缺口`,
        alternative: alternativeFunds.length
          ? `替代候选：已找到 ${alternativeFunds.length} 只，但横比需等主基金补证`
          : '替代候选：暂无可比样本',
        next: salesRuleEvidenceCopy.primaryNextAction,
      }
    }
    if (alternativeReadyFunds.length) {
      const topAlternative = alternativeReadyFunds[0]
      return {
        tone: 'emerald' as const,
        title: '已有可比替代，不能只看单只基金',
        verdict: `优先比较 ${topAlternative.name}`,
        detail: `${topAlternative.name}（${topAlternative.windCode}）在当前画像下选基分 ${topAlternative.investorScore.toFixed(1)}，销售规则未见硬缺口；建议先做同屏横评，再决定是否入研究清单。`,
        primary: `主基金：${detailGate.label}，证据 ${detailGate.evidenceGrade}`,
        alternative: `可比替代：${alternativeReadyFunds.length} 只，最高分 ${topAlternative.investorScore.toFixed(1)}`,
        next: alternativeComparisonHref ? '打开横向比较，比较收益、回撤、成本、经理和门禁' : '至少选择 1 只替代基金做一对一比较',
      }
    }
    if (alternativeGapFunds.length) {
      return {
        tone: 'amber' as const,
        title: '替代候选也被销售规则拦住',
        verdict: '先补替代候选规则，再做横向比较',
        detail: `当前找到 ${alternativeFunds.length} 只替代候选，其中 ${alternativeGapFunds.length} 只销售规则仍有硬缺口；不能把这些候选直接当作可研究替代。`,
        primary: `主基金：${detailGate.label}，证据 ${detailGate.evidenceGrade}`,
        alternative: `待补替代：${alternativeGapFunds.slice(0, 3).map((item) => item.windCode).join('、')}`,
        next: '批量补替代候选销售规则，补齐后回到横向比较',
      }
    }
    return {
      tone: 'slate' as const,
      title: '暂缺可用替代结论',
      verdict: '不要直接下结论，先扩大候选范围',
      detail: '当前画像、持有期、研究方式假设和基金类型下，暂未形成可用于研究复核横比的替代样本。',
      primary: `主基金：${detailGate.label}，证据 ${detailGate.evidenceGrade}`,
      alternative: '替代候选：暂无可比对象',
      next: '回到完整选基页放宽基金类型、证据等级或分数阈值',
    }
  })()
  const holdingExposureDecision = buildHoldingExposureDecision()
  const methodologyFocus = buildFundDetailMethodologyFocus(fund)
  const onePageMemoLines = [
    `# ${fund.name}（${fund.windCode}）研究复核一页纸`,
    `研究画像：${detailGate.profileLabel}；持有期 ${detailGate.horizonLabel}；研究方式假设 ${detailGate.purchasePlanLabel}`,
    `结论：${detailGate.label}；证据等级 ${detailGate.evidenceGrade}；开放状态 ${detailGate.operationLabel}`,
    `核心指标：近一年收益 ${formatPercent(detailGate.annualReturn)}；最大回撤 ${formatPercent(detailGate.maxDrawdown)}；年化波动 ${formatPercent(detailGate.volatility)}；规模 ${detailGate.totalAsset == null ? '待补' : `${detailGate.totalAsset.toFixed(2)} 亿`}`,
    `基金经理：${managerSummary}`,
    `费率/申赎证据：${detailGate.feeSummary}；销售规则完整度 ${buyEvidence?.completenessScore ?? 0}；基础必补 ${buyEvidence?.requiredMissingCount ?? 0} 项；销售规则硬缺口 ${salesRuleHardGapCount ?? '待扫描'} 项`,
    `适配依据：${detailGate.suitabilityNotes.join('；')}`,
    `研究替代结论：${alternativeDecisionBrief.title}；${alternativeDecisionBrief.verdict}；${alternativeDecisionBrief.next}`,
    `替代边界：${alternativeDecisionBrief.primary}；${alternativeDecisionBrief.alternative}`,
    `研究模板：${methodologyFocus.templateName}；核心维度 ${methodologyFocus.dimensions.map((dimension) => dimension.name).join('、')}`,
    `方法论缺口：${methodologyFocus.methodologyMissingEvidenceFields.slice(0, 8).join('、') || '无'}`,
    `持仓暴露：${holdingExposureDecision.label}；${holdingExposureDecision.primaryRisk}；${holdingExposureDecision.nextAction}`,
    `反证核查：若收益追涨、销售规则、回撤预算、份额成本、经理持仓归因或同类替代任一项无法解释，先降级为观察或补证样本。`,
    `硬性阻断：${detailGate.hardBlocks.length ? detailGate.hardBlocks.join('；') : '暂无'}`,
    `主要补证：${[...detailGate.cautionFlags, ...salesRuleGapMissingItems, ...requiredMissingItems.map((item) => item.label)].slice(0, 8).join('；') || '暂无'}`,
    `持有体验：${purchaseSimulation ? `一次性配置假设 ${formatPercent(purchaseSimulation.lumpSum.returnRate)}；定投 ${formatPercent(purchaseSimulation.sip.returnRate)}；${feeAdjustedCoverageLabel}，费用后 ${formatPercent(lumpSumFeeAdjustedReturn)} / ${formatPercent(sipFeeAdjustedReturn)}；样本 ${purchaseSimulation.period.observations} 条` : '待测算'}`,
    `研究复核：${detailGate.mustVerifyBeforeBuy.join('；')}`,
    '声明：仅用于基金研究复核，不构成申赎操作指令。',
  ]
  const onePageMemo = onePageMemoLines.join('\n')
  const onePageEvidenceTsvCell = (value: unknown) => String(value ?? '').replace(/\t/g, ' ').replace(/\r?\n/g, ' ').trim()
  const onePageEvidenceTsv = [
    ['核查维度', '状态/结论', '已知证据', '缺口/风险', '下一步动作', '处理入口', '硬边界'],
    [
      '方法论模板',
      methodologyFocus.templateName,
      methodologyFocus.dimensions.map((dimension) => dimension.name).join('、'),
      methodologyFocus.methodologyMissingEvidenceFields.join('、') || '无',
      methodologyFocus.readyForFormalReview ? '按模板进入正式研究复核' : '先补方法论硬门槛证据',
      '',
      methodologyFocus.boundary,
    ],
    ...methodologyFocus.tsvRows.map((row) => [
      row[0],
      row[1],
      row[2],
      row[3],
      '按该维度补齐证据',
      '',
      methodologyFocus.boundary,
    ]),
    [
      '研究复核总闸门',
      detailGate.label,
      `证据等级 ${detailGate.evidenceGrade}；开放状态 ${detailGate.operationLabel}`,
      formalReportBlocked ? formalReportBlockSummary : detailGate.hardBlocks.join('；') || '暂无硬阻断',
      formalReportBlocked ? (reportSalesRuleBlocked ? '先补销售规则硬缺口' : '继续补齐正式研究门禁证据') : '进入横评、详情复核和报告留痕',
      formalReportBlocked && reportSalesRuleBlocked ? salesRulesHrefForFund() : '',
      '不是申赎操作指令；正式报告门禁未过时不得作为研究结论',
    ],
    [
      '研究画像与计划金额',
      `${detailGate.profileLabel} / ${detailGate.horizonLabel} / ${detailGate.purchasePlanLabel}`,
      `计划金额 ${formatMoney(currentPlannedAmount())}`,
      investorPurchasePlan === 'sip' ? '需核定投支持、起点和限购' : '需核起购、申购费和限购',
      '确认销售平台实时规则与本人适当性',
      salesRulesHrefForFund(),
      '计划金额变化后必须重新扫描金额执行门禁',
    ],
    [
      '销售规则硬缺口',
      salesRuleHardGapCount === 0 ? '通过' : salesRuleHardGapCount === null ? '待扫描' : `待补 ${salesRuleHardGapCount} 项`,
      fund.salesRule ? `${fund.salesRule.platform || 'manual'}；来源日期 ${fund.salesRule.sourceUpdatedAt || '待补'}` : '本地销售规则待补',
      salesRuleGapMissingItems.slice(0, 8).join('、') || '暂无硬缺口',
      salesRuleHardGapCount === 0 ? '研究复核仍复核销售平台实时状态' : '补齐 30 天内销售平台/合同来源后重扫',
      salesRulesHrefForFund(),
      '未清零前不能入正式研究候选或保存正式研究复核报告',
    ],
    [
      'R1-R5 适当性',
      fund.salesRule?.riskLevel || '待补',
      `风险等级来源：${fund.salesRule?.sourceUrl || fund.salesRule?.notes || '待补'}`,
      detailGate.suitabilityNotes.join('；') || '适当性仍需研究复核',
      '确认 R1-R5 来自销售平台/合同且在 30 天窗口内',
      salesRulesHrefForFund(),
      'Tushare fund_basic 不能作为 R1-R5 来源',
    ],
    [
      '计划金额执行',
      executionAmountGate?.label || '金额门槛待扫描',
      executionAmountGate?.detail || `当前${investorPurchasePlan === 'sip' ? '计划月扣款' : '计划配置'} ${formatMoney(currentPlannedAmount())}`,
      executionAmountGate?.status === 'blocked' ? '当前计划金额不可执行' : '金额门槛仍需实时复核',
      executionAmountGate?.status === 'blocked' ? '调整计划金额或补销售规则后重扫' : '保留金额口径进入回放/横评',
      salesRulesHrefForFund(),
      '金额不可执行时不得保存正式研究复核报告',
    ],
    [
      '费用与赎回',
      buyEvidence?.completenessLevel || 'thin',
      `证据完整度 ${buyEvidence?.completenessScore ?? 0}；${detailGate.feeSummary}`,
      [...requiredMissingItems.map((item) => item.label), ...(feeAdjusted?.missingItems || [])].slice(0, 8).join('、') || '暂无费用缺口',
      '补申购费、赎回费、销售服务费和持有期规则',
      salesRulesHrefForFund(),
      '费用证据不完整时费用后测算只作观察',
    ],
    [
      '真实净值回放',
      purchaseSimulation ? `${purchaseSimulation.period.observations} 条样本` : '待回放',
      purchaseSimulation ? `一次性 ${formatPercent(purchaseSimulation.lumpSum.returnRate)}；定投 ${formatPercent(purchaseSimulation.sip.returnRate)}` : '未完成真实 NAV 回放',
      purchaseSimulation ? feeAdjustedMissingText || '回放样本需结合费用证据' : '缺回放不能验证持有体验和压力测试',
      purchaseSimulation ? '结合压力体验和横评复核' : '先生成真实净值回放',
      '',
      '缺真实回放不得生成正式研究复核报告',
    ],
    [
      '持仓与经理',
      `${holdingExposureDecision.label} / ${managerSummary}`,
      holdingExposureDecision.primaryRisk,
      holdingExposureDecision.status === 'done' ? '暂无持仓暴露硬缺口' : holdingExposureDecision.nextAction,
      '补季报持仓、行业暴露和经理任期样本',
      '',
      '经理或持仓解释不足时不应只看收益排序',
    ],
    [
      '替代横评',
      alternativeDecisionBrief.verdict,
      alternativeDecisionBrief.primary,
      alternativeDecisionBrief.alternative,
      alternativeDecisionBrief.next,
      alternativeComparisonHref || '',
      '没有打败同类替代前不进入正式候选',
    ],
    [
      '正式报告',
      formalReportBlocked ? '待补证' : savedReportId ? '已保存/可查看' : '可生成待保存',
      savedReportId ? `报告ID ${savedReportId}` : formalReportBlocked ? formalReportBlockSummary : '门禁当前未阻断',
      formalReportBlocked ? formalReportBlockReason : '报告仍需研究复核实时规则',
      formalReportBlocked ? '先处理阻断项' : '保存到报告库并复核报告有效性',
      savedReportId ? `/reports/${savedReportId}` : '',
      '报告留痕不等于申赎操作指令',
    ],
  ].map((row) => row.map(onePageEvidenceTsvCell).join('\t')).join('\n')
  const hasSalesRuleStatus = Boolean(fund.salesRule?.purchaseStatus && fund.salesRule.purchaseStatus !== 'unknown')
  const hasSalesRiskLevel = Boolean(fund.salesRule?.riskLevel)
  const hasPurchaseFee = fund.salesRule?.purchaseFeeRate !== null && fund.salesRule?.purchaseFeeRate !== undefined
  const hasRedemptionRule = hasSourceBackedRedemptionRules(fund.salesRule)
  const hasPlanRule = investorPurchasePlan === 'sip'
    ? fund.salesRule?.supportsSip !== null && fund.salesRule?.supportsSip !== undefined && fund.salesRule?.minSipAmount !== null && fund.salesRule?.minSipAmount !== undefined
    : fund.salesRule?.minPurchaseAmount !== null && fund.salesRule?.minPurchaseAmount !== undefined
  const salesRulesReady = hasSalesRuleStatus && hasSalesRiskLevel && hasPurchaseFee && hasRedemptionRule && hasPlanRule && salesRuleHardGapCount === 0
  const currentPurchaseAmount = investorPurchasePlan === 'sip'
    ? asPositiveNumber(simulationForm.monthlyAmount, 1000)
    : asPositiveNumber(simulationForm.lumpSumAmount, 10000)
  const planAmountFloor = investorPurchasePlan === 'sip' ? asNumber(fund.salesRule?.minSipAmount) : asNumber(fund.salesRule?.minPurchaseAmount)
  const dailyLimitAmount = asNumber(fund.salesRule?.dailyLimitAmount)
  const purchaseStatus = fund.salesRule?.purchaseStatus || 'unknown'
  const purchaseStatusIsOpen = purchaseStatus === 'open' || purchaseStatus === 'limited'
  const purchaseStatusBlocked = purchaseStatus === 'closed'
  const planAmountBlocked = planAmountFloor !== null && currentPurchaseAmount < planAmountFloor
  const dailyLimitBlocked = investorPurchasePlan === 'lump_sum' && dailyLimitAmount !== null && currentPurchaseAmount > dailyLimitAmount
  const salesRuleChecklist = [
    {
      title: '申购状态',
      status: purchaseStatusBlocked ? 'blocked' as const : purchaseStatusIsOpen ? 'done' as const : 'verify' as const,
      label: fund.salesRule?.purchaseStatusLabel || detailGate.operationLabel,
      detail: purchaseStatus === 'limited' ? '限额开放，必须结合限购金额确认可执行额度。' : purchaseStatusBlocked ? '销售端暂停申购，不进入研究候选。' : '研究复核需复核销售平台实时开放状态。',
    },
    {
      title: '申购费率',
      status: hasPurchaseFee ? 'done' as const : 'verify' as const,
      label: fund.salesRule?.purchaseFeeRate == null ? '待补' : formatPercent(fund.salesRule.purchaseFeeRate),
      detail: '影响真实配置成本，应使用销售平台折扣后费率。',
    },
    {
      title: '赎回规则',
      status: hasRedemptionRule ? 'done' as const : 'verify' as const,
      label: hasRedemptionRule ? `${fund.salesRule?.redemptionFeeRules?.length || 0} 条规则` : '待补',
      detail: redemptionRuleSummary || '短持有期赎回费会显著影响研究复核回放；未补齐前不能假设赎回成本。',
    },
    {
      title: investorPurchasePlan === 'sip' ? '定投起点' : '最低申购',
      status: fund.salesRule?.supportsSip === false && investorPurchasePlan === 'sip' ? 'blocked' as const : planAmountBlocked ? 'blocked' as const : planAmountFloor === null ? 'verify' as const : 'done' as const,
      label: planAmountFloor === null ? '待补' : formatMoney(planAmountFloor),
      detail: `${detailGate.purchasePlanLabel}金额 ${formatMoney(currentPurchaseAmount)}${planAmountBlocked ? '，低于平台起点。' : '，需与平台规则匹配。'}`,
    },
    {
      title: '限购金额',
      status: dailyLimitBlocked ? 'blocked' as const : dailyLimitAmount === null ? 'verify' as const : 'done' as const,
      label: dailyLimitAmount === null ? '待补' : formatMoney(dailyLimitAmount),
      detail: dailyLimitBlocked ? '当前一次性计划金额超过本地记录限购金额。' : '限购决定真实可执行金额，不等于基金质量判断。',
    },
    {
      title: '风险等级',
      status: detailGate.salesRiskLevel === null ? 'verify' as const : detailGate.salesRiskLevel > detailGate.maxSalesRiskLevel ? 'blocked' as const : 'done' as const,
      label: detailGate.salesRiskLevel === null ? '待补' : `R${detailGate.salesRiskLevel} / 最高 R${detailGate.maxSalesRiskLevel}`,
      detail: '用于研究画像适当性匹配，高于画像承受等级时阻断。',
    },
    {
      title: '来源日期',
      status: fund.salesRule?.sourceUpdatedAt ? 'done' as const : 'verify' as const,
      label: fund.salesRule?.sourceUpdatedAt || '待补',
      detail: fund.salesRule?.platform ? `来源：${fund.salesRule.platform}` : '需要记录销售平台来源和更新日期。',
    },
  ]
  const holdingExperience = buildHoldingExperienceEvidence()
  const simulationReturnForPlan = purchaseSimulation
    ? investorPurchasePlan === 'sip'
      ? purchaseSimulation.sip.returnRate
      : purchaseSimulation.lumpSum.returnRate
    : null
  const simulationDrawdownForPlan = purchaseSimulation
    ? investorPurchasePlan === 'sip'
      ? purchaseSimulation.sip.maxAccountDrawdown
      : purchaseSimulation.lumpSum.maxDrawdown
    : null
  const professionalScore = fund.professionalScoring?.overall_score ?? null
  const professionalScoreMissing = professionalScore === null
  const purchaseDecisionComponentScores = {
    buyEvidence: buyEvidence?.completenessScore ?? 30,
    professional: professionalScoreMissing ? 0 : professionalScore,
    holdingExperience: holdingExperience.score,
    holdingExposure: holdingExposureDecision.score,
    suitabilityGate: detailGate.hardBlocks.length ? 20 : detailGate.cautionFlags.length ? 56 : 82,
    salesRules: salesRulesReady ? 90 : salesRuleHardGapCount === null ? 45 : 30,
  }
  const purchaseDecisionBreakdown = [
    {
      label: '证据完整度',
      score: purchaseDecisionComponentScores.buyEvidence,
      weight: 24,
      contribution: purchaseDecisionComponentScores.buyEvidence * 0.24,
      detail: `基础必补 ${buyEvidence?.requiredMissingCount ?? 0} 项；销售规则硬缺口 ${salesRuleHardGapCount ?? '待扫描'} 项`,
    },
    {
      label: '专业评价',
      score: purchaseDecisionComponentScores.professional,
      weight: 18,
      contribution: purchaseDecisionComponentScores.professional * 0.18,
      detail: professionalScoreMissing ? '专业评分待补，本项不加分，并触发研究复核分封顶。' : '来自基金专业评分模型。',
    },
    {
      label: '持有体验',
      score: purchaseDecisionComponentScores.holdingExperience,
      weight: 18,
      contribution: purchaseDecisionComponentScores.holdingExperience * 0.18,
      detail: holdingExperience.label,
    },
    {
      label: '持仓暴露',
      score: purchaseDecisionComponentScores.holdingExposure,
      weight: 12,
      contribution: purchaseDecisionComponentScores.holdingExposure * 0.12,
      detail: holdingExposureDecision.primaryRisk,
    },
    {
      label: '适当性门禁',
      score: purchaseDecisionComponentScores.suitabilityGate,
      weight: 14,
      contribution: purchaseDecisionComponentScores.suitabilityGate * 0.14,
      detail: detailGate.hardBlocks.length ? '存在硬性阻断。' : detailGate.cautionFlags.length ? '存在待复核事项。' : '画像、期限、风险预算暂未触发硬阻断。',
    },
    {
      label: '销售规则',
      score: purchaseDecisionComponentScores.salesRules,
      weight: 14,
      contribution: purchaseDecisionComponentScores.salesRules * 0.14,
      detail: salesRulesReady ? '销售规则硬缺口已清零。' : reportSalesRuleBlocked ? '销售规则硬缺口未清零。' : '销售规则仍需复核。',
    },
  ]
  const rawPurchaseDecisionScore = Math.round(Math.max(0, Math.min(100,
    purchaseDecisionBreakdown.reduce((sum, item) => sum + item.contribution, 0),
  )))
  const purchaseDecisionScore = detailGate.level === 'blocked'
    ? Math.min(rawPurchaseDecisionScore, 25)
    : formalReportBlocked
      ? Math.min(rawPurchaseDecisionScore, 55)
      : professionalScoreMissing
        ? Math.min(rawPurchaseDecisionScore, 60)
        : rawPurchaseDecisionScore
  const purchaseDecisionCapReason = detailGate.level === 'blocked'
    ? `硬性阻断封顶 25；原始研究分 ${rawPurchaseDecisionScore}`
    : formalReportBlocked
      ? `正式研究复核证据门禁封顶 55：${formalReportBlockReason}；原始研究分 ${rawPurchaseDecisionScore}`
      : professionalScoreMissing
        ? `专业评分缺失封顶 60；原始研究分 ${rawPurchaseDecisionScore}`
        : `未触发封顶；原始研究分 ${rawPurchaseDecisionScore}`
  const purchaseDecisionTone = detailGate.level === 'blocked'
    ? 'rose'
    : formalReportBlocked
      ? 'amber'
      : purchaseDecisionScore >= 75
        ? 'emerald'
        : purchaseDecisionScore >= 60
          ? 'blue'
          : 'slate'
  const purchaseDecisionLabel = detailGate.level === 'blocked'
    ? '不进入研究候选'
    : formalReportBlocked
      ? '补证前不可研究'
      : purchaseDecisionScore >= 75
        ? '可进入研究复核'
        : purchaseDecisionScore >= 60
          ? '可观察后复核'
          : '先补证再研究'
  const purchaseDecisionClass = purchaseDecisionTone === 'rose'
    ? 'bg-rose-50 text-rose-800 ring-1 ring-rose-100'
    : purchaseDecisionTone === 'amber'
      ? 'bg-amber-50 text-amber-800 ring-1 ring-amber-100'
      : purchaseDecisionTone === 'emerald'
        ? 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-100'
        : purchaseDecisionTone === 'blue'
          ? 'bg-blue-50 text-blue-800 ring-1 ring-blue-100'
          : 'bg-slate-50 text-slate-700 ring-1 ring-slate-100'
  const purchaseDecisionSummary = detailGate.level === 'blocked'
    ? `${fund.name} 当前存在硬性阻断，不应纳入研究候选。`
    : formalReportBlocked
      ? `${fund.name} 当前只适合继续研究和补证；${formalReportBlockSummary}，不输出可研究结论。`
      : `${fund.name} 当前可进入研究复核，但仍需保存研究复核报告并复核销售平台实时规则。`
  const buyDecisionRole = (() => {
    if (detailGate.level === 'blocked') {
      return {
        tone: 'rose' as const,
        label: '排除研究路径',
        subtitle: '硬阻断样本',
        summary: `${detailGate.hardBlocks[0] || '适当性或基础研究门禁未通过'}，不进入研究清单、横评优先位或正式报告。`,
        proofPoints: [
          `风险画像：${detailGate.profileLabel}`,
          `证据等级：${detailGate.evidenceGrade}`,
          `硬阻断：${detailGate.hardBlocks.length || 1} 项`,
        ],
        nextAction: '仅保留研究观察，除非硬阻断消失后重新评估。',
      }
    }
    if (formalReportBlocked || reportSalesRuleBlocked) {
      return {
        tone: 'amber' as const,
        label: '补证优先样本',
        subtitle: '不能作为正式候选',
        summary: formalReportBlockReason || reportBlockReason || '正式研究复核证据未达标，先补齐门禁证据。',
        proofPoints: [
          `销售硬缺口：${salesRuleHardGapCount ?? '待扫描'} 项`,
          `回放：${purchaseSimulation ? `${purchaseSimulation.period.observations} 条` : '待跑'}`,
          `必补：${buyEvidence?.requiredMissingCount ?? 0} 项`,
        ],
        nextAction: reportSalesRuleBlocked ? '先补销售规则硬缺口。' : !purchaseSimulation ? '先跑真实净值回放。' : '继续补齐正式研究门禁证据。',
      }
    }
    if (alternativeReadyFunds.length > 0 && !savedReportId) {
      return {
        tone: 'blue' as const,
        label: '横评候选样本',
        subtitle: '先和替代基金比',
        summary: `已有 ${alternativeReadyFunds.length} 只同画像替代候选可比较，单基金结论不能直接升级为研究复核结论。`,
        proofPoints: [
          `替代候选：${alternativeReadyFunds.slice(0, 2).map((item) => item.name).join('、')}`,
          `研究复核分：${purchaseDecisionScore}`,
          `横评状态：待确认是否仍领先`,
        ],
        nextAction: alternativeComparisonHref ? '打开横向比较，确认是否仍领先。' : '扩大同类样本后再比较。',
      }
    }
    return {
      tone: 'emerald' as const,
      label: savedReportId || candidatePoolMember ? '正式研究候选' : '可推进研究复核',
      subtitle: savedReportId ? '已有报告留痕' : '待保存报告',
      summary: savedReportId
        ? '研究复核报告已保存，可进入销售平台材料复核。'
        : '核心门禁暂未阻断，应保存研究复核报告并固定当前证据口径。',
      proofPoints: [
        `研究复核分：${purchaseDecisionScore}`,
        `销售规则：${salesRulesReady ? '无硬缺口' : '需复核'}`,
        `回放：${purchaseSimulation ? `${purchaseSimulation.period.observations} 条` : '待跑'}`,
      ],
      nextAction: savedReportId ? '查看报告并做销售平台材料复核。' : '保存研究复核报告。',
    }
  })()
  const buyDecisionRoleClass = buyDecisionRole.tone === 'rose'
    ? 'border-rose-100 bg-rose-50 text-rose-900'
    : buyDecisionRole.tone === 'amber'
      ? 'border-amber-100 bg-amber-50 text-amber-900'
      : buyDecisionRole.tone === 'blue'
        ? 'border-blue-100 bg-blue-50 text-blue-900'
        : 'border-emerald-100 bg-emerald-50 text-emerald-900'
  const profileSensitivityRows = (Object.keys(investorRiskProfiles) as InvestorRiskProfile[]).map((profile) => {
    const gate = buildDetailGate(fund, { profile, horizon: investorHorizon, purchasePlan: investorPurchasePlan })
    const rawScore = Math.round(Math.max(0, Math.min(100,
      (buyEvidence?.completenessScore ?? 30) * 0.24 +
      (professionalScoreMissing ? 0 : professionalScore) * 0.18 +
      holdingExperience.score * 0.18 +
      holdingExposureDecision.score * 0.12 +
      (gate.hardBlocks.length ? 20 : gate.cautionFlags.length ? 56 : 82) * 0.14 +
      (salesRulesReady ? 90 : salesRuleHardGapCount === null ? 45 : 30) * 0.14,
    )))
    const score = gate.level === 'blocked'
      ? Math.min(rawScore, 25)
      : reportSalesRuleBlocked
        ? Math.min(rawScore, 55)
        : professionalScoreMissing
          ? Math.min(rawScore, 60)
          : rawScore
    const label = gate.level === 'blocked'
      ? '不进入研究候选'
      : reportSalesRuleBlocked
        ? '补规则前不可研究'
        : score >= 75
          ? '可进入研究复核'
          : score >= 60
            ? '可观察后复核'
            : '先补证再研究'
    return {
      profile,
      profileLabel: gate.profileLabel,
      score,
      rawScore,
      label,
      riskBudget: gate.riskBudget,
      maxSalesRiskLevel: gate.maxSalesRiskLevel,
      hardBlocks: gate.hardBlocks,
      cautionFlags: gate.cautionFlags,
      isCurrent: profile === investorRiskProfile,
    }
  })
  const planSensitivityRows = (Object.keys(investorPurchasePlans) as InvestorPurchasePlan[]).map((purchasePlan) => {
    const gate = buildDetailGate(fund, { profile: investorRiskProfile, horizon: investorHorizon, purchasePlan })
    const planReturn = purchaseSimulation
      ? purchasePlan === 'sip'
        ? sipFeeAdjustedReturn
        : lumpSumFeeAdjustedReturn
      : null
    const planDrawdown = purchaseSimulation
      ? purchasePlan === 'sip'
        ? purchaseSimulation.sip.maxAccountDrawdown
        : purchaseSimulation.lumpSum.maxDrawdown
      : null
    return {
      purchasePlan,
      label: gate.purchasePlanLabel,
      gateLabel: gate.label,
      hardBlocks: gate.hardBlocks,
      cautionFlags: gate.cautionFlags,
      returnRate: planReturn,
      drawdown: planDrawdown,
      isCurrent: purchasePlan === investorPurchasePlan,
    }
  })
  const blockedProfileCount = profileSensitivityRows.filter((item) => item.hardBlocks.length > 0).length
  const sensitivityConclusion = reportSalesRuleBlocked
    ? '销售规则硬缺口未清零，所有画像敏感性只能作为研究观察，不能生成正式研究结论。'
    : blockedProfileCount > 0
      ? `${blockedProfileCount} 个风险画像会触发硬阻断；这只基金不是“所有研究画像都适合”的通用候选。`
      : '当前三类风险画像未触发硬阻断，但分数、回撤预算和研究方式假设差异仍需分别留痕。'
  const navAgeDays = evidenceAgeDays(fund.navDate)
  const salesRuleAgeDays = evidenceAgeDays(fund.salesRule?.sourceUpdatedAt || salesRuleGap?.ruleSourceUpdatedAt)
  const holdingQuarterDate = holdingEvidence?.quarter ? `${holdingEvidence.quarter.slice(0, 4)}-${holdingEvidence.quarter.slice(4, 6) || '12'}-01` : null
  const holdingAgeDays = evidenceAgeDays(holdingQuarterDate)
  const simulationEndAgeDays = evidenceAgeDays(purchaseSimulation?.period.endDate)
  const buyBeforeFreshnessItems = [
    {
      key: 'nav',
      title: '净值日期',
      status: evidenceFreshnessStatus(navAgeDays, 10, 30),
      ageDays: navAgeDays,
      label: fund.navDate ? formatDateText(fund.navDate) : '待补',
      detail: '净值过旧会扭曲收益、回撤和持有体验回放起点。',
      action: '刷新真实净值',
      href: '/evidence-coverage',
    },
    {
      key: 'sales-rule',
      title: '销售规则来源日',
      status: salesRuleHardGapCount === null
        ? 'missing' as const
        : salesRuleHardGapCount > 0
          ? 'stale' as const
          : evidenceFreshnessStatus(salesRuleAgeDays, 30, 90),
      ageDays: salesRuleAgeDays,
      label: fund.salesRule?.sourceUpdatedAt || salesRuleGap?.ruleSourceUpdatedAt || '待补',
      detail: '申购状态、费率、限购和风险等级必须接近当前销售平台。',
      action: '核查销售规则',
      href: salesRulesHrefForFund(),
    },
    {
      key: 'holding',
      title: '持仓季度',
      status: holdingEvidence?.status === 'available'
        ? evidenceFreshnessStatus(holdingAgeDays, 150, 240)
        : 'missing' as const,
      ageDays: holdingAgeDays,
      label: holdingEvidence?.quarter || '待补',
      detail: '持仓过旧时，行业/个股暴露不能支撑研究复核结论。',
      action: '补持仓证据',
      href: `/api/funds/${encodeURIComponent(fund.windCode)}/holdings`,
    },
    {
      key: 'simulation',
      title: '回放截止日',
      status: purchaseSimulation
        ? evidenceFreshnessStatus(simulationEndAgeDays, 30, 90)
        : 'missing' as const,
      ageDays: simulationEndAgeDays,
      label: purchaseSimulation?.period.endDate || '待测算',
      detail: '持有体验回放需要覆盖最新净值，否则收益/回撤体验可能滞后。',
      action: purchaseSimulation ? '重跑持有体验回放' : '先跑持有体验回放',
      href: null,
    },
  ]
  const staleFreshnessItems = buyBeforeFreshnessItems.filter((item) => item.status === 'stale')
  const missingFreshnessItems = buyBeforeFreshnessItems.filter((item) => item.status === 'missing')
  const watchFreshnessItems = buyBeforeFreshnessItems.filter((item) => item.status === 'watch')
  const freshnessScore = Math.max(0, 100
    - staleFreshnessItems.length * 24
    - missingFreshnessItems.length * 18
    - watchFreshnessItems.length * 10)
  const freshnessLabel = staleFreshnessItems.length
    ? '证据已过期/硬缺口'
    : missingFreshnessItems.length
      ? '关键证据待补'
      : watchFreshnessItems.length
        ? '证据临近复核'
        : '证据时效可用'
  const freshnessSummary = staleFreshnessItems.length
    ? `${staleFreshnessItems.map((item) => item.title).join('、')} 已过期或存在硬缺口，不能沿用为正式研究复核结论。`
    : missingFreshnessItems.length
      ? `${missingFreshnessItems.map((item) => item.title).join('、')} 待补，先补证再保存研究复核报告。`
      : watchFreshnessItems.length
        ? `${watchFreshnessItems.map((item) => item.title).join('、')} 临近复核窗口，研究复核需重新确认。`
        : '净值、销售规则、持仓和回放时效暂可用于研究复核；正式研究复核前仍需销售平台实时复核。'
  const freshnessPrimaryAction = staleFreshnessItems[0] || missingFreshnessItems[0] || watchFreshnessItems[0] || null
  const alternativeDecisionRows = alternativeFunds.slice(0, 4).map((item) => {
    const gap = alternativeSalesRuleGaps[item.windCode.toUpperCase()]
    const alternativeBlocked = Boolean(gap && gap.missingCount > 0)
    const scoreGap = item.investorScore == null ? null : item.investorScore - purchaseDecisionScore
    const returnGap = item.annualReturn == null || detailGate.annualReturn == null
      ? null
      : item.annualReturn - detailGate.annualReturn
    const drawdownGap = item.maxDrawdown == null || detailGate.maxDrawdown == null
      ? null
      : Math.abs(item.maxDrawdown) - Math.abs(detailGate.maxDrawdown)
    const evidenceGap = (item.purchaseGate?.evidenceGrade || '-') === detailGate.evidenceGrade
      ? '证据相当'
      : `${item.purchaseGate?.evidenceGrade || '-'} vs ${detailGate.evidenceGrade}`
    const wins = [
      scoreGap !== null && scoreGap >= 5 ? '研究分领先' : '',
      returnGap !== null && returnGap > 0.02 ? '收益领先' : '',
      drawdownGap !== null && drawdownGap < -0.02 ? '回撤更低' : '',
      !alternativeBlocked ? '规则无硬缺口' : '',
      item.riskSuitability?.status === 'matched' ? '适当性匹配' : '',
    ].filter(Boolean)
    const risks = [
      alternativeBlocked ? `销售规则缺 ${gap?.missingCount || 0} 项` : '',
      drawdownGap !== null && drawdownGap > 0.02 ? '回撤压力更高' : '',
      returnGap !== null && returnGap < -0.02 ? '收益落后' : '',
      item.riskSuitability?.status === 'mismatch' ? '适当性不匹配' : '',
      item.purchaseGate?.cautionFlags?.[0] || item.warnings?.[0] || '',
    ].filter(Boolean)
    const verdict = reportSalesRuleBlocked
      ? '主基金补证前仅作观察'
      : alternativeBlocked
        ? '先补替代规则'
        : wins.length >= 3 || (scoreGap !== null && scoreGap >= 8)
          ? '优先纳入横评'
          : wins.length
            ? '可作为备选'
            : '暂不优先'

    return {
      ...item,
      alternativeBlocked,
      gap,
      scoreGap,
      returnGap,
      drawdownGap,
      evidenceGap,
      wins,
      risks,
      verdict,
    }
  })
  const alternativeMatrixSummary = (() => {
    if (alternativeScanPending) return '正在扫描替代候选，暂不形成横评结论。'
    if (reportSalesRuleBlocked) return '主基金销售规则硬缺口未清零，替代矩阵只用于研究观察，不能作为研究选择。'
    const compareReadyRows = alternativeDecisionRows.filter((item) => !item.alternativeBlocked)
    if (!compareReadyRows.length) return alternativeDecisionRows.length ? '替代候选也存在销售规则硬缺口，先补规则再比较。' : '当前缺少同画像替代样本，先扩大选基范围。'
    const leadingRows = compareReadyRows.filter((item) => item.verdict === '优先纳入横评')
    if (leadingRows.length) return `${leadingRows[0].name} 等 ${leadingRows.length} 只在研究分、收益/回撤或证据上具备挑战主基金的条件，建议先横评。`
    return `已有 ${compareReadyRows.length} 只可比替代，但优势不明显；可作为研究复核备选池一起复核。`
  })()
  const alternativeDecisionMatrixTsv = [
    ['角色', '基金代码', '基金名称', '决策', '研究分/分差', '近一年收益/收益差', '最大回撤/回撤差', '证据', '销售规则状态', '适当性', '优势', '风险', '下一动作', '入口'],
    [
      '主基金',
      fund.windCode,
      fund.name,
      purchaseDecisionLabel,
      `基准 ${purchaseDecisionScore}`,
      formatPercent(detailGate.annualReturn),
      formatPercent(detailGate.maxDrawdown),
      detailGate.evidenceGrade,
      reportSalesRuleBlocked ? reportBlockReason : '以主基金销售规则门禁为准',
      detailGate.suitabilityNotes.slice(0, 2).join('；') || '适当性仍需复核',
      reportSalesRuleBlocked ? '' : '作为当前比较基准',
      reportSalesRuleBlocked ? reportBlockReason : '',
      alternativeMatrixSummary,
      alternativeComparisonHref || alternativeSalesRulesHref,
    ],
    ...alternativeDecisionRows.map((item) => [
      '替代候选',
      item.windCode,
      item.name,
      item.verdict,
      formatScoreDiff(item.scoreGap),
      item.returnGap === null ? '待补' : formatScoreDiff(item.returnGap * 100, '%'),
      item.drawdownGap === null ? '待补' : formatScoreDiff(item.drawdownGap * 100, '%'),
      item.evidenceGap,
      item.alternativeBlocked ? `销售规则缺 ${item.gap?.missingCount || 0} 项` : '销售规则未见硬缺口',
      item.riskSuitability?.label || '风险等级待补',
      item.wins.join('；') || '暂无明确优势',
      item.risks.join('；') || '暂无明确风险',
      item.alternativeBlocked ? '先补替代销售规则，再回到横向比较' : '纳入同画像横评，比较收益、回撤、成本和门禁',
      item.alternativeBlocked ? salesRulesHrefForCodes([item.windCode]) : alternativeComparisonHref || `/analysis/comparison?codes=${encodeURIComponent([fund.windCode, item.windCode].join(','))}`,
    ]),
    ['说明', '替代横评矩阵只服务基金筛选和基金分析；主基金或替代候选销售规则/R1-R5、计划金额、适当性、净值回放和研究复核报告门禁未清零前，不形成研究建议。', '', '', '', '', '', '', '', '', '', '', alternativeMatrixSummary, alternativeComparisonHref || alternativeSalesRulesHref],
  ].map((row) => row.map(onePageEvidenceTsvCell).join('\t')).join('\n')
  const purchaseDecisionReasons = [
    `证据完整度 ${buyEvidence?.completenessScore ?? 0}，基础必补 ${buyEvidence?.requiredMissingCount ?? 0} 项`,
    professionalScore == null ? '专业评分待补' : `专业评分 ${professionalScore.toFixed(1)} / ${fund.professionalScoring?.overall_grade || '评级待补'}`,
    purchaseSimulation
      ? `${detailGate.purchasePlanLabel}回放 ${formatPercent(simulationReturnForPlan)}，回撤 ${formatPercent(simulationDrawdownForPlan)}，样本 ${purchaseSimulation.period.observations} 条`
      : '持有体验回放待完成',
    salesRuleHardGapCount === null ? '销售规则硬缺口待扫描' : `销售规则硬缺口 ${salesRuleHardGapCount} 项`,
    `持仓暴露：${holdingExposureDecision.label}，${holdingExposureDecision.primaryRisk}`,
    detailGate.hardBlocks.length ? `硬阻断：${detailGate.hardBlocks.slice(0, 2).join('；')}` : '',
    detailGate.cautionFlags.length ? `待补：${detailGate.cautionFlags.slice(0, 2).join('；')}` : '',
  ].filter(Boolean)
  const purchaseDecisionRecheckTriggers = [
    reportSalesRuleBlocked
      ? `销售规则硬缺口 ${salesRuleHardGapCount ?? '待扫描'} 项清零后，当前“不可研究/先补证”结论才允许重新评估。`
      : '',
    salesRulesReady ? '' : `补齐${salesRuleEvidenceCopy.recheckFields}后，费用后收益和适当性可能改变。`,
    !purchaseSimulation ? '真实净值回放尚未完成，跑完回放后收益/回撤体验可能改变排序。' : '',
    purchaseSimulation && Math.abs(simulationDrawdownForPlan ?? 0) > detailGate.riskBudget * 0.9
      ? `当前回撤接近画像预算，若回放区间延长或净值更新后回撤扩大，结论会转为更谨慎。`
      : '',
    detailGate.salesRiskLevel === null
      ? '销售平台风险等级补齐后，若高于当前画像承受等级，将直接阻断研究候选。'
      : '',
    shareClassInfo?.siblingCount
      ? `同基金 ${shareClassInfo.siblingCount} 个份额仍需完成 A/C/I/H 成本比较；若推荐份额不是当前份额，当前基金详情结论只代表当前份额的核查顺序。`
      : '',
    alternativeReadyFunds.length > 0 && !reportSalesRuleBlocked
      ? '同画像替代候选已可比较；若替代基金在费用后回放、回撤或证据完整度明显领先，单基金优先级会下调。'
      : '',
    ...holdingExposureDecision.reverseTriggers,
  ].filter(Boolean).slice(0, 6)
  const purchaseDowngradeQueue = [
    detailGate.level === 'blocked' ? {
      key: 'hard-block',
      lane: '排除研究路径',
      severity: 'high' as const,
      reason: detailGate.hardBlocks[0] || '适当性、风险预算或基础研究门禁触发硬阻断。',
      nextAction: '只保留研究观察，硬阻断消失后再重新诊断。',
      href: null as string | null,
    } : null,
    reportSalesRuleBlocked ? {
      key: 'sales-rule',
      lane: '降级为补规则样本',
      severity: 'high' as const,
      reason: `销售规则硬缺口 ${salesRuleHardGapCount ?? '待扫描'} 项未清零，不能进入正式候选或保存研究复核报告。`,
      nextAction: salesRuleEvidenceCopy.primaryNextAction,
      href: salesRulesHrefForFund(),
    } : null,
    missingFreshnessItems.length || staleFreshnessItems.length ? {
      key: 'freshness',
      lane: '降级为刷新证据样本',
      severity: staleFreshnessItems.length ? 'high' as const : 'medium' as const,
      reason: `${[...staleFreshnessItems, ...missingFreshnessItems].map((item) => item.title).slice(0, 3).join('、')} 不满足今日复核要求。`,
      nextAction: '刷新净值、销售规则、持仓或回放后，再恢复研究判断。',
      href: freshnessPrimaryAction?.href || null,
    } : null,
    alternativeReadyFunds.length > 0 && !reportSalesRuleBlocked ? {
      key: 'alternative',
      lane: '降级为横评候选',
      severity: 'medium' as const,
      reason: `已有 ${alternativeReadyFunds.length} 只同画像替代候选可比较，单基金不能直接升级为研究复核结论。`,
      nextAction: alternativeComparisonHref ? '先打开横向比较，确认是否仍领先。' : '扩大同类样本后再比较。',
      href: alternativeComparisonHref || null,
    } : null,
    holdingExposureDecision.status === 'verify' ? {
      key: 'holding-exposure',
      lane: '降级为持仓解释样本',
      severity: 'medium' as const,
      reason: holdingExposureDecision.primaryRisk,
      nextAction: holdingExposureDecision.nextAction,
      href: null as string | null,
    } : null,
    blockedProfileCount > 0 && !detailGate.hardBlocks.length ? {
      key: 'profile-specific',
      lane: '限定画像候选',
      severity: 'low' as const,
      reason: `${blockedProfileCount} 个风险画像会触发硬阻断，不是通用候选。`,
      nextAction: '保留当前画像结论，切换画像时重新诊断。',
      href: '#fund-profile-sensitivity-matrix',
    } : null,
  ].filter((item): item is NonNullable<typeof item> => Boolean(item))
  const effectivePurchaseDowngradeQueue = purchaseDowngradeQueue.length
    ? purchaseDowngradeQueue
    : [{
        key: 'keep-research',
        lane: '保持研究复核候选',
        severity: 'low' as const,
        reason: '当前未识别需要立即降级的触发项；仍需复核销售平台实时规则。',
      nextAction: savedReportId ? '查看已保存报告并做材料复核。' : '保存研究复核报告固定证据口径。',
        href: savedReportId ? `/reports/${savedReportId}` : null,
      }]
  const singleFundCounterEvidenceChecks = [
    {
      key: 'return-chasing',
      title: '收益榜反证',
      status: detailGate.annualReturn === null ? 'verify' as const : detailGate.maxDrawdown !== null && Math.abs(detailGate.maxDrawdown) > detailGate.riskBudget ? 'blocked' as const : 'pass' as const,
      evidence: `近一年收益 ${formatPercent(detailGate.annualReturn)}；最大回撤 ${formatPercent(detailGate.maxDrawdown)}；画像预算 ${formatPercent(-detailGate.riskBudget)}`,
      counterQuestion: '如果只是因为近期收益靠前才看它，最大回撤和费用后回放能否解释这笔风险？',
      eliminationLine: '回撤超过当前画像预算，或真实回放缺失时，不能因收益亮眼进入正式研究候选。',
      nextAction: purchaseSimulation ? '用真实净值回放复核收益是否来自可承受波动。' : '先跑真实净值回放，再比较费用后收益和回撤。',
      href: null as string | null,
    },
    {
      key: 'sales-rule',
      title: '销售可执行反证',
      status: reportSalesRuleBlocked ? 'blocked' as const : salesRulesReady ? 'pass' as const : 'verify' as const,
      evidence: salesRuleHardGapCount === null ? '销售规则硬缺口待扫描' : `销售规则硬缺口 ${salesRuleHardGapCount} 项；${executionAmountGate?.label || '金额门禁待核'}`,
      counterQuestion: '如果今天真要按这个金额研究，它是否开放、金额是否可执行、R1-R5 是否有 30 天来源背书？',
      eliminationLine: '销售规则/R1-R5、限购、起购或定投门禁未清零前，直接淘汰出正式研究候选。',
      nextAction: salesRuleEvidenceCopy.primaryNextAction,
      href: salesRulesHrefForFund(),
    },
    {
      key: 'cost-share-class',
      title: '份额成本反证',
      status: shareClassInfo?.siblingCount && shareClassPurchaseAdvice.warnings.length === 0 ? 'pass' as const : 'verify' as const,
      evidence: shareClassInfo?.siblingCount
        ? `同基金 ${shareClassInfo.siblingCount} 个份额；${shareClassPurchaseAdvice.title}；${shareClassPurchaseAdvice.warnings[0] || '未见份额成本硬缺口'}`
        : '同基金 A/C/I/H 份额仍待检索或确认',
      counterQuestion: '当前份额是否真是这笔金额、这个持有期下成本更低且门槛可执行的份额？',
      eliminationLine: '存在更适配份额且当前份额金额门禁/费用证据不足时，当前份额不能作为正式候选。',
      nextAction: shareClassInfo?.siblingCount ? (shareClassPurchaseAdvice.warnings[0] || '完成同基金份额成本复核。') : '先检索同基金份额并补齐费用、赎回和金额门禁。',
      href: shareClassComparisonHref || null,
    },
    {
      key: 'manager-holding',
      title: '经理与持仓归因反证',
      status: holdingExposureDecision.status === 'done' ? 'pass' as const : 'verify' as const,
      evidence: `${managerSummary}；${holdingExposureDecision.label}；${holdingExposureDecision.primaryRisk}`,
      counterQuestion: '收益到底来自经理可复用能力，还是行业/个股暴露、短期风格或持仓集中带来的偶然结果？',
      eliminationLine: '经理任期、持仓暴露或能力圈解释不足时，不得只凭经理名气或历史收益推进。',
      nextAction: holdingExposureDecision.nextAction,
      href: null as string | null,
    },
    {
      key: 'alternative',
      title: '同类替代反证',
      status: alternativeReadyFunds.length > 0 && !reportSalesRuleBlocked ? 'verify' as const : alternativeFunds.length ? 'verify' as const : 'pass' as const,
      evidence: alternativeReadyFunds.length
        ? `已有 ${alternativeReadyFunds.length} 只可比替代；${alternativeDecisionBrief.verdict}`
        : alternativeFunds.length
          ? `找到 ${alternativeFunds.length} 只替代但规则仍待补`
          : '暂未形成可比替代样本',
      counterQuestion: '有没有同画像、同类型、销售规则更干净且回撤/费用更优的基金能替代它？',
      eliminationLine: '被同画像替代在费用后回放、回撤、证据完整度或销售门禁上明显打败时，应退出首选候选。',
      nextAction: alternativeDecisionBrief.next,
      href: alternativeComparisonHref || alternativeSalesRulesHref || null,
    },
  ]
  const singleFundEliminationLine = (() => {
    const blockedCheck = singleFundCounterEvidenceChecks.find((item) => item.status === 'blocked')
    const verifyChecks = singleFundCounterEvidenceChecks.filter((item) => item.status === 'verify')
    if (blockedCheck) {
      return {
        tone: 'rose' as const,
        label: '退出正式研究候选',
        reason: blockedCheck.eliminationLine,
        nextAction: blockedCheck.nextAction,
        href: blockedCheck.href,
      }
    }
    if (formalReportBlocked || verifyChecks.length >= 2) {
      return {
        tone: 'amber' as const,
        label: '降级为补证观察',
        reason: `${verifyChecks.slice(0, 2).map((item) => item.title).join('、') || formalReportBlockSummary} 尚未通过反证核查。`,
        nextAction: verifyChecks[0]?.nextAction || '先补齐正式研究门禁证据，再重新诊断。',
        href: verifyChecks[0]?.href || null,
      }
    }
    return {
      tone: 'emerald' as const,
      label: '可保留研究候选',
      reason: '当前未触发单基金淘汰线，但仍必须保留销售平台实时复核和替代横评边界。',
      nextAction: savedReportId ? '查看报告并做销售平台材料复核。' : '保存研究复核报告，固定证据口径。',
      href: savedReportId ? `/reports/${savedReportId}` : null,
    }
  })()
  const singleFundCounterEvidenceTsv = [
    ['核查项', '状态', '已知证据', '反证问题', '淘汰线', '下一步', '入口', '硬边界'],
    ...singleFundCounterEvidenceChecks.map((item) => [
      item.title,
      item.status === 'blocked' ? '阻断' : item.status === 'verify' ? '待复核' : '通过',
      item.evidence,
      item.counterQuestion,
      item.eliminationLine,
      item.nextAction,
      item.href || '',
      '本清单只服务基金筛选、基金分析和研究复核；不得输出申赎操作指令。',
    ]),
    [
      '单基金淘汰线',
      singleFundEliminationLine.label,
      singleFundEliminationLine.reason,
      '如果反证无法排除，是否还应继续占用首选候选位置？',
      '任一硬阻断未解除，或被同画像替代明确打败，应退出正式研究候选。',
      singleFundEliminationLine.nextAction,
      singleFundEliminationLine.href || '',
      '反证未闭环前不能保存或沿用正式研究复核结论。',
    ],
  ].map((row) => row.map(onePageEvidenceTsvCell).join('\t')).join('\n')
  const purchaseScoreCapAudit = (() => {
    const lostByCap = Math.max(0, rawPurchaseDecisionScore - purchaseDecisionScore)
    const weakFactors = purchaseDecisionBreakdown
      .filter((item) => item.score < 65)
      .sort((left, right) => left.score - right.score)
      .slice(0, 4)
    const unlockSteps = [
      reportSalesRuleBlocked ? '补齐销售规则/R1-R5、申赎字段、来源日期和复查队列' : '',
      formalReportBlocked && !reportSalesRuleBlocked ? '补齐正式研究复核报告门禁：净值回放、横评、持仓或成本证据' : '',
      professionalScoreMissing ? '补基金专业评分，缺失项不按中性分处理' : '',
      !purchaseSimulation ? '跑真实净值持有体验回放，不能用静态收益替代持有体验' : '',
      holdingExposureDecision.status !== 'done' ? '补最新季报持仓，解释行业/个股暴露' : '',
      alternativeReadyFunds.length > 0 && !reportSalesRuleBlocked ? '完成同画像替代横评，确认是否仍领先' : '',
    ].filter(Boolean)
    const auditTone = detailGate.level === 'blocked' || lostByCap >= 30
      ? 'rose'
      : formalReportBlocked || lostByCap > 0 || weakFactors.length
        ? 'amber'
        : 'emerald'

    return {
      rawScore: rawPurchaseDecisionScore,
      finalScore: purchaseDecisionScore,
      lostByCap,
      capReason: purchaseDecisionCapReason,
      weakFactors,
      unlockSteps: unlockSteps.length ? unlockSteps : ['当前未触发结构化封顶；正式研究复核前仍需销售平台实时复核'],
      auditTone,
      verdict: lostByCap > 0
        ? '分数被硬门禁封顶'
        : weakFactors.length
          ? '未封顶但有薄弱项'
          : '当前未触发封顶',
      boundary: '研究复核分只用于基金研究排序；封顶项未解除前，高分也不能进入正式研究候选或保存正式研究复核结论。',
    }
  })()
  const buyWorkflowSteps = [
    {
      title: '1. 适当性门禁',
      status: detailGate.hardBlocks.length ? 'blocked' as const : detailGate.cautionFlags.length ? 'verify' as const : 'done' as const,
      label: detailGate.label,
      description: `${detailGate.profileLabel} · ${detailGate.horizonLabel} · ${detailGate.purchasePlanLabel}；历史回撤 ${formatPercent(detailGate.maxDrawdown)}，预算 ${formatPercent(-detailGate.riskBudget)}。`,
      actionLabel: '切换画像复核',
      actionHref: null,
    },
    {
      title: '2. 销售规则',
      status: salesRulesReady ? 'done' as const : 'verify' as const,
      label: salesRulesReady ? '可用于研究复核' : salesRuleHardGapCount === null ? '硬缺口待扫描' : `先补 ${salesRuleHardGapCount} 项硬缺口`,
      description: `申购状态 ${detailGate.operationLabel}；风险等级 ${detailGate.salesRiskLevel === null ? '待补' : `R${detailGate.salesRiskLevel}`}；费率/限购 ${detailGate.feeSummary}；硬缺口 ${salesRuleHardGapCount ?? '待扫描'} 项。`,
      actionLabel: salesRulesReady ? '查看销售规则' : '补销售规则',
      actionHref: salesRulesHrefForFund(),
    },
    {
      title: '3. 持有体验回放',
      status: purchaseSimulation ? 'done' as const : 'pending' as const,
      label: purchaseSimulation ? `${purchaseSimulation.period.observations} 条净值样本` : '等待真实净值测算',
      description: purchaseSimulation
        ? `一次性 ${formatPercent(purchaseSimulation.lumpSum.returnRate)} / 定投 ${formatPercent(purchaseSimulation.sip.returnRate)}；${feeAdjustedCoverageLabel}，费用后 ${formatPercent(lumpSumFeeAdjustedReturn)} / ${formatPercent(sipFeeAdjustedReturn)}。`
        : '需要真实净值序列才能评估持有后可能经历的收益、回撤和月度胜率。',
      actionLabel: '刷新测算',
      actionHref: null,
    },
    {
      title: '4. 同类替代比较',
      status: alternativeWorkflowStatus,
      label: alternativeWorkflowLabel,
      description: alternativeWorkflowDescription,
      actionLabel: alternativeWorkflowActionLabel,
      actionHref: alternativeWorkflowActionHref,
    },
    {
      title: '5. 持仓暴露',
      status: holdingExposureDecision.status,
      label: holdingExposureDecision.label,
      description: `${holdingExposureDecision.primaryRisk}；${holdingExposureDecision.nextAction}。`,
      actionLabel: holdingExposureDecision.status === 'done' ? '查看持仓证据' : '补持仓证据',
      actionHref: null,
    },
    {
      title: '6. 研究留痕',
      status: formalReportBlocked ? 'verify' as const : savedReportId ? 'done' as const : 'pending' as const,
      label: formalReportBlocked ? '正式报告待补证' : savedReportId ? '已保存报告' : '尚未保存研究复核报告',
      description: formalReportBlocked
        ? `${formalReportBlockSummary}；补齐前只保留一页纸摘要，不生成正式研究复核报告。`
        : savedReportId
        ? '研究复核报告已进入本地研究报告库，可回溯证据、参数和不构成建议声明。'
        : '研究复核前应保存一份本地报告，固定当时画像、销售规则、净值回放和证据缺口。',
      actionLabel: formalReportBlocked ? (reportSalesRuleBlocked ? '先补销售规则' : !purchaseSimulation ? '先跑回放' : '继续补证') : savedReportId ? '查看报告' : '保存报告',
      actionHref: formalReportBlocked ? (reportSalesRuleBlocked ? salesRulesHrefForFund() : null) : savedReportId ? `/reports/${savedReportId}` : null,
    },
  ]
  const firstBlockedTradeRule = salesRuleChecklist.find((item) => item.status === 'blocked')
  const firstMissingTradeRule = salesRuleChecklist.find((item) => item.status === 'verify')
  const purchasePriorityAction = (() => {
    if (firstBlockedTradeRule) {
      return {
        tone: 'rose' as const,
        badge: '先处理阻断',
        title: firstBlockedTradeRule.title,
        description: firstBlockedTradeRule.detail,
        why: '这类问题会直接影响真实可执行性或适当性，不能用收益、评分或经理优势覆盖。',
        actionLabel: firstBlockedTradeRule.title === '风险等级' ? '切换画像复核' : '补销售规则',
        actionHref: firstBlockedTradeRule.title === '风险等级' ? null : salesRulesHrefForFund(),
        actionKind: firstBlockedTradeRule.title === '风险等级' ? 'profile' as const : 'link' as const,
        relatedItems: [firstBlockedTradeRule.label],
      }
    }
    if (salesRuleHardGapCount === null) {
      return {
        tone: 'amber' as const,
        badge: '先完成扫描',
        title: '销售规则硬缺口扫描',
        description: salesRuleEvidenceCopy.scanDescription,
        why: '扫描完成前不能判断这只基金是否能进入研究清单或正式研究复核报告。',
        actionLabel: salesRuleGapLoading ? '扫描中...' : '重扫销售规则',
        actionHref: null,
        actionKind: 'scanSalesRule' as const,
        relatedItems: ['申购状态', '申购费率', '赎回规则', '风险等级'],
      }
    }
    if (salesRuleHardGapCount > 0 || firstMissingTradeRule) {
      const missingItems = salesRuleGapMissingItems.length
        ? salesRuleGapMissingItems
        : firstMissingTradeRule
          ? [firstMissingTradeRule.title]
          : []
      return {
        tone: 'amber' as const,
        badge: '先补规则',
        title: missingItems[0] || '销售规则硬缺口',
        description: salesRuleGap?.nextAction || firstMissingTradeRule?.detail || '补齐销售平台可追溯规则后，再进入研究清单和正式报告。',
        why: salesRuleEvidenceCopy.gateWhy,
        actionLabel: `补规则 ${salesRuleHardGapCount || 1} 项`,
        actionHref: salesRulesHrefForFund(),
        actionKind: 'link' as const,
        relatedItems: missingItems.slice(0, 6),
      }
    }
    if (!purchaseSimulation) {
      return {
        tone: 'blue' as const,
        badge: '补持有体验',
        title: '真实净值回放',
        description: '需要用当前金额和研究方式假设测算收益、回撤、月度胜率与费用后结果。',
        why: '研究选择不能只看静态收益排名，必须看研究假设持有路径下可能经历的波动。',
        actionLabel: simulationLoading ? '测算中...' : '刷新测算',
        actionHref: null,
        actionKind: 'simulate' as const,
        relatedItems: [detailGate.purchasePlanLabel, `${simulationForm.months || 12} 个月`, feeAdjustedCoverageLabel],
      }
    }
    if (!alternativeComparisonHref && alternativeWorkflowStatus !== 'done') {
      return {
        tone: 'slate' as const,
        badge: '补横向比较',
        title: '同类替代比较',
        description: alternativeWorkflowDescription,
        why: '单基金判断容易高估个体优势，研究复核前应至少看同画像同类型替代。',
        actionLabel: alternativeWorkflowActionLabel,
        actionHref: alternativeWorkflowActionHref,
        actionKind: 'link' as const,
        relatedItems: alternativeSearchMeta?.attempts.slice(0, 3) || [fund.type || '同类型基金'],
      }
    }
    if (!savedReportId) {
      return {
        tone: 'emerald' as const,
        badge: '形成留痕',
        title: '保存研究复核报告',
        description: '固定当前画像、销售规则、净值回放、横向比较和证据缺口，方便后续复核。',
        why: '正式研究复核需要可追溯记录，避免事后只记得结论、忘记证据边界。',
        actionLabel: reportSaving ? '保存中...' : '保存报告',
        actionHref: null,
        actionKind: 'saveReport' as const,
        relatedItems: ['画像参数', '销售规则', '费用后回放', '不构成建议声明'],
      }
    }
    return {
      tone: 'emerald' as const,
      badge: '可进入复核',
      title: '进入最终研究复核',
      description: '当前核心研究复核证据已形成，仍需打开销售平台复核实时状态。',
      why: '系统只负责基金研究、选择和证据留痕，不替代销售平台最终适当性与销售平台确认。',
      actionLabel: '查看报告',
      actionHref: `/reports/${savedReportId}`,
      actionKind: 'link' as const,
      relatedItems: ['实时申购状态', '实时费率', '销售平台正式适当性'],
    }
  })()
  const purchasePriorityClass = purchasePriorityAction.tone === 'rose'
    ? 'border-rose-100 bg-rose-50 text-rose-900'
    : purchasePriorityAction.tone === 'amber'
      ? 'border-amber-100 bg-amber-50 text-amber-900'
      : purchasePriorityAction.tone === 'blue'
        ? 'border-blue-100 bg-blue-50 text-blue-900'
        : purchasePriorityAction.tone === 'emerald'
          ? 'border-emerald-100 bg-emerald-50 text-emerald-900'
          : 'border-slate-100 bg-slate-50 text-slate-900'
  const buyBeforeHealthCheck = (() => {
    const candidateReady = canEnterCandidatePool(fund) && !formalReportBlocked
    const alternativeReady = alternativeReadyFunds.length >= 2 || Boolean(alternativeComparisonHref)
    const healthItems = [
      {
        title: '能不能进入研究候选',
        status: candidateReady ? 'done' as const : detailGate.level === 'blocked' ? 'blocked' as const : 'verify' as const,
        label: candidateReady ? '可以进入观察候选' : formalReportBlocked ? '暂不进入研究候选' : detailGate.label,
        detail: candidateReady
          ? '销售规则、适当性和正式报告前置门禁暂未发现硬阻断；仍需最终复核销售平台实时状态。'
          : candidatePoolBlockReason || formalReportBlockSummary || detailGate.hardBlocks[0] || detailGate.cautionFlags[0] || '仍有研究复核证据待补。',
      },
      {
        title: '销售规则/R1-R5是否过关',
        status: salesRulesReady ? 'done' as const : reportSalesRuleBlocked ? 'blocked' as const : 'verify' as const,
        label: salesRulesReady ? '规则相对完整' : salesRuleHardGapCount === null ? '硬缺口待扫描' : `仍缺 ${salesRuleHardGapCount} 项`,
        detail: salesRulesReady
          ? '申购、费率、赎回、限购和销售风险等级可进入研究复核，但形成正式结论前仍要复核实时页面。'
          : salesRuleEvidenceCopy.primaryNextAction,
      },
      {
        title: '持有体验是否有真实回放',
        status: purchaseSimulation ? 'done' as const : 'verify' as const,
        label: purchaseSimulation ? holdingExperience.label : '净值回放待补',
        detail: purchaseSimulation
          ? `${detailGate.purchasePlanLabel}收益 ${formatPercent(simulationReturnForPlan)}，回撤 ${formatPercent(simulationDrawdownForPlan)}，样本 ${purchaseSimulation.period.observations} 条。`
          : '未完成真实净值回放时，不能只凭长期收益、排名或评分进入研究候选。',
      },
      {
        title: '有没有同画像替代比较',
        status: alternativeReady ? 'done' as const : 'verify' as const,
        label: alternativeReady ? '替代样本可比较' : '替代横评待补',
        detail: alternativeReady
          ? `已形成 ${alternativeReadyFunds.length || 2} 只同画像替代候选；研究复核需比较收益、回撤、费用和销售规则。`
          : alternativeWorkflowDescription,
      },
    ]
    const blockedCount = healthItems.filter((item) => item.status === 'blocked').length
    const verifyCount = healthItems.filter((item) => item.status === 'verify').length
    const doneCount = healthItems.filter((item) => item.status === 'done').length
    const headline = blockedCount
      ? '研究复核体检：存在硬阻断'
      : verifyCount
        ? '研究复核体检：先补证再比较'
        : '研究复核体检：可进入最终复核'
    const summary = blockedCount
      ? '这只基金当前不能进入研究候选；先处理销售规则、适当性或风险预算硬阻断。'
      : verifyCount
        ? `4 项研究复核体检已完成 ${doneCount} 项，仍有 ${verifyCount} 项需要补证或横评。`
        : '核心研究复核证据已形成，但系统只提供基金研究结论，最终仍需销售平台实时适当性和申赎规则确认。'
    return {
      headline,
      summary,
      healthItems,
      doneCount,
      verifyCount,
      blockedCount,
      primaryActionLabel: purchasePriorityAction.actionLabel,
      primaryActionHref: purchasePriorityAction.actionHref,
      primaryActionKind: purchasePriorityAction.actionKind,
    }
  })()

  const copyOnePageMemo = async () => {
    try {
      await navigator.clipboard.writeText(onePageMemo)
      setSummaryCopied(true)
      setBannerMessage('已复制研究复核一页纸，可粘贴到研究记录或研究清单备注。')
      window.setTimeout(() => setSummaryCopied(false), 1600)
    } catch (error) {
      console.error('复制研究复核一页纸失败:', error)
      setErrorMessage('复制失败，请手动选中研究复核一页纸内容。')
    }
  }

  const copyOnePageEvidenceTsv = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(onePageEvidenceTsv)
      } else {
        const memoElement = document.createElement('textarea')
        memoElement.value = onePageEvidenceTsv
        memoElement.setAttribute('readonly', 'true')
        memoElement.style.position = 'fixed'
        memoElement.style.left = '-9999px'
        document.body.appendChild(memoElement)
        memoElement.select()
        document.execCommand('copy')
        document.body.removeChild(memoElement)
      }
      setBannerMessage('已复制研究复核 TSV；阻断项会保留硬边界，不作为研究结论。')
    } catch (error) {
      console.error('复制研究复核 TSV 失败:', error)
      setErrorMessage('复制失败，请改用下载 TSV 或手动复制。')
    }
  }

  const downloadOnePageEvidenceTsv = () => {
    const blob = new Blob([`\ufeff${onePageEvidenceTsv}`], { type: 'text/tab-separated-values;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${fund.windCode || fundId}_${fund.name || '基金'}_研究复核表.tsv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    setBannerMessage('已下载研究复核 TSV，可用于补证、复核和研究留痕。')
  }

  const copyAlternativeDecisionMatrixTsv = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(alternativeDecisionMatrixTsv)
      } else {
        const memoElement = document.createElement('textarea')
        memoElement.value = alternativeDecisionMatrixTsv
        memoElement.setAttribute('readonly', 'true')
        memoElement.style.position = 'fixed'
        memoElement.style.left = '-9999px'
        document.body.appendChild(memoElement)
        memoElement.select()
        document.execCommand('copy')
        document.body.removeChild(memoElement)
      }
      setBannerMessage('已复制替代横评矩阵 TSV；主基金或替代候选硬门禁未清零前不形成研究建议。')
    } catch (error) {
      console.error('复制替代横评矩阵 TSV 失败:', error)
      downloadAlternativeDecisionMatrixTsv()
      setBannerMessage('复制受限，已转下载替代横评矩阵 TSV。')
    }
  }

  const downloadAlternativeDecisionMatrixTsv = () => {
    const blob = new Blob([`\ufeff${alternativeDecisionMatrixTsv}`], { type: 'text/tab-separated-values;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${fund.windCode || fundId}_${fund.name || '基金'}_替代横评矩阵.tsv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    setBannerMessage('已下载替代横评矩阵 TSV；用于同画像替代复核，不作为申赎操作指令。')
  }

  const copySingleFundCounterEvidenceTsv = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(singleFundCounterEvidenceTsv)
      } else {
        const memoElement = document.createElement('textarea')
        memoElement.value = singleFundCounterEvidenceTsv
        memoElement.setAttribute('readonly', 'true')
        memoElement.style.position = 'fixed'
        memoElement.style.left = '-9999px'
        document.body.appendChild(memoElement)
        memoElement.select()
        document.execCommand('copy')
        document.body.removeChild(memoElement)
      }
      setBannerMessage('已复制单基金反证核查 TSV；反证未闭环前不形成研究结论。')
    } catch (error) {
      console.error('复制单基金反证核查 TSV 失败:', error)
      setErrorMessage('复制失败，请改用下载 TSV 或手动复制。')
    }
  }

  const downloadSingleFundCounterEvidenceTsv = () => {
    const blob = new Blob([`\ufeff${singleFundCounterEvidenceTsv}`], { type: 'text/tab-separated-values;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${fund.windCode || fundId}_${fund.name || '基金'}_单基金反证核查.tsv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    setBannerMessage('已下载单基金反证核查 TSV；用于研究留痕，不作为申赎操作指令。')
  }

  const prePurchaseReportParams = () => new URLSearchParams({
    profile: investorRiskProfile,
    horizon: investorHorizon,
    purchasePlan: investorPurchasePlan,
    plannedAmount: String(currentPlannedAmount()),
    months: simulationForm.months || '12',
    lumpSumAmount: simulationForm.lumpSumAmount || '10000',
    monthlyAmount: simulationForm.monthlyAmount || '1000',
  })

  const downloadPrePurchaseReport = async () => {
    if (formalReportBlocked) {
      setErrorMessage(`${fund.name} ${formalReportBlockSummary}，补齐前不生成正式研究复核报告。`)
      return
    }
    try {
      setReportGenerating(true)
      setErrorMessage(null)
      const params = prePurchaseReportParams()
      params.set('format', 'markdown')
      const response = await fetch(`/api/funds/${encodeURIComponent(fund.windCode || fundId)}/research-review-report?${params.toString()}`)
      const text = await response.text()
      if (!response.ok) {
        const payload = (() => {
          try {
            return JSON.parse(text)
          } catch {
            return {}
          }
        })()
        throw new Error(payload.error || payload.detail || '生成研究复核报告失败')
      }

      const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${fund.windCode || fundId}_${fund.name || '基金'}_研究复核报告.md`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      setBannerMessage('已生成研究复核报告，内容来自本地基金库、材料核验和真实净值回放。')
    } catch (error) {
      console.error('生成研究复核报告失败:', error)
      setErrorMessage(error instanceof Error ? error.message : '生成研究复核报告失败')
    } finally {
      setReportGenerating(false)
    }
  }

  const savePrePurchaseReport = async () => {
    if (formalReportBlocked) {
      setErrorMessage(`${fund.name} ${formalReportBlockSummary}，补齐前不保存正式研究复核报告。`)
      return
    }
    try {
      setReportSaving(true)
      setErrorMessage(null)
      const response = await fetch(`/api/funds/${encodeURIComponent(fund.windCode || fundId)}/research-review-report?${prePurchaseReportParams().toString()}`, {
        method: 'POST',
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.error || payload.detail || '保存研究复核报告失败')
      }
      setSavedReportId(payload.reportId || payload.id)
      setBannerMessage('已保存研究复核报告到本地研究报告库。')
    } catch (error) {
      console.error('保存研究复核报告失败:', error)
      setErrorMessage(error instanceof Error ? error.message : '保存研究复核报告失败')
    } finally {
      setReportSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <Link href={sourceReturnHref} className="inline-flex items-center text-gray-600 hover:text-gray-900" data-testid="fund-detail-return-link">
          <ArrowLeft className="mr-2 h-4 w-4" />
          返回列表
        </Link>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void addToCandidatePool()}
            disabled={addingToPool || candidatePoolLoading || !fund || formalReportBlocked || !canEnterCandidatePool(fund) || Boolean(candidatePoolMember)}
            title={candidatePoolBlockReason || '加入研究清单'}
            className={`inline-flex items-center rounded-lg border px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50 ${
              candidatePoolMember && formalReportBlocked
                ? 'border-amber-300 text-amber-700 hover:bg-amber-50'
                : 'border-emerald-300 text-emerald-700 hover:bg-emerald-50'
            }`}
          >
            {candidatePoolMember
              ? formalReportBlocked
                ? `研究清单待补证 · ${poolStatusLabels[candidatePoolMember.status] || candidatePoolMember.status}`
                : `已在研究清单 · ${poolStatusLabels[candidatePoolMember.status] || candidatePoolMember.status}`
              : candidatePoolLoading
                ? '检查研究清单...'
                : formalReportBlocked
                  ? '补证后入池'
                : fund && !canEnterCandidatePool(fund)
                  ? '不可入池'
                  : addingToPool ? '加入中...' : '加入研究清单'}
          </button>
          <Link href={`/analysis/fund?fundId=${fund.id}`} className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">
            <Sparkles className="h-4 w-4" /> 基金研究
          </Link>
          <Link href={canonicalResearchHref('/rankings')} className="inline-flex items-center rounded-lg border border-amber-300 px-4 py-2 text-sm text-amber-700 hover:bg-amber-50">
            回排行榜
          </Link>
          <Link href={salesRulesHrefForFund()} className="inline-flex items-center rounded-lg border border-cyan-300 px-4 py-2 text-sm text-cyan-700 hover:bg-cyan-50">
            补销售规则
          </Link>
          <Link href="/market" className="inline-flex items-center rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
            去全市场浏览器
          </Link>
        </div>
      </div>

      {bannerMessage && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {bannerMessage}
          <Link href="/market?source=research-list" className="ml-2 font-medium text-emerald-800 hover:text-emerald-900">查看研究清单</Link>
        </div>
      )}

      {candidatePoolMember && formalReportBlocked ? (
        <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">
          <AlertCircle className="mt-0.5 h-4 w-4" />
          <span>
            {fund.name} 已存在于研究清单，但当前{formalReportBlockSummary}；在补齐前只能作为待补证研究对象，不能继续作为研究候选或保存正式研究复核报告。
            <Link href={reportSalesRuleBlocked ? salesRulesHrefForFund() : '#fund-buy-before-freshness-radar'} className="ml-2 font-medium text-amber-900 hover:text-amber-950">
              {reportSalesRuleBlocked ? '去补销售规则' : '查看补证原因'}
            </Link>
          </span>
        </div>
      ) : null}

      {errorMessage && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <AlertCircle className="mt-0.5 h-4 w-4" />
          <span>{errorMessage}</span>
        </div>
      )}

      <div className="rounded-lg bg-white p-6 shadow">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{fund.name}</h1>
            <p className="mt-1 text-sm text-gray-500">代码: {fund.windCode}</p>
          </div>
          <span className="rounded-full bg-blue-100 px-3 py-1 text-sm text-blue-800">{fund.type}</span>
          {candidatePoolMember ? (
            <span className={`ml-2 rounded-full px-3 py-1 text-sm ${
              formalReportBlocked ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'
            }`}>
              {formalReportBlocked ? '研究清单待补证' : '研究清单'}：{poolStatusLabels[candidatePoolMember.status] || candidatePoolMember.status}
            </span>
          ) : null}
        </div>

        {!errorMessage ? (
          <button
            type="button"
            onClick={() => void fetchFundDetail()}
            className="mt-4 inline-flex rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            刷新详情
          </button>
        ) : null}

        <div className="mt-4 rounded-xl border border-blue-100 bg-blue-50 p-4 text-sm text-blue-800">
          这个页面适合回看单只基金的信任度、走势和历史报告；如果要继续横向筛选，请回基金排行榜；如果申赎证据不足，请补销售规则。
        </div>

        <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-4">
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <TrendingUp className="h-6 w-6 text-blue-600" />
            </div>
            <div className="ml-3">
              <p className="text-sm text-gray-500">最新净值</p>
              <p className="text-lg font-semibold text-gray-900">{fund.nav ? Number(fund.nav).toFixed(4) : '-'}</p>
              {fund.navDate && <p className="text-xs text-gray-400">{formatDateText(fund.navDate)}</p>}
            </div>
          </div>

          <div className="flex items-start">
            <div className="flex-shrink-0">
              <DollarSign className="h-6 w-6 text-green-600" />
            </div>
            <div className="ml-3">
              <p className="text-sm text-gray-500">基金规模</p>
              <p className="text-lg font-semibold text-gray-900">{fund.totalAsset ? `${Number(fund.totalAsset).toFixed(2)} 亿` : '-'}</p>
            </div>
          </div>

          <div className="flex items-start">
            <div className="flex-shrink-0">
              <Calendar className="h-6 w-6 text-purple-600" />
            </div>
            <div className="ml-3">
              <p className="text-sm text-gray-500">成立日期</p>
              <p className="text-lg font-semibold text-gray-900">{formatDateText(fund.establishmentDate)}</p>
            </div>
          </div>

          <div className="flex items-start">
            <div className="flex-shrink-0">
              <TrendingUp className="h-6 w-6 text-orange-600" />
            </div>
            <div className="ml-3">
              <p className="text-sm text-gray-500">基金经理</p>
              <p className="text-lg font-semibold text-gray-900">
                {fund.managers?.length ? fund.managers.map((manager) => manager.name || manager.managerId).join(' / ') : `${fund.managerIds.length} 位`}
              </p>
              <p className="mt-1 text-xs text-gray-500">
                {fund.managers?.length
                  ? fund.managers.map((manager) => {
                    const tenure = manager.managementYears == null ? '任期待核' : `${manager.managementYears.toFixed(1)}年`
                    return `${manager.education || '学历待补'} · ${tenure}`
                  }).join('；')
                  : '经理明细待同步'}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-indigo-100 bg-white p-5 shadow" data-testid="fund-detail-methodology-focus">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700 ring-1 ring-indigo-100">
              <ClipboardCheck className="h-3.5 w-3.5" />
              研究模板
            </div>
            <h2 className="mt-3 text-lg font-semibold text-slate-950">{methodologyFocus.templateName}</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">{methodologyFocus.matchRationale}</p>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
            methodologyFocus.readyForFormalReview ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
          }`}>
            {methodologyFocus.readyForFormalReview ? '方法论证据可复核' : `方法论缺口 ${methodologyFocus.methodologyMissingEvidenceFields.length} 项`}
          </span>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {methodologyFocus.dimensions.slice(0, 6).map((dimension) => (
            <div key={dimension.key} className={`rounded-xl border p-3 text-sm ${
              dimension.hardGate ? 'border-indigo-100 bg-indigo-50/60' : 'border-slate-100 bg-slate-50'
            }`}>
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-slate-900">{dimension.name}</div>
                <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-100">
                  权重 {dimension.weight}
                </span>
              </div>
              <div className="mt-2 text-xs leading-5 text-slate-600">{dimension.reason}</div>
              {dimension.hardGate ? <div className="mt-2 text-[11px] font-semibold text-indigo-700">核心研究维度</div> : null}
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">
          <span className="font-semibold">方法论缺口：</span>
          {methodologyFocus.methodologyMissingEvidenceFields.length ? methodologyFocus.methodologyMissingEvidenceFields.slice(0, 10).join('、') : '暂无'}
        </div>
        <div className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600">
          {methodologyFocus.boundary}
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-emerald-100 bg-white shadow" data-testid="fund-buy-before-health-check">
        <div className="flex flex-col gap-4 border-b border-emerald-100 bg-emerald-950 px-5 py-4 text-white lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs text-emerald-100 ring-1 ring-white/10">
              <ShieldCheck className="h-3.5 w-3.5" />
              单基金研究复核体检
            </div>
            <h2 className="mt-3 text-xl font-semibold">{buyBeforeHealthCheck.headline}</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-emerald-100">{buyBeforeHealthCheck.summary}</p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            {buyBeforeHealthCheck.primaryActionHref ? (
              <Link href={buyBeforeHealthCheck.primaryActionHref} className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-emerald-950 hover:bg-emerald-50">
                {buyBeforeHealthCheck.primaryActionLabel}
              </Link>
            ) : buyBeforeHealthCheck.primaryActionKind === 'scanSalesRule' ? (
              <button
                type="button"
                onClick={() => void fetchSalesRuleGap(fund.windCode)}
                disabled={salesRuleGapLoading}
                className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-emerald-950 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {buyBeforeHealthCheck.primaryActionLabel}
              </button>
            ) : buyBeforeHealthCheck.primaryActionKind === 'simulate' ? (
              <button
                type="button"
                onClick={() => void fetchPurchaseSimulation(fund.windCode, simulationForm)}
                disabled={simulationLoading}
                className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-emerald-950 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {buyBeforeHealthCheck.primaryActionLabel}
              </button>
            ) : buyBeforeHealthCheck.primaryActionKind === 'saveReport' ? (
              <button
                type="button"
                onClick={() => void savePrePurchaseReport()}
                disabled={reportSaving || formalReportBlocked}
                className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-emerald-950 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {formalReportBlocked ? '补证后保存' : buyBeforeHealthCheck.primaryActionLabel}
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => void copyOnePageMemo()}
              className="rounded-lg border border-white/20 px-3 py-2 text-xs font-semibold text-white hover:bg-white/10"
            >
              复制一页纸
            </button>
          </div>
        </div>
        <div className="grid gap-3 bg-emerald-50/50 p-4 md:grid-cols-4">
          <div className="rounded-2xl bg-white px-4 py-3 ring-1 ring-emerald-100">
            <div className="text-xs text-slate-500">已完成</div>
            <div className="mt-1 text-2xl font-bold text-emerald-800">{buyBeforeHealthCheck.doneCount}</div>
          </div>
          <div className="rounded-2xl bg-white px-4 py-3 ring-1 ring-amber-100">
            <div className="text-xs text-slate-500">待补证/横评</div>
            <div className="mt-1 text-2xl font-bold text-amber-700">{buyBeforeHealthCheck.verifyCount}</div>
          </div>
          <div className="rounded-2xl bg-white px-4 py-3 ring-1 ring-rose-100">
            <div className="text-xs text-slate-500">硬阻断</div>
            <div className="mt-1 text-2xl font-bold text-rose-700">{buyBeforeHealthCheck.blockedCount}</div>
          </div>
          <div className="rounded-2xl bg-white px-4 py-3 ring-1 ring-slate-100">
            <div className="text-xs text-slate-500">当前画像</div>
            <div className="mt-1 text-sm font-semibold text-slate-950">{detailGate.profileLabel} · {detailGate.horizonLabel} · {detailGate.purchasePlanLabel}</div>
          </div>
        </div>
        <div className="grid gap-3 p-5 md:grid-cols-2 xl:grid-cols-4">
          {buyBeforeHealthCheck.healthItems.map((item) => {
            const itemClassName = item.status === 'done'
              ? 'border-emerald-100 bg-emerald-50 text-emerald-950'
              : item.status === 'blocked'
                ? 'border-rose-100 bg-rose-50 text-rose-950'
                : 'border-amber-100 bg-amber-50 text-amber-950'
            return (
              <div key={item.title} className={`rounded-2xl border p-4 ${itemClassName}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="text-sm font-semibold">{item.title}</div>
                  <span className="rounded-full bg-white/80 px-2 py-0.5 text-[11px] font-semibold ring-1 ring-black/5">
                    {item.status === 'done' ? '已过' : item.status === 'blocked' ? '阻断' : '待补'}
                  </span>
                </div>
                <div className="mt-3 text-base font-semibold">{item.label}</div>
                <p className="mt-2 text-xs leading-5 opacity-80">{item.detail}</p>
              </div>
            )
          })}
        </div>
        <div className="border-t border-emerald-100 bg-emerald-50 px-5 py-3 text-xs leading-5 text-emerald-900">
          边界：研究复核体检只服务基金研究和选择；销售规则、R1-R5 来源、真实净值回放或替代横评缺失时，不输出申赎操作指令，也不绕过正式研究复核报告门禁。
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl bg-slate-950 shadow-xl" data-testid="fund-purchase-decision-strip">
        <div className="grid gap-0 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="p-6 text-white">
            <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs text-blue-100 ring-1 ring-white/10">
              <ShieldCheck className="h-3.5 w-3.5" />
              单基金研究判断 · {detailGate.profileLabel} · {detailGate.horizonLabel} · {detailGate.purchasePlanLabel}
            </div>
            <div className="mt-5 flex flex-wrap items-end gap-4">
              <div>
                <div className="text-5xl font-bold tracking-tight">{purchaseDecisionScore}</div>
                <div className="mt-1 text-xs text-slate-300">研究复核分</div>
              </div>
              <span className={`mb-2 rounded-full px-3 py-1 text-xs font-semibold ${purchaseDecisionClass}`}>
                {purchaseDecisionLabel}
              </span>
            </div>
            <p className="mt-5 text-sm leading-6 text-slate-200">
              {purchaseDecisionSummary}
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Link
                href={salesRulesHrefForFund()}
                className="rounded-lg bg-cyan-300 px-3 py-2 text-xs font-semibold text-slate-950 hover:bg-cyan-200"
              >
                {reportSalesRuleBlocked ? '先补销售规则' : '查看销售规则'}
              </Link>
              <Link
                href={alternativeComparisonHref || canonicalResearchHref(`/investor-selection?profile=${investorRiskProfile}&horizon=${investorHorizon}&purchasePlan=${investorPurchasePlan}&type=${encodeURIComponent(fund.type || '')}`)}
                className="rounded-lg border border-white/20 px-3 py-2 text-xs font-semibold text-white hover:bg-white/10"
              >
                {alternativeComparisonHref ? '同类横向比较' : '找同类替代'}
              </Link>
              <button
                type="button"
                onClick={() => void addToCandidatePool()}
                disabled={addingToPool || candidatePoolLoading || formalReportBlocked || !canEnterCandidatePool(fund) || Boolean(candidatePoolMember)}
                title={candidatePoolBlockReason || '加入研究清单'}
                className="rounded-lg border border-emerald-300/40 px-3 py-2 text-xs font-semibold text-emerald-100 hover:bg-emerald-300/10 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {candidatePoolMember ? '已在研究清单' : formalReportBlocked ? '补证后入清单' : addingToPool ? '加入中...' : '加入研究清单'}
              </button>
            </div>
          </div>

          <div className="grid gap-3 bg-white p-6 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
              <div className="text-xs font-medium text-slate-500">销售规则门禁</div>
              <div className="mt-2 text-lg font-semibold text-slate-950">
                {salesRuleHardGapCount === null ? '待扫描' : salesRuleHardGapCount > 0 ? `缺 ${salesRuleHardGapCount} 项` : '无硬缺口'}
              </div>
              <div className="mt-2 text-xs leading-5 text-slate-600">
                {salesRuleHardGapCount && salesRuleGapMissingItems.length
                  ? salesRuleGapMissingItems.slice(0, 4).join('、')
                  : salesRulesReady
                    ? '申购、费率、风险等级和当前研究口径规则已可用于研究复核。'
                    : '销售规则证据仍需复核。'}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
              <div className="text-xs font-medium text-slate-500">持有体验</div>
              <div className="mt-2 text-lg font-semibold text-slate-950">{holdingExperience.label}</div>
              <div className="mt-2 text-xs leading-5 text-slate-600">
                {purchaseSimulation
                  ? `${detailGate.purchasePlanLabel}收益 ${formatPercent(simulationReturnForPlan)}，回撤 ${formatPercent(simulationDrawdownForPlan)}，净值样本 ${purchaseSimulation.period.observations} 条。`
                  : '等待真实净值回放，不用静态收益替代持有体验。'}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
              <div className="text-xs font-medium text-slate-500">适当性与风险</div>
              <div className="mt-2 text-lg font-semibold text-slate-950">{detailGate.label}</div>
              <div className="mt-2 text-xs leading-5 text-slate-600">
                历史回撤 {formatPercent(detailGate.maxDrawdown)}；当前画像预算 {formatPercent(-detailGate.riskBudget)}；销售风险等级 {detailGate.salesRiskLevel === null ? '待补' : `R${detailGate.salesRiskLevel}`}。
              </div>
            </div>

            <div className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
              <div className="text-xs font-medium text-slate-500">评分依据</div>
              <div className="mt-2 space-y-1 text-xs leading-5 text-slate-600">
                {purchaseDecisionReasons.slice(0, 5).map((reason) => (
                  <div key={reason}>• {reason}</div>
                ))}
              </div>
            </div>

            <div className={`rounded-2xl border p-4 md:col-span-2 ${buyDecisionRoleClass}`} data-testid="fund-buy-decision-role">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="inline-flex rounded-full bg-white/70 px-2.5 py-1 text-[11px] font-semibold ring-1 ring-black/5">
                    {buyDecisionRole.subtitle}
                  </div>
                  <div className="mt-3 text-xl font-semibold">{buyDecisionRole.label}</div>
                  <p className="mt-2 text-sm leading-6 opacity-85">{buyDecisionRole.summary}</p>
                  <p className="mt-2 text-xs leading-5 opacity-75">下一步：{buyDecisionRole.nextAction}</p>
                </div>
                <div className="grid min-w-64 gap-2 text-xs">
                  {buyDecisionRole.proofPoints.map((point) => (
                    <div key={point} className="rounded-xl bg-white/70 px-3 py-2 ring-1 ring-black/5">
                      {point}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-cyan-100 bg-cyan-50 p-4 md:col-span-2" data-testid="fund-purchase-score-breakdown">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold text-cyan-700">决策分拆解</div>
                  <div className="mt-1 text-sm font-semibold text-slate-950">
                    原始研究分 {rawPurchaseDecisionScore} → 当前研究复核分 {purchaseDecisionScore}
                  </div>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${purchaseDecisionClass}`}>
                  封顶原因：{purchaseDecisionCapReason}
                </span>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                {purchaseDecisionBreakdown.map((item) => (
                  <div key={item.label} className="rounded-xl bg-white p-3 ring-1 ring-cyan-100">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-semibold text-slate-800">{item.label}</span>
                      <span className="text-slate-500">权重 {item.weight}% · 贡献 {item.contribution.toFixed(1)}</span>
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-cyan-500"
                        style={{ width: `${Math.max(0, Math.min(100, item.score))}%` }}
                      />
                    </div>
                    <div className="mt-2 text-xs leading-5 text-slate-600">
                      分项 {Math.round(item.score)}：{item.detail}
                    </div>
                  </div>
                ))}
              </div>
              {formalReportBlocked ? (
                <div className="mt-3 rounded-xl bg-amber-100 px-3 py-2 text-xs leading-5 text-amber-900">
                  {formalReportBlockSummary}；本页只能输出研究观察结论，不能加入正式研究候选，也不能保存正式研究复核报告。
                </div>
              ) : null}
            </div>

            <div className={`rounded-2xl border p-4 md:col-span-2 ${
              purchaseScoreCapAudit.auditTone === 'rose'
                ? 'border-rose-100 bg-rose-50'
                : purchaseScoreCapAudit.auditTone === 'amber'
                  ? 'border-amber-100 bg-amber-50'
                  : 'border-emerald-100 bg-emerald-50'
            }`} data-testid="fund-purchase-score-cap-audit">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Score cap audit</div>
                  <div className="mt-1 text-lg font-semibold text-slate-950">{purchaseScoreCapAudit.verdict}</div>
                  <div className="mt-2 text-sm leading-6 text-slate-700">
                    原始研究分 {purchaseScoreCapAudit.rawScore}，当前研究复核分 {purchaseScoreCapAudit.finalScore}
                    {purchaseScoreCapAudit.lostByCap > 0 ? `，封顶扣减 ${purchaseScoreCapAudit.lostByCap} 分。` : '，当前未发生封顶扣减。'}
                  </div>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${purchaseDecisionClass}`}>
                  {purchaseScoreCapAudit.capReason}
                </span>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-xl bg-white/80 p-3 ring-1 ring-black/5">
                  <div className="text-sm font-semibold text-slate-900">薄弱分项</div>
                  <ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-slate-700">
                    {(purchaseScoreCapAudit.weakFactors.length ? purchaseScoreCapAudit.weakFactors : [{ label: '暂无低于 65 分的分项', score: purchaseDecisionScore, detail: '仍需正式研究复核。' }]).map((item) => (
                      <li key={`${item.label}-${item.score}`}>
                        {item.label} {Math.round(item.score)} 分：{item.detail}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-xl bg-white/80 p-3 ring-1 ring-black/5">
                  <div className="text-sm font-semibold text-slate-900">解锁顺序</div>
                  <ol className="mt-2 list-decimal space-y-1 pl-4 text-xs leading-5 text-slate-700">
                    {purchaseScoreCapAudit.unlockSteps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                </div>
              </div>
              <div className="mt-3 rounded-xl bg-slate-950 px-3 py-2 text-xs leading-5 text-white/90">
                {purchaseScoreCapAudit.boundary}
              </div>
            </div>

            <div className="rounded-2xl border border-violet-100 bg-violet-50 p-4 md:col-span-2" data-testid="fund-profile-sensitivity-matrix">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold text-violet-700">画像敏感性矩阵</div>
                  <div className="mt-1 text-sm font-semibold text-slate-950">换研究画像或研究方式假设后，结论是否反转</div>
                </div>
                <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-violet-800 ring-1 ring-violet-100">
                  {blockedProfileCount ? `${blockedProfileCount} 个画像硬阻断` : '未见画像硬阻断'}
                </span>
              </div>
              <p className="mt-2 text-xs leading-5 text-violet-900">
                {sensitivityConclusion}
              </p>
              <div className="mt-4 overflow-hidden rounded-xl border border-violet-100 bg-white">
                <table className="min-w-full divide-y divide-violet-100 text-xs">
                  <thead className="bg-violet-50 text-left text-violet-700">
                    <tr>
                      <th className="px-3 py-2 font-semibold">风险画像</th>
                      <th className="px-3 py-2 font-semibold">研究复核分</th>
                      <th className="px-3 py-2 font-semibold">回撤预算</th>
                      <th className="px-3 py-2 font-semibold">销售风险上限</th>
                      <th className="px-3 py-2 font-semibold">结论边界</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-violet-100">
                    {profileSensitivityRows.map((row) => (
                      <tr key={row.profile} className={row.isCurrent ? 'bg-violet-50/70' : 'bg-white'}>
                        <td className="px-3 py-2 font-semibold text-slate-900">
                          {row.profileLabel}{row.isCurrent ? '（当前）' : ''}
                        </td>
                        <td className="px-3 py-2 text-slate-700">{row.score} / 原始 {row.rawScore}</td>
                        <td className="px-3 py-2 text-slate-700">{formatPercent(-row.riskBudget)}</td>
                        <td className="px-3 py-2 text-slate-700">最高 R{row.maxSalesRiskLevel}</td>
                        <td className="px-3 py-2 text-slate-700">
                          {row.hardBlocks[0] || row.cautionFlags[0] || row.label}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {planSensitivityRows.map((row) => (
                  <div key={row.purchasePlan} className={`rounded-xl px-3 py-2 text-xs leading-5 ring-1 ${row.isCurrent ? 'bg-white text-violet-950 ring-violet-200' : 'bg-white/70 text-violet-900 ring-violet-100'}`}>
                    <div className="font-semibold">
                      {row.label}{row.isCurrent ? '（当前研究方式假设）' : ''}
                    </div>
                    <div className="mt-1">
                      费后回放 {formatPercent(row.returnRate)}；回撤 {formatPercent(row.drawdown)}；{row.hardBlocks[0] || row.cautionFlags[0] || row.gateLabel}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-rose-100 bg-rose-50 p-4 md:col-span-2" data-testid="fund-purchase-downgrade-queue">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold text-rose-700">研究结论降级队列</div>
                  <div className="mt-1 text-sm font-semibold text-slate-950">从“可研究”降到哪一档，以及为什么</div>
                </div>
                <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-rose-800 ring-1 ring-rose-100">
                  {effectivePurchaseDowngradeQueue.length} 条触发项
                </span>
              </div>
              <p className="mt-2 text-xs leading-5 text-rose-900">
                降级不是负面评分，而是研究复核风险控制：销售规则、R1-R5、净值回放、持仓暴露或替代基金任何一项改变，都要重新定位研究路径。
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                {effectivePurchaseDowngradeQueue.map((item) => {
                  const itemClassName = item.severity === 'high'
                    ? 'border-rose-100 bg-white text-rose-950'
                    : item.severity === 'medium'
                      ? 'border-amber-100 bg-white text-amber-950'
                      : 'border-slate-100 bg-white text-slate-800'
                  return (
                    <div key={item.key} className={`rounded-xl border p-3 ${itemClassName}`}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="font-semibold">{item.lane}</div>
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                          {item.severity === 'high' ? '硬降级' : item.severity === 'medium' ? '需复核' : '观察'}
                        </span>
                      </div>
                      <div className="mt-2 text-xs leading-5 opacity-80">{item.reason}</div>
                      <div className="mt-2 text-xs leading-5 opacity-80">下一步：{item.nextAction}</div>
                      {item.href ? (
                        <Link href={item.href} className="mt-3 inline-flex rounded-lg bg-rose-700 px-3 py-2 text-xs font-semibold text-white hover:bg-rose-800">
                          执行处理
                        </Link>
                      ) : null}
                    </div>
                  )
                })}
              </div>
              <div className="mt-3 rounded-xl border border-rose-100 bg-white px-3 py-2 text-xs leading-5 text-rose-800">
                硬边界：被降级的基金不能进入正式研究候选；补齐触发项后必须重新跑详情诊断、横向比较和报告留痕。
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-950 p-4 text-white md:col-span-2" data-testid="fund-single-counter-evidence-checklist">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Counter Evidence</div>
                  <div className="mt-1 text-sm font-semibold">单基金反证核查清单</div>
                  <p className="mt-2 max-w-3xl text-xs leading-5 text-slate-300">
                    防止单只基金因为收益榜、经理名气、平台热度或当前份额路径被误推进；每一条都必须能被销售规则、真实回放、份额成本、持仓归因或同类替代解释。
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
                    singleFundEliminationLine.tone === 'rose'
                      ? 'bg-rose-500/20 text-rose-100 ring-1 ring-rose-300/30'
                      : singleFundEliminationLine.tone === 'amber'
                        ? 'bg-amber-400/20 text-amber-100 ring-1 ring-amber-300/30'
                        : 'bg-emerald-400/20 text-emerald-100 ring-1 ring-emerald-300/30'
                  }`}>
                    {singleFundEliminationLine.label}
                  </span>
                  <button
                    type="button"
                    onClick={() => void copySingleFundCounterEvidenceTsv()}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-900 hover:bg-slate-100"
                    data-testid="fund-single-counter-evidence-copy-tsv"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    复制反证 TSV
                  </button>
                  <button
                    type="button"
                    onClick={downloadSingleFundCounterEvidenceTsv}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-2 text-xs font-semibold text-white ring-1 ring-white/15 hover:bg-white/15"
                    data-testid="fund-single-counter-evidence-download-tsv"
                  >
                    <Download className="h-3.5 w-3.5" />
                    下载反证 TSV
                  </button>
                </div>
              </div>

              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="text-xs font-semibold text-slate-300">单基金淘汰线</div>
                <div className="mt-1 text-sm font-semibold">{singleFundEliminationLine.reason}</div>
                <div className="mt-2 text-xs leading-5 text-slate-300">下一步：{singleFundEliminationLine.nextAction}</div>
                {singleFundEliminationLine.href ? (
                  <Link href={singleFundEliminationLine.href} className="mt-3 inline-flex rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-950 hover:bg-slate-100">
                    执行处理
                  </Link>
                ) : null}
              </div>

              <div className="mt-4 grid gap-3 lg:grid-cols-5">
                {singleFundCounterEvidenceChecks.map((item) => (
                  <div key={item.key} className="rounded-2xl border border-white/10 bg-white/5 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="text-sm font-semibold">{item.title}</div>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                        item.status === 'blocked'
                          ? 'bg-rose-400/20 text-rose-100'
                          : item.status === 'verify'
                            ? 'bg-amber-300/20 text-amber-100'
                            : 'bg-emerald-300/20 text-emerald-100'
                      }`}>
                        {item.status === 'blocked' ? '阻断' : item.status === 'verify' ? '待复核' : '通过'}
                      </span>
                    </div>
                    <div className="mt-2 text-xs leading-5 text-slate-300">{item.evidence}</div>
                    <div className="mt-3 rounded-xl bg-slate-900/70 px-3 py-2 text-xs leading-5 text-slate-200">
                      反证问题：{item.counterQuestion}
                    </div>
                    <div className="mt-2 text-xs leading-5 text-slate-300">淘汰线：{item.eliminationLine}</div>
                    {item.href ? (
                      <Link href={item.href} className="mt-3 inline-flex rounded-lg bg-white/10 px-3 py-2 text-xs font-semibold text-white ring-1 ring-white/15 hover:bg-white/15">
                        去处理
                      </Link>
                    ) : null}
                  </div>
                ))}
              </div>
              <div className="mt-3 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs leading-5 text-slate-300">
                硬边界：单基金反证核查只服务基金筛选、基金分析、基金经理/持仓解释和研究复核留痕；反证未闭环前不能输出申赎操作指令、不能绕过正式研究复核报告门禁。
              </div>
            </div>

            <div className="rounded-2xl border border-amber-100 bg-amber-50 p-4 md:col-span-2" data-testid="fund-purchase-recheck-triggers">
              <div className="text-xs font-semibold text-amber-700">什么情况下结论会改变</div>
              <div className="mt-2 grid gap-2 text-xs leading-5 text-amber-900 md:grid-cols-2">
                {purchaseDecisionRecheckTriggers.length ? purchaseDecisionRecheckTriggers.map((trigger) => (
                  <div key={trigger} className="rounded-xl bg-white/70 px-3 py-2 ring-1 ring-amber-100">
                    {trigger}
                  </div>
                )) : (
                  <div className="rounded-xl bg-white/70 px-3 py-2 ring-1 ring-amber-100">
                    当前没有明显反转触发器；但正式研究复核前仍需复核销售平台实时规则和最新净值。
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-indigo-100 bg-white shadow" data-testid="fund-buy-before-freshness-radar">
        <div className="flex flex-col gap-3 border-b border-indigo-100 bg-indigo-950 px-5 py-4 text-white lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs text-indigo-100 ring-1 ring-white/10">
              <ClipboardCheck className="h-3.5 w-3.5" />
              研究证据时效雷达
            </div>
            <h2 className="mt-3 text-xl font-semibold">这份单基金证据今天还能不能用</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-indigo-100">
              研究复核不能只看评分，还要看净值、销售规则、持仓和回放是否足够新；过期证据只能用于研究观察。
            </p>
          </div>
          <div className="rounded-2xl bg-white/10 px-4 py-3 text-sm ring-1 ring-white/10">
            <div className="text-xs text-indigo-200">时效分</div>
            <div className="mt-1 text-3xl font-bold text-white">{freshnessScore}</div>
            <div className="mt-1 max-w-md leading-6 text-indigo-100">{freshnessLabel}</div>
          </div>
        </div>
        <div className="grid gap-4 p-5 lg:grid-cols-[1fr_1.4fr]">
          <div className="rounded-2xl border border-indigo-100 bg-indigo-50 p-4">
            <div className="text-sm font-semibold text-indigo-950">当前判断</div>
            <div className="mt-2 text-sm leading-6 text-indigo-900">{freshnessSummary}</div>
            <div className="mt-4 flex flex-wrap gap-2">
              {freshnessPrimaryAction?.href ? (
                <Link href={freshnessPrimaryAction.href} className="rounded-lg bg-indigo-700 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-800">
                  {freshnessPrimaryAction.action}
                </Link>
              ) : freshnessPrimaryAction?.key === 'simulation' ? (
                <button
                  type="button"
                  onClick={() => void fetchPurchaseSimulation(fund.windCode, simulationForm)}
                  disabled={simulationLoading}
                  className="rounded-lg bg-indigo-700 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-800 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {simulationLoading ? '回放中...' : freshnessPrimaryAction.action}
                </button>
              ) : null}
              <Link href={salesRulesHrefForFund()} className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-amber-800 ring-1 ring-amber-200 hover:bg-amber-50">
                复核销售平台规则
              </Link>
            </div>
            <div className="mt-4 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
              硬门禁：证据过期、销售规则缺口或回放缺失时，不能保存或沿用正式研究复核报告。
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {buyBeforeFreshnessItems.map((item) => (
              <div key={item.key} className={`rounded-2xl border p-4 ${
                item.status === 'fresh'
                  ? 'border-emerald-100 bg-emerald-50'
                  : item.status === 'watch'
                    ? 'border-blue-100 bg-blue-50'
                    : item.status === 'stale'
                      ? 'border-rose-100 bg-rose-50'
                      : 'border-amber-100 bg-amber-50'
              }`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-950">{item.title}</div>
                    <div className="mt-1 text-xs text-slate-500">{item.label}</div>
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                    item.status === 'fresh'
                      ? 'bg-emerald-100 text-emerald-800'
                      : item.status === 'watch'
                        ? 'bg-blue-100 text-blue-800'
                        : item.status === 'stale'
                          ? 'bg-rose-100 text-rose-800'
                          : 'bg-amber-100 text-amber-800'
                  }`}>
                    {item.status === 'fresh' ? '可用' : item.status === 'watch' ? '临近复核' : item.status === 'stale' ? '过期/阻断' : '待补'}
                  </span>
                </div>
                <div className="mt-3 text-xs leading-5 text-slate-600">{item.detail}</div>
                <div className="mt-2 text-xs font-medium text-slate-700">
                  {item.ageDays === null ? '距今天数：待补' : `距今天数：${item.ageDays} 天`}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-fuchsia-100 bg-white p-6 shadow" data-testid="fund-share-class-decision-card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
              <ShieldCheck className="h-5 w-5 text-fuchsia-600" />
              同基金份额选择
            </div>
            <p className="mt-1 text-sm text-slate-500">
              买基金前先确认买的是 A/C/H/I 哪个份额；同基金不同份额不能只按收益分独立下结论。
            </p>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
            shareClassInfo ? 'bg-fuchsia-50 text-fuchsia-700 ring-1 ring-fuchsia-100' : 'bg-amber-50 text-amber-700 ring-1 ring-amber-100'
          }`}>
            {shareClassDecisionLabel}
          </span>
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-2xl bg-fuchsia-50 p-4 text-sm text-fuchsia-950">
            <div className="text-xs font-semibold text-fuchsia-700">当前份额</div>
            <div className="mt-2 text-2xl font-bold">{currentShareClass}</div>
            <div className="mt-2 leading-6">{shareClassDecisionDetail}</div>
            <div data-testid="fund-share-class-purchase-advice" className="mt-4 rounded-xl bg-white p-3 text-slate-800 ring-1 ring-fuchsia-100">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-xs font-semibold text-fuchsia-700">份额配置核查建议</div>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                  shareClassPurchaseAdvice.confidence === 'medium' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                }`}>
                  {shareClassPurchaseAdvice.confidence === 'medium' ? '中等置信' : '低置信待补'}
                </span>
              </div>
              <div className="mt-2 font-semibold text-slate-950">
                {shareClassPurchaseAdvice.recommendedCode
                  ? `${shareClassPurchaseAdvice.title}：${shareClassPurchaseAdvice.recommendedClass}类 ${shareClassPurchaseAdvice.recommendedCode}`
                  : shareClassPurchaseAdvice.title}
              </div>
              {shareClassPurchaseAdvice.recommendedName ? (
                <div className="mt-1 text-xs text-slate-500">{shareClassPurchaseAdvice.recommendedName}</div>
              ) : null}
              <div className="mt-2 space-y-1 text-xs leading-5 text-slate-600">
                {shareClassPurchaseAdvice.reasons.slice(0, 4).map((reason) => (
                  <div key={reason}>• {reason}</div>
                ))}
              </div>
              <div className="mt-2 rounded-lg bg-amber-50 px-2 py-1.5 text-xs leading-5 text-amber-800">
                {shareClassPurchaseAdvice.warnings[0] || '正式选择前仍必须补齐销售平台实时费率、风险等级和申赎规则。'}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {shareClassComparisonHref ? (
                <Link href={shareClassComparisonHref} className="rounded-lg bg-fuchsia-600 px-3 py-2 text-xs font-semibold text-white hover:bg-fuchsia-700">
                  多份额对比
                </Link>
              ) : null}
              <button
                type="button"
                onClick={() => void fetchShareClassFunds(fund)}
                disabled={shareClassLoading}
                className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-fuchsia-700 ring-1 ring-fuchsia-100 hover:bg-fuchsia-50 disabled:opacity-50"
              >
                {shareClassLoading ? '识别中...' : '刷新份额识别'}
              </button>
              <Link href={salesRulesHrefForCodes(shareClassCompareCodes.length ? shareClassCompareCodes : [fund.windCode])} className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50">
                补份额规则
              </Link>
            </div>
          </div>

          <div className="overflow-hidden rounded-2xl border border-slate-100">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-medium text-slate-500">
                <tr>
                  <th className="px-4 py-3">份额</th>
                  <th className="px-4 py-3">代码</th>
                  <th className="px-4 py-3">计划金额成本</th>
                  <th className="px-4 py-3">规模</th>
                  <th className="px-4 py-3">研究动作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {shareClassRows.length ? shareClassRows.map((item) => {
                  const classType = inferShareClass(item.name) || '未知'
                  const fee = totalFee(item)
                  const cost = shareClassCurrentSalesRuleCost(item)
                  const isCurrent = item.windCode.toUpperCase() === fund.windCode.toUpperCase()
                  const amountGate = item.executionAmountGate
                  const amountGateBlocked = amountGate?.status === 'blocked'
                  const amountGateClass = amountGate?.status === 'pass'
                    ? 'bg-emerald-50 text-emerald-700 ring-emerald-100'
                    : amountGateBlocked
                      ? 'bg-rose-50 text-rose-700 ring-rose-100'
                      : 'bg-amber-50 text-amber-700 ring-amber-100'
                  const isBestCost = !amountGateBlocked && bestCostShareClass?.windCode === item.windCode && cost.knownCost !== null
                  return (
                    <tr key={item.windCode} className={isCurrent ? 'bg-fuchsia-50/50' : ''}>
                      <td className="px-4 py-3">
                        <div className="font-semibold text-slate-950">{classType}类</div>
                        <div className="mt-1 text-xs text-slate-500">{item.name}</div>
                      </td>
                      <td className="px-4 py-3 text-slate-700">{item.windCode}</td>
                      <td className="px-4 py-3">
                        <span className={`font-semibold ${isBestCost ? 'text-emerald-700' : 'text-slate-900'}`}>
                          {cost.knownCost === null ? '待补' : formatMoney(cost.knownCost)}
                        </span>
                        <div className="mt-1 text-xs text-slate-500">
                          管托费率 {fee === null ? '待补' : `${fee.toFixed(2)}%`}
                          {cost.purchaseFeeAmount !== null ? ` · 申购费 ${formatMoney(cost.purchaseFeeAmount)}` : ''}
                          {cost.salesServiceFeeAmount !== null ? ` · 销服费 ${formatMoney(cost.salesServiceFeeAmount)}` : ''}
                        </div>
                        {cost.missing.length ? <div className="mt-1 text-xs text-amber-700">待补：{cost.missing.slice(0, 3).join('、')}</div> : null}
                        <div className={`mt-2 inline-flex rounded-full px-2 py-1 text-xs font-medium ring-1 ${amountGateClass}`}>
                          份额金额门禁：{amountGate?.label || '金额门槛待补'}
                        </div>
                        {amountGate?.detail ? <div className="mt-1 text-xs text-slate-500">{amountGate.detail}</div> : null}
                        {isBestCost ? <div className="mt-1 text-xs text-emerald-700">当前样本已知成本较低</div> : null}
                      </td>
                      <td className="px-4 py-3 text-slate-700">{item.totalAsset == null ? '待补' : `${Number(item.totalAsset).toFixed(2)} 亿`}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-2">
                          <Link href={`/funds/${encodeURIComponent(item.id || item.windCode)}?${detailContextQuery}`} className="rounded-lg bg-slate-50 px-2.5 py-1.5 text-xs font-medium text-blue-700 ring-1 ring-blue-100 hover:bg-blue-50">
                            详情
                          </Link>
                          <Link href={salesRulesHrefForFund(item.windCode)} className="rounded-lg bg-slate-50 px-2.5 py-1.5 text-xs font-medium text-amber-700 ring-1 ring-amber-100 hover:bg-amber-50">
                            规则
                          </Link>
                        </div>
                      </td>
                    </tr>
                  )
                }) : (
                  <tr>
                    <td colSpan={5} className="px-4 py-5 text-sm leading-6 text-amber-700">
                      {shareClassLoading ? '正在读取同基金份额...' : shareClassError || '未发现可展示的同基金份额样本。'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {shareClassInfo?.warnings.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {shareClassInfo.warnings.map((warning) => (
              <span key={warning} className="rounded-full bg-fuchsia-50 px-3 py-1 text-xs text-fuchsia-700 ring-1 ring-fuchsia-100">{warning}</span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="rounded-2xl border border-blue-100 bg-white p-6 shadow">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
              <UserCheck className="h-5 w-5 text-blue-600" />
              研究画像适配诊断
            </div>
            <p className="mt-1 text-sm text-slate-500">
              同一只基金对不同风险承受力、持有期和研究方式假设的结论不同；这里把适当性假设显式化。
            </p>
          </div>
          <div className={`rounded-full px-3 py-1 text-xs font-semibold ${detailGate.className}`}>
            {detailGate.profileLabel} · {detailGate.horizonLabel} · {detailGate.purchasePlanLabel}
          </div>
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-3">
          <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
            <div className="text-sm font-semibold text-slate-900">风险承受力</div>
            <div className="mt-3 grid gap-2">
              {(Object.entries(investorRiskProfiles) as Array<[InvestorRiskProfile, typeof investorRiskProfiles[InvestorRiskProfile]]>).map(([key, item]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setInvestorRiskProfile(key)}
                  className={`rounded-lg px-3 py-2 text-left text-sm ring-1 transition ${
                    investorRiskProfile === key ? 'bg-blue-600 text-white ring-blue-600' : 'bg-white text-slate-700 ring-slate-100 hover:ring-blue-200'
                  }`}
                >
                  <div className="font-medium">{item.label}</div>
                  <div className={`mt-0.5 text-xs ${investorRiskProfile === key ? 'text-blue-100' : 'text-slate-500'}`}>
                    回撤预算 {formatPercent(-item.maxDrawdownTolerance)} · 最高 R{item.maxSalesRiskLevel}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
            <div className="text-sm font-semibold text-slate-900">计划持有期</div>
            <div className="mt-3 grid gap-2">
              {(Object.entries(investorHorizons) as Array<[InvestorHorizon, typeof investorHorizons[InvestorHorizon]]>).map(([key, item]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setInvestorHorizon(key)}
                  className={`rounded-lg px-3 py-2 text-left text-sm ring-1 transition ${
                    investorHorizon === key ? 'bg-indigo-600 text-white ring-indigo-600' : 'bg-white text-slate-700 ring-slate-100 hover:ring-indigo-200'
                  }`}
                >
                  <div className="font-medium">{item.label}</div>
                  <div className={`mt-0.5 text-xs ${investorHorizon === key ? 'text-indigo-100' : 'text-slate-500'}`}>
                    至少看 {item.minSampleMonths} 个月回放样本
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
            <div className="text-sm font-semibold text-slate-900">研究方式假设</div>
            <div className="mt-3 grid gap-2">
              {(Object.entries(investorPurchasePlans) as Array<[InvestorPurchasePlan, typeof investorPurchasePlans[InvestorPurchasePlan]]>).map(([key, item]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setInvestorPurchasePlan(key)}
                  className={`rounded-lg px-3 py-2 text-left text-sm ring-1 transition ${
                    investorPurchasePlan === key ? 'bg-emerald-600 text-white ring-emerald-600' : 'bg-white text-slate-700 ring-slate-100 hover:ring-emerald-200'
                  }`}
                >
                  <div className="font-medium">{item.label}</div>
                  <div className={`mt-0.5 text-xs ${investorPurchasePlan === key ? 'text-emerald-100' : 'text-slate-500'}`}>
                    {item.note}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-4">
          <div className="rounded-xl bg-blue-50 p-4 text-sm text-blue-900">
            <div className="text-xs text-blue-700">画像回撤预算</div>
            <div className="mt-1 text-lg font-semibold">{formatPercent(-detailGate.riskBudget)}</div>
          </div>
          <div className="rounded-xl bg-indigo-50 p-4 text-sm text-indigo-900">
            <div className="text-xs text-indigo-700">销售风险等级</div>
            <div className="mt-1 text-lg font-semibold">
              {detailGate.salesRiskLevel === null ? '待补' : `R${detailGate.salesRiskLevel}`} / 最高 R{detailGate.maxSalesRiskLevel}
            </div>
          </div>
          <div className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-900">
            <div className="text-xs text-emerald-700">计划金额约束</div>
            <div className="mt-1 text-sm font-semibold leading-6">
              {investorPurchasePlan === 'sip'
                ? `每月 ${formatMoney(asPositiveNumber(simulationForm.monthlyAmount, 1000))}`
                : `一次性 ${formatMoney(asPositiveNumber(simulationForm.lumpSumAmount, 10000))}`}
            </div>
          </div>
          <div className="rounded-xl bg-amber-50 p-4 text-sm text-amber-900">
            <div className="text-xs text-amber-700">当前结论</div>
            <div className="mt-1 text-lg font-semibold">{detailGate.label}</div>
          </div>
        </div>

        <div className="mt-5 rounded-2xl border border-slate-100 bg-slate-50 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-950">申赎规则核查矩阵</div>
              <div className="mt-1 text-xs text-slate-500">
                对标销售平台申赎前检查：不是申赎入口，只确认当前计划金额假设是否具备可执行证据。
              </div>
            </div>
            <Link href={salesRulesHrefForFund()} className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50">
              {salesRulesReady ? '查看销售规则' : '补齐申赎规则'}
            </Link>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {salesRuleChecklist.map((item) => (
              <div key={item.title} className={`rounded-xl border p-3 ${workflowStatusClass(item.status)}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="text-xs font-medium opacity-75">{item.title}</div>
                  <span className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-semibold">
                    {item.status === 'done' ? '具备' : item.status === 'blocked' ? '阻断' : '待补'}
                  </span>
                </div>
                <div className="mt-2 text-sm font-semibold">{item.label}</div>
                <div className="mt-2 min-h-10 text-[11px] leading-5 opacity-80">{item.detail}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-4">
            <div className="text-sm font-semibold text-emerald-950">适配依据</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {detailGate.suitabilityNotes.map((item) => (
                <span key={item} className="rounded-full bg-white px-3 py-1 text-xs text-emerald-800">{item}</span>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-rose-100 bg-rose-50 p-4">
            <div className="text-sm font-semibold text-rose-950">不适配/待核原因</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {[...detailGate.hardBlocks, ...detailGate.cautionFlags].slice(0, 8).map((item) => (
                <span key={item} className="rounded-full bg-white px-3 py-1 text-xs text-rose-800">{item}</span>
              ))}
              {detailGate.hardBlocks.length === 0 && detailGate.cautionFlags.length === 0 ? (
                <span className="rounded-full bg-white px-3 py-1 text-xs text-rose-800">暂无高优先级适配问题</span>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
              <ShieldCheck className="h-5 w-5 text-emerald-600" />
              研究复核工作流
            </div>
            <p className="mt-1 text-sm text-slate-500">
              对标销售平台“申赎前确认”，但只做到基金研究闭环：适当性、销售规则、持有体验、横向比较和报告留痕。
            </p>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${detailGate.className}`}>
            {detailGate.label} · 证据 {detailGate.evidenceGrade}
          </span>
        </div>

        <div className={`mt-5 rounded-2xl border p-4 ${purchasePriorityClass}`} data-testid="fund-purchase-priority-action">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0 flex-1">
              <div className="inline-flex rounded-full bg-white/70 px-2.5 py-1 text-[11px] font-semibold ring-1 ring-black/5">
                {purchasePriorityAction.badge}
              </div>
              <div className="mt-3 text-lg font-semibold">{purchasePriorityAction.title}</div>
              <p className="mt-2 text-sm leading-6 opacity-85">{purchasePriorityAction.description}</p>
              <p className="mt-2 text-xs leading-5 opacity-75">为什么优先做：{purchasePriorityAction.why}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {purchasePriorityAction.relatedItems.map((item) => (
                  <span key={item} className="rounded-full bg-white/70 px-2.5 py-1 text-xs ring-1 ring-black/5">{item}</span>
                ))}
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              {purchasePriorityAction.actionHref ? (
                <Link href={purchasePriorityAction.actionHref} className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-900 ring-1 ring-black/5 hover:bg-slate-50">
                  {purchasePriorityAction.actionLabel}
                </Link>
              ) : purchasePriorityAction.actionKind === 'scanSalesRule' ? (
                <button
                  type="button"
                  onClick={() => void fetchSalesRuleGap(fund.windCode)}
                  disabled={salesRuleGapLoading}
                  className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-900 ring-1 ring-black/5 hover:bg-slate-50 disabled:opacity-50"
                >
                  {purchasePriorityAction.actionLabel}
                </button>
              ) : purchasePriorityAction.actionKind === 'simulate' ? (
                <button
                  type="button"
                  onClick={() => void fetchPurchaseSimulation(fund.windCode, simulationForm)}
                  disabled={simulationLoading}
                  className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-900 ring-1 ring-black/5 hover:bg-slate-50 disabled:opacity-50"
                >
                  {purchasePriorityAction.actionLabel}
                </button>
              ) : purchasePriorityAction.actionKind === 'saveReport' ? (
                <button
                  type="button"
                  onClick={() => void savePrePurchaseReport()}
                  disabled={reportSaving || formalReportBlocked}
                  title={formalReportBlocked ? formalReportBlockSummary : '保存正式研究复核报告'}
                  className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-900 ring-1 ring-black/5 hover:bg-slate-50 disabled:opacity-50"
                >
                  {formalReportBlocked ? '补证后保存' : purchasePriorityAction.actionLabel}
                </button>
              ) : (
                <span className="rounded-lg bg-white/70 px-3 py-2 text-xs font-semibold text-slate-600 ring-1 ring-black/5">
                  {purchasePriorityAction.actionLabel}
                </span>
              )}
              <Link href={salesRulesHrefForFund()} className="rounded-lg bg-white/60 px-3 py-2 text-xs font-semibold text-slate-700 ring-1 ring-black/5 hover:bg-white">
                查看申赎规则
              </Link>
            </div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 xl:grid-cols-5">
          {buyWorkflowSteps.map((step) => (
            <div key={step.title} className={`rounded-2xl border p-4 ${workflowStatusClass(step.status)}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="font-semibold">{step.title}</div>
                <span className="rounded-full bg-white/70 px-2 py-1 text-[11px] font-medium">
                  {step.status === 'done' ? '已具备' : step.status === 'blocked' ? '阻断' : step.status === 'verify' ? '待复核' : '待执行'}
                </span>
              </div>
              <div className="mt-2 text-sm font-medium">{step.label}</div>
              <div className="mt-2 min-h-16 text-xs leading-5 opacity-80">{step.description}</div>
              {step.actionHref ? (
                <Link href={step.actionHref} className="mt-4 inline-flex rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-800 ring-1 ring-black/5 hover:bg-slate-50">
                  {step.actionLabel}
                </Link>
              ) : step.title === '3. 持有体验回放' ? (
                <button
                  type="button"
                  onClick={() => void fetchPurchaseSimulation(fund.windCode, simulationForm)}
                  disabled={simulationLoading}
                  className="mt-4 inline-flex rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-800 ring-1 ring-black/5 hover:bg-slate-50 disabled:opacity-50"
                >
                  {simulationLoading ? '测算中...' : step.actionLabel}
                </button>
              ) : step.title === '6. 研究留痕' ? (
                <button
                  type="button"
                  onClick={() => void savePrePurchaseReport()}
                  disabled={reportSaving || formalReportBlocked}
                  title={formalReportBlocked ? formalReportBlockSummary : '保存正式研究复核报告'}
                  className="mt-4 inline-flex rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-800 ring-1 ring-black/5 hover:bg-slate-50 disabled:opacity-50"
                >
                  {reportSaving ? '保存中...' : formalReportBlocked ? '补证后保存' : step.actionLabel}
                </button>
              ) : (
                <span className="mt-4 inline-flex rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-500 ring-1 ring-black/5">
                  {step.actionLabel}
                </span>
              )}
            </div>
          ))}
        </div>

        <div className="mt-4 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-800">
          这里不会生成申赎操作指令；若任一环节显示“阻断”或“待复核”，应先补齐对应证据，再进入研究清单、横向比较或报告留痕。
        </div>
      </div>

      <div className="rounded-2xl bg-white p-6 shadow">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">同画像替代候选</h2>
            <p className="mt-1 text-sm text-gray-500">
              基于当前研究画像、计划持有期、研究方式假设和基金类型，从研究筛选引擎中拉取可比较候选。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {alternativeComparisonHref ? (
              <Link
                href={alternativeComparisonHref}
                className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700"
              >
                对比本基金+可比替代
              </Link>
            ) : null}
            <Link
              href={alternativeSalesRulesHref}
              className="rounded-lg border border-cyan-200 px-3 py-2 text-sm text-cyan-700 hover:bg-cyan-50"
            >
              {salesRuleBlockedCompareCodes.length ? `先补规则（${salesRuleBlockedCompareCodes.length}）` : '批量补销售规则'}
            </Link>
            <Link
              href={canonicalResearchHref(`/investor-selection?profile=${investorRiskProfile}&horizon=${investorHorizon}&purchasePlan=${investorPurchasePlan}&type=${encodeURIComponent(fund.type || '')}&eligibleOnly=true&minEvidenceGrade=B`)}
              className="rounded-lg border border-blue-200 px-3 py-2 text-sm text-blue-700 hover:bg-blue-50"
            >
              打开完整选基
            </Link>
          </div>
        </div>

        {alternativeSearchMeta ? (
          <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-xs text-slate-600">
            <div className="font-semibold text-slate-800">{alternativeSearchMeta.note}</div>
            <div className="mt-1 leading-5">
              搜索路径：{alternativeSearchMeta.attempts.length ? alternativeSearchMeta.attempts.join(' → ') : '待重试'}；样本 {alternativeSearchMeta.total}；来源 {alternativeSearchMeta.source}。
            </div>
            <div className="mt-1 leading-5">
              替代候选销售规则：{alternativeSalesRuleGapsLoading
                ? '扫描中'
                : alternativeSalesRuleGapError
                  ? `扫描失败：${alternativeSalesRuleGapError}，暂不能视为可比。`
                  : alternativeGapFunds.length
                  ? `${alternativeGapFunds.length} 只仍有硬缺口，横比前应先补规则。`
                  : alternativeFunds.length
                    ? '未检测到替代候选硬缺口。'
                    : '待获取替代候选。'}
            </div>
          </div>
        ) : null}

        <div className={`mt-4 rounded-2xl border p-4 ${
          alternativePrioritySummary.tone === 'emerald'
            ? 'border-emerald-100 bg-emerald-50 text-emerald-900'
            : alternativePrioritySummary.tone === 'blue'
              ? 'border-blue-100 bg-blue-50 text-blue-900'
              : alternativePrioritySummary.tone === 'amber'
                ? 'border-amber-100 bg-amber-50 text-amber-900'
                : 'border-slate-100 bg-slate-50 text-slate-900'
        }`} data-testid="fund-alternative-priority">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-sm font-semibold">{alternativePrioritySummary.title}</div>
              <p className="mt-2 text-xs leading-5 opacity-85">{alternativePrioritySummary.detail}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {alternativePrioritySummary.chips.length ? alternativePrioritySummary.chips.map((chip) => (
                  <span key={chip} className="rounded-full bg-white/70 px-2.5 py-1 text-xs ring-1 ring-black/5">{chip}</span>
                )) : (
                  <span className="rounded-full bg-white/70 px-2.5 py-1 text-xs ring-1 ring-black/5">暂无可比对象</span>
                )}
              </div>
            </div>
            {alternativePrioritySummary.actionHref ? (
              <Link
                href={alternativePrioritySummary.actionHref}
                className="inline-flex shrink-0 items-center justify-center rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-900 ring-1 ring-black/5 hover:bg-slate-50"
              >
                {alternativePrioritySummary.actionLabel}
              </Link>
            ) : (
              <span className="inline-flex shrink-0 items-center justify-center rounded-lg bg-white/70 px-3 py-2 text-xs font-semibold text-slate-500 ring-1 ring-black/5">
                {alternativePrioritySummary.actionLabel}
              </span>
            )}
          </div>
        </div>

        <div className={`mt-4 rounded-2xl border p-4 ${
          alternativeDecisionBrief.tone === 'emerald'
            ? 'border-emerald-100 bg-emerald-50'
            : alternativeDecisionBrief.tone === 'amber'
              ? 'border-amber-100 bg-amber-50'
              : 'border-slate-100 bg-slate-50'
        }`} data-testid="fund-alternative-decision-brief">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">研究替代结论</div>
              <h3 className="mt-1 text-base font-semibold text-slate-950">{alternativeDecisionBrief.title}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-700">{alternativeDecisionBrief.detail}</p>
            </div>
            <div className="rounded-xl bg-white px-4 py-3 text-sm font-semibold text-slate-900 ring-1 ring-black/5">
              {alternativeDecisionBrief.verdict}
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {[
              ['主基金状态', alternativeDecisionBrief.primary],
              ['替代候选', alternativeDecisionBrief.alternative],
              ['下一步', alternativeDecisionBrief.next],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-white px-3 py-3 ring-1 ring-black/5">
                <div className="text-xs font-medium text-slate-500">{label}</div>
                <div className="mt-1 text-xs leading-5 text-slate-800">{value}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50/60 p-4" data-testid="fund-alternative-decision-matrix">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-sm font-semibold text-blue-950">替代横评矩阵</div>
              <p className="mt-1 text-xs leading-5 text-blue-800">{alternativeMatrixSummary}</p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              {alternativeComparisonHref ? (
                <Link href={alternativeComparisonHref} className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-700">
                  打开正式横评
                </Link>
              ) : (
                <span className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-blue-700 ring-1 ring-blue-100">
                  {reportSalesRuleBlocked ? '硬缺口清零后横评' : '样本待补'}
                </span>
              )}
              <button
                type="button"
                onClick={() => void copyAlternativeDecisionMatrixTsv()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-blue-700 ring-1 ring-blue-100 hover:bg-blue-50"
                data-testid="fund-alternative-matrix-copy-tsv"
              >
                <Copy className="h-3.5 w-3.5" />
                复制矩阵 TSV
              </button>
              <button
                type="button"
                onClick={downloadAlternativeDecisionMatrixTsv}
                className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-blue-700 ring-1 ring-blue-100 hover:bg-blue-50"
                data-testid="fund-alternative-matrix-download-tsv"
              >
                <Download className="h-3.5 w-3.5" />
                下载矩阵 TSV
              </button>
            </div>
          </div>

          <div className="mt-3 overflow-x-auto rounded-xl border border-blue-100 bg-white">
            <table className="min-w-full divide-y divide-slate-100 text-left text-xs">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-3 py-2 font-semibold">候选</th>
                  <th className="px-3 py-2 font-semibold">决策</th>
                  <th className="px-3 py-2 font-semibold">分数差</th>
                  <th className="px-3 py-2 font-semibold">收益差</th>
                  <th className="px-3 py-2 font-semibold">回撤差</th>
                  <th className="px-3 py-2 font-semibold">证据</th>
                  <th className="px-3 py-2 font-semibold">优势/风险</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                <tr className="bg-blue-50/40">
                  <td className="px-3 py-2 font-semibold text-slate-950">{fund.name}<div className="mt-0.5 text-[11px] font-normal text-slate-500">{fund.windCode}</div></td>
                  <td className="px-3 py-2 text-slate-700">{purchaseDecisionLabel}</td>
                  <td className="px-3 py-2 text-slate-700">基准 {purchaseDecisionScore}</td>
                  <td className="px-3 py-2 text-slate-700">{formatPercent(detailGate.annualReturn)}</td>
                  <td className="px-3 py-2 text-slate-700">{formatPercent(detailGate.maxDrawdown)}</td>
                  <td className="px-3 py-2 text-slate-700">{detailGate.evidenceGrade}</td>
                  <td className="px-3 py-2 text-slate-700">{reportSalesRuleBlocked ? reportBlockReason : detailGate.suitabilityNotes.slice(0, 2).join('；')}</td>
                </tr>
                {alternativeDecisionRows.length ? alternativeDecisionRows.map((item) => (
                  <tr key={`matrix-${item.windCode}`}>
                    <td className="px-3 py-2 font-semibold text-slate-950">
                      {item.name}
                      <div className="mt-0.5 text-[11px] font-normal text-slate-500">{item.windCode}</div>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`rounded-full px-2 py-1 font-medium ${
                        item.verdict === '优先纳入横评'
                          ? 'bg-emerald-100 text-emerald-700'
                          : item.verdict.includes('规则')
                            ? 'bg-amber-100 text-amber-700'
                            : 'bg-slate-100 text-slate-700'
                      }`}>
                        {item.verdict}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-slate-700">{formatScoreDiff(item.scoreGap)}</td>
                    <td className="px-3 py-2 text-slate-700">{item.returnGap === null ? '待补' : formatScoreDiff(item.returnGap * 100, '%')}</td>
                    <td className="px-3 py-2 text-slate-700">{item.drawdownGap === null ? '待补' : formatScoreDiff(item.drawdownGap * 100, '%')}</td>
                    <td className="px-3 py-2 text-slate-700">{item.evidenceGap}</td>
                    <td className="px-3 py-2 text-slate-700">
                      {[...item.wins, ...item.risks].slice(0, 3).join('；') || '暂无明确优势'}
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={7} className="px-3 py-5 text-center text-slate-500">暂无替代候选矩阵；请打开完整选基或放宽证据等级。</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="mt-2 text-[11px] leading-5 text-blue-700">
            回撤差为“替代候选绝对回撤 - 主基金绝对回撤”，负数代表替代候选回撤更低；销售规则硬缺口未清零时，本矩阵只用于研究观察。
          </div>
        </div>

        {alternativesLoading ? (
          <div className="mt-4 rounded-xl border border-dashed border-gray-200 p-6 text-center text-sm text-gray-500">
            正在按当前画像刷新替代候选...
          </div>
        ) : alternativeFunds.length > 0 ? (
          <div className="mt-5 grid gap-4 xl:grid-cols-4">
            {alternativeFunds.map((item) => (
              <div key={item.windCode} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                {(() => {
                  const alternativeGap = alternativeSalesRuleGaps[item.windCode.toUpperCase()]
                  const alternativeBlocked = Boolean(alternativeGap && alternativeGap.missingCount > 0)
                  return (
                    <>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-950">{item.name}</div>
                    <div className="mt-1 text-xs text-slate-500">{item.windCode} · {item.type || '未分类'}</div>
                  </div>
                  <span className="rounded-full bg-blue-100 px-2 py-1 text-xs font-semibold text-blue-700">
                    {item.investorScore.toFixed(1)}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-700">
                  <div className="rounded-lg bg-white px-3 py-2">
                    <div className="text-slate-500">1Y收益</div>
                    <div className="mt-1 font-semibold text-slate-950">{formatPercent(item.annualReturn)}</div>
                  </div>
                  <div className="rounded-lg bg-white px-3 py-2">
                    <div className="text-slate-500">最大回撤</div>
                    <div className="mt-1 font-semibold text-rose-700">{formatPercent(item.maxDrawdown)}</div>
                  </div>
                  <div className="rounded-lg bg-white px-3 py-2">
                    <div className="text-slate-500">规模</div>
                    <div className="mt-1 font-semibold text-slate-950">{item.totalAsset == null ? '待补' : `${item.totalAsset.toFixed(2)} 亿`}</div>
                  </div>
                  <div className="rounded-lg bg-white px-3 py-2">
                    <div className="text-slate-500">门禁</div>
                    <div className="mt-1 font-semibold text-slate-950">{item.purchaseGate?.label || '待核'}</div>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1">
                  {alternativeBlocked ? (
                    <span className="rounded-full bg-amber-100 px-2 py-1 text-xs font-medium text-amber-800">
                      销售规则缺 {alternativeGap.missingCount} 项
                    </span>
                  ) : null}
                  {(item.reasons || []).slice(0, 2).map((reason) => (
                    <span key={reason} className="rounded-full bg-white px-2 py-1 text-xs text-slate-600">{reason}</span>
                  ))}
                </div>
                <div className="mt-3 rounded-xl bg-white px-3 py-2 text-xs leading-5 text-slate-600">
                  <div>适当性：{item.riskSuitability?.label || '风险等级待补'}</div>
                  <div>证据边界：{item.purchaseGate?.evidenceGrade || '-'} · {(item.purchaseGate?.cautionFlags || item.warnings || []).slice(0, 2).join('；') || '暂无额外提示'}</div>
                </div>
                <div className="mt-4 flex gap-2">
                  <Link
                    href={`/funds/${encodeURIComponent(item.windCode)}?${detailContextQuery}`}
                    className="flex-1 rounded-lg bg-white px-3 py-2 text-center text-xs font-medium text-blue-700 ring-1 ring-blue-100 hover:bg-blue-50"
                  >
                    看详情
                  </Link>
                  <Link
                    href={alternativeBlocked
                      ? salesRulesHrefForFund(item.windCode)
                      : `/analysis/comparison?codes=${encodeURIComponent(`${fund.windCode},${item.windCode}`)}&profile=${investorRiskProfile}&horizon=${investorHorizon}&purchasePlan=${investorPurchasePlan}&autoReplay=1`}
                    className={`flex-1 rounded-lg px-3 py-2 text-center text-xs font-medium ${alternativeBlocked ? 'bg-amber-600 text-white hover:bg-amber-700' : 'bg-blue-600 text-white hover:bg-blue-700'}`}
                  >
                    {alternativeBlocked ? '先补规则' : '对比'}
                  </Link>
                </div>
                    </>
                  )
                })()}
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-4 rounded-xl border border-amber-100 bg-amber-50 p-4 text-sm text-amber-800">
            当前画像下没有找到更高证据等级的同类型替代候选。可以放宽证据等级、扩大基金类型，或先补齐全市场数据后再比较。
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
              <ClipboardCheck className="h-5 w-5 text-blue-600" />
              研究复核一页纸
            </div>
            <p className="mt-1 text-sm text-slate-500">
              把“能不能进入研究清单、为什么、还缺什么”集中成一张可复制的研究复核卡。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void copyOnePageMemo()}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
            >
              <Copy className="h-4 w-4" />
              {summaryCopied ? '已复制' : '复制一页纸'}
            </button>
            <button
              type="button"
              onClick={() => void copyOnePageEvidenceTsv()}
              className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700 hover:bg-blue-100"
              data-testid="fund-detail-one-page-tsv-copy"
            >
              <Copy className="h-4 w-4" />
              复制核查 TSV
            </button>
            <button
              type="button"
              onClick={downloadOnePageEvidenceTsv}
              className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm text-blue-700 hover:bg-blue-50"
              data-testid="fund-detail-one-page-tsv-download"
            >
              <Download className="h-4 w-4" />
              下载核查 TSV
            </button>
            <button
              type="button"
              onClick={() => void downloadPrePurchaseReport()}
              disabled={reportGenerating || formalReportBlocked}
              title={formalReportBlocked ? formalReportBlockSummary : '下载研究复核报告'}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-3 py-2 text-sm text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Download className="h-4 w-4" />
              {reportGenerating ? '生成中...' : formalReportBlocked ? '补证后下载' : '下载核查报告'}
            </button>
            <button
              type="button"
              onClick={() => void savePrePurchaseReport()}
              disabled={reportSaving || formalReportBlocked}
              title={formalReportBlocked ? formalReportBlockSummary : '保存到报告库'}
              className="inline-flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              {reportSaving ? '保存中...' : formalReportBlocked ? '补证后保存' : '保存到报告库'}
            </button>
            {formalReportBlocked ? (
              <Link
                href={reportSalesRuleBlocked ? salesRulesHrefForFund() : '#fund-buy-before-freshness-radar'}
                className="inline-flex items-center rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800 hover:bg-amber-100"
              >
                {reportSalesRuleBlocked ? '先补销售规则' : '查看补证原因'}
              </Link>
            ) : null}
            {savedReportId ? (
              <Link href={`/reports/${savedReportId}`} className="inline-flex items-center rounded-lg px-3 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50">
                查看已保存报告
              </Link>
            ) : null}
          </div>
        </div>

        {activeSalesRuleEvidenceAlert ? (
          <div className="mt-4 rounded-2xl border border-rose-100 bg-rose-50 p-4 text-sm leading-6 text-rose-900" data-testid="fund-detail-active-sales-rule-evidence-alert">
            <div className="font-semibold">复查队列拦截：销售规则/R1-R5 证据过期或待补</div>
            <div className="mt-1">
              {activeSalesRuleEvidenceAlert.title || '销售规则/R1-R5证据待补'}
              {activeSalesRuleEvidenceAlert.message ? `：${activeSalesRuleEvidenceAlert.message}` : ''}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link href={salesRulesHrefForFund()} className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700">
                补销售规则/R1-R5
              </Link>
              <Link href={reviewEventsHref({ returnTo: detailReturnHref })} className="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-rose-800 ring-1 ring-rose-100 hover:bg-rose-100">
                打开复查队列
              </Link>
            </div>
          </div>
        ) : null}

        <div className="mt-5 grid gap-4 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="rounded-2xl bg-slate-950 p-5 text-white">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${detailGate.className}`}>
                {detailGate.label}
              </span>
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-slate-200">
                证据 {detailGate.evidenceGrade}
              </span>
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-slate-200">
                {formalReportBlocked ? `正式报告待补证：${formalReportBlockReason}` : `硬缺口 ${salesRuleHardGapCount ?? '待扫'} 项`}
              </span>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-white/10 p-3">
                <div className="text-xs text-slate-300">近一年收益 / 回撤</div>
                <div className="mt-1 text-lg font-semibold">{formatPercent(detailGate.annualReturn)} / {formatPercent(detailGate.maxDrawdown)}</div>
              </div>
              <div className="rounded-xl bg-white/10 p-3">
                <div className="text-xs text-slate-300">规模 / 开放状态</div>
                <div className="mt-1 text-lg font-semibold">{detailGate.totalAsset == null ? '规模待补' : `${detailGate.totalAsset.toFixed(2)} 亿`} / {detailGate.operationLabel}</div>
              </div>
              <div className="rounded-xl bg-white/10 p-3 sm:col-span-2">
                <div className="text-xs text-slate-300">基金经理</div>
                <div className="mt-1 text-sm font-semibold leading-6">{managerSummary}</div>
              </div>
            </div>
            <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200">
              {buyEvidence?.conclusion || '申赎执行证据待补，研究复核必须复核销售平台。'}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-4">
              <div className="text-sm font-semibold text-emerald-950">可用证据</div>
              <div className="mt-3 space-y-2">
                <div className="rounded-lg bg-white px-3 py-2 text-sm text-emerald-900">费率：{detailGate.feeSummary}</div>
                <div className="rounded-lg bg-white px-3 py-2 text-sm text-emerald-900">净值日期：{fund.navDate || '待补'}</div>
                <div className="rounded-lg bg-white px-3 py-2 text-sm text-emerald-900">持有体验：{purchaseSimulation ? `${purchaseSimulation.period.observations} 条净值样本` : '待测算'}</div>
              </div>
            </div>
            <div className="rounded-xl border border-amber-100 bg-amber-50 p-4">
              <div className="text-sm font-semibold text-amber-950">必须补证</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {[...detailGate.cautionFlags, ...salesRuleGapMissingItems, ...requiredMissingItems.map((item) => item.label)].slice(0, 8).map((item, index) => (
                  <span key={`one-page-gap-${index}-${item}`} className="rounded-full bg-white px-3 py-1 text-xs text-amber-800">{item}</span>
                ))}
                {detailGate.cautionFlags.length === 0 && salesRuleGapMissingItems.length === 0 && requiredMissingItems.length === 0 ? (
                  <span className="rounded-full bg-white px-3 py-1 text-xs text-amber-800">暂无高优先级缺口</span>
                ) : null}
              </div>
            </div>
            <div className="rounded-xl border border-blue-100 bg-blue-50 p-4 md:col-span-2">
              <div className="text-sm font-semibold text-blue-950">复制版摘要</div>
              <pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-white p-3 text-xs leading-5 text-slate-700">{onePageMemo}</pre>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl bg-white p-6 shadow">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">基金经理证据</h2>
            <p className="mt-1 text-sm text-gray-500">
              来自 Tushare fund_manager，用于研究复核经理是否明确、任期是否足够形成可观察样本。
            </p>
          </div>
          <span className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">
            {fund.managers?.length ? '已接入经理明细' : '待补经理明细'}
          </span>
        </div>
        {fund.managers?.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {fund.managers.map((manager) => (
              <div key={manager.managerId || manager.name} className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="text-base font-semibold text-slate-950">{manager.name || '姓名待补'}</div>
                    <div className="mt-1 text-xs text-slate-500">{manager.managerId || manager.windCode || 'manager_id 待补'}</div>
                  </div>
                  <span className="rounded-full bg-white px-2 py-1 text-xs text-slate-600">
                    {manager.source || 'tushare.fund_manager'}
                  </span>
                </div>
                <div className="mt-3 grid gap-2 text-sm text-slate-700 sm:grid-cols-3">
                  <div className="rounded-lg bg-white px-3 py-2">学历：{manager.education || '待补'}</div>
                  <div className="rounded-lg bg-white px-3 py-2">管理年限：{manager.managementYears == null ? '待核' : `${manager.managementYears.toFixed(1)}年`}</div>
                  <div className="rounded-lg bg-white px-3 py-2">在管基金：{manager.currentFunds?.length || 0} 只</div>
                </div>
                <div className="mt-3 text-xs text-slate-500">
                  任期：{manager.beginDate || '待补'} 至 {manager.endDate || '在任/待核'}；公司：{manager.company || '待补'}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            当前基金仅有经理 ID 或尚未同步经理明细。研究复核不要把经理维度视为已通过，应先补齐 fund_manager 数据。
          </div>
        )}
      </div>

      <div className="rounded-2xl bg-white p-6 shadow">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">持仓与行业暴露证据</h2>
            <p className="mt-1 text-sm text-gray-500">
              对标销售平台详情页的“重仓持股/行业配置”，但只展示通过可信过滤的持仓；疑似样例数据会被拦截。
            </p>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
            holdingEvidence?.status === 'available' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
          }`}>
            {holdingLoading ? '读取中' : holdingEvidence?.status === 'available' ? `已验证 ${holdingEvidence.quarter}` : '持仓待补'}
          </span>
        </div>

        {holdingEvidence?.status === 'available' ? (
          <div className="space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4" data-testid="fund-holding-exposure-decision-card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold text-slate-500">持仓暴露研究判断</div>
                  <div className="mt-1 text-lg font-semibold text-slate-950">{holdingExposureDecision.label}</div>
                  <div className="mt-2 text-sm leading-6 text-slate-600">{holdingExposureDecision.primaryRisk}</div>
                </div>
                <div className="rounded-xl bg-white px-4 py-3 text-right ring-1 ring-slate-100">
                  <div className="text-xs text-slate-500">暴露分</div>
                  <div className="text-2xl font-bold text-slate-950">{holdingExposureDecision.score}</div>
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <div className="rounded-xl bg-white px-3 py-2 text-sm text-slate-700 ring-1 ring-slate-100">
                  前十大：<span className="font-semibold text-slate-950">{formatPercent(holdingExposureDecision.topTenWeight)}</span>
                </div>
                <div className="rounded-xl bg-white px-3 py-2 text-sm text-slate-700 ring-1 ring-slate-100">
                  第一行业：<span className="font-semibold text-slate-950">{holdingExposureDecision.topIndustry} {formatPercent(holdingExposureDecision.topIndustryWeight)}</span>
                </div>
                <div className="rounded-xl bg-white px-3 py-2 text-sm text-slate-700 ring-1 ring-slate-100">
                  研究动作：<span className="font-semibold text-slate-950">{holdingExposureDecision.nextAction}</span>
                </div>
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                <div className="rounded-xl bg-white p-3 text-xs leading-5 text-slate-600 ring-1 ring-slate-100">
                  <div className="font-semibold text-slate-900">当前判断依据</div>
                  <div className="mt-2 space-y-1">
                    {holdingExposureDecision.reasons.map((reason) => <div key={reason}>• {reason}</div>)}
                  </div>
                </div>
                <div className="rounded-xl bg-white p-3 text-xs leading-5 text-slate-600 ring-1 ring-slate-100">
                  <div className="font-semibold text-slate-900">结论反转条件</div>
                  <div className="mt-2 space-y-1">
                    {holdingExposureDecision.reverseTriggers.map((trigger) => <div key={trigger}>• {trigger}</div>)}
                  </div>
                </div>
              </div>
            </div>
            <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="overflow-hidden rounded-xl border border-slate-100">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50 text-left text-xs font-medium text-slate-500">
                  <tr>
                    <th className="px-4 py-3">股票</th>
                    <th className="px-4 py-3">行业</th>
                    <th className="px-4 py-3">权重</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {holdingEvidence.holdings.slice(0, 10).map((holding) => (
                    <tr key={`${holding.stockCode}-${holding.stockName}`}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-900">{holding.stockName || '名称待补'}</div>
                        <div className="mt-1 text-xs text-slate-500">{holding.stockCode || '代码待补'}</div>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{holding.industry || '行业待补'}</td>
                      <td className="px-4 py-3 font-semibold text-slate-900">{formatPercent(holding.weight)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="rounded-xl border border-blue-100 bg-blue-50 p-4">
              <div className="text-sm font-semibold text-blue-950">行业权重</div>
              <div className="mt-3 space-y-2">
                {holdingEvidence.industryBuckets.slice(0, 6).map((bucket) => (
                  <div key={bucket.industry} className="rounded-lg bg-white px-3 py-2 text-sm text-blue-900">
                    <div className="flex items-center justify-between gap-3">
                      <span>{bucket.industry}</span>
                      <span className="font-semibold">{formatPercent(bucket.weight)}</span>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-3 text-xs leading-5 text-blue-700">
                前十大合计权重：{formatPercent(holdingEvidence.totalWeight)}；来源：{holdingEvidence.source}
              </div>
            </div>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-amber-100 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
            <div className="font-semibold">当前不展示持仓结论</div>
            <div className="mt-1">{holdingEvidence?.note || '正在读取或尚未取得可验证持仓。'}</div>
            <div className="mt-3 grid gap-2 text-xs md:grid-cols-3">
              <div className="rounded-lg bg-white px-3 py-2">已检查季度：{holdingEvidence?.checkedQuarters?.join(' / ') || '待读取'}</div>
              <div className="rounded-lg bg-white px-3 py-2">已拦截疑似样例：{holdingEvidence?.rejectedMockLikeQuarters?.length || 0}</div>
              <div className="rounded-lg bg-white px-3 py-2">研究动作：补齐季报持仓后再判断行业/个股暴露</div>
            </div>
            <div className="mt-3 rounded-lg bg-white px-3 py-2 text-xs" data-testid="fund-holding-exposure-decision-card">
              持仓暴露研究判断：{holdingExposureDecision.label}；{holdingExposureDecision.nextAction}
            </div>
          </div>
        )}
      </div>

      <div className="overflow-hidden rounded-2xl bg-slate-950 shadow">
        <div className="grid gap-0 lg:grid-cols-[1.1fr_1fr]">
          <div className="p-6 text-white">
            <div className="flex items-center gap-2 text-sm font-semibold text-emerald-200">
              <ShieldCheck className="h-5 w-5" />
              研究复核诊断（{detailGate.profileLabel}）
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${detailGate.className}`}>
                {detailGate.label} · 证据 {detailGate.evidenceGrade}
              </span>
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs text-slate-200">研究用途，不提供申赎操作指令</span>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-5">
              <div className="rounded-xl bg-white/10 p-4">
                <div className="text-xs text-slate-300">近一年收益</div>
                <div className="mt-1 text-xl font-semibold">{formatPercent(detailGate.annualReturn)}</div>
              </div>
              <div className="rounded-xl bg-white/10 p-4">
                <div className="text-xs text-slate-300">最大回撤</div>
                <div className="mt-1 text-xl font-semibold text-rose-200">{formatPercent(detailGate.maxDrawdown)}</div>
              </div>
              <div className="rounded-xl bg-white/10 p-4">
                <div className="text-xs text-slate-300">年化波动</div>
                <div className="mt-1 text-xl font-semibold">{formatPercent(detailGate.volatility)}</div>
              </div>
              <div className="rounded-xl bg-white/10 p-4">
                <div className="text-xs text-slate-300">开放状态</div>
                <div className="mt-1 text-base font-semibold">{detailGate.operationLabel}</div>
              </div>
              <div className="rounded-xl bg-white/10 p-4">
                <div className="text-xs text-slate-300">费率证据</div>
                <div className="mt-1 text-sm font-semibold leading-5">{detailGate.feeSummary}</div>
              </div>
            </div>
            {detailGate.hardBlocks.length ? (
              <div className="mt-5 rounded-xl border border-rose-300/20 bg-rose-400/10 p-4">
                <div className="text-sm font-semibold text-rose-100">硬性阻断</div>
                <div className="mt-2 space-y-1 text-sm text-rose-100">
                  {detailGate.hardBlocks.map((item) => <div key={item}>• {item}</div>)}
                </div>
              </div>
            ) : (
              <div className="mt-5 rounded-xl border border-emerald-300/20 bg-emerald-400/10 p-4 text-sm text-emerald-100">
                暂无硬性阻断，但仍需完成销售端状态、费率和持仓证据复核。
              </div>
            )}
          </div>

          <div className="border-t border-white/10 bg-white/[0.03] p-6 lg:border-l lg:border-t-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
              <ClipboardCheck className="h-5 w-5 text-amber-200" />
              研究复核前必须复核
            </div>
            <div className="mt-4 space-y-2">
              {detailGate.mustVerifyBeforeBuy.map((item) => (
                <div key={item} className="rounded-xl bg-white/10 px-3 py-2 text-sm text-slate-200">• {item}</div>
              ))}
            </div>
            {detailGate.cautionFlags.length ? (
              <div className="mt-5">
                <div className="text-xs font-semibold text-amber-100">补证提示</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {detailGate.cautionFlags.slice(0, 5).map((item) => (
                    <span key={item} className="rounded-full bg-amber-300/10 px-3 py-1 text-xs text-amber-100">{item}</span>
                  ))}
                </div>
              </div>
            ) : null}
            {detailGate.dataGaps.length ? (
              <div className="mt-5">
                <div className="text-xs font-semibold text-slate-200">当前数据缺口</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {detailGate.dataGaps.map((gap) => (
                    <span key={gap} className="rounded-full bg-white/10 px-3 py-1 text-xs text-slate-200">{gap}</span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {fund.buyEvidence ? (
        <div className="rounded-2xl bg-white p-6 shadow">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">销售端申赎规则核查</h2>
              <p className="mt-1 text-sm text-gray-500">
                区分“已入库证据”和“研究复核必须去销售平台复核”的缺口，避免把基础研究数据误当成可申赎操作结论。
                当前证据口径：{investorPurchasePlans[fund.buyEvidence.purchasePlan || investorPurchasePlan].label}。
              </p>
            </div>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${buyEvidenceClass(fund.buyEvidence.completenessLevel)}`}>
              证据完整度 {fund.buyEvidence.completenessScore ?? 0} · 硬缺口 {salesRuleHardGapCount ?? '待扫'}
            </span>
          </div>
          <div className={`mb-4 rounded-xl border p-4 ${
            salesRuleHardGapCount === 0
              ? 'border-emerald-100 bg-emerald-50'
              : 'border-rose-100 bg-rose-50'
          }`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className={`text-sm font-semibold ${salesRuleHardGapCount === 0 ? 'text-emerald-950' : 'text-rose-950'}`}>
                  销售规则硬缺口扫描
                </div>
                <div className={`mt-1 text-xs leading-5 ${salesRuleHardGapCount === 0 ? 'text-emerald-800' : 'text-rose-800'}`}>
                  {salesRuleGapLoading
                    ? '正在按当前基金代码扫描本地销售规则缺口...'
                    : salesRuleGapError
                      ? salesRuleGapError
                      : salesRuleHardGapCount === 0
                        ? '本地销售规则关键字段相对完整；研究复核仍需复核销售平台实时状态。'
                        : salesRuleHardGapCount === null
                          ? '尚未完成硬缺口扫描，不能把销售规则视为已通过。'
                          : `${salesRuleGap?.purchaseGateLabel || '代码级研究复核证据待补'}；优先级 ${salesRuleGap?.priority || 'high'}；下一步：${salesRuleGap?.nextAction || '补齐销售规则'}`}
                </div>
                <div
                  className={`mt-2 rounded-lg px-3 py-2 text-xs leading-5 ${
                    executionAmountGate?.status === 'pass'
                      ? 'bg-white text-emerald-800 ring-1 ring-emerald-100'
                      : executionAmountGate?.status === 'blocked'
                        ? 'bg-white text-rose-800 ring-1 ring-rose-100'
                        : 'bg-white text-amber-800 ring-1 ring-amber-100'
                  }`}
                  data-testid="fund-detail-execution-amount-gate"
                >
                  计划金额门禁：{executionAmountGate?.label || '金额门槛待扫描'}；{executionAmountGate?.detail || `当前${investorPurchasePlan === 'sip' ? '计划月扣款' : '计划配置'} ${formatMoney(currentPlannedAmount())}，需先完成销售规则扫描。`}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {salesRuleGapCanUseTushareFoundation ? (
                  <button
                    type="button"
                    onClick={() => void importTushareFoundationForFund()}
                    disabled={foundationHydrating || salesRuleGapLoading}
                    className="rounded-lg border border-cyan-200 bg-white px-3 py-2 text-xs font-medium text-cyan-700 hover:bg-cyan-50 disabled:cursor-not-allowed disabled:opacity-50"
                    title={`只导入 Tushare fund_basic 的申购/赎回起始状态和来源日期，不会补${foundationManualFields}。`}
                  >
                    {foundationHydrating ? '导入基础状态中...' : '先导入基础状态'}
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => void fetchSalesRuleGap(fund.windCode)}
                  disabled={salesRuleGapLoading || foundationHydrating}
                  className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-slate-700 ring-1 ring-black/5 hover:bg-slate-50 disabled:opacity-50"
                >
                  {salesRuleGapLoading ? '扫描中...' : '重新扫描'}
                </button>
                <Link
                  href={salesRulesHrefForFund()}
                  className="rounded-lg bg-slate-950 px-3 py-2 text-xs font-medium text-white hover:bg-slate-800"
                >
                  打开补证台
                </Link>
              </div>
            </div>
            {salesRuleGapMissingItems.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {salesRuleGapMissingItems.map((item, index) => (
                  <span key={`sales-rule-gap-chip-${index}-${item}`} className="rounded-full bg-white px-3 py-1 text-xs text-rose-800">{item}</span>
                ))}
              </div>
            ) : null}
          </div>
          <div className="mb-4 rounded-xl border border-indigo-100 bg-indigo-50 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-indigo-950">手工补录销售平台规则</div>
                <div className="mt-1 text-xs text-indigo-800">用于补齐 Tushare 不覆盖的{foundationManualFields}；保存后只写入本地 PostgreSQL。</div>
              </div>
              <button
                type="button"
                onClick={() => void saveSalesRule()}
                disabled={salesRuleSaving}
                className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {salesRuleSaving ? '保存中...' : '保存并刷新证据'}
              </button>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <label className="text-xs font-medium text-indigo-950">
                申购状态
                <select
                  name="sales-rule-purchase-status"
                  value={salesRuleForm.purchaseStatus}
                  onChange={(event) => setSalesRuleForm((current) => ({ ...current, purchaseStatus: event.target.value as SalesRuleFormState['purchaseStatus'] }))}
                  className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  <option value="unknown">申购待核</option>
                  <option value="open">开放申购</option>
                  <option value="limited">限额申购</option>
                  <option value="closed">暂停申购</option>
                </select>
              </label>
              <label className="text-xs font-medium text-indigo-950">
                申购费率 %
                <input name="sales-rule-purchase-fee-rate" value={salesRuleForm.purchaseFeeRate} onChange={(event) => setSalesRuleForm((current) => ({ ...current, purchaseFeeRate: event.target.value }))} inputMode="decimal" placeholder="如 0.15" className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900" />
              </label>
              <label className="text-xs font-medium text-indigo-950">
                赎回费率 %
                <input name="sales-rule-redemption-fee-rate" value={salesRuleForm.redemptionFeeRate} onChange={(event) => setSalesRuleForm((current) => ({ ...current, redemptionFeeRate: event.target.value }))} inputMode="decimal" placeholder="如 0.50" className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900" />
              </label>
              <label className="text-xs font-medium text-indigo-950">
                对应持有天数
                <input name="sales-rule-redemption-holding-days" value={salesRuleForm.redemptionHoldingDays} onChange={(event) => setSalesRuleForm((current) => ({ ...current, redemptionHoldingDays: event.target.value }))} inputMode="numeric" placeholder="如 7" className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900" />
              </label>
              <label className="text-xs font-medium text-indigo-950">
                最低申购金额
                <input name="sales-rule-min-purchase-amount" value={salesRuleForm.minPurchaseAmount} onChange={(event) => setSalesRuleForm((current) => ({ ...current, minPurchaseAmount: event.target.value }))} inputMode="decimal" placeholder="如 10" className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900" />
              </label>
              <label className="text-xs font-medium text-indigo-950">
                定投起点
                <input name="sales-rule-min-sip-amount" value={salesRuleForm.minSipAmount} onChange={(event) => setSalesRuleForm((current) => ({ ...current, minSipAmount: event.target.value }))} inputMode="decimal" placeholder="如 10" className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900" />
              </label>
              <label className="text-xs font-medium text-indigo-950">
                单日限购金额
                <input name="sales-rule-daily-limit-amount" value={salesRuleForm.dailyLimitAmount} onChange={(event) => setSalesRuleForm((current) => ({ ...current, dailyLimitAmount: event.target.value }))} inputMode="decimal" placeholder="留空表示待核" className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900" />
              </label>
              <label className="text-xs font-medium text-indigo-950">
                是否支持定投
                <select
                  name="sales-rule-supports-sip"
                  value={salesRuleForm.supportsSip}
                  onChange={(event) => setSalesRuleForm((current) => ({ ...current, supportsSip: event.target.value as SalesRuleFormState['supportsSip'] }))}
                  className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  <option value="">待核</option>
                  <option value="true">支持</option>
                  <option value="false">不支持</option>
                </select>
              </label>
              <label className="text-xs font-medium text-indigo-950">
                销售服务费 %
                <input name="sales-rule-sales-service-fee-rate" value={salesRuleForm.salesServiceFeeRate} onChange={(event) => setSalesRuleForm((current) => ({ ...current, salesServiceFeeRate: event.target.value }))} inputMode="decimal" placeholder="A类通常留空" className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900" />
              </label>
              <label className="text-xs font-medium text-indigo-950">
                平台风险等级
                <input name="sales-rule-risk-level" value={salesRuleForm.riskLevel} onChange={(event) => setSalesRuleForm((current) => ({ ...current, riskLevel: event.target.value }))} placeholder="如 R3" className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900" />
              </label>
              <label className="text-xs font-medium text-indigo-950">
                来源日期
                <input name="sales-rule-source-updated-at" type="date" value={salesRuleForm.sourceUpdatedAt} onChange={(event) => setSalesRuleForm((current) => ({ ...current, sourceUpdatedAt: event.target.value }))} className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900" />
              </label>
              <label className="text-xs font-medium text-indigo-950">
                来源链接
                <input name="sales-rule-source-url" value={salesRuleForm.sourceUrl} onChange={(event) => setSalesRuleForm((current) => ({ ...current, sourceUrl: event.target.value }))} placeholder="销售平台或合同链接" className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900" />
              </label>
              <label className="text-xs font-medium text-indigo-950 md:col-span-4">
                备注
                <input name="sales-rule-notes" value={salesRuleForm.notes} onChange={(event) => setSalesRuleForm((current) => ({ ...current, notes: event.target.value }))} placeholder="例如：来自天天基金页面，研究复核仍需复核实时状态" className="mt-1 w-full rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm text-slate-900" />
              </label>
            </div>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-blue-100 bg-blue-50 p-4 lg:col-span-2">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-blue-950">本地销售规则覆盖</div>
                  <div className="mt-1 text-xs text-blue-800">
                    {fund.salesRule
                      ? `${fund.salesRule.platform || 'manual'} · ${fund.salesRule.purchaseStatusLabel || '状态待核'} · 更新 ${fund.salesRule.sourceUpdatedAt || '待补'}`
                      : '未配置销售平台规则；当前仅使用 Tushare 基础字段和必补清单。'}
                  </div>
                </div>
                <Link
                  href={`/api/funds/${encodeURIComponent(fund.windCode)}/materials?purchasePlan=${investorPurchasePlan}`}
                  className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-blue-700 ring-1 ring-blue-100 hover:bg-blue-50"
                >
                  查看规则 API
                </Link>
                <Link
                  href={salesRulesHrefForFund()}
                  className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-700"
                >
                  去维护台补规则
                </Link>
                {!hasRedemptionRule ? (
                  <Link
                    href={redemptionRuleBackfillHref}
                    data-testid="fund-detail-sales-rule-redemption-backfill-link"
                    className="rounded-lg bg-orange-600 px-3 py-2 text-xs font-medium text-white hover:bg-orange-700"
                  >
                    补赎回费/持有期
                  </Link>
                ) : null}
              </div>
              {fund.salesRule ? (
                <div className="mt-3 grid gap-2 text-xs text-blue-900 md:grid-cols-4">
                  <div className="rounded-lg bg-white px-3 py-2">申购费：{fund.salesRule.purchaseFeeSourceBacked ? (fund.salesRule.purchaseFeeRate == null ? '待补' : `${fund.salesRule.purchaseFeeRate.toFixed(2)}%`) : '缺30天来源'}</div>
                  <div className="rounded-lg bg-white px-3 py-2">最低申购：{fund.salesRule.minPurchaseSourceBacked ? formatMoney(fund.salesRule.minPurchaseAmount) : '缺30天来源'}</div>
                  <div className="rounded-lg bg-white px-3 py-2">定投：{fund.salesRule.supportsSipSourceBacked ? (fund.salesRule.supportsSip == null ? '待核' : fund.salesRule.supportsSip ? `支持 · ${fund.salesRule.minSipSourceBacked ? formatMoney(fund.salesRule.minSipAmount) : '起点缺来源'}` : '不支持') : '缺30天来源'}</div>
                  <div className="rounded-lg bg-white px-3 py-2">风险等级：{fund.salesRule.riskLevel || '待补'}</div>
                  <div className="rounded-lg bg-white px-3 py-2 md:col-span-4">
                    申赎字段来源背书：申购费、起购/定投、限购和销售服务费必须有 30 天内销售平台/基金合同来源；只有数值不进入正式研究判断。
                  </div>
                  <div className={`rounded-lg px-3 py-2 md:col-span-4 ${riskLevelSourceBacked ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-800'}`}>
                    R1-R5来源背书：{riskLevelEvidenceLabel || '待扫描'}{riskLevelEvidenceDetail ? `；${riskLevelEvidenceDetail}` : ''}
                  </div>
                </div>
              ) : null}
              <div className="mt-4 rounded-xl border border-amber-200 bg-white p-4" data-testid="fund-risk-source-audit-entry">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-amber-950">R1-R5 来源可信度闸门</div>
                    <div className="mt-1 max-w-3xl text-xs leading-5 text-amber-800">
                      单基金研究复核必须先确认 R1-R5 来自销售平台或基金合同，且来源日期处于 30 天研究复核窗口内；缺失、无来源或来源过期都会阻断正式候选、研究清单和正式研究复核报告。
                      Tushare fund_basic 只能作为基础档案字段，不能作为 R1-R5 适当性来源。
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link
                      href={salesRulesHrefForFund()}
                      className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-amber-800 ring-1 ring-amber-200 hover:bg-amber-50"
                    >
                      维护本基金规则
                    </Link>
                    <Link
                      href={riskLevelSourceAuditHref}
                      className="rounded-lg bg-amber-600 px-3 py-2 text-xs font-semibold text-white hover:bg-amber-700"
                    >
                      进入 R1-R5 补证队列
                    </Link>
                  </div>
                </div>
                <div className="mt-3 grid gap-2 text-xs text-amber-900 md:grid-cols-3">
                  <div className="rounded-lg bg-amber-50 px-3 py-2">当前状态：{riskLevelEvidenceLabel || '待扫描'}</div>
                  <div className="rounded-lg bg-amber-50 px-3 py-2">来源要求：销售平台 / 基金合同 / 可追溯公告</div>
                  <div className="rounded-lg bg-amber-50 px-3 py-2">正式路径：未背书前只能研究观察</div>
                </div>
              </div>
            </div>
            <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-4">
              <div className="text-sm font-semibold text-emerald-900">已知证据</div>
              <div className="mt-3 grid gap-2">
                {(fund.buyEvidence.knownItems || []).slice(0, 8).map((item) => (
                  <div key={`${item.label}-${item.value}`} className="rounded-lg bg-white px-3 py-2 text-sm text-emerald-900">
                    <div className="font-medium">{item.label}：{item.value}</div>
                    <div className="mt-0.5 text-xs text-emerald-700">{item.source} · {item.confidence}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-xl border border-amber-100 bg-amber-50 p-4">
              <div className="text-sm font-semibold text-amber-900">研究复核必须补证</div>
              <div className="mt-3 grid gap-2">
                {salesRuleGapMissingItems.slice(0, 8).map((item, index) => (
                  <div key={`sales-gap-${index}-${item}`} className="rounded-lg bg-white px-3 py-2 text-sm text-amber-900">
                    <div className="font-medium">{item}</div>
                    <div className="mt-0.5 text-xs text-amber-700">来自销售规则硬缺口扫描，研究复核需补齐本地证据并复核销售平台实时状态。</div>
                  </div>
                ))}
                {(fund.buyEvidence.missingItems || []).filter((item) => item.requiredBeforeBuy).slice(0, 8).map((item, index) => (
                  <div key={`buy-evidence-gap-${index}-${item.label}`} className="rounded-lg bg-white px-3 py-2 text-sm text-amber-900">
                    <div className="font-medium">{item.label}</div>
                    <div className="mt-0.5 text-xs text-amber-700">{item.reason}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="mt-4 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
            {fund.buyEvidence.conclusion}
          </div>
        </div>
      ) : null}

      <div className="rounded-2xl bg-white p-6 shadow">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">持有体验测算</h2>
            <p className="mt-1 text-sm text-gray-500">
              基于真实净值序列回放一次性配置假设和每月定投；费用后结果只在本地销售规则有费率证据时展示，不做未来收益预测。
            </p>
          </div>
          <button
            type="button"
            onClick={() => fund?.windCode && void fetchPurchaseSimulation(fund.windCode, simulationForm)}
            disabled={simulationLoading}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {simulationLoading ? '测算中...' : '刷新测算'}
          </button>
        </div>
        <div className="mb-5 grid gap-3 rounded-2xl border border-slate-100 bg-slate-50 p-4 md:grid-cols-4">
          <label className="text-xs font-medium text-slate-600">
            回放周期（月）
            <input
              name="simulation-months"
              value={simulationForm.months}
              onChange={(event) => setSimulationForm((current) => ({ ...current, months: event.target.value }))}
              inputMode="numeric"
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            一次性计划金额
            <input
              name="simulation-lump-sum-amount"
              value={simulationForm.lumpSumAmount}
              onChange={(event) => setSimulationForm((current) => ({ ...current, lumpSumAmount: event.target.value }))}
              inputMode="decimal"
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            每月定投金额
            <input
              name="simulation-monthly-amount"
              value={simulationForm.monthlyAmount}
              onChange={(event) => setSimulationForm((current) => ({ ...current, monthlyAmount: event.target.value }))}
              inputMode="decimal"
              className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900"
            />
          </label>
          <div className="rounded-xl bg-white px-3 py-2 text-xs text-slate-600 ring-1 ring-slate-100">
            <div className="font-medium text-slate-900">费用来源</div>
            <div className="mt-1 leading-5">
              {feeAdjustedCoverageLabel}；{feeAdjustedMissingText}
            </div>
            <div className="mt-1 leading-5 text-slate-500">
              平台：{feeAdjusted?.assumptions.salesRulePlatform || fund.salesRule?.platform || '待补'}
            </div>
          </div>
        </div>
        {purchaseSimulation ? (
          <>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-xl bg-slate-950 p-4 text-white">
                <div className="text-xs text-slate-300">净值样本</div>
                <div className="mt-1 text-xl font-semibold">{purchaseSimulation.period.observations} 条</div>
                <div className="mt-1 text-xs text-slate-300">
                  {purchaseSimulation.period.startDate} 至 {purchaseSimulation.period.endDate}
                </div>
              </div>
              <div className="rounded-xl border border-blue-100 bg-blue-50 p-4">
                <div className="text-xs text-blue-700">一次性配置假设 {formatMoney(purchaseSimulation.assumptions.lumpSumAmount)}</div>
                <div className="mt-2 text-2xl font-semibold text-blue-950">{formatPercent(purchaseSimulation.lumpSum.returnRate)}</div>
                <div className="mt-1 text-sm text-blue-800">
                  期末 {formatMoney(purchaseSimulation.lumpSum.endingValue)}，盈亏 {formatMoney(purchaseSimulation.lumpSum.profit)}
                </div>
                <div className="mt-1 text-xs text-blue-700">期间最大回撤 {formatPercent(purchaseSimulation.lumpSum.maxDrawdown)}</div>
                <div className="mt-3 rounded-lg bg-white/70 px-3 py-2 text-xs text-blue-800">
                  费用后 {formatPercent(lumpSumFeeAdjustedReturn)}；费用合计 {formatMoney(lumpSumFeeAdjustedCost)}
                  {lumpSumFeeAdjustedEndingValue !== null ? `；期末 ${formatMoney(lumpSumFeeAdjustedEndingValue)}` : ''}
                </div>
              </div>
              <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-4">
                <div className="text-xs text-emerald-700">每月定投 {formatMoney(purchaseSimulation.assumptions.monthlyAmount)}</div>
                <div className="mt-2 text-2xl font-semibold text-emerald-950">{formatPercent(purchaseSimulation.sip.returnRate)}</div>
                <div className="mt-1 text-sm text-emerald-800">
                  投入 {formatMoney(purchaseSimulation.sip.totalInvested)}，期末 {formatMoney(purchaseSimulation.sip.endingValue)}
                </div>
                <div className="mt-1 text-xs text-emerald-700">
                  扣款 {purchaseSimulation.sip.contributionCount} 次，账户回撤 {formatPercent(purchaseSimulation.sip.maxAccountDrawdown)}
                </div>
                <div className="mt-3 rounded-lg bg-white/70 px-3 py-2 text-xs text-emerald-800">
                  费用后 {formatPercent(sipFeeAdjustedReturn)}；费用合计 {formatMoney(sipFeeAdjustedCost)}
                  {sipFeeAdjustedEndingValue !== null ? `；期末 ${formatMoney(sipFeeAdjustedEndingValue)}` : ''}
                </div>
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <div className="rounded-xl bg-blue-50 p-4 text-sm text-blue-900">
                一次性申购费：{formatMoney(feeAdjusted?.lumpSum?.purchaseFee ?? simulationFeeEstimate?.lumpSumPurchaseFee ?? null)}
              </div>
              <div className="rounded-xl bg-blue-50 p-4 text-sm text-blue-900">
                一次性赎回费：{formatMoney(feeAdjusted?.lumpSum?.redemptionFee ?? null)}
              </div>
              <div className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-900">
                定投申购费：{formatMoney(feeAdjusted?.sip?.purchaseFee ?? simulationFeeEstimate?.sipPurchaseFee ?? null)}
              </div>
              <div className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-900">
                定投赎回费：{formatMoney(feeAdjusted?.sip?.redemptionFee ?? null)}
              </div>
            </div>
            <div className="mt-4 rounded-2xl border border-orange-100 bg-orange-50 p-4" data-testid="fund-detail-redemption-fee-ladder">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold text-orange-700">赎回费持有期阶梯</div>
                  <div className="mt-1 text-sm font-semibold text-orange-950">
                    {lumpSumRedemptionRule
                      ? `一次性回放命中：${lumpSumRedemptionRule.label} · ${formatPercent(lumpSumRedemptionRule.feeRate)}`
                      : '一次性回放命中规则待补'}
                  </div>
                </div>
                <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-orange-800 ring-1 ring-orange-100">
                  持有 {feeAdjusted?.lumpSum?.holdingDays ?? '待补'} 天
                </span>
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                <div className="rounded-xl bg-white/80 p-3 text-xs leading-5 text-orange-900 ring-1 ring-orange-100">
                  <div className="font-semibold">一次性阶梯</div>
                  {lumpSumRedemptionLadder.length ? (
                    <div className="mt-1 space-y-1">
                      {lumpSumRedemptionLadder.slice(0, 4).map((rule) => (
                        <div key={`${rule.holdingDays ?? 'open'}-${rule.feeRate}-${rule.label}`} className={rule.isCurrent ? 'font-semibold text-orange-950' : ''}>
                          {rule.isCurrent ? '当前 · ' : ''}{rule.label} · {rule.holdingDays === null ? '开放持有期' : `${rule.holdingDays}天节点`} · {formatPercent(rule.feeRate)}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-1">赎回费阶梯待补，不能假设短持成本。</div>
                  )}
                </div>
                <div className="rounded-xl bg-white/80 p-3 text-xs leading-5 text-orange-900 ring-1 ring-orange-100" data-testid="fund-detail-sip-redemption-rule-buckets">
                  <div className="font-semibold">定投批次命中</div>
                  {sipRedemptionRuleBuckets.length ? (
                    <div className="mt-1 space-y-1">
                      {sipRedemptionRuleBuckets.slice(0, 4).map((bucket) => (
                        <div key={`${bucket.holdingDays ?? 'open'}-${bucket.feeRate}-${bucket.label}`}>
                          {bucket.label} · {formatPercent(bucket.feeRate)} · {bucket.lotCount} 批 · 赎回费 {formatMoney(bucket.redemptionFee)}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-1">定投各批次赎回规则待补，不把首条规则套用到所有批次。</div>
                  )}
                </div>
              </div>
              <div className="mt-3 rounded-xl bg-white/80 px-3 py-2 text-xs leading-5 text-orange-900 ring-1 ring-orange-100">
                研究复核口径：赎回费按真实回放持有天数逐笔匹配；规则缺失时只提示待补，不生成默认赎回成本。
              </div>
              {!lumpSumRedemptionLadder.length ? (
                <Link
                  href={redemptionRuleBackfillHref}
                  data-testid="fund-detail-redemption-rule-backfill-link"
                  className="mt-3 inline-flex rounded-lg bg-orange-700 px-3 py-2 text-xs font-semibold text-white hover:bg-orange-800"
                >
                  进入赎回规则补证队列
                </Link>
              ) : null}
            </div>
            {(lumpSumFeeAdjustedProfit !== null || sipFeeAdjustedProfit !== null) ? (
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-700">
                  一次性费用后盈亏：{formatMoney(lumpSumFeeAdjustedProfit)}
                </div>
                <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-700">
                  定投费用后盈亏：{formatMoney(sipFeeAdjustedProfit)}
                </div>
              </div>
            ) : null}
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <div className="rounded-xl bg-gray-50 p-4 text-sm text-gray-700">
                正收益月份：{purchaseSimulation.monthlyExperience.positiveMonths}/{purchaseSimulation.monthlyExperience.months}
              </div>
              <div className="rounded-xl bg-gray-50 p-4 text-sm text-gray-700">
                最好月份：{purchaseSimulation.monthlyExperience.bestMonth?.month || '-'} · {formatPercent(purchaseSimulation.monthlyExperience.bestMonth?.returnRate ?? null)}
              </div>
              <div className="rounded-xl bg-gray-50 p-4 text-sm text-gray-700">
                最差月份：{purchaseSimulation.monthlyExperience.worstMonth?.month || '-'} · {formatPercent(purchaseSimulation.monthlyExperience.worstMonth?.returnRate ?? null)}
              </div>
            </div>
            {purchaseSimulation.stressExperience ? (
              <div className="mt-4 rounded-2xl border border-rose-100 bg-rose-50 p-4" data-testid="fund-purchase-stress-experience">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold text-rose-700">持有压力体验</div>
                    <div className="mt-1 text-lg font-semibold text-rose-950">
                      {purchaseSimulation.stressExperience.label} · {purchaseSimulation.stressExperience.stressScore}分
                    </div>
                  </div>
                  <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-rose-800 ring-1 ring-rose-100">
                    最长亏损等待 {Math.round(purchaseSimulation.stressExperience.longestUnderwaterDays)} 天
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-rose-900">
                  {purchaseSimulation.stressExperience.interpretation}
                </p>
                <div className="mt-4 grid gap-3 md:grid-cols-4">
                  <div className="rounded-xl bg-white/80 px-3 py-2 text-xs text-rose-900 ring-1 ring-rose-100">
                    <div className="text-rose-600">最深回撤日</div>
                    <div className="mt-1 font-semibold">{purchaseSimulation.stressExperience.troughDate}</div>
                    <div className="mt-1">{formatPercent(purchaseSimulation.stressExperience.worstDrawdown)}</div>
                  </div>
                  <div className="rounded-xl bg-white/80 px-3 py-2 text-xs text-rose-900 ring-1 ring-rose-100">
                    <div className="text-rose-600">回本等待</div>
                    <div className="mt-1 font-semibold">
                      {purchaseSimulation.stressExperience.recoveryDays === null ? '回放期未回本' : `${purchaseSimulation.stressExperience.recoveryDays} 天`}
                    </div>
                    <div className="mt-1">相对前高口径</div>
                  </div>
                  <div className="rounded-xl bg-white/80 px-3 py-2 text-xs text-rose-900 ring-1 ring-rose-100">
                    <div className="text-rose-600">最长连跌</div>
                    <div className="mt-1 font-semibold">{purchaseSimulation.stressExperience.longestLosingStreakMonths} 个月</div>
                    <div className="mt-1">按月末净值</div>
                  </div>
                  <div className="rounded-xl bg-white/80 px-3 py-2 text-xs text-rose-900 ring-1 ring-rose-100">
                    <div className="text-rose-600">最差三个月</div>
                    <div className="mt-1 font-semibold">
                      {purchaseSimulation.stressExperience.worstThreeMonthReturn
                        ? `${purchaseSimulation.stressExperience.worstThreeMonthReturn.startMonth}~${purchaseSimulation.stressExperience.worstThreeMonthReturn.endMonth}`
                        : '样本不足'}
                    </div>
                    <div className="mt-1">{formatPercent(purchaseSimulation.stressExperience.worstThreeMonthReturn?.returnRate ?? null)}</div>
                  </div>
                </div>
                <div className="mt-3 rounded-xl bg-white/80 px-3 py-2 text-xs leading-5 text-rose-900 ring-1 ring-rose-100">
                  研究使用方式：若最长亏损等待超过计划持有期、最差三个月超出心理承受，不能只凭长期收益或评分进入研究候选。
                </div>
              </div>
            ) : null}
            <div className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">
              {purchaseSimulation.disclaimer}
              {feeAdjusted?.coverage === 'full'
                ? ' 本次费用后结果已使用本地合并销售规则中的申购费和赎回费。'
                : ` 当前费用证据不完整（${feeAdjustedMissingText}），不能把费用后结果当成正式研究复核结论。`}
            </div>
          </>
        ) : (
          <div className="rounded-xl border border-dashed border-gray-200 p-8 text-center text-sm text-gray-500">
            {simulationLoading ? '正在读取真实净值并测算...' : '当前净值样本不足，暂无法测算。'}
          </div>
        )}
      </div>

      {fund.peerPercentiles?.metrics ? (
        <div className="rounded-2xl bg-white p-6 shadow">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-lg font-semibold text-gray-900">
                <BarChart3 className="h-5 w-5 text-indigo-600" />
                同类分位
              </div>
              <p className="mt-1 text-sm text-gray-500">
                按 {fund.peerPercentiles.peer_group || fund.peerPercentiles.fund_type || fund.type || '同类型'} 基金横向比较，避免只看绝对收益。
              </p>
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-indigo-50 px-3 py-1 text-indigo-700">
                样本 {fund.peerPercentiles.peer_count || '-'} 只
              </span>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">
                {fund.peerPercentiles.peer_group_source === 'fund_type_fallback' ? '按基金类型回退' : '按研究同类池'}
              </span>
              <span className={`rounded-full px-3 py-1 ${peerSampleInsufficient ? 'bg-amber-100 text-amber-800' : 'bg-emerald-50 text-emerald-700'}`}>
                {peerSampleInsufficient
                  ? `有效样本不足 ${peerMinimumSample} 只`
                  : peerEvidenceThin ? `可用指标 ${peerUsableMetricCount} 个，证据偏薄` : '样本口径可用'}
              </span>
            </div>
          </div>
          <div className={`mb-4 rounded-2xl border p-4 ${peerVerdictClass(peerInterpretation.tone)}`} data-testid="fund-peer-interpretation-card">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide opacity-70">同类研究复核解读</div>
                <h3 className="mt-1 text-base font-semibold">{peerInterpretation.title}</h3>
                <p className="mt-2 text-sm leading-6 opacity-85">{peerInterpretation.detail}</p>
              </div>
              <div className="shrink-0 space-y-2 lg:text-right">
                <div className="rounded-full bg-white/70 px-3 py-1 text-xs font-semibold ring-1 ring-black/5">
                  {peerInterpretation.verdict}
                </div>
                <Link
                  href={peerInterpretation.actionHref}
                  className="inline-flex rounded-lg bg-slate-950 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800"
                >
                  {peerInterpretation.actionLabel}
                </Link>
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <div className="rounded-xl bg-white/75 p-3 ring-1 ring-black/5">
                <div className="text-xs opacity-70">同类优势分</div>
                <div className="mt-1 text-xl font-semibold">{peerAdvantageScore ?? '待补'}</div>
                <div className="mt-1 text-xs opacity-70">综合专业分、收益、回撤、波动分位</div>
              </div>
              <div className="rounded-xl bg-white/75 p-3 ring-1 ring-black/5">
                <div className="text-xs opacity-70">主要优势</div>
                <div className="mt-1 text-sm font-semibold">
                  {peerStrengths.length ? peerStrengths.slice(0, 2).map((item) => `${item.label} ${item.percentile}`).join(' / ') : '暂无显著优势'}
                </div>
              </div>
              <div className="rounded-xl bg-white/75 p-3 ring-1 ring-black/5">
                <div className="text-xs opacity-70">主要短板</div>
                <div className="mt-1 text-sm font-semibold">
                  {peerWeaknesses.length ? peerWeaknesses.slice(0, 2).map((item) => `${item.label} ${item.percentile}`).join(' / ') : '暂无尾部短板'}
                </div>
              </div>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-4">
            {Object.entries(fund.peerPercentiles.metrics).map(([metricName, metric]) => (
              <div key={metricName} className="rounded-xl border border-gray-100 bg-gray-50 p-4">
                <div className="text-xs text-gray-500">{metric.label || metricName}</div>
                <div className="mt-1 text-lg font-semibold text-gray-900">{formatPeerMetricValue(metric.value, metric.unit)}</div>
                <div className={`mt-3 inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${peerPercentileClass(metric.percentile)}`}>
                  分位 {metric.percentile ?? '-'} · 排名 {metric.rank ?? '-'}/{metric.peer_count || '-'}
                </div>
                <div className="mt-2 text-xs text-gray-500">
                  {metric.sample_status === 'insufficient_peer_sample'
                    ? `有效样本不足 ${metric.minimum_peer_count || peerMinimumSample} 只，不纳入同类优势判断`
                    : metric.direction === 'lower' ? '数值越低越好' : '数值越高越好'}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {fund.researchProfile && (
        <div className="rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">研究画像</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
            <div>
              <p className="text-sm text-gray-500">同类池</p>
              <p className="mt-1 text-sm font-medium text-gray-900">{fund.researchProfile.peerGroup || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">主基准</p>
              <p className="mt-1 text-sm font-medium text-gray-900">{fund.researchProfile.primaryBenchmark || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">风格标签</p>
              <p className="mt-1 text-sm font-medium text-gray-900">{fund.researchProfile.styleLabel || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">经理任期起点</p>
              <p className="mt-1 text-sm font-medium text-gray-900">{formatDateText(fund.researchProfile.managerTenureStart)}</p>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-lg bg-gray-50 p-4">
              <p className="text-sm font-medium text-gray-700">容量 / 流动性备注</p>
              <p className="mt-2 text-sm text-gray-600">{fund.researchProfile.capacityNotes || '暂无容量备注'}</p>
            </div>
            <div className="rounded-lg bg-gray-50 p-4">
              <p className="text-sm font-medium text-gray-700">数据质量备注</p>
              <p className="mt-2 text-sm text-gray-600">{fund.researchProfile.dataQualityNotes || '暂无数据质量备注'}</p>
            </div>
          </div>
          {fund.researchProfile.strategyTags && fund.researchProfile.strategyTags.length > 0 ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {fund.researchProfile.strategyTags.map((tag) => (
                <span key={tag} className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">{tag}</span>
              ))}
            </div>
          ) : null}
        </div>
      )}

      {rollingMetricRows.length > 0 && (
        <div className="rounded-lg bg-white p-6 shadow">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">滚动评价</h2>
              <p className="mt-1 text-sm text-gray-500">按 3M / 6M / 1Y / 3Y 观察收益、回撤、波动与胜率。</p>
            </div>
            <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">MetricSnapshot</span>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-100 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">窗口</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">区间收益</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">年化收益</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">最大回撤</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">年化波动</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">胜率</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">夏普 / Calmar</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {rollingMetricRows.map(({ window, label, metrics }) => (
                  <tr key={window}>
                    <td className="px-4 py-3 font-semibold text-gray-900">
                      {label}
                      {metrics?.tenure_days ? <div className="text-xs font-normal text-gray-500">{Number(metrics.tenure_days).toFixed(0)} 天</div> : null}
                    </td>
                    <td className="px-4 py-3 text-gray-900">{formatPercent(metrics?.total_return)}</td>
                    <td className="px-4 py-3 text-gray-900">{formatPercent(metrics?.annualized_return)}</td>
                    <td className="px-4 py-3 text-rose-700">{formatPercent(metrics?.max_drawdown)}</td>
                    <td className="px-4 py-3 text-gray-900">{formatPercent(metrics?.annualized_volatility)}</td>
                    <td className="px-4 py-3 text-emerald-700">{formatPercent(metrics?.positive_return_ratio)}</td>
                    <td className="px-4 py-3 text-gray-900">{formatRatio(metrics?.sharpe_ratio)} / {formatRatio(metrics?.calmar_ratio)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 text-xs text-gray-500">
            口径：优先使用研究画像中的同类池与主基准，指标由净值序列滚动切片计算。
          </div>
        </div>
      )}

      {fund.professionalScoring && (
        <div className="rounded-lg bg-white p-6 shadow">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">专业评分</h2>
              <p className="mt-1 text-sm text-gray-500">按基金类型、同类池、滚动指标、任期切片和数据质量综合评分。</p>
            </div>
            <div className="text-right">
              <div className="text-3xl font-bold text-blue-700">{Number(fund.professionalScoring.overall_score ?? 0).toFixed(1)}</div>
              <div className="mt-1 text-sm text-gray-500">评级 {fund.professionalScoring.overall_grade || '-'}</div>
            </div>
          </div>
          <div className="mb-4 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-blue-50 px-3 py-1 font-medium text-blue-700">{fund.professionalScoring.fund_type_profile || 'unknown'}</span>
            <span className="rounded-full bg-gray-100 px-3 py-1 text-gray-700">{fund.professionalScoring.peer_group || '待分类'}</span>
            <span className="rounded-full bg-gray-100 px-3 py-1 text-gray-700">{fund.professionalScoring.primary_benchmark || '待映射基准'}</span>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {Object.entries(fund.professionalScoring.dimension_scores || {}).map(([key, item]) => (
              <div key={key} className="rounded-lg border border-gray-200 p-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-gray-700">{dimensionLabels[key] || key}</p>
                  <p className="text-sm font-semibold text-gray-900">{Number(item.score ?? 0).toFixed(1)}</p>
                </div>
                <div className="mt-2 h-2 rounded-full bg-gray-100">
                  <div className="h-2 rounded-full bg-blue-500" style={{ width: `${Math.max(0, Math.min(100, Number(item.score ?? 0)))}%` }} />
                </div>
                <p className="mt-2 text-xs text-gray-500">权重 {Math.round(Number(item.weight ?? 0) * 100)}%</p>
              </div>
            ))}
          </div>
          {(fund.professionalScoring.positive_factors?.length || fund.professionalScoring.negative_factors?.length) ? (
            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
                <div className="font-medium">加分因子</div>
                <ul className="mt-1 list-disc pl-5">
                  {(fund.professionalScoring.positive_factors || []).slice(0, 4).map((factor) => <li key={factor}>{factor}</li>)}
                </ul>
              </div>
              <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                <div className="font-medium">复核因子</div>
                <ul className="mt-1 list-disc pl-5">
                  {(fund.professionalScoring.negative_factors || ['暂无明显扣分项']).slice(0, 4).map((factor) => <li key={factor}>{factor}</li>)}
                </ul>
              </div>
            </div>
          ) : null}
        </div>
      )}

      <div className="rounded-lg bg-white p-6 shadow">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">数据可信度</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <div>
            <p className="text-sm text-gray-500">数据截至日期</p>
            <p className="mt-1 text-sm font-medium text-gray-900">{formatDateTimeText(fund.trust?.dataAsOf)}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">最近同步时间</p>
            <p className="mt-1 text-sm font-medium text-gray-900">{formatDateTimeText(fund.trust?.syncedAt)}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">评分记录数</p>
            <p className="mt-1 text-sm font-medium text-gray-900">{fund.trust?.scoreCount ?? 0}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">研究报告数</p>
            <p className="mt-1 text-sm font-medium text-gray-900">{fund.trust?.reportCount ?? 0}</p>
          </div>
        </div>
        <div className="mt-4 inline-flex rounded-full bg-blue-50 px-3 py-1 text-sm text-blue-700">
          数据完整度：{fund.trust?.dataQualityStatus || 'unknown'} · {fund.trust?.dataQualityScore ?? fund.dataQuality?.score ?? 0} 分
        </div>
        {fund.dataQuality?.summary ? (
          <div className="mt-3 rounded-lg bg-gray-50 p-3 text-sm text-gray-700">{fund.dataQuality.summary}</div>
        ) : null}
        {fund.dataQuality?.issues && fund.dataQuality.issues.length > 0 ? (
          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            <div className="font-medium">待复核项</div>
            <ul className="mt-1 list-disc pl-5">
              {fund.dataQuality.issues.slice(0, 3).map((issue) => <li key={issue}>{issue}</li>)}
            </ul>
          </div>
        ) : null}
      </div>

      <div className="rounded-lg bg-white p-6 shadow">
        <NavChart fundCode={fund.windCode} fundName={fund.name} days={365} height={400} />
      </div>

      {fund.performanceData && Object.keys(fund.performanceData).length > 0 && (
        <div className="rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">业绩数据</h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {Object.entries(fund.performanceData).map(([key, value]) => (
              <div key={key} className="rounded-lg border border-gray-200 p-4">
                <p className="text-sm text-gray-500">{key}</p>
                <p className="text-lg font-semibold text-gray-900">{typeof value === 'number' ? value.toFixed(2) : String(value)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {fund.riskMetrics && Object.keys(fund.riskMetrics).length > 0 && (
        <div className="rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">风险指标</h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {Object.entries(fund.riskMetrics).map(([key, value]) => (
              <div key={key} className="rounded-lg border border-gray-200 p-4">
                <p className="text-sm text-gray-500">{key}</p>
                <p className="text-lg font-semibold text-gray-900">{typeof value === 'number' ? value.toFixed(2) : String(value)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {fund.scores && fund.scores.length > 0 && (
        <div className="rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">评分记录</h2>
          <div className="space-y-2">
            {fund.scores.map((score) => (
              <div key={String(score.id)} className="flex items-center justify-between border-b border-gray-100 pb-2">
                <span className="text-sm text-gray-600">{String(score.dimension)}</span>
                <span className="text-sm font-semibold text-gray-900">{Number(score.score).toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {fund.aiReports && fund.aiReports.length > 0 && (
        <div className="rounded-lg bg-white p-6 shadow">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-gray-900">基金研究报告</h2>
            <Link href={`/analysis/fund?fundId=${fund.id}`} className="text-sm font-medium text-blue-600 hover:text-blue-700">继续分析</Link>
          </div>
          <div className="space-y-3">
            {fund.aiReports.map((report) => {
              const reportType = String(report.reportType ?? report.report_type ?? '分析报告')
              const isPrePurchaseReport = reportType === 'fund_pre_purchase_check'
              const stalePrePurchaseReport = isPrePurchaseReport && formalReportBlocked
              const buyBeforeDecision = report.buyBeforeDecision as {
                status?: string
                label?: string
                hardBlocks?: string[]
                cautionFlags?: string[]
                nextActions?: string[]
              } | null | undefined
              const buyBeforeGateStatus = buyBeforeDecision?.status || ''
              const buyBeforeGateClassName = buyBeforeGateStatus === 'blocked_by_hard_gate'
                ? 'bg-rose-100 text-rose-800'
                : buyBeforeGateStatus === 'verify_first'
                  ? 'bg-amber-100 text-amber-800'
                  : buyBeforeGateStatus === 'research_ready'
                    ? 'bg-emerald-100 text-emerald-800'
                    : 'bg-slate-100 text-slate-700'
              const riskLevelGatePolicy = report.riskLevelGatePolicy as ReportRiskLevelGatePolicy | null | undefined
              const reportBuyBeforeQueue = buyBeforeDecision
                ? buildBuyBeforeEvidenceQueue([{
                    targetType: 'fund',
                    targetId: fund.windCode,
                    relatedCodes: [fund.windCode],
                    purchasePlan: investorPurchasePlan,
                    decisionSummary: {
                      buyBeforeGateStatus,
                      buyBeforeGateHardBlocks: buyBeforeDecision.hardBlocks || [],
                      buyBeforeGateCautionFlags: buyBeforeDecision.cautionFlags || [],
                    },
                  }])
                : []
              return (
                <div
                  key={String(report.id)}
                  className={`rounded-lg border p-4 transition-colors ${
                    stalePrePurchaseReport ? 'border-amber-200 bg-amber-50 hover:border-amber-300' : 'border-gray-200 hover:border-blue-300'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-gray-900">{reportType}</span>
                      {stalePrePurchaseReport ? (
                        <span className="rounded-full bg-amber-100 px-2 py-1 text-[11px] font-semibold text-amber-800">
                          当前证据待补，仅供回看
                        </span>
                      ) : null}
                      {buyBeforeDecision ? (
                        <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${buyBeforeGateClassName}`} data-testid="fund-detail-report-buy-before-gate">
                          研究复核总闸门：{buyBeforeDecision.label || buyBeforeGateStatus}
                        </span>
                      ) : null}
                      {riskLevelGatePolicy ? (
                        <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${riskLevelPolicyBadgeClass(riskLevelGatePolicy.tone)}`} data-testid="fund-detail-report-risk-level-policy">
                          R1-R5：{riskLevelGatePolicy.label}
                        </span>
                      ) : null}
                    </div>
                    <span className="text-xs text-gray-500">{formatDateText(String(report.createdAt ?? report.created_at ?? ''))}</span>
                  </div>
                  {riskLevelGatePolicy?.requiresRegeneration ? (
                    <div className="mt-2 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900" data-testid="fund-detail-report-risk-level-policy-card">
                      <div className="font-semibold">
                        R1-R5 旧门禁/未标记：不能证明已采用 30 天来源背书
                      </div>
                      <div className="mt-1 text-amber-800">
                        {riskLevelGatePolicy.detail}
                      </div>
                      <Link
                        href={riskLevelSourceAuditHref}
                        className="mt-2 inline-flex font-semibold text-amber-800 underline underline-offset-2"
                      >
                        进入 R1-R5 来源补证队列
                      </Link>
                    </div>
                  ) : null}
                  {buyBeforeDecision ? (
                    <div className={`mt-2 rounded-xl px-3 py-2 text-xs leading-5 ${
                      buyBeforeGateStatus === 'blocked_by_hard_gate'
                        ? 'bg-rose-50 text-rose-800'
                        : buyBeforeGateStatus === 'verify_first'
                          ? 'bg-amber-50 text-amber-800'
                          : 'bg-emerald-50 text-emerald-800'
                    }`}>
                      {buyBeforeDecision.hardBlocks?.[0]
                        || buyBeforeDecision.cautionFlags?.[0]
                        || buyBeforeDecision.nextActions?.[0]
                        || '报告已保存研究复核总闸门；正式研究复核仍需复核销售平台实时规则。'}
                    </div>
                  ) : null}
                  {reportBuyBeforeQueue.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-2" data-testid="fund-detail-report-buy-before-actions">
                      {reportBuyBeforeQueue.slice(0, 3).map((item) => (
                        <Link
                          key={item.key}
                          href={buyBeforeActionHrefForDetail(item.href)}
                          className="inline-flex items-center rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-700 hover:border-blue-200 hover:text-blue-700"
                        >
                          {item.action}
                          <span className="ml-1 text-slate-400">· {item.count}</span>
                        </Link>
                      ))}
                    </div>
                  ) : null}
                  {stalePrePurchaseReport ? (
                    <div className="mt-2 text-xs leading-5 text-amber-800">
                      当前{formalReportBlockSummary}，这份旧研究复核不能作为继续研究的有效报告；请先补证后重新生成。
                    </div>
                  ) : null}
                  {report.content ? (
                    <p className={`mt-2 line-clamp-2 text-sm ${stalePrePurchaseReport ? 'text-amber-900' : 'text-gray-600'}`}>{String(report.content)}</p>
                  ) : null}
                  {report.id ? (
                    <Link
                      href={`/reports/${encodeURIComponent(String(report.id))}`}
                      className={`mt-3 inline-flex text-xs font-semibold underline underline-offset-2 ${stalePrePurchaseReport ? 'text-amber-800' : 'text-blue-700'}`}
                    >
                      查看报告详情
                    </Link>
                  ) : null}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
