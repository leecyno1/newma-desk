'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { AlertCircle, ChevronLeft, ChevronRight, Copy, Download, GitCompare, Globe2, Search, ShieldCheck, Sparkles } from 'lucide-react'
import { materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'

interface Fund {
  id: string
  windCode: string
  name: string
  type: string
  nav: number | null
  navDate: string | null
  totalAsset: number | null
  establishmentDate: string | null
  performanceData: unknown
}

type SalesRuleGapStatus = {
  windCode: string
  priority: 'high' | 'medium' | 'low'
  missingItems: string[]
  missingCount: number
  nextAction?: string
  alertsHref?: string | null
  gateSource?: string | null
}

type RawAlertEvent = {
  fund_id?: string | null
  event_type?: string
  status?: string
  title?: string
  message?: string
  details?: unknown
}

type RiskProfile = 'conservative' | 'balanced' | 'aggressive'
type InvestmentHorizon = 'lt1y' | '1to3y' | 'gt3y'
type PurchasePlan = 'lump_sum' | 'sip'

function appendReturnTo(href: string, returnTo: string) {
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`
}

function defaultPlannedAmountForPlan(purchasePlan: PurchasePlan) {
  return purchasePlan === 'lump_sum' ? '10000' : '1000'
}

function normalizePlannedAmountInput(value: string | null | undefined, purchasePlan: PurchasePlan) {
  const amount = Number(value || '')
  return Number.isFinite(amount) && amount > 0 ? String(Math.round(amount)) : defaultPlannedAmountForPlan(purchasePlan)
}

function plannedAmountSearchParams(purchasePlan: PurchasePlan, plannedAmount: string) {
  const amount = normalizePlannedAmountInput(plannedAmount, purchasePlan)
  return {
    plannedAmount: amount,
    [purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount']: amount,
  }
}

function pickBrowserParam<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  if (typeof globalThis.window === 'undefined') return fallback
  const value = new URLSearchParams(globalThis.window.location.search).get(key) || ''
  return allowed.includes(value as T) ? value as T : fallback
}

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : {}
    } catch {
      return {}
    }
  }
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function stringValue(value: unknown) {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function alertFundCode(event: RawAlertEvent) {
  const details = asRecord(event.details)
  return (
    stringValue(details.wind_code) ||
    stringValue(details.fund_code) ||
    stringValue(event.fund_id)
  ).toUpperCase()
}

export default function FundsPage() {
  const initialPurchasePlan = useMemo(() => pickBrowserParam('purchasePlan', ['lump_sum', 'sip'] as const, 'sip'), [])
  const [funds, setFunds] = useState<Fund[]>([])
  const [loading, setLoading] = useState(true)
  const [searchText, setSearchText] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [riskProfile, setRiskProfile] = useState<RiskProfile>(() => pickBrowserParam('profile', ['conservative', 'balanced', 'aggressive'] as const, 'balanced'))
  const [investmentHorizon, setInvestmentHorizon] = useState<InvestmentHorizon>(() => pickBrowserParam('horizon', ['lt1y', '1to3y', 'gt3y'] as const, '1to3y'))
  const [purchasePlan, setPurchasePlan] = useState<PurchasePlan>(initialPurchasePlan)
  const [plannedAmount, setPlannedAmount] = useState(() => {
    if (typeof globalThis.window === 'undefined') return defaultPlannedAmountForPlan(initialPurchasePlan)
    const params = new URLSearchParams(globalThis.window.location.search)
    return normalizePlannedAmountInput(
      params.get('plannedAmount') || params.get(initialPurchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount'),
      initialPurchasePlan,
    )
  })
  const [compareCodes, setCompareCodes] = useState<string[]>([])
  const [purchaseQueueTsvStatus, setPurchaseQueueTsvStatus] = useState<'idle' | 'copied' | 'fallback'>('idle')
  const [salesRuleGaps, setSalesRuleGaps] = useState<SalesRuleGapStatus[]>([])
  const [salesRuleGapsChecked, setSalesRuleGapsChecked] = useState(false)
  const plannedAmountParams = useMemo(
    () => plannedAmountSearchParams(purchasePlan, plannedAmount),
    [plannedAmount, purchasePlan],
  )

  const fetchFunds = useCallback(async () => {
    setLoading(true)
    setErrorMessage(null)
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '20',
        purchasePlan,
        ...plannedAmountParams,
        ...(appliedSearch && { search: appliedSearch })
      })

      const response = await fetch(`/api/funds?${params}`)
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data.error || '获取基金列表失败')
      }

      setFunds(data.data || [])
      setTotalPages(data.pagination?.totalPages || 1)
      setCompareCodes([])
      setSalesRuleGaps([])
      setSalesRuleGapsChecked(false)
    } catch (error) {
      console.error('获取基金列表失败:', error)
      setFunds([])
      setTotalPages(1)
      setErrorMessage(error instanceof Error ? error.message : '获取基金列表失败')
    } finally {
      setLoading(false)
    }
  }, [appliedSearch, page, plannedAmountParams, purchasePlan])

  useEffect(() => {
    const timeout = globalThis.setTimeout(() => {
      void fetchFunds()
    }, 0)
    return () => globalThis.clearTimeout(timeout)
  }, [fetchFunds])

  const currentFundCodes = useMemo(
    () => Array.from(new Set(funds.map((fund) => fund.windCode).filter(Boolean))),
    [funds],
  )

  useEffect(() => {
    const controller = new AbortController()
    const timeout = globalThis.setTimeout(async () => {
      if (!currentFundCodes.length) {
        setSalesRuleGaps([])
        setSalesRuleGapsChecked(!loading)
        return
      }

      try {
        setSalesRuleGapsChecked(false)
        const params = new URLSearchParams({ codes: currentFundCodes.slice(0, 100).join(','), purchasePlan, ...plannedAmountParams })
        const [gapResponse, alertsResponse] = await Promise.all([
          fetch(`/api/evidence-coverage/materials/gaps?${params.toString()}`, {
            cache: 'no-store',
            signal: controller.signal,
          }),
          fetch('/api/evidence-coverage/review-events', {
            cache: 'no-store',
            signal: controller.signal,
          }),
        ])
        const payload = await gapResponse.json().catch(() => ({}))
        const alertsPayload = await alertsResponse.json().catch(() => ({}))
        if (!gapResponse.ok) throw new Error(payload.error || payload.detail || '读取基金列表销售规则缺口失败')
        if (!alertsResponse.ok) throw new Error(alertsPayload.error || alertsPayload.detail || '读取复查队列失败，不能证明销售规则/R1-R5证据有效。')
        const gapMap = ((payload.gaps || []) as SalesRuleGapStatus[]).reduce((acc, gap) => {
          acc.set(gap.windCode.toUpperCase(), gap)
          return acc
        }, new Map<string, SalesRuleGapStatus>())
        const targetCodes = new Set(currentFundCodes.map((code) => code.toUpperCase()))
        const activeSalesRuleAlerts = (Array.isArray(alertsPayload.events) ? alertsPayload.events as RawAlertEvent[] : [])
          .filter((event) => event.event_type === 'sales_rule_evidence' && event.status !== 'resolved' && targetCodes.has(alertFundCode(event)))
        activeSalesRuleAlerts.forEach((event) => {
          const windCode = alertFundCode(event)
          const existing = gapMap.get(windCode)
          const title = stringValue(event.title) || '销售规则/R1-R5证据待补'
          const message = stringValue(event.message)
          const missingItem = `复查队列未解决：${title}${message ? `（${message}）` : ''}`
          const missingItems = Array.from(new Set([...(existing?.missingItems || []), missingItem]))
          gapMap.set(windCode, {
            ...(existing || { windCode }),
            priority: 'high',
            missingItems,
            missingCount: Math.max(existing?.missingCount || 0, missingItems.length),
            nextAction: '先打开复查队列，处理销售规则/R1-R5过期或待补事件',
            alertsHref: reviewEventsHref(),
            gateSource: 'local.alert_events.sales_rule_evidence',
          })
        })
        setSalesRuleGaps(Array.from(gapMap.values()))
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error('读取基金列表销售规则缺口失败:', error)
          setSalesRuleGaps(currentFundCodes.map((windCode) => ({
            windCode,
            priority: 'high',
            missingItems: ['复查队列读取失败：不能证明销售规则/R1-R5证据有效'],
            missingCount: 1,
            nextAction: '先打开复查队列，确认销售规则/R1-R5证据事件状态后再继续研究复核',
            alertsHref: reviewEventsHref(),
            gateSource: 'local.alert_events.sales_rule_evidence',
          })))
        }
      } finally {
        if (!controller.signal.aborted) setSalesRuleGapsChecked(true)
      }
    }, 0)

    return () => {
      controller.abort()
      globalThis.clearTimeout(timeout)
    }
  }, [currentFundCodes, loading, plannedAmountParams, purchasePlan])

  const detailContextQuery = useMemo(() => new URLSearchParams({
    profile: riskProfile,
    horizon: investmentHorizon,
    purchasePlan,
    ...plannedAmountParams,
  }).toString(), [investmentHorizon, plannedAmountParams, purchasePlan, riskProfile])
  const fundsReturnHref = useMemo(() => {
    const params = new URLSearchParams({
      page: String(page),
      profile: riskProfile,
      horizon: investmentHorizon,
      purchasePlan,
      ...plannedAmountParams,
    })
    if (appliedSearch) params.set('search', appliedSearch)
    return `/funds?${params.toString()}`
  }, [appliedSearch, investmentHorizon, page, plannedAmountParams, purchasePlan, riskProfile])
  const comparisonHref = compareCodes.length >= 2
    ? appendReturnTo(`/analysis/comparison?${new URLSearchParams({
      codes: compareCodes.join(','),
      profile: riskProfile,
      horizon: investmentHorizon,
      purchasePlan,
      ...plannedAmountParams,
      autoReplay: '1',
    }).toString()}`, fundsReturnHref)
    : appendReturnTo('/analysis/comparison', fundsReturnHref)
  const salesRulesHref = compareCodes.length
    ? appendReturnTo(materialEvidenceHref(new URLSearchParams({ codes: compareCodes.join(','), purchasePlan, ...plannedAmountParams })), fundsReturnHref)
    : appendReturnTo(materialEvidenceHref(new URLSearchParams({ purchasePlan, ...plannedAmountParams })), fundsReturnHref)
  const salesRulesHrefForFund = (fund: Fund) => appendReturnTo(
    materialEvidenceHref(new URLSearchParams({ codes: fund.windCode, purchasePlan, ...plannedAmountParams })),
    fundsReturnHref,
  )
  const detailHref = (fund: Fund) => appendReturnTo(`/funds/${encodeURIComponent(fund.id)}?${detailContextQuery}`, fundsReturnHref)
  const salesRuleGapByCode = useMemo(() => {
    const gapMap = new Map<string, SalesRuleGapStatus>()
    salesRuleGaps.forEach((gap) => gapMap.set(gap.windCode.toUpperCase(), gap))
    return gapMap
  }, [salesRuleGaps])
  const listGateSummary = useMemo(() => {
    const gapCodes = new Set(salesRuleGaps.map((gap) => gap.windCode.toUpperCase()))
    const readyCodes = currentFundCodes.filter((code) => !gapCodes.has(code.toUpperCase()))
    const reviewAlertBlocked = salesRuleGaps.some((gap) => Boolean(gap.alertsHref))
    return {
      ready: salesRuleGapsChecked ? readyCodes.length : 0,
      blocked: salesRuleGaps.length,
      reviewAlerts: salesRuleGaps.filter((gap) => Boolean(gap.alertsHref)).length,
      missingItems: salesRuleGaps.reduce((sum, gap) => sum + gap.missingCount, 0),
      highPriority: salesRuleGaps.filter((gap) => gap.priority === 'high').length,
      blockedHref: reviewAlertBlocked
        ? reviewEventsHref({ returnTo: fundsReturnHref })
        : appendReturnTo(
          salesRuleGaps.length
          ? materialEvidenceHref(new URLSearchParams({ codes: salesRuleGaps.map((gap) => gap.windCode).join(','), purchasePlan, ...plannedAmountParams }))
          : materialEvidenceHref(new URLSearchParams({ purchasePlan, ...plannedAmountParams })),
          fundsReturnHref,
        ),
      reviewAlertBlocked,
    }
  }, [currentFundCodes, fundsReturnHref, plannedAmountParams, purchasePlan, salesRuleGaps, salesRuleGapsChecked])
  const fundListPurchaseQueue = useMemo(() => {
    return funds.slice(0, 8).map((fund) => {
      const gap = salesRuleGapByCode.get(fund.windCode.toUpperCase()) || null
      const reviewAlertBlocked = Boolean(gap?.alertsHref)
      const status = !salesRuleGapsChecked ? 'scanning' : gap ? 'rules_missing' : 'ready'
      return {
        fund,
        gap,
        status,
        label: status === 'scanning'
          ? '规则扫描中'
          : status === 'rules_missing'
            ? reviewAlertBlocked ? '复查队列补证' : '先补销售规则'
            : '可进入研究复核',
        action: status === 'rules_missing'
          ? reviewAlertBlocked
            ? '先打开复查队列，处理销售规则/R1-R5过期或待补事件'
            : `补齐 ${gap?.missingCount ?? 0} 项销售规则硬缺口`
          : status === 'ready'
            ? '进入详情复核净值回放、持仓暴露、同类比较和报告留痕'
            : '等待当前页销售规则扫描完成',
        href: status === 'rules_missing' ? gap?.alertsHref || salesRulesHrefForFund(fund) : detailHref(fund),
        badgeClass: status === 'rules_missing'
          ? reviewAlertBlocked ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800'
          : status === 'ready'
            ? 'bg-emerald-100 text-emerald-800'
            : 'bg-slate-100 text-slate-600',
      }
    })
  }, [detailHref, funds, salesRuleGapByCode, salesRuleGapsChecked, salesRulesHrefForFund])
  const fundListQueueTsvCell = (value: unknown) => String(value ?? '').replace(/\t/g, ' ').replace(/\r?\n/g, ' ').trim()
  const fundListPurchaseQueueTsv = [
    ['基金代码', '基金名称', '基金类型', '研究状态', '销售规则缺口数', '缺口字段', '下一步', '详情入口', '补证入口', '硬边界'].join('\t'),
    ...fundListPurchaseQueue.map((item) => [
      item.fund.windCode,
      item.fund.name,
      item.fund.type || '类型待补',
      item.label,
      item.gap?.missingCount ?? 0,
      item.gap?.missingItems.join('、') || '无',
      item.action,
      detailHref(item.fund),
      item.gap?.alertsHref || salesRulesHrefForFund(item.fund),
      '基金列表只作为入口；销售规则硬缺口或复查队列未清零前，不能保存正式研究复核报告或把基金当成研究候选。',
    ].map(fundListQueueTsvCell).join('\t')),
    ['说明', '当前页研究行动队列', '', salesRuleGapsChecked ? '门禁已扫描' : '门禁扫描中', listGateSummary.missingItems, listGateSummary.reviewAlerts ? `复查队列 ${listGateSummary.reviewAlerts} 只` : '', `研究口径：${purchasePlan === 'sip' ? '每月定投' : '一次性配置'} ${normalizePlannedAmountInput(plannedAmount, purchasePlan)} 元`, fundsReturnHref, listGateSummary.blockedHref, '列表页不输出申赎指令；正式判断必须进入详情、横评和研究复核报告门禁。'].map(fundListQueueTsvCell).join('\t'),
  ].join('\n')
  const downloadFundListPurchaseQueueTsv = () => {
    if (!fundListPurchaseQueue.length) return
    const blob = new Blob([`\ufeff${fundListPurchaseQueueTsv}`], { type: 'text/tab-separated-values;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `基金列表研究行动队列_${purchasePlan}_${new Date().toISOString().slice(0, 10)}.tsv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }
  const copyFundListPurchaseQueueTsv = async () => {
    if (!fundListPurchaseQueue.length) return
    try {
      if (!globalThis.navigator?.clipboard?.writeText) {
        throw new Error('clipboard unavailable')
      }
      await globalThis.navigator.clipboard.writeText(fundListPurchaseQueueTsv)
      setPurchaseQueueTsvStatus('copied')
    } catch {
      downloadFundListPurchaseQueueTsv()
      setPurchaseQueueTsvStatus('fallback')
    }
    globalThis.setTimeout(() => setPurchaseQueueTsvStatus('idle'), 1800)
  }

  const investorSelectionHref = `/investor-selection?${new URLSearchParams({
    profile: riskProfile,
    horizon: investmentHorizon,
    purchasePlan,
    ...plannedAmountParams,
    eligibleOnly: 'true',
    minEvidenceGrade: 'B',
  }).toString()}`
  const marketHref = `/market?${new URLSearchParams({
    profile: riskProfile,
    horizon: investmentHorizon,
    purchasePlan,
    ...plannedAmountParams,
  }).toString()}`
  const fundAnalysisHref = (fund: Fund) => `/analysis/fund?${new URLSearchParams({
    fundId: fund.id,
    profile: riskProfile,
    horizon: investmentHorizon,
    purchasePlan,
    ...plannedAmountParams,
  }).toString()}`

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    setAppliedSearch(searchText.trim())
  }

  const toggleCompare = (fund: Fund) => {
    setCompareCodes((current) => {
      if (current.includes(fund.windCode)) return current.filter((code) => code !== fund.windCode)
      return [...current, fund.windCode].slice(0, 6)
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-end gap-4">
        {!loading && funds.length === 0 && !errorMessage ? (
          <button
            type="button"
            onClick={() => void fetchFunds()}
            className="inline-flex rounded-lg border border-blue-200 px-3 py-2 text-sm text-blue-700 hover:bg-blue-50"
          >
            加载基金列表
          </button>
        ) : null}
        <Link href={marketHref} className="inline-flex items-center gap-2 rounded-lg bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100">
          <Globe2 className="h-4 w-4" /> 前往全市场浏览器
        </Link>
      </div>

      <div className="rounded-xl border border-blue-100 bg-blue-50 p-4 text-sm text-blue-800">
        <div className="flex items-start gap-2">
          <Sparkles className="mt-0.5 h-4 w-4" />
          <span>如果你要做研究清单构建，优先从全市场浏览器开始；这里更适合做单只基金详情回看。</span>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold text-slate-900">
              <ShieldCheck className="h-5 w-5 text-blue-600" />
              研究查看上下文
            </div>
            <p className="mt-1 text-sm text-slate-500">从列表进入详情、横评和报告时会保留这组画像。</p>
          </div>
          <div className="grid gap-3 md:grid-cols-4">
            <label className="text-xs font-medium text-slate-500">
              风险画像
              <select value={riskProfile} onChange={(event) => setRiskProfile(event.target.value as RiskProfile)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900">
                <option value="conservative">稳健型</option>
                <option value="balanced">均衡型</option>
                <option value="aggressive">进取型</option>
              </select>
            </label>
            <label className="text-xs font-medium text-slate-500">
              持有期
              <select value={investmentHorizon} onChange={(event) => setInvestmentHorizon(event.target.value as InvestmentHorizon)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900">
                <option value="lt1y">1年以内</option>
                <option value="1to3y">1-3年</option>
                <option value="gt3y">3年以上</option>
              </select>
            </label>
            <label className="text-xs font-medium text-slate-500">
              研究方式
              <select value={purchasePlan} onChange={(event) => setPurchasePlan(event.target.value as PurchasePlan)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900">
                <option value="sip">定投</option>
                <option value="lump_sum">一次性配置</option>
              </select>
            </label>
            <label className="text-xs font-medium text-slate-500">
              {purchasePlan === 'sip' ? '每月定投金额' : '计划配置金额'}
              <input
                type="number"
                min="1"
                step="100"
                value={plannedAmount}
                onChange={(event) => setPlannedAmount(event.target.value)}
                onBlur={() => setPlannedAmount((value) => normalizePlannedAmountInput(value, purchasePlan))}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </label>
          </div>
        </div>
        <div className="mt-4 rounded-xl bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600">
          当前研究口径：{purchasePlan === 'sip' ? '每月定投' : '一次性配置'} ¥{Number(normalizePlannedAmountInput(plannedAmount, purchasePlan)).toLocaleString('zh-CN')}；销售规则扫描、补证、详情、横评和研究模型都按此金额判断起购/定投起点/限购。
        </div>
      </div>

      {errorMessage && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <AlertCircle className="mt-0.5 h-4 w-4" />
          <span>{errorMessage}</span>
        </div>
      )}

      <div className="rounded-lg bg-white p-4 shadow">
        <form onSubmit={handleSearch} className="flex gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索基金名称或代码..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="w-full rounded-lg border border-gray-300 py-2 pl-10 pr-4 focus:border-transparent focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <button type="submit" className="rounded-lg bg-blue-600 px-6 py-2 text-white transition-colors hover:bg-blue-700">
            搜索
          </button>
        </form>
      </div>

      <div className="overflow-hidden rounded-lg bg-white shadow">
        {loading ? (
          <div className="p-8 text-center text-gray-500">加载中...</div>
        ) : funds.length === 0 ? (
          <div className="p-8 text-center text-gray-500">暂无数据，可尝试切换到全市场浏览器扩大搜索范围。</div>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-6 py-4">
              <div className="text-sm text-gray-600">
                对比篮：{compareCodes.length ? compareCodes.join(' / ') : '尚未选择基金'}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setCompareCodes(funds.slice(0, 4).map((fund) => fund.windCode))}
                  className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50"
                >
                  <GitCompare className="h-4 w-4" />
                  选当前前4只
                </button>
                {compareCodes.length ? (
                  <Link
                    href={salesRulesHref}
                    className="rounded-lg border border-cyan-200 px-3 py-2 text-sm font-medium text-cyan-700 hover:bg-cyan-50"
                  >
                    补已选规则
                  </Link>
                ) : (
                  <span className="cursor-not-allowed rounded-lg bg-cyan-100 px-3 py-2 text-sm font-medium text-cyan-400">
                    补已选规则
                  </span>
                )}
                {compareCodes.length >= 2 ? (
                  <Link
                    href={comparisonHref}
                    className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
                  >
                    去对比（{compareCodes.length}）
                  </Link>
                ) : (
                  <span className="cursor-not-allowed rounded-lg bg-indigo-100 px-3 py-2 text-sm font-medium text-indigo-400">
                    去对比（{compareCodes.length}）
                  </span>
                )}
              </div>
            </div>
            <div className="border-b border-slate-100 bg-slate-50 px-6 py-5" data-testid="fund-list-purchase-gate-radar">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="text-sm font-semibold text-slate-950">当前页研究门禁雷达</div>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    基金列表只作为入口；销售规则硬缺口或复查队列未清零前，不能保存正式研究复核报告或把基金当成研究候选。
                  </p>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <span className="rounded-full bg-emerald-100 px-3 py-1 font-semibold text-emerald-700">
                    规则相对完整 {salesRuleGapsChecked ? listGateSummary.ready : '-'}
                  </span>
                  <span className="rounded-full bg-amber-100 px-3 py-1 font-semibold text-amber-700">
                    待补基金 {salesRuleGapsChecked ? listGateSummary.blocked : '-'}
                  </span>
                  <span className="rounded-full bg-rose-100 px-3 py-1 font-semibold text-rose-700">
                    缺口项 {salesRuleGapsChecked ? listGateSummary.missingItems : '-'}
                  </span>
                  {listGateSummary.reviewAlerts ? (
                    <span className="rounded-full bg-red-100 px-3 py-1 font-semibold text-red-700">
                      复查队列 {listGateSummary.reviewAlerts}
                    </span>
                  ) : null}
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2 text-sm">
                {listGateSummary.blocked ? (
                  <Link href={listGateSummary.blockedHref} className="rounded-lg bg-amber-600 px-3 py-2 font-medium text-white hover:bg-amber-700">
                    {listGateSummary.reviewAlertBlocked ? '处理复查队列' : '补当前页缺口'}
                  </Link>
                ) : null}
                <Link href={marketHref} className="rounded-lg border border-blue-200 px-3 py-2 font-medium text-blue-700 hover:bg-blue-50">
                  去全市场浏览器
                </Link>
                <Link href={investorSelectionHref} className="rounded-lg border border-emerald-200 px-3 py-2 font-medium text-emerald-700 hover:bg-emerald-50">
                  用研究模型筛
                </Link>
              </div>
            </div>
            <div className="border-b border-slate-100 bg-white px-6 py-5" data-testid="fund-list-purchase-action-queue">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-slate-950">基金列表研究行动队列</div>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    当前页前 8 只基金按“先补规则 / 再诊断 / 再横评和报告”拆解，避免列表页只停留在查看。
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
                    {salesRuleGapsChecked ? '门禁已扫描' : '门禁扫描中'}
                  </span>
                  <button
                    type="button"
                    onClick={() => void copyFundListPurchaseQueueTsv()}
                    disabled={!fundListPurchaseQueue.length}
                    className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                    data-testid="fund-list-purchase-queue-copy-tsv"
                  >
                    <Copy className="h-3.5 w-3.5" />
                    {purchaseQueueTsvStatus === 'copied' ? '已复制 TSV' : purchaseQueueTsvStatus === 'fallback' ? '已转下载 TSV' : '复制行动 TSV'}
                  </button>
                  <button
                    type="button"
                    onClick={downloadFundListPurchaseQueueTsv}
                    disabled={!fundListPurchaseQueue.length}
                    className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                    data-testid="fund-list-purchase-queue-download-tsv"
                  >
                    <Download className="h-3.5 w-3.5" />
                    下载行动 TSV
                  </button>
                </div>
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                {fundListPurchaseQueue.map((item) => (
                  <div key={item.fund.windCode} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold text-slate-950">{item.fund.name}</div>
                        <div className="mt-1 text-xs text-slate-500">{item.fund.windCode} · {item.fund.type || '类型待补'}</div>
                      </div>
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${item.badgeClass}`}>
                        {item.label}
                      </span>
                    </div>
                    <div className="mt-3 rounded-xl bg-white px-3 py-2 text-xs leading-5 text-slate-700 ring-1 ring-slate-100">
                      下一步：{item.action}
                    </div>
                    {item.gap ? (
                      <div className="mt-2 text-xs leading-5 text-amber-700">
                        缺口：{item.gap.missingItems.slice(0, 4).join('、')}
                      </div>
                    ) : null}
                    <div className="mt-3 flex flex-wrap gap-2 text-xs font-semibold">
                      <Link href={item.href} className="rounded-lg bg-slate-900 px-3 py-1.5 text-white hover:bg-slate-800">
                        {item.gap?.alertsHref ? '开复查队列' : item.status === 'rules_missing' ? '补规则' : '基金诊断'}
                      </Link>
                      <Link href={detailHref(item.fund)} className="rounded-lg border border-blue-200 px-3 py-1.5 text-blue-700 hover:bg-blue-50">
                        详情
                      </Link>
                      <button
                        type="button"
                        onClick={() => toggleCompare(item.fund)}
                        disabled={!compareCodes.includes(item.fund.windCode) && compareCodes.length >= 6}
                        className="rounded-lg border border-indigo-200 px-3 py-1.5 text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {compareCodes.includes(item.fund.windCode) ? '移出横评' : '加入横评'}
                      </button>
                      <Link href={item.gap?.alertsHref || salesRulesHrefForFund(item.fund)} className="rounded-lg border border-amber-200 px-3 py-1.5 text-amber-700 hover:bg-amber-50">
                        {item.gap?.alertsHref ? '开复查队列' : '查规则'}
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">基金代码</th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">基金名称</th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">类型</th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">最新净值</th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">规模(亿)</th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 bg-white">
                  {funds.map((fund) => {
                    const gap = salesRuleGapByCode.get(fund.windCode.toUpperCase()) || null
                    return (
                      <tr key={fund.id} className="hover:bg-gray-50">
                        <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-gray-900">{fund.windCode}</td>
                        <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-900">{fund.name}</td>
                        <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">{fund.type || '-'}</td>
                        <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-900">{fund.nav ? Number(fund.nav).toFixed(4) : '-'}</td>
                        <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-900">{fund.totalAsset ? Number(fund.totalAsset).toFixed(2) : '-'}</td>
                        <td className="whitespace-nowrap px-6 py-4 text-sm">
                          <div className="flex flex-wrap gap-3">
                            <Link href={detailHref(fund)} className="font-medium text-blue-600 hover:text-blue-700">查看详情</Link>
                            <Link href={fundAnalysisHref(fund)} className="font-medium text-purple-600 hover:text-purple-700">基金研究</Link>
                            <Link href={gap?.alertsHref || salesRulesHrefForFund(fund)} className="font-medium text-cyan-700 hover:text-cyan-900">
                              {gap?.alertsHref ? '开复查队列' : '补规则'}
                            </Link>
                            <button
                              type="button"
                              onClick={() => toggleCompare(fund)}
                              disabled={!compareCodes.includes(fund.windCode) && compareCodes.length >= 6}
                              className="font-medium text-indigo-700 hover:text-indigo-900 disabled:cursor-not-allowed disabled:text-gray-400"
                            >
                              {compareCodes.includes(fund.windCode) ? '移出对比' : '加入对比'}
                            </button>
                            <Link href={marketHref} className="font-medium text-indigo-600 hover:text-indigo-700">去全市场研究</Link>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between border-t border-gray-200 px-6 py-4">
              <div className="text-sm text-gray-500">第 {page} 页，共 {totalPages} 页</div>
              <div className="flex gap-2">
                <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="inline-flex items-center rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">
                  <ChevronLeft className="mr-1 h-4 w-4" /> 上一页
                </button>
                <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="inline-flex items-center rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50">
                  下一页 <ChevronRight className="ml-1 h-4 w-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
