import { backendApiBaseUrl } from '@/lib/backend-api'
import { materialEvidenceHref } from '@/lib/research-platform/routes'

export type InvestorRiskProfileKey = 'conservative' | 'balanced' | 'aggressive'
export type SalesRuleImpactPurchasePlan = 'lump_sum' | 'sip'

type FundListPayload = {
  total?: number
  funds?: Array<Record<string, unknown>>
}

export type SalesRuleSuitabilityImpactProfile = {
  key: InvestorRiskProfileKey
  label: string
  maxSalesRiskLevel: number
  matchedCount: number
  mismatchCount: number
  missingRiskCount: number
  knownRiskCount: number
  reopenableCount: number
  sampleFunds: Array<{
    windCode: string
    name: string
    type: string
    screeningScore: number | null
  }>
  actionHref: string
}

export type SalesRuleImpactPayload = {
  generatedAt: string
  source: string
  totalFunds: number
  profiles: SalesRuleSuitabilityImpactProfile[]
  summary: {
    riskLevelKnownCount: number
    riskLevelMissingCount: number
    riskLevelCoverage: number
    bestReopenProfile: InvestorRiskProfileKey | null
    totalReopenableSlots: number
  }
  nextActions: Array<{
    label: string
    detail: string
    href: string
    priority: 'high' | 'medium' | 'low'
  }>
}

const investorRiskProfiles: Array<{ key: InvestorRiskProfileKey; label: string; maxSalesRiskLevel: number }> = [
  { key: 'conservative', label: '稳健型', maxSalesRiskLevel: 2 },
  { key: 'balanced', label: '均衡型', maxSalesRiskLevel: 3 },
  { key: 'aggressive', label: '进取型', maxSalesRiskLevel: 5 },
]

const DEFAULT_PURCHASE_PLAN: SalesRuleImpactPurchasePlan = 'sip'
const DEFAULT_PLANNED_AMOUNTS: Record<SalesRuleImpactPurchasePlan, number> = {
  lump_sum: 10000,
  sip: 1000,
}

function numberValue(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function nullableNumber(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function percent(covered: number, total: number) {
  if (total <= 0) return 0
  return Math.round((covered / total) * 1000) / 10
}

function textValue(value: unknown, fallback = '') {
  if (value === null || value === undefined) return fallback
  return String(value)
}

function normalizePlannedAmount(value: unknown, purchasePlan: SalesRuleImpactPurchasePlan) {
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? Math.round(amount) : DEFAULT_PLANNED_AMOUNTS[purchasePlan]
}

function purchaseContextParams(purchasePlan: SalesRuleImpactPurchasePlan, plannedAmount: number) {
  return {
    purchasePlan,
    plannedAmount: String(plannedAmount),
    [purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount']: String(plannedAmount),
  }
}

async function fetchFundList(params: URLSearchParams): Promise<FundListPayload> {
  const response = await fetch(`${backendApiBaseUrl}/api/funds?${params.toString()}`, {
    cache: 'no-store',
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || '读取基金适当性影响失败')
  }
  return payload
}

async function fetchCount(params: URLSearchParams) {
  const payload = await fetchFundList(params)
  return numberValue(payload.total)
}

function baseParams(purchasePlan: SalesRuleImpactPurchasePlan, extra: Record<string, string> = {}) {
  const params = new URLSearchParams({
    page: '1',
    page_size: '1',
    sort_by: 'screening_score',
    sort_order: 'desc',
    purchase_plan: purchasePlan,
    ...extra,
  })
  return params
}

async function fetchProfileImpact(profile: typeof investorRiskProfiles[number], purchasePlan: SalesRuleImpactPurchasePlan, plannedAmount: number): Promise<SalesRuleSuitabilityImpactProfile> {
  const matchedParams = baseParams(purchasePlan, {
    sales_risk_filter: 'matched',
    max_sales_risk_level: String(profile.maxSalesRiskLevel),
  })
  const mismatchParams = baseParams(purchasePlan, {
    sales_risk_filter: 'mismatch',
    max_sales_risk_level: String(profile.maxSalesRiskLevel),
  })
  const missingParams = baseParams(purchasePlan, {
    sales_risk_filter: 'missing',
  })
  const knownParams = baseParams(purchasePlan, {
    sales_risk_filter: 'known',
  })
  const sampleParams = new URLSearchParams(missingParams)
  sampleParams.set('page_size', '5')

  const [matchedCount, mismatchCount, missingPayload, knownCount] = await Promise.all([
    fetchCount(matchedParams),
    fetchCount(mismatchParams),
    fetchFundList(sampleParams),
    fetchCount(knownParams),
  ])
  const missingRiskCount = numberValue(missingPayload.total)
  const sampleFunds = (missingPayload.funds || []).slice(0, 5).map((fund) => ({
    windCode: textValue(fund.wind_code ?? fund.windCode),
    name: textValue(fund.name),
    type: textValue(fund.type),
    screeningScore: nullableNumber(fund.screening_score ?? fund.screeningScore),
  })).filter((fund) => fund.windCode)

  const matchedReturnHref = `/market?${new URLSearchParams({
    salesRiskFilter: 'matched',
    profile: profile.key,
    sortBy: 'screeningScore',
    sortOrder: 'desc',
    ...purchaseContextParams(purchasePlan, plannedAmount),
  }).toString()}`
  const actionHref = materialEvidenceHref(new URLSearchParams({
    scope: 'market',
    focus: 'risk_level',
    queueMode: 'high_score_missing_risk',
    returnTo: matchedReturnHref,
    ...purchaseContextParams(purchasePlan, plannedAmount),
  }))

  return {
    ...profile,
    matchedCount,
    mismatchCount,
    missingRiskCount,
    knownRiskCount: knownCount,
    reopenableCount: missingRiskCount,
    sampleFunds,
    actionHref,
  }
}

export async function getSalesRuleImpact(
  purchasePlan: SalesRuleImpactPurchasePlan = DEFAULT_PURCHASE_PLAN,
  plannedAmountInput?: number | string | null,
): Promise<SalesRuleImpactPayload> {
  const plannedAmount = normalizePlannedAmount(plannedAmountInput, purchasePlan)
  const [totalFunds, profiles] = await Promise.all([
    fetchCount(baseParams(purchasePlan)),
    Promise.all(investorRiskProfiles.map((profile) => fetchProfileImpact(profile, purchasePlan, plannedAmount))),
  ])
  const riskLevelKnownCount = Math.max(...profiles.map((profile) => profile.knownRiskCount), 0)
  const riskLevelMissingCount = Math.max(...profiles.map((profile) => profile.missingRiskCount), 0)
  const bestProfile = [...profiles].sort((left, right) => {
    return right.reopenableCount - left.reopenableCount
      || left.maxSalesRiskLevel - right.maxSalesRiskLevel
  })[0]
  const totalReopenableSlots = profiles.reduce((sum, profile) => sum + profile.reopenableCount, 0)
  const bestReopenProfile = bestProfile && bestProfile.reopenableCount > 0 ? bestProfile.key : null
  const riskSourceHref = materialEvidenceHref(new URLSearchParams({
    scope: 'market',
    focus: 'risk_level',
    queueMode: 'high_score_missing_risk',
    ...purchaseContextParams(purchasePlan, plannedAmount),
  }))
  const matchedMarketHref = `/market?${new URLSearchParams({
    salesRiskFilter: 'matched',
    profile: 'balanced',
    sortBy: 'screeningScore',
    sortOrder: 'desc',
    ...purchaseContextParams(purchasePlan, plannedAmount),
  }).toString()}`
  const candidateRiskHref = materialEvidenceHref(new URLSearchParams({
    scope: 'market',
    focus: 'risk_level',
    queueMode: 'candidate_missing_risk',
    ...purchaseContextParams(purchasePlan, plannedAmount),
  }))
  const riskLevelOnlyHref = materialEvidenceHref(new URLSearchParams({
    scope: 'market',
    focus: 'risk_level',
    queueMode: 'risk_level_only',
    ...purchaseContextParams(purchasePlan, plannedAmount),
  }))
  const nextActions = [
    riskLevelMissingCount > 0
      ? {
          label: '先补全市场风险来源',
          detail: `当前 ${riskLevelMissingCount} 只基金缺 R1-R5 来源背书或来源已过期，适当性匹配池无法判断；先补高分样本的 R1-R5。`,
          href: riskSourceHref,
          priority: 'high' as const,
        }
      : {
          label: '复核适当性匹配池',
          detail: '当前全市场 R1-R5 来源背书缺口已清零，可回到全市场浏览器按画像筛选匹配池。',
          href: matchedMarketHref,
          priority: 'medium' as const,
        },
    {
      label: '查研究清单风险来源',
      detail: '优先处理已经进入研究流程的候选/观察基金，避免无来源或过期 R1-R5 让正式研究复核报告被硬门禁拦截。',
      href: candidateRiskHref,
      priority: 'high' as const,
    },
    {
      label: '找临门一脚样本',
      detail: '只看销售规则基本齐、主要缺 R1-R5 来源背书的基金，补完后最可能直接打开适当性匹配。',
      href: riskLevelOnlyHref,
      priority: 'medium' as const,
    },
  ]

  return {
    generatedAt: new Date().toISOString(),
    source: 'backend.funds.sales_risk_filter_source_backed_30d + local.fund_sales_rules',
    totalFunds,
    profiles,
    summary: {
      riskLevelKnownCount,
      riskLevelMissingCount,
      riskLevelCoverage: percent(riskLevelKnownCount, riskLevelKnownCount + riskLevelMissingCount),
      bestReopenProfile,
      totalReopenableSlots,
    },
    nextActions,
  }
}
