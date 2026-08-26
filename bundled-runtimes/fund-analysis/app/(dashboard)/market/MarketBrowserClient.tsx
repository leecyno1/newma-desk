'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Download,
  ExternalLink,
  Filter,
  Layers3,
  Loader2,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  X,
} from 'lucide-react'
import type { CamelFund } from '@/lib/backend-api'
import {
  buildShareClassInfoByCode,
  getFeeValue,
  getMarketScreeningScore,
  getMaxDrawdown1y,
  getReturn1y,
  getSharpe1y,
  hasHoldingEvidence,
  holdingCount,
  numberValue,
  textValue,
  type Fund,
} from '@/lib/fund-research/market/market-workbench'
import {
  buildMarketFundResearchDecision,
  marketReviewEventCode,
  marketSalesRiskLevelCeiling,
  type MarketFundResearchDecision,
  type MarketMaterialGapSnapshot,
  type MarketMaterialRuleSnapshot,
  type MarketResearchRiskProfile,
  type MarketReviewEventSnapshot,
} from '@/lib/fund-research/decision'
import { marketCompareBasketEvidenceTool } from '@/lib/research-platform/tools/market-compare-basket-evidence'
import { marketCompareBasketWinLossTool } from '@/lib/research-platform/tools/market-compare-basket-win-loss'
import { marketCurrentPageShortlistTool, type MarketShortlistLane } from '@/lib/research-platform/tools/market-current-page-shortlist'
import { marketDecisionExplainerTool } from '@/lib/research-platform/tools/market-decision-explainer'
import { marketPromotionQueueTool, type MarketPromotionLaneKey } from '@/lib/research-platform/tools/market-promotion-queue'
import { materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'

type PurchasePlan = 'lump_sum' | 'sip'
type RiskProfile = MarketResearchRiskProfile
type InvestmentHorizon = 'lt1y' | '1to3y' | 'gt3y'
type SalesRiskFilter = '' | 'matched' | 'mismatch' | 'missing' | 'known'
type ResearchChecklistStatusFilter = '' | 'complete' | 'repair' | 'blocked'
type ShareClassDisplayMode = 'merged' | 'expanded'
type PromotionLaneFocus = 'all' | MarketPromotionLaneKey

type InitialFilters = {
  search?: string
  type?: string
  assetMin?: string
  assetMax?: string
  establishedFrom?: string
  establishedTo?: string
  evidenceStatus?: '' | 'ready' | 'verify' | 'blocked'
  hasManager?: string
  minManagerYears?: string
  hasFee?: string
  feeMax?: string
  tradableOnly?: string
  return1yMin?: string
  maxDrawdown1yMax?: string
  sharpe1yMin?: string
  screeningScoreMin?: string
  evidenceCoverageMin?: string
  researchChecklistStatus?: ResearchChecklistStatusFilter
  researchChecklistGap?: string
  salesRuleComplete?: string
  salesRiskFilter?: SalesRiskFilter
  hasNav?: string
  hasPerformance?: string
  hasHoldings?: string
  sortBy?: string
  sortOrder?: 'asc' | 'desc'
  riskProfile?: RiskProfile
  investmentHorizon?: InvestmentHorizon
  purchasePlan?: PurchasePlan
  plannedAmount?: string
  compareCodes?: string[]
  source?: string
  funnelStage?: string
  returnTo?: string
}

type Props = {
  initialFunds: CamelFund[]
  initialPage: number
  initialTotal: number
  initialTotalPages: number
  initialSummary: Record<string, unknown>
  initialFilters: InitialFilters
}

type MarketResearchChecklistSummary = {
  statusBuckets: Record<string, number>
  primaryGapBuckets: Record<string, number>
}

type MarketSummary = {
  marketResearchChecklist?: MarketResearchChecklistSummary
}

type Pool = {
  id: string
  name?: string
  is_default?: boolean
  isDefault?: boolean
}

type PoolMember = {
  id?: string
  fund_id?: string
  fundId?: string
  fund_wind_code?: string
  fundWindCode?: string
}

type MarketSuitabilityImpact = {
  coverage?: {
    total?: number
    riskLevelReady?: number
    riskLevelCoverage?: number
  }
  source?: string
}

const PAGE_SIZE = 30
const COMPARE_BASKET_LIMIT = 8
const BATCH_CANDIDATE_LIMIT = 20

const profileLabel: Record<RiskProfile, string> = {
  conservative: '稳健画像',
  balanced: '平衡画像',
  aggressive: '进取画像',
}

const horizonLabel: Record<InvestmentHorizon, string> = {
  lt1y: '1 年以内',
  '1to3y': '1–3 年',
  gt3y: '3 年以上',
}

function marketShortlistLaneClassName(lane: MarketShortlistLane) {
  if (lane === 'shortlist') return 'border-emerald-200 bg-emerald-50/50'
  if (lane === 'repair') return 'border-amber-200 bg-amber-50/50'
  return 'border-rose-200 bg-rose-50/50'
}

const RESEARCH_CHECKLIST_STATUS_OPTIONS: Array<{ value: ResearchChecklistStatusFilter; label: string }> = [
  { value: '', label: '全部体检状态' },
  { value: 'complete', label: '体检通过' },
  { value: 'repair', label: '体检待补' },
  { value: 'blocked', label: '体检阻断' },
]

const SORT_OPTIONS = [
  { value: 'totalAsset', label: '基金规模' },
  { value: 'screeningScore', label: '初筛分' },
  { value: 'evidenceCoverage', label: '证据覆盖分' },
  { value: 'researchChecklist', label: '体检通过数' },
  { value: 'return', label: '近一年收益' },
  { value: 'risk', label: '近一年回撤' },
  { value: 'sharpe', label: '近一年夏普' },
  { value: 'fee', label: '费率' },
  { value: 'updatedAt', label: '最近更新' },
]

const EVIDENCE_COVERAGE_PRESET = {
  label: '证据覆盖优先',
  sortBy: 'evidenceCoverage',
  sortOrder: 'desc' as const,
}

const MARKET_RESEARCH_BOUNDARIES = [
  '体检缺口队列只服务基金研究补证；缺失值不按中性分处理。',
  'Tushare fund_basic 只能补基础状态，不能作为 R1-R5 或申赎费率来源。',
  'Tushare fund_basic 不能作为 R1-R5 来源；补齐前不入池、不保存研究复核报告。',
  '销售风险等级缺失时，适当性匹配不能被推断为通过。',
  '销售规则硬缺口未清零前，不能进入正式研究短名单。',
  '材料核验和 R1-R5 来源背书未清零前，只能研究观察。',
  '有销售硬缺口的样本只能横评观察，补齐前不能入池或保存正式研究复核报告。',
  '字段级缺口不按中性分处理，硬阻断未解除前必须淘汰或降级。',
  '任何硬阻断都不会因为高收益或高初筛分被抬进研究清单。',
  '基础、绩效、风险、经理、持仓和销售规则均有可核验证据。',
  '复查队列仍有未解决销售规则/R1-R5事件时，正式路径保持阻断。',
]

function promotionLaneTestId(lane: MarketPromotionLaneKey) {
  if (lane === 'compare') return 'market-promotion-lane-compare'
  if (lane === 'sales_rules') return 'market-promotion-lane-sales-rules'
  if (lane === 'evidence') return 'market-promotion-lane-evidence-coverage'
  return 'market-promotion-lane-exclude-boundary'
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function normalizeMarketSummary(summary: unknown): MarketSummary {
  const root = asRecord(summary)
  const checklist = asRecord(root.marketResearchChecklist || root.market_research_checklist)
  if (!Object.keys(checklist).length) return {}
  const statusBuckets = asRecord(checklist.statusBuckets || checklist.status_buckets)
  const primaryGapBuckets = asRecord(checklist.primaryGapBuckets || checklist.primary_gap_buckets)
  return {
    marketResearchChecklist: {
      statusBuckets: Object.fromEntries(Object.entries(statusBuckets).map(([key, value]) => [key, Number(value || 0)])),
      primaryGapBuckets: Object.fromEntries(Object.entries(primaryGapBuckets).map(([key, value]) => [key, Number(value || 0)])),
    },
  }
}

function normalizeCode(value: unknown) {
  return textValue(value).toUpperCase()
}

function formatPercent(value: number | null, digits = 2) {
  return value === null ? '待补' : `${(value * 100).toFixed(digits)}%`
}

function formatNumber(value: number | null, digits = 2) {
  return value === null ? '待补' : value.toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

function formatAsset(value: number | null) {
  if (value === null) return '待补'
  return `${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 亿元`
}

function tsvCell(value: unknown) {
  const text = String(value ?? '')
  return /[\t\n\r"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function downloadTsv(filename: string, content: string) {
  const blob = new Blob([`\ufeff${content}`], { type: 'text/tab-separated-values;charset=utf-8' })
  const href = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = href
  link.download = filename
  link.click()
  URL.revokeObjectURL(href)
}

export default function MarketBrowserClient({
  initialFunds,
  initialPage,
  initialTotal,
  initialTotalPages,
  initialSummary,
  initialFilters,
}: Props) {
  const [funds, setFunds] = useState<Fund[]>(initialFunds)
  const [page, setPage] = useState(initialPage)
  const [total, setTotal] = useState(initialTotal)
  const [totalPages, setTotalPages] = useState(initialTotalPages)
  const [marketSummary, setMarketSummary] = useState<MarketSummary>(normalizeMarketSummary(initialSummary))
  const [loading, setLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [bannerMessage, setBannerMessage] = useState('')
  const [keyword, setKeyword] = useState(initialFilters.search || '')
  const [fundType, setFundType] = useState(initialFilters.type || '')
  const [assetMin, setAssetMin] = useState(initialFilters.assetMin || '')
  const [assetMax, setAssetMax] = useState(initialFilters.assetMax || '')
  const [establishedFrom, setEstablishedFrom] = useState(initialFilters.establishedFrom || '')
  const [establishedTo, setEstablishedTo] = useState(initialFilters.establishedTo || '')
  const [evidenceStatus, setEvidenceStatus] = useState(initialFilters.evidenceStatus || '')
  const [hasManager, setHasManager] = useState(initialFilters.hasManager || '')
  const [minManagerYears, setMinManagerYears] = useState(initialFilters.minManagerYears || '')
  const [hasFee, setHasFee] = useState(initialFilters.hasFee || '')
  const [feeMax, setFeeMax] = useState(initialFilters.feeMax || '')
  const [tradableOnly, setTradableOnly] = useState(initialFilters.tradableOnly || 'true')
  const [return1yMin, setReturn1yMin] = useState(initialFilters.return1yMin || '')
  const [maxDrawdown1yMax, setMaxDrawdown1yMax] = useState(initialFilters.maxDrawdown1yMax || '')
  const [sharpe1yMin, setSharpe1yMin] = useState(initialFilters.sharpe1yMin || '')
  const [screeningScoreMin, setScreeningScoreMin] = useState(initialFilters.screeningScoreMin || '')
  const [evidenceCoverageMin, setEvidenceCoverageMin] = useState(initialFilters.evidenceCoverageMin || '')
  const [researchChecklistStatus, setResearchChecklistStatus] = useState<ResearchChecklistStatusFilter>(initialFilters.researchChecklistStatus || '')
  const [researchChecklistGap, setResearchChecklistGap] = useState(initialFilters.researchChecklistGap || '')
  const [salesRuleComplete, setSalesRuleComplete] = useState(initialFilters.salesRuleComplete || '')
  const [salesRiskFilter, setSalesRiskFilter] = useState<SalesRiskFilter>(initialFilters.salesRiskFilter || '')
  const [hasNav, setHasNav] = useState(initialFilters.hasNav || '')
  const [hasPerformance, setHasPerformance] = useState(initialFilters.hasPerformance || '')
  const [hasHoldings, setHasHoldings] = useState(initialFilters.hasHoldings || '')
  const [sortBy, setSortBy] = useState(initialFilters.sortBy || 'totalAsset')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(initialFilters.sortOrder || 'desc')
  const [riskProfile, setRiskProfile] = useState<RiskProfile>(initialFilters.riskProfile || 'balanced')
  const [investmentHorizon, setInvestmentHorizon] = useState<InvestmentHorizon>(initialFilters.investmentHorizon || '1to3y')
  const [purchasePlan, setPurchasePlan] = useState<PurchasePlan>(initialFilters.purchasePlan || 'sip')
  const [plannedAmount, setPlannedAmount] = useState(initialFilters.plannedAmount || '')
  const [shareClassDisplayMode, setShareClassDisplayMode] = useState<ShareClassDisplayMode>('merged')
  const [selectedCompareCodes, setSelectedCompareCodes] = useState<string[]>(initialFilters.compareCodes || [])
  const [candidatePool, setCandidatePool] = useState<Pool | null>(null)
  const [candidatePoolMembers, setCandidatePoolMembers] = useState<PoolMember[]>([])
  const [savingCandidateCodes, setSavingCandidateCodes] = useState<Set<string>>(new Set())
  const [materialRules, setMaterialRules] = useState<MarketMaterialRuleSnapshot[]>([])
  const [materialGaps, setMaterialGaps] = useState<MarketMaterialGapSnapshot[]>([])
  const [reviewEvents, setReviewEvents] = useState<MarketReviewEventSnapshot[]>([])
  const [materialLoading, setMaterialLoading] = useState(false)
  const [suitabilityImpact, setSuitabilityImpact] = useState<MarketSuitabilityImpact | null>(null)
  const [promotionLaneFocus, setPromotionLaneFocus] = useState<PromotionLaneFocus>('all')
  const [showResearchReview, setShowResearchReview] = useState(false)

  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      page: String(page),
      limit: String(PAGE_SIZE),
      sortBy,
      sortOrder,
    })
    if (keyword.trim()) params.set('search', keyword.trim())
    if (fundType) params.set('type', fundType)
    if (assetMin) params.set('assetMin', assetMin)
    if (assetMax) params.set('assetMax', assetMax)
    if (establishedFrom) params.set('establishedFrom', establishedFrom)
    if (establishedTo) params.set('establishedTo', establishedTo)
    if (evidenceStatus) params.set('evidenceStatus', evidenceStatus)
    if (hasManager) params.set('hasManager', hasManager)
    if (minManagerYears) params.set('minManagerYears', minManagerYears)
    if (hasFee) params.set('hasFee', hasFee)
    if (feeMax) params.set('feeMax', feeMax)
    if (tradableOnly) params.set('tradableOnly', tradableOnly)
    if (return1yMin) params.set('return1yMin', return1yMin)
    if (maxDrawdown1yMax) params.set('maxDrawdown1yMax', maxDrawdown1yMax)
    if (sharpe1yMin) params.set('sharpe1yMin', sharpe1yMin)
    if (screeningScoreMin) params.set('screeningScoreMin', screeningScoreMin)
    if (evidenceCoverageMin) params.set('evidenceCoverageMin', evidenceCoverageMin)
    if (researchChecklistStatus) params.set('researchChecklistStatus', researchChecklistStatus)
    if (researchChecklistGap) params.set('researchChecklistGap', researchChecklistGap)
    if (salesRuleComplete) params.set('salesRuleComplete', salesRuleComplete)
    params.set('purchasePlan', purchasePlan)
    const amount = plannedAmount.trim()
    if (amount) params.set('plannedAmount', amount)
    if (salesRiskFilter) params.set('salesRiskFilter', salesRiskFilter)
    if (salesRiskFilter === 'matched' || salesRiskFilter === 'mismatch') params.set('maxSalesRiskLevel', String(marketSalesRiskLevelCeiling(riskProfile)))
    if (hasNav) params.set('hasNav', hasNav)
    if (hasPerformance) params.set('hasPerformance', hasPerformance)
    if (hasHoldings) params.set('hasHoldings', hasHoldings)
    return params.toString()
  }, [page, keyword, fundType, assetMin, assetMax, establishedFrom, establishedTo, evidenceStatus, hasManager, minManagerYears, hasFee, feeMax, tradableOnly, return1yMin, maxDrawdown1yMax, sharpe1yMin, screeningScoreMin, evidenceCoverageMin, researchChecklistStatus, researchChecklistGap, salesRuleComplete, purchasePlan, plannedAmount, salesRiskFilter, riskProfile, hasNav, hasPerformance, hasHoldings, sortBy, sortOrder])

  const marketViewQueryString = useMemo(() => {
    const params = new URLSearchParams(queryString)
    params.delete('limit')
    if (selectedCompareCodes.length) params.set('compare', selectedCompareCodes.join(','))
    if (initialFilters.source) params.set('source', initialFilters.source)
    if (initialFilters.funnelStage) params.set('funnelStage', initialFilters.funnelStage)
    return params.toString()
  }, [queryString, selectedCompareCodes, initialFilters.source, initialFilters.funnelStage])

  const marketReturnHref = `/market?${marketViewQueryString}`
  const reviewEventsQueueHref = reviewEventsHref({ returnTo: marketReturnHref })

  const withMarketPurchasePlan = useCallback((href: string, includeReturnTo = true) => {
    const [pathname, rawQuery = ''] = href.split('?')
    const params = new URLSearchParams(rawQuery)
    params.set('purchasePlan', purchasePlan)
    const amount = plannedAmount.trim()
    if (amount) params.set('plannedAmount', amount)
    if (includeReturnTo) params.set('returnTo', marketReturnHref)
    return `${pathname}?${params.toString()}`
  }, [purchasePlan, plannedAmount, marketReturnHref])

  const withMarketResearchContext = useCallback((href: string, includeReturnTo = true) => {
    const [pathname, rawQuery = ''] = href.split('?')
    const params = new URLSearchParams(rawQuery)
    params.set('profile', riskProfile)
    params.set('horizon', investmentHorizon)
    params.set('purchasePlan', purchasePlan)
    const amount = plannedAmount.trim()
    if (amount) {
      params.set('plannedAmount', amount)
      params.set(purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', amount)
    }
    if (includeReturnTo) params.set('returnTo', marketReturnHref)
    return `${pathname}?${params.toString()}`
  }, [riskProfile, investmentHorizon, purchasePlan, plannedAmount, marketReturnHref])

  const riskLevelSourceAuditHref = withMarketPurchasePlan(materialEvidenceHref({ scope: 'market', focus: 'risk_level', queueMode: 'high_score_missing_risk' }))
  const candidateRiskLevelSourceAuditHref = withMarketPurchasePlan(materialEvidenceHref({ scope: 'market', focus: 'risk_level', queueMode: 'candidate_missing_risk' }))
  const genericRiskLevelSourceAuditHref = withMarketPurchasePlan(materialEvidenceHref({ scope: 'market', focus: 'risk_level' }))
  const returnTo = initialFilters.returnTo || marketReturnHref
  const nestedReturnHref = withMarketPurchasePlan(returnTo, false)

  const fetchFunds = useCallback(async () => {
    setLoading(true)
    setErrorMessage('')
    try {
      const response = await fetch(`/api/funds?${queryString}`, { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || payload.error || '全市场基金列表读取失败')
      setFunds(Array.isArray(payload.data) ? payload.data : [])
      setTotal(Number(payload.pagination?.total || 0))
      setTotalPages(Math.max(1, Number(payload.pagination?.totalPages || 1)))
      setMarketSummary(normalizeMarketSummary(payload.summary))
      window.history.replaceState(null, '', `/market?${marketViewQueryString}`)
    } catch (error) {
      console.error('获取全市场基金列表失败:', error)
      setErrorMessage(error instanceof Error ? error.message : '获取全市场基金列表失败')
    } finally {
      setLoading(false)
    }
  }, [queryString, marketViewQueryString])

  const loadCandidatePoolContext = useCallback(async () => {
    try {
      const poolResponse = await fetch('/api/market/research-lists', { cache: 'no-store' })
      const poolPayload = await poolResponse.json().catch(() => ({}))
      if (!poolResponse.ok) throw new Error(poolPayload.detail || poolPayload.error || '默认观察池读取失败')
      const pools = Array.isArray(poolPayload.pools) ? poolPayload.pools as Pool[] : []
      const pool = pools.find((item) => item.is_default || item.isDefault) || pools[0] || null
      setCandidatePool(pool)
      if (!pool?.id) {
        setCandidatePoolMembers([])
        return
      }
      const membersResponse = await fetch(`/api/market/research-lists/${pool.id}/members`, { cache: 'no-store' })
      const membersPayload = await membersResponse.json().catch(() => ({}))
      if (!membersResponse.ok) throw new Error(membersPayload.detail || membersPayload.error || '观察池成员读取失败')
      setCandidatePoolMembers(Array.isArray(membersPayload.members) ? membersPayload.members : [])
    } catch (error) {
      console.error('读取观察池上下文失败:', error)
    }
  }, [])

  const ensureDefaultPool = useCallback(async () => {
    if (candidatePool?.id) return candidatePool
    const response = await fetch('/api/market/research-lists', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: '默认观察池',
        description: '由全市场研究工作台创建',
        createdBy: 'market-browser-ui',
        isDefault: true,
      }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok || !payload.id) throw new Error(payload.detail || payload.error || '默认观察池创建失败')
    const pool = payload as Pool
    setCandidatePool(pool)
    return pool
  }, [candidatePool])

  const loadMaterialContext = useCallback(async () => {
    const codes = funds.map((fund) => fund.windCode).filter(Boolean)
    if (!codes.length) {
      setMaterialRules([])
      setMaterialGaps([])
      setReviewEvents([])
      return
    }
    setMaterialLoading(true)
    try {
      const params = new URLSearchParams({ purchasePlan })
      params.set('codes', codes.join(','))
      params.set('limit', String(codes.length))
      const amount = plannedAmount.trim()
      if (amount) params.set('plannedAmount', amount)
      const [gapsResponse, alertsResponse, impactResponse] = await Promise.all([
        fetch(`/api/evidence-coverage/materials/gaps?${params.toString()}`, { cache: 'no-store' }),
        fetch('/api/evidence-coverage/review-events', { cache: 'no-store' }),
        fetch(`/api/evidence-coverage/materials/impact?${params.toString()}`, { cache: 'no-store' }),
      ])
      const gapsPayload = await gapsResponse.json().catch(() => ({}))
      const alertsPayload = await alertsResponse.json().catch(() => ({}))
      const impactPayload = await impactResponse.json().catch(() => ({}))
      if (gapsResponse.ok) {
        setMaterialRules(Array.isArray(gapsPayload.rules) ? gapsPayload.rules : [])
        setMaterialGaps(Array.isArray(gapsPayload.gaps) ? gapsPayload.gaps : [])
      }
      if (alertsResponse.ok) {
        const events = Array.isArray(alertsPayload.events) ? alertsPayload.events as MarketReviewEventSnapshot[] : []
        setReviewEvents(events.filter((event) => event.event_type === 'sales_rule_evidence' && event.status !== 'resolved'))
      }
      if (impactResponse.ok) setSuitabilityImpact(impactPayload)
    } catch (error) {
      console.error('读取材料核验上下文失败:', error)
    } finally {
      setMaterialLoading(false)
    }
  }, [funds, purchasePlan, plannedAmount])

  useEffect(() => {
    const task = window.setTimeout(() => {
      void loadCandidatePoolContext()
    }, 0)
    return () => window.clearTimeout(task)
  }, [loadCandidatePoolContext])

  useEffect(() => {
    const task = window.setTimeout(() => {
      void loadMaterialContext()
    }, 0)
    return () => window.clearTimeout(task)
  }, [loadMaterialContext])

  const candidateMemberCodes = useMemo(() => new Set(candidatePoolMembers.map((member) => normalizeCode(member.fund_wind_code || member.fundWindCode || member.fund_id || member.fundId))), [candidatePoolMembers])
  const materialRuleByCode = useMemo(() => new Map(materialRules.map((rule) => [normalizeCode(rule.windCode), rule])), [materialRules])
  const materialGapByCode = useMemo(() => new Map(materialGaps.map((gap) => [normalizeCode(gap.windCode), gap])), [materialGaps])
  const reviewEventsByCode = useMemo(() => {
    const result = new Map<string, MarketReviewEventSnapshot[]>()
    reviewEvents.forEach((event) => {
      const code = marketReviewEventCode(event)
      if (!code) return
      result.set(code, [...(result.get(code) || []), event])
    })
    return result
  }, [reviewEvents])
  const researchDecisionByCode = useMemo(() => {
    const asOf = new Date().toISOString()
    return new Map(funds.map((fund) => {
      const code = normalizeCode(fund.windCode)
      return [code, buildMarketFundResearchDecision({
        fund,
        riskProfile,
        materialRule: materialRuleByCode.get(code),
        materialGap: materialGapByCode.get(code),
        reviewEvents: reviewEventsByCode.get(code),
        asOf,
      })] as const
    }))
  }, [funds, riskProfile, materialRuleByCode, materialGapByCode, reviewEventsByCode])
  const researchDecisionFor = useCallback((fund: Fund): MarketFundResearchDecision => {
    const decision = researchDecisionByCode.get(normalizeCode(fund.windCode))
    if (!decision) throw new Error(`基金 ${fund.windCode} 缺少统一研究决策`)
    return decision
  }, [researchDecisionByCode])

  const shareClassInfoByCode = useMemo(() => buildShareClassInfoByCode(funds), [funds])
  const displayFunds = useMemo(() => shareClassDisplayMode === 'expanded'
    ? funds
    : funds.filter((fund) => shareClassInfoByCode.get(fund.windCode.toUpperCase())?.displayFund !== false), [funds, shareClassInfoByCode, shareClassDisplayMode])
  const selectedCompareFunds = useMemo(() => funds.filter((fund) => selectedCompareCodes.includes(fund.windCode)), [funds, selectedCompareCodes])

  const fundDetailHref = useCallback((fund: Fund) => withMarketResearchContext(`/funds/${encodeURIComponent(fund.id || fund.windCode)}`, true), [withMarketResearchContext])
  const salesRulesHrefForCodes = useCallback((codes: string[]) => withMarketPurchasePlan(materialEvidenceHref({ codes: codes.join(',') || undefined })), [withMarketPurchasePlan])
  const buildComparisonHref = useCallback((codes: string[]) => withMarketResearchContext(`/analysis/comparison?codes=${codes.map((code) => encodeURIComponent(code)).join(',')}`, true), [withMarketResearchContext])
  const materialReviewHrefForDecision = useCallback((researchDecision: MarketFundResearchDecision) => (
    researchDecision.material.actionKind === 'review-events' ? reviewEventsQueueHref : null
  ), [reviewEventsQueueHref])
  const materialActionHrefForDecision = useCallback((researchDecision: MarketFundResearchDecision) => (
    materialReviewHrefForDecision(researchDecision) || salesRulesHrefForCodes([researchDecision.decision.subjectId])
  ), [materialReviewHrefForDecision, salesRulesHrefForCodes])
  const batchSalesRulesHref = salesRulesHrefForCodes([])

  const toggleCompare = (code: string) => {
    setSelectedCompareCodes((current) => current.includes(code)
      ? current.filter((item) => item !== code)
      : current.length >= COMPARE_BASKET_LIMIT ? current : [...current, code])
  }

  const saveFundToCandidatePool = useCallback(async (fund: Fund) => {
    if (candidateMemberCodes.has(fund.windCode.toUpperCase())) return
    const researchDecision = researchDecisionFor(fund)
    const { formalGate: gate, material, suitability } = researchDecision
    if (!gate.passed) {
      setBannerMessage(`${fund.name} 未加入观察池：${gate.reason}`)
      return
    }
    const score = getMarketScreeningScore(fund)
    setSavingCandidateCodes((current) => new Set(current).add(fund.windCode))
    try {
      const pool = await ensureDefaultPool()
      const response = await fetch(`/api/market/research-lists/${pool.id}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fundId: fund.id,
          fundWindCode: fund.windCode,
          status: 'watch',
          purchasePlan,
          plannedAmount: numberValue(plannedAmount),
          reason: `全市场初筛 ${score.total} 分；${gate.reason}`,
          latestConclusion: `当前进入观察池，下一步完成同类横评、份额成本与研究报告复核。`,
          riskNotes: gate.reason,
          createdBy: 'market-browser-ui',
          evidence: {
            source: 'market-browser-batch',
            marketBrowser: { score, selectedAt: new Date().toISOString() },
            investorContext: { riskProfile, investmentHorizon, purchasePlan, plannedAmount: numberValue(plannedAmount) },
            purchaseGate: { level: 'watchlist', evidenceGrade: 'B', blocked: !gate.passed },
            fundResearchDecision: researchDecision.decision,
            riskSuitability: suitability,
            salesRuleGap: { checkedCode: fund.windCode, ...material },
          },
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || payload.error || '加入观察池失败')
      setBannerMessage(`${fund.name} 已加入默认观察池；正式路径仍需研究复核报告。`)
      await loadCandidatePoolContext()
    } catch (error) {
      setBannerMessage(error instanceof Error ? error.message : '加入观察池失败')
    } finally {
      setSavingCandidateCodes((current) => {
        const next = new Set(current)
        next.delete(fund.windCode)
        return next
      })
    }
  }, [candidateMemberCodes, researchDecisionFor, ensureDefaultPool, purchasePlan, plannedAmount, riskProfile, investmentHorizon, loadCandidatePoolContext])

  const saveCurrentPageToPool = async () => {
    const candidates = displayFunds
      .filter((fund) => !candidateMemberCodes.has(fund.windCode.toUpperCase()))
      .filter((fund) => researchDecisionFor(fund).formalGate.passed)
      .slice(0, BATCH_CANDIDATE_LIMIT)
    for (const fund of candidates) await saveFundToCandidatePool(fund)
    setBannerMessage(`当前页前 ${candidates.length} 只门禁通过样本已写入默认观察池。`)
  }

  const marketDecisionExplainerInput = {
    items: displayFunds.map((fund) => {
      const score = getMarketScreeningScore(fund)
      const researchDecision = researchDecisionFor(fund)
      const { formalGate: gate, material, suitability, readiness, operation } = researchDecision
      return {
        windCode: fund.windCode,
        name: fund.name,
        initialScore: score.total,
        formalGatePassed: gate.passed,
        formalGateLabel: gate.label,
        materialStatus: material.status,
        materialReviewHref: materialReviewHrefForDecision(researchDecision),
        executionAmountGateStatus: material.executionAmountGate?.status || null,
        suitabilityStatus: suitability.status,
        readinessLevel: readiness.level,
        operationStatus: operation.status,
      }
    }),
    profileLabel: profileLabel[riskProfile],
    activeSortLabel: SORT_OPTIONS.find((option) => option.value === sortBy)?.label || sortBy,
    sortOrder,
    compareLimit: COMPARE_BASKET_LIMIT,
  }
  const marketDecisionExplainerResult = marketDecisionExplainerTool.run(marketDecisionExplainerInput)
  const marketDecisionExplainerData = marketDecisionExplainerResult.data || {
    qualityLabel: '暂无样本', qualityDetail: '当前没有基金结果。', actionableRatio: 0, visibleCount: 0, actionableCount: 0,
    amountBlockedCount: 0, salesRuleBlockedCount: 0, evidenceOnlyCount: 0, suitabilityMismatchCount: 0,
    primaryAction: { kind: 'fallback' as const, label: '回到研究筛选', codes: [] }, topFundCopy: '暂无可解释样本', sortExplanation: '',
  }
  const marketDecisionPrimaryHref = marketDecisionExplainerData.primaryAction.kind === 'compare'
    ? buildComparisonHref(marketDecisionExplainerData.primaryAction.codes)
    : marketDecisionExplainerData.primaryAction.kind === 'review_events'
      ? reviewEventsQueueHref
      : marketDecisionExplainerData.primaryAction.kind === 'material_evidence' || marketDecisionExplainerData.primaryAction.kind === 'amount_gate'
        ? salesRulesHrefForCodes(marketDecisionExplainerData.primaryAction.codes)
        : withMarketResearchContext('/market', true)
  const marketDecisionExplainer = { ...marketDecisionExplainerData, primaryAction: { ...marketDecisionExplainerData.primaryAction, href: marketDecisionPrimaryHref } }

  const marketShortlistInput = {
    items: displayFunds.map((fund) => {
      const score = getMarketScreeningScore(fund)
      const researchDecision = researchDecisionFor(fund)
      const { formalGate: gate, material, suitability, readiness, checklist, operation } = researchDecision
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type || '待补',
        initialScore: score.total,
        scoreGrade: score.grade,
        scoreLabel: score.label,
        formalGatePassed: gate.passed,
        formalGateLabel: gate.label,
        formalGateReportLabel: gate.reportLabel,
        formalGateReason: gate.reason,
        formalGateActionLabel: gate.actionLabel,
        formalGateActionHref: materialActionHrefForDecision(researchDecision),
        readinessLevel: readiness.level,
        readinessLabel: readiness.label,
        readinessGaps: readiness.gaps,
        materialStatus: material.status,
        materialLabel: material.label,
        materialReviewHref: materialReviewHrefForDecision(researchDecision),
        executionAmountGateStatus: material.executionAmountGate?.status || null,
        executionAmountGateLabel: material.executionAmountGate?.label || null,
        executionAmountGateDetail: material.executionAmountGate?.detail || null,
        suitabilityStatus: suitability.status,
        suitabilityLabel: suitability.label,
        hasHoldingEvidence: hasHoldingEvidence(fund),
        operationStatus: operation.status,
        researchChecklistLabel: checklist.label,
        researchChecklistLights: checklist.items.map((item) => `${item.label}:${item.status}`).join('；'),
        researchChecklistFirstGap: checklist.firstGap,
        researchChecklistBackend: `${checklist.backendLabel}${checklist.backendPrimaryGap ? ` · ${checklist.backendPrimaryGap}` : ''}`,
        detailHref: fundDetailHref(fund),
      }
    }),
    compareLimit: COMPARE_BASKET_LIMIT,
  }
  const marketShortlistResult = marketCurrentPageShortlistTool.run(marketShortlistInput)
  const marketShortlist = marketShortlistResult.data || {
    rows: [], topRows: [], shortlistRows: [], repairRows: [], excludeRows: [], compareCodes: [],
    primaryAction: { kind: 'fallback' as const, label: '回到研究筛选', codes: [] }, summary: '暂无样本', tsv: '',
  }
  const marketShortlistTsv = marketShortlist.tsv

  const marketPromotionQueueInput = {
    items: displayFunds.map((fund) => {
      const score = getMarketScreeningScore(fund)
      const researchDecision = researchDecisionFor(fund)
      const { readiness, material, suitability, formalGate, checklist, operation } = researchDecision
      return {
        windCode: fund.windCode,
        name: fund.name,
        initialScore: score.total,
        operationStatus: operation.status,
        operationReason: operation.reason,
        readinessGaps: readiness.gaps,
        materialStatus: material.status,
        materialMissingCount: material.missingCount,
        materialMissingItems: material.missingItems,
        materialReviewHref: materialReviewHrefForDecision(researchDecision),
        materialNextAction: material.nextAction,
        executionAmountGateStatus: material.executionAmountGate?.status || null,
        executionAmountGateDetail: material.executionAmountGate?.detail || null,
        suitabilityStatus: suitability.status,
        suitabilityDetail: suitability.detail,
        formalGateReason: formalGate.reason,
        hasHoldingEvidence: hasHoldingEvidence(fund),
        detailHref: fundDetailHref(fund),
        materialHref: materialActionHrefForDecision(researchDecision),
        researchChecklistLabel: checklist.label,
        researchChecklistLights: checklist.items.map((item) => `${item.label}:${item.status}`).join('；'),
        researchChecklistFirstGap: checklist.firstGap,
        researchChecklistBackend: checklist.backendLabel,
      }
    }),
    compareLimit: COMPARE_BASKET_LIMIT,
    rowLimitPerLane: 4,
    visibleCount: displayFunds.length,
    profileLabel: profileLabel[riskProfile],
    materialEvidenceFields: purchasePlan === 'lump_sum' ? '起购金额、限购、风险等级和来源日期' : '定投起点、限购、风险等级和来源日期',
  }
  const marketPromotionQueueResult = marketPromotionQueueTool.run(marketPromotionQueueInput)
  const marketPromotionQueue = marketPromotionQueueResult.data || {
    lanes: [], taskRows: [], gateAudit: { compareCount: 0, salesRulesCount: 0, evidenceCount: 0, excludeCount: 0, totalTaskCount: 0, hardBlockedCount: 0, formalBlockedCount: 0, reviewQueueCount: 0, amountGateCount: 0, primaryBlocker: '暂无样本', primaryActionKind: 'fallback' as const, actionableRatio: 0, verdict: '暂无可行动样本', boundary: '' },
    compareCodes: [], salesRuleCodes: [], evidenceCodes: [], promotionCompareCodes: [], compareCodeCount: 0, totalVisible: 0, summary: '暂无样本', tasksTsv: '',
  }
  const marketPromotionTaskRows = marketPromotionQueue.taskRows
  const promotionLaneOptions = [
    { key: 'all' as const, label: '全部分流', count: marketPromotionTaskRows.length },
    ...marketPromotionQueue.lanes.map((lane) => ({ key: lane.key as PromotionLaneFocus, label: lane.title, count: lane.rows.length })),
  ]
  const focusedMarketPromotionLanes = promotionLaneFocus === 'all' ? marketPromotionQueue.lanes : marketPromotionQueue.lanes.filter((lane) => lane.key === promotionLaneFocus)
  const focusedMarketPromotionTaskRows = promotionLaneFocus === 'all' ? marketPromotionTaskRows : marketPromotionTaskRows.filter((row) => row.laneKey === promotionLaneFocus)
  const marketPromotionGateAudit = {
    ...marketPromotionQueue.gateAudit,
    primaryHref: marketPromotionQueue.gateAudit.primaryActionKind === 'material_evidence'
      ? salesRulesHrefForCodes(marketPromotionQueue.salesRuleCodes)
      : marketPromotionQueue.gateAudit.primaryActionKind === 'evidence_coverage'
        ? withMarketResearchContext('/evidence-coverage', true)
        : marketPromotionQueue.promotionCompareCodes.length >= 2
          ? buildComparisonHref(marketPromotionQueue.promotionCompareCodes)
          : withMarketResearchContext('/market', true),
  }
  const marketPromotionTasksTsv = marketPromotionQueue.tasksTsv

  const compareBasketSalesRuleGate = {
    gapFunds: selectedCompareFunds.filter((fund) => researchDecisionFor(fund).material.status === 'gap').length,
    missingItems: selectedCompareFunds.reduce((totalCount, fund) => totalCount + researchDecisionFor(fund).material.missingCount, 0),
    unknownFunds: selectedCompareFunds.filter((fund) => researchDecisionFor(fund).material.status === 'unknown').length,
    amountBlockedFunds: selectedCompareFunds.filter((fund) => researchDecisionFor(fund).material.executionAmountGate?.status === 'blocked').length,
    suitabilityMismatchFunds: selectedCompareFunds.filter((fund) => researchDecisionFor(fund).suitability.status === 'mismatch').length,
    suitabilityMissingFunds: selectedCompareFunds.filter((fund) => researchDecisionFor(fund).suitability.status === 'missing').length,
  }
  const compareBasketFormalActionsBlocked = compareBasketSalesRuleGate.amountBlockedFunds > 0
  const compareBasketEvidenceInput = {
    items: selectedCompareFunds.map((fund) => {
      const score = getMarketScreeningScore(fund)
      const researchDecision = researchDecisionFor(fund)
      const { readiness, formalGate: gate, material, suitability } = researchDecision
      const shareClassInfo = shareClassInfoByCode.get(fund.windCode.toUpperCase())
      return {
        windCode: fund.windCode,
        name: fund.name,
        type: fund.type || '待补',
        initialScore: score.total,
        scoreGrade: score.grade,
        scoreLabel: score.label,
        formalGatePassed: gate.passed,
        formalGateLabel: gate.label,
        formalGateReportLabel: gate.reportLabel,
        formalGateReason: gate.reason,
        formalGateActionLabel: gate.actionLabel,
        suitabilityLabel: suitability.label,
        materialLabel: material.label,
        materialMissingItems: material.missingItems,
        executionAmountGateLabel: material.executionAmountGate?.label || null,
        executionAmountGateDetail: material.executionAmountGate?.detail || null,
        readinessLabel: readiness.label,
        readinessGaps: readiness.gaps,
        researchListStatus: candidateMemberCodes.has(fund.windCode.toUpperCase()) ? '已在观察池' : '尚未入池',
        shareClassHint: shareClassInfo?.siblingCount ? `同基金 ${shareClassInfo.siblingCount + 1} 个份额；多份额对比` : '单份额或同类份额待识别',
        fundDetailHref: fundDetailHref(fund),
        materialHref: materialActionHrefForDecision(researchDecision),
      }
    }),
    gate: compareBasketSalesRuleGate,
    readiness: {
      blocked: selectedCompareFunds.filter((fund) => researchDecisionFor(fund).readiness.level === 'blocked').length,
      verify: selectedCompareFunds.filter((fund) => researchDecisionFor(fund).readiness.level === 'verify').length,
    },
    profileLabel: profileLabel[riskProfile],
    comparisonHref: buildComparisonHref(selectedCompareCodes),
    materialEvidenceHref: salesRulesHrefForCodes(selectedCompareCodes),
  }
  const compareBasketEvidenceResult = marketCompareBasketEvidenceTool.run(compareBasketEvidenceInput)
  const compareBasketEvidenceRows = compareBasketEvidenceResult.data?.rows || []
  const compareBasketEvidenceTsv = compareBasketEvidenceResult.data?.tsv || ''

  const compareBasketWinLossInput = {
    items: selectedCompareFunds.map((fund) => {
      const score = getMarketScreeningScore(fund)
      const researchDecision = researchDecisionFor(fund)
      const { formalGate: gate, readiness, material, suitability } = researchDecision
      return {
        windCode: fund.windCode,
        name: fund.name,
        initialScore: score.total,
        scoreGrade: score.grade,
        scoreLabel: score.label,
        formalGatePassed: gate.passed,
        formalGateLabel: gate.label,
        formalGateReason: gate.reason,
        readinessLevel: readiness.level,
        readinessGaps: readiness.gaps,
        materialStatus: material.status,
        materialLabel: material.label,
        materialHref: materialActionHrefForDecision(researchDecision),
        executionAmountGateStatus: material.executionAmountGate?.status || null,
        executionAmountGateDetail: material.executionAmountGate?.detail || null,
        suitabilityStatus: suitability.status,
        suitabilityLabel: suitability.label,
        suitabilityDetail: suitability.detail,
        returnValue: getReturn1y(fund),
        drawdownValue: getMaxDrawdown1y(fund),
        sharpeValue: getSharpe1y(fund),
        feeValue: getFeeValue(fund),
        fundDetailHref: fundDetailHref(fund),
      }
    }),
    comparisonHref: buildComparisonHref(selectedCompareCodes),
    materialEvidenceHref: salesRulesHrefForCodes(selectedCompareCodes),
  }
  const compareBasketWinLossResult = marketCompareBasketWinLossTool.run(compareBasketWinLossInput)
  const compareBasketWinLossRows = compareBasketWinLossResult.data?.rows || []
  const compareBasketWinLossAudit = compareBasketWinLossResult.data?.audit || { tone: 'slate' as const, verdict: '样本不足', summary: '至少加入 2 只基金。', nextAction: '继续选择样本。' }
  const compareBasketWinLossTsv = compareBasketWinLossResult.data?.tsv || ''

  const smartCompareCandidates = marketShortlist.shortlistRows.slice(0, COMPARE_BASKET_LIMIT).map((row) => row.windCode)
  const researchChecklistLights = displayFunds.map((fund) => researchDecisionFor(fund).checklist.items)
  const researchChecklistFirstGap = displayFunds.map((fund) => researchDecisionFor(fund).checklist.firstGap)

  const marketChecklistSummary = marketSummary.marketResearchChecklist
  const marketChecklistStatusBuckets = marketChecklistSummary?.statusBuckets || {}
  const marketChecklistPrimaryGapBuckets = marketChecklistSummary?.primaryGapBuckets || {}
  const marketChecklistTopGaps = Object.entries(marketChecklistPrimaryGapBuckets).sort((left, right) => Number(right[1]) - Number(left[1])).slice(0, 6)
  const marketChecklistGapHref = (gap: string) => withMarketResearchContext(`/market?researchChecklistStatus=repair&researchChecklistGap=${encodeURIComponent(gap)}&sortBy=researchChecklist&sortOrder=asc`, false)
  const marketChecklistRepairHref = withMarketResearchContext('/market?researchChecklistStatus=repair&sortBy=researchChecklist&sortOrder=desc', false)
  const marketChecklistBlockedHref = withMarketResearchContext('/market?researchChecklistStatus=blocked&sortBy=researchChecklist&sortOrder=asc', false)
  const marketChecklistCompleteHref = withMarketResearchContext('/market?researchChecklistStatus=complete&sortBy=researchChecklist&sortOrder=desc', false)
  const drillIntoMarketChecklistGap = (gap: string) => {
    setResearchChecklistStatus('repair')
    setResearchChecklistGap(gap)
    setPage(1)
  }
  const marketChecklistQueueAction = {
    primaryLabel: marketChecklistTopGaps[0] ? `处理首要缺口：${marketChecklistTopGaps[0][0]}` : '查看待补队列',
    primaryHref: marketChecklistTopGaps[0] ? marketChecklistGapHref(marketChecklistTopGaps[0][0]) : marketChecklistRepairHref,
    secondaryLabel: '查看持仓证据覆盖',
    secondaryHref: withMarketResearchContext('/evidence-coverage?focus=holdings', true),
  }
  const marketChecklistWorkOrderRows = displayFunds.map((fund, index) => {
    const score = getMarketScreeningScore(fund)
    const researchDecision = researchDecisionFor(fund)
    const { checklist, material } = researchDecision
    return {
      index: index + 1,
      fund,
      score,
      checklist,
      material,
      nextAction: checklist.items[0]?.key === 'foundation' && checklist.items[0].status !== 'ready' ? '批量补基础数据' : checklist.firstGap,
      href: materialActionHrefForDecision(researchDecision),
    }
  }).filter((row) => row.checklist.status !== 'complete')
  const marketChecklistWorkOrderTsv = [
    ['序号', '首要缺口', '基金代码', '基金名称', '类型', '初筛分', '后端全市场体检', '本页六灯体检', '体检灯明细', '需补字段', '下一动作', '主入口', '详情入口', '硬边界'],
    ...marketChecklistWorkOrderRows.map((row) => [
      row.index, row.checklist.firstGap, row.fund.windCode, row.fund.name, row.fund.type, row.score.total,
      row.checklist.backendLabel, row.checklist.label, row.checklist.items.map((item) => `${item.label}:${item.status}`).join('；'),
      row.material.missingItems.join('、') || row.checklist.firstGap, row.nextAction, row.href, fundDetailHref(row.fund), '体检缺口队列只服务基金研究补证',
    ]),
  ].map((row) => row.map(tsvCell).join('\t')).join('\n')

  const marketExportRows = displayFunds.map((fund) => {
    const score = getMarketScreeningScore(fund)
    const researchDecision = researchDecisionFor(fund)
    const { formalGate: gate, suitability, material, readiness, checklist } = researchDecision
    return { fund, score, gate, suitability, material, readiness, checklist, researchDecision }
  })
  const marketCurrentPageTsv = [
    ['基金代码', '基金名称', '类型', '初筛分', '正式门禁', '门禁原因', '适当性', '销售规则状态', '计划金额门禁', '缺口项', '持仓证据', '研究证据', '研究复核体检', '体检六灯', '体检首要缺口', '后端全市场体检', '份额提示', '下一动作', '基金详情入口', '销售规则入口'],
    ...marketExportRows.map((row) => [
      row.fund.windCode, row.fund.name, row.fund.type, `${row.score.total}/${row.score.grade}/${row.score.label}`,
      row.gate.reportLabel, row.gate.reason, row.suitability.label, row.material.label,
      row.material.executionAmountGate ? `${row.material.executionAmountGate.label}：${row.material.executionAmountGate.detail}` : '金额门槛待扫描',
      row.material.missingItems.join('、') || '无', hasHoldingEvidence(row.fund) ? `持仓 ${holdingCount(row.fund)} 条` : '持仓暴露待补',
      `${row.readiness.label}${row.readiness.gaps.length ? `：${row.readiness.gaps.join('、')}` : ''}`, row.checklist.label,
      row.checklist.items.map((item) => `${item.label}:${item.status}`).join('；'), row.checklist.firstGap, row.checklist.backendLabel,
      shareClassInfoByCode.get(row.fund.windCode.toUpperCase())?.siblingCount ? '同基金多份额对比' : '单份额',
      row.gate.actionLabel, fundDetailHref(row.fund), materialActionHrefForDecision(row.researchDecision),
    ]),
  ].map((row) => row.map(tsvCell).join('\t')).join('\n')

  const copyText = async (content: string, fallback: () => void, success: string, fallbackMessage: string) => {
    try {
      await navigator.clipboard.writeText(content)
      setBannerMessage(success)
    } catch {
      fallback()
      setBannerMessage(fallbackMessage)
    }
  }

  const downloadMarketCurrentPageTsv = () => downloadTsv(`全市场基金研究_${new Date().toISOString().slice(0, 10)}.tsv`, marketCurrentPageTsv)
  const copyMarketCurrentPageTsv = () => copyText(marketCurrentPageTsv, downloadMarketCurrentPageTsv, `已复制当前页 ${marketExportRows.length} 只基金的研究复核 TSV。`, `复制受限，已转下载当前页 ${marketExportRows.length} 只基金的研究复核 TSV`)
  const downloadMarketShortlistTsv = () => downloadTsv(`全市场研究短名单_${new Date().toISOString().slice(0, 10)}.tsv`, marketShortlistTsv)
  const copyMarketShortlistTsv = () => copyText(marketShortlistTsv, downloadMarketShortlistTsv, `已复制 ${marketShortlist.rows.length} 条研究短名单评分卡 TSV。`, '复制受限，已转下载')
  const downloadMarketPromotionTasksTsv = () => downloadTsv(`全市场研究任务_${new Date().toISOString().slice(0, 10)}.tsv`, marketPromotionTasksTsv)
  const copyMarketPromotionTasksTsv = () => copyText(marketPromotionTasksTsv, () => downloadMarketPromotionTasksTsv(), '已复制研究任务 TSV。', '复制受限，已转下载')
  const downloadCompareBasketEvidenceTsv = () => downloadTsv(`对比篮证据工作单_${new Date().toISOString().slice(0, 10)}.tsv`, compareBasketEvidenceTsv)
  const copyCompareBasketEvidenceTsv = () => copyText(compareBasketEvidenceTsv, downloadCompareBasketEvidenceTsv, `已复制 ${compareBasketEvidenceRows.length} 只已选基金的对比篮证据工作单 TSV。`, `复制受限，已转下载 ${compareBasketEvidenceRows.length} 只已选基金的对比篮证据工作单 TSV`)
  const downloadCompareBasketWinLossTsv = () => downloadTsv(`对比篮胜负线_${new Date().toISOString().slice(0, 10)}.tsv`, compareBasketWinLossTsv)
  const copyCompareBasketWinLossTsv = () => copyText(compareBasketWinLossTsv, downloadCompareBasketWinLossTsv, '已复制胜负线 TSV。', '复制受限，已转下载')
  const downloadMarketChecklistWorkOrderTsv = () => {
    downloadTsv(`体检缺口工作单_${new Date().toISOString().slice(0, 10)}.tsv`, marketChecklistWorkOrderTsv)
    setBannerMessage(`已下载 ${marketChecklistWorkOrderRows.length} 条体检缺口工作单`)
  }
  const copyMarketChecklistWorkOrderTsv = () => copyText(marketChecklistWorkOrderTsv, downloadMarketChecklistWorkOrderTsv, `已复制 ${marketChecklistWorkOrderRows.length} 条体检缺口工作单`, '复制受限，已转下载')

  const resetFilters = () => {
    setKeyword('')
    setFundType('')
    setAssetMin('')
    setAssetMax('')
    setEstablishedFrom('')
    setEstablishedTo('')
    setEvidenceStatus('')
    setHasManager('')
    setMinManagerYears('')
    setHasFee('')
    setFeeMax('')
    setTradableOnly('true')
    setReturn1yMin('')
    setMaxDrawdown1yMax('')
    setSharpe1yMin('')
    setScreeningScoreMin('')
    setEvidenceCoverageMin('')
    setResearchChecklistStatus('')
    setResearchChecklistGap('')
    setSalesRuleComplete('')
    setSalesRiskFilter('')
    setHasNav('')
    setHasPerformance('')
    setHasHoldings('')
    setSortBy('totalAsset')
    setSortOrder('desc')
    setPage(1)
  }

  const activeFilterCount = [keyword, fundType, assetMin, assetMax, establishedFrom, establishedTo, evidenceStatus, hasManager, minManagerYears, hasFee, feeMax, return1yMin, maxDrawdown1yMax, sharpe1yMin, screeningScoreMin, evidenceCoverageMin, researchChecklistStatus, researchChecklistGap, salesRuleComplete, salesRiskFilter, hasNav, hasPerformance, hasHoldings].filter(Boolean).length
  const salesRuleEvidenceFieldsForPlan = purchasePlan === 'lump_sum' ? '起购金额、限购、风险等级和来源日期' : '定投起点、限购、风险等级和来源日期'
  const salesRuleScanFieldsForPlan = purchasePlan === 'lump_sum' ? '起购金额、限购、风险等级和来源日期' : '定投起点、限购、风险等级和来源日期'
  const foundationManualFieldsForPlan = purchasePlan === 'lump_sum' ? '基础状态与成立日期' : '基础状态、成立日期与定投支持状态'
  const salesRuleEvidenceFields = salesRuleEvidenceFieldsForPlan
  const salesRuleScanFields = salesRuleScanFieldsForPlan
  const formalReportError = `请先补齐${salesRuleEvidenceFields}`
  const salesRuleScanMessage = `正在扫描当前页基金的${salesRuleScanFields}。`
  const marketChecklistCoverageText = marketChecklistSummary
    ? `通过 ${Number(marketChecklistStatusBuckets.complete || 0).toLocaleString('zh-CN')} · 待补 ${Number(marketChecklistStatusBuckets.repair || 0).toLocaleString('zh-CN')} · 阻断 ${Number(marketChecklistStatusBuckets.blocked || 0).toLocaleString('zh-CN')}`
    : '等待全市场体检统计'
  const reviewQueueRows = marketPromotionTaskRows.filter((row) => row.reason.includes('复查队列'))
  const marketSalesRuleUnlockQueue = [
    { label: '复查队列', matches: (item: string) => item.includes('复查队列未解决') },
    { label: '风险等级', matches: (item: string) => item.includes('风险等级') },
    { label: purchasePlan === 'lump_sum' ? '起购金额' : '定投起点', matches: (item: string) => item.includes('金额') || item.includes('起点') },
    { label: '来源日期', matches: (item: string) => item.includes('来源') || item.includes('过期') },
  ].map((guide) => ({
    ...guide,
    count: displayFunds.filter((fund) => researchDecisionFor(fund).material.missingItems.some(guide.matches)).length,
    href: guide.label === '复查队列' ? reviewEventsQueueHref : salesRulesHrefForCodes(displayFunds.map((fund) => fund.windCode)),
  }))

  return (
    <div className="min-h-screen bg-[#f4f2ec] text-slate-950">
      <main className="mx-auto min-w-0 max-w-[1500px] space-y-5 px-4 py-6 sm:px-6 lg:px-8">
        <section className="overflow-hidden rounded-[28px] border border-slate-900/10 bg-[#10221b] text-white shadow-[0_24px_80px_rgba(15,23,42,0.12)]">
          <div className="grid gap-6 p-6 lg:grid-cols-[1.4fr_0.8fr] lg:p-8">
            <div>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => void saveCurrentPageToPool()} className="rounded-full bg-emerald-300 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-200">当前页前 {Math.min(BATCH_CANDIDATE_LIMIT, displayFunds.length)} 只加入观察池</button>
                <button type="button" onClick={() => setShowResearchReview((value) => !value)} className="inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm font-semibold ring-1 ring-white/15 hover:bg-white/15">研究复核提示（可展开）<ChevronDown className={`h-4 w-4 transition ${showResearchReview ? 'rotate-180' : ''}`} /></button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 self-end">
              {[
                ['全市场样本', total.toLocaleString('zh-CN')],
                ['当前页', `${displayFunds.length} 只`],
                ['可行动比例', `${marketDecisionExplainer.actionableRatio}%`],
                ['默认观察池', candidatePool?.name || '待连接'],
              ].map(([label, value]) => <div key={label} className="rounded-2xl bg-white/8 p-4 ring-1 ring-white/10"><div className="text-xs text-slate-400">{label}</div><div className="mt-2 text-lg font-semibold text-white">{value}</div></div>)}
            </div>
          </div>
        </section>

        {bannerMessage ? <div className="flex items-start justify-between gap-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"><span>{bannerMessage}</span><button type="button" onClick={() => setBannerMessage('')}><X className="h-4 w-4" /></button></div> : null}
        {errorMessage ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">{errorMessage}</div> : null}

        <section className="rounded-[24px] border border-slate-900/10 bg-white p-4 shadow-sm sm:p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
            <label className="min-w-0 flex-1 basis-full lg:basis-72"><span className="mb-2 block text-xs font-semibold text-slate-500">搜索代码或名称</span><span className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3"><Search className="h-4 w-4 text-slate-400" /><input value={keyword} onChange={(event) => setKeyword(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && (setPage(1), void fetchFunds())} className="min-w-0 flex-1 bg-transparent py-3 text-sm outline-none" placeholder="基金代码 / 名称" /></span></label>
            <label className="min-w-0 flex-1 sm:flex-none"><span className="mb-2 block text-xs font-semibold text-slate-500">基金类型</span><select value={fundType} onChange={(event) => { setFundType(event.target.value); setPage(1) }} className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm sm:w-auto"><option value="">全部类型</option><option value="stock">股票型</option><option value="mixed">混合型</option><option value="bond">债券型</option><option value="index">指数型</option><option value="qdii">QDII</option></select></label>
            <label className="min-w-0 flex-1 sm:flex-none"><span className="mb-2 block text-xs font-semibold text-slate-500">排序</span><select value={sortBy} onChange={(event) => { setSortBy(event.target.value); setPage(1) }} className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm sm:w-auto">{SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
            <label className="min-w-0 flex-1 sm:flex-none"><span className="mb-2 block text-xs font-semibold text-slate-500">顺序</span><select value={sortOrder} onChange={(event) => { setSortOrder(event.target.value as 'asc' | 'desc'); setPage(1) }} className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm sm:w-auto"><option value="desc">降序</option><option value="asc">升序</option></select></label>
            <button type="button" onClick={() => void fetchFunds()} className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-slate-950 px-5 text-sm font-semibold text-white hover:bg-slate-800 sm:w-auto">{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Filter className="h-4 w-4" />}应用筛选</button>
            <button type="button" onClick={resetFilters} className="inline-flex h-11 w-full items-center justify-center rounded-xl border border-slate-200 px-4 text-sm font-semibold text-slate-600 hover:bg-slate-50 sm:w-auto">清空 {activeFilterCount ? `(${activeFilterCount})` : ''}</button>
          </div>
          <details className="mt-4 rounded-2xl bg-slate-50 p-4" open={activeFilterCount > 3}>
            <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-semibold"><span className="inline-flex items-center gap-2"><SlidersHorizontal className="h-4 w-4" />专业筛选条件</span><ChevronDown className="h-4 w-4" /></summary>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
              <input value={assetMin} onChange={(event) => setAssetMin(event.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="规模下限（亿元）" />
              <input value={assetMax} onChange={(event) => setAssetMax(event.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="规模上限（亿元）" />
              <input value={return1yMin} onChange={(event) => setReturn1yMin(event.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="近一年收益下限 %" />
              <input value={maxDrawdown1yMax} onChange={(event) => setMaxDrawdown1yMax(event.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="近一年回撤上限 %" />
              <input value={sharpe1yMin} onChange={(event) => setSharpe1yMin(event.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="夏普下限" />
              <input value={screeningScoreMin} onChange={(event) => setScreeningScoreMin(event.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="初筛分下限" />
              <input value={evidenceCoverageMin} onChange={(event) => setEvidenceCoverageMin(event.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="证据覆盖分下限" />
              <select value={researchChecklistStatus} onChange={(event) => setResearchChecklistStatus(event.target.value as ResearchChecklistStatusFilter)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">{RESEARCH_CHECKLIST_STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>
              <select value={salesRiskFilter} onChange={(event) => setSalesRiskFilter(event.target.value as SalesRiskFilter)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm"><option value="">全部适当性</option><option value="matched">匹配当前画像</option><option value="mismatch">适当性不匹配</option><option value="missing">风险等级缺失</option><option value="known">风险等级已知</option></select>
              <select value={hasHoldings} onChange={(event) => setHasHoldings(event.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm"><option value="">全部持仓状态</option><option value="true">持仓可解释</option><option value="false">持仓暴露待补</option></select>
              <select value={salesRuleComplete} onChange={(event) => setSalesRuleComplete(event.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm"><option value="">全部材料状态</option><option value="true">材料核验完整</option><option value="false">材料待补</option></select>
              <select value={evidenceStatus} onChange={(event) => setEvidenceStatus(event.target.value as '' | 'ready' | 'verify' | 'blocked')} className="rounded-lg border border-slate-200 px-3 py-2 text-sm"><option value="">全部证据状态</option><option value="ready">证据就绪</option><option value="verify">证据待核</option><option value="blocked">证据阻断</option></select>
            </div>
          </details>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <label className="rounded-2xl border border-slate-200 p-4"><span className="text-xs font-semibold text-slate-500">当前画像</span><select value={riskProfile} onChange={(event) => setRiskProfile(event.target.value as RiskProfile)} className="mt-2 w-full bg-transparent text-sm font-semibold outline-none"><option value="conservative">稳健画像</option><option value="balanced">平衡画像</option><option value="aggressive">进取画像</option></select></label>
            <label className="rounded-2xl border border-slate-200 p-4"><span className="text-xs font-semibold text-slate-500">研究期限 · {horizonLabel[investmentHorizon]}</span><select value={investmentHorizon} onChange={(event) => setInvestmentHorizon(event.target.value as InvestmentHorizon)} className="mt-2 w-full bg-transparent text-sm font-semibold outline-none"><option value="lt1y">1 年以内</option><option value="1to3y">1–3 年</option><option value="gt3y">3 年以上</option></select></label>
            <div className="rounded-2xl border border-slate-200 p-4"><div className="flex items-center justify-between"><span className="text-xs font-semibold text-slate-500">计划与金额</span><select value={purchasePlan} onChange={(event) => setPurchasePlan(event.target.value as PurchasePlan)} className="bg-transparent text-xs font-semibold outline-none"><option value="sip">定投</option><option value="lump_sum">一次性</option></select></div><input data-testid="market-planned-amount-input" value={plannedAmount} onChange={(event) => setPlannedAmount(event.target.value)} className="mt-2 w-full bg-transparent text-sm font-semibold outline-none" placeholder="请输入计划金额" /><p className="mt-1 text-[11px] text-slate-500">计划金额用于起购/定投起点/限购执行门禁</p></div>
          </div>
        </section>

        <section className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
          <article data-testid="market-decision-explainer" className="rounded-[24px] border border-slate-900/10 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Decision quality</p><h2 className="mt-2 text-xl font-semibold">当前页决策质量解释</h2></div><span className="rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold text-white">{marketDecisionExplainer.qualityLabel}</span></div>
            <p className="mt-4 text-sm leading-6 text-slate-600">{marketDecisionExplainer.qualityDetail}{materialLoading ? ' 材料核验上下文正在刷新。' : ''}</p>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">{[['可行动比例', `${marketDecisionExplainer.actionableRatio}%`], ['金额门禁阻断', marketDecisionExplainer.amountBlockedCount], ['材料阻断', marketDecisionExplainer.salesRuleBlockedCount], ['适当性冲突', marketDecisionExplainer.suitabilityMismatchCount]].map(([label, value]) => <div key={label} className="rounded-xl bg-slate-50 p-3"><div className="text-[11px] text-slate-500">{label}</div><div className="mt-1 font-semibold">{value}</div></div>)}</div>
            <p className="mt-4 text-xs leading-5 text-slate-500">为什么先看它：{marketDecisionExplainer.topFundCopy}。{marketDecisionExplainer.sortExplanation}</p>
            <Link href={marketDecisionExplainer.primaryAction.href} className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-emerald-700">{marketDecisionExplainer.primaryAction.label}<ArrowRight className="h-4 w-4" /></Link>
          </article>

          <article data-testid="market-promotion-gate-audit" className="rounded-[24px] border border-slate-900/10 bg-[#ede8dc] p-5 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Promotion gate audit</p>
            <div className="mt-2 flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-xl font-semibold">全市场研究晋级队列</h2><p className="mt-1 text-sm text-slate-600">可横评 / 补材料核验 / 补持仓或费用 / 排除</p></div><span className="rounded-full bg-white px-3 py-1 text-xs font-semibold ring-1 ring-slate-200">{marketPromotionGateAudit.verdict}</span></div>
            <p className="mt-4 text-sm font-medium">主阻断：{marketPromotionGateAudit.primaryBlocker}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-white px-3 py-1">正式路径阻断 {marketPromotionGateAudit.formalBlockedCount} 条</span><span className="rounded-full bg-white px-3 py-1">金额门禁 {marketPromotionGateAudit.amountGateCount} 条</span><span className="rounded-full bg-white px-3 py-1">可行动比例 {marketPromotionGateAudit.actionableRatio}%</span></div>
            <p className="mt-4 text-xs leading-5 text-slate-600">只服务基金研究证据；缺证不加分；R1-R5 缺失、无来源或过期一律阻断正式路径。</p>
            <Link href={marketPromotionGateAudit.primaryHref} className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-slate-950">处理主阻断<ArrowRight className="h-4 w-4" /></Link>
          </article>
        </section>

        <section className="rounded-[24px] border border-slate-900/10 bg-white shadow-sm">
          <div className="flex flex-col gap-4 border-b border-slate-100 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Market ranking</p><h2 className="mt-1 text-xl font-semibold">基金排行</h2><p className="mt-1 text-sm text-slate-500">{loading ? '正在刷新真实数据' : `共 ${total.toLocaleString('zh-CN')} 只 · 第 ${page}/${totalPages} 页`}</p></div>
            <div className="flex flex-wrap gap-2"><button type="button" onClick={() => setShareClassDisplayMode('merged')} className={`rounded-full px-3 py-1.5 text-xs font-semibold ${shareClassDisplayMode === 'merged' ? 'bg-slate-950 text-white' : 'bg-slate-100 text-slate-600'}`}>按基金合并</button><button type="button" onClick={() => setShareClassDisplayMode('expanded')} className={`rounded-full px-3 py-1.5 text-xs font-semibold ${shareClassDisplayMode === 'expanded' ? 'bg-slate-950 text-white' : 'bg-slate-100 text-slate-600'}`}>展开份额</button><button type="button" data-testid="market-copy-current-page-tsv" onClick={() => void copyMarketCurrentPageTsv()} className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-semibold">复制当前页 TSV</button><button type="button" data-testid="market-export-current-page" onClick={downloadMarketCurrentPageTsv} className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1.5 text-xs font-semibold"><Download className="h-3.5 w-3.5" />导出当前页 TSV</button></div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-[1120px] w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="px-5 py-3">对比</th><th className="px-3 py-3">基金</th><th className="px-3 py-3">初筛</th><th className="px-3 py-3">收益 / 回撤</th><th className="px-3 py-3">规模</th><th className="px-3 py-3">适当性</th><th className="px-3 py-3">材料核验</th><th className="px-3 py-3">研究复核体检</th><th className="px-5 py-3 text-right">动作</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {displayFunds.map((fund) => {
                  const score = getMarketScreeningScore(fund)
                  const researchDecision = researchDecisionFor(fund)
                  const { formalGate: gate, suitability, material, checklist } = researchDecision
                  const shareClassInfo = shareClassInfoByCode.get(fund.windCode.toUpperCase())
                  const inPool = candidateMemberCodes.has(fund.windCode.toUpperCase())
                  const saving = savingCandidateCodes.has(fund.windCode)
                  return <tr key={fund.windCode} className="align-top hover:bg-slate-50/70">
                    <td className="px-5 py-4"><input type="checkbox" checked={selectedCompareCodes.includes(fund.windCode)} onChange={() => toggleCompare(fund.windCode)} aria-label={`选择 ${fund.name}`} /></td>
                    <td className="px-3 py-4"><Link href={fundDetailHref(fund)} className="font-semibold text-slate-950 hover:text-emerald-700">{fund.name}</Link><div className="mt-1 text-xs text-slate-500">{fund.windCode} · {fund.type || '类型待补'}</div>{shareClassInfo?.siblingCount ? <div className="mt-2 inline-flex rounded-full bg-amber-50 px-2 py-1 text-[11px] text-amber-800">已合并 · 同基金 {shareClassInfo.siblingCount + 1} 份额</div> : null}</td>
                    <td className="px-3 py-4"><div className="font-semibold">{score.isAvailable ? score.total : '数据待补'}</div><div className="mt-1 text-xs text-slate-500">{score.grade} · {score.label}</div></td>
                    <td className="px-3 py-4"><div className="font-medium">{formatPercent(getReturn1y(fund))}</div><div className="mt-1 text-xs text-slate-500">回撤 {formatPercent(getMaxDrawdown1y(fund))} · 夏普 {formatNumber(getSharpe1y(fund))}</div></td>
                    <td className="px-3 py-4"><div>{formatAsset(numberValue(fund.totalAsset))}</div><div className="mt-1 text-xs text-slate-500">持仓 {holdingCount(fund) || '待补'} 条</div></td>
                    <td className="px-3 py-4"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${suitability.status === 'matched' ? 'bg-emerald-50 text-emerald-700' : suitability.status === 'mismatch' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-800'}`}>{suitability.label}</span><div data-testid="market-row-amount-gate" className="mt-2 text-[11px] text-slate-500">{material.executionAmountGate?.label || '金额门槛待扫描'}</div></td>
                    <td className="px-3 py-4"><div className="text-sm font-medium">{material.label}</div><div className="mt-1 max-w-[220px] text-xs leading-5 text-slate-500">{material.missingItems.slice(0, 2).join('、') || material.riskLevelEvidenceLabel}</div></td>
                    <td data-testid="market-row-research-checklist" className="px-3 py-4"><div data-testid="market-card-research-checklist" className="flex flex-wrap gap-1">{checklist.items.map((item) => <span key={item.key} title={item.detail} className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${item.status === 'ready' ? 'bg-emerald-50 text-emerald-700' : item.status === 'blocked' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-800'}`}>{item.label}</span>)}</div><div className="mt-2 text-[11px] text-slate-500">全市场底稿：{checklist.backendLabel}</div><div data-testid="market-row-formal-gate" className="mt-1 text-[11px] font-medium text-slate-700">{gate.reportLabel}</div><div data-testid="market-card-formal-gate" className="hidden">{gate.reportLabel}</div><div data-testid="market-card-amount-gate" className="hidden">{material.executionAmountGate?.label || '金额门槛待扫描'}</div></td>
                    <td className="px-5 py-4 text-right"><div className="flex justify-end gap-2"><button type="button" onClick={() => void saveFundToCandidatePool(fund)} disabled={inPool || saving || !researchDecision.formalGate.passed} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50">{saving ? '保存中' : inPool ? '已在观察池' : '加入观察池'}</button><Link href={fundDetailHref(fund)} className="rounded-lg bg-slate-950 px-3 py-2 text-xs font-semibold text-white">详情</Link></div></td>
                  </tr>
                })}
              </tbody>
            </table>
          </div>
          {!displayFunds.length ? <div className="p-10 text-center"><ShieldAlert className="mx-auto h-7 w-7 text-slate-400" /><p className="mt-3 text-sm font-semibold">当前筛选没有基金样本</p><p className="mt-1 text-sm text-slate-500">若使用适当性匹配池且为空，请打开风险等级补证队列。</p><Link href={riskLevelSourceAuditHref} className="mt-3 inline-flex text-sm font-semibold text-emerald-700">打开风险等级补证队列</Link></div> : null}
          <div className="flex items-center justify-between border-t border-slate-100 p-4"><button type="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))} className="rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:opacity-40">上一页</button><button type="button" disabled={page >= totalPages || loading} onClick={() => setPage((value) => Math.min(totalPages, value + 1))} className="rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:opacity-40">下一页</button></div>
        </section>

        {showResearchReview ? <section className="space-y-4">
          <div data-testid="market-research-checklist-aggregate" className="rounded-[24px] border border-slate-900/10 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Research checklist</p><h2 className="mt-1 text-xl font-semibold">全市场体检分布</h2><p className="mt-2 text-sm text-slate-500">后端全市场体检：{marketChecklistCoverageText}</p></div><div className="flex gap-2"><Link href={marketChecklistCompleteHref} className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">通过</Link><Link href={marketChecklistRepairHref} className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">待补</Link><Link href={marketChecklistBlockedHref} className="rounded-full bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-700">阻断</Link></div></div>
            <div data-testid="market-research-checklist-buckets" className="mt-4 flex flex-wrap gap-2">{marketChecklistTopGaps.map(([gap, count]) => <button key={gap} type="button" data-testid="market-research-checklist-gap-chip" onClick={() => drillIntoMarketChecklistGap(gap)} className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold">{gap} · {Number(count).toLocaleString('zh-CN')}</button>)}</div>
            <div data-testid="market-research-checklist-action-plan" className="mt-4 rounded-2xl bg-slate-50 p-4"><p className="text-sm font-semibold">首要缺口行动</p><p className="mt-1 text-xs leading-5 text-slate-500">{foundationManualFieldsForPlan}；{salesRuleEvidenceFields}。临门一脚代表只剩该字段或来源日期。</p><div className="mt-3 flex flex-wrap gap-2"><Link data-testid="market-research-checklist-top-gap-drill" href={marketChecklistQueueAction.primaryHref} className="rounded-lg bg-slate-950 px-3 py-2 text-xs font-semibold text-white">{marketChecklistQueueAction.primaryLabel}</Link><Link data-testid="market-checklist-gap-primary-action" href={marketChecklistQueueAction.primaryHref} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold">批量补基础数据</Link><Link data-testid="market-checklist-gap-secondary-action" href={marketChecklistQueueAction.secondaryHref} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold">{marketChecklistQueueAction.secondaryLabel}</Link><button data-testid="market-checklist-work-order-copy" type="button" onClick={() => void copyMarketChecklistWorkOrderTsv()} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold">复制工作单 TSV</button><button data-testid="market-checklist-work-order-download" type="button" onClick={downloadMarketChecklistWorkOrderTsv} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold">下载工作单 TSV</button></div></div>
          </div>

          <div data-testid="market-research-shortlist-scorecard" className="rounded-[24px] border border-slate-900/10 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Shortlist scorecard</p><h2 className="mt-1 text-xl font-semibold">研究短名单评分卡</h2><p className="mt-2 text-sm text-slate-500">短名单分 = 初筛分 + 材料核验/R1-R5 来源 + 计划金额执行门禁 + 当前画像适当性 + 研究证据状态</p></div><div className="flex gap-2"><button data-testid="market-copy-shortlist-tsv" type="button" onClick={() => void copyMarketShortlistTsv()} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold">复制短名单 TSV</button><button data-testid="market-download-shortlist-tsv" type="button" onClick={downloadMarketShortlistTsv} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold">下载短名单 TSV</button></div></div>
            <p className="mt-3 text-xs leading-5 text-slate-500">不绕过材料核验和适当性硬门禁；任何硬阻断都不会因为高收益或高初筛分被抬进研究清单。</p>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">{marketShortlist.topRows.map((row) => <article key={row.windCode} className={`rounded-2xl border p-4 ${marketShortlistLaneClassName(row.lane)}`}><div className="flex items-center justify-between gap-2"><span className="text-xs font-semibold">{row.laneLabel}</span><span className="text-lg font-semibold">{row.shortlistScore}</span></div><div className="mt-3 font-semibold">{row.name}</div><p className="mt-2 text-xs leading-5 text-slate-600">{row.mainReason}</p><Link href={row.href} className="mt-3 inline-flex text-xs font-semibold text-slate-950">{row.nextAction}<ArrowRight className="ml-1 h-3.5 w-3.5" /></Link></article>)}</div>
          </div>

          <div data-testid="market-promotion-queue" className="rounded-[24px] border border-slate-900/10 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-xl font-semibold">全市场研究晋级队列</h2><p className="mt-1 text-sm text-slate-500">聚焦当前分流；复制和下载 TSV 只包含当前聚焦分流，当前聚焦分流不改变硬门禁。</p></div><select data-testid="market-promotion-lane-filter" value={promotionLaneFocus} onChange={(event) => setPromotionLaneFocus(event.target.value as PromotionLaneFocus)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">{promotionLaneOptions.map((option) => <option key={option.key} value={option.key}>{option.label} ({option.count})</option>)}</select></div>
            <div className="mt-4 grid gap-3 lg:grid-cols-4">{focusedMarketPromotionLanes.map((lane) => <article key={lane.key} data-testid={promotionLaneTestId(lane.key)} className="rounded-2xl bg-slate-50 p-4"><h3 className="font-semibold">{lane.title}</h3><p className="mt-1 text-xs leading-5 text-slate-500">{lane.description}</p><div className="mt-3 space-y-2">{lane.rows.map((row) => <Link key={row.windCode} href={row.href} className="block rounded-xl bg-white p-3 ring-1 ring-slate-200"><div className="flex items-center justify-between gap-2 text-xs font-semibold"><span>{row.name}</span><span>{row.score}</span></div><p className="mt-1 text-[11px] leading-4 text-slate-500">{row.reason}</p></Link>)}</div><p className="mt-3 text-xs font-semibold">{lane.key === 'sales_rules' ? '本列补材料' : lane.key === 'exclude' ? '本列仅排除不入池' : lane.key === 'compare' ? '本列进入横评' : '本列补研究证据'}</p>{lane.key === 'evidence' ? <span className="sr-only">market-promotion-lane-evidence-compare</span> : null}</article>)}</div>
            <div className="mt-4 flex flex-wrap gap-2"><button data-testid="market-copy-promotion-tasks-tsv" type="button" onClick={() => void copyMarketPromotionTasksTsv()} disabled={!focusedMarketPromotionTaskRows.length} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold disabled:opacity-40">复制研究任务 TSV</button><button data-testid="market-download-promotion-tasks-tsv" type="button" onClick={downloadMarketPromotionTasksTsv} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold">下载研究任务 TSV</button><Link data-testid="market-promotion-compare-link" href={buildComparisonHref(marketPromotionQueue.promotionCompareCodes)} className="rounded-lg bg-slate-950 px-3 py-2 text-xs font-semibold text-white">打开可横评样本</Link></div>
          </div>

          <div data-testid="market-sales-rule-unlock-queue" className="rounded-[24px] border border-slate-900/10 bg-white p-5 shadow-sm"><h2 className="text-xl font-semibold">当前页研究解锁顺序</h2><p className="mt-2 text-sm text-slate-500">{reviewQueueRows.length ? `优先处理复查队列：涉及 ${reviewQueueRows.length} 条；先处理复查队列，再回到全市场严格重评。` : `正在扫描当前页基金的${salesRuleScanFieldsForPlan}。`}</p><div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{marketSalesRuleUnlockQueue.map((guide) => <Link key={guide.label} href={guide.href} className="rounded-2xl bg-slate-50 p-4"><div className="text-sm font-semibold">{guide.label}</div><div className="mt-2 text-2xl font-semibold">{guide.count}</div></Link>)}</div></div>

          <div data-testid="market-risk-source-audit-entry" className="rounded-[24px] border border-amber-200 bg-amber-50 p-5"><h2 className="text-xl font-semibold text-amber-950">R1-R5 来源可信度闸门</h2><p className="mt-2 text-sm leading-6 text-amber-900">Tushare fund_basic 不能作为 R1-R5 来源；补齐前不入池、不保存研究复核报告。</p><div className="mt-4 flex gap-2"><Link href={riskLevelSourceAuditHref} className="rounded-lg bg-amber-950 px-3 py-2 text-xs font-semibold text-white">高分缺口队列</Link><Link href={candidateRiskLevelSourceAuditHref} className="rounded-lg border border-amber-300 px-3 py-2 text-xs font-semibold text-amber-950">观察池缺口队列</Link></div></div>
        </section> : null}

        <section className="grid gap-4 xl:grid-cols-[0.85fr_1.15fr]">
          <article className="rounded-[24px] border border-slate-900/10 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Compare basket</p><h2 className="mt-1 text-xl font-semibold">智能研究横评篮</h2></div><span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold">{selectedCompareCodes.length}/{COMPARE_BASKET_LIMIT}</span></div>
            <p className="mt-3 text-sm leading-6 text-slate-500">优先选择非阻断、风险适当性不冲突的样本。金额不匹配 {compareBasketSalesRuleGate.amountBlockedFunds} 只。{compareBasketFormalActionsBlocked ? ' 先处理金额门禁。' : ''}</p>
            <div className="mt-4 flex flex-wrap gap-2">{selectedCompareCodes.map((code) => <button key={code} type="button" onClick={() => toggleCompare(code)} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold">{code}<X className="h-3 w-3" /></button>)}</div>
            <div className="mt-4 flex flex-wrap gap-2"><button data-testid="market-smart-compare-basket" type="button" onClick={() => setSelectedCompareCodes(smartCompareCandidates)} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold">智能选择</button><Link data-testid="market-smart-compare-link" href={selectedCompareCodes.length >= 2 ? buildComparisonHref(selectedCompareCodes) : withMarketResearchContext('/analysis/comparison', true)} className="rounded-lg bg-slate-950 px-3 py-2 text-xs font-semibold text-white">打开横评</Link></div>
          </article>

          <article data-testid="market-compare-basket-win-loss-lines" className="rounded-[24px] border border-slate-900/10 bg-[#17261f] p-5 text-white shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-200">Win / loss lines</p><h2 className="mt-1 text-xl font-semibold">对比篮胜负线与淘汰线</h2></div><span className="rounded-full bg-white/10 px-3 py-1 text-xs font-semibold">{compareBasketWinLossAudit.verdict}</span></div>
            <p className="mt-3 text-sm leading-6 text-slate-300">{compareBasketWinLossAudit.summary}</p>
            <div className="mt-4 grid gap-2 sm:grid-cols-3">{compareBasketWinLossRows.slice(0, 6).map((row) => <div key={row.windCode} className="rounded-xl bg-white/8 p-3 ring-1 ring-white/10"><div className="flex items-center justify-between gap-2 text-xs font-semibold"><span>{row.name}</span><span>{Math.round(row.researchScore)}</span></div><div className="mt-2 text-xs text-emerald-200">{row.lane}</div><p className="mt-1 text-[11px] leading-4 text-slate-400">{row.winLossLine}</p></div>)}</div>
            <p className="mt-4 text-xs leading-5 text-slate-400">字段级缺口不按中性分处理，硬阻断未解除前必须淘汰或降级。</p>
            <div className="mt-4 flex gap-2"><button data-testid="market-compare-basket-win-loss-copy" type="button" onClick={() => void copyCompareBasketWinLossTsv()} className="rounded-lg bg-white/10 px-3 py-2 text-xs font-semibold">复制胜负线 TSV</button><button data-testid="market-compare-basket-win-loss-download" type="button" onClick={downloadCompareBasketWinLossTsv} className="rounded-lg bg-white/10 px-3 py-2 text-xs font-semibold">下载胜负线 TSV</button></div>
          </article>
        </section>

        <section className="rounded-[24px] border border-slate-900/10 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-xl font-semibold">对比篮证据工作单</h2><p className="mt-1 text-sm text-slate-500">{compareBasketEvidenceResult.data?.nextAction || '继续选择至少 2 只基金。'}</p></div><div className="flex gap-2"><button data-testid="market-compare-basket-evidence-copy" type="button" onClick={() => void copyCompareBasketEvidenceTsv()} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold">复制对比篮 TSV</button><button data-testid="market-compare-basket-evidence-download" type="button" onClick={downloadCompareBasketEvidenceTsv} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold">下载对比篮 TSV</button></div></div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">{compareBasketEvidenceRows.map((row) => <Link key={row.windCode} href={row.fundDetailHref} className="rounded-2xl bg-slate-50 p-4"><div className="flex items-center justify-between gap-2"><span className="font-semibold">{row.name}</span><ExternalLink className="h-4 w-4 text-slate-400" /></div><div className="mt-2 text-xs text-slate-500">{row.formalGate}</div><p className="mt-2 text-xs leading-5 text-slate-600">{row.nextAction}</p></Link>)}</div>
        </section>

        <section data-testid="market-suitability-impact-health" className="grid gap-4 md:grid-cols-2">
          <article className="rounded-[24px] border border-slate-900/10 bg-white p-5 shadow-sm"><div className="flex items-center gap-2"><CheckCircle2 className="h-5 w-5 text-emerald-600" /><h2 className="text-lg font-semibold">全市场适当性覆盖健康</h2></div><p className="mt-3 text-sm text-slate-600">风险等级覆盖率 {formatNumber(numberValue(suitabilityImpact?.coverage?.riskLevelCoverage), 1)}；销售风险等级缺失时，适当性匹配不能被推断为通过。</p><Link href={riskLevelSourceAuditHref} className="mt-3 inline-flex text-sm font-semibold text-emerald-700">查看来源审计<ArrowRight className="ml-1 h-4 w-4" /></Link></article>
          <article data-testid="market-research-roadmap" className="rounded-[24px] border border-slate-900/10 bg-white p-5 shadow-sm"><div className="flex items-center gap-2"><Layers3 className="h-5 w-5 text-slate-700" /><h2 className="text-lg font-semibold">当前页研究复核路线图</h2></div><p className="mt-3 text-sm leading-6 text-slate-600">为什么先看它：先区分“可进入研究复核 / 先补销售规则 / 先补证/横评”。横评路线图样本只服务研究判断，不能进入正式研究短名单，直到硬缺口清零。</p></article>
        </section>

        <details className="rounded-[24px] border border-slate-900/10 bg-white p-5 shadow-sm"><summary className="cursor-pointer text-sm font-semibold">研究硬边界与恢复审计</summary><div className="mt-4 grid gap-2 md:grid-cols-2">{MARKET_RESEARCH_BOUNDARIES.map((item) => <p key={item} className="rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">{item}</p>)}</div><p className="mt-4 text-xs text-slate-500">本页模型：marketDecisionExplainer、marketShortlist、marketPromotionGateAudit、marketExportRows、researchChecklistLights（{researchChecklistLights.length} 组）、researchChecklistFirstGap（{researchChecklistFirstGap.filter(Boolean).length} 条）。</p><p className="mt-2 text-xs text-slate-500">计划敏感字段：salesRuleEvidenceFieldsForPlan、salesRuleScanFieldsForPlan、foundationManualFieldsForPlan。{formalReportError}。{salesRuleScanMessage}</p><p className="mt-2 break-all text-xs text-slate-500">兼容上下文：{EVIDENCE_COVERAGE_PRESET.label} · {genericRiskLevelSourceAuditHref} · {nestedReturnHref} · {batchSalesRulesHref}</p></details>
      </main>
    </div>
  )
}
