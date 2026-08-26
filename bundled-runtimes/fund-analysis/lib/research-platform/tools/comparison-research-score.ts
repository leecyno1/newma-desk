import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type ComparisonResearchPlan = 'lump_sum' | 'sip'

export type ComparisonResearchScoreBreakdown = {
  key: 'professional' | 'evidence' | 'replay' | 'drawdown' | 'stress' | 'fee'
  label: string
  rawScore: number
  contribution: number
  weight: number
  note: string
}

export type ComparisonResearchScoreInputItem = {
  windCode: string
  fundName: string
  professionalScore: number | null
  evidenceScore: number
  requiredMissingCount: number
  feeComparable: boolean
  feeGapReason: string
  missingItems: string[]
  materialMissingCount: number
  operationLabel: string
  conclusion: string
  replay: {
    returnRate: number | null
    drawdown: number | null
    stressScore: number | null
    stressLabel: string | null
    longestUnderwaterDays: number | null
    worstThreeMonthReturn: number | null
    evidenceGateStatus: 'pass' | 'verify_first' | null
    evidenceGateMissingEvidence: string[]
    evidenceGateSummary: string | null
  } | null
}

export type ComparisonResearchScoreInput = {
  researchPlan: ComparisonResearchPlan
  researchPlanLabel: string
  items: ComparisonResearchScoreInputItem[]
}

export type ComparisonResearchScoreRow = {
  windCode: string
  researchScore: number
  breakdown: ComparisonResearchScoreBreakdown[]
  caps: string[]
  reasons: string[]
}

export type ComparisonResearchScoreOutput = {
  rows: ComparisonResearchScoreRow[]
  scoringPolicy: {
    weights: Record<ComparisonResearchScoreBreakdown['key'], number>
    sourceReferences: string[]
    hardBoundary: string
  }
}

const toolName = 'comparison-research-score'
const version = '1.0.0'

const weights: Record<ComparisonResearchScoreBreakdown['key'], number> = {
  professional: 0.22,
  evidence: 0.20,
  replay: 0.20,
  drawdown: 0.14,
  stress: 0.12,
  fee: 0.12,
}

function clampScore(value: number) {
  return Math.max(0, Math.min(100, value))
}

function percentText(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return `${(Number(value) * 100).toFixed(2)}%`
}

function drawdownComfortScore(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 0
  const drawdown = Math.abs(Number(value))
  if (drawdown <= 0.05) return 92
  if (drawdown <= 0.12) return 80
  if (drawdown <= 0.20) return 66
  if (drawdown <= 0.30) return 48
  if (drawdown <= 0.45) return 30
  return 15
}

function buildReturnScoreScale(items: ComparisonResearchScoreInputItem[]) {
  const returns = items
    .map((item) => item.replay?.returnRate)
    .filter((value): value is number => value !== null && value !== undefined)
  const minReturn = returns.length ? Math.min(...returns) : null
  const maxReturn = returns.length ? Math.max(...returns) : null
  return (value: number | null | undefined) => {
    if (value === null || value === undefined || minReturn === null || maxReturn === null) return 0
    if (maxReturn === minReturn) return 70
    return clampScore(35 + ((value - minReturn) / (maxReturn - minReturn)) * 60)
  }
}

function scoreItem(
  item: ComparisonResearchScoreInputItem,
  input: ComparisonResearchScoreInput,
  returnScore: (value: number | null | undefined) => number,
): ComparisonResearchScoreRow {
  const professionalScoreMissing = item.professionalScore === null
  const professionalScore = professionalScoreMissing ? 0 : item.professionalScore as number
  const replayReturn = item.replay?.returnRate ?? null
  const replayDrawdown = item.replay?.drawdown ?? null
  const replayMissing = replayReturn === null || replayReturn === undefined
  const replayDrawdownMissing = replayDrawdown === null || replayDrawdown === undefined
  const replayScore = returnScore(replayReturn)
  const drawdownScore = drawdownComfortScore(replayDrawdown)
  const stressScoreMissing = item.replay?.stressScore === null || item.replay?.stressScore === undefined
  const stressScore = stressScoreMissing ? 0 : item.replay?.stressScore as number
  const replayEvidenceGateVerify = item.replay?.evidenceGateStatus === 'verify_first'
  const feeScore = item.feeComparable ? 88 : Math.max(25, 65 - item.missingItems.length * 8)
  const breakdown: ComparisonResearchScoreBreakdown[] = [
    {
      key: 'professional',
      label: '专业评分',
      rawScore: professionalScore,
      contribution: professionalScore * weights.professional,
      weight: weights.professional,
      note: professionalScoreMissing ? '专业评分待补，本项不加分，并触发横评分封顶' : `专业评分 ${professionalScore.toFixed(1)}`,
    },
    {
      key: 'evidence',
      label: '研究证据',
      rawScore: item.evidenceScore,
      contribution: item.evidenceScore * weights.evidence,
      weight: weights.evidence,
      note: `证据完整度 ${item.evidenceScore}，必补 ${item.requiredMissingCount} 项`,
    },
    {
      key: 'replay',
      label: '历史回放',
      rawScore: replayScore,
      contribution: replayScore * weights.replay,
      weight: weights.replay,
      note: replayMissing ? '历史回放缺失，本项不加分，并触发研究评分封顶' : `${input.researchPlanLabel}回放 ${percentText(replayReturn)}`,
    },
    {
      key: 'drawdown',
      label: '回撤舒适度',
      rawScore: drawdownScore,
      contribution: drawdownScore * weights.drawdown,
      weight: weights.drawdown,
      note: replayDrawdownMissing ? '回撤回放缺失，本项不加分，并触发研究评分封顶' : `回撤 ${percentText(replayDrawdown)}，舒适度 ${drawdownScore.toFixed(0)}`,
    },
    {
      key: 'stress',
      label: '压力体验',
      rawScore: stressScore,
      contribution: stressScore * weights.stress,
      weight: weights.stress,
      note: !stressScoreMissing
        ? `${item.replay?.stressLabel || '压力体验'}，最长亏损等待 ${Math.round(item.replay?.longestUnderwaterDays ?? 0)} 天，最差三个月 ${percentText(item.replay?.worstThreeMonthReturn)}`
        : '压力体验缺失，本项不加分，并触发研究评分封顶',
    },
    {
      key: 'fee',
      label: '费用可比性',
      rawScore: feeScore,
      contribution: feeScore * weights.fee,
      weight: weights.fee,
      note: item.feeComparable ? '费用证据可初步横比' : `费用待补：${item.feeGapReason}`,
    },
  ]
  let researchScore = clampScore(breakdown.reduce((sum, part) => sum + part.contribution, 0))
  const caps: string[] = []
  if (item.requiredMissingCount > 0) {
    researchScore = Math.min(researchScore, 72)
    caps.push(`必补项 ${item.requiredMissingCount} 项，研究评分封顶 72`)
  }
  if (professionalScoreMissing) {
    researchScore = Math.min(researchScore, 65)
    caps.push('专业评分缺失，研究评分封顶 65')
  }
  if (replayMissing) {
    researchScore = Math.min(researchScore, 68)
    caps.push('历史回放缺失，研究评分封顶 68')
  }
  if (replayDrawdownMissing) {
    researchScore = Math.min(researchScore, 70)
    caps.push('回撤回放缺失，研究评分封顶 70')
  }
  if (stressScoreMissing) {
    researchScore = Math.min(researchScore, 70)
    caps.push('压力体验缺失，研究评分封顶 70')
  }
  if (replayEvidenceGateVerify) {
    researchScore = Math.min(researchScore, 62)
    caps.push('测算证据门禁未过，研究评分封顶 62')
  }
  if (item.materialMissingCount > 0) {
    researchScore = Math.min(researchScore, 56)
    caps.push(`材料核验硬缺口 ${item.materialMissingCount} 项，研究评分封顶 56`)
  }
  if (item.operationLabel.includes('阻断') || item.operationLabel.includes('暂停') || item.conclusion === '暂不进入研究') {
    researchScore = Math.min(researchScore, 25)
    caps.push('运作状态阻断，研究评分封顶 25')
  }

  const reasons = [
    `专业评分 ${item.professionalScore !== null ? item.professionalScore.toFixed(1) : '待补'}`,
    `证据分 ${item.evidenceScore}`,
    replayReturn !== null && replayReturn !== undefined ? `${input.researchPlanLabel}回放 ${percentText(replayReturn)}` : '历史回放待跑',
    `回撤舒适度 ${drawdownComfortScore(replayDrawdown).toFixed(0)}`,
    item.replay?.stressScore !== null && item.replay?.stressScore !== undefined
      ? `压力体验 ${item.replay.stressScore} 分，最长亏损等待 ${Math.round(item.replay.longestUnderwaterDays ?? 0)} 天`
      : '压力体验待跑',
    item.replay?.evidenceGateStatus === 'pass'
      ? '测算证据门禁通过'
      : item.replay?.evidenceGateStatus === 'verify_first'
        ? `测算门禁待补：${item.replay.evidenceGateMissingEvidence.slice(0, 4).join('、') || item.replay.evidenceGateSummary || '只可作压力观察'}`
        : '测算证据门禁待补',
    item.feeComparable ? '费用可初步横比' : `费用待补：${item.feeGapReason}`,
    item.materialMissingCount > 0 ? `材料核验缺 ${item.materialMissingCount} 项` : '材料核验未见硬缺口',
  ]

  return {
    windCode: item.windCode,
    researchScore: Math.round(researchScore),
    breakdown,
    caps,
    reasons,
  }
}

export const comparisonResearchScoreTool: ResearchTool<ComparisonResearchScoreInput, ComparisonResearchScoreOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'comparison',
    purpose: '把横评研究评分、权重、证据缺口封顶和解释理由集中为可审计 ToolResult，避免页面或报告散落评分规则。',
    inputSchema: 'ComparisonResearchScoreInput',
    outputSchema: 'ComparisonResearchScoreOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '研究评分只用于同类横评排序和复核优先级，不输出操作指令或配置动作。',
      '历史回放、费用、材料核验或压力体验缺失时必须触发封顶或 gaps。',
    ],
  },
  run(input) {
    const returnScore = buildReturnScoreScale(input.items)
    const rows = input.items.map((item) => scoreItem(item, input, returnScore))
    const itemsWithGaps = input.items.filter((item) => (
      item.requiredMissingCount > 0
      || item.materialMissingCount > 0
      || !item.replay
      || item.replay.evidenceGateStatus === 'verify_first'
      || !item.feeComparable
    ))
    const hardBlocks = input.items.length === 0 ? ['缺少横评样本，不能生成研究评分。'] : []
    return createToolResult(toolName, version, input, {
      rows,
      scoringPolicy: {
        weights,
        sourceReferences: [
          'QuantStats/Empyrical 风险收益指标拆解',
          'OpenBB provider-style 数据来源隔离',
          'FinRobot tool-to-report 可审计编排',
        ],
        hardBoundary: '横评研究评分是证据排序工具；缺历史回放、费用或材料核验时必须降级为待复核，不形成操作结论。',
      },
    }, {
      ok: hardBlocks.length === 0 && itemsWithGaps.length === 0,
      hardBlocks,
      evidence: rows.map((row) => ({
        id: `comparison-research-score:${row.windCode}`,
        label: '横评研究评分',
        source: 'comparison.research_score.derived_metric',
        freshness: 'derived',
        subjectId: row.windCode,
        note: `研究评分 ${row.researchScore}；封顶 ${row.caps.length ? row.caps.join('；') : '无'}`,
      })),
      gaps: itemsWithGaps.map((item) => ({
        key: `comparison-research-score:${item.windCode}`,
        label: '横评评分证据待补',
        severity: item.materialMissingCount > 0 ? 'hard_block' : 'verify_first',
        subjectId: item.windCode,
        reason: [
          item.requiredMissingCount > 0 ? `必补证据 ${item.requiredMissingCount} 项` : '',
          item.materialMissingCount > 0 ? `材料核验 ${item.materialMissingCount} 项` : '',
          !item.replay ? '历史回放缺失' : '',
          item.replay?.evidenceGateStatus === 'verify_first' ? '测算证据门禁待补' : '',
          !item.feeComparable ? `费用不可比：${item.feeGapReason}` : '',
        ].filter(Boolean).join('；'),
        requiredBeforeFormalReview: true,
      })),
      nextActions: itemsWithGaps.map((item) => ({
        key: `comparison-research-score:${item.windCode}`,
        label: '补横评评分证据',
        href: `/funds/${encodeURIComponent(item.windCode)}`,
        priority: item.materialMissingCount > 0 ? 'high' : 'medium',
        reason: `${item.fundName} 横评研究评分仍有证据缺口。`,
      })),
    })
  },
}
