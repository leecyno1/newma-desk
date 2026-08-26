import { buildShareClassInfoByCode, summarizeShareClassGroups, type ShareClassInfo } from '@/lib/share-class'
import {
  buildStrictRiskLevelSourcePolicy,
  type StrictRiskLevelSourcePolicy,
} from '@/lib/report-risk-level-source-policy'
import { renderFundComparisonMarkdown } from '@/lib/fund-comparison-report-markdown'
import {
  type ComparisonDecisiveAudit,
  type ComparisonWinLossLine,
} from '@/lib/comparison-decisive-audit'
import { comparisonResearchScoreTool } from '@/lib/research-platform/tools/comparison-research-score'
import { comparisonResearchSummaryTool } from '@/lib/research-platform/tools/comparison-research-summary'
import { comparisonWinLossAuditTool } from '@/lib/research-platform/tools/comparison-win-loss-audit'
import { peerGroupBenchmarkTool, type PeerBenchmarkClassification } from '@/lib/research-platform/tools/peer-group-benchmark'

type RiskProfile = 'conservative' | 'balanced' | 'aggressive'
type InvestmentHorizon = 'lt1y' | '1to3y' | 'gt3y'
type PurchasePlan = 'lump_sum' | 'sip'

type FundSummary = {
  id?: string | null
  wind_code: string
  name: string
  type?: string | null
  peer_group?: string | null
  primary_benchmark?: string | null
  peer_count?: number | null
  professional_score?: number | null
  professional_grade?: string | null
  operation_status?: {
    status?: 'blocked' | 'watch' | 'unknown'
    label?: string
    reason?: string
  } | null
  sales_status?: {
    purchase_start_date?: string | null
    redeem_start_date?: string | null
  } | null
  fee_info?: {
    management_fee?: number | null
    custodian_fee?: number | null
    missing?: string[]
  } | null
  buy_evidence?: {
    completenessScore?: number
    completenessLevel?: 'strong' | 'partial' | 'thin'
    requiredMissingCount?: number
    conclusion?: string
  } | null
}

type MatrixValue = {
  value: number | null
  display: string
  peer_percentile: number | null
}

type MatrixRow = {
  metric_name: string
  label: string
  direction: 'higher' | 'lower'
  best_code: string | null
  values: Record<string, MatrixValue>
}

export type ComparisonMatrix = {
  metric_window: string
  funds: FundSummary[]
  matrix_rows: MatrixRow[]
  recommendations: string[]
}

export type SimulationResult = {
  windCode: string
  name: string
  status: 'ok' | 'error'
  simulation?: {
    source: string
    period: {
      startDate: string
      endDate: string
      observations: number
    }
    lumpSum: {
      returnRate: number | null
      maxDrawdown: number | null
      profit: number
    }
    sip: {
      returnRate: number | null
      maxAccountDrawdown: number | null
      profit: number
      contributionCount: number
    }
    feeAdjusted?: {
      coverage: 'none' | 'partial' | 'full'
      missingItems: string[]
      assumptions?: {
        purchaseFeeRate?: number | null
        redemptionFeeRules?: Array<{ label: string; feeRate: number; holdingDays: number | null }>
        salesRulePlatform?: string | null
      }
      lumpSum: null | {
        returnRate: number | null
        totalFee: number
        profit: number
      }
      sip: null | {
        returnRate: number | null
        totalFee: number
        profit: number
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
    evidenceGate?: {
      status: 'pass' | 'verify_first'
      label: string
      summary: string
      hardBoundary: string
      purchasePlan: PurchasePlan
      maxDrawdownTolerance: number | null
      feeCoverage: 'none' | 'partial' | 'full'
      missingEvidence: string[]
      plannedReplayAmount: number
      replayInvested: number
      replayDrawdown: number | null
      stressDrawdown: number
      estimatedLoss: number | null
      recoveryDays: number | null
      reasons: string[]
      actions: string[]
    }
	  }
  error?: string
}

export type SalesRuleGap = {
  windCode: string
  fundName?: string
  priority?: 'high' | 'medium' | 'low'
  missingItems?: string[]
  missingCount?: number
  nextAction?: string
}

type ComparisonContext = {
  profile: RiskProfile
  profileLabel: string
  horizon: InvestmentHorizon
  horizonLabel: string
  purchasePlan: PurchasePlan
  purchasePlanLabel: string
  plannedAmount: number | null
}

export type FundComparisonReport = {
  source: string
  generatedAt: string
  context: ComparisonContext
  metricWindow: string
  codes: string[]
  summary: {
    totalFunds: number
    blockedCount: number
    verifyFirstCount: number
    strongEvidenceCount: number
    averageEvidenceScore: number
    leadingFundName: string
    leadingFundCode: string
    decisionFundName: string
    decisionFundCode: string
    decisionBasis: string
    decisionReturn: number | null
    decisionDrawdown: number | null
    decisionScore: number | null
    decisionRunnerUpName: string
    decisionRunnerUpCode: string
    decisionScoreGap: number | null
    decisionWinLossLines: ComparisonWinLossLine[]
    decisiveAudit: ComparisonDecisiveAudit
    decisionReasons: string[]
    decisionRecheckTriggers: string[]
    replayEvidenceGatePassCount: number
    replayEvidenceGateVerifyCount: number
    feeComparableCount: number
    feeGapCount: number
    salesHardGapCount: number
    salesHighPriorityGapCount: number
    shareClassGroupCount: number
    shareClassFundCount: number
    peerGroupCount: number
    benchmarkCount: number
    peerInsufficientSampleCount: number
    peerBenchmarkBoundary: string
  }
  riskLevelSourcePolicy: StrictRiskLevelSourcePolicy
  items: Array<{
    windCode: string
    fundName: string
    fundType: string
    peerGroup: string
    broadAssetBucket: string
    primaryBenchmark: string
    peerGroupSource: PeerBenchmarkClassification['source']
    peerSampleStatus: PeerBenchmarkClassification['sampleStatus']
    peerSampleNote: string
    peerCount: number | null
    professionalScore: number | null
    professionalGrade: string
    operationLabel: string
    evidenceScore: number
    requiredMissingCount: number
    managementFee: number | null
    custodianFee: number | null
    feeComparable: boolean
    feeGapReason: string
    missingItems: string[]
    salesRuleMissingItems: string[]
    salesRuleMissingCount: number
    salesRulePriority: 'high' | 'medium' | 'low' | null
    shareClassInfo: ShareClassInfo | null
    leadingMetrics: string[]
    decisionScore: number
    decisionScoreBreakdown: Array<{
      key: string
      label: string
      rawScore: number
      contribution: number
      weight: number
      note: string
    }>
    decisionScoreCaps: string[]
    decisionScoreReasons: string[]
    purchaseSimulation: {
      lumpSumReturn: number | null
      lumpSumMaxDrawdown: number | null
      sipReturn: number | null
      sipMaxAccountDrawdown: number | null
      feeAdjustedCoverage: 'none' | 'partial' | 'full'
      feeAdjustedMissingItems: string[]
      feeAdjustedReturnUsed: boolean
      lumpSumFeeAdjustedReturn: number | null
      lumpSumFeeAdjustedTotalFee: number | null
	      sipFeeAdjustedReturn: number | null
	      sipFeeAdjustedTotalFee: number | null
	      monthlyPositiveRatio: number | null
	      stressLabel: string | null
	      stressScore: number | null
	      longestUnderwaterDays: number | null
	      recoveryDays: number | null
	      worstThreeMonthReturn: number | null
	      observations: number | null
      evidenceGateStatus: 'pass' | 'verify_first' | null
      evidenceGateLabel: string | null
      evidenceGateSummary: string | null
      evidenceGateHardBoundary: string | null
      evidenceGateMissingEvidence: string[]
      evidenceGateReasons: string[]
      evidenceGateActions: string[]
      evidenceGatePlannedReplayAmount: number | null
      evidenceGateReplayInvested: number | null
      evidenceGateStressDrawdown: number | null
      evidenceGateEstimatedLoss: number | null
	    } | null
    conclusion: string
    nextActions: string[]
  }>
  markdown: string
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
  lump_sum: '一次性投入口径',
  sip: '月度投入口径',
}

function normalizeContext(input: {
  profile?: string | null
  horizon?: string | null
  purchasePlan?: string | null
  plannedAmount?: number | null
}): ComparisonContext {
  const profile = ['conservative', 'balanced', 'aggressive'].includes(input.profile || '')
    ? input.profile as RiskProfile
    : 'balanced'
  const horizon = ['lt1y', '1to3y', 'gt3y'].includes(input.horizon || '')
    ? input.horizon as InvestmentHorizon
    : '1to3y'
  const purchasePlan = ['lump_sum', 'sip'].includes(input.purchasePlan || '')
    ? input.purchasePlan as PurchasePlan
    : 'sip'

  return {
    profile,
    profileLabel: profileLabels[profile],
    horizon,
    horizonLabel: horizonLabels[horizon],
    purchasePlan,
    purchasePlanLabel: purchasePlanLabels[purchasePlan],
    plannedAmount: Number.isFinite(Number(input.plannedAmount)) && Number(input.plannedAmount) > 0 ? Number(input.plannedAmount) : null,
  }
}

function evidenceDecision(fund: FundSummary) {
  if (fund.operation_status?.status === 'blocked') return '暂不进入研究'
  const missingCount = fund.buy_evidence?.requiredMissingCount ?? 0
  if (missingCount > 0) return '先补研究证据'
  const score = fund.buy_evidence?.completenessScore ?? 0
  if (score >= 75) return '可进入下一轮研究'
  return '观察并补证'
}

function replayReturnForPlan(
  simulation: FundComparisonReport['items'][number]['purchaseSimulation'],
  purchasePlan: PurchasePlan,
) {
  if (!simulation) return null
  if (purchasePlan === 'sip') {
    return simulation.sipFeeAdjustedReturn ?? simulation.sipReturn
  }
  return simulation.lumpSumFeeAdjustedReturn ?? simulation.lumpSumReturn
}

function replayDrawdownForPlan(
  simulation: FundComparisonReport['items'][number]['purchaseSimulation'],
  purchasePlan: PurchasePlan,
) {
  if (!simulation) return null
  return purchasePlan === 'sip' ? simulation.sipMaxAccountDrawdown : simulation.lumpSumMaxDrawdown
}

function buildNextActions(fund: FundSummary, leadingMetrics: string[]) {
  const actions = [
    fund.operation_status?.status === 'blocked' ? `处理申购状态：${fund.operation_status.label || '状态阻断'}` : '',
    (fund.buy_evidence?.requiredMissingCount ?? 0) > 0 ? '补销售平台风险等级、申购费率、赎回费和最低申购金额' : '',
    fund.fee_info?.missing?.length ? `补费用字段：${fund.fee_info.missing.slice(0, 4).join('、')}` : '',
    leadingMetrics.length ? '' : '补同类优势证据，确认不是跨类型误比',
    fund.buy_evidence?.completenessLevel === 'strong' ? '生成单基金研究复核一页纸' : '',
  ].filter(Boolean)
  return Array.from(new Set(actions)).slice(0, 5)
}

export function buildFundComparisonReport(input: {
  matrix: ComparisonMatrix
  simulationResults?: SimulationResult[]
  salesRuleGaps?: SalesRuleGap[]
  profile?: string | null
  horizon?: string | null
  purchasePlan?: string | null
  plannedAmount?: number | null
  generatedAt?: string
}): FundComparisonReport {
  const context = normalizeContext(input)
  const simulationByCode = new Map((input.simulationResults || []).map((result) => [result.windCode, result]))
  const salesGapByCode = new Map(
    (input.salesRuleGaps || [])
      .filter((gap) => gap.windCode)
      .map((gap) => [gap.windCode.toUpperCase(), gap]),
  )
  const shareClassSummary = summarizeShareClassGroups(input.matrix.funds)
  const shareClassInfoByCode = buildShareClassInfoByCode(input.matrix.funds)
  const peerBenchmarkResult = peerGroupBenchmarkTool.run({
    funds: input.matrix.funds.map((fund) => ({
      windCode: fund.wind_code,
      name: fund.name,
      fundType: fund.type,
      peerGroup: fund.peer_group,
      primaryBenchmark: fund.primary_benchmark,
      peerCount: fund.peer_count,
    })),
    minimumPeerCount: 5,
  })
  const peerBenchmarkByCode = new Map(
    (peerBenchmarkResult.data?.funds || []).map((fund) => [fund.windCode.toUpperCase(), fund]),
  )
  const leadingCountByCode = new Map<string, number>()

  input.matrix.matrix_rows.forEach((row) => {
    if (!row.best_code) return
    leadingCountByCode.set(row.best_code, (leadingCountByCode.get(row.best_code) || 0) + 1)
  })

  const baseItems = input.matrix.funds.map((fund) => {
    const peerBenchmark = peerBenchmarkByCode.get(fund.wind_code.toUpperCase())
    const leadingMetrics = input.matrix.matrix_rows
      .filter((row) => row.best_code === fund.wind_code)
      .map((row) => row.label)
    const simulationResult = simulationByCode.get(fund.wind_code)
    const salesRuleGap = salesGapByCode.get(fund.wind_code.toUpperCase()) || null
    const salesRuleMissingItems = salesRuleGap?.missingItems || []
    const missingItems = [
      ...(fund.buy_evidence?.requiredMissingCount ? ['销售平台风险等级/申赎费率等必核项'] : []),
      ...(fund.fee_info?.missing || []),
      ...salesRuleMissingItems,
    ]
    const feeComparable = missingItems.length === 0
    const feeGapReason = feeComparable
      ? '管理/托管和销售端必核项暂未发现明显缺口'
      : missingItems.slice(0, 5).join('、')
    const purchaseSimulation = simulationResult?.status === 'ok' && simulationResult.simulation
      ? {
          lumpSumReturn: simulationResult.simulation.lumpSum.returnRate,
          lumpSumMaxDrawdown: simulationResult.simulation.lumpSum.maxDrawdown,
          sipReturn: simulationResult.simulation.sip.returnRate,
          sipMaxAccountDrawdown: simulationResult.simulation.sip.maxAccountDrawdown,
          feeAdjustedCoverage: simulationResult.simulation.feeAdjusted?.coverage || 'none',
          feeAdjustedMissingItems: simulationResult.simulation.feeAdjusted?.missingItems || [],
          feeAdjustedReturnUsed: context.purchasePlan === 'sip'
            ? simulationResult.simulation.feeAdjusted?.sip?.returnRate !== null && simulationResult.simulation.feeAdjusted?.sip?.returnRate !== undefined
            : simulationResult.simulation.feeAdjusted?.lumpSum?.returnRate !== null && simulationResult.simulation.feeAdjusted?.lumpSum?.returnRate !== undefined,
          lumpSumFeeAdjustedReturn: simulationResult.simulation.feeAdjusted?.lumpSum?.returnRate ?? null,
          lumpSumFeeAdjustedTotalFee: simulationResult.simulation.feeAdjusted?.lumpSum?.totalFee ?? null,
	          sipFeeAdjustedReturn: simulationResult.simulation.feeAdjusted?.sip?.returnRate ?? null,
	          sipFeeAdjustedTotalFee: simulationResult.simulation.feeAdjusted?.sip?.totalFee ?? null,
	          monthlyPositiveRatio: simulationResult.simulation.monthlyExperience.positiveRatio,
	          stressLabel: simulationResult.simulation.stressExperience?.label || null,
	          stressScore: simulationResult.simulation.stressExperience?.stressScore ?? null,
	          longestUnderwaterDays: simulationResult.simulation.stressExperience?.longestUnderwaterDays ?? null,
	          recoveryDays: simulationResult.simulation.stressExperience?.recoveryDays ?? null,
	          worstThreeMonthReturn: simulationResult.simulation.stressExperience?.worstThreeMonthReturn?.returnRate ?? null,
	          observations: simulationResult.simulation.period.observations,
          evidenceGateStatus: simulationResult.simulation.evidenceGate?.status ?? null,
          evidenceGateLabel: simulationResult.simulation.evidenceGate?.label ?? null,
          evidenceGateSummary: simulationResult.simulation.evidenceGate?.summary ?? null,
          evidenceGateHardBoundary: simulationResult.simulation.evidenceGate?.hardBoundary ?? null,
          evidenceGateMissingEvidence: simulationResult.simulation.evidenceGate?.missingEvidence || [],
          evidenceGateReasons: simulationResult.simulation.evidenceGate?.reasons || [],
          evidenceGateActions: simulationResult.simulation.evidenceGate?.actions || [],
          evidenceGatePlannedReplayAmount: simulationResult.simulation.evidenceGate?.plannedReplayAmount ?? null,
          evidenceGateReplayInvested: simulationResult.simulation.evidenceGate?.replayInvested ?? null,
          evidenceGateStressDrawdown: simulationResult.simulation.evidenceGate?.stressDrawdown ?? null,
          evidenceGateEstimatedLoss: simulationResult.simulation.evidenceGate?.estimatedLoss ?? null,
	        }
      : null

    return {
      windCode: fund.wind_code,
      fundName: fund.name,
      fundType: fund.type || '',
      peerGroup: peerBenchmark?.peerGroup || fund.peer_group || '',
      broadAssetBucket: peerBenchmark?.broadAssetBucket || '',
      primaryBenchmark: peerBenchmark?.primaryBenchmark || fund.primary_benchmark || '',
      peerGroupSource: peerBenchmark?.source || 'broad_asset_bucket_fallback',
      peerSampleStatus: peerBenchmark?.sampleStatus || 'missing_peer_group',
      peerSampleNote: peerBenchmark?.sampleNote || '同类组/基准映射待补。',
      peerCount: peerBenchmark?.peerCount ?? fund.peer_count ?? null,
      professionalScore: fund.professional_score ?? null,
      professionalGrade: fund.professional_grade || '',
      operationLabel: fund.operation_status?.label || '申购待核',
      evidenceScore: fund.buy_evidence?.completenessScore ?? 0,
      requiredMissingCount: fund.buy_evidence?.requiredMissingCount ?? 0,
      managementFee: fund.fee_info?.management_fee ?? null,
      custodianFee: fund.fee_info?.custodian_fee ?? null,
      feeComparable,
      feeGapReason,
      missingItems: Array.from(new Set(missingItems)),
      salesRuleMissingItems,
      salesRuleMissingCount: salesRuleGap?.missingCount ?? salesRuleMissingItems.length,
      salesRulePriority: salesRuleGap?.priority || null,
      shareClassInfo: shareClassInfoByCode.get(fund.wind_code.toUpperCase()) || null,
      leadingMetrics,
      decisionScore: 0,
      decisionScoreBreakdown: [],
      decisionScoreCaps: [],
      decisionScoreReasons: [],
      purchaseSimulation,
      conclusion: evidenceDecision(fund),
      nextActions: buildNextActions(fund, leadingMetrics),
    }
  })
  const scoreInputItems = baseItems.map((item) => ({
    windCode: item.windCode,
    fundName: item.fundName,
    professionalScore: item.professionalScore,
    evidenceScore: item.evidenceScore,
    requiredMissingCount: item.requiredMissingCount,
    feeComparable: item.feeComparable,
    feeGapReason: item.feeGapReason,
    missingItems: item.missingItems,
    materialMissingCount: item.salesRuleMissingCount,
    operationLabel: item.operationLabel,
    conclusion: item.conclusion,
    replay: item.purchaseSimulation ? {
      returnRate: replayReturnForPlan(item.purchaseSimulation, context.purchasePlan),
      drawdown: replayDrawdownForPlan(item.purchaseSimulation, context.purchasePlan),
      stressScore: item.purchaseSimulation.stressScore,
      stressLabel: item.purchaseSimulation.stressLabel,
      longestUnderwaterDays: item.purchaseSimulation.longestUnderwaterDays,
      worstThreeMonthReturn: item.purchaseSimulation.worstThreeMonthReturn,
      evidenceGateStatus: item.purchaseSimulation.evidenceGateStatus,
      evidenceGateMissingEvidence: item.purchaseSimulation.evidenceGateMissingEvidence,
      evidenceGateSummary: item.purchaseSimulation.evidenceGateSummary,
    } : null,
  }))
  const scoreResult = comparisonResearchScoreTool.run({
    researchPlan: context.purchasePlan,
    researchPlanLabel: context.purchasePlanLabel,
    items: scoreInputItems,
  })
  const scoreByCode = new Map((scoreResult.data?.rows || []).map((row) => [row.windCode.toUpperCase(), row]))
  const items = baseItems.map((item) => {
    const scoreRow = scoreByCode.get(item.windCode.toUpperCase())
    return {
      ...item,
      decisionScore: scoreRow?.researchScore ?? 0,
      decisionScoreBreakdown: scoreRow?.breakdown || [],
      decisionScoreCaps: scoreRow?.caps || ['横评研究评分工具未返回结果'],
      decisionScoreReasons: scoreRow?.reasons || [],
    }
  })

  const totalEvidenceScore = items.reduce((sum, item) => sum + item.evidenceScore, 0)
  const feeComparableCount = items.filter((item) => item.feeComparable).length
  const feeGapCount = items.length - feeComparableCount
  const salesHardGapCount = items.filter((item) => item.salesRuleMissingCount > 0).length
  const salesHighPriorityGapCount = items.filter((item) => item.salesRulePriority === 'high').length
  const replayEvidenceGatePassCount = items.filter((item) => item.purchaseSimulation?.evidenceGateStatus === 'pass').length
  const replayEvidenceGateVerifyCount = items.filter((item) => item.purchaseSimulation?.evidenceGateStatus === 'verify_first' || !item.purchaseSimulation?.evidenceGateStatus).length
  const leadingFund = items
    .slice()
    .sort((left, right) => {
      const rightLeads = leadingCountByCode.get(right.windCode) || 0
      const leftLeads = leadingCountByCode.get(left.windCode) || 0
      if (rightLeads !== leftLeads) return rightLeads - leftLeads
      return right.evidenceScore - left.evidenceScore
    })[0]
  const decisionRankedItems = items
    .slice()
    .sort((left, right) => {
      if (right.decisionScore !== left.decisionScore) return right.decisionScore - left.decisionScore
      const leftReturn = replayReturnForPlan(left.purchaseSimulation, context.purchasePlan)
      const rightReturn = replayReturnForPlan(right.purchaseSimulation, context.purchasePlan)
      if ((rightReturn ?? -Infinity) !== (leftReturn ?? -Infinity)) {
        return (rightReturn ?? -Infinity) - (leftReturn ?? -Infinity)
      }
      const leftDrawdown = replayDrawdownForPlan(left.purchaseSimulation, context.purchasePlan)
      const rightDrawdown = replayDrawdownForPlan(right.purchaseSimulation, context.purchasePlan)
      return Math.abs(leftDrawdown ?? Infinity) - Math.abs(rightDrawdown ?? Infinity)
    })
  const decisionFund = decisionRankedItems[0]
  const decisionRunnerUp = decisionRankedItems[1]
  const replayItems = items.filter((item) => {
    const replayReturn = replayReturnForPlan(item.purchaseSimulation, context.purchasePlan)
    return replayReturn !== null && replayReturn !== undefined
  })
  const decisionReturn = decisionFund
    ? replayReturnForPlan(decisionFund.purchaseSimulation, context.purchasePlan)
    : null
  const decisionDrawdown = decisionFund
    ? replayDrawdownForPlan(decisionFund.purchaseSimulation, context.purchasePlan)
    : null
  const decisionRunnerUpReturn = decisionRunnerUp
    ? replayReturnForPlan(decisionRunnerUp.purchaseSimulation, context.purchasePlan)
    : null
  const decisionRunnerUpDrawdown = decisionRunnerUp
    ? replayDrawdownForPlan(decisionRunnerUp.purchaseSimulation, context.purchasePlan)
    : null
  const decisionScoreGap = decisionFund && decisionRunnerUp
    ? decisionFund.decisionScore - decisionRunnerUp.decisionScore
    : null
  const summaryResult = comparisonResearchSummaryTool.run({
    leader: decisionFund ? {
      windCode: decisionFund.windCode,
      fundName: decisionFund.fundName,
      researchScore: decisionFund.decisionScore,
      professionalScore: decisionFund.professionalScore,
      evidenceScore: decisionFund.evidenceScore,
      materialMissingCount: decisionFund.salesRuleMissingCount,
      feeComparable: decisionFund.feeComparable,
      replayReturn: decisionReturn,
      replayDrawdown: decisionDrawdown,
      feeAdjustedReturnUsed: Boolean(decisionFund.purchaseSimulation?.feeAdjustedReturnUsed),
    } : null,
    runnerUp: decisionRunnerUp ? {
      windCode: decisionRunnerUp.windCode,
      fundName: decisionRunnerUp.fundName,
      researchScore: decisionRunnerUp.decisionScore,
      professionalScore: decisionRunnerUp.professionalScore,
      evidenceScore: decisionRunnerUp.evidenceScore,
      materialMissingCount: decisionRunnerUp.salesRuleMissingCount,
      feeComparable: decisionRunnerUp.feeComparable,
      replayReturn: decisionRunnerUpReturn,
      replayDrawdown: decisionRunnerUpDrawdown,
      feeAdjustedReturnUsed: Boolean(decisionRunnerUp.purchaseSimulation?.feeAdjustedReturnUsed),
    } : null,
    researchPlanLabel: context.purchasePlanLabel,
    replayEvidenceCount: replayItems.length,
    feeGapCount,
  })
  const decisionBasis = summaryResult.data?.decisionBasis || '缺少可解释领先样本，不能生成横评研究摘要。'
  const decisionReasons = summaryResult.data?.decisionReasons || []
  const winLossInputItems = decisionRankedItems.map((item) => ({
    windCode: item.windCode,
    fundName: item.fundName,
    researchScore: item.decisionScore,
    evidenceScore: item.evidenceScore,
    materialMissingCount: item.salesRuleMissingCount,
    feeComparable: item.feeComparable,
    feeGapReason: item.feeGapReason,
    missingItems: item.missingItems,
    replay: item.purchaseSimulation ? {
      returnRate: replayReturnForPlan(item.purchaseSimulation, context.purchasePlan),
      drawdown: replayDrawdownForPlan(item.purchaseSimulation, context.purchasePlan),
      stressScore: item.purchaseSimulation.stressScore,
    } : null,
  }))
  const winLossAuditResult = comparisonWinLossAuditTool.run({
    leader: winLossInputItems[0] || null,
    challengers: winLossInputItems.slice(1),
    researchPlan: context.purchasePlan,
    researchPlanLabel: context.purchasePlanLabel,
    maxChallengers: 4,
  })
  const decisionWinLossLines = winLossAuditResult.data?.winLossLines || []
  const decisiveAudit = winLossAuditResult.data?.decisiveAudit || {
    title: '第一名能否真的赢第二名',
    confidence: '样本不足',
    passCount: 0,
    totalCount: 0,
    items: [],
    boundary: '至少需要第一名和一个可比替代样本；任一材料或费用硬缺口未清零时，只能保留研究态胜负线。',
  }
  const decisionRecheckTriggers = winLossAuditResult.data?.recheckTriggers || []
  const riskLevelSourcePolicy = buildStrictRiskLevelSourcePolicy({
    sourceBacked: salesHardGapCount === 0 && items.length > 0,
    scopeLabel: '横评样本',
    totalCount: items.length,
    blockedCount: salesHardGapCount,
  })

  const payloadWithoutMarkdown = {
    source: 'local_comparison_matrix_buy_evidence_nav_replay',
    generatedAt: input.generatedAt || new Date().toISOString(),
    context,
    metricWindow: input.matrix.metric_window,
    codes: input.matrix.funds.map((fund) => fund.wind_code),
    summary: {
      totalFunds: items.length,
      blockedCount: input.matrix.funds.filter((fund) => fund.operation_status?.status === 'blocked').length,
      verifyFirstCount: items.filter((item) => item.requiredMissingCount > 0 || item.missingItems.length > 0).length,
      strongEvidenceCount: input.matrix.funds.filter((fund) => fund.buy_evidence?.completenessLevel === 'strong').length,
      averageEvidenceScore: items.length ? Math.round(totalEvidenceScore / items.length) : 0,
      leadingFundName: leadingFund?.fundName || '',
      leadingFundCode: leadingFund?.windCode || '',
      decisionFundName: decisionFund?.fundName || '',
      decisionFundCode: decisionFund?.windCode || '',
      decisionBasis,
      decisionReturn,
      decisionDrawdown,
      decisionScore: decisionFund?.decisionScore ?? null,
      decisionRunnerUpName: decisionRunnerUp?.fundName || '',
      decisionRunnerUpCode: decisionRunnerUp?.windCode || '',
      decisionScoreGap,
      decisionWinLossLines,
      decisiveAudit,
      decisionReasons,
      decisionRecheckTriggers,
      replayEvidenceGatePassCount,
      replayEvidenceGateVerifyCount,
      feeComparableCount,
      feeGapCount,
      salesHardGapCount,
      salesHighPriorityGapCount,
      shareClassGroupCount: shareClassSummary.groupCount,
      shareClassFundCount: shareClassSummary.fundCount,
      peerGroupCount: peerBenchmarkResult.data?.peerGroupCount || 0,
      benchmarkCount: peerBenchmarkResult.data?.benchmarkCount || 0,
      peerInsufficientSampleCount: peerBenchmarkResult.data?.insufficientSampleCount || 0,
      peerBenchmarkBoundary: peerBenchmarkResult.data?.policy.hardBoundary || '同类组、基准和样本数量不足时，横评只能作为研究观察。',
    },
    riskLevelSourcePolicy,
    items,
  }

  return {
    ...payloadWithoutMarkdown,
    markdown: renderFundComparisonMarkdown(payloadWithoutMarkdown),
  }
}
