import type { ShareClassInfo } from '@/lib/share-class'
import { hasValidSalesRuleSourceIdentityEvidence } from '@/lib/sales-rule-source-evidence'
import type { MethodologyDimension } from '@/lib/research-platform/tools'
import { resolveMethodologyConfigFromDataSync } from '@/lib/research-platform/methodology-mapping-repository'

type InvestorRiskProfile = 'conservative' | 'balanced' | 'aggressive'
type InvestorHorizon = 'lt1y' | '1to3y' | 'gt3y'
type InvestorPurchasePlan = 'lump_sum' | 'sip'

type NavPoint = {
  date: string
  nav: number
}

type BuyEvidence = {
  completenessScore?: number
  completenessLevel?: string
  conclusion?: string
  knownItems?: Array<{ label: string; value: string; source: string; confidence: string }>
  missingItems?: Array<{ label: string; severity: string; reason: string; requiredBeforeBuy: boolean }>
  requiredMissingCount?: number
  mustVerifyBeforeBuy?: string[]
}

type ReportFund = {
  id?: string
  windCode?: string
  name?: string
  type?: string
  nav?: number | null
  navDate?: string | null
  establishmentDate?: string | null
  totalAsset?: number | null
  performanceData?: Record<string, unknown>
  riskMetrics?: Record<string, unknown>
  holdingCount?: number | null
  benchmark?: string | Record<string, unknown> | null
  peerPercentiles?: {
    peer_group?: string | null
    primary_benchmark?: string | null
  } | null
  researchProfile?: {
    primaryBenchmark?: string
    peerGroup?: string
    styleLabel?: string
    strategyTags?: string[]
  } | null
  operationStatus?: {
    status?: string
    label?: string
    reason?: string
  } | null
  salesRule?: {
    platform?: string | null
    riskLevel?: string | null
    sourceUrl?: string | null
	    sourceUpdatedAt?: string | null
	    notes?: string | null
	    minPurchaseAmount?: number | null
	    minPurchaseSourceBacked?: boolean
	    minSipAmount?: number | null
	    minSipSourceBacked?: boolean
	    dailyLimitAmount?: number | null
	    dailyLimitSourceBacked?: boolean
	    purchaseFeeRate?: number | null
	    purchaseFeeSourceBacked?: boolean
	    redemptionFeeRules?: Array<{
	      label?: string
	      feeRate?: number | null
	      holdingDays?: number | null
	    }>
	    redemptionFeeSourceUrl?: string | null
	    redemptionFeeSourceUpdatedAt?: string | null
	    redemptionFeePlatform?: string | null
	    redemptionFeeNotes?: string | null
	    salesServiceFeeRate?: number | null
	    salesServiceFeeSourceBacked?: boolean
	    supportsSip?: boolean | null
	    supportsSipSourceBacked?: boolean
	  } | null
  managers?: Array<{
    managerId?: string
    name?: string
    managementYears?: number | null
    beginDate?: string | null
  }>
}

type PurchaseSimulation = {
  source: string
  period: {
    startDate: string
    endDate: string
    observations: number
    months: number
  }
  assumptions: {
    lumpSumAmount: number
    monthlyAmount: number
    feeIncluded: boolean
  }
  lumpSum: {
    totalInvested: number
    endingValue: number
    profit: number
    returnRate: number
    maxDrawdown: number
    holdingDays?: number | null
  }
  sip: {
    totalInvested: number
    endingValue: number
    profit: number
    returnRate: number | null
    contributionCount: number
    maxAccountDrawdown: number
  }
  monthlyExperience: {
    months: number
    positiveMonths: number
    positiveRatio: number | null
    bestMonth?: { month: string; returnRate: number } | null
    worstMonth?: { month: string; returnRate: number } | null
  }
  stressExperience?: {
    label: string
    stressLevel: 'comfortable' | 'watchable' | 'bumpy' | 'stressful'
    stressScore: number
    worstDrawdown: number
    troughDate: string
    recoveryDays: number | null
    longestUnderwaterDays: number
    longestLosingStreakMonths: number
    worstThreeMonthReturn: {
      startMonth: string
      endMonth: string
      returnRate: number
    } | null
    interpretation: string
  }
}

type HoldingEvidence = {
  status: 'available' | 'unavailable'
  quarter?: string
  holdings?: Array<{
    stockCode?: string
    stockName?: string
    industry?: string
    weight?: number | null
  }>
  industryBuckets?: Array<{ industry: string; weight: number }>
  totalWeight?: number | null
  checkedQuarters?: string[]
  rejectedMockLikeQuarters?: string[]
  source?: string
  note?: string
}

type SalesRuleGapEvidence = {
  status: 'available' | 'unavailable'
  source: string
  total: number
  executionAmountGate?: {
    plannedAmount: number | null
    status: 'pass' | 'blocked' | 'unknown'
    label: string
    detail: string
    minPurchaseAmount: number | null
    minSipAmount: number | null
    dailyLimitAmount: number | null
  } | null
  gap?: {
    windCode: string
    fundName: string
    priority: 'high' | 'medium' | 'low'
    missingItems: string[]
    missingCount: number
    nextAction: string
  } | null
}

type ShareClassEvidence = {
  status: 'available' | 'unavailable'
  source: string
  note: string
  current: ShareClassInfo | null
  funds: Array<{
    windCode?: string
    name?: string
    type?: string
    shareClass?: string
    annualBaseFeeAmount?: number | null
    purchaseFeeAmount?: number | null
    salesServiceFeeAmount?: number | null
    knownCost?: number | null
    costMissingItems?: string[]
    executionAmountGate?: {
      plannedAmount: number | null
      status: 'pass' | 'blocked' | 'unknown'
      label: string
      detail: string
      minPurchaseAmount: number | null
      minSipAmount: number | null
      dailyLimitAmount: number | null
    } | null
    salesRuleMissingItems?: string[]
    salesRuleMissingCount?: number
  }>
}

type ShareClassDecision = {
  title: string
  recommendedCode: string
  recommendedName: string
  recommendedClass: string
  confidence: 'medium' | 'low'
  formalChoiceReady: boolean
  reasons: string[]
  warnings: string[]
}

type ManagerAttributionDecision = {
  label: string
  status: 'covered' | 'partial' | 'weak' | 'missing'
  attributionWindowYears: number
  coverageRatio: number | null
  maxTenureYears: number | null
  managerNames: string[]
  reasons: string[]
  warnings: string[]
}

type HoldingExposureDecision = {
  label: string
  score: number
  topTenWeight: number | null
  topIndustryWeight: number | null
  topIndustry: string
  primaryRisk: string
  nextAction: string
  reasons: string[]
  reverseTriggers: string[]
}

export type AlternativeCandidate = {
  windCode?: string
  name?: string
  type?: string
  investorScore?: number | null
  investorRating?: string | null
  annualReturn?: number | null
  maxDrawdown?: number | null
  totalAsset?: number | null
  purchaseGate?: {
    level?: string
    label?: string
    evidenceGrade?: string
    cautionFlags?: string[]
    hardBlocks?: string[]
  }
  riskSuitability?: {
    status?: string
    label?: string
  }
  reasons?: string[]
  warnings?: string[]
  salesRuleGap?: {
    missingCount: number
    missingItems: string[]
    priority?: 'high' | 'medium' | 'low'
    nextAction?: string
  } | null
}

export type AlternativeEvidence = {
  status: 'available' | 'unavailable'
  note: string
  attempts: string[]
  total: number
  source: string
  funds: AlternativeCandidate[]
}

type AlternativeDecision = {
  title: string
  verdict: string
  detail: string
  primary: string
  alternative: string
  next: string
  status: 'blocked_primary' | 'compare_ready' | 'blocked_alternatives' | 'no_alternatives'
}

type AlternativeWinLossLine = {
  challengerCode: string
  challengerName: string
  status: 'win' | 'close' | 'rules_pending' | 'lose'
  label: string
  summary: string
  thresholds: Array<{ key: string; label: string; passed: boolean; detail: string }>
  passedChecks: number
  totalChecks: number
}

const investorRiskProfiles: Record<InvestorRiskProfile, {
  label: string
  note: string
  maxDrawdownTolerance: number
  maxSalesRiskLevel: number
}> = {
  conservative: {
    label: '稳健型',
    note: '优先控制回撤和销售风险等级',
    maxDrawdownTolerance: 0.08,
    maxSalesRiskLevel: 2,
  },
  balanced: {
    label: '均衡型',
    note: '兼顾收益弹性、回撤和证据完整度',
    maxDrawdownTolerance: 0.15,
    maxSalesRiskLevel: 3,
  },
  aggressive: {
    label: '进取型',
    note: '可接受更高波动，但仍不能跳过研究证据',
    maxDrawdownTolerance: 0.28,
    maxSalesRiskLevel: 5,
  },
}

const investorHorizons: Record<InvestorHorizon, { label: string; minSampleMonths: number; note: string }> = {
  lt1y: { label: '1年以内', minSampleMonths: 6, note: '短持有期更看重回撤、赎回规则和流动性' },
  '1to3y': { label: '1-3年', minSampleMonths: 12, note: '需要至少一年净值样本观察持有体验' },
  gt3y: { label: '3年以上', minSampleMonths: 36, note: '更重视跨周期收益、经理任期和风格稳定' },
}

const investorPurchasePlans: Record<InvestorPurchasePlan, { label: string; note: string }> = {
  lump_sum: { label: '一次性配置假设', note: '重点核查限购、申购费和短期回撤压力' },
  sip: { label: '定投', note: '重点核查是否支持定投、定投起点和月度胜率' },
}

function salesRuleEvidenceCopyForPlan(purchasePlan: InvestorPurchasePlan) {
  if (purchasePlan === 'lump_sum') {
    return {
      formalFields: '申购费、赎回费、销售服务费、起购金额、限购和风险等级',
      recheckFields: '申购费、赎回费、销售服务费、起购金额、限购和风险等级',
      reviewChecklist: '复核销售平台实时申购状态、起购金额、限购、费率与风险等级',
      primaryNextAction: '先补主基金申购、费率、赎回、起购金额、限购、风险等级和来源日期',
    }
  }
  return {
    formalFields: '申购费、赎回费、销售服务费、定投规则、限购和风险等级',
    recheckFields: '申购费、赎回费、销售服务费、定投起点、限购和风险等级',
    reviewChecklist: '复核销售平台实时申购/定投状态、限购、费率与风险等级',
    primaryNextAction: '先补主基金申购、费率、赎回、定投、限购、风险等级和来源日期',
  }
}

function asNumber(value: unknown) {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function metric(source: Record<string, unknown> | null | undefined, keys: string[]) {
  for (const key of keys) {
    const value = asNumber(source?.[key])
    if (value !== null) return value
  }
  return null
}

const supportedMethodologyTemplateNames = [
  '主动权益基金研究模板',
  '固收基金研究模板',
  '指数基金研究模板',
  '货币基金研究模板',
  'QDII 基金研究模板',
  'FOF 基金研究模板',
  '量化基金研究模板',
]

function availableMethodologyEvidenceForReport(
  fund: ReportFund,
  holdingEvidence?: HoldingEvidence | null,
  shareClassEvidence?: ShareClassEvidence | null,
) {
  const benchmark = typeof fund.benchmark === 'string' ? fund.benchmark : fund.benchmark?.primaryBenchmark
  return Array.from(new Set([
    fund.type ? 'asset_class' : '',
    fund.type ? 'strategy_type' : '',
    fund.totalAsset != null ? 'aum' : '',
    fund.performanceData ? 'excess_return' : '',
    fund.performanceData ? 'tracking_difference' : '',
    fund.riskMetrics ? 'tracking_error' : '',
    fund.riskMetrics ? 'duration' : '',
    benchmark || fund.researchProfile?.primaryBenchmark || fund.peerPercentiles?.primary_benchmark ? 'benchmark_mapping' : '',
    benchmark || fund.researchProfile?.primaryBenchmark || fund.peerPercentiles?.primary_benchmark ? 'index_benchmark' : '',
    fund.peerPercentiles?.peer_group || fund.researchProfile?.peerGroup ? 'peer_group_policy' : '',
    fund.peerPercentiles?.peer_group || fund.researchProfile?.peerGroup ? 'same_index_peers' : '',
    fund.researchProfile?.styleLabel ? 'style_exposure' : '',
    fund.researchProfile?.strategyTags?.length ? 'style_tags' : '',
    fund.managers?.length ? 'tenure_slice' : '',
    fund.managers?.length ? 'representative_fund' : '',
    holdingEvidence?.status === 'available' ? 'top_holdings' : '',
    holdingEvidence?.status === 'available' ? 'holding_count' : '',
    holdingEvidence?.status === 'available' ? 'industry_exposure' : '',
    holdingEvidence?.status === 'available' ? 'constituents' : '',
    fund.salesRule ? 'fee_rate' : '',
    shareClassEvidence?.status === 'available' ? 'share_class' : '',
    shareClassEvidence?.status === 'available' ? 'expense_ratio' : '',
  ].filter(Boolean)))
}

function dimensionReportAnchor(dimension: MethodologyDimension) {
  if (dimension.name.includes('信用暴露')) return '第 6 节经理归因覆盖外，需补充债券评级、主体集中度和违约历史证据。'
  if (dimension.name.includes('费用与跟踪误差')) return '第 3.1 节同基金份额比较和第 4 节回放费用估算应优先阅读。'
  if (dimension.name.includes('汇率与区域暴露')) return '第 5 节持仓与行业暴露需扩展为区域、币种和海外市场暴露。'
  if (dimension.name.includes('底层基金穿透')) return '第 5 节持仓证据需升级为底层基金和资产配置穿透。'
  if (dimension.name.includes('模型稳定性')) return '第 2 节方法论缺口需重点补因子衰减、IC 稳定性和容量信号。'
  if (dimension.name.includes('基准与归因')) return '第 2 节核心指标和第 7 节替代候选必须围绕基准和超额来源解释。'
  if (dimension.name.includes('同类池')) return '第 7 节同画像替代候选必须先确认同类池可解释。'
  if (dimension.name.includes('持仓')) return '第 5 节持仓与行业暴露是该模板的核心证据。'
  if (dimension.name.includes('基金经理')) return '第 6 节经理归因覆盖是该模板的核心证据。'
  if (dimension.name.includes('基金公司')) return '需结合公司产品线、平台能力和同公司横评补证。'
  return '作为报告后续章节的证据检查项。'
}

function buildReportMethodologySections(
  fund: ReportFund,
  holdingEvidence?: HoldingEvidence | null,
  shareClassEvidence?: ShareClassEvidence | null,
) {
  const data = resolveMethodologyConfigFromDataSync({
    fundType: fund.type,
    assetClass: fund.type,
    strategyFamilyKey: fund.researchProfile?.strategyTags?.[0] || fund.researchProfile?.styleLabel || fund.type,
    availableEvidence: availableMethodologyEvidenceForReport(fund, holdingEvidence, shareClassEvidence),
  })
  const dimensions = (data.dimensions || []).slice(0, 6)
  const methodologySectionLines = [
    `- 研究模板：${data.templateName || '基金分类待确认'}`,
    `- 匹配依据：${data.matchRationale || '基金分类证据待补，暂不选择评价模板。'}`,
    `- 核心研究维度：${dimensions.map((dimension) => `${dimension.name}（权重 ${dimension.weight}）`).join('；') || '待补'}`,
    `- 方法论缺口：${data.missingEvidenceFields?.length ? data.missingEvidenceFields.join('、') : '无'}`,
    ...dimensions.map((dimension) => `- 章节重点：${dimension.name}；${dimension.reason}；${dimensionReportAnchor(dimension)}`),
    '- 方法论模板只决定研究口径；证据不完整时只能输出补证方向，不输出申赎执行、资产配置或审批动作。',
  ]
  return {
    templateKey: data.templateKey,
    templateName: data.templateName || '基金分类待确认',
    dimensions,
    missingEvidenceFields: data.missingEvidenceFields || [],
    readyForFormalReview: Boolean(data.readyForFormalReview),
    methodologySectionLines,
    supportedMethodologyTemplateNames,
    hardBlocks: data.readyForFormalReview ? [] : [data.resolutionStatus === 'unclassified'
      ? '基金分类证据待补，不能选择评价模板'
      : `${data.templateName} 方法论硬门槛证据待补`],
  }
}

function parseSalesRiskLevel(value: string | null | undefined) {
  const match = String(value || '').trim().match(/R?([1-5])/i)
  return match ? Number(match[1]) : null
}

const SALES_RISK_SOURCE_MAX_AGE_DAYS = 30

function isFreshSalesRiskSourceDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}/u.test(value)) return false
  const sourceDate = new Date(`${value.slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(sourceDate.getTime())) return false
  const currentDate = new Date()
  currentDate.setUTCHours(0, 0, 0, 0)
  const ageDays = Math.floor((currentDate.getTime() - sourceDate.getTime()) / 86_400_000)
  return ageDays >= 0 && ageDays <= SALES_RISK_SOURCE_MAX_AGE_DAYS
}

function hasSourceBackedSalesRiskLevel(rule: ReportFund['salesRule']) {
  if (!rule?.riskLevel || parseSalesRiskLevel(rule.riskLevel) === null) return false
  const sourceUpdatedAt = String(rule.sourceUpdatedAt || '').trim()
  if (!isFreshSalesRiskSourceDate(sourceUpdatedAt)) return false
  const platform = String(rule.platform || '').trim()
  const sourceUrl = String(rule.sourceUrl || '').trim()
  const notes = String(rule.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function hasSourceBackedSalesRuleField(
  rule: ReportFund['salesRule'],
  sourceFlag: keyof NonNullable<ReportFund['salesRule']>,
  value: unknown,
) {
  if (value === null || value === undefined || value === '') return false
  const explicitFlag = rule?.[sourceFlag]
  if (explicitFlag === true) return true
  if (explicitFlag === false) return false
  const sourceUpdatedAt = String(rule?.sourceUpdatedAt || '').trim()
  if (!isFreshSalesRiskSourceDate(sourceUpdatedAt)) return false
  const platform = String(rule?.platform || '').trim()
  const sourceUrl = String(rule?.sourceUrl || '').trim()
  const notes = String(rule?.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function hasSourceBackedRedemptionRules(rule: ReportFund['salesRule']) {
  if (!rule?.redemptionFeeRules?.length) return false
  const sourceUpdatedAt = String(rule.redemptionFeeSourceUpdatedAt || rule.sourceUpdatedAt || '').trim()
  if (!isFreshSalesRiskSourceDate(sourceUpdatedAt)) return false
  const platform = String(rule.redemptionFeePlatform || rule.platform || '').trim()
  const sourceUrl = String(rule.redemptionFeeSourceUrl || rule.sourceUrl || '').trim()
  const notes = String(rule.redemptionFeeNotes || rule.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function buildRiskLevelSourcePolicy(rule: ReportFund['salesRule'], salesRiskLevel: number | null, sourceBacked: boolean) {
  const sourceUpdatedAt = String(rule?.sourceUpdatedAt || '').trim()
  const platform = String(rule?.platform || '').trim()
  const sourceUrl = String(rule?.sourceUrl || '').trim()
  const notes = String(rule?.notes || '').trim()
  const hasExcludedSource = platform.toLowerCase().includes('tushare') || sourceUrl.toLowerCase().includes('tushare.fund_basic')
  return {
    label: '销售风险等级（R1-R5 30天来源背书）',
    status: sourceBacked ? 'source_backed_30d' : 'blocked_missing_stale_or_excluded',
    sourceBacked,
    hardGate: true,
    windowDays: SALES_RISK_SOURCE_MAX_AGE_DAYS,
    riskLevel: salesRiskLevel === null ? null : `R${salesRiskLevel}`,
    sourceUpdatedAt: sourceUpdatedAt || null,
    sourceFresh: Boolean(sourceUpdatedAt && isFreshSalesRiskSourceDate(sourceUpdatedAt)),
    platform: platform || null,
    sourceUrl: sourceUrl || null,
    hasSourceEvidence: hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes }),
    excludedSources: ['Tushare fund_basic'],
    hasExcludedSource,
    acceptableSources: ['销售平台', '基金合同', '招募说明书'],
    signals: [
      'R1-R5 来源背书',
      '30天来源窗口',
      '销售风险等级（R1-R5 30天来源背书）',
      'Tushare fund_basic 排除',
      '销售平台/基金合同来源',
    ],
  }
}

function percentText(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return `${(Number(value) * 100).toFixed(2)}%`
}

function percentPointText(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  const sign = Number(value) > 0 ? '+' : ''
  return `${sign}${(Number(value) * 100).toFixed(2)}pct`
}

function evidenceGradeScore(value: string | null | undefined) {
  if (value === 'A') return 4
  if (value === 'B') return 3
  if (value === 'C') return 2
  return 1
}

function buildManagerAttributionDecision(
  fund: ReportFund,
  investorContext: ReturnType<typeof normalizeInvestorContext>,
): ManagerAttributionDecision {
  const managers = Array.isArray(fund.managers) ? fund.managers : []
  const managerNames = managers.map((manager) => manager.name || manager.managerId || '姓名待补').filter(Boolean)
  const tenureYears = managers
    .map((manager) => asNumber(manager.managementYears))
    .filter((value): value is number => value !== null)
  const maxTenureYears = tenureYears.length ? Math.max(...tenureYears) : null
  const attributionWindowYears = investorContext.horizon === 'gt3y' ? 3 : 1
  const coverageRatio = maxTenureYears === null
    ? null
    : Math.round(Math.max(0, Math.min(1, maxTenureYears / attributionWindowYears)) * 100)
  const status: ManagerAttributionDecision['status'] = !managers.length
    ? 'missing'
    : coverageRatio === null
      ? 'missing'
      : coverageRatio >= 100
        ? 'covered'
        : coverageRatio >= 60
          ? 'partial'
          : 'weak'
  const label = status === 'covered'
    ? '现任经理覆盖观察窗口'
    : status === 'partial'
      ? '现任经理部分覆盖观察窗口'
      : status === 'weak'
        ? '现任经理弱覆盖观察窗口'
        : '经理归因待补'

  return {
    label,
    status,
    attributionWindowYears,
    coverageRatio,
    maxTenureYears,
    managerNames,
    reasons: [
      managerNames.length ? `现任经理：${managerNames.join(' / ')}` : '现任经理明细待补',
      maxTenureYears === null ? '最长任期待补' : `最长任期约 ${maxTenureYears.toFixed(1)} 年`,
      coverageRatio === null ? `${attributionWindowYears}年业绩归因覆盖率待补` : `${attributionWindowYears}年业绩归因覆盖率 ${coverageRatio}%`,
    ],
    warnings: [
      status === 'covered' ? '' : `现任经理任期未完整覆盖 ${attributionWindowYears} 年观察窗口，不能把完整窗口业绩直接归因给现任经理。`,
      status === 'weak' ? '经理任期覆盖率偏低，正式研究复核报告应先复核上任前后收益、回撤和规模变化。' : '',
      status === 'missing' ? '经理明细或任期待补，经理维度不能作为正式研究复核加分依据。' : '',
    ].filter(Boolean),
  }
}

function buildHoldingExposureDecision(
  holdingEvidence: HoldingEvidence | null | undefined,
  investorContext: ReturnType<typeof normalizeInvestorContext>,
): HoldingExposureDecision {
  if (!holdingEvidence || holdingEvidence.status !== 'available') {
    return {
      label: '持仓暴露待补',
      score: 35,
      topTenWeight: null,
      topIndustryWeight: null,
      topIndustry: '行业待补',
      primaryRisk: '缺少可信季报持仓，不能解释行业/个股暴露',
      nextAction: '补齐最新季报持仓后，再判断集中度和风格暴露是否支持研究结论',
      reasons: [
        holdingEvidence?.note || '未取得可验证持仓，暂不做行业/个股暴露判断。',
        `已检查季度：${holdingEvidence?.checkedQuarters?.join(' / ') || '待补'}`,
        `已拦截疑似样例季度：${holdingEvidence?.rejectedMockLikeQuarters?.length || 0}`,
      ],
      reverseTriggers: [
        '可信持仓补齐后，若前十大或单一行业集中度过高，结论会转为更谨慎。',
        '若持仓行业与基金名称、基准或研究画像明显不一致，需要重新确认同类比较口径。',
      ],
    }
  }

  const topTenWeight = holdingEvidence.totalWeight ?? null
  const sortedIndustries = [...(holdingEvidence.industryBuckets || [])].sort((left, right) => right.weight - left.weight)
  const topIndustry = sortedIndustries[0] || null
  const topIndustryWeight = topIndustry?.weight ?? null
  const topStock = (holdingEvidence.holdings || []).slice().sort((left, right) => (right.weight ?? 0) - (left.weight ?? 0))[0] || null
  const concentrationBudget = investorContext.profile === 'conservative' ? 0.45 : investorContext.profile === 'balanced' ? 0.6 : 0.75
  const industryBudget = investorContext.profile === 'conservative' ? 0.3 : investorContext.profile === 'balanced' ? 0.4 : 0.5
  const topTenRisk = topTenWeight !== null && topTenWeight > concentrationBudget
  const industryRisk = topIndustryWeight !== null && topIndustryWeight > industryBudget
  const score = Math.round(Math.max(0, Math.min(100,
    82
    - (topTenRisk ? 22 : topTenWeight !== null && topTenWeight > concentrationBudget * 0.8 ? 10 : 0)
    - (industryRisk ? 18 : topIndustryWeight !== null && topIndustryWeight > industryBudget * 0.85 ? 8 : 0)
    - ((holdingEvidence.holdings || []).length < 10 ? 10 : 0)
    - ((holdingEvidence.industryBuckets || []).length < 3 ? 8 : 0),
  )))
  const label = topTenRisk || industryRisk
    ? '暴露集中，先解释风险来源'
    : score >= 72
      ? '持仓暴露可用于研究判断'
      : '持仓暴露可观察'
  const primaryRisk = [
    topTenRisk ? `前十大权重 ${percentText(topTenWeight)} 超过${investorContext.profileLabel}集中度预算 ${percentText(concentrationBudget)}` : '',
    industryRisk ? `${topIndustry?.industry || '第一行业'}权重 ${percentText(topIndustryWeight)} 超过行业预算 ${percentText(industryBudget)}` : '',
  ].filter(Boolean).join('；') || '未发现超出当前画像预算的集中度信号'

  return {
    label,
    score,
    topTenWeight,
    topIndustryWeight,
    topIndustry: topIndustry?.industry || '行业待补',
    primaryRisk,
    nextAction: topTenRisk || industryRisk
      ? '先解释重仓行业/个股风险，再进入研究清单、横向比较或研究复核报告'
      : '复核最新季报是否延续当前暴露，再与同类基金横向比较',
    reasons: [
      `持仓季度 ${holdingEvidence.quarter || '待补'}，前十大合计 ${percentText(topTenWeight)}`,
      `第一行业 ${topIndustry?.industry || '待补'} ${percentText(topIndustryWeight)}，行业桶 ${(holdingEvidence.industryBuckets || []).length} 个`,
      topStock ? `第一重仓 ${topStock.stockName || topStock.stockCode || '名称待补'} ${percentText(topStock.weight ?? null)}` : '第一重仓待补',
      `可信过滤来源：${holdingEvidence.source || 'backend.tushare.fund_holding.filtered'}`,
    ],
    reverseTriggers: [
      topTenRisk || industryRisk
        ? '若后续季报显示集中度下降且同类回撤不劣于替代候选，可重新提高研究优先级。'
        : '若后续季报显示前十大或第一行业集中度明显升高，当前结论会转为更谨慎。',
      '若重仓行业与基金基准、名称或同类分组不一致，需要重新确认同类比较口径。',
    ],
  }
}

function moneyText(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return `¥${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
}

function feeRateText(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return `${Number(value).toFixed(2)}%`
}

function estimateFee(amount: number | null | undefined, feeRate: number | null) {
  if (amount === null || amount === undefined || feeRate === null) return null
  return amount * feeRate / 100
}

type NormalizedRedemptionRule = {
  holdingDays: number | null
  feeRate: number
  label: string
}

function horizonDaysForContext(horizon: InvestorHorizon) {
  if (horizon === 'lt1y') return 180
  if (horizon === '1to3y') return 365
  return 1095
}

function normalizeRedemptionRules(rules: NonNullable<ReportFund['salesRule']>['redemptionFeeRules'] | null | undefined): NormalizedRedemptionRule[] {
  return (rules || [])
    .map((rule) => ({
      holdingDays: asNumber(rule.holdingDays),
      feeRate: asNumber(rule.feeRate),
      label: rule.label || '赎回费率',
    }))
    .filter((rule): rule is NormalizedRedemptionRule => rule.feeRate !== null)
    .sort((left, right) => (left.holdingDays ?? 0) - (right.holdingDays ?? 0))
}

function redemptionRuleAtHoldingDays(
  rules: NonNullable<ReportFund['salesRule']>['redemptionFeeRules'] | null | undefined,
  holdingDays: number | null,
) {
  const normalizedRules = normalizeRedemptionRules(rules)
  if (!normalizedRules.length) return null
  if (holdingDays === null) return normalizedRules[0]
  return normalizedRules.find((rule) => rule.holdingDays === null || holdingDays <= rule.holdingDays)
    || normalizedRules[normalizedRules.length - 1]
}

function buildAlternativeWinLossLines({
  fund,
  annualReturn,
  maxDrawdownValue,
  feeEstimate,
  hasCompleteTransactionFeeRates,
  salesRuleHardGap,
  evidenceGrade,
  alternativeEvidence,
}: {
  fund: ReportFund
  annualReturn: number | null
  maxDrawdownValue: number | null
  feeEstimate: { purchaseFeeRate: number | null; redemptionFeeRate: number | null; salesServiceFeeRate: number | null } | null
  hasCompleteTransactionFeeRates: boolean
  salesRuleHardGap: SalesRuleGapEvidence['gap'] | null | undefined
  evidenceGrade: string
  alternativeEvidence?: AlternativeEvidence | null
}): AlternativeWinLossLine[] {
  return (alternativeEvidence?.funds || []).slice(0, 4).map((alternative) => {
    const returnDelta = annualReturn !== null && alternative.annualReturn !== null && alternative.annualReturn !== undefined
      ? annualReturn - alternative.annualReturn
      : null
    const drawdownDelta = maxDrawdownValue !== null && alternative.maxDrawdown !== null && alternative.maxDrawdown !== undefined
      ? Math.abs(maxDrawdownValue) - Math.abs(alternative.maxDrawdown)
      : null
    const scoreDelta = alternative.investorScore === null || alternative.investorScore === undefined ? null : 0 - alternative.investorScore
    const primaryRulesReady = !salesRuleHardGap?.missingCount
    const alternativeRulesReady = !(alternative.salesRuleGap?.missingCount)
    const salesRuleReady = primaryRulesReady && alternativeRulesReady
    const riskWin = drawdownDelta !== null && drawdownDelta <= 0.02
    const returnWin = returnDelta !== null && returnDelta >= -0.01
    const scoreWin = alternative.investorScore === null || alternative.investorScore === undefined ? false : alternative.investorScore <= 70
    const costWin = hasCompleteTransactionFeeRates && feeEstimate?.salesServiceFeeRate !== null && feeEstimate?.salesServiceFeeRate !== undefined
    const evidenceWin = evidenceGradeScore(evidenceGrade) >= evidenceGradeScore(alternative.purchaseGate?.evidenceGrade || 'D')
    const passedChecks = [salesRuleReady, riskWin, returnWin, scoreWin, costWin, evidenceWin].filter(Boolean).length
    const status = !salesRuleReady
      ? 'rules_pending'
      : passedChecks >= 5
        ? 'win'
        : passedChecks >= 3
          ? 'close'
          : 'lose'
    return {
      challengerCode: alternative.windCode || '',
      challengerName: alternative.name || alternative.windCode || '替代候选',
      status,
      label: status === 'win' ? '主基金胜出' : status === 'close' ? '接近' : status === 'rules_pending' ? '规则待补' : '主基金未胜出',
      summary: `${alternative.name || alternative.windCode || '替代候选'}：收益差 ${percentPointText(returnDelta)}；回撤差 ${percentPointText(drawdownDelta)}；主基金申购费 ${feeRateText(feeEstimate?.purchaseFeeRate)}；替代分 ${alternative.investorScore ?? '待补'}`,
      thresholds: [
        {
          key: 'sales_rules',
          label: '销售规则',
          passed: salesRuleReady,
          detail: salesRuleReady
            ? '主基金与替代候选均未见销售规则硬缺口。'
            : `补齐前只做研究态横评；主基金缺 ${salesRuleHardGap?.missingCount || 0} 项，替代缺 ${alternative.salesRuleGap?.missingCount || 0} 项。`,
        },
        {
          key: 'risk',
          label: '回撤控制',
          passed: riskWin,
          detail: `主基金回撤不能比替代高 2pct 以上；当前 ${percentPointText(drawdownDelta)}。`,
        },
        {
          key: 'return',
          label: '收益弹性',
          passed: returnWin,
          detail: `主基金近一年收益不能落后替代 1pct 以上；当前 ${percentPointText(returnDelta)}。`,
        },
        {
          key: 'score',
          label: '选基分',
          passed: scoreWin,
          detail: `替代候选选基分 ${alternative.investorScore ?? '待补'}；若替代显著领先，主基金不能单独入选。`,
        },
        {
          key: 'cost',
          label: '费用口径',
          passed: costWin,
          detail: `主基金至少需补齐申购费、赎回费和销售服务费后才可做费用后横评；当前申购费 ${feeRateText(feeEstimate?.purchaseFeeRate)}，赎回费 ${feeRateText(feeEstimate?.redemptionFeeRate)}，销售服务费 ${feeRateText(feeEstimate?.salesServiceFeeRate)}。`,
        },
        {
          key: 'evidence',
          label: '证据等级',
          passed: evidenceWin,
          detail: `主基金证据 ${evidenceGrade}，替代 ${alternative.purchaseGate?.evidenceGrade || 'D'}。`,
        },
      ],
      passedChecks,
      totalChecks: 6,
    }
  })
}

function maxDrawdown(values: number[]) {
  let peak = values[0] ?? 0
  let worst = 0
  for (const value of values) {
    if (value > peak) peak = value
    if (peak > 0) worst = Math.min(worst, value / peak - 1)
  }
  return worst
}

function monthlyFirstRows(rows: NavPoint[]) {
  const seen = new Set<string>()
  return rows.filter((row) => {
    const month = row.date.slice(0, 7)
    if (seen.has(month)) return false
    seen.add(month)
    return true
  })
}

function monthlyReturns(rows: NavPoint[]) {
  const monthLast = new Map<string, NavPoint>()
  for (const row of rows) {
    monthLast.set(row.date.slice(0, 7), row)
  }
  const monthRows = Array.from(monthLast.values()).sort((left, right) => left.date.localeCompare(right.date))
  const returns = []
  for (let index = 1; index < monthRows.length; index += 1) {
    const previous = monthRows[index - 1]
    const current = monthRows[index]
    returns.push({
      month: current.date.slice(0, 7),
      returnRate: current.nav / previous.nav - 1,
    })
  }
  return returns
}

function daysBetween(startDate: string, endDate: string) {
  const start = new Date(startDate)
  const end = new Date(endDate)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null
  return Math.max(0, Math.floor((end.getTime() - start.getTime()) / 86_400_000))
}

function buildStressExperience(rows: NavPoint[], returns: Array<{ month: string; returnRate: number }>) {
  const first = rows[0]
  let peakNav = first.nav
  let peakDate = first.date
  let troughDate = first.date
  let worstDrawdown = 0
  let worstRecoveryDays: number | null = null
  let longestUnderwaterDays = 0
  let currentUnderwaterStart: string | null = null

  for (const row of rows) {
    if (row.nav >= peakNav) {
      if (currentUnderwaterStart) {
        longestUnderwaterDays = Math.max(longestUnderwaterDays, daysBetween(currentUnderwaterStart, row.date) ?? 0)
        if (peakDate <= troughDate && row.date >= troughDate && worstRecoveryDays === null) {
          worstRecoveryDays = daysBetween(peakDate, row.date)
        }
        currentUnderwaterStart = null
      }
      peakNav = row.nav
      peakDate = row.date
    } else {
      if (!currentUnderwaterStart) currentUnderwaterStart = peakDate
      const drawdown = row.nav / peakNav - 1
      if (drawdown < worstDrawdown) {
        worstDrawdown = drawdown
        troughDate = row.date
        worstRecoveryDays = null
      }
    }
  }

  if (currentUnderwaterStart) {
    longestUnderwaterDays = Math.max(longestUnderwaterDays, daysBetween(currentUnderwaterStart, rows[rows.length - 1].date) ?? 0)
  }

  let longestLosingStreakMonths = 0
  let currentLosingStreakMonths = 0
  let worstThreeMonthReturn: null | { startMonth: string; endMonth: string; returnRate: number } = null

  returns.forEach((item, index) => {
    if (item.returnRate < 0) {
      currentLosingStreakMonths += 1
      longestLosingStreakMonths = Math.max(longestLosingStreakMonths, currentLosingStreakMonths)
    } else {
      currentLosingStreakMonths = 0
    }

    if (index >= 2) {
      const windowRows = returns.slice(index - 2, index + 1)
      const compoundedReturn = windowRows.reduce((product, row) => product * (1 + row.returnRate), 1) - 1
      if (!worstThreeMonthReturn || compoundedReturn < worstThreeMonthReturn.returnRate) {
        worstThreeMonthReturn = {
          startMonth: windowRows[0].month,
          endMonth: windowRows[windowRows.length - 1].month,
          returnRate: compoundedReturn,
        }
      }
    }
  })

  const stressScore = Math.round(Math.max(0, Math.min(100,
    100 -
    Math.abs(worstDrawdown) * 220 -
    longestLosingStreakMonths * 6 -
    Math.min(30, longestUnderwaterDays / 18),
  )))
  const stressLevel: NonNullable<PurchaseSimulation['stressExperience']>['stressLevel'] = stressScore >= 75
    ? 'comfortable'
    : stressScore >= 60
      ? 'watchable'
      : stressScore >= 45
        ? 'bumpy'
        : 'stressful'
  const label = stressLevel === 'comfortable'
    ? '压力体验较温和'
    : stressLevel === 'watchable'
      ? '压力体验可观察'
      : stressLevel === 'bumpy'
        ? '压力体验偏颠簸'
        : '压力体验压力较大'

  return {
    label,
    stressLevel,
    stressScore,
    worstDrawdown,
    troughDate,
    recoveryDays: worstRecoveryDays,
    longestUnderwaterDays,
    longestLosingStreakMonths,
    worstThreeMonthReturn,
    interpretation: worstRecoveryDays === null
      ? '历史回放期内最大回撤尚未完全回本，研究复核需确认研究画像能否承受账面亏损持续时间。'
      : `最大回撤后约 ${worstRecoveryDays} 天回到前高，研究复核需结合计划持有期判断等待成本。`,
  }
}

function simulateLumpSum(rows: NavPoint[], amount: number) {
  const first = rows[0]
  const last = rows[rows.length - 1]
  const units = amount / first.nav
  const endingValue = units * last.nav
  return {
    totalInvested: amount,
    endingValue: Math.round(endingValue * 100) / 100,
    profit: Math.round((endingValue - amount) * 100) / 100,
    returnRate: endingValue / amount - 1,
    maxDrawdown: maxDrawdown(rows.map((row) => row.nav)),
    holdingDays: daysBetween(first.date, last.date),
  }
}

function simulateSip(rows: NavPoint[], monthlyAmount: number) {
  const contributionRows = monthlyFirstRows(rows)
  let totalInvested = 0
  let units = 0
  const accountValues: number[] = []

  for (const row of rows) {
    if (contributionRows.some((item) => item.date === row.date)) {
      totalInvested += monthlyAmount
      units += monthlyAmount / row.nav
    }
    accountValues.push(units * row.nav)
  }

  const last = rows[rows.length - 1]
  const endingValue = units * last.nav
  return {
    totalInvested,
    endingValue: Math.round(endingValue * 100) / 100,
    profit: Math.round((endingValue - totalInvested) * 100) / 100,
    returnRate: totalInvested > 0 ? endingValue / totalInvested - 1 : null,
    contributionCount: contributionRows.length,
    maxAccountDrawdown: maxDrawdown(accountValues.filter((value) => value > 0)),
  }
}

export function normalizeNavRows(rows: Array<Record<string, unknown>>): NavPoint[] {
  return rows
    .map((row) => ({
      date: String(row.date || ''),
      nav: asNumber(row.nav) ?? 0,
    }))
    .filter((row) => row.date && row.nav > 0)
    .sort((left, right) => left.date.localeCompare(right.date))
}

export function buildPurchaseSimulationFromNav(
  rows: NavPoint[],
  months: number,
  lumpSumAmount: number,
  monthlyAmount: number,
): PurchaseSimulation | null {
  if (rows.length < 2) return null
  const returns = monthlyReturns(rows)
  const positiveMonths = returns.filter((item) => item.returnRate > 0).length
  const bestMonth = returns.reduce((best, item) => !best || item.returnRate > best.returnRate ? item : best, null as null | { month: string; returnRate: number })
  const worstMonth = returns.reduce((worst, item) => !worst || item.returnRate < worst.returnRate ? item : worst, null as null | { month: string; returnRate: number })

  return {
    source: 'backend.tushare.fund_nav',
    period: {
      startDate: rows[0].date,
      endDate: rows[rows.length - 1].date,
      observations: rows.length,
      months,
    },
    assumptions: {
      lumpSumAmount,
      monthlyAmount,
      feeIncluded: false,
    },
    lumpSum: simulateLumpSum(rows, lumpSumAmount),
    sip: simulateSip(rows, monthlyAmount),
    monthlyExperience: {
      months: returns.length,
      positiveMonths,
      positiveRatio: returns.length ? positiveMonths / returns.length : null,
      bestMonth,
      worstMonth,
    },
    stressExperience: buildStressExperience(rows, returns),
  }
}

export function normalizeInvestorContext(input: {
  profile?: string | null
  horizon?: string | null
  purchasePlan?: string | null
}) {
  const profile = ['conservative', 'balanced', 'aggressive'].includes(input.profile || '')
    ? input.profile as InvestorRiskProfile
    : 'balanced'
  const horizon = ['lt1y', '1to3y', 'gt3y'].includes(input.horizon || '')
    ? input.horizon as InvestorHorizon
    : '1to3y'
  const purchasePlan = ['lump_sum', 'sip'].includes(input.purchasePlan || '')
    ? input.purchasePlan as InvestorPurchasePlan
    : 'sip'

  return {
    profile,
    horizon,
    purchasePlan,
    profileLabel: investorRiskProfiles[profile].label,
    horizonLabel: investorHorizons[horizon].label,
    purchasePlanLabel: investorPurchasePlans[purchasePlan].label,
    profileNote: investorRiskProfiles[profile].note,
    horizonNote: investorHorizons[horizon].note,
    purchasePlanNote: investorPurchasePlans[purchasePlan].note,
    maxDrawdownTolerance: investorRiskProfiles[profile].maxDrawdownTolerance,
    maxSalesRiskLevel: investorRiskProfiles[profile].maxSalesRiskLevel,
    minSampleMonths: investorHorizons[horizon].minSampleMonths,
  }
}

export function buildResearchReviewReport({
  fund,
  buyEvidence,
  investorContext,
  plannedAmount: plannedAmountInput,
  purchaseSimulation,
  simulationError,
  holdingEvidence,
  salesRuleGapEvidence,
  alternativeEvidence,
  shareClassEvidence,
  generatedAt,
}: {
  fund: ReportFund
  buyEvidence: BuyEvidence
  investorContext: ReturnType<typeof normalizeInvestorContext>
  plannedAmount?: number | null
  purchaseSimulation: PurchaseSimulation | null
  simulationError?: string | null
  holdingEvidence?: HoldingEvidence | null
  salesRuleGapEvidence?: SalesRuleGapEvidence | null
  alternativeEvidence?: AlternativeEvidence | null
  shareClassEvidence?: ShareClassEvidence | null
  generatedAt: string
}) {
  const salesRuleEvidenceCopy = salesRuleEvidenceCopyForPlan(investorContext.purchasePlan)
  const annualReturn = metric(fund.performanceData || {}, ['annualized_return_1y', 'return_1y', 'annual_return'])
  const maxDrawdownValue = metric(fund.riskMetrics || {}, ['max_drawdown_1y', 'max_drawdown', 'max_drawdown_2y'])
  const volatility = metric(fund.riskMetrics || {}, ['annualized_volatility_1y', 'volatility', 'annualized_volatility_2y'])
  const drawdown = maxDrawdownValue === null ? null : Math.abs(maxDrawdownValue)
  const totalAsset = asNumber(fund.totalAsset)
  const hasVerifiedSalesRiskLevel = hasSourceBackedSalesRiskLevel(fund.salesRule)
  const salesRiskLevel = hasVerifiedSalesRiskLevel ? parseSalesRiskLevel(fund.salesRule?.riskLevel) : null
  const riskLevelSourcePolicy = buildRiskLevelSourcePolicy(fund.salesRule, salesRiskLevel, hasVerifiedSalesRiskLevel)
  const operationStatus = fund.operationStatus
  const rawMinPurchaseAmount = asNumber(fund.salesRule?.minPurchaseAmount)
  const rawMinSipAmount = asNumber(fund.salesRule?.minSipAmount)
  const rawDailyLimitAmount = asNumber(fund.salesRule?.dailyLimitAmount)
  const minPurchaseAmount = hasSourceBackedSalesRuleField(fund.salesRule, 'minPurchaseSourceBacked', rawMinPurchaseAmount) ? rawMinPurchaseAmount : null
  const minSipAmount = hasSourceBackedSalesRuleField(fund.salesRule, 'minSipSourceBacked', rawMinSipAmount) ? rawMinSipAmount : null
  const dailyLimitAmount = hasSourceBackedSalesRuleField(fund.salesRule, 'dailyLimitSourceBacked', rawDailyLimitAmount) ? rawDailyLimitAmount : null
  const supportsSip = hasSourceBackedSalesRuleField(fund.salesRule, 'supportsSipSourceBacked', fund.salesRule?.supportsSip) ? fund.salesRule?.supportsSip : null
  const fallbackPlannedAmount = asNumber(plannedAmountInput)
  const plannedAmount = purchaseSimulation
    ? investorContext.purchasePlan === 'lump_sum'
      ? purchaseSimulation.lumpSum.totalInvested
      : purchaseSimulation.assumptions.monthlyAmount
    : fallbackPlannedAmount
  const rawPurchaseFeeRate = asNumber(fund.salesRule?.purchaseFeeRate)
  const purchaseFeeRate = hasSourceBackedSalesRuleField(fund.salesRule, 'purchaseFeeSourceBacked', rawPurchaseFeeRate) ? rawPurchaseFeeRate : null
  const redemptionHoldingDays = purchaseSimulation?.lumpSum.holdingDays ?? horizonDaysForContext(investorContext.horizon)
  const redemptionRule = hasSourceBackedRedemptionRules(fund.salesRule)
    ? redemptionRuleAtHoldingDays(fund.salesRule?.redemptionFeeRules, redemptionHoldingDays)
    : null
  const redemptionFeeRate = asNumber(redemptionRule?.feeRate)
  const rawSalesServiceFeeRate = asNumber(fund.salesRule?.salesServiceFeeRate)
  const salesServiceFeeRate = hasSourceBackedSalesRuleField(fund.salesRule, 'salesServiceFeeSourceBacked', rawSalesServiceFeeRate) ? rawSalesServiceFeeRate : null
  const feeEstimate = purchaseSimulation
    ? {
        purchaseFeeRate,
        redemptionFeeRate,
        redemptionRuleLabel: redemptionRule?.label || null,
        salesServiceFeeRate,
        lumpSumPurchaseFee: estimateFee(purchaseSimulation.lumpSum.totalInvested, purchaseFeeRate),
        lumpSumRedemptionFee: estimateFee(purchaseSimulation.lumpSum.endingValue, redemptionFeeRate),
        sipPurchaseFee: estimateFee(purchaseSimulation.sip.totalInvested, purchaseFeeRate),
        sipRedemptionFee: estimateFee(purchaseSimulation.sip.endingValue, redemptionFeeRate),
      }
    : null
  const hasCompleteTransactionFeeRates = purchaseFeeRate !== null && redemptionFeeRate !== null && salesServiceFeeRate !== null
  const lumpSumEstimatedCost = feeEstimate
    ? hasCompleteTransactionFeeRates ? (feeEstimate.lumpSumPurchaseFee ?? 0) + (feeEstimate.lumpSumRedemptionFee ?? 0) : null
    : null
  const sipEstimatedCost = feeEstimate
    ? hasCompleteTransactionFeeRates ? (feeEstimate.sipPurchaseFee ?? 0) + (feeEstimate.sipRedemptionFee ?? 0) : null
    : null
  const lumpSumNetProfit = purchaseSimulation && lumpSumEstimatedCost !== null
    ? purchaseSimulation.lumpSum.profit - lumpSumEstimatedCost
    : null
  const sipNetProfit = purchaseSimulation && sipEstimatedCost !== null
    ? purchaseSimulation.sip.profit - sipEstimatedCost
    : null
  const lumpSumNetReturn = purchaseSimulation && lumpSumNetProfit !== null && purchaseSimulation.lumpSum.totalInvested > 0
    ? lumpSumNetProfit / purchaseSimulation.lumpSum.totalInvested
    : null
  const sipNetReturn = purchaseSimulation && sipNetProfit !== null && purchaseSimulation.sip.totalInvested > 0
    ? sipNetProfit / purchaseSimulation.sip.totalInvested
    : null
  const hasVerifiedHoldings = holdingEvidence?.status === 'available'
  const holdingExposureDecision = buildHoldingExposureDecision(holdingEvidence, investorContext)
  const managerAttributionDecision = buildManagerAttributionDecision(fund, investorContext)
  const stressExperience = purchaseSimulation?.stressExperience || null
  const salesRuleHardGap = salesRuleGapEvidence?.gap || null
  const executionAmountGate = salesRuleGapEvidence?.executionAmountGate || null
  const salesRuleMissingItems = salesRuleHardGap?.missingItems || []
  const requiredMissingItems = (buyEvidence.missingItems || []).filter((item) => item.requiredBeforeBuy)
  const currentShareClassInfo = shareClassEvidence?.current || null
  const shareClassDecision: ShareClassDecision = (() => {
    const shareFunds = shareClassEvidence?.funds || []
    if (!shareFunds.length) {
      return {
        title: '份额选择待补证',
        recommendedCode: '',
        recommendedName: '',
        recommendedClass: '',
        confidence: 'low',
        formalChoiceReady: false,
        reasons: ['当前报告未取得同基金多份额样本，需先核对销售平台 A/C/I/H 份额列表。'],
        warnings: ['不能只看当前份额收益或名称后缀做研究决定。'],
      }
    }

    const classPriority = investorContext.horizon === 'lt1y' || investorContext.purchasePlan === 'sip'
      ? ['C', 'A', 'I', 'H', '未知']
      : ['A', 'I', 'C', 'H', '未知']
    const gateRank = (item: ShareClassEvidence['funds'][number]) => {
      if (item.executionAmountGate?.status === 'pass') return 0
      if (item.executionAmountGate?.status === 'unknown' || !item.executionAmountGate) return 1
      return 2
    }
    const rankedFunds = shareFunds
      .map((item) => ({
        ...item,
        shareClass: item.shareClass || '未知',
      }))
      .sort((left, right) => {
        const leftGateRank = gateRank(left)
        const rightGateRank = gateRank(right)
        if (leftGateRank !== rightGateRank) return leftGateRank - rightGateRank
        if (left.knownCost !== right.knownCost) return (left.knownCost ?? 999999) - (right.knownCost ?? 999999)
        const leftRank = classPriority.includes(left.shareClass || '') ? classPriority.indexOf(left.shareClass || '') : classPriority.length
        const rightRank = classPriority.includes(right.shareClass || '') ? classPriority.indexOf(right.shareClass || '') : classPriority.length
        if (leftRank !== rightRank) return leftRank - rightRank
        return String(left.windCode || '').localeCompare(String(right.windCode || ''))
      })
    const recommended = rankedFunds[0]
    const blockedShareClassCount = rankedFunds.filter((item) => item.executionAmountGate?.status === 'blocked').length
    const unknownShareClassCount = rankedFunds.filter((item) => item.executionAmountGate?.status === 'unknown' || !item.executionAmountGate).length
    const costMissingCount = rankedFunds.reduce((sum, item) => sum + (item.costMissingItems?.length || 0), 0)
    const formalChoiceReady = Boolean(
      currentShareClassInfo
      && recommended
      && recommended.executionAmountGate?.status === 'pass'
      && recommended.knownCost !== null
      && recommended.knownCost !== undefined
      && blockedShareClassCount === 0
      && unknownShareClassCount === 0
      && costMissingCount === 0,
    )
    const reasons = [
      investorContext.horizon === 'lt1y'
        ? '持有期为 1 年以内，优先核查短持成本、赎回费和销售服务费。'
        : investorContext.horizon === 'gt3y'
          ? '持有期为 3 年以上，优先核查长期总费率、申购费折扣和赎回持有期。'
          : '持有期为 1-3 年，需要同时比较申购费、销售服务费、赎回费和管理/托管费。',
      investorContext.purchasePlan === 'sip'
        ? '研究方式假设为定投，需重点核对定投起点、定投费率和 C 类销售服务费。'
        : '研究方式假设为一次性配置假设，需重点核对申购费折扣、限购和赎回持有期。',
      recommended?.knownCost != null
        ? `按计划金额 ${moneyText(recommended.executionAmountGate?.plannedAmount ?? plannedAmount)} 估算，${recommended.shareClass || '未知'} 类 ${recommended.windCode || '代码待补'} 已知成本为 ${moneyText(recommended.knownCost)}。`
        : recommended
        ? `按当前画像和持有期，先核查 ${recommended.shareClass || '未知'} 类 ${recommended.windCode || '代码待补'} 是否更合适。`
        : '当前没有可排序份额样本。',
      formalChoiceReady
        ? '金额门禁和份额成本证据已清零，可作为份额选择复核顺序进入人工确认。'
        : '份额金额门禁或成本证据未清零前，不输出正式推荐份额代码，只输出核查顺序。',
    ].filter(Boolean)
    return {
      title: formalChoiceReady ? '份额选择可复核' : currentShareClassInfo ? '暂定份额核查顺序' : '份额选择待补证',
      recommendedCode: formalChoiceReady ? recommended?.windCode || '' : '',
      recommendedName: formalChoiceReady ? recommended?.name || '' : '',
      recommendedClass: formalChoiceReady ? recommended?.shareClass || '' : '',
      confidence: formalChoiceReady ? 'medium' : 'low',
      formalChoiceReady,
      reasons,
      warnings: [
        !formalChoiceReady && recommended ? `暂不输出推荐代码；先核查 ${recommended.shareClass || '未知'} 类 ${recommended.windCode || '代码待补'} 的费用和金额门禁。` : '',
        blockedShareClassCount ? `${blockedShareClassCount} 个份额未通过当前计划金额门禁，不能作为正式推荐。` : '',
        unknownShareClassCount ? `${unknownShareClassCount} 个份额金额门禁待补，需先补起购/定投/限购。` : '',
        costMissingCount ? `仍有 ${costMissingCount} 项份额成本证据待补，结论只能作为核查顺序。` : '',
        `正式选择前仍必须补齐${salesRuleEvidenceCopy.formalFields}。`,
        currentShareClassInfo ? '同基金多份额必须先完成份额成本比较，再进入跨基金横评或研究清单。' : '当前份额样本不足，不能输出份额选择结论。',
      ].filter(Boolean),
    }
  })()
  const managerSummary = Array.isArray(fund.managers) && fund.managers.length
    ? fund.managers.map((manager) => {
      const tenure = manager.managementYears == null ? '任期待核' : `${Number(manager.managementYears).toFixed(1)}年`
      const since = manager.beginDate ? `任职起点 ${manager.beginDate}` : '任职起点待补'
      return `${manager.name || manager.managerId || '姓名待补'}（${tenure}，${since}）`
    }).join('；')
    : '经理明细待同步'
  const managerAttributionLines = [
    `- 经理归因判断：${managerAttributionDecision.label}`,
    `- 观察窗口：${managerAttributionDecision.attributionWindowYears} 年；覆盖率：${managerAttributionDecision.coverageRatio === null ? '待补' : `${managerAttributionDecision.coverageRatio}%`}`,
    ...managerAttributionDecision.reasons.map((item) => `- 判断依据：${item}`),
    ...managerAttributionDecision.warnings.map((item) => `- 归因风险：${item}`),
  ]

  const hardBlocks = [
    operationStatus?.status === 'blocked' ? operationStatus.reason || '存在退市、清算或终止信号' : '',
    drawdown !== null && drawdown > investorContext.maxDrawdownTolerance
      ? `最大回撤 ${percentText(-drawdown)} 超过${investorContext.profileLabel}预算 ${percentText(-investorContext.maxDrawdownTolerance)}`
      : '',
    totalAsset !== null && totalAsset < 2 ? '基金规模低于 2 亿，需先排除清盘和流动性风险' : '',
    salesRiskLevel !== null && salesRiskLevel > investorContext.maxSalesRiskLevel
      ? `销售风险等级 R${salesRiskLevel} 超过${investorContext.profileLabel}可接受等级 R${investorContext.maxSalesRiskLevel}`
      : '',
    investorContext.purchasePlan === 'sip' && supportsSip === false ? '销售规则显示不支持定投' : '',
    executionAmountGate?.status === 'blocked' ? executionAmountGate.detail : '',
    plannedAmount !== null && investorContext.purchasePlan === 'sip' && minSipAmount !== null && plannedAmount < minSipAmount
      ? `计划月扣款 ${moneyText(plannedAmount)} 低于销售平台定投起点 ${moneyText(minSipAmount)}`
      : '',
    plannedAmount !== null && investorContext.purchasePlan === 'lump_sum' && minPurchaseAmount !== null && plannedAmount < minPurchaseAmount
      ? `计划配置 ${moneyText(plannedAmount)} 低于销售平台起购金额 ${moneyText(minPurchaseAmount)}`
      : '',
    plannedAmount !== null && dailyLimitAmount !== null && dailyLimitAmount > 0 && plannedAmount > dailyLimitAmount
      ? `计划金额 ${moneyText(plannedAmount)} 超过销售平台限购金额 ${moneyText(dailyLimitAmount)}`
      : '',
    purchaseSimulation && investorContext.purchasePlan === 'lump_sum' && Math.abs(purchaseSimulation.lumpSum.maxDrawdown) > investorContext.maxDrawdownTolerance
      ? `持有体验回放最大回撤 ${percentText(purchaseSimulation.lumpSum.maxDrawdown)} 超过画像预算`
      : '',
    purchaseSimulation && investorContext.purchasePlan === 'sip' && Math.abs(purchaseSimulation.sip.maxAccountDrawdown) > investorContext.maxDrawdownTolerance
      ? `定投账户回撤 ${percentText(purchaseSimulation.sip.maxAccountDrawdown)} 超过画像预算`
      : '',
    stressExperience && stressExperience.recoveryDays === null && Math.abs(stressExperience.worstDrawdown) > investorContext.maxDrawdownTolerance * 0.9
      ? `持有压力体验显示最大回撤尚未回本，且接近${investorContext.profileLabel}预算`
      : '',
  ].filter(Boolean)

  const cautionFlags = [
    !operationStatus || operationStatus.status === 'unknown' ? '缺少销售端实时申购/赎回开放状态' : '',
    totalAsset === null ? '基金规模缺失，无法判断容量和清盘风险' : '',
    salesRiskLevel === null ? '销售平台风险等级待补，适当性匹配不完整' : '',
    minPurchaseAmount === null ? '最低申购金额待补' : '',
    investorContext.purchasePlan === 'sip' && minSipAmount === null ? '定投起点待补' : '',
    dailyLimitAmount === null ? '限购金额待补' : '',
    purchaseFeeRate === null ? '申购费率待补，费用后收益无法完整估算' : '',
    redemptionFeeRate === null ? '赎回费率待补，费用后收益无法完整估算' : '',
    !purchaseSimulation ? `净值回放未完成：${simulationError || '净值样本不足'}` : '',
    purchaseSimulation && purchaseSimulation.monthlyExperience.months < investorContext.minSampleMonths
      ? `${investorContext.horizonLabel}至少需要 ${investorContext.minSampleMonths} 个月回放，当前 ${purchaseSimulation.monthlyExperience.months} 个月`
      : '',
    !hasVerifiedHoldings ? `持仓明细待补：${holdingEvidence?.note || '未取得可验证持仓，暂不能解释行业/个股暴露'}` : '',
    ...managerAttributionDecision.warnings,
    currentShareClassInfo?.siblingCount ? `同基金多份额待比较：${currentShareClassInfo.baseName} 存在 ${currentShareClassInfo.siblingCount} 个份额样本` : '',
    ...salesRuleMissingItems.map((item) => `销售规则硬缺口：${item}`),
    ...requiredMissingItems.map((item) => item.label),
  ].filter(Boolean)
  const alternativeReadyFunds = (alternativeEvidence?.funds || [])
    .filter((item) => !item.salesRuleGap?.missingCount)
  const alternativeGapFunds = (alternativeEvidence?.funds || [])
    .filter((item) => item.salesRuleGap?.missingCount)
  const recheckTriggers = [
    salesRuleHardGap?.missingCount
      ? `销售规则硬缺口 ${salesRuleHardGap.missingCount} 项清零后，当前“先补证/不可生成正式报告”结论才允许重新评估。`
      : '',
    !hasCompleteTransactionFeeRates || salesServiceFeeRate === null
      ? `补齐${salesRuleEvidenceCopy.recheckFields}后，费用后收益和适当性可能改变。`
      : '',
    !purchaseSimulation ? '真实净值回放尚未完成，跑完回放后收益/回撤体验可能改变排序。' : '',
    purchaseSimulation && investorContext.purchasePlan === 'sip' && Math.abs(purchaseSimulation.sip.maxAccountDrawdown) > investorContext.maxDrawdownTolerance * 0.9
      ? '定投账户回撤接近画像预算，若回放区间延长或净值更新后回撤扩大，结论会转为更谨慎。'
      : '',
    purchaseSimulation && investorContext.purchasePlan === 'lump_sum' && Math.abs(purchaseSimulation.lumpSum.maxDrawdown) > investorContext.maxDrawdownTolerance * 0.9
      ? '一次性配置假设回撤接近画像预算，若回放区间延长或净值更新后回撤扩大，结论会转为更谨慎。'
      : '',
    stressExperience && stressExperience.longestUnderwaterDays > investorContext.minSampleMonths * 30
      ? '持有压力体验显示亏损等待时间较长；若计划持有期缩短或研究画像无法承受账面亏损，结论会下调。'
      : '',
    salesRiskLevel === null
      ? '销售平台风险等级补齐后，若高于当前画像承受等级，将直接阻断研究候选。'
      : '',
    currentShareClassInfo?.siblingCount
      ? `同基金 ${currentShareClassInfo.siblingCount} 个份额仍需完成 A/C/I/H 成本比较；若推荐份额不是当前份额，当前结论只代表当前份额的核查顺序。`
      : '',
    managerAttributionDecision.status !== 'covered'
      ? '经理归因覆盖率未达 100%；若上任后业绩/回撤与完整窗口表现差异明显，结论会转为更谨慎。'
      : '',
    alternativeReadyFunds.length > 0 && !salesRuleHardGap?.missingCount
      ? '同画像替代候选已可比较；若替代基金在费用后回放、回撤或证据完整度明显领先，单基金优先级会下调。'
      : '',
    ...holdingExposureDecision.reverseTriggers,
  ].filter(Boolean).slice(0, 8)

  const evidenceScore = [
    fund.nav !== null && fund.nav !== undefined,
    Boolean(fund.navDate),
    Boolean(fund.establishmentDate),
    annualReturn !== null,
    maxDrawdownValue !== null,
    totalAsset !== null,
    operationStatus?.status && operationStatus.status !== 'unknown',
    Boolean(purchaseSimulation),
    hasVerifiedHoldings,
    (buyEvidence.requiredMissingCount ?? 0) === 0,
  ].filter(Boolean).length
  const evidenceGrade = evidenceScore >= 8 && cautionFlags.length <= 2 ? 'A' : evidenceScore >= 6 ? 'B' : evidenceScore >= 4 ? 'C' : 'D'
  const level = hardBlocks.length ? 'blocked' : evidenceGrade === 'D' || cautionFlags.length >= 5 ? 'verify_first' : 'research_ready'
  const verdictLabel = level === 'blocked' ? '不进入研究复核候选' : level === 'verify_first' ? '先补证再比较' : '可进入研究复核候选'

  const reviewChecklist = [
    ...hardBlocks.map((item) => `暂停推进：${item}`),
    ...cautionFlags.slice(0, 8).map((item) => `补证：${item}`),
    salesRuleEvidenceCopy.reviewChecklist,
    currentShareClassInfo?.siblingCount ? '先比较同基金 A/C/I/H 等份额的申购费、销售服务费、赎回费和持有期，再进入跨基金横评' : '核对是否存在未进入样本的 A/C/I/H 等同基金份额',
    '对比至少 2 只同类型、同画像替代基金',
    `持仓暴露：${holdingExposureDecision.nextAction}`,
    `经理归因：${managerAttributionDecision.status === 'covered' ? '继续复核现任经理稳定性' : '先核上任前后业绩差异，不能把老业绩归因给现任经理'}`,
    stressExperience
      ? `持有压力体验：复核最长亏损等待 ${Math.round(stressExperience.longestUnderwaterDays)} 天、最差三个月 ${percentText(stressExperience.worstThreeMonthReturn?.returnRate ?? null)} 是否超出研究画像承受范围`
      : '持有压力体验：先完成真实净值回放，不能只凭长期收益或评分进入研究候选',
    '确认基金合同、最新季报和经理任期是否支持当前结论',
  ]
  const alternativeDecision: AlternativeDecision = (() => {
    if (salesRuleHardGap?.missingCount) {
      return {
        status: 'blocked_primary',
        title: '暂不比较收益，先补主基金规则',
        verdict: '主基金自身未过研究复核销售规则门禁',
        detail: `销售规则仍缺 ${salesRuleHardGap.missingCount} 项（${salesRuleMissingItems.slice(0, 8).join('、') || '销售平台关键字段待补'}）。在主基金硬缺口清零前，替代候选只能作为研究观察，不进入研究选择。`,
        primary: `主基金：${salesRuleHardGap.missingCount} 项硬缺口`,
        alternative: alternativeEvidence?.funds?.length
          ? `替代候选：已找到 ${alternativeEvidence.funds.length} 只，但横比需等主基金补证`
          : '替代候选：暂无可比样本',
        next: salesRuleHardGap.nextAction || salesRuleEvidenceCopy.primaryNextAction,
      }
    }
    if (alternativeReadyFunds.length) {
      const topAlternative = alternativeReadyFunds[0]
      return {
        status: 'compare_ready',
        title: '已有可比替代，不能只看单只基金',
        verdict: `优先比较 ${topAlternative.name || topAlternative.windCode || '最高分替代候选'}`,
        detail: `${topAlternative.name || topAlternative.windCode || '最高分替代候选'}（${topAlternative.windCode || '-'}）在当前画像下选基分 ${topAlternative.investorScore ?? '待补'}，销售规则未见硬缺口；建议先做同屏横评，再决定是否进入研究清单。`,
        primary: `主基金：${verdictLabel}，证据 ${evidenceGrade}`,
        alternative: `可比替代：${alternativeReadyFunds.length} 只，最高分 ${topAlternative.investorScore ?? '待补'}`,
        next: '打开横向比较，比较收益、回撤、成本、经理和门禁',
      }
    }
    if (alternativeGapFunds.length) {
      return {
        status: 'blocked_alternatives',
        title: '替代候选也被销售规则拦住',
        verdict: '先补替代候选规则，再做横向比较',
        detail: `当前找到 ${alternativeEvidence?.funds.length || 0} 只替代候选，其中 ${alternativeGapFunds.length} 只销售规则仍有硬缺口；不能把这些候选直接当作可研究替代。`,
        primary: `主基金：${verdictLabel}，证据 ${evidenceGrade}`,
        alternative: `待补替代：${alternativeGapFunds.slice(0, 3).map((item) => item.windCode || item.name || '代码待补').join('、')}`,
        next: '批量补替代候选销售规则，补齐后回到横向比较',
      }
    }
    return {
      status: 'no_alternatives',
      title: '暂缺可用替代结论',
      verdict: '不要直接下结论，先扩大候选范围',
      detail: '当前画像、持有期、研究方式假设和基金类型下，暂未形成可用于研究横比的替代样本。',
      primary: `主基金：${verdictLabel}，证据 ${evidenceGrade}`,
      alternative: '替代候选：暂无可比对象',
      next: '回到完整选基页放宽基金类型、证据等级或分数阈值',
    }
  })()
  const alternativeWinLossLines = buildAlternativeWinLossLines({
    fund,
    annualReturn,
    maxDrawdownValue,
    feeEstimate,
    hasCompleteTransactionFeeRates,
    salesRuleHardGap,
    evidenceGrade,
    alternativeEvidence,
  })

  const sources = [
    'backend.tushare.fund_basic',
    'backend.tushare.fund_nav',
    hasVerifiedHoldings ? holdingEvidence?.source || 'backend.tushare.fund_holding.filtered' : 'backend.tushare.fund_holding.filtered（待补或不可用）',
    fund.salesRule ? 'local.sales_rules' : 'local.sales_rules（待补）',
    salesRuleGapEvidence?.status === 'available' ? salesRuleGapEvidence.source : 'explicit_codes_plus_local_sales_rules（待补）',
    Array.isArray(fund.managers) && fund.managers.length ? 'backend.tushare.fund_manager' : 'backend.tushare.fund_manager（待补）',
    alternativeEvidence?.source
      ? `${alternativeEvidence.source}${alternativeEvidence.status === 'available' ? '' : '（替代候选待补）'}`
      : 'api.investor_selection（替代候选待补）',
    shareClassEvidence?.source
      ? `${shareClassEvidence.source}${shareClassEvidence.status === 'available' ? '' : '（同基金份额待补）'}`
      : 'api.funds.keyword_share_class（同基金份额待补）',
  ]
  const holdingLines = hasVerifiedHoldings
    ? [
        `- 持仓暴露研究判断：${holdingExposureDecision.label}；暴露分 ${holdingExposureDecision.score}`,
        `- 暴露风险：${holdingExposureDecision.primaryRisk}`,
        `- 研究动作：${holdingExposureDecision.nextAction}`,
        ...holdingExposureDecision.reasons.map((item) => `- 判断依据：${item}`),
        ...holdingExposureDecision.reverseTriggers.map((item) => `- 结论反转条件：${item}`),
        `- 持仓季度：${holdingEvidence?.quarter || '待补'}；前十大合计权重：${percentText(holdingEvidence?.totalWeight ?? null)}`,
        `- 行业暴露：${(holdingEvidence?.industryBuckets || []).slice(0, 5).map((bucket) => `${bucket.industry} ${percentText(bucket.weight)}`).join('；') || '行业待补'}`,
        `- 重仓示例：${(holdingEvidence?.holdings || []).slice(0, 5).map((holding) => `${holding.stockName || holding.stockCode || '名称待补'} ${percentText(holding.weight ?? null)}`).join('；') || '持仓明细待补'}`,
        `- 持仓备注：${holdingEvidence?.note || '研究复核仍需以最新季报/销售平台披露为准。'}`,
      ]
    : [
        `- 持仓暴露研究判断：${holdingExposureDecision.label}；暴露分 ${holdingExposureDecision.score}`,
        `- 研究动作：${holdingExposureDecision.nextAction}`,
        ...holdingExposureDecision.reverseTriggers.map((item) => `- 结论反转条件：${item}`),
        `- 状态：持仓待补；${holdingEvidence?.note || '未取得可验证持仓，暂不做行业/个股暴露判断。'}`,
        `- 已检查季度：${holdingEvidence?.checkedQuarters?.join(' / ') || '待补'}`,
        `- 已拦截疑似样例季度：${holdingEvidence?.rejectedMockLikeQuarters?.join(' / ') || '无'}`,
      ]
  const alternativeLines = alternativeEvidence?.status === 'available' && alternativeEvidence.funds.length
    ? [
        `- 搜索口径：${alternativeEvidence.note}`,
        `- 搜索路径：${alternativeEvidence.attempts.join(' → ') || '待补'}`,
        `- 替代横评矩阵：主基金 ${fund.name || fund.windCode}；替代候选按研究分、收益差、回撤差、证据等级和销售规则硬缺口排序复核。`,
        ...alternativeEvidence.funds.slice(0, 4).map((item) => {
          const warnings = (item.purchaseGate?.cautionFlags || item.warnings || []).slice(0, 2).join('；') || '暂无额外提示'
          const salesGap = item.salesRuleGap?.missingCount
            ? `；销售规则缺 ${item.salesRuleGap.missingCount} 项（${item.salesRuleGap.missingItems.slice(0, 4).join('、')}）`
            : '；销售规则未见硬缺口'
          const scoreGap = item.investorScore == null ? '待补' : `${item.investorScore >= 70 ? '较强' : item.investorScore >= 55 ? '中等' : '偏弱'}（${item.investorScore}）`
          const candidateAnnualReturn = item.annualReturn ?? null
          const candidateMaxDrawdown = item.maxDrawdown ?? null
          const returnGap = candidateAnnualReturn === null || annualReturn === null
            ? '收益差待补'
            : `收益差 ${(Number(candidateAnnualReturn - annualReturn) * 100).toFixed(2)}%`
          const drawdownGap = candidateMaxDrawdown === null || maxDrawdownValue === null
            ? '回撤差待补'
            : `回撤差 ${(Math.abs(candidateMaxDrawdown) - Math.abs(maxDrawdownValue)) * 100 >= 0 ? '+' : ''}${((Math.abs(candidateMaxDrawdown) - Math.abs(maxDrawdownValue)) * 100).toFixed(2)}%`
          return `- ${item.name || item.windCode}（${item.windCode || '-'}）：选基分 ${scoreGap}；${returnGap}；${drawdownGap}；门禁 ${item.purchaseGate?.label || '待核'}；1Y收益 ${percentText(item.annualReturn)}；最大回撤 ${percentText(item.maxDrawdown)}；适当性 ${item.riskSuitability?.label || '风险等级待补'}${salesGap}；边界 ${warnings}`
        }),
      ]
    : [
        `- 状态：替代候选待补；${alternativeEvidence?.note || '当前报告未取得同画像替代候选，不能只依据单基金结论推进。'}`,
        `- 已尝试路径：${alternativeEvidence?.attempts?.join(' → ') || '待补'}`,
        ...((alternativeEvidence?.funds || []).slice(0, 4).map((item) => {
          const gap = item.salesRuleGap
          return `- 待补候选 ${item.name || item.windCode}（${item.windCode || '-'}）：${gap?.missingCount ? `销售规则缺 ${gap.missingCount} 项（${gap.missingItems.slice(0, 4).join('、')}）` : '销售规则状态待核'}；补齐前不作为可比替代结论。`
        })),
      ]
  const alternativeWinLossMarkdownLines = alternativeWinLossLines.length
    ? [
        '',
        '### 8.1 横评胜负线',
        ...alternativeWinLossLines.flatMap((line) => [
          `- 对 ${line.challengerName}（${line.challengerCode || '代码待补'}）：${line.label}，${line.passedChecks}/${line.totalChecks} 关；${line.summary}`,
          ...line.thresholds.map((threshold) => `  - ${threshold.label}：${threshold.passed ? '过线' : '待证明'}；${threshold.detail}`),
        ]),
      ]
    : [
        '',
        '### 8.1 横评胜负线',
        '- 当前缺少可比替代样本，暂不能形成胜负线；不能只凭单基金评分进入研究候选。',
      ]
  const shareClassLines = shareClassEvidence?.status === 'available' && currentShareClassInfo
    ? [
        `- 当前份额：${currentShareClassInfo.baseName} ${currentShareClassInfo.classType}类；同基金 ${currentShareClassInfo.siblingCount} 份额`,
        `- 兄弟份额：${currentShareClassInfo.siblingCodes.length ? currentShareClassInfo.siblingCodes.join('、') : '待补'}`,
        `- 份额选择建议：${shareClassDecision.recommendedCode ? `${shareClassDecision.title}：${shareClassDecision.recommendedClass}类 ${shareClassDecision.recommendedCode}（${shareClassDecision.recommendedName || '名称待补'}）` : shareClassDecision.title}`,
        ...shareClassEvidence.funds.map((item) => `- 份额金额门禁：${item.shareClass || '未知'}类 ${item.windCode || '代码待补'}：${item.executionAmountGate?.label || '金额门槛待补'}；计划金额成本 ${moneyText(item.knownCost)}；待补 ${item.costMissingItems?.length ? item.costMissingItems.slice(0, 4).join('、') : '无'}`),
        ...shareClassDecision.reasons.map((item) => `- 建议依据：${item}`),
        ...shareClassDecision.warnings.map((item) => `- 份额门禁：${item}`),
        `- 判断边界：${currentShareClassInfo.hint}`,
        ...currentShareClassInfo.warnings.map((item) => `- 风险提示：${item}`),
      ]
    : [
        `- 状态：${shareClassEvidence?.note || '当前未发现同基金 A/C/I/H 等多份额样本；仍需研究复核核对基金合同和销售平台份额列表。'}`,
        `- 份额选择建议：${shareClassDecision.title}`,
        ...shareClassDecision.reasons.map((item) => `- 建议依据：${item}`),
      ]
  const stressExperienceLines = stressExperience
    ? [
        `- 持有压力体验：${stressExperience.label}；压力分 ${stressExperience.stressScore}`,
        `- 最长亏损等待：${Math.round(stressExperience.longestUnderwaterDays)} 天；最大回撤低点：${stressExperience.troughDate}，${percentText(stressExperience.worstDrawdown)}`,
        `- 最大回撤回本：${stressExperience.recoveryDays === null ? '回放期未回本' : `${stressExperience.recoveryDays} 天`}`,
        `- 最长连跌：${stressExperience.longestLosingStreakMonths} 个月；最差三个月：${stressExperience.worstThreeMonthReturn ? `${stressExperience.worstThreeMonthReturn.startMonth}~${stressExperience.worstThreeMonthReturn.endMonth} ${percentText(stressExperience.worstThreeMonthReturn.returnRate)}` : '待补'}`,
        `- 研究解释：${stressExperience.interpretation}`,
        '- 使用边界：若最长亏损等待超过计划持有期、最差三个月超出心理承受，不能只凭长期收益或评分进入研究候选。',
      ]
    : [
        `- 持有压力体验：待补；${simulationError || '真实净值回放未完成'}`,
        '- 使用边界：压力体验缺失时，不能只凭长期收益或评分进入研究候选。',
      ]
  const reportMethodology = buildReportMethodologySections(fund, holdingEvidence, shareClassEvidence)
  const methodologySectionLines = reportMethodology.methodologySectionLines

  const markdownLines = [
    `# ${fund.name || fund.windCode}（${fund.windCode || fund.id}）研究复核报告`,
    '',
    `生成时间：${generatedAt}`,
    `研究画像：${investorContext.profileLabel}；持有期：${investorContext.horizonLabel}；研究方式假设：${investorContext.purchasePlanLabel}`,
    '',
    '## 1. 核查结论',
    `- 结论：${verdictLabel}`,
    `- 证据等级：${evidenceGrade}`,
    `- 销售规则完整度：${buyEvidence.completenessScore ?? 0}；研究复核必补：${buyEvidence.requiredMissingCount ?? 0} 项`,
    `- 主要原因：${hardBlocks[0] || cautionFlags[0] || buyEvidence.conclusion || '当前证据未发现硬性阻断，但研究复核仍需复核销售平台实时状态。'}`,
    `- 什么情况下结论会改变：${recheckTriggers.length ? recheckTriggers.join('；') : '当前没有明显反转触发器；但正式购研究复核仍需复核销售平台实时规则和最新净值。'}`,
    '',
    '## 2. 方法论模板与章节重点',
    ...methodologySectionLines,
    '',
    '## 3. 核心指标',
    `- 近一年收益：${percentText(annualReturn)}`,
    `- 最大回撤：${percentText(maxDrawdownValue)}`,
    `- 年化波动：${percentText(volatility)}`,
    `- 基金规模：${totalAsset === null ? '待补' : `${totalAsset.toFixed(2)} 亿`}`,
    `- 净值日期：${fund.navDate || '待补'}`,
    `- 申购状态：${operationStatus?.label || '待补'}`,
    `- 基金经理：${managerSummary}`,
    '',
    '## 4. 销售与适当性',
    `- 销售风险等级：${salesRiskLevel === null ? '待补' : `R${salesRiskLevel}`}；当前画像最高接受 R${investorContext.maxSalesRiskLevel}`,
    `- R1-R5 来源背书：${riskLevelSourcePolicy.sourceBacked ? '已通过' : '未通过'}；30天来源窗口：${riskLevelSourcePolicy.sourceFresh ? '来源日期在 30 天内' : '来源日期缺失、过期或未来日期'}；来源：${riskLevelSourcePolicy.platform || '待补'} / ${riskLevelSourcePolicy.sourceUpdatedAt || '待补'}`,
    `- 销售风险等级（R1-R5 30天来源背书）：${riskLevelSourcePolicy.sourceBacked ? '销售平台/基金合同来源已背书，仍需研究复核实时复核' : '缺失、无来源、来源过期或来源被排除，正式路径硬阻断'}`,
    '- Tushare fund_basic 不能作为 R1-R5 风险等级来源；只允许作为基金基础档案辅助字段。',
    `- 计划金额执行门禁：${executionAmountGate ? `${executionAmountGate.label}；${executionAmountGate.detail}` : plannedAmount === null ? '真实净值回放未完成，暂不能验算计划金额。' : '本次报告未取得销售规则金额门禁结果。'}`,
    `- 最低申购：${moneyText(minPurchaseAmount)}；定投起点：${moneyText(minSipAmount)}；限购：${moneyText(dailyLimitAmount)}`,
    `- 销售规则硬缺口：${salesRuleHardGap ? `缺 ${salesRuleHardGap.missingCount} 项（${salesRuleMissingItems.slice(0, 8).join('、')}）` : '当前未检测到硬缺口，仍需复核销售平台实时状态'}`,
    `- 缺口优先级：${salesRuleHardGap?.priority || '无'}；下一步：${salesRuleHardGap?.nextAction || '研究复核实时申赎、费率、限购和风险等级'}`,
    `- 研究画像适配依据：${[investorContext.profileNote, investorContext.horizonNote, investorContext.purchasePlanNote].join('；')}`,
    '',
    '## 4.1 同基金份额比较',
    ...shareClassLines,
    '',
    '## 5. 持有体验回放',
    purchaseSimulation
      ? `- 一次性配置假设：收益 ${percentText(purchaseSimulation.lumpSum.returnRate)}，最大回撤 ${percentText(purchaseSimulation.lumpSum.maxDrawdown)}，期末 ${moneyText(purchaseSimulation.lumpSum.endingValue)}`
      : `- 一次性配置假设：${simulationError || '待测算'}`,
    purchaseSimulation
      ? `- 定投：收益 ${percentText(purchaseSimulation.sip.returnRate)}，账户回撤 ${percentText(purchaseSimulation.sip.maxAccountDrawdown)}，扣款 ${purchaseSimulation.sip.contributionCount} 次`
      : '- 定投：待测算',
    purchaseSimulation
      ? `- 样本：${purchaseSimulation.period.observations} 条净值，${purchaseSimulation.period.startDate} 至 ${purchaseSimulation.period.endDate}`
      : '- 样本：待补',
    purchaseSimulation
      ? `- 费用后粗估：一次性 ${percentText(lumpSumNetReturn)}（估算成本 ${moneyText(lumpSumEstimatedCost)}）；定投 ${percentText(sipNetReturn)}（估算成本 ${moneyText(sipEstimatedCost)}）`
      : '- 费用后粗估：待测算',
    `- 费用假设：申购费 ${feeRateText(purchaseFeeRate)}；赎回费 ${feeRateText(redemptionFeeRate)}${redemptionRule?.label ? `（${redemptionRule.label}）` : ''}；销售服务费 ${feeRateText(salesServiceFeeRate)}。真实费用需按销售平台折扣、持有期和基金合同复核。`,
    `- 赎回费匹配口径：按计划持有期约 ${redemptionHoldingDays} 天匹配，不默认使用第一条赎回规则。`,
    ...stressExperienceLines,
    '',
    '## 6. 持仓与行业暴露',
    ...holdingLines,
    '',
    '## 7. 经理归因覆盖',
    ...managerAttributionLines,
    '',
    '## 8. 同画像替代候选',
    `- 研究替代结论：${alternativeDecision.title}`,
    `- 替代结论：${alternativeDecision.verdict}`,
    `- 结论说明：${alternativeDecision.detail}`,
    `- 主基金状态：${alternativeDecision.primary}`,
    `- 替代候选状态：${alternativeDecision.alternative}`,
    `- 下一步：${alternativeDecision.next}`,
    ...alternativeLines,
    ...alternativeWinLossMarkdownLines,
    '',
    '## 9. 研究复核必须复核',
    ...reviewChecklist.map((item) => `- ${item}`),
    '',
    '## 10. 数据来源',
    ...sources.map((item) => `- ${item}`),
    '',
    '声明：本报告仅用于基金研究和研究复核，不构成申赎操作指令或收益承诺。',
  ]

  return {
    generatedAt,
    fund: {
      id: fund.id,
      windCode: fund.windCode,
      name: fund.name,
      type: fund.type,
    },
    investorContext,
    plannedAmount,
    verdict: {
      level,
      label: verdictLabel,
      evidenceGrade,
      hardBlocks,
      cautionFlags,
      recheckTriggers,
    },
    metrics: {
      annualReturn,
      maxDrawdown: maxDrawdownValue,
      volatility,
      totalAsset,
      navDate: fund.navDate,
      operationLabel: operationStatus?.label || null,
      managerSummary,
    },
    sales: {
      salesRiskLevel,
      riskLevelSourcePolicy,
      minPurchaseAmount,
      minSipAmount,
      dailyLimitAmount,
      buyEvidence,
    },
    riskLevelSourcePolicy,
    purchaseSimulation,
    feeEstimate: feeEstimate ? {
      ...feeEstimate,
      lumpSumEstimatedCost,
      sipEstimatedCost,
      lumpSumNetProfit,
      sipNetProfit,
      lumpSumNetReturn,
      sipNetReturn,
    } : null,
    holdingEvidence: holdingEvidence || null,
    holdingExposureDecision,
    managerAttributionDecision,
    salesRuleGapEvidence: salesRuleGapEvidence || null,
    alternativeEvidence: alternativeEvidence || null,
    alternativeWinLossLines,
    shareClassEvidence: shareClassEvidence || null,
    shareClassDecision,
    methodology: reportMethodology,
    alternativeDecision,
    reviewChecklist,
    sources,
    markdown: markdownLines.join('\n'),
  }
}
