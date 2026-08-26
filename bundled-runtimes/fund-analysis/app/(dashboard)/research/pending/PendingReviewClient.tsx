'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  AlertCircle,
  CheckCircle2,
  Filter,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  XCircle,
} from 'lucide-react'

type ProposalKind = 'manager' | 'fund' | 'classification' | 'style_label' | 'tag' | 'other'

type PendingProposal = {
  id: string
  kind: ProposalKind
  value?: string
  candidate_id?: string
  confidence?: number
  extraction_source?: string
  source_ref?: Record<string, unknown>
  identity_verification?: { status?: string }
  report_id: string
  report_title?: string
  report_date?: string
  report_date_source?: string
  report_date_precision?: string
  review_status?: string
}

type PendingPayload = {
  total: number
  data: PendingProposal[]
}

const KIND_LABEL: Record<ProposalKind, string> = {
  manager: '经理身份',
  fund: '基金归属',
  classification: '分类',
  style_label: '风格标签',
  tag: '标签',
  other: '其他',
}

const KIND_COLOR: Record<ProposalKind, string> = {
  manager: 'bg-[#e3ecf8] text-[#274c74]',
  fund: 'bg-[#e8efe8] text-[#2b5a3f]',
  classification: 'bg-[#efe8f4] text-[#5a3a6f]',
  style_label: 'bg-[#faedd4] text-[#7c5a1a]',
  tag: 'bg-[#f2f0e5] text-[#5f5a35]',
  other: 'bg-[#ececec] text-[#565656]',
}

const TABS: Array<{ key: 'all' | ProposalKind; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'manager', label: KIND_LABEL.manager },
  { key: 'fund', label: KIND_LABEL.fund },
  { key: 'classification', label: KIND_LABEL.classification },
  { key: 'style_label', label: KIND_LABEL.style_label },
  { key: 'tag', label: KIND_LABEL.tag },
]

function formatConfidence(value?: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—'
  return `${Math.round(value * 100)}%`
}

function formatDate(iso?: string, precision?: string) {
  if (!iso) return '日期待确认'
  const s = iso.slice(0, 10)
  if (precision === 'quarter') {
    const month = Number(s.slice(5, 7))
    return `${s.slice(0, 4)} Q${Math.floor((month - 1) / 3) + 1}`
  }
  if (precision === 'month') return `${s.slice(0, 7)} 月`
  return s
}

export default function PendingReviewClient() {
  const [items, setItems] = useState<PendingProposal[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'all' | ProposalKind>('all')
  const [minConfidence, setMinConfidence] = useState<number>(0.88)
  const [busy, setBusy] = useState<string | null>(null)
  const [bulkResult, setBulkResult] = useState<string>('')

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true)
    else setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/research/pending', { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '加载待确认队列失败')
      const data = (payload as PendingPayload).data || []
      // sort by confidence desc, then by kind
      data.sort((a, b) => (b.confidence || 0) - (a.confidence || 0))
      setItems(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载待确认队列失败')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const counts = useMemo(() => {
    const acc: Record<string, number> = { all: items.length }
    for (const item of items) {
      const k = item.kind || 'other'
      acc[k] = (acc[k] || 0) + 1
    }
    return acc
  }, [items])

  const visible = useMemo(() => {
    if (activeTab === 'all') return items
    return items.filter((item) => item.kind === activeTab)
  }, [items, activeTab])

  const review = useCallback(async (item: PendingProposal, action: 'confirmed' | 'rejected') => {
    const key = `${item.report_id}:${item.id}`
    setBusy(key)
    setError('')
    try {
      const response = await fetch(`/api/research/pending/${encodeURIComponent(item.report_id)}/${encodeURIComponent(item.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '复核失败')
      // remove item from local list
      setItems((current) => current.filter((row) => !(row.report_id === item.report_id && row.id === item.id)))
    } catch (err) {
      setError(err instanceof Error ? err.message : '复核失败')
    } finally {
      setBusy(null)
    }
  }, [])

  const bulkConfirm = useCallback(async (kind: 'managers' | 'labels') => {
    setBusy(`bulk:${kind}`)
    setError('')
    setBulkResult('')
    try {
      const response = await fetch(`/api/research/pending/bulk/${kind}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ min_confidence: minConfidence }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '批量确认失败')
      const label = kind === 'managers' ? '经理身份' : '标签 / 分类 / 风格'
      setBulkResult(
        `批量确认 ${label}：确认 ${payload.confirmed ?? 0}，涉及基金 ${payload.linked_fund_count ?? 0}，失败 ${payload.failed ?? 0}。`
      )
      await load(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : '批量确认失败')
    } finally {
      setBusy(null)
    }
  }, [minConfidence, load])

  return (
    <div className="space-y-6">
      <section className="border border-[#d9dfda] bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-bold text-[#28624e]">
            <Sparkles className="h-4 w-4" />
            批量确认
          </div>
          <button
            type="button"
            onClick={() => void load(true)}
            disabled={refreshing}
            className="inline-flex items-center gap-1 border border-[#c8d0ca] px-3 py-1.5 text-xs text-[#4a5a52] hover:border-[#28745c] disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto_auto]">
          <label className="text-xs text-[#4a5a52]">
            置信度门槛：<strong className="text-[#1f5d3f]">{Math.round(minConfidence * 100)}%</strong>
            <input
              type="range"
              min={0.5}
              max={0.99}
              step={0.01}
              value={minConfidence}
              onChange={(event) => setMinConfidence(Number(event.target.value))}
              className="mt-2 w-full"
            />
            <span className="text-[10px] text-[#8b978f]">
              经理默认 ≥88%，标签默认 ≥90%；LLM 建议永远走单条人工复核。
            </span>
          </label>
          <button
            type="button"
            onClick={() => void bulkConfirm('managers')}
            disabled={busy !== null}
            className="h-11 self-end bg-[#173f35] px-4 text-sm font-bold text-white disabled:opacity-40"
          >
            确认高置信度经理
          </button>
          <button
            type="button"
            onClick={() => void bulkConfirm('labels')}
            disabled={busy !== null}
            className="h-11 self-end border border-[#173f35] px-4 text-sm font-bold text-[#173f35] disabled:opacity-40"
          >
            确认高置信度标签
          </button>
        </div>
        {bulkResult ? (
          <div className="mt-3 flex items-start gap-2 border border-[#c8dcc9] bg-[#f2f8f3] px-3 py-2 text-xs text-[#22503a]">
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5" />
            {bulkResult}
          </div>
        ) : null}
        {error ? (
          <div className="mt-3 flex items-start gap-2 border border-[#e4c2b8] bg-[#fdeee7] px-3 py-2 text-xs text-[#7d3225]">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5" />
            {error}
          </div>
        ) : null}
      </section>

      <section className="border border-[#d9dfda] bg-white">
        <div className="flex items-center gap-3 border-b border-[#e6ebe6] px-5 py-3 text-xs text-[#4a5a52]">
          <Filter className="h-3.5 w-3.5" />
          按类型筛选：
          <div className="flex flex-wrap gap-1.5">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={`border px-2.5 py-1 text-xs transition ${
                  activeTab === tab.key
                    ? 'border-[#28624e] bg-[#28624e] text-white'
                    : 'border-[#c8d0ca] bg-white text-[#4a5a52] hover:border-[#28624e]'
                }`}
              >
                {tab.label} <span className="ml-1 opacity-70">{counts[tab.key] || 0}</span>
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="grid place-items-center px-5 py-14 text-sm text-[#66736c]">
            <span className="flex items-center gap-2"><LoaderCircle className="h-4 w-4 animate-spin" />正在加载待确认队列</span>
          </div>
        ) : visible.length === 0 ? (
          <div className="grid place-items-center px-5 py-14 text-sm text-[#66736c]">
            <CheckCircle2 className="mb-2 h-6 w-6 text-[#4c7b62]" />
            <div>当前分类下没有待确认项，很棒。</div>
          </div>
        ) : (
          <ul className="divide-y divide-[#eef2ee]">
            {visible.map((item) => {
              const key = `${item.report_id}:${item.id}`
              const kind = (item.kind || 'other') as ProposalKind
              const chipColor = KIND_COLOR[kind] || KIND_COLOR.other
              const isLlm = item.extraction_source === 'llm'
              return (
                <li key={key} className="grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,1fr)_auto]">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className={`inline-flex items-center px-2 py-0.5 ${chipColor}`}>
                        {KIND_LABEL[kind] || kind}
                      </span>
                      <span className="text-[#748079]">置信度 <strong className="text-[#1f5d3f]">{formatConfidence(item.confidence)}</strong></span>
                      <span className="text-[#748079]">来源：{item.extraction_source || '未标注'}</span>
                      {isLlm ? (
                        <span className="inline-flex items-center gap-1 bg-[#fdeee7] px-1.5 py-0.5 text-[10px] text-[#8f2f21]">
                          <AlertCircle className="h-3 w-3" />LLM 建议：只能单条人工复核
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-2 text-sm font-bold text-[#1f2d26]">
                      {item.value || '未识别值'}
                    </div>
                    <Link
                      href={`/research?report_id=${encodeURIComponent(item.report_id)}`}
                      className="mt-1 block truncate text-xs text-[#28745c] hover:underline"
                    >
                      {item.report_title || item.report_id} · {formatDate(item.report_date, item.report_date_precision)}
                    </Link>
                  </div>
                  <div className="flex items-center justify-end gap-2 self-center">
                    <button
                      type="button"
                      onClick={() => void review(item, 'confirmed')}
                      disabled={busy === key}
                      className="inline-flex items-center gap-1 bg-[#28624e] px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      确认
                    </button>
                    <button
                      type="button"
                      onClick={() => void review(item, 'rejected')}
                      disabled={busy === key}
                      className="inline-flex items-center gap-1 border border-[#c88b83] px-3 py-1.5 text-xs font-bold text-[#8f2f21] disabled:opacity-50"
                    >
                      <XCircle className="h-3.5 w-3.5" />
                      驳回
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}
