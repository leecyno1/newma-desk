import { NextResponse } from 'next/server'
import { backendApiBaseUrl, toCamelFund } from '@/lib/backend-api'

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

function percentParamToDecimal(value: string | null) {
  if (!value) return ''
  const numberValue = Number(value)
  if (!Number.isFinite(numberValue)) return ''
  return String(numberValue / 100)
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const backendParams = new URLSearchParams({
      page: searchParams.get('page') || '1',
      page_size: searchParams.get('limit') || '20',
      sort_by: sortByMap[searchParams.get('sortBy') || 'updatedAt'] || 'updated_at',
      sort_order: searchParams.get('sortOrder') || 'desc',
    })

    const search = searchParams.get('search')
    const type = searchParams.get('type')
    const assetMin = searchParams.get('assetMin')
    const assetMax = searchParams.get('assetMax')
    const establishedFrom = searchParams.get('establishedFrom')
    const establishedTo = searchParams.get('establishedTo')
    const evidenceStatus = searchParams.get('evidenceStatus')
    const hasManager = searchParams.get('hasManager')
    const minManagerYears = searchParams.get('minManagerYears')
    const hasFee = searchParams.get('hasFee')
    const feeMax = searchParams.get('feeMax')
    const tradableOnly = searchParams.get('tradableOnly')
    const return1yMin = searchParams.get('return1yMin')
    const maxDrawdown1yMax = searchParams.get('maxDrawdown1yMax')
    const sharpe1yMin = searchParams.get('sharpe1yMin')
    const screeningScoreMin = searchParams.get('screeningScoreMin')
    const evidenceCoverageMin = searchParams.get('evidenceCoverageMin')
    const researchChecklistStatus = searchParams.get('researchChecklistStatus')
    const researchChecklistGap = searchParams.get('researchChecklistGap')
    const salesRuleComplete = searchParams.get('salesRuleComplete')
    const purchasePlan = searchParams.get('purchasePlan') === 'lump_sum' ? 'lump_sum' : 'sip'
    const plannedAmount = Number(searchParams.get('plannedAmount') || '')
    const safePlannedAmount = Number.isFinite(plannedAmount) && plannedAmount > 0 ? plannedAmount : null
    const maxSalesRiskLevel = searchParams.get('maxSalesRiskLevel')
    const salesRiskFilter = searchParams.get('salesRiskFilter')
    const hasNav = searchParams.get('hasNav')
    const hasPerformance = searchParams.get('hasPerformance')
    const hasHoldings = searchParams.get('hasHoldings')
    const return1yMinDecimal = percentParamToDecimal(return1yMin)
    const maxDrawdown1yMaxDecimal = percentParamToDecimal(maxDrawdown1yMax)

    if (search) backendParams.set('keyword', search)
    if (type) backendParams.set('fund_type', type)
    if (assetMin) backendParams.set('asset_min', assetMin)
    if (assetMax) backendParams.set('asset_max', assetMax)
    if (establishedFrom) backendParams.set('established_from', establishedFrom)
    if (establishedTo) backendParams.set('established_to', establishedTo)
    if (evidenceStatus) backendParams.set('evidence_status', evidenceStatus)
    if (hasManager) backendParams.set('has_manager', hasManager)
    if (minManagerYears) backendParams.set('min_manager_years', minManagerYears)
    if (hasFee) backendParams.set('has_fee', hasFee)
    if (feeMax) backendParams.set('fee_max', feeMax)
    if (tradableOnly) backendParams.set('tradable_only', tradableOnly)
    if (return1yMinDecimal !== '') backendParams.set('return_1y_min', return1yMinDecimal)
    if (maxDrawdown1yMaxDecimal !== '') backendParams.set('max_drawdown_1y_max', maxDrawdown1yMaxDecimal)
    if (sharpe1yMin) backendParams.set('sharpe_1y_min', sharpe1yMin)
    if (screeningScoreMin) backendParams.set('screening_score_min', screeningScoreMin)
    if (evidenceCoverageMin) backendParams.set('evidence_coverage_min', evidenceCoverageMin)
    if (researchChecklistStatus) backendParams.set('research_checklist_status', researchChecklistStatus)
    if (researchChecklistGap) backendParams.set('research_checklist_gap', researchChecklistGap)
    if (salesRuleComplete) backendParams.set('sales_rule_complete', salesRuleComplete)
    backendParams.set('purchase_plan', purchasePlan)
    if (safePlannedAmount !== null) backendParams.set('planned_amount', String(safePlannedAmount))
    if (maxSalesRiskLevel) backendParams.set('max_sales_risk_level', maxSalesRiskLevel)
    if (salesRiskFilter) backendParams.set('sales_risk_filter', salesRiskFilter)
    if (hasNav) backendParams.set('has_nav', hasNav)
    if (hasPerformance) backendParams.set('has_performance', hasPerformance)
    if (hasHoldings) backendParams.set('has_holdings', hasHoldings)

    const response = await fetch(`${backendApiBaseUrl}/api/funds?${backendParams.toString()}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      const detail = payload.detail || payload.error
      return NextResponse.json(
        typeof detail === 'object' && detail !== null
          ? {
            error: detail.message || '获取基金列表失败',
            code: detail.code || 'backend_error',
            detail,
          }
          : { error: detail || '获取基金列表失败', code: response.status === 503 ? 'backend_unavailable' : 'backend_error' },
        { status: response.status }
      )
    }

    const page = Number(payload.page || searchParams.get('page') || 1)
    const limit = Number(payload.page_size || searchParams.get('limit') || 20)
    const total = Number(payload.total || 0)

    return NextResponse.json({
      data: (payload.funds || []).map(toCamelFund),
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.max(1, Math.ceil(total / limit)),
      },
      summary: payload.summary || {},
      source: payload.source || 'backend',
    })
  } catch (error) {
    console.error('获取基金列表失败:', error)
    return NextResponse.json(
      { error: '获取基金列表失败' },
      { status: 500 }
    )
  }
}
