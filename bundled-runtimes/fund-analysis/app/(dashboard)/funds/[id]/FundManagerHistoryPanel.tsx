'use client'

import Link from 'next/link'
import { useState } from 'react'
import { CircleAlert, History, RefreshCw, UsersRound } from 'lucide-react'

export type FundManagerTenure = {
  managerId: string
  managerName: string
  company: string
  startDate: string
  endDate: string
  isCurrent: boolean
  tenureDays: number
  shareCodes: string[]
  sources: string[]
}

export type FundManagerHistorySnapshot = {
  windCode: string
  status: string
  product: {
    canonicalCode: string
    canonicalName: string
    shareCodes: string[]
  }
  summary: {
    managerCount: number
    currentManagerCount: number
    historicalManagerCount: number
    changeEventCount: number
    teamMode: string
    firstTenureStart: string
    recordUpdatedAt: string
  }
  tenures: FundManagerTenure[]
  sources: string[]
  boundary: string
  missingItems: string[]
}

function formatDate(value: string) {
  if (!value) return '—'
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString('zh-CN')
}

function formatDuration(days: number) {
  if (!days) return '时长待补'
  if (days < 365) return `${days} 天`
  return `${(days / 365.25).toFixed(1)} 年`
}

function sourceLabel(source: string) {
  return source === 'tushare.fund_manager' ? 'Tushare 基金经理任职' : source
}

export default function FundManagerHistoryPanel({ snapshot }: { snapshot: FundManagerHistorySnapshot }) {
  const [syncing, setSyncing] = useState(false)
  const [message, setMessage] = useState('')

  async function syncHistory() {
    setSyncing(true)
    setMessage('')
    try {
      const response = await fetch(`/api/funds/${encodeURIComponent(snapshot.windCode)}/manager-history`, { method: 'POST' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '同步失败')
      window.location.reload()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '同步失败')
      setSyncing(false)
    }
  }

  if (snapshot.status !== 'available' || !snapshot.tenures.length) {
    return (
      <section className="border border-[#dfd8c8] bg-[#fffaf0] p-5 sm:p-6">
        <div className="flex gap-3">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-[#8a6a2c]" />
          <div>
            <h2 className="text-base font-bold text-[#433a27]">基金经理历史待补</h2>
            <p className="mt-2 text-xs leading-6 text-[#786744]">{snapshot.missingItems[0] || '本地暂无可核验任职记录，不展示推测结果。'}</p>
            <button type="button" onClick={() => void syncHistory()} disabled={syncing} className="mt-4 inline-flex h-9 items-center gap-2 rounded-md bg-[#765d2c] px-3 text-xs font-bold text-white disabled:opacity-60">
              <RefreshCw className={`h-3.5 w-3.5 ${syncing ? 'animate-spin' : ''}`} />{syncing ? '正在同步' : '同步真实任职'}
            </button>
            {message ? <p className="mt-2 text-[11px] text-[#9a4b3d]">{message}</p> : null}
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><History className="h-5 w-5 text-[#28745c]" />基金经理变动记录</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">同一基金不同份额已合并；任职区间重叠表示多人共管。</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] font-bold">
          <span className="bg-[#e3efe8] px-2.5 py-1 text-[#236149]">现任 {snapshot.summary.currentManagerCount} 人</span>
          <span className="bg-[#f0f2ef] px-2.5 py-1 text-[#59665f]">累计 {snapshot.summary.managerCount} 人</span>
          {snapshot.summary.teamMode === 'co_managed' ? <span className="bg-[#eef1f7] px-2.5 py-1 text-[#56627a]">当前共管</span> : null}
          <button type="button" onClick={() => void syncHistory()} disabled={syncing} className="inline-flex items-center gap-1.5 border border-[#cbd5cf] bg-white px-2.5 py-1 text-[#526159] disabled:opacity-60">
            <RefreshCw className={`h-3 w-3 ${syncing ? 'animate-spin' : ''}`} />{syncing ? '同步中' : '更新数据'}
          </button>
        </div>
      </div>
      {message ? <div className="border-b border-[#ead8d3] bg-[#fff5f2] px-5 py-2 text-[11px] text-[#9a4b3d]">{message}</div> : null}

      <div className="divide-y divide-[#e6eae7]">
        {snapshot.tenures.map((tenure) => (
          <article key={`${tenure.managerId}-${tenure.startDate}`} className="grid gap-3 px-5 py-4 sm:grid-cols-[minmax(10rem,1fr)_minmax(12rem,1.2fr)_auto] sm:items-center sm:px-6">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <Link href={`/managers/${encodeURIComponent(tenure.managerId)}`} className="font-bold text-[#25342c] hover:text-[#28745c]">{tenure.managerName}</Link>
                {tenure.isCurrent ? <span className="bg-[#dcece4] px-2 py-0.5 text-[10px] font-bold text-[#236149]">现任</span> : null}
              </div>
              <div className="mt-1 text-[10px] text-[#8a948f]">{tenure.company || '基金公司以产品档案为准'}</div>
            </div>
            <div>
              <div className="text-xs font-bold text-[#4c5a53]">{formatDate(tenure.startDate)} — {tenure.isCurrent ? '至今' : formatDate(tenure.endDate)}</div>
              <div className="mt-1 text-[10px] text-[#8a948f]">任职 {formatDuration(tenure.tenureDays)} · 覆盖 {tenure.shareCodes.join(' / ')}</div>
            </div>
            <div className="text-left text-[10px] text-[#7c8781] sm:text-right">
              {tenure.sources.map(sourceLabel).join('、') || '本地任职表'}
            </div>
          </article>
        ))}
      </div>

      <div className="grid gap-px border-t border-[#e1e6e2] bg-[#e1e6e2] sm:grid-cols-3">
        <div className="bg-[#f7f9f7] px-5 py-3"><span className="text-[10px] text-[#818b86]">最早记录</span><strong className="mt-1 block text-sm text-[#34423b]">{formatDate(snapshot.summary.firstTenureStart)}</strong></div>
        <div className="bg-[#f7f9f7] px-5 py-3"><span className="text-[10px] text-[#818b86]">经理加入节点</span><strong className="mt-1 block text-sm text-[#34423b]">{snapshot.summary.changeEventCount} 次</strong></div>
        <div className="bg-[#f7f9f7] px-5 py-3"><span className="text-[10px] text-[#818b86]">记录更新</span><strong className="mt-1 block text-sm text-[#34423b]">{formatDate(snapshot.summary.recordUpdatedAt)}</strong></div>
      </div>

      <div className="flex gap-3 border-t border-[#e1e6e2] bg-[#fffaf0] px-5 py-3 text-[11px] leading-5 text-[#765d2c]">
        <UsersRound className="mt-0.5 h-4 w-4 shrink-0" />
        <p>{snapshot.boundary}</p>
      </div>
    </section>
  )
}
