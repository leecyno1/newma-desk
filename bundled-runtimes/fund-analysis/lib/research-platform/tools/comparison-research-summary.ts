import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type ComparisonResearchSummaryFund = {
  windCode: string
  fundName: string
  researchScore: number
  professionalScore: number | null
  evidenceScore: number
  materialMissingCount: number
  feeComparable: boolean
  replayReturn: number | null
  replayDrawdown: number | null
  feeAdjustedReturnUsed: boolean
}

export type ComparisonResearchSummaryInput = {
  leader: ComparisonResearchSummaryFund | null
  runnerUp?: ComparisonResearchSummaryFund | null
  researchPlanLabel: string
  replayEvidenceCount: number
  feeGapCount: number
}

export type ComparisonResearchSummaryOutput = {
  decisionBasis: string
  decisionReasons: string[]
  policy: {
    sourceReferences: string[]
    hardBoundary: string
  }
}

const toolName = 'comparison-research-summary'
const version = '1.0.0'

function percentText(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return `${(Number(value) * 100).toFixed(2)}%`
}

function signedNumber(value: number) {
  return `${value >= 0 ? '+' : ''}${value}`
}

function professionalScoreDelta(leader: ComparisonResearchSummaryFund, runnerUp: ComparisonResearchSummaryFund) {
  return (leader.professionalScore ?? 0) - (runnerUp.professionalScore ?? 0)
}

function buildDecisionBasis(input: ComparisonResearchSummaryInput) {
  if (!input.leader) return '缺少可解释领先样本，不能生成横评研究摘要。'
  if (input.replayEvidenceCount > 0) {
    return `${input.researchPlanLabel}历史净值回放纳入综合评分${input.leader.feeAdjustedReturnUsed ? '（已优先采用费用后收益）' : input.feeGapCount > 0 ? '；费用证据待补，需费后确认' : ''}`
  }
  return '同类指标领先维度与研究证据综合评分'
}

function buildReasons(input: ComparisonResearchSummaryInput) {
  const leader = input.leader
  const runnerUp = input.runnerUp || null
  if (!leader) return []
  return [
    leader.materialMissingCount > 0
      ? `第一名 ${leader.fundName} 仍有材料核验硬缺口，不能直接作为正式研究结论。`
      : '第一名暂未发现材料核验硬缺口，可进入下一层研究复核。',
    runnerUp?.materialMissingCount && !leader.materialMissingCount
      ? `相对 ${runnerUp.fundName}，领先样本少了材料核验硬缺口阻断。`
      : '',
    leader.replayReturn !== null && runnerUp?.replayReturn !== null && runnerUp?.replayReturn !== undefined
      ? `${input.researchPlanLabel}费用优先回放收益差 ${percentText(leader.replayReturn - runnerUp.replayReturn)}。`
      : '历史持有体验回放不足，收益差暂不能作为主要依据。',
    leader.replayDrawdown !== null && runnerUp?.replayDrawdown !== null && runnerUp?.replayDrawdown !== undefined
      ? `回撤差 ${percentText(Math.abs(leader.replayDrawdown) - Math.abs(runnerUp.replayDrawdown))}；负数代表第一名回撤更低。`
      : '',
    runnerUp ? `研究证据分差 ${signedNumber(leader.evidenceScore - runnerUp.evidenceScore)}。` : '',
    runnerUp ? `专业评分差 ${signedNumber(Number(professionalScoreDelta(leader, runnerUp).toFixed(1)))}。` : '',
    leader.feeComparable ? '第一名费用证据可初步横比。' : '第一名费用证据仍不可直接横比，需要补费率/赎回规则。',
  ].filter(Boolean)
}

export const comparisonResearchSummaryTool: ResearchTool<ComparisonResearchSummaryInput, ComparisonResearchSummaryOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'comparison',
    purpose: '生成横评研究摘要、判断依据和排序原因，避免报告构建器散落叙事规则。',
    inputSchema: 'ComparisonResearchSummaryInput',
    outputSchema: 'ComparisonResearchSummaryOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: false,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '研究摘要只解释证据排序和复核方向，不输出操作指令。',
    ],
  },
  run(input) {
    const decisionBasis = buildDecisionBasis(input)
    const decisionReasons = buildReasons(input)
    const hardBlocks = input.leader ? [] : ['缺少可解释领先样本，不能生成横评研究摘要。']
    return createToolResult(toolName, version, input, {
      decisionBasis,
      decisionReasons,
      policy: {
        sourceReferences: [
          'QuantStats/Empyrical attribution-style metric explanation',
          'OpenBB provider-style evidence separation',
          'FinRobot auditable summary orchestration',
        ],
        hardBoundary: '横评研究摘要只能解释结构化证据；材料、费用或回放缺失时必须保留待复核语义。',
      },
    }, {
      ok: hardBlocks.length === 0,
      hardBlocks,
      evidence: input.leader ? [{
        id: `comparison-research-summary:${input.leader.windCode}`,
        label: '横评研究摘要',
        source: 'comparison.research_summary.derived_metric',
        freshness: 'derived',
        subjectId: input.leader.windCode,
        note: decisionBasis,
      }] : [],
      gaps: input.leader && (input.leader.materialMissingCount > 0 || input.feeGapCount > 0 || input.replayEvidenceCount === 0)
        ? [{
            key: `comparison-research-summary:${input.leader.windCode}`,
            label: '横评摘要证据待补',
            severity: input.leader.materialMissingCount > 0 ? 'hard_block' : 'verify_first',
            subjectId: input.leader.windCode,
            reason: decisionReasons.join('；') || decisionBasis,
            requiredBeforeFormalReview: true,
          }]
        : [],
      nextActions: input.leader && (input.leader.materialMissingCount > 0 || input.feeGapCount > 0 || input.replayEvidenceCount === 0)
        ? [{
            key: `comparison-research-summary:${input.leader.windCode}`,
            label: '补横评摘要证据',
            href: `/funds/${encodeURIComponent(input.leader.windCode)}`,
            priority: input.leader.materialMissingCount > 0 ? 'high' : 'medium',
            reason: decisionBasis,
          }]
        : [],
    })
  },
}
