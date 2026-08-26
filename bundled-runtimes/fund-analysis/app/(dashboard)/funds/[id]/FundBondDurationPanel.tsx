'use client'

import { useState } from 'react'
import { CircleAlert, ExternalLink, Gauge, RefreshCw } from 'lucide-react'

export type FundBondDurationWeight = {
  seriesKey: string
  groupLabel: string
  periodLabel: string
  weight: number
  indexDuration: number
  durationContribution: number
}

export type FundBondDurationSnapshot = {
  windCode: string
  status: string
  asOfDate: string
  dataStart: string
  dataEnd: string
  windowWeeks: number
  observations: number
  estimatedDuration: number | null
  durationBucket: string
  rSquared: number | null
  trackingError: number | null
  fitLabel: string
  formalDurationReady: boolean
  weights: FundBondDurationWeight[]
  missingItems: string[]
  limitations: string[]
  sourceUrl: string
}

function formatDate(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

function formatDuration(value: number | null) {
  return value == null ? '待测算' : `${value.toFixed(2)} 年`
}

function normalizeSnapshot(payload: Record<string, unknown>): FundBondDurationSnapshot {
  const numberOrNull = (value: unknown) => {
    const parsed = Number(value)
    return value == null || value === '' || !Number.isFinite(parsed) ? null : parsed
  }
  const weights = (Array.isArray(payload.weights) ? payload.weights : []).map((value) => {
    const row = value && typeof value === 'object' ? value as Record<string, unknown> : {}
    return {
      seriesKey: String(row.series_key || ''),
      groupLabel: String(row.group_label || ''),
      periodLabel: String(row.period_label || ''),
      weight: Number(row.weight || 0),
      indexDuration: Number(row.index_duration || 0),
      durationContribution: Number(row.duration_contribution || 0),
    }
  })
  return {
    windCode: String(payload.wind_code || ''),
    status: String(payload.status || 'unavailable'),
    asOfDate: String(payload.as_of_date || ''),
    dataStart: String(payload.data_start || ''),
    dataEnd: String(payload.data_end || ''),
    windowWeeks: Number(payload.window_weeks || 104),
    observations: Number(payload.observations || 0),
    estimatedDuration: numberOrNull(payload.estimated_duration),
    durationBucket: String(payload.duration_bucket || ''),
    rSquared: numberOrNull(payload.r_squared),
    trackingError: numberOrNull(payload.tracking_error),
    fitLabel: String(payload.fit_label || '尚未测算'),
    formalDurationReady: Boolean(payload.formal_duration_ready),
    weights,
    missingItems: Array.isArray(payload.missing_items) ? payload.missing_items.map(String) : [],
    limitations: Array.isArray(payload.limitations) ? payload.limitations.map(String) : [],
    sourceUrl: String(payload.source_url || ''),
  }
}

export default function FundBondDurationPanel({ initialSnapshot, fundType, windCode }: { initialSnapshot: FundBondDurationSnapshot; fundType: string; windCode: string }) {
  const [snapshot, setSnapshot] = useState(initialSnapshot)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const isBondFund = fundType.includes('债') || fundType.toLowerCase().includes('bond')

  if (!isBondFund) return null

  async function calculate() {
    setRunning(true)
    setError('')
    try {
      const response = await fetch(`/api/funds/${encodeURIComponent(windCode)}/bond-duration?window_weeks=${snapshot.windowWeeks || 104}`, { method: 'POST' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '久期测算失败')
      setSnapshot(normalizeSnapshot(payload))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '久期测算失败')
    } finally {
      setRunning(false)
    }
  }

  const hasResult = snapshot.estimatedDuration != null
  const weakEvidence = snapshot.status === 'low_fit'

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><Gauge className="h-5 w-5 text-[#28745c]" />净值回归久期</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">用基金周收益和 20 条真实中债分期限指数现场估算，只解释利率敏感度，不参与基金评分。</p>
        </div>
        <div className="flex items-center gap-3">
          {snapshot.sourceUrl ? <a href={snapshot.sourceUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-bold text-[#28745c]">中债来源<ExternalLink className="h-3.5 w-3.5" /></a> : null}
          <button type="button" onClick={calculate} disabled={running} className="inline-flex h-10 items-center gap-2 rounded-md bg-[#173f35] px-4 text-xs font-bold text-white disabled:cursor-wait disabled:opacity-60">
            <RefreshCw className={`h-3.5 w-3.5 ${running ? 'animate-spin' : ''}`} />{running ? '正在测算' : hasResult ? '重新测算' : '现场测算久期'}
          </button>
        </div>
      </div>

      {error ? <div className="flex gap-3 border-b border-[#ead0cb] bg-[#fff4f2] px-5 py-4 text-xs text-[#8a433b]"><CircleAlert className="h-4 w-4 shrink-0" />{error}</div> : null}

      {hasResult ? (
        <>
          <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-2 xl:grid-cols-4">
            {[
              ['估算久期', formatDuration(snapshot.estimatedDuration)],
              ['久期区间', snapshot.durationBucket || '—'],
              ['回归拟合度', snapshot.rSquared == null ? '—' : `${(snapshot.rSquared * 100).toFixed(1)}%`],
              ['有效样本', `${snapshot.observations} 周`],
            ].map(([label, value]) => <div key={label} className="bg-white p-5"><div className="text-xs font-bold text-[#66726c]">{label}</div><div className="mt-2 text-xl font-bold text-[#1d2923]">{value}</div></div>)}
          </div>

          <div className="grid border-t border-[#e1e6e2] lg:grid-cols-[minmax(0,1.35fr)_minmax(260px,0.65fr)]">
            <div className="p-5 sm:p-6 lg:border-r lg:border-[#e1e6e2]">
              <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-bold text-[#26342d]">四类债券指数权重</h3><span className="text-[10px] text-[#87918c]">截至 {formatDate(snapshot.asOfDate)}</span></div>
              <div className="mt-5 space-y-4">
                {snapshot.weights.map((row) => (
                  <div key={row.seriesKey}>
                    <div className="flex items-center justify-between gap-4 text-xs"><span className="font-medium text-[#4f5d56]">{row.groupLabel} · {row.periodLabel}</span><strong>{(row.weight * 100).toFixed(1)}%</strong></div>
                    <div className="mt-2 h-1.5 overflow-hidden bg-[#e8ece9]"><div className="h-full bg-[#3a8068]" style={{ width: `${Math.max(0, Math.min(100, row.weight * 100))}%` }} /></div>
                    <div className="mt-1 text-[10px] text-[#8b958f]">指数久期 {row.indexDuration.toFixed(2)} 年 · 贡献 {row.durationContribution.toFixed(2)} 年</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-[#f8faf8] p-5 sm:p-6">
              <span className={`inline-flex px-2.5 py-1 text-[11px] font-bold ${weakEvidence ? 'bg-[#fff0d2] text-[#7b5719]' : 'bg-[#e1eee7] text-[#246149]'}`}>{snapshot.fitLabel}</span>
              <p className="mt-4 text-xs leading-6 text-[#59675f]">{weakEvidence ? '拟合较弱，当前久期只能作为辅助线索，不能当作基金正式披露久期。' : '拟合度通过门槛，可作为理解基金利率敏感度的量化证据。'}</p>
              <p className="mt-3 text-[11px] leading-6 text-[#7c8781]">样本区间 {formatDate(snapshot.dataStart)}—{formatDate(snapshot.dataEnd)}。可转债、股票、杠杆和信用利差变化会进入回归残差。</p>
            </div>
          </div>
        </>
      ) : (
        <div className="flex gap-3 px-5 py-7 text-sm text-[#65716b] sm:px-6">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-[#8d6a2f]" />
          <div><strong>{snapshot.status === 'insufficient_evidence' ? '净值样本不足' : '尚未测算久期'}</strong><p className="mt-1 text-xs leading-6">{snapshot.missingItems[0] || '点击“现场测算久期”后运行，不会批量占用资源。'}</p></div>
        </div>
      )}
    </section>
  )
}
