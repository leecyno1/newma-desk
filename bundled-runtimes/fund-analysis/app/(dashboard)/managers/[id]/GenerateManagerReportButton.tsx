'use client'

import { useContext, useState } from 'react'
import { FundNavigationContext } from '@/lib/newma-desk/page-data'
import { useRouter } from 'next/navigation'
import { LoaderCircle, Sparkles } from 'lucide-react'
import { backendApiBaseUrl } from '@/lib/backend-api'

/** 经理详情页的 AI 分析报告生成入口（研究输出，生成后跳转报告详情） */
export default function GenerateManagerReportButton({ managerId }: { managerId: string }) {
  const router = useRouter()
  const deskNavigation = useContext(FundNavigationContext)
  const [reportHref, setReportHref] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generate = async () => {
    setLoading(true)
    setError('')
    setReportHref('')
    try {
      const response = await fetch(
        `${backendApiBaseUrl}/api/reports/manager/${encodeURIComponent(managerId)}`,
        { method: 'POST' },
      )
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || '生成失败')
      const reportId = payload.id || payload.report_id
      if (reportId) {
        const href = `/reports/${encodeURIComponent(reportId)}`
        if (deskNavigation) setReportHref(href)
        else router.push(href)
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
            AI 分析生成中…
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            生成 AI 分析报告
          </>
        )}
      </button>
      {error ? <span className="text-[11px] text-[#a05a52]">{error}</span> : null}
      {reportHref ? <a href={reportHref} className="text-sm underline">报告已生成，查看报告</a> : null}
      <span className="text-[10px] text-[#8d9a92]">基于任期指标与调研纪要，研究输出不构成投资建议</span>
    </div>
  )
}
