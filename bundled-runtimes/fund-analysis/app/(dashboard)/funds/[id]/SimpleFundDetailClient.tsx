'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BookOpenText,
  Bot,
  CalendarDays,
  Check,
  CheckCircle2,
  ChartNoAxesCombined,
  CircleAlert,
  Database,
  Copy,
  GitCompareArrows,
  History,
  Save,
  ShieldCheck,
  UserRound,
} from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CamelFund } from '@/lib/backend-api'
import { buildFundMarketEnvironment, type FundMarketEnvironment } from '@/lib/fund-market-environment'
import {
  asRecord,
  drawdownMetric,
  formatAsset,
  formatPercent,
  managerName,
  numberValue,
  returnMetric,
  sharpeMetric,
  styleLabel,
  type SimpleFund,
  windowMetrics,
} from '@/lib/simple-fund-view'
import FundAttributionEvidence from './FundAttributionEvidence'
import FundAssetAllocationPanel, { type FundAssetAllocationSnapshot } from './FundAssetAllocationPanel'
import FundBondAnomalyPanel, { type FundBondAnomalySnapshot } from './FundBondAnomalyPanel'
import FundBondDurationPanel, { type FundBondDurationSnapshot } from './FundBondDurationPanel'
import FundBondHoldingPanel, { type FundBondHoldingSnapshot } from './FundBondHoldingPanel'
import FundHolderStructurePanel, { type FundHolderStructureSnapshot } from './FundHolderStructurePanel'
import FundHoldingProfile, { type FundHoldingSnapshot } from './FundHoldingProfile'
import FundHoldingChangesPanel, { type FundHoldingChanges } from './FundHoldingChangesPanel'
import FundProductProfilePanel, { type FundProductProfile } from './FundProductProfilePanel'
import FundFofHoldingPanel, { type FundFofHoldingSnapshot } from './FundFofHoldingPanel'
import FundDataQualityPanel, { type FundDataQualitySnapshot } from './FundDataQualityPanel'
import FundDrawdownRecoveryPanel, { type FundDrawdownRecoverySnapshot } from './FundDrawdownRecoveryPanel'
import FundPeriodPerformancePanel, { type FundPeriodPerformanceSnapshot } from './FundPeriodPerformancePanel'
import FundShareClassPanel, { type FundShareClassSnapshot } from './FundShareClassPanel'
import FundManagerHistoryPanel, { type FundManagerHistorySnapshot } from './FundManagerHistoryPanel'
import FundManagerTenurePerformancePanel, { type FundManagerTenurePerformance } from './FundManagerTenurePerformancePanel'
import GenerateFundReportButton from './GenerateFundReportButton'

export type FundNavPoint = {
  date: string
  nav: number
  unitNav: number | null
  accumNav: number | null
  navBasis: 'accum_nav' | 'unit_nav'
  benchmarkNav: number | null
}

export type FundPeerMetric = {
  key: string
  label: string
  value: number | null
  unit: string
  percentile: number | null
  rank: number | null
  peerCount: number
  sampleStatus: string
  metricWindow: string
}

export type CrossMarketPeerMetric = {
  metric: string
  label: string
  value: number | null
  unit: string
  percentile: number | null
  positionLabel: string
  sampleSize: number
  minimumPeerCount: number
  sampleStatus: string
  dispersionStatus: string
}

export type CrossMarketHoldingEvidence = {
  status: string
  quarter: string
  peerGroupName: string
  profilePeerCount: number
  minimumPeerCount: number
  labels: string[]
  comparisons: CrossMarketPeerMetric[]
  missingItems: string[]
  boundary: string
}

export type FundEvaluation = {
  status: string
  methodologyVersion: string
  calculationMethod: string
  evaluationWindow: string
  asOfDate: string
  classificationStatus: string
  peerGroup: string
  peerGroupId: string
  benchmark: string
  benchmarkCode: string
  benchmarkType: string
  benchmarkWeight: number | null
  benchmarkComponents: Array<{
    code: string
    name: string
    asset: string
    weight: number
  }>
  contractDimensions: {
    baseIndex: string
    priceReturn: string
    tenor: string
  } | null
  strategyFamily: string
  activePassive: string
  confidence: number | null
  sampleStatus: string
  validPeerCount: number
  minimumPeerCount: number
  score: number | null
  grade: string
  dimensions: Array<{
    key: string
    score: number | null
    weight: number | null
    weightedScore: number | null
    evidence: string[]
  }>
  metricScores: Record<string, number>
  methodology: {
    status: string
    profileKey: string
    profileName: string
    evaluationWindow: string
    scoreFormula: string
    boundary: string
    dimensions: Array<{
      key: string
      label: string
      weight: number | null
      metrics: Array<{
        path: string
        label: string
        unit: string
        direction: string
        rule: string
        fallbackPaths: string[]
      }>
    }>
  }
  peerMetrics: FundPeerMetric[]
  crossMarketHolding: CrossMarketHoldingEvidence
  positiveFactors: string[]
  negativeFactors: string[]
  missingItems: string[]
  dataQualityStatus: string
  dataQualityScore: number | null
}

export type FundEvaluationHistoryItem = {
  id: string
  evaluationWindow: string
  asOfDate: string
  createdAt: string
  status: string
  methodologyVersion: string
  calculationMethod: string
  peerGroupName: string
  overallScore: number | null
  overallGrade: string
  peerRank: number | null
  peerCount: number | null
  peerPercentile: number | null
  dimensions: Array<{ key: string; score: number | null }>
  evidenceCoverage: {
    coveragePercent: number | null
    missingDimensions: string[]
  }
  missingItems: string[]
  change: {
    summary: string
    comparisonStatus: string
    comparable: boolean
    scoreDelta: number | null
    rawScoreDelta: number | null
    rankChange: number | null
    rawRankChange: number | null
    percentileDelta: number | null
    evidenceCoverageDelta: number | null
    dataQualityDelta: number | null
    drivers: Array<{ key: string; delta: number }>
    methodologyChanged: boolean
    peerGroupChanged: boolean
  } | null
}

type FundEvaluationStatistics = {
  status: string
  metricWindow: string
  peerGroup: string
  primaryBenchmark: string
  classifiedPeerCount: number
  scoredPeerCount: number
  minimumPeerCount: number
  coverageRate: number
  methodologyVersion: string
  ranking: Array<{
    windCode: string
    name: string
    fundType: string
    rank: number
    score: number
    grade: string
    percentile: number
    isCurrent: boolean
    dimensionScores: Array<{ key: string; score: number }>
    dataCoverage: {
      availableMetricCount: number
      requiredMetricCount: number
      coverageRate: number
    }
  }>
  unscoredPeerCount: number
  unscoredSummary: Record<string, number>
  summary: {
    average: number | null
    median: number | null
    highest: number | null
    lowest: number | null
  }
  distribution: Array<{
    key: string
    label: string
    lower: number
    upper: number
    count: number
    percentage: number
  }>
  dimensions: Array<{
    key: string
    average: number | null
    median: number | null
    currentScore: number | null
    sampleCount: number
    minimumPeerCount: number
    sampleStatus: string
  }>
  current: {
    score: number | null
    rank: number | null
    peerCount: number | null
    percentile: number | null
    sampleStatus: string
  }
  boundary: string
}

export type FundResearchMemo = {
  id: string
  title: string
  managerName: string
  reportDate: string
  source: string
  summary: string
  classifications: string[]
  styleLabels: string[]
  fundClassifications: string[]
  fundStyleLabels: string[]
  managerClassifications: string[]
  managerStyleLabels: string[]
  keyPoints: string[]
  evidenceScope: string
}

export type FundHoldingStyleFactor = {
  factor: string
  label: string
  exposure: number | null
  unit: string
  percentile: number | null
  percentileLabel: string
  sampleSize: number
}

export type FundHoldingStyle = {
  status: string
  quarter: string
  peerGroupName: string
  sampleSize: number
  minimumPeerCount: number
  holdingsDisclosedWeight: number | null
  labels: string[]
  descriptors: FundHoldingStyleFactor[]
  peerPercentiles: FundHoldingStyleFactor[]
  modelScope: string
  missingItems: string[]
}

export type FundHoldingExperiencePeriod = {
  months: number
  label: string
  status: string
  sampleCount: number
  positiveProbability: number | null
  nonLossProbability: number | null
  returnThresholdProbabilities: Array<{
    threshold: number
    probability: number | null
  }>
  medianReturn: number | null
  averageReturn: number | null
  bestReturn: number | null
  worstReturn: number | null
  averageActualDays: number | null
  firstBuyDate: string
  lastBuyDate: string
}

export type FundHoldingExperience = {
  status: string
  source: string
  navBasis: string
  sampleStart: string
  sampleEnd: string
  navObservations: number
  periods: FundHoldingExperiencePeriod[]
  missingItems: string[]
}

export type FundAssessmentSummary = {
  status: string
  evaluationWindow: string
  evaluationWindowLabel: string
  verdict: string
  peerGroup: string
  score: number | null
  grade: string
  peerRank: number | null
  peerCount: number | null
  peerPercentile: number | null
  advantages: string[]
  risks: string[]
  managerStabilityEvidence: {
    status: string
    label: string
    currentManagerCount: number
    currentManagerNames: string[]
    teamMode: string
    currentTeamStart: string
    currentTeamDays: number
    latestChangeDate: string
    changesLastYear: number
    changesLastThreeYears: number
    includedInScore: boolean
    note: string
  }
  scaleTrendEvidence: {
    status: string
    label: string
    latestReportDate: string
    latestAssetYi: number | null
    oneYearChange: number | null
    threeYearChange: number | null
    peakAssetYi: number | null
    peakDate: string
    latestFromPeak: number | null
    observations: number
    includedInScore: boolean
    note: string
  }
  drawdownRecoveryEvidence: {
    status: string
    label: string
    historyStart: string
    historyEnd: string
    navBasis: string
    observations: number
    currentDrawdown: number | null
    currentUnderwaterDays: number
    worstDrawdown: number | null
    worstRecoveryDays: number | null
    longestUnderwaterDays: number
    materialEpisodeCount: number
    recoveredMaterialEpisodeCount: number
    includedInScore: boolean
    note: string
  }
  styleEvidence: {
    status: string
    labels: string[]
    memoLabels: string[]
    quarter: string
    sampleSize: number
    scope: string
    note: string
  }
  styleDriftEvidence: {
    status: string
    level: string
    label: string
    previousQuarter: string
    latestQuarter: string
    factorCount: number
    changedFactorCount: number
    maxPercentileChange: number | null
    addedLabels: string[]
    removedLabels: string[]
    includedInScore: boolean
    note: string
    boundary: string
  }
  researchEvidence: {
    status: string
    count: number
    fundLevelCount: number
    fundSpecificCount: number
    managerLevelCount: number
    latestTitle: string
    latestDate: string
    note: string
  }
  attributionEvidence: {
    status: string
    mode: string
    headline: string
    detail: string
    quarter: string
    activeReturn: number | null
    coverage: number | null
    formalBarraReady: boolean
    barraDescriptorReady: boolean
  }
  boundary: string
}

export type FundDetailHighlight = {
  id: string
  tone: 'strength' | 'risk' | 'neutral'
  label: string
  value: string
  detail: string
  source: string
  asOfDate: string
  metricName: string
}

export type FundPlainLanguageBrief = {
  status: string
  title: string
  fundName: string
  evidenceCount: number
  items: Array<{
    key: string
    label: string
    text: string
    status: string
    source: string
    asOfDate: string
    evidenceId: string
  }>
  copyText: string
  boundary: string
}

type Props = {
  fund: CamelFund
  nav: FundNavPoint[]
  evaluationWindows: Record<string, FundEvaluation>
  evaluationHistory: FundEvaluationHistoryItem[]
  assessmentSummary: FundAssessmentSummary
  detailHighlights: FundDetailHighlight[]
  plainLanguageBrief: FundPlainLanguageBrief
  researchMemos: FundResearchMemo[]
  dataQuality: FundDataQualitySnapshot
  shareClasses: FundShareClassSnapshot
  managerHistory: FundManagerHistorySnapshot
  managerTenurePerformance: FundManagerTenurePerformance
  assetAllocation: FundAssetAllocationSnapshot
  drawdownRecovery: FundDrawdownRecoverySnapshot
  periodPerformance: FundPeriodPerformanceSnapshot
  fofHoldings: FundFofHoldingSnapshot
  bondAnomaly: FundBondAnomalySnapshot
  bondDuration: FundBondDurationSnapshot
  bondHoldings: FundBondHoldingSnapshot
  holderStructure: FundHolderStructureSnapshot
  holdingSnapshot: FundHoldingSnapshot
  holdingChanges: FundHoldingChanges
  holdingStyle: FundHoldingStyle
  holdingExperience: FundHoldingExperience
  productProfile: FundProductProfile
}

const windows = [
  { value: '6m', label: '近 6 月', observations: 126 },
  { value: '1y', label: '近 1 年', observations: 252 },
  { value: '3y', label: '近 3 年', observations: 756 },
] as const

const dimensionLabels: Record<string, string> = {
  return: '收益能力',
  excess_return: '超额收益',
  active_efficiency: '主动管理效率',
  drawdown_control: '回撤控制',
  risk: '风险控制',
  risk_adjusted: '风险调整后收益',
  consistency: '表现稳定性',
  manager_tenure: '经理任期',
  tracking_quality: '跟踪质量',
  cost_efficiency: '成本效率',
  scale_liquidity: '规模与流动性',
  income_competitiveness: '收益竞争力',
  capital_preservation: '净值稳定性',
  income_stability: '收益稳定性',
  data_quality: '数据质量',
}

const activePassiveLabels: Record<string, string> = {
  active: '主动管理',
  passive: '被动跟踪',
  enhanced_index: '指数增强',
}

const windowLabels: Record<string, string> = {
  '6m': '近 6 月',
  '1y': '近 1 年',
  '3y': '近 3 年',
}

function humanizeFactor(value: string) {
  return Object.entries(dimensionLabels).reduce(
    (result, [key, label]) => result.replace(new RegExp(`\\b${key}\\b`, 'gu'), label),
    value,
  )
}

function AssessmentEvidenceCard({ title, status, tone, headline, detail }: { title: string; status: string; tone: 'ready' | 'warning'; headline: string; detail: string }) {
  return (
    <div className="bg-white p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-bold text-[#3f5047]">{title}</span>
        <span className={`rounded-sm px-2 py-1 text-[10px] font-bold ${tone === 'ready' ? 'bg-[#e3f0e9] text-[#226148]' : 'bg-[#fff1d5] text-[#7d5a1b]'}`}>{status}</span>
      </div>
      <p className="mt-3 line-clamp-2 text-sm font-bold leading-6 text-[#1d2923]">{headline}</p>
      <p className="mt-2 line-clamp-3 text-xs leading-6 text-[#6b7771]">{detail}</p>
    </div>
  )
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

function volatilityMetric(fund: SimpleFund, window: string) {
  const rolling = windowMetrics(fund, window)
  const risk = asRecord(fund.riskMetrics)
  return numberValue(
    rolling.annualized_volatility,
    risk[`annualized_volatility_${window}`],
    risk[`volatility_${window}`],
  )
}

function metricValue(metric: FundPeerMetric) {
  if (metric.value == null) return '—'
  if (metric.unit === 'percent') return formatPercent(metric.value, 2)
  if (metric.unit === 'cny_100m') return formatAsset(metric.value)
  return metric.value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function chartWindow(nav: FundNavPoint[], observations: number, startDate = '', endDate = '') {
  if (!nav.length) return []
  if (startDate || endDate) {
    const dated = nav.filter((point) => (!startDate || point.date >= startDate) && (!endDate || point.date <= endDate))
    if (dated.length) return dated
  }
  return nav.slice(-observations)
}

function buildChartSeries(nav: FundNavPoint[]) {
  if (!nav.length) {
    return {
      data: [],
      startDate: '',
      endDate: '',
      observations: 0,
      benchmarkObservations: 0,
      benchmarkCoverage: null,
      navBasis: 'unit_nav' as const,
    }
  }

  const firstCommonIndex = nav.findIndex((point) => point.benchmarkNav != null)
  const aligned = firstCommonIndex >= 0 ? nav.slice(firstCommonIndex) : nav
  const baseFundNav = aligned[0]?.nav ?? null
  const baseBenchmarkNav = aligned[0]?.benchmarkNav ?? null
  const benchmarkObservations = aligned.filter((point) => point.benchmarkNav != null).length
  const navBasis = aligned.some((point) => point.navBasis === 'accum_nav') ? 'accum_nav' : 'unit_nav'
  const data = aligned.map((point) => ({
    ...point,
    fundGrowth: baseFundNav != null && baseFundNav > 0 ? ((point.nav / baseFundNav) - 1) * 100 : null,
    benchmarkGrowth: baseBenchmarkNav != null && point.benchmarkNav != null && baseBenchmarkNav > 0
      ? ((point.benchmarkNav / baseBenchmarkNav) - 1) * 100
      : null,
  }))

  return {
    data,
    startDate: aligned[0]?.date || '',
    endDate: aligned[aligned.length - 1]?.date || '',
    observations: aligned.length,
    benchmarkObservations,
    benchmarkCoverage: aligned.length ? benchmarkObservations / aligned.length : null,
    navBasis,
  }
}

function managerNames(fund: SimpleFund) {
  const managers = Array.isArray(fund.managers) ? fund.managers : []
  const names = managers.map((item) => String(asRecord(item).name || '')).filter(Boolean)
  return names.length ? names.join('、') : '经理待补充'
}

function formatHoldingStyleValue(item: FundHoldingStyleFactor) {
  if (item.exposure == null) return '—'
  if (item.unit === 'cny_100m') return `${item.exposure.toFixed(0)} 亿元`
  if (item.unit === 'ratio') return `${(item.exposure * 100).toFixed(1)}%`
  return item.exposure.toFixed(2)
}

function formatCrossMarketMetric(item: CrossMarketPeerMetric) {
  if (item.value == null) return '—'
  if (item.unit === 'percent') return `${(item.value * 100).toFixed(1)}%`
  if (item.unit === 'hhi') return item.value.toFixed(3)
  return item.value.toFixed(2)
}

function CrossMarketPeerPanel({ evidence }: { evidence: CrossMarketHoldingEvidence }) {
  const items = evidence.comparisons.filter((item) => [
    'cn_a_weight',
    'hk_weight',
    'security_hhi',
    'industry_hhi',
    'top_three_share_of_disclosed',
    'market_allocation_hhi',
  ].includes(item.metric))
  if (!items.length) return null
  const ready = evidence.status === 'peer_comparison_ready'
  const evidenceNotice = evidence.missingItems.find((item) => item.includes('公开持仓'))
    || evidence.missingItems[0]
  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><BarChart3 className="h-5 w-5 text-[#28745c]" />同类持仓画像</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">{evidence.quarter || '季度待补'} · {evidence.peerGroupName || '专业同类组待补'}。只比较同季度公开持仓，不跨类别。</p>
        </div>
        <span className={`rounded-sm px-2.5 py-1 text-[11px] font-bold ${ready ? 'bg-[#e2f0e8] text-[#1f684e]' : 'bg-[#fff1d2] text-[#815a16]'}`}>
          {ready ? `${evidence.profilePeerCount} 只同类样本` : `样本 ${evidence.profilePeerCount}/${evidence.minimumPeerCount}`}
        </span>
      </div>

      {evidence.labels.length ? <div className="flex flex-wrap gap-2 border-b border-[#edf0ed] bg-[#f7faf8] px-5 py-4 sm:px-6">{evidence.labels.map((label) => <span key={label} className="rounded-sm bg-[#e4efe9] px-3 py-1.5 text-xs font-bold text-[#28654f]">{label}</span>)}</div> : null}
      {evidenceNotice || !ready ? <div className="flex gap-3 border-b border-[#eadfbf] bg-[#fffaf0] px-5 py-3 text-xs leading-6 text-[#735b2b] sm:px-6"><CircleAlert className="mt-1 h-4 w-4 shrink-0" /><p>{evidenceNotice || `同季度同类公开持仓只有 ${evidence.profilePeerCount} 只，最低需要 ${evidence.minimumPeerCount} 只；当前不贴“偏高/偏低”标签。`}</p></div> : null}

      <div className="grid gap-px bg-[#e2e7e3] sm:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <article key={item.metric} className="bg-white p-5">
            <div className="text-xs font-bold text-[#536159]">{item.label}</div>
            <div className="mt-3 flex items-end justify-between gap-3"><strong className="text-2xl text-[#1d2923]">{formatCrossMarketMetric(item)}</strong>{item.percentile != null ? <span className="text-xs font-bold text-[#28745c]">同类分位 {item.percentile.toFixed(0)}%</span> : null}</div>
            {item.percentile != null ? <div className="mt-3 h-1.5 overflow-hidden bg-[#e4e9e5]"><div className="h-full bg-[#3a8068]" style={{ width: `${Math.max(0, Math.min(100, item.percentile))}%` }} /></div> : null}
            <div className="mt-2 text-[11px] leading-5 text-[#89938e]">{item.positionLabel || `同类样本 ${item.sampleSize}/${item.minimumPeerCount}`}</div>
          </article>
        ))}
      </div>
      <div className="border-t border-[#e3e7e4] bg-[#fffaf0] px-5 py-3 text-[11px] leading-5 text-[#765d2c]">{evidence.boundary || '公开持仓画像只用于解释，不参与基金评分。'}</div>
    </section>
  )
}

function normalizeFeeRate(value: number | null) {
  if (value == null) return null
  return Math.abs(value) >= 0.05 ? value / 100 : value
}

function baseFeeRate(fund: CamelFund) {
  const managementFee = normalizeFeeRate(fund.managementFee)
  const custodianFee = normalizeFeeRate(fund.custodianFee)
  if (managementFee == null && custodianFee == null) return null
  return (managementFee || 0) + (custodianFee || 0)
}

function probabilityTone(value: number | null) {
  if (value == null) return 'text-[#777f7b]'
  if (value >= 0.7) return 'text-[#17634b]'
  if (value >= 0.5) return 'text-[#8a6725]'
  return 'text-[#9a5047]'
}

function HoldingExperiencePanel({ experience }: { experience: FundHoldingExperience }) {
  const periods = experience.periods.filter((item) => item.status === 'sufficient')
  const clearest = [...periods].sort((left, right) => (right.positiveProbability ?? -1) - (left.positiveProbability ?? -1))[0]
  const thresholds = periods.find((item) => item.returnThresholdProbabilities.length)?.returnThresholdProbabilities || []
  return (
    <section className="overflow-hidden border border-[#cbdad2] bg-[#f4f8f5]">
      <div className="grid gap-4 border-b border-[#dce6e0] p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold text-[#28745c]"><CalendarDays className="h-4 w-4" />持有体验</div>
          <h2 className="mt-3 text-xl font-bold text-[#1b2922]">同一只基金，持有多久更容易熬过波动</h2>
          <p className="mt-2 text-xs leading-6 text-[#68746e]">把每个历史净值日都当作买入日，回放持有 1、3、6、12 个月后的真实结果；优先使用累计净值处理分红。</p>
        </div>
        <div className="text-left lg:text-right">
          <div className="text-[11px] text-[#77827c]">历史上最高赚钱概率</div>
          <div className="mt-1 text-lg font-bold text-[#215f4a]">{clearest ? `${clearest.label} · ${formatPercent(clearest.positiveProbability, 0)}` : '样本待补'}</div>
          <div className="mt-1 text-[10px] text-[#89938e]">{formatDate(experience.sampleStart)} 至 {formatDate(experience.sampleEnd)} · {experience.navObservations} 条净值</div>
        </div>
      </div>

      {periods.length ? (
        <>
          <div className="grid gap-px bg-[#dce4df] sm:grid-cols-2 xl:grid-cols-4">
            {periods.map((item) => (
              <article key={item.months} className="bg-white p-5">
                <div className="flex items-center justify-between gap-3"><strong className="text-sm text-[#26342d]">{item.label}</strong><span className="text-[10px] text-[#85908a]">{item.sampleCount} 次历史买入</span></div>
                <div className={`mt-5 text-3xl font-bold ${probabilityTone(item.positiveProbability)}`}>{formatPercent(item.positiveProbability, 0)}</div>
                <div className="mt-1 text-[11px] text-[#748079]">赚钱概率</div>
                <div className="mt-4 h-1.5 overflow-hidden bg-[#e9edea]"><div className="h-full bg-[#3c8369]" style={{ width: `${Math.max(0, Math.min(100, (item.positiveProbability || 0) * 100))}%` }} /></div>
                <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
                  <div><dt className="text-[#87918c]">中位收益</dt><dd className="mt-1 font-bold text-[#2c4237]">{formatPercent(item.medianReturn, 1)}</dd></div>
                  <div><dt className="text-[#87918c]">平均收益</dt><dd className="mt-1 font-bold text-[#2c4237]">{formatPercent(item.averageReturn, 1)}</dd></div>
                  <div><dt className="text-[#87918c]">最差一次</dt><dd className="mt-1 font-bold text-[#9a5047]">{formatPercent(item.worstReturn, 1)}</dd></div>
                  <div><dt className="text-[#87918c]">最好一次</dt><dd className="mt-1 font-bold text-[#17634b]">{formatPercent(item.bestReturn, 1)}</dd></div>
                </dl>
              </article>
            ))}
          </div>
          {thresholds.length ? (
            <div className="border-t border-[#dce6e0] bg-white p-5 sm:p-6">
              <h3 className="text-sm font-bold text-[#26342d]">达到目标收益的历史概率</h3>
              <p className="mt-1 text-[11px] leading-5 text-[#78847e]">例如“收益 &gt; 3%”表示历史上按该期限持有后，收益超过 3% 的买入次数占比。</p>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[42rem] border-collapse text-center text-xs">
                  <thead>
                    <tr className="border-y border-[#e3e8e4] bg-[#f5f7f5] text-[#69766f]">
                      <th className="px-3 py-3 text-left font-bold">持有期限</th>
                      {thresholds.map((item) => <th key={item.threshold} className="px-3 py-3 font-bold">收益 &gt; {formatPercent(item.threshold, 0)}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {periods.map((period) => (
                      <tr key={period.months} className="border-b border-[#edf0ed] last:border-b-0">
                        <th className="px-3 py-3 text-left font-bold text-[#314239]">{period.label}</th>
                        {thresholds.map((threshold) => {
                          const result = period.returnThresholdProbabilities.find((item) => item.threshold === threshold.threshold)
                          return <td key={threshold.threshold} className={`px-3 py-3 font-bold ${probabilityTone(result?.probability ?? null)}`}>{formatPercent(result?.probability ?? null, 0)}</td>
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </>
      ) : <div className="px-6 py-10 text-center text-sm text-[#748079]">{experience.missingItems[0] || '真实净值样本不足，暂时无法回放持有体验。'}</div>}

      <div className="border-t border-[#dce6e0] bg-[#fffaf0] px-5 py-3 text-[11px] leading-5 text-[#765d2c]">历史赚钱概率不是未来承诺，也不构成投资建议；它只用于理解不同持有期限下曾经出现过的收益分布。</div>
    </section>
  )
}

function captureTone(value: number | null, direction: 'up' | 'down') {
  if (value == null) return 'text-[#777f7b]'
  if (direction === 'up') {
    if (value >= 1.1) return 'text-[#17634b]'
    if (value >= 0.8) return 'text-[#8a6725]'
    return 'text-[#9a5047]'
  }
  if (value <= 0.8) return 'text-[#17634b]'
  if (value <= 1.1) return 'text-[#8a6725]'
  return 'text-[#9a5047]'
}

function captureConclusion(value: number | null, direction: 'up' | 'down') {
  if (value == null) return '样本待补'
  if (direction === 'up') {
    if (value >= 1.1) return '上涨弹性较强'
    if (value >= 0.8) return '上涨基本跟随'
    return '上涨参与偏弱'
  }
  if (value <= 0.8) return '下跌阶段较抗跌'
  if (value <= 1.1) return '下跌基本同步'
  return '下跌放大偏高'
}

function MarketEnvironmentPanel({ profile, benchmark, windowLabel }: { profile: FundMarketEnvironment; benchmark: string; windowLabel: string }) {
  const recentMonths = profile.months.slice(-6)
  return (
    <section className="overflow-hidden border border-[#cbdad2] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#dfe6e1] p-5 sm:p-6">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold text-[#28745c]"><ChartNoAxesCombined className="h-4 w-4" />市场环境表现</div>
          <h2 className="mt-3 text-xl font-bold text-[#1b2922]">市场涨时跟得上，跌时守得住吗</h2>
          <p className="mt-2 text-xs leading-6 text-[#68746e]">使用{windowLabel}基金与 {benchmark} 的共同月末净值计算；只解释历史表现，不改变基金评分。</p>
        </div>
        <span className={`rounded-sm px-2.5 py-1 text-[11px] font-bold ${profile.status === 'ready' ? 'bg-[#e2f0e8] text-[#1f684e]' : 'bg-[#fff1d2] text-[#815a16]'}`}>
          {profile.status === 'ready' ? `${profile.monthlyPeriods} 个月度样本` : profile.status === 'partial' ? '样本偏少' : '证据不足'}
        </span>
      </div>

      {profile.status === 'insufficient' ? (
        <div className="px-6 py-10 text-center text-sm text-[#748079]">{profile.missingItems[0] || '基金与评价基准的共同月末净值不足。'}</div>
      ) : (
        <>
          <div className="grid gap-px bg-[#dfe6e1] sm:grid-cols-2 xl:grid-cols-4">
            <article className="bg-[#f7faf8] p-5">
              <div className="text-[11px] text-[#748079]">上涨捕获率</div>
              <div className={`mt-2 text-3xl font-bold ${captureTone(profile.upsideCapture, 'up')}`}>{formatPercent(profile.upsideCapture, 0)}</div>
              <div className="mt-2 text-sm font-bold text-[#304239]">{captureConclusion(profile.upsideCapture, 'up')}</div>
              <div className="mt-1 text-[10px] leading-5 text-[#849089]">{profile.upMonths} 个基准上涨月 · 跑赢率 {formatPercent(profile.upOutperformanceRate, 0)}</div>
            </article>
            <article className="bg-[#f7faf8] p-5">
              <div className="text-[11px] text-[#748079]">下跌捕获率</div>
              <div className={`mt-2 text-3xl font-bold ${captureTone(profile.downsideCapture, 'down')}`}>{formatPercent(profile.downsideCapture, 0)}</div>
              <div className="mt-2 text-sm font-bold text-[#304239]">{captureConclusion(profile.downsideCapture, 'down')}</div>
              <div className="mt-1 text-[10px] leading-5 text-[#849089]">{profile.downMonths} 个基准下跌月 · 防守率 {formatPercent(profile.downProtectionRate, 0)}</div>
            </article>
            <article className="bg-white p-5">
              <div className="text-[11px] text-[#748079]">上涨月平均超额</div>
              <div className={`mt-2 text-2xl font-bold ${(profile.upAverageExcessReturn || 0) >= 0 ? 'text-[#17634b]' : 'text-[#9a5047]'}`}>{formatPercent(profile.upAverageExcessReturn, 2)}</div>
              <div className="mt-2 text-[10px] leading-5 text-[#849089]">正数表示基准上涨时，基金月均表现更强。</div>
            </article>
            <article className="bg-white p-5">
              <div className="text-[11px] text-[#748079]">下跌月平均超额</div>
              <div className={`mt-2 text-2xl font-bold ${(profile.downAverageExcessReturn || 0) >= 0 ? 'text-[#17634b]' : 'text-[#9a5047]'}`}>{formatPercent(profile.downAverageExcessReturn, 2)}</div>
              <div className="mt-2 text-[10px] leading-5 text-[#849089]">正数表示基准下跌时，基金平均少跌或逆势上涨。</div>
            </article>
          </div>

          {recentMonths.length ? (
            <div className="border-t border-[#e2e7e3] p-5 sm:p-6">
              <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-sm font-bold text-[#304239]">最近月度表现</h3><span className="text-[10px] text-[#87918c]">绿：跑赢基准 · 红：跑输基准</span></div>
              <div className="mt-4 grid gap-2 sm:grid-cols-3 xl:grid-cols-6">
                {recentMonths.map((item) => (
                  <div key={item.month} className={`border px-3 py-3 ${item.excessReturn >= 0 ? 'border-[#cfe1d7] bg-[#f2f8f4]' : 'border-[#ead5d0] bg-[#fff7f5]'}`}>
                    <div className="flex items-center justify-between gap-2 text-[10px] text-[#75817a]"><span>{item.month}</span><span>{item.market === 'up' ? '基准上涨' : item.market === 'down' ? '基准下跌' : '基准持平'}</span></div>
                    <div className={`mt-2 text-sm font-bold ${item.excessReturn >= 0 ? 'text-[#17634b]' : 'text-[#9a5047]'}`}>超额 {formatPercent(item.excessReturn, 2)}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}

      <div className="border-t border-[#e3e7e4] bg-[#fffaf0] px-5 py-3 text-[11px] leading-5 text-[#765d2c]">
        {profile.methodology} 捕获率 100% 表示与基准大致同步；下跌捕获率越低通常表示历史防守更好。{profile.missingItems.length ? ` ${profile.missingItems.join('')}` : ''}
      </div>
    </section>
  )
}

const briefSourceLabels: Record<string, string> = {
  professional_classification_evaluation: '专业分类与同类评价',
  category_peer_percentile: '专业同类分位',
  holding_style_and_research_memos: '公开持仓与调研纪要',
  'local.postgres.holding_style_snapshots': '公开持仓风格快照',
  'local.postgres.fund_nav': '本地真实净值',
}

function PlainLanguageBriefPanel({ brief }: { brief: FundPlainLanguageBrief }) {
  const [copied, setCopied] = useState(false)
  const items = brief.items.filter((item) => item.text)
  if (!items.length) return null

  async function copyBrief() {
    await navigator.clipboard.writeText(brief.copyText)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }

  return (
    <section className="overflow-hidden border border-[#bfcfc6] bg-[#f3f8f5]">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#d8e3dd] p-5 sm:p-6">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold text-[#28745c]"><BookOpenText className="h-4 w-4" />基金速览</div>
          <h2 className="mt-3 text-xl font-bold text-[#1b2922]">{brief.title || '一分钟看懂这只基金'}</h2>
          <p className="mt-2 text-xs leading-6 text-[#68746e]">把专业评价、风格、纪要和历史持有体验压缩到一处；每句话都保留证据来源。</p>
        </div>
        <button type="button" onClick={() => void copyBrief()} className="inline-flex h-10 items-center gap-2 rounded-md border border-[#8aa697] bg-white px-4 text-xs font-bold text-[#245f4b] hover:bg-[#eaf3ee]">
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          {copied ? '已复制' : '复制摘要'}
        </button>
      </div>
      <ol className="divide-y divide-[#e0e7e3] bg-white">
        {items.map((item, index) => (
          <li key={item.key} className="grid gap-3 px-5 py-4 sm:grid-cols-[1.5rem_6.5rem_minmax(0,1fr)] sm:px-6">
            <span className={`grid h-6 w-6 place-items-center rounded-full text-[11px] font-bold ${item.key === 'strength' ? 'bg-[#dceee5] text-[#226148]' : item.key === 'risk' ? 'bg-[#f7e5e1] text-[#8c4b43]' : 'bg-[#edf0ed] text-[#536159]'}`}>{index + 1}</span>
            <strong className="text-sm text-[#29372f]">{item.label}</strong>
            <div>
              <p className="text-sm leading-7 text-[#425047]">{item.text}</p>
              <div className="mt-1.5 text-[10px] text-[#8a948f]">{item.status === 'available' ? '已核验证据' : '证据待补'} · {briefSourceLabels[item.source] || '基金研究快照'}{item.asOfDate ? ` · 截至 ${formatDate(item.asOfDate)}` : ''}</div>
            </div>
          </li>
        ))}
      </ol>
      <div className="border-t border-[#d8e3dd] bg-[#fffaf0] px-5 py-3 text-[11px] leading-5 text-[#765d2c]">{brief.boundary}</div>
    </section>
  )
}

function scoreMessage(evaluation: FundEvaluation) {
  if (evaluation.classificationStatus !== 'classified') return '专业分类证据不足，暂不输出综合分。'
  if (evaluation.sampleStatus !== 'sufficient' && evaluation.validPeerCount < evaluation.minimumPeerCount) return `同类有效样本 ${evaluation.validPeerCount} 只，低于 ${evaluation.minimumPeerCount} 只门槛，暂不输出综合分。`
  if (evaluation.sampleStatus !== 'sufficient') return '本基金核心指标不足，暂不输出综合分。'
  return '评价数据尚未满足当前类别方法，暂不输出综合分。'
}

function formatEvaluationMetric(value: number | null, unit: string) {
  if (value == null) return '数据待补'
  if (unit === 'percent') return formatPercent(value, 2)
  if (unit === 'cny_100m') return `${value.toFixed(value >= 10 ? 1 : 2)} 亿元`
  if (unit === 'days') return `${value.toFixed(0)} 天`
  return value.toFixed(2)
}

function benchmarkComposition(components: FundEvaluation['benchmarkComponents']) {
  return components
    .map((component) => `${component.name} ${component.weight.toFixed(component.weight % 1 ? 1 : 0)}%`)
    .join(' + ')
}

function EvaluationDetailPanel({ evaluation }: { evaluation: FundEvaluation }) {
  const methodology = evaluation.methodology
  if (!methodology.dimensions.length) return null

  return (
    <details className="border-b border-[#e0e5e1] bg-[#f8faf8]">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 text-sm font-bold text-[#28463a] sm:px-6">
        <span>查看评分详情：指标、规则与加权过程</span>
        <span className="text-[11px] font-normal text-[#718078]">{methodology.profileName || '类别专属评价'} · {evaluation.evaluationWindow || '1y'}</span>
      </summary>
      <div className="border-t border-[#e0e5e1] px-5 py-5 sm:px-6">
        <div className="grid gap-px bg-[#dfe5e1] sm:grid-cols-4">
          <div className="bg-white p-4"><div className="text-[10px] text-[#85908a]">评价方法</div><div className="mt-1 text-xs font-bold text-[#304239]">{methodology.profileName || '待确认'}</div></div>
          <div className="bg-white p-4"><div className="text-[10px] text-[#85908a]">数据窗口</div><div className="mt-1 text-xs font-bold text-[#304239]">{windowLabels[evaluation.evaluationWindow] || evaluation.evaluationWindow || '—'}</div></div>
          <div className="bg-white p-4"><div className="text-[10px] text-[#85908a]">数据截至</div><div className="mt-1 text-xs font-bold text-[#304239]">{formatDate(evaluation.asOfDate)}</div></div>
          <div className="bg-white p-4"><div className="text-[10px] text-[#85908a]">计算方式</div><div className="mt-1 text-xs font-bold text-[#304239]">维度加权求和</div></div>
        </div>

        <div className="mt-5 overflow-x-auto border border-[#dfe5e1] bg-white">
          <table className="w-full min-w-[38rem] border-collapse text-xs">
            <thead><tr className="border-b border-[#e2e7e3] bg-[#f2f5f2] text-left text-[#6b7871]"><th className="px-4 py-3">评分维度</th><th className="px-4 py-3 text-right">维度得分</th><th className="px-4 py-3 text-right">权重</th><th className="px-4 py-3 text-right">分数贡献</th><th className="px-4 py-3">依据</th></tr></thead>
            <tbody>
              {evaluation.dimensions.map((dimension) => (
                <tr key={dimension.key} className="border-b border-[#edf0ed] last:border-b-0">
                  <th className="px-4 py-3 text-left font-bold text-[#34463d]">{dimensionLabels[dimension.key] || dimension.key}</th>
                  <td className="px-4 py-3 text-right font-bold text-[#2d6d56]">{dimension.score == null ? '—' : dimension.score.toFixed(1)}</td>
                  <td className="px-4 py-3 text-right text-[#68756e]">{dimension.weight == null ? '—' : formatPercent(dimension.weight, 0)}</td>
                  <td className="px-4 py-3 text-right font-bold text-[#34463d]">{dimension.weightedScore == null ? '—' : dimension.weightedScore.toFixed(2)}</td>
                  <td className="max-w-xs px-4 py-3 leading-5 text-[#718078]">{dimension.evidence.join('；') || '按当前类别规则计算'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          {methodology.dimensions.map((dimension) => {
            const scoredDimension = evaluation.dimensions.find((item) => item.key === dimension.key)
            return (
              <article key={dimension.key} className="border border-[#dfe5e1] bg-white p-4">
                <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-bold text-[#304239]">{dimension.label || dimensionLabels[dimension.key] || dimension.key}</h3><span className="text-[11px] text-[#678077]">权重 {dimension.weight == null ? '—' : formatPercent(dimension.weight, 0)} · 得分 {scoredDimension?.score == null ? '—' : scoredDimension.score.toFixed(1)}</span></div>
                {dimension.metrics.length ? <div className="mt-3 divide-y divide-[#edf0ed]">{dimension.metrics.map((metric) => {
                  const candidatePaths = [metric.path, ...metric.fallbackPaths]
                  const matchedPath = candidatePaths.find((path) => evaluation.metricScores[path] != null)
                  const value = matchedPath ? evaluation.metricScores[matchedPath] : null
                  return (
                    <div key={`${dimension.key}:${metric.path}`} className="py-3 first:pt-0 last:pb-0">
                      <div className="flex items-start justify-between gap-4"><span className="text-xs font-bold text-[#56655d]">{metric.label}</span><span className="shrink-0 text-xs font-bold text-[#245f4a]">{formatEvaluationMetric(value, metric.unit)}</span></div>
                      <div className="mt-1 text-[10px] leading-5 text-[#89938e]">{metric.direction === 'lower' ? '数值越低通常越好' : '数值越高通常越好'} · {metric.rule}</div>
                    </div>
                  )
                })}</div> : <p className="mt-3 text-[11px] leading-5 text-[#7b8780]">根据基金基础数据、净值覆盖和指标快照完整度计算。</p>}
              </article>
            )
          })}
        </div>
        <div className="mt-4 text-[10px] leading-5 text-[#849089]">方法版本：{evaluation.calculationMethod || evaluation.methodologyVersion || '待确认'}。{methodology.boundary}</div>
      </div>
    </details>
  )
}

function normalizeHistoryItem(value: unknown): FundEvaluationHistoryItem {
  const item = asRecord(value)
  const change = asRecord(item.change)
  const dimensionScores = asRecord(item.dimension_scores ?? item.dimensionScores)
  const evidenceCoverage = asRecord(item.evidence_coverage ?? item.evidenceCoverage)
  const drivers = Array.isArray(change.drivers) ? change.drivers : []
  const missingDimensions = evidenceCoverage.missing_dimensions ?? evidenceCoverage.missingDimensions
  const missingItems = item.missing_items ?? item.missingItems
  return {
    id: String(item.id || ''),
    evaluationWindow: String(item.evaluation_window ?? item.evaluationWindow ?? ''),
    asOfDate: String(item.as_of_date ?? item.asOfDate ?? ''),
    createdAt: String(item.created_at ?? item.createdAt ?? ''),
    status: String(item.status || ''),
    methodologyVersion: String(item.methodology_version ?? item.methodologyVersion ?? ''),
    calculationMethod: String(item.calculation_method ?? item.calculationMethod ?? ''),
    peerGroupName: String(item.peer_group_name ?? item.peerGroupName ?? ''),
    overallScore: numberValue(item.overall_score, item.overallScore),
    overallGrade: String(item.overall_grade ?? item.overallGrade ?? ''),
    peerRank: numberValue(item.peer_rank, item.peerRank),
    peerCount: numberValue(item.peer_count, item.peerCount),
    peerPercentile: numberValue(item.peer_percentile, item.peerPercentile),
    dimensions: Object.entries(dimensionScores).map(([key, raw]) => ({
      key,
      score: numberValue(asRecord(raw).score),
    })),
    evidenceCoverage: {
      coveragePercent: numberValue(evidenceCoverage.coverage_percent, evidenceCoverage.coveragePercent),
      missingDimensions: Array.isArray(missingDimensions)
        ? missingDimensions.map(String).filter(Boolean)
        : [],
    },
    missingItems: Array.isArray(missingItems)
      ? missingItems.map(String).filter(Boolean)
      : [],
    change: Object.keys(change).length ? {
      summary: String(change.summary || ''),
      comparisonStatus: String(change.comparison_status ?? change.comparisonStatus ?? ''),
      comparable: Boolean(change.comparable),
      scoreDelta: numberValue(change.score_delta, change.scoreDelta),
      rawScoreDelta: numberValue(change.raw_score_delta, change.rawScoreDelta),
      rankChange: numberValue(change.rank_change, change.rankChange),
      rawRankChange: numberValue(change.raw_rank_change, change.rawRankChange),
      percentileDelta: numberValue(change.percentile_delta, change.percentileDelta),
      evidenceCoverageDelta: numberValue(change.evidence_coverage_delta, change.evidenceCoverageDelta),
      dataQualityDelta: numberValue(change.data_quality_delta, change.dataQualityDelta),
      drivers: drivers.map((raw) => {
        const driver = asRecord(raw)
        return { key: String(driver.key || ''), delta: numberValue(driver.delta) || 0 }
      }).filter((driver) => driver.key),
      methodologyChanged: Boolean(change.methodology_changed ?? change.methodologyChanged),
      peerGroupChanged: Boolean(change.peer_group_changed ?? change.peerGroupChanged),
    } : null,
  }
}

function deltaText(value: number | null, suffix = '') {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}${suffix}`
}

function normalizeEvaluationStatistics(value: unknown): FundEvaluationStatistics {
  const root = asRecord(value)
  const summary = asRecord(root.summary)
  const current = asRecord(root.current)
  const unscoredSummary = asRecord(root.unscored_summary ?? root.unscoredSummary)
  return {
    status: String(root.status || 'unavailable'),
    metricWindow: String(root.metric_window ?? root.metricWindow ?? ''),
    peerGroup: String(root.peer_group ?? root.peerGroup ?? ''),
    primaryBenchmark: String(root.primary_benchmark ?? root.primaryBenchmark ?? ''),
    classifiedPeerCount: Number(root.classified_peer_count ?? root.classifiedPeerCount ?? 0),
    scoredPeerCount: Number(root.scored_peer_count ?? root.scoredPeerCount ?? 0),
    minimumPeerCount: Number(root.minimum_peer_count ?? root.minimumPeerCount ?? 0),
    coverageRate: Number(root.coverage_rate ?? root.coverageRate ?? 0),
    methodologyVersion: String(root.methodology_version ?? root.methodologyVersion ?? ''),
    ranking: (Array.isArray(root.ranking) ? root.ranking : []).map((value) => {
      const item = asRecord(value)
      const dataCoverage = asRecord(item.data_coverage ?? item.dataCoverage)
      const dimensionScores = asRecord(item.dimension_scores ?? item.dimensionScores)
      return {
        windCode: String(item.wind_code ?? item.windCode ?? ''),
        name: String(item.name || item.wind_code || item.windCode || ''),
        fundType: String(item.fund_type ?? item.fundType ?? ''),
        rank: Number(item.rank || 0),
        score: Number(item.score || 0),
        grade: String(item.grade || ''),
        percentile: Number(item.percentile || 0),
        isCurrent: Boolean(item.is_current ?? item.isCurrent),
        dimensionScores: Object.entries(dimensionScores).flatMap(([key, rawScore]) => {
          const score = numberValue(rawScore)
          return score == null ? [] : [{ key, score }]
        }),
        dataCoverage: {
          availableMetricCount: Number(dataCoverage.available_metric_count ?? dataCoverage.availableMetricCount ?? 0),
          requiredMetricCount: Number(dataCoverage.required_metric_count ?? dataCoverage.requiredMetricCount ?? 0),
          coverageRate: Number(dataCoverage.coverage_rate ?? dataCoverage.coverageRate ?? 0),
        },
      }
    }).filter((item) => item.windCode && item.rank > 0),
    unscoredPeerCount: Number(root.unscored_peer_count ?? root.unscoredPeerCount ?? 0),
    unscoredSummary: Object.fromEntries(
      Object.entries(unscoredSummary).map(([key, count]) => [key, Number(count || 0)]),
    ),
    summary: {
      average: numberValue(summary.average),
      median: numberValue(summary.median),
      highest: numberValue(summary.highest),
      lowest: numberValue(summary.lowest),
    },
    distribution: (Array.isArray(root.distribution) ? root.distribution : []).map((value) => {
      const item = asRecord(value)
      return {
        key: String(item.key || ''),
        label: String(item.label || ''),
        lower: Number(item.lower || 0),
        upper: Number(item.upper || 0),
        count: Number(item.count || 0),
        percentage: Number(item.percentage || 0),
      }
    }).filter((item) => item.key),
    dimensions: (Array.isArray(root.dimensions) ? root.dimensions : []).map((value) => {
      const item = asRecord(value)
      return {
        key: String(item.key || ''),
        average: numberValue(item.average),
        median: numberValue(item.median),
        currentScore: numberValue(item.current_score, item.currentScore),
        sampleCount: Number(item.sample_count ?? item.sampleCount ?? 0),
        minimumPeerCount: Number(item.minimum_peer_count ?? item.minimumPeerCount ?? 0),
        sampleStatus: String(item.sample_status ?? item.sampleStatus ?? ''),
      }
    }).filter((item) => item.key),
    current: {
      score: numberValue(current.score),
      rank: numberValue(current.rank),
      peerCount: numberValue(current.peer_count, current.peerCount),
      percentile: numberValue(current.percentile),
      sampleStatus: String(current.sample_status ?? current.sampleStatus ?? ''),
    },
    boundary: String(root.boundary || '仅在同类基金内比较，不构成投资建议。'),
  }
}

function EvaluationStatisticsPanel({ fundCode, window, windowLabel }: { fundCode: string; window: string; windowLabel: string }) {
  const requestKey = `${fundCode}:${window}`
  const [showAllRanking, setShowAllRanking] = useState(false)
  const [result, setResult] = useState<{
    key: string
    data: FundEvaluationStatistics | null
    error: string
  }>({ key: '', data: null, error: '' })

  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/funds/${encodeURIComponent(fundCode)}/evaluation-statistics?window=${encodeURIComponent(window)}`, {
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload.error || '同类评分统计不可用')
        return normalizeEvaluationStatistics(payload)
      })
      .then((data) => setResult({ key: requestKey, data, error: '' }))
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return
        setResult({
          key: requestKey,
          data: null,
          error: reason instanceof Error ? reason.message : '同类评分统计不可用',
        })
      })
    return () => controller.abort()
  }, [fundCode, requestKey, window])

  const statistics = result.key === requestKey ? result.data : null
  const error = result.key === requestKey ? result.error : ''
  const loading = result.key !== requestKey
  const maxBucketCount = Math.max(1, ...(statistics?.distribution.map((item) => item.count) || []))
  const currentScore = statistics?.current.score
  const rankingPreview = statistics?.ranking.slice(0, 10) || []
  const currentRanking = statistics?.ranking.find((item) => item.isCurrent)
  const rankingRows = showAllRanking || !statistics
    ? statistics?.ranking || []
    : currentRanking && !rankingPreview.some((item) => item.windCode === currentRanking.windCode)
      ? [...rankingPreview, currentRanking]
      : rankingPreview
  const unscoredLabels: Record<string, string> = {
    insufficient_history: '历史不足',
    invalid_metric_range: '指标超出有效范围',
    missing_required_metrics: '核心指标缺失',
    insufficient_evidence: '证据不足',
  }
  const unscoredText = statistics
    ? Object.entries(statistics.unscoredSummary)
      .filter(([, count]) => count > 0)
      .map(([reason, count]) => `${unscoredLabels[reason] || reason} ${count} 只`)
      .join(' · ')
    : ''

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><BarChart3 className="h-5 w-5 text-[#28745c]" />同类评分统计</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">{windowLabel}可比量化口径；用于看同类分布，不替代上方正式综合评分。</p>
        </div>
        {statistics ? <div className="text-right text-xs text-[#67746d]"><div className="font-bold text-[#2c4438]">{statistics.peerGroup || '同类组待确认'}</div><div className="mt-1">可评分 {statistics.scoredPeerCount} / {statistics.classifiedPeerCount} 只 · 覆盖 {statistics.coverageRate.toFixed(0)}%</div></div> : null}
      </div>

      {loading ? <div className="px-6 py-12 text-center text-sm text-[#748079]">正在统计同类基金…</div> : error ? <div className="px-6 py-10 text-center text-sm text-[#915248]">{error}</div> : statistics ? (
        <>
          {statistics.status !== 'sufficient' ? <div className="border-b border-[#ead7ad] bg-[#fff8e8] px-5 py-3 text-xs leading-6 text-[#73541e]">有效样本 {statistics.scoredPeerCount} 只，最低需要 {statistics.minimumPeerCount} 只；以下仅展示数据覆盖，不形成有效同类结论。</div> : null}
          <div className="grid gap-px bg-[#e2e7e3] sm:grid-cols-4">
            {[
              ['同类平均', statistics.summary.average],
              ['同类中位数', statistics.summary.median],
              ['最高分', statistics.summary.highest],
              ['最低分', statistics.summary.lowest],
            ].map(([label, value]) => (
              <div key={String(label)} className="bg-[#f7f9f7] p-4"><div className="text-[11px] text-[#7a8580]">{label}</div><div className="mt-1 text-xl font-bold text-[#25352d]">{typeof value === 'number' ? value.toFixed(1) : '—'}</div></div>
            ))}
          </div>
          <div className="grid gap-8 p-5 sm:p-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(18rem,0.8fr)]">
            <div>
              <div className="flex items-center justify-between gap-4"><h3 className="text-sm font-bold text-[#314139]">评分分布</h3><span className="text-[11px] text-[#7b8680]">{statistics.current.rank && statistics.current.peerCount ? `本基金同类第 ${statistics.current.rank} / ${statistics.current.peerCount}` : '当前名次待样本满足后显示'}</span></div>
              <div className="mt-5 flex h-36 items-end gap-3 border-b border-[#cad4ce] px-2">
                {statistics.distribution.map((bucket) => {
                  const containsCurrent = currentScore != null && currentScore >= bucket.lower && (bucket.upper === 100 ? currentScore <= bucket.upper : currentScore < bucket.upper)
                  return (
                    <div key={bucket.key} className="flex h-full min-w-0 flex-1 flex-col justify-end text-center">
                      <div className="mb-2 text-[10px] font-bold text-[#607069]">{bucket.count}</div>
                      <div className={`mx-auto w-full max-w-16 ${containsCurrent ? 'bg-[#173f35]' : 'bg-[#84aa99]'}`} style={{ height: `${Math.max(bucket.count ? 8 : 2, bucket.count / maxBucketCount * 100)}%` }} />
                      <div className="mt-2 pb-2 text-[10px] text-[#7f8a84]">{bucket.label}</div>
                    </div>
                  )
                })}
              </div>
              <p className="mt-3 text-[11px] leading-5 text-[#7b8680]">深色柱表示本基金可比评分所在区间。可比评分只采用同类都能横向核对的指标。</p>
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#314139]">维度对照</h3>
              <div className="mt-4 space-y-4">
                {statistics.dimensions.length ? statistics.dimensions.map((dimension) => (
                  <div key={dimension.key}>
                    <div className="flex items-center justify-between gap-3 text-xs"><span className="font-bold text-[#536159]">{dimensionLabels[dimension.key] || dimension.key}</span><span className="text-[#68756e]">本基金 {dimension.currentScore == null ? '—' : dimension.currentScore.toFixed(1)} · 同类均值 {dimension.average == null ? '—' : dimension.average.toFixed(1)}</span></div>
                    <div className="relative mt-2 h-1.5 bg-[#e2e8e4]"><div className="h-full bg-[#84aa99]" style={{ width: `${Math.max(0, Math.min(100, dimension.average || 0))}%` }} />{dimension.currentScore != null ? <span className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2 bg-[#173f35]" style={{ left: `${Math.max(0, Math.min(100, dimension.currentScore))}%` }} /> : null}</div>
                    <div className="mt-1 text-[10px] text-[#929b96]">有效样本 {dimension.sampleCount} 只</div>
                  </div>
                )) : <p className="text-xs leading-6 text-[#858f8a]">当前类别的维度样本不足。</p>}
              </div>
            </div>
          </div>
          <div className="border-t border-[#e3e7e4]">
            <div className="flex flex-wrap items-start justify-between gap-3 px-5 py-4 sm:px-6">
              <div>
                <h3 className="text-sm font-bold text-[#314139]">同类评分结果</h3>
                <p className="mt-1 text-[11px] leading-5 text-[#7b8680]">仅排列 {statistics.peerGroup || '当前同类组'} 在 {windowLabel} 窗口下的可比评分。</p>
              </div>
              <div className="text-right text-[11px] leading-5 text-[#7b8680]">
                <div>已评分 {statistics.ranking.length} 只</div>
                {unscoredText ? <div>未评分：{unscoredText}</div> : null}
              </div>
            </div>
            {rankingRows.length ? (
              <div className="overflow-x-auto border-t border-[#edf0ed]">
                <table className="min-w-[760px] w-full text-left text-xs">
                  <thead className="bg-[#f6f8f6] text-[11px] text-[#718078]">
                    <tr>
                      <th className="px-4 py-3 font-medium">排名</th>
                      <th className="px-4 py-3 font-medium">基金</th>
                      <th className="px-4 py-3 font-medium">评分</th>
                      <th className="px-4 py-3 font-medium">核心维度</th>
                      <th className="px-4 py-3 font-medium">数据覆盖</th>
                      <th className="px-4 py-3 text-right font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#edf0ed]">
                    {rankingRows.map((item) => (
                      <tr key={item.windCode} className={item.isCurrent ? 'bg-[#f0f7f3]' : 'bg-white'}>
                        <td className="px-4 py-3 font-bold text-[#245f4a]">{item.rank}</td>
                        <td className="px-4 py-3">
                          <div className="font-bold text-[#2c3b34]">{item.name}</div>
                          <div className="mt-1 text-[10px] text-[#8b9590]">{item.windCode}{item.fundType ? ` · ${item.fundType}` : ''}{item.isCurrent ? ' · 当前基金' : ''}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-bold text-[#173f35]">{item.score.toFixed(1)} <span className="text-[10px] text-[#748079]">{item.grade}</span></div>
                          <div className="mt-1 text-[10px] text-[#8b9590]">百分位 {item.percentile.toFixed(0)}%</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex max-w-[21rem] flex-wrap gap-1.5">
                            {item.dimensionScores.slice(0, 3).map((dimension) => (
                              <span key={dimension.key} className="border border-[#dce5df] bg-[#f8faf8] px-2 py-1 text-[10px] text-[#5f6f67]">{dimensionLabels[dimension.key] || dimension.key} {dimension.score.toFixed(0)}</span>
                            ))}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-bold text-[#4c5d55]">{item.dataCoverage.availableMetricCount} / {item.dataCoverage.requiredMetricCount}</div>
                          <div className="mt-1 text-[10px] text-[#8b9590]">{item.dataCoverage.coverageRate.toFixed(0)}%</div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex justify-end gap-3 whitespace-nowrap">
                            <Link href={`/funds/${encodeURIComponent(item.windCode)}`} className="font-bold text-[#28745c] hover:underline">查看详情</Link>
                            {!item.isCurrent ? <Link href={`/compare?${new URLSearchParams({ codes: `${fundCode},${item.windCode}` }).toString()}`} className="font-bold text-[#756039] hover:underline">与本基金对比</Link> : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <div className="border-t border-[#edf0ed] px-5 py-8 text-center text-xs text-[#7b8680]">当前窗口还没有可排序的同类评分。</div>}
            {statistics.ranking.length > 10 ? (
              <div className="border-t border-[#edf0ed] px-5 py-3 text-center">
                <button type="button" onClick={() => setShowAllRanking((value) => !value)} className="text-xs font-bold text-[#28745c] hover:underline">{showAllRanking ? '收起榜单' : `查看全部 ${statistics.ranking.length} 只`}</button>
              </div>
            ) : null}
          </div>
          <div className="border-t border-[#e3e7e4] bg-[#fffaf0] px-5 py-3 text-[11px] leading-5 text-[#765d2c]">{statistics.boundary}</div>
        </>
      ) : null}
    </section>
  )
}

function EvaluationHistoryPanel({
  fundCode,
  window,
  windowLabel,
  initialItems,
}: {
  fundCode: string
  window: string
  windowLabel: string
  initialItems: FundEvaluationHistoryItem[]
}) {
  const [items, setItems] = useState(initialItems)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const selectedItems = items.filter((item) => item.evaluationWindow === window)
  const latest = selectedItems[0]
  const oldest = selectedItems[selectedItems.length - 1]
  const historyComparable = selectedItems.slice(0, -1).every((item) => item.change?.comparable !== false)
  const scoreChange = historyComparable && latest?.overallScore != null && oldest?.overallScore != null
    ? latest.overallScore - oldest.overallScore
    : null

  async function saveEvaluation() {
    setSaving(true)
    setMessage('')
    try {
      const response = await fetch(`/api/funds/${encodeURIComponent(fundCode)}/evaluation-history?window=${encodeURIComponent(window)}`, {
        method: 'POST',
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '保存失败')
      const history = asRecord(payload.history)
      const savedWindowItems = (Array.isArray(history.items) ? history.items : [])
        .map(normalizeHistoryItem)
        .filter((item) => item.id)
      setItems((current) => [
        ...current.filter((item) => item.evaluationWindow !== window),
        ...savedWindowItems,
      ].sort((left, right) => right.createdAt.localeCompare(left.createdAt)))
      setMessage(String(payload.message || (payload.status === 'unchanged' ? '评价没有变化，未重复保存。' : '本次评价已保存。')))
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><History className="h-5 w-5 text-[#28745c]" />评分历史</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">只在你点击保存时留档，用于比较分数、同类名次和方法版本变化。</p>
        </div>
        <div className="text-right">
          <button type="button" onClick={() => void saveEvaluation()} disabled={saving} className="inline-flex h-10 items-center gap-2 rounded-md bg-[#173f35] px-4 text-xs font-bold text-white hover:bg-[#225747] disabled:cursor-wait disabled:opacity-60">
            <Save className="h-4 w-4" />{saving ? '正在保存' : `保存${windowLabel}评价`}
          </button>
          {message ? <p className="mt-2 text-[11px] text-[#607069]">{message}</p> : null}
        </div>
      </div>

      {selectedItems.length ? (
        <>
          <div className="grid gap-px bg-[#e2e7e3] sm:grid-cols-3">
            <div className="bg-[#f7f9f7] p-4"><div className="text-[11px] text-[#7a8580]">已保存记录</div><div className="mt-1 text-xl font-bold">{selectedItems.length}</div></div>
            <div className="bg-[#f7f9f7] p-4"><div className="text-[11px] text-[#7a8580]">最近评分</div><div className="mt-1 text-xl font-bold text-[#17604a]">{latest.overallScore == null ? '待补' : latest.overallScore.toFixed(1)}</div></div>
            <div className="bg-[#f7f9f7] p-4"><div className="text-[11px] text-[#7a8580]">首尾变化</div><div className={`mt-1 text-xl font-bold ${!historyComparable || scoreChange == null || scoreChange === 0 ? 'text-[#536159]' : scoreChange > 0 ? 'text-[#17604a]' : 'text-[#955047]'}`}>{historyComparable ? deltaText(scoreChange, ' 分') : '评价口径已变化'}</div></div>
          </div>
          <div className="divide-y divide-[#e4e8e4]">
            {selectedItems.slice(0, 8).map((item, index) => (
              <article key={item.id} className="grid gap-4 p-5 sm:grid-cols-[9rem_minmax(0,1fr)_auto] sm:items-center sm:p-6">
                <div><div className="text-sm font-bold text-[#26342d]">{formatDate(item.createdAt)}</div><div className="mt-1 text-[10px] text-[#8a948f]">数据截至 {formatDate(item.asOfDate)}</div></div>
                <div>
                  <div className="flex flex-wrap items-center gap-2"><strong className="text-2xl text-[#173f35]">{item.overallScore == null ? '待补' : item.overallScore.toFixed(1)}</strong>{item.overallGrade ? <span className="rounded-sm bg-[#e4efe9] px-2 py-1 text-[10px] font-bold text-[#28654f]">{item.overallGrade} 级</span> : null}<span className="text-xs text-[#66726c]">{item.peerRank && item.peerCount ? `同类第 ${item.peerRank} / ${item.peerCount}` : '同类名次待补'}</span></div>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[#7d8882]"><span>{item.peerGroupName || '同类组待补'}</span><span>{item.methodologyVersion || '方法版本待补'}</span>{item.evidenceCoverage.coveragePercent != null ? <span>证据覆盖 {item.evidenceCoverage.coveragePercent.toFixed(0)}%</span> : null}{item.change?.methodologyChanged ? <span className="font-bold text-[#8a6220]">方法版本已变化</span> : null}{item.change?.peerGroupChanged ? <span className="font-bold text-[#8a6220]">同类组已变化</span> : null}</div>
                  {item.change?.summary ? <p className={`mt-2 text-xs leading-5 ${item.change.comparable ? 'text-[#536159]' : 'font-bold text-[#87601f]'}`}>{item.change.summary}</p> : null}
                </div>
                <div className="text-left sm:text-right"><div className={`text-sm font-bold ${item.change?.comparable === false || item.change?.scoreDelta == null || item.change.scoreDelta === 0 ? 'text-[#68746e]' : item.change.scoreDelta > 0 ? 'text-[#17604a]' : 'text-[#955047]'}`}>{index === selectedItems.length - 1 || !item.change ? '首次记录' : item.change.comparable === false ? '不宜直接比较' : `评分 ${deltaText(item.change.scoreDelta)}`}</div>{item.change?.comparable !== false && item.change?.rankChange != null ? <div className="mt-1 text-[11px] text-[#7d8882]">名次 {item.change.rankChange > 0 ? `上升 ${item.change.rankChange.toFixed(0)}` : item.change.rankChange < 0 ? `下降 ${Math.abs(item.change.rankChange).toFixed(0)}` : '不变'}</div> : null}</div>
              </article>
            ))}
          </div>
        </>
      ) : <div className="px-6 py-10 text-center text-sm text-[#748079]">还没有保存过{windowLabel}评价。点击右上角即可建立第一条记录。</div>}
      <div className="border-t border-[#e3e7e4] bg-[#fffaf0] px-5 py-3 text-[11px] leading-5 text-[#765d2c]">历史评分用于研究复核，不构成投资建议；Barra 和 Brinson 不参与评分。</div>
    </section>
  )
}

const contractBaseLabels: Record<string, string> = {
  composite: '中债综合指数',
  new_composite: '中债新综合指数',
  total: '中债总指数',
}

const contractPriceLabels: Record<string, string> = {
  full_price: '全价',
  wealth: '财富',
  total_wealth: '总财富合同写法',
  unspecified: '合同未注明',
}

const contractTenorLabels: Record<string, string> = {
  all: '全期限',
  under_1y: '1年以下',
  '1_3y': '1—3年',
  '0_3y': '0—3年',
  '0_5y': '0—5年',
  '3_5y': '3—5年',
  '1_5y': '1—5年',
  '3_7y': '3—7年',
  '5_10y': '5—10年',
  '7_10y': '7—10年',
  over_10y: '10年以上',
}

export default function SimpleFundDetailClient({ fund, nav, evaluationWindows, evaluationHistory, assessmentSummary, detailHighlights, plainLanguageBrief, researchMemos, dataQuality, shareClasses, managerHistory, managerTenurePerformance, assetAllocation, drawdownRecovery, periodPerformance, fofHoldings, bondAnomaly, bondDuration, bondHoldings, holderStructure, holdingSnapshot, holdingChanges, holdingStyle, holdingExperience, productProfile }: Props) {
  const [window, setWindow] = useState<(typeof windows)[number]['value']>('1y')
  const selectedWindow = windows.find((item) => item.value === window) || windows[1]
  const evaluation = evaluationWindows[window] || evaluationWindows['1y']
  const typedFund = fund as SimpleFund
  const selectedRolling = windowMetrics(typedFund, window)
  const metricStartDate = typeof selectedRolling.window_start_date === 'string' ? selectedRolling.window_start_date : ''
  const metricEndDate = typeof selectedRolling.window_end_date === 'string' ? selectedRolling.window_end_date : ''
  const metricObservations = numberValue(selectedRolling.actual_observations, selectedRolling.observations, selectedWindow.observations) || selectedWindow.observations
  const selectedNav = useMemo(
    () => chartWindow(nav, metricObservations, metricStartDate, metricEndDate),
    [metricEndDate, metricObservations, metricStartDate, nav],
  )
  const chartSeries = useMemo(() => buildChartSeries(selectedNav), [selectedNav])
  const marketEnvironment = useMemo(() => buildFundMarketEnvironment(selectedNav), [selectedNav])
  const chartData = chartSeries.data
  const chartMatchesEvaluation = Boolean(
    metricStartDate
    && metricEndDate
    && chartSeries.startDate === metricStartDate
    && chartSeries.endDate === metricEndDate
    && chartSeries.observations === metricObservations,
  )
  const professionalScoreReady = evaluation.score != null
  const scoreIsPartial = evaluation.status === 'partial'
  const usablePeerMetrics = evaluation.peerMetrics.filter((metric) => metric.sampleStatus === 'sufficient' && metric.percentile != null)
  const manager = managerName(typedFund)
  const managers = managerNames(typedFund)
  const researchProfile = asRecord(fund.researchProfile)
  const selectedReturn = returnMetric(typedFund, window)
  const selectedDrawdown = drawdownMetric(typedFund, window)
  const selectedVolatility = volatilityMetric(typedFund, window)
  const selectedSharpe = sharpeMetric(typedFund, window)
  const selectedWindowLabel = windowLabels[window] || window
  const declaredBaseFee = baseFeeRate(fund)
  const feePeerMetric = evaluation.peerMetrics.find((metric) => metric.key === 'expense_ratio' && metric.sampleStatus === 'sufficient')
  const company = fund.company || '基金公司待补充'
  const managerTenureStart = typeof researchProfile.managerTenureStart === 'string'
    ? researchProfile.managerTenureStart
    : ''
  const classification = evaluation.peerGroup || '专业分类待确认'
  const benchmark = evaluation.benchmark || String(fund.benchmark || '') || '基准待补充'
  const contractBenchmark = String(fund.contractBenchmark || fund.benchmark || '') || '合同基准待补充'
  const contractDimensions = evaluation.contractDimensions
  const benchmarkDetail = benchmarkComposition(evaluation.benchmarkComponents)
  const analysisHref = `/analysis?${new URLSearchParams({ fundCode: fund.windCode }).toString()}`
  const attributionHref = `/analysis/advanced?${new URLSearchParams({ fundCode: fund.windCode }).toString()}`
  const assessmentStyleStatus = assessmentSummary.styleEvidence.labels.length
    ? '量化确认'
    : assessmentSummary.styleEvidence.status === 'peer_percentile_neutral'
      ? '量化中性'
      : assessmentSummary.styleEvidence.status === 'descriptor_ready'
        ? '原始描述'
        : assessmentSummary.styleEvidence.memoLabels.length
          ? '纪要语境'
          : '待补证据'
  const assessmentStyleHeadline = assessmentSummary.styleEvidence.labels.length
    ? assessmentSummary.styleEvidence.labels.slice(0, 3).join(' · ')
    : assessmentSummary.styleEvidence.status === 'peer_percentile_neutral'
      ? '同类差异不显著'
      : assessmentSummary.styleEvidence.memoLabels.slice(0, 3).join(' · ') || '暂无标签'
  const styleDriftStatus = assessmentSummary.styleDriftEvidence.level === 'low'
    ? '基本稳定'
    : assessmentSummary.styleDriftEvidence.level === 'medium'
      ? '有所变化'
      : assessmentSummary.styleDriftEvidence.level === 'high'
        ? '变化明显'
        : '待补数据'
  const isFof = evaluation.methodology.profileKey.startsWith('fof_')

  return (
    <div className="space-y-7">
      <section className="border-b border-[#dce1dc] pb-7">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <Link href="/discover" className="inline-flex items-center gap-2 text-xs font-bold text-[#28745c]"><ArrowLeft className="h-4 w-4" />返回找基金</Link>
          <GenerateFundReportButton windCode={fund.windCode} />
        </div>
        <div className="mt-5 grid gap-6 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-xs text-[#66726c]">
              <span className="font-bold text-[#28745c]">{classification}</span>
              <span>{fund.windCode}</span>
              <span>{fund.type || '类型待补充'}</span>
            </div>
            <h1 className="mt-3 break-words text-3xl font-bold leading-tight text-[#18231e] sm:text-4xl">{fund.name || fund.windCode}</h1>
            <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm text-[#65716b]">
              <span className="inline-flex items-center gap-2"><UserRound className="h-4 w-4 text-[#28745c]" />{managers}</span>
              <span>{company}</span>
              {managerTenureStart ? <span>现任团队起点 {formatDate(managerTenureStart)}</span> : null}
              <span>{styleLabel(typedFund)}</span>
              <span>{activePassiveLabels[evaluation.activePassive] || evaluation.activePassive || '管理方式待确认'}</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link href={analysisHref} className="inline-flex h-11 items-center gap-2 rounded-md bg-[#173f35] px-5 text-sm font-bold text-white hover:bg-[#225747]"><Bot className="h-4 w-4" />开始 AI 分析</Link>
            <Link href={attributionHref} className="inline-flex h-11 items-center gap-2 rounded-md border border-[#7fa18f] bg-[#edf4f0] px-5 text-sm font-bold text-[#245f4b] hover:bg-[#e2eee8]"><ChartNoAxesCombined className="h-4 w-4" />业绩归因</Link>
            <Link href="/discover" className="inline-flex h-11 items-center gap-2 rounded-md border border-[#bfc9c2] bg-white px-5 text-sm font-bold text-[#315e4d] hover:border-[#7fa18f]"><GitCompareArrows className="h-4 w-4" />找同类比较</Link>
          </div>
        </div>
      </section>

      <section className="grid overflow-hidden border border-[#dbe1dc] bg-white sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-8">
        {[
          ['最新净值', fund.nav == null ? '—' : fund.nav.toFixed(4), formatDate(fund.navDate)],
          [`${selectedWindowLabel}收益`, formatPercent(selectedReturn), '基金真实净值口径'],
          [`${selectedWindowLabel}最大回撤`, formatPercent(selectedDrawdown), '越小通常越稳'],
          [`${selectedWindowLabel}年化波动`, formatPercent(selectedVolatility), '净值波动幅度'],
          [`${selectedWindowLabel} Sharpe`, selectedSharpe?.toFixed(2) || '—', '风险调整后收益'],
          ['基金规模', formatAsset(fund.totalAsset), '单位：亿元'],
          ['基础费率', formatPercent(declaredBaseFee, 2), feePeerMetric?.rank && feePeerMetric.peerCount ? `同类第 ${feePeerMetric.rank} / ${feePeerMetric.peerCount} 名` : '管理费 + 托管费'],
          ['成立日期', formatDate(fund.establishmentDate), '基础档案'],
        ].map(([label, value, note], index) => (
          <div key={label} className={`min-w-0 p-5 ${index ? 'border-t border-[#e4e8e4] sm:border-l sm:border-t-0' : ''} ${index > 1 ? 'sm:border-t xl:border-t-0' : ''} ${index > 0 && index % 2 === 0 ? 'sm:border-l-0 xl:border-l' : ''}`}>
            <div className="text-xs text-[#748079]">{label}</div>
            <div className="mt-2 break-words text-xl font-bold text-[#1d2923]">{value}</div>
            <div className="mt-2 text-[11px] text-[#919a95]">{note}</div>
          </div>
        ))}
      </section>

      <PlainLanguageBriefPanel brief={plainLanguageBrief} />

      <FundDataQualityPanel snapshot={dataQuality} />

      <FundProductProfilePanel profile={productProfile} />

      <FundShareClassPanel snapshot={shareClasses} />

      <FundManagerHistoryPanel snapshot={managerHistory} />

      <FundManagerTenurePerformancePanel snapshot={managerTenurePerformance} />

      <section className="overflow-hidden border border-[#cbdad2] bg-white">
        <div className="grid gap-5 border-b border-[#dfe7e2] bg-[#f3f7f4] p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold text-[#28745c]"><CheckCircle2 className="h-4 w-4" />综合评价</div>
            <h2 className="mt-3 text-xl font-bold leading-8 text-[#1b2922]">{assessmentSummary.verdict || '当前证据不足，暂不形成综合结论。'}</h2>
            <p className="mt-2 text-xs leading-6 text-[#68746e]">{assessmentSummary.peerGroup || classification} · {assessmentSummary.boundary || '基金评价不提供买卖建议。'}</p>
          </div>
          <div className={`min-w-[8.5rem] border px-5 py-4 text-center ${assessmentSummary.score == null ? 'border-[#dccb9e] bg-[#fff9eb]' : 'border-[#b9d5c8] bg-white'}`}>
            <div className="text-[11px] font-bold text-[#65736c]">专业评分</div>
            <div className={`mt-2 text-3xl font-bold ${assessmentSummary.score == null ? 'text-[#8a6a2c]' : 'text-[#17604a]'}`}>{assessmentSummary.score == null ? '待补' : assessmentSummary.score.toFixed(1)}</div>
            <div className="mt-1 text-[10px] text-[#7b8781]">{assessmentSummary.grade ? `${assessmentSummary.grade} 级` : '受证据门禁约束'}</div>
          </div>
        </div>

        <div className="grid gap-px bg-[#dfe6e1] md:grid-cols-2 xl:grid-cols-4">
          <AssessmentEvidenceCard
            title="量化评价"
            status={assessmentSummary.score == null ? '待补数据' : '已完成'}
            tone={assessmentSummary.score == null ? 'warning' : 'ready'}
            headline={assessmentSummary.advantages[0] ? humanizeFactor(assessmentSummary.advantages[0]) : '暂无明确优势'}
            detail={assessmentSummary.risks[0] ? humanizeFactor(assessmentSummary.risks[0]) : '当前没有额外量化警报。'}
          />
          <AssessmentEvidenceCard
            title="经理团队"
            status={assessmentSummary.managerStabilityEvidence.status === 'stable_3y' ? '稳定三年+' : assessmentSummary.managerStabilityEvidence.status === 'recent_change' ? '近期变动' : assessmentSummary.managerStabilityEvidence.status === 'unavailable' ? '待补数据' : '已有记录'}
            tone={assessmentSummary.managerStabilityEvidence.status === 'stable_3y' || assessmentSummary.managerStabilityEvidence.status === 'established_team' ? 'ready' : 'warning'}
            headline={assessmentSummary.managerStabilityEvidence.label || '经理任职历史待补'}
            detail={assessmentSummary.managerStabilityEvidence.note || '经理变动只作为解释证据，不直接改变评分。'}
          />
          <AssessmentEvidenceCard
            title="规模趋势"
            status={assessmentSummary.scaleTrendEvidence.status === 'stable' ? '基本稳定' : assessmentSummary.scaleTrendEvidence.status === 'small_scale' ? '规模偏小' : assessmentSummary.scaleTrendEvidence.status === 'shrinking' ? '明显缩水' : assessmentSummary.scaleTrendEvidence.status === 'rapid_growth' ? '增长较快' : assessmentSummary.scaleTrendEvidence.status === 'insufficient_evidence' ? '待补数据' : '已有记录'}
            tone={assessmentSummary.scaleTrendEvidence.status === 'stable' || assessmentSummary.scaleTrendEvidence.status === 'growing' ? 'ready' : 'warning'}
            headline={assessmentSummary.scaleTrendEvidence.label || '规模趋势待补'}
            detail={assessmentSummary.scaleTrendEvidence.note || '规模趋势只作为容量和持续性证据，不直接改变评分。'}
          />
          <AssessmentEvidenceCard
            title="回撤修复"
            status={assessmentSummary.drawdownRecoveryEvidence.status === 'near_high' ? '接近前高' : assessmentSummary.drawdownRecoveryEvidence.status === 'minor_drawdown' ? '小幅回撤' : assessmentSummary.drawdownRecoveryEvidence.status === 'current_drawdown' ? '明显回撤' : assessmentSummary.drawdownRecoveryEvidence.status === 'deep_unrecovered' ? '长期未修复' : '待补数据'}
            tone={assessmentSummary.drawdownRecoveryEvidence.status === 'near_high' || assessmentSummary.drawdownRecoveryEvidence.status === 'minor_drawdown' ? 'ready' : 'warning'}
            headline={assessmentSummary.drawdownRecoveryEvidence.label || '回撤修复待补'}
            detail={assessmentSummary.drawdownRecoveryEvidence.note || '回撤修复只描述历史风险，不直接改变评分。'}
          />
          <AssessmentEvidenceCard
            title="风格标签"
            status={assessmentStyleStatus}
            tone={assessmentSummary.styleEvidence.labels.length || assessmentSummary.styleEvidence.status === 'peer_percentile_neutral' ? 'ready' : 'warning'}
            headline={assessmentStyleHeadline}
            detail={assessmentSummary.styleEvidence.note}
          />
          <AssessmentEvidenceCard
            title="风格变化"
            status={styleDriftStatus}
            tone={assessmentSummary.styleDriftEvidence.level === 'low' ? 'ready' : 'warning'}
            headline={assessmentSummary.styleDriftEvidence.label || '公开持仓风格变化待补'}
            detail={assessmentSummary.styleDriftEvidence.note || '至少需要两个可比较的公开持仓期。'}
          />
          <AssessmentEvidenceCard
            title="调研纪要"
            status={assessmentSummary.researchEvidence.status === 'fund_specific' ? '基金专属' : assessmentSummary.researchEvidence.status === 'manager_level' ? '经理层' : '暂无纪要'}
            tone={assessmentSummary.researchEvidence.status === 'fund_specific' ? 'ready' : 'warning'}
            headline={assessmentSummary.researchEvidence.latestTitle || `${assessmentSummary.researchEvidence.count} 份关联纪要`}
            detail={`${assessmentSummary.researchEvidence.note}${assessmentSummary.researchEvidence.count ? `（基金专属 ${assessmentSummary.researchEvidence.fundLevelCount}，经理层 ${assessmentSummary.researchEvidence.managerLevelCount}）` : ''}`}
          />
          <AssessmentEvidenceCard
            title="Barra / Brinson"
            status={assessmentSummary.attributionEvidence.status === 'not_run' ? '现场运行' : assessmentSummary.attributionEvidence.status === 'ok' ? '正式结果' : assessmentSummary.attributionEvidence.status === 'partial_evidence' ? '部分证据' : '证据不足'}
            tone={assessmentSummary.attributionEvidence.status === 'ok' ? 'ready' : 'warning'}
            headline={assessmentSummary.attributionEvidence.headline || '尚未运行现场归因'}
            detail={assessmentSummary.attributionEvidence.detail || '归因只用于解释，不参与评分。'}
          />
        </div>
      </section>

      <section>
        <div className="flex flex-wrap items-end justify-between gap-3 pb-4">
          <div>
            <h2 className="text-lg font-bold">亮点与风险证据</h2>
            <p className="mt-1 text-xs leading-6 text-[#7a8580]">只在同类有效样本充足且有利分位≥80% 或≤20% 时下结论；Barra / Brinson 不参与评分。</p>
          </div>
          <span className="text-xs text-[#7a8580]">{detailHighlights.length ? `${detailHighlights.length} 条可核验证据` : '当前没有达到结论门槛的证据'}</span>
        </div>
        {detailHighlights.length ? (
          <div className="grid overflow-hidden border border-[#dbe1dc] bg-[#e1e6e2] sm:grid-cols-2 xl:grid-cols-3">
            {detailHighlights.map((item) => (
              <article key={item.id} className={`p-5 ${item.tone === 'strength' ? 'bg-[#f4f8f5]' : item.tone === 'risk' ? 'bg-[#fff8f6]' : 'bg-white'}`}>
                <div className="flex items-start justify-between gap-3">
                  <span className={`text-xs font-bold ${item.tone === 'strength' ? 'text-[#28745c]' : item.tone === 'risk' ? 'text-[#98564d]' : 'text-[#59665f]'}`}>{item.label}</span>
                  <span className="shrink-0 text-[10px] text-[#87918c]">{item.tone === 'strength' ? '优势' : item.tone === 'risk' ? '风险' : '历史体验'}</span>
                </div>
                <strong className="mt-3 block text-lg text-[#1d2923]">{item.value}</strong>
                <p className="mt-2 text-xs leading-6 text-[#637069]">{item.detail}</p>
                <div className="mt-3 text-[10px] text-[#929b96]">{item.asOfDate ? `截至 ${formatDate(item.asOfDate)}` : '日期待补'} · {item.source === 'category_peer_percentile' ? '专业同类分位' : '真实净值回放'}</div>
              </article>
            ))}
          </div>
        ) : (
          <div className="border border-[#ded8c8] bg-[#fffaf0] px-5 py-6 text-sm text-[#735f35]">样本或分位未达到结论门槛，当前不强行归纳优势和风险。</div>
        )}
      </section>

      <HoldingExperiencePanel experience={holdingExperience} />

      <MarketEnvironmentPanel profile={marketEnvironment} benchmark={benchmark} windowLabel={selectedWindowLabel} />

      <section className="grid gap-7 xl:grid-cols-[minmax(0,1.55fr)_minmax(20rem,0.75fr)]">
        <div className="border border-[#dbe1dc] bg-white p-4 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="flex items-center gap-2 text-lg font-bold"><ChartNoAxesCombined className="h-5 w-5 text-[#28745c]" />历史净值</h2>
              <p className="mt-1 text-xs leading-6 text-[#7a8580]">默认使用累计净值处理分红和份额折算；累计净值缺失时才使用单位净值。</p>
            </div>
            <div className="inline-flex border border-[#cfd6d0] bg-[#f7f8f5] p-1">
              {windows.map((item) => (
                <button key={item.value} type="button" onClick={() => setWindow(item.value)} className={`h-8 px-3 text-xs font-bold ${window === item.value ? 'bg-[#173f35] text-white' : 'text-[#67736d]'}`}>{item.label}</button>
              ))}
            </div>
          </div>
          {chartData.length ? (
            <div className="mt-6 h-[310px] w-full sm:h-[390px]">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 320, height: 310 }}>
                <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 4, left: -12 }}>
                  <CartesianGrid stroke="#e6eae6" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" minTickGap={48} tick={{ fontSize: 11, fill: '#718078' }} tickLine={false} axisLine={false} />
                  <YAxis domain={['auto', 'auto']} tick={{ fontSize: 11, fill: '#718078' }} tickLine={false} axisLine={false} tickFormatter={(value) => `${Number(value).toFixed(0)}%`} />
                  <Tooltip labelFormatter={(label) => formatDate(String(label))} formatter={(value, name) => [`${Number(value).toFixed(2)}%`, name === 'fundGrowth' ? '本基金' : benchmark]} />
                  <Line type="monotone" dataKey="fundGrowth" name="fundGrowth" stroke="#176a52" strokeWidth={2.4} dot={false} connectNulls />
                  {chartData.some((point) => point.benchmarkGrowth != null) ? <Line type="monotone" dataKey="benchmarkGrowth" name="benchmarkGrowth" stroke="#9a7c45" strokeWidth={1.8} strokeDasharray="5 4" dot={false} connectNulls /> : null}
                </LineChart>
              </ResponsiveContainer>
              <div className="mt-2 flex flex-wrap gap-4 text-[11px] text-[#68746e]"><span className="inline-flex items-center gap-1.5"><i className="h-0.5 w-4 bg-[#176a52]" />本基金</span>{chartData.some((point) => point.benchmarkGrowth != null) ? <span className="inline-flex items-center gap-1.5"><i className="h-0.5 w-4 bg-[#9a7c45]" />{benchmark}</span> : null}</div>
              <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 border-t border-[#edf0ed] pt-3 text-[10px] text-[#87918c]">
                <span>{chartSeries.navBasis === 'accum_nav' ? '累计净值口径' : '单位净值口径'}</span>
                <span>{formatDate(chartSeries.startDate)} 至 {formatDate(chartSeries.endDate)}</span>
                <span>{chartSeries.observations} 个净值日 · {chartMatchesEvaluation ? '与评价窗口一致' : '按可核验区间展示'}</span>
                {chartSeries.benchmarkObservations ? <span>基准共同日期 {chartSeries.benchmarkObservations} 个 · 覆盖 {formatPercent(chartSeries.benchmarkCoverage, 0)}</span> : <span>当前没有可核验基准曲线</span>}
              </div>
            </div>
          ) : <div className="mt-6 grid h-[310px] place-items-center border border-dashed border-[#cdd5cf] px-5 text-center text-sm text-[#79847e]">当前区间没有可用净值数据</div>}
        </div>

        <div className="border border-[#dbe1dc] bg-white">
          <div className="border-b border-[#e1e6e2] p-5">
            <div className="flex items-center gap-2 text-xs font-bold text-[#28745c]"><ShieldCheck className="h-4 w-4" />专业分类</div>
            <h2 className="mt-3 text-xl font-bold text-[#1c2923]">{classification}</h2>
            <dl className="mt-5 space-y-3 text-sm">
              <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3"><dt className="text-[#7b8680]">评价基准</dt><dd className="break-words font-medium">{benchmark}</dd></div>
              {benchmarkDetail ? <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3"><dt className="text-[#7b8680]">基准构成</dt><dd className="break-words font-medium leading-6">{benchmarkDetail}</dd></div> : null}
              <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3"><dt className="text-[#7b8680]">合同基准</dt><dd className="break-words font-medium">{contractBenchmark}</dd></div>
              {contractDimensions ? <>
                <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3"><dt className="text-[#7b8680]">基础指数</dt><dd className="break-words font-medium">{contractBaseLabels[contractDimensions.baseIndex] || contractDimensions.baseIndex}</dd></div>
                <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3"><dt className="text-[#7b8680]">收益口径</dt><dd className="break-words font-medium">{contractPriceLabels[contractDimensions.priceReturn] || contractDimensions.priceReturn}</dd></div>
                <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3"><dt className="text-[#7b8680]">期限范围</dt><dd className="break-words font-medium">{contractTenorLabels[contractDimensions.tenor] || contractDimensions.tenor}</dd></div>
                <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3"><dt className="text-[#7b8680]">主基准权重</dt><dd className="break-words font-medium">{evaluation.benchmarkWeight == null ? '合同未明确' : `${evaluation.benchmarkWeight.toFixed(0)}%`}</dd></div>
              </> : null}
              <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3"><dt className="text-[#7b8680]">策略类别</dt><dd className="break-words font-medium">{evaluation.strategyFamily || fund.type || '待确认'}</dd></div>
              <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3"><dt className="text-[#7b8680]">风格标签</dt><dd className="break-words font-medium">{styleLabel(typedFund)}</dd></div>
              <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3"><dt className="text-[#7b8680]">基金经理</dt><dd className="break-words font-medium">{managers}</dd></div>
              {managerTenureStart ? <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3"><dt className="text-[#7b8680]">团队起点</dt><dd className="break-words font-medium">{formatDate(managerTenureStart)}</dd></div> : null}
              <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3"><dt className="text-[#7b8680]">管理人</dt><dd className="break-words font-medium">{company}</dd></div>
            </dl>
          </div>
          <div className="p-5">
            <p className="text-xs leading-6 text-[#66726c]">{contractDimensions ? '债券基金按基础指数、收益口径和期限严格分组；任一维度不同都不混在一起评价。' : '系统先确定专业同类组，再选择该类别的指标和权重。不同类型基金不直接比分。'}</p>
          </div>
        </div>
      </section>

      <FundPeriodPerformancePanel snapshot={periodPerformance} />

      <FundDrawdownRecoveryPanel snapshot={drawdownRecovery} />

      <section>
        <div className="flex flex-wrap items-end justify-between gap-3 pb-4">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold"><BarChart3 className="h-5 w-5 text-[#28745c]" />分类内专业评价</h2>
            <p className="mt-1 text-xs leading-6 text-[#7a8580]">当前查看 {selectedWindowLabel}；基金评分使用类别专用方法，同类样本不足时不输出综合分和同类排名。</p>
          </div>
          <div className="text-xs text-[#748079]">同类有效样本 {evaluation.validPeerCount || '—'} 只</div>
        </div>

        <div className="grid overflow-hidden border border-[#dbe1dc] bg-white lg:grid-cols-[18rem_minmax(0,1fr)]">
          <div className="border-b border-[#e0e5e1] p-6 lg:border-b-0 lg:border-r">
            {professionalScoreReady ? (
              <>
                <div className="flex items-center gap-2 text-xs font-bold text-[#28745c]"><span>类别方法评分</span>{scoreIsPartial ? <span className="rounded-sm bg-[#fff1d4] px-1.5 py-0.5 text-[10px] text-[#845f1d]">部分证据</span> : null}</div>
                <div className="mt-3 flex items-end gap-3"><strong className="text-5xl leading-none text-[#173f35]">{evaluation.score?.toFixed(1)}</strong><span className="pb-1 text-sm text-[#748079]">/ 100{evaluation.grade ? ` · ${evaluation.grade}` : ''}</span></div>
                <p className="mt-5 text-xs leading-6 text-[#66726c]">{scoreIsPartial ? '核心 1 年指标已参与评价，经理任期等辅助证据待补。' : '分数由当前基金类别的专用方法计算，AI 不参与改分。'}</p>
              </>
            ) : (
              <div className="flex gap-3 text-[#73541e]">
                <CircleAlert className="mt-0.5 h-5 w-5 shrink-0" />
                <div><strong className="text-sm">暂不输出综合分</strong><p className="mt-2 text-xs leading-6">{scoreMessage(evaluation)}</p></div>
              </div>
            )}
          </div>

          <div className="min-w-0">
            {professionalScoreReady && evaluation.dimensions.length ? (
              <div className="grid gap-px border-b border-[#e0e5e1] bg-[#e4e8e4] sm:grid-cols-2 xl:grid-cols-3">
                {evaluation.dimensions.map((dimension) => (
                  <div key={dimension.key} className="bg-white p-5">
                    <div className="flex items-center justify-between gap-3 text-xs"><span className="font-bold">{dimensionLabels[dimension.key] || dimension.key}</span><span className="text-[#28745c]">{dimension.score == null ? '—' : dimension.score.toFixed(1)}</span></div>
                    <div className="mt-3 h-1.5 overflow-hidden bg-[#e5eae6]"><div className="h-full bg-[#3a8068]" style={{ width: `${Math.max(0, Math.min(100, dimension.score || 0))}%` }} /></div>
                    <div className="mt-2 text-[11px] text-[#8a948f]">权重 {dimension.weight == null ? '—' : formatPercent(dimension.weight, 0)}</div>
                  </div>
                ))}
              </div>
            ) : null}

            {professionalScoreReady ? <EvaluationDetailPanel evaluation={evaluation} /> : null}

            <div className="grid gap-6 p-5 sm:grid-cols-2 sm:p-6">
              <div>
                <h3 className="text-sm font-bold text-[#28654f]">已确认优势</h3>
                {evaluation.positiveFactors.length ? <ul className="mt-3 space-y-2 text-xs leading-6 text-[#536159]">{evaluation.positiveFactors.slice(0, 5).map((item) => <li key={item} className="flex gap-2"><span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#28745c]" />{humanizeFactor(item)}</li>)}</ul> : <p className="mt-3 text-xs leading-6 text-[#858f8a]">暂无足够证据归纳优势。</p>}
              </div>
              <div>
                <h3 className="text-sm font-bold text-[#915248]">风险与待核对项</h3>
                {[...evaluation.negativeFactors, ...evaluation.missingItems].length ? <ul className="mt-3 space-y-2 text-xs leading-6 text-[#5e5b55]">{Array.from(new Set([...evaluation.negativeFactors, ...evaluation.missingItems])).slice(0, 5).map((item) => <li key={item} className="flex gap-2"><span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#a45d54]" />{humanizeFactor(item)}</li>)}</ul> : <p className="mt-3 text-xs leading-6 text-[#858f8a]">当前没有额外数据缺口。</p>}
              </div>
            </div>
          </div>
        </div>
      </section>

      <EvaluationStatisticsPanel
        fundCode={fund.windCode}
        window={window}
        windowLabel={selectedWindowLabel}
      />

      <EvaluationHistoryPanel
        fundCode={fund.windCode}
        window={window}
        windowLabel={selectedWindowLabel}
        initialItems={evaluationHistory}
      />

      {evaluation.sampleStatus !== 'sufficient' && professionalScoreReady ? (
        <section className="flex gap-3 border border-[#e4cc99] bg-[#fff8e8] px-5 py-4 text-sm text-[#73541e]">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0" />
          <div><strong>同类排名暂不可用</strong><p className="mt-1 text-xs leading-6">当前有效样本 {evaluation.validPeerCount} 只，最低需要 {evaluation.minimumPeerCount} 只。基金自身评分仍可查看，但不展示同类分位和排名。</p></div>
        </section>
      ) : null}

      {usablePeerMetrics.length ? (
        <section>
          <div className="pb-4">
            <h2 className="text-lg font-bold">同类位置</h2>
            <p className="mt-1 text-xs leading-6 text-[#7a8580]">当前查看 {selectedWindowLabel}；百分位越高表示同类排序越靠前，不跨类别比较。</p>
          </div>
          <div className="grid overflow-hidden border border-[#dbe1dc] bg-white sm:grid-cols-2 xl:grid-cols-4">
            {usablePeerMetrics.map((metric, index) => (
              <div key={metric.key} className={`p-5 ${index ? 'border-t border-[#e2e6e3] sm:border-l sm:border-t-0' : ''} ${index > 1 ? 'sm:border-t xl:border-t-0' : ''} ${index === 2 ? 'sm:border-l-0 xl:border-l' : ''}`}>
                <div className="text-xs font-bold text-[#59665f]">{metric.label}</div>
                <div className="mt-3 flex items-end justify-between gap-3"><strong className="text-2xl text-[#1d2923]">{metricValue(metric)}</strong><span className="text-xs font-bold text-[#28745c]">{metric.percentile?.toFixed(0)}%</span></div>
                <div className="mt-3 h-1.5 overflow-hidden bg-[#e4e9e5]"><div className="h-full bg-[#3a8068]" style={{ width: `${Math.max(0, Math.min(100, metric.percentile || 0))}%` }} /></div>
                <div className="mt-2 text-[11px] text-[#89938e]">同类第 {metric.rank || '—'} / {metric.peerCount || '—'} 名</div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <CrossMarketPeerPanel evidence={evaluation.crossMarketHolding} />

      <FundAssetAllocationPanel snapshot={assetAllocation} />

      {isFof ? <FundFofHoldingPanel snapshot={fofHoldings} /> : null}

      <FundBondDurationPanel initialSnapshot={bondDuration} fundType={String(fund.type || '')} windCode={fund.windCode} />

      <FundBondAnomalyPanel snapshot={bondAnomaly} fundType={String(fund.type || '')} />

      <FundBondHoldingPanel snapshot={bondHoldings} fundType={String(fund.type || '')} assetAllocation={assetAllocation} />

      <FundHolderStructurePanel snapshot={holderStructure} />

      <FundHoldingProfile snapshot={holdingSnapshot} fundType={String(fund.type || '')} />

      <FundHoldingChangesPanel snapshot={holdingChanges} />

      {holdingStyle.status !== 'unavailable' ? (
        <section className="overflow-hidden border border-[#dbe1dc] bg-white">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
            <div>
              <h2 className="flex items-center gap-2 text-lg font-bold"><BarChart3 className="h-5 w-5 text-[#28745c]" />公开持仓风格</h2>
              <p className="mt-1 text-xs leading-6 text-[#7a8580]">{holdingStyle.quarter || '季度待补'} · {holdingStyle.peerGroupName || '同类组待补'}。{holdingStyle.modelScope}</p>
            </div>
            <span className={`rounded-sm px-2.5 py-1 text-[11px] font-bold ${holdingStyle.status === 'peer_percentile_ready' ? 'bg-[#e2f0e8] text-[#1f684e]' : 'bg-[#fff1d2] text-[#815a16]'}`}>
              {holdingStyle.status === 'peer_percentile_ready' || holdingStyle.status === 'peer_percentile_neutral' ? `${holdingStyle.sampleSize} 只同类样本` : `样本 ${holdingStyle.sampleSize}/${holdingStyle.minimumPeerCount}`}
            </span>
          </div>
          {holdingStyle.status === 'peer_percentile_ready' || holdingStyle.status === 'peer_percentile_neutral' ? (
            <div className="p-5 sm:p-6">
              {holdingStyle.labels.length ? <div className="flex flex-wrap gap-2">{holdingStyle.labels.map((label) => <span key={label} className="rounded-sm bg-[#e7f1eb] px-3 py-1.5 text-xs font-bold text-[#28654f]">{label}</span>)}</div> : <div className="flex gap-3 border border-[#d8ded9] bg-[#f5f7f5] px-4 py-3 text-xs leading-6 text-[#5f6c65]"><CircleAlert className="mt-1 h-4 w-4 shrink-0" /><p>同类样本数量已达门槛，但同类差异不显著，因此不强行贴大盘、小盘、价值或高低波标签。</p></div>}
              <div className={`${holdingStyle.labels.length ? 'mt-5' : 'mt-4'} grid gap-px overflow-hidden border border-[#e0e5e1] bg-[#e0e5e1] sm:grid-cols-2 xl:grid-cols-4`}>
                {holdingStyle.peerPercentiles.slice(0, 8).map((item) => (
                  <div key={item.factor} className="bg-white p-4">
                    <div className="text-xs font-bold text-[#536159]">{item.label || item.factor}</div>
                    <div className="mt-2 text-lg font-bold text-[#1d2923]">{formatHoldingStyleValue(item)}</div>
                    <div className="mt-2 text-[11px] text-[#28745c]">{item.percentileLabel || `同类分位 ${item.percentile == null ? '—' : `${(item.percentile * 100).toFixed(0)}%`}`}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="p-5 sm:p-6">
              <div className="flex gap-3 border border-[#eadfbf] bg-[#fffaf0] px-4 py-3 text-xs leading-6 text-[#735b2b]"><CircleAlert className="mt-1 h-4 w-4 shrink-0" /><p>同季度同类样本不足，当前只展示原始描述子，不生成大盘、价值、成长或低波标签。</p></div>
              <div className="mt-4 grid gap-px overflow-hidden border border-[#e0e5e1] bg-[#e0e5e1] sm:grid-cols-2 xl:grid-cols-4">
                {holdingStyle.descriptors.slice(0, 8).map((item) => <div key={item.factor} className="bg-white p-4"><div className="text-xs font-bold text-[#536159]">{item.label || item.factor}</div><div className="mt-2 text-lg font-bold text-[#1d2923]">{formatHoldingStyleValue(item)}</div></div>)}
              </div>
            </div>
          )}
        </section>
      ) : null}

      <FundAttributionEvidence
        fundCode={fund.windCode}
        fundType={String(fund.type || '')}
        fullReportHref={attributionHref}
      />

      <section>
        <div className="flex flex-wrap items-end justify-between gap-3 pb-4">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold"><BookOpenText className="h-5 w-5 text-[#28745c]" />相关调研纪要</h2>
            <p className="mt-1 text-xs leading-6 text-[#7a8580]">基金专属纪要与经复核的现任经理纪要分开标注；经理层观点不外推为本基金持仓。</p>
          </div>
          <div className="flex items-center gap-4 text-xs"><span className="text-[#738078]">基金专属 {assessmentSummary.researchEvidence.fundLevelCount} · 经理层 {assessmentSummary.researchEvidence.managerLevelCount}</span><Link href="/research" className="inline-flex items-center gap-1 font-bold text-[#28745c]">打开调研库<ArrowRight className="h-4 w-4" /></Link></div>
        </div>
        {researchMemos.length ? (
          <div className="divide-y divide-[#e0e5e1] border border-[#dbe1dc] bg-white">
            {researchMemos.map((memo) => (
              <article key={memo.id} className="grid gap-4 p-5 md:grid-cols-[minmax(0,1fr)_auto] md:p-6">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] text-[#7a8580]"><span className={`rounded-sm px-2 py-1 font-bold ${memo.evidenceScope === 'manager_level' ? 'bg-[#fff1d5] text-[#7d5a1b]' : 'bg-[#e3f0e9] text-[#226148]'}`}>{memo.evidenceScope === 'manager_level' ? '经理层纪要' : '基金专属纪要'}</span><span className="inline-flex items-center gap-1"><UserRound className="h-3.5 w-3.5" />{memo.managerName || manager}</span><span className="inline-flex items-center gap-1"><CalendarDays className="h-3.5 w-3.5" />{formatDate(memo.reportDate)}</span>{memo.source ? <span>{memo.source}</span> : null}</div>
                  <h3 className="mt-2 break-words text-sm font-bold text-[#1d2923]">{memo.title || '无标题纪要'}</h3>
                  <p className="mt-2 line-clamp-2 text-xs leading-6 text-[#66726c]">{memo.summary || memo.keyPoints.join('；') || '该纪要暂无摘要。'}</p>
                </div>
                <div className="max-w-sm space-y-2 md:text-right">
                  {[...memo.fundClassifications, ...memo.fundStyleLabels].length ? <div className="flex flex-wrap items-center gap-2 md:justify-end"><span className="text-[10px] font-bold text-[#28745c]">基金专属标签</span>{[...memo.fundClassifications, ...memo.fundStyleLabels].slice(0, 5).map((tag, index) => <span key={`fund-${tag}-${index}`} className="rounded-sm bg-[#e7f1eb] px-2 py-1 text-[11px] text-[#28654f]">{tag}</span>)}</div> : null}
                  {[...memo.managerClassifications, ...memo.managerStyleLabels].length ? <div className="flex flex-wrap items-center gap-2 md:justify-end"><span className="text-[10px] font-bold text-[#86611d]">经理通用标签</span>{[...memo.managerClassifications, ...memo.managerStyleLabels].slice(0, 5).map((tag, index) => <span key={`manager-${tag}-${index}`} className="rounded-sm bg-[#fff3dc] px-2 py-1 text-[11px] text-[#77591f]">{tag}</span>)}</div> : null}
                </div>
              </article>
            ))}
          </div>
        ) : <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-10 text-center text-sm text-[#748079]">调研库中还没有绑定这只基金的纪要。</div>}
      </section>

      <section className="grid gap-3 border-t border-[#dce1dc] pt-6 md:grid-cols-3">
        <div className="flex gap-3 text-xs leading-6 text-[#65716b]"><Database className="mt-1 h-4 w-4 shrink-0 text-[#28745c]" /><span>基金档案、净值与指标均来自后端数据库。</span></div>
        <div className="flex gap-3 text-xs leading-6 text-[#65716b]"><ShieldCheck className="mt-1 h-4 w-4 shrink-0 text-[#28745c]" /><span>专业评分受分类、核心指标和同类样本门禁约束；样本不足时不输出综合分和排名。</span></div>
        <div className="flex gap-3 text-xs leading-6 text-[#65716b]"><BarChart3 className="mt-1 h-4 w-4 shrink-0 text-[#28745c]" /><span>Barra 和 Brinson 只用于解释，不改变评分。</span></div>
      </section>
    </div>
  )
}
