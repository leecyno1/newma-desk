'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { LoaderCircle, Sparkles } from 'lucide-react'
import { backendApiBaseUrl } from '@/lib/backend-api'

/** 基金详情页的 AI 评价分析报告生成入口（本地证据 + LLM 叙述增强，生成后跳转报告详情） */
export default function GenerateFundReportButton({ windCode }: { windCode: string }) {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generate = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(
        `${backendApiBaseUrl}/api/reports/fund/${encodeURIComponent(windCode)}/evaluation-analysis`,
        { method: 'POST' },
      )
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || '生成失败')
      const reportId = payload.report_id || payload.id
      if (reportId) {
        router.push(`/reports/${reportId}`)
      } else {
        setError('报告已生成但未返回编号，请在报告列表中查看')
      }
    } catch (exc) {
      setError(`AI 报告生成失败: ${exc instanceof Error ? exc.message : String(exc)}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={generate}
        disabled={loading}
        className="inline-flex items-center gap-2 bg-[#173f35] px-4 py-2 text-xs font-bold text-white hover:bg-[#28624e] disabled:opacity-60"
      >
        {loading ? (
          <>
            <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
            AI 分析生成中（约 15 秒）…
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            生成 AI 分析报告
          </>
        )}
      </button>
      {error ? <span className="text-[11px] text-[#a05a52]">{error}</span> : null}
      <span className="text-[10px] text-[#8d9a92]">同类分位证据 + 叙述分析，研究输出不构成投资建议</span>
    </div>
  )
}
