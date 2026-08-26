'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Sparkles, Loader2 } from 'lucide-react'
import ReportActionBar from '@/components/analysis/ReportActionBar'

type PurchasePlan = 'lump_sum' | 'sip'

function defaultPlannedAmountForPlan(purchasePlan: PurchasePlan) {
  return purchasePlan === 'lump_sum' ? '10000' : '1000'
}

function normalizePlannedAmountInput(value: string | null | undefined, purchasePlan: PurchasePlan) {
  const amount = Number(value || '')
  return Number.isFinite(amount) && amount > 0 ? String(Math.round(amount)) : defaultPlannedAmountForPlan(purchasePlan)
}

export default function FundAnalysisClient({
  initialFundId = '',
  initialPurchasePlan = 'sip',
  initialPlannedAmount = '',
}: {
  initialFundId?: string
  initialPurchasePlan?: PurchasePlan
  initialPlannedAmount?: string
}) {
  const [fundId, setFundId] = useState(initialFundId)
  const [purchasePlan, setPurchasePlan] = useState<PurchasePlan>(initialPurchasePlan)
  const [plannedAmount, setPlannedAmount] = useState(() => normalizePlannedAmountInput(initialPlannedAmount, initialPurchasePlan))
  const [includeReports, setIncludeReports] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [content, setContent] = useState('')
  const [status, setStatus] = useState('')
  const [reportId, setReportId] = useState<string | null>(null)
  const currentPlannedAmount = () => Number(normalizePlannedAmountInput(plannedAmount, purchasePlan))
  const currentAnalysisReturnHref = `/analysis/fund?${new URLSearchParams({
    fundId: fundId.trim(),
    purchasePlan,
    plannedAmount: String(currentPlannedAmount()),
    [purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount']: String(currentPlannedAmount()),
  }).toString()}`

  const handleGenerate = async () => {
    if (!fundId.trim()) {
      alert('请输入基金 ID')
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
            type: 'fund',
            targetId: fundId,
            includeReports,
            purchasePlan,
            plannedAmount: currentPlannedAmount(),
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
        href="/analysis"
        className="inline-flex items-center text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        返回
      </Link>

      <div className="bg-white rounded-lg shadow p-6">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              基金 ID *
            </label>
            <input
              type="text"
              value={fundId}
              onChange={(e) => setFundId(e.target.value)}
              placeholder="输入基金 ID"
              disabled={generating}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
            />
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="block text-sm font-medium text-gray-700">
              研究方式口径
              <select
                value={purchasePlan}
                onChange={(event) => {
                  const nextPlan = event.target.value as PurchasePlan
                  setPurchasePlan(nextPlan)
                  setPlannedAmount((value) => normalizePlannedAmountInput(value, nextPlan))
                }}
                disabled={generating}
                className="mt-2 w-full rounded-lg border border-gray-300 px-4 py-2 text-gray-900 focus:border-transparent focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              >
                <option value="sip">定投</option>
                <option value="lump_sum">一次性配置</option>
              </select>
            </label>
            <label className="block text-sm font-medium text-gray-700">
              {purchasePlan === 'sip' ? '每月定投金额' : '计划配置金额'}
              <input
                type="number"
                min="1"
                step="100"
                value={plannedAmount}
                onChange={(event) => setPlannedAmount(event.target.value)}
                onBlur={() => setPlannedAmount((value) => normalizePlannedAmountInput(value, purchasePlan))}
                disabled={generating}
                className="mt-2 w-full rounded-lg border border-gray-300 px-4 py-2 text-gray-900 focus:border-transparent focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
            </label>
          </div>

          <div className="rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">
            研究口径：{purchasePlan === 'sip' ? '每月定投' : '一次性配置'} ¥{currentPlannedAmount().toLocaleString('zh-CN')}。生成报告会按该金额复核起购/定投起点/限购和销售规则硬门禁。
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="includeReports"
              checked={includeReports}
              onChange={(e) => setIncludeReports(e.target.checked)}
              disabled={generating}
              className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
            />
            <label htmlFor="includeReports" className="ml-2 text-sm text-gray-700">
              包含调研报告（如果有）
            </label>
          </div>

          <button
            onClick={handleGenerate}
            disabled={!fundId.trim() || generating}
            className="w-full flex items-center justify-center px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {generating ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                生成中...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 mr-2" />
                生成研究备忘录
              </>
            )}
          </button>
        </div>
      </div>

      {/* 状态提示 */}
      {status && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm text-blue-800">{status}</p>
        </div>
      )}

      {/* 生成的内容 */}
      {content && (
        <div className="bg-white rounded-lg shadow p-6 space-y-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">研究备忘录</h2>
            {reportId && (
              <Link
                href={`/reports/${reportId}`}
                className="text-sm text-blue-600 hover:text-blue-800"
              >
              查看完整报告
              </Link>
            )}
          </div>
          <ReportActionBar
            targetType="fund"
            targetId={fundId}
            content={content}
            reportId={reportId}
            purchasePlan={purchasePlan}
            plannedAmount={currentPlannedAmount()}
            returnTo={currentAnalysisReturnHref}
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
