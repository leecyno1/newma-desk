'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, BookMarked, CheckCircle2, Eye, LoaderCircle, Plus, RefreshCw } from 'lucide-react'

type Thesis = {
  id: string
  fund_wind_code: string
  title: string
  state: string
  one_liner?: string
  core_reasoning: Array<{ point?: string; weight?: string }>
  sell_triggers: Array<{ condition?: string; type?: string }>
  next_review_date?: string
  created_at?: string
  updated_at?: string
}

type Payload = {
  data: Thesis[]
  total: number
  counts_by_state: Record<string, number>
}

const STATE_LABEL: Record<string, string> = {
  candidate: '候选中',
  researching: '研究中',
  observing: '观察中',
  invalid: '已失效',
  archived: '已归档',
}

const STATE_COLOR: Record<string, string> = {
  candidate: 'bg-[#e8efe8] text-[#2b5a3f]',
  researching: 'bg-[#e3ecf8] text-[#274c74]',
  observing: 'bg-[#faedd4] text-[#7c5a1a]',
  invalid: 'bg-[#fde7e2] text-[#8f2f21]',
  archived: 'bg-[#ececec] text-[#565656]',
}

const TABS: Array<{ key: string; label: string }> = [
  { key: 'active', label: '活跃' },
  { key: 'candidate', label: '候选中' },
  { key: 'researching', label: '研究中' },
  { key: 'observing', label: '观察中' },
  { key: 'closed', label: '已关闭' },
]

export default function ThesesClient() {
  const [theses, setTheses] = useState<Thesis[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('active')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      if (tab === 'active') {
        // no state filter, default excludes closed
      } else if (tab === 'closed') {
        params.set('include_closed', 'true')
        params.set('state', 'invalid')
      } else {
        params.set('state', tab)
      }
      const response = await fetch(`/api/theses?${params.toString()}`, { cache: 'no-store' })
      const payload = await response.json().catch(() => ({})) as Payload
      if (!response.ok) throw new Error(payload && 'detail' in payload ? String((payload as unknown as { detail: string }).detail) : '加载失败')
      setTheses(payload.data || [])
      setCounts(payload.counts_by_state || {})
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [tab])

  useEffect(() => { void load() }, [load])

  const activeCount = (counts.candidate || 0) + (counts.researching || 0) + (counts.observing || 0)

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-end">
        <div className="flex gap-2">
          <button type="button" onClick={() => void load()} className="inline-flex items-center gap-1 border border-[#c8d0ca] px-3 py-1.5 text-xs hover:border-[#28745c]">
            <RefreshCw className="h-3.5 w-3.5" />刷新
          </button>
          <Link href="/theses/new" className="inline-flex items-center gap-1 bg-[#173f35] px-3 py-1.5 text-xs font-bold text-white">
            <Plus className="h-3.5 w-3.5" />新建论点
          </Link>
        </div>
      </header>

      <nav className="flex items-center gap-1 border-b border-[#eaedea] text-xs">
        {TABS.map((t) => {
          const count = t.key === 'active' ? activeCount : t.key === 'closed' ? (counts.invalid || 0) + (counts.archived || 0) : counts[t.key] || 0
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`border-b-2 px-3 py-2 font-medium transition ${tab === t.key ? 'border-[#28745c] text-[#1f2d26]' : 'border-transparent text-[#748079] hover:text-[#3d5347]'}`}
            >
              {t.label} <span className="ml-1 opacity-60">{count}</span>
            </button>
          )
        })}
      </nav>

      {error ? <div className="flex items-center gap-2 border border-[#e4c78e] bg-[#fef9ee] px-3 py-2 text-xs text-[#78571f]"><AlertCircle className="h-3.5 w-3.5" />{error}</div> : null}

      {loading ? (
        <div className="grid place-items-center py-12 text-xs text-[#748079]"><LoaderCircle className="h-4 w-4 animate-spin" /></div>
      ) : theses.length === 0 ? (
        <div className="border border-dashed border-[#cbd3cd] px-6 py-12 text-center text-xs text-[#748079]">
          <BookMarked className="mx-auto h-5 w-5 text-[#a3ada7]" />
          <p className="mt-3">当前无投资论点。从基金详情或候选基金页面进入，记录研究结论。</p>
        </div>
      ) : (
        <div className="divide-y divide-[#eef1ee] border border-[#d9dfda] bg-white">
          {theses.map((thesis) => (
            <Link key={thesis.id} href={`/funds/${encodeURIComponent(thesis.fund_wind_code)}`} className="flex items-start gap-4 px-4 py-3 hover:bg-[#f7faf8]">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className={`inline-block px-1.5 py-0.5 text-[10px] font-bold ${STATE_COLOR[thesis.state] || STATE_COLOR.candidate}`}>
                    {STATE_LABEL[thesis.state] || thesis.state}
                  </span>
                  <span className="truncate text-xs font-bold text-[#1f2d26]">{thesis.title}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-[#748079]">
                  <span>{thesis.fund_wind_code}</span>
                  {thesis.one_liner ? <span className="text-[#4a5a52]">— {thesis.one_liner}</span> : null}
                </div>
                {thesis.core_reasoning.length ? (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {thesis.core_reasoning.slice(0, 3).map((r, i) => (
                      <span key={i} className="inline-flex items-center gap-1 bg-[#f0f3f0] px-1.5 py-0.5 text-[10px] text-[#3d5347]">
                        <CheckCircle2 className="h-2.5 w-2.5" />{r.point || '—'}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
              <div className="shrink-0 text-right text-[10px] text-[#8b978f]">
                {thesis.next_review_date ? <div>复查 {thesis.next_review_date}</div> : null}
                {thesis.sell_triggers.length ? <div className="mt-1 flex items-center gap-1"><Eye className="h-2.5 w-2.5" />{thesis.sell_triggers.length} 触发条件</div> : null}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
