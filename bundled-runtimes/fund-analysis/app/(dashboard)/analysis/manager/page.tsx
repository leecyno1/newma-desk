'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Sparkles, Loader2 } from 'lucide-react'
import ReportActionBar from '@/components/analysis/ReportActionBar'

type PurchasePlan = 'lump_sum' | 'sip'

const purchasePlanLabels: Record<PurchasePlan, string> = {
  lump_sum: '一次性配置',
  sip: '定投',
}

function appendReturnTo(href: string, returnTo: string) {
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`
}

function safeReturnPath(returnTo: string | null | undefined, fallback = '/analysis') {
  return returnTo?.startsWith('/') && !returnTo.startsWith('//') ? returnTo : fallback
}

function defaultPlannedAmountForPlan(purchasePlan: PurchasePlan) {
  return purchasePlan === 'lump_sum' ? '10000' : '1000'
}

function normalizePlannedAmountInput(value: string | null | undefined, purchasePlan: PurchasePlan) {
  const amount = Number(value || '')
  return Number.isFinite(amount) && amount > 0 ? String(Math.round(amount)) : defaultPlannedAmountForPlan(purchasePlan)
}

export default function ManagerAnalysisPage() {
  const [managerId, setManagerId] = useState('')
  const [includeReports, setIncludeReports] = useState(true)
  const [purchasePlan, setPurchasePlan] = useState<PurchasePlan>('sip')
  const [plannedAmount, setPlannedAmount] = useState('1000')
  const [generating, setGenerating] = useState(false)
  const [content, setContent] = useState('')
  const [status, setStatus] = useState('')
  const [reportId, setReportId] = useState<string | null>(null)
  const [sourceReturnHref, setSourceReturnHref] = useState('/analysis')
  const currentPlannedAmount = Number(normalizePlannedAmountInput(plannedAmount, purchasePlan))

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      const params = new URLSearchParams(window.location.search)
      const queryManagerId = params.get('managerId') || params.get('targetId') || ''
      const queryPurchasePlan = params.get('purchasePlan')
      const nextPurchasePlan = queryPurchasePlan === 'lump_sum' || queryPurchasePlan === 'sip' ? queryPurchasePlan : 'sip'
      if (queryManagerId) setManagerId(queryManagerId)
      setPurchasePlan(nextPurchasePlan)
      setPlannedAmount(normalizePlannedAmountInput(
        params.get('plannedAmount') || params.get(nextPurchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount'),
        nextPurchasePlan,
      ))
      setSourceReturnHref(safeReturnPath(params.get('returnTo')))
    }, 0)
    return () => window.clearTimeout(timeoutId)
  }, [])

  const handleGenerate = async () => {
    if (!managerId.trim()) {
      alert('请输入基金经理 ID')
      return
    }

    setGenerating(true)
    setContent('')
    setStatus('正在连接...')
    setReportId(null)

    try {
      const response = await fetch('/api/analysis/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'manager',
          targetId: managerId,
          includeReports,
          purchasePlan,
          plannedAmount: Number(normalizePlannedAmountInput(plannedAmount, purchasePlan)),
          returnTo: sourceReturnHref,
        })
      })

      if (!response.ok) {
        throw new Error('生成失败')
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('无法读取响应流')
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6))

            if (data.type === 'start' || data.type === 'progress') {
              setStatus(data.message)
            } else if (data.type === 'content') {
              setContent(prev => prev + data.text)
            } else if (data.type === 'complete') {
              setStatus(data.message)
              setReportId(data.reportId)
            } else if (data.type === 'error') {
              setStatus(`错误: ${data.message}`)
            }
          }
        }
      }
    } catch (error) {
      console.error('生成失败:', error)
      setStatus(`错误: ${error instanceof Error ? error.message : '生成失败'}`)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Link
        href={sourceReturnHref}
        className="inline-flex items-center text-gray-600 hover:text-gray-900"
        data-testid="manager-analysis-return-link"
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        返回
      </Link>

      <div className="bg-white rounded-lg shadow p-6">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              基金经理 ID *
            </label>
            <input
              type="text"
              value={managerId}
              onChange={(e) => setManagerId(e.target.value)}
              placeholder="输入基金经理 ID"
              disabled={generating}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent disabled:opacity-50"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              研究方式口径
            </label>
            <select
              value={purchasePlan}
              onChange={(event) => setPurchasePlan(event.target.value as PurchasePlan)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-green-500 focus:outline-none"
            >
              <option value="sip">{purchasePlanLabels.sip}</option>
              <option value="lump_sum">{purchasePlanLabels.lump_sum}</option>
            </select>
            <p className="mt-1 text-xs text-gray-500">
              影响报告里的横评和补销售规则入口，避免一次性配置被定投口径覆盖。
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              计划金额（元）
            </label>
            <input
              type="number"
              min={1}
              step={1}
              value={plannedAmount}
              onChange={(event) => setPlannedAmount(event.target.value)}
              onBlur={() => setPlannedAmount(normalizePlannedAmountInput(plannedAmount, purchasePlan))}
              disabled={generating}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-green-500 focus:outline-none disabled:opacity-50"
            />
            <p className="mt-1 text-xs text-gray-500">
              当前报告按 {purchasePlanLabels[purchasePlan]} · {Number(normalizePlannedAmountInput(plannedAmount, purchasePlan)).toLocaleString('zh-CN')} 元生成补规则和横评入口。
            </p>
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="includeReports"
              checked={includeReports}
              onChange={(e) => setIncludeReports(e.target.checked)}
              disabled={generating}
              className="w-4 h-4 text-green-600 border-gray-300 rounded focus:ring-green-500"
            />
            <label htmlFor="includeReports" className="ml-2 text-sm text-gray-700">
              包含调研报告（如果有）
            </label>
          </div>

          <button
            onClick={handleGenerate}
            disabled={!managerId.trim() || generating}
            className="w-full flex items-center justify-center px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {generating ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                生成中...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 mr-2" />
                生成分析报告
              </>
            )}
          </button>
        </div>
      </div>

      {status && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <p className="text-sm text-green-800">{status}</p>
        </div>
      )}

      {content && (
        <div className="bg-white rounded-lg shadow p-6 space-y-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">分析报告</h2>
            {reportId && (
              <Link
                href={appendReturnTo(`/reports/${reportId}`, sourceReturnHref)}
                className="text-sm text-green-600 hover:text-green-800"
              >
              查看完整报告
              </Link>
            )}
          </div>
          <ReportActionBar
            targetType="manager"
            targetId={managerId}
            content={content}
            reportId={reportId}
            purchasePlan={purchasePlan}
            plannedAmount={currentPlannedAmount}
            returnTo={sourceReturnHref}
          />
          <div className="prose max-w-none">
            <pre className="whitespace-pre-wrap text-sm text-gray-700 leading-relaxed font-sans">
              {content}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
