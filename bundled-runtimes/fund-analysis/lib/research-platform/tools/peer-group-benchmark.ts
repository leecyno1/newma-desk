import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type PeerBenchmarkSource = 'research_profile' | 'fund_type_inferred' | 'broad_asset_bucket_fallback'
export type PeerSampleStatus = 'sufficient' | 'thin_sample' | 'missing_peer_group'

export type PeerBenchmarkFundInput = {
  windCode: string
  name?: string | null
  fundType?: string | null
  peerGroup?: string | null
  primaryBenchmark?: string | null
  peerCount?: number | null
  assetClass?: string | null
  strategyFamily?: string | null
  activePassive?: string | null
  styleTags?: string[] | null
  scaleBucket?: string | null
  inceptionDate?: string | null
  asOfDate?: string | null
}

export type PeerBenchmarkInput = {
  funds: PeerBenchmarkFundInput[]
  minimumPeerCount?: number
}

export type PeerBenchmarkClassification = {
  windCode: string
  name: string
  fundType: string
  peerGroup: string
  broadAssetBucket: string
  primaryBenchmark: string
  source: PeerBenchmarkSource
  sampleStatus: PeerSampleStatus
  peerCount: number | null
  minimumPeerCount: number
  sampleNote: string
  explainablePeerKey: string
  dimensions: {
    assetClass: string
    strategyFamily: string
    activePassive: string
    styleTags: string[]
    scaleBucket: string
    ageBucket: string
  }
  matchedRules: string[]
  missingRules: string[]
  exclusionWarnings: string[]
  benchmarkMappingRationale: string
}

export type PeerBenchmarkOutput = {
  funds: PeerBenchmarkClassification[]
  peerGroupCount: number
  benchmarkCount: number
  insufficientSampleCount: number
  policy: {
    minimumPeerCount: number
    benchmarkFallbackAllowed: boolean
    hardBoundary: string
    openSourceReferences: string[]
  }
}

const toolName = 'peer-group-benchmark'
const version = '1.0.0'
const defaultMinimumPeerCount = 5

function normalizeText(value: unknown) {
  return String(value ?? '').trim()
}

function includesAny(text: string, tokens: string[]) {
  const normalized = text.toLowerCase()
  return tokens.some((token) => normalized.includes(token.toLowerCase()))
}

function normalizeTags(value: string[] | null | undefined) {
  return Array.isArray(value) ? value.map((item) => normalizeText(item)).filter(Boolean) : []
}

function inferActivePassive(text: string) {
  if (includesAny(text, ['指数', 'index', 'etf', '联接', '被动'])) return '被动'
  if (includesAny(text, ['增强', '量化增强'])) return '指数增强'
  if (includesAny(text, ['主动', '股票', '混合', '债券', 'qdii'])) return '主动'
  return '待补'
}

function yearDifference(startDate: string, endDate: string) {
  const start = new Date(startDate)
  const end = new Date(endDate)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) return null
  return (end.getTime() - start.getTime()) / (365.25 * 24 * 60 * 60 * 1000)
}

function ageBucket(inceptionDate: string, asOfDate: string) {
  const years = yearDifference(inceptionDate, asOfDate)
  if (years === null) return '成立年限待补'
  if (years < 1) return '成立不满1年'
  if (years < 3) return '成立1-3年'
  if (years < 5) return '成立3-5年'
  return '成立5年以上'
}

function stableKeyPart(value: string) {
  return normalizeText(value).replace(/\s+/g, '-').replace(/[\\/|]+/g, '-').toLowerCase() || 'missing'
}

function inferBucketAndBenchmark(fundType: string, peerGroup: string) {
  const text = `${fundType} ${peerGroup}`
  if (includesAny(text, ['qdii', '全球', '海外', '港股', '美股', '国际'])) {
    return {
      broadAssetBucket: 'QDII/海外基金',
      peerGroup: peerGroup || 'QDII/海外基金',
      primaryBenchmark: '同类 QDII 基金指数/对应市场指数',
      source: peerGroup ? 'research_profile' : 'fund_type_inferred' as PeerBenchmarkSource,
    }
  }
  if (includesAny(text, ['货币', 'money'])) {
    return {
      broadAssetBucket: '货币市场基金',
      peerGroup: peerGroup || '货币市场基金',
      primaryBenchmark: '货币基金同类收益基准',
      source: peerGroup ? 'research_profile' : 'fund_type_inferred' as PeerBenchmarkSource,
    }
  }
  if (includesAny(text, ['债', 'bond', '纯债', '信用债', '可转债'])) {
    return {
      broadAssetBucket: '债券基金',
      peerGroup: peerGroup || '债券基金',
      primaryBenchmark: '中债综合财富指数/同类债基指数',
      source: peerGroup ? 'research_profile' : 'fund_type_inferred' as PeerBenchmarkSource,
    }
  }
  if (includesAny(text, ['指数', 'index', 'etf', '联接'])) {
    return {
      broadAssetBucket: '指数基金',
      peerGroup: peerGroup || '指数基金',
      primaryBenchmark: '跟踪指数/同类指数基金基准',
      source: peerGroup ? 'research_profile' : 'fund_type_inferred' as PeerBenchmarkSource,
    }
  }
  if (includesAny(text, ['混合', '偏股', '灵活配置', 'hybrid'])) {
    return {
      broadAssetBucket: '主动权益/混合基金',
      peerGroup: peerGroup || '主动权益/混合基金',
      primaryBenchmark: '中证偏股基金指数/同类混合基金指数',
      source: peerGroup ? 'research_profile' : 'fund_type_inferred' as PeerBenchmarkSource,
    }
  }
  if (includesAny(text, ['股票', 'stock', 'equity'])) {
    return {
      broadAssetBucket: '主动权益基金',
      peerGroup: peerGroup || '主动权益基金',
      primaryBenchmark: '中证主动式股票基金指数/同类权益基金指数',
      source: peerGroup ? 'research_profile' : 'fund_type_inferred' as PeerBenchmarkSource,
    }
  }
  return {
    broadAssetBucket: '未分类基金',
    peerGroup: peerGroup || '同类组待补',
    primaryBenchmark: '基准待补',
    source: peerGroup ? 'research_profile' : 'broad_asset_bucket_fallback' as PeerBenchmarkSource,
  }
}

function sampleStatus(peerGroup: string, peerCount: number | null, minimumPeerCount: number): PeerSampleStatus {
  if (!peerGroup || peerGroup === '同类组待补') return 'missing_peer_group'
  if (peerCount === null || peerCount < minimumPeerCount) return 'thin_sample'
  return 'sufficient'
}

function sampleNote(status: PeerSampleStatus, peerCount: number | null, minimumPeerCount: number) {
  if (status === 'missing_peer_group') return '缺少研究画像同类组，当前只能使用宽口径资产桶，不输出同类优势结论。'
  if (status === 'thin_sample') return `同类样本 ${peerCount ?? '待补'} 只，低于 ${minimumPeerCount} 只最小样本线，只能作为观察性横评。`
  return `同类样本 ${peerCount} 只，达到最小样本线，可进入同类分位和胜负线复核。`
}

function classifyFund(fund: PeerBenchmarkFundInput, minimumPeerCount: number): PeerBenchmarkClassification {
  const windCode = normalizeText(fund.windCode)
  const name = normalizeText(fund.name) || windCode
  const fundType = normalizeText(fund.fundType)
  const explicitPeerGroup = normalizeText(fund.peerGroup)
  const explicitBenchmark = normalizeText(fund.primaryBenchmark)
  const inferred = inferBucketAndBenchmark(fundType, explicitPeerGroup)
  const assetClass = normalizeText(fund.assetClass) || inferred.broadAssetBucket
  const strategyFamily = normalizeText(fund.strategyFamily) || inferred.peerGroup
  const activePassive = normalizeText(fund.activePassive) || inferActivePassive(`${fundType} ${strategyFamily} ${name}`)
  const styleTags = normalizeTags(fund.styleTags)
  const scaleBucket = normalizeText(fund.scaleBucket) || '规模层待补'
  const fundAgeBucket = ageBucket(normalizeText(fund.inceptionDate), normalizeText(fund.asOfDate) || new Date().toISOString().slice(0, 10))
  const peerCount = Number.isFinite(Number(fund.peerCount)) ? Number(fund.peerCount) : null
  const status = sampleStatus(inferred.peerGroup, peerCount, minimumPeerCount)
  const missingRules = [
    assetClass && assetClass !== '未分类基金' ? '' : '资产类别',
    strategyFamily && strategyFamily !== '同类组待补' ? '' : '策略族谱',
    activePassive && activePassive !== '待补' ? '' : '主动/被动',
    styleTags.length ? '' : '风格标签',
    scaleBucket !== '规模层待补' ? '' : '规模分层',
    fundAgeBucket !== '成立年限待补' ? '' : '成立年限',
  ].filter(Boolean)
  const matchedRules = [
    assetClass && assetClass !== '未分类基金' ? `资产类别=${assetClass}` : '',
    strategyFamily && strategyFamily !== '同类组待补' ? `策略族谱=${strategyFamily}` : '',
    activePassive && activePassive !== '待补' ? `主动/被动=${activePassive}` : '',
    styleTags.length ? `风格标签=${styleTags.join('/')}` : '',
    scaleBucket !== '规模层待补' ? `规模分层=${scaleBucket}` : '',
    fundAgeBucket !== '成立年限待补' ? `成立年限=${fundAgeBucket}` : '',
  ].filter(Boolean)
  const exclusionWarnings = [
    activePassive === '待补' ? '主动/被动属性缺失，可能把指数、增强和主动产品混比。' : '',
    fundAgeBucket === '成立不满1年' ? '成立不满1年，滚动业绩和回撤样本不足，应从正式 peer 样本中降权或观察。' : '',
    missingRules.includes('策略族谱') ? '策略族谱缺失，不能解释同类池为什么成立。' : '',
  ].filter(Boolean)
  const benchmark = explicitBenchmark || inferred.primaryBenchmark
  const explainablePeerKey = [
    assetClass,
    strategyFamily,
    activePassive,
    styleTags[0] || 'style-missing',
    scaleBucket,
    fundAgeBucket,
  ].map(stableKeyPart).join('|')
  return {
    windCode,
    name,
    fundType,
    peerGroup: inferred.peerGroup,
    broadAssetBucket: inferred.broadAssetBucket,
    primaryBenchmark: benchmark,
    source: explicitPeerGroup ? 'research_profile' : inferred.source,
    sampleStatus: status,
    peerCount,
    minimumPeerCount,
    sampleNote: sampleNote(status, peerCount, minimumPeerCount),
    explainablePeerKey,
    dimensions: {
      assetClass,
      strategyFamily,
      activePassive,
      styleTags,
      scaleBucket,
      ageBucket: fundAgeBucket,
    },
    matchedRules,
    missingRules,
    exclusionWarnings,
    benchmarkMappingRationale: explicitBenchmark
      ? '使用研究画像显式基准；后续归因和超额收益以该基准为主。'
      : `按 ${assetClass}/${strategyFamily}/${activePassive} 推断基准；正式研究前需复核基准是否与合同或招募书一致。`,
  }
}

export const peerGroupBenchmarkTool: ResearchTool<PeerBenchmarkInput, PeerBenchmarkOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'comparison',
    purpose: '统一基金同类组、宽口径资产桶、基准映射和样本充分性判定，避免横评页面/报告各自猜 peer group。',
    inputSchema: 'PeerBenchmarkInput',
    outputSchema: 'PeerBenchmarkOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '同类组缺失或样本不足时，只能输出研究观察，不输出同类优势结论。',
      '基准映射优先采用 research_profile；推断基准必须显式披露来源。',
      '同类池必须解释资产类别、策略族谱、主动/被动、风格、规模和成立年限分层。',
    ],
  },
  run(input) {
    const minimumPeerCount = Number.isFinite(Number(input.minimumPeerCount)) && Number(input.minimumPeerCount) > 0
      ? Number(input.minimumPeerCount)
      : defaultMinimumPeerCount
    const funds = input.funds
      .filter((fund) => normalizeText(fund.windCode))
      .map((fund) => classifyFund(fund, minimumPeerCount))
    const insufficientFunds = funds.filter((fund) => fund.sampleStatus !== 'sufficient' || fund.missingRules.length > 0)
    const hardBlocks = funds.length === 0 ? ['缺少可映射的基金样本，不能生成同类组或基准判断。'] : []
    const output: PeerBenchmarkOutput = {
      funds,
      peerGroupCount: new Set(funds.map((fund) => fund.peerGroup).filter(Boolean)).size,
      benchmarkCount: new Set(funds.map((fund) => fund.primaryBenchmark).filter((benchmark) => benchmark && benchmark !== '基准待补')).size,
      insufficientSampleCount: insufficientFunds.length,
      policy: {
        minimumPeerCount,
        benchmarkFallbackAllowed: true,
        hardBoundary: '同类组、基准或样本数量不足时，横评只能说明研究排序和补证方向，不能生成正式研究优势结论。',
        openSourceReferences: [
          'OpenBB provider/adapter 分层',
          'QuantStats/Empyrical 基准对齐后再做绩效比较',
          'FinRobot tool-to-report 编排',
        ],
      },
    }
    return createToolResult(toolName, version, input, output, {
      ok: hardBlocks.length === 0 && insufficientFunds.length === 0,
      hardBlocks,
      evidence: funds.map((fund) => ({
        id: `peer-benchmark:${fund.windCode}`,
        label: `${fund.name} 同类组与基准映射`,
        source: fund.source,
        freshness: 'derived',
        subjectId: fund.windCode,
        note: `${fund.peerGroup} / ${fund.primaryBenchmark}；${fund.sampleNote}`,
        field: fund.explainablePeerKey,
      })),
      gaps: insufficientFunds.map((fund) => ({
        key: `peer-benchmark:${fund.windCode}`,
        label: fund.missingRules.length
          ? `同类池解释维度待补：${fund.missingRules.join('、')}`
          : fund.sampleStatus === 'missing_peer_group' ? '同类组待补' : '同类样本不足',
        severity: 'verify_first',
        subjectId: fund.windCode,
        reason: [fund.sampleNote, fund.missingRules.length ? `缺少 ${fund.missingRules.join('、')}。` : '', ...fund.exclusionWarnings].filter(Boolean).join(' '),
        requiredBeforeFormalReview: true,
      })),
      nextActions: insufficientFunds.map((fund) => ({
        key: `peer-benchmark:${fund.windCode}`,
        label: fund.missingRules.length ? '补齐同类池解释维度' : fund.sampleStatus === 'missing_peer_group' ? '补研究画像同类组' : '扩充同类样本指标',
        href: `/funds/${encodeURIComponent(fund.windCode)}`,
        priority: 'medium',
        reason: [fund.sampleNote, fund.missingRules.length ? `待补：${fund.missingRules.join('、')}` : ''].filter(Boolean).join(' '),
      })),
    })
  },
}
