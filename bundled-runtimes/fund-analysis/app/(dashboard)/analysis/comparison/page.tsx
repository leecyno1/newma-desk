'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, BarChart3, ClipboardCheck, Copy, Download, GitCompare, Loader2, Percent, ShieldCheck, Trophy } from 'lucide-react'
import { buildShareClassInfoByCode, type ShareClassInfo } from '@/lib/share-class'
import { salesRuleFoundationManualFieldsForPlan } from '@/lib/sales-rule-purchase-plan-copy'
import { canonicalResearchHref, materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'

type FundSummary = {
  id?: string | null
  wind_code: string
  name: string
  type: string
  peer_group?: string
  primary_benchmark?: string
  peer_count?: number
  professional_score?: number | null
  professional_grade?: string | null
  operation_status?: {
    status?: 'blocked' | 'watch' | 'unknown'
    label?: string
    reason?: string
    purchase_start_date?: string | null
    redeem_start_date?: string | null
  } | null
  sales_status?: {
    purchase_start_date?: string | null
    redeem_start_date?: string | null
    status?: string | null
  } | null
  fee_info?: {
    management_fee?: number | null
    custodian_fee?: number | null
    missing?: string[]
  } | null
  benchmark?: string | null
  buy_evidence?: {
    completenessScore?: number
    completenessLevel?: 'strong' | 'partial' | 'thin'
    requiredMissingCount?: number
    conclusion?: string
  } | null
  shareClassInfo?: ShareClassInfo | null
}

type MatrixValue = {
  value: number | null
  display: string
  peer_percentile: number | null
}

type MatrixRow = {
  metric_name: string
  label: string
  unit: string
  direction: 'higher' | 'lower'
  window: string | null
  best_code: string | null
  values: Record<string, MatrixValue>
}

type ComparisonMatrix = {
  metric_window: string
  funds: FundSummary[]
  matrix_rows: MatrixRow[]
  recommendations: string[]
}

type ComparisonReportBlockAction = {
  code?: string
  salesRulesHref?: string
  alertsHref?: string
  alertCount?: number
}

type PurchaseSimulation = {
  source: string
  period: {
    startDate: string
    endDate: string
    observations: number
  }
  lumpSum: {
    totalInvested: number
    endingValue: number
    profit: number
    returnRate: number | null
    maxDrawdown: number | null
  }
  sip: {
    contributionCount: number
    totalInvested: number
    endingValue: number
    profit: number
    returnRate: number | null
    maxAccountDrawdown: number | null
  }
  feeAdjusted?: {
    coverage: 'none' | 'partial' | 'full'
    missingItems: string[]
    lumpSum: null | {
      totalFee: number
      endingValue: number
      profit: number
      returnRate: number | null
    }
    sip: null | {
      totalFee: number
      endingValue: number
      profit: number
      returnRate: number | null
    }
  }
  monthlyExperience: {
    months: number
    positiveMonths: number
    positiveRatio: number | null
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

type FundSimulationResult = {
  windCode: string
  name: string
  status: 'ok' | 'error'
  simulation?: PurchaseSimulation
  error?: string
}

type SalesRuleGap = {
  windCode: string
  fundName: string
  priority: 'high' | 'medium' | 'low'
  missingItems: string[]
  missingCount: number
  purchaseGateLabel: string
  nextAction: string
  ruleSourceUpdatedAt?: string | null
  alertsHref?: string | null
  gateSource?: string | null
}

type RawAlertEvent = {
  fund_id?: string | null
  event_type?: string
  status?: string
  title?: string
  message?: string
  details?: unknown
}

type SalesRuleExecutionAmountGate = {
  plannedAmount: number | null
  status: 'pass' | 'blocked' | 'unknown'
  label: string
  detail: string
  minPurchaseAmount: number | null
  minSipAmount: number | null
  dailyLimitAmount: number | null
}

type SalesRuleGapsPayload = {
  source: string
  totalMembers: number
  gapCount: number
  gaps: SalesRuleGap[]
  rules?: Array<{
    windCode: string
    executionAmountGate?: SalesRuleExecutionAmountGate
  }>
  summary: {
    high: number
    medium: number
    low: number
  }
}

type RiskProfile = 'conservative' | 'balanced' | 'aggressive'
type InvestmentHorizon = 'lt1y' | '1to3y' | 'gt3y'
type PurchasePlan = 'lump_sum' | 'sip'

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : {}
    } catch {
      return {}
    }
  }
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function stringValue(value: unknown) {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function alertFundCode(event: RawAlertEvent) {
  const details = asRecord(event.details)
  return (
    stringValue(details.wind_code) ||
    stringValue(details.fund_code) ||
    stringValue(event.fund_id)
  ).toUpperCase()
}
type DecisionScore = {
  windCode: string
  fund: FundSummary
  score: number
  label: string
  tone: 'emerald' | 'blue' | 'amber' | 'rose' | 'slate'
  gateLabel: string
  gateDetail: string
  simulationReturn: number | null
  simulationDrawdown: number | null
  stressScore: number | null
  longestUnderwaterDays: number | null
  worstThreeMonthReturn: number | null
  breakdown: Array<{
    key: string
    label: string
    rawScore: number
    contribution: number
    weight: number
    note: string
  }>
  scoreCaps: string[]
  reasons: string[]
  nextAction: string
  salesGap: SalesRuleGap | null
  feeComparable: boolean
}

const profileLabels: Record<RiskProfile, string> = {
  conservative: '稳健型',
  balanced: '均衡型',
  aggressive: '进取型',
}

const horizonLabels: Record<InvestmentHorizon, string> = {
  lt1y: '1年以内',
  '1to3y': '1-3年',
  gt3y: '3年以上',
}

const purchasePlanLabels: Record<PurchasePlan, string> = {
  lump_sum: '一次性配置假设',
  sip: '每月定投',
}

const profileOptions: Array<{ value: RiskProfile; label: string; note: string }> = [
  { value: 'conservative', label: '稳健型', note: '回撤和风险等级优先' },
  { value: 'balanced', label: '均衡型', note: '收益、风险和证据均衡' },
  { value: 'aggressive', label: '进取型', note: '接受更高波动看弹性' },
]

const horizonOptions: Array<{ value: InvestmentHorizon; label: string }> = [
  { value: 'lt1y', label: '1年以内' },
  { value: '1to3y', label: '1-3年' },
  { value: 'gt3y', label: '3年以上' },
]

const purchasePlanOptions: Array<{ value: PurchasePlan; label: string }> = [
  { value: 'sip', label: '每月定投' },
  { value: 'lump_sum', label: '一次性配置假设' },
]

function evidenceLabel(score: number | null | undefined) {
  const safeScore = score ?? 0
  if (safeScore >= 75) return '证据较完整'
  if (safeScore >= 45) return '证据部分覆盖'
  return '研究证据不足'
}

function parseCodes(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[\n,，\s]+/)
        .map((item) => item.trim())
        .filter(Boolean)
    )
  )
}

function percentileClass(value: number | null) {
  if (value === null || value === undefined) return 'bg-gray-100 text-gray-500'
  if (value >= 75) return 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100'
  if (value >= 50) return 'bg-blue-50 text-blue-700 ring-1 ring-blue-100'
  if (value >= 25) return 'bg-amber-50 text-amber-700 ring-1 ring-amber-100'
  return 'bg-rose-50 text-rose-700 ring-1 ring-rose-100'
}

function operationClass(status?: string) {
  if (status === 'blocked') return 'bg-rose-100 text-rose-800'
  if (status === 'watch') return 'bg-amber-100 text-amber-800'
  return 'bg-slate-100 text-slate-700'
}

function formatFee(value: number | null | undefined) {
  return value === null || value === undefined ? '待补' : `${Number(value).toFixed(2)}%`
}

function formatPercent(value: number | null | undefined) {
  return value === null || value === undefined ? '待补' : `${(value * 100).toFixed(2)}%`
}

function formatMoney(value: number | null | undefined) {
  return value === null || value === undefined ? '待补' : `${Number(value).toFixed(0)}元`
}

function tsvCell(value: unknown) {
  return String(value ?? '').replace(/\t|\r?\n/gu, ' ')
}

function safeFileStem(value: string) {
  return value.replace(/[\\/:*?"<>|\s]+/gu, '_').replace(/_+/gu, '_').replace(/^_|_$/gu, '').slice(0, 80) || 'comparison_decision'
}

function clampScore(value: number) {
  return Math.max(0, Math.min(100, value))
}

function buyEvidenceClass(level?: string) {
  if (level === 'strong') return 'bg-emerald-100 text-emerald-800'
  if (level === 'partial') return 'bg-amber-100 text-amber-800'
  return 'bg-rose-100 text-rose-800'
}

function decisionToneClass(tone: DecisionScore['tone']) {
  if (tone === 'emerald') return 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-100'
  if (tone === 'blue') return 'bg-blue-50 text-blue-800 ring-1 ring-blue-100'
  if (tone === 'amber') return 'bg-amber-50 text-amber-800 ring-1 ring-amber-100'
  if (tone === 'rose') return 'bg-rose-50 text-rose-800 ring-1 ring-rose-100'
  return 'bg-slate-50 text-slate-700 ring-1 ring-slate-100'
}

function drawdownComfortScore(value: number | null) {
  if (value === null || value === undefined) return 0
  const drawdown = Math.abs(value)
  if (drawdown <= 0.05) return 92
  if (drawdown <= 0.12) return 80
  if (drawdown <= 0.20) return 66
  if (drawdown <= 0.30) return 48
  if (drawdown <= 0.45) return 30
  return 15
}

function comparisonMissingItems(fund: FundSummary) {
  return [
    ...(fund.buy_evidence?.requiredMissingCount ? ['销售平台风险等级/申赎费率等必核项'] : []),
    ...(fund.fee_info?.missing || []),
  ]
}

function feeComparability(fund: FundSummary) {
  const missingItems = comparisonMissingItems(fund)
  const comparable = missingItems.length === 0
  return {
    comparable,
    missingItems,
    reason: comparable
      ? '管理/托管和销售端必核项暂未发现明显缺口'
      : missingItems.slice(0, 5).join('、'),
  }
}

const DEFAULT_CODES_TEXT = '022478.OF\n022864.OF'
const ALLOWED_METRIC_WINDOWS = ['1y', '3y', 'manager_tenure']

function initialCodesText() {
  if (typeof globalThis.window === 'undefined') return DEFAULT_CODES_TEXT
  const codesParam = new URLSearchParams(globalThis.window.location.search).get('codes')
  const windCodes = parseCodes(codesParam || '')
  return windCodes.length > 0 ? windCodes.join('\n') : DEFAULT_CODES_TEXT
}

function initialUrlValue<T extends string>(key: string, allowed: T[], fallback: T) {
  if (typeof globalThis.window === 'undefined') return fallback
  const value = new URLSearchParams(globalThis.window.location.search).get(key) || ''
  return allowed.includes(value as T) ? value as T : fallback
}

function appendReturnTo(href: string, returnTo: string) {
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`
}

function safeReturnPath(returnTo: string | null | undefined, fallback = '/analysis') {
  return returnTo?.startsWith('/') && !returnTo.startsWith('//') ? returnTo : fallback
}

function buildComparisonMemo(matrix: ComparisonMatrix, context: {
  profile: RiskProfile
  horizon: InvestmentHorizon
  purchasePlan: PurchasePlan
}, salesRuleGaps: SalesRuleGap[] = []) {
  const salesGapByCode = new Map(salesRuleGaps.map((gap) => [gap.windCode.toUpperCase(), gap]))
  const shareClassInfoByCode = buildShareClassInfoByCode(matrix.funds)
  const fundLines = matrix.funds.map((fund) => {
    const evidenceScore = fund.buy_evidence?.completenessScore ?? 0
    const operation = fund.operation_status?.label || '申购待核'
    const missing = comparisonMissingItems(fund)
    const salesGap = salesGapByCode.get(fund.wind_code.toUpperCase())
    const shareClassInfo = shareClassInfoByCode.get(fund.wind_code.toUpperCase())
    return `- ${fund.name}（${fund.wind_code}）：${evidenceLabel(evidenceScore)} ${evidenceScore}；${operation}；管理费 ${formatFee(fund.fee_info?.management_fee)}；销售规则 ${salesGap ? `缺 ${salesGap.missingCount} 项` : '未见硬缺口'}；${shareClassInfo ? `同基金多份额 ${shareClassInfo.siblingCount} 个，需先比费用/持有期；` : ''}待补 ${missing.length ? missing.slice(0, 4).join('、') : '暂无明显缺口'}`
  })
  const shareClassLines = Array.from(shareClassInfoByCode.entries())
    .slice(0, 8)
    .map(([code, info]) => `- ${code}：${info.baseName} ${info.classType}类；同基金份额 ${info.siblingCodes.join('、')}；${info.warnings.join('；')}`)
  const leaderLines = matrix.matrix_rows
    .filter((row) => row.best_code)
    .slice(0, 6)
    .map((row) => {
      const winner = matrix.funds.find((fund) => fund.wind_code === row.best_code)
      return `- ${row.label}：${winner?.name || row.best_code}`
    })
  const recommendationLines = matrix.recommendations.map((item) => `- ${item}`)

  return [
    '# 基金横向比较备忘录',
    `指标窗口：${matrix.metric_window}`,
    `研究画像：${profileLabels[context.profile]}；持有期：${horizonLabels[context.horizon]}；研究方式假设：${purchasePlanLabels[context.purchasePlan]}`,
    '',
    '## 对比基金与研究证据',
    ...fundLines,
    '',
    '## 维度领先样本',
    ...(leaderLines.length ? leaderLines : ['- 暂无明确领先样本']),
    '',
    '## 研究提示',
    ...(recommendationLines.length ? recommendationLines : ['- 暂无结构化提示']),
    '',
    '## 销售规则硬缺口',
    ...(salesRuleGaps.length
      ? salesRuleGaps.slice(0, 8).map((gap) => `- ${gap.fundName}（${gap.windCode}）：缺 ${gap.missingCount} 项，${gap.missingItems.slice(0, 5).join('、')}`)
      : ['- 当前对比样本暂未发现销售规则硬缺口，仍需复核销售平台实时状态。']),
    '',
    '## 同基金多份额',
    ...(shareClassLines.length
      ? shareClassLines
      : ['- 当前对比样本暂未发现 A/C/I/H 等同基金多份额；仍需在详情页核对是否存在未进入样本的份额类别。']),
    '',
    '## 边界',
    '- 本备忘录仅用于基金研究、筛选和研究复核，不构成申赎操作指令或收益承诺。',
  ].join('\n')
}

function ComparisonAnalysisPageContent() {
  const [sourceReturnHref, setSourceReturnHref] = useState('/analysis')
  const [codesText, setCodesText] = useState(initialCodesText)
  const [metricWindow, setMetricWindow] = useState('1y')
  const [profile, setProfile] = useState<RiskProfile>(() => initialUrlValue('profile', ['conservative', 'balanced', 'aggressive'], 'balanced'))
  const [horizon, setHorizon] = useState<InvestmentHorizon>(() => initialUrlValue('horizon', ['lt1y', '1to3y', 'gt3y'], '1to3y'))
  const [purchasePlan, setPurchasePlan] = useState<PurchasePlan>(() => initialUrlValue('purchasePlan', ['lump_sum', 'sip'], 'sip'))
  const foundationManualFields = salesRuleFoundationManualFieldsForPlan(purchasePlan)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [memoStatus, setMemoStatus] = useState('')
  const [matrix, setMatrix] = useState<ComparisonMatrix | null>(null)
  const [simulationMonths, setSimulationMonths] = useState(12)
  const [simulationLumpSumAmount, setSimulationLumpSumAmount] = useState(10000)
  const [simulationMonthlyAmount, setSimulationMonthlyAmount] = useState(1000)
  const [simulationLoading, setSimulationLoading] = useState(false)
  const [simulationStatus, setSimulationStatus] = useState('')
  const [simulationResults, setSimulationResults] = useState<FundSimulationResult[]>([])
  const [addingFundCode, setAddingFundCode] = useState<string | null>(null)
  const [poolMessage, setPoolMessage] = useState('')
  const [poolError, setPoolError] = useState('')
  const [salesGapPayload, setSalesGapPayload] = useState<SalesRuleGapsPayload | null>(null)
  const [salesGapLoading, setSalesGapLoading] = useState(false)
  const [salesGapError, setSalesGapError] = useState('')
  const [foundationHydrating, setFoundationHydrating] = useState(false)
  const [savingReport, setSavingReport] = useState(false)
  const [savedReportId, setSavedReportId] = useState<string | null>(null)
  const [reportMessage, setReportMessage] = useState('')
  const [reportError, setReportError] = useState('')
  const [reportBlockAction, setReportBlockAction] = useState<ComparisonReportBlockAction | null>(null)
  const [decisionTsvStatus, setDecisionTsvStatus] = useState<'idle' | 'copied' | 'fallback'>('idle')
  const [urlParamsReady, setUrlParamsReady] = useState(false)
  const [autoReplay, setAutoReplay] = useState(false)
  const autoCompared = useRef(false)
  const autoReplayed = useRef(false)
  const currentPlannedAmount = useCallback(() => (
    purchasePlan === 'lump_sum' ? simulationLumpSumAmount : simulationMonthlyAmount
  ), [purchasePlan, simulationLumpSumAmount, simulationMonthlyAmount])
  const comparedCodes = useMemo(() => matrix?.funds.map((fund) => fund.wind_code) || [], [matrix])
  const comparisonReturnHref = useMemo(() => {
    const params = new URLSearchParams({
      codes: (comparedCodes.length ? comparedCodes : parseCodes(codesText)).join(','),
      profile,
      horizon,
      purchasePlan,
      plannedAmount: String(currentPlannedAmount()),
      autoReplay: autoReplay ? '1' : '0',
    })
    if (sourceReturnHref !== '/analysis') params.set('returnTo', sourceReturnHref)
    return `/analysis/comparison?${params.toString()}`
  }, [autoReplay, codesText, comparedCodes, currentPlannedAmount, horizon, profile, purchasePlan, sourceReturnHref])

  const loadSalesRuleGaps = useCallback(async (windCodes: string[]) => {
    if (!windCodes.length) {
      setSalesGapPayload(null)
      setSalesGapError('')
      return
    }
    setSalesGapLoading(true)
    setSalesGapError('')
    try {
      const params = new URLSearchParams({
        codes: windCodes.join(','),
        limit: '100',
        purchasePlan,
        plannedAmount: String(currentPlannedAmount()),
      })
      const [gapResponse, alertsResponse] = await Promise.all([
        fetch(`/api/evidence-coverage/materials/gaps?${params.toString()}`, { cache: 'no-store' }),
        fetch('/api/evidence-coverage/review-events', { cache: 'no-store' }),
      ])
      const payload = await gapResponse.json().catch(() => ({}))
      const alertsPayload = await alertsResponse.json().catch(() => ({}))
      const normalizedCodes = Array.from(new Set(windCodes.map((code) => code.trim().toUpperCase()).filter(Boolean)))
      const failClosedPayload: SalesRuleGapsPayload = {
        source: 'local.alert_events.sales_rule_evidence',
        totalMembers: normalizedCodes.length,
        gapCount: normalizedCodes.length,
        gaps: normalizedCodes.map((windCode) => ({
          windCode,
          fundName: windCode,
          priority: 'high',
          missingItems: ['复查队列读取失败：不能证明销售规则/R1-R5证据有效'],
          missingCount: 1,
          purchaseGateLabel: '复查队列拦截',
          nextAction: '先打开复查队列，确认销售规则/R1-R5证据事件状态后再继续横评研究',
          alertsHref: reviewEventsHref({ returnTo: comparisonReturnHref }),
          gateSource: 'local.alert_events.sales_rule_evidence',
        })),
        rules: [],
        summary: { high: normalizedCodes.length, medium: 0, low: 0 },
      }
      if (!gapResponse.ok || !alertsResponse.ok) {
        setSalesGapPayload(failClosedPayload)
        throw new Error(!gapResponse.ok
          ? payload.error || '读取销售规则缺口失败'
          : alertsPayload.error || alertsPayload.detail || '读取复查队列失败，不能证明销售规则/R1-R5证据有效。')
      }
      const targetCodes = new Set(normalizedCodes)
      const gapMap = ((payload.gaps || []) as SalesRuleGap[]).reduce((acc, gap) => {
        acc.set(gap.windCode.toUpperCase(), gap)
        return acc
      }, new Map<string, SalesRuleGap>())
      const activeSalesRuleAlerts = (Array.isArray(alertsPayload.events) ? alertsPayload.events as RawAlertEvent[] : [])
        .filter((event) => event.event_type === 'sales_rule_evidence' && event.status !== 'resolved' && targetCodes.has(alertFundCode(event)))
      activeSalesRuleAlerts.forEach((event) => {
        const windCode = alertFundCode(event)
        const existing = gapMap.get(windCode)
        const title = stringValue(event.title) || '销售规则/R1-R5证据待补'
        const message = stringValue(event.message)
        const missingItem = `复查队列未解决：${title}${message ? `（${message}）` : ''}`
        const missingItems = Array.from(new Set([...(existing?.missingItems || []), missingItem]))
        gapMap.set(windCode, {
          ...(existing || {
            windCode,
            fundName: windCode,
            purchaseGateLabel: '复查队列拦截',
          }),
          priority: 'high',
          missingItems,
          missingCount: Math.max(existing?.missingCount || 0, missingItems.length),
          nextAction: '先打开复查队列，处理销售规则/R1-R5过期或待补事件',
          alertsHref: reviewEventsHref({ returnTo: comparisonReturnHref }),
          gateSource: 'local.alert_events.sales_rule_evidence',
        })
      })
      const gaps = Array.from(gapMap.values())
      setSalesGapPayload({
        ...payload,
        source: activeSalesRuleAlerts.length
          ? `${payload.source || 'local.sales_rule_gaps'}+local.alert_events.sales_rule_evidence`
          : payload.source,
        gapCount: gaps.length,
        gaps,
        summary: {
          high: gaps.filter((gap) => gap.priority === 'high').length,
          medium: gaps.filter((gap) => gap.priority === 'medium').length,
          low: gaps.filter((gap) => gap.priority === 'low').length,
        },
      })
    } catch (error) {
      const normalizedCodes = Array.from(new Set(windCodes.map((code) => code.trim().toUpperCase()).filter(Boolean)))
      setSalesGapPayload({
        source: 'local.alert_events.sales_rule_evidence',
        totalMembers: normalizedCodes.length,
        gapCount: normalizedCodes.length,
        gaps: normalizedCodes.map((windCode) => ({
          windCode,
          fundName: windCode,
          priority: 'high',
          missingItems: ['复查队列读取失败：不能证明销售规则/R1-R5证据有效'],
          missingCount: 1,
          purchaseGateLabel: '复查队列拦截',
          nextAction: '先打开复查队列，确认销售规则/R1-R5证据事件状态后再继续横评研究',
          alertsHref: reviewEventsHref({ returnTo: comparisonReturnHref }),
          gateSource: 'local.alert_events.sales_rule_evidence',
        })),
        rules: [],
        summary: { high: normalizedCodes.length, medium: 0, low: 0 },
      })
      setSalesGapError(error instanceof Error ? error.message : '读取销售规则缺口失败')
    } finally {
      setSalesGapLoading(false)
    }
  }, [comparisonReturnHref, currentPlannedAmount, purchasePlan])

  const runCompare = useCallback(async (windCodes = parseCodes(codesText), selectedWindow = metricWindow) => {
    if (windCodes.length < 2) {
      alert('请至少输入两只基金代码')
      return
    }

    setLoading(true)
    setStatus('正在计算同类分位和对比矩阵...')
    setMemoStatus('')
    setMatrix(null)
    setSimulationResults([])
    setSimulationStatus('')
    setPoolMessage('')
    setPoolError('')
    setSalesGapPayload(null)
    setSalesGapError('')
    setSavedReportId(null)
    setReportMessage('')
    setReportError('')
    setReportBlockAction(null)

    try {
      const response = await fetch('/api/funds/compare-matrix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ windCodes, window: selectedWindow, purchasePlan, plannedAmount: currentPlannedAmount() }),
      })
      const payload = await response.json()

      if (!response.ok) {
        throw new Error(payload.error || '生成对比矩阵失败')
      }

      setMatrix(payload)
      void loadSalesRuleGaps((payload.funds || []).map((fund: FundSummary) => fund.wind_code))
      setStatus(`已生成 ${payload.funds?.length || 0} 只基金的结构化对比矩阵`)
    } catch (error) {
      console.error('生成对比矩阵失败:', error)
      setStatus(`错误: ${error instanceof Error ? error.message : '生成对比矩阵失败'}`)
    } finally {
      setLoading(false)
    }
  }, [codesText, currentPlannedAmount, loadSalesRuleGaps, metricWindow, purchasePlan])

  const memoText = useMemo(
    () => matrix ? buildComparisonMemo(matrix, { profile, horizon, purchasePlan }, salesGapPayload?.gaps || []) : '',
    [horizon, matrix, profile, purchasePlan, salesGapPayload],
  )
  const salesRulesHref = appendReturnTo(
    comparedCodes.length
      ? materialEvidenceHref(new URLSearchParams({ codes: comparedCodes.join(','), purchasePlan, plannedAmount: String(currentPlannedAmount()) }))
      : materialEvidenceHref(new URLSearchParams({ purchasePlan, plannedAmount: String(currentPlannedAmount()) })),
    comparisonReturnHref,
  )
  const salesRulesHrefForCode = (windCode: string) => appendReturnTo(
    materialEvidenceHref(new URLSearchParams({ codes: windCode, purchasePlan, plannedAmount: String(currentPlannedAmount()) })),
    comparisonReturnHref,
  )
  const salesRuleActionHrefForGap = (gap: SalesRuleGap | null | undefined, windCode: string) => (
    gap?.alertsHref ? appendReturnTo(gap.alertsHref, comparisonReturnHref) : salesRulesHrefForCode(windCode)
  )
  const salesGapByCode = useMemo(() => {
    const gapMap = new Map<string, SalesRuleGap>()
    salesGapPayload?.gaps.forEach((gap) => {
      gapMap.set(gap.windCode.toUpperCase(), gap)
    })
    return gapMap
  }, [salesGapPayload])
  const activeSalesRuleReviewGaps = useMemo(
    () => (salesGapPayload?.gaps || []).filter((gap) => Boolean(gap.alertsHref)),
    [salesGapPayload],
  )
  const salesRuleGroupActionHref = activeSalesRuleReviewGaps.length
    ? reviewEventsHref({ returnTo: comparisonReturnHref })
    : salesRulesHref
  const executionAmountGateByCode = useMemo(() => {
    const gateMap = new Map<string, SalesRuleExecutionAmountGate>()
    ;(salesGapPayload?.rules || []).forEach((rule) => {
      if (rule.windCode && rule.executionAmountGate) {
        gateMap.set(rule.windCode.toUpperCase(), rule.executionAmountGate)
      }
    })
    return gateMap
  }, [salesGapPayload])
  const shareClassInfoByCode = useMemo(() => {
    return matrix ? buildShareClassInfoByCode(matrix.funds) : new Map<string, ShareClassInfo>()
  }, [matrix])
  const foundationFillableCodes = useMemo(() => {
    return Array.from(new Set(
      (salesGapPayload?.gaps || [])
        .filter((gap) => gap.missingItems.some((item) =>
          item.includes('销售规则整条待补')
            || item.includes('来源日期')
            || (item.includes('申购状态') && !gap.ruleSourceUpdatedAt),
        ))
        .map((gap) => gap.windCode),
    ))
  }, [salesGapPayload])
  const detailContextQuery = new URLSearchParams({
    profile,
    horizon,
    purchasePlan,
    plannedAmount: String(currentPlannedAmount()),
    months: String(simulationMonths),
    lumpSumAmount: String(simulationLumpSumAmount),
    monthlyAmount: String(simulationMonthlyAmount),
  }).toString()
  const fundDetailHref = (fund: ComparisonMatrix['funds'][number]) => `/funds/${encodeURIComponent(fund.id || fund.wind_code)}?${detailContextQuery}`
  const simulationReturnForPlan = useCallback((simulation: PurchaseSimulation) => {
    const feeAdjustedReturn = purchasePlan === 'sip'
      ? simulation.feeAdjusted?.sip?.returnRate
      : simulation.feeAdjusted?.lumpSum?.returnRate
    if (feeAdjustedReturn !== null && feeAdjustedReturn !== undefined) return feeAdjustedReturn
    return purchasePlan === 'sip' ? simulation.sip.returnRate : simulation.lumpSum.returnRate
  }, [purchasePlan])
  const bestLumpSumResult = useMemo(() => {
    return simulationResults
      .filter((result): result is FundSimulationResult & { simulation: PurchaseSimulation } => result.status === 'ok' && Boolean(result.simulation))
      .sort((left, right) => (right.simulation.lumpSum.returnRate ?? -Infinity) - (left.simulation.lumpSum.returnRate ?? -Infinity))[0] || null
  }, [simulationResults])
  const bestSipResult = useMemo(() => {
    return simulationResults
      .filter((result): result is FundSimulationResult & { simulation: PurchaseSimulation } => result.status === 'ok' && Boolean(result.simulation))
      .sort((left, right) => (right.simulation.sip.returnRate ?? -Infinity) - (left.simulation.sip.returnRate ?? -Infinity))[0] || null
  }, [simulationResults])
  const purchaseDecision = useMemo(() => {
    if (!matrix?.funds.length) return null

    const simulationLeaders = simulationResults
      .filter((result): result is FundSimulationResult & { simulation: PurchaseSimulation } => result.status === 'ok' && Boolean(result.simulation))
      .sort((left, right) => {
        const leftReturn = simulationReturnForPlan(left.simulation)
        const rightReturn = simulationReturnForPlan(right.simulation)
        if ((rightReturn ?? -Infinity) !== (leftReturn ?? -Infinity)) {
          return (rightReturn ?? -Infinity) - (leftReturn ?? -Infinity)
        }
        const leftDrawdown = purchasePlan === 'sip' ? left.simulation.sip.maxAccountDrawdown : left.simulation.lumpSum.maxDrawdown
        const rightDrawdown = purchasePlan === 'sip' ? right.simulation.sip.maxAccountDrawdown : right.simulation.lumpSum.maxDrawdown
        return Math.abs(leftDrawdown ?? Infinity) - Math.abs(rightDrawdown ?? Infinity)
      })
    const scoreLeaders = [...matrix.funds].sort((left, right) => (right.professional_score ?? -Infinity) - (left.professional_score ?? -Infinity))
    const primaryCode = simulationLeaders[0]?.windCode || scoreLeaders[0]?.wind_code
    const runnerCode = simulationLeaders[1]?.windCode || scoreLeaders.find((fund) => fund.wind_code !== primaryCode)?.wind_code || null
    const primaryFund = matrix.funds.find((fund) => fund.wind_code === primaryCode) || null
    const runnerUpFund = matrix.funds.find((fund) => fund.wind_code === runnerCode) || null
    const primarySimulation = simulationResults.find((result) => result.windCode === primaryCode && result.status === 'ok')
    const primaryReturn = primarySimulation?.status === 'ok'
      ? primarySimulation.simulation ? simulationReturnForPlan(primarySimulation.simulation) : null
      : null
    const primaryDrawdown = primarySimulation?.status === 'ok'
      ? purchasePlan === 'sip'
        ? primarySimulation.simulation?.sip.maxAccountDrawdown
        : primarySimulation.simulation?.lumpSum.maxDrawdown
      : null
    const verifyFunds = matrix.funds.filter((fund) => (fund.buy_evidence?.requiredMissingCount ?? 0) > 0)
    const blockedFunds = matrix.funds.filter((fund) => fund.operation_status?.status === 'blocked')
    const feeComparableCount = matrix.funds.filter((fund) => feeComparability(fund).comparable).length
    const feeGapCount = matrix.funds.length - feeComparableCount
    const salesHardGapCount = salesGapPayload?.gapCount ?? 0
    const shareClassInfoByCode = buildShareClassInfoByCode(matrix.funds)
    const shareClassFundCount = shareClassInfoByCode.size
    const nextChecks = [
      simulationLeaders.length ? '' : '先运行持有体验回放，再确认收益/回撤体验排序',
      salesHardGapCount ? `补齐 ${salesHardGapCount} 只基金的销售规则硬缺口，再判断是否可进入研究复核` : '',
      !salesHardGapCount && verifyFunds.length ? `复核 ${verifyFunds.length} 只基金的销售规则、费率、限购和风险等级` : '',
      feeGapCount ? `${feeGapCount} 只基金费用证据不可直接横比，当前领先需费后确认` : '',
      shareClassFundCount ? `${shareClassFundCount} 个同基金多份额样本需先比较 A/C/I 等份额成本和持有期` : '',
      blockedFunds.length ? `${blockedFunds.length} 只基金存在申赎阻断，不能进入研究候选` : '',
      '研究复核仍需以销售平台实时适当性、申赎状态和费率为准',
    ].filter(Boolean)

    return {
      primaryFund,
      runnerUpFund,
      basisLabel: simulationLeaders.length
        ? `${purchasePlanLabels[purchasePlan]}历史回放领先`
        : '专业评分暂定领先',
      primaryReturn,
      primaryDrawdown,
      verifyCount: verifyFunds.length,
      blockedCount: blockedFunds.length,
      feeComparableCount,
      feeGapCount,
      salesHardGapCount,
      shareClassFundCount,
      totalCount: matrix.funds.length,
      nextChecks,
      conclusion: primaryFund
        ? salesHardGapCount
          ? `当前不输出可研究优先样本；${primaryFund.name} 仅作为补齐销售规则后的优先核查样本，不能直接入池或生成正式横评报告。`
          : `${profileLabels[profile]}、${horizonLabels[horizon]}、${purchasePlanLabels[purchasePlan]}场景下，${primaryFund.name} 当前更适合作为优先核查对象；仍需复核实时申赎证据${feeGapCount ? '并完成费用后确认' : ''}${shareClassFundCount ? '，并先完成同基金多份额成本比较' : ''}。`
        : '当前样本不足，暂不能形成优先核查对象。',
    }
  }, [horizon, matrix, profile, purchasePlan, salesGapPayload?.gapCount, simulationResults, simulationReturnForPlan])

  const decisionScores = useMemo<DecisionScore[]>(() => {
    if (!matrix?.funds.length) return []

    const simulationByCode = new Map(
      simulationResults
        .filter((result): result is FundSimulationResult & { simulation: PurchaseSimulation } => result.status === 'ok' && Boolean(result.simulation))
        .map((result) => [result.windCode.toUpperCase(), result]),
    )
    const simulatedReturns = matrix.funds
      .map((fund) => {
        const result = simulationByCode.get(fund.wind_code.toUpperCase())
        if (!result) return null
        return simulationReturnForPlan(result.simulation)
      })
      .filter((value): value is number => value !== null && value !== undefined)
    const minReturn = simulatedReturns.length ? Math.min(...simulatedReturns) : null
    const maxReturn = simulatedReturns.length ? Math.max(...simulatedReturns) : null
    const returnScore = (value: number | null) => {
      if (value === null || value === undefined || minReturn === null || maxReturn === null) return 0
      if (maxReturn === minReturn) return 70
      return clampScore(35 + ((value - minReturn) / (maxReturn - minReturn)) * 60)
    }

    return matrix.funds
      .map((fund) => {
        const result = simulationByCode.get(fund.wind_code.toUpperCase())
        const simulationReturn = result
          ? simulationReturnForPlan(result.simulation)
          : null
        const simulationDrawdown = result
          ? purchasePlan === 'sip'
            ? result.simulation.sip.maxAccountDrawdown
            : result.simulation.lumpSum.maxDrawdown
          : null
        const stressExperience = result?.simulation.stressExperience || null
        const stressScore = stressExperience?.stressScore ?? null
        const worstThreeMonthReturn = stressExperience?.worstThreeMonthReturn?.returnRate ?? null
        const feeStatus = feeComparability(fund)
        const salesGap = salesGapByCode.get(fund.wind_code.toUpperCase()) || null
        const requiredMissingCount = fund.buy_evidence?.requiredMissingCount ?? 0
        const evidenceScore = fund.buy_evidence?.completenessScore ?? 0
        const professionalScoreMissing = fund.professional_score === null || fund.professional_score === undefined
        const professionalScore = professionalScoreMissing ? 0 : fund.professional_score as number
        const replayMissing = simulationReturn === null || simulationReturn === undefined
        const replayDrawdownMissing = simulationDrawdown === null || simulationDrawdown === undefined
        const replayScore = returnScore(simulationReturn)
        const drawdownScore = drawdownComfortScore(simulationDrawdown)
        const stressScoreMissing = stressScore === null || stressScore === undefined
        const stressComfortScore = stressScoreMissing ? 0 : stressScore
        const feeScore = feeStatus.comparable ? 88 : Math.max(25, 65 - feeStatus.missingItems.length * 8)
        const breakdown = [
          {
            key: 'professional',
            label: '专业评分',
            rawScore: professionalScore,
            contribution: professionalScore * 0.22,
            weight: 0.22,
            note: professionalScoreMissing ? '专业评分待补，本项不加分，并触发横评分封顶' : `专业评分 ${professionalScore.toFixed(1)}`,
          },
          {
            key: 'evidence',
            label: '研究证据',
            rawScore: evidenceScore,
            contribution: evidenceScore * 0.20,
            weight: 0.20,
            note: `证据完整度 ${evidenceScore}，必补 ${requiredMissingCount} 项`,
          },
          {
            key: 'replay',
            label: '持有体验回放',
            rawScore: replayScore,
            contribution: replayScore * 0.20,
            weight: 0.20,
            note: replayMissing ? '持有体验回放缺失，本项不加分，并触发决策分封顶' : `${purchasePlanLabels[purchasePlan]}回放 ${formatPercent(simulationReturn)}`,
          },
          {
            key: 'drawdown',
            label: '回撤舒适度',
            rawScore: drawdownScore,
            contribution: drawdownScore * 0.14,
            weight: 0.14,
            note: replayDrawdownMissing ? '回撤回放缺失，本项不加分，并触发决策分封顶' : `回撤 ${formatPercent(simulationDrawdown)}，舒适度 ${drawdownScore.toFixed(0)}`,
          },
          {
            key: 'stress',
            label: '压力体验',
            rawScore: stressComfortScore,
            contribution: stressComfortScore * 0.12,
            weight: 0.12,
            note: stressExperience
              ? `${stressExperience.label}，最长亏损等待 ${Math.round(stressExperience.longestUnderwaterDays)} 天，最差三个月 ${formatPercent(worstThreeMonthReturn)}`
              : '压力体验缺失，本项不加分，并触发决策分封顶',
          },
          {
            key: 'fee',
            label: '费用可比性',
            rawScore: feeScore,
            contribution: feeScore * 0.12,
            weight: 0.12,
            note: feeStatus.comparable ? '费用证据可初步横比' : `费用待补：${feeStatus.reason}`,
          },
        ]
        let score = clampScore(
          professionalScore * 0.22
          + evidenceScore * 0.20
          + replayScore * 0.20
          + drawdownScore * 0.14
          + stressComfortScore * 0.12
          + feeScore * 0.12,
        )

        const operationBlocked = fund.operation_status?.status === 'blocked'
        const scoreCaps: string[] = []
        if (requiredMissingCount > 0) score = Math.min(score, 72)
        if (requiredMissingCount > 0) scoreCaps.push(`必补项 ${requiredMissingCount} 项，决策分封顶 72`)
        if (professionalScoreMissing) {
          score = Math.min(score, 65)
          scoreCaps.push('专业评分缺失，决策分封顶 65')
        }
        if (replayMissing) {
          score = Math.min(score, 68)
          scoreCaps.push('持有体验回放缺失，决策分封顶 68')
        }
        if (replayDrawdownMissing) {
          score = Math.min(score, 70)
          scoreCaps.push('回撤回放缺失，决策分封顶 70')
        }
        if (stressScoreMissing) {
          score = Math.min(score, 70)
          scoreCaps.push('压力体验缺失，决策分封顶 70')
        }
        if (salesGap) {
          score = Math.min(score, 56)
          scoreCaps.push(`销售规则硬缺口 ${salesGap.missingCount} 项，决策分封顶 56`)
        }
        if (operationBlocked) {
          score = Math.min(score, 25)
          scoreCaps.push('申赎/运作状态阻断，决策分封顶 25')
        }

        let label = '暂不优先'
        let tone: DecisionScore['tone'] = 'slate'
        let gateLabel = '可继续研究'
        let gateDetail = '当前没有检测到销售规则硬缺口，但仍需复核实时状态。'
        let nextAction = '做研究复核一页纸与销售平台复核'

        if (operationBlocked) {
          label = '暂停研究路径'
          tone = 'rose'
          gateLabel = '申赎阻断'
          gateDetail = fund.operation_status?.reason || '存在不可申购或非在运作信号。'
          nextAction = '暂不入池，先确认运作/申购状态'
        } else if (salesGap) {
          label = '补规则前不可进入研究短名单'
          tone = 'rose'
          gateLabel = `销售硬缺口 ${salesGap.missingCount} 项`
          gateDetail = salesGap.missingItems.slice(0, 5).join('、')
          nextAction = '先补销售规则，再重新比较'
        } else if (requiredMissingCount > 0 || !feeStatus.comparable) {
          label = '补证后复核'
          tone = 'amber'
          gateLabel = requiredMissingCount > 0 ? `研究证据待补 ${requiredMissingCount} 项` : '费用不可直接横比'
          gateDetail = requiredMissingCount > 0
            ? fund.buy_evidence?.conclusion || '销售平台风险等级、费率、限购或申赎证据仍需补齐。'
            : feeStatus.reason
          nextAction = '补证后再决定是否进研究复核'
        } else if (score >= 76) {
          label = '优先研究复核'
          tone = 'emerald'
          gateLabel = '研究证据较完整'
          nextAction = '进入研究复核报告与研究清单留痕'
        } else if (score >= 62) {
          label = '备选研究复核'
          tone = 'blue'
          gateLabel = '可作为备选'
          nextAction = '与优先样本继续做费后比较'
        }

        const reasons = [
          `专业评分 ${fund.professional_score?.toFixed?.(1) || '待补'}`,
          `证据分 ${fund.buy_evidence?.completenessScore ?? 0}`,
          result ? `${purchasePlanLabels[purchasePlan]}回放 ${formatPercent(simulationReturn)}` : '持有体验回放待跑',
          `回撤舒适度 ${drawdownComfortScore(simulationDrawdown).toFixed(0)}`,
          stressExperience ? `压力体验 ${stressExperience.stressScore} 分，最长亏损等待 ${Math.round(stressExperience.longestUnderwaterDays)} 天` : '压力体验待跑',
          feeStatus.comparable ? '费用可初步横比' : `费用待补：${feeStatus.reason}`,
          salesGap ? `销售规则缺 ${salesGap.missingCount} 项` : salesGapPayload ? '销售规则未见硬缺口' : '销售规则待读取',
        ]

        return {
          windCode: fund.wind_code,
          fund,
          score: Math.round(score),
          label,
          tone,
          gateLabel,
          gateDetail,
          simulationReturn,
          simulationDrawdown,
          stressScore,
          longestUnderwaterDays: stressExperience?.longestUnderwaterDays ?? null,
          worstThreeMonthReturn,
          breakdown,
          scoreCaps,
          reasons,
          nextAction,
          salesGap,
          feeComparable: feeStatus.comparable,
        }
      })
      .sort((left, right) => right.score - left.score)
  }, [matrix, purchasePlan, salesGapByCode, salesGapPayload, simulationResults, simulationReturnForPlan])
  const decisionExplanation = useMemo(() => {
    const leader = decisionScores[0] || null
    const runner = decisionScores[1] || null
    if (!leader) return null

    const returnGap = leader.simulationReturn != null && runner?.simulationReturn != null
      ? leader.simulationReturn - runner.simulationReturn
      : null
    const drawdownGap = leader.simulationDrawdown != null && runner?.simulationDrawdown != null
      ? Math.abs(leader.simulationDrawdown) - Math.abs(runner.simulationDrawdown)
      : null
    const stressGap = leader.stressScore != null && runner?.stressScore != null
      ? leader.stressScore - runner.stressScore
      : null
    const evidenceGap = (leader.fund.buy_evidence?.completenessScore ?? 0) - (runner?.fund.buy_evidence?.completenessScore ?? 0)
    const professionalGap = (leader.fund.professional_score ?? 0) - (runner?.fund.professional_score ?? 0)
    const scoreGap = runner ? leader.score - runner.score : null
    const reasons = [
      leader.salesGap ? `第一名 ${leader.fund.name} 仍有销售规则硬缺口，不能直接作为研究候选。` : '第一名暂未发现销售规则硬缺口，可进入下一层研究复核。',
      runner?.salesGap && !leader.salesGap ? `相对 ${runner.fund.name}，领先样本少了销售规则硬缺口阻断。` : '',
      returnGap !== null ? `${purchasePlanLabels[purchasePlan]}费用优先回放收益差 ${formatPercent(returnGap)}。` : '持有体验回放不足，收益差暂不能作为主要依据。',
      drawdownGap !== null ? `回撤差 ${formatPercent(drawdownGap)}；负数代表第一名回撤更低。` : '',
      stressGap !== null ? `压力体验分差 ${stressGap > 0 ? '+' : ''}${stressGap}；压力分越高，历史亏损等待和连跌体验越温和。` : '',
      evidenceGap ? `研究证据分差 ${evidenceGap > 0 ? '+' : ''}${evidenceGap}。` : '',
      professionalGap ? `专业评分差 ${professionalGap > 0 ? '+' : ''}${professionalGap.toFixed(1)}。` : '',
      leader.feeComparable ? '第一名费用证据可初步横比。' : '第一名费用证据仍不可直接横比，需要补费率/赎回规则。',
    ].filter(Boolean)
    const recheckTriggers = [
      scoreGap !== null && scoreGap <= 5 ? `分差只有 ${scoreGap} 分，视为接近；补齐费率或重跑回放后可能反转。` : '',
      leader.salesGap ? `补齐 ${leader.fund.name} 的销售规则硬缺口前，只能把它当作补证优先样本。` : '',
      runner?.salesGap && !leader.salesGap ? `${runner.fund.name} 若补齐销售规则，可能重新进入可比候选。` : '',
      !leader.feeComparable ? `${leader.fund.name} 的费用证据不可直接横比，费后收益可能被高估。` : '',
      runner && returnGap !== null && returnGap < 0 ? `${runner.fund.name} 的${purchasePlanLabels[purchasePlan]}回放收益更高，需要确认第一名是否靠证据分领先。` : '',
      runner && drawdownGap !== null && drawdownGap > 0 ? `${runner.fund.name} 的回撤更低，稳健画像下应优先复核风险体验。` : '',
      leader.longestUnderwaterDays !== null && leader.longestUnderwaterDays > simulationMonths * 20 ? `${leader.fund.name} 的最长亏损等待较长，若研究画像计划持有期缩短或无法承受账面亏损，排序应下调。` : '',
      runner && stressGap !== null && stressGap < 0 ? `${runner.fund.name} 的压力体验更温和，不能只看收益或总分。` : '',
      !simulationResults.length ? '尚未运行持有体验回放，当前排序更偏静态评分。' : '',
      salesGapPayload?.gapCount ? `当前仍有 ${salesGapPayload.gapCount} 只基金销售规则硬缺口，补齐前不保存正式横评报告。` : '',
    ].filter(Boolean)
    const leaderBreakdown = [...leader.breakdown].sort((left, right) => right.contribution - left.contribution)
    const runnerBreakdown = runner ? [...runner.breakdown].sort((left, right) => right.contribution - left.contribution) : []
    const decisiveEdges = [
      leader.salesGap ? '' : `${leader.fund.name} 暂列第一，不代表可执行；只能作为研究复核优先样本。`,
      runner ? `相对 ${runner.fund.name}，当前分差 ${scoreGap} 分。` : '当前缺少第二只可比基金，建议补充同类样本。',
      leaderBreakdown[0] ? `最大贡献项：${leaderBreakdown[0].label} +${leaderBreakdown[0].contribution.toFixed(1)}。` : '',
      runnerBreakdown[0] ? `${runner?.fund.name} 最大贡献项：${runnerBreakdown[0].label} +${runnerBreakdown[0].contribution.toFixed(1)}。` : '',
      returnGap !== null ? `${purchasePlanLabels[purchasePlan]}回放收益差 ${formatPercent(returnGap)}。` : '尚未形成完整持有体验回放收益差。',
      drawdownGap !== null ? `回撤体验差 ${formatPercent(drawdownGap)}，稳健画像需重点看绝对回撤。` : '',
      stressGap !== null ? `压力体验差 ${stressGap > 0 ? '+' : ''}${stressGap} 分，最长亏损等待和最差三个月会影响真实持有体验。` : '',
    ].filter(Boolean)
    const decisiveCheckItems = runner ? [
      {
        label: '分差安全垫',
        passed: scoreGap !== null && scoreGap >= 8,
        detail: scoreGap === null ? '缺第二名分数，不能判断安全垫。' : `第一名领先 ${scoreGap} 分；低于 8 分视为容易反转。`,
      },
      {
        label: '费后回放收益',
        passed: returnGap !== null && returnGap >= 0.01,
        detail: returnGap === null ? '缺真实回放收益，不采信静态收益排序。' : `${purchasePlanLabels[purchasePlan]}回放收益差 ${formatPercent(returnGap)}。`,
      },
      {
        label: '回撤不劣于替代',
        passed: drawdownGap !== null && drawdownGap <= 0.02,
        detail: drawdownGap === null ? '缺回撤回放，无法判断风险体验。' : `回撤差 ${formatPercent(drawdownGap)}；正数代表第一名回撤更高。`,
      },
      {
        label: '压力体验不落后',
        passed: stressGap !== null && stressGap >= -5,
        detail: stressGap === null ? '缺压力体验，无法判断真实持有舒适度。' : `压力体验分差 ${stressGap > 0 ? '+' : ''}${stressGap}。`,
      },
      {
        label: '证据完整度不落后',
        passed: evidenceGap >= 0,
        detail: `研究证据分差 ${evidenceGap > 0 ? '+' : ''}${evidenceGap}；第二名证据更完整时不能只看收益。`,
      },
      {
        label: '销售规则可正式横评',
        passed: !leader.salesGap && !runner.salesGap && leader.feeComparable && runner.feeComparable,
        detail: leader.salesGap || runner.salesGap
          ? '任一方销售规则/R1-R5 未清零，只能研究态横评。'
          : !leader.feeComparable || !runner.feeComparable
            ? '费用证据不可比，会扭曲费后收益。'
            : '双方销售规则和费用证据可进入下一层复核。',
      },
    ] : []
    const decisivePassCount = decisiveCheckItems.filter((item) => item.passed).length
    const decisiveConfidence = !runner
      ? '样本不足'
      : leader.salesGap || runner.salesGap
        ? '仅补证观察'
        : decisivePassCount >= 5
          ? '领先较稳'
          : decisivePassCount >= 3
            ? '领先待复核'
            : '领先很脆弱'
    const decisiveAudit = {
      title: '第一名能否真的赢第二名',
      confidence: decisiveConfidence,
      passCount: decisivePassCount,
      totalCount: decisiveCheckItems.length,
      items: decisiveCheckItems,
      boundary: '至少同时看分差、费后回放、回撤、压力体验、证据完整度和销售规则；任一硬门禁未过时，横评只能作为研究观察。',
    }
    const pairwiseDeltas = runner ? [
      {
        metric: '决策分',
        leaderValue: `${leader.score} 分`,
        runnerValue: `${runner.score} 分`,
        edge: scoreGap !== null ? `${scoreGap > 0 ? '+' : ''}${scoreGap} 分` : '待补',
        verdict: scoreGap !== null && scoreGap <= 5 ? '非常接近，补证后可能反转' : '当前领先但仍需门禁复核',
      },
      {
        metric: `${purchasePlanLabels[purchasePlan]}回放收益`,
        leaderValue: formatPercent(leader.simulationReturn),
        runnerValue: formatPercent(runner.simulationReturn),
        edge: returnGap !== null ? formatPercent(returnGap) : '待回放',
        verdict: returnGap === null
          ? '缺真实回放，不可用收益差决策'
          : returnGap < 0
            ? '第二名回放收益更高，需要解释第一名为何领先'
            : '第一名回放收益占优',
      },
      {
        metric: '回撤体验',
        leaderValue: formatPercent(leader.simulationDrawdown),
        runnerValue: formatPercent(runner.simulationDrawdown),
        edge: drawdownGap !== null ? formatPercent(drawdownGap) : '待回放',
        verdict: drawdownGap === null
          ? '缺回撤回放，不可判断风险体验差'
          : drawdownGap > 0
            ? '第二名回撤更低，稳健画像需重点复核'
            : '第一名回撤更温和',
      },
      {
        metric: '压力体验',
        leaderValue: leader.stressScore === null ? '待补' : `${leader.stressScore} 分`,
        runnerValue: runner.stressScore === null ? '待补' : `${runner.stressScore} 分`,
        edge: stressGap !== null ? `${stressGap > 0 ? '+' : ''}${stressGap} 分` : '待补',
        verdict: stressGap === null
          ? '缺压力体验，不可判断真实持有舒适度'
          : stressGap < 0
            ? '第二名压力体验更好，不能只看收益或总分'
            : '第一名压力体验占优',
      },
      {
        metric: '研究证据',
        leaderValue: `${leader.fund.buy_evidence?.completenessScore ?? 0} 分`,
        runnerValue: `${runner.fund.buy_evidence?.completenessScore ?? 0} 分`,
        edge: `${evidenceGap > 0 ? '+' : ''}${evidenceGap}`,
        verdict: evidenceGap < 0 ? '第二名证据更完整，需防第一名凭收益领先' : '第一名证据不弱于第二名',
      },
      {
        metric: '专业评分',
        leaderValue: leader.fund.professional_score == null ? '待补' : leader.fund.professional_score.toFixed(1),
        runnerValue: runner.fund.professional_score == null ? '待补' : runner.fund.professional_score.toFixed(1),
        edge: `${professionalGap > 0 ? '+' : ''}${professionalGap.toFixed(1)}`,
        verdict: leader.fund.professional_score == null || runner.fund.professional_score == null
          ? '专业评分缺失方不加中性分，补齐后重评'
          : professionalGap < 0
            ? '第二名专业评分更高，需解释第一名其他优势'
            : '第一名专业评分占优',
      },
      {
        metric: '费用/销售规则',
        leaderValue: leader.salesGap ? `销售缺 ${leader.salesGap.missingCount} 项` : leader.feeComparable ? '费用可比' : '费用待补',
        runnerValue: runner.salesGap ? `销售缺 ${runner.salesGap.missingCount} 项` : runner.feeComparable ? '费用可比' : '费用待补',
        edge: leader.salesGap || runner.salesGap || !leader.feeComparable || !runner.feeComparable ? '不可直接横比' : '可横比',
        verdict: leader.salesGap || runner.salesGap
          ? '任一方销售规则硬缺口未清零，不能形成正式研究复核横评结论'
          : !leader.feeComparable || !runner.feeComparable
            ? '费用不可比会扭曲费后收益，需补齐再重跑'
            : '费用证据允许进入下一步横评',
      },
    ] : []
    const knockoutLines = decisionScores
      .filter((item) => item.windCode !== leader.windCode)
      .map((item) => {
        if (item.fund.operation_status?.status === 'blocked') {
          return `${item.fund.name}：申赎/运作状态阻断，先排除研究路径。`
        }
        if (item.salesGap) {
          return `${item.fund.name}：销售规则缺 ${item.salesGap.missingCount} 项，补齐前不能作为正式研究复核候选。`
        }
        if (item.scoreCaps.length) {
          return `${item.fund.name}：${item.scoreCaps[0]}，暂列补证样本。`
        }
        if (!item.feeComparable) {
          return `${item.fund.name}：费用证据不可直接横比，需补费后再判断。`
        }
        return `${item.fund.name}：决策分低于领先样本 ${leader.score - item.score} 分，暂列备选横评对象。`
      })
      .filter(Boolean)
    const nextActions = [
      leader.salesGap ? `先补 ${leader.fund.name} 销售规则硬缺口，不保存正式横评报告。` : '',
      !leader.salesGap && leader.feeComparable ? `把 ${leader.fund.name} 加入观察池前，打开研究复核一页纸复核同类、经理、持仓和实时销售规则。` : '',
      !leader.feeComparable ? `先补 ${leader.fund.name} 申购费、赎回费和销售服务费，避免费后收益排序失真。` : '',
      leader.longestUnderwaterDays !== null ? `复核 ${leader.fund.name} 最长亏损等待 ${Math.round(leader.longestUnderwaterDays)} 天、最差三个月 ${formatPercent(leader.worstThreeMonthReturn)} 是否超出研究画像承受范围。` : '',
      runner?.salesGap ? `补齐 ${runner.fund.name} 销售规则后重跑横评，确认是否反超。` : '',
      !simulationResults.length ? '先运行持有体验回放，避免只按静态评分排序。' : '',
      salesGapPayload?.gapCount ? `当前 ${salesGapPayload.gapCount} 只基金有销售规则硬缺口，全部清零前不输出正式研究候选。` : '',
    ].filter(Boolean)

    return {
      leader,
      runner,
      scoreGap,
      reasons,
      recheckTriggers,
      decisiveEdges,
      pairwiseDeltas,
      knockoutLines,
      nextActions,
      decisiveAudit,
      conclusion: leader.salesGap
        ? '当前只有“补证优先样本”，没有可研究优先样本。'
        : runner
          ? `${leader.fund.name} 暂时领先 ${runner.fund.name}${runner ? ` ${scoreGap} 分` : ''}，但仍需逐项复核销售平台实时规则。`
          : `${leader.fund.name} 是当前唯一可比较样本，建议补充更多同类基金。`,
    }
  }, [decisionScores, purchasePlan, salesGapPayload, simulationMonths, simulationResults.length])

  const buyForwardQueue = useMemo(() => {
    if (!decisionScores.length) return null
    const leaderScore = decisionScores[0]?.score ?? 0
    const hasSimulation = simulationResults.length > 0
    const ready = decisionScores
      .filter((item) =>
        !item.salesGap
        && item.fund.operation_status?.status !== 'blocked'
        && item.feeComparable
        && (item.fund.buy_evidence?.requiredMissingCount ?? 0) === 0
        && item.simulationReturn !== null
        && item.simulationDrawdown !== null
      )
      .slice(0, 3)
    const blocked = decisionScores
      .filter((item) =>
        Boolean(item.salesGap)
        || item.fund.operation_status?.status === 'blocked'
        || !item.feeComparable
        || (item.fund.buy_evidence?.requiredMissingCount ?? 0) > 0
        || item.simulationReturn === null
      )
      .slice(0, 5)
    const reversal = decisionScores
      .filter((item, index) =>
        index > 0
        && (
          leaderScore - item.score <= 8
          || Boolean(item.salesGap)
          || !item.feeComparable
          || item.simulationReturn === null
          || !hasSimulation
        )
      )
      .slice(0, 4)
    const blockerText = (item: DecisionScore) => {
      if (item.salesGap?.alertsHref) return `复查队列未解决 ${item.salesGap.missingCount} 项：${item.salesGap.missingItems.slice(0, 4).join('、')}`
      if (item.salesGap) return `销售规则硬缺口 ${item.salesGap.missingCount} 项：${item.salesGap.missingItems.slice(0, 4).join('、')}`
      if (item.fund.operation_status?.status === 'blocked') return item.fund.operation_status.reason || '申赎/运作状态阻断'
      if ((item.fund.buy_evidence?.requiredMissingCount ?? 0) > 0) return `研究必补证据 ${item.fund.buy_evidence?.requiredMissingCount} 项`
      if (!item.feeComparable) return '费用、申赎或赎回规则不可直接横比'
      if (item.simulationReturn === null) return '缺真实净值持有体验回放'
      return item.gateDetail
    }
    const actionTasks = decisionScores
      .flatMap((item, index) => {
        const tasks: Array<{
          kind: 'sales_rule' | 'operation' | 'fee' | 'evidence' | 'simulation' | 'reversal'
          priority: number
          windCode: string
          fund: FundSummary
          title: string
          detail: string
          cta: string
        }> = []
        const rankGap = Math.max(0, leaderScore - item.score)
        const requiredMissingCount = item.fund.buy_evidence?.requiredMissingCount ?? 0
        if (item.fund.operation_status?.status === 'blocked') {
          tasks.push({
            kind: 'operation',
            priority: 100,
            windCode: item.windCode,
            fund: item.fund,
            title: '确认申赎/运作状态',
            detail: item.fund.operation_status.reason || '申赎或运作状态阻断，补规则前不进入研究路径。',
            cta: '打开基金详情',
          })
        }
        if (item.salesGap) {
          tasks.push({
            kind: 'sales_rule',
            priority: 95,
            windCode: item.windCode,
            fund: item.fund,
            title: item.salesGap.alertsHref ? '处理复查队列硬阻断' : '补销售规则硬缺口',
            detail: `缺 ${item.salesGap.missingCount} 项：${item.salesGap.missingItems.slice(0, 5).join('、')}。`,
            cta: item.salesGap.alertsHref ? '处理复查队列' : '去补销售规则',
          })
        }
        if (requiredMissingCount > 0 && !item.salesGap) {
          tasks.push({
            kind: 'evidence',
            priority: 82,
            windCode: item.windCode,
            fund: item.fund,
            title: '补研究必核证据',
            detail: `仍有 ${requiredMissingCount} 项必补证据，缺失项不能按中性处理。`,
            cta: '打开研究复核一页纸',
          })
        }
        if (!item.feeComparable) {
          tasks.push({
            kind: 'fee',
            priority: 78,
            windCode: item.windCode,
            fund: item.fund,
            title: '补费用与赎回成本',
            detail: '费用、申购费、赎回费或销售服务费不可直接横比，费后排序可能失真。',
            cta: item.salesGap?.alertsHref ? '处理复查队列' : item.salesGap ? '去补销售规则' : '打开研究复核一页纸',
          })
        }
        if (item.simulationReturn === null || item.simulationDrawdown === null) {
          tasks.push({
            kind: 'simulation',
            priority: 68,
            windCode: item.windCode,
            fund: item.fund,
            title: '补真实净值持有体验回放',
            detail: `${purchasePlanLabels[purchasePlan]}收益或回撤体验待跑，不能只用静态评分排序。`,
            cta: '重跑持有体验回放',
          })
        }
        if (index > 0 && rankGap <= 8) {
          tasks.push({
            kind: 'reversal',
            priority: 52,
            windCode: item.windCode,
            fund: item.fund,
            title: '复核可能反转样本',
            detail: `距第一名仅 ${rankGap} 分，补齐证据或重跑回放后可能反超。`,
            cta: '打开研究复核一页纸',
          })
        }
        return tasks
      })
      .sort((left, right) => right.priority - left.priority)
      .slice(0, 8)

    return {
      ready,
      blocked,
      reversal,
      actionTasks,
      summary: ready.length
        ? `${ready.length} 只具备继续研究复核条件；仍需销售平台实时复核。`
        : '当前没有可直接推进的正式研究复核候选，先按阻断队列补证。',
      blockerText,
    }
  }, [decisionScores, simulationResults.length])
  const comparisonHealthCheck = useMemo(() => {
    if (!matrix?.funds.length || !decisionScores.length) return null
    const formalReadyRows = decisionScores.filter((item) =>
      !item.salesGap
      && item.fund.operation_status?.status !== 'blocked'
      && item.feeComparable
      && (item.fund.buy_evidence?.requiredMissingCount ?? 0) === 0
      && item.simulationReturn !== null
      && item.simulationDrawdown !== null,
    )
    const salesBlockedRows = decisionScores.filter((item) => Boolean(item.salesGap))
    const operationBlockedRows = decisionScores.filter((item) => item.fund.operation_status?.status === 'blocked')
    const evidenceBlockedRows = decisionScores.filter((item) => (item.fund.buy_evidence?.requiredMissingCount ?? 0) > 0)
    const feeGapRows = decisionScores.filter((item) => !item.feeComparable)
    const replayMissingRows = decisionScores.filter((item) => item.simulationReturn === null || item.simulationDrawdown === null)
    const leader = decisionScores[0]
    const leaderFormalReady = Boolean(leader && formalReadyRows.some((item) => item.windCode === leader.windCode))
    const blockedCount = new Set([
      ...salesBlockedRows.map((item) => item.windCode),
      ...operationBlockedRows.map((item) => item.windCode),
    ]).size
    const verifyCount = new Set([
      ...evidenceBlockedRows.map((item) => item.windCode),
      ...feeGapRows.map((item) => item.windCode),
      ...replayMissingRows.map((item) => item.windCode),
    ]).size
    const headline = !formalReadyRows.length
      ? '横评体检：暂无正式可推进样本'
      : leaderFormalReady
        ? '横评体检：第一名可进入研究复核'
        : '横评体检：第一名仍需补证'
    const summary = !formalReadyRows.length
      ? '这组基金还不能形成正式研究优先级；先清销售规则/R1-R5、费用和真实净值回放缺口。'
      : leaderFormalReady
        ? `${leader.fund.name} 当前通过横评前置门禁，可进入研究复核报告和观察池复核；仍不构成申赎操作指令。`
        : `${leader.fund.name} 暂列第一，但存在硬缺口或证据缺口，只能作为补证优先样本。`
    const lanes = [
      {
        title: '能不能形成正式横评结论',
        status: formalReadyRows.length >= 2 ? 'done' as const : formalReadyRows.length ? 'verify' as const : 'blocked' as const,
        label: formalReadyRows.length >= 2 ? `${formalReadyRows.length} 只可正式横评` : formalReadyRows.length ? '样本偏少' : '暂无可正式横评样本',
        detail: formalReadyRows.length >= 2
          ? '至少两只基金通过销售规则、费用、回放和研究证据门禁，可进入正式横评报告复核。'
          : '正式横评至少需要两只规则和证据均可比的基金；不足时只能输出补证路线。',
      },
      {
        title: '第一名是否能推进',
        status: leaderFormalReady ? 'done' as const : leader?.salesGap || leader?.fund.operation_status?.status === 'blocked' ? 'blocked' as const : 'verify' as const,
        label: leaderFormalReady ? '第一名可复核' : leader ? leader.gateLabel : '第一名待生成',
        detail: leaderFormalReady
          ? `${leader.fund.name} 当前分 ${leader.score}，但仍需销售平台实时状态、费率和适当性最终复核。`
          : leader?.gateDetail || '先生成对比矩阵和持有体验回放。',
      },
      {
        title: '阻断来自哪里',
        status: blockedCount ? 'blocked' as const : verifyCount ? 'verify' as const : 'done' as const,
        label: blockedCount ? `${blockedCount} 只硬阻断` : verifyCount ? `${verifyCount} 只待补证` : '未见硬阻断',
        detail: [
          salesBlockedRows.length ? `销售规则/R1-R5 ${salesBlockedRows.length} 只` : '',
          operationBlockedRows.length ? `申赎状态 ${operationBlockedRows.length} 只` : '',
          feeGapRows.length ? `费用不可比 ${feeGapRows.length} 只` : '',
          replayMissingRows.length ? `回放待补 ${replayMissingRows.length} 只` : '',
        ].filter(Boolean).join('；') || '当前没有识别到销售规则、运作状态、费用或回放硬缺口。',
      },
      {
        title: '下一步先做什么',
        status: blockedCount || verifyCount ? 'verify' as const : 'done' as const,
        label: salesBlockedRows.length ? '先补销售规则/R1-R5' : replayMissingRows.length ? '先重跑回放' : feeGapRows.length ? '先补费用' : '保存横评报告',
        detail: salesBlockedRows.length
          ? '销售规则和 R1-R5 来源未清零前，不能把横评第一名保存为正式研究候选。'
          : replayMissingRows.length
            ? '缺真实净值持有体验回放时，不能只凭专业评分或历史收益排序。'
            : feeGapRows.length
              ? '费用证据不可比时，费后收益排序可能反转。'
              : '可保存横评报告固定证据口径，但正式研究复核仍需销售平台实时复核。',
      },
    ]
    const primaryActionKind = salesBlockedRows.length ? 'sales_rules' as const : replayMissingRows.length ? 'simulation' as const : 'report' as const
    return {
      headline,
      summary,
      lanes,
      doneCount: lanes.filter((item) => item.status === 'done').length,
      verifyCount: lanes.filter((item) => item.status === 'verify').length,
      blockedCount: lanes.filter((item) => item.status === 'blocked').length,
      formalReadyCount: formalReadyRows.length,
      primaryActionKind,
    }
  }, [decisionScores, matrix?.funds])
  const leaderInvestorFourQuestions = useMemo(() => {
    const leader = decisionScores[0] || null
    const runner = decisionScores[1] || null
    if (!leader) return null
    const leaderFormalReady = Boolean(leader
      && !leader.salesGap
      && leader.fund.operation_status?.status !== 'blocked'
      && leader.feeComparable
      && (leader.fund.buy_evidence?.requiredMissingCount ?? 0) === 0
      && leader.simulationReturn !== null
      && leader.simulationDrawdown !== null)
    const scoreGap = runner ? leader.score - runner.score : null
    const gapCopy = scoreGap === null ? '缺少第二名样本' : `领先第二名 ${scoreGap} 分`
    const stressCopy = leader.longestUnderwaterDays !== null
      ? `最长亏损等待约 ${Math.round(leader.longestUnderwaterDays)} 天，最差三个月 ${formatPercent(leader.worstThreeMonthReturn)}`
      : '压力体验待跑'
    const gateBlockers = [
      leader.salesGap ? `销售规则/R1-R5 缺 ${leader.salesGap.missingCount} 项` : '',
      leader.fund.operation_status?.status === 'blocked' ? (leader.fund.operation_status.reason || '申赎/运作状态阻断') : '',
      !leader.feeComparable ? '费用和赎回证据不可直接横比' : '',
      (leader.fund.buy_evidence?.requiredMissingCount ?? 0) > 0 ? `研究必补 ${(leader.fund.buy_evidence?.requiredMissingCount ?? 0)} 项` : '',
      leader.simulationReturn === null || leader.simulationDrawdown === null ? '真实净值持有体验回放待跑' : '',
    ].filter(Boolean)
    const questions = [
      {
        key: 'can-continue',
        question: '第一名现在能不能继续进入研究复核？',
        answer: leaderFormalReady
          ? `${leader.fund.name} 可继续研究复核，但仍不是申赎操作指令。`
          : `${leader.fund.name} 暂列第一，但只能先补证或观察。`,
        evidence: gateBlockers.length ? gateBlockers.slice(0, 3).join('；') : `决策分 ${leader.score}；${gapCopy}；销售规则未见硬缺口。`,
        nextAction: gateBlockers.length ? gateBlockers[0] : '打开详情页做研究复核一页纸、份额成本和销售平台实时复核。',
      },
      {
        key: 'why-leader',
        question: '为什么是它领先，而不是只看收益榜？',
        answer: decisionExplanation?.decisiveEdges.slice(0, 2).join('；') || `${leader.fund.name} 当前综合决策分最高。`,
        evidence: [
          `回放收益 ${formatPercent(leader.simulationReturn)}`,
          `回放回撤 ${formatPercent(leader.simulationDrawdown)}`,
          `证据分 ${leader.fund.buy_evidence?.completenessScore ?? 0}`,
          `专业评分 ${leader.fund.professional_score?.toFixed?.(1) || '待补'}`,
        ].join('；'),
        nextAction: runner ? `继续复核与 ${runner.fund.name} 的分差、费用和压力体验。` : '补充第二只同类基金再横评。',
      },
      {
        key: 'cost-executable',
        question: '这笔金额配置起来贵不贵、卡不卡？',
        answer: leader.feeComparable
          ? '费用证据可初步横比，但仍需详情页确认同基金 A/C/I/H 份额和赎回持有期。'
          : '费用或赎回规则不可比，暂不能确认费后优势。',
        evidence: leader.gateDetail,
        nextAction: leader.feeComparable ? '进入详情页做份额成本复核。' : '先补申购费、赎回费、销售服务费和金额门禁。',
      },
      {
        key: 'can-hold',
        question: '如果持有，回撤和等待压力扛不扛得住？',
        answer: leader.simulationDrawdown !== null
          ? `${purchasePlanLabels[purchasePlan]}回撤 ${formatPercent(leader.simulationDrawdown)}；${stressCopy}。`
          : '缺真实净值回放，不能判断持有后的压力体验。',
        evidence: leader.stressScore !== null ? `压力体验分 ${leader.stressScore}` : '压力体验待补',
        nextAction: leader.simulationReturn === null || leader.simulationDrawdown === null ? '先运行持有体验回放。' : '结合研究持有期和回撤预算复核。',
      },
    ]
    const verdict = leaderFormalReady
      ? '第一名可进入研究复核'
      : gateBlockers.length
        ? '第一名先补证，不进正式候选'
        : '第一名仍需横评确认'
    const primaryHref = gateBlockers.length && leader.salesGap
      ? salesRuleActionHrefForGap(leader.salesGap, leader.windCode)
      : fundDetailHref(leader.fund)
    return {
      leader,
      runner,
      verdict,
      leaderFormalReady,
      gateBlockers,
      questions,
      primaryHref,
      primaryActionLabel: gateBlockers.length ? '处理第一阻断' : '打开第一名详情',
      boundary: '横评第一名只能回答“先研究谁”；销售规则、R1-R5、费用、真实回放和详情页研究复核报告未闭环前，不形成研究结论。',
    }
  }, [decisionExplanation?.decisiveEdges, decisionScores, fundDetailHref, purchasePlan, salesRuleActionHrefForGap])

  const copyMemo = useCallback(async () => {
    if (!memoText) return
    try {
      if (!globalThis.navigator?.clipboard?.writeText) {
        throw new Error('clipboard unavailable')
      }
      await Promise.race([
        globalThis.navigator.clipboard.writeText(memoText),
        new Promise((_, reject) => {
          globalThis.setTimeout(() => reject(new Error('clipboard timeout')), 1500)
        }),
      ])
      setMemoStatus('已复制研究备忘录')
    } catch {
      setMemoStatus('复制失败，请手动选中文本复制')
    }
  }, [memoText])

  const comparisonDecisionTsv = useMemo(() => {
    if (!matrix?.funds.length || !decisionScores.length) return ''
    const actionTasks = buyForwardQueue?.actionTasks || []
    const actionTaskHref = (task: typeof actionTasks[number]) => {
      const taskSalesGap = salesGapByCode.get(task.windCode.toUpperCase())
      return task.kind === 'sales_rule' || (task.kind === 'fee' && taskSalesGap)
        ? salesRuleActionHrefForGap(taskSalesGap, task.windCode)
        : fundDetailHref(task.fund)
    }
    return [
      ['证据组', '基金代码', '基金名称', '决策排名/分数', '状态/结论', '关键证据', '下一动作', '入口', '硬边界'].join('\t'),
      [
        '横评口径',
        comparedCodes.join('、'),
        `${profileLabels[profile]} / ${horizonLabels[horizon]} / ${purchasePlanLabels[purchasePlan]}`,
        `窗口=${metricWindow}；计划金额=${currentPlannedAmount().toLocaleString('zh-CN')} 元；回放月数=${simulationMonths}`,
        comparisonHealthCheck?.headline || '横评体检待生成',
        comparisonHealthCheck?.summary || purchaseDecision?.conclusion || '待生成横评结论',
        comparisonHealthCheck?.primaryActionKind === 'sales_rules' ? '先补销售规则/R1-R5' : comparisonHealthCheck?.primaryActionKind === 'simulation' ? '重跑持有体验回放' : '保存横评报告前复核门禁',
        comparisonReturnHref,
        '横评只服务基金研究、筛选和研究复核；不输出申赎操作指令。',
      ].map(tsvCell).join('\t'),
      ...decisionScores.map((item, index) => [
        '横评决策分',
        item.windCode,
        item.fund.name,
        `第 ${index + 1} 名 / ${item.score} 分`,
        item.gateLabel,
        [
          `回放收益=${formatPercent(item.simulationReturn)}`,
          `回放回撤=${formatPercent(item.simulationDrawdown)}`,
          `压力体验=${item.stressScore ?? '待补'}`,
          `费用可比=${item.feeComparable ? '是' : '否'}`,
          item.salesGap ? `销售规则缺 ${item.salesGap.missingCount} 项` : '销售规则未见硬缺口',
          item.scoreCaps.length ? `封顶=${item.scoreCaps.join('；')}` : '',
      ].filter(Boolean).join('；'),
        item.nextAction,
        item.salesGap ? salesRuleActionHrefForGap(item.salesGap, item.windCode) : fundDetailHref(item.fund),
        item.salesGap
          ? '销售规则/R1-R5 来源背书未清零前，不能入池、不能保存正式横评报告。'
          : item.fund.operation_status?.status === 'blocked'
            ? '申赎或运作状态阻断时，只能排除或观察。'
            : '决策分领先不等于可研究，仍需研究复核一页纸和销售平台实时复核。',
      ].map(tsvCell).join('\t')),
      ...(decisionExplanation?.pairwiseDeltas || []).map((item) => [
        '一对一PK差异',
        decisionExplanation?.leader.windCode || '',
        decisionExplanation?.runner?.windCode || '',
        item.metric,
        item.edge,
        `${decisionExplanation?.leader.fund.name || '第一名'}=${item.leaderValue}；${decisionExplanation?.runner?.fund.name || '第二名'}=${item.runnerValue}`,
        item.verdict,
        item.verdict.includes('补') || item.verdict.includes('不可') ? '补证后重跑横评' : '进入详情研究复核',
        decisionExplanation?.leader.salesGap ? salesRuleActionHrefForGap(decisionExplanation.leader.salesGap, decisionExplanation.leader.windCode) : decisionExplanation?.leader ? fundDetailHref(decisionExplanation.leader.fund) : comparisonReturnHref,
        '一对一领先项只解释研究排序；销售规则、费用、回放或压力体验缺失时不能形成正式研究结论。',
      ].map(tsvCell).join('\t')),
      ...actionTasks.map((task, index) => [
        '字段级补证清单',
        task.windCode,
        task.fund.name,
        `P${index + 1} / ${task.priority}`,
        task.title,
        task.detail,
        task.cta,
        actionTaskHref(task),
        '字段级缺口不按中性分处理；补齐后必须重跑横评。',
      ].map(tsvCell).join('\t')),
      ...(leaderInvestorFourQuestions?.questions || []).map((item, index) => [
        '第一名研究复核四问',
        leaderInvestorFourQuestions?.leader.windCode || '',
        leaderInvestorFourQuestions?.leader.fund.name || '',
        `Q${index + 1}`,
        item.question,
        `${item.answer}；证据：${item.evidence}`,
        item.nextAction,
        leaderInvestorFourQuestions?.primaryHref || comparisonReturnHref,
        leaderInvestorFourQuestions?.boundary || '横评第一名只能回答先研究谁，不能替代正式研究复核报告。',
      ].map(tsvCell).join('\t')),
      [
        '正式结论边界',
        purchaseDecision?.primaryFund?.wind_code || '',
        purchaseDecision?.primaryFund?.name || '待生成',
        `正式可比=${comparisonHealthCheck?.formalReadyCount ?? 0} 只`,
        purchaseDecision?.conclusion || '当前样本不足',
        decisionExplanation?.recheckTriggers.join('；') || '补齐销售规则、费用和真实净值回放后重评',
        '进入详情研究复核一页纸、补证台或保存横评报告',
        purchaseDecision?.primaryFund ? fundDetailHref(purchaseDecision.primaryFund) : comparisonReturnHref,
        '正式横评至少需要两只规则、费用、回放和研究证据均可比的基金；不足时只能输出补证路线。',
      ].map(tsvCell).join('\t'),
    ].join('\n')
  }, [
    buyForwardQueue?.actionTasks,
    comparedCodes,
    comparisonHealthCheck,
    comparisonReturnHref,
    currentPlannedAmount,
    decisionExplanation?.recheckTriggers,
    decisionScores,
    fundDetailHref,
    horizon,
    leaderInvestorFourQuestions,
    matrix?.funds.length,
    metricWindow,
    profile,
    purchaseDecision,
    purchasePlan,
    salesGapByCode,
    salesRuleActionHrefForGap,
    salesRulesHrefForCode,
    simulationMonths,
  ])

  const downloadComparisonDecisionTsv = useCallback(() => {
    if (!comparisonDecisionTsv) return
    const blob = new Blob([`\uFEFF${comparisonDecisionTsv}`], { type: 'text/tab-separated-values;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${safeFileStem(`基金横评决策_${comparedCodes.join('_')}`)}_${new Date().toISOString().slice(0, 10)}.tsv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }, [comparedCodes, comparisonDecisionTsv])

  const copyComparisonDecisionTsv = useCallback(async () => {
    if (!comparisonDecisionTsv) return
    try {
      let copied = false
      if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(comparisonDecisionTsv)
          copied = true
        } catch {
          copied = false
        }
      }
      if (!copied) {
        const textArea = document.createElement('textarea')
        textArea.value = comparisonDecisionTsv
        textArea.style.position = 'fixed'
        textArea.style.opacity = '0'
        document.body.appendChild(textArea)
        textArea.focus()
        textArea.select()
        copied = document.execCommand('copy')
        textArea.remove()
      }
      if (!copied) throw new Error('copy failed')
      setDecisionTsvStatus('copied')
      globalThis.setTimeout(() => setDecisionTsvStatus('idle'), 1800)
    } catch {
      downloadComparisonDecisionTsv()
      setDecisionTsvStatus('fallback')
      globalThis.setTimeout(() => setDecisionTsvStatus('idle'), 1800)
    }
  }, [comparisonDecisionTsv, downloadComparisonDecisionTsv])

  const runPurchaseSimulationCompare = useCallback(async () => {
    if (!matrix?.funds.length) return

    setSimulationLoading(true)
    setSimulationStatus('正在读取每只基金真实净值并回放持有体验...')
    setSimulationResults([])

    const params = new URLSearchParams({
      months: String(simulationMonths),
      lumpSumAmount: String(simulationLumpSumAmount),
      monthlyAmount: String(simulationMonthlyAmount),
    })

    try {
      const results = await Promise.all(matrix.funds.map(async (fund) => {
        try {
          const response = await fetch(`/api/funds/${encodeURIComponent(fund.wind_code)}/historical-nav-replay?${params.toString()}`, {
            cache: 'no-store',
          })
          const payload = await response.json().catch(() => ({}))
          if (!response.ok) {
            throw new Error(payload.error || payload.detail || '净值回放失败')
          }
          return {
            windCode: fund.wind_code,
            name: fund.name,
            status: 'ok' as const,
            simulation: payload as PurchaseSimulation,
          }
        } catch (error) {
          return {
            windCode: fund.wind_code,
            name: fund.name,
            status: 'error' as const,
            error: error instanceof Error ? error.message : '净值回放失败',
          }
        }
      }))

      setSimulationResults(results)
      const successCount = results.filter((result) => result.status === 'ok').length
      setSimulationStatus(`已完成 ${successCount}/${results.length} 只基金的持有体验回放`)
    } finally {
      setSimulationLoading(false)
    }
  }, [matrix?.funds, simulationLumpSumAmount, simulationMonthlyAmount, simulationMonths])

  const importTushareFoundationForComparison = useCallback(async () => {
    if (!foundationFillableCodes.length) {
      setSalesGapError('当前对比样本没有可由 Tushare fund_basic 先补的基础状态缺口。')
      return
    }

    try {
      setFoundationHydrating(true)
      setSalesGapError('')
      const response = await fetch('/api/evidence-coverage/materials/tushare-foundation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codes: foundationFillableCodes, purchasePlan, plannedAmount: currentPlannedAmount() }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.error || payload.detail || '导入 Tushare 基础申赎状态失败')
      }
      await loadSalesRuleGaps(comparedCodes)
      setStatus(`已从 Tushare fund_basic 导入 ${payload.savedCount || 0} 只基金的基础申赎状态；${foundationManualFields}仍需销售平台核验。`)
      if (payload.failedCount) {
        const failedPreview = Array.isArray(payload.failed)
          ? payload.failed.slice(0, 3).map((item: { windCode?: string; error?: string }) => `${item.windCode || '未知基金'}：${item.error || '原因待查'}`).join('；')
          : ''
        setSalesGapError(`另有 ${payload.failedCount} 只基础状态导入失败${failedPreview ? `：${failedPreview}` : '。'}`)
      }
    } catch (error) {
      console.error('导入对比样本 Tushare 基础状态失败:', error)
      setSalesGapError(error instanceof Error ? error.message : '导入 Tushare 基础申赎状态失败')
    } finally {
      setFoundationHydrating(false)
    }
  }, [comparedCodes, currentPlannedAmount, foundationFillableCodes, loadSalesRuleGaps, purchasePlan])

  const saveComparisonReport = useCallback(async () => {
    if (!matrix) return
    if (!salesGapPayload) {
      setReportError('销售规则缺口尚未完成扫描，不能保存正式横向比较报告。')
      setReportBlockAction({ salesRulesHref })
      return
    }
    if (salesGapPayload.gapCount > 0) {
      if (activeSalesRuleReviewGaps.length > 0) {
        setReportError(`当前对比仍有 ${activeSalesRuleReviewGaps.length} 只基金存在未解决销售规则/R1-R5复查事件，处理前不保存正式横向比较报告。`)
        setReportBlockAction({ code: 'STALE_SALES_RULE_EVIDENCE_ALERT_BLOCKED', salesRulesHref, alertsHref: reviewEventsHref({ returnTo: comparisonReturnHref }), alertCount: activeSalesRuleReviewGaps.length })
      } else {
        setReportError(`当前对比仍有 ${salesGapPayload.gapCount} 只基金存在销售规则硬缺口，补齐前不保存正式横向比较报告。`)
        setReportBlockAction({ code: 'SALES_RULE_GAP_BLOCKED', salesRulesHref })
      }
      return
    }
    const amountBlockedRules = (salesGapPayload.rules || []).filter((rule) => rule.executionAmountGate?.status === 'blocked')
    if (amountBlockedRules.length > 0) {
      setReportError(`当前对比有 ${amountBlockedRules.length} 只基金计划金额未通过起购/定投起点/限购门禁，调整金额或补规则前不保存正式横向比较报告。`)
      setReportBlockAction({ code: 'SALES_RULE_AMOUNT_GATE_BLOCKED', salesRulesHref })
      return
    }

    try {
      setSavingReport(true)
      setReportMessage('')
      setReportError('')
      setReportBlockAction(null)
      setSavedReportId(null)
      const response = await fetch('/api/funds/comparison-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          matrix,
          simulationResults,
          salesRuleGaps: salesGapPayload?.gaps || [],
          profile,
          horizon,
          purchasePlan,
          plannedAmount: currentPlannedAmount(),
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || !payload.saved) {
        setReportBlockAction({
          code: payload.code,
          salesRulesHref: payload.salesRulesHref,
          alertsHref: payload.alertsHref,
          alertCount: Array.isArray(payload.salesRuleEvidenceAlerts) ? payload.salesRuleEvidenceAlerts.length : undefined,
        })
        throw new Error(payload.error || '保存横向比较报告失败')
      }
      setSavedReportId(payload.reportId || payload.id)
      setReportMessage('已保存基金横向比较报告，可在报告库回看。')
      setReportBlockAction(null)
    } catch (error) {
      console.error('保存横向比较报告失败:', error)
      setReportError(error instanceof Error ? error.message : '保存横向比较报告失败')
    } finally {
      setSavingReport(false)
    }
  }, [activeSalesRuleReviewGaps.length, currentPlannedAmount, horizon, matrix, profile, purchasePlan, salesGapPayload, salesRulesHref, simulationResults])

  const ensureDefaultPool = useCallback(async () => {
    const poolResponse = await fetch('/api/market/research-lists', { cache: 'no-store' })
    const poolPayload = await poolResponse.json().catch(() => ({}))
    if (!poolResponse.ok) {
      throw new Error(poolPayload.detail || poolPayload.error || '读取默认观察池失败')
    }

    const poolId = poolPayload.pools?.[0]?.id as string | undefined
    if (poolId) return poolId

    const createResponse = await fetch('/api/market/research-lists', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: '默认观察池',
        description: '由基金对比矩阵自动创建',
        createdBy: 'comparison-ui',
        isDefault: true,
      }),
    })
    const createdPayload = await createResponse.json().catch(() => ({}))
    if (!createResponse.ok || !createdPayload.id) {
      throw new Error(createdPayload.detail || createdPayload.error || '创建默认观察池失败')
    }
    return createdPayload.id as string
  }, [])

  const addComparisonFundToPool = useCallback(async (fund: FundSummary) => {
    if (!fund.id) {
      setPoolError(`${fund.name} 缺少本地基金 ID，不能加入观察池。`)
      return
    }
    if (!salesGapPayload) {
      setPoolError('销售规则缺口尚未完成扫描，不能加入观察池。')
      return
    }
    const salesRuleGap = salesGapByCode.get(fund.wind_code.toUpperCase())
    if (salesRuleGap) {
      setPoolError(salesRuleGap.alertsHref
        ? `${fund.name} 复查队列仍有 ${salesRuleGap.missingCount} 项未解决事件，处理前不能加入观察池。`
        : `${fund.name} 销售规则仍缺 ${salesRuleGap.missingCount} 项，补齐前不能加入观察池。`)
      return
    }
    if (fund.operation_status?.status === 'blocked') {
      setPoolError(`${fund.name} 存在不可申购/非在运作信号，不能加入观察池。`)
      return
    }

    try {
      setAddingFundCode(fund.wind_code)
      setPoolMessage('')
      setPoolError('')
      const poolId = await ensureDefaultPool()
      const simulationResult = simulationResults.find((result) => result.windCode === fund.wind_code)
      const leaderRows = (matrix?.matrix_rows || [])
        .filter((row) => row.best_code === fund.wind_code)
        .slice(0, 6)
        .map((row) => row.label)
      const decisionRow = decisionScores.find((item) => item.windCode === fund.wind_code) || null
      const decisionRank = decisionRow ? decisionScores.findIndex((item) => item.windCode === fund.wind_code) + 1 : null
      const comparisonTraceConclusion = decisionRow
        ? `横评留痕：第 ${decisionRank} 名，决策分 ${decisionRow.score}，${decisionRow.label}；门禁：${decisionRow.gateLabel}；下一步：${decisionRow.nextAction}。${decisionExplanation?.conclusion || '仍需销售平台实时规则复核。'}`
        : `对比矩阵入池：${matrix?.metric_window || metricWindow}，${leaderRows.length ? `领先 ${leaderRows.join('、')}` : '进入横向研究'}。`
      const comparisonTraceRiskNotes = [
        decisionRow?.gateDetail,
        decisionRow?.scoreCaps.slice(0, 3).join('；'),
        decisionExplanation?.recheckTriggers.slice(0, 4).join('；'),
        fund.buy_evidence?.conclusion,
        fund.operation_status?.reason,
        fund.fee_info?.missing?.length ? `费用待补：${fund.fee_info.missing.slice(0, 4).join('、')}` : '',
      ].filter(Boolean).join('；') || null

      const response = await fetch(`/api/market/research-lists/${poolId}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fundId: fund.id,
          status: 'watch',
          reason: decisionRow
            ? `对比矩阵入池：决策分 ${decisionRow.score}，${decisionRow.label}；${leaderRows.length ? `领先 ${leaderRows.join('、')}` : '进入横向研究'}`
            : `对比矩阵入池：${matrix?.metric_window || metricWindow}，${leaderRows.length ? `领先 ${leaderRows.join('、')}` : '进入横向研究'}`,
          latestConclusion: comparisonTraceConclusion,
          riskNotes: comparisonTraceRiskNotes,
          evidence: {
            source: 'comparison-matrix',
            addedAt: new Date().toISOString(),
            comparison: {
              window: matrix?.metric_window || metricWindow,
              comparedCodes,
              leaderMetrics: leaderRows,
              professionalScore: fund.professional_score ?? null,
              professionalGrade: fund.professional_grade ?? null,
              peerGroup: fund.peer_group ?? null,
              peerCount: fund.peer_count ?? null,
            },
            comparisonDecision: decisionRow ? {
              rank: decisionRank,
              score: decisionRow.score,
              label: decisionRow.label,
              gateLabel: decisionRow.gateLabel,
              gateDetail: decisionRow.gateDetail,
              nextAction: decisionRow.nextAction,
              reasons: decisionRow.reasons,
              scoreCaps: decisionRow.scoreCaps,
              isLeader: decisionExplanation?.leader.windCode === fund.wind_code,
              leaderCode: decisionExplanation?.leader.windCode || null,
              runnerCode: decisionExplanation?.runner?.windCode || null,
              scoreGap: decisionExplanation?.scoreGap ?? null,
              conclusion: decisionExplanation?.conclusion || null,
              decisiveEdges: decisionExplanation?.decisiveEdges || [],
              recheckTriggers: decisionExplanation?.recheckTriggers || [],
              knockoutLines: decisionExplanation?.knockoutLines || [],
              nextActions: decisionExplanation?.nextActions || [],
            } : null,
            buyEvidence: fund.buy_evidence ?? null,
            operationStatus: fund.operation_status ?? null,
            feeInfo: fund.fee_info ?? null,
            purchaseSimulation: simulationResult?.status === 'ok'
              ? {
                  months: simulationMonths,
                  lumpSumReturn: simulationResult.simulation?.lumpSum.returnRate ?? null,
                  lumpSumMaxDrawdown: simulationResult.simulation?.lumpSum.maxDrawdown ?? null,
                  sipReturn: simulationResult.simulation?.sip.returnRate ?? null,
                  sipMaxAccountDrawdown: simulationResult.simulation?.sip.maxAccountDrawdown ?? null,
                  observations: simulationResult.simulation?.period.observations ?? null,
                }
              : null,
            investorContext: {
              profile,
              profileLabel: profileLabels[profile],
              horizon,
              horizonLabel: horizonLabels[horizon],
              purchasePlan,
              purchasePlanLabel: purchasePlanLabels[purchasePlan],
              plannedAmount: currentPlannedAmount(),
              plannedAmountLabel: purchasePlan === 'sip'
                ? `计划月扣款 ${currentPlannedAmount()} 元`
                : `计划配置 ${currentPlannedAmount()} 元`,
            },
          },
          createdBy: 'comparison-ui',
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail || payload.error || '加入观察池失败')
      }
      setPoolMessage(`已将 ${fund.name} 加入观察池，可继续维护研究结论。`)
    } catch (error) {
      console.error('对比页加入观察池失败:', error)
      setPoolError(error instanceof Error ? error.message : '加入观察池失败')
    } finally {
      setAddingFundCode(null)
    }
  }, [comparedCodes, currentPlannedAmount, decisionExplanation, decisionScores, ensureDefaultPool, horizon, matrix, metricWindow, profile, purchasePlan, salesGapByCode, salesGapPayload, simulationMonths, simulationResults])

  useEffect(() => {
    if (typeof globalThis.window === 'undefined') return
    const params = new URLSearchParams(globalThis.window.location.search)
    const windCodes = parseCodes(params.get('codes') || '')
    const windowParam = params.get('window') || ''
    const profileParam = params.get('profile') || ''
	    const horizonParam = params.get('horizon') || ''
	    const purchasePlanParam = params.get('purchasePlan') || ''
	    const plannedAmountParam = Number(params.get('plannedAmount') || '')
	    const lumpSumAmountParam = Number(params.get('lumpSumAmount') || '')
    const monthlyAmountParam = Number(params.get('monthlyAmount') || '')
	    const autoReplayParam = params.get('autoReplay') || ''

	    const timeout = globalThis.setTimeout(() => {
      setSourceReturnHref(safeReturnPath(params.get('returnTo')))
	      if (windCodes.length > 0) {
        setCodesText(windCodes.join('\n'))
        autoCompared.current = false
      }
      if (ALLOWED_METRIC_WINDOWS.includes(windowParam)) {
        setMetricWindow(windowParam)
      }
      if (['conservative', 'balanced', 'aggressive'].includes(profileParam)) {
        setProfile(profileParam as RiskProfile)
      }
      if (['lt1y', '1to3y', 'gt3y'].includes(horizonParam)) {
        setHorizon(horizonParam as InvestmentHorizon)
      }
      if (['lump_sum', 'sip'].includes(purchasePlanParam)) {
        setPurchasePlan(purchasePlanParam as PurchasePlan)
      }
      if (Number.isFinite(lumpSumAmountParam) && lumpSumAmountParam > 0) {
        setSimulationLumpSumAmount(lumpSumAmountParam)
      }
      if (Number.isFinite(monthlyAmountParam) && monthlyAmountParam > 0) {
        setSimulationMonthlyAmount(monthlyAmountParam)
      }
      if (Number.isFinite(plannedAmountParam) && plannedAmountParam > 0) {
        if (purchasePlanParam === 'lump_sum') {
          setSimulationLumpSumAmount(plannedAmountParam)
        } else {
          setSimulationMonthlyAmount(plannedAmountParam)
        }
      }
      if (autoReplayParam === '1' || autoReplayParam === 'true') {
        setAutoReplay(true)
        autoReplayed.current = false
      }
      setUrlParamsReady(true)
    }, 0)
    return () => globalThis.clearTimeout(timeout)
  }, [])

  useEffect(() => {
    if (!urlParamsReady || autoCompared.current) return
    const windCodes = parseCodes(codesText)
    if (windCodes.length >= 2) {
      autoCompared.current = true
      const timeout = globalThis.setTimeout(() => {
        void runCompare(windCodes, metricWindow)
      }, 0)
      return () => globalThis.clearTimeout(timeout)
    }
  }, [codesText, metricWindow, runCompare, urlParamsReady])

  useEffect(() => {
    if (!autoReplay || !matrix?.funds.length || autoReplayed.current) return
    autoReplayed.current = true
    const timeout = globalThis.setTimeout(() => {
      void runPurchaseSimulationCompare()
    }, 0)
    return () => globalThis.clearTimeout(timeout)
  }, [autoReplay, matrix, runPurchaseSimulationCompare])

  useEffect(() => {
    if (!matrix?.funds.length) return
    const timeout = globalThis.setTimeout(() => {
      void loadSalesRuleGaps(matrix.funds.map((fund) => fund.wind_code))
    }, 0)
    return () => globalThis.clearTimeout(timeout)
  }, [loadSalesRuleGaps, matrix?.funds, purchasePlan])

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <Link
        href={sourceReturnHref}
        className="inline-flex items-center text-gray-600 hover:text-gray-900"
        data-testid="comparison-return-link"
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        返回
      </Link>

      <div className="overflow-hidden rounded-2xl bg-slate-950 shadow-xl">
        <div className="relative p-6 text-white md:p-8">
          <div className="absolute right-0 top-0 h-40 w-40 rounded-full bg-blue-500/20 blur-3xl" />
          <div className="absolute bottom-0 left-1/3 h-32 w-32 rounded-full bg-emerald-500/10 blur-3xl" />
          <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-end">
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-xl bg-white/10 px-4 py-3 ring-1 ring-white/10">
                <BarChart3 className="mx-auto h-5 w-5 text-blue-200" />
                <div className="mt-1 text-xs text-slate-300">滚动指标</div>
              </div>
              <div className="rounded-xl bg-white/10 px-4 py-3 ring-1 ring-white/10">
                <Percent className="mx-auto h-5 w-5 text-emerald-200" />
                <div className="mt-1 text-xs text-slate-300">同类分位</div>
              </div>
              <div className="rounded-xl bg-white/10 px-4 py-3 ring-1 ring-white/10">
                <ShieldCheck className="mx-auto h-5 w-5 text-amber-200" />
                <div className="mt-1 text-xs text-slate-300">尽调建议</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {autoReplay ? (
        <div className="rounded-2xl border border-amber-100 bg-amber-50 p-4 text-sm text-amber-950 shadow" data-testid="comparison-auto-replay-intent">
          <div className="font-semibold">来自补证队列：自动重跑真实回放横评</div>
          <div className="mt-1 text-xs leading-5 text-amber-800">
            已带入 {parseCodes(codesText).length} 只基金、{purchasePlanLabels[purchasePlan]}、计划金额 ¥{currentPlannedAmount().toLocaleString('zh-CN')}；页面会先生成对比矩阵，再自动运行持有体验回放。
          </div>
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
        <div className="rounded-2xl bg-white p-6 shadow">
          <label htmlFor="comparison-codes" className="block text-sm font-semibold text-gray-900">基金代码</label>
          <p className="mt-1 text-xs text-gray-500">支持换行、空格或逗号分隔，单次最多 10 只。</p>
          <textarea
            id="comparison-codes"
            name="comparison_codes"
            value={codesText}
            onChange={(event) => setCodesText(event.target.value)}
            disabled={loading}
            rows={7}
            className="mt-3 w-full rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 font-mono text-sm outline-none focus:border-blue-500 focus:bg-white"
            placeholder="000002.OF&#10;000007.OF"
          />

          <label htmlFor="comparison-window" className="mt-5 block text-sm font-semibold text-gray-900">指标窗口</label>
          <select
            id="comparison-window"
            name="comparison_window"
            value={metricWindow}
            onChange={(event) => setMetricWindow(event.target.value)}
            disabled={loading}
            className="mt-2 w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
          >
            <option value="1y">近 1 年</option>
            <option value="3y">近 3 年</option>
            <option value="manager_tenure">现任经理任期</option>
          </select>

          <div className="mt-5 rounded-2xl border border-blue-100 bg-blue-50 p-4">
            <div className="text-sm font-semibold text-blue-950">研究画像假设</div>
            <p className="mt-1 text-xs leading-5 text-blue-800">
              用于备忘录、入池证据和后续研究复核；不替代销售平台正式适当性测评。
            </p>
            <div className="mt-3 grid gap-3">
              <label className="text-xs font-medium text-blue-950">
                风险承受力
                <select
                  name="comparison_profile"
                  value={profile}
                  onChange={(event) => setProfile(event.target.value as RiskProfile)}
                  className="mt-1 w-full rounded-lg border border-blue-100 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  {profileOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label} · {option.note}</option>
                  ))}
                </select>
              </label>
              <label className="text-xs font-medium text-blue-950">
                计划持有期
                <select
                  name="comparison_horizon"
                  value={horizon}
                  onChange={(event) => setHorizon(event.target.value as InvestmentHorizon)}
                  className="mt-1 w-full rounded-lg border border-blue-100 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  {horizonOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <label className="text-xs font-medium text-blue-950">
                研究方式假设
                <select
                  name="comparison_purchase_plan"
                  value={purchasePlan}
                  onChange={(event) => setPurchasePlan(event.target.value as PurchasePlan)}
                  className="mt-1 w-full rounded-lg border border-blue-100 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  {purchasePlanOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
            </div>
            <div className="mt-3 rounded-xl bg-white px-3 py-2 text-xs leading-5 text-blue-900">
              当前：{profileLabels[profile]} · {horizonLabels[horizon]} · {purchasePlanLabels[purchasePlan]} · 计划金额 ¥{currentPlannedAmount().toLocaleString('zh-CN')}
            </div>
          </div>

          <button
            onClick={() => void runCompare()}
            disabled={loading || parseCodes(codesText).length < 2}
            className="mt-5 inline-flex w-full items-center justify-center rounded-xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-950/10 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                计算中...
              </>
            ) : (
              <>
                <GitCompare className="mr-2 h-4 w-4" />
                生成对比矩阵
              </>
            )}
          </button>

          {status && (
            <div className="mt-4 rounded-xl bg-blue-50 px-4 py-3 text-sm text-blue-800">
              {status}
            </div>
          )}

          {poolMessage ? (
            <div className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              {poolMessage}
              <Link href={canonicalResearchHref('/pools?status=candidate')} className="ml-2 font-medium text-emerald-700 hover:text-emerald-900">
                去研究清单查看
              </Link>
            </div>
          ) : null}

          {poolError ? (
            <div className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800">
              {poolError}
            </div>
          ) : null}

          {reportMessage ? (
            <div className="mt-4 rounded-xl bg-purple-50 px-4 py-3 text-sm text-purple-800">
              {reportMessage}
              {savedReportId ? (
                <Link href={`/reports/${savedReportId}`} className="ml-2 font-medium text-purple-700 hover:text-purple-900">
                  查看报告
                </Link>
              ) : null}
            </div>
          ) : null}

          {reportError ? (
            <div className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-800" data-testid="comparison-report-block-action">
              <div>{reportError}</div>
              {reportBlockAction ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {reportBlockAction.alertsHref ? (
                    <Link
                      href={appendReturnTo(reportBlockAction.alertsHref, comparisonReturnHref)}
                      className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700"
                    >
                      打开复查队列{reportBlockAction.alertCount ? ` · ${reportBlockAction.alertCount}` : ''}
                    </Link>
                  ) : null}
                  {(reportBlockAction.salesRulesHref || salesRulesHref) ? (
                    <Link
                      href={reportBlockAction.salesRulesHref || salesRulesHref}
                      className="rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-rose-800 ring-1 ring-rose-100 hover:bg-rose-100"
                    >
                      补销售规则/R1-R5
                    </Link>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="space-y-6">
          {matrix ? (
            <>
              {purchaseDecision ? (
                <div className="overflow-hidden rounded-2xl bg-gradient-to-br from-slate-950 via-slate-900 to-blue-950 p-6 text-white shadow-xl" data-testid="comparison-purchase-decision">
                  <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                    <div className="max-w-3xl">
                      <div className="inline-flex rounded-full bg-white/10 px-3 py-1 text-xs text-blue-100 ring-1 ring-white/10">
                        研究选择结论 · {profileLabels[profile]} · {horizonLabels[horizon]} · {purchasePlanLabels[purchasePlan]}
                      </div>
                      <h2 className="mt-4 text-2xl font-bold">
                        优先核查：{purchaseDecision.primaryFund?.name || '待生成'}
                      </h2>
                      <p className="mt-3 text-sm leading-6 text-slate-200">
                        {purchaseDecision.conclusion}
                      </p>
                      <div className="mt-4 flex flex-wrap gap-2 text-xs">
                        <span className="rounded-full bg-emerald-400/15 px-3 py-1 text-emerald-100 ring-1 ring-emerald-300/20">
                          依据：{purchaseDecision.basisLabel}
                        </span>
                        {purchaseDecision.primaryReturn != null ? (
                          <span className="rounded-full bg-white/10 px-3 py-1 text-slate-100">
                            回放收益 {formatPercent(purchaseDecision.primaryReturn)}
                          </span>
                        ) : null}
                        {purchaseDecision.primaryDrawdown != null ? (
                          <span className="rounded-full bg-white/10 px-3 py-1 text-slate-100">
                            回放回撤 {formatPercent(purchaseDecision.primaryDrawdown)}
                          </span>
                        ) : null}
                        {purchaseDecision.runnerUpFund ? (
                          <span className="rounded-full bg-white/10 px-3 py-1 text-slate-100">
                            备选：{purchaseDecision.runnerUpFund.name}
                          </span>
                        ) : null}
                        <span className="rounded-full bg-white/10 px-3 py-1 text-slate-100">
                          费用可比性 {purchaseDecision.feeComparableCount}/{purchaseDecision.totalCount}
                        </span>
                      </div>
                      {purchaseDecision.feeGapCount > 0 ? (
                        <div className="mt-4 rounded-xl bg-amber-300/10 px-4 py-3 text-sm leading-6 text-amber-100 ring-1 ring-amber-200/20">
                          费用边界：当前领先只代表历史净值回放或指标领先，不代表费用后真实领先；需补齐申购费、赎回费、销售服务费等证据后再确认。
                        </div>
                      ) : null}
                    </div>
                    <div className="min-w-64 rounded-2xl bg-white/10 p-4 ring-1 ring-white/10">
                      <div className="text-sm font-semibold text-white">研究复核闸门</div>
                      <div className="mt-3 grid grid-cols-2 gap-3 text-center">
                        <div className="rounded-xl bg-white/10 px-3 py-3">
                          <div className="text-2xl font-bold">{purchaseDecision.verifyCount}</div>
                          <div className="mt-1 text-xs text-slate-300">待补证</div>
                        </div>
                        <div className="rounded-xl bg-white/10 px-3 py-3">
                          <div className="text-2xl font-bold">{purchaseDecision.blockedCount}</div>
                          <div className="mt-1 text-xs text-slate-300">阻断</div>
                        </div>
                        <div className="rounded-xl bg-white/10 px-3 py-3">
                          <div className="text-2xl font-bold">{purchaseDecision.salesHardGapCount}</div>
                          <div className="mt-1 text-xs text-slate-300">销售硬缺口</div>
                        </div>
                        <div className="rounded-xl bg-white/10 px-3 py-3">
                          <div className="text-2xl font-bold">{purchaseDecision.feeGapCount}</div>
                          <div className="mt-1 text-xs text-slate-300">费用缺口</div>
                        </div>
                        <div className="rounded-xl bg-white/10 px-3 py-3">
                          <div className="text-2xl font-bold">{purchaseDecision.shareClassFundCount}</div>
                          <div className="mt-1 text-xs text-slate-300">多份额样本</div>
                        </div>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <Link href={salesRuleGroupActionHref} className="rounded-lg bg-cyan-300 px-3 py-2 text-xs font-semibold text-slate-950 hover:bg-cyan-200">
                          {activeSalesRuleReviewGaps.length ? '处理复查队列' : '补销售规则'}
                        </Link>
                        <button
                          type="button"
                          onClick={() => void runPurchaseSimulationCompare()}
                          disabled={simulationLoading}
                          className="rounded-lg border border-white/20 px-3 py-2 text-xs font-semibold text-white hover:bg-white/10 disabled:opacity-50"
                        >
                          {simulationLoading ? '回放中...' : '重跑回放'}
                        </button>
                      </div>
                    </div>
                  </div>
                  <div className="mt-5 grid gap-2 md:grid-cols-2">
                    {purchaseDecision.nextChecks.map((item) => (
                      <div key={item} className="rounded-xl bg-white/10 px-4 py-3 text-sm leading-6 text-slate-100 ring-1 ring-white/10">
                        {item}
                      </div>
                    ))}
                  </div>
                  {decisionExplanation ? (
                    <div className="mt-5 rounded-2xl bg-white/10 p-4 ring-1 ring-white/10" data-testid="comparison-decision-explanation">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <div className="text-sm font-semibold text-white">为什么这样排序</div>
                          <p className="mt-1 text-xs leading-5 text-slate-300">{decisionExplanation.conclusion}</p>
                        </div>
                        <div className="rounded-xl bg-white/10 px-3 py-2 text-xs text-slate-100">
                          {decisionExplanation.runner
                            ? `分差 ${decisionExplanation.scoreGap} · 对比 ${decisionExplanation.runner.fund.name}`
                            : '单样本 · 建议补充同类基金'}
                        </div>
                      </div>
                      <div className="mt-3 grid gap-2 md:grid-cols-2">
                        {decisionExplanation.reasons.slice(0, 6).map((reason) => (
                          <div key={reason} className="rounded-xl bg-slate-950/30 px-3 py-2 text-xs leading-5 text-slate-100 ring-1 ring-white/10">
                            {reason}
                          </div>
                        ))}
                      </div>
                      {decisionExplanation.recheckTriggers.length ? (
                        <div className="mt-4 rounded-2xl bg-amber-300/10 p-4 ring-1 ring-amber-200/20" data-testid="comparison-decision-recheck-triggers">
                          <div className="text-sm font-semibold text-amber-100">什么情况下结论会改变</div>
                          <div className="mt-3 grid gap-2 md:grid-cols-2">
                            {decisionExplanation.recheckTriggers.slice(0, 6).map((trigger) => (
                              <div key={trigger} className="rounded-xl bg-slate-950/30 px-3 py-2 text-xs leading-5 text-amber-50 ring-1 ring-white/10">
                                {trigger}
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  <div className="mt-5 rounded-2xl bg-white/10 p-4 ring-1 ring-white/10" data-testid="comparison-sales-rule-gaps">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-white">销售规则硬缺口</div>
                        <div className="mt-1 text-xs text-slate-300">
                          {salesGapLoading
                            ? '正在读取本地销售规则表...'
                            : salesGapPayload
                              ? `当前对比 ${salesGapPayload.totalMembers} 只，${salesGapPayload.gapCount} 只仍缺必核销售证据 · ${salesGapPayload.source}`
                              : salesGapError || '尚未读取销售规则缺口'}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {foundationFillableCodes.length ? (
                          <button
                            type="button"
                            onClick={() => void importTushareFoundationForComparison()}
                            disabled={foundationHydrating || salesGapLoading}
                            className="rounded-lg border border-cyan-200 bg-white/10 px-3 py-2 text-xs font-semibold text-cyan-100 hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-50"
                            title={`只导入 Tushare fund_basic 的申购/赎回起始状态和来源日期，不会补${foundationManualFields}。`}
                          >
                            {foundationHydrating ? '导入中...' : `先导入基础状态（${foundationFillableCodes.length}）`}
                          </button>
                        ) : null}
                        <Link href={salesRuleGroupActionHref} className="rounded-lg bg-cyan-300 px-3 py-2 text-xs font-semibold text-slate-950 hover:bg-cyan-200">
                          {activeSalesRuleReviewGaps.length ? '打开复查队列' : '打开补证工作台'}
                        </Link>
                      </div>
                    </div>
                    {salesGapPayload?.gaps.length ? (
                      <div className="mt-3 grid gap-2 md:grid-cols-2">
                        {salesGapPayload.gaps.slice(0, 4).map((gap) => (
                          <div key={gap.windCode} className="rounded-xl bg-slate-950/40 px-3 py-2 text-xs leading-5 text-slate-100 ring-1 ring-white/10">
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-semibold">{gap.fundName}</span>
                              <span className="font-mono text-slate-300">{gap.windCode}</span>
                            </div>
                            <div className="mt-1 text-amber-100">
                              缺 {gap.missingCount} 项：{gap.missingItems.slice(0, 4).join('、')}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {comparisonHealthCheck ? (
                <div className="overflow-hidden rounded-2xl border border-violet-100 bg-white shadow" data-testid="comparison-buy-before-health-check">
                  <div className="flex flex-col gap-4 border-b border-violet-100 bg-violet-950 px-5 py-4 text-white lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs text-violet-100 ring-1 ring-white/10">
                        <ClipboardCheck className="h-3.5 w-3.5" />
                        横评研究复核体检
                      </div>
                      <h2 className="mt-3 text-xl font-semibold">{comparisonHealthCheck.headline}</h2>
                      <p className="mt-2 max-w-4xl text-sm leading-6 text-violet-100">{comparisonHealthCheck.summary}</p>
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2">
                      {comparisonHealthCheck.primaryActionKind === 'sales_rules' ? (
                        <Link href={salesRuleGroupActionHref} className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-violet-950 hover:bg-violet-50">
                          {activeSalesRuleReviewGaps.length ? '处理复查队列' : '补销售规则/R1-R5'}
                        </Link>
                      ) : comparisonHealthCheck.primaryActionKind === 'simulation' ? (
                        <button
                          type="button"
                          onClick={() => void runPurchaseSimulationCompare()}
                          disabled={simulationLoading}
                          className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-violet-950 hover:bg-violet-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {simulationLoading ? '回放中...' : '重跑持有体验回放'}
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void saveComparisonReport()}
                          className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-violet-950 hover:bg-violet-50"
                        >
                          保存横评报告
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="grid gap-3 bg-violet-50/60 p-4 md:grid-cols-4">
                    <div className="rounded-2xl bg-white px-4 py-3 ring-1 ring-violet-100">
                      <div className="text-xs text-slate-500">正式可比样本</div>
                      <div className="mt-1 text-2xl font-bold text-violet-950">{comparisonHealthCheck.formalReadyCount}</div>
                    </div>
                    <div className="rounded-2xl bg-white px-4 py-3 ring-1 ring-emerald-100">
                      <div className="text-xs text-slate-500">已通过项</div>
                      <div className="mt-1 text-2xl font-bold text-emerald-700">{comparisonHealthCheck.doneCount}</div>
                    </div>
                    <div className="rounded-2xl bg-white px-4 py-3 ring-1 ring-amber-100">
                      <div className="text-xs text-slate-500">待补项</div>
                      <div className="mt-1 text-2xl font-bold text-amber-700">{comparisonHealthCheck.verifyCount}</div>
                    </div>
                    <div className="rounded-2xl bg-white px-4 py-3 ring-1 ring-rose-100">
                      <div className="text-xs text-slate-500">硬阻断项</div>
                      <div className="mt-1 text-2xl font-bold text-rose-700">{comparisonHealthCheck.blockedCount}</div>
                    </div>
                  </div>
                  <div className="grid gap-3 p-5 md:grid-cols-2 xl:grid-cols-4">
                    {comparisonHealthCheck.lanes.map((lane) => {
                      const laneClassName = lane.status === 'done'
                        ? 'border-emerald-100 bg-emerald-50 text-emerald-950'
                        : lane.status === 'blocked'
                          ? 'border-rose-100 bg-rose-50 text-rose-950'
                          : 'border-amber-100 bg-amber-50 text-amber-950'
                      return (
                        <div key={lane.title} className={`rounded-2xl border p-4 ${laneClassName}`}>
                          <div className="flex items-start justify-between gap-2">
                            <div className="text-sm font-semibold">{lane.title}</div>
                            <span className="rounded-full bg-white/80 px-2 py-0.5 text-[11px] font-semibold ring-1 ring-black/5">
                              {lane.status === 'done' ? '已过' : lane.status === 'blocked' ? '阻断' : '待补'}
                            </span>
                          </div>
                          <div className="mt-3 text-base font-semibold">{lane.label}</div>
                          <p className="mt-2 text-xs leading-5 opacity-80">{lane.detail}</p>
                        </div>
                      )
                    })}
                  </div>
                  <div className="border-t border-violet-100 bg-violet-50 px-5 py-3 text-xs leading-5 text-violet-900">
                    边界：横评第一名只是研究优先样本；销售规则、R1-R5 来源、费用可比性或真实净值回放缺失时，不保存为正式研究结论，也不输出申赎操作指令。
                  </div>
                </div>
              ) : null}

              {leaderInvestorFourQuestions ? (
                <div className="overflow-hidden rounded-2xl border border-emerald-100 bg-white shadow" data-testid="comparison-leader-four-questions">
                  <div className="flex flex-col gap-4 border-b border-emerald-100 bg-emerald-950 px-5 py-4 text-white lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <div className="inline-flex rounded-full bg-white/10 px-3 py-1 text-xs text-emerald-100 ring-1 ring-white/10">
                        第一名研究复核四问
                      </div>
                      <h2 className="mt-3 text-xl font-semibold">{leaderInvestorFourQuestions.verdict}</h2>
                      <p className="mt-2 max-w-4xl text-sm leading-6 text-emerald-100">
                        横评结束后先回答研究员最关心的四件事：能不能继续研究、为什么它领先、这笔金额是否可执行、回撤压力能不能承受。
                      </p>
                    </div>
                    <Link
                      href={leaderInvestorFourQuestions.primaryHref}
                      className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-emerald-950 hover:bg-emerald-50"
                    >
                      {leaderInvestorFourQuestions.primaryActionLabel}
                    </Link>
                  </div>
                  <div className="grid gap-3 p-5 md:grid-cols-2">
                    {leaderInvestorFourQuestions.questions.map((item, index) => (
                      <div key={item.key} className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="text-sm font-semibold text-emerald-950">{index + 1}. {item.question}</div>
                          <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-100">
                            研究复核
                          </span>
                        </div>
                        <div className="mt-3 text-sm leading-6 text-slate-900">{item.answer}</div>
                        <div className="mt-2 rounded-xl bg-white px-3 py-2 text-xs leading-5 text-slate-700 ring-1 ring-emerald-100">
                          证据：{item.evidence}
                        </div>
                        <div className="mt-2 text-xs leading-5 text-emerald-800">下一步：{item.nextAction}</div>
                      </div>
                    ))}
                  </div>
                  <div className="border-t border-emerald-100 bg-emerald-50 px-5 py-3 text-xs leading-5 text-emerald-900">
                    硬边界：{leaderInvestorFourQuestions.boundary}
                  </div>
                </div>
              ) : null}

              {buyForwardQueue ? (
                <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow" data-testid="comparison-buy-forward-queue">
                  <div className="border-b border-slate-100 bg-slate-950 px-5 py-4 text-white">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="inline-flex rounded-full bg-white/10 px-3 py-1 text-xs text-slate-100 ring-1 ring-white/10">
                          横评研究推进队列
                        </div>
                        <h2 className="mt-3 text-xl font-semibold">从“谁分高”落到“下一步处理谁”</h2>
                        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">
                          {buyForwardQueue.summary} 这里仍然只做基金研究和研究复核，不输出申赎操作指令。
                        </p>
                      </div>
                      <div className="rounded-2xl bg-white/10 px-4 py-3 text-xs leading-5 text-slate-100 ring-1 ring-white/10">
                        正式候选必须同时满足：无销售硬缺口、无申赎阻断、费用可比、研究必补清零、真实净值回放已跑。
                      </div>
                    </div>
                  </div>
                  <div className="grid gap-4 p-5 lg:grid-cols-3">
                    <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4">
                      <div className="text-sm font-semibold text-emerald-950">可推进研究</div>
                      <div className="mt-1 text-xs leading-5 text-emerald-800">不是可执行，只是可以进入研究复核报告和观察池留痕。</div>
                      <div className="mt-3 space-y-2">
                        {buyForwardQueue.ready.length ? buyForwardQueue.ready.map((item) => (
                          <div key={`ready-${item.windCode}`} className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-emerald-900 ring-1 ring-emerald-100">
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-semibold">{item.fund.name}</span>
                              <span className="font-mono text-emerald-700">{item.score}</span>
                            </div>
                            <div className="mt-1">{item.nextAction}</div>
                            <Link href={fundDetailHref(item.fund)} className="mt-2 inline-flex rounded-lg bg-emerald-600 px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-700">
                              打开研究复核一页纸
                            </Link>
                          </div>
                        )) : (
                          <div className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-emerald-900 ring-1 ring-emerald-100">
                            当前没有样本满足正式推进条件。
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-rose-100 bg-rose-50 p-4">
                      <div className="text-sm font-semibold text-rose-950">先补证阻断</div>
                      <div className="mt-1 text-xs leading-5 text-rose-800">这些阻断项优先级高于收益排名和专业评分。</div>
                      <div className="mt-3 space-y-2">
                        {buyForwardQueue.blocked.map((item) => (
                          <div key={`blocked-${item.windCode}`} className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-rose-900 ring-1 ring-rose-100">
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-semibold">{item.fund.name}</span>
                              <span className="font-mono text-rose-700">{item.windCode}</span>
                            </div>
                            <div className="mt-1">{buyForwardQueue.blockerText(item)}</div>
                            <Link href={item.salesGap ? salesRuleActionHrefForGap(item.salesGap, item.windCode) : fundDetailHref(item.fund)} className="mt-2 inline-flex rounded-lg bg-white px-2.5 py-1.5 text-[11px] font-semibold text-rose-700 ring-1 ring-rose-100 hover:bg-rose-50">
                              {item.salesGap?.alertsHref ? '开复查队列' : item.salesGap ? '补销售规则' : '补研究证据'}
                            </Link>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-amber-100 bg-amber-50 p-4">
                      <div className="text-sm font-semibold text-amber-950">排序反转条件</div>
                      <div className="mt-1 text-xs leading-5 text-amber-800">分差小、证据缺或回放缺时，不要把当前排名当成结论。</div>
                      <div className="mt-3 space-y-2">
                        {buyForwardQueue.reversal.length ? buyForwardQueue.reversal.map((item) => (
                          <div key={`reversal-${item.windCode}`} className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-amber-900 ring-1 ring-amber-100">
                            <div className="font-semibold">{item.fund.name}</div>
                            <div className="mt-1">
                              距第一名 {Math.max(0, (decisionScores[0]?.score ?? item.score) - item.score)} 分；{buyForwardQueue.blockerText(item)}
                            </div>
                          </div>
                        )) : (
                          <div className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-amber-900 ring-1 ring-amber-100">
                            暂无接近反转样本；继续扩大同类样本和回放窗口。
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="border-t border-slate-100 bg-slate-50 px-5 py-4" data-testid="comparison-actionable-evidence-queue">
                    <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                      <div>
                        <div className="text-sm font-semibold text-slate-950">字段级补证清单</div>
                        <div className="mt-1 text-xs leading-5 text-slate-600">
                          按硬阻断优先级排序：申赎状态、销售规则、R1-R5来源背书、费用证据和真实净值回放先于收益排名。
                        </div>
                      </div>
                      <Link href={salesRuleGroupActionHref} className="inline-flex rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800">
                        {activeSalesRuleReviewGaps.length ? `处理复查队列 · ${activeSalesRuleReviewGaps.length}` : '打开整组补证工作台'}
                      </Link>
                    </div>
                    <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                      {buyForwardQueue.actionTasks.length ? buyForwardQueue.actionTasks.map((task, index) => (
                        <div key={`${task.kind}-${task.windCode}-${index}`} className="rounded-xl bg-white px-3 py-3 text-xs leading-5 text-slate-700 ring-1 ring-slate-200">
                          <div className="flex items-center justify-between gap-2">
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 font-semibold text-slate-700">P{index + 1}</span>
                            <span className="font-mono text-slate-400">{task.windCode}</span>
                          </div>
                          <div className="mt-2 font-semibold text-slate-950">{task.fund.name}</div>
                          <div className="mt-1 font-semibold text-slate-700">{task.title}</div>
                          <div className="mt-1 text-slate-500">{task.detail}</div>
                          {task.kind === 'simulation' ? (
                            <button
                              type="button"
                              onClick={() => void runPurchaseSimulationCompare()}
                              disabled={simulationLoading || !matrix.funds.length}
                              className="mt-2 inline-flex rounded-lg bg-emerald-50 px-2.5 py-1.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-100 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {simulationLoading ? '回放中...' : task.cta}
                            </button>
                          ) : (
                            <Link
                              href={(() => {
                                const taskSalesGap = salesGapByCode.get(task.windCode.toUpperCase())
                                return task.kind === 'sales_rule' || (task.kind === 'fee' && taskSalesGap)
                                  ? salesRuleActionHrefForGap(taskSalesGap, task.windCode)
                                  : fundDetailHref(task.fund)
                              })()}
                              className="mt-2 inline-flex rounded-lg bg-white px-2.5 py-1.5 text-[11px] font-semibold text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50"
                            >
                              {task.cta}
                            </Link>
                          )}
                        </div>
                      )) : (
                        <div className="rounded-xl bg-white px-3 py-3 text-xs leading-5 text-slate-600 ring-1 ring-slate-200">
                          当前没有字段级补证任务；可进入研究复核一页纸做最终复核。
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ) : null}

              {decisionScores.length ? (
                <div className="overflow-hidden rounded-2xl bg-white shadow" data-testid="comparison-decision-scorecard">
                  <div className="border-b border-gray-100 px-5 py-4">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div>
                        <h2 className="text-lg font-semibold text-gray-900">研究决策评分卡</h2>
                        <p className="mt-1 text-sm leading-6 text-gray-500">
                          综合专业评分、证据完整度、持有体验回放、回撤舒适度、压力体验、费用可比性和销售规则硬缺口；销售规则缺失会直接压低评分并阻断研究路径。
                        </p>
                      </div>
                      <div className="rounded-xl bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600">
                        分数是研究排序，不是申赎操作指令；正式研究复核仍需销售平台适当性、申赎状态和费率确认。
                      </div>
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-100">
                      <thead className="bg-gray-50">
                        <tr className="text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                          <th className="px-5 py-3">排序</th>
                          <th className="px-5 py-3">基金</th>
                          <th className="px-5 py-3">决策分</th>
                          <th className="px-5 py-3">研究门禁</th>
                          <th className="px-5 py-3">回放体验</th>
                          <th className="px-5 py-3">评分依据</th>
                          <th className="px-5 py-3">下一步</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100 bg-white">
                        {decisionScores.map((item, index) => (
                          <tr key={`decision-score-${item.windCode}`} className="align-top hover:bg-gray-50">
                            <td className="px-5 py-4">
                              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-sm font-bold text-slate-700">
                                {index + 1}
                              </div>
                            </td>
                            <td className="px-5 py-4">
                              <Link href={fundDetailHref(item.fund)} className="font-semibold text-gray-900 hover:text-blue-700">
                                {item.fund.name}
                              </Link>
                              <div className="mt-1 font-mono text-xs text-gray-500">{item.windCode}</div>
                              <div className="mt-2 text-xs text-gray-500">{item.fund.type || item.fund.peer_group || '类型待补'}</div>
                            </td>
                            <td className="px-5 py-4">
                              <div className="text-2xl font-bold text-gray-900">{item.score}</div>
                              <span className={`mt-2 inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${decisionToneClass(item.tone)}`}>
                                {item.label}
                              </span>
                              <div className="mt-3 space-y-1.5" data-testid="comparison-decision-score-breakdown">
                                <div className="text-[11px] font-semibold text-gray-400">决策分拆解</div>
                                {item.breakdown.map((part) => {
                                  const width = Math.max(4, Math.min(100, part.rawScore))
                                  return (
                                    <div key={`${item.windCode}-${part.key}`} title={part.note}>
                                      <div className="mb-0.5 flex items-center justify-between gap-2 text-[11px] text-gray-500">
                                        <span>{part.label}</span>
                                        <span>+{part.contribution.toFixed(1)}</span>
                                      </div>
                                      <div className="h-1.5 rounded-full bg-gray-100">
                                        <div className="h-1.5 rounded-full bg-violet-500" style={{ width: `${width}%` }} />
                                      </div>
                                    </div>
                                  )
                                })}
                                {item.scoreCaps.length ? (
                                  <div className="rounded-lg bg-amber-50 px-2 py-1 text-[11px] leading-4 text-amber-700">
                                    封顶：{item.scoreCaps.slice(0, 2).join('；')}
                                  </div>
                                ) : null}
                              </div>
                            </td>
                            <td className="px-5 py-4">
                              <div className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${decisionToneClass(item.tone)}`}>
                                {item.gateLabel}
                              </div>
                              <div className="mt-2 max-w-xs text-xs leading-5 text-gray-500">
                                {item.gateDetail}
                              </div>
                              <div
                                className={`mt-2 max-w-xs rounded-lg px-2 py-1 text-xs leading-5 ${
                                  executionAmountGateByCode.get(item.windCode.toUpperCase())?.status === 'blocked'
                                    ? 'bg-rose-50 text-rose-800'
                                    : executionAmountGateByCode.get(item.windCode.toUpperCase())?.status === 'pass'
                                      ? 'bg-emerald-50 text-emerald-800'
                                      : 'bg-amber-50 text-amber-800'
                                }`}
                                data-testid="comparison-execution-amount-gate"
                              >
                                金额门禁：{executionAmountGateByCode.get(item.windCode.toUpperCase())?.label || '金额门槛待扫描'}
                              </div>
                            </td>
	                            <td className="px-5 py-4 text-sm text-gray-700">
	                              <div>{purchasePlanLabels[purchasePlan]}收益 {formatPercent(item.simulationReturn)}</div>
	                              <div className="mt-1 text-xs text-rose-700">回撤 {formatPercent(item.simulationDrawdown)}</div>
	                              <div className="mt-2 rounded-lg bg-rose-50 px-2 py-1 text-xs leading-5 text-rose-800" data-testid="comparison-stress-experience-cell">
	                                压力体验 {item.stressScore ?? '待跑'} 分
	                                {item.longestUnderwaterDays !== null ? ` · 最长亏损等待 ${Math.round(item.longestUnderwaterDays)} 天` : ''}
	                                {item.worstThreeMonthReturn !== null ? ` · 最差三个月 ${formatPercent(item.worstThreeMonthReturn)}` : ''}
	                              </div>
	                              {!simulationResults.length ? (
                                <button
                                  type="button"
                                  onClick={() => void runPurchaseSimulationCompare()}
                                  disabled={simulationLoading}
                                  className="mt-2 rounded-lg bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 ring-1 ring-emerald-100 hover:bg-emerald-100 disabled:opacity-50"
                                >
                                  {simulationLoading ? '回放中...' : '先跑回放'}
                                </button>
                              ) : null}
                            </td>
                            <td className="px-5 py-4">
                              <div className="max-w-sm space-y-1 text-xs leading-5 text-gray-600">
                                {item.reasons.slice(0, 5).map((reason) => (
                                  <div key={`${item.windCode}-${reason}`}>• {reason}</div>
                                ))}
                              </div>
                            </td>
                            <td className="px-5 py-4">
                              <div className="max-w-xs text-sm leading-6 text-gray-700">{item.nextAction}</div>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {item.salesGap ? (
                                  <Link href={salesRuleActionHrefForGap(item.salesGap, item.windCode)} className="rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800 ring-1 ring-amber-100 hover:bg-amber-100">
                                    {item.salesGap.alertsHref ? '开复查队列' : '补销售规则'}
                                  </Link>
                                ) : (
                                  <button
                                    type="button"
                                    onClick={() => void addComparisonFundToPool(item.fund)}
                                    disabled={addingFundCode === item.windCode || salesGapLoading || !salesGapPayload || item.fund.operation_status?.status === 'blocked' || !item.fund.id}
                                    className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-gray-300"
                                  >
                                    {addingFundCode === item.windCode
                                      ? '加入中...'
                                      : salesGapLoading || !salesGapPayload
                                        ? '扫描规则后入池'
                                        : '加入观察池'}
                                  </button>
                                )}
                                <Link href={fundDetailHref(item.fund)} className="rounded-lg border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50">
                                  研究复核一页纸
                                </Link>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}

              {decisionExplanation ? (
                <div className="overflow-hidden rounded-2xl border border-cyan-100 bg-white shadow" data-testid="comparison-decisive-edge-card">
                  <div className="border-b border-cyan-100 bg-cyan-950 px-5 py-4 text-white">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <div className="inline-flex rounded-full bg-white/10 px-3 py-1 text-xs text-cyan-100 ring-1 ring-white/10">
                          横评胜负手与淘汰线
                        </div>
                        <h2 className="mt-3 text-xl font-semibold">为什么它暂时领先，谁被先排除</h2>
                        <p className="mt-2 max-w-3xl text-sm leading-6 text-cyan-100">
                          把研究决策评分拆成研究员能复核的判断：胜负手、淘汰线、下一步补证动作。这里仍然不是申赎操作指令。
                        </p>
                      </div>
                      <div className="rounded-2xl bg-white/10 px-4 py-3 text-sm ring-1 ring-white/10">
                        <div className="text-xs text-cyan-200">当前横评结论</div>
                        <div className="mt-1 max-w-md leading-6 text-white">{decisionExplanation.conclusion}</div>
                      </div>
                    </div>
                  </div>
                  <div className="grid gap-4 p-5 lg:grid-cols-3">
                    <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4">
                      <div className="text-sm font-semibold text-emerald-950">胜负手</div>
                      <div className="mt-1 text-xs leading-5 text-emerald-800">解释领先样本靠什么暂时胜出，而不是只给一个总分。</div>
                      <div className="mt-3 space-y-2">
                        {decisionExplanation.decisiveEdges.slice(0, 5).map((item) => (
                          <div key={item} className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-emerald-900 ring-1 ring-emerald-100">
                            {item}
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-rose-100 bg-rose-50 p-4">
                      <div className="text-sm font-semibold text-rose-950">淘汰线</div>
                      <div className="mt-1 text-xs leading-5 text-rose-800">销售规则、申赎状态、费用不可比会先于收益排名触发排除。</div>
                      <div className="mt-3 space-y-2">
                        {decisionExplanation.knockoutLines.length ? decisionExplanation.knockoutLines.slice(0, 5).map((item) => (
                          <div key={item} className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-rose-900 ring-1 ring-rose-100">
                            {item}
                          </div>
                        )) : (
                          <div className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-rose-900 ring-1 ring-rose-100">
                            暂无明确淘汰样本；继续补充同类基金和持有体验回放。
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-amber-100 bg-amber-50 p-4">
                      <div className="text-sm font-semibold text-amber-950">下一步补证</div>
                      <div className="mt-1 text-xs leading-5 text-amber-800">把横评结论转成研究动作，避免“看完对比不知道该做什么”。</div>
                      <div className="mt-3 space-y-2">
                        {decisionExplanation.nextActions.slice(0, 5).map((item) => (
                          <div key={item} className="rounded-xl bg-white px-3 py-2 text-xs leading-5 text-amber-900 ring-1 ring-amber-100">
                            {item}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="border-t border-cyan-50 px-5 py-4" data-testid="comparison-decisive-confidence-audit">
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Decisive confidence audit</div>
                          <div className="mt-1 text-lg font-semibold text-slate-950">{decisionExplanation.decisiveAudit.title}</div>
                          <p className="mt-2 text-sm leading-6 text-slate-600">
                            当前置信度：{decisionExplanation.decisiveAudit.confidence}；
                            通过 {decisionExplanation.decisiveAudit.passCount}/{decisionExplanation.decisiveAudit.totalCount} 条胜负线。
                          </p>
                        </div>
                        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
                          不输出申赎操作指令
                        </span>
                      </div>
                      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        {(decisionExplanation.decisiveAudit.items.length ? decisionExplanation.decisiveAudit.items : [{
                          label: '样本不足',
                          passed: false,
                          detail: '至少需要两只同类候选才能判断第一名是否真的胜出。',
                        }]).map((item) => (
                          <div key={item.label} className={`rounded-xl border p-3 text-xs leading-5 ${
                            item.passed
                              ? 'border-emerald-100 bg-white text-emerald-900'
                              : 'border-amber-100 bg-white text-amber-900'
                          }`}>
                            <div className="flex items-start justify-between gap-2">
                              <div className="font-semibold">{item.label}</div>
                              <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                                item.passed ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                              }`}>
                                {item.passed ? '通过' : '待复核'}
                              </span>
                            </div>
                            <div className="mt-2">{item.detail}</div>
                          </div>
                        ))}
                      </div>
                      <div className="mt-3 rounded-xl bg-slate-950 px-3 py-2 text-xs leading-5 text-white/90">
                        {decisionExplanation.decisiveAudit.boundary}
                      </div>
                    </div>
                  </div>
                  {decisionExplanation.pairwiseDeltas.length ? (
                    <div className="border-t border-cyan-50 px-5 py-4" data-testid="comparison-pairwise-pk-deltas">
                      <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
                        <div>
                          <div className="text-sm font-semibold text-slate-950">一对一 PK 差异</div>
                          <p className="mt-1 text-xs leading-5 text-slate-500">
                            逐项比较第一名和第二名，标出可能反转或不能直接采信的指标；领先项只解释研究排序，不构成研究建议。
                          </p>
                        </div>
                        <div className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-semibold text-cyan-800">
                          {decisionExplanation.leader.fund.name} vs {decisionExplanation.runner?.fund.name}
                        </div>
                      </div>
                      <div className="mt-3 overflow-x-auto rounded-2xl border border-slate-200">
                        <table className="min-w-full divide-y divide-slate-200 text-sm">
                          <thead className="bg-slate-50 text-xs text-slate-500">
                            <tr>
                              <th className="px-4 py-2 text-left font-semibold">指标</th>
                              <th className="px-4 py-2 text-left font-semibold">第一名</th>
                              <th className="px-4 py-2 text-left font-semibold">第二名</th>
                              <th className="px-4 py-2 text-left font-semibold">差异</th>
                              <th className="px-4 py-2 text-left font-semibold">研究解释</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100 bg-white">
                            {decisionExplanation.pairwiseDeltas.map((item) => (
                              <tr key={item.metric}>
                                <td className="px-4 py-3 font-medium text-slate-900">{item.metric}</td>
                                <td className="px-4 py-3 text-slate-700">{item.leaderValue}</td>
                                <td className="px-4 py-3 text-slate-700">{item.runnerValue}</td>
                                <td className="px-4 py-3 text-slate-700">{item.edge}</td>
                                <td className="px-4 py-3 text-xs leading-5 text-slate-600">{item.verdict}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : null}
                  <div className="border-t border-cyan-50 bg-slate-50 px-5 py-4">
                    <div className="flex flex-wrap gap-2">
                      {decisionExplanation.leader.salesGap ? (
                        <Link href={salesRuleActionHrefForGap(decisionExplanation.leader.salesGap, decisionExplanation.leader.windCode)} className="rounded-lg bg-amber-600 px-3 py-2 text-xs font-semibold text-white hover:bg-amber-700">
                          {decisionExplanation.leader.salesGap.alertsHref ? '处理领先样本复查队列' : '补领先样本销售规则'}
                        </Link>
                      ) : (
                        <Link href={fundDetailHref(decisionExplanation.leader.fund)} className="rounded-lg bg-cyan-700 px-3 py-2 text-xs font-semibold text-white hover:bg-cyan-800">
                          打开领先样本研究复核一页纸
                        </Link>
                      )}
                      {decisionExplanation.runner ? (
                        <Link href={fundDetailHref(decisionExplanation.runner.fund)} className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50">
                          复核第二名
                        </Link>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => void runPurchaseSimulationCompare()}
                        disabled={simulationLoading || !matrix.funds.length}
                        className="rounded-lg bg-white px-3 py-2 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {simulationLoading ? '回放中...' : '重跑持有体验回放'}
                      </button>
                    </div>
                    <div className="mt-3 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                      硬门禁：销售规则硬缺口、复查队列未清零、申赎阻断或费用不可比未处理前，横评只能作为研究排序，不能保存或沿用为正式研究结论。
                    </div>
                  </div>
                </div>
              ) : null}

              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {matrix.funds.map((fund) => {
                  const feeStatus = feeComparability(fund)
                  const salesGap = salesGapByCode.get(fund.wind_code.toUpperCase())
                  const shareClassInfo = shareClassInfoByCode.get(fund.wind_code.toUpperCase()) || fund.shareClassInfo || null
                  return (
                  <div key={fund.wind_code} className="rounded-2xl bg-white p-5 shadow">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <Link href={fundDetailHref(fund)} className="font-semibold text-gray-900 hover:text-blue-700">
                          {fund.name}
                        </Link>
                        <div className="mt-1 font-mono text-xs text-gray-500">{fund.wind_code}</div>
                      </div>
                      <div className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">
                        {fund.professional_grade || '-'}
                      </div>
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <div className="text-xs text-gray-400">专业评分</div>
                        <div className="mt-1 text-lg font-bold text-gray-900">{fund.professional_score?.toFixed?.(1) || '暂无'}</div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-400">同类样本</div>
                        <div className="mt-1 text-lg font-bold text-gray-900">{fund.peer_count || 0}</div>
                      </div>
                    </div>
                    <div className="mt-4 rounded-xl bg-gray-50 p-3 text-xs text-gray-600">
                      <div>{fund.peer_group || '待分类'}</div>
                      <div className="mt-1 text-gray-400">{fund.primary_benchmark || '待映射基准'}</div>
                    </div>
                    <div className="mt-3 rounded-xl border border-amber-100 bg-amber-50 p-3 text-xs text-amber-900">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-full px-2 py-1 font-semibold ${operationClass(fund.operation_status?.status)}`}>
                          {fund.operation_status?.label || '申购待核'}
                        </span>
                        <span className={`rounded-full px-2 py-1 font-semibold ${buyEvidenceClass(fund.buy_evidence?.completenessLevel)}`}>
                          研究证据 {fund.buy_evidence?.completenessScore ?? 0} · 必补 {fund.buy_evidence?.requiredMissingCount ?? '-'}
                        </span>
                        <span className="rounded-full bg-white px-2 py-1 text-amber-800">
                          管理费 {formatFee(fund.fee_info?.management_fee)}
                        </span>
                        <span className="rounded-full bg-white px-2 py-1 text-amber-800">
                          托管费 {formatFee(fund.fee_info?.custodian_fee)}
                        </span>
                        <span className={`rounded-full px-2 py-1 font-semibold ${feeStatus.comparable ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}`}>
                          费用可比性：{feeStatus.comparable ? '可初步横比' : '不可直接费后横比'}
                        </span>
                        <span className={`rounded-full px-2 py-1 font-semibold ${salesGap ? 'bg-rose-100 text-rose-800' : 'bg-emerald-100 text-emerald-800'}`}>
                          销售规则：{salesGap ? `缺 ${salesGap.missingCount} 项` : salesGapPayload ? '未见硬缺口' : '待读取'}
                        </span>
                        {shareClassInfo ? (
                          <span className="rounded-full bg-fuchsia-100 px-2 py-1 font-semibold text-fuchsia-800">
                            {shareClassInfo.classType}类 · 同基金 {shareClassInfo.siblingCount} 份额
                          </span>
                        ) : null}
                      </div>
                      <div className="mt-2 leading-5 text-amber-800">
                        申购起始：{fund.sales_status?.purchase_start_date || '待补'}；赎回起始：{fund.sales_status?.redeem_start_date || '待补'}
                      </div>
                      {!feeStatus.comparable ? (
                        <div className="mt-1 text-rose-700">费用边界：{feeStatus.reason}</div>
                      ) : null}
                      {fund.fee_info?.missing?.length ? (
                        <div className="mt-1 text-amber-700">待核：{fund.fee_info.missing.slice(0, 4).join('、')}</div>
                      ) : null}
                      {salesGap ? (
                        <div className="mt-1 text-rose-700">销售硬缺口：{salesGap.missingItems.slice(0, 4).join('、')}</div>
                      ) : null}
                      {shareClassInfo ? (
                        <div className="mt-1 text-fuchsia-700">同基金多份额：{shareClassInfo.hint}</div>
                      ) : null}
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void addComparisonFundToPool(fund)}
                        disabled={addingFundCode === fund.wind_code || salesGapLoading || !salesGapPayload || Boolean(salesGap) || fund.operation_status?.status === 'blocked' || !fund.id}
                        data-testid={`comparison-add-pool-${fund.wind_code}`}
                        className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-gray-300"
                      >
                        {salesGapLoading || !salesGapPayload
                          ? '扫描规则后入池'
                          : salesGap
                          ? '先补规则'
                          : fund.operation_status?.status === 'blocked'
                          ? '不可入池'
                          : addingFundCode === fund.wind_code
                            ? '加入中...'
                            : '加入观察池'}
                      </button>
                      <Link
                        href={fundDetailHref(fund)}
                        className="rounded-lg border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50"
                      >
                        研究复核一页纸
                      </Link>
                    </div>
	                  </div>
                  )
                })}
              </div>

              <div className="overflow-hidden rounded-2xl bg-white shadow">
                <div className="border-b border-gray-100 px-5 py-4">
                  <h2 className="text-lg font-semibold text-gray-900">研究复核横评</h2>
                  <p className="mt-1 text-sm text-gray-500">
                    对比基金是否具备继续研究的申赎状态、费用、申赎和研究证据；缺口不会被隐藏。
                  </p>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-100">
                    <thead className="bg-gray-50">
                      <tr className="text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        <th className="px-5 py-3">基金</th>
                        <th className="px-5 py-3">研究证据</th>
                        <th className="px-5 py-3">申购/赎回</th>
                        <th className="px-5 py-3">管理费/托管费</th>
                        <th className="px-5 py-3">费用可比性</th>
                        <th className="px-5 py-3">待补缺口</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 bg-white">
                      {matrix.funds.map((fund) => {
                        const evidenceScore = fund.buy_evidence?.completenessScore ?? 0
                        const feeStatus = feeComparability(fund)
                        const salesGap = salesGapByCode.get(fund.wind_code.toUpperCase())
                        const missingItems = Array.from(new Set([
                          ...feeStatus.missingItems,
                          ...(salesGap?.missingItems || []),
                        ]))
                        return (
                          <tr key={`buy-check-${fund.wind_code}`} className="align-top hover:bg-gray-50">
                            <td className="px-5 py-4">
                              <div className="font-semibold text-gray-900">{fund.name}</div>
                              <div className="mt-1 font-mono text-xs text-gray-500">{fund.wind_code}</div>
                            </td>
                            <td className="px-5 py-4">
                              <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${buyEvidenceClass(fund.buy_evidence?.completenessLevel)}`}>
                                {evidenceLabel(evidenceScore)} · {evidenceScore}
                              </span>
                              <div className="mt-2 max-w-xs text-xs leading-5 text-gray-500">
                                {fund.buy_evidence?.conclusion || '待生成研究证据结论'}
                              </div>
                            </td>
                            <td className="px-5 py-4 text-sm text-gray-700">
                              <div className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${operationClass(fund.operation_status?.status)}`}>
                                {fund.operation_status?.label || '申购待核'}
                              </div>
                              <div className="mt-2 text-xs leading-5 text-gray-500">
                                申购：{fund.sales_status?.purchase_start_date || '待补'}；赎回：{fund.sales_status?.redeem_start_date || '待补'}
                              </div>
                            </td>
                            <td className="px-5 py-4 text-sm text-gray-700">
                              <div>管理费 {formatFee(fund.fee_info?.management_fee)}</div>
                              <div className="mt-1">托管费 {formatFee(fund.fee_info?.custodian_fee)}</div>
                            </td>
                            <td className="px-5 py-4 text-sm text-gray-700">
                              <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${feeStatus.comparable ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}`}>
                                {feeStatus.comparable ? '可初步横比' : '不可直接费后横比'}
                              </span>
                              <div className="mt-2 max-w-xs text-xs leading-5 text-gray-500">
                                {feeStatus.reason}
                              </div>
                            </td>
                            <td className="px-5 py-4 text-sm text-amber-800">
                              {missingItems.length ? missingItems.slice(0, 5).join('、') : '暂无明显缺口'}
                              {salesGap ? (
                                <div className="mt-2 rounded-lg bg-rose-50 px-2 py-1 text-xs text-rose-700">
                                  销售规则硬缺口 {salesGap.missingCount} 项，补齐前不可入池或保存正式横评报告。
                                </div>
                              ) : null}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="overflow-hidden rounded-2xl bg-white shadow" data-testid="comparison-historical-nav-replay">
                <div className="border-b border-gray-100 px-5 py-4">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h2 className="text-lg font-semibold text-gray-900">历史持有体验横向回放</h2>
                      <p className="mt-1 text-sm text-gray-500">
                        对同一组基金用同样金额做真实净值回放，比较一次性投入、月度投入、最大回撤和月度胜率。
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <label className="text-xs text-gray-500">
                        期限（月）
                        <input
                          name="simulation_months"
                          type="number"
                          min={3}
                          max={60}
                          value={simulationMonths}
                          onChange={(event) => setSimulationMonths(Number(event.target.value) || 12)}
                          className="mt-1 block w-24 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900"
                        />
                      </label>
                      <label className="text-xs text-gray-500">
                        一次性金额
                        <input
                          name="simulation_lump_sum_amount"
                          type="number"
                          min={100}
                          step={100}
                          value={simulationLumpSumAmount}
                          onChange={(event) => setSimulationLumpSumAmount(Number(event.target.value) || 10000)}
                          className="mt-1 block w-28 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900"
                        />
                      </label>
                      <label className="text-xs text-gray-500">
                        月定投
                        <input
                          name="simulation_monthly_amount"
                          type="number"
                          min={10}
                          step={10}
                          value={simulationMonthlyAmount}
                          onChange={(event) => setSimulationMonthlyAmount(Number(event.target.value) || 1000)}
                          className="mt-1 block w-24 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900"
                        />
                      </label>
                      <button
                        type="button"
                        onClick={() => void runPurchaseSimulationCompare()}
                        disabled={simulationLoading || !matrix.funds.length}
                        data-testid="comparison-run-historical-nav-replay"
                        className="self-end rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-gray-300"
                      >
                        {simulationLoading ? '回放中...' : '回放持有体验'}
                      </button>
                    </div>
                  </div>
                  {simulationStatus ? (
                    <div className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                      {simulationStatus}
                    </div>
                  ) : null}
                </div>

                {simulationResults.length ? (
                  <div data-testid="comparison-historical-nav-replay-result">
                    <div className="grid gap-4 border-b border-gray-100 bg-slate-50 p-5 md:grid-cols-2">
                      <div className="rounded-2xl bg-white p-4 ring-1 ring-gray-100">
                        <div className="text-xs text-gray-500">一次性收益领先</div>
                        <div className="mt-2 text-lg font-semibold text-gray-900">{bestLumpSumResult?.name || '暂无'}</div>
                        <div className="mt-1 text-sm text-gray-500">
                          {bestLumpSumResult ? `${formatPercent(bestLumpSumResult.simulation.lumpSum.returnRate)}，最大回撤 ${formatPercent(bestLumpSumResult.simulation.lumpSum.maxDrawdown)}` : '样本不足'}
                        </div>
                      </div>
                      <div className="rounded-2xl bg-white p-4 ring-1 ring-gray-100">
                        <div className="text-xs text-gray-500">定投收益领先</div>
                        <div className="mt-2 text-lg font-semibold text-gray-900">{bestSipResult?.name || '暂无'}</div>
                        <div className="mt-1 text-sm text-gray-500">
                          {bestSipResult ? `${formatPercent(bestSipResult.simulation.sip.returnRate)}，账户回撤 ${formatPercent(bestSipResult.simulation.sip.maxAccountDrawdown)}` : '样本不足'}
                        </div>
                      </div>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-100">
                        <thead className="bg-gray-50">
                          <tr className="text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                            <th className="px-5 py-3">基金</th>
                            <th className="px-5 py-3">净值样本</th>
                            <th className="px-5 py-3">一次性配置假设</th>
                            <th className="px-5 py-3">每月定投</th>
	                            <th className="px-5 py-3">压力体验</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 bg-white">
                          {simulationResults.map((result) => (
                            <tr key={`simulation-${result.windCode}`} className="align-top hover:bg-gray-50">
                              <td className="px-5 py-4">
                                <div className="font-semibold text-gray-900">{result.name}</div>
                                <div className="mt-1 font-mono text-xs text-gray-500">{result.windCode}</div>
                              </td>
                              {result.status === 'ok' && result.simulation ? (
                                <>
                                  <td className="px-5 py-4 text-sm text-gray-700">
                                    <div>{result.simulation.period.startDate} 至 {result.simulation.period.endDate}</div>
                                    <div className="mt-1 text-xs text-gray-500">{result.simulation.period.observations} 条 · {result.simulation.source}</div>
                                  </td>
                                  <td className="px-5 py-4 text-sm text-gray-700">
                                    <div>收益 <b>{formatPercent(result.simulation.lumpSum.returnRate)}</b></div>
                                    <div className={result.simulation.lumpSum.profit >= 0 ? 'mt-1 text-emerald-700' : 'mt-1 text-rose-700'}>
                                      盈亏 {formatMoney(result.simulation.lumpSum.profit)}
                                    </div>
                                    {result.simulation.feeAdjusted?.lumpSum ? (
                                      <div className="mt-1 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
                                        费后 {formatPercent(result.simulation.feeAdjusted.lumpSum.returnRate)} · 费用 {formatMoney(result.simulation.feeAdjusted.lumpSum.totalFee)}
                                      </div>
                                    ) : null}
                                    <div className="mt-1 text-xs text-rose-700">最大回撤 {formatPercent(result.simulation.lumpSum.maxDrawdown)}</div>
                                  </td>
                                  <td className="px-5 py-4 text-sm text-gray-700">
                                    <div>收益 <b>{formatPercent(result.simulation.sip.returnRate)}</b></div>
                                    <div className={result.simulation.sip.profit >= 0 ? 'mt-1 text-emerald-700' : 'mt-1 text-rose-700'}>
                                      盈亏 {formatMoney(result.simulation.sip.profit)}
                                    </div>
                                    {result.simulation.feeAdjusted?.sip ? (
                                      <div className="mt-1 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
                                        费后 {formatPercent(result.simulation.feeAdjusted.sip.returnRate)} · 费用 {formatMoney(result.simulation.feeAdjusted.sip.totalFee)}
                                      </div>
                                    ) : null}
                                    <div className="mt-1 text-xs text-rose-700">账户回撤 {formatPercent(result.simulation.sip.maxAccountDrawdown)}</div>
                                    <div className="mt-1 text-xs text-gray-500">扣款 {result.simulation.sip.contributionCount} 次</div>
                                  </td>
	                                  <td className="px-5 py-4 text-sm text-gray-700">
	                                    <div>上涨月份 {result.simulation.monthlyExperience.positiveMonths}/{result.simulation.monthlyExperience.months}</div>
	                                    <div className="mt-1 text-xs text-gray-500">月度胜率 {formatPercent(result.simulation.monthlyExperience.positiveRatio)}</div>
	                                    {result.simulation.stressExperience ? (
	                                      <div className="mt-2 rounded-lg bg-rose-50 px-2 py-1 text-xs leading-5 text-rose-800" data-testid="comparison-simulation-stress-experience">
	                                        <div>{result.simulation.stressExperience.label} · {result.simulation.stressExperience.stressScore} 分</div>
	                                        <div>最长亏损等待 {Math.round(result.simulation.stressExperience.longestUnderwaterDays)} 天</div>
	                                        <div>最差三个月 {formatPercent(result.simulation.stressExperience.worstThreeMonthReturn?.returnRate ?? null)}</div>
	                                      </div>
	                                    ) : null}
	                                  </td>
                                </>
                              ) : (
                                <td className="px-5 py-4 text-sm text-amber-800" colSpan={4}>
                                  {result.error || '净值样本不足，无法回放'}
                                </td>
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="border-t border-gray-100 px-5 py-3 text-xs leading-5 text-gray-500">
	                      回放基于历史净值；若本地销售规则已录入申购/赎回费，会同步展示费用后粗估。压力体验用于识别最长亏损等待和最差三个月，不能只凭长期收益或评分进入研究候选。
                    </div>
                  </div>
                ) : (
                  <div className="p-8 text-center text-sm text-gray-500">
                    点击“回放持有体验”，系统会对当前对比基金逐只读取真实净值并计算持有体验。
                  </div>
                )}
              </div>

              <div className="overflow-hidden rounded-2xl bg-white shadow">
                <div className="border-b border-gray-100 px-5 py-4">
                  <h2 className="text-lg font-semibold text-gray-900">指标矩阵</h2>
                  <p className="mt-1 text-sm text-gray-500">每个单元格上方为原始值，下方为该基金在同类池中的分位。</p>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-100">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="sticky left-0 z-10 bg-gray-50 px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                          指标
                        </th>
                        {matrix.funds.map((fund) => (
                          <th key={fund.wind_code} className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                            {fund.name}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 bg-white">
                      {matrix.matrix_rows.map((row) => (
                        <tr key={row.metric_name} className="hover:bg-gray-50">
                          <td className="sticky left-0 z-10 bg-white px-5 py-4">
                            <div className="font-medium text-gray-900">{row.label}</div>
                            <div className="mt-1 text-xs text-gray-400">
                              {row.direction === 'higher' ? '越高越好' : '越低越好'}
                            </div>
                          </td>
                          {matrix.funds.map((fund) => {
                            const value = row.values[fund.wind_code]
                            const isBest = row.best_code === fund.wind_code
                            return (
                              <td key={`${row.metric_name}-${fund.wind_code}`} className="px-5 py-4">
                                <div className="flex items-center gap-2">
                                  <span className="text-sm font-semibold text-gray-900">{value?.display || '暂无'}</span>
                                  {isBest && <Trophy className="h-4 w-4 text-amber-500" />}
                                </div>
                                <div className={`mt-2 inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${percentileClass(value?.peer_percentile ?? null)}`}>
                                  同类分位 {value?.peer_percentile ?? '暂无'}
                                </div>
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="rounded-2xl bg-white p-6 shadow">
                <h2 className="text-lg font-semibold text-gray-900">对比结论</h2>
                <ul className="mt-4 space-y-3">
                  {matrix.recommendations.map((item) => (
                    <li key={item} className="flex gap-3 rounded-xl bg-slate-50 px-4 py-3 text-sm text-gray-700">
                      <ShieldCheck className="mt-0.5 h-4 w-4 flex-none text-slate-500" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-2xl bg-slate-950 p-6 text-white shadow-xl">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs text-slate-200 ring-1 ring-white/10">
                      <ClipboardCheck className="h-3.5 w-3.5" />
                      可复制研究产物
                    </div>
                    <h2 className="mt-3 text-lg font-semibold">研究比较备忘录</h2>
                    <p className="mt-1 text-sm leading-6 text-slate-300">
                      汇总对比基金、证据完整度、维度领先样本和必补缺口，可复制到研究记录或继续补销售规则。
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => void copyMemo()}
                      data-testid="comparison-copy-memo"
                      className="rounded-xl bg-white px-4 py-2 text-sm font-medium text-slate-950 hover:bg-slate-100"
                    >
                      复制备忘录
                    </button>
                    <button
                      type="button"
                      onClick={() => void copyComparisonDecisionTsv()}
                      disabled={!comparisonDecisionTsv}
                      data-testid="comparison-copy-decision-tsv"
                      className="inline-flex items-center gap-1.5 rounded-xl border border-white/20 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Copy className="h-4 w-4" />
                      {decisionTsvStatus === 'copied' ? '已复制 TSV' : decisionTsvStatus === 'fallback' ? '已转下载 TSV' : '复制决策 TSV'}
                    </button>
                    <button
                      type="button"
                      onClick={downloadComparisonDecisionTsv}
                      disabled={!comparisonDecisionTsv}
                      data-testid="comparison-download-decision-tsv"
                      className="inline-flex items-center gap-1.5 rounded-xl border border-white/20 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Download className="h-4 w-4" />
                      下载决策 TSV
                    </button>
                    <button
                      onClick={() => void saveComparisonReport()}
                      disabled={savingReport || salesGapLoading || !salesGapPayload || salesGapPayload.gapCount > 0}
                      data-testid="comparison-save-report"
                      className="rounded-xl bg-emerald-400 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {savingReport
                        ? '保存中...'
                        : salesGapLoading || !salesGapPayload
                          ? '扫描规则后保存'
                          : salesGapPayload.gapCount > 0
                            ? '补证后保存报告'
                            : '保存横向比较报告'}
                    </button>
                    {savedReportId ? (
                      <Link
                        href={`/reports/${savedReportId}`}
                        data-testid="comparison-saved-report-link"
                        className="rounded-xl border border-emerald-300/50 px-4 py-2 text-sm font-medium text-emerald-100 hover:bg-white/10"
                      >
                        查看已保存报告
                      </Link>
                    ) : null}
                    <Link
                      href={salesRuleGroupActionHref}
                      data-testid="comparison-sales-rules-link"
                      className="rounded-xl border border-white/20 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-white/10"
                    >
                      {activeSalesRuleReviewGaps.length ? '处理这组复查队列' : '补这组销售规则'}
                    </Link>
                  </div>
                </div>
                {memoStatus ? (
                  <div className="mt-4 rounded-xl bg-white/10 px-4 py-3 text-sm text-emerald-100">
                    {memoStatus}
                  </div>
                ) : null}
                {salesGapPayload?.gapCount ? (
                  <div className="mt-4 rounded-xl bg-amber-300/10 px-4 py-3 text-sm leading-6 text-amber-100 ring-1 ring-amber-200/20">
                    当前仍有 {salesGapPayload.gapCount} 只基金销售规则硬缺口；可复制备忘录回看，但不能保存正式横向比较报告，也不能把缺口基金加入观察池。
                  </div>
                ) : null}
                <textarea
                  id="comparison-memo-text"
                  name="comparison_memo_text"
                  aria-label="研究比较备忘录"
                  readOnly
                  value={memoText}
                  data-testid="comparison-memo-text"
                  rows={12}
                  className="mt-4 w-full rounded-2xl border border-white/10 bg-slate-900 px-4 py-3 font-mono text-xs leading-6 text-slate-100 outline-none"
                />
              </div>

            </>
          ) : (
            <div className="flex min-h-[420px] items-center justify-center rounded-2xl border border-dashed border-gray-200 bg-white p-10 text-center shadow-sm">
              <div>
                <GitCompare className="mx-auto h-10 w-10 text-gray-300" />
                <h2 className="mt-4 text-lg font-semibold text-gray-900">等待生成对比矩阵</h2>
                <p className="mt-2 max-w-md text-sm text-gray-500">
                  输入基金代码后，系统会计算滚动指标、专业评分和同类分位，生成适合投研初筛的横向矩阵。
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ComparisonAnalysisPage() {
  return <ComparisonAnalysisPageContent />
}
