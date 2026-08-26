import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type FundEntityShareClassInput = {
  windCode: string
  shareClass?: string | null
  feeClass?: string | null
  isPrimary?: boolean | null
  status?: string | null
}

export type FundEntityStandardizationInput = {
  canonicalCode?: string | null
  canonicalName?: string | null
  companyName?: string | null
  productLine?: string | null
  strategyFamily?: string | null
  assetClass?: string | null
  activePassive?: string | null
  lifecycleStage?: string | null
  establishedAt?: string | null
  terminatedAt?: string | null
  shareClasses?: FundEntityShareClassInput[]
  lifecycleEvents?: Array<{ eventDate?: string | null; eventType?: string | null; source?: string | null }>
  changeHistory?: Array<{ changedAt?: string | null; changeType?: string | null; source?: string | null }>
}

export type FundEntityStandardizationOutput = {
  canonicalReady: boolean
  entityCompletenessScore: number
  normalizedName: string
  canonicalCode: string
  companyReady: boolean
  productLineReady: boolean
  strategyFamilyReady: boolean
  lifecycleReady: boolean
  shareClassReady: boolean
  primaryShareClassWindCode: string | null
  shareClassCount: number
  missingDimensions: string[]
  policy: {
    requiredDimensions: string[]
    hardBoundary: string
  }
}

const toolName = 'fund-entity-standardization'
const version = '1.0.0'

function normalizeText(value: unknown) {
  return String(value ?? '').trim()
}

function normalizeName(value: unknown) {
  return normalizeText(value)
    .replace(/[（(][A-Z人民币美元港币份额类]+[）)]$/iu, '')
    .replace(/\s+/g, '')
}

function asArray<T>(value: T[] | null | undefined) {
  return Array.isArray(value) ? value : []
}

function hasDateText(value: unknown) {
  return /^\d{4}-\d{2}-\d{2}/.test(normalizeText(value))
}

function scoreFromReadyFlags(flags: boolean[]) {
  return Math.round((flags.filter(Boolean).length / flags.length) * 100)
}

export const fundEntityStandardizationTool: ResearchTool<FundEntityStandardizationInput, FundEntityStandardizationOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'fund',
    purpose: '检查基金研究对象是否已经统一到主基金实体、份额、公司、产品线、策略族谱、生命周期和变更历史口径。',
    inputSchema: 'FundEntityStandardizationInput',
    outputSchema: 'FundEntityStandardizationOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '主基金实体缺失时，不能把不同份额、不同策略或不同生命周期阶段的基金混在一起做同类横评。',
      '基金公司、产品线、策略族谱、生命周期和变更历史必须显式披露缺口，不能在报告中默认完整。',
    ],
  },
  run(input) {
    const canonicalCode = normalizeText(input.canonicalCode)
    const canonicalName = normalizeText(input.canonicalName)
    const normalizedName = normalizeName(canonicalName)
    const shareClasses = asArray(input.shareClasses).filter((shareClass) => normalizeText(shareClass.windCode))
    const lifecycleEvents = asArray(input.lifecycleEvents)
    const changeHistory = asArray(input.changeHistory)

    const companyReady = Boolean(normalizeText(input.companyName))
    const productLineReady = Boolean(normalizeText(input.productLine))
    const strategyFamilyReady = Boolean(normalizeText(input.strategyFamily) && normalizeText(input.assetClass))
    const activePassiveReady = Boolean(normalizeText(input.activePassive))
    const lifecycleStageReady = Boolean(normalizeText(input.lifecycleStage))
    const lifecycleReady = lifecycleStageReady && (
      hasDateText(input.establishedAt)
      || lifecycleEvents.some((event) => hasDateText(event.eventDate) && normalizeText(event.eventType) && normalizeText(event.source))
    )
    const changeHistoryReady = changeHistory.length === 0
      ? false
      : changeHistory.every((item) => hasDateText(item.changedAt) && normalizeText(item.changeType) && normalizeText(item.source))
    const shareClassReady = shareClasses.length > 0
      && shareClasses.every((shareClass) => normalizeText(shareClass.windCode))
      && shareClasses.some((shareClass) => shareClass.isPrimary || normalizeText(shareClass.shareClass))
    const primaryShareClassWindCode = shareClasses.find((shareClass) => shareClass.isPrimary)?.windCode
      || shareClasses[0]?.windCode
      || null
    const canonicalReady = Boolean(canonicalCode && canonicalName && normalizedName)
    const readiness = [
      canonicalReady,
      companyReady,
      productLineReady,
      strategyFamilyReady,
      activePassiveReady,
      lifecycleReady,
      changeHistoryReady,
      shareClassReady,
    ]
    const missingDimensions = [
      canonicalReady ? '' : '主基金实体',
      companyReady ? '' : '基金公司',
      productLineReady ? '' : '产品线',
      strategyFamilyReady ? '' : '策略族谱/资产类别',
      activePassiveReady ? '' : '主动/被动属性',
      lifecycleReady ? '' : '生命周期',
      changeHistoryReady ? '' : '变更历史',
      shareClassReady ? '' : '份额映射',
    ].filter(Boolean)
    const hardBlocks = canonicalReady ? [] : ['缺少主基金实体标准化，不能进入正式同类横评或研究结论复核。']
    const output: FundEntityStandardizationOutput = {
      canonicalReady,
      entityCompletenessScore: scoreFromReadyFlags(readiness),
      normalizedName,
      canonicalCode,
      companyReady,
      productLineReady,
      strategyFamilyReady,
      lifecycleReady,
      shareClassReady,
      primaryShareClassWindCode,
      shareClassCount: shareClasses.length,
      missingDimensions,
      policy: {
        requiredDimensions: ['主基金实体', '份额映射', '基金公司', '产品线', '策略族谱', '生命周期', '变更历史'],
        hardBoundary: '实体层不完整时，系统只能输出补证方向；不得把筛选排序、历史收益或报告文本当成正式研究结论。',
      },
    }

    return createToolResult(toolName, version, input, output, {
      ok: hardBlocks.length === 0 && missingDimensions.length === 0,
      hardBlocks,
      evidence: [
        {
          id: `fund-entity:${canonicalCode || normalizedName || 'missing'}`,
          label: '基金研究对象标准化检查',
          source: 'fund_entity_standardization_tool',
          freshness: 'derived',
          subjectId: canonicalCode || primaryShareClassWindCode || undefined,
          note: `完整度 ${output.entityCompletenessScore}%；缺口：${missingDimensions.join('、') || '无'}`,
        },
      ],
      gaps: missingDimensions.map((dimension) => ({
        key: `fund-entity:${dimension}`,
        label: `${dimension}待补`,
        severity: dimension === '主基金实体' ? 'hard_block' : 'verify_first',
        subjectId: canonicalCode || primaryShareClassWindCode || undefined,
        reason: `${dimension}未完成标准化，后续同类池、归因、经理和公司研究会失去统一口径。`,
        requiredBeforeFormalReview: true,
      })),
      nextActions: missingDimensions.map((dimension) => ({
        key: `fund-entity:${dimension}`,
        label: `补齐${dimension}`,
        href: canonicalCode ? `/funds/${encodeURIComponent(canonicalCode)}` : '/market',
        priority: dimension === '主基金实体' ? 'high' : 'medium',
        reason: `${dimension}是基金研究实体层的必要字段。`,
      })),
    })
  },
}
