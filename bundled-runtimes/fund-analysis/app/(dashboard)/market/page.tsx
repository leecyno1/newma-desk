import { backendApiBaseUrl, toCamelFund } from '@/lib/backend-api'
import MarketBrowserClient from './MarketBrowserClient'

export const dynamic = 'force-dynamic'

const PAGE_SIZE = 30
const COMPARE_BASKET_LIMIT = 8
const RISK_PROFILES = ['conservative', 'balanced', 'aggressive'] as const
const INVESTMENT_HORIZONS = ['lt1y', '1to3y', 'gt3y'] as const
const PURCHASE_PLANS = ['lump_sum', 'sip'] as const
const SALES_RISK_FILTERS = ['matched', 'mismatch', 'missing', 'known'] as const
const RESEARCH_CHECKLIST_STATUSES = ['complete', 'repair', 'blocked'] as const
type SalesRiskFilter = '' | (typeof SALES_RISK_FILTERS)[number]
type ResearchChecklistStatus = '' | (typeof RESEARCH_CHECKLIST_STATUSES)[number]
const PROFILE_MAX_SALES_RISK_LEVEL: Record<(typeof RISK_PROFILES)[number], number> = {
  conservative: 2,
  balanced: 3,
  aggressive: 5,
}

const sortByMap: Record<string, string> = {
  updatedAt: 'updated_at',
  name: 'name',
  windCode: 'wind_code',
  nav: 'nav',
  totalAsset: 'total_asset',
  establishmentDate: 'establishment_date',
  return: 'return',
  risk: 'risk',
  sharpe: 'sharpe',
  fee: 'fee',
  screeningScore: 'screening_score',
  evidenceCoverage: 'evidence_coverage',
  researchChecklist: 'research_checklist',
}

function percentParamToDecimal(value: string) {
  if (!value) return ''
  const numberValue = Number(value)
  if (!Number.isFinite(numberValue)) return ''
  return String(numberValue / 100)
}

function enumParam<T extends readonly string[]>(value: string, allowed: T, fallback: T[number]): T[number] {
  return allowed.includes(value) ? value as T[number] : fallback
}

function codeListParam(value: string) {
  return Array.from(new Set(value.split(',').map((code) => code.trim().toUpperCase()).filter(Boolean))).slice(0, COMPARE_BASKET_LIMIT)
}

function salesRiskFilterParam(value: string): SalesRiskFilter {
  return SALES_RISK_FILTERS.includes(value as (typeof SALES_RISK_FILTERS)[number])
    ? value as SalesRiskFilter
    : ''
}

function researchChecklistStatusParam(value: string): ResearchChecklistStatus {
  return RESEARCH_CHECKLIST_STATUSES.includes(value as (typeof RESEARCH_CHECKLIST_STATUSES)[number])
    ? value as ResearchChecklistStatus
    : ''
}

function plannedAmountParam(value: string) {
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? value : ''
}

export default async function MarketBrowserPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const query = await searchParams
  const getParam = (key: string) => {
    const value = query[key]
    return Array.isArray(value) ? value[0] || '' : value || ''
  }
  const initialFilters = {
    search: getParam('search'),
    type: getParam('type'),
    assetMin: getParam('assetMin'),
    assetMax: getParam('assetMax'),
    establishedFrom: getParam('establishedFrom'),
    establishedTo: getParam('establishedTo'),
    evidenceStatus: getParam('evidenceStatus') as '' | 'ready' | 'verify' | 'blocked',
    hasManager: getParam('hasManager'),
    minManagerYears: getParam('minManagerYears'),
    hasFee: getParam('hasFee'),
    feeMax: getParam('feeMax'),
    tradableOnly: getParam('tradableOnly') || 'true',
    return1yMin: getParam('return1yMin'),
    maxDrawdown1yMax: getParam('maxDrawdown1yMax'),
    sharpe1yMin: getParam('sharpe1yMin'),
    screeningScoreMin: getParam('screeningScoreMin'),
    evidenceCoverageMin: getParam('evidenceCoverageMin'),
    researchChecklistStatus: researchChecklistStatusParam(getParam('researchChecklistStatus')),
    researchChecklistGap: getParam('researchChecklistGap'),
    salesRuleComplete: getParam('salesRuleComplete'),
    salesRiskFilter: salesRiskFilterParam(getParam('salesRiskFilter')),
    hasNav: getParam('hasNav'),
    hasPerformance: getParam('hasPerformance'),
    hasHoldings: getParam('hasHoldings'),
    sortBy: getParam('sortBy') || 'totalAsset',
    sortOrder: getParam('sortOrder') === 'asc' ? 'asc' : 'desc' as 'asc' | 'desc',
    riskProfile: enumParam(getParam('profile'), RISK_PROFILES, 'balanced'),
    investmentHorizon: enumParam(getParam('horizon'), INVESTMENT_HORIZONS, '1to3y'),
    purchasePlan: enumParam(getParam('purchasePlan'), PURCHASE_PLANS, 'sip'),
    plannedAmount: plannedAmountParam(getParam('plannedAmount')),
    compareCodes: codeListParam(getParam('compare')),
    source: getParam('source'),
    funnelStage: getParam('funnelStage'),
    returnTo: getParam('returnTo'),
  }
  const pageParam = Number(getParam('page') || '1')
  const initialPage = Number.isFinite(pageParam) && pageParam > 0 ? Math.floor(pageParam) : 1
  let initialFunds = []
  let initialTotal = 0
  let initialTotalPages = 1
  let initialSummary = {}

  try {
    const params = new URLSearchParams({
      page: initialPage.toString(),
      page_size: PAGE_SIZE.toString(),
      sort_by: sortByMap[initialFilters.sortBy] || 'updated_at',
      sort_order: initialFilters.sortOrder,
    })
    if (initialFilters.search) params.set('keyword', initialFilters.search)
    if (initialFilters.type) params.set('fund_type', initialFilters.type)
    if (initialFilters.assetMin) params.set('asset_min', initialFilters.assetMin)
    if (initialFilters.assetMax) params.set('asset_max', initialFilters.assetMax)
    if (initialFilters.establishedFrom) params.set('established_from', initialFilters.establishedFrom)
    if (initialFilters.establishedTo) params.set('established_to', initialFilters.establishedTo)
    if (initialFilters.evidenceStatus) params.set('evidence_status', initialFilters.evidenceStatus)
    if (initialFilters.hasManager) params.set('has_manager', initialFilters.hasManager)
    if (initialFilters.minManagerYears) params.set('min_manager_years', initialFilters.minManagerYears)
    if (initialFilters.hasFee) params.set('has_fee', initialFilters.hasFee)
    if (initialFilters.feeMax) params.set('fee_max', initialFilters.feeMax)
    if (initialFilters.tradableOnly) params.set('tradable_only', initialFilters.tradableOnly)
    const return1yMinDecimal = percentParamToDecimal(initialFilters.return1yMin)
    const maxDrawdown1yMaxDecimal = percentParamToDecimal(initialFilters.maxDrawdown1yMax)
    if (return1yMinDecimal !== '') params.set('return_1y_min', return1yMinDecimal)
    if (maxDrawdown1yMaxDecimal !== '') params.set('max_drawdown_1y_max', maxDrawdown1yMaxDecimal)
    if (initialFilters.sharpe1yMin) params.set('sharpe_1y_min', initialFilters.sharpe1yMin)
    if (initialFilters.screeningScoreMin) params.set('screening_score_min', initialFilters.screeningScoreMin)
    if (initialFilters.evidenceCoverageMin) params.set('evidence_coverage_min', initialFilters.evidenceCoverageMin)
    if (initialFilters.researchChecklistStatus) params.set('research_checklist_status', initialFilters.researchChecklistStatus)
    if (initialFilters.researchChecklistGap) params.set('research_checklist_gap', initialFilters.researchChecklistGap)
    if (initialFilters.salesRuleComplete) params.set('sales_rule_complete', initialFilters.salesRuleComplete)
    params.set('purchase_plan', initialFilters.purchasePlan)
    if (initialFilters.plannedAmount) params.set('planned_amount', initialFilters.plannedAmount)
    if (initialFilters.salesRiskFilter) {
      params.set('sales_risk_filter', initialFilters.salesRiskFilter)
      if (initialFilters.salesRiskFilter === 'matched' || initialFilters.salesRiskFilter === 'mismatch') {
        params.set('max_sales_risk_level', String(PROFILE_MAX_SALES_RISK_LEVEL[initialFilters.riskProfile]))
      }
    }
    if (initialFilters.hasNav) params.set('has_nav', initialFilters.hasNav)
    if (initialFilters.hasPerformance) params.set('has_performance', initialFilters.hasPerformance)
    if (initialFilters.hasHoldings) params.set('has_holdings', initialFilters.hasHoldings)
    const response = await fetch(`${backendApiBaseUrl}/api/funds/?${params.toString()}`, {
      cache: 'no-store',
    })
    const payload = await response.json()

    if (response.ok) {
      initialFunds = (payload.funds || []).map(toCamelFund)
      initialTotal = Number(payload.total || 0)
      initialTotalPages = Math.max(1, Math.ceil(initialTotal / PAGE_SIZE))
      initialSummary = payload.summary || {}
    }
  } catch (error) {
    console.error('预取全市场基金失败:', error)
  }

  return (
    <MarketBrowserClient
      initialFunds={initialFunds}
      initialPage={initialPage}
      initialTotal={initialTotal}
      initialTotalPages={initialTotalPages}
      initialSummary={initialSummary}
      initialFilters={initialFilters}
    />
  )
}
