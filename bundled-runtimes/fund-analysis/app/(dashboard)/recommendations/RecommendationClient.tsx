'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, BookmarkPlus, Bot, CheckCircle2, CircleAlert, GitCompareArrows, LoaderCircle, Tags, X } from 'lucide-react'
import type { CamelFund } from '@/lib/backend-api'
import { primaryPresets } from '@/lib/fund-category-presets'
import {
  bondHoldingEvidence,
  baseFeeRate,
  drawdownMetric,
  fofHoldingEvidence,
  formatAsset,
  formatPercent,
  managerName,
  peerGroup,
  professionalFundScore,
  professionalScoreEvidence,
  professionalScorePeerPosition,
  recommendationEvidence,
  returnMetric,
  styleLabel,
  styleLabelStatus,
  type SimpleFund,
} from '@/lib/simple-fund-view'

type Props = {
  initialFunds: CamelFund[]
  initialCategories: string[]
  universeTotal: number
  initialReadyCategoryCount: number
  initialError: string
  initialCategory?: string
}

type Watchlist = {
  id: string
  name: string
}

type StyleOption = {
  value: string
  matchedCount: number
  confirmedCount: number
  derivedCount: number
  suggestedCount: number
  quantitativeCount: number
}

export type RecommendationCoverageGroup = {
  key: string
  name: string
  status: 'ready' | 'partial' | 'blocked'
  minimumPeerCount: number
  classifiedCount: number
  databaseFundCount: number
  evaluationMethodReadyCount: number
  metricReadyCount: number
  styleReadyCount: number
  recommendationReadyCount: number
  missingReasonCounts: Record<string, number>
}

export type RecommendationCoverageReport = {
  summary: {
    categoryCount: number
    readyCategoryCount: number
    classifiedCount: number
    databaseFundCount: number
    evaluationMethodReadyCount: number
    metricReadyCount: number
    styleReadyCount: number
    recommendationReadyCount: number
  } | null
  groups: RecommendationCoverageGroup[]
  backfillCommand: string
}

const exclusionReasonLabels: Record<string, string> = {
  peer_sample_insufficient: '同类基金样本不足',
  peer_evaluation_sample_insufficient: '达到最低评价样本门槛还缺',
  evaluation_method_missing: '该类别尚未配置评价方法',
  required_category_evidence_missing: '缺少该类别要求的关键指标',
  category_score_unavailable: '类别评分暂时无法计算',
}

function exclusionReasonLabel(reason: string) {
  return exclusionReasonLabels[reason] || '基金分类或评价证据不完整'
}

function toCoverageReport(payload: Record<string, unknown>): RecommendationCoverageReport {
  const rawSummary = payload.summary && typeof payload.summary === 'object'
    ? payload.summary as Record<string, unknown>
    : null
  const groups: RecommendationCoverageGroup[] = (Array.isArray(payload.groups) ? payload.groups : []).map((item) => {
    const group = item && typeof item === 'object' ? item as Record<string, unknown> : {}
    return {
      key: String(group.key || ''),
      name: String(group.name || group.key || ''),
      status: String(group.status || 'blocked') as RecommendationCoverageGroup['status'],
      minimumPeerCount: Number(group.minimum_peer_count || 0),
      classifiedCount: Number(group.classified_count || 0),
      databaseFundCount: Number(group.database_fund_count || 0),
      evaluationMethodReadyCount: Number(group.evaluation_method_ready_count || 0),
      metricReadyCount: Number(group.metric_ready_count || 0),
      styleReadyCount: Number(group.style_ready_count || 0),
      recommendationReadyCount: Number(group.recommendation_ready_count || 0),
      missingReasonCounts: group.missing_reason_counts && typeof group.missing_reason_counts === 'object'
        ? group.missing_reason_counts as Record<string, number>
        : {},
    }
  })
  return {
    summary: rawSummary ? {
      categoryCount: Number(rawSummary.category_count || 0),
      readyCategoryCount: Number(rawSummary.ready_category_count || 0),
      classifiedCount: Number(rawSummary.classified_count || 0),
      databaseFundCount: Number(rawSummary.database_fund_count || 0),
      evaluationMethodReadyCount: Number(rawSummary.evaluation_method_ready_count || 0),
      metricReadyCount: Number(rawSummary.metric_ready_count || 0),
      styleReadyCount: Number(rawSummary.style_ready_count || 0),
      recommendationReadyCount: Number(rawSummary.recommendation_ready_count || 0),
    } : null,
    groups,
    backfillCommand: '',
  }
}

export default function RecommendationClient({ initialFunds, initialCategories, universeTotal, initialReadyCategoryCount, initialError, initialCategory = '' }: Props) {
  const universe = initialFunds as SimpleFund[]
  const categories = useMemo(() => initialCategories.length
    ? initialCategories
    : Array.from(new Set(universe.map((fund) => peerGroup(fund)).filter((value) => value !== '类别待确认'))),
  [initialCategories, universe])
  const quickCategories = useMemo(
    () => primaryPresets.filter((preset) => categories.includes(preset.category)),
    [categories],
  )
  const [category, setCategory] = useState(initialCategory)
  const [style, setStyle] = useState('')
  const [categoryFunds, setCategoryFunds] = useState<SimpleFund[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [peerUniverseCount, setPeerUniverseCount] = useState(0)
  const [evidenceEligibleCount, setEvidenceEligibleCount] = useState(0)
  const [longTermReadyCount, setLongTermReadyCount] = useState(0)
  const [styleMatchedCount, setStyleMatchedCount] = useState(0)
  const [excludedCount, setExcludedCount] = useState(0)
  const [excludedReasonCounts, setExcludedReasonCounts] = useState<Record<string, number>>({})
  const [availableStyles, setAvailableStyles] = useState<string[]>([])
  const [styleOptions, setStyleOptions] = useState<StyleOption[]>([])
  const [watchlists, setWatchlists] = useState<Watchlist[]>([])
  const [selectedWatchlistId, setSelectedWatchlistId] = useState('')
  const [watchlistTargets, setWatchlistTargets] = useState<SimpleFund[]>([])
  const [savingWatchlist, setSavingWatchlist] = useState(false)
  const [watchlistNotice, setWatchlistNotice] = useState('')
  const [coverage, setCoverage] = useState<RecommendationCoverageReport | null>(null)
  const [coverageLoading, setCoverageLoading] = useState(false)
  const [coverageError, setCoverageError] = useState('')
  const recommendations = categoryFunds

  useEffect(() => {
    if (initialCategory) void loadCandidates(initialCategory)
  }, [initialCategory])

  async function loadCandidates(nextCategory: string, nextStyle = '') {
    setCategoryFunds([])
    setPeerUniverseCount(0)
    setEvidenceEligibleCount(0)
    setLongTermReadyCount(0)
    setStyleMatchedCount(0)
    setExcludedCount(0)
    setExcludedReasonCounts({})
    setLoadError('')
    if (!nextCategory) return
    setLoading(true)
    try {
      const params = new URLSearchParams({ category: nextCategory })
      if (nextStyle) params.set('style', nextStyle)
      const response = await fetch(`/api/recommendations?${params}`, {
        cache: 'no-store',
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '同类基金评价暂时不可用')
      setCategoryFunds(Array.isArray(payload.data) ? payload.data : [])
      setPeerUniverseCount(Number(payload.peerUniverseCount || 0))
      setEvidenceEligibleCount(Number(payload.evidenceEligibleCount || 0))
      setLongTermReadyCount(Number(payload.longTermReadyCount || 0))
      setStyleMatchedCount(Number(payload.styleMatchedCount || 0))
      setExcludedCount(Number(payload.excludedCount || 0))
      setExcludedReasonCounts(payload.excludedReasonCounts && typeof payload.excludedReasonCounts === 'object'
        ? payload.excludedReasonCounts as Record<string, number>
        : {})
      setAvailableStyles(Array.isArray(payload.availableStyles) ? payload.availableStyles : [])
      setStyleOptions(Array.isArray(payload.availableStyleOptions)
        ? payload.availableStyleOptions.map((item: Record<string, unknown>) => ({
            value: String(item.value || ''),
            matchedCount: Number(item.matched_count || item.matchedCount || 0),
            confirmedCount: Number(item.confirmed_count || item.confirmedCount || 0),
            derivedCount: Number(item.derived_count || item.derivedCount || 0),
            suggestedCount: Number(item.suggested_count || item.suggestedCount || 0),
            quantitativeCount: Number(item.quantitative_count || item.quantitativeCount || 0),
          })).filter((item: StyleOption) => item.value)
        : [])
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : '同类基金评价暂时不可用')
    } finally {
      setLoading(false)
    }
  }

  async function loadCoverage() {
    if (coverage || coverageLoading) return
    setCoverageLoading(true)
    setCoverageError('')
    try {
      const response = await fetch('/api/recommendations/coverage', { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '基金评价覆盖暂时不可用')
      setCoverage(toCoverageReport(payload))
    } catch (error) {
      setCoverageError(error instanceof Error ? error.message : '基金评价覆盖暂时不可用')
    } finally {
      setCoverageLoading(false)
    }
  }

  function chooseCategory(nextCategory: string) {
    setCategory(nextCategory)
    setStyle('')
    setAvailableStyles([])
    setStyleOptions([])
    void loadCandidates(nextCategory)
  }

  async function openWatchlist(targets: SimpleFund[]) {
    setLoadError('')
    setWatchlistNotice('')
    try {
      const response = await fetch('/api/watchlists', { cache: 'no-store' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || '加载自选分组失败')
      const groups = Array.isArray(payload.watchlists) ? payload.watchlists : []
      setWatchlists(groups)
      setSelectedWatchlistId(String(groups[0]?.id || ''))
      setWatchlistTargets(targets)
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : '加载自选分组失败')
    }
  }

  async function saveToWatchlist() {
    if (!selectedWatchlistId || watchlistTargets.length === 0) return
    setSavingWatchlist(true)
    setLoadError('')
    const results = await Promise.all(watchlistTargets.map(async (fund) => {
      const evidence = recommendationEvidence(fund)
      const reason = evidence.reasons.length
        ? `推荐入选：${evidence.reasons.join('；')}`
        : `${category}同类候选`
      const response = await fetch(`/api/watchlists/${encodeURIComponent(selectedWatchlistId)}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fundId: fund.windCode, reason }),
      })
      return response.ok
    }))
    const successCount = results.filter(Boolean).length
    const failedCount = results.length - successCount
    const groupName = watchlists.find((item) => String(item.id) === selectedWatchlistId)?.name || '我的自选'
    setWatchlistTargets([])
    setSavingWatchlist(false)
    setWatchlistNotice(`${successCount} 只候选已加入“${groupName}”${failedCount ? `，${failedCount} 只加入失败` : ''}。`)
  }

  const compareHref = `/compare?${new URLSearchParams({
    codes: recommendations.slice(0, 6).map((fund) => fund.windCode).join(','),
  }).toString()}`
  const exclusionReasons = Object.entries(excludedReasonCounts)
    .filter(([, count]) => Number(count) > 0)
    .sort(([, left], [, right]) => Number(right) - Number(left))

  return (
    <div className="space-y-7">
      <section className="border-b border-[#dce1dc] pb-6">
        <div className="border-l-4 border-[#d7b46a] bg-[#fff9eb] px-4 py-3 text-xs leading-6 text-[#755722]">
          候选组用于缩小研究范围，不跨类比较，不代表收益承诺或买卖建议。
        </div>
      </section>

      {initialError ? <div className="border border-[#e5c98f] bg-[#fff8e8] px-5 py-4 text-sm text-[#78551c]">{initialError}</div> : null}
      {loadError ? <div className="border border-[#e5c98f] bg-[#fff8e8] px-5 py-4 text-sm text-[#78551c]">{loadError}</div> : null}
      {watchlistNotice ? <div className="flex items-center justify-between gap-4 border border-[#bad7ca] bg-[#edf6f1] px-5 py-4 text-sm text-[#285c49]"><span>{watchlistNotice}</span><Link href="/watchlist" className="font-bold underline underline-offset-4">查看我的自选</Link></div> : null}

      {quickCategories.length ? (
        <section>
          <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-[#1e2d26]">主动基金候选</h2>
              <p className="mt-1 text-xs leading-6 text-[#76817b]">按同类组做分类内评价，排名限于同一 peer group。</p>
            </div>
            <span className="text-xs font-bold text-[#28745c]">同类组内评价</span>
          </div>
          <div className="grid gap-px overflow-hidden border border-[#d7ddd8] bg-[#d7ddd8] sm:grid-cols-2 xl:grid-cols-3">
            {quickCategories.map((preset) => {
              const active = category === preset.category
              return (
                <button
                  key={preset.category}
                  type="button"
                  onClick={() => chooseCategory(preset.category)}
                  aria-pressed={active}
                  className={`group min-h-32 bg-white p-5 text-left transition ${active ? 'shadow-[inset_0_0_0_2px_#28745c]' : 'hover:bg-[#f5f8f5]'}`}
                >
                  <span className={`font-mono text-[11px] font-bold tracking-[0.18em] ${active ? 'text-[#28745c]' : 'text-[#a0aaa4]'}`}>{preset.mark}</span>
                  <strong className="mt-5 block text-base text-[#1d2b25] group-hover:text-[#245f4b]">{preset.label}</strong>
                  <span className="mt-1 block text-xs leading-5 text-[#76817b]">{preset.description}</span>
                </button>
              )
            })}
          </div>
        </section>
      ) : null}

      <section className="grid gap-5 border border-[#dbe1dc] bg-white p-5 md:grid-cols-2">
        <label className="block">
          <span className="text-sm font-bold">指数 / 被动工具 / 其他分类</span>
          <span className="mt-1 block text-xs text-[#7a8580]">被动指数仅评判跟踪误差、费率和规模，不做选基推荐</span>
          <select value={category} onChange={(event) => void chooseCategory(event.target.value)} className="mt-3 h-11 w-full rounded-md border border-[#cfd6d0] bg-white px-3 text-sm outline-none focus:border-[#28745c]">
            <option value="">请选择一个基金类别</option>
            {categories.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-sm font-bold">风格标签</span>
          <span className="mt-1 block text-xs text-[#7a8580]">可选；已确认画像、真实持仓同类分位、纪要推断和产品定位会分层标注</span>
          <select value={style} disabled={!category || loading} onChange={(event) => {
            const nextStyle = event.target.value
            setStyle(nextStyle)
            void loadCandidates(category, nextStyle)
          }} className="mt-3 h-11 w-full rounded-md border border-[#cfd6d0] bg-white px-3 text-sm outline-none focus:border-[#28745c] disabled:bg-[#f1f3f0] disabled:text-[#9aa39e]">
            <option value="">不限风格</option>
            {availableStyles.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          {category && !loading && availableStyles.length === 0 ? (
            <span className="mt-2 block text-xs leading-5 text-[#8a6c34]">该类别暂无可核验的风格标签，当前先按同类业绩和风险评价。</span>
          ) : null}
        </label>
      </section>

      {category && availableStyles.length ? (
        <section className="border border-[#dbe1dc] bg-white p-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-sm font-bold">按风格继续缩小范围</h2>
              <p className="mt-1 text-xs leading-6 text-[#7a8580]">标签优先使用已确认画像和真实持仓同类分位；基金专属纪要推断会单独标为建议，不冒充已确认风格；产品定位也单独标注。仍只在当前同类组内筛选。</p>
            </div>
            {style ? <button type="button" onClick={() => { setStyle(''); void loadCandidates(category) }} className="text-xs font-bold text-[#28745c]">清除风格筛选</button> : null}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {availableStyles.map((item) => {
              const option = styleOptions.find((entry) => entry.value === item)
              return (
              <button
                key={item}
                type="button"
                onClick={() => { setStyle(item); void loadCandidates(category, item) }}
                aria-pressed={style === item}
                className={`rounded-full border px-3 py-1.5 text-xs font-bold transition ${style === item ? 'border-[#28745c] bg-[#28745c] text-white' : 'border-[#cbd4ce] bg-white text-[#4d5d55] hover:border-[#7fa18f]'}`}
              >
                {item}{option ? ` ${option.matchedCount}` : ''}
              </button>
              )
            })}
          </div>
          <p className="mt-3 text-[11px] leading-5 text-[#89928d]">数字表示当前同类组内有该证据的可评价基金数。量化标签需达到同季度同类样本门槛；“产品定位”不冒充持仓风格。</p>
        </section>
      ) : null}

      <details className="border border-[#dbe1dc] bg-white" onToggle={(event) => {
        if (event.currentTarget.open) void loadCoverage()
      }}>
          <summary className="cursor-pointer list-none px-5 py-4 text-sm font-bold text-[#26362f]">
            数据准备情况：{coverage?.summary
              ? `${coverage.summary.readyCategoryCount} / ${coverage.summary.categoryCount}`
              : initialReadyCategoryCount} 个类别可以生成候选
          </summary>
          <div className="border-t border-[#e5e9e6] px-5 py-4">
            {coverageLoading ? (
              <div className="flex items-center gap-2 py-5 text-xs text-[#68746e]"><LoaderCircle className="h-4 w-4 animate-spin text-[#28745c]" />正在读取完整覆盖审计</div>
            ) : coverageError ? (
              <div className="flex items-center justify-between gap-4 py-3 text-xs text-[#8a5e20]"><span>{coverageError}</span><button type="button" onClick={() => void loadCoverage()} className="font-bold underline underline-offset-4">重新加载</button></div>
            ) : coverage?.groups.length ? (
              <>
              <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-xs">
                <thead className="text-[#748079]"><tr><th className="pb-3">基金类别</th><th className="pb-3">分类成员</th><th className="pb-3">数据库基金</th><th className="pb-3">评价方法</th><th className="pb-3">指标齐全</th><th className="pb-3">风格标签</th><th className="pb-3">可推荐</th></tr></thead>
                <tbody className="divide-y divide-[#edf0ed]">
                  {coverage.groups.map((group) => (
                    <tr key={group.key}>
                      <td className="py-3 pr-4"><span className="font-bold text-[#33463d]">{group.name}</span><span className={`ml-2 rounded-sm px-1.5 py-0.5 text-[10px] ${group.status === 'ready' ? 'bg-[#e4f1ea] text-[#21664d]' : group.status === 'partial' ? 'bg-[#fff2d8] text-[#805b18]' : 'bg-[#f5e9e6] text-[#8d4e44]'}`}>{group.status === 'ready' ? '可用' : group.status === 'partial' ? '待补' : '无样本'}</span></td>
                      <td className="py-3">{group.classifiedCount}</td>
                      <td className="py-3">{group.databaseFundCount}</td>
                      <td className="py-3">{group.evaluationMethodReadyCount}</td>
                      <td className="py-3">{group.metricReadyCount}</td>
                      <td className="py-3">{group.styleReadyCount}</td>
                      <td className="py-3 font-bold text-[#28664f]">{group.recommendationReadyCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
              <p className="mt-4 text-xs leading-6 text-[#748079]">指标缺口只通过真实净值数据补齐；样本不足的类别不会出现在上方可选列表中。</p>
              </>
            ) : null}
          </div>
        </details>

      <section>
        <div className="flex flex-wrap items-end justify-between gap-4 pb-4">
          <div>
            <h2 className="text-xl font-bold">候选基金 <span className="text-[#28745c]">{recommendations.length}</span> / 10</h2>
            <p className="mt-1 text-xs text-[#79847e]">
              {category
                ? `完整同类组 ${peerUniverseCount} 只，${evidenceEligibleCount} 只通过关键证据门槛，${longTermReadyCount} 只具备近 3 年完整收益风险证据${style ? `，${styleMatchedCount} 只匹配“${style}”` : ''}。`
                : `基金数据库共 ${universeTotal.toLocaleString('zh-CN')} 只，选择类别后开始评价。`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {recommendations.length ? <button type="button" onClick={() => void openWatchlist(recommendations)} className="inline-flex h-10 items-center gap-2 bg-[#173f35] px-4 text-sm font-bold text-white"><BookmarkPlus className="h-4 w-4" />一键加入当前候选</button> : null}
            {recommendations.length >= 2 ? (
              <Link href={compareHref} className="inline-flex h-10 items-center gap-2 rounded-md border border-[#9ab3a8] px-4 text-sm font-bold text-[#285d4b] hover:bg-[#edf4f0]">
                <GitCompareArrows className="h-4 w-4" />比较前 {Math.min(6, recommendations.length)} 只
              </Link>
            ) : null}
          </div>
        </div>

        {loading ? (
          <div className="flex min-h-52 items-center justify-center gap-3 border border-dashed border-[#cbd3cd] bg-white text-sm text-[#66726c]">
            <LoaderCircle className="h-5 w-5 animate-spin text-[#28745c]" />正在读取同类专业评价
          </div>
        ) : !category ? (
          <div className="flex min-h-52 flex-col items-center justify-center border border-dashed border-[#cbd3cd] bg-white px-6 text-center">
            <Tags className="h-6 w-6 text-[#28745c]" />
            <strong className="mt-3 text-sm">先选择一个基金类别</strong>
            <span className="mt-2 text-xs leading-6 text-[#78837d]">系统不会在股票、债券、货币和指数基金之间进行横向排名。</span>
          </div>
        ) : recommendations.length === 0 ? (
          <div className="flex min-h-52 flex-col items-center justify-center border border-dashed border-[#cbd3cd] bg-white px-6 text-center">
            <CircleAlert className="h-6 w-6 text-[#9a7a3a]" />
            <strong className="mt-3 text-sm">当前没有满足条件的候选基金</strong>
            {style && evidenceEligibleCount > 0 ? (
              <span className="mt-2 text-xs leading-6 text-[#78837d]">该类别有 {evidenceEligibleCount} 只通过证据门槛，但没有基金匹配“{style}”标签；可以先选择“不限风格”。</span>
            ) : excludedCount > 0 ? (
              <div className="mt-2 max-w-xl text-left text-xs leading-6 text-[#78837d]">
                <div>同类组共 {peerUniverseCount} 只，{excludedCount} 只因证据不足未进入候选：</div>
                <ul className="mt-1 list-disc pl-5">
                  {exclusionReasons.map(([reason, count]) => <li key={reason}>{exclusionReasonLabel(reason)}：{count} 只</li>)}
                </ul>
              </div>
            ) : (
              <span className="mt-2 text-xs leading-6 text-[#78837d]">当前类别尚未形成可核验的同类评价样本。</span>
            )}
          </div>
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {recommendations.map((fund, index) => {
              const annualReturn = returnMetric(fund)
              const drawdown = drawdownMetric(fund)
              const score = professionalFundScore(fund)
              const scoreEvidence = professionalScoreEvidence(fund)
              const peerPosition = professionalScorePeerPosition(fund)
              const baseFee = baseFeeRate(fund)
              const evidence = recommendationEvidence(fund)
              const multiPeriod = evidence.multiPeriod
              const managerTenure = evidence.managerTenure
              const primaryStyle = styleLabel(fund)
              const primaryStyleStatus = styleLabelStatus(fund)
              const bondEvidence = bondHoldingEvidence(fund)
              const fofEvidence = fofHoldingEvidence(fund)
              const primaryStyleSuffix = primaryStyleStatus === 'llm_suggested'
                ? ' · 纪要推断'
                : primaryStyleStatus === 'derived' ? ' · 产品定位' : ''
              return (
                <article key={fund.windCode} className="grid grid-cols-[2.6rem_minmax(0,1fr)] gap-4 border border-[#dbe1dc] bg-white p-5 transition hover:border-[#90ad9f]">
                  <div className="grid h-10 w-10 place-items-center rounded-md bg-[#edf2ee] text-sm font-black text-[#32614f]">{String(index + 1).padStart(2, '0')}</div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <Link href={`/funds/${encodeURIComponent(fund.windCode)}`} className="font-bold text-[#1b2923] hover:text-[#28745c]">{fund.name || fund.windCode}</Link>
                        <p className="mt-1 text-xs text-[#7a8580]">{fund.windCode} · {managerName(fund)}</p>
                      </div>
                      <div className="text-right">
                        <span className="block text-[11px] text-[#7a8580]">同类专业评分</span>
                        <strong className="mt-1 block text-xl text-[#24664f]">{score?.toFixed(1) || '—'}</strong>
                        <span className={`mt-1 block text-[11px] ${scoreEvidence.status === 'partial' ? 'text-[#856225]' : 'text-[#426756]'}`}>{scoreEvidence.label}</span>
                        {peerPosition.rank != null && peerPosition.peerCount != null
                          ? <span className="mt-1 block text-[11px] text-[#7a8580]">同类第 {peerPosition.rank} / {peerPosition.peerCount}</span>
                          : peerPosition.percentile != null
                            ? <span className="mt-1 block text-[11px] text-[#7a8580]">同类有利分位 {peerPosition.percentile.toFixed(0)}%</span>
                            : null}
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs">
                      <span className="rounded-sm bg-[#e9f0ec] px-2 py-1 text-[#315e4d]">{peerGroup(fund)}</span>
                      {style ? <span className="rounded-sm bg-[#e9e4d6] px-2 py-1 font-bold text-[#6d5725]">匹配风格：{style}</span> : null}
                      {!style || primaryStyle !== style ? <span className="rounded-sm bg-[#f0eee8] px-2 py-1 text-[#685f49]">{style ? `主标签：${primaryStyle}` : primaryStyle}{primaryStyleSuffix}</span> : null}
                    </div>
                    {bondEvidence.available ? (
                      <p className="mt-2 text-[11px] leading-5 text-[#7b817d]">债券风格依据：近 {bondEvidence.periodCount} 期公开重仓债券{bondEvidence.source ? ` · ${bondEvidence.source}` : ''}；不代表全部组合。</p>
                    ) : null}
                    {fofEvidence.available ? (
                      <p className="mt-2 text-[11px] leading-5 text-[#7b817d]">FOF 穿透依据：{fofEvidence.reportDate} 公开底层基金 {fofEvidence.disclosedFundCount} 只{fofEvidence.disclosedNavRatio != null ? ` · 占净值 ${fofEvidence.disclosedNavRatio.toFixed(2)}%` : ''}{fofEvidence.top5NavRatio != null ? ` · 前 5 大 ${fofEvidence.top5NavRatio.toFixed(2)}%` : ''}；不代表全部组合。</p>
                    ) : null}
                    {managerTenure.applicable ? (
                      <p className={`mt-2 text-[11px] leading-5 ${managerTenure.coverageStatus === 'full_tenure' ? 'text-[#426756]' : 'text-[#856225]'}`}>
                        <strong>经理任期证据：</strong>{managerTenure.coverageStatus === 'full_tenure'
                          ? `完整覆盖${managerTenure.totalReturn == null ? '' : ` · 任期收益 ${formatPercent(managerTenure.totalReturn)}`}`
                          : managerTenure.coverageStatus === 'partial_since_data_start'
                            ? `本地仅覆盖 ${managerTenure.coverageRatio == null ? '不完整区间' : `${Math.round(managerTenure.coverageRatio * 100)}%`} · 不计分、不排名`
                            : managerTenure.note || '待补，不能把完整历史业绩归因给现任经理'}
                      </p>
                    ) : null}
                    <p className={`mt-2 text-[11px] leading-5 ${scoreEvidence.status === 'partial' ? 'text-[#856225]' : 'text-[#617069]'}`}>
                      <strong>评分证据：</strong>{scoreEvidence.label}
                      {scoreEvidence.coveragePercent != null ? ` · 评价维度覆盖 ${scoreEvidence.coveragePercent}%` : ''}
                      {scoreEvidence.missingDimensions.length ? ` · 待补：${scoreEvidence.missingDimensions.join('、')}` : ''}
                      {scoreEvidence.dataQualityScore != null ? ` · 已用数据质量 ${scoreEvidence.dataQualityScore.toFixed(0)}/100` : ''}
                    </p>
                    <p className={`mt-2 text-[11px] leading-5 ${multiPeriod.status === 'long_term_ready' ? 'text-[#426756]' : 'text-[#856225]'}`}>
                      <strong>长期证据：</strong>{multiPeriod.status === 'long_term_ready'
                        ? `近 3 年收益、回撤和 Sharpe 完整${multiPeriod.usedInScore ? '，已纳入当前类别评分' : '，用于长期观察'}${multiPeriod.consistencyLabel ? ` · ${multiPeriod.consistencyLabel}` : ''}`
                        : '近 3 年完整收益风险证据不足，当前候选主要依据近 1 年数据'}
                    </p>
                    <div className="mt-4 grid grid-cols-3 gap-x-3 gap-y-4 border-y border-[#edf0ed] py-3 text-xs">
                      <div><span className="block text-[#7a8580]">近 6 月</span><strong className="mt-1 block">{formatPercent(multiPeriod.return6m)}</strong></div>
                      <div><span className="block text-[#7a8580]">近 1 年</span><strong className="mt-1 block">{formatPercent(multiPeriod.return1y ?? annualReturn)}</strong></div>
                      <div><span className="block text-[#7a8580]">近 3 年年化</span><strong className="mt-1 block">{formatPercent(multiPeriod.annualizedReturn3y)}</strong></div>
                      <div><span className="block text-[#7a8580]">近 1 年回撤</span><strong className="mt-1 block">{formatPercent(multiPeriod.maxDrawdown1y ?? drawdown)}</strong></div>
                      <div><span className="block text-[#7a8580]">近 3 年回撤</span><strong className="mt-1 block">{formatPercent(multiPeriod.maxDrawdown3y)}</strong></div>
                      <div><span className="block text-[#7a8580]">基金规模</span><strong className="mt-1 block">{formatAsset(fund.totalAsset)}</strong>{baseFee != null ? <span className="mt-1 block text-[10px] font-normal text-[#89928d]">管理+托管费 {baseFee.toFixed(2)}%</span> : null}</div>
                    </div>
                    <div className="mt-3 grid gap-2 text-xs leading-5 text-[#66726c]">
                      <div className="flex gap-2">
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#2d7b5e]" />
                        <span><strong className="text-[#345e4e]">入选依据：</strong>{evidence.reasons.join('；')}</span>
                      </div>
                      <div className="flex gap-2">
                        <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-[#a07837]" />
                        <span><strong className="text-[#775e32]">主要风险：</strong>{evidence.risks.join(' ')}</span>
                      </div>
                    </div>
                    {evidence.alternatives.length ? (
                      <div className="mt-3 border-t border-[#edf0ed] pt-3 text-xs">
                        <strong className="text-[#526159]">可替代基金：</strong>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {evidence.alternatives.map((alternative) => (
                            <Link key={alternative.windCode} href={`/funds/${encodeURIComponent(alternative.windCode)}`} className="rounded-sm bg-[#f1f4f1] px-2 py-1 text-[#315e4d] hover:bg-[#e5ede8]">
                              {alternative.name}{alternative.overallScore != null ? ` · ${alternative.overallScore.toFixed(1)} 分` : ''}
                            </Link>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    <p className="mt-3 text-[11px] text-[#89928d]">数据截至 {evidence.dataAsOf || fund.navDate || '待补'} · 仅在“{category}”同类组内评价</p>
                    <div className="mt-4 flex flex-wrap gap-4">
                      <Link href={`/funds/${encodeURIComponent(fund.windCode)}`} className="inline-flex items-center gap-1 text-xs font-bold text-[#28745c]">查看基金与风险 <ArrowRight className="h-3.5 w-3.5" /></Link>
                      <Link href={`/analysis?${new URLSearchParams({ fundCode: fund.windCode }).toString()}`} className="inline-flex items-center gap-1 text-xs font-bold text-[#6a5840]"><Bot className="h-3.5 w-3.5" />现场分析这只基金</Link>
                      <button type="button" onClick={() => void openWatchlist([fund])} className="inline-flex items-center gap-1 text-xs font-bold text-[#315d4c]"><BookmarkPlus className="h-3.5 w-3.5" />加入自选</button>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </section>

      {watchlistTargets.length ? (
        <div className="fixed inset-0 z-[70] grid place-items-center bg-[#13221c]/55 p-4" role="dialog" aria-modal="true" aria-label="加入我的自选">
          <div className="w-full max-w-md border border-[#d7ddd8] bg-[#fbfcfa] p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div><div className="text-xs font-bold uppercase tracking-[0.1em] text-[#28745c]">加入自选</div><h2 className="mt-2 text-xl font-bold text-[#18231e]">{watchlistTargets.length === 1 ? watchlistTargets[0].name : `当前 ${watchlistTargets.length} 只候选基金`}</h2><p className="mt-2 text-xs leading-5 text-[#75817b]">系统会把每只基金的入选依据保存为收藏理由。</p></div>
              <button type="button" onClick={() => setWatchlistTargets([])} className="grid h-8 w-8 place-items-center text-[#69756f] hover:bg-[#edf0ed]" aria-label="关闭"><X className="h-4 w-4" /></button>
            </div>
            <label className="mt-6 block text-xs font-bold text-[#5e6a64]">选择分组
              <select value={selectedWatchlistId} onChange={(event) => setSelectedWatchlistId(event.target.value)} className="mt-2 h-11 w-full border border-[#cbd3cd] bg-white px-3 text-sm outline-none focus:border-[#28745c]">
                {watchlists.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            <div className="mt-6 flex justify-end gap-2"><button type="button" onClick={() => setWatchlistTargets([])} className="h-10 border border-[#cbd3cd] px-4 text-sm font-bold text-[#5f6b65]">取消</button><button type="button" onClick={() => void saveToWatchlist()} disabled={savingWatchlist || !selectedWatchlistId} className="h-10 bg-[#173f35] px-5 text-sm font-bold text-white disabled:opacity-50">{savingWatchlist ? '加入中' : `加入 ${watchlistTargets.length} 只`}</button></div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
