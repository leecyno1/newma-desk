'use client'

import { useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { RefreshCw } from 'lucide-react'
import { useFundPageData } from '@/lib/newma-desk/page-data'

type NavResult = {
  latest_nav_date: string
  observations: number
  adjusted_observations: number
  metrics_recalculated: boolean
}

export default function RefreshFundNavButton({ windCode }: { windCode: string }) {
  const router = useRouter()
  const pending = useRef(false)
  const [status, setStatus] = useState<'idle' | 'updating' | 'saved' | 'error'>('idle')
  const [result, setResult] = useState<NavResult | null>(null)
  const [message, setMessage] = useState('')
  useFundPageData(useMemo(() => ({
    selection: { symbol: windCode, assetType: 'fund' as const },
    filters: {},
    summary: { status, fundCode: windCode, result, message, scope: '近30天净值；评价指标未重算，久期可另行重算' },
    visibleBlocks: [{ id: 'fund-nav-refresh', type: 'action', title: '净值更新' }],
  }), [windCode, status, result, message]), 'nav-refresh')

  async function refresh() {
    if (pending.current) return
    pending.current = true
    setStatus('updating')
    setResult(null)
    setMessage('')
    try {
      const response = await fetch(`/api/funds/${encodeURIComponent(windCode)}/nav-refresh`, { method: 'POST' })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '净值更新失败，请重试。')
      setResult(data)
      setStatus('saved')
      setMessage(`已更新至 ${data.latest_nav_date} · ${data.observations} 条净值，${data.adjusted_observations} 条有复权值。评价指标未重算，久期可另行重算。`)
      router.refresh()
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error && !(error instanceof TypeError) ? error.message : '暂未收到更新结果，请刷新页面核对净值日期。')
    } finally {
      pending.current = false
    }
  }

  return <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
    <button type="button" disabled={status === 'updating'} onClick={refresh} className="inline-flex h-8 items-center gap-1.5 rounded border border-[#cfd6d0] px-2.5 font-medium text-[#28745c] disabled:opacity-60">
      <RefreshCw aria-hidden="true" className={`h-3.5 w-3.5 ${status === 'updating' ? 'animate-spin' : ''}`} />{status === 'updating' ? '正在更新净值' : '更新净值'}
    </button>
    <span role="status" className={status === 'error' ? 'text-[#a04f45]' : 'text-[#7a8580]'}>{message || '从官方源更新近30天净值'}</span>
  </div>
}
