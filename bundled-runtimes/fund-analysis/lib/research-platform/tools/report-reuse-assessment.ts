import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export const REPORT_REUSE_MAX_AGE_DAYS = 30

export type ReportReuseInput = {
  id: string
  title: string
  targetId?: string | null
  targetType: string
  reportType: string
  reportDate: string
  actionHref: string
  relatedCodes?: string[]
  currentSalesRuleGate?: {
    status?: 'ready' | 'blocked' | 'unknown' | string
    missingCount?: number | null
    actionHref?: string
    source?: string
  } | null
  decisionSummary?: {
    buyBeforeGateStatus?: string
    buyBeforeGateHardBlocks?: string[]
    buyBeforeGateCautionFlags?: string[]
    replayEvidenceGateStatus?: string
    replayEvidenceGateLabel?: string
    replayEvidenceGateMissingEvidence?: string[]
  } | null
  riskLevelGatePolicy?: {
    requiresRegeneration?: boolean
    detail?: string
    effectiveDate?: string
  } | null
  followUp: {
    label: string
    href: string
  }
  riskLevelSourceQueueHref?: string
  replayEvidenceRerunHref?: string
}

export type ReportReuseStatus = 'invalidated' | 'rerun_required' | 'research_trace'
export type ReportTodayUsabilityDecision = '只作历史回看' | '需重跑' | '今天可沿用研究'

export type ReportReuseAssessmentOutput = {
  status: ReportReuseStatus
  label: string
  reason: string
  actionLabel: string
  actionHref: string
  ageDays: number | null
  todayDecision: ReportTodayUsabilityDecision
  hardBoundary: string
  nextEvidence: string
}

const toolName = 'report-reuse-assessment'
const version = '1.0.0'

function reportAgeDays(reportDate: string) {
  const parsed = new Date(reportDate)
  if (Number.isNaN(parsed.getTime())) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const reportDay = new Date(parsed)
  reportDay.setHours(0, 0, 0, 0)
  return Math.floor((today.getTime() - reportDay.getTime()) / 86_400_000)
}

function isReviewQueueGate(gate: ReportReuseInput['currentSalesRuleGate']) {
  return Boolean(
    gate?.source?.includes('alert')
      || gate?.actionHref?.includes('/alerts')
      || gate?.actionHref?.includes('section=review-events'),
  )
}

export const reportReuseAssessmentTool: ResearchTool<ReportReuseInput, ReportReuseAssessmentOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'report',
    purpose: '判断历史基金研究报告今天能否作为研究留痕继续参考。',
    inputSchema: 'ReportReuseInput',
    outputSchema: 'ReportReuseAssessmentOutput',
    evidencePolicy: 'snapshot',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '旧报告不能绕过最新销售平台证据、R1-R5、费率、申赎、限购、净值回放和测算证据。',
      '可沿用仅表示研究留痕可参考，不表示正式研究复核已完成。',
    ],
  },
  run(input) {
    const ageDays = reportAgeDays(input.reportDate)
    const salesGate = input.currentSalesRuleGate?.status || 'none'
    const buyBeforeStatus = input.decisionSummary?.buyBeforeGateStatus || ''
    const hardBlock = input.decisionSummary?.buyBeforeGateHardBlocks?.[0] || ''
    const caution = input.decisionSummary?.buyBeforeGateCautionFlags?.[0] || ''
    const replayEvidenceGateStatus = input.decisionSummary?.replayEvidenceGateStatus || ''
    const replayEvidenceGateLabel = input.decisionSummary?.replayEvidenceGateLabel || ''
    const replayEvidenceGateMissingEvidence = input.decisionSummary?.replayEvidenceGateMissingEvidence || []
    const isComparisonReport = input.targetType === 'comparison' || input.reportType.includes('comparison')
    const hasReplayEvidenceGap = isComparisonReport && Boolean(replayEvidenceGateStatus) && replayEvidenceGateStatus !== 'pass'
    const replayEvidenceGapSummary = hasReplayEvidenceGap
      ? `${replayEvidenceGateLabel || '测算证据门禁未通过'}，${
          replayEvidenceGateMissingEvidence.length
            ? `待补 ${replayEvidenceGateMissingEvidence.slice(0, 3).join('、')}`
            : '需重跑真实净值、费率、回撤预算和回本等待测算'
        }`
      : ''

    let assessment: Omit<ReportReuseAssessmentOutput, 'todayDecision' | 'hardBoundary' | 'nextEvidence'>
    if (salesGate === 'blocked') {
      const reviewQueueGate = isReviewQueueGate(input.currentSalesRuleGate)
      assessment = {
        status: 'invalidated',
        label: '不可复用',
        reason: reviewQueueGate
          ? `当前复查队列仍有 ${input.currentSalesRuleGate?.missingCount ?? 0} 项销售规则/R1-R5事件未解决，处理前只能回看。${replayEvidenceGapSummary ? `同时${replayEvidenceGapSummary}；处理复查队列后仍需重跑真实回放横评。` : ''}`
          : `当前销售规则仍缺 ${input.currentSalesRuleGate?.missingCount ?? 0} 项，R1-R5、费率、申赎或限购缺口清零前只能回看。${replayEvidenceGapSummary ? `同时${replayEvidenceGapSummary}；补销售规则后仍需重跑真实回放横评。` : ''}`,
        actionLabel: reviewQueueGate ? '处理复查队列' : '补销售规则',
        actionHref: input.currentSalesRuleGate?.actionHref || input.followUp.href,
        ageDays,
      }
    } else if (salesGate === 'unknown') {
      assessment = {
        status: 'invalidated',
        label: '门禁待扫描',
        reason: `当前销售规则门禁未知，不能证明 R1-R5、申赎和费用仍有效。${replayEvidenceGapSummary ? `同时${replayEvidenceGapSummary}；扫描销售规则后仍需重跑真实回放横评。` : ''}`,
        actionLabel: '扫描销售规则',
        actionHref: input.followUp.href,
        ageDays,
      }
    } else if (buyBeforeStatus === 'blocked_by_hard_gate') {
      assessment = {
        status: 'invalidated',
        label: '硬阻断失效',
        reason: hardBlock || '报告生成时研究总闸门已硬阻断，不能复用为正式研究依据。',
        actionLabel: '查看硬阻断',
        actionHref: input.actionHref,
        ageDays,
      }
    } else if (input.riskLevelGatePolicy?.requiresRegeneration) {
      assessment = {
        status: 'rerun_required',
        label: '旧R1-R5门禁',
        reason: `${input.riskLevelGatePolicy.detail || 'R1-R5 来源背书待补'} 生效日 ${input.riskLevelGatePolicy.effectiveDate || '待核'}；先进入 R1-R5 来源补证队列，再重跑当前报告。`,
        actionLabel: '重跑R1-R5门禁',
        actionHref: input.riskLevelSourceQueueHref || input.followUp.href,
        ageDays,
      }
    } else if (hasReplayEvidenceGap) {
      const missingEvidenceText = replayEvidenceGateMissingEvidence.length
        ? `待补：${replayEvidenceGateMissingEvidence.slice(0, 4).join('、')}。`
        : '需重跑真实净值、费率、回撤预算和回本等待测算。'
      assessment = {
        status: 'rerun_required',
        label: replayEvidenceGateStatus === 'missing' ? '缺测算门禁' : '回放待补证',
        reason: `${replayEvidenceGateLabel || '测算证据门禁未通过'}；${missingEvidenceText} 门禁未过的历史回放不能作为正式研究横评结论。`,
        actionLabel: '重跑真实回放横评',
        actionHref: input.replayEvidenceRerunHref || input.followUp.href,
        ageDays,
      }
    } else if (ageDays === null || ageDays > REPORT_REUSE_MAX_AGE_DAYS) {
      assessment = {
        status: 'rerun_required',
        label: '需重跑',
        reason: ageDays === null
          ? '报告日期不可解析，无法证明 NAV、回放、费率和销售风险等级仍在复核窗口内。'
          : `报告已生成 ${ageDays} 天，超过 ${REPORT_REUSE_MAX_AGE_DAYS} 天复核窗口；NAV、费率、R1-R5 和真实回放需要重跑。`,
        actionLabel: input.followUp.label,
        actionHref: input.followUp.href,
        ageDays,
      }
    } else if (buyBeforeStatus === 'verify_first') {
      assessment = {
        status: 'rerun_required',
        label: '先复核再复用',
        reason: caution || '报告仅达到先复核状态，需补同类、持仓、经理任期或真实回放证据后重跑。',
        actionLabel: input.followUp.label,
        actionHref: input.followUp.href,
        ageDays,
      }
    } else if (!buyBeforeStatus) {
      assessment = {
        status: 'rerun_required',
        label: '缺研究闸门',
        reason: '旧报告缺少结构化研究总闸门，不能直接当作研究选择证据。',
        actionLabel: input.followUp.label,
        actionHref: input.followUp.href,
        ageDays,
      }
    } else {
      assessment = {
        status: 'research_trace',
        label: '可作研究留痕',
        reason: '当前销售规则无硬缺口，研究总闸门具备结构化结论；正式使用前仍需复核销售平台实时页面。',
        actionLabel: input.followUp.label,
        actionHref: input.followUp.href,
        ageDays,
      }
    }

    const todayDecision: ReportTodayUsabilityDecision = assessment.status === 'research_trace'
      ? '今天可沿用研究'
      : assessment.status === 'rerun_required'
        ? '需重跑'
        : '只作历史回看'
    const hardBoundary = todayDecision === '今天可沿用研究'
      ? '沿用范围仅限研究留痕与研究复核；正式研究结论仍必须重新核验销售平台实时 R1-R5、费率、申赎、限购和最新净值回放。'
      : '历史报告不能跳过今日销售平台/R1-R5/费率/申赎/限购/真实回放证据；缺口清零前不得沿用为正式研究依据。'
    const output = {
      ...assessment,
      todayDecision,
      hardBoundary,
      nextEvidence: assessment.status === 'research_trace'
        ? '打开原报告对应对象，复核实时销售规则与最新净值回放'
        : assessment.reason,
    }

    return createToolResult(toolName, version, input, output, {
      ok: output.status === 'research_trace',
      hardBlocks: output.status === 'invalidated' ? [output.reason] : [],
      gaps: output.status === 'research_trace' ? [] : [{
        key: output.status,
        label: output.label,
        severity: output.status === 'invalidated' ? 'hard_block' : 'verify_first',
        subjectId: input.id,
        reason: output.reason,
        requiredBeforeFormalReview: true,
      }],
      evidence: [{
        id: `report-reuse:${input.id}`,
        label: '报告复用有效性判断',
        source: 'report_reuse_assessment.derived_snapshot',
        freshness: output.status === 'research_trace' ? 'snapshot' : 'stale',
        subjectId: input.id,
        note: `报告年龄：${ageDays === null ? '不可解析' : `${ageDays} 天`}；今日结论：${todayDecision}`,
      }],
      nextActions: [{
        key: output.status,
        label: output.actionLabel,
        href: output.actionHref,
        priority: output.status === 'invalidated' ? 'high' : output.status === 'rerun_required' ? 'medium' : 'low',
        reason: output.nextEvidence,
      }],
    })
  },
}
