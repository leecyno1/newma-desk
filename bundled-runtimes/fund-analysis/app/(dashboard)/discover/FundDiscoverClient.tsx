'use client'

import Link from 'next/link'
import { useCallback, useMemo, useState } from 'react'
import { ArrowLeft, ArrowRight, CircleAlert, GitCompareArrows, RotateCcw, Search, SlidersHorizontal, X } from 'lucide-react'
import type { CamelFund } from '@/lib/backend-api'
import { fundCategoryPresets } from '@/lib/fund-category-presets'
import FundBrowserViewControls, { type FundBrowserViewMode } from './FundBrowserViewControls'
import FundBrowserResultCard from './FundBrowserResultCard'
import FundBrowserDataTable from './FundBrowserDataTable'
import {
  normalizeSelectionRule,
  type SelectionRule,
} from './fund-browser-view-model'
import {
  asRecord,
  professionalPeerGroup,
  professionalPeerGroupId,
  textValue,
  type SimpleFund,
} from '@/lib/simple-fund-view'

type Props = {
  initialFunds: CamelFund[]
  initialCategories: FundCategoryCoverage[]
  initialTotal: number
  initialSource: string
  initialError: string
  initialPeerGroup?: string
  initialSearch?: string
  initialAvailability?: FundAvailability
  initialSelectionContext?: Record<string, unknown>
  initialStyleTagCatalog?: Record<string, unknown>
}

type FundAvailability = 'evaluated' | 'classified' | 'all'

type FundCategoryCoverage = {
  id: string
  key: string
  name: string
  count: number
  evaluatedCount: number
  pendingCount: number
  evaluationCoverage: number
  evaluationAsOfDate: string | null
  assetClass: string | null
  activePassive: string | null
  benchmarkCode: string | null
  benchmarkName: string | null
  strategyFamilyKey: string | null
  strategyFamilyName: string | null
  contractDimensions: BondContractDimensions | null
}

type BondContractDimensions = {
  baseIndex: string
  priceReturn: string
  tenor: string
}

type BondDimensionKey = keyof BondContractDimensions

type Watchlist = {
  id: string
  name: string
  is_default?: boolean
}

type BrowserFilters = {
  assetMin: string
  minAgeYears: string
  minManagerYears: string
  return6mMin: string
  return1yMin: string
  return3yMin: string
  maxDrawdown1yMax: string
  sharpe1yMin: string
  sortBy: string
}

type SelectionContext = {
  status: string
  summary: string
  sortLabel: string
  availabilityLabel: string
  rules: SelectionRule[]
  boundary: string
}

type StyleTagOption = {
  value: string
  fundCount: number
  evidenceLevel: 'strong' | 'context' | 'classification'
  sourceLabels: string[]
}

type StyleTagCatalog = {
  tags: StyleTagOption[]
  fundCount: number
  taggedFundCount: number
  coverageRate: number
  holdingFundCount: number
  memoFundCount: number
  positioningFundCount: number
  boundary: string
}

const emptyFilters: BrowserFilters = {
  assetMin: '',
  minAgeYears: '',
  minManagerYears: '',
  return6mMin: '',
  return1yMin: '',
  return3yMin: '',
  maxDrawdown1yMax: '',
  sharpe1yMin: '',
  sortBy: 'multi_period',
}

const sortLabels: Record<string, string> = {
  quality: '数据较完整优先',
  multi_period: '多周期同类领先',
  return_6m: '近 6 月收益较高',
  return_1y: '近 1 年收益较高',
  return_3y: '近 3 年收益较高',
  drawdown: '回撤较小优先',
  sharpe: 'Sharpe 较高优先',
  asset: '规模较大优先',
  history: '成立较早优先',
}

const filterLabels: Array<[keyof BrowserFilters, string, (value: string) => string]> = [
  ['assetMin', '规模', (value) => `不少于 ${value} 亿`],
  ['minAgeYears', '成立年限', (value) => `至少 ${value} 年`],
  ['minManagerYears', '经理年限', (value) => `至少 ${value} 年`],
  ['return6mMin', '近 6 月', (value) => `收益不低于 ${value}%`],
  ['return1yMin', '近 1 年', (value) => `收益不低于 ${value}%`],
  ['return3yMin', '近 3 年', (value) => `收益不低于 ${value}%`],
  ['maxDrawdown1yMax', '回撤', (value) => `不超过 ${value}%`],
  ['sharpe1yMin', 'Sharpe', (value) => `不低于 ${value}`],
]

const bondDimensionLabels: Record<BondDimensionKey, Record<string, string>> = {
  baseIndex: {
    composite: '中债综合指数',
    new_composite: '中债新综合指数',
    total: '中债总指数',
  },
  priceReturn: {
    full_price: '全价',
    wealth: '财富',
    total_wealth: '总财富合同写法',
    unspecified: '价格口径未注明',
  },
  tenor: {
    all: '全期限',
    under_1y: '1年以下',
    '1_3y': '1—3年',
    '0_3y': '0—3年',
    '0_5y': '0—5年',
    '1_5y': '1—5年',
    '3_5y': '3—5年',
    '3_7y': '3—7年',
    '5_10y': '5—10年',
    '7_10y': '7—10年',
    over_10y: '10年以上',
  },
}

function bondDimensionLabel(dimension: BondDimensionKey, value: string) {
  return bondDimensionLabels[dimension][value] || value
}

function categoryDisplayName(category: FundCategoryCoverage | undefined) {
  if (!category) return ''
  const dimensions = category.contractDimensions
  if (!dimensions) return category.name
  return [
    bondDimensionLabel('baseIndex', dimensions.baseIndex),
    bondDimensionLabel('priceReturn', dimensions.priceReturn),
    bondDimensionLabel('tenor', dimensions.tenor),
  ].join(' · ')
}

function peerGroupDisplayName(name: string, categories: FundCategoryCoverage[]) {
  const category = categories.find((item) => item.name === name || item.key === name || item.id === name)
  return categoryDisplayName(category) || name
}

function uniqueBondDimensionOptions(categories: FundCategoryCoverage[], dimension: BondDimensionKey) {
  return Array.from(new Set(categories.flatMap((item) => item.contractDimensions?.[dimension] || [])))
    .sort((left, right) => bondDimensionLabel(dimension, left).localeCompare(bondDimensionLabel(dimension, right), 'zh-CN'))
}

function normalizeSelectionContext(value: unknown): SelectionContext {
  const item = asRecord(value)
  return {
    status: textValue(item.status),
    summary: textValue(item.summary),
    sortLabel: textValue(item.sort_label, item.sortLabel),
    availabilityLabel: textValue(item.availability_label, item.availabilityLabel),
    rules: (Array.isArray(item.rules) ? item.rules : []).map(normalizeSelectionRule).filter((rule) => rule.key),
    boundary: textValue(item.boundary),
  }
}

function normalizeStyleTagCatalog(value: unknown): StyleTagCatalog {
  const item = asRecord(value)
  const coverage = asRecord(item.coverage)
  return {
    tags: (Array.isArray(item.tags) ? item.tags : []).flatMap((entry) => {
      const tag = asRecord(entry)
      const tagValue = textValue(tag.value)
      if (!tagValue) return []
      const sources = Array.isArray(tag.sources) ? tag.sources : []
      const evidenceLevel = textValue(tag.evidence_level, tag.evidenceLevel)
      return [{
        value: tagValue,
        fundCount: Number(tag.fund_count ?? tag.fundCount ?? 0),
        evidenceLevel: evidenceLevel === 'strong' || evidenceLevel === 'context' ? evidenceLevel : 'classification',
        sourceLabels: sources.map((source) => textValue(asRecord(source).label)).filter(Boolean),
      }]
    }),
    fundCount: Number(coverage.fund_count ?? coverage.fundCount ?? 0),
    taggedFundCount: Number(coverage.tagged_fund_count ?? coverage.taggedFundCount ?? 0),
    coverageRate: Number(coverage.coverage_rate ?? coverage.coverageRate ?? 0),
    holdingFundCount: Number(coverage.holding_quantitative_fund_count ?? coverage.holdingQuantitativeFundCount ?? 0),
    memoFundCount: Number(coverage.memo_confirmed_fund_count ?? coverage.memoConfirmedFundCount ?? 0),
    positioningFundCount: Number(coverage.product_positioning_fund_count ?? coverage.productPositioningFundCount ?? 0),
    boundary: textValue(item.boundary),
  }
}

export default function FundDiscoverClient({ initialFunds, initialCategories, initialTotal, initialSource, initialError, initialPeerGroup = '', initialSearch = '', initialAvailability = 'evaluated', initialSelectionContext = {}, initialStyleTagCatalog = {} }: Props) {
  const [funds, setFunds] = useState<SimpleFund[]>(initialFunds)
  const [searchText, setSearchText] = useState(initialSearch)
  const [appliedSearch, setAppliedSearch] = useState(initialSearch)
  const [peerGroupFilter, setPeerGroupFilter] = useState(initialPeerGroup)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(initialError)
  const [total, setTotal] = useState(initialTotal)
  const [compareFunds, setCompareFunds] = useState<SimpleFund[]>([])
  const [viewMode, setViewMode] = useState<FundBrowserViewMode>('cards')
  const [watchlistFund, setWatchlistFund] = useState<SimpleFund | null>(null)
  const [watchlists, setWatchlists] = useState<Watchlist[]>([])
  const [selectedWatchlistId, setSelectedWatchlistId] = useState('')
  const [watchlistReason, setWatchlistReason] = useState('')
  const [addingToWatchlist, setAddingToWatchlist] = useState(false)
  const [notice, setNotice] = useState('')
  const [filters, setFilters] = useState<BrowserFilters>(emptyFilters)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [availability, setAvailability] = useState<FundAvailability>(initialAvailability)
  const [source, setSource] = useState(initialSource)
  const [selectionContext, setSelectionContext] = useState<SelectionContext>(() => normalizeSelectionContext(initialSelectionContext))
  const [styleTagCatalog, setStyleTagCatalog] = useState<StyleTagCatalog>(() => normalizeStyleTagCatalog(initialStyleTagCatalog))
  const [selectedStyleTags, setSelectedStyleTags] = useState<string[]>([])
  const [styleMatch, setStyleMatch] = useState<'any' | 'all'>('any')
  const initialBondCategory = initialCategories.find((item) =>
    (item.name === initialPeerGroup || item.key === initialPeerGroup || item.id === initialPeerGroup)
    && item.contractDimensions,
  )
  const [bondBaseIndex, setBondBaseIndex] = useState(initialBondCategory?.contractDimensions?.baseIndex || '')
  const [bondPriceReturn, setBondPriceReturn] = useState(initialBondCategory?.contractDimensions?.priceReturn || '')
  const [bondTenor, setBondTenor] = useState(initialBondCategory?.contractDimensions?.tenor || '')

  const runSearch = useCallback(async (
    nextPeerGroup = peerGroupFilter,
    nextPage = 1,
    nextFilters = filters,
    nextAvailability = availability,
    nextSearch = searchText,
    nextStyleTags = selectedStyleTags,
    nextStyleMatch = styleMatch,
  ) => {
    setLoading(true)
    setError('')
    const params = new URLSearchParams({ limit: '30', page: String(nextPage), availability: nextAvailability })
    if (nextSearch.trim()) params.set('search', nextSearch.trim())
    if (nextPeerGroup) params.set('peerGroup', nextPeerGroup)
    if (nextPeerGroup) {
      if (nextFilters.assetMin) params.set('assetMin', nextFilters.assetMin)
      if (nextFilters.minAgeYears) params.set('minAgeYears', nextFilters.minAgeYears)
      if (nextFilters.minManagerYears) params.set('minManagerYears', nextFilters.minManagerYears)
      if (nextFilters.return6mMin) params.set('return6mMin', String(Number(nextFilters.return6mMin) / 100))
      if (nextFilters.return1yMin) params.set('return1yMin', String(Number(nextFilters.return1yMin) / 100))
      if (nextFilters.return3yMin) params.set('return3yMin', String(Number(nextFilters.return3yMin) / 100))
      if (nextFilters.maxDrawdown1yMax) params.set('maxDrawdown1yMax', String(Number(nextFilters.maxDrawdown1yMax) / 100))
      if (nextFilters.sharpe1yMin) params.set('sharpe1yMin', nextFilters.sharpe1yMin)
      if (nextStyleTags.length) params.set('styleTags', nextStyleTags.join(','))
      params.set('styleMatch', nextStyleMatch)
      params.set('sortBy', nextFilters.sortBy)
    }
    try {
      const response = await fetch(`/api/fund-browser?${params.toString()}`)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || '基金查询失败')
      setFunds(payload.data || [])
      setTotal(Number(payload.pagination?.total || 0))
      setAvailability((payload.availability || nextAvailability) as FundAvailability)
      setSource(String(payload.source || 'fund_database'))
      setSelectionContext(normalizeSelectionContext(payload.selectionContext))
      setStyleTagCatalog(normalizeStyleTagCatalog(payload.styleTagCatalog))
      setAppliedSearch(nextSearch.trim())
      setPage(nextPage)
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : '基金查询失败')
    } finally {
      setLoading(false)
    }
  }, [searchText, peerGroupFilter, filters, availability, selectedStyleTags, styleMatch])

  const compareCodes = compareFunds.map((fund) => fund.windCode)
  const compareHref = `/compare?${new URLSearchParams({ codes: compareCodes.join(',') }).toString()}`
  const lockedPeerGroup = compareFunds.length ? professionalPeerGroup(compareFunds[0]) : ''
  const quickCategories = useMemo(() => {
    return fundCategoryPresets.flatMap((preset) => {
      const category = initialCategories.find((item) => item.name === preset.category)
      return category ? [{ ...preset, ...category }] : []
    })
  }, [initialCategories])
  const selectedCategory = useMemo(
    () => initialCategories.find((item) => item.name === peerGroupFilter || item.key === peerGroupFilter || item.id === peerGroupFilter),
    [initialCategories, peerGroupFilter],
  )
  const bondCategories = useMemo(
    () => initialCategories.filter((item) => item.contractDimensions),
    [initialCategories],
  )
  const regularCategories = useMemo(
    () => initialCategories.filter((item) => !item.contractDimensions),
    [initialCategories],
  )
  const bondBaseIndexOptions = useMemo(
    () => uniqueBondDimensionOptions(bondCategories, 'baseIndex'),
    [bondCategories],
  )
  const bondPriceReturnOptions = useMemo(
    () => uniqueBondDimensionOptions(
      bondCategories.filter((item) => !bondBaseIndex || item.contractDimensions?.baseIndex === bondBaseIndex),
      'priceReturn',
    ),
    [bondCategories, bondBaseIndex],
  )
  const bondTenorOptions = useMemo(
    () => uniqueBondDimensionOptions(
      bondCategories.filter((item) => (
        (!bondBaseIndex || item.contractDimensions?.baseIndex === bondBaseIndex)
        && (!bondPriceReturn || item.contractDimensions?.priceReturn === bondPriceReturn)
      )),
      'tenor',
    ),
    [bondCategories, bondBaseIndex, bondPriceReturn],
  )
  const activeFilterCount = Object.entries(filters).filter(([key, value]) => key !== 'sortBy' && value).length + selectedStyleTags.length
  const selectedFilterChips = filterLabels.flatMap(([key, label, format]) => {
    const value = filters[key]
    return value ? [{ key, label: `${label}：${format(value)}` }] : []
  })
  const totalPages = Math.max(1, Math.ceil(total / 30))
  const sourceLabel = {
    database: '本地基金库',
    fund_database: '本地基金库',
    evaluated_fund_universe: '可评价基金库',
    standardized_classified_universe: '标准分类基金库',
    standardized_peer_group_universe: '标准同类基金库',
    unavailable: '暂不可用',
  }[source] || source
  const availabilityMeta: Record<FundAvailability, { label: string; description: string }> = {
    evaluated: { label: '可评价', description: '已分类且当前方法能实际输出专业评分；默认推荐从这里开始。' },
    classified: { label: '已分类', description: '已进入标准同类组，但部分基金仍缺少评价指标。' },
    all: { label: '全部基金', description: '完整基础基金库，包含待分类和数据待补基金。' },
  }

  function changeAvailability(nextAvailability: FundAvailability) {
    setCompareFunds([])
    setError('')
    void runSearch(peerGroupFilter, 1, filters, nextAvailability)
  }

  function updateFilter(key: keyof BrowserFilters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function resetFilters() {
    setFilters(emptyFilters)
    setSelectedStyleTags([])
    setStyleMatch('any')
    void runSearch(peerGroupFilter, 1, emptyFilters, availability, searchText, [], 'any')
  }

  function selectPeerGroup(nextPeerGroup: string, nextFilters = filters) {
    setPeerGroupFilter(nextPeerGroup)
    setStyleTagCatalog(normalizeStyleTagCatalog({}))
    setSelectedStyleTags([])
    setStyleMatch('any')
    setCompareFunds([])
    setError('')
    void runSearch(nextPeerGroup, 1, nextFilters, availability, searchText, [], 'any')
  }

  function selectRecommendedPlan(category: string) {
    const planFilters = { ...filters, sortBy: 'multi_period' }
    setFilters(planFilters)
    setBondBaseIndex('')
    setBondPriceReturn('')
    setBondTenor('')
    selectPeerGroup(category, planFilters)
  }

  function removeFilter(key: keyof BrowserFilters) {
    const nextFilters = { ...filters, [key]: '' }
    setFilters(nextFilters)
    void runSearch(peerGroupFilter, 1, nextFilters)
  }

  function toggleStyleTag(value: string) {
    setSelectedStyleTags((current) => current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value])
  }

  function removeStyleTag(value: string) {
    const nextTags = selectedStyleTags.filter((item) => item !== value)
    setSelectedStyleTags(nextTags)
    void runSearch(peerGroupFilter, 1, filters, availability, searchText, nextTags, styleMatch)
  }

  function selectBondDimension(dimension: BondDimensionKey, value: string) {
    const nextBaseIndex = dimension === 'baseIndex' ? value : bondBaseIndex
    const nextPriceReturn = dimension === 'baseIndex' ? '' : dimension === 'priceReturn' ? value : bondPriceReturn
    const nextTenor = dimension === 'baseIndex' || dimension === 'priceReturn' ? '' : value

    setBondBaseIndex(nextBaseIndex)
    setBondPriceReturn(nextPriceReturn)
    setBondTenor(nextTenor)

    const matchingCategories = bondCategories.filter((item) => {
      const contract = item.contractDimensions
      return contract
        && (!nextBaseIndex || contract.baseIndex === nextBaseIndex)
        && (!nextPriceReturn || contract.priceReturn === nextPriceReturn)
        && (!nextTenor || contract.tenor === nextTenor)
    })
    const exactCategory = nextBaseIndex && nextPriceReturn && nextTenor && matchingCategories.length === 1
      ? matchingCategories[0]
      : undefined

    setCompareFunds([])
    setError('')
    if (exactCategory) {
      setPeerGroupFilter(exactCategory.name)
      setStyleTagCatalog(normalizeStyleTagCatalog({}))
      setSelectedStyleTags([])
      setStyleMatch('any')
      void runSearch(exactCategory.name, 1, filters, availability, searchText, [], 'any')
    } else if (selectedCategory?.contractDimensions) {
      setPeerGroupFilter('')
    }
  }

  function resetBondDimensions() {
    setBondBaseIndex('')
    setBondPriceReturn('')
    setBondTenor('')
    if (selectedCategory?.contractDimensions) selectPeerGroup('')
  }

  function toggleCompare(fund: SimpleFund) {
    if (compareFunds.some((item) => item.windCode === fund.windCode)) {
      setCompareFunds((current) => current.filter((item) => item.windCode !== fund.windCode))
      return
    }
    if (compareFunds.length >= 6) return
    const selectedGroupId = professionalPeerGroupId(fund)
    if (!selectedGroupId) {
      setError('这只基金尚未完成专业分类，可以浏览，但暂不能加入同类比较。')
      return
    }
    if (compareFunds.length && professionalPeerGroupId(compareFunds[0]) !== selectedGroupId) {
      setError(`已锁定“${professionalPeerGroup(compareFunds[0])}”同类组，请只选择该类基金。`)
      return
    }
    setError('')
    setCompareFunds((current) => [...current, fund])
  }

  async function openWatchlist(fund: SimpleFund) {
    setError('')
    setNotice('')
    setWatchlistFund(fund)
    setWatchlistReason('')
    try {
      const response = await fetch('/api/watchlists', { cache: 'no-store' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || '加载自选分组失败')
      const groups = Array.isArray(payload.watchlists) ? payload.watchlists : []
      setWatchlists(groups)
      setSelectedWatchlistId(String(groups[0]?.id || ''))
    } catch (watchlistError) {
      setWatchlistFund(null)
      setError(watchlistError instanceof Error ? watchlistError.message : '加载自选分组失败')
    }
  }

  async function addToWatchlist() {
    if (!watchlistFund || !selectedWatchlistId) return
    setAddingToWatchlist(true)
    setError('')
    try {
      const response = await fetch(`/api/watchlists/${encodeURIComponent(selectedWatchlistId)}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fundId: watchlistFund.windCode, reason: watchlistReason.trim() || null }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || '加入自选失败')
      const groupName = watchlists.find((item) => String(item.id) === selectedWatchlistId)?.name || '我的自选'
      setNotice(`已将“${watchlistFund.name || watchlistFund.windCode}”加入“${groupName}”。`)
      setWatchlistFund(null)
    } catch (watchlistError) {
      setError(watchlistError instanceof Error ? watchlistError.message : '加入自选失败')
    } finally {
      setAddingToWatchlist(false)
    }
  }

  return (
    <div className="space-y-7">
      <section className="border-b border-[#dce1dc] pb-7">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="flex items-center gap-3 text-sm text-[#65716b]">
            <Link href="/evaluation" className="rounded-sm border border-[#9fc4b4] bg-white px-3 py-2 font-bold text-[#245c49] hover:bg-[#edf5f1]">评价一只基金</Link>
            <span className="rounded-sm bg-[#e7eee9] px-3 py-2 font-semibold text-[#245c49]">{total.toLocaleString('zh-CN')} 只基金</span>
            <span className="hidden sm:inline">来源：{sourceLabel}</span>
          </div>
        </div>

        <form
          className="mt-7 grid gap-3 lg:grid-cols-[minmax(0,1fr)_18rem_auto]"
          onSubmit={(event) => {
            event.preventDefault()
            void runSearch()
          }}
        >
          <label className="relative block min-w-0">
            <span className="sr-only">搜索基金</span>
            <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#7d8882]" />
            <input
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="输入基金名称或代码"
              className="h-12 w-full rounded-md border border-[#cfd6d0] bg-white pl-12 pr-4 text-sm outline-none transition focus:border-[#28745c] focus:ring-2 focus:ring-[#28745c]/10"
            />
          </label>
          <select
            value={peerGroupFilter}
            onChange={(event) => {
              const nextPeerGroup = event.target.value
              const category = initialCategories.find((item) => item.name === nextPeerGroup)
              if (category?.contractDimensions) {
                setBondBaseIndex(category.contractDimensions.baseIndex)
                setBondPriceReturn(category.contractDimensions.priceReturn)
                setBondTenor(category.contractDimensions.tenor)
              } else {
                setBondBaseIndex('')
                setBondPriceReturn('')
                setBondTenor('')
              }
              selectPeerGroup(nextPeerGroup)
            }}
            aria-label="专业同类组"
            className="h-12 min-w-0 w-full rounded-md border border-[#cfd6d0] bg-white px-4 text-sm outline-none focus:border-[#28745c]"
          >
            <option value="">全部专业类别</option>
            <optgroup label="常用专业类别">
              {regularCategories.map((category) => (
                <option key={category.id} value={category.name}>
                  {categoryDisplayName(category)}（可评价 {category.evaluatedCount} / 已分类 {category.count}）
                </option>
              ))}
            </optgroup>
            <optgroup label="债券合同基准">
              {bondCategories.map((category) => (
                <option key={category.id} value={category.name}>
                  {categoryDisplayName(category)}（可评价 {category.evaluatedCount} / 已分类 {category.count}）
                </option>
              ))}
            </optgroup>
          </select>
          <button type="submit" disabled={loading} className="h-12 rounded-md bg-[#173f35] px-6 text-sm font-bold text-white transition hover:bg-[#225747] disabled:opacity-60">
            {loading ? '查询中' : '查找基金'}
          </button>
        </form>
        {quickCategories.length ? (
          <div className="mt-5 border border-[#d8dfd9] bg-[#f7f8f3] p-5">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-[#758079]">第 1 步</span>
                <h2 className="mt-1 text-lg font-bold text-[#213029]">你想找什么基金？</h2>
                <p className="mt-1 text-xs leading-5 text-[#6e7973]">选择一个常见用途，系统自动锁定专业同类组，并按多周期同类表现排序。</p>
              </div>
              <span className="text-xs text-[#7a8580]">推荐方案</span>
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {quickCategories.map((item) => {
                const active = peerGroupFilter === item.category
                return (
                  <button
                    key={item.category}
                    type="button"
                    onClick={() => selectRecommendedPlan(item.category)}
                    className={`group min-h-28 border p-4 text-left transition ${active ? 'border-[#246149] bg-[#173f35] text-white shadow-[0_10px_25px_rgba(23,63,53,0.14)]' : 'border-[#d2d9d3] bg-white text-[#27342e] hover:-translate-y-0.5 hover:border-[#759c8c]'}`}
                  >
                    <span className={`text-[10px] font-bold tracking-[0.16em] ${active ? 'text-[#b9d9cc]' : 'text-[#87928c]'}`}>{item.mark}</span>
                    <strong className="mt-3 block text-base">{item.label}</strong>
                    <small className={`mt-1 block leading-5 ${active ? 'text-[#d2e4dc]' : 'text-[#6f7b75]'}`}>{item.description}</small>
                    <span className={`mt-3 block text-[11px] font-bold ${active ? 'text-white' : 'text-[#28745c]'}`}>可评价 {item.evaluatedCount} 只</span>
                  </button>
                )
              })}
            </div>
          </div>
        ) : null}
        <details className="mt-4 border border-[#d6ddd7] bg-[#f7f8f5]">
          <summary className="cursor-pointer px-4 py-3 text-sm font-bold text-[#4f5d56]">专业筛选与数据范围</summary>
          <div className="border-t border-[#dbe1dc] px-4 pb-4">
        {bondCategories.length ? (
          <div className="mt-4 border border-[#d6ddd7] bg-[#f7f9f7] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <strong className="text-sm text-[#26332d]">债券基金精确分类</strong>
                <p className="mt-1 text-xs leading-5 text-[#738078]">依次选择基础指数、收益口径和期限。三项必须完全一致，才进入同一个专业同类组。</p>
              </div>
              {(bondBaseIndex || bondPriceReturn || bondTenor) ? (
                <button type="button" onClick={resetBondDimensions} className="inline-flex items-center gap-1.5 text-xs font-bold text-[#5d6c65]"><RotateCcw className="h-3.5 w-3.5" />重置</button>
              ) : null}
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <BondDimensionSelect label="基础指数" value={bondBaseIndex} options={bondBaseIndexOptions} dimension="baseIndex" onChange={(value) => {
                selectBondDimension('baseIndex', value)
              }} />
              <BondDimensionSelect label="收益口径" value={bondPriceReturn} options={bondPriceReturnOptions} dimension="priceReturn" disabled={!bondBaseIndex} onChange={(value) => {
                selectBondDimension('priceReturn', value)
              }} />
              <BondDimensionSelect label="期限" value={bondTenor} options={bondTenorOptions} dimension="tenor" disabled={!bondBaseIndex || !bondPriceReturn} onChange={(value) => selectBondDimension('tenor', value)} />
            </div>
            {selectedCategory?.contractDimensions ? (
              <div className="mt-3 border-l-2 border-[#28745c] bg-white px-3 py-2 text-xs text-[#476158]">
                当前同类组：<strong>{categoryDisplayName(selectedCategory)}</strong> · 可评价 {selectedCategory.evaluatedCount} / 已分类 {selectedCategory.count}
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="mt-4 flex flex-col gap-3 border border-[#dbe1dc] bg-white p-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-2">
            {(['evaluated', 'classified', 'all'] as FundAvailability[]).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => changeAvailability(item)}
                disabled={loading}
                className={availability === item ? 'bg-[#173f35] px-4 py-2 text-xs font-bold text-white' : 'border border-[#cbd3cd] bg-[#f8faf8] px-4 py-2 text-xs font-bold text-[#53615a]'}
              >
                {availabilityMeta[item].label}
              </button>
            ))}
          </div>
          <p className="text-xs leading-5 text-[#68756e]">{availabilityMeta[availability].description}</p>
        </div>
        {selectedCategory ? (
          <div className="mt-4 grid gap-px overflow-hidden border border-[#d7ded9] bg-[#d7ded9] sm:grid-cols-3">
            <CoverageStat label="已分类" value={selectedCategory.count} detail="同一专业类别的基金实体" />
            <CoverageStat label="可评价" value={selectedCategory.evaluatedCount} detail={`覆盖率 ${(selectedCategory.evaluationCoverage * 100).toFixed(1)}%`} strong />
            <CoverageStat label="评价待补" value={selectedCategory.pendingCount} detail={selectedCategory.evaluationAsOfDate ? `数据截至 ${selectedCategory.evaluationAsOfDate}` : '核心指标仍待同步'} />
          </div>
        ) : null}

        <div className="mt-5 border border-[#d6ddd7] bg-[#f7f8f5]">
          <button type="button" onClick={() => setFiltersOpen((current) => !current)} className="flex w-full items-center gap-3 px-4 py-3 text-left">
            <span className="grid h-8 w-8 place-items-center bg-[#e5ece7] text-[#27634f]"><SlidersHorizontal className="h-4 w-4" /></span>
            <span className="min-w-0 flex-1"><strong className="block text-sm text-[#26332d]">快速筛选</strong><small className="mt-0.5 block text-xs text-[#758079]">先选专业类别，再用风格标签、业绩和风险缩小范围</small></span>
            {activeFilterCount ? <span className="rounded-full bg-[#27634f] px-2.5 py-1 text-xs font-bold text-white">已选 {activeFilterCount}</span> : null}
            <span className="text-xs font-semibold text-[#5f6b65]">{filtersOpen ? '收起' : '展开'}</span>
          </button>

          {filtersOpen ? (
            <div className="border-t border-[#dbe1dc] px-4 py-5">
              {!peerGroupFilter ? <div className="mb-4 border-l-2 border-[#b8863d] bg-[#fff8e9] px-4 py-3 text-xs leading-5 text-[#72541f]">请先选择一个专业同类组。不同类别不应放在同一个收益或风险榜单中。</div> : null}
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <FilterSelect label="基金规模" value={filters.assetMin} disabled={!peerGroupFilter} onChange={(value) => updateFilter('assetMin', value)} options={[["", "不限"], ["5", "不少于 5 亿"], ["10", "不少于 10 亿"], ["50", "不少于 50 亿"]]} />
                <FilterSelect label="成立年限" value={filters.minAgeYears} disabled={!peerGroupFilter} onChange={(value) => updateFilter('minAgeYears', value)} options={[["", "不限"], ["1", "至少 1 年"], ["3", "至少 3 年"], ["5", "至少 5 年"]]} />
                <FilterSelect label="经理管理年限" value={filters.minManagerYears} disabled={!peerGroupFilter} onChange={(value) => updateFilter('minManagerYears', value)} options={[["", "不限"], ["3", "至少 3 年"], ["5", "至少 5 年"], ["10", "至少 10 年"]]} />
                <FilterSelect label="近 6 月收益" value={filters.return6mMin} disabled={!peerGroupFilter} onChange={(value) => updateFilter('return6mMin', value)} options={[["", "不限"], ["0", "不低于 0%"], ["5", "不低于 5%"], ["10", "不低于 10%"]]} />
                <FilterSelect label="近 1 年收益" value={filters.return1yMin} disabled={!peerGroupFilter} onChange={(value) => updateFilter('return1yMin', value)} options={[["", "不限"], ["0", "不低于 0%"], ["5", "不低于 5%"], ["10", "不低于 10%"]]} />
                <FilterSelect label="近 3 年累计收益" value={filters.return3yMin} disabled={!peerGroupFilter} onChange={(value) => updateFilter('return3yMin', value)} options={[["", "不限"], ["0", "不低于 0%"], ["10", "不低于 10%"], ["30", "不低于 30%"]]} />
                <FilterSelect label="近 1 年最大回撤" value={filters.maxDrawdown1yMax} disabled={!peerGroupFilter} onChange={(value) => updateFilter('maxDrawdown1yMax', value)} options={[["", "不限"], ["10", "不超过 10%"], ["20", "不超过 20%"], ["30", "不超过 30%"]]} />
                <FilterSelect label="近 1 年 Sharpe" value={filters.sharpe1yMin} disabled={!peerGroupFilter} onChange={(value) => updateFilter('sharpe1yMin', value)} options={[["", "不限"], ["0", "不低于 0"], ["0.5", "不低于 0.5"], ["1", "不低于 1"]]} />
                <div className="border border-[#d7ded9] bg-[#f8faf8] p-4 md:col-span-2 xl:col-span-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <strong className="text-sm text-[#2b3932]">风格标签</strong>
                      <p className="mt-1 text-xs leading-5 text-[#718078]">
                        {peerGroupFilter
                          ? `标签覆盖 ${styleTagCatalog.taggedFundCount}/${styleTagCatalog.fundCount} 只；持仓量化 ${styleTagCatalog.holdingFundCount}、产品纪要 ${styleTagCatalog.memoFundCount}、产品定位 ${styleTagCatalog.positioningFundCount}。`
                          : '选择专业同类组后，显示该组可核验的标签。'}
                      </p>
                    </div>
                    {selectedStyleTags.length > 1 ? (
                      <div className="flex border border-[#cbd5cf] bg-white p-1 text-[11px] font-bold">
                        <button type="button" onClick={() => setStyleMatch('any')} className={styleMatch === 'any' ? 'bg-[#285f4c] px-3 py-1.5 text-white' : 'px-3 py-1.5 text-[#66736c]'}>任一匹配</button>
                        <button type="button" onClick={() => setStyleMatch('all')} className={styleMatch === 'all' ? 'bg-[#285f4c] px-3 py-1.5 text-white' : 'px-3 py-1.5 text-[#66736c]'}>全部匹配</button>
                      </div>
                    ) : null}
                  </div>
                  {styleTagCatalog.tags.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {styleTagCatalog.tags.map((tag) => {
                        const selected = selectedStyleTags.includes(tag.value)
                        const sourceLabel = tag.evidenceLevel === 'strong' ? '持仓' : tag.evidenceLevel === 'context' ? '纪要' : '定位'
                        return (
                          <button
                            key={tag.value}
                            type="button"
                            disabled={!peerGroupFilter}
                            onClick={() => toggleStyleTag(tag.value)}
                            title={tag.sourceLabels.join('、')}
                            className={selected ? 'border border-[#285f4c] bg-[#285f4c] px-3 py-2 text-xs font-bold text-white' : 'border border-[#cdd6d0] bg-white px-3 py-2 text-xs text-[#536159] hover:border-[#739887]'}
                          >
                            {tag.value} · {tag.fundCount}<span className={`ml-1.5 text-[9px] ${selected ? 'text-[#d5e8df]' : 'text-[#8a958f]'}`}>{sourceLabel}</span>
                          </button>
                        )
                      })}
                    </div>
                  ) : (
                    <p className="mt-3 border-l-2 border-[#b8863d] bg-[#fff8e9] px-3 py-2 text-xs leading-5 text-[#74551e]">
                      {peerGroupFilter ? '该同类组暂无可核验标签；不会用经理层纪要或模型猜测补标签。' : '暂无标签目录。'}
                    </p>
                  )}
                  {styleTagCatalog.boundary ? <p className="mt-3 text-[10px] leading-5 text-[#87928c]">{styleTagCatalog.boundary}</p> : null}
                </div>
                <FilterSelect label="结果排序" value={filters.sortBy} disabled={!peerGroupFilter} onChange={(value) => updateFilter('sortBy', value)} options={[["quality", "数据较完整优先"], ["multi_period", "多周期同类领先"], ["return_6m", "近 6 月收益较高"], ["return_1y", "近 1 年收益较高"], ["return_3y", "近 3 年收益较高"], ["drawdown", "回撤较小优先"], ["sharpe", "Sharpe 较高优先"], ["asset", "规模较大优先"], ["history", "成立较早优先"]]} />
                <div className="flex items-end gap-2">
                  <button type="button" disabled={!peerGroupFilter || loading} onClick={() => void runSearch(peerGroupFilter, 1)} className="h-11 flex-1 bg-[#173f35] px-4 text-sm font-bold text-white transition hover:bg-[#225747] disabled:cursor-not-allowed disabled:opacity-40">应用筛选</button>
                  <button type="button" disabled={!activeFilterCount && filters.sortBy === 'multi_period'} onClick={resetFilters} className="grid h-11 w-11 place-items-center border border-[#c7d0ca] bg-white text-[#66736c] disabled:opacity-40" aria-label="清空筛选"><RotateCcw className="h-4 w-4" /></button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
          </div>
        </details>

        <div className="mt-4 border border-[#d7ded9] bg-white px-4 py-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <strong className="mr-1 text-[#34423b]">已选条件</strong>
            {peerGroupFilter ? (
              <button type="button" onClick={() => selectPeerGroup('')} className="inline-flex items-center gap-1.5 border border-[#bad0c5] bg-[#edf5f1] px-2.5 py-1.5 font-bold text-[#245f4b]">
                {categoryDisplayName(selectedCategory) || peerGroupFilter}<X className="h-3 w-3" />
              </button>
            ) : <span className="text-[#8a948f]">尚未选择专业类别</span>}
            {selectedFilterChips.map((item) => (
              <button key={item.key} type="button" onClick={() => removeFilter(item.key)} className="inline-flex items-center gap-1.5 border border-[#d3dad5] bg-[#f7f8f7] px-2.5 py-1.5 text-[#5b6861]">
                {item.label}<X className="h-3 w-3" />
              </button>
            ))}
            {selectedStyleTags.map((tag) => (
              <button key={tag} type="button" onClick={() => removeStyleTag(tag)} className="inline-flex items-center gap-1.5 border border-[#bad0c5] bg-[#edf5f1] px-2.5 py-1.5 font-bold text-[#245f4b]">
                风格：{tag}<X className="h-3 w-3" />
              </button>
            ))}
            {peerGroupFilter ? <span className="border border-[#e2d6bd] bg-[#fff8e9] px-2.5 py-1.5 font-semibold text-[#73571f]">排序：{sortLabels[filters.sortBy] || filters.sortBy}</span> : null}
            {(peerGroupFilter || activeFilterCount || filters.sortBy !== 'multi_period') ? (
              <button type="button" onClick={() => {
                setPeerGroupFilter('')
                setFilters(emptyFilters)
                setSelectedStyleTags([])
                setStyleMatch('any')
                setCompareFunds([])
                void runSearch('', 1, emptyFilters, availability, searchText, [], 'any')
              }} className="ml-auto inline-flex items-center gap-1.5 font-bold text-[#6d7872]"><RotateCcw className="h-3.5 w-3.5" />全部清空</button>
            ) : null}
          </div>
        </div>
      </section>

      {error ? (
        <div className="border border-[#e5c98f] bg-[#fff8e8] px-5 py-4 text-sm text-[#78551c]">{error}</div>
      ) : null}
      {notice ? (
        <div className="flex items-center justify-between gap-4 border border-[#bad7ca] bg-[#edf6f1] px-5 py-4 text-sm text-[#285c49]"><span>{notice}</span><Link href="/watchlist" className="font-bold underline underline-offset-4">查看我的自选</Link></div>
      ) : null}

      {lockedPeerGroup ? (
        <section className="flex flex-wrap items-center gap-x-4 gap-y-2 border-l-4 border-[#2b775d] bg-[#eef5f1] px-5 py-4 text-sm text-[#315e4d]">
          <strong>比较已锁定：{lockedPeerGroup}</strong>
          <span className="text-xs text-[#64736c]">已选 {compareCodes.length} / 6 只，其他类别不会加入。</span>
        </section>
      ) : null}

      <section>
        <div className="flex flex-wrap items-center justify-between gap-3 pb-4">
          <div>
            <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-[#758079]">第 2 步</span>
            <h2 className="mt-1 text-lg font-bold">{appliedSearch ? `“${appliedSearch}”的结果` : peerGroupFilter ? '看同类表现' : '先选一个用途'}</h2>
            <p className="mt-1 text-xs text-[#7b8680]">{peerGroupFilter ? `当前只显示“${categoryDisplayName(selectedCategory) || peerGroupFilter}”标准同类组 · ${availabilityMeta[availability].label} · ${sortLabels[filters.sortBy] || filters.sortBy}。` : '全市场列表只用于查找，不产生跨类别排名。请选择上方推荐方案后再判断优劣。'}</p>
          </div>
          {compareCodes.length >= 2 ? (
            <Link href={compareHref} className="inline-flex h-10 items-center gap-2 rounded-md bg-[#173f35] px-4 text-sm font-bold text-white">
              <GitCompareArrows className="h-4 w-4" />比较 {compareCodes.length} 只基金
            </Link>
          ) : null}
        </div>

        {(peerGroupFilter || appliedSearch) && selectionContext.summary ? (
          <div className="mb-4 border border-[#c8d8cf] bg-[#f1f7f3] p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <strong className="text-sm text-[#264537]">本次筛选怎么来的</strong>
                <p className="mt-1 text-xs leading-6 text-[#5f6e66]">{selectionContext.summary}</p>
              </div>
              <span className="bg-white px-2.5 py-1 text-[10px] font-bold text-[#28745c]">共 {total.toLocaleString('zh-CN')} 只</span>
            </div>
            {selectionContext.rules.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {selectionContext.rules.map((rule) => <span key={rule.key} className="border border-[#d7e1db] bg-white px-2.5 py-1.5 text-[11px] text-[#52635a]">{rule.text}</span>)}
              </div>
            ) : null}
            <p className="mt-3 text-[10px] leading-5 text-[#87928c]">{selectionContext.boundary}</p>
          </div>
        ) : null}

        {!peerGroupFilter && !appliedSearch ? (
          <div className="border border-dashed border-[#cbd3cd] bg-[#fafbf8] px-6 py-14 text-center text-sm text-[#748079]">
            <CircleAlert className="mx-auto mb-3 h-5 w-5 text-[#9a7a3a]" />
            选择“大盘核心”“主动选股”“稳健债券”等用途后，这里会展示同类基金的多周期表现和风险提示。
          </div>
        ) : funds.length === 0 ? (
          <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-16 text-center text-sm text-[#748079]"><CircleAlert className="mx-auto mb-3 h-5 w-5 text-[#9a7a3a]" />没有找到可展示的基金。</div>
        ) : (
          <div className="space-y-3">
            <FundBrowserViewControls
              mode={viewMode}
              onModeChange={setViewMode}
              compareCount={compareFunds.length}
              compareHref={compareHref}
              onClearCompare={() => setCompareFunds([])}
            />
            {viewMode === 'cards' ? <div className="grid gap-3 xl:grid-cols-2">
              {funds.map((fund) => (
                <FundBrowserResultCard
                  key={fund.windCode}
                  fund={fund}
                  selected={compareCodes.includes(fund.windCode)}
                  compareCount={compareCodes.length}
                  onToggleCompare={toggleCompare}
                  onOpenWatchlist={(item) => void openWatchlist(item)}
                />
              ))}
            </div> : null}

            {viewMode === 'table' ? <details open className="border border-[#dbe1dc] bg-white">
              <summary className="cursor-pointer px-4 py-3 text-xs font-bold text-[#53615a]">专业数据表 · 逐列比较</summary>
              <FundBrowserDataTable
                funds={funds}
                compareCodes={compareCodes}
                peerGroupName={(name) => peerGroupDisplayName(name, initialCategories)}
                onToggleCompare={toggleCompare}
                onOpenWatchlist={(fund) => void openWatchlist(fund)}
              />
            </details> : null}
          </div>
        )}

        {(peerGroupFilter || appliedSearch) && funds.length > 0 && totalPages > 1 ? (
          <div className="mt-5 flex items-center justify-between border-t border-[#dce2dd] pt-4 text-sm">
            <span className="text-[#718078]">第 {page} / {totalPages} 页 · 共 {total.toLocaleString('zh-CN')} 只</span>
            <div className="flex gap-2">
              <button type="button" disabled={page <= 1 || loading} onClick={() => void runSearch(peerGroupFilter, page - 1)} className="inline-flex h-9 items-center gap-2 border border-[#c6d0c9] bg-white px-3 font-semibold disabled:opacity-40"><ArrowLeft className="h-4 w-4" />上一页</button>
              <button type="button" disabled={page >= totalPages || loading} onClick={() => void runSearch(peerGroupFilter, page + 1)} className="inline-flex h-9 items-center gap-2 border border-[#c6d0c9] bg-white px-3 font-semibold disabled:opacity-40">下一页<ArrowRight className="h-4 w-4" /></button>
            </div>
          </div>
        ) : null}
      </section>

      {peerGroupFilter ? (
        <section className="border border-[#d8dfd9] bg-[#f7f8f3] px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-[#758079]">第 3 步</span>
              <strong className="mt-1 block text-sm text-[#27342e]">选中 2—6 只基金做同类比较</strong>
              <p className="mt-1 text-xs text-[#707b75]">比较只接受当前专业同类组，避免把风险收益特征不同的基金放在一起。</p>
            </div>
            <Link href={compareCodes.length >= 2 ? compareHref : '/compare'} aria-disabled={compareCodes.length < 2} className={`inline-flex h-10 items-center gap-2 px-4 text-sm font-bold ${compareCodes.length >= 2 ? 'bg-[#173f35] text-white' : 'pointer-events-none bg-[#dde3df] text-[#89938e]'}`}>
              <GitCompareArrows className="h-4 w-4" />{compareCodes.length >= 2 ? `比较 ${compareCodes.length} 只基金` : `还需选择 ${2 - compareCodes.length} 只`}
            </Link>
          </div>
        </section>
      ) : null}

      {watchlistFund ? (
        <div className="fixed inset-0 z-[70] grid place-items-center bg-[#13221c]/55 p-4" role="dialog" aria-modal="true" aria-label="加入我的自选">
          <div className="w-full max-w-md border border-[#d7ddd8] bg-[#fbfcfa] p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div><div className="text-xs font-bold uppercase tracking-[0.1em] text-[#28745c]">加入自选</div><h2 className="mt-2 text-xl font-bold text-[#18231e]">{watchlistFund.name || watchlistFund.windCode}</h2><p className="mt-1 text-xs text-[#75817b]">{watchlistFund.windCode}</p></div>
              <button type="button" onClick={() => setWatchlistFund(null)} className="grid h-8 w-8 place-items-center text-[#69756f] hover:bg-[#edf0ed]" aria-label="关闭"><X className="h-4 w-4" /></button>
            </div>
            <label className="mt-6 block text-xs font-bold text-[#5e6a64]">选择分组
              <select value={selectedWatchlistId} onChange={(event) => setSelectedWatchlistId(event.target.value)} className="mt-2 h-11 w-full border border-[#cbd3cd] bg-white px-3 text-sm outline-none focus:border-[#28745c]">
                {watchlists.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            <label className="mt-4 block text-xs font-bold text-[#5e6a64]">为什么关注（可不填）
              <textarea value={watchlistReason} onChange={(event) => setWatchlistReason(event.target.value)} rows={3} placeholder="例如：同类中回撤较小，继续观察经理风格是否稳定。" className="mt-2 w-full resize-none border border-[#cbd3cd] bg-white p-3 text-sm leading-6 outline-none focus:border-[#28745c]" />
            </label>
            <div className="mt-6 flex justify-end gap-2"><button type="button" onClick={() => setWatchlistFund(null)} className="h-10 border border-[#cbd3cd] px-4 text-sm font-bold text-[#5f6b65]">取消</button><button type="button" onClick={() => void addToWatchlist()} disabled={addingToWatchlist || !selectedWatchlistId} className="h-10 bg-[#173f35] px-5 text-sm font-bold text-white disabled:opacity-50">{addingToWatchlist ? '加入中' : '加入自选'}</button></div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function FilterSelect({ label, value, options, disabled, onChange }: { label: string; value: string; options: string[][]; disabled: boolean; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-bold text-[#5d6963]">{label}</span>
      <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} className="h-11 w-full border border-[#cbd3cd] bg-white px-3 text-sm outline-none transition focus:border-[#28745c] disabled:cursor-not-allowed disabled:bg-[#ecefeb] disabled:text-[#9aa39e]">
        {options.map(([optionValue, optionLabel]) => <option key={`${label}-${optionValue}`} value={optionValue}>{optionLabel}</option>)}
      </select>
    </label>
  )
}

function BondDimensionSelect({ label, value, options, dimension, disabled = false, onChange }: { label: string; value: string; options: string[]; dimension: BondDimensionKey; disabled?: boolean; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-bold text-[#5d6963]">{label}</span>
      <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} className="h-11 w-full border border-[#cbd3cd] bg-white px-3 text-sm outline-none transition focus:border-[#28745c] disabled:cursor-not-allowed disabled:bg-[#ecefeb] disabled:text-[#9aa39e]">
        <option value="">请选择</option>
        {options.map((option) => <option key={`${dimension}-${option}`} value={option}>{bondDimensionLabel(dimension, option)}</option>)}
      </select>
    </label>
  )
}

function CoverageStat({ label, value, detail, strong = false }: { label: string; value: number; detail: string; strong?: boolean }) {
  return (
    <div className="bg-white px-4 py-3">
      <span className="block text-[11px] font-bold text-[#758079]">{label}</span>
      <strong className={`mt-1 block text-xl ${strong ? 'text-[#28745c]' : 'text-[#26332d]'}`}>{value.toLocaleString('zh-CN')}</strong>
      <small className="mt-1 block text-[10px] text-[#849089]">{detail}</small>
    </div>
  )
}
