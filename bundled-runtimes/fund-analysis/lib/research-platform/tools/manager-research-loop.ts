import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type ManagerTenureSliceInput = {
  fundCode: string
  fundName?: string | null
  role?: string | null
  coManagerNames?: string[] | null
  startDate?: string | null
  endDate?: string | null
  excessReturn?: number | null
  maxDrawdown?: number | null
}

export type ManagerRepresentativeFundInput = {
  fundCode: string
  fundName?: string | null
  excessReturn?: number | null
  maxDrawdown?: number | null
  attributionSummary?: string | null
  styleDriftScore?: number | null
  platformContribution?: number | null
}

export type ManagerTransitionEventInput = {
  fundCode?: string | null
  eventDate?: string | null
  eventType?: string | null
  previousManagerNames?: string[] | null
  nextManagerNames?: string[] | null
  impactReturn?: number | null
  impactDrawdown?: number | null
}

export type ManagerResearchLoopInput = {
  managerId: string
  managerName?: string | null
  asOfDate?: string | null
  tenureSlices?: ManagerTenureSliceInput[]
  representativeFunds?: ManagerRepresentativeFundInput[]
  transitionEvents?: ManagerTransitionEventInput[]
  platformEvidence?: {
    company?: string | null
    researchTeam?: string | null
    platformContribution?: number | null
  } | null
}

export type ManagerResearchLoopOutput = {
  loopReady: boolean
  tenureCoverage: {
    sliceCount: number
    activeSliceCount: number
    coManagedSliceCount: number
    averageTenureYears: number | null
    status: string
  }
  representativeAttribution: {
    representativeCount: number
    bestFund: string
    weakestFund: string
    averageExcessReturn: number | null
    averageMaxDrawdown: number | null
  }
  styleDrift: {
    averageStyleDriftScore: number | null
    status: string
  }
  transitionImpact: {
    eventCount: number
    departureOrSuccessionCount: number
    status: string
  }
  platformContribution: {
    company: string
    researchTeam: string
    contributionScore: number | null
    status: string
  }
  missingDimensions: string[]
  warnings: string[]
  policy: {
    hardBoundary: string
    requiredDimensions: string[]
  }
}

const toolName = 'manager-research-loop'
const version = '1.0.0'

function normalizeText(value: unknown) {
  return String(value ?? '').trim()
}

function finiteNumber(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function round2(value: number) {
  return Math.round(value * 100) / 100
}

function dateOrNull(value: unknown) {
  const text = normalizeText(value)
  if (!text) return null
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? null : date
}

function yearsBetween(startDate: Date, endDate: Date) {
  if (endDate < startDate) return null
  return (endDate.getTime() - startDate.getTime()) / (365.25 * 24 * 60 * 60 * 1000)
}

function average(values: Array<number | null>) {
  const valid = values.filter((item): item is number => item !== null)
  return valid.length ? round2(valid.reduce((sum, item) => sum + item, 0) / valid.length) : null
}

function normalizeNames(values: string[] | null | undefined) {
  return Array.isArray(values) ? values.map((item) => normalizeText(item)).filter(Boolean) : []
}

export const managerResearchLoopTool: ResearchTool<ManagerResearchLoopInput, ManagerResearchLoopOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'manager',
    purpose: '把基金经理任期切片、共管产品拆分、代表作归因、风格漂移、离任/接任影响和平台贡献统一成研究闭环。',
    inputSchema: 'ManagerResearchLoopInput',
    outputSchema: 'ManagerResearchLoopOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '经理评价必须落到任期切片和基金产品，不得把公司名气或经理名气直接当成基金结论。',
      '共管、离任、接任和平台贡献未拆清前，只能输出研究假设和补证清单。',
    ],
  },
  run(input) {
    const asOfDate = dateOrNull(input.asOfDate) || new Date()
    const tenureSlices = Array.isArray(input.tenureSlices) ? input.tenureSlices : []
    const representativeFunds = Array.isArray(input.representativeFunds) ? input.representativeFunds : []
    const transitionEvents = Array.isArray(input.transitionEvents) ? input.transitionEvents : []
    const tenureYears = tenureSlices.map((slice) => {
      const start = dateOrNull(slice.startDate)
      if (!start) return null
      return yearsBetween(start, dateOrNull(slice.endDate) || asOfDate)
    })
    const activeSliceCount = tenureSlices.filter((slice) => !normalizeText(slice.endDate)).length
    const coManagedSliceCount = tenureSlices.filter((slice) => normalizeNames(slice.coManagerNames).length > 0 || normalizeText(slice.role) === 'co_manager').length
    const averageTenureYears = average(tenureYears)
    const representativeWithReturn = representativeFunds
      .map((fund) => ({ fund, excessReturn: finiteNumber(fund.excessReturn) }))
      .filter((item): item is { fund: ManagerRepresentativeFundInput; excessReturn: number } => item.excessReturn !== null)
      .sort((left, right) => right.excessReturn - left.excessReturn)
    const bestFund = representativeWithReturn[0]?.fund.fundName || representativeWithReturn[0]?.fund.fundCode || '代表作待补'
    const weakestFund = representativeWithReturn.at(-1)?.fund.fundName || representativeWithReturn.at(-1)?.fund.fundCode || '代表作待补'
    const averageExcessReturn = average(representativeFunds.map((fund) => finiteNumber(fund.excessReturn)))
    const averageMaxDrawdown = average(representativeFunds.map((fund) => finiteNumber(fund.maxDrawdown)))
    const averageStyleDriftScore = average(representativeFunds.map((fund) => finiteNumber(fund.styleDriftScore)))
    const departureOrSuccessionCount = transitionEvents.filter((event) => {
      const eventType = normalizeText(event.eventType)
      return eventType.includes('离任') || eventType.includes('接任') || eventType.toLowerCase().includes('departure') || eventType.toLowerCase().includes('succession')
    }).length
    const platformContribution = finiteNumber(input.platformEvidence?.platformContribution)
    const missingDimensions = [
      tenureSlices.length ? '' : '经理任期切片',
      coManagedSliceCount || tenureSlices.length ? '' : '共管产品拆分',
      representativeFunds.length ? '' : '代表作归因',
      averageStyleDriftScore !== null ? '' : '风格漂移',
      transitionEvents.length ? '' : '离任/接任影响',
      platformContribution !== null || normalizeText(input.platformEvidence?.researchTeam) ? '' : '团队平台贡献',
    ].filter(Boolean)
    const warnings = [
      averageTenureYears !== null && averageTenureYears < 2 ? '平均任期不足 2 年，不能把长周期基金业绩直接归因给该经理。' : '',
      coManagedSliceCount > 0 ? `存在 ${coManagedSliceCount} 段共管任期，代表作归因必须拆分。` : '',
      averageStyleDriftScore !== null && averageStyleDriftScore >= 60 ? '风格漂移分偏高，需要复核持仓和基准口径变化。' : '',
      departureOrSuccessionCount > 0 ? `存在 ${departureOrSuccessionCount} 个离任/接任事件，需要观察交接窗口收益和回撤。` : '',
      platformContribution === null ? '平台贡献待补，不能区分经理个人能力与公司投研平台支持。' : '',
    ].filter(Boolean)
    const output: ManagerResearchLoopOutput = {
      loopReady: missingDimensions.length === 0,
      tenureCoverage: {
        sliceCount: tenureSlices.length,
        activeSliceCount,
        coManagedSliceCount,
        averageTenureYears,
        status: tenureSlices.length === 0 ? '任期待补' : averageTenureYears !== null && averageTenureYears >= 3 ? '任期样本较完整' : '任期样本偏短',
      },
      representativeAttribution: {
        representativeCount: representativeFunds.length,
        bestFund,
        weakestFund,
        averageExcessReturn,
        averageMaxDrawdown,
      },
      styleDrift: {
        averageStyleDriftScore,
        status: averageStyleDriftScore === null ? '风格漂移待补' : averageStyleDriftScore >= 60 ? '漂移偏高' : averageStyleDriftScore >= 30 ? '漂移可观察' : '风格较稳定',
      },
      transitionImpact: {
        eventCount: transitionEvents.length,
        departureOrSuccessionCount,
        status: transitionEvents.length === 0 ? '交接事件待补' : departureOrSuccessionCount > 0 ? '需复核交接影响' : '未见离任/接任冲击',
      },
      platformContribution: {
        company: normalizeText(input.platformEvidence?.company) || '基金公司待补',
        researchTeam: normalizeText(input.platformEvidence?.researchTeam) || '投研团队待补',
        contributionScore: platformContribution,
        status: platformContribution === null ? '平台贡献待补' : platformContribution >= 70 ? '平台支持较强' : platformContribution >= 40 ? '平台支持可观察' : '平台支持偏弱',
      },
      missingDimensions,
      warnings,
      policy: {
        hardBoundary: '经理闭环未完成时，经理评价只能作为研究线索；不得把历史收益、代表作或公司平台直接外推为目标基金结论。',
        requiredDimensions: ['经理任期切片', '共管产品拆分', '代表作归因', '风格漂移', '离任/接任影响', '团队平台贡献'],
      },
    }
    const subjectId = normalizeText(input.managerId)
    return createToolResult(toolName, version, input, output, {
      ok: output.loopReady,
      hardBlocks: tenureSlices.length ? [] : ['缺少经理任期切片，不能进行经理归因闭环评价。'],
      evidence: [
        {
          id: `manager-loop:${subjectId || 'missing'}`,
          label: `${normalizeText(input.managerName) || subjectId || '基金经理'} 研究闭环`,
          source: 'manager_research_loop_tool',
          freshness: 'derived',
          subjectId: subjectId || undefined,
          note: `任期切片 ${tenureSlices.length}；代表作 ${representativeFunds.length}；交接事件 ${transitionEvents.length}；缺口 ${missingDimensions.join('、') || '无'}`,
        },
      ],
      gaps: missingDimensions.map((dimension) => ({
        key: `manager-loop:${dimension}`,
        label: `${dimension}待补`,
        severity: dimension === '经理任期切片' ? 'hard_block' : 'verify_first',
        subjectId: subjectId || undefined,
        reason: `${dimension}不完整，经理评价不能形成闭环研究结论。`,
        requiredBeforeFormalReview: true,
      })),
      nextActions: missingDimensions.map((dimension) => ({
        key: `manager-loop:${dimension}`,
        label: `补齐${dimension}`,
        href: subjectId ? `/managers/${encodeURIComponent(subjectId)}` : '/managers',
        priority: dimension === '经理任期切片' ? 'high' : 'medium',
        reason: `${dimension}是基金经理研究闭环的必要证据。`,
      })),
    })
  },
}
