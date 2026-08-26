'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useMemo, useState, useTransition } from 'react'
import { ArrowLeft, BarChart3, Bot, Building2, CalendarRange, CircleAlert, ExternalLink, FileText, GitCompareArrows, Network, Plus, Search, ShieldCheck, Sparkles, X } from 'lucide-react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CamelFund } from '@/lib/backend-api'
import EvidenceTriptychStrip from './EvidenceTriptychStrip'
import DecisionSupportPanel from './DecisionSupportPanel'
import {
  asRecord,
  formatAsset,
  formatPercent,
  numberValue,
  professionalPeerGroup,
  professionalPeerGroupId,
  styleLabel,
  type SimpleFund,
  windowMetrics,
} from '@/lib/simple-fund-view'

type WindowEvaluation = {
  status: string
  sampleStatus: string
  validPeerCount: number
  minimumPeerCount: number
  score: number | null
  grade: string
  peerRank: number | null
  peerCount: number | null
  peerPercentile: number | null
}

type CalendarPeriodPerformance = {
  year: number
  label: string
  isYtd: boolean
  return: number
  coverageStatus: string
  observationCoverage: number | null
  rank: number | null
  peerCount: number
  percentile: number | null
  peerMedianReturn: number | null
  abovePeerMedian: boolean | null
}

type CalendarPerformanceSnapshot = {
  status: string
  navBasis: string
  latestNavDate: string
  peerGroupName: string
  periods: CalendarPeriodPerformance[]
  summary: {
    completePeriodCount: number
    positivePeriodCount: number
    peerRankedPeriodCount: number
    abovePeerMedianCount: number
  }
  boundary: string
}

type ManagerTenurePerformance = {
  status: string
  coverageStatus: string
  requestedStartDate: string
  actualStartDate: string
  actualEndDate: string
  coverageRatio: number | null
  observations: number
  totalReturn: number | null
  annualizedReturn: number | null
  maxDrawdown: number | null
  sharpeRatio: number | null
  peerRankingStatus: string
  peerRank: number | null
  peerCount: number | null
  peerPercentile: number | null
  scopeNote: string
}

type MultiPeriodEvidence = {
  status: string
  return6m: number | null
  return1y: number | null
  annualizedReturn1y: number | null
  annualizedReturn3y: number | null
  maxDrawdown1y: number | null
  maxDrawdown3y: number | null
  sharpeRatio3y: number | null
  annualizedReturnGap: number | null
  consistencyStatus: string
  consistencyLabel: string
  usedInScore: boolean
  dataAsOf: string
}

export type ComparisonFund = {
  fund: CamelFund
  classification: {
    status: string
    peerGroup: string
    peerGroupId: string
    benchmark: string
  }
  evaluation: {
    status: string
    sampleStatus: string
    validPeerCount: number
    minimumPeerCount: number
    score: number | null
    grade: string
  }
  evaluationWindows: Record<'6m' | '1y' | '3y', WindowEvaluation>
  holding: {
    latestQuarter: string
    reportDate: string
    announcementDate: string
    holdingCount: number
    weightBasis: string
    topTenWeight: number | null
    topTenEquityWeight: number | null
    firstStockName: string
    firstStockWeight: number | null
  }
  managers: Array<{
    id: string
    name: string
    managementYears: number | null
    beginDate: string
  }>
  managerTenureStart: string
  managerTenurePerformance: ManagerTenurePerformance
  multiPeriodEvidence: MultiPeriodEvidence
  researchMemoCount: number
  attributionEvidence: AttributionEvidenceSnippet
  styleEvidence: StyleEvidenceSnippet
  memoHighlights: MemoHighlight[]
  periodPerformance: CalendarPerformanceSnapshot
}

export type AttributionEvidenceSnippet = {
  status: string
  headline: string
  detail: string
  coverage: number | null
  formalBarraReady: boolean
  barraDescriptorReady: boolean
}

export type StyleEvidenceSnippet = {
  status: string
  scope: string
  quarter: string
  labels: string[]
  memoLabels: string[]
}

export type MemoHighlight = {
  id: string
  title: string
  reportDate: string
  managerName: string
  scope: 'fund' | 'manager' | 'other'
  summary: string
}

type AlignedFundMetrics = {
  windCode: string
  navBasis: string
  observations: number
  totalReturn: number | null
  annualizedReturn: number | null
  maxDrawdown: number | null
  annualizedVolatility: number | null
  sharpeRatio: number | null
  drawdownStatus: string
  drawdownLabel: string
  currentDrawdown: number | null
  currentUnderwaterDays: number
  worstDeclineDays: number
  worstRecoveryDays: number | null
  worstRecovered: boolean
  longestUnderwaterDays: number
  materialEpisodeCount: number
  recoveredMaterialEpisodeCount: number
}

type AlignedComparisonWindow = {
  status: string
  requestedStartDate: string
  actualStartDate: string
  actualEndDate: string
  observations: number
  actualSpanDays: number
  calendarCoverageRatio: number
  observationCoverageRatio: number
  rankingEligible: boolean
  scopeNote: string
  funds: Record<string, AlignedFundMetrics>
  chart: Array<{ date: string; values: Record<string, number> }>
}

export type AlignedComparison = {
  status: string
  methodology: string
  riskFreeRate: number
  simulationUsed: boolean
  windows: Record<'6m' | '1y' | '3y', AlignedComparisonWindow>
}

export type HoldingSimilarityPair = {
  status: string
  fundA: string
  fundB: string
  quarter: string
  reportDateA: string
  reportDateB: string
  weightBasisA: string
  weightBasisB: string
  holdingCountA: number
  holdingCountB: number
  commonHoldingCount: number
  unionHoldingCount: number
  overlapRatio: number | null
  jaccardScore: number | null
  cosineSimilarity: number | null
  similarityLevel: string
  commonHoldings: Array<{
    stockCode: string
    stockName: string
    weightA: number | null
    weightB: number | null
    overlapContribution: number | null
  }>
  missingItems: string[]
}

export type HoldingSimilaritySnapshot = {
  status: string
  methodology: string
  scope: string
  source: string
  simulationUsed: boolean
  pairCount: number
  availablePairCount: number
  missingCodes: string[]
  pairs: HoldingSimilarityPair[]
}

const colors = ['#176a52', '#a45d45', '#6b7334', '#2e6284', '#7b5384', '#8a702e']
const windows = [
  { value: '6m', label: '近 6 月' },
  { value: '1y', label: '近 1 年' },
  { value: '3y', label: '近 3 年' },
] as const

function latestMetric(fund: SimpleFund, metric: string) {
  const performance = asRecord(fund.performanceData)
  const latest = windowMetrics(fund, 'latest')
  return numberValue(performance[metric], latest[metric])
}

function trackingErrorMetric(fund: SimpleFund, window = '1y') {
  const risk = asRecord(fund.riskMetrics)
  const rolling = windowMetrics(fund, window)
  return numberValue(rolling.tracking_error, risk[`tracking_error_${window}`], window === '1y' ? risk.tracking_error : null)
}

function trackingDifferenceMetric(fund: SimpleFund, window = '1y') {
  const performance = asRecord(fund.performanceData)
  const rolling = windowMetrics(fund, window)
  return numberValue(
    rolling.tracking_difference,
    rolling.excess_return,
    performance[`tracking_difference_${window}`],
    window === '1y' ? performance.tracking_difference : null,
  )
}

function formatMoneyIncome(value: number | null | undefined) {
  return value == null || Number.isNaN(value) ? '—' : `${value.toFixed(4)} 元`
}

function formatYears(value: number | null) {
  return value == null ? '年限待补' : `${value.toFixed(1)} 年`
}

function formatDate(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

function formatSignedPercent(value: number | null, digits = 1) {
  if (value == null) return '—'
  const normalized = Math.abs(value) <= 2 ? value * 100 : value
  return `${normalized > 0 ? '+' : ''}${normalized.toFixed(digits)}%`
}

function calendarReturnTone(value: number | null) {
  if (value == null || value === 0) return 'text-[#4f5d56]'
  return value > 0 ? 'text-[#9b4f45]' : 'text-[#24705a]'
}

function drawdownStatusLabel(status: string) {
  if (status === 'deep_unrecovered') return '深度回撤未修复'
  if (status === 'current_drawdown') return '仍在明显回撤'
  if (status === 'minor_drawdown') return '处于小幅回撤'
  if (status === 'near_high') return '接近区间高位'
  return '证据待补'
}

function selectedEvaluation(item: ComparisonFund, window: '6m' | '1y' | '3y') {
  return item.evaluationWindows[window] || item.evaluation
}

function peerPositionLabel(evaluation: WindowEvaluation) {
  if (evaluation.peerRank != null && evaluation.peerCount != null) {
    return `${evaluation.peerRank.toFixed(0)} / ${evaluation.peerCount.toFixed(0)}`
  }
  return '—'
}

function holdingConcentration(item: ComparisonFund) {
  return item.holding.weightBasis === 'fund_nav'
    ? item.holding.topTenWeight
    : item.holding.topTenEquityWeight
}

function holdingBasisLabel(item: ComparisonFund) {
  return item.holding.weightBasis === 'fund_nav' ? '占基金净值' : '占股票市值'
}

function compareHref(codes: string[]) {
  return codes.length ? `/compare?${new URLSearchParams({ codes: codes.join(',') }).toString()}` : '/compare'
}

function metricLeader(
  funds: ComparisonFund[],
  value: (item: ComparisonFund) => number | null,
  direction: 'high' | 'low' = 'high',
) {
  return funds
    .map((item) => ({ item, value: value(item) }))
    .filter((row): row is { item: ComparisonFund; value: number } => row.value != null && Number.isFinite(row.value))
    .sort((left, right) => direction === 'high' ? right.value - left.value : left.value - right.value)[0] || null
}

function similarityMeta(level: string) {
  if (level === 'high') return { label: '高重合', className: 'bg-[#f7e4df] text-[#8a473f]' }
  if (level === 'medium') return { label: '中等重合', className: 'bg-[#fff0d4] text-[#7b581c]' }
  if (level === 'low') return { label: '低重合', className: 'bg-[#e4f0e9] text-[#24624c]' }
  return { label: '证据不足', className: 'bg-[#ecefed] text-[#69736e]' }
}

function managerTenureCoverageLabel(performance: ManagerTenurePerformance) {
  if (performance.coverageStatus === 'full_tenure') return '完整任期'
  if (performance.coverageStatus === 'partial_since_data_start') return '本地可见期'
  return '数据待补'
}

function managerTenurePeerLabel(performance: ManagerTenurePerformance) {
  if (performance.coverageStatus === 'partial_since_data_start') return '部分覆盖·不排名'
  if (performance.peerRank && performance.peerCount) return `${performance.peerRank} / ${performance.peerCount}`
  if (performance.peerRankingStatus === 'insufficient_peer_sample') return '同类样本不足'
  return '—'
}

function multiPeriodStatusMeta(evidence: MultiPeriodEvidence) {
  if (evidence.status === 'long_term_ready') {
    return { label: '近 3 年证据完整', className: 'bg-[#e4f0e9] text-[#24624c]' }
  }
  return { label: '近 3 年证据不足', className: 'bg-[#fff0d4] text-[#7b581c]' }
}

function formatPercentagePoints(value: number | null) {
  return value == null ? '' : `${(value * 100).toFixed(1)} 个百分点`
}

export default function SimpleComparisonClient({ funds, alignedComparison, holdingSimilarity }: { funds: ComparisonFund[]; alignedComparison: AlignedComparison | null; holdingSimilarity: HoldingSimilaritySnapshot | null }) {
  const router = useRouter()
  const [window, setWindow] = useState<(typeof windows)[number]['value']>('1y')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<CamelFund[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [isNavigating, startTransition] = useTransition()
  const selectedWindow = windows.find((item) => item.value === window) || windows[1]
  const selectedCodes = funds.map((item) => item.fund.windCode)
  const lockedPeerGroupId = funds[0]?.classification.peerGroupId || ''
  const lockedPeerGroup = funds[0]?.classification.peerGroup || ''
  const peerGroupIds = Array.from(new Set(funds.map((item) => item.classification.peerGroupId).filter(Boolean)))
  const fullyClassified = funds.every((item) => item.classification.status === 'classified' && item.classification.peerGroupId)
  const comparable = funds.length >= 2 && fullyClassified && peerGroupIds.length === 1
  const alignedWindow = alignedComparison?.windows?.[window]
  const alignedReady = alignedWindow?.status === 'available' || alignedWindow?.status === 'partial'
  const alignedRankingEligible = alignedWindow?.rankingEligible === true
  const alignedLeaderFallback = alignedReady && !alignedRankingEligible ? '部分区间不排名' : '数据待补'
  const chartData = useMemo(() => (alignedWindow?.chart || []).map((point) => ({ date: point.date, ...point.values })), [alignedWindow])
  const alignedMetric = (item: ComparisonFund, key: keyof AlignedFundMetrics) => {
    const value = alignedWindow?.funds?.[item.fund.windCode]?.[key]
    return typeof value === 'number' && Number.isFinite(value) ? value : null
  }
  const peerGroup = comparable ? funds[0].classification.peerGroup : ''
  const isMoneyMarket = peerGroup.startsWith('货币-')
  const isIndexFund = peerGroup.startsWith('指数-')
  const scoreRanking = [...funds]
    .filter((item) => selectedEvaluation(item, window).peerPercentile != null)
    .sort((left, right) => Number(selectedEvaluation(right, window).peerPercentile) - Number(selectedEvaluation(left, window).peerPercentile))
  const scoreLeader = scoreRanking[0] || null
  const scoreGap = scoreRanking.length >= 2
    ? Number(selectedEvaluation(scoreRanking[0], window).peerPercentile) - Number(selectedEvaluation(scoreRanking[1], window).peerPercentile)
    : null
  const returnLeader = alignedRankingEligible ? metricLeader(funds, (item) => alignedMetric(item, 'totalReturn')) : null
  const drawdownLeader = alignedRankingEligible ? metricLeader(funds, (item) => alignedMetric(item, 'maxDrawdown'), 'high') : null
  const sharpeLeader = alignedRankingEligible ? metricLeader(funds, (item) => alignedMetric(item, 'sharpeRatio')) : null
  const sevenDayYieldLeader = metricLeader(funds, (item) => latestMetric(item.fund as SimpleFund, 'seven_day_annualized_yield'))
  const incomePer10000Leader = metricLeader(funds, (item) => latestMetric(item.fund as SimpleFund, 'income_per_10000'))
  const assetLeader = metricLeader(funds, (item) => numberValue(item.fund.totalAsset))
  const trackingErrorLeader = metricLeader(funds, (item) => trackingErrorMetric(item.fund as SimpleFund, window), 'low')
  const trackingDifferenceLeader = metricLeader(funds, (item) => {
    const value = trackingDifferenceMetric(item.fund as SimpleFund, window)
    return value == null ? null : Math.abs(value)
  }, 'low')
  const expenseLeader = metricLeader(funds, (item) => latestMetric(item.fund as SimpleFund, 'expense_ratio'), 'low')
  const volatilityLeader = alignedRankingEligible ? metricLeader(funds, (item) => alignedMetric(item, 'annualizedVolatility'), 'low') : null
  const currentDrawdownLeader = alignedRankingEligible ? metricLeader(funds, (item) => alignedMetric(item, 'currentDrawdown')) : null
  const maxDrawdownLeader = alignedRankingEligible ? metricLeader(funds, (item) => alignedMetric(item, 'maxDrawdown')) : null
  const underwaterLeader = alignedRankingEligible ? metricLeader(funds, (item) => alignedMetric(item, 'longestUnderwaterDays'), 'low') : null
  const fundNameByCode = new Map(funds.map((item) => [item.fund.windCode, item.fund.name || item.fund.windCode]))
  const similarityPairs = holdingSimilarity?.pairs || []
  const availableSimilarityPairs = similarityPairs.filter((pair) => pair.status === 'available' && pair.overlapRatio != null)
  const highestSimilarityPair = availableSimilarityPairs[0] || null
  const calendarYears = useMemo(() => Array.from(new Set(
    funds.flatMap((item) => item.periodPerformance.periods.map((period) => period.year)),
  )).sort((left, right) => right - left).slice(0, 5), [funds])

  async function searchFunds() {
    const keyword = query.trim()
    if (!keyword) {
      setResults([])
      setSearchError('请输入基金名称或代码。')
      return
    }
    setSearching(true)
    setSearchError('')
    const params = new URLSearchParams({ search: keyword, limit: '12' })
    if (lockedPeerGroup) params.set('peerGroup', lockedPeerGroup)
    try {
      const response = await fetch(`/api/fund-browser?${params.toString()}`, { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '基金搜索失败')
      setResults(Array.isArray(payload.data) ? payload.data : [])
    } catch (error) {
      setResults([])
      setSearchError(error instanceof Error ? error.message : '基金搜索失败')
    } finally {
      setSearching(false)
    }
  }

  function addFund(fund: CamelFund) {
    if (selectedCodes.includes(fund.windCode) || funds.length >= 6) return
    const peerGroupId = professionalPeerGroupId(fund)
    if (!peerGroupId) {
      setSearchError('这只基金尚未完成标准分类，暂不能加入同类比较。')
      return
    }
    if (lockedPeerGroupId && peerGroupId !== lockedPeerGroupId) {
      setSearchError(`当前已锁定“${lockedPeerGroup}”，只能添加同类基金。`)
      return
    }
    startTransition(() => router.push(compareHref([...selectedCodes, fund.windCode])))
  }

  function removeFund(code: string) {
    startTransition(() => router.push(compareHref(selectedCodes.filter((item) => item !== code))))
  }

  return (
    <div className="space-y-7">
      <section className="border-b border-[#dce1dc] pb-7">
        <Link href="/discover" className="inline-flex items-center gap-2 text-xs font-bold text-[#28745c]"><ArrowLeft className="h-4 w-4" />返回基金浏览器</Link>
        <div className="mt-5 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-end">
          <div className="text-sm text-[#66726c]">已选 {funds.length} / 6 只 · 仅同类比较</div>
        </div>
      </section>

      <section className="border border-[#dbe1dc] bg-white p-5 sm:p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="text-lg font-bold text-[#18231e]">直接添加比较基金</h2>
            <p className="mt-1 text-xs leading-6 text-[#748079]">
              {lockedPeerGroup ? `已锁定“${lockedPeerGroup}”，搜索结果只显示同类基金。` : '先添加第一只已完成标准分类的基金，系统会自动锁定同类组。'}
            </p>
          </div>
          {funds.length ? (
            <div className="flex flex-wrap gap-2">
              {funds.map((item, index) => (
                <span key={item.fund.windCode} className="inline-flex items-center gap-2 border border-[#cfd8d2] bg-[#f6f8f6] px-3 py-2 text-xs font-semibold text-[#42524a]">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: colors[index] }} />
                  {item.fund.name || item.fund.windCode}
                  <button type="button" onClick={() => removeFund(item.fund.windCode)} disabled={isNavigating} className="text-[#87918c] hover:text-[#8c413c]" aria-label={`移出比较：${item.fund.name || item.fund.windCode}`}><X className="h-3.5 w-3.5" /></button>
                </span>
              ))}
            </div>
          ) : null}
        </div>

        <form
          className="mt-5 flex flex-col gap-3 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault()
            void searchFunds()
          }}
        >
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">搜索基金名称或代码</span>
            <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#7c8781]" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入基金名称或代码，例如 000961" className="h-11 w-full rounded-md border border-[#cbd3cd] bg-[#fbfcfb] pl-11 pr-4 text-sm outline-none focus:border-[#28745c]" />
          </label>
          <button type="submit" disabled={searching || isNavigating} className="h-11 rounded-md bg-[#173f35] px-5 text-sm font-bold text-white disabled:opacity-50">{searching ? '搜索中' : '搜索基金'}</button>
        </form>

        {searchError ? <p className="mt-3 text-sm text-[#8b5c24]">{searchError}</p> : null}
        {results.length ? (
          <div className="mt-4 divide-y divide-[#e5e9e5] border border-[#dce2dd]">
            {results.map((fund) => {
              const selected = selectedCodes.includes(fund.windCode)
              const groupId = professionalPeerGroupId(fund)
              const groupName = professionalPeerGroup(fund)
              const allowed = Boolean(groupId) && (!lockedPeerGroupId || groupId === lockedPeerGroupId)
              return (
                <div key={fund.windCode} className="flex flex-col gap-3 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-bold text-[#1d2a24]">{fund.name || fund.windCode}</div>
                    <div className="mt-1 text-xs text-[#748079]">{fund.windCode} · {groupName || '标准分类待确认'} · {fund.company || '公司待补充'}</div>
                  </div>
                  <button type="button" onClick={() => addFund(fund)} disabled={selected || !allowed || funds.length >= 6 || isNavigating} className="inline-flex h-9 shrink-0 items-center justify-center gap-2 border border-[#aebdb5] px-3 text-xs font-bold text-[#2d614f] disabled:cursor-not-allowed disabled:border-[#dde2de] disabled:text-[#a0aaa5]">
                    <Plus className="h-3.5 w-3.5" />{selected ? '已添加' : !allowed ? '不同类' : '加入比较'}
                  </button>
                </div>
              )
            })}
          </div>
        ) : null}
      </section>

      {funds.length < 2 ? (
        <section className="border border-dashed border-[#cbd3cd] bg-[#f9faf8] px-6 py-12 text-center">
          <GitCompareArrows className="mx-auto h-7 w-7 text-[#75847c]" />
          <h2 className="mt-4 text-xl font-bold text-[#26342d]">再添加 {funds.length ? '一只同类基金' : '两只同类基金'}</h2>
          <p className="mt-2 text-sm leading-7 text-[#6e7973]">选满两只后，系统会自动展示真实净值、核心指标和分维度结论。</p>
        </section>
      ) : null}

      {funds.length >= 2 && !comparable ? (
        <section className="border border-[#e1c890] bg-[#fff8e8] p-5 text-[#73541e]">
          <div className="flex gap-3">
            <CircleAlert className="mt-0.5 h-5 w-5 shrink-0" />
            <div>
              <h2 className="font-bold">这些基金不在同一个专业同类组</h2>
              <p className="mt-2 text-sm leading-7">系统已停止横向指标和净值比较。请返回基金浏览器，选择分类一致的基金。</p>
            </div>
          </div>
        </section>
      ) : comparable ? (
        <section className="flex flex-wrap items-center gap-3 border-l-4 border-[#2b775d] bg-[#eef5f1] px-5 py-4 text-sm text-[#2b5e4c]">
          <strong>{peerGroup}</strong>
          <span>同类组校验通过</span>
          <span className="text-[#6d7a74]">基准：{funds[0].classification.benchmark || '待补充'}</span>
        </section>
      ) : null}

      {comparable ? (
        <section data-testid="aligned-comparison-evidence" className="border border-[#dbe1dc] bg-white px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <strong className="text-sm text-[#26342d]">同一净值区间</strong>
              <p className="mt-1 text-xs leading-6 text-[#6f7b75]">
                {alignedReady
                  ? `${formatDate(alignedWindow.actualStartDate)} 至 ${formatDate(alignedWindow.actualEndDate)} · ${alignedWindow.observations} 个共同净值日`
                  : '当前基金缺少足够的共同净值日期，暂不输出横向曲线和同区间风险收益指标。'}
              </p>
            </div>
            <span className={`px-3 py-1.5 text-xs font-bold ${alignedRankingEligible ? 'bg-[#e8f1ec] text-[#28624e]' : 'bg-[#fff3dc] text-[#835f25]'}`}>
              {alignedRankingEligible ? '完整共同区间' : alignedReady ? '部分共同区间 · 不排名' : '共同日期不足'}
            </span>
          </div>
          <p className="mt-2 text-[11px] leading-5 text-[#859089]">所有基金只使用共同有净值的日期，累计净值优先；不使用各自不同的起点制造虚假可比性。{alignedReady ? ` 所选窗口覆盖 ${(Number(alignedWindow.calendarCoverageRatio || 0) * 100).toFixed(0)}%，共同净值密度 ${(Number(alignedWindow.observationCoverageRatio || 0) * 100).toFixed(0)}%。` : ''}</p>
          {alignedReady && !alignedRankingEligible ? <p className="mt-2 text-[11px] font-bold leading-5 text-[#835f25]">当前只展示实际可见期，不宣布收益、回撤、波动或修复速度领先。</p> : null}
        </section>
      ) : null}

      {comparable ? <EvidenceTriptychStrip funds={funds} /> : null}

      {comparable ? <DecisionSupportPanel codes={selectedCodes} nameByCode={fundNameByCode} /> : null}

      {comparable ? (
        <section data-testid="multi-period-evidence" className="overflow-hidden border border-[#dbe1dc] bg-white">
          <div className="border-b border-[#e1e6e2] p-5 sm:p-6">
            <h2 className="flex items-center gap-2 text-lg font-bold"><CalendarRange className="h-5 w-5 text-[#28745c]" />短期和长期分开看</h2>
            <p className="mt-1 text-xs leading-6 text-[#7a8580]">近 1 年领先不等于长期持续。只有近 3 年收益、回撤和 Sharpe 都完整，才标为长期证据完整。</p>
          </div>
          <div className="grid gap-px bg-[#e1e6e2] lg:grid-cols-2 xl:grid-cols-3">
            {funds.map((item) => {
              const evidence = item.multiPeriodEvidence
              const status = multiPeriodStatusMeta(evidence)
              return (
                <article key={item.fund.windCode} className="bg-white p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div><strong className="text-sm text-[#26342d]">{item.fund.name || item.fund.windCode}</strong><span className="mt-1 block text-[10px] text-[#87918c]">数据截至 {formatDate(evidence.dataAsOf)}</span></div>
                    <span className={`shrink-0 px-2.5 py-1 text-[11px] font-bold ${status.className}`}>{status.label}</span>
                  </div>
                  <div className="mt-4 grid grid-cols-3 gap-px bg-[#e5e9e6] text-center">
                    <div className="bg-[#f8faf8] p-3"><span className="text-[10px] text-[#7b8680]">近 1 年年化</span><strong className="mt-1 block text-sm">{formatPercent(evidence.annualizedReturn1y)}</strong></div>
                    <div className="bg-[#f8faf8] p-3"><span className="text-[10px] text-[#7b8680]">近 3 年年化</span><strong className="mt-1 block text-sm">{formatPercent(evidence.annualizedReturn3y)}</strong></div>
                    <div className="bg-[#f8faf8] p-3"><span className="text-[10px] text-[#7b8680]">近 3 年回撤</span><strong className="mt-1 block text-sm text-[#915248]">{formatPercent(evidence.maxDrawdown3y)}</strong></div>
                  </div>
                  <p className={`mt-4 text-xs leading-6 ${evidence.consistencyStatus === 'divergent' ? 'text-[#8a4c43]' : 'text-[#66736c]'}`}>
                    {evidence.status === 'long_term_ready'
                      ? `${evidence.consistencyLabel || '短长期一致性待补'}${evidence.annualizedReturnGap == null ? '' : `，年化收益相差 ${formatPercentagePoints(evidence.annualizedReturnGap)}`}。`
                      : '长期数据不足，只能描述当前可见的短期表现。'}
                  </p>
                </article>
              )
            })}
          </div>
        </section>
      ) : null}

      {comparable ? (
        <section className="border border-[#dbe1dc] bg-white p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs font-bold text-[#28745c]"><Sparkles className="h-4 w-4" />横向比较结论</div>
              <h2 className="mt-2 text-xl font-bold text-[#18231e]">
                {scoreLeader ? `综合评价暂列前：${scoreLeader.fund.name || scoreLeader.fund.windCode}` : '先看各维度谁更突出'}
              </h2>
              <p className="mt-2 text-sm leading-7 text-[#65716b]">
                {scoreLeader
                  ? `${selectedWindow.label}同类综合位置 ${peerPositionLabel(selectedEvaluation(scoreLeader, window))}${scoreGap != null ? `，同类位置分位领先第二名 ${scoreGap.toFixed(1)} 个百分点` : ''}。类别方法评分独立展示，不随窗口变化。`
                  : '当前综合评分证据不足，但真实净值、收益、回撤、波动和费率仍可独立比较。'}
                不生成买卖或仓位建议。
              </p>
            </div>
            {scoreLeader ? (
              <div className="flex flex-wrap gap-3">
                <Link href={`/funds/${encodeURIComponent(scoreLeader.fund.windCode)}`} className="inline-flex h-10 items-center gap-2 rounded-md border border-[#9ab3a8] px-4 text-xs font-bold text-[#285d4b]">查看详情<ExternalLink className="h-3.5 w-3.5" /></Link>
                <Link href={`/analysis?${new URLSearchParams({ fundCode: scoreLeader.fund.windCode }).toString()}`} className="inline-flex h-10 items-center gap-2 rounded-md bg-[#173f35] px-4 text-xs font-bold text-white"><Bot className="h-3.5 w-3.5" />现场综合分析</Link>
              </div>
            ) : null}
          </div>
          <div className="mt-5 grid gap-px overflow-hidden border border-[#e1e6e2] bg-[#e1e6e2] sm:grid-cols-2 lg:grid-cols-4">
            {isMoneyMarket ? (
              <>
                <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">七日年化较高</div><strong className="mt-2 block text-sm">{sevenDayYieldLeader?.item.fund.name || '数据待补'}</strong><span className="mt-1 block text-xs text-[#66726c]">{formatPercent(sevenDayYieldLeader?.value)}</span></div>
                <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">万份收益较高</div><strong className="mt-2 block text-sm">{incomePer10000Leader?.item.fund.name || '数据待补'}</strong><span className="mt-1 block text-xs text-[#66726c]">{formatMoneyIncome(incomePer10000Leader?.value)}</span></div>
                <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">基金规模较大</div><strong className="mt-2 block text-sm">{assetLeader?.item.fund.name || '数据待补'}</strong><span className="mt-1 block text-xs text-[#66726c]">{formatAsset(assetLeader?.value)}</span></div>
                <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">基础费率较低</div><strong className="mt-2 block text-sm">{expenseLeader?.item.fund.name || '数据待补'}</strong><span className="mt-1 block text-xs text-[#66726c]">{formatPercent(expenseLeader?.value)}</span></div>
              </>
            ) : isIndexFund ? (
              <>
                <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">跟踪误差较小</div><strong className="mt-2 block text-sm">{trackingErrorLeader?.item.fund.name || '数据待补'}</strong><span className="mt-1 block text-xs text-[#66726c]">{formatPercent(trackingErrorLeader?.value)}</span></div>
                <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">跟踪差异绝对值较小</div><strong className="mt-2 block text-sm">{trackingDifferenceLeader?.item.fund.name || '数据待补'}</strong><span className="mt-1 block text-xs text-[#66726c]">{formatPercent(trackingDifferenceLeader?.value)}</span></div>
                <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">基础费率较低</div><strong className="mt-2 block text-sm">{expenseLeader?.item.fund.name || '数据待补'}</strong><span className="mt-1 block text-xs text-[#66726c]">{formatPercent(expenseLeader?.value)}</span></div>
                <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">基金规模较大</div><strong className="mt-2 block text-sm">{assetLeader?.item.fund.name || '数据待补'}</strong><span className="mt-1 block text-xs text-[#66726c]">{formatAsset(assetLeader?.value)}</span></div>
              </>
            ) : (
              <>
                <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">{selectedWindow.label}收益领先</div><strong className="mt-2 block text-sm">{returnLeader?.item.fund.name || alignedLeaderFallback}</strong><span className="mt-1 block text-xs text-[#66726c]">{formatPercent(returnLeader?.value ?? null)}</span></div>
                <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">回撤控制较好</div><strong className="mt-2 block text-sm">{drawdownLeader?.item.fund.name || alignedLeaderFallback}</strong><span className="mt-1 block text-xs text-[#66726c]">{formatPercent(drawdownLeader?.value ?? null)}</span></div>
                <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">波动较低</div><strong className="mt-2 block text-sm">{volatilityLeader?.item.fund.name || alignedLeaderFallback}</strong><span className="mt-1 block text-xs text-[#66726c]">{formatPercent(volatilityLeader?.value ?? null)}</span></div>
                <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">Sharpe 较高</div><strong className="mt-2 block text-sm">{sharpeLeader?.item.fund.name || alignedLeaderFallback}</strong><span className="mt-1 block text-xs text-[#66726c]">{sharpeLeader?.value?.toFixed(2) || '—'}</span></div>
              </>
            )}
          </div>
          <div className="mt-4 flex gap-3 text-xs leading-6 text-[#65716b]"><ShieldCheck className="mt-1 h-4 w-4 shrink-0 text-[#28745c]" /><span>{isMoneyMarket ? '货币基金按收益率、万份收益、规模和净值稳定性评价，不使用股票基金的 Sharpe 结论。' : isIndexFund ? '指数基金优先比较跟踪质量、费率和规模，区间收益只用于核对实际跟踪结果。' : '如果收益、回撤和 Sharpe 由不同基金领先，说明没有单一维度全面胜出，应继续查看经理、风格和归因证据。'}</span></div>
        </section>
      ) : null}

      {funds.length ? (
      <section className="overflow-x-auto border border-[#dbe1dc] bg-white">
        <table className="w-full min-w-[1040px] border-collapse text-left text-sm">
          <thead className="bg-[#f1f4f1] text-xs text-[#66726c]">
            <tr>
              <th className="px-4 py-3">基金</th>
              <th className="px-4 py-3">专业同类组</th>
              <th className="px-4 py-3">风格</th>
              <th className="px-4 py-3">基金公司</th>
              <th className="px-4 py-3">经理团队 / 管理年限</th>
              <th className="px-4 py-3 text-right">关联纪要</th>
              <th className="px-4 py-3 text-right">专业评分</th>
              <th className="w-12 px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-[#e5e9e5]">
            {funds.map((item, index) => (
              <tr key={item.fund.windCode}>
                <td className="px-4 py-4">
                  <Link href={`/funds/${encodeURIComponent(item.fund.windCode)}`} className="inline-flex items-center gap-1 font-bold text-[#1d2a24] hover:text-[#28745c]">
                    <span className="mr-1 h-2.5 w-2.5 rounded-full" style={{ backgroundColor: colors[index] }} />
                    {item.fund.name || item.fund.windCode}<ExternalLink className="h-3.5 w-3.5" />
                  </Link>
                  <div className="mt-1 text-xs text-[#78837d]">{item.fund.windCode}</div>
                  <Link href={`/analysis?${new URLSearchParams({ fundCode: item.fund.windCode }).toString()}`} className="mt-2 inline-flex items-center gap-1 text-[11px] font-bold text-[#6a5840]"><Bot className="h-3 w-3" />现场分析</Link>
                </td>
                <td className="px-4 py-4">{item.classification.peerGroup || '分类待确认'}</td>
                <td className="px-4 py-4">{styleLabel(item.fund)}</td>
                <td className="px-4 py-4"><span className="inline-flex items-start gap-2"><Building2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#718078]" />{item.fund.company || '公司待补充'}</span></td>
                <td className="px-4 py-4">
                  {item.managers.length ? (
                    <div className="space-y-2">
                      {item.managers.map((manager) => (
                        <div key={manager.id || manager.name}>
                          <span className="font-semibold text-[#26342d]">{manager.name}</span>
                          <span className="ml-2 text-xs text-[#75817b]">管理 {formatYears(manager.managementYears)}</span>
                        </div>
                      ))}
                      {item.managerTenureStart ? <div className="text-[11px] text-[#88928d]">当前团队起始：{item.managerTenureStart}</div> : null}
                    </div>
                  ) : '经理待补充'}
                </td>
                <td className="px-4 py-4 text-right"><span className="inline-flex items-center justify-end gap-1.5"><FileText className="h-3.5 w-3.5 text-[#7b8780]" />{item.researchMemoCount}</span></td>
                <td className="px-4 py-4 text-right font-bold text-[#28654f]">
                  {selectedEvaluation(item, window).score == null ? '—' : selectedEvaluation(item, window).score?.toFixed(1)}
                  <span className="mt-1 block text-[10px] font-normal text-[#75817b]">{selectedWindow.label}同类 {peerPositionLabel(selectedEvaluation(item, window))}</span>
                  {selectedEvaluation(item, window).score != null && selectedEvaluation(item, window).status === 'partial' ? <span className="mt-1 block text-[10px] font-normal text-[#987235]">部分证据</span> : null}
                </td>
                <td className="px-4 py-4 text-right"><button type="button" onClick={() => removeFund(item.fund.windCode)} disabled={isNavigating} className="text-[#8a958f] hover:text-[#8f463f]" aria-label={`移出比较：${item.fund.name || item.fund.windCode}`}><X className="h-4 w-4" /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      ) : null}

      {funds.length ? (
        <section className="overflow-hidden border border-[#dbe1dc] bg-white">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
            <div>
              <h2 className="flex items-center gap-2 text-lg font-bold"><CalendarRange className="h-5 w-5 text-[#28745c]" />现任经理任职期表现</h2>
              <p className="mt-1 text-xs leading-6 text-[#7a8580]">只评价现任团队共同任期；本地净值起点晚于上任日时，明确标为“本地可见期”，不冒充完整任期。</p>
            </div>
            <span className="text-xs text-[#7a8580]">多人共管取现任团队中最晚上任日</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1120px] border-collapse text-left text-xs">
              <thead className="bg-[#f1f4f1] text-[#66726c]"><tr><th className="px-4 py-3">基金</th><th className="px-4 py-3">团队上任日</th><th className="px-4 py-3">实际净值起点</th><th className="px-4 py-3">覆盖口径</th><th className="px-4 py-3 text-right">任期收益</th><th className="px-4 py-3 text-right">年化收益</th><th className="px-4 py-3 text-right">最大回撤</th><th className="px-4 py-3 text-right">Sharpe</th><th className="px-4 py-3 text-right">同区间同类名次</th></tr></thead>
              <tbody className="divide-y divide-[#e5e9e5]">
                {funds.map((item) => {
                  const performance = item.managerTenurePerformance
                  const partial = performance.coverageStatus === 'partial_since_data_start'
                  return (
                    <tr key={item.fund.windCode}>
                      <td className="px-4 py-4"><strong className="text-sm text-[#26342d]">{item.fund.name || item.fund.windCode}</strong><span className="mt-1 block text-[10px] text-[#87918c]">{item.managers.map((manager) => manager.name).join(' / ') || '经理待补'}</span></td>
                      <td className="px-4 py-4">{formatDate(performance.requestedStartDate || item.managerTenureStart)}</td>
                      <td className="px-4 py-4">{formatDate(performance.actualStartDate)}<span className="mt-1 block text-[10px] text-[#87918c]">{performance.observations ? `${performance.observations} 个净值日` : '净值待补'}</span></td>
                      <td className="px-4 py-4"><span className={`inline-flex px-2.5 py-1 text-[11px] font-bold ${partial ? 'bg-[#fff0d4] text-[#7b581c]' : performance.coverageStatus === 'full_tenure' ? 'bg-[#e4f0e9] text-[#24624c]' : 'bg-[#ecefed] text-[#69736e]'}`}>{managerTenureCoverageLabel(performance)}</span><span className="mt-1 block text-[10px] text-[#87918c]">{performance.coverageRatio == null ? '—' : `覆盖 ${(performance.coverageRatio * 100).toFixed(0)}%`}</span></td>
                      <td className="px-4 py-4 text-right font-bold">{formatPercent(performance.totalReturn)}</td>
                      <td className="px-4 py-4 text-right">{formatPercent(performance.annualizedReturn)}</td>
                      <td className="px-4 py-4 text-right text-[#915248]">{formatPercent(performance.maxDrawdown)}</td>
                      <td className="px-4 py-4 text-right">{performance.sharpeRatio == null ? '—' : performance.sharpeRatio.toFixed(2)}</td>
                      <td className="px-4 py-4 text-right"><strong>{managerTenurePeerLabel(performance)}</strong>{performance.peerPercentile != null ? <span className="mt-1 block text-[10px] text-[#87918c]">分位 {performance.peerPercentile.toFixed(1)}%</span> : null}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="flex gap-3 border-t border-[#eadfbf] bg-[#fffaf0] px-5 py-4 text-[11px] leading-5 text-[#735b2b]"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" /><p>只有净值从上任附近开始完整覆盖时，才生成现任经理同区间同类排名；部分覆盖指标仅用于说明本地可见历史。</p></div>
        </section>
      ) : null}

      {comparable ? (
        <>
          <section className="border border-[#dbe1dc] bg-white p-4 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="flex items-center gap-2 text-lg font-bold"><BarChart3 className="h-5 w-5 text-[#28745c]" />同区间归一化净值</h2>
                <p className="mt-1 text-xs text-[#7a8580]">所有基金在共同净值首日设为 100；曲线来自本地真实净值，不补点、不模拟。</p>
              </div>
              <div className="inline-flex border border-[#cfd6d0] bg-[#f7f8f5] p-1">
                {windows.map((item) => (
                  <button key={item.value} type="button" onClick={() => setWindow(item.value)} className={`h-8 px-3 text-xs font-bold ${window === item.value ? 'bg-[#173f35] text-white' : 'text-[#67736d]'}`}>{item.label}</button>
                ))}
              </div>
            </div>
            {chartData.length ? (
              <div className="mt-6 h-[320px] w-full sm:h-[390px]">
                <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 320, height: 320 }}>
                  <LineChart data={chartData} margin={{ top: 6, right: 8, bottom: 6, left: -16 }}>
                    <CartesianGrid stroke="#e6eae6" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" minTickGap={48} tick={{ fontSize: 11, fill: '#718078' }} tickLine={false} axisLine={false} />
                    <YAxis domain={['auto', 'auto']} tick={{ fontSize: 11, fill: '#718078' }} tickLine={false} axisLine={false} />
                    <Tooltip formatter={(value) => [`${Number(value).toFixed(2)}`, '归一化净值']} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    {funds.map((item, index) => <Line key={item.fund.windCode} dataKey={item.fund.windCode} name={item.fund.name || item.fund.windCode} stroke={colors[index]} strokeWidth={2} dot={false} connectNulls />)}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : <div className="mt-6 grid h-64 place-items-center border border-dashed border-[#cdd5cf] text-sm text-[#79847e]">当前区间没有可用净值数据</div>}
          </section>

          <section>
            <div className="pb-4">
              <h2 className="text-lg font-bold">核心指标</h2>
              <p className="mt-1 text-xs text-[#7a8580]">收益和风险只按上方共同净值区间重算；同类样本仍采用对应标准窗口。</p>
            </div>
            <div className="overflow-x-auto border border-[#dbe1dc] bg-white">
              {isMoneyMarket ? (
                <table className="w-full min-w-[760px] border-collapse text-left text-sm">
                  <thead className="bg-[#f1f4f1] text-xs text-[#66726c]"><tr><th className="px-4 py-3">基金</th><th className="px-4 py-3 text-right">七日年化</th><th className="px-4 py-3 text-right">万份收益</th><th className="px-4 py-3 text-right">{selectedWindow.label}收益</th><th className="px-4 py-3 text-right">规模</th><th className="px-4 py-3 text-right">同类有效样本</th></tr></thead>
                  <tbody className="divide-y divide-[#e5e9e5]">
                    {funds.map((item) => {
                      const fund = item.fund as SimpleFund
                      return <tr key={item.fund.windCode}><td className="px-4 py-4 font-bold">{item.fund.name || item.fund.windCode}</td><td className="px-4 py-4 text-right">{formatPercent(latestMetric(fund, 'seven_day_annualized_yield'))}</td><td className="px-4 py-4 text-right">{formatMoneyIncome(latestMetric(fund, 'income_per_10000'))}</td><td className="px-4 py-4 text-right">{formatPercent(alignedMetric(item, 'totalReturn'))}</td><td className="px-4 py-4 text-right">{formatAsset(item.fund.totalAsset)}</td><td className="px-4 py-4 text-right">{selectedEvaluation(item, window).validPeerCount || '—'}</td></tr>
                    })}
                  </tbody>
                </table>
              ) : isIndexFund ? (
                <table className="w-full min-w-[820px] border-collapse text-left text-sm">
                  <thead className="bg-[#f1f4f1] text-xs text-[#66726c]"><tr><th className="px-4 py-3">基金</th><th className="px-4 py-3 text-right">{selectedWindow.label}跟踪误差</th><th className="px-4 py-3 text-right">{selectedWindow.label}跟踪差异</th><th className="px-4 py-3 text-right">基础费率</th><th className="px-4 py-3 text-right">{selectedWindow.label}收益</th><th className="px-4 py-3 text-right">规模</th><th className="px-4 py-3 text-right">同类有效样本</th></tr></thead>
                  <tbody className="divide-y divide-[#e5e9e5]">
                    {funds.map((item) => {
                      const fund = item.fund as SimpleFund
                      return <tr key={item.fund.windCode}><td className="px-4 py-4 font-bold">{item.fund.name || item.fund.windCode}</td><td className="px-4 py-4 text-right">{formatPercent(trackingErrorMetric(fund, window))}</td><td className="px-4 py-4 text-right">{formatPercent(trackingDifferenceMetric(fund, window))}</td><td className="px-4 py-4 text-right">{formatPercent(latestMetric(fund, 'expense_ratio'))}</td><td className="px-4 py-4 text-right">{formatPercent(alignedMetric(item, 'totalReturn'))}</td><td className="px-4 py-4 text-right">{formatAsset(item.fund.totalAsset)}</td><td className="px-4 py-4 text-right">{selectedEvaluation(item, window).validPeerCount || '—'}<span className="mt-1 block text-[10px] text-[#87918c]">同类 {peerPositionLabel(selectedEvaluation(item, window))}</span></td></tr>
                    })}
                  </tbody>
                </table>
              ) : (
              <table className="w-full min-w-[820px] border-collapse text-left text-sm">
                <thead className="bg-[#f1f4f1] text-xs text-[#66726c]">
                  <tr>
                    <th className="px-4 py-3">基金</th>
                    <th className="px-4 py-3 text-right">区间收益</th>
                    <th className="px-4 py-3 text-right">最大回撤</th>
                    <th className="px-4 py-3 text-right">年化波动</th>
                    <th className="px-4 py-3 text-right">Sharpe</th>
                    <th className="px-4 py-3 text-right">规模</th>
                    <th className="px-4 py-3 text-right">同类有效样本</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#e5e9e5]">
                  {funds.map((item) => {
                    return (
                      <tr key={item.fund.windCode}>
                        <td className="px-4 py-4 font-bold">{item.fund.name || item.fund.windCode}</td>
                        <td className="px-4 py-4 text-right">{formatPercent(alignedMetric(item, 'totalReturn'))}</td>
                        <td className="px-4 py-4 text-right text-[#984f48]">{formatPercent(alignedMetric(item, 'maxDrawdown'))}</td>
                        <td className="px-4 py-4 text-right">{formatPercent(alignedMetric(item, 'annualizedVolatility'))}</td>
                        <td className="px-4 py-4 text-right">{alignedMetric(item, 'sharpeRatio')?.toFixed(2) || '—'}</td>
                        <td className="px-4 py-4 text-right">{formatAsset(item.fund.totalAsset)}</td>
                        <td className="px-4 py-4 text-right">{selectedEvaluation(item, window).validPeerCount || '—'}<span className="mt-1 block text-[10px] text-[#87918c]">同类 {peerPositionLabel(selectedEvaluation(item, window))}</span></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              )}
            </div>
          </section>

          {calendarYears.length ? (
            <section className="overflow-hidden border border-[#dbe1dc] bg-white">
              <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
                <div>
                  <h2 className="flex items-center gap-2 text-lg font-bold"><CalendarRange className="h-5 w-5 text-[#28745c]" />年度业绩稳定性</h2>
                  <p className="mt-1 text-xs leading-6 text-[#7a8580]">按自然年度比较真实净值收益、同类名次和同类中位数，优先看多年表现是否持续。</p>
                </div>
                <span className="text-xs text-[#7a8580]">最近净值截至 {funds.map((item) => item.periodPerformance.latestNavDate).filter(Boolean).sort().at(0) || '—'}</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1080px] border-collapse text-left text-xs">
                  <thead className="bg-[#f1f4f1] text-[#66726c]">
                    <tr>
                      <th className="px-4 py-3">基金</th>
                      {calendarYears.map((year) => <th key={year} className="px-4 py-3 text-right">{funds.flatMap((item) => item.periodPerformance.periods).find((period) => period.year === year)?.label || `${year} 年`}</th>)}
                      <th className="px-4 py-3 text-right">完整区间</th>
                      <th className="px-4 py-3 text-right">正收益</th>
                      <th className="px-4 py-3 text-right">高于同类中位数</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#e5e9e5]">
                    {funds.map((item) => (
                      <tr key={item.fund.windCode}>
                        <td className="px-4 py-4">
                          <strong className="text-sm text-[#26342d]">{item.fund.name || item.fund.windCode}</strong>
                          <span className="mt-1 block text-[10px] text-[#87918c]">{item.periodPerformance.navBasis === 'accum_nav' ? '累计净值' : '单位净值'}</span>
                        </td>
                        {calendarYears.map((year) => {
                          const period = item.periodPerformance.periods.find((entry) => entry.year === year)
                          if (!period) return <td key={year} className="px-4 py-4 text-right text-[#9aa39e]">—</td>
                          const complete = period.coverageStatus === 'complete'
                          return (
                            <td key={year} className="px-4 py-4 text-right">
                              <strong className={`text-sm ${calendarReturnTone(period.return)}`}>{formatSignedPercent(period.return)}</strong>
                              <span className={`mt-1 block text-[10px] ${complete ? 'text-[#68746e]' : 'text-[#987235]'}`}>
                                {complete ? (period.rank && period.peerCount ? `同类 ${period.rank} / ${period.peerCount}` : '同类样本不足') : '部分区间 · 不排名'}
                              </span>
                              <span className="mt-1 block text-[10px] text-[#929b96]">
                                {complete && period.peerMedianReturn != null
                                  ? `中位数 ${formatSignedPercent(period.peerMedianReturn)}`
                                  : `净值覆盖 ${period.observationCoverage == null ? '—' : `${(period.observationCoverage * 100).toFixed(0)}%`}`}
                              </span>
                            </td>
                          )
                        })}
                        <td className="px-4 py-4 text-right font-bold text-[#26342d]">{item.periodPerformance.summary.completePeriodCount}</td>
                        <td className="px-4 py-4 text-right">{item.periodPerformance.summary.positivePeriodCount} / {item.periodPerformance.summary.completePeriodCount || '—'}</td>
                        <td className="px-4 py-4 text-right">{item.periodPerformance.summary.abovePeerMedianCount} / {item.periodPerformance.summary.peerRankedPeriodCount || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex gap-3 border-t border-[#eadfbf] bg-[#fffaf0] px-5 py-4 text-[11px] leading-5 text-[#735b2b]">
                <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
                <p>{funds[0].periodPerformance.boundary || '年度收益仅使用本地真实净值；部分区间不参与同类排名。'}</p>
              </div>
            </section>
          ) : null}

          {alignedReady && alignedWindow ? (
          <section className="overflow-hidden border border-[#dbe1dc] bg-white">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
              <div>
                <h2 className="flex items-center gap-2 text-lg font-bold"><BarChart3 className="h-5 w-5 text-[#28745c]" />回撤修复对比</h2>
                <p className="mt-1 text-xs leading-6 text-[#7a8580]">使用上方{selectedWindow.label}共同净值日期重算，回答“跌了多少、多久见底、多久回到原高点”。</p>
              </div>
              <span className="text-xs text-[#7a8580]">共同区间 {formatDate(alignedWindow.actualStartDate)} 至 {formatDate(alignedWindow.actualEndDate)}</span>
            </div>

            <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-3">
              <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">当前更接近区间高位</div><strong className="mt-2 block text-sm">{currentDrawdownLeader?.item.fund.name || alignedLeaderFallback}</strong><span className="mt-1 block text-xs text-[#66726c]">当前回撤 {formatPercent(currentDrawdownLeader?.value ?? null)}</span></div>
              <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">最大回撤相对较小</div><strong className="mt-2 block text-sm">{maxDrawdownLeader?.item.fund.name || alignedLeaderFallback}</strong><span className="mt-1 block text-xs text-[#66726c]">最大回撤 {formatPercent(maxDrawdownLeader?.value ?? null)}</span></div>
              <div className="bg-[#f8faf8] p-4"><div className="text-xs text-[#748079]">低于前高最长时间较短</div><strong className="mt-2 block text-sm">{underwaterLeader?.item.fund.name || alignedLeaderFallback}</strong><span className="mt-1 block text-xs text-[#66726c]">最长 {underwaterLeader?.value == null ? '—' : `${underwaterLeader.value.toFixed(0)} 天`}</span></div>
            </div>

            <div className="overflow-x-auto border-t border-[#e1e6e2]">
              <table className="w-full min-w-[980px] border-collapse text-left text-xs">
                <thead className="bg-[#f1f4f1] text-[#66726c]"><tr><th className="px-4 py-3">基金</th><th className="px-4 py-3">当前状态</th><th className="px-4 py-3 text-right">当前回撤</th><th className="px-4 py-3 text-right">区间最大回撤</th><th className="px-4 py-3 text-right">峰值至谷底</th><th className="px-4 py-3 text-right">谷底后修复</th><th className="px-4 py-3 text-right">最长低于前高</th><th className="px-4 py-3 text-right">5% 以上回撤</th></tr></thead>
                <tbody className="divide-y divide-[#e5e9e5]">
                  {funds.map((item) => {
                    const metrics = alignedWindow.funds[item.fund.windCode]
                    return (
                      <tr key={item.fund.windCode}>
                        <td className="px-4 py-4 font-bold text-[#26342d]">{item.fund.name || item.fund.windCode}</td>
                        <td className="px-4 py-4">{metrics ? drawdownStatusLabel(metrics.drawdownStatus) : '—'}</td>
                        <td className="px-4 py-4 text-right"><strong className="text-[#915248]">{formatPercent(metrics?.currentDrawdown ?? null)}</strong><span className="mt-1 block text-[10px] text-[#87918c]">{metrics?.currentUnderwaterDays ? `${metrics.currentUnderwaterDays} 天未回前高` : '已在区间高位附近'}</span></td>
                        <td className="px-4 py-4 text-right font-bold text-[#915248]">{formatPercent(metrics?.maxDrawdown ?? null)}</td>
                        <td className="px-4 py-4 text-right">{metrics ? `${metrics.worstDeclineDays} 天` : '—'}</td>
                        <td className="px-4 py-4 text-right">{!metrics ? '—' : metrics.worstRecovered && metrics.worstRecoveryDays != null ? `${metrics.worstRecoveryDays} 天` : '尚未修复'}</td>
                        <td className="px-4 py-4 text-right">{metrics ? `${metrics.longestUnderwaterDays} 天` : '—'}</td>
                        <td className="px-4 py-4 text-right">{metrics ? `${metrics.recoveredMaterialEpisodeCount} / ${metrics.materialEpisodeCount} 已修复` : '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex gap-3 border-t border-[#eadfbf] bg-[#fffaf0] px-5 py-4 text-[11px] leading-5 text-[#735b2b]"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" /><p>只描述同一历史区间内的回撤经历；修复更快不代表未来一定更稳，也不进入买卖或仓位判断。</p></div>
          </section>
          ) : null}

          <section>
            <div className="pb-4">
              <h2 className="text-lg font-bold">最新持仓差异</h2>
              <p className="mt-1 text-xs leading-6 text-[#7a8580]">仅比较本地已同步的最新公开持仓，不会因打开页面而请求外部数据。不同权重口径不会混排。</p>
            </div>
            <div className="overflow-x-auto border border-[#dbe1dc] bg-white">
              <table className="w-full min-w-[840px] border-collapse text-left text-sm">
                <thead className="bg-[#f1f4f1] text-xs text-[#66726c]"><tr><th className="px-4 py-3">基金</th><th className="px-4 py-3">最新披露</th><th className="px-4 py-3">权重口径</th><th className="px-4 py-3 text-right">披露重仓股</th><th className="px-4 py-3 text-right">前十大集中度</th><th className="px-4 py-3">第一重仓</th></tr></thead>
                <tbody className="divide-y divide-[#e5e9e5]">
                  {funds.map((item) => (
                    <tr key={item.fund.windCode}>
                      <td className="px-4 py-4 font-bold">{item.fund.name || item.fund.windCode}</td>
                      <td className="px-4 py-4"><div>{item.holding.latestQuarter || '暂无本地持仓'}</div><div className="mt-1 text-[11px] text-[#87918c]">{formatDate(item.holding.reportDate)}</div></td>
                      <td className="px-4 py-4">{item.holding.holdingCount ? holdingBasisLabel(item) : '—'}</td>
                      <td className="px-4 py-4 text-right">{item.holding.holdingCount || '—'}</td>
                      <td className="px-4 py-4 text-right">{formatPercent(holdingConcentration(item))}</td>
                      <td className="px-4 py-4"><div className="font-semibold">{item.holding.firstStockName || '—'}</div><div className="mt-1 text-[11px] text-[#87918c]">{item.holding.firstStockName ? `${holdingBasisLabel(item)} ${formatPercent(item.holding.firstStockWeight)}` : '本地数据待同步'}</div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="overflow-hidden border border-[#dbe1dc] bg-white">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
              <div>
                <h2 className="flex items-center gap-2 text-lg font-bold"><Network className="h-5 w-5 text-[#28745c]" />重仓相似度</h2>
                <p className="mt-1 max-w-4xl text-xs leading-6 text-[#7a8580]">只比较同一报告期的前十大公开重仓股。各基金前十大权重先归一化，再计算重合度；不是完整组合相关性。</p>
              </div>
              {highestSimilarityPair ? (
                <div className="text-right text-xs text-[#6f7a74]"><div>最高重合</div><strong className="mt-1 block text-lg text-[#1d2923]">{formatPercent(highestSimilarityPair.overlapRatio)}</strong></div>
              ) : null}
            </div>

            {availableSimilarityPairs.length ? (
              <div className="grid gap-px bg-[#e1e6e2] lg:grid-cols-2">
                {availableSimilarityPairs.map((pair) => {
                  const meta = similarityMeta(pair.similarityLevel)
                  return (
                    <article key={`${pair.fundA}:${pair.fundB}:${pair.quarter}`} className="bg-white p-5 sm:p-6">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="text-xs text-[#7a8580]">{pair.quarter} · 同期前十大重仓</div>
                          <h3 className="mt-2 text-sm font-bold leading-6 text-[#26342d]">{fundNameByCode.get(pair.fundA) || pair.fundA}<span className="mx-2 text-[#9aa39e]">↔</span>{fundNameByCode.get(pair.fundB) || pair.fundB}</h3>
                        </div>
                        <span className={`shrink-0 px-2.5 py-1 text-[11px] font-bold ${meta.className}`}>{meta.label}</span>
                      </div>
                      <div className="mt-5 grid grid-cols-3 gap-px bg-[#e5e9e6]">
                        <div className="bg-[#f8faf8] p-3"><div className="text-[10px] text-[#7b8680]">重仓重合度</div><strong className="mt-1 block text-lg">{formatPercent(pair.overlapRatio)}</strong></div>
                        <div className="bg-[#f8faf8] p-3"><div className="text-[10px] text-[#7b8680]">共同重仓股</div><strong className="mt-1 block text-lg">{pair.commonHoldingCount} 只</strong></div>
                        <div className="bg-[#f8faf8] p-3"><div className="text-[10px] text-[#7b8680]">股票集合重合</div><strong className="mt-1 block text-lg">{formatPercent(pair.jaccardScore)}</strong></div>
                      </div>
                      {pair.commonHoldings.length ? (
                        <div className="mt-4 space-y-2">
                          {pair.commonHoldings.slice(0, 5).map((holding) => (
                            <div key={holding.stockCode} className="flex items-center justify-between gap-4 border-b border-[#edf0ed] pb-2 text-xs last:border-0 last:pb-0">
                              <div><span className="font-bold text-[#31443a]">{holding.stockName || holding.stockCode}</span><span className="ml-2 text-[10px] text-[#8a948f]">{holding.stockCode}</span></div>
                              <div className="shrink-0 text-[#68746e]">{formatPercent(holding.weightA)} / {formatPercent(holding.weightB)}</div>
                            </div>
                          ))}
                        </div>
                      ) : <p className="mt-4 text-xs leading-6 text-[#77827c]">两只基金的前十大公开重仓股没有重合。</p>}
                    </article>
                  )
                })}
              </div>
            ) : (
              <div className="px-6 py-10 text-center text-sm text-[#748079]">{similarityPairs[0]?.missingItems[0] || '需要至少两只基金在同一报告期具备可信前十大持仓。'}</div>
            )}

            <div className="flex gap-3 border-t border-[#eadfbf] bg-[#fffaf0] px-5 py-4 text-xs leading-6 text-[#735b2b]">
              <ShieldCheck className="mt-1 h-4 w-4 shrink-0" />
              <p>{holdingSimilarity?.scope || '重仓相似度只用于识别重复暴露，不构成配置、交易或组合建议。'} 重合较低也不能证明完整组合已经分散。</p>
            </div>
          </section>
        </>
      ) : null}
    </div>
  )
}
