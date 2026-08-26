'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, FileText, Clock, Sparkles, CheckCircle2, AlertCircle } from 'lucide-react'
import { canonicalResearchHref, materialEvidenceHref } from '@/lib/research-platform/routes'

type AnalysisMetadata = {
  includeReports?: boolean
  reportsCount?: number
  reportCount?: number
  evidenceCount?: number
  chunksCount?: number
  referencesCount?: number
  generatedAt?: string
  completedAt?: string
  model?: string
  llmModel?: string
  mode?: string
  codes?: string[]
  dataSources?: Record<string, unknown>
  profile?: string
  horizon?: string
  purchasePlan?: string
  months?: string | number | null
  lumpSumAmount?: string | number | null
  monthlyAmount?: string | number | null
}

interface AnalysisReport {
  id: string
  reportType: string
  targetType: string
  targetTypeLabel?: string
  targetId: string
  compareId: string | null
  content: string
  prompt: string
  metadata: AnalysisMetadata | null
  createdAt: string
}

interface AnalysisDetailClientProps {
  reportId: string
  initialReport?: AnalysisReport | null
  initialError?: string | null
}

type CurrentSalesRuleGate = {
  status: 'idle' | 'loading' | 'ready' | 'blocked' | 'error'
  missingCount: number | null
  missingItems: string[]
  message: string
}

const getTrustSummary = (metadata: AnalysisMetadata | null) => {
  const reportsCount = metadata?.reportsCount || metadata?.reportCount || 0
  const evidenceCount = metadata?.evidenceCount || metadata?.chunksCount || metadata?.referencesCount || 0
  const generatedAt = metadata?.generatedAt || metadata?.completedAt || null
  const model = metadata?.model || metadata?.llmModel || '未知模型'
  const trustLevel = reportsCount >= 3 || evidenceCount >= 5 ? '较高' : reportsCount > 0 || evidenceCount > 0 ? '中等' : '待补证据'

  return {
    reportsCount,
    evidenceCount,
    generatedAt,
    model,
    trustLevel,
  }
}

const getGenerationBadge = (metadata: AnalysisMetadata | null) => {
  if (metadata?.mode === 'deterministic_pre_purchase_check') {
    return {
      label: '研究复核报告',
      className: 'bg-amber-100 text-amber-800',
    }
  }

  if (metadata?.mode === 'deterministic_fund_pool_shortlist') {
    return {
      label: '研究短名单报告',
      className: 'bg-emerald-100 text-emerald-800',
    }
  }

  if (metadata?.mode === 'deterministic_fund_comparison') {
    return {
      label: '横向比较报告',
      className: 'bg-purple-100 text-purple-800',
    }
  }

  if (metadata?.mode === 'deterministic_evidence_backed') {
    return {
      label: '本地证据报告',
      className: 'bg-emerald-100 text-emerald-800',
    }
  }

  return {
    label: '模型生成',
    className: 'bg-blue-100 text-blue-800',
  }
}

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}

const stringValue = (value: unknown) => {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function appendReturnTo(href: string, returnTo: string) {
  if (href.includes('returnTo=')) return href
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`
}

const reportContextParams = (report: AnalysisReport) => {
  const dataSources = asRecord(report.metadata?.dataSources)
  const investorContext = asRecord(dataSources.investorContext)
  const simulation = asRecord(dataSources.purchaseSimulation)
  const summary = asRecord(dataSources.summary)
  const params = new URLSearchParams()
  const profile = stringValue(investorContext.profile) || stringValue(report.metadata?.profile)
  const horizon = stringValue(investorContext.horizon) || stringValue(report.metadata?.horizon)
  const purchasePlan = stringValue(investorContext.purchasePlan) || stringValue(report.metadata?.purchasePlan) || stringValue(summary.purchasePlan)
  const months = stringValue(simulation.months) || stringValue(report.metadata?.months)
  const lumpSumAmount = stringValue(simulation.lumpSumAmount) || stringValue(report.metadata?.lumpSumAmount)
  const monthlyAmount = stringValue(simulation.monthlyAmount) || stringValue(report.metadata?.monthlyAmount)
  if (profile) params.set('profile', profile)
  if (horizon) params.set('horizon', horizon)
  if (purchasePlan) params.set('purchasePlan', purchasePlan)
  if (months) params.set('months', months)
  if (lumpSumAmount) params.set('lumpSumAmount', lumpSumAmount)
  if (monthlyAmount) params.set('monthlyAmount', monthlyAmount)
  return params
}

const salesRulesHrefForReport = (report: AnalysisReport, codes: string) => {
  const params = new URLSearchParams({ codes })
  const purchasePlan = reportContextParams(report).get('purchasePlan')
  if (purchasePlan) params.set('purchasePlan', purchasePlan)
  return materialEvidenceHref(params)
}

const getContextActions = (report: AnalysisReport, salesRuleGate: CurrentSalesRuleGate, reportReturnHref: string) => {
  if (report.targetType === 'fund_pool') {
    const actionLinks = asRecord(asRecord(report.metadata?.dataSources).actionLinks)
    const comparison = stringValue(actionLinks.comparison)
    return [
      { label: '回到研究清单', href: stringValue(actionLinks.pool) || '/market', tone: 'emerald' },
      { label: '补销售规则', href: appendReturnTo(stringValue(actionLinks.batchSalesRules) ? canonicalResearchHref(stringValue(actionLinks.batchSalesRules)) : materialEvidenceHref(), reportReturnHref), tone: 'amber' },
      ...(comparison ? [{ label: '重新打开对比', href: comparison, tone: 'blue' }] : []),
      { label: '重新下载短名单', href: `/api/market/research-lists/${encodeURIComponent(report.targetId)}/shortlist-report?format=markdown`, tone: 'slate', external: true },
    ]
  }

  if (report.targetType === 'fund') {
    const params = reportContextParams(report)
    const query = params.toString()
    const detailHref = `/funds/${encodeURIComponent(report.targetId)}${query ? `?${query}` : ''}`
    params.set('format', 'markdown')
    return [
      { label: '查看基金详情', href: detailHref, tone: 'blue' },
      { label: '补销售规则', href: appendReturnTo(salesRulesHrefForReport(report, report.targetId), reportReturnHref), tone: 'amber' },
      ...(salesRuleGate.status === 'ready'
        ? [{ label: '下载研究复核', href: `/api/funds/${encodeURIComponent(report.targetId)}/research-review-report?${params.toString()}`, tone: 'emerald', external: true }]
        : []),
    ]
  }

  if (report.targetType === 'manager') {
    return [
      { label: '查看基金经理', href: `/managers/${encodeURIComponent(report.targetId)}`, tone: 'blue' },
      { label: '回到经理库', href: '/managers', tone: 'slate' },
    ]
  }

  if (report.targetType === 'comparison') {
    const codes = Array.isArray(report.metadata?.codes)
      ? report.metadata.codes.filter(Boolean).join(',')
      : ''
    const codeParam = codes || report.targetId
    const params = new URLSearchParams({ codes: codeParam })
    const profile = stringValue(report.metadata?.profile)
    const horizon = stringValue(report.metadata?.horizon)
    const purchasePlan = stringValue(report.metadata?.purchasePlan)
    if (profile) params.set('profile', profile)
    if (horizon) params.set('horizon', horizon)
    if (purchasePlan) params.set('purchasePlan', purchasePlan)
    params.set('autoReplay', '1')
    return [
      { label: '重新打开对比', href: `/analysis/comparison?${params.toString()}`, tone: 'blue' },
      { label: '补销售规则', href: appendReturnTo(salesRulesHrefForReport(report, codeParam), reportReturnHref), tone: 'amber' },
      { label: '回到报告库', href: '/reports', tone: 'slate' },
    ]
  }

  return [
    { label: '回到报告库', href: '/reports', tone: 'slate' },
  ]
}

const actionClassName = (tone: string) => {
  if (tone === 'emerald') return 'bg-emerald-600 text-white hover:bg-emerald-700'
  if (tone === 'amber') return 'border border-amber-200 text-amber-700 hover:bg-amber-50'
  if (tone === 'blue') return 'bg-blue-600 text-white hover:bg-blue-700'
  return 'border border-gray-200 text-gray-700 hover:bg-gray-50'
}

export default function AnalysisDetailClient({
  reportId,
  initialReport = null,
  initialError = null,
}: AnalysisDetailClientProps) {
  const [report, setReport] = useState<AnalysisReport | null>(initialReport)
  const [loading, setLoading] = useState(!initialReport && !initialError)
  const [loadedId, setLoadedId] = useState(initialReport || initialError ? reportId : '')
  const [bannerMessage, setBannerMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(initialError)
  const [salesRuleGate, setSalesRuleGate] = useState<CurrentSalesRuleGate>({
    status: 'idle',
    missingCount: null,
    missingItems: [],
    message: '销售规则硬缺口待扫描',
  })

  const fetchReport = useCallback(async () => {
    if (!reportId) return

    setLoading(true)
    setBannerMessage(null)
    setErrorMessage(null)
    try {
      const response = await fetch(`/api/analysis/${reportId}`)
      if (response.ok) {
        const data = await response.json()
        setReport(data)
        setLoadedId(reportId)
      } else {
        setReport(null)
        setLoadedId(reportId)
        setErrorMessage('分析报告不存在或暂时不可用')
      }
    } catch (error) {
      console.error('获取分析报告失败:', error)
      setReport(null)
      setLoadedId(reportId)
      setErrorMessage('获取分析报告失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [reportId])

  useEffect(() => {
    if (reportId && loadedId !== reportId) {
      const timeout = globalThis.setTimeout(() => {
        void fetchReport()
      }, 0)
      return () => globalThis.clearTimeout(timeout)
    }
  }, [reportId, loadedId, fetchReport])

  useEffect(() => {
    let cancelled = false
    const timeout = globalThis.setTimeout(async () => {
      if (!report || report.targetType !== 'fund' || !report.targetId) {
        if (cancelled) return
        setSalesRuleGate({
          status: 'idle',
          missingCount: null,
          missingItems: [],
          message: '非单基金报告不需要单基金销售规则门禁',
        })
        return
      }

      setSalesRuleGate({
        status: 'loading',
        missingCount: null,
        missingItems: [],
        message: '正在扫描当前基金销售规则硬缺口...',
      })

      try {
        const params = new URLSearchParams({ codes: report.targetId, limit: '1' })
        const purchasePlan = reportContextParams(report).get('purchasePlan')
        if (purchasePlan === 'lump_sum' || purchasePlan === 'sip') params.set('purchasePlan', purchasePlan)
        const response = await fetch(`/api/evidence-coverage/materials/gaps?${params.toString()}`, { cache: 'no-store' })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(payload.error || payload.detail || '读取销售规则硬缺口失败')
        if (cancelled) return

        const gap = (payload.gaps || [])[0]
        const missingItems = Array.isArray(gap?.missingItems) ? gap.missingItems.map(String) : []
        const missingCount = Number(gap?.missingCount || 0)
        setSalesRuleGate({
          status: missingCount > 0 ? 'blocked' : 'ready',
          missingCount,
          missingItems,
          message: missingCount > 0
            ? `当前基金销售规则仍缺 ${missingCount} 项：${missingItems.slice(0, 5).join('、')}。旧研究复核报告只能回看，不能继续下载为正式研究复核。`
            : '当前未检测到销售规则硬缺口，可重新生成研究复核报告；形成研究结论前仍需复核销售平台实时状态。',
        })
      } catch (error) {
        if (cancelled) return
        setSalesRuleGate({
          status: 'error',
          missingCount: null,
          missingItems: [],
          message: error instanceof Error ? error.message : '读取销售规则硬缺口失败',
        })
      }
    }, 0)

    return () => {
      cancelled = true
      globalThis.clearTimeout(timeout)
    }
  }, [report])

  const trust = useMemo(() => getTrustSummary(report?.metadata || null), [report])
  const generationBadge = useMemo(() => getGenerationBadge(report?.metadata || null), [report])
  const reportReturnHref = `/analysis/${encodeURIComponent(reportId)}`
  const contextActions = useMemo(() => report ? getContextActions(report, salesRuleGate, reportReturnHref) : [], [report, reportReturnHref, salesRuleGate])
  const stalePrePurchaseReport =
    Boolean(report?.reportType && (report.reportType === 'fund_pre_purchase_check' || report.reportType === '研究复核报告')) &&
    salesRuleGate.status === 'blocked'

  if (!loadedId && !loading) {
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        <Link href="/analysis" className="inline-flex items-center text-gray-600 hover:text-gray-900">
          <ArrowLeft className="mr-2 h-4 w-4" />
          返回列表
        </Link>
        <div className="rounded-lg bg-white p-10 text-center text-gray-500 shadow">
          点击下方按钮加载分析报告详情。
          <div className="mt-4">
            <button onClick={() => void fetchReport()} className="rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700">
              加载报告
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-gray-500">加载中...</div>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center">
        <div className="mb-4 text-gray-500">{errorMessage || '分析报告不存在'}</div>
        <div className="flex gap-3">
          <Link href="/analysis" className="text-blue-600 hover:text-blue-800">
            返回列表
          </Link>
          <button onClick={() => void fetchReport()} className="text-gray-700 hover:text-gray-900">
            重试加载
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <Link href="/analysis" className="inline-flex items-center text-gray-600 hover:text-gray-900">
          <ArrowLeft className="mr-2 h-4 w-4" />
          返回列表
        </Link>
        <button onClick={() => void fetchReport()} className="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">
          刷新报告
        </button>
      </div>

      {bannerMessage && (
        <div className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          <CheckCircle2 className="mt-0.5 h-4 w-4" />
          <span>{bannerMessage}</span>
        </div>
      )}

      {errorMessage && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <AlertCircle className="mt-0.5 h-4 w-4" />
          <span>{errorMessage}</span>
        </div>
      )}

      <div className="rounded-lg bg-white p-6 shadow">
        <div className="mb-4 flex items-start justify-between">
          <div className="flex items-center">
            <div className="mr-4 rounded-lg bg-blue-100 p-3">
              <Sparkles className="h-6 w-6 text-blue-600" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{report.reportType}</h1>
              <div className="mt-2 flex items-center gap-4 text-sm text-gray-500">
                <div className="flex items-center">
                  <Clock className="mr-1 h-4 w-4" />
                  {new Date(report.createdAt).toLocaleString('zh-CN')}
                </div>
                <div className="flex items-center">
                  <FileText className="mr-1 h-4 w-4" />
                  {report.targetTypeLabel || (report.targetType === 'fund' ? '基金' : report.targetType === 'fund_pool' ? '研究清单' : report.targetType === 'comparison' ? '基金对比' : '基金经理')}
                </div>
              </div>
            </div>
          </div>
          <span className={`rounded-full px-3 py-1 text-sm ${generationBadge.className}`}>{generationBadge.label}</span>
        </div>

        {report.metadata && (
          <div className="mt-4 rounded-lg bg-gray-50 p-4 text-sm text-gray-600">
            {report.metadata.includeReports ? `包含 ${report.metadata.reportsCount || 0} 份调研报告` : '当前报告未显式绑定研报证据'}
          </div>
        )}

        {report.targetType === 'fund' ? (
          <div className={`mt-4 rounded-xl border px-4 py-3 text-sm ${
            salesRuleGate.status === 'ready'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
              : salesRuleGate.status === 'loading'
                ? 'border-slate-200 bg-slate-50 text-slate-700'
                : 'border-amber-200 bg-amber-50 text-amber-800'
          }`}>
            <div className="font-semibold">当前销售规则门禁</div>
            <div className="mt-1 leading-5">{salesRuleGate.message}</div>
            {salesRuleGate.status !== 'ready' ? (
              <div className="mt-2">
                <Link href={appendReturnTo(salesRulesHrefForReport(report, report.targetId), reportReturnHref)} className="font-medium underline underline-offset-2">
                  先补销售规则
                </Link>
              </div>
            ) : null}
          </div>
        ) : null}

        {contextActions.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {contextActions.map((action) => (
              action.external ? (
                <a key={action.label} href={action.href} className={`rounded-lg px-3 py-2 text-sm font-medium ${actionClassName(action.tone)}`}>
                  {action.label}
                </a>
              ) : (
                <Link key={action.label} href={action.href} className={`rounded-lg px-3 py-2 text-sm font-medium ${actionClassName(action.tone)}`}>
                  {action.label}
                </Link>
              )
            ))}
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div className="rounded-lg bg-white p-5 shadow">
          <div className="text-xs text-gray-500">可信度等级</div>
          <div className="mt-2 text-xl font-semibold text-gray-900">{trust.trustLevel}</div>
          <div className="mt-1 text-xs text-gray-500">依据已接入证据与报告数量判断</div>
        </div>
        <div className="rounded-lg bg-white p-5 shadow">
          <div className="text-xs text-gray-500">报告证据数</div>
          <div className="mt-2 text-xl font-semibold text-gray-900">{trust.reportsCount}</div>
          <div className="mt-1 text-xs text-gray-500">可追溯到研报与外部材料</div>
        </div>
        <div className="rounded-lg bg-white p-5 shadow">
          <div className="text-xs text-gray-500">片段 / 引用数</div>
          <div className="mt-2 text-xl font-semibold text-gray-900">{trust.evidenceCount}</div>
          <div className="mt-1 text-xs text-gray-500">用于支持结论的底层证据片段</div>
        </div>
        <div className="rounded-lg bg-white p-5 shadow">
          <div className="text-xs text-gray-500">生成模型</div>
          <div className="mt-2 break-all text-sm font-semibold text-gray-900">{trust.model}</div>
          <div className="mt-1 text-xs text-gray-500">{trust.generatedAt ? `证据整理于 ${new Date(trust.generatedAt).toLocaleString('zh-CN')}` : '暂无证据整理时间'}</div>
        </div>
      </div>

      <div className="rounded-lg bg-white p-6 shadow">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">分析报告</h2>
        <div className="prose max-w-none">
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-gray-700">{report.content}</pre>
        </div>
      </div>

      <div className="flex gap-4">
        <button
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(report.content)
              setBannerMessage('分析报告已复制到剪贴板。')
              setErrorMessage(null)
            } catch (error) {
              console.error('复制报告失败:', error)
              setErrorMessage('复制失败，请手动复制内容')
            }
          }}
          className="flex-1 rounded-lg border border-gray-300 px-6 py-3 text-gray-700 transition-colors hover:bg-gray-50"
        >
          复制内容
        </button>
        <button
          onClick={() => {
            const blob = new Blob([report.content], { type: 'text/plain' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `${report.reportType}${stalePrePurchaseReport ? '_旧报告回看' : ''}_${new Date().toISOString().split('T')[0]}.txt`
            a.click()
            URL.revokeObjectURL(url)
            setBannerMessage(stalePrePurchaseReport ? '旧研究复核报告已下载，仅供回看；补齐销售规则后再重新生成正式研究复核。' : '分析报告文件已开始下载。')
            setErrorMessage(null)
          }}
          className={`flex-1 rounded-lg px-6 py-3 text-white transition-colors ${stalePrePurchaseReport ? 'bg-amber-600 hover:bg-amber-700' : 'bg-blue-600 hover:bg-blue-700'}`}
        >
          {stalePrePurchaseReport ? '下载旧报告回看' : '下载报告'}
        </button>
      </div>
    </div>
  )
}
