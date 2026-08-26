import {
  buildComparisonDecisiveAudit,
  type ComparisonDecisiveAudit,
  type ComparisonWinLossLine,
} from '@/lib/comparison-decisive-audit'
import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type ComparisonWinLossAuditPlan = 'lump_sum' | 'sip'

export type ComparisonWinLossAuditFund = {
  windCode: string
  fundName: string
  researchScore: number
  evidenceScore: number
  materialMissingCount: number
  feeComparable: boolean
  feeGapReason: string
  missingItems: string[]
  replay: {
    returnRate: number | null
    drawdown: number | null
    stressScore: number | null
  } | null
}

export type ComparisonWinLossAuditInput = {
  leader: ComparisonWinLossAuditFund | null
  challengers: ComparisonWinLossAuditFund[]
  researchPlan: ComparisonWinLossAuditPlan
  researchPlanLabel: string
  maxChallengers?: number
}

export type ComparisonWinLossAuditOutput = {
  winLossLines: ComparisonWinLossLine[]
  decisiveAudit: ComparisonDecisiveAudit
  recheckTriggers: string[]
  policy: {
    maxChallengers: number
    hardBoundary: string
    sourceReferences: string[]
  }
}

const toolName = 'comparison-win-loss-audit'
const version = '1.0.0'

function percentPointText(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  const sign = Number(value) > 0 ? '+' : ''
  return `${sign}${(Number(value) * 100).toFixed(2)}pct`
}

function buildLine(
  leader: ComparisonWinLossAuditFund,
  challenger: ComparisonWinLossAuditFund,
  researchPlanLabel: string,
): ComparisonWinLossLine {
  const leaderReturn = leader.replay?.returnRate ?? null
  const challengerReturn = challenger.replay?.returnRate ?? null
  const leaderDrawdown = leader.replay?.drawdown ?? null
  const challengerDrawdown = challenger.replay?.drawdown ?? null
  const returnDelta = leaderReturn !== null && challengerReturn !== null ? leaderReturn - challengerReturn : null
  const drawdownDelta = leaderDrawdown !== null && challengerDrawdown !== null ? Math.abs(leaderDrawdown) - Math.abs(challengerDrawdown) : null
  const scoreDelta = leader.researchScore - challenger.researchScore
  const evidenceDelta = leader.evidenceScore - challenger.evidenceScore
  const stressDelta = leader.replay?.stressScore !== null && leader.replay?.stressScore !== undefined && challenger.replay?.stressScore !== null && challenger.replay?.stressScore !== undefined
    ? leader.replay.stressScore - challenger.replay.stressScore
    : null
  const materialReady = leader.materialMissingCount === 0 && challenger.materialMissingCount === 0
  const riskWin = drawdownDelta !== null && drawdownDelta <= 0.02
  const returnWin = returnDelta !== null && returnDelta >= -0.01
  const scoreWin = scoreDelta >= 0
  const evidenceWin = evidenceDelta >= 0
  const stressWin = stressDelta === null || stressDelta >= -5
  const costWin = leader.feeComparable && (challenger.feeComparable || leader.missingItems.length <= challenger.missingItems.length)
  const passedChecks = [materialReady, riskWin, returnWin, scoreWin, evidenceWin, stressWin, costWin].filter(Boolean).length
  const status = !materialReady
    ? 'rules_pending'
    : passedChecks >= 6
      ? 'win'
      : passedChecks >= 4
        ? 'close'
        : 'lose'

  return {
    challengerCode: challenger.windCode,
    challengerName: challenger.fundName,
    status,
    label: status === 'win' ? '第一名胜出' : status === 'close' ? '接近' : status === 'rules_pending' ? '材料待补' : '第一名未胜出',
    summary: `${challenger.fundName}：研究评分差 ${scoreDelta >= 0 ? '+' : ''}${scoreDelta}；收益差 ${percentPointText(returnDelta)}；回撤差 ${percentPointText(drawdownDelta)}；证据分差 ${evidenceDelta >= 0 ? '+' : ''}${evidenceDelta}`,
    thresholds: [
      {
        key: 'sales_rules',
        label: '材料核验',
        passed: materialReady,
        detail: materialReady
          ? '两只基金均未见材料核验硬缺口，可进入正式横评复核。'
          : `任一基金材料核验未补齐，只能作为研究态横评；第一名缺 ${leader.materialMissingCount} 项，替代缺 ${challenger.materialMissingCount} 项。`,
      },
      {
        key: 'score',
        label: '研究评分',
        passed: scoreWin,
        detail: `第一名研究评分不能低于替代；当前差 ${scoreDelta >= 0 ? '+' : ''}${scoreDelta}。`,
      },
      {
        key: 'return',
        label: '费用优先回放收益',
        passed: returnWin,
        detail: `${researchPlanLabel}回放收益不能落后替代 1pct 以上；当前差 ${percentPointText(returnDelta)}。`,
      },
      {
        key: 'risk',
        label: '回撤舒适度',
        passed: riskWin,
        detail: `回撤不能比替代高 2pct 以上；当前差 ${percentPointText(drawdownDelta)}。`,
      },
      {
        key: 'evidence',
        label: '研究证据',
        passed: evidenceWin,
        detail: `证据分不能低于替代；当前差 ${evidenceDelta >= 0 ? '+' : ''}${evidenceDelta}。`,
      },
      {
        key: 'stress',
        label: '压力体验',
        passed: stressWin,
        detail: `压力分不能落后替代 5 分以上；当前差 ${stressDelta === null ? '待补' : `${stressDelta >= 0 ? '+' : ''}${stressDelta}`}。`,
      },
      {
        key: 'cost',
        label: '费用可比性',
        passed: costWin,
        detail: leader.feeComparable ? '第一名费用证据可初步横比。' : `第一名费用仍待补：${leader.feeGapReason}`,
      },
    ],
    passedChecks,
    totalChecks: 7,
  }
}

function buildRecheckTriggers(
  leader: ComparisonWinLossAuditFund | null,
  runnerUp: ComparisonWinLossAuditFund | undefined,
  scoreGap: number | null,
  winLossLines: ComparisonWinLossLine[],
) {
  if (!leader) return []
  const firstLine = winLossLines[0]
  const returnThreshold = firstLine?.thresholds.find((threshold) => threshold.key === 'return')
  const riskThreshold = firstLine?.thresholds.find((threshold) => threshold.key === 'risk')
  return [
    scoreGap !== null && scoreGap <= 5 ? `分差只有 ${scoreGap} 分，视为接近；补齐费率或重跑回放后可能反转。` : '',
    leader.materialMissingCount > 0 ? `补齐 ${leader.fundName} 的材料核验硬缺口前，只能把它当作补证优先样本。` : '',
    runnerUp?.materialMissingCount && !leader.materialMissingCount ? `${runnerUp.fundName} 若补齐材料核验，可能重新进入可比研究样本。` : '',
    !leader.feeComparable ? `${leader.fundName} 的费用证据不可直接横比，费后收益可能被高估。` : '',
    returnThreshold && !returnThreshold.passed ? returnThreshold.detail : '',
    riskThreshold && !riskThreshold.passed ? riskThreshold.detail : '',
    winLossLines.length ? '' : '尚未形成胜负线，当前排序更偏静态评分。',
  ].filter(Boolean)
}

export const comparisonWinLossAuditTool: ResearchTool<ComparisonWinLossAuditInput, ComparisonWinLossAuditOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'comparison',
    purpose: '生成横评第一名对替代样本的胜负线、置信审计和反转条件，避免报告层散落领先判断。',
    inputSchema: 'ComparisonWinLossAuditInput',
    outputSchema: 'ComparisonWinLossAuditOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '胜负线只解释研究排序是否稳健，不输出操作指令。',
      '材料核验、费用、回放或压力体验缺失时必须进入 recheckTriggers 或 gaps。',
    ],
  },
  run(input) {
    const maxChallengers = Number.isFinite(Number(input.maxChallengers)) && Number(input.maxChallengers) > 0
      ? Number(input.maxChallengers)
      : 4
    const challengers = input.leader
      ? input.challengers.filter((item) => item.windCode !== input.leader?.windCode).slice(0, maxChallengers)
      : []
    const winLossLines = input.leader
      ? challengers.map((challenger) => buildLine(input.leader as ComparisonWinLossAuditFund, challenger, input.researchPlanLabel))
      : []
    const decisiveAudit = buildComparisonDecisiveAudit(winLossLines)
    const runnerUp = challengers[0]
    const scoreGap = input.leader && runnerUp ? input.leader.researchScore - runnerUp.researchScore : null
    const recheckTriggers = buildRecheckTriggers(input.leader, runnerUp, scoreGap, winLossLines)
    const output: ComparisonWinLossAuditOutput = {
      winLossLines,
      decisiveAudit,
      recheckTriggers,
      policy: {
        maxChallengers,
        hardBoundary: '至少需要第一名和一个可比替代样本；任一材料或费用硬缺口未清零时，只能保留研究态胜负线。',
        sourceReferences: [
          'QuantStats/Empyrical drawdown-return comparison pattern',
          'OpenBB provider-style evidence separation',
          'FinRobot auditable tool-to-report orchestration',
        ],
      },
    }
    const hardBlocks = input.leader ? [] : ['缺少横评第一名，不能生成胜负线审计。']
    const gapLines = winLossLines.filter((line) => line.passedChecks < line.totalChecks)
    return createToolResult(toolName, version, input, output, {
      ok: hardBlocks.length === 0 && gapLines.length === 0,
      hardBlocks,
      evidence: winLossLines.map((line) => ({
        id: `comparison-win-loss:${input.leader?.windCode || 'leader'}:${line.challengerCode}`,
        label: '横评胜负线',
        source: 'comparison.win_loss.derived_metric',
        freshness: 'derived',
        subjectId: input.leader?.windCode || undefined,
        note: `${line.challengerName}：${line.label}；${line.summary}`,
      })),
      gaps: gapLines.map((line) => ({
        key: `comparison-win-loss:${line.challengerCode}`,
        label: '胜负线待复核',
        severity: line.status === 'rules_pending' ? 'hard_block' : 'verify_first',
        subjectId: line.challengerCode,
        reason: line.thresholds.filter((threshold) => !threshold.passed).map((threshold) => threshold.detail).slice(0, 3).join('；'),
        requiredBeforeFormalReview: true,
      })),
      nextActions: gapLines.map((line) => ({
        key: `comparison-win-loss:${line.challengerCode}`,
        label: '补胜负线证据',
        href: `/funds/${encodeURIComponent(line.challengerCode)}`,
        priority: line.status === 'rules_pending' ? 'high' : 'medium',
        reason: line.summary,
      })),
    })
  },
}
