'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Search, Sparkles, Calendar, FileText, ShieldCheck, Tag, Download } from 'lucide-react'
import { canonicalResearchHref, materialEvidenceHref } from '@/lib/research-platform/routes'

interface SearchResult {
  id: string
  title: string
  summary: string | null
  reportDate: string
  source: string
  tags: string[]
  similarity: string
  targetId?: string
  targetType?: string
  reportType?: string
  reportTypeLabel?: string
  purchasePlan?: 'lump_sum' | 'sip'
  plannedAmount?: number | null
  actionHref?: string
  relatedCodes?: string[]
  decisionSummary?: {
    verifyFirstCount?: number
    salesRuleGapCount?: number
    totalFunds?: number
    decisionFundName?: string
    decisionFundCode?: string
    decisionBasis?: string
    topPurchaseDecisionLabel?: string
    topPurchaseDecisionAction?: string
    topPurchaseDecisionReason?: string
    sourceDecisionCards?: Array<{
      windCode: string
      fundName: string
      label: string
      latestConclusion: string
      nextAction: string
      bullets: string[]
      hardBoundary: string
      reviewFreshnessStatus?: string
      reviewFreshnessLabel?: string
      reviewFreshnessDetail?: string
    }>
    replayEvidenceGateStatus?: string
    replayEvidenceGateLabel?: string
    replayEvidenceGateMissingEvidence?: string[]
    replayEvidenceGatePassCount?: number
    replayEvidenceGateVerifyCount?: number
  }
  currentSalesRuleGate?: {
    status: 'ready' | 'blocked' | 'unknown'
    missingCount: number | null
    missingItems: string[]
    actionHref: string
    source: string
    blockedFunds?: number
  }
  riskLevelGatePolicy?: {
    status: string
    label: string
    detail: string
    tone: 'emerald' | 'amber' | 'slate'
    requiresRegeneration: boolean
    effectiveDate: string
    signals?: string[]
  }
}

function appendReturnTo(href: string, returnTo: string) {
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`
}

function resultPurchasePlan(result: Pick<SearchResult, 'purchasePlan'>) {
  return result.purchasePlan === 'lump_sum' ? 'lump_sum' : 'sip'
}

function resultPlannedAmount(result: Pick<SearchResult, 'plannedAmount'>) {
  const amount = Number(result.plannedAmount)
  return Number.isFinite(amount) && amount > 0 ? amount : null
}

function isReviewQueueGate(gate?: SearchResult['currentSalesRuleGate'] | null) {
  return Boolean(
    gate?.actionHref?.startsWith('/alerts')
      || gate?.actionHref?.includes('section=review-events')
      || gate?.source?.includes('local.alert_events.sales_rule_evidence'),
  )
}

function appendPurchaseContext(href: string, result: Pick<SearchResult, 'purchasePlan' | 'plannedAmount'>) {
  const [path, query = ''] = href.split('?')
  const params = new URLSearchParams(query)
  const purchasePlan = resultPurchasePlan(result)
  const plannedAmount = resultPlannedAmount(result)
  params.set('purchasePlan', purchasePlan)
  if (plannedAmount) {
    params.set('plannedAmount', String(plannedAmount))
    params.set(purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(plannedAmount))
  }
  return `${path}?${params.toString()}`
}

function reportTypeClass(reportType?: string) {
  if (reportType === 'fund_pre_purchase_check') return 'bg-amber-100 text-amber-800'
  if (reportType === 'fund_comparison_report') return 'bg-purple-100 text-purple-800'
  if (reportType === 'fund_pool_shortlist_report') return 'bg-emerald-100 text-emerald-800'
  if (reportType === 'fund_pool_gap_snapshot') return 'bg-slate-100 text-slate-700'
  return 'bg-blue-100 text-blue-800'
}

function followUpClass(tone: string) {
  if (tone === 'amber') return 'border-amber-100 bg-amber-50 text-amber-900'
  if (tone === 'purple') return 'border-purple-100 bg-purple-50 text-purple-900'
  if (tone === 'blue') return 'border-blue-100 bg-blue-50 text-blue-900'
  if (tone === 'emerald') return 'border-emerald-100 bg-emerald-50 text-emerald-900'
  return 'border-slate-100 bg-slate-50 text-slate-900'
}

function riskLevelPolicyBadgeClass(tone: NonNullable<SearchResult['riskLevelGatePolicy']>['tone']) {
  if (tone === 'emerald') return 'bg-emerald-100 text-emerald-800'
  if (tone === 'amber') return 'bg-amber-100 text-amber-800'
  return 'bg-slate-100 text-slate-700'
}

function searchTodayUsabilityClass(decision: string) {
  if (decision === '只作历史回看') return 'border-rose-100 bg-rose-50 text-rose-950'
  if (decision === '需重跑') return 'border-amber-100 bg-amber-50 text-amber-950'
  return 'border-emerald-100 bg-emerald-50 text-emerald-950'
}

function searchTodayUsabilityBadgeClass(decision: string) {
  if (decision === '只作历史回看') return 'bg-rose-100 text-rose-800'
  if (decision === '需重跑') return 'bg-amber-100 text-amber-800'
  return 'bg-emerald-100 text-emerald-800'
}

function replayEvidenceGateBadgeClass(status?: string) {
  if (status === 'pass') return 'bg-emerald-100 text-emerald-800'
  if (status === 'verify_first' || status === 'missing') return 'bg-amber-100 text-amber-800'
  return 'bg-slate-100 text-slate-700'
}

function replayEvidenceGateCardClass(status?: string) {
  if (status === 'pass') return 'border-emerald-100 bg-emerald-50 text-emerald-950'
  if (status === 'verify_first' || status === 'missing') return 'border-amber-100 bg-amber-50 text-amber-950'
  return 'border-slate-100 bg-slate-50 text-slate-900'
}

function riskLevelSourceQueueHref(result: SearchResult) {
  const codes = Array.from(new Set((result.relatedCodes || [])
    .concat(result.targetType === 'fund' && result.targetId ? [result.targetId] : [])
    .map((code) => String(code || '').trim().toUpperCase())
    .filter(Boolean)))
  const params = new URLSearchParams({
    scope: 'market',
    focus: 'risk_level',
    queueMode: 'candidate_missing_risk',
  })
  if (codes.length > 0) params.set('codes', codes.join(','))
  return appendReturnTo(appendPurchaseContext(materialEvidenceHref(params), result), '/reports/search')
}

function poolReviewHref(result: SearchResult) {
  return result.targetId
    ? appendPurchaseContext(`/pools?poolId=${encodeURIComponent(result.targetId)}&status=candidate`, result)
    : appendPurchaseContext('/pools?status=candidate', result)
}

function shortlistReviewFreshness(result: SearchResult) {
  return result.decisionSummary?.sourceDecisionCards?.find((card) => card.reviewFreshnessLabel) || null
}

function searchResultTodayUsability(result: SearchResult, followUp = searchResultFollowUp(result)) {
  const salesGate = result.currentSalesRuleGate?.status || 'none'
  const reviewFreshness = shortlistReviewFreshness(result)
  const reviewFreshnessLabel = reviewFreshness?.reviewFreshnessLabel || ''
  const reviewFreshnessBlocked = Boolean(
    reviewFreshness
      && (
        reviewFreshness.reviewFreshnessStatus === 'overdue'
        || reviewFreshness.reviewFreshnessStatus === 'missing'
        || reviewFreshnessLabel.includes('过期')
        || reviewFreshnessLabel.includes('待补')
      ),
  )
  const replayStatus = result.decisionSummary?.replayEvidenceGateStatus
  const decision = salesGate === 'blocked' || salesGate === 'unknown'
    ? '只作历史回看'
    : result.riskLevelGatePolicy?.requiresRegeneration || reviewFreshnessBlocked || (replayStatus && replayStatus !== 'pass')
      ? '需重跑'
      : '今天可沿用研究'
  const hardBoundary = decision === '今天可沿用研究'
    ? '搜索命中只证明历史证据链可参考；进入研究复核前仍要重新核验最新销售平台、R1-R5、费率、申赎、限购和净值回放。'
    : '搜索命中不能替代今日证据；销售规则、R1-R5、费率、申赎、限购、净值回放或测算证据任一缺失，只能降级为补证观察或历史回看。'
  return {
    decision,
    reason: followUp.detail,
    actionLabel: followUp.label,
    actionHref: followUp.href,
    hardBoundary,
  }
}

function searchResultFollowUp(result: SearchResult) {
  const relatedCodes = result.relatedCodes || []
  const gate = result.currentSalesRuleGate
  if (gate?.status === 'blocked' || gate?.status === 'unknown') {
    const reviewQueueGate = isReviewQueueGate(gate)
    return {
      label: reviewQueueGate ? '处理复查队列' : '先补销售规则',
      href: appendReturnTo(gate.actionHref ? canonicalResearchHref(gate.actionHref) : appendPurchaseContext(materialEvidenceHref(), result), '/reports/search'),
      tone: 'amber',
      detail: gate.status === 'blocked'
        ? reviewQueueGate
          ? `复查队列仍有 ${gate.missingCount ?? 0} 项未解决事件${gate.blockedFunds ? `，涉及 ${gate.blockedFunds} 只基金` : ''}；处理前这份报告只能回看，不能作为继续研究复核的有效留痕。`
          : `仍缺 ${gate.missingCount ?? 0} 项${gate.blockedFunds ? `，涉及 ${gate.blockedFunds} 只基金` : ''}；补齐前这份报告只能回看，不能作为继续研究复核的有效留痕。`
        : '先完成销售规则扫描，再判断报告是否仍然有效。',
    }
  }
  if (result.riskLevelGatePolicy?.requiresRegeneration) {
    return {
      label: '补 R1-R5 来源',
      href: riskLevelSourceQueueHref(result),
      tone: 'amber',
      detail: `${result.riskLevelGatePolicy.detail} 先补 30 天来源背书，再重跑或复核报告。`,
    }
  }
  const reviewFreshness = shortlistReviewFreshness(result)
  if (reviewFreshness && (result.reportType === 'fund_pool_shortlist_report' || result.reportType === 'fund_pool_gap_snapshot' || result.targetType === 'fund_pool')) {
    const reviewFreshnessLabel = reviewFreshness.reviewFreshnessLabel || ''
    const blockedByReviewDate = reviewFreshness.reviewFreshnessStatus === 'overdue'
      || reviewFreshness.reviewFreshnessStatus === 'missing'
      || reviewFreshnessLabel.includes('过期')
      || reviewFreshnessLabel.includes('待补')
    return {
      label: blockedByReviewDate ? '更新复查结论' : '回研究清单复核',
      href: poolReviewHref(result),
      tone: blockedByReviewDate ? 'amber' : 'emerald',
      detail: `${reviewFreshness.fundName || reviewFreshness.windCode || '候选基金'}：${reviewFreshnessLabel || '复查时效待核'}${reviewFreshness.reviewFreshnessDetail ? `；${reviewFreshness.reviewFreshnessDetail}` : ''}。搜索命中的短名单报告不能替代今天的复查。`,
    }
  }
  if (result.reportType?.includes('comparison') && result.decisionSummary?.replayEvidenceGateStatus && result.decisionSummary.replayEvidenceGateStatus !== 'pass' && relatedCodes.length >= 2) {
    return {
      label: '重跑真实回放横评',
      href: appendPurchaseContext(`/analysis/comparison?codes=${encodeURIComponent(relatedCodes.join(','))}&autoReplay=1`, result),
      tone: 'amber',
      detail: result.decisionSummary.replayEvidenceGateStatus === 'missing'
        ? '搜索命中的旧横评缺测算证据门禁；重跑真实净值、费率、回撤预算回放前只能回看。'
        : '搜索命中的横评测算证据门禁未通过；补齐费用、回撤预算和回本等待证据后再使用。',
    }
  }
  if (result.reportType?.includes('comparison') && relatedCodes.length >= 2) {
    return {
      label: '重跑横向比较',
      href: appendPurchaseContext(`/analysis/comparison?codes=${encodeURIComponent(relatedCodes.join(','))}&autoReplay=1`, result),
      tone: 'purple',
      detail: result.decisionSummary?.decisionFundName
        ? `重新核验 ${result.decisionSummary.decisionFundName} 的排序、费后回放和替代关系。`
        : '重新核验排序、费后回放和替代关系。',
    }
  }
  if (result.reportType === 'fund_pre_purchase_check' && result.targetId) {
    return {
      label: '复核基金详情',
      href: appendPurchaseContext(`/funds/${encodeURIComponent(result.targetId)}`, result),
      tone: 'blue',
      detail: '回到单基金详情复核净值回放、费用、持仓和替代候选。',
    }
  }
  if ((result.reportType === 'fund_pool_shortlist_report' || result.reportType === 'fund_pool_gap_snapshot' || result.targetType === 'fund_pool') && result.targetId) {
    return {
      label: '维护研究清单',
      href: poolReviewHref(result),
      tone: 'emerald',
      detail: '回到研究清单维护研究队列、补证状态和下一轮横向比较。',
    }
  }
  if (result.targetType === 'manager' && result.targetId) {
    return {
      label: '查看基金经理',
      href: `/managers/${encodeURIComponent(result.targetId)}`,
      tone: 'slate',
      detail: '回到基金经理维度复核管理产品和任职证据。',
    }
  }
  return {
    label: '查看报告',
    href: result.actionHref || `/reports/${result.id}`,
    tone: 'slate',
    detail: '进入报告详情查看结构化证据和正文留痕。',
  }
}

export default function SemanticSearchPage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searched, setSearched] = useState(false)

  const searchTodayUsabilityRows = results.map((result) => {
    const followUp = searchResultFollowUp(result)
    return {
      result,
      followUp,
      usability: searchResultTodayUsability(result, followUp),
    }
  })
  const searchTodayUsabilityAudit = [
    {
      decision: '只作历史回看',
      title: '先排除失效命中',
      detail: '当前销售规则/R1-R5 或复查队列仍阻断；搜索结果只能回看，不能沿用为研究复核依据。',
      rows: searchTodayUsabilityRows.filter((row) => row.usability.decision === '只作历史回看'),
    },
    {
      decision: '需重跑',
      title: '再重跑证据链',
      detail: '旧 R1-R5、复查时效、回放测算或横评证据不足；需要回原页面补证重跑。',
      rows: searchTodayUsabilityRows.filter((row) => row.usability.decision === '需重跑'),
    },
    {
      decision: '今天可沿用研究',
      title: '最后保留研究线索',
      detail: '仅作为研究留痕和候选复核线索，进入正式研究复核前仍要核验最新证据。',
      rows: searchTodayUsabilityRows.filter((row) => row.usability.decision === '今天可沿用研究'),
    },
  ]

  const downloadSearchTodayUsabilityTsv = () => {
    if (!searchTodayUsabilityRows.length) return
    const header = ['今日结论', '报告标题', '报告类型', '匹配度', '下一步', '处理入口', '硬边界']
    const rows = searchTodayUsabilityRows.map((row) => [
      row.usability.decision,
      row.result.title,
      row.result.reportTypeLabel || row.result.reportType || '',
      `${(Number(row.result.similarity) * 100).toFixed(1)}%`,
      row.usability.actionLabel,
      row.usability.actionHref,
      row.usability.hardBoundary,
    ])
    const tsv = [header, ...rows]
      .map((row) => row.map((cell) => String(cell || '').replace(/\t/g, ' ').replace(/\n/g, ' ')).join('\t'))
      .join('\n')
    const blob = new Blob([`\ufeff${tsv}`], { type: 'text/tab-separated-values;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `报告搜索今日沿用判断-${new Date().toISOString().slice(0, 10)}.tsv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!query.trim()) return

    setSearching(true)
    setSearched(true)

    try {
      const response = await fetch('/api/reports/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, limit: 20, threshold: 0.6 })
      })

      const data = await response.json()

      if (response.ok) {
        setResults(data.results || [])
      } else {
        console.error('搜索失败:', data.error)
        setResults([])
      }
    } catch (error) {
      console.error('搜索失败:', error)
      setResults([])
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Link
        href="/reports"
        className="inline-flex items-center text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        返回列表
      </Link>

      <div className="bg-white rounded-lg shadow p-6">
        <form onSubmit={handleSearch} className="space-y-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="输入您想了解的内容，例如：这位基金经理的投资风格是什么？"
              className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            />
          </div>
          <button
            type="submit"
            disabled={!query.trim() || searching}
            className="w-full flex items-center justify-center px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {searching ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                搜索中...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 mr-2" />
                搜索报告
              </>
            )}
          </button>
        </form>
      </div>

      {/* 搜索结果 */}
      {searched && (
        <div className="bg-white rounded-lg shadow" data-testid="report-search-buy-before-results">
          {results.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              {searching ? '搜索中...' : '未找到相关报告'}
            </div>
          ) : (
            <>
              <div className="p-4 border-b border-gray-200">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-sm text-gray-600">
                      找到 <span className="font-medium text-gray-900">{results.length}</span> 个相关报告
                    </p>
                    <p className="mt-1 text-xs leading-5 text-gray-500">
                      搜索只负责找历史材料；下面先判断今天能否沿用，再进入补证、重跑或报告详情。
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={downloadSearchTodayUsabilityTsv}
                    disabled={!searchTodayUsabilityRows.length}
                    className="inline-flex items-center gap-1 rounded-full bg-slate-950 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                    data-testid="report-search-today-usability-download"
                  >
                    <Download className="h-3.5 w-3.5" />
                    下载搜索沿用 TSV
                  </button>
                </div>
                <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4" data-testid="report-search-today-usability-audit">
                  <div className="text-sm font-semibold text-slate-950">搜索结果今日沿用判断</div>
                  <p className="mt-1 text-xs leading-5 text-slate-600">
                    将命中的历史报告分成“只作历史回看 / 需重跑 / 今天可沿用研究”，防止搜索命中绕过最新证据门禁。
                  </p>
                  <div className="mt-3 grid gap-3 lg:grid-cols-3">
                    {searchTodayUsabilityAudit.map((lane) => (
                      <div key={lane.decision} className={`rounded-2xl border p-3 ${searchTodayUsabilityClass(lane.decision)}`}>
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="text-sm font-semibold">{lane.title}</div>
                            <div className="mt-1 text-xs leading-5 opacity-80">{lane.detail}</div>
                          </div>
                          <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${searchTodayUsabilityBadgeClass(lane.decision)}`}>
                            {lane.rows.length}
                          </span>
                        </div>
                        <div className="mt-2 space-y-2">
                          {lane.rows.slice(0, 2).map((row) => (
                            <div key={`${lane.decision}-${row.result.id}`} className="rounded-xl bg-white/80 p-2 text-xs shadow-sm">
                              <div className="truncate font-semibold text-slate-950">{row.result.title}</div>
                              <div className="mt-1 leading-5 opacity-80">{row.usability.actionLabel} · {(Number(row.result.similarity) * 100).toFixed(1)}%</div>
                            </div>
                          ))}
                          {!lane.rows.length ? (
                            <div className="rounded-xl border border-dashed border-white/80 bg-white/60 px-3 py-4 text-xs leading-5 opacity-70">
                              当前搜索暂无该类命中。
                            </div>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-3 rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-xs leading-5 text-rose-800">
                    搜索沿用硬边界：历史报告不能覆盖今日销售平台/R1-R5/费率/申赎/限购/净值回放；硬证据不足时只给补证或重跑动作，不给申赎指令。
                  </div>
                </div>
              </div>
              <div className="divide-y divide-gray-200">
                {results.map((result) => {
                  const followUp = searchResultFollowUp(result)
                  const todayUsability = searchResultTodayUsability(result, followUp)
                  const reviewQueueGate = isReviewQueueGate(result.currentSalesRuleGate)
                  return (
                  <div
                    key={result.id}
                    className="p-6 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <Link href={result.actionHref || `/reports/${result.id}`} className="flex-1">
                        <h3 className="text-lg font-semibold text-gray-900 hover:text-purple-700">
                          {result.title}
                        </h3>
                      </Link>
                      <span className="ml-4 px-2 py-1 bg-purple-100 text-purple-800 text-xs rounded-full">
                        相似度 {(Number(result.similarity) * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="mb-3 flex flex-wrap gap-2">
                      {result.reportTypeLabel ? (
                        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${reportTypeClass(result.reportType)}`}>
                          {result.reportTypeLabel}
                        </span>
                      ) : null}
                      {result.targetId ? (
                        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">
                          {result.targetId}
                        </span>
                      ) : null}
                      {result.decisionSummary?.totalFunds ? (
                        <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-700">
                          对象 {result.decisionSummary.totalFunds}
                        </span>
                      ) : null}
                      {result.decisionSummary?.verifyFirstCount ? (
                        <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs text-amber-800">
                          先补证 {result.decisionSummary.verifyFirstCount}
                        </span>
                      ) : null}
                      {result.currentSalesRuleGate?.status === 'blocked' ? (
                        <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">
                          {reviewQueueGate ? '复查队列未清零，仅供回看' : '当前规则待补，仅供回看'}
                        </span>
                      ) : null}
                      {result.currentSalesRuleGate?.status === 'ready' ? (
                        <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-800">
                          当前规则无硬缺口
                        </span>
                      ) : null}
                      {result.riskLevelGatePolicy ? (
                        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${riskLevelPolicyBadgeClass(result.riskLevelGatePolicy.tone)}`} data-testid="report-search-risk-level-policy">
                          R1-R5：{result.riskLevelGatePolicy.label}
                        </span>
                      ) : null}
                      {result.decisionSummary?.replayEvidenceGateStatus ? (
                        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${replayEvidenceGateBadgeClass(result.decisionSummary.replayEvidenceGateStatus)}`}>
                          测算证据：{result.decisionSummary.replayEvidenceGateLabel || result.decisionSummary.replayEvidenceGateStatus}
                        </span>
                      ) : null}
                    </div>
                    {result.summary && (
                      <p className="text-sm text-gray-600 mb-3 line-clamp-2">
                        {result.summary}
                      </p>
                    )}
                    <div className={`mb-3 rounded-xl border px-4 py-3 text-sm ${searchTodayUsabilityClass(todayUsability.decision)}`} data-testid="report-search-result-today-usability">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="font-semibold">今日沿用判断：{todayUsability.decision}</div>
                        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${searchTodayUsabilityBadgeClass(todayUsability.decision)}`}>
                          搜索命中 ≠ 今日可用
                        </span>
                      </div>
                      <div className="mt-1 text-xs leading-5 opacity-80">{todayUsability.reason}</div>
                      <div className="mt-2 rounded-lg bg-white/70 px-2 py-1.5 text-xs leading-5 text-slate-700">
                        {todayUsability.hardBoundary}
                      </div>
                    </div>
                    {result.currentSalesRuleGate?.status === 'blocked' ? (
                      <div className="mb-3 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="report-search-sales-rule-gate">
                        <div className="font-semibold">
                          搜索命中的旧报告仅供回看：{reviewQueueGate ? `复查队列仍有 ${result.currentSalesRuleGate.missingCount} 项未解决事件` : `当前销售规则仍缺 ${result.currentSalesRuleGate.missingCount} 项`}
                          {result.currentSalesRuleGate.blockedFunds ? `，涉及 ${result.currentSalesRuleGate.blockedFunds} 只基金` : ''}
                        </div>
                        <div className="mt-1 text-xs leading-5 text-amber-800">
                          {result.currentSalesRuleGate.missingItems.slice(0, 5).join('、') || (reviewQueueGate ? '复查队列待处理' : '销售规则待补')}；{reviewQueueGate ? '处理前' : '补齐前'}不保存或沿用正式研究结论。
                        </div>
                      </div>
                    ) : null}
                    {result.riskLevelGatePolicy?.requiresRegeneration ? (
                      <div className="mb-3 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="report-search-risk-level-policy-card">
                        <div className="font-semibold">
                          R1-R5 旧门禁/未标记：搜索命中的报告不能证明已采用 30 天来源背书
                        </div>
                        <div className="mt-1 text-xs leading-5 text-amber-800">
                          {result.riskLevelGatePolicy.detail}
                        </div>
                        <Link
                          href={riskLevelSourceQueueHref(result)}
                          className="mt-2 inline-flex text-xs font-semibold text-amber-800 underline underline-offset-2"
                        >
                          进入 R1-R5 来源补证队列
                        </Link>
                      </div>
                    ) : null}
                    {result.decisionSummary?.replayEvidenceGateStatus ? (
                      <div className={`mb-3 rounded-xl border px-4 py-3 text-sm ${replayEvidenceGateCardClass(result.decisionSummary.replayEvidenceGateStatus)}`} data-testid="report-search-replay-evidence-gate">
                        <div className="font-semibold">
                          测算证据门禁：{result.decisionSummary.replayEvidenceGateLabel || result.decisionSummary.replayEvidenceGateStatus}
                        </div>
                        <div className="mt-1 text-xs leading-5 opacity-80">
                          通过 {result.decisionSummary.replayEvidenceGatePassCount ?? 0} 只；待补/只观察 {result.decisionSummary.replayEvidenceGateVerifyCount ?? 0} 只。
                          {result.decisionSummary.replayEvidenceGateStatus === 'missing'
                            ? ' 搜索命中的旧横评未记录测算证据门禁；重跑前只能回看，不能作为正式研究结论。'
                            : result.decisionSummary.replayEvidenceGateStatus === 'pass'
                            ? ' 历史回放仍只作为压力测试证据，不能替代正式研究复核。'
                            : ' 门禁未过的历史回放不能作为正式研究结论。'}
                        </div>
                        {result.decisionSummary.replayEvidenceGateMissingEvidence?.length ? (
                          <div className="mt-1 text-xs leading-5 opacity-80">
                            待补证据：{result.decisionSummary.replayEvidenceGateMissingEvidence.slice(0, 4).join('、')}
                          </div>
                        ) : null}
                        {result.reportType?.includes('comparison') && (result.relatedCodes || []).length >= 2 ? (
                          <Link
                            href={appendPurchaseContext(`/analysis/comparison?codes=${encodeURIComponent((result.relatedCodes || []).join(','))}&autoReplay=1`, result)}
                            className="mt-2 inline-flex text-xs font-semibold underline underline-offset-2"
                          >
                            重跑真实回放横评
                          </Link>
                        ) : null}
                      </div>
                    ) : null}
                    {result.decisionSummary?.decisionFundName || result.decisionSummary?.topPurchaseDecisionLabel ? (
                      <div className="mb-3 rounded-xl border border-cyan-100 bg-cyan-50 px-4 py-3 text-sm text-cyan-950" data-testid="report-search-purchase-decision">
                        <div className="font-semibold">
                          {result.decisionSummary?.decisionFundName
                            ? `研究选择：${result.decisionSummary.decisionFundName}${result.decisionSummary.decisionFundCode ? `（${result.decisionSummary.decisionFundCode}）` : ''}`
                            : `短名单决策卡：${result.decisionSummary?.topPurchaseDecisionLabel}`}
                        </div>
                        <div className="mt-1 text-xs leading-5 text-cyan-800">
                          {result.decisionSummary?.decisionBasis || result.decisionSummary?.topPurchaseDecisionAction || result.decisionSummary?.topPurchaseDecisionReason || '回到报告详情复核结构化证据'}
                        </div>
                      </div>
                    ) : null}
                    {result.decisionSummary?.sourceDecisionCards?.[0]?.reviewFreshnessLabel ? (
                      <div className="mb-3 rounded-xl border border-fuchsia-100 bg-fuchsia-50 px-4 py-3 text-sm text-fuchsia-950" data-testid="report-search-review-freshness">
                        <div className="font-semibold">
                          短名单复查时效：{result.decisionSummary.sourceDecisionCards[0].reviewFreshnessLabel}
                        </div>
                        <div className="mt-1 text-xs leading-5 text-fuchsia-800">
                          {result.decisionSummary.sourceDecisionCards[0].fundName || result.decisionSummary.sourceDecisionCards[0].windCode || '候选基金'}：
                          {result.decisionSummary.sourceDecisionCards[0].reviewFreshnessDetail || '回到研究清单更新复查日、净值、销售规则和研究结论后再使用。'}
                        </div>
                        <Link
                          href={poolReviewHref(result)}
                          className="mt-2 inline-flex text-xs font-semibold text-fuchsia-800 underline underline-offset-2"
                        >
                          回研究清单更新复查
                        </Link>
                      </div>
                    ) : null}
                    <div className={`mb-3 rounded-xl border px-4 py-3 text-sm ${followUpClass(followUp.tone)}`} data-testid="report-search-next-action">
                      <div className="flex items-center font-semibold">
                        <ShieldCheck className="mr-2 h-4 w-4" />
                        下一步：{followUp.label}
                      </div>
                      <div className="mt-1 text-xs leading-5 opacity-80">{followUp.detail}</div>
                      <Link
                        href={followUp.href}
                        className="mt-2 inline-flex text-xs font-semibold underline underline-offset-2"
                      >
                        执行下一步
                      </Link>
                    </div>
                    <div className="flex items-center gap-4 text-sm text-gray-500">
                      <div className="flex items-center">
                        <Calendar className="w-4 h-4 mr-1" />
                        {new Date(result.reportDate).toLocaleDateString('zh-CN')}
                      </div>
                      <div className="flex items-center">
                        <FileText className="w-4 h-4 mr-1" />
                        {result.source}
                      </div>
                      {result.tags.length > 0 && (
                        <div className="flex items-center gap-1">
                          <Tag className="w-4 h-4" />
                          {result.tags.slice(0, 2).join(', ')}
                          {result.tags.length > 2 && ` +${result.tags.length - 2}`}
                        </div>
                      )}
                    </div>
                  </div>
                  )
                })}
              </div>
            </>
          )}
        </div>
      )}

      {/* 使用提示 */}
      {!searched && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <h3 className="text-sm font-medium text-blue-900 mb-2">使用提示</h3>
          <ul className="text-sm text-blue-800 space-y-1">
            <li>• 使用自然语言描述您想了解的内容</li>
            <li>• 系统会优先搜索报告标题、摘要、正文、标签和核心要点</li>
            <li>• 匹配度越高，内容越相关</li>
            <li>• 不依赖外部向量服务，上传后的调研报告也会进入检索</li>
          </ul>
        </div>
      )}
    </div>
  )
}
