import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type CompanyProductLineInput = {
  name: string
  assetClass?: string | null
  fundCount?: number | null
  activeFundCount?: number | null
  totalAsset?: number | null
  flagshipFundCodes?: string[] | null
  averageExcessReturn?: number | null
  issuanceCount?: number | null
  liquidationCount?: number | null
}

export type CompanyResearchEventInput = {
  eventDate?: string | null
  eventType?: string | null
  title?: string | null
  affectedFundCodes?: string[] | null
  researchImpact?: string | null
}

export type CompanyResearchInput = {
  companyId?: string | null
  companyName: string
  researchTeam?: string | null
  platformCapabilityScore?: number | null
  productLines?: CompanyProductLineInput[]
  scaleTrend?: Array<{ asOfDate: string; totalAsset: number | null }>
  events?: CompanyResearchEventInput[]
  sameCompanyReviewCount?: number | null
  source?: string | null
}

export type CompanyResearchOutput = {
  companyReady: boolean
  productLineCount: number
  activeProductLineCount: number
  totalAsset: number | null
  flagshipFundCodes: string[]
  issuanceCount: number
  liquidationCount: number
  scaleChange: number | null
  platformCapability: {
    researchTeam: string
    score: number | null
    status: string
  }
  productLineReview: Array<{
    name: string
    assetClass: string
    fundCount: number | null
    totalAsset: number | null
    averageExcessReturn: number | null
    warning: string
  }>
  eventSummary: {
    eventCount: number
    liquidationEventCount: number
    teamOrManagerEventCount: number
  }
  sameCompanyReview: {
    sampleCount: number | null
    status: string
  }
  missingDimensions: string[]
  warnings: string[]
  policy: {
    hardBoundary: string
    requiredDimensions: string[]
  }
}

const toolName = 'company-research'
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

function asArray<T>(value: T[] | null | undefined) {
  return Array.isArray(value) ? value : []
}

function sumNumbers(values: Array<number | null>) {
  const valid = values.filter((item): item is number => item !== null)
  return valid.length ? round2(valid.reduce((sum, item) => sum + item, 0)) : null
}

function scaleChange(scaleTrend: Array<{ asOfDate: string; totalAsset: number | null }>) {
  const rows = scaleTrend
    .map((row) => ({ asOfDate: normalizeText(row.asOfDate), totalAsset: finiteNumber(row.totalAsset) }))
    .filter((row): row is { asOfDate: string; totalAsset: number } => Boolean(row.asOfDate) && row.totalAsset !== null)
    .sort((left, right) => left.asOfDate.localeCompare(right.asOfDate))
  if (rows.length < 2) return null
  return round2(rows.at(-1)!.totalAsset - rows[0].totalAsset)
}

export const companyResearchTool: ResearchTool<CompanyResearchInput, CompanyResearchOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'fund',
    purpose: '评价基金公司产品线、投研团队、平台能力、发行/清盘/规模变化和同公司产品横评证据。',
    inputSchema: 'CompanyResearchInput',
    outputSchema: 'CompanyResearchOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '基金公司研究只服务基金筛选、基金分析和经理评价，不输出公司层面的配置或交易结论。',
      '产品线、投研团队、平台能力和同公司横评证据缺失时，不能把公司品牌直接当成基金质量结论。',
    ],
  },
  run(input) {
    const productLines = asArray(input.productLines).filter((line) => normalizeText(line.name))
    const events = asArray(input.events)
    const trend = asArray(input.scaleTrend)
    const totalAsset = sumNumbers(productLines.map((line) => finiteNumber(line.totalAsset)))
    const activeProductLineCount = productLines.filter((line) => (finiteNumber(line.activeFundCount) ?? finiteNumber(line.fundCount) ?? 0) > 0).length
    const flagshipFundCodes = Array.from(new Set(productLines.flatMap((line) => asArray(line.flagshipFundCodes).map(normalizeText).filter(Boolean))))
    const issuanceCount = productLines.reduce((sum, line) => sum + (finiteNumber(line.issuanceCount) ?? 0), 0)
    const liquidationCount = productLines.reduce((sum, line) => sum + (finiteNumber(line.liquidationCount) ?? 0), 0)
    const platformScore = finiteNumber(input.platformCapabilityScore)
    const sameCompanyReviewCount = finiteNumber(input.sameCompanyReviewCount)
    const liquidationEventCount = events.filter((event) => normalizeText(event.eventType).includes('清盘') || normalizeText(event.title).includes('清盘')).length
    const teamOrManagerEventCount = events.filter((event) => {
      const text = `${normalizeText(event.eventType)} ${normalizeText(event.title)}`
      return text.includes('团队') || text.includes('经理') || text.includes('投研') || text.toLowerCase().includes('team')
    }).length
    const productLineReview = productLines.map((line) => {
      const fundCount = finiteNumber(line.fundCount)
      const lineTotalAsset = finiteNumber(line.totalAsset)
      const averageExcessReturn = finiteNumber(line.averageExcessReturn)
      const lineLiquidationCount = finiteNumber(line.liquidationCount) ?? 0
      return {
        name: normalizeText(line.name),
        assetClass: normalizeText(line.assetClass) || '资产类别待补',
        fundCount,
        totalAsset: lineTotalAsset,
        averageExcessReturn,
        warning: [
          fundCount !== null && fundCount <= 1 ? '产品线样本偏薄' : '',
          lineTotalAsset !== null && lineTotalAsset < 10 ? '产品线规模偏小' : '',
          lineLiquidationCount > 0 ? `近阶段清盘 ${lineLiquidationCount} 只` : '',
        ].filter(Boolean).join('；') || '暂未触发产品线硬警示',
      }
    })
    const missingDimensions = [
      normalizeText(input.companyName) ? '' : '基金公司',
      productLines.length ? '' : '产品线',
      normalizeText(input.researchTeam) ? '' : '投研团队',
      platformScore !== null ? '' : '平台能力',
      trend.length >= 2 ? '' : '规模变化',
      events.length ? '' : '发行/清盘/团队事件',
      sameCompanyReviewCount !== null && sameCompanyReviewCount >= 2 ? '' : '同公司产品横评',
    ].filter(Boolean)
    const warnings = [
      liquidationCount > 0 || liquidationEventCount > 0 ? `检测到清盘相关信号 ${liquidationCount + liquidationEventCount} 个，需复核产品线持续性。` : '',
      platformScore !== null && platformScore < 40 ? '平台能力评分偏低，需谨慎区分个别经理能力和公司平台支持。' : '',
      activeProductLineCount >= 6 ? '产品线跨度较大，需要按策略族谱拆开横评，不能用公司整体均值代替。' : '',
      sameCompanyReviewCount !== null && sameCompanyReviewCount < 2 ? '同公司横评样本不足，不能判断产品线内相对优劣。' : '',
    ].filter(Boolean)
    const output: CompanyResearchOutput = {
      companyReady: missingDimensions.length === 0,
      productLineCount: productLines.length,
      activeProductLineCount,
      totalAsset,
      flagshipFundCodes,
      issuanceCount,
      liquidationCount,
      scaleChange: scaleChange(trend),
      platformCapability: {
        researchTeam: normalizeText(input.researchTeam) || '投研团队待补',
        score: platformScore,
        status: platformScore === null ? '平台能力待补' : platformScore >= 70 ? '平台能力较强' : platformScore >= 40 ? '平台能力可观察' : '平台能力偏弱',
      },
      productLineReview,
      eventSummary: {
        eventCount: events.length,
        liquidationEventCount,
        teamOrManagerEventCount,
      },
      sameCompanyReview: {
        sampleCount: sameCompanyReviewCount,
        status: sameCompanyReviewCount === null ? '同公司横评待补' : sameCompanyReviewCount >= 5 ? '同公司横评较充分' : sameCompanyReviewCount >= 2 ? '同公司横评可观察' : '同公司横评样本不足',
      },
      missingDimensions,
      warnings,
      policy: {
        hardBoundary: '公司研究证据不完整时，只能输出平台和产品线补证方向；不得把基金公司品牌、规模或单一明星经理直接外推为单基金研究结论。',
        requiredDimensions: ['产品线', '投研团队', '平台能力', '发行/清盘/规模变化', '同公司产品横评'],
      },
    }
    const subjectId = normalizeText(input.companyId) || normalizeText(input.companyName)
    return createToolResult(toolName, version, input, output, {
      ok: output.companyReady,
      hardBlocks: productLines.length ? [] : ['缺少基金公司产品线，不能进行公司研究横评。'],
      evidence: [
        {
          id: `company-research:${subjectId || 'missing'}`,
          label: `${normalizeText(input.companyName) || '基金公司'} 公司研究`,
          source: normalizeText(input.source) || 'company_research_tool',
          freshness: 'derived',
          subjectId: subjectId || undefined,
          note: `产品线 ${productLines.length}；规模 ${totalAsset ?? '待补'}；发行 ${issuanceCount}；清盘 ${liquidationCount}；缺口 ${missingDimensions.join('、') || '无'}`,
        },
      ],
      gaps: missingDimensions.map((dimension) => ({
        key: `company-research:${dimension}`,
        label: `${dimension}待补`,
        severity: dimension === '产品线' ? 'hard_block' : 'verify_first',
        subjectId: subjectId || undefined,
        reason: `${dimension}不完整，基金公司研究不能形成闭环判断。`,
        requiredBeforeFormalReview: true,
      })),
      nextActions: missingDimensions.map((dimension) => ({
        key: `company-research:${dimension}`,
        label: `补齐${dimension}`,
        href: '/managers',
        priority: dimension === '产品线' ? 'high' : 'medium',
        reason: `${dimension}是基金公司研究的必要证据。`,
      })),
    })
  },
}
