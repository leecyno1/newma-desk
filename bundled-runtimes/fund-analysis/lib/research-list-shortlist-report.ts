import { backendApiBaseUrl } from '@/lib/backend-api'
import { getSalesRuleGaps, type SalesRuleExecutionAmountGate, type SalesRuleGap } from '@/lib/sales-rule-gaps'
import { fetchActiveSalesRuleEvidenceAlertsForCodes, type ActiveSalesRuleEvidenceAlert } from '@/lib/sales-rule-review-alerts'
import { materialEvidenceHref } from '@/lib/research-platform/routes'
import {
  buildStrictRiskLevelSourcePolicy,
  strictRiskLevelSourcePolicyMarkdownLines,
  type StrictRiskLevelSourcePolicy,
} from '@/lib/report-risk-level-source-policy'

type PurchasePlan = 'lump_sum' | 'sip'

type ScoreBreakdownItem = {
  key?: string
  label: string
  score: number
  maxScore: number
  note?: string
}

type SourceDecisionEvidence = {
  latestConclusion?: string | null
  conclusion?: string | null
  nextAction?: string | null
  salesRuleStatus?: string | null
  hardBoundary?: string | null
  criteriaSummary?: string | null
  screeningScore?: number | null
  score?: number | null
  rank?: number | null
  rankInResult?: number | null
  label?: string | null
  gateLabel?: string | null
  gateDetail?: string | null
  dataGaps?: string[]
  costMissingItems?: string[]
  topBreakdown?: ScoreBreakdownItem[]
  reasons?: string[]
  scoreCaps?: string[]
  decisiveEdges?: string[]
  recheckTriggers?: string[]
  knockoutLines?: string[]
  nextActions?: string[]
}

type ScreeningCriterionTrace = {
  key?: string
  label: string
  status: 'matched' | 'missing' | 'outside' | string
  actual: string
  threshold: string
  source: string
  note?: string
}

type ScreeningDecisionTrace = {
  source?: string
  rankInResult?: number | null
  plannedAmountLabel?: string | null
  criteriaEvidence?: ScreeningCriterionTrace[]
  matchedCriteriaCount?: number
  missingCriteriaCount?: number
  outsideCriteriaCount?: number
  dataGaps?: string[]
  summary?: string
  nextResearchStep?: string
  hardBoundary?: string
}

type Pool = {
  id: string
  name?: string
  description?: string | null
}

function normalizePurchasePlan(value: unknown): PurchasePlan {
  return value === 'lump_sum' || value === 'sip' ? value : 'sip'
}

function defaultPlannedAmountForPlan(purchasePlan: PurchasePlan) {
  return purchasePlan === 'lump_sum' ? 10000 : 1000
}

function normalizePlannedAmount(value: unknown, purchasePlan: PurchasePlan) {
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? amount : defaultPlannedAmountForPlan(purchasePlan)
}

type PoolMember = {
  id?: string
  fund_id?: string
  fundId?: string
  fund_wind_code?: string
  fundWindCode?: string
  fund_name?: string
  fundName?: string
  fund_type?: string
  fundType?: string
  fund_total_asset?: number | string | null
  fundTotalAsset?: number | string | null
  status?: string
  reason?: string | null
  latest_conclusion?: string | null
  latestConclusion?: string | null
  next_review_date?: string | null
  nextReviewDate?: string | null
  risk_notes?: string | null
  riskNotes?: string | null
  evidence?: {
    source?: string
    ranking?: {
      lens?: string
      label?: string
      rank?: number
      score?: number
      rating?: string
      percentile?: number
      scoreBreakdown?: ScoreBreakdownItem[]
      scorePenalty?: string[]
      costEvidence?: {
        label?: string
        score?: number
        totalAnnualFee?: number | null
        managementFee?: number | null
        custodianFee?: number | null
        purchaseFeeRate?: number | null
        minPurchaseAmount?: number | null
        minSipAmount?: number | null
        hasRedemptionRules?: boolean
        missing?: string[]
        note?: string
      }
    }
    rankingDecision?: SourceDecisionEvidence | null
    screeningDecision?: SourceDecisionEvidence | null
    screeningDecisionTrace?: ScreeningDecisionTrace | null
    comparisonDecision?: SourceDecisionEvidence | null
    investorContext?: {
      profileLabel?: string
      horizonLabel?: string
      purchasePlanLabel?: string
      plannedAmount?: number | string | null
      plannedAmountLabel?: string | null
    }
    purchaseGate?: {
      level?: string
      label?: string
      evidenceGrade?: string
      hardBlocks?: string[]
      cautionFlags?: string[]
      mustVerifyBeforeBuy?: string[]
      suitabilityNotes?: string[]
    }
    buyEvidence?: {
      completenessScore?: number
      completenessLevel?: string
      requiredMissingCount?: number
      conclusion?: string
    } | null
    comparison?: {
      window?: string
      comparedCodes?: string[]
      professionalScore?: number | null
      professionalGrade?: string | null
      peerGroup?: string | null
      peerCount?: number | null
    } | null
    holdingExperience?: {
      label?: string
      score?: number
      sipFriendlyScore?: number
      drawdownStress?: number | null
      sampleStatus?: string
    } | null
    purchaseSimulation?: {
      months?: number | null
      observations?: number | null
    } | null
    formalReportGate?: {
      blocked?: boolean
      checkedAt?: string | null
      replay?: {
        months?: number | null
        observations?: number | null
      } | null
    } | null
  } | null
}

type DecisionBucket = 'ready' | 'verify_first' | 'blocked'

type PurchaseDecisionCard = {
  label: string
  primaryAction: string
  reasons: string[]
  reverseTriggers: string[]
}

type ReviewFreshnessEvidence = {
  status: 'missing' | 'overdue' | 'scheduled'
  label: string
  detail: string
  nextReviewDate: string | null
}

export type ShortlistReportItem = {
  memberId?: string
  windCode: string
  fundName: string
  fundType: string
  totalAsset: number | string | null
  status: string
  investorContext: string
  purchaseGateLabel: string
  evidenceGrade: string
  evidenceScore: number | null
  requiredMissingCount: number | null
  salesRuleMissingCount: number
  salesRuleMissingItems: string[]
  executionAmountGate: SalesRuleExecutionAmountGate | null
  decisionBucket: DecisionBucket
  decisionLabel: string
  conclusion: string
  riskNotes: string
  nextActions: string[]
  actionLinks: {
    fundDetail: string
    salesRules: string
    prePurchaseReport: string | null
    comparison: string | null
  }
  source: string
  rankingScore: number | null
  rankingRating: string
  rankingRank: number | null
  rankingPercentile: number | null
  scoreBreakdown: Array<{
    label: string
    score: number
    maxScore: number
    note?: string
  }>
  scorePenalty: string[]
  costEvidence: {
    label?: string
    score?: number
    totalAnnualFee?: number | null
    managementFee?: number | null
    custodianFee?: number | null
    purchaseFeeRate?: number | null
    minPurchaseAmount?: number | null
    minSipAmount?: number | null
    hasRedemptionRules?: boolean
    missing?: string[]
    note?: string
  } | null
  sourceDecisionLabel: string
  sourceDecisionLatestConclusion: string
  sourceDecisionNextAction: string
  sourceDecisionBullets: string[]
  sourceDecisionHardBoundary: string
  screeningTraceSummary: string
  screeningTraceCriteria: string[]
  screeningTraceHardBoundary: string
  screeningTraceSource: string
  reviewFreshnessStatus: ReviewFreshnessEvidence['status']
  reviewFreshnessLabel: string
  reviewFreshnessDetail: string
  decisionCard: PurchaseDecisionCard
}

export type ShortlistReportPayload = {
  source: string
  generatedAt: string
  pool: {
    id: string
    name: string
    description: string | null
  }
  status: string
  summary: {
    totalMembers: number
    readyCount: number
    verifyFirstCount: number
    blockedCount: number
    salesRuleGapCount: number
    highPriorityGapCount: number
    prePurchaseEvidenceGapCount: number
  }
  riskLevelSourcePolicy: StrictRiskLevelSourcePolicy
  actionLinks: {
    pool: string
    batchSalesRules: string
    comparison: string | null
  }
  purchasePlan: PurchasePlan
  plannedAmount: number
  members: ShortlistReportItem[]
  markdown: string
}

async function fetchPool(poolId: string) {
  const response = await fetch(`${backendApiBaseUrl}/api/fund-pools`, { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || '读取研究清单失败')
  }
  const pools = (payload.pools || []) as Pool[]
  return pools.find((pool) => pool.id === poolId) || { id: poolId, name: '研究清单', description: null }
}

async function fetchMembers(poolId: string, status: string) {
  const response = await fetch(
    `${backendApiBaseUrl}/api/fund-pools/${encodeURIComponent(poolId)}/members?status=${encodeURIComponent(status)}`,
    { cache: 'no-store' },
  )
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || '读取研究清单成员失败')
  }
  return (payload.members || []) as PoolMember[]
}

function codeOf(member: PoolMember) {
  return member.fund_wind_code || member.fundWindCode || member.fund_id || member.fundId || ''
}

function nameOf(member: PoolMember) {
  return member.fund_name || member.fundName || codeOf(member)
}

function evidenceContext(member: PoolMember) {
  const context = member.evidence?.investorContext
  return [context?.profileLabel, context?.horizonLabel, context?.purchasePlanLabel].filter(Boolean).join(' · ') || '画像待补'
}

function investorParams(member: PoolMember, format?: 'markdown') {
  const context = member.evidence?.investorContext
  const params = new URLSearchParams()
  if (format) params.set('format', format)
  if (context?.profileLabel === '稳健型') params.set('profile', 'conservative')
  if (context?.profileLabel === '均衡型') params.set('profile', 'balanced')
  if (context?.profileLabel === '进取型') params.set('profile', 'aggressive')
  if (context?.horizonLabel === '1年以内') {
    params.set('horizon', 'lt1y')
    params.set('months', '12')
  }
  if (context?.horizonLabel === '1-3年') {
    params.set('horizon', '1to3y')
    params.set('months', '12')
  }
  if (context?.horizonLabel === '3年以上') {
    params.set('horizon', 'gt3y')
    params.set('months', '36')
  }
  if (context?.purchasePlanLabel?.startsWith('一次性')) params.set('purchasePlan', 'lump_sum')
  if (context?.purchasePlanLabel === '每月定投' || context?.purchasePlanLabel === '定投') params.set('purchasePlan', 'sip')
  return params
}

function plannedAmountFromEvidence(member: PoolMember, fallbackPlan: PurchasePlan, fallbackAmount: number) {
  const amount = Number(member.evidence?.investorContext?.plannedAmount)
  return Number.isFinite(amount) && amount > 0 ? amount : fallbackAmount || defaultPlannedAmountForPlan(fallbackPlan)
}

function comparisonHref(member: PoolMember) {
  const windCode = codeOf(member)
  const comparedCodes = member.evidence?.comparison?.comparedCodes || []
  const codes = Array.from(new Set([windCode, ...comparedCodes].filter(Boolean)))
  if (codes.length < 2) return null
  const params = investorParams(member)
  const plan = memberPurchasePlan(member, 'sip')
  const amount = plannedAmountFromEvidence(member, plan, defaultPlannedAmountForPlan(plan))
  params.set('codes', codes.slice(0, 8).join(','))
  if (!params.get('purchasePlan')) params.set('purchasePlan', plan)
  params.set('plannedAmount', String(amount))
  params.set(plan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(amount))
  params.set('autoReplay', '1')
  return `/analysis/comparison?${params.toString()}`
}

function memberPurchasePlan(member: PoolMember, fallback: PurchasePlan) {
  const plan = investorParams(member).get('purchasePlan')
  return normalizePurchasePlan(plan || fallback)
}

function actionLinks(member: PoolMember, gap: SalesRuleGap | null, purchasePlan: PurchasePlan, plannedAmount: number) {
  const windCode = codeOf(member)
  const prePurchaseParams = investorParams(member, 'markdown')
  const memberPlan = memberPurchasePlan(member, purchasePlan)
  const memberAmount = plannedAmountFromEvidence(member, memberPlan, plannedAmount)
  if (!prePurchaseParams.get('purchasePlan')) prePurchaseParams.set('purchasePlan', memberPlan)
  prePurchaseParams.set('plannedAmount', String(memberAmount))
  prePurchaseParams.set(memberPlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(memberAmount))
  const salesRuleParams = new URLSearchParams({
    codes: windCode,
    purchasePlan: memberPlan,
    plannedAmount: String(memberAmount),
  })
  const fundDetailParams = investorParams(member)
  if (!fundDetailParams.get('purchasePlan')) fundDetailParams.set('purchasePlan', memberPlan)
  fundDetailParams.set('plannedAmount', String(memberAmount))
  fundDetailParams.set(memberPlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(memberAmount))
  const fundDetailQuery = fundDetailParams.toString()
  return {
    fundDetail: `/funds/${encodeURIComponent(windCode)}${fundDetailQuery ? `?${fundDetailQuery}` : ''}`,
    salesRules: materialEvidenceHref(salesRuleParams),
    prePurchaseReport: gap?.missingCount ? null : `/api/funds/${encodeURIComponent(windCode)}/pre-purchase-report?${prePurchaseParams.toString()}`,
    comparison: comparisonHref(member),
  }
}

function sourceDecisionEvidence(member: PoolMember) {
  const evidence = member.evidence
  const screeningTrace = evidence?.screeningDecisionTrace
  return evidence?.comparisonDecision || evidence?.rankingDecision || evidence?.screeningDecision || (screeningTrace ? {
    latestConclusion: screeningTrace.summary || '',
    nextAction: screeningTrace.nextResearchStep || '',
    hardBoundary: screeningTrace.hardBoundary || '',
    rankInResult: screeningTrace.rankInResult || null,
    dataGaps: screeningTrace.dataGaps || [],
    label: '筛选命中证据',
  } : null)
}

function sourceDecisionLabel(member: PoolMember) {
  const evidence = member.evidence
  if (evidence?.comparisonDecision) return '横评决策留痕'
  if (evidence?.rankingDecision) return '榜单决策留痕'
  if (evidence?.screeningDecision) return '筛选决策留痕'
  if (evidence?.screeningDecisionTrace) return '筛选条件证据留痕'
  return '来源决策留痕待补'
}

function screeningDecisionTrace(member: PoolMember) {
  return member.evidence?.screeningDecisionTrace || null
}

function screeningTraceCriteriaBullets(trace: ScreeningDecisionTrace | null) {
  return (trace?.criteriaEvidence || []).slice(0, 6).map((item) => {
    const statusLabel = item.status === 'matched' ? '命中' : item.status === 'missing' ? '待补' : item.status === 'outside' ? '未通过' : item.status
    return `${item.label}：实际 ${item.actual} / 阈值 ${item.threshold} / ${statusLabel} / 来源 ${item.source}${item.note ? `（${item.note}）` : ''}`
  })
}

function sourceDecisionBullets(decision: SourceDecisionEvidence | null, trace: ScreeningDecisionTrace | null = null) {
  if (!decision) return ['旧研究清单记录未留存筛选/榜单/横评来源决策，不能把入清单本身视作研究依据']
  return [
    decision.salesRuleStatus,
    decision.gateLabel ? `闸门：${decision.gateLabel}${decision.gateDetail ? `（${decision.gateDetail}）` : ''}` : '',
    decision.label ? `来源标签：${decision.label}` : '',
    decision.criteriaSummary ? `筛选条件：${decision.criteriaSummary}` : '',
    decision.screeningScore != null ? `筛选评分：${formatRankingScore(decision.screeningScore)}` : '',
    decision.score != null ? `来源评分：${formatRankingScore(decision.score)}` : '',
    decision.rankInResult != null ? `筛选排名：第 ${decision.rankInResult} 名` : '',
    decision.rank != null ? `横评/榜单排名：第 ${decision.rank} 名` : '',
    decision.costMissingItems?.length ? `成本缺口：${decision.costMissingItems.slice(0, 4).join('、')}` : '',
    decision.dataGaps?.length ? `基础数据待补：${decision.dataGaps.slice(0, 4).join('、')}` : '',
    trace?.summary ? `筛选证据摘要：${trace.summary}` : '',
    ...screeningTraceCriteriaBullets(trace).slice(0, 3),
    ...(decision.reasons || []).slice(0, 3),
    ...(decision.decisiveEdges || []).slice(0, 3),
    ...(decision.scoreCaps || []).slice(0, 2),
  ].filter(Boolean).slice(0, 8) as string[]
}

function sourceDecisionHardBoundary(decision: SourceDecisionEvidence | null) {
  if (!decision) return '缺少来源决策留痕时，只能作为待复核研究对象，不能进入正式研究候选。'
  return decision.hardBoundary || (decision.knockoutLines?.length ? decision.knockoutLines.slice(0, 3).join('；') : '')
}

function reviewDateText(member: PoolMember) {
  const value = String(member.next_review_date || member.nextReviewDate || '').trim()
  return value ? value.slice(0, 10) : ''
}

function reviewFreshnessEvidence(member: PoolMember): ReviewFreshnessEvidence {
  const nextReviewDate = reviewDateText(member)
  if (!nextReviewDate) {
    return {
      status: 'missing',
      label: '复查日待补',
      detail: '缺少下次复查日期，不能证明该研究结论仍在复核窗口内。',
      nextReviewDate: null,
    }
  }

  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const reviewDate = new Date(`${nextReviewDate}T00:00:00`)
  if (Number.isFinite(reviewDate.getTime()) && reviewDate < today) {
    const overdueDays = Math.max(1, Math.ceil((today.getTime() - reviewDate.getTime()) / 86400000))
    return {
      status: 'overdue',
      label: '复查日已过期',
      detail: `下次复查日 ${nextReviewDate} 已过期 ${overdueDays} 天；需更新净值、销售规则、同类比较和研究结论后再生成正式短名单。`,
      nextReviewDate,
    }
  }

  return {
    status: 'scheduled',
    label: '复查日在有效窗口内',
    detail: `下次复查日 ${nextReviewDate} 尚未到期；仍需在正式研究复核中复核销售平台实时规则。`,
    nextReviewDate,
  }
}

function nextActions(member: PoolMember, gap: SalesRuleGap | null) {
  const gate = member.evidence?.purchaseGate
  const comparisonCount = member.evidence?.comparison?.comparedCodes?.length || 0
  const costMissingCount = member.evidence?.ranking?.costEvidence?.missing?.length ?? (member.evidence?.ranking?.costEvidence ? 0 : 1)
  const formalGate = member.evidence?.formalReportGate
  const formalReplay = formalGate?.replay || member.evidence?.purchaseSimulation || null
  const replayMonths = Number(formalReplay?.months)
  const replayObservations = Number(formalReplay?.observations)
  const replayReady = Number.isFinite(replayMonths) && replayMonths > 0 && Number.isFinite(replayObservations) && replayObservations > 0
  const holdingExperienceReady = Boolean(member.evidence?.holdingExperience?.score || member.evidence?.holdingExperience?.sipFriendlyScore)
  const reviewFreshness = reviewFreshnessEvidence(member)
  const actions = [
    gap?.missingCount ? `补销售规则：${gap.missingItems.slice(0, 4).join('、')}` : '',
    ...(gate?.hardBlocks || []).map((item) => `处理硬阻断：${item}`),
    ...(gate?.cautionFlags || []).map((item) => `复核提示：${item}`),
    ...(gate?.mustVerifyBeforeBuy || []).map((item) => `研究必核：${item}`),
    comparisonCount >= 2 ? '' : '补同类替代对比',
    replayReady || holdingExperienceReady ? '' : '补持有回放/持有体验',
    formalGate && formalGate.blocked !== true && formalGate.checkedAt ? '' : '补正式研究复核报告门禁',
    costMissingCount > 0 ? '补成本证据' : '',
    member.evidence?.buyEvidence?.requiredMissingCount ? (gap?.missingCount ? '补销售规则后再生成研究复核一页纸报告' : '生成或更新研究复核一页纸报告') : '',
    member.latest_conclusion || member.latestConclusion ? '' : '补最新研究结论',
    reviewFreshness.status === 'missing' ? '设定下次复查日期' : '',
    reviewFreshness.status === 'overdue' ? `更新复查结论：${reviewFreshness.detail}` : '',
  ].filter(Boolean)
  return Array.from(new Set(actions)).slice(0, 6)
}

function decisionBucketFromSignals(item: {
  purchaseGateLabel: string
  nextActions: string[]
  salesRuleMissingCount: number
  requiredMissingCount: number | null
  executionAmountGate?: SalesRuleExecutionAmountGate | null
}): DecisionBucket {
  if (item.executionAmountGate?.status === 'blocked') return 'blocked'
  if (item.purchaseGateLabel.includes('阻断') || item.nextActions.some((action) => action.includes('硬阻断'))) return 'blocked'
  if (item.salesRuleMissingCount > 0 || (item.requiredMissingCount ?? 0) > 0) return 'verify_first'
  if (item.nextActions.some((action) => (
    action.includes('补同类替代对比')
    || action.includes('补持有回放')
    || action.includes('补正式研究复核报告门禁')
    || action.includes('补成本证据')
    || action.includes('补最新研究结论')
    || action.includes('设定下次复查日期')
    || action.includes('更新复查结论')
    || action.includes('生成或更新研究复核一页纸报告')
  ))) return 'verify_first'
  return 'ready'
}

function decisionLabel(bucket: DecisionBucket) {
  if (bucket === 'ready') return '可进入研究复核'
  if (bucket === 'blocked') return '暂不纳入研究候选'
  return '先补证再判断'
}

function purchaseDecisionCard(member: PoolMember, gap: SalesRuleGap | null, bucket: DecisionBucket): PurchaseDecisionCard {
  const evidence = member.evidence
  const costEvidence = evidence?.ranking?.costEvidence
  const comparison = evidence?.comparison
  const holdingExperience = evidence?.holdingExperience
  const hardBlocks = evidence?.purchaseGate?.hardBlocks || []
  const cautionFlags = evidence?.purchaseGate?.cautionFlags || []
  const verifyBeforeBuy = evidence?.purchaseGate?.mustVerifyBeforeBuy || []
  const requiredMissingCount = evidence?.buyEvidence?.requiredMissingCount ?? 0
  const executionAmountGate = gap?.executionAmountGate || null
  const costMissingCount = costEvidence?.missing?.length ?? (costEvidence ? 0 : 1)
  const comparisonCount = comparison?.comparedCodes?.length || 0
  const experienceReady = Boolean(holdingExperience?.score || holdingExperience?.sipFriendlyScore)
  const profileText = evidenceContext(member)

  const reasons = [
    gap?.missingCount
      ? `销售规则仍缺 ${gap.missingCount} 项：${gap.missingItems.slice(0, 3).join('、')}`
      : '销售规则硬缺口当前未检出；正式研究复核仍需复核销售平台实时开放、费率和限购',
    executionAmountGate?.status === 'blocked' ? `计划金额不可执行：${executionAmountGate.detail}` : '',
    comparisonCount >= 2
      ? `已有同画像横评：同组 ${comparisonCount} 只，样本来自 ${comparison?.window || '研究清单'}`
      : '同类替代比较不足，尚不能解释为什么选它而不是同类基金',
    experienceReady
      ? `持有体验已有评分：${holdingExperience?.label || '待命名'}，得分 ${holdingExperience?.score ?? '待补'}`
      : '缺少持有体验/持有回放证据，暂不能判断真实持有压力',
    costEvidence
      ? `成本证据：${costEvidence.label || '成本待补'}，成本分 ${costEvidence.score ?? 0}/10，缺口 ${costMissingCount} 项`
      : '缺排行榜成本快照，费率、定投、赎回、限购仍需补证',
    `研究画像：${profileText}；证据等级 ${evidence?.purchaseGate?.evidenceGrade || '-'}`,
  ].filter(Boolean).slice(0, 5)

  const reverseTriggers = [
    gap?.missingCount ? '销售规则硬缺口清零，并记录来源日期与平台字段' : '',
    executionAmountGate?.status === 'blocked' ? '调整计划金额或补充销售端起购/限购证据后重新核验' : '',
    requiredMissingCount > 0 ? '必补证据项清零，且研究复核报告可正式生成' : '',
    comparisonCount < 2 ? '完成至少 2 只同画像/同类型替代基金横评' : '',
    !experienceReady ? '补齐持有体验或持有回放，回撤不超过当前画像预算' : '',
    costMissingCount > 0 ? '补齐申购费、赎回费/持有期、定投起点和限购金额' : '',
    hardBlocks.length ? `硬阻断消失：${hardBlocks.slice(0, 2).join('；')}` : '',
    cautionFlags.length || verifyBeforeBuy.length ? '补证提示全部复核并留痕' : '',
  ].filter(Boolean).slice(0, 5)

  if (bucket === 'blocked') {
    return {
      label: '暂不进入研究判断',
      primaryAction: '先处理研究硬阻断，只保留研究观察',
      reasons,
      reverseTriggers,
    }
  }
  if (bucket === 'verify_first') {
    return {
      label: '先补证，暂不形成结论',
      primaryAction: '优先补销售规则、成本、横评和持有回放，再决定是否保留候选',
      reasons,
      reverseTriggers,
    }
  }
  return {
    label: '可进入研究清单复核',
    primaryAction: '进入横向比较和研究复核报告留痕，不自动生成申赎指令',
    reasons,
    reverseTriggers: reverseTriggers.length ? reverseTriggers : ['若销售平台规则、风险等级、费率或净值回撤发生变化，重新降级复核'],
  }
}

function formatRankingScore(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return Number(value).toFixed(0)
}

function formatRankingPercentile(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return `${Math.round(Number(value) * 100)}%`
}

function formatFee(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return `${Number(value).toFixed(2)}%`
}

function costEvidenceLine(member: ShortlistReportItem) {
  const cost = member.costEvidence
  if (!cost) return '- 入池成本证据：待补（建议从成本榜/排行榜重新入池或补充 evidence.ranking.costEvidence）'
  const managementCustodianFee = (cost.managementFee ?? null) === null || (cost.custodianFee ?? null) === null
    ? null
    : (cost.managementFee || 0) + (cost.custodianFee || 0)
  return `- 入池成本证据：${cost.label || '成本待补'}；成本分 ${cost.score ?? 0}/10；年费 ${formatFee(cost.totalAnnualFee)}；管理+托管 ${formatFee(managementCustodianFee)}；申购费 ${formatFee(cost.purchaseFeeRate)}；赎回规则 ${cost.hasRedemptionRules ? '已录入' : '待补'}；成本缺口 ${cost.missing?.length ? cost.missing.slice(0, 5).join('、') : '暂无'}`
}

function topScoreBreakdown(member: PoolMember) {
  return (member.evidence?.ranking?.scoreBreakdown || [])
    .slice()
    .sort((left, right) => Number(right.score || 0) - Number(left.score || 0))
    .slice(0, 5)
    .map((item) => ({
      label: item.label,
      score: Number(item.score || 0),
      maxScore: Number(item.maxScore || 0),
      note: item.note,
    }))
}

function amountGateGapForMember(
  member: PoolMember,
  gate: SalesRuleExecutionAmountGate | null | undefined,
  status: string,
): SalesRuleGap | null {
  if (gate?.status !== 'blocked') return null
  const windCode = codeOf(member)
  return {
    memberId: member.id,
    windCode,
    fundName: nameOf(member),
    fundType: member.fund_type || member.fundType || '',
    totalAsset: member.fund_total_asset ?? member.fundTotalAsset ?? null,
    status: member.status || status,
    priority: 'high',
    missingItems: [`计划金额执行门禁：${gate.label}`],
    missingCount: 1,
    evidenceMissingCount: 1,
    evidenceScore: null,
    purchaseGateLabel: '计划金额执行门禁阻断',
    investorContext: member.evidence?.investorContext || null,
    ruleUpdatedAt: null,
    ruleSourceUpdatedAt: null,
    riskLevel: null,
    riskLevelSourceBacked: false,
    riskLevelEvidenceStatus: 'missing',
    riskLevelEvidenceLabel: '金额门禁阻断',
    riskLevelEvidenceDetail: gate.detail,
    executionAmountGate: gate,
    nextAction: gate.detail,
  }
}

function unknownExecutionAmountGate(plannedAmount: number): SalesRuleExecutionAmountGate {
  return {
    plannedAmount,
    status: 'unknown',
    label: '金额门槛待补',
    detail: '销售规则/R1-R5复查事件未处理，不能证明计划金额满足起购、定投起点或限购。',
    advice: '先处理复查队列并补齐销售平台金额规则；未补前不能进入正式研究清单报告。',
    actionLabel: '处理复查队列',
    shortfallAmount: null,
    suggestedAmount: null,
    minPurchaseAmount: null,
    minSipAmount: null,
    dailyLimitAmount: null,
  }
}

function reviewAlertGapForMember(
  member: PoolMember,
  alerts: ActiveSalesRuleEvidenceAlert[],
  existingGap: SalesRuleGap | null,
  executionAmountGate: SalesRuleExecutionAmountGate | null | undefined,
  status: string,
  plannedAmount: number,
): SalesRuleGap | null {
  if (!alerts.length) return existingGap
  const windCode = codeOf(member)
  const alertMissingItems = alerts.map((alert) => `复查队列未解决：${alert.title}${alert.message ? `（${alert.message}）` : ''}`)
  const missingItems = Array.from(new Set([...(existingGap?.missingItems || []), ...alertMissingItems]))
  return {
    memberId: member.id,
    windCode,
    fundName: nameOf(member),
    fundType: member.fund_type || member.fundType || existingGap?.fundType || '',
    totalAsset: member.fund_total_asset ?? member.fundTotalAsset ?? existingGap?.totalAsset ?? null,
    status: member.status || status,
    priority: 'high',
    missingItems,
    missingCount: Math.max(existingGap?.missingCount || 0, missingItems.length),
    evidenceMissingCount: Math.max(existingGap?.evidenceMissingCount || 0, missingItems.length),
    evidenceScore: existingGap?.evidenceScore ?? null,
    purchaseGateLabel: '复查队列拦截',
    investorContext: member.evidence?.investorContext || existingGap?.investorContext || null,
    ruleUpdatedAt: existingGap?.ruleUpdatedAt || null,
    ruleSourceUpdatedAt: existingGap?.ruleSourceUpdatedAt || null,
    riskLevel: existingGap?.riskLevel || null,
    riskLevelSourceBacked: false,
    riskLevelEvidenceStatus: 'stale',
    riskLevelEvidenceLabel: 'R1-R5 复查待处理',
    riskLevelEvidenceDetail: '复查队列仍有未解决销售规则/R1-R5过期或待补事件，不能作为正式短名单证据。',
    executionAmountGate: existingGap?.executionAmountGate || executionAmountGate || unknownExecutionAmountGate(plannedAmount),
    nextAction: '先处理复查队列中的销售规则/R1-R5证据事件，再生成正式研究清单报告。',
  }
}

function buildMarkdown(payload: Omit<ShortlistReportPayload, 'markdown'>) {
  const readyMembers = payload.members.filter((member) => member.decisionBucket === 'ready')
  const verifyMembers = payload.members.filter((member) => member.decisionBucket === 'verify_first')
  const blockedMembers = payload.members.filter((member) => member.decisionBucket === 'blocked')
  const lines = [
    `# ${payload.pool.name} · 研究清单报告`,
    '',
    `- 生成时间：${payload.generatedAt}`,
    `- 成员状态：${payload.status}`,
    `- 研究方式/计划金额：${payload.purchasePlan === 'sip' ? '定投' : '一次性配置'} / ${payload.plannedAmount.toLocaleString('zh-CN')} 元`,
    `- 数据来源：${payload.source}`,
    `- 候选数量：${payload.summary.totalMembers}`,
    `- 可继续研究 / 先补证 / 阻断：${payload.summary.readyCount} / ${payload.summary.verifyFirstCount} / ${payload.summary.blockedCount}`,
    `- 销售规则缺口：${payload.summary.salesRuleGapCount} 只，其中高优先级 ${payload.summary.highPriorityGapCount} 只`,
    ...strictRiskLevelSourcePolicyMarkdownLines(payload.riskLevelSourcePolicy),
    `- 批量补销售规则：${payload.actionLinks.batchSalesRules}`,
    payload.actionLinks.comparison ? `- 横向对比：${payload.actionLinks.comparison}` : '- 横向对比：研究清单少于 2 只或证据不足，暂不生成链接',
    '',
    '## 研究决策分层',
    '',
    `- 可进入研究复核：${readyMembers.map((member) => `${member.fundName}(${member.windCode})`).join('、') || '暂无'}`,
    `- 先补证再判断：${verifyMembers.map((member) => `${member.fundName}(${member.windCode})`).join('、') || '暂无'}`,
    `- 暂不纳入研究候选：${blockedMembers.map((member) => `${member.fundName}(${member.windCode})`).join('、') || '暂无'}`,
    '',
    '## 短名单明细与入口',
    '',
  ]

  payload.members.forEach((member, index) => {
    lines.push(
      `### ${index + 1}. ${member.fundName}（${member.windCode}）`,
      '',
      `- 类型/规模：${member.fundType || '待补'} / ${member.totalAsset ?? '待补'} 亿`,
      `- 研究画像：${member.investorContext}`,
      `- 决策分层：${member.decisionLabel}`,
      `- 研究决策卡：${member.decisionCard.label}；${member.decisionCard.primaryAction}`,
      `- 当前判断依据：${member.decisionCard.reasons.join('；')}`,
      `- 结论反转条件：${member.decisionCard.reverseTriggers.length ? member.decisionCard.reverseTriggers.join('；') : '持续复核销售规则、净值回撤、费率和同类替代表现'}`,
      member.rankingScore != null
        ? `- 入清单评分：研究分 ${formatRankingScore(member.rankingScore)}；评级 ${member.rankingRating || '待补'}；榜单第 ${member.rankingRank ?? '待补'}；分位 ${formatRankingPercentile(member.rankingPercentile)}`
        : '- 入清单评分：待补（建议从排行榜入清单或补充 evidence.ranking）',
      member.scoreBreakdown.length
        ? `- 评分拆解：${member.scoreBreakdown.map((item) => `${item.label} ${formatRankingScore(item.score)}/${formatRankingScore(item.maxScore)}${item.note ? `（${item.note}）` : ''}`).join('；')}`
        : '- 评分拆解：待补',
      `- 扣分/封顶：${member.scorePenalty.length ? member.scorePenalty.join('；') : '暂无'}`,
      costEvidenceLine(member),
      `- 来源决策留痕：${member.sourceDecisionLabel}`,
      `- 来源结论：${member.sourceDecisionLatestConclusion || '待补'}`,
      `- 来源下一步：${member.sourceDecisionNextAction || '补来源页筛选/榜单/横评决策留痕'}`,
      `- 来源关键依据：${member.sourceDecisionBullets.length ? member.sourceDecisionBullets.join('；') : '待补'}`,
      `- 筛选条件证据：${member.screeningTraceCriteria.length ? member.screeningTraceCriteria.join('；') : '待补'}`,
      `- 筛选证据来源：${member.screeningTraceSource || '待补'}`,
      member.screeningTraceHardBoundary ? `- 筛选证据硬边界：${member.screeningTraceHardBoundary}` : '- 筛选证据硬边界：筛选命中只证明进入研究样本，不能替代销售规则、R1-R5、横评和研究复核报告。',
      `- 来源硬边界：${member.sourceDecisionHardBoundary || '销售规则、适当性、横评和研究证据未完成前，不进入正式研究候选。'}`,
      `- 研究闸门：${member.purchaseGateLabel}；证据 ${member.evidenceGrade}`,
      `- 计划金额执行门禁：${member.executionAmountGate?.label || '待核'}；${member.executionAmountGate?.detail || '未取得金额门禁扫描结果'}`,
      `- 销售规则缺口：${member.salesRuleMissingCount ? `${member.salesRuleMissingCount} 项（${member.salesRuleMissingItems.slice(0, 6).join('、')}）` : '未检测到硬缺口'}`,
      `- 研究结论：${member.conclusion || '待补'}`,
      `- 风险备注：${member.riskNotes || '待补'}`,
      `- 复查时效：${member.reviewFreshnessLabel}；${member.reviewFreshnessDetail}`,
      `- 下一步：${member.nextActions.length ? member.nextActions.join('；') : '进入研究复核一页纸'}`,
      `- 入口：基金详情 ${member.actionLinks.fundDetail}；销售规则 ${member.actionLinks.salesRules}；研究复核报告 ${member.actionLinks.prePurchaseReport || '补证后生成'}${member.actionLinks.comparison ? `；横向对比 ${member.actionLinks.comparison}` : ''}`,
      '',
    )
  })

  lines.push(
    '## 使用边界',
      '',
      '- 本报告只用于基金研究和研究复核，不构成投资建议。',
      '- 报告内“研究决策卡”只输出研究分层、证据缺口和反转条件，不输出申赎指令。',
      '- 销售规则来自本地已维护证据和研究清单缺口队列，形成正式研究结论前仍需复核销售平台实时状态。',
  )

  return lines.join('\n')
}

export async function buildResearchListShortlistReport(poolId: string, status = 'candidate', options: { purchasePlan?: PurchasePlan; plannedAmount?: number | null } = {}): Promise<ShortlistReportPayload> {
  const purchasePlan = normalizePurchasePlan(options.purchasePlan)
  const plannedAmount = normalizePlannedAmount(options.plannedAmount, purchasePlan)
  const [pool, members, gapPayload] = await Promise.all([
    fetchPool(poolId),
    fetchMembers(poolId, status),
    getSalesRuleGaps(status, 300, { purchasePlan, plannedAmount }),
  ])
  const activeSalesRuleEvidenceAlertsByCode = await fetchActiveSalesRuleEvidenceAlertsForCodes(members.map(codeOf))
  const gapsByCode = new Map(gapPayload.gaps.map((gap) => [gap.windCode, gap]))
  const rulesByCode = new Map(gapPayload.rules.map((rule) => [rule.windCode, rule]))

  members.forEach((member) => {
    const windCode = codeOf(member).toUpperCase()
    if (!windCode) return
    const alerts = activeSalesRuleEvidenceAlertsByCode.get(windCode.toUpperCase()) || []
    const mergedGap = reviewAlertGapForMember(member, alerts, gapsByCode.get(windCode) || null, rulesByCode.get(windCode)?.executionAmountGate, status, plannedAmount)
    if (mergedGap) gapsByCode.set(windCode, mergedGap)
  })

  const reportMembers = members.map((member) => {
    const windCode = codeOf(member).toUpperCase()
    const rule = rulesByCode.get(windCode) || null
    const gap = gapsByCode.get(windCode) || amountGateGapForMember(member, rule?.executionAmountGate, status)
    const actions = nextActions(member, gap)
    const ranking = member.evidence?.ranking
    const sourceDecision = sourceDecisionEvidence(member)
    const screeningTrace = screeningDecisionTrace(member)
    const reviewFreshness = reviewFreshnessEvidence(member)
    const baseItem = {
      memberId: member.id,
      windCode,
      fundName: nameOf(member),
      fundType: member.fund_type || member.fundType || '',
      totalAsset: member.fund_total_asset ?? member.fundTotalAsset ?? null,
      status: member.status || status,
      investorContext: evidenceContext(member),
      purchaseGateLabel: member.evidence?.purchaseGate?.label || '研究闸门待核',
      evidenceGrade: member.evidence?.purchaseGate?.evidenceGrade || '-',
      evidenceScore: member.evidence?.buyEvidence?.completenessScore ?? null,
      requiredMissingCount: member.evidence?.buyEvidence?.requiredMissingCount ?? null,
      salesRuleMissingCount: gap?.missingCount || 0,
      salesRuleMissingItems: gap?.missingItems || [],
      executionAmountGate: gap?.executionAmountGate || rule?.executionAmountGate || null,
      conclusion: member.latest_conclusion || member.latestConclusion || member.evidence?.buyEvidence?.conclusion || '',
      riskNotes: member.risk_notes || member.riskNotes || '',
      nextActions: actions,
      actionLinks: actionLinks(member, gap, purchasePlan, plannedAmount),
      source: member.evidence?.source || '研究清单',
      rankingScore: ranking?.score ?? null,
      rankingRating: ranking?.rating || '',
      rankingRank: ranking?.rank ?? null,
      rankingPercentile: ranking?.percentile ?? null,
      scoreBreakdown: topScoreBreakdown(member),
      scorePenalty: ranking?.scorePenalty || [],
      costEvidence: ranking?.costEvidence || null,
      sourceDecisionLabel: sourceDecisionLabel(member),
      sourceDecisionLatestConclusion: sourceDecision?.latestConclusion || sourceDecision?.conclusion || '',
      sourceDecisionNextAction: sourceDecision?.nextAction || sourceDecision?.nextActions?.[0] || '',
      sourceDecisionBullets: sourceDecisionBullets(sourceDecision, screeningTrace),
      sourceDecisionHardBoundary: sourceDecisionHardBoundary(sourceDecision),
      screeningTraceSummary: screeningTrace?.summary || '',
      screeningTraceCriteria: screeningTraceCriteriaBullets(screeningTrace),
      screeningTraceHardBoundary: screeningTrace?.hardBoundary || '',
      screeningTraceSource: screeningTrace?.source || '',
      reviewFreshnessStatus: reviewFreshness.status,
      reviewFreshnessLabel: reviewFreshness.label,
      reviewFreshnessDetail: reviewFreshness.detail,
    }
    const bucket = decisionBucketFromSignals(baseItem)
    const reportItem = {
      ...baseItem,
      decisionBucket: bucket,
      decisionLabel: decisionLabel(bucket),
      decisionCard: purchaseDecisionCard(member, gap, bucket),
    }
    return reportItem
  }).filter((member) => member.windCode)

  const sortedReportMembers = reportMembers.sort((left, right) => {
    const bucketWeight: Record<DecisionBucket, number> = { ready: 0, verify_first: 1, blocked: 2 }
    return bucketWeight[left.decisionBucket] - bucketWeight[right.decisionBucket]
      || right.salesRuleMissingCount - left.salesRuleMissingCount
      || (right.requiredMissingCount || 0) - (left.requiredMissingCount || 0)
      || left.windCode.localeCompare(right.windCode)
  })

  const salesRuleGapCodes = sortedReportMembers
    .filter((member) => member.salesRuleMissingCount > 0)
    .map((member) => member.windCode)
  const batchSalesRuleParams = new URLSearchParams()
  batchSalesRuleParams.set('purchasePlan', purchasePlan)
  batchSalesRuleParams.set('plannedAmount', String(plannedAmount))
  if (salesRuleGapCodes.length > 0) batchSalesRuleParams.set('codes', Array.from(new Set(salesRuleGapCodes)).join(','))

  const comparisonCodes = sortedReportMembers.map((member) => member.windCode).filter(Boolean).slice(0, 8)
  const poolComparisonParams = new URLSearchParams()
  if (comparisonCodes.length >= 2) {
    poolComparisonParams.set('codes', comparisonCodes.join(','))
    poolComparisonParams.set('profile', 'balanced')
    poolComparisonParams.set('horizon', '1to3y')
    poolComparisonParams.set('purchasePlan', purchasePlan)
    poolComparisonParams.set('plannedAmount', String(plannedAmount))
    poolComparisonParams.set(purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(plannedAmount))
    poolComparisonParams.set('autoReplay', '1')
  }

  const summary = {
    totalMembers: sortedReportMembers.length,
    readyCount: sortedReportMembers.filter((member) => member.decisionBucket === 'ready').length,
    verifyFirstCount: sortedReportMembers.filter((member) => member.decisionBucket === 'verify_first').length,
    blockedCount: sortedReportMembers.filter((member) => member.decisionBucket === 'blocked').length,
    salesRuleGapCount: sortedReportMembers.filter((member) => member.salesRuleMissingCount > 0).length,
    highPriorityGapCount: sortedReportMembers.filter((member) => {
      const gap = gapsByCode.get(member.windCode)
      return gap?.priority === 'high' || member.executionAmountGate?.status === 'blocked'
    }).length,
    prePurchaseEvidenceGapCount: sortedReportMembers.filter((member) => member.decisionBucket !== 'ready').length,
  }
  const riskLevelSourcePolicy = buildStrictRiskLevelSourcePolicy({
    sourceBacked: summary.salesRuleGapCount === 0 && sortedReportMembers.length > 0,
    scopeLabel: '研究清单成员',
    totalCount: sortedReportMembers.length,
    blockedCount: summary.salesRuleGapCount,
  })

  const payloadWithoutMarkdown = {
    source: 'backend.fund_pools_plus_local_sales_rule_gaps+local.alert_events.sales_rule_evidence',
    generatedAt: new Date().toISOString(),
    pool: {
      id: pool.id,
      name: pool.name || '研究清单',
      description: pool.description || null,
    },
    status,
    purchasePlan,
    plannedAmount,
    summary,
    riskLevelSourcePolicy,
    actionLinks: {
      pool: `/pools?status=${encodeURIComponent(status)}&purchasePlan=${purchasePlan}&plannedAmount=${encodeURIComponent(String(plannedAmount))}`,
      batchSalesRules: materialEvidenceHref(batchSalesRuleParams),
      comparison: comparisonCodes.length >= 2 ? `/analysis/comparison?${poolComparisonParams.toString()}` : null,
    },
    members: sortedReportMembers,
  }

  return {
    ...payloadWithoutMarkdown,
    markdown: buildMarkdown(payloadWithoutMarkdown),
  }
}
