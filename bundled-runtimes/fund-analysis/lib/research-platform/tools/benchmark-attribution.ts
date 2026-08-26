import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type BenchmarkAttributionInput = {
  windCode: string
  canonicalCode?: string | null
  fundName?: string | null
  benchmarkCode?: string | null
  benchmarkName?: string | null
  benchmarkSource?: string | null
  mappingMethod?: string | null
  mappingRationale?: string | null
  periodStart?: string | null
  periodEnd?: string | null
  totalReturn?: number | null
  benchmarkReturn?: number | null
  allocationEffect?: number | null
  selectionEffect?: number | null
  interactionEffect?: number | null
  styleContribution?: Array<{ factor: string; contribution: number | null; exposure?: number | null }>
  industryContribution?: Array<{ industry: string; contribution: number | null; activeWeight?: number | null }>
  assetAllocation?: Array<{ assetClass: string; weight: number | null; contribution?: number | null }>
  evidenceRefs?: Array<{ label: string; source: string; sourceUpdatedAt?: string | null }>
}

export type BenchmarkAttributionOutput = {
  benchmarkReady: boolean
  attributionReady: boolean
  excessReturn: number | null
  explainedReturn: number | null
  residualReturn: number | null
  dominantSource: string
  benchmarkMapping: {
    benchmarkCode: string
    benchmarkName: string
    source: string
    method: string
    rationale: string
  }
  decomposition: Array<{ key: string; label: string; value: number | null; note: string }>
  styleHighlights: string[]
  industryHighlights: string[]
  assetAllocationHighlights: string[]
  missingDimensions: string[]
  policy: {
    hardBoundary: string
    requiredDimensions: string[]
  }
}

const toolName = 'benchmark-attribution'
const version = '1.0.0'

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

function contributionLabel(value: number | null) {
  if (value === null) return '待补'
  if (value > 0) return '正贡献'
  if (value < 0) return '负贡献'
  return '中性'
}

function topContribution<T extends { contribution: number | null }>(items: T[], key: keyof T) {
  const sorted = items
    .map((item) => ({ item, contribution: finiteNumber(item.contribution) }))
    .filter((item): item is { item: T; contribution: number } => item.contribution !== null)
    .sort((left, right) => Math.abs(right.contribution) - Math.abs(left.contribution))
  const top = sorted[0]
  if (!top) return null
  return `${String(top.item[key] ?? '未知')} ${contributionLabel(top.contribution)} ${round4(top.contribution)}`
}

function normalizeContributionItems<T extends Record<string, unknown>>(
  items: T[],
): Array<T & { contribution: number | null }> {
  return items.map((item) => ({
    ...item,
    contribution: finiteNumber(item.contribution),
  }))
}

export const benchmarkAttributionTool: ResearchTool<BenchmarkAttributionInput, BenchmarkAttributionOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'fund',
    purpose: '把基金基准映射、超额收益、Brinson 分解、风格暴露、行业贡献和资产配置归因统一成可复核收益来源解释。',
    inputSchema: 'BenchmarkAttributionInput',
    outputSchema: 'BenchmarkAttributionOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '缺少可追溯基准映射时，不能输出超额收益或主动能力结论。',
      '归因分解缺少风格、行业或资产配置证据时，只能说明缺口，不能用残差包装成能力。',
    ],
  },
  run(input) {
    const benchmarkCode = normalizeText(input.benchmarkCode)
    const benchmarkName = normalizeText(input.benchmarkName)
    const benchmarkSource = normalizeText(input.benchmarkSource)
    const mappingMethod = normalizeText(input.mappingMethod) || 'peer_group_or_research_profile'
    const mappingRationale = normalizeText(input.mappingRationale)
    const totalReturn = finiteNumber(input.totalReturn)
    const benchmarkReturn = finiteNumber(input.benchmarkReturn)
    const allocationEffect = finiteNumber(input.allocationEffect)
    const selectionEffect = finiteNumber(input.selectionEffect)
    const interactionEffect = finiteNumber(input.interactionEffect)
    const styleContribution = normalizeContributionItems(Array.isArray(input.styleContribution) ? input.styleContribution : [])
    const industryContribution = normalizeContributionItems(Array.isArray(input.industryContribution) ? input.industryContribution : [])
    const assetAllocation = normalizeContributionItems(Array.isArray(input.assetAllocation) ? input.assetAllocation : [])
    const benchmarkReady = Boolean(benchmarkCode && benchmarkName && benchmarkSource && mappingRationale)
    const excessReturn = totalReturn !== null && benchmarkReturn !== null ? round4(totalReturn - benchmarkReturn) : null
    const explainedParts = [allocationEffect, selectionEffect, interactionEffect].filter((item): item is number => item !== null)
    const explainedReturn = explainedParts.length ? round4(explainedParts.reduce((sum, item) => sum + item, 0)) : null
    const residualReturn = excessReturn !== null && explainedReturn !== null ? round4(excessReturn - explainedReturn) : null
    const missingDimensions = [
      benchmarkReady ? '' : '自动基准映射/来源证据',
      excessReturn !== null ? '' : '基金与基准同期收益',
      allocationEffect !== null ? '' : '配置效应',
      selectionEffect !== null ? '' : '选择效应',
      styleContribution.length ? '' : '风格暴露贡献',
      industryContribution.length ? '' : '行业贡献',
      assetAllocation.length ? '' : '资产配置拆解',
    ].filter(Boolean)
    const attributionReady = benchmarkReady && excessReturn !== null && explainedReturn !== null && missingDimensions.length === 0
    const decomposition = [
      { key: 'total_return', label: '基金收益', value: totalReturn, note: '研究窗口内基金收益。' },
      { key: 'benchmark_return', label: '基准收益', value: benchmarkReturn, note: '与基金策略口径匹配的基准收益。' },
      { key: 'excess_return', label: '超额收益', value: excessReturn, note: '基金收益减基准收益。' },
      { key: 'allocation_effect', label: '配置效应', value: allocationEffect, note: '行业或资产配置偏离带来的贡献。' },
      { key: 'selection_effect', label: '选择效应', value: selectionEffect, note: '个券或个股选择带来的贡献。' },
      { key: 'interaction_effect', label: '交互效应', value: interactionEffect, note: '配置与选择交互项。' },
      { key: 'residual_return', label: '残差', value: residualReturn, note: '超额收益中尚未被解释的部分，不能直接归因为能力。' },
    ]
    const styleHighlights = [
      topContribution(styleContribution, 'factor'),
    ].filter(Boolean) as string[]
    const industryHighlights = [
      topContribution(industryContribution, 'industry'),
    ].filter(Boolean) as string[]
    const assetAllocationHighlights = [
      topContribution(assetAllocation, 'assetClass'),
    ].filter(Boolean) as string[]
    const dominantCandidates = [
      { label: '配置效应', value: allocationEffect },
      { label: '选择效应', value: selectionEffect },
      { label: '交互效应', value: interactionEffect },
      { label: '残差', value: residualReturn },
    ].filter((item): item is { label: string; value: number } => item.value !== null)
      .sort((left, right) => Math.abs(right.value) - Math.abs(left.value))
    const dominantSource = dominantCandidates[0]
      ? `${dominantCandidates[0].label} ${contributionLabel(dominantCandidates[0].value)} ${round4(dominantCandidates[0].value)}`
      : '收益来源待补'
    const output: BenchmarkAttributionOutput = {
      benchmarkReady,
      attributionReady,
      excessReturn,
      explainedReturn,
      residualReturn,
      dominantSource,
      benchmarkMapping: {
        benchmarkCode,
        benchmarkName,
        source: benchmarkSource,
        method: mappingMethod,
        rationale: mappingRationale,
      },
      decomposition,
      styleHighlights,
      industryHighlights,
      assetAllocationHighlights,
      missingDimensions,
      policy: {
        hardBoundary: '基准来源、同期收益和归因证据不完整时，只能输出研究假设和补证清单，不输出主动能力、风格能力或行业能力结论。',
        requiredDimensions: ['自动基准映射', '超额收益', '配置效应', '选择效应', '风格暴露', '行业贡献', '资产配置拆解'],
      },
    }
    const subjectId = normalizeText(input.canonicalCode) || normalizeText(input.windCode)
    return createToolResult(toolName, version, input, output, {
      ok: attributionReady,
      hardBlocks: benchmarkReady ? [] : ['缺少可追溯基准映射，不能生成超额收益或归因结论。'],
      evidence: [
        {
          id: `benchmark-attribution:${subjectId || 'missing'}`,
          label: `${normalizeText(input.fundName) || subjectId || '基金'} 基准与归因解释`,
          source: benchmarkSource || 'benchmark_attribution_tool',
          freshness: 'derived',
          subjectId: subjectId || undefined,
          note: `${benchmarkName || '基准待补'}；超额 ${excessReturn ?? '待补'}；主导来源：${dominantSource}`,
        },
      ],
      gaps: missingDimensions.map((dimension) => ({
        key: `benchmark-attribution:${dimension}`,
        label: `${dimension}待补`,
        severity: dimension === '自动基准映射/来源证据' ? 'hard_block' : 'verify_first',
        subjectId: subjectId || undefined,
        reason: `${dimension}不完整，收益来源解释不能进入正式研究结论。`,
        requiredBeforeFormalReview: true,
      })),
      nextActions: missingDimensions.map((dimension) => ({
        key: `benchmark-attribution:${dimension}`,
        label: `补齐${dimension}`,
        href: subjectId ? `/funds/${encodeURIComponent(subjectId)}` : '/analysis',
        priority: dimension === '自动基准映射/来源证据' ? 'high' : 'medium',
        reason: `${dimension}是基金基准与归因体系的必要证据。`,
      })),
    })
  },
}
