import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type HoldingDeepResearchHolding = {
  stockCode?: string | null
  stockName?: string | null
  weight?: number | null
  industry?: string | null
  themeTags?: string[] | null
  styleTags?: string[] | null
  marketCap?: string | null
}

export type HoldingDeepResearchInput = {
  windCode: string
  fundName?: string | null
  quarter?: string | null
  holdings: HoldingDeepResearchHolding[]
  previousHoldings?: HoldingDeepResearchHolding[]
  peerWindCode?: string | null
  peerQuarter?: string | null
  peerHoldings?: HoldingDeepResearchHolding[]
  source?: string | null
}

export type HoldingDeepResearchOutput = {
  holdingReady: boolean
  holdingCount: number
  topTenWeight: number | null
  topThreeWeight: number | null
  topIndustry: string
  topIndustryWeight: number | null
  industryBuckets: Array<{ industry: string; weight: number }>
  themeTags: string[]
  styleTags: string[]
  marketCapBuckets: Array<{ bucket: string; weight: number }>
  turnoverEstimate: number | null
  heavyPositionChanges: Array<{ stockCode: string; stockName: string; change: number; direction: string }>
  similarity: {
    peerWindCode: string
    quarter: string
    overlapWeight: number | null
    jaccardScore: number | null
    cosineSimilarity: number | null
    commonHoldings: Array<{
      stockCode: string
      stockName: string
      weightA: number
      weightB: number
      normalizedWeightA: number
      normalizedWeightB: number
      overlapContribution: number
    }>
    level: string
    methodology: string
    scope: string
  } | null
  concentrationWarnings: string[]
  missingDimensions: string[]
  policy: {
    hardBoundary: string
    requiredDimensions: string[]
  }
}

const toolName = 'holding-deep-research'
const version = '1.1.0'
const similarityMethodology = 'same_quarter_top10_normalized_overlap_v1'
const similarityScope = '仅比较同一报告期前十大公开重仓股，并将各自前十大权重归一化；不是完整组合相关性。'

function normalizeText(value: unknown) {
  return String(value ?? '').trim()
}

function finiteNumber(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function round4(value: number) {
  return Math.round(value * 10000) / 10000
}

function normalizeTags(value: string[] | null | undefined) {
  return Array.isArray(value) ? value.map((item) => normalizeText(item)).filter(Boolean) : []
}

function normalizedHoldings(holdings: HoldingDeepResearchHolding[]) {
  return holdings
    .map((holding) => ({
      stockCode: normalizeText(holding.stockCode),
      stockName: normalizeText(holding.stockName),
      weight: finiteNumber(holding.weight) ?? 0,
      industry: normalizeText(holding.industry) || '行业待补',
      themeTags: normalizeTags(holding.themeTags),
      styleTags: normalizeTags(holding.styleTags),
      marketCap: normalizeText(holding.marketCap) || '市值层待补',
    }))
    .filter((holding) => (holding.stockCode || holding.stockName) && holding.weight > 0)
    .sort((left, right) => right.weight - left.weight)
}

function bucketBy<T extends string>(items: Array<{ weight: number } & Record<T, string>>, key: T) {
  const buckets = new Map<string, number>()
  for (const item of items) {
    buckets.set(item[key], (buckets.get(item[key]) || 0) + item.weight)
  }
  return Array.from(buckets.entries())
    .map(([name, weight]) => ({ name, weight: round4(weight) }))
    .sort((left, right) => right.weight - left.weight)
}

function uniqueSorted(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort()
}

function holdingKey(holding: { stockCode: string; stockName: string }) {
  return holding.stockCode || holding.stockName
}

function normalizedTopTen(holdings: ReturnType<typeof normalizedHoldings>) {
  const topTen = holdings.slice(0, 10)
  const totalWeight = topTen.reduce((sum, holding) => sum + holding.weight, 0)
  if (topTen.length < 5 || totalWeight <= 0) return []
  return topTen.map((holding) => ({
    ...holding,
    normalizedWeight: holding.weight / totalWeight,
  }))
}

function calculateTurnover(
  current: ReturnType<typeof normalizedHoldings>,
  previous: ReturnType<typeof normalizedHoldings>,
) {
  if (!previous.length || !current.length) return null
  const previousWeights = new Map(previous.map((holding) => [holdingKey(holding), holding.weight]))
  const keys = new Set([...current.map(holdingKey), ...previous.map(holdingKey)])
  let absoluteChange = 0
  for (const key of keys) {
    const currentWeight = current.find((holding) => holdingKey(holding) === key)?.weight || 0
    absoluteChange += Math.abs(currentWeight - (previousWeights.get(key) || 0))
  }
  return round4(absoluteChange / 2)
}

function heavyPositionChanges(
  current: ReturnType<typeof normalizedHoldings>,
  previous: ReturnType<typeof normalizedHoldings>,
) {
  const previousWeights = new Map(previous.map((holding) => [holdingKey(holding), holding.weight]))
  return current
    .slice(0, 10)
    .map((holding) => {
      const change = round4(holding.weight - (previousWeights.get(holdingKey(holding)) || 0))
      return {
        stockCode: holding.stockCode,
        stockName: holding.stockName || holding.stockCode,
        change,
        direction: change > 0 ? '增持/新进' : change < 0 ? '减持' : '持平',
      }
    })
    .filter((item) => item.change !== 0)
    .sort((left, right) => Math.abs(right.change) - Math.abs(left.change))
}

function similarity(
  current: ReturnType<typeof normalizedHoldings>,
  peer: ReturnType<typeof normalizedHoldings>,
  peerWindCode: string,
  quarter: string,
  peerQuarter: string,
) {
  if (!peerWindCode || !quarter || !peerQuarter || quarter !== peerQuarter) return null
  const currentTopTen = normalizedTopTen(current)
  const peerTopTen = normalizedTopTen(peer)
  if (!currentTopTen.length || !peerTopTen.length) return null
  const currentMap = new Map(currentTopTen.map((holding) => [holdingKey(holding), holding]))
  const peerMap = new Map(peerTopTen.map((holding) => [holdingKey(holding), holding]))
  const commonKeys = Array.from(currentMap.keys()).filter((key) => peerMap.has(key))
  const unionKeys = new Set([...currentMap.keys(), ...peerMap.keys()])
  const commonHoldings = commonKeys.map((key) => {
    const currentHolding = currentMap.get(key)!
    const peerHolding = peerMap.get(key)!
    return {
      stockCode: currentHolding.stockCode,
      stockName: currentHolding.stockName || peerHolding.stockName || currentHolding.stockCode,
      weightA: currentHolding.weight,
      weightB: peerHolding.weight,
      normalizedWeightA: round4(currentHolding.normalizedWeight),
      normalizedWeightB: round4(peerHolding.normalizedWeight),
      overlapContribution: round4(Math.min(currentHolding.normalizedWeight, peerHolding.normalizedWeight)),
    }
  }).sort((left, right) => right.overlapContribution - left.overlapContribution)
  const overlapWeight = round4(commonHoldings.reduce((sum, item) => sum + item.overlapContribution, 0))
  const jaccardScore = unionKeys.size > 0 ? round4(commonKeys.length / unionKeys.size) : null
  const dotProduct = Array.from(unionKeys).reduce(
    (sum, key) => sum + (currentMap.get(key)?.normalizedWeight || 0) * (peerMap.get(key)?.normalizedWeight || 0),
    0,
  )
  const currentNorm = Math.sqrt(currentTopTen.reduce((sum, holding) => sum + holding.normalizedWeight ** 2, 0))
  const peerNorm = Math.sqrt(peerTopTen.reduce((sum, holding) => sum + holding.normalizedWeight ** 2, 0))
  const cosineSimilarity = currentNorm > 0 && peerNorm > 0 ? round4(dotProduct / (currentNorm * peerNorm)) : null
  const level = overlapWeight >= 0.55 || (jaccardScore !== null && jaccardScore >= 0.5)
    ? '高相似'
    : overlapWeight >= 0.25 || (jaccardScore !== null && jaccardScore >= 0.25)
      ? '中相似'
      : '低相似'
  return {
    peerWindCode,
    quarter,
    overlapWeight,
    jaccardScore,
    cosineSimilarity,
    commonHoldings,
    level,
    methodology: similarityMethodology,
    scope: similarityScope,
  }
}

export const holdingDeepResearchTool: ResearchTool<HoldingDeepResearchInput, HoldingDeepResearchOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'fund',
    purpose: '对基金持仓做穿透、行业/主题/风格标签、集中度、换手、重仓变化和基金间持仓相似度研究。',
    inputSchema: 'HoldingDeepResearchInput',
    outputSchema: 'HoldingDeepResearchOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '持仓缺失或疑似样例数据时，不能输出行业、主题、风格或相似度结论。',
      '持仓相似度只用于研究替代性和拥挤度判断，不构成配置、交易或组合建议。',
    ],
  },
  run(input) {
    const current = normalizedHoldings(Array.isArray(input.holdings) ? input.holdings : [])
    const previous = normalizedHoldings(Array.isArray(input.previousHoldings) ? input.previousHoldings : [])
    const peer = normalizedHoldings(Array.isArray(input.peerHoldings) ? input.peerHoldings : [])
    const holdingReady = current.length >= 5
    const topTenWeight = current.length ? round4(current.slice(0, 10).reduce((sum, item) => sum + item.weight, 0)) : null
    const topThreeWeight = current.length ? round4(current.slice(0, 3).reduce((sum, item) => sum + item.weight, 0)) : null
    const industryBuckets = bucketBy(current, 'industry').map((item) => ({ industry: item.name, weight: item.weight }))
    const marketCapBuckets = bucketBy(current, 'marketCap').map((item) => ({ bucket: item.name, weight: item.weight }))
    const topIndustry = industryBuckets[0]?.industry || '行业待补'
    const topIndustryWeight = industryBuckets[0]?.weight ?? null
    const themeTags = uniqueSorted(current.flatMap((holding) => holding.themeTags))
    const styleTags = uniqueSorted(current.flatMap((holding) => holding.styleTags))
    const turnoverEstimate = calculateTurnover(current, previous)
    const changes = heavyPositionChanges(current, previous)
    const quarter = normalizeText(input.quarter)
    const peerQuarter = normalizeText(input.peerQuarter) || quarter
    const similarityResult = similarity(current, peer, normalizeText(input.peerWindCode), quarter, peerQuarter)
    const concentrationWarnings = [
      topTenWeight !== null && topTenWeight >= 60 ? `前十大权重 ${topTenWeight}%，集中度偏高。` : '',
      topIndustryWeight !== null && topIndustryWeight >= 35 ? `第一行业 ${topIndustry} 权重 ${topIndustryWeight}%，行业集中度偏高。` : '',
      similarityResult?.level === '高相似' ? `与 ${similarityResult.peerWindCode} 持仓高相似，横评时需避免把同一暴露当成分散研究样本。` : '',
    ].filter(Boolean)
    const missingDimensions = [
      holdingReady ? '' : '可信持仓明细',
      industryBuckets.some((item) => item.industry !== '行业待补') ? '' : '行业标签',
      themeTags.length ? '' : '主题标签',
      styleTags.length ? '' : '风格标签',
      previous.length ? '' : '上一期持仓/换手估算',
      similarityResult ? '' : '同期基金间持仓相似度',
    ].filter(Boolean)
    const output: HoldingDeepResearchOutput = {
      holdingReady,
      holdingCount: current.length,
      topTenWeight,
      topThreeWeight,
      topIndustry,
      topIndustryWeight,
      industryBuckets,
      themeTags,
      styleTags,
      marketCapBuckets,
      turnoverEstimate,
      heavyPositionChanges: changes,
      similarity: similarityResult,
      concentrationWarnings,
      missingDimensions,
      policy: {
        hardBoundary: '持仓穿透、行业/主题/风格标签、换手或同期前十大重仓相似度证据缺失时，只能输出持仓补证清单，不输出持仓优势、分散性或替代性结论。',
        requiredDimensions: ['可信持仓明细', '行业标签', '主题标签', '风格标签', '换手估算', '重仓变化', '同期基金间持仓相似度'],
      },
    }
    const hardBlocks = holdingReady ? [] : ['缺少至少 5 条可信持仓，不能生成持仓穿透或相似度研究结论。']
    return createToolResult(toolName, version, input, output, {
      ok: hardBlocks.length === 0 && missingDimensions.length === 0,
      hardBlocks,
      evidence: [
        {
          id: `holding-deep:${normalizeText(input.windCode) || 'missing'}:${normalizeText(input.quarter) || 'latest'}`,
          label: `${normalizeText(input.fundName) || normalizeText(input.windCode) || '基金'} 持仓深挖`,
          source: normalizeText(input.source) || 'holding_deep_research_tool',
          freshness: 'derived',
          subjectId: normalizeText(input.windCode) || undefined,
          note: `持仓 ${current.length} 条；前十大 ${topTenWeight ?? '待补'}；第一行业 ${topIndustry} ${topIndustryWeight ?? '待补'}；相似度 ${similarityResult?.level || '待补'}`,
        },
      ],
      gaps: missingDimensions.map((dimension) => ({
        key: `holding-deep:${dimension}`,
        label: `${dimension}待补`,
        severity: dimension === '可信持仓明细' ? 'hard_block' : 'verify_first',
        subjectId: normalizeText(input.windCode) || undefined,
        reason: `${dimension}不完整，不能形成持仓研究结论。`,
        requiredBeforeFormalReview: true,
      })),
      nextActions: missingDimensions.map((dimension) => ({
        key: `holding-deep:${dimension}`,
        label: `补齐${dimension}`,
        href: normalizeText(input.windCode) ? `/funds/${encodeURIComponent(normalizeText(input.windCode))}` : '/analysis',
        priority: dimension === '可信持仓明细' ? 'high' : 'medium',
        reason: `${dimension}是持仓研究深挖的必要证据。`,
      })),
    })
  },
}
