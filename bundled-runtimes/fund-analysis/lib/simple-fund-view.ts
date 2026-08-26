import type { CamelFund } from '@/lib/backend-api'

type UnknownRecord = Record<string, unknown>

export type SimpleFund = CamelFund & {
  managers?: Array<UnknownRecord>
  researchProfile?: UnknownRecord | null
  styleProfile?: UnknownRecord | null
  fundEvaluation?: UnknownRecord | null
  rollingMetrics?: UnknownRecord
  dataQuality?: UnknownRecord | null
  professionalScoring?: UnknownRecord | null
  recommendationEvidence?: UnknownRecord | null
}

export function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {}
}

export function numberValue(...values: unknown[]) {
  for (const value of values) {
    if (value == null || value === '') continue
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

export function textValue(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
    if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  }
  return ''
}

export function windowMetrics(fund: SimpleFund, window: string) {
  return asRecord(asRecord(fund.rollingMetrics)[window])
}

export function returnMetric(fund: SimpleFund, window = '1y') {
  const performance = asRecord(fund.performanceData)
  const rolling = windowMetrics(fund, window)
  const periodKey = `return_${window}`
  return numberValue(
    rolling.total_return,
    performance[periodKey],
    window === '1y' ? performance.total_return : null,
  )
}

export function peerReturnMetric(fund: SimpleFund, window: string) {
  const metric = asRecord(asRecord(fund.peerReturnMetrics)[window])
  return {
    value: numberValue(metric.value),
    percentile: numberValue(metric.percentile),
    rank: numberValue(metric.rank),
    peerCount: numberValue(metric.peerCount, metric.peer_count),
  }
}

export function drawdownMetric(fund: SimpleFund, window = '1y') {
  const risk = asRecord(fund.riskMetrics)
  const performance = asRecord(fund.performanceData)
  const rolling = windowMetrics(fund, window)
  return numberValue(
    rolling.max_drawdown,
    risk[`max_drawdown_${window}`],
    risk.max_drawdown,
    performance.max_drawdown,
  )
}

export function sharpeMetric(fund: SimpleFund, window = '1y') {
  const risk = asRecord(fund.riskMetrics)
  const performance = asRecord(fund.performanceData)
  const rolling = windowMetrics(fund, window)
  return numberValue(rolling.sharpe_ratio, risk.sharpe_ratio, performance.sharpe_ratio)
}

export function styleLabel(fund: SimpleFund) {
  const projected = asRecord(fund.styleProfile)
  if (textValue(projected.primaryLabel, projected.primary_label)) {
    return textValue(projected.primaryLabel, projected.primary_label)
  }
  if (Object.keys(projected).length) return '风格待确认'
  const profile = asRecord(fund.researchProfile)
  const suggestions = Array.isArray(profile.memoStyleSuggestions)
    ? profile.memoStyleSuggestions
    : Array.isArray(profile.memo_style_suggestions) ? profile.memo_style_suggestions : []
  const firstSuggestion = suggestions.length ? asRecord(suggestions[0]) : {}
  const derived = Array.isArray(profile.derivedStyleEvidence)
    ? profile.derivedStyleEvidence
    : Array.isArray(profile.derived_style_evidence) ? profile.derived_style_evidence : []
  const firstDerived = derived.length ? asRecord(derived[0]) : {}
  return textValue(profile.styleLabel, profile.style_label, firstSuggestion.value, firstDerived.value) || '风格待确认'
}

export function styleLabelStatus(fund: SimpleFund) {
  const projected = asRecord(fund.styleProfile)
  if (Object.keys(projected).length) {
    return textValue(projected.status) || 'unavailable'
  }
  const profile = asRecord(fund.researchProfile)
  if (textValue(profile.styleLabel, profile.style_label)) return 'confirmed'
  const suggestions = Array.isArray(profile.memoStyleSuggestions)
    ? profile.memoStyleSuggestions
    : Array.isArray(profile.memo_style_suggestions) ? profile.memo_style_suggestions : []
  if (suggestions.length) {
    return suggestions.some((item) => textValue(asRecord(item).status) === 'confirmed')
      ? 'confirmed'
      : 'llm_suggested'
  }
  const derived = Array.isArray(profile.derivedStyleEvidence)
    ? profile.derivedStyleEvidence
    : Array.isArray(profile.derived_style_evidence) ? profile.derived_style_evidence : []
  return derived.length ? 'derived' : 'unavailable'
}

export function bondHoldingEvidence(fund: SimpleFund) {
  const projected = asRecord(fund.styleProfile)
  const profile = asRecord(projected.bondHoldingStyle ?? projected.bond_holding_style)
  const primary = asRecord(projected.primaryEvidence ?? projected.primary_evidence)
  const periodCount = numberValue(
    profile.periodCount,
    profile.period_count,
    primary.periodCount,
    primary.period_count,
  )
  const source = textValue(
    profile.dataSource,
    profile.data_source,
    primary.dataSource,
    primary.data_source,
  )
  return {
    periodCount,
    source: source.includes('eastmoney') ? '东方财富公开持仓' : source,
    caveat: textValue(primary.caveat),
    available: periodCount != null && periodCount > 0,
  }
}

export function fofHoldingEvidence(fund: SimpleFund) {
  const projected = asRecord(fund.styleProfile)
  const profile = asRecord(projected.fofHoldingStyle ?? projected.fof_holding_style)
  const reportDate = textValue(profile.reportDate, profile.report_date)
  const disclosedFundCount = numberValue(profile.disclosedFundCount, profile.disclosed_fund_count)
  const disclosedNavRatio = numberValue(profile.disclosedNavRatio, profile.disclosed_nav_ratio)
  const top5NavRatio = numberValue(profile.top5NavRatio, profile.top5_nav_ratio)
  return {
    reportDate,
    disclosedFundCount,
    disclosedNavRatio,
    top5NavRatio,
    available: Boolean(reportDate && disclosedFundCount != null && disclosedFundCount > 0),
  }
}

const styleAliases: Record<string, string[]> = {
  '大盘成长': ['大盘成长', 'large growth', 'large_growth'],
  '成长': ['成长', 'growth'],
  '价值': ['价值', 'value'],
  '均衡': ['均衡', '平衡', '混合', 'blend', 'balanced'],
  '质量': ['质量', '品质', 'quality'],
  '红利': ['红利', '股息', 'dividend'],
  '大盘': ['大盘', 'large cap', 'large_cap'],
  '中盘': ['中盘', 'mid cap', 'mid_cap'],
  '小盘': ['小盘', 'small cap', 'small_cap', 'small'],
  '中小盘': ['中小盘', 'mid small', 'mid_small'],
  '宽基': ['宽基', 'broad market', 'broad_market'],
  '行业主题': ['行业', '主题', 'sector', 'thematic'],
  '低波稳健': ['低波', '稳健', 'low volatility', 'low_volatility', 'defensive'],
  '指数增强': ['指数增强', '增强指数', 'enhanced index'],
  '固收+': ['固收+', '固收加', 'fixed income plus'],
  '高等级信用': ['高等级信用', 'high grade credit'],
}

function normalizedStyleText(value: string) {
  return value.trim().toLowerCase().replaceAll('型', '').replace(/[\s_-]+/gu, ' ')
}

export function matchesStyleLabel(fund: SimpleFund, selectedStyle: string) {
  if (!selectedStyle) return true
  const target = normalizedStyleText(selectedStyle)
  const aliases = styleAliases[selectedStyle] || [selectedStyle]
  const profileTags = asRecord(fund.researchProfile).strategyTags
  const profile = asRecord(fund.researchProfile)
  const projected = asRecord(fund.styleProfile)
  const projectedEvidence = Array.isArray(projected.labelEvidence)
    ? projected.labelEvidence
    : Array.isArray(projected.label_evidence) ? projected.label_evidence : []
  const memoSuggestions = Array.isArray(profile.memoStyleSuggestions)
    ? profile.memoStyleSuggestions
    : Array.isArray(profile.memo_style_suggestions) ? profile.memo_style_suggestions : []
  const derivedStyles = Array.isArray(profile.derivedStyleEvidence)
    ? profile.derivedStyleEvidence
    : Array.isArray(profile.derived_style_evidence) ? profile.derived_style_evidence : []
  const tags = [
    styleLabel(fund),
    peerGroup(fund),
    fund.type,
    ...(Array.isArray(profileTags) ? profileTags : []),
    ...memoSuggestions.map((item) => textValue(asRecord(item).value)),
    ...derivedStyles.map((item) => textValue(asRecord(item).value)),
    ...projectedEvidence.map((item) => textValue(asRecord(item).value)),
  ].map((value) => normalizedStyleText(String(value || ''))).join(' ')

  if (aliases.some((alias) => tags.includes(normalizedStyleText(alias)))) return true
  if (target === '低波稳健') {
    const drawdown = drawdownMetric(fund)
    return drawdown != null && Math.abs(drawdown) <= 0.12
  }
  return false
}

export function peerGroup(fund: SimpleFund) {
  const profile = asRecord(fund.researchProfile)
  return textValue(profile.peerGroup, profile.peer_group, fund.type) || '类别待确认'
}

export function professionalPeerGroup(fund: SimpleFund) {
  const profile = asRecord(fund.researchProfile)
  return textValue(profile.peerGroup, profile.peer_group)
}

export function professionalPeerGroupId(fund: SimpleFund) {
  const profile = asRecord(fund.researchProfile)
  return textValue(profile.peerGroupId, profile.peer_group_id, profile.peerGroupKey, profile.peer_group_key)
}

export function managerName(fund: SimpleFund) {
  const managers = Array.isArray(fund.managers) ? fund.managers : []
  const first = managers.length ? asRecord(managers[0]) : {}
  return textValue(first.name) || '经理待补充'
}

export function managerYears(fund: SimpleFund) {
  const managers = Array.isArray(fund.managers) ? fund.managers : []
  const first = managers.length ? asRecord(managers[0]) : {}
  return numberValue(first.managementYears, first.management_years)
}

export function evidenceCoverage(fund: SimpleFund) {
  const direct = numberValue(fund.evidenceCoverageScore)
  if (direct != null) return direct > 1 ? Math.min(100, direct) : Math.min(100, direct * 100)

  let complete = 0
  const checks = [fund.nav, returnMetric(fund), drawdownMetric(fund), fund.totalAsset, styleLabel(fund) !== '风格待确认']
  for (const check of checks) {
    if (check !== null && check !== undefined && check !== false) complete += 1
  }
  return complete * 20
}

export function formatPercent(value: number | null, digits = 1) {
  if (value == null) return '—'
  const normalized = value * 100
  return `${normalized.toFixed(digits)}%`
}

export function formatAsset(value: number | null) {
  if (value == null) return '—'
  return `${value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 亿`
}

export function professionalFundScore(fund: SimpleFund) {
  const scoring = asRecord(fund.professionalScoring)
  const status = textValue(scoring.status)
  const qualityStatus = textValue(asRecord(scoring.data_quality).status, asRecord(fund.dataQuality).status)
  if (status === 'insufficient_evidence' || qualityStatus === 'insufficient') return null
  return numberValue(scoring.overall_score, scoring.overallScore)
}

export function professionalScoreStatus(fund: SimpleFund) {
  return textValue(asRecord(fund.professionalScoring).status) || 'unavailable'
}

const scoreDimensionLabels: Record<string, string> = {
  return: '收益能力',
  risk: '风险控制',
  risk_adjusted: '风险调整后收益',
  consistency: '表现稳定性',
  manager_tenure: '经理任期',
  data_quality: '数据质量',
  tracking: '跟踪能力',
  excess_return: '超额收益',
  liquidity: '流动性',
  cost: '费率',
  scale: '基金规模',
}

export function professionalScoreEvidence(fund: SimpleFund) {
  const scoring = asRecord(fund.professionalScoring)
  const status = textValue(scoring.status) || 'unavailable'
  const dimensions = asRecord(scoring.dimension_scores ?? scoring.dimensionScores)
  const dimensionEntries = Object.entries(dimensions)
    .map(([key, value]) => ({ key, value: asRecord(value) }))
  const configuredWeight = dimensionEntries.reduce(
    (total, item) => total + (numberValue(item.value.weight) || 0),
    0,
  )
  const coveredWeight = dimensionEntries.reduce(
    (total, item) => total + (item.value.included_in_score === true || item.value.includedInScore === true
      ? numberValue(item.value.weight) || 0
      : 0),
    0,
  )
  const missingDimensions = dimensionEntries
    .filter((item) => item.value.included_in_score === false || item.value.includedInScore === false)
    .map((item) => scoreDimensionLabels[item.key] || item.key)
  const dataQuality = asRecord(scoring.data_quality ?? scoring.dataQuality)

  return {
    status,
    label: status === 'ok' || status === 'complete'
      ? '完整评分'
      : status === 'partial'
        ? '部分证据评分'
        : '评分证据待补',
    coveragePercent: configuredWeight > 0
      ? Math.round(Math.min(1, coveredWeight / configuredWeight) * 100)
      : null,
    missingDimensions,
    dataQualityScore: numberValue(dataQuality.score),
  }
}

export function professionalScorePercentile(fund: SimpleFund) {
  const peerPercentiles = asRecord(fund.peerPercentiles)
  const metrics = asRecord(peerPercentiles.metrics)
  const professional = asRecord(metrics.professional_score)
  return numberValue(professional.percentile)
}

export function professionalScorePeerPosition(fund: SimpleFund) {
  const peerPercentiles = asRecord(fund.peerPercentiles)
  const metrics = asRecord(peerPercentiles.metrics)
  const professional = asRecord(metrics.professional_score)
  return {
    percentile: numberValue(professional.percentile),
    rank: numberValue(professional.rank),
    peerCount: numberValue(professional.peer_count, professional.peerCount),
  }
}

export function baseFeeRate(fund: SimpleFund) {
  const managementFee = numberValue(fund.managementFee)
  const custodianFee = numberValue(fund.custodianFee)
  if (managementFee == null && custodianFee == null) return null
  return (managementFee || 0) + (custodianFee || 0)
}

export function recommendationEvidence(fund: SimpleFund) {
  const evidence = asRecord(fund.recommendationEvidence)
  const managerTenure = asRecord(evidence.managerTenure ?? evidence.manager_tenure)
  const multiPeriod = asRecord(evidence.multiPeriod ?? evidence.multi_period)
  const alternatives = Array.isArray(evidence.alternatives)
    ? evidence.alternatives.map((item) => asRecord(item)).filter((item) => textValue(item.windCode, item.wind_code))
    : []
  return {
    reasons: Array.isArray(evidence.reasons) ? evidence.reasons.map(String).filter(Boolean) : [],
    risks: Array.isArray(evidence.risks) ? evidence.risks.map(String).filter(Boolean) : [],
    dataAsOf: textValue(evidence.dataAsOf, evidence.data_as_of),
    methodologyVersion: textValue(evidence.methodologyVersion, evidence.methodology_version),
    multiPeriod: {
      status: textValue(multiPeriod.status) || 'short_term_only',
      return6m: numberValue(multiPeriod.return6m, multiPeriod.return_6m),
      return1y: numberValue(multiPeriod.return1y, multiPeriod.return_1y),
      annualizedReturn1y: numberValue(multiPeriod.annualizedReturn1y, multiPeriod.annualized_return_1y),
      annualizedReturn3y: numberValue(multiPeriod.annualizedReturn3y, multiPeriod.annualized_return_3y),
      maxDrawdown1y: numberValue(multiPeriod.maxDrawdown1y, multiPeriod.max_drawdown_1y),
      maxDrawdown3y: numberValue(multiPeriod.maxDrawdown3y, multiPeriod.max_drawdown_3y),
      sharpeRatio3y: numberValue(multiPeriod.sharpeRatio3y, multiPeriod.sharpe_ratio_3y),
      annualizedReturnGap: numberValue(multiPeriod.annualizedReturnGap, multiPeriod.annualized_return_gap),
      consistencyStatus: textValue(multiPeriod.consistencyStatus, multiPeriod.consistency_status),
      consistencyLabel: textValue(multiPeriod.consistencyLabel, multiPeriod.consistency_label),
      usedInScore: Boolean(multiPeriod.usedInScore ?? multiPeriod.used_in_score),
      dataAsOf: textValue(multiPeriod.dataAsOf, multiPeriod.data_as_of),
    },
    managerTenure: {
      status: textValue(managerTenure.status) || 'unavailable',
      coverageStatus: textValue(managerTenure.coverageStatus, managerTenure.coverage_status),
      coverageRatio: numberValue(managerTenure.coverageRatio, managerTenure.coverage_ratio),
      requestedStartDate: textValue(managerTenure.requestedStartDate, managerTenure.requested_start_date),
      actualStartDate: textValue(managerTenure.actualStartDate, managerTenure.actual_start_date),
      totalReturn: numberValue(managerTenure.totalReturn, managerTenure.total_return),
      applicable: Boolean(managerTenure.applicable),
      includedInScore: Boolean(managerTenure.includedInScore ?? managerTenure.included_in_score),
      note: textValue(managerTenure.note),
    },
    alternatives: alternatives.map((item) => ({
      windCode: textValue(item.windCode, item.wind_code),
      name: textValue(item.name, item.windCode, item.wind_code),
      styleLabel: textValue(item.styleLabel, item.style_label),
      overallScore: numberValue(item.overallScore, item.overall_score),
      reason: textValue(item.reason),
    })),
  }
}
