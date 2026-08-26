'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  BookMarked,
  Eye,
  FlaskConical,
  ListChecks,
  LoaderCircle,
  RefreshCw,
  ScanSearch,
} from 'lucide-react'

type Tab = 'queue' | 'theses' | 'watches' | 'anomalies' | 'postmortems'

const TABS: Array<{ key: Tab; label: string; icon: typeof ListChecks }> = [
  { key: 'queue', label: '研究队列', icon: ListChecks },
  { key: 'theses', label: '投资论点', icon: BookMarked },
  { key: 'watches', label: '观察项', icon: Eye },
  { key: 'anomalies', label: '异常筛查', icon: ScanSearch },
  { key: 'postmortems', label: '决策复盘', icon: FlaskConical },
]

export default function WorkbenchClient() {
  const [tab, setTab] = useState<Tab>('queue')

  return (
    <div className="space-y-4">
      <nav className="flex items-center gap-1 overflow-x-auto border-b border-[#eaedea] text-xs">
        {TABS.map((t) => {
          const Icon = t.icon
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 font-medium transition ${tab === t.key ? 'border-[#28745c] text-[#1f2d26]' : 'border-transparent text-[#748079] hover:text-[#3d5347]'}`}
            >
              <Icon className="h-3.5 w-3.5" />
              {t.label}
            </button>
          )
        })}
      </nav>

      {tab === 'queue' && <QueuePanel />}
      {tab === 'theses' && <ThesesPanel />}
      {tab === 'watches' && <WatchesPanel />}
      {tab === 'anomalies' && <AnomaliesPanel />}
      {tab === 'postmortems' && <PostmortemsPanel />}
    </div>
  )
}

// ─────────────── 研究队列 ───────────────

type QueueItem = {
  id: string
  fund_wind_code: string
  fund_name?: string
  status: string
  priority: number
  source?: string
  next_review_date?: string
  output_committed: boolean
  thesis_id?: string
  conclusion?: string
  notes?: string
}

const QUEUE_STATUS_LABEL: Record<string, string> = {
  queued: '排队中',
  researching: '研究中',
  concluded: '已结论',
  dropped: '已放弃',
}

const QUEUE_STATUS_COLOR: Record<string, string> = {
  queued: 'bg-[#eef1ee] text-[#5b6a63]',
  researching: 'bg-[#e3ecf8] text-[#274c74]',
  concluded: 'bg-[#e6f2ec] text-[#1f5d3f]',
  dropped: 'bg-[#ececec] text-[#565656]',
}

function QueuePanel() {
  const [items, setItems] = useState<QueueItem[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [newCode, setNewCode] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/research-queue', { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || '加载研究队列失败')
      setItems(payload.data || [])
      setCounts(payload.counts_by_status || {})
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const transition = useCallback(async (id: string, status: string) => {
    await fetch(`/api/research-queue/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    })
    await load()
  }, [load])

  const addItem = useCallback(async () => {
    const code = newCode.trim().toUpperCase()
    if (!code) return
    const response = await fetch('/api/research-queue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fund_wind_code: code, source: 'manual' }),
    })
    if (response.ok) {
      setNewCode('')
      await load()
    }
  }, [newCode, load])

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-2 text-[11px] text-[#748079]">
          {Object.entries(QUEUE_STATUS_LABEL).map(([key, label]) => (
            <span key={key}>{label} <strong className="text-[#28745c]">{counts[key] || 0}</strong></span>
          ))}
        </div>
        <form
          className="flex gap-2"
          onSubmit={(event) => { event.preventDefault(); void addItem() }}
        >
          <input
            value={newCode}
            onChange={(event) => setNewCode(event.target.value)}
            placeholder="基金代码 如 000031.OF"
            className="h-8 w-44 border border-[#cfd6d0] px-2 text-xs outline-none focus:border-[#28745c]"
          />
          <button type="submit" className="h-8 bg-[#173f35] px-3 text-xs font-bold text-white">加入队列</button>
        </form>
      </div>

      {error ? <ErrorNote text={error} /> : null}
      {loading ? <LoadingNote /> : items.length === 0 ? (
        <EmptyNote text="研究队列为空。把候选基金加入队列，承诺产出论点或结论。" />
      ) : (
        <div className="divide-y divide-[#eef1ee] border border-[#d9dfda] bg-white">
          {items.map((item) => (
            <div key={item.id} className="flex items-center gap-3 px-4 py-2.5">
              <span className={`inline-block px-1.5 py-0.5 text-[10px] font-bold ${QUEUE_STATUS_COLOR[item.status] || QUEUE_STATUS_COLOR.queued}`}>
                {QUEUE_STATUS_LABEL[item.status] || item.status}
              </span>
              <span className="text-[10px] text-[#8b978f]">P{item.priority}</span>
              <Link href={`/funds/${encodeURIComponent(item.fund_wind_code)}`} className="min-w-0 flex-1 truncate text-xs font-medium text-[#1f2d26] hover:text-[#28745c]">
                {item.fund_name || item.fund_wind_code}
                <span className="ml-2 text-[10px] font-normal text-[#8b978f]">{item.fund_wind_code}</span>
              </Link>
              {item.output_committed ? <span className="text-[10px] text-[#1f5d3f]">✓ 已承诺产出</span> : null}
              {item.next_review_date ? <span className="text-[10px] text-[#8b978f]">复查 {item.next_review_date}</span> : null}
              <div className="flex gap-1">
                {item.status === 'queued' ? (
                  <button type="button" onClick={() => void transition(item.id, 'researching')} className="border border-[#c8d0ca] px-2 py-1 text-[10px] hover:border-[#28745c]">开始研究</button>
                ) : null}
                {item.status === 'researching' ? (
                  <button type="button" onClick={() => void transition(item.id, 'concluded')} className="border border-[#c8d0ca] px-2 py-1 text-[10px] hover:border-[#28745c]">标记结论</button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

// ─────────────── 投资论点 ───────────────

type Thesis = {
  id: string
  fund_wind_code: string
  title: string
  state: string
  one_liner?: string
  core_reasoning: Array<{ point?: string }>
  next_review_date?: string
}

const THESIS_STATE_LABEL: Record<string, string> = {
  candidate: '候选中',
  researching: '研究中',
  observing: '观察中',
  invalid: '已失效',
  archived: '已归档',
}

const THESIS_STATE_COLOR: Record<string, string> = {
  candidate: 'bg-[#e8efe8] text-[#2b5a3f]',
  researching: 'bg-[#e3ecf8] text-[#274c74]',
  observing: 'bg-[#faedd4] text-[#7c5a1a]',
  invalid: 'bg-[#fde7e2] text-[#8f2f21]',
  archived: 'bg-[#ececec] text-[#565656]',
}

function ThesesPanel() {
  const [theses, setTheses] = useState<Thesis[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/theses', { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || '加载论点失败')
      setTheses(payload.data || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-[#748079]">共 {theses.length} 条论点</span>
        <Link href="/theses" className="text-[11px] font-bold text-[#28745c] hover:underline">打开论点管理页</Link>
      </div>
      {error ? <ErrorNote text={error} /> : null}
      {loading ? <LoadingNote /> : theses.length === 0 ? (
        <EmptyNote text="暂无投资论点。在论点管理页为研究基金建立结构化论点。" />
      ) : (
        <div className="divide-y divide-[#eef1ee] border border-[#d9dfda] bg-white">
          {theses.map((thesis) => (
            <div key={thesis.id} className="flex items-center gap-3 px-4 py-2.5">
              <span className={`inline-block px-1.5 py-0.5 text-[10px] font-bold ${THESIS_STATE_COLOR[thesis.state] || THESIS_STATE_COLOR.candidate}`}>
                {THESIS_STATE_LABEL[thesis.state] || thesis.state}
              </span>
              <Link href={`/funds/${encodeURIComponent(thesis.fund_wind_code)}`} className="min-w-0 flex-1">
                <span className="block truncate text-xs font-medium text-[#1f2d26] hover:text-[#28745c]">{thesis.title}</span>
                {thesis.one_liner ? <span className="block truncate text-[10px] text-[#748079]">{thesis.one_liner}</span> : null}
              </Link>
              <span className="text-[10px] text-[#8b978f]">{thesis.core_reasoning.length} 条逻辑</span>
              {thesis.next_review_date ? <span className="text-[10px] text-[#8b978f]">复查 {thesis.next_review_date}</span> : null}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

// ─────────────── 观察项 ───────────────

type Watch = {
  id: string
  fund_wind_code: string
  metric_field: string
  operator: string
  threshold: number
  note?: string
  status: string
  triggered_value?: number
  triggered_at?: string
}

const WATCH_STATUS_LABEL: Record<string, string> = {
  active: '监控中',
  triggered: '已触发',
  dismissed: '已忽略',
}

function WatchesPanel() {
  const [watches, setWatches] = useState<Watch[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [scanResult, setScanResult] = useState<string>('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/watches', { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || '加载观察项失败')
      setWatches(payload.data || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const scan = useCallback(async () => {
    setScanResult('扫描中…')
    try {
      const response = await fetch('/api/watches/scan', { method: 'POST' })
      const payload = await response.json().catch(() => ({}))
      setScanResult(`扫描完成：${payload.active_watches ?? 0} 个监控项，${payload.triggered_count ?? 0} 个触发`)
      await load()
    } catch {
      setScanResult('扫描失败')
    }
  }, [load])

  const dismiss = useCallback(async (id: string) => {
    await fetch(`/api/watches/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'dismissed' }),
    })
    await load()
  }, [load])

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-[#748079]">共 {watches.length} 个观察项{scanResult ? ` · ${scanResult}` : ''}</span>
        <button type="button" onClick={() => void scan()} className="flex items-center gap-1 border border-[#c8d0ca] px-2 py-1 text-[11px] hover:border-[#28745c]">
          <RefreshCw className="h-3 w-3" />立即扫描
        </button>
      </div>
      {error ? <ErrorNote text={error} /> : null}
      {loading ? <LoadingNote /> : watches.length === 0 ? (
        <EmptyNote text="暂无观察项。可对任意基金的规模、回撤、集中度等指标设置阈值监控。" />
      ) : (
        <div className="divide-y divide-[#eef1ee] border border-[#d9dfda] bg-white">
          {watches.map((watch) => (
            <div key={watch.id} className="flex items-center gap-3 px-4 py-2.5">
              <span className={`inline-block px-1.5 py-0.5 text-[10px] font-bold ${watch.status === 'triggered' ? 'bg-[#fde7e2] text-[#8f2f21]' : watch.status === 'active' ? 'bg-[#e6f2ec] text-[#1f5d3f]' : 'bg-[#ececec] text-[#565656]'}`}>
                {WATCH_STATUS_LABEL[watch.status] || watch.status}
              </span>
              <Link href={`/funds/${encodeURIComponent(watch.fund_wind_code)}`} className="text-xs font-medium text-[#1f2d26] hover:text-[#28745c]">
                {watch.fund_wind_code}
              </Link>
              <span className="min-w-0 flex-1 truncate text-[11px] text-[#4a5a52]">
                {watch.metric_field} {watch.operator} {formatThreshold(watch.metric_field, watch.threshold)}
                {watch.note ? ` · ${watch.note}` : ''}
              </span>
              {watch.triggered_value != null ? <span className="text-[10px] text-[#8f2f21]">当前 {formatThreshold(watch.metric_field, watch.triggered_value)}</span> : null}
              {watch.status === 'triggered' ? (
                <button type="button" onClick={() => void dismiss(watch.id)} className="border border-[#c8d0ca] px-2 py-1 text-[10px] hover:border-[#28745c]">忽略</button>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function formatThreshold(metric: string, value: number) {
  if (metric === 'total_asset') return `${(value / 1e8).toFixed(1)} 亿`
  if (['max_drawdown', 'annualized_return', 'institution_ratio', 'top_ten_weight'].includes(metric)) {
    return `${(value * 100).toFixed(1)}%`
  }
  return String(value)
}

// ─────────────── 异常筛查 ───────────────

type Anomaly = {
  type: string
  wind_code: string
  description: string
  [key: string]: unknown
}

type AnomalyPayload = {
  scan_date: string
  total_anomalies: number
  by_type: Record<string, number>
  anomalies: Record<string, Anomaly[]>
}

const ANOMALY_TYPE_LABEL: Record<string, string> = {
  scale_anomaly: '规模异动',
  drawdown_anomaly: '回撤异常',
  manager_change: '经理变更',
  concentration_change: '集中度突变',
}

function AnomaliesPanel() {
  const [payload, setPayload] = useState<AnomalyPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/anomalies/scan?limit=30', { cache: 'no-store' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || '扫描失败')
      setPayload(data as AnomalyPayload)
    } catch (err) {
      setError(err instanceof Error ? err.message : '扫描失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const allAnomalies = payload
    ? Object.entries(payload.anomalies).flatMap(([type, list]) => list.map((item) => ({ ...item, type })))
    : []

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex gap-3 text-[11px] text-[#748079]">
          {payload ? Object.entries(payload.by_type).map(([type, count]) => (
            <span key={type}>{ANOMALY_TYPE_LABEL[type] || type} <strong className={count > 0 ? 'text-[#8f2f21]' : 'text-[#28745c]'}>{count}</strong></span>
          )) : null}
        </div>
        <button type="button" onClick={() => void load()} className="flex items-center gap-1 border border-[#c8d0ca] px-2 py-1 text-[11px] hover:border-[#28745c]">
          <RefreshCw className="h-3 w-3" />重新扫描
        </button>
      </div>
      {error ? <ErrorNote text={error} /> : null}
      {loading ? <LoadingNote /> : allAnomalies.length === 0 ? (
        <EmptyNote text="当前无异常。异常筛查只覆盖主动基金，不含 ETF/指数。" />
      ) : (
        <div className="divide-y divide-[#eef1ee] border border-[#d9dfda] bg-white">
          {allAnomalies.map((anomaly, index) => (
            <div key={`${anomaly.wind_code}-${index}`} className="flex items-center gap-3 px-4 py-2.5">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-[#c98a2b]" />
              <span className="w-16 shrink-0 text-[10px] font-bold text-[#7c5a1a]">{ANOMALY_TYPE_LABEL[anomaly.type] || anomaly.type}</span>
              <Link href={`/funds/${encodeURIComponent(anomaly.wind_code)}`} className="text-xs font-medium text-[#1f2d26] hover:text-[#28745c]">
                {anomaly.wind_code}
              </Link>
              <span className="min-w-0 flex-1 truncate text-[11px] text-[#4a5a52]">{anomaly.description}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

// ─────────────── 决策复盘 ───────────────

type Postmortem = {
  id: string
  fund_wind_code: string
  fund_name?: string
  thesis_title?: string
  outcome: string
  actual_return_pct?: number
  excess_return_pct?: number
  lesson_learned?: string
  decision_bias?: string
  reviewed_at?: string
}

type PostmortemStats = {
  by_outcome: Record<string, number>
  by_bias: Record<string, number>
  avg_actual_return_pct?: number
  avg_excess_return_pct?: number
}

const OUTCOME_LABEL: Record<string, string> = {
  validated: '论点被证实',
  invalidated: '论点被证伪',
  inconclusive: '无法判断',
}

function PostmortemsPanel() {
  const [postmortems, setPostmortems] = useState<Postmortem[]>([])
  const [stats, setStats] = useState<PostmortemStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [listRes, statsRes] = await Promise.all([
        fetch('/api/postmortems', { cache: 'no-store' }),
        fetch('/api/postmortems/stats', { cache: 'no-store' }),
      ])
      const listPayload = await listRes.json().catch(() => ({}))
      if (!listRes.ok) throw new Error(listPayload.detail || '加载复盘失败')
      setPostmortems(listPayload.data || [])
      if (statsRes.ok) setStats(await statsRes.json().catch(() => null))
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  return (
    <section className="space-y-3">
      {stats ? (
        <div className="grid grid-cols-2 gap-px overflow-hidden border border-[#d4dbd6] bg-[#d4dbd6] sm:grid-cols-4">
          <StatCell label="被证实" value={String(stats.by_outcome.validated || 0)} />
          <StatCell label="被证伪" value={String(stats.by_outcome.invalidated || 0)} />
          <StatCell label="无法判断" value={String(stats.by_outcome.inconclusive || 0)} />
          <StatCell label="平均超额" value={stats.avg_excess_return_pct != null ? `${stats.avg_excess_return_pct.toFixed(1)}%` : '—'} />
        </div>
      ) : null}

      <div className="flex justify-end">
        <button type="button" onClick={() => setShowForm((v) => !v)} className="border border-[#c8d0ca] px-3 py-1.5 text-[11px] font-bold text-[#3d5347] hover:border-[#28745c]">
          {showForm ? '收起' : '+ 新建复盘'}
        </button>
      </div>
      {showForm ? <NewPostmortemForm onDone={() => { setShowForm(false); void load() }} /> : null}

      {error ? <ErrorNote text={error} /> : null}
      {loading ? <LoadingNote /> : postmortems.length === 0 ? (
        <EmptyNote text="暂无决策复盘。论点关闭后系统会要求完成结构化复盘，积累后可识别系统性决策偏差。" />
      ) : (
        <div className="divide-y divide-[#eef1ee] border border-[#d9dfda] bg-white">
          {postmortems.map((pm) => (
            <div key={pm.id} className="flex items-center gap-3 px-4 py-2.5">
              <span className={`inline-block px-1.5 py-0.5 text-[10px] font-bold ${pm.outcome === 'validated' ? 'bg-[#e6f2ec] text-[#1f5d3f]' : pm.outcome === 'invalidated' ? 'bg-[#fde7e2] text-[#8f2f21]' : 'bg-[#ececec] text-[#565656]'}`}>
                {OUTCOME_LABEL[pm.outcome] || pm.outcome}
              </span>
              <Link href={`/funds/${encodeURIComponent(pm.fund_wind_code)}`} className="min-w-0 flex-1">
                <span className="block truncate text-xs font-medium text-[#1f2d26] hover:text-[#28745c]">{pm.thesis_title || pm.fund_name || pm.fund_wind_code}</span>
                {pm.lesson_learned ? <span className="block truncate text-[10px] text-[#748079]">{pm.lesson_learned}</span> : null}
              </Link>
              {pm.excess_return_pct != null ? <span className={`text-[11px] font-bold ${pm.excess_return_pct >= 0 ? 'text-[#1f5d3f]' : 'text-[#8f2f21]'}`}>{pm.excess_return_pct.toFixed(1)}%</span> : null}
              {pm.decision_bias ? <span className="text-[10px] text-[#7c5a1a]">{pm.decision_bias}</span> : null}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function NewPostmortemForm({ onDone }: { onDone: () => void }) {
  const [theses, setTheses] = useState<Array<{ id: string; title: string; fund_wind_code: string }>>([])
  const [thesisId, setThesisId] = useState('')
  const [outcome, setOutcome] = useState('validated')
  const [actual, setActual] = useState('')
  const [peerMedian, setPeerMedian] = useState('')
  const [lesson, setLesson] = useState('')
  const [bias, setBias] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')

  useEffect(() => {
    void (async () => {
      const res = await fetch('/api/theses?include_closed=true', { cache: 'no-store' })
      const payload = await res.json().catch(() => ({}))
      setTheses((payload.data || []).map((t: { id: string; title: string; fund_wind_code: string }) => ({ id: t.id, title: t.title, fund_wind_code: t.fund_wind_code })))
    })()
  }, [])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!thesisId) { setFormError('请选择一个论点'); return }
    setSaving(true)
    setFormError('')
    const excess = actual !== '' && peerMedian !== '' ? Number(actual) - Number(peerMedian) : undefined
    const response = await fetch('/api/postmortems', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        thesis_id: thesisId,
        outcome,
        actual_return_pct: actual !== '' ? Number(actual) : undefined,
        peer_median_return_pct: peerMedian !== '' ? Number(peerMedian) : undefined,
        excess_return_pct: excess,
        lesson_learned: lesson || undefined,
        decision_bias: bias || undefined,
      }),
    })
    setSaving(false)
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      setFormError(payload.detail || '保存失败')
      return
    }
    onDone()
  }

  const inputCls = 'h-8 w-full border border-[#cfd6d0] px-2 text-xs outline-none focus:border-[#28745c]'

  return (
    <form onSubmit={submit} className="grid gap-3 border border-[#d9dfda] bg-white p-4 sm:grid-cols-2">
      <label className="sm:col-span-2 block text-[11px] text-[#4a5a52]">
        关联论点
        <select value={thesisId} onChange={(e) => setThesisId(e.target.value)} className={`${inputCls} mt-1`}>
          <option value="">选择论点…</option>
          {theses.map((t) => <option key={t.id} value={t.id}>{t.title}（{t.fund_wind_code}）</option>)}
        </select>
      </label>
      <label className="block text-[11px] text-[#4a5a52]">
        结果
        <select value={outcome} onChange={(e) => setOutcome(e.target.value)} className={`${inputCls} mt-1`}>
          <option value="validated">论点被证实</option>
          <option value="invalidated">论点被证伪</option>
          <option value="inconclusive">无法判断</option>
        </select>
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label className="block text-[11px] text-[#4a5a52]">实际收益%<input value={actual} onChange={(e) => setActual(e.target.value)} type="number" step="0.1" className={`${inputCls} mt-1`} /></label>
        <label className="block text-[11px] text-[#4a5a52]">同类中位%<input value={peerMedian} onChange={(e) => setPeerMedian(e.target.value)} type="number" step="0.1" className={`${inputCls} mt-1`} /></label>
      </div>
      <label className="block text-[11px] text-[#4a5a52]">教训<input value={lesson} onChange={(e) => setLesson(e.target.value)} className={`${inputCls} mt-1`} placeholder="这次学到了什么" /></label>
      <label className="block text-[11px] text-[#4a5a52]">决策偏差<input value={bias} onChange={(e) => setBias(e.target.value)} className={`${inputCls} mt-1`} placeholder="如：过度依赖近1年收益" /></label>
      {formError ? <div className="sm:col-span-2 text-[11px] text-[#8f2f21]">{formError}</div> : null}
      <div className="sm:col-span-2 flex justify-end">
        <button type="submit" disabled={saving} className="bg-[#173f35] px-4 py-1.5 text-xs font-bold text-white disabled:opacity-50">{saving ? '保存中…' : '保存复盘'}</button>
      </div>
    </form>
  )
}

function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white px-3 py-2 text-center">
      <div className="text-sm font-bold text-[#1f2d26]">{value}</div>
      <div className="text-[10px] text-[#748079]">{label}</div>
    </div>
  )
}

// ─────────────── 通用小组件 ───────────────

function ErrorNote({ text }: { text: string }) {
  return <div className="flex items-center gap-2 border border-[#e4c78e] bg-[#fef9ee] px-3 py-2 text-xs text-[#78571f]"><AlertTriangle className="h-3.5 w-3.5 shrink-0" />{text}</div>
}

function LoadingNote() {
  return <div className="grid place-items-center border border-dashed border-[#cbd3cd] px-4 py-10 text-xs text-[#748079]"><LoaderCircle className="h-4 w-4 animate-spin" /></div>
}

function EmptyNote({ text }: { text: string }) {
  return <div className="border border-dashed border-[#cbd3cd] px-6 py-10 text-center text-xs text-[#748079]">{text}</div>
}
