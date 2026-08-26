import { NextResponse } from 'next/server'
import postgres from 'postgres'
import { createHash } from 'crypto'
import {
  buildFundComparisonReport,
  type ComparisonMatrix,
  type SimulationResult,
} from '@/lib/fund-comparison-report'
import { getSalesRuleGapsForCodes } from '@/lib/sales-rule-gaps'
import { fetchActiveSalesRuleEvidenceAlertsForCodes } from '@/lib/sales-rule-review-alerts'
import { materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const sql = postgres(process.env.DATABASE_URL || '', { max: 1 })

function jsonSafe(value: unknown) {
  return JSON.parse(JSON.stringify(value))
}

function isMatrix(value: unknown): value is ComparisonMatrix {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<ComparisonMatrix>
  return Array.isArray(candidate.funds) && Array.isArray(candidate.matrix_rows)
}

function comparisonTargetId(codes: string[]) {
  const normalizedCodes = codes.map((code) => code.toUpperCase()).sort().join(',')
  const digest = createHash('sha1').update(normalizedCodes).digest('hex').slice(0, 16)
  return `comparison:${digest}`
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    if (!isMatrix(body.matrix)) {
      return NextResponse.json(
        { error: '缺少有效的对比矩阵，请先生成基金对比矩阵。' },
        { status: 400 },
      )
    }
    const matrix: ComparisonMatrix = body.matrix
    const matrixCodes = matrix.funds.map((fund) => fund.wind_code).filter(Boolean)
    const purchasePlan = typeof body.purchasePlan === 'string' ? body.purchasePlan : null
    const plannedAmount = Number(body.plannedAmount)
    const safePlannedAmount = Number.isFinite(plannedAmount) && plannedAmount > 0 ? plannedAmount : null
    const currentSalesRuleGaps = await getSalesRuleGapsForCodes(matrixCodes, matrixCodes.length, {
      purchasePlan: purchasePlan === 'lump_sum' || purchasePlan === 'sip' ? purchasePlan : null,
      plannedAmount: safePlannedAmount,
    })
    const activeSalesRuleEvidenceAlertsByCode = await fetchActiveSalesRuleEvidenceAlertsForCodes(matrixCodes)
    const activeSalesRuleEvidenceAlerts = Array.from(activeSalesRuleEvidenceAlertsByCode.values()).flat()

    const amountBlockedRules = (currentSalesRuleGaps.rules || []).filter((rule) => rule.executionAmountGate.status === 'blocked')
    if (activeSalesRuleEvidenceAlerts.length > 0) {
      const blockedCodes = Array.from(new Set(activeSalesRuleEvidenceAlerts.map((alert) => alert.fundCode).filter(Boolean)))
      const materialEvidenceParams = new URLSearchParams({
        codes: blockedCodes.join(','),
        returnTo: '/analysis/comparison',
      })
      if (purchasePlan) materialEvidenceParams.set('purchasePlan', purchasePlan)
      if (safePlannedAmount) materialEvidenceParams.set('plannedAmount', String(safePlannedAmount))
      return NextResponse.json(
        {
          error: `当前对比有 ${blockedCodes.length} 只基金存在未解决销售规则/R1-R5复查事件，补齐前不保存正式横向比较报告。`,
          code: 'STALE_SALES_RULE_EVIDENCE_ALERT_BLOCKED',
          salesRuleEvidenceAlerts: activeSalesRuleEvidenceAlerts,
          salesRulesHref: materialEvidenceHref(materialEvidenceParams),
          alertsHref: reviewEventsHref({ returnTo: '/analysis/comparison' }),
        },
        { status: 409 },
      )
    }
    if (amountBlockedRules.length > 0) {
      return NextResponse.json(
        {
          error: `当前对比有 ${amountBlockedRules.length} 只基金计划金额未通过起购/定投起点/限购门禁，调整金额或补规则前不保存正式横向比较报告。`,
          code: 'SALES_RULE_AMOUNT_GATE_BLOCKED',
          salesRuleRules: amountBlockedRules,
          salesRuleGaps: currentSalesRuleGaps.gaps,
          summary: currentSalesRuleGaps.summary,
        },
        { status: 409 },
      )
    }
    if (currentSalesRuleGaps.gapCount > 0) {
      return NextResponse.json(
        {
          error: `当前对比仍有 ${currentSalesRuleGaps.gapCount} 只基金存在销售规则硬缺口，补齐前不保存正式横向比较报告。`,
          code: 'SALES_RULE_GAP_BLOCKED',
          salesRuleGaps: currentSalesRuleGaps.gaps,
          summary: currentSalesRuleGaps.summary,
        },
        { status: 409 },
      )
    }

    const report = buildFundComparisonReport({
      matrix,
      simulationResults: Array.isArray(body.simulationResults) ? body.simulationResults as SimulationResult[] : [],
      salesRuleGaps: currentSalesRuleGaps.gaps,
      profile: typeof body.profile === 'string' ? body.profile : null,
      horizon: typeof body.horizon === 'string' ? body.horizon : null,
      purchasePlan,
      plannedAmount: safePlannedAmount,
      generatedAt: new Date().toISOString(),
    })

    const dataSources = jsonSafe({
      source: 'fund_comparison_report',
      metricWindow: report.metricWindow,
      codes: report.codes,
      summary: report.summary,
      riskLevelSourcePolicy: report.riskLevelSourcePolicy,
      decisionWinLossLines: report.summary.decisionWinLossLines,
      decisiveAudit: report.summary.decisiveAudit,
      items: report.items.map((item) => ({
        windCode: item.windCode,
        fundName: item.fundName,
        evidenceScore: item.evidenceScore,
        requiredMissingCount: item.requiredMissingCount,
        feeComparable: item.feeComparable,
        feeGapReason: item.feeGapReason,
        missingItems: item.missingItems,
        salesRuleMissingItems: item.salesRuleMissingItems,
        salesRuleMissingCount: item.salesRuleMissingCount,
        salesRulePriority: item.salesRulePriority,
        shareClassInfo: item.shareClassInfo,
        leadingMetrics: item.leadingMetrics,
        decisionScore: item.decisionScore,
        decisionScoreBreakdown: item.decisionScoreBreakdown,
        decisionScoreCaps: item.decisionScoreCaps,
        decisionScoreReasons: item.decisionScoreReasons,
        purchaseSimulation: item.purchaseSimulation,
      })),
      salesRuleGaps: jsonSafe(currentSalesRuleGaps.gaps),
      salesRuleRules: jsonSafe(currentSalesRuleGaps.rules),
      currentSalesRuleGaps: jsonSafe({
        source: currentSalesRuleGaps.source,
        totalMembers: currentSalesRuleGaps.totalMembers,
        gapCount: currentSalesRuleGaps.gapCount,
        summary: currentSalesRuleGaps.summary,
      }),
    })
	    const generationParams = jsonSafe({
      mode: 'deterministic_fund_comparison',
      provider: 'local_comparison_matrix',
      model: 'backend_compare_matrix_buy_evidence_nav_replay',
      generatedAt: report.generatedAt,
      profile: report.context.profile,
      horizon: report.context.horizon,
      purchasePlan: report.context.purchasePlan,
      plannedAmount: report.context.plannedAmount,
      totalFunds: report.summary.totalFunds,
      verifyFirstCount: report.summary.verifyFirstCount,
      blockedCount: report.summary.blockedCount,
      decisionFundName: report.summary.decisionFundName,
      decisionFundCode: report.summary.decisionFundCode,
      decisionBasis: report.summary.decisionBasis,
      decisionReturn: report.summary.decisionReturn,
	      decisionDrawdown: report.summary.decisionDrawdown,
      decisionScore: report.summary.decisionScore,
      decisionWinLossLineCount: report.summary.decisionWinLossLines.length,
	      decisionStressScore: report.items.find((item) => item.windCode === report.summary.decisionFundCode)?.purchaseSimulation?.stressScore ?? null,
	      decisionLongestUnderwaterDays: report.items.find((item) => item.windCode === report.summary.decisionFundCode)?.purchaseSimulation?.longestUnderwaterDays ?? null,
	      decisionWorstThreeMonthReturn: report.items.find((item) => item.windCode === report.summary.decisionFundCode)?.purchaseSimulation?.worstThreeMonthReturn ?? null,
      decisionRunnerUpCode: report.summary.decisionRunnerUpCode,
      decisionScoreGap: report.summary.decisionScoreGap,
      decisiveAudit: report.summary.decisiveAudit,
      decisionReturnBasis: 'fee_adjusted_when_available_else_raw_nav_replay',
      decisionReplayEvidenceGateStatus: report.items.find((item) => item.windCode === report.summary.decisionFundCode)?.purchaseSimulation?.evidenceGateStatus ?? null,
      decisionReplayEvidenceGateLabel: report.items.find((item) => item.windCode === report.summary.decisionFundCode)?.purchaseSimulation?.evidenceGateLabel ?? null,
      decisionReplayEvidenceGateMissingEvidence: report.items.find((item) => item.windCode === report.summary.decisionFundCode)?.purchaseSimulation?.evidenceGateMissingEvidence ?? [],
      replayEvidenceGatePassCount: report.summary.replayEvidenceGatePassCount,
      replayEvidenceGateVerifyCount: report.summary.replayEvidenceGateVerifyCount,
      feeComparableCount: report.summary.feeComparableCount,
      feeGapCount: report.summary.feeGapCount,
      salesHardGapCount: report.summary.salesHardGapCount,
      salesHighPriorityGapCount: report.summary.salesHighPriorityGapCount,
      riskLevelSourcePolicyStatus: report.riskLevelSourcePolicy.status,
      riskLevelSourceBacked: report.riskLevelSourcePolicy.sourceBacked,
      riskLevelGateSignals: report.riskLevelSourcePolicy.signals,
      shareClassGroupCount: report.summary.shareClassGroupCount,
      shareClassFundCount: report.summary.shareClassFundCount,
    })

    const savedRows = await sql<{ id: string }[]>`
      INSERT INTO ai_analysis_reports (
        target_type,
        target_id,
        report_type,
        content,
        data_sources,
        research_reports_used,
        generation_params,
        created_at
      ) VALUES (
        'comparison',
        ${comparisonTargetId(report.codes)},
        'fund_comparison_report',
        ${report.markdown},
        CAST(${JSON.stringify(dataSources)} AS jsonb),
        ARRAY[]::text[],
        CAST(${JSON.stringify(generationParams)} AS jsonb),
        NOW()
      )
      RETURNING id::text
    `
    const saved = savedRows[0]

    return NextResponse.json({
      id: saved?.id,
      reportId: saved?.id,
      saved: Boolean(saved?.id),
      report,
    })
  } catch (error) {
    console.error('保存基金横向比较报告失败:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '保存基金横向比较报告失败' },
      { status: 500 },
    )
  }
}
