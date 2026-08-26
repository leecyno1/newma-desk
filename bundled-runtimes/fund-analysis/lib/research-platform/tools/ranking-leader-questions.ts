import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type RankingLeaderQuestionStatus = '通过' | '待补' | '阻断'

export type RankingLeaderFund = {
  windCode: string
  name: string
  investorScore: number
  investorRating: string
  reasons?: string[]
  purchaseGate: {
    level: 'ready' | 'verify_first' | 'blocked' | string
    label: string
    description: string
    evidenceGrade: string
    hardBlocks?: string[]
    cautionFlags?: string[]
  }
  scoreBreakdown?: Array<{ label: string; score: number; maxScore: number }>
  costEvidence?: {
    status?: 'strong' | 'weak' | 'missing' | string
    label?: string
    totalAnnualFee?: number | null
    purchaseFeeRate?: number | null
  } | null
}

export type RankingLeaderSalesGap = {
  missingCount: number
  missingItems: string[]
  alertsHref?: string | null
}

export type RankingLeaderQuestionsInput = {
  leader: RankingLeaderFund | null
  salesRuleGap?: RankingLeaderSalesGap | null
  peerCount: number
  comparisonCodes: string[]
  visibleFundCount: number
  purchasePlan: 'lump_sum' | 'sip'
  plannedAmount: number
  costMissing: string[]
  rankingReturnHref: string
  fundDetailHref: string
  salesRulesHref: string
  comparisonHref: string
  marketHref: string
}

export type RankingLeaderQuestionRow = {
  question: string
  status: RankingLeaderQuestionStatus
  answer: string
  actionLabel: string
  actionHref: string
}

export type RankingLeaderQuestionsOutput = {
  leader: RankingLeaderFund | null
  rows: RankingLeaderQuestionRow[]
  passCount: number
  blockedCount: number
  verdict: string
  actionLabel: string
  actionHref: string
  hardBoundary: string
}

const toolName = 'ranking-leader-questions'
const version = '1.0.0'

function formatFee(value: number | null | undefined) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)}%` : '待补'
}

function topScoreBreakdown(leader: RankingLeaderFund) {
  return [...(leader.scoreBreakdown || [])]
    .sort((left, right) => (right.score / Math.max(1, right.maxScore)) - (left.score / Math.max(1, left.maxScore)))
    .slice(0, 3)
}

export const rankingLeaderQuestionsTool: ResearchTool<RankingLeaderQuestionsInput, RankingLeaderQuestionsOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'ranking',
    purpose: '把排行榜第一名拆成研究复核四问，防止把排名误读为结论。',
    inputSchema: 'RankingLeaderQuestionsInput',
    outputSchema: 'RankingLeaderQuestionsOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: false,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '排行榜第一名只代表当前口径研究排序，不形成正式研究结论。',
      '必须检查销售规则、成本字段、替代横评和详情页研究核查。',
    ],
  },
  run(input) {
    if (!input.leader) {
      const output: RankingLeaderQuestionsOutput = {
        leader: null,
        rows: [],
        passCount: 0,
        blockedCount: 0,
        verdict: '暂无榜首样本，先扩大榜单或调整筛选条件。',
        actionLabel: '回全市场扩样',
        actionHref: input.marketHref,
        hardBoundary: '没有可解释榜首时，不能形成任何研究结论。',
      }
      return createToolResult(toolName, version, input, output, {
        ok: false,
        hardBlocks: ['暂无榜首样本'],
        gaps: [{
          key: 'ranking-leader',
          label: '榜首样本缺失',
          severity: 'hard_block',
          reason: '排行榜未返回可解释第一名。',
          requiredBeforeFormalReview: true,
        }],
        nextActions: [{
          key: 'expand-ranking-sample',
          label: output.actionLabel,
          href: output.actionHref,
          priority: 'high',
          reason: output.verdict,
        }],
      })
    }

    const leader = input.leader
    const gap = input.salesRuleGap || null
    const rows: RankingLeaderQuestionRow[] = [
      {
        question: '第一名能不能进入研究复核？',
        status: gap || leader.purchaseGate.level === 'blocked' ? '阻断' : leader.purchaseGate.level === 'verify_first' ? '待补' : '通过',
        answer: gap
          ? `不能。${gap.alertsHref ? '复查队列未解决' : '销售规则硬缺口'}仍有 ${gap.missingCount} 项：${gap.missingItems.slice(0, 4).join('、') || '规则证据待补'}。`
          : leader.purchaseGate.level === 'blocked'
            ? `不能。${leader.purchaseGate.hardBlocks?.[0] || leader.purchaseGate.description}`
            : leader.purchaseGate.level === 'verify_first'
              ? `只能补证观察。${leader.purchaseGate.cautionFlags?.[0] || leader.purchaseGate.description}`
              : '可以作为研究线索推进，但仍需详情页研究核查和报告门禁。',
        actionLabel: gap ? gap.alertsHref ? '开复查队列' : '补销售规则' : '看详情复核',
        actionHref: gap ? gap.alertsHref || input.salesRulesHref : input.fundDetailHref,
      },
      {
        question: '为什么是第一名，而不是只看收益排名？',
        status: leader.scoreBreakdown?.length || leader.reasons?.length || input.peerCount >= 5 ? '通过' : '待补',
        answer: [
          `研究分 ${Math.round(leader.investorScore)}，${leader.purchaseGate.label}，证据 ${leader.purchaseGate.evidenceGrade}。`,
          leader.scoreBreakdown?.length ? `主要贡献：${topScoreBreakdown(leader).map((item) => `${item.label}${Math.round(item.score)}/${item.maxScore}`).join('、')}。` : '',
          input.peerCount ? `同类样本 ${input.peerCount} 只。` : '同类样本待补。',
          (leader.reasons || []).slice(0, 2).join('；'),
        ].filter(Boolean).join(' '),
        actionLabel: input.comparisonCodes.length >= 1 ? '拿替代样本横评' : '看详情证据',
        actionHref: input.comparisonCodes.length >= 1 ? input.comparisonHref : input.fundDetailHref,
      },
      {
        question: '计划金额和成本证据能不能执行？',
        status: input.costMissing.length ? '待补' : leader.costEvidence?.status === 'strong' ? '通过' : '待补',
        answer: input.costMissing.length
          ? `成本/申赎字段仍缺：${input.costMissing.slice(0, 5).join('、')}；${input.purchasePlan === 'sip' ? '定投' : '一次性配置'} ${input.plannedAmount.toLocaleString('zh-CN')} 元口径不能默认可执行。`
          : `成本证据 ${leader.costEvidence?.label || '已返回'}；年费 ${formatFee(leader.costEvidence?.totalAnnualFee)}，申购费 ${formatFee(leader.costEvidence?.purchaseFeeRate)}，仍需核验销售平台实时页面。`,
        actionLabel: input.costMissing.length ? '补成本/申赎证据' : '看详情复核成本',
        actionHref: input.costMissing.length ? input.salesRulesHref : input.fundDetailHref,
      },
      {
        question: '有没有替代基金证明第一名不是孤例？',
        status: input.comparisonCodes.length >= 2 ? '通过' : input.visibleFundCount >= 2 ? '待补' : '阻断',
        answer: input.comparisonCodes.length >= 2
          ? `已找到 ${input.comparisonCodes.length} 只可横评替代样本；进入横评后再比较费后回放、回撤预算、经理和份额成本。`
          : input.visibleFundCount >= 2
            ? '榜单有替代样本，但销售规则或证据缺口仍需清理后再横评。'
            : '当前只有单一样本，不能证明第一名相对同类或替代基金占优。',
        actionLabel: input.comparisonCodes.length >= 1 ? '打开榜首横评' : '扩大榜单样本',
        actionHref: input.comparisonCodes.length >= 1 ? input.comparisonHref : input.marketHref,
      },
    ]
    const passCount = rows.filter((row) => row.status === '通过').length
    const blockedCount = rows.filter((row) => row.status === '阻断').length
    const output: RankingLeaderQuestionsOutput = {
      leader,
      rows,
      passCount,
      blockedCount,
      verdict: blockedCount
        ? `榜首 ${leader.name} 仍有硬阻断，不能从排行榜直接推进；先处理阻断项。`
        : passCount === rows.length
          ? `榜首 ${leader.name} 可进入横评和详情页研究核查，但排名本身不是研究结论。`
          : `榜首 ${leader.name} 只能作为优先研究线索，先补齐待补问题后再横评。`,
      actionLabel: input.comparisonCodes.length >= 1 ? '横评榜首和替代样本' : '看榜首详情',
      actionHref: input.comparisonCodes.length >= 1 ? input.comparisonHref : input.fundDetailHref,
      hardBoundary: '榜首只代表当前口径研究排序第一；未完成销售规则、R1-R5、成本、横评和详情页研究核查前，不能进入正式研究结论。',
    }
    return createToolResult(toolName, version, input, output, {
      ok: blockedCount === 0,
      hardBlocks: rows.filter((row) => row.status === '阻断').map((row) => row.answer),
      gaps: rows.filter((row) => row.status !== '通过').map((row) => ({
        key: row.question,
        label: row.status === '阻断' ? '榜首硬阻断' : '榜首证据待补',
        severity: row.status === '阻断' ? 'hard_block' : 'verify_first',
        subjectId: leader.windCode,
        reason: row.answer,
        requiredBeforeFormalReview: true,
      })),
      evidence: [{
        id: `ranking-leader:${leader.windCode}`,
        label: '排行榜榜首研究排序',
        source: 'ranking.investor_score.derived_metric',
        freshness: 'derived',
        subjectId: leader.windCode,
        note: `研究分 ${Math.round(leader.investorScore)}，同类样本 ${input.peerCount} 只。`,
      }],
      nextActions: rows.map((row) => ({
        key: row.question,
        label: row.actionLabel,
        href: row.actionHref,
        priority: row.status === '阻断' ? 'high' : row.status === '待补' ? 'medium' : 'low',
        reason: row.answer,
      })),
    })
  },
}
