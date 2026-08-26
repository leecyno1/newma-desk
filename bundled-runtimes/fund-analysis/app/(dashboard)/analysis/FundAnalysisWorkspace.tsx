'use client'

import Link from 'next/link'
import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  BarChart3,
  BookOpenText,
  CheckCircle2,
  Clock3,
  FileText,
  GitCompareArrows,
  LoaderCircle,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Tags,
} from 'lucide-react'

type FundOption = {
  windCode: string
  name: string
  type: string
  managers?: Array<{ name?: string }>
}

type AnalysisHistory = {
  id: string
  reportType: string
  targetId: string
  content: string
  metadata?: Record<string, unknown>
  createdAt: string
}

type AnalysisResult = {
  id?: string | null
  report: string
  metadata?: Record<string, unknown>
  timeline?: AnalysisTimeline | null
}

type AnalysisRevision = {
  id: string
  revision: number
  is_current: boolean
  created_at: string
  mode: string
  mode_label: string
  provider?: string | null
  model?: string | null
  question?: string
  change_summary: string
}

type AnalysisTimeline = {
  current_revision: number
  total_revisions: number
  revisions: AnalysisRevision[]
}

type LlmHealth = {
  status: 'ready' | 'degraded' | 'unconfigured'
  configured: boolean
  provider?: string
  model?: string
  retry_after_seconds?: number
}

type EvidenceSnapshot = {
  assessment_summary?: {
    status?: string
    verdict?: string
    peer_group?: string
    score?: number | null
    grade?: string
    peer_rank?: number | null
    peer_count?: number | null
    style_evidence?: { status?: string; labels?: string[]; memo_labels?: string[]; scope?: string; quarter?: string }
    attribution_evidence?: { status?: string; headline?: string; detail?: string; quarter?: string; coverage?: number | null; formal_barra_ready?: boolean; barra_descriptor_ready?: boolean }
    research_evidence?: { status?: string; count?: number; fund_specific_count?: number; manager_level_count?: number; latest_title?: string; latest_date?: string; note?: string }
  }
  research_memos?: { count?: number; fund_specific_count?: number; manager_level_count?: number }
  attribution?: { status?: string; quarter?: string; evidence_origin?: { label?: string; mode?: string } }
}

function formatDate(value?: string | null) {
  if (!value) return '时间待补'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function analysisModeLabel(metadata?: Record<string, unknown>) {
  return metadata?.mode === 'llm_evaluation_evidence' ? '模型综合评价' : '本地证据评价'
}

function attributionEvidenceLabel(metadata?: Record<string, unknown>) {
  const quarter = typeof metadata?.attribution_quarter === 'string' ? metadata.attribution_quarter : ''
  if (metadata?.attribution_evidence_mode === 'saved_history') return `归因：${quarter || '当前季度'} 已保存结果`
  if (metadata?.attribution_evidence_mode === 'live_calculation') return `归因：${quarter || '当前季度'} 现场计算`
  if (metadata?.attribution_evidence_mode === 'timed_out') return `归因：${quarter || '当前季度'} 现场计算超时，本次未采用`
  if (metadata?.attribution_evidence_mode === 'not_run') return `归因：${quarter || '当前季度'} 本次未运行`
  return ''
}

function memoEvidenceLabel(metadata?: Record<string, unknown>) {
  const fundCount = Number(metadata?.fund_specific_research_count || 0)
  const managerCount = Number(metadata?.manager_level_research_count || 0)
  if (fundCount > 0 && managerCount > 0) return `纪要：基金 ${fundCount} · 经理 ${managerCount}`
  if (fundCount > 0) return `纪要：基金专属 ${fundCount}`
  if (managerCount > 0) return `纪要：经理层 ${managerCount}`
  return ''
}

function managerTenureEvidenceLabel(metadata?: Record<string, unknown>) {
  const status = typeof metadata?.manager_tenure_coverage_status === 'string' ? metadata.manager_tenure_coverage_status : ''
  const coverage = Number(metadata?.manager_tenure_coverage_ratio)
  if (status === 'full_tenure') return '经理任期：完整覆盖'
  if (status === 'partial_since_data_start') {
    return `经理任期：本地覆盖${Number.isFinite(coverage) ? ` ${Math.round(coverage * 100)}%` : ''} · 不排名`
  }
  return ''
}

function multiPeriodEvidenceMeta(metadata?: Record<string, unknown>) {
  const status = typeof metadata?.multi_period_status === 'string' ? metadata.multi_period_status : ''
  const consistency = typeof metadata?.multi_period_consistency_label === 'string'
    ? metadata.multi_period_consistency_label
    : ''
  if (status === 'long_term_ready') {
    return {
      label: `长期证据：近 3 年完整${consistency ? ` · ${consistency}` : ''}`,
      className: 'bg-[#e4f0e9] text-[#24624c]',
    }
  }
  if (status === 'short_term_only') {
    return { label: '长期证据：近 3 年不足', className: 'bg-[#fff0d4] text-[#7b581c]' }
  }
  return null
}

function numberOrNull(value: unknown) {
  const parsed = Number(value)
  return value === null || value === undefined || value === '' || !Number.isFinite(parsed) ? null : parsed
}

function stringList(value: unknown) {
  return Array.isArray(value) ? value.map(String).map((item) => item.trim()).filter(Boolean) : []
}

function evidenceFromMetadata(metadata?: Record<string, unknown> | null): EvidenceSnapshot | null {
  if (!metadata) return null
  const styleLabels = stringList(metadata.style_labels)
  const memoLabels = stringList(metadata.memo_style_labels)
  const score = numberOrNull(metadata.evaluation_score)
  const rank = numberOrNull(metadata.peer_rank)
  const peerCount = numberOrNull(metadata.peer_count)
  const fundCount = numberOrNull(metadata.fund_specific_research_count) || 0
  const managerCount = numberOrNull(metadata.manager_level_research_count) || 0
  return {
    assessment_summary: {
      status: String(metadata.evaluation_status || ''),
      verdict: String(metadata.evaluation_verdict || ''),
      peer_group: String(metadata.peer_group || ''),
      score,
      grade: String(metadata.evaluation_grade || ''),
      peer_rank: rank,
      peer_count: peerCount,
      style_evidence: {
        status: String(metadata.style_evidence_status || ''),
        scope: String(metadata.style_evidence_scope || ''),
        quarter: String(metadata.style_evidence_quarter || ''),
        labels: styleLabels,
        memo_labels: memoLabels,
      },
      attribution_evidence: {
        status: String(metadata.attribution_evidence_status || metadata.attribution_status || ''),
        headline: String(metadata.attribution_evidence_headline || ''),
        detail: String(metadata.attribution_evidence_detail || ''),
        quarter: String(metadata.attribution_quarter || ''),
        coverage: numberOrNull(metadata.attribution_disclosure_coverage),
        formal_barra_ready: metadata.formal_barra_ready === true,
        barra_descriptor_ready: metadata.barra_descriptor_ready === true,
      },
      research_evidence: {
        status: String(metadata.research_evidence_status || ''),
        count: fundCount + managerCount,
        fund_specific_count: fundCount,
        manager_level_count: managerCount,
        note: String(metadata.research_evidence_note || ''),
      },
    },
  }
}

function statusLabel(status?: string) {
  if (status === 'ok' || status === 'available' || status === 'complete') return '证据完整'
  if (status === 'partial' || status === 'partial_evidence') return '部分可用'
  if (status === 'manager_level') return '仅经理层'
  if (status === 'peer_percentile_ready' || status === 'quantitative') return '量化持仓'
  if (status === 'not_requested' || status === 'not_run') return '未运行'
  return status ? '证据不足' : '待读取'
}

function EvidenceSummary({ snapshot, loading, title }: { snapshot: EvidenceSnapshot | null; loading?: boolean; title: string }) {
  if (loading) return <div className="mt-4 flex items-center gap-2 border-t border-[#dfe4df] pt-4 text-xs text-[#6f7b74]"><LoaderCircle className="h-4 w-4 animate-spin text-[#28745c]" />正在读取评价、归因和纪要证据</div>
  if (!snapshot) return null
  const assessment = snapshot.assessment_summary || {}
  const style = assessment.style_evidence || {}
  const attribution = assessment.attribution_evidence || {}
  const research = assessment.research_evidence || {}
  const fundMemos = Number(research.fund_specific_count ?? snapshot.research_memos?.fund_specific_count ?? 0)
  const managerMemos = Number(research.manager_level_count ?? snapshot.research_memos?.manager_level_count ?? 0)
  const labels = [...(style.labels || []), ...(style.memo_labels || [])].filter((label, index, all) => all.indexOf(label) === index)
  const coverage = numberOrNull(attribution.coverage)
  return (
    <section className="mt-4 border-t border-[#dfe4df] pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-xs font-bold text-[#25342c]">{title}</h3><span className="text-[10px] text-[#859089]">现场数据 · 不采用模拟结论</span></div>
      <div className="mt-3 grid gap-px overflow-hidden border border-[#dfe4df] bg-[#dfe4df] sm:grid-cols-2 xl:grid-cols-4">
        <div className="min-w-0 bg-[#fafbf9] p-3"><div className="flex items-center justify-between gap-2 text-[10px] text-[#738078]"><span>分类评价</span><BarChart3 className="h-3.5 w-3.5" /></div><strong className="mt-2 block truncate text-sm text-[#1f3028]">{assessment.peer_group || '同类组待确认'}</strong><p className="mt-1 text-[11px] text-[#647169]">{assessment.score != null ? `${Number(assessment.score).toFixed(1)} 分 · ${assessment.grade || '无等级'}` : statusLabel(assessment.status)}{assessment.peer_rank && assessment.peer_count ? ` · ${assessment.peer_rank}/${assessment.peer_count}` : ''}</p></div>
        <div className="min-w-0 bg-[#fafbf9] p-3"><div className="flex items-center justify-between gap-2 text-[10px] text-[#738078]"><span>风格证据</span><Tags className="h-3.5 w-3.5" /></div><strong className="mt-2 block text-sm text-[#1f3028]">{statusLabel(style.status)}</strong><p className="mt-1 line-clamp-2 text-[11px] text-[#647169]">{labels.length ? labels.join(' · ') : '暂无可核验风格标签'}{style.quarter ? ` · ${style.quarter}` : ''}</p></div>
        <div className="min-w-0 bg-[#fafbf9] p-3"><div className="flex items-center justify-between gap-2 text-[10px] text-[#738078]"><span>Barra / Brinson</span><ShieldCheck className="h-3.5 w-3.5" /></div><strong className="mt-2 block text-sm text-[#1f3028]">{attribution.headline || statusLabel(attribution.status)}</strong><p className="mt-1 line-clamp-2 text-[11px] text-[#647169]">{attribution.quarter || snapshot.attribution?.quarter || '季度待确认'}{coverage != null ? ` · 披露覆盖 ${(coverage * 100).toFixed(1)}%` : ''}{attribution.formal_barra_ready ? ' · 正式 Barra' : attribution.barra_descriptor_ready ? ' · 风格描述子' : ''}</p></div>
        <div className="min-w-0 bg-[#fafbf9] p-3"><div className="flex items-center justify-between gap-2 text-[10px] text-[#738078]"><span>调研纪要</span><BookOpenText className="h-3.5 w-3.5" /></div><strong className="mt-2 block text-sm text-[#1f3028]">基金 {fundMemos} · 经理 {managerMemos}</strong><p className="mt-1 line-clamp-2 text-[11px] text-[#647169]">{research.latest_title || research.note || (managerMemos ? '经理层纪要不外推为本基金持仓' : '暂无相关纪要')}</p></div>
      </div>
      {assessment.verdict ? <p className="mt-3 text-xs leading-5 text-[#59675f]">{assessment.verdict}</p> : null}
      {attribution.detail ? <p className="mt-1 text-[11px] leading-5 text-[#7a672f]">归因边界：{attribution.detail}</p> : null}
    </section>
  )
}

function historyFundName(item: AnalysisHistory) {
  const name = typeof item.metadata?.fund_name === 'string' ? item.metadata.fund_name.trim() : ''
  return name || item.targetId
}

function historyPeerGroup(item: AnalysisHistory) {
  return typeof item.metadata?.peer_group === 'string' ? item.metadata.peer_group.trim() : ''
}

function healthCopy(health: LlmHealth | null) {
  if (!health) return { label: '模型状态读取中', detail: '分析仍可使用本地证据评价。', tone: 'text-[#65716b]' }
  if (health.status === 'ready') return { label: 'AI 模型已配置', detail: `${health.provider || '模型服务'} · ${health.model || '默认模型'}`, tone: 'text-[#28745c]' }
  if (health.status === 'degraded') return { label: 'AI 暂时降级', detail: health.retry_after_seconds ? `约 ${health.retry_after_seconds} 秒后恢复尝试，本次自动使用本地证据。` : '本次自动使用本地证据评价。', tone: 'text-[#9a681d]' }
  return { label: 'AI 模型未配置', detail: '仍可运行本地证据评价，不会生成模拟结论。', tone: 'text-[#65716b]' }
}

function ReportBody({ content }: { content: string }) {
  const lines = content.split('\n')
  return (
    <div className="space-y-2 text-sm leading-8 text-[#303d36]">
      {lines.map((rawLine, index) => {
        const line = rawLine.trim()
        if (!line) return <div key={index} className="h-2" />
        if (line.startsWith('# ')) return <h2 key={index} className="pt-2 text-2xl font-bold leading-tight text-[#18231e]">{line.slice(2)}</h2>
        if (line.startsWith('## ')) return <h3 key={index} className="border-b border-[#dfe4df] pb-2 pt-5 text-lg font-bold text-[#18231e]">{line.slice(3)}</h3>
        if (line.startsWith('### ')) return <h4 key={index} className="pt-3 font-bold text-[#1d2923]">{line.slice(4)}</h4>
        if (line.startsWith('- ')) return <div key={index} className="flex gap-2"><span className="mt-3 h-1.5 w-1.5 shrink-0 rounded-full bg-[#28745c]" /><span>{line.slice(2)}</span></div>
        if (line.startsWith('|')) return <div key={index} className="overflow-x-auto whitespace-pre font-mono text-xs text-[#526159]">{line}</div>
        if (line === '```json' || line === '```') return null
        return <p key={index}>{line}</p>
      })}
    </div>
  )
}

export default function FundAnalysisWorkspace({ initialFund = null }: { initialFund?: FundOption | null }) {
  const [query, setQuery] = useState(initialFund ? `${initialFund.name} ${initialFund.windCode}` : '')
  const [funds, setFunds] = useState<FundOption[]>([])
  const [fundLoading, setFundLoading] = useState(false)
  const [selectedFund, setSelectedFund] = useState<FundOption | null>(initialFund)
  const [question, setQuestion] = useState('')
  const [running, setRunning] = useState(false)
  const [progressStep, setProgressStep] = useState(0)
  const [error, setError] = useState('')
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [history, setHistory] = useState<AnalysisHistory[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [llmHealth, setLlmHealth] = useState<LlmHealth | null>(null)
  const [evidenceSnapshot, setEvidenceSnapshot] = useState<EvidenceSnapshot | null>(null)
  const [evidenceLoading, setEvidenceLoading] = useState(Boolean(initialFund))

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const response = await fetch('/api/analysis?targetType=fund&reportType=fund_evaluation_analysis&limit=20', { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      setHistory(response.ok && Array.isArray(payload.data) ? payload.data : [])
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  const loadLlmHealth = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch('/api/analysis/health', { cache: 'no-store', signal })
      const payload = await response.json().catch(() => ({}))
      setLlmHealth(payload as LlmHealth)
    } catch (healthError) {
      if (healthError instanceof DOMException && healthError.name === 'AbortError') return
      setLlmHealth({ status: 'degraded', configured: false })
    }
  }, [])

  useEffect(() => {
    const timer = globalThis.setTimeout(() => void loadHistory(), 0)
    return () => globalThis.clearTimeout(timer)
  }, [loadHistory])

  useEffect(() => {
    const controller = new AbortController()
    const timer = globalThis.setTimeout(() => void loadLlmHealth(controller.signal), 0)
    return () => {
      globalThis.clearTimeout(timer)
      controller.abort()
    }
  }, [loadLlmHealth])

  useEffect(() => {
    if (query.trim().length < 2 || selectedFund) {
      const timer = globalThis.setTimeout(() => {
        setFunds([])
        setFundLoading(false)
      }, 0)
      return () => globalThis.clearTimeout(timer)
    }
    const timer = globalThis.setTimeout(async () => {
      setFundLoading(true)
      try {
        const params = new URLSearchParams({ search: query.trim(), limit: '10' })
        const response = await fetch(`/api/fund-browser?${params.toString()}`, { cache: 'no-store' })
        const payload = await response.json().catch(() => ({}))
        setFunds(response.ok && Array.isArray(payload.data) ? payload.data : [])
      } finally {
        setFundLoading(false)
      }
    }, 300)
    return () => globalThis.clearTimeout(timer)
  }, [query, selectedFund])

  useEffect(() => {
    if (!selectedFund?.windCode) return
    const controller = new AbortController()
    const params = new URLSearchParams({ window: '1y', include_research: 'true', include_attribution: 'true', live_attribution: 'false' })
    const timer = globalThis.setTimeout(() => {
      fetch(`/api/funds/${encodeURIComponent(selectedFund.windCode)}/research-snapshot?${params.toString()}`, { cache: 'no-store', signal: controller.signal })
        .then(async (response) => {
          const payload = await response.json().catch(() => ({}))
          if (!response.ok) throw new Error(payload.error || '证据快照不可用')
          setEvidenceSnapshot(payload as EvidenceSnapshot)
        })
        .catch((snapshotError) => {
          if (snapshotError instanceof DOMException && snapshotError.name === 'AbortError') return
          setEvidenceSnapshot(null)
        })
        .finally(() => { if (!controller.signal.aborted) setEvidenceLoading(false) })
    }, 0)
    return () => {
      globalThis.clearTimeout(timer)
      controller.abort()
    }
  }, [selectedFund?.windCode])

  const progressLabels = ['读取基金与分类', '计算同类评价', '读取风险与归因', '检索调研纪要', '形成综合评价']

  async function runAnalysis(event: FormEvent) {
    event.preventDefault()
    if (!selectedFund) {
      setError('请先选择一只基金')
      return
    }
    setRunning(true)
    setProgressStep(0)
    setError('')
    setResult(null)
    const progressTimer = globalThis.setInterval(() => setProgressStep((step) => Math.min(progressLabels.length - 1, step + 1)), 1800)
    try {
      const response = await fetch('/api/analysis/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ windCode: selectedFund.windCode, question }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(typeof payload.error === 'string' ? payload.error : '分析失败')
      setResult(payload)
      setProgressStep(progressLabels.length - 1)
      await loadHistory()
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : '分析失败')
    } finally {
      globalThis.clearInterval(progressTimer)
      setRunning(false)
      void loadLlmHealth()
    }
  }

  async function openHistoryReport(reportId: string, fallbackTargetId = '') {
    setError('')
    try {
      const response = await fetch(`/api/analysis/${encodeURIComponent(reportId)}`, { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '无法读取分析历史')
      setResult({ id: payload.id, report: payload.content, metadata: payload.metadata, timeline: payload.timeline })
      const targetId = payload.targetId || fallbackTargetId
      setSelectedFund({ windCode: targetId, name: targetId, type: '' })
      setQuery(targetId)
      setEvidenceSnapshot(null)
      setEvidenceLoading(true)
      globalThis.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (historyError) {
      setError(historyError instanceof Error ? historyError.message : '无法读取分析历史')
    }
  }

  async function openHistory(item: AnalysisHistory) {
    await openHistoryReport(item.id, item.targetId)
  }

  const selectedManager = useMemo(() => selectedFund?.managers?.map((manager) => manager.name).filter(Boolean).join('、') || '', [selectedFund])
  const modelHealthCopy = healthCopy(llmHealth)
  const resultMultiPeriodEvidence = multiPeriodEvidenceMeta(result?.metadata)

  return (
    <div className="space-y-7">
      <section className="grid gap-7 border-b border-[#dce1dc] pb-8 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-end">
        <div>
          <Link href={selectedFund ? `/analysis/advanced?fundCode=${encodeURIComponent(selectedFund.windCode)}` : '/analysis/advanced'} className="inline-flex items-center gap-2 text-xs font-bold text-[#28745c]">单独查看 Barra / Brinson 业绩归因<ArrowRight className="h-4 w-4" /></Link>
          <div className={`mt-3 text-xs ${modelHealthCopy.tone}`}><strong>{modelHealthCopy.label}</strong><span className="ml-2">{modelHealthCopy.detail}</span></div>
        </div>
        <div className="grid grid-cols-3 gap-px overflow-hidden border border-[#dbe1dc] bg-[#dbe1dc] text-center text-xs">
          <div className="bg-white p-3"><BarChart3 className="mx-auto h-4 w-4 text-[#28745c]" /><span className="mt-2 block">同类评价</span></div>
          <div className="bg-white p-3"><ShieldCheck className="mx-auto h-4 w-4 text-[#28745c]" /><span className="mt-2 block">归因证据</span></div>
          <div className="bg-white p-3"><BookOpenText className="mx-auto h-4 w-4 text-[#28745c]" /><span className="mt-2 block">调研纪要</span></div>
        </div>
      </section>

      <section className="grid gap-7 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-5">
          <form onSubmit={runAnalysis} className="border border-[#dbe1dc] bg-white p-5 sm:p-6">
            <label className="block text-sm font-bold">选择基金</label>
            <div className="relative mt-3">
              <Search className="pointer-events-none absolute left-4 top-3.5 h-5 w-5 text-[#7d8882]" />
              <input value={query} onChange={(event) => { setQuery(event.target.value); setSelectedFund(null); setEvidenceSnapshot(null); setEvidenceLoading(false) }} placeholder="输入基金名称或代码" className="h-12 w-full rounded-md border border-[#cfd6d0] bg-white pl-12 pr-4 text-sm outline-none focus:border-[#28745c]" />
              {fundLoading ? <LoaderCircle className="absolute right-4 top-4 h-4 w-4 animate-spin text-[#28745c]" /> : null}
              {funds.length ? (
                <div className="absolute inset-x-0 top-14 z-20 max-h-72 overflow-y-auto border border-[#cfd6d0] bg-white shadow-xl">
                  {funds.map((fund) => (
                    <button key={fund.windCode} type="button" onClick={() => { setSelectedFund(fund); setQuery(`${fund.name} ${fund.windCode}`); setFunds([]); setEvidenceSnapshot(null); setEvidenceLoading(true) }} className="flex w-full items-center justify-between gap-4 border-b border-[#edf0ed] px-4 py-3 text-left text-sm hover:bg-[#f2f6f3]">
                      <span className="min-w-0"><strong className="block truncate">{fund.name || fund.windCode}</strong><small className="mt-1 block text-[#7a8580]">{fund.windCode} · {fund.type || '类别待确认'}</small></span>
                      <ArrowRight className="h-4 w-4 shrink-0 text-[#849088]" />
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            {selectedFund ? (
              <div className="mt-3 rounded-md bg-[#edf4f0] px-4 py-3">
                <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-[#315e4d]"><span className="font-bold">{selectedFund.name}</span><span>{selectedFund.windCode}</span><span>{selectedFund.type || '类别待确认'}</span>{selectedManager ? <span>{selectedManager}</span> : null}</div>
                <EvidenceSummary snapshot={evidenceSnapshot} loading={evidenceLoading} title="本次分析将使用的证据" />
              </div>
            ) : null}

            <label className="mt-5 block text-sm font-bold" htmlFor="analysis-question">你最关心什么 <span className="font-normal text-[#7a8580]">（可选）</span></label>
            <textarea id="analysis-question" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={1000} rows={3} placeholder="例如：这只基金的超额收益主要来自哪里？风格是否稳定？" className="mt-3 w-full resize-y rounded-md border border-[#cfd6d0] bg-white px-4 py-3 text-sm leading-6 outline-none focus:border-[#28745c]" />

            <button type="submit" disabled={!selectedFund || running} className="mt-4 inline-flex h-11 items-center gap-2 rounded-md bg-[#173f35] px-5 text-sm font-bold text-white hover:bg-[#225747] disabled:cursor-not-allowed disabled:opacity-50">
              {running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}{running ? '正在分析' : '开始分析'}
            </button>
          </form>

          {error ? <div className="border border-[#e5c98f] bg-[#fff8e8] px-5 py-4 text-sm text-[#78551c]">{error}</div> : null}

          {running ? (
            <div className="border border-[#dbe1dc] bg-white p-6">
              <div className="flex items-center gap-3"><LoaderCircle className="h-5 w-5 animate-spin text-[#28745c]" /><strong className="text-sm">{progressLabels[progressStep]}</strong></div>
              <div className="mt-5 grid grid-cols-5 gap-2">
                {progressLabels.map((label, index) => <div key={label}><div className={`h-1.5 ${index <= progressStep ? 'bg-[#28745c]' : 'bg-[#dfe4df]'}`} /><span className="mt-2 hidden text-[10px] leading-4 text-[#7a8580] sm:block">{label}</span></div>)}
              </div>
            </div>
          ) : null}

          {result ? (
            <article className="border border-[#dbe1dc] bg-white">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#dfe4df] px-5 py-4 sm:px-7">
                <div className="flex flex-wrap items-center gap-2 text-xs font-bold text-[#28745c]"><Sparkles className="h-4 w-4" />{analysisModeLabel(result.metadata)}{resultMultiPeriodEvidence ? <span className={`rounded-sm px-2 py-1 text-[10px] ${resultMultiPeriodEvidence.className}`}>{resultMultiPeriodEvidence.label}</span> : null}{attributionEvidenceLabel(result.metadata) ? <span className="rounded-sm bg-[#edf4f0] px-2 py-1 text-[10px] text-[#47685a]">{attributionEvidenceLabel(result.metadata)}</span> : null}{managerTenureEvidenceLabel(result.metadata) ? <span className="rounded-sm bg-[#eef1f7] px-2 py-1 text-[10px] text-[#56627a]">{managerTenureEvidenceLabel(result.metadata)}</span> : null}{memoEvidenceLabel(result.metadata) ? <span className="rounded-sm bg-[#f2f0e7] px-2 py-1 text-[10px] text-[#756532]">{memoEvidenceLabel(result.metadata)}</span> : null}</div>
                {result.id ? <span className="text-xs text-[#7a8580]">已保存到分析历史</span> : null}
              </div>
              <div className="px-5 sm:px-7"><EvidenceSummary snapshot={evidenceFromMetadata(result.metadata)} title="本次分析实际使用的证据" /></div>
              <div className="px-5 py-6 sm:px-7 sm:py-8"><ReportBody content={result.report} /></div>
              {result.timeline?.revisions?.length ? (
                <div className="border-t border-[#dfe4df] px-5 py-5 sm:px-7">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="flex items-center gap-2 text-sm font-bold"><Clock3 className="h-4 w-4 text-[#28745c]" />分析版本</h3>
                    <span className="text-xs text-[#7a8580]">当前 V{result.timeline.current_revision} / 共 {result.timeline.total_revisions} 版</span>
                  </div>
                  <div className="mt-4 divide-y divide-[#e5e9e6] border-y border-[#e5e9e6]">
                    {result.timeline.revisions.map((revision) => (
                      <button key={revision.id} type="button" onClick={() => void openHistoryReport(revision.id)} disabled={revision.is_current} className="grid w-full gap-1 py-3 text-left disabled:cursor-default sm:grid-cols-[5rem_minmax(0,1fr)_10rem] sm:items-center">
                        <strong className={revision.is_current ? 'text-[#28745c]' : 'text-[#36443d]'}>V{revision.revision}{revision.is_current ? ' · 当前' : ''}</strong>
                        <span className="text-xs leading-5 text-[#5f6c65]">{revision.change_summary}</span>
                        <span className="text-xs text-[#929b96] sm:text-right">{formatDate(revision.created_at)}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </article>
          ) : null}
        </div>

        <aside className="min-w-0">
          <div className="flex items-center justify-between border-b border-[#dbe1dc] pb-3">
            <h2 className="flex items-center gap-2 text-sm font-bold"><Clock3 className="h-4 w-4 text-[#28745c]" />分析历史</h2>
            <span className="text-xs text-[#7a8580]">{history.length}</span>
          </div>
          {historyLoading ? <div className="flex items-center gap-2 py-5 text-xs text-[#7a8580]"><LoaderCircle className="h-4 w-4 animate-spin" />读取中</div> : null}
          <div className="divide-y divide-[#e0e5e1]">
            {history.map((item) => (
              <button key={item.id} type="button" onClick={() => void openHistory(item)} className="block w-full py-4 text-left hover:text-[#28745c]">
                <div className="flex items-center justify-between gap-3"><strong className="truncate text-sm">{historyFundName(item)}</strong><FileText className="h-4 w-4 shrink-0 text-[#849088]" /></div>
                <p className="mt-1 text-[11px] text-[#929b96]">{item.targetId}{historyPeerGroup(item) ? ` · ${historyPeerGroup(item)}` : ''}</p>
                <p className="mt-2 line-clamp-2 text-xs leading-5 text-[#6c7871]">{item.content || '基金评价分析'}</p>
                <span className="mt-2 block text-[11px] text-[#929b96]">{formatDate(item.createdAt)}</span>
              </button>
            ))}
          </div>
          {!historyLoading && !history.length ? <p className="py-5 text-xs leading-6 text-[#7a8580]">完成第一次分析后，记录会保存在这里。</p> : null}
          <Link href="/discover" className="mt-5 flex items-center justify-between border border-[#dbe1dc] bg-white px-4 py-3 text-sm font-bold text-[#315e4d] hover:border-[#90ad9f]">
            <span className="inline-flex items-center gap-2"><GitCompareArrows className="h-4 w-4" />选择同类基金比较</span><ArrowRight className="h-4 w-4" />
          </Link>
        </aside>
      </section>

      <section className="grid gap-3 border-t border-[#dce1dc] pt-6 sm:grid-cols-3">
        <div className="flex gap-3 text-xs leading-6 text-[#65716b]"><CheckCircle2 className="mt-1 h-4 w-4 shrink-0 text-[#28745c]" /><span>评分只来自分类专属方法，不由 AI 即兴设计。</span></div>
        <div className="flex gap-3 text-xs leading-6 text-[#65716b]"><CheckCircle2 className="mt-1 h-4 w-4 shrink-0 text-[#28745c]" /><span>Barra 和 Brinson 类证据只解释收益与风险来源。</span></div>
        <div className="flex gap-3 text-xs leading-6 text-[#65716b]"><CheckCircle2 className="mt-1 h-4 w-4 shrink-0 text-[#28745c]" /><span>数据不足时明示缺口，不使用模拟数据补结论。</span></div>
      </section>
    </div>
  )
}
