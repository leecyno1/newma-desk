'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  BarChart3,
  BookOpenText,
  Building2,
  Check,
  CircleAlert,
  Database,
  Search,
  ShieldCheck,
  Sparkles,
  UserRoundPlus,
  X,
} from 'lucide-react'

type ManagerSummary = {
  id: string
  name: string
  company?: string | null
  management_years?: number | null
  current_fund_count?: number
  memo_count?: number
  category_labels?: string[]
}

type Product = {
  fund_code: string
  fund_name?: string | null
  type?: string | null
  category?: string | null
  start_date?: string | null
  end_date?: string | null
  is_current?: boolean
  tenure_return?: number | null
  annualized_return?: number | null
  annualized_volatility?: number | null
  downside_risk?: number | null
  max_drawdown?: number | null
  sharpe_ratio?: number | null
  sortino_ratio?: number | null
  record_breaking_days_ratio?: number | null
  total_asset?: number | null
  share_codes?: string[]
  share_count?: number
  metric_status?: string | null
  comparison_nav_observations?: number | null
  peer_ranking?: PeerRanking
}

type PeerMetric = {
  rank?: number | null
  peer_count?: number | null
  percentile?: number | null
  sample_status?: string | null
}

type PeerRanking = {
  status?: string | null
  peer_group_name?: string | null
  period_start?: string | null
  period_end?: string | null
  valid_peer_count?: number | null
  minimum_peer_count?: number | null
  metrics?: Record<string, PeerMetric>
}

type AssessmentEvidence = {
  direction?: string | null
  label?: string | null
  statement?: string | null
  fund_code?: string | null
  metric_name?: string | null
  rank?: number | null
  peer_count?: number | null
}

type ManagerAssessment = {
  status?: string | null
  summary?: string | null
  current_product_count?: number
  tenure_evaluated_product_count?: number
  peer_ranked_product_count?: number
  memo_count?: number
  representative_product?: Product | null
  strengths?: AssessmentEvidence[]
  risks?: AssessmentEvidence[]
  scope_note?: string | null
}

type HistoryItem = {
  id?: string | null
  date?: string | null
  title?: string | null
  summary?: string | null
  source?: string | null
  tags?: string[]
}

type ComparedManager = {
  id: string
  name: string
  company?: string | null
  education?: string | null
  work_years?: number | null
  management_years?: number | null
  management_start_date?: string | null
  current_fund_count: number
  current_share_count: number
  managed_asset?: number | null
  managed_asset_product_count?: number
  managed_asset_scope?: string | null
  memo_count: number
  latest_memo_date?: string | null
  manager_assessment?: ManagerAssessment
  representative_product?: Product | null
  evidence?: {
    fund_metric_latest_date?: string | null
    research_latest_date?: string | null
    missing_items?: string[]
    profile_evidence_field_count?: number
    profile_evidence_item_count?: number
    profile_evidence_report_count?: number
  }
  profile?: {
    status?: string | null
    product_positioning?: string | null
    investment_objective?: string | null
    investment_method?: string | null
    holding_style?: string | null
    excess_return_source?: string | null
    core_philosophy?: string | null
    risk_philosophy?: string | null
    focus_industries?: string[]
    style_label?: string | null
    memo_style_labels?: string[]
    memo_classifications?: string[]
  }
  current_products: Product[]
  selected_category_products: Product[]
  selected_product?: Product | null
  product_tenures: Product[]
  history: HistoryItem[]
}

type MetricMeta = Record<string, { label: string; direction: 'higher' | 'lower' }>
type MetricValues = Record<string, number | string | null | undefined>

type ComparisonPayload = {
  status: string
  reason?: string
  selected_category?: string | null
  categories: Array<{ key: string; label: string; manager_count: number; product_count: number }>
  managers: ComparedManager[]
  common_period?: {
    status: string
    period_start?: string | null
    period_end?: string | null
    observation_count: number
    expected_observations?: number
    observation_coverage?: number
    minimum_observation_coverage?: number
    sample_status?: string
    metrics: Record<string, MetricValues>
    leaders: Record<string, string[]>
    metric_meta?: MetricMeta
    highlight_eligible?: boolean
    highlight_reason?: string
  }
  comparison_gate?: {
    category_status?: string
    selected_category?: string | null
    selected_manager_count?: number
    selected_product_count?: number
    common_period_status?: string
    highlight_eligible?: boolean
  }
  comparison_summary?: {
    status: string
    headline?: string
    points?: Array<{
      dimension: string
      leader_manager_ids?: string[]
      statement: string
    }>
    scope_note?: string
  }
  simulation_used?: boolean
}

const metricOrder = [
  'total_return',
  'record_breaking_days_ratio',
  'annualized_return',
  'max_drawdown',
  'annualized_volatility',
  'downside_risk',
  'sharpe_ratio',
  'sortino_ratio',
]

const defaultMetricMeta: MetricMeta = {
  total_return: { label: '共同区间收益', direction: 'higher' },
  record_breaking_days_ratio: { label: '创新高天数占比', direction: 'higher' },
  annualized_return: { label: '年化收益', direction: 'higher' },
  max_drawdown: { label: '最大回撤', direction: 'higher' },
  annualized_volatility: { label: '年化波动', direction: 'lower' },
  downside_risk: { label: '下行风险', direction: 'lower' },
  sharpe_ratio: { label: 'Sharpe', direction: 'higher' },
  sortino_ratio: { label: 'Sortino', direction: 'higher' },
}

function percent(value: unknown, digits = 1) {
  if (value == null || value === '') return '—'
  const parsed = Number(value)
  return Number.isFinite(parsed) ? `${(parsed * 100).toFixed(digits)}%` : '—'
}

function number(value: unknown, digits = 2) {
  if (value == null || value === '') return '—'
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed.toFixed(digits) : '—'
}

function asset(value: unknown) {
  if (value == null || value === '') return '待补'
  const parsed = Number(value)
  return Number.isFinite(parsed) ? `${parsed.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 亿` : '待补'
}

function years(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? `${parsed.toFixed(1)} 年` : '待补'
}

function dateText(value: unknown) {
  return typeof value === 'string' && value ? value.slice(0, 10) : '—'
}

function metricText(name: string, value: unknown) {
  return name === 'sharpe_ratio' || name === 'sortino_ratio' ? number(value) : percent(value)
}

function peerMetricText(product: Product, metricName: string) {
  const metric = product.peer_ranking?.metrics?.[metricName]
  if (metric?.sample_status === 'sufficient' && metric.rank && metric.peer_count) {
    return `${metric.rank} / ${metric.peer_count}`
  }
  return '—'
}

function peerRankingText(product: Product) {
  const ranking = product.peer_ranking
  if (ranking?.status === 'sufficient') {
    return `收益 ${peerMetricText(product, 'total_return')} · 年化 ${peerMetricText(product, 'annualized_return')} · 回撤 ${peerMetricText(product, 'max_drawdown')} · 夏普 ${peerMetricText(product, 'sharpe_ratio')}`
  }
  if (ranking?.status === 'insufficient_peer_sample') {
    return `样本不足（可比 ${ranking.valid_peer_count || 0}，门槛 ${ranking.minimum_peer_count || '—'}）`
  }
  return '同类排名待补'
}

function commonPeriodMessage(status: string | undefined) {
  if (status === 'insufficient_local_nav') return '至少一只所选产品缺少足够的本地真实净值，暂不比较。'
  if (status === 'insufficient_common_period') return '产品各自有净值，但共同交易日期不足，暂不比较。'
  if (status === 'insufficient_common_coverage') return '共同日期分布过于稀疏，样本覆盖不足，暂不比较。'
  if (status === 'insufficient_managers_in_category') return '并非每位经理都选中了该类别的产品，暂不比较。'
  if (status === 'no_common_category') return '这些经理没有共同的精确专业分类，不做跨类别比较。'
  return '当前证据不足，不生成模拟对比。'
}

function comparisonHref(managerIds: string[], category: string, productCodes: Record<string, string>) {
  const params = new URLSearchParams()
  managerIds.forEach((managerId) => params.append('manager_id', managerId))
  if (category) params.set('category', category)
  managerIds.forEach((managerId) => params.append('product_code', productCodes[managerId] || ''))
  const suffix = params.toString()
  return suffix ? `/managers/compare?${suffix}` : '/managers/compare'
}

export default function ManagerComparisonClient({
  initialManagerIds,
  initialProductCodes,
  initialCategory,
}: {
  initialManagerIds: string[]
  initialProductCodes: string[]
  initialCategory: string
}) {
  const router = useRouter()
  const [managerIds, setManagerIds] = useState(() => Array.from(new Set(initialManagerIds)).slice(0, 4))
  const [selectedSummaries, setSelectedSummaries] = useState<Record<string, ManagerSummary>>({})
  const [category, setCategory] = useState(initialCategory)
  const [productCodes, setProductCodes] = useState<Record<string, string>>(() => Object.fromEntries(
    initialManagerIds.map((managerId, index) => [managerId, initialProductCodes[index] || '']),
  ))
  const [payload, setPayload] = useState<ComparisonPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState<ManagerSummary[]>([])
  const [searching, setSearching] = useState(false)
  const [highlight, setHighlight] = useState(true)
  const [historyManagerId, setHistoryManagerId] = useState(initialManagerIds[0] || '')
  const [historyKeyword, setHistoryKeyword] = useState('')
  const productCodeKey = useMemo(
    () => managerIds.map((managerId) => `${managerId}:${productCodes[managerId] || ''}`).join('|'),
    [managerIds, productCodes],
  )

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setSearching(true)
      try {
        const params = new URLSearchParams({ page: '1', page_size: '8' })
        if (query.trim()) params.set('keyword', query.trim())
        const response = await fetch(`/api/managers/browser?${params.toString()}`, { signal: controller.signal })
        const data = await response.json()
        if (!response.ok) throw new Error(data.error || '搜索暂时不可用')
        setSearchResults(Array.isArray(data.managers) ? data.managers : [])
      } catch (caught) {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '搜索暂时不可用')
      } finally {
        if (!controller.signal.aborted) setSearching(false)
      }
    }, 220)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [query])

  useEffect(() => {
    if (managerIds.length < 2) {
      setPayload(null)
      setLoading(false)
      return
    }
    const controller = new AbortController()
    const load = async () => {
      setLoading(true)
      setError('')
      const params = new URLSearchParams()
      managerIds.forEach((managerId) => params.append('manager_id', managerId))
      if (category) params.set('category', category)
      managerIds.forEach((managerId) => params.append('product_code', productCodes[managerId] || ''))
      try {
        const response = await fetch(`/api/managers/compare?${params.toString()}`, { signal: controller.signal })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || data.error || '基金经理对比暂时不可用')
        const comparison = data as ComparisonPayload
        setPayload(comparison)
        setSelectedSummaries((current) => ({
          ...current,
          ...Object.fromEntries((comparison.managers || []).map((manager) => [manager.id, manager])),
        }))
        if (!category && comparison.selected_category) {
          setCategory(comparison.selected_category)
          router.replace(comparisonHref(managerIds, comparison.selected_category, productCodes), { scroll: false })
        }
        if (!historyManagerId || !managerIds.includes(historyManagerId)) setHistoryManagerId(managerIds[0])
      } catch (caught) {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '基金经理对比暂时不可用')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [category, managerIds, productCodeKey, router])

  const comparedManagers = payload?.managers || []
  const commonCategories = (payload?.categories || []).filter((item) => item.manager_count === managerIds.length)
  const commonPeriod = payload?.common_period
  const comparisonSummary = payload?.comparison_summary
  const metricMeta = commonPeriod?.metric_meta || defaultMetricMeta
  const highlightEligible = Boolean(commonPeriod?.status === 'available' && commonPeriod.highlight_eligible)
  const activeHistoryManager = comparedManagers.find((manager) => manager.id === historyManagerId) || comparedManagers[0]
  const filteredHistory = (activeHistoryManager?.history || []).filter((item) => {
    const needle = historyKeyword.trim().toLowerCase()
    return !needle || `${item.title || ''} ${item.summary || ''} ${(item.tags || []).join(' ')}`.toLowerCase().includes(needle)
  })

  const selectedRows = useMemo(() => managerIds.map((managerId) => (
    comparedManagers.find((manager) => manager.id === managerId)
    || selectedSummaries[managerId]
    || { id: managerId, name: managerId.split('|')[0] } as ManagerSummary
  )), [comparedManagers, managerIds, selectedSummaries])

  function navigate(nextIds: string[], nextCategory = category, nextProducts = productCodes) {
    router.replace(comparisonHref(nextIds, nextCategory, nextProducts), { scroll: false })
  }

  function addManager(manager: ManagerSummary) {
    if (managerIds.includes(manager.id) || managerIds.length >= 4) return
    const nextIds = [...managerIds, manager.id]
    const nextProducts = { ...productCodes, [manager.id]: '' }
    setSelectedSummaries((current) => ({ ...current, [manager.id]: manager }))
    setManagerIds(nextIds)
    setCategory('')
    setProductCodes(nextProducts)
    setHistoryManagerId((current) => current || manager.id)
    navigate(nextIds, '', nextProducts)
  }

  function removeManager(managerId: string) {
    const nextIds = managerIds.filter((item) => item !== managerId)
    const nextProducts = { ...productCodes }
    delete nextProducts[managerId]
    setManagerIds(nextIds)
    setCategory('')
    setProductCodes(nextProducts)
    if (historyManagerId === managerId) setHistoryManagerId(nextIds[0] || '')
    navigate(nextIds, '', nextProducts)
  }

  function changeCategory(nextCategory: string) {
    const nextProducts = Object.fromEntries(managerIds.map((managerId) => [managerId, '']))
    setCategory(nextCategory)
    setProductCodes(nextProducts)
    navigate(managerIds, nextCategory, nextProducts)
  }

  function changeProduct(managerId: string, productCode: string) {
    const nextProducts = { ...productCodes, [managerId]: productCode }
    setProductCodes(nextProducts)
    navigate(managerIds, category, nextProducts)
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/managers" className="inline-flex items-center gap-2 text-sm font-bold text-[#28745c]">
          <ArrowLeft className="h-4 w-4" />返回基金经理库
        </Link>
        <span className="text-xs text-[#718078]">只比较同一专业分类的真实基金产品</span>
      </div>

      <section className="relative overflow-hidden border border-[#cfd8d1] bg-[#173f35] px-6 py-8 text-white sm:px-8 sm:py-10">
        <div className="absolute -right-24 -top-28 h-80 w-80 rounded-full border border-white/10" />
        <div className="absolute -right-4 top-16 h-48 w-48 rounded-full border border-white/10" />
        <div className="relative flex justify-end">
          <div className="grid grid-cols-2 gap-px overflow-hidden border border-white/20 bg-white/20 text-[#18231e] sm:grid-cols-4">
            <div className="bg-[#f7f5ed] px-5 py-4"><strong className="block text-2xl">{managerIds.length} / 4</strong><span className="text-[11px] text-[#68756e]">已选经理</span></div>
            <div className="bg-[#f7f5ed] px-5 py-4"><strong className="block text-2xl">{commonCategories.length}</strong><span className="text-[11px] text-[#68756e]">共同分类</span></div>
            <div className="bg-[#f7f5ed] px-5 py-4"><strong className="block text-2xl">{commonPeriod?.observation_count || 0}</strong><span className="text-[11px] text-[#68756e]">共同交易日</span></div>
          </div>
        </div>
      </section>

      <section className="grid gap-5 border border-[#d9e0db] bg-white p-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] sm:p-6">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.12em] text-[#28745c]"><UserRoundPlus className="h-4 w-4" />添加经理</div>
          <label className="relative mt-3 block">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#7c8982]" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索经理或基金公司" className="h-11 w-full border border-[#ccd6cf] bg-[#fbfcfa] pl-11 pr-4 text-sm outline-none focus:border-[#28745c]" />
          </label>
          <div className="mt-3 max-h-64 divide-y divide-[#e6eae7] overflow-y-auto border border-[#e0e5e1]">
            {searching ? <p className="px-4 py-5 text-sm text-[#718078]">正在搜索…</p> : searchResults.map((manager) => {
              const selected = managerIds.includes(manager.id)
              return (
                <button key={manager.id} type="button" onClick={() => addManager(manager)} disabled={selected || managerIds.length >= 4} className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left transition hover:bg-[#f4f7f4] disabled:cursor-not-allowed disabled:opacity-50">
                  <span className="min-w-0"><strong className="block truncate text-sm text-[#233129]">{manager.name}</strong><small className="mt-1 block truncate text-[#78847e]">{manager.company || '基金公司待补'} · 纪要 {manager.memo_count || 0} 份</small></span>
                  <span className="shrink-0 text-xs font-bold text-[#28745c]">{selected ? '已选' : '加入'}</span>
                </button>
              )
            })}
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs font-bold uppercase tracking-[0.12em] text-[#28745c]">当前对比</div>
            {managerIds.length ? <button type="button" onClick={() => { setManagerIds([]); setCategory(''); setProductCodes({}); setPayload(null); navigate([], '', {}) }} className="text-xs font-bold text-[#8b5e54]">清空</button> : null}
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {selectedRows.map((manager) => (
              <article key={manager.id} className="relative border border-[#d9e0db] bg-[#f8faf8] p-4">
                <button type="button" onClick={() => removeManager(manager.id)} aria-label={`移除${manager.name}`} className="absolute right-3 top-3 text-[#7e8983] hover:text-[#8b4f48]"><X className="h-4 w-4" /></button>
                <strong className="block pr-8 text-lg text-[#233129]">{manager.name}</strong>
                <p className="mt-1 truncate text-xs text-[#748079]">{manager.company || '基金公司待补'}</p>
                <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-bold">
                  <span className="bg-[#e7f0eb] px-2 py-1 text-[#28624e]">在管 {manager.current_fund_count || 0}</span>
                  <span className="bg-[#fff3dc] px-2 py-1 text-[#8a682f]">纪要 {manager.memo_count || 0}</span>
                </div>
              </article>
            ))}
            {managerIds.length < 2 ? <div className="grid min-h-28 place-items-center border border-dashed border-[#cbd3cd] px-4 text-center text-sm text-[#748079]">再选 {2 - managerIds.length} 位经理即可开始对比</div> : null}
          </div>
        </div>
      </section>

      {error ? <section className="border-l-4 border-[#b77964] bg-[#fff6f1] px-5 py-4 text-sm text-[#855746]"><div className="flex items-start gap-2"><CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />{error}</div></section> : null}

      {managerIds.length >= 2 ? (
        <section className="border border-[#d9e0db] bg-white p-5 sm:p-6">
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
            <div>
              <label className="text-xs font-bold text-[#5f6d65]" htmlFor="manager-category">精确专业分类</label>
              <select id="manager-category" value={category} onChange={(event) => changeCategory(event.target.value)} disabled={!commonCategories.length} className="mt-2 h-11 w-full border border-[#ccd6cf] bg-[#fbfcfa] px-3 text-sm font-bold text-[#2b3931] outline-none focus:border-[#28745c]">
                {!category ? <option value="">自动选择共同分类</option> : null}
                {commonCategories.map((item) => <option key={item.key} value={item.key}>{item.label} · {item.product_count} 个产品</option>)}
              </select>
            </div>
            <label className={`flex h-11 items-center gap-3 border px-4 text-sm font-bold ${highlightEligible ? 'cursor-pointer border-[#ccd6cf] bg-[#fbfcfa] text-[#34443b]' : 'cursor-not-allowed border-[#e0e3e1] bg-[#f4f5f3] text-[#929a95]'}`}>
              <input type="checkbox" checked={highlight && highlightEligible} disabled={!highlightEligible} onChange={(event) => setHighlight(event.target.checked)} className="accent-[#28745c]" />高亮优势项
            </label>
          </div>
          {commonCategories.length ? (
            <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {comparedManagers.map((manager) => (
                <label key={manager.id} className="block border border-[#e0e5e1] bg-[#f8faf8] p-4 text-xs font-bold text-[#5f6d65]">
                  {manager.name}的代表产品
                  <select value={productCodes[manager.id] || manager.selected_product?.fund_code || ''} onChange={(event) => changeProduct(manager.id, event.target.value)} className="mt-2 h-10 w-full border border-[#ccd6cf] bg-white px-2 text-xs font-normal text-[#27352d] outline-none focus:border-[#28745c]">
                    {(manager.selected_category_products || []).map((product) => <option key={product.fund_code} value={product.fund_code}>{product.fund_name || product.fund_code} / {product.fund_code}</option>)}
                  </select>
                </label>
              ))}
            </div>
          ) : <p className="mt-4 bg-[#fff7e8] px-4 py-3 text-sm text-[#795f2d]">这些经理目前没有共同的精确专业分类，不强行比较收益。</p>}
        </section>
      ) : null}

      {loading ? <section className="border border-[#d9e0db] bg-white px-6 py-16 text-center text-sm text-[#718078]">正在对齐同类产品与共同交易日…</section> : null}

      {!loading && comparedManagers.length ? (
        <>
          {comparisonSummary?.status === 'available' ? (
            <section className="border border-[#c7d7ce] bg-[#edf4f0] p-5 sm:p-6" data-testid="manager-comparison-summary">
              <div className="flex items-start gap-3">
                <Sparkles className="mt-1 h-5 w-5 shrink-0 text-[#28745c]" />
                <div>
                  <div className="text-xs font-bold tracking-[0.12em] text-[#28745c]">先看结论</div>
                  <h2 className="mt-2 text-xl font-bold text-[#213129]">{comparisonSummary.headline}</h2>
                </div>
              </div>
              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {(comparisonSummary.points || []).map((item) => (
                  <article key={item.dimension} className="border border-[#d6e1da] bg-white p-4">
                    <strong className="text-sm text-[#28745c]">{item.dimension}</strong>
                    <p className="mt-2 text-xs leading-6 text-[#59675f]">{item.statement}</p>
                  </article>
                ))}
              </div>
              <p className="mt-4 text-[11px] leading-5 text-[#6e7b74]">{comparisonSummary.scope_note}</p>
            </section>
          ) : null}

          <section>
            <div className="mb-4 flex items-end justify-between gap-4">
              <div><div className="flex items-center gap-2 text-[#28745c]"><Building2 className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.12em]">Basic facts</span></div><h2 className="mt-2 text-2xl font-bold">基本资料对照</h2></div>
              <span className="text-xs text-[#718078]">不生成经理综合分</span>
            </div>
            <div className="overflow-x-auto border border-[#d7ded8] bg-white">
              <table className="min-w-[760px] w-full text-left text-sm">
                <thead className="bg-[#f3f5f2]"><tr><th className="w-40 px-4 py-3 text-xs text-[#66736c]">项目</th>{comparedManagers.map((manager) => <th key={manager.id} className="px-4 py-3"><Link href={`/managers/${encodeURIComponent(manager.id)}`} className="text-base font-bold text-[#244f40] hover:underline">{manager.name}</Link></th>)}</tr></thead>
                <tbody className="divide-y divide-[#e5e9e6]">
                  {[
                    ['基金公司', (manager: ComparedManager) => manager.company || '待补'],
                    ['学历', (manager: ComparedManager) => manager.education || '待补'],
                    ['从业年限', (manager: ComparedManager) => years(manager.work_years)],
                    ['管理年限', (manager: ComparedManager) => years(manager.management_years)],
                    ['管理起始日', (manager: ComparedManager) => dateText(manager.management_start_date)],
                    ['在管规模', (manager: ComparedManager) => `${asset(manager.managed_asset)} · ${manager.managed_asset_product_count || 0} 个已同步样本`],
                    ['在管产品', (manager: ComparedManager) => `${manager.current_fund_count} 个 / ${manager.current_share_count} 份额`],
                    ['代表产品', (manager: ComparedManager) => manager.representative_product?.fund_name || manager.representative_product?.fund_code || '证据不足'],
                    ['关联纪要', (manager: ComparedManager) => `${manager.memo_count} 份 · 最新 ${dateText(manager.latest_memo_date)}`],
                  ].map(([label, render]) => <tr key={String(label)}><th className="bg-[#fafbf9] px-4 py-3 text-xs font-bold text-[#66736c]">{String(label)}</th>{comparedManagers.map((manager) => <td key={manager.id} className="px-4 py-3 text-[#2f3d35]">{(render as (manager: ComparedManager) => string)(manager)}</td>)}</tr>)}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-[11px] leading-5 text-[#7a8580]">在管规模仅汇总本地已同步规模的基金实体，不代表基金公司或经理官方披露总规模。</p>
          </section>

          <section>
            <div className="mb-4"><div className="flex items-center gap-2 text-[#28745c]"><ShieldCheck className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.12em]">Manager assessment</span></div><h2 className="mt-2 text-2xl font-bold">经理评价摘要</h2><p className="mt-1 text-sm text-[#6d7872]">评价只落到具体基金、经理任期和同区间同类排名，不生成经理综合分。</p></div>
            <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
              {comparedManagers.map((manager) => {
                const assessment = manager.manager_assessment || {}
                const representative = assessment.representative_product || manager.representative_product
                const strengths = assessment.strengths || []
                const risks = assessment.risks || []
                return (
                  <article key={manager.id} className="border border-[#d7ded8] bg-white p-5">
                    <div className="flex items-start justify-between gap-3"><div><strong className="text-xl text-[#233129]">{manager.name}</strong><p className="mt-1 text-[11px] text-[#748079]">{manager.company || '基金公司待补'}</p></div><span className={`px-2 py-1 text-[10px] font-bold ${assessment.status === 'available' ? 'bg-[#e3f0e8] text-[#226047]' : assessment.status === 'partial' ? 'bg-[#fff2d8] text-[#80602b]' : 'bg-[#f0f1ef] text-[#6e7973]'}`}>{assessment.status === 'available' ? '证据完整' : assessment.status === 'partial' ? '部分可评' : '证据不足'}</span></div>
                    <p className="mt-4 min-h-12 text-xs leading-6 text-[#59675f]">{assessment.summary || '暂无可核验的单产品经理任期评价。'}</p>
                    <div className="mt-4 grid grid-cols-3 gap-px overflow-hidden border border-[#e1e6e2] bg-[#e1e6e2] text-center"><div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-base">{assessment.current_product_count || manager.current_fund_count}</strong><span className="text-[10px] text-[#78837d]">在管</span></div><div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-base text-[#28745c]">{assessment.tenure_evaluated_product_count || 0}</strong><span className="text-[10px] text-[#78837d]">任期可评</span></div><div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-base text-[#28745c]">{assessment.peer_ranked_product_count || 0}</strong><span className="text-[10px] text-[#78837d]">同类可比</span></div></div>
                    <div className="mt-4 bg-[#f6f8f5] p-3 text-xs"><span className="font-bold text-[#28745c]">代表观察：</span><span className="text-[#56645c]">{representative?.fund_name || representative?.fund_code || '待补'}</span>{representative?.fund_code ? <span className="mt-1 block text-[10px] text-[#7b8680]">{representative.fund_code} · {representative.category || '分类待补'}</span> : null}</div>
                    {strengths.length ? <div className="mt-4"><div className="text-[11px] font-bold text-[#28745c]">同类前 20% 证据</div>{strengths.slice(0, 2).map((item) => <p key={`${item.fund_code}-${item.metric_name}`} className="mt-2 border-l-2 border-[#79a890] pl-3 text-[11px] leading-5 text-[#56645c]">{item.statement || item.label}</p>)}</div> : null}
                    {risks.length ? <div className="mt-4"><div className="text-[11px] font-bold text-[#9a624e]">同类后 20% 风险</div>{risks.slice(0, 2).map((item) => <p key={`${item.fund_code}-${item.metric_name}`} className="mt-2 border-l-2 border-[#c6927e] pl-3 text-[11px] leading-5 text-[#6d5b53]">{item.statement || item.label}</p>)}</div> : null}
                  </article>
                )
              })}
            </div>
          </section>

          <section>
            <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
              <div><div className="flex items-center gap-2 text-[#28745c]"><BarChart3 className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.12em]">Same period evidence</span></div><h2 className="mt-2 text-2xl font-bold">共同区间量化对比</h2></div>
              {commonPeriod?.status === 'available' ? <p className="text-xs text-[#718078]">{dateText(commonPeriod.period_start)} 至 {dateText(commonPeriod.period_end)} · {commonPeriod.observation_count} 个共同交易日 · 覆盖 {percent(commonPeriod.observation_coverage, 0)}</p> : null}
            </div>
            {commonPeriod?.status === 'available' ? (
              <div className="overflow-x-auto border border-[#d7ded8] bg-white">
                <table className="min-w-[760px] w-full text-left text-sm">
                  <thead className="bg-[#f3f5f2]"><tr><th className="w-40 px-4 py-3 text-xs text-[#66736c]">指标</th>{comparedManagers.map((manager) => <th key={manager.id} className="px-4 py-3"><span className="block font-bold">{manager.name}</span><small className="mt-1 block font-normal text-[#718078]">{manager.selected_product?.fund_name || '代表产品待选'}</small></th>)}</tr></thead>
                  <tbody className="divide-y divide-[#e5e9e6]">
                    {metricOrder.map((metricName) => {
                      const leaders = commonPeriod.leaders?.[metricName] || []
                      return <tr key={metricName}><th className="bg-[#fafbf9] px-4 py-3 text-xs font-bold text-[#66736c]">{metricMeta[metricName]?.label || metricName}</th>{comparedManagers.map((manager) => {
                        const isLeader = leaders.includes(manager.id)
                        return <td key={manager.id} className={`px-4 py-3 font-bold ${highlight && highlightEligible && isLeader ? 'bg-[#e3f0e8] text-[#205e49]' : 'text-[#2d3b33]'}`}><span>{metricText(metricName, commonPeriod.metrics?.[manager.id]?.[metricName])}</span>{highlight && highlightEligible && isLeader ? <span className="ml-2 inline-flex items-center gap-1 bg-[#28745c] px-2 py-0.5 text-[10px] text-white"><Check className="h-3 w-3" />优势</span> : null}</td>
                      })}</tr>
                    })}
                  </tbody>
                </table>
              </div>
            ) : <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-12 text-center text-sm text-[#748079]">{commonPeriodMessage(commonPeriod?.status)}</div>}
          </section>

          <section>
            <div className="mb-4"><div className="flex items-center gap-2 text-[#28745c]"><Database className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.12em]">Product tenure</span></div><h2 className="mt-2 text-2xl font-bold">各自产品任职全景</h2><p className="mt-1 text-sm text-[#6d7872]">保留每只产品的真实任职区间；A/C 份额合并但代码可追溯。</p></div>
            <div className="space-y-5">
              {comparedManagers.map((manager) => (
                <article key={manager.id} className="border border-[#d7ded8] bg-white">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e2e7e3] bg-[#f5f7f4] px-4 py-3"><strong className="text-lg">{manager.name}</strong><span className="text-xs text-[#718078]">{manager.product_tenures.length} 个产品</span></div>
                  <div className="overflow-x-auto">
                    <table className="min-w-[960px] w-full text-left text-xs">
                      <thead className="text-[#66736c]"><tr><th className="px-4 py-3">基金产品 / 代码</th><th className="px-4 py-3">专业分类</th><th className="px-4 py-3">任职区间</th><th className="px-4 py-3">任期回报</th><th className="px-4 py-3">年化波动</th><th className="px-4 py-3">下行风险</th><th className="px-4 py-3">同类任期排名</th><th className="px-4 py-3">状态</th></tr></thead>
                      <tbody className="divide-y divide-[#e7ebe8]">{manager.product_tenures.map((product) => <tr key={`${product.fund_code}-${product.start_date}`} className={product.is_current ? '' : 'bg-[#fbfbfa] text-[#68736d]'}><td className="px-4 py-3"><Link href={`/funds/${encodeURIComponent(product.fund_code)}`} className="font-bold text-[#244f40] hover:underline">{product.fund_name || product.fund_code}</Link><div className="mt-1 text-[10px] text-[#7b8680]">{product.fund_code}{(product.share_codes || []).length > 1 ? ` · ${(product.share_codes || []).join(' / ')}` : ''}</div></td><td className="px-4 py-3">{product.category || product.type || '待分类'}</td><td className="px-4 py-3">{dateText(product.start_date)} – {product.is_current ? '至今' : dateText(product.end_date)}</td><td className="px-4 py-3 font-bold text-[#267257]">{percent(product.tenure_return)}</td><td className="px-4 py-3">{percent(product.annualized_volatility)}</td><td className="px-4 py-3">{percent(product.downside_risk)}</td><td className="min-w-64 px-4 py-3"><span className="block font-bold text-[#34443b]">{peerRankingText(product)}</span><span className="mt-1 block text-[10px] text-[#7b8680]">{product.peer_ranking?.peer_group_name || product.category || '同类组待补'} · 同区间</span></td><td className="px-4 py-3"><span className="block">{product.is_current ? '现任' : '已卸任'}</span><span className="mt-1 block text-[10px] text-[#7b8680]">{product.metric_status === 'manager_product_tenure' ? '任期指标已核验' : '任期指标待补'}</span></td></tr>)}</tbody>
                    </table>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section>
            <div className="mb-4"><div className="flex items-center gap-2 text-[#28745c]"><ShieldCheck className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.12em]">Research framework</span></div><h2 className="mt-2 text-2xl font-bold">投资框架对照</h2><p className="mt-1 text-sm text-[#6d7872]">只展示已从本地调研纪要归纳并留存的内容。</p></div>
            <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
              {comparedManagers.map((manager) => {
                const profile = manager.profile || {}
                const evidence = manager.evidence || {}
                const evidenceFields = evidence.profile_evidence_field_count || 0
                const evidenceItems = evidence.profile_evidence_item_count || 0
                return <article key={manager.id} className="border border-[#d7ded8] bg-white p-5"><div className="flex items-center justify-between gap-3"><strong className="text-xl">{manager.name}</strong><span className={`px-2 py-1 text-[10px] font-bold ${profile.status === 'available' ? 'bg-[#e5f0ea] text-[#28624e]' : 'bg-[#f1f2f0] text-[#6e7973]'}`}>{profile.status === 'available' ? '纪要已归纳' : '待归纳'}</span></div><div className="mt-4 grid grid-cols-3 gap-px overflow-hidden border border-[#e1e6e2] bg-[#e1e6e2] text-center"><div className="bg-[#fafbf9] px-2 py-2"><strong className="block text-sm">{manager.memo_count}</strong><span className="text-[9px] text-[#7a8580]">关联纪要</span></div><div className="bg-[#fafbf9] px-2 py-2"><strong className="block text-sm">{evidenceFields}</strong><span className="text-[9px] text-[#7a8580]">有据字段</span></div><div className="bg-[#fafbf9] px-2 py-2"><strong className="block text-sm">{evidenceItems}</strong><span className="text-[9px] text-[#7a8580]">证据条目</span></div></div><dl className="mt-5 space-y-4 text-xs leading-6"><div><dt className="font-bold text-[#28745c]">产品定位</dt><dd className="mt-1 text-[#58665e]">{profile.product_positioning || '待从纪要确认'}</dd></div><div><dt className="font-bold text-[#28745c]">投资目标</dt><dd className="mt-1 text-[#58665e]">{profile.investment_objective || '待从纪要确认'}</dd></div><div><dt className="font-bold text-[#28745c]">投资方法</dt><dd className="mt-1 text-[#58665e]">{profile.investment_method || '待从纪要确认'}</dd></div><div><dt className="font-bold text-[#28745c]">核心理念</dt><dd className="mt-1 text-[#58665e]">{profile.core_philosophy || '待从纪要确认'}</dd></div><div><dt className="font-bold text-[#28745c]">持仓风格</dt><dd className="mt-1 text-[#58665e]">{profile.holding_style || '待从纪要确认'}</dd></div><div><dt className="font-bold text-[#28745c]">超额来源</dt><dd className="mt-1 text-[#58665e]">{profile.excess_return_source || '待从纪要确认'}</dd></div><div><dt className="font-bold text-[#28745c]">风险理念</dt><dd className="mt-1 text-[#58665e]">{profile.risk_philosophy || '待从纪要确认'}</dd></div></dl>{(profile.focus_industries || []).length ? <div className="mt-4 flex flex-wrap gap-2">{profile.focus_industries?.slice(0, 8).map((industry) => <span key={industry} className="bg-[#f0f3f0] px-2 py-1 text-[10px] text-[#59675f]">{industry}</span>)}</div> : null}{(profile.memo_classifications || profile.memo_style_labels || []).length ? <div className="mt-4 border-t border-[#e5e9e6] pt-3 text-[10px] leading-5 text-[#6f7b74]">纪要标签：{[...(profile.memo_classifications || []), ...(profile.memo_style_labels || [])].slice(0, 6).join(' · ')}</div> : null}{evidenceFields === 0 ? <p className="mt-3 bg-[#fff7e8] px-3 py-2 text-[10px] leading-5 text-[#7a602e]">画像字段尚未形成可追溯证据，当前内容仅作待核验展示。</p> : null}</article>
              })}
            </div>
          </section>

          <section>
            <div className="mb-4"><div className="flex items-center gap-2 text-[#28745c]"><BookOpenText className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.12em]">Research history</span></div><h2 className="mt-2 text-2xl font-bold">历史观点</h2></div>
            <div className="border border-[#d7ded8] bg-white p-5 sm:p-6">
              <div className="grid gap-3 md:grid-cols-[auto_minmax(0,1fr)]">
                <div className="flex flex-wrap gap-2">{comparedManagers.map((manager) => <button key={manager.id} type="button" onClick={() => setHistoryManagerId(manager.id)} className={activeHistoryManager?.id === manager.id ? 'bg-[#173f35] px-4 py-2 text-xs font-bold text-white' : 'border border-[#d7ded9] bg-[#f8faf8] px-4 py-2 text-xs font-bold text-[#526159]'}>{manager.name} · {manager.history.length}</button>)}</div>
                <label className="relative block"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#7c8982]" /><input value={historyKeyword} onChange={(event) => setHistoryKeyword(event.target.value)} placeholder="筛选标题、摘要或标签" className="h-10 w-full border border-[#ccd6cf] bg-[#fbfcfa] pl-10 pr-3 text-xs outline-none focus:border-[#28745c]" /></label>
              </div>
              <div className="mt-5 space-y-3">{filteredHistory.length ? filteredHistory.map((item) => <article key={item.id || item.title} className="border-l-2 border-[#88ae9d] bg-[#f8faf8] px-4 py-4"><div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-sm text-[#26342c]">{item.title || '纪要标题待补'}</strong><span className="text-[11px] text-[#75817a]">{dateText(item.date)}</span></div><p className="mt-2 text-xs leading-6 text-[#66736c]">{item.summary || '摘要待提取'}</p>{(item.tags || []).length ? <div className="mt-2 flex flex-wrap gap-2">{item.tags?.map((tag) => <span key={tag} className="bg-white px-2 py-1 text-[10px] text-[#59675f]">{tag}</span>)}</div> : null}</article>) : <p className="py-8 text-center text-sm text-[#748079]">当前没有匹配的真实调研纪要。</p>}</div>
            </div>
          </section>

          <section className="grid gap-4 border border-[#cad7d0] bg-[#edf3ef] p-5 text-xs leading-6 text-[#536159] md:grid-cols-3">
            <div><Sparkles className="h-4 w-4 text-[#28745c]" /><strong className="mt-2 block text-[#27352d]">优势高亮</strong><p>只在同一精确专业分类、同一交易日交集上计算。</p></div>
            <div><Database className="h-4 w-4 text-[#28745c]" /><strong className="mt-2 block text-[#27352d]">数据缺失</strong><p>净值、纪要或风格证据不足时留空，不用模拟替代。</p></div>
            <div><ShieldCheck className="h-4 w-4 text-[#28745c]" /><strong className="mt-2 block text-[#27352d]">功能边界</strong><p>用于基金评价、分类和经理研究，不输出投资处置建议。</p></div>
          </section>
        </>
      ) : null}
    </div>
  )
}
