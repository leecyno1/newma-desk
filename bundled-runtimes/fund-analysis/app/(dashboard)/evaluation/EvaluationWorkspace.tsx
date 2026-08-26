'use client'

import Link from 'next/link'
import { useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Gauge,
  LoaderCircle,
  Search,
  ShieldCheck,
} from 'lucide-react'

type FundCandidate = {
  windCode: string
  name: string
  type: string
}

type ScoreItem = {
  score?: number
  weight?: number
  weighted_score?: number
  evidence?: string[]
}

type PeerMetric = {
  label?: string
  value?: number
  percentile?: number
  rank?: number
  peer_count?: number
  sample_status?: string
  unit?: string
}

type CrossMarketMetric = {
  metric?: string
  label?: string
  value?: number
  percentile?: number | null
  position_label?: string
  sample_size?: number
  minimum_peer_count?: number
  unit?: string
}

type BenchmarkComponent = {
  code?: string
  name?: string
  asset?: string
  weight?: number
}

type BenchmarkMapping = {
  confidence?: number
  rationale?: string
  mapping_method?: string
  source?: string
  evidence_refs?: {
    declaredBenchmark?: string
    benchmarkComponents?: BenchmarkComponent[]
  }
}

type EvaluationResult = {
  status: string
  methodology_version?: string
  target?: {
    wind_code?: string
    name?: string
    fund_type?: string
    as_of_date?: string
  }
  classification?: {
    status?: string
    peer_group?: string
    primary_benchmark?: string
    legal_type?: string
    asset_class?: string
    strategy_family_name?: string
    active_passive?: string
    evaluation_profile_key?: string
    confidence?: number
    source?: string
    evidence?: Array<{ field?: string; source?: string; reason?: string }>
    benchmark_mapping?: BenchmarkMapping
  }
  peer_context?: {
    peer_group?: string
    primary_benchmark?: string
    benchmark_mapping?: BenchmarkMapping
    valid_metric_peer_count?: number
    minimum_peer_count?: number
    sample_status?: string
    metric_window?: string
  }
  evaluation?: {
    overall_score?: number | null
    overall_grade?: string
    dimension_scores?: Record<string, ScoreItem>
    peer_percentiles?: Record<string, PeerMetric>
    positive_factors?: string[]
    negative_factors?: string[]
    calculation_method?: string
  }
  methodology?: {
    profile_name?: string
    score_formula?: string
    boundary?: string
  }
  explanatory_evidence?: {
    cross_market_holding?: {
      status?: string
      quarter?: string
      peer_group_name?: string
      profile_peer_count?: number
      minimum_peer_count?: number
      labels?: string[]
      comparisons?: CrossMarketMetric[]
      missing_items?: string[]
      boundary?: string
    }
    holding_stability?: {
      status?: string
      level?: string
      label?: string
      latest_quarter?: string
      previous_quarter?: string
      top10_overlap_ratio?: number
      industry_overlap_ratio?: number
      jaccard_score?: number
      retained_holding_count?: number
      union_holding_count?: number
      boundary?: string
    }
  }
  missing_items?: string[]
}

type HistoryItem = {
  id: string
  wind_code: string
  fund_name?: string
  fund_type?: string
  evaluation_window: string
  as_of_date?: string
  status: string
  overall_score?: number | null
  overall_grade?: string
  peer_group_name?: string
  peer_rank?: number | null
  peer_count?: number | null
  evidence_coverage?: {
    coverage_percent?: number | null
    missing_dimensions?: string[]
  }
  change?: {
    summary?: string
    comparable?: boolean
    score_delta?: number | null
    rank_change?: number | null
    methodology_changed?: boolean
    peer_group_changed?: boolean
  } | null
  created_at: string
}

type AttributionHistoryItem = {
  quarter?: string
  benchmark_id?: string
  status?: string
  active_return?: number | null
  allocation_effect?: number | null
  selection_effect?: number | null
  residual?: number | null
  updated_at?: string
}

type ResearchEvidenceSnapshot = {
  research_memos?: {
    count?: number
    fund_specific_count?: number
    manager_level_count?: number
    items?: Array<{
      id?: string
      title?: string
      report_date?: string
      manager_name?: string
      evidence_scope?: string
    }>
  }
  style_profile?: {
    primary_label?: string | null
    status?: string
    label_evidence?: Array<{
      value?: string
      status?: string
      source?: string
      basis?: string
      caveat?: string
    }>
    manager_memo_style_labels?: string[]
    manager_memo_classifications?: string[]
    memo_style_labels?: string[]
    memo_classifications?: string[]
  }
}

const windows = [
  { key: '6m', label: '近 6 个月', hint: '至少约 183 天净值' },
  { key: '1y', label: '近 1 年', hint: '默认评价窗口' },
  { key: '3y', label: '近 3 年', hint: '至少约 1095 天净值' },
] as const

type WindowKey = typeof windows[number]['key']

const dimensionLabels: Record<string, string> = {
  return: '收益能力',
  risk: '风险控制',
  risk_adjusted: '风险调整后收益',
  consistency: '表现稳定性',
  manager_tenure: '经理任期',
  tracking_quality: '跟踪质量',
  cost_efficiency: '成本效率',
  scale_liquidity: '规模与流动性',
  excess_return: '超额收益',
  active_efficiency: '主动管理效率',
  drawdown_control: '回撤控制',
  income_competitiveness: '收益竞争力',
  capital_preservation: '净值稳定性',
  income_stability: '收益稳定性',
  data_quality: '数据质量',
}

const assetClassLabels: Record<string, string> = {
  equity: '权益',
  bond: '固收',
  mixed: '混合',
  money_market: '货币',
  index: '指数',
  fof: 'FOF',
  qdii: 'QDII',
}

const activePassiveLabels: Record<string, string> = {
  active: '主动管理',
  passive: '被动跟踪',
  enhanced: '指数增强',
}

function numberText(value?: number | null, digits = 1) {
  return value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(digits)
}

function metricText(value?: number, unit?: string) {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  if (unit === 'percent') return `${(Number(value) * 100).toFixed(2)}%`
  if (unit === 'cny_100m') return `${Number(value).toFixed(2)} 亿元`
  return Number(value).toFixed(3)
}

function percentText(value?: number | null) {
  return value == null || !Number.isFinite(Number(value)) ? '—' : `${(Number(value) * 100).toFixed(2)}%`
}

function benchmarkComposition(components?: BenchmarkComponent[]) {
  return (components || [])
    .filter((component) => component.name && Number.isFinite(Number(component.weight)))
    .map((component) => `${component.name} ${Number(component.weight).toFixed(Number(component.weight) % 1 ? 1 : 0)}%`)
    .join(' + ')
}

function statusMeta(status: string) {
  if (status === 'ok') return { label: '评价完成', className: 'border-[#9fc9b8] bg-[#eaf4ef] text-[#225e49]' }
  if (status === 'partial') return { label: '部分完成', className: 'border-[#e3c783] bg-[#fff8e6] text-[#79581d]' }
  return { label: '证据不足', className: 'border-[#dfb6ad] bg-[#fff1ee] text-[#8a4337]' }
}

function HistoryRows({
  items,
  emptyText,
  onOpen,
}: {
  items: HistoryItem[]
  emptyText: string
  onOpen: (item: HistoryItem) => void
}) {
  if (!items.length) return <div className="px-6 py-12 text-center text-sm text-[#78837d]">{emptyText}</div>
  return (
    <div className="divide-y divide-[#e4e8e4]">
      {items.map((item) => {
        const meta = statusMeta(item.status)
        return (
          <button key={item.id} type="button" onClick={() => onOpen(item)} className="grid w-full gap-3 px-5 py-4 text-left hover:bg-[#f5f7f5] sm:grid-cols-[minmax(0,1fr)_7rem_8rem_auto] sm:items-center">
            <span>
              <strong className="block text-sm">{item.fund_name || item.wind_code || item.peer_group_name || '基金评价'}</strong>
              <small className="mt-1 block text-xs text-[#7a857f]">{item.wind_code}{item.peer_group_name ? ` · ${item.peer_group_name}` : ''} · {new Date(item.created_at).toLocaleString('zh-CN', { hour12: false })}</small>
              {item.change?.summary ? <small className={`mt-1 block text-xs leading-5 ${item.change.comparable === false ? 'font-bold text-[#87601f]' : 'text-[#607069]'}`}>{item.change.summary}</small> : null}
            </span>
            <span className="text-xs font-semibold text-[#5e6b64]">{windows.find((window) => window.key === item.evaluation_window)?.label || item.evaluation_window}</span>
            <span><span className="block font-mono text-sm font-bold text-[#245f4b]">{numberText(item.overall_score)}</span>{item.evidence_coverage?.coverage_percent != null ? <small className="mt-1 block text-[10px] text-[#7a857f]">证据 {item.evidence_coverage.coverage_percent.toFixed(0)}%</small> : null}</span>
            <span className={`justify-self-start border px-2 py-1 text-[11px] font-bold sm:justify-self-end ${meta.className}`}>{meta.label}</span>
          </button>
        )
      })}
    </div>
  )
}

export default function EvaluationWorkspace({ initialRecentHistory }: { initialRecentHistory: HistoryItem[] }) {
  const [query, setQuery] = useState('')
  const [candidates, setCandidates] = useState<FundCandidate[]>([])
  const [selectedFund, setSelectedFund] = useState<FundCandidate | null>(null)
  const [windowKey, setWindowKey] = useState<WindowKey>('1y')
  const [result, setResult] = useState<EvaluationResult | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [recentHistory, setRecentHistory] = useState<HistoryItem[]>(initialRecentHistory)
  const [attributionHistory, setAttributionHistory] = useState<AttributionHistoryItem[]>([])
  const [loadingAttribution, setLoadingAttribution] = useState(false)
  const [researchEvidence, setResearchEvidence] = useState<ResearchEvidenceSnapshot | null>(null)
  const [loadingResearch, setLoadingResearch] = useState(false)
  const [searching, setSearching] = useState(false)
  const [running, setRunning] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [error, setError] = useState('')

  async function loadHistory(windCode: string) {
    setLoadingHistory(true)
    try {
      const response = await fetch(`/api/funds/${encodeURIComponent(windCode)}/evaluation-history?limit=30`, { cache: 'no-store' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || '获取评价历史失败')
      setHistory(Array.isArray(payload.items) ? payload.items : [])
    } catch (historyError) {
      setError(historyError instanceof Error ? historyError.message : '获取评价历史失败')
    } finally {
      setLoadingHistory(false)
    }
  }

  async function loadAttributionHistory(windCode: string) {
    setLoadingAttribution(true)
    try {
      const response = await fetch(`/api/attribution/fund/${encodeURIComponent(windCode)}/history?limit=4`, { cache: 'no-store' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || '获取归因历史失败')
      setAttributionHistory(Array.isArray(payload.history) ? payload.history : [])
    } catch {
      setAttributionHistory([])
    } finally {
      setLoadingAttribution(false)
    }
  }

  async function loadResearchEvidence(windCode: string) {
    setLoadingResearch(true)
    try {
      const query = new URLSearchParams({
        window: windowKey,
        include_research: 'true',
        include_attribution: 'false',
        live_attribution: 'false',
      })
      const response = await fetch(`/api/funds/${encodeURIComponent(windCode)}/research-snapshot?${query.toString()}`, { cache: 'no-store' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || '获取调研证据失败')
      setResearchEvidence(payload)
    } catch {
      setResearchEvidence(null)
    } finally {
      setLoadingResearch(false)
    }
  }

  async function loadRecentHistory() {
    const response = await fetch('/api/evaluations/history?limit=30', { cache: 'no-store' })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error || '获取最近评价结果失败')
    setRecentHistory(Array.isArray(payload.items) ? payload.items : [])
  }

  async function searchFunds(event: React.FormEvent) {
    event.preventDefault()
    const keyword = query.trim()
    if (!keyword) return
    setSearching(true)
    setError('')
    try {
      const params = new URLSearchParams({ search: keyword, limit: '8', availability: 'all' })
      const response = await fetch(`/api/fund-browser?${params.toString()}`, { cache: 'no-store' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || '基金查询失败')
      setCandidates(Array.isArray(payload.data) ? payload.data : [])
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : '基金查询失败')
    } finally {
      setSearching(false)
    }
  }

  function selectFund(fund: FundCandidate) {
    setSelectedFund(fund)
    setQuery(`${fund.name} ${fund.windCode}`)
    setCandidates([])
    setResult(null)
    setError('')
    void loadHistory(fund.windCode)
    void loadAttributionHistory(fund.windCode)
    void loadResearchEvidence(fund.windCode)
  }

  async function runEvaluation() {
    if (!selectedFund) return
    setRunning(true)
    setError('')
    try {
      const response = await fetch(
        `/api/funds/${encodeURIComponent(selectedFund.windCode)}/evaluation-history?window=${encodeURIComponent(windowKey)}`,
        { method: 'POST' },
      )
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || '基金评价失败')
      setResult(payload.evaluation || null)
      setHistory(Array.isArray(payload.history?.items) ? payload.history.items : [])
      await loadRecentHistory()
    } catch (evaluationError) {
      setError(evaluationError instanceof Error ? evaluationError.message : '基金评价失败')
    } finally {
      setRunning(false)
    }
  }

  async function openHistory(item: HistoryItem) {
    const windCode = item.wind_code || selectedFund?.windCode
    if (!windCode) return
    setError('')
    try {
      const response = await fetch(
        `/api/funds/${encodeURIComponent(windCode)}/evaluation-history/${encodeURIComponent(item.id)}`,
        { cache: 'no-store' },
      )
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || '读取评价记录失败')
      if (selectedFund?.windCode !== windCode) {
        const fund = { windCode, name: item.fund_name || windCode, type: item.fund_type || '' }
        setSelectedFund(fund)
        setQuery(`${fund.name} ${fund.windCode}`)
        void loadHistory(windCode)
        void loadAttributionHistory(windCode)
        void loadResearchEvidence(windCode)
      }
      setWindowKey(item.evaluation_window as WindowKey)
      setResult(payload.evaluation || null)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (historyError) {
      setError(historyError instanceof Error ? historyError.message : '读取评价记录失败')
    }
  }

  const dimensions = Object.entries(result?.evaluation?.dimension_scores || {})
  const peerMetrics = Object.entries(result?.evaluation?.peer_percentiles || {})
  const crossMarketHolding = result?.explanatory_evidence?.cross_market_holding
  const holdingStability = result?.explanatory_evidence?.holding_stability
  const crossMarketMetrics = (crossMarketHolding?.comparisons || []).filter((item) => [
    'cn_a_weight',
    'hk_weight',
    'security_hhi',
    'industry_hhi',
    'top_three_share_of_disclosed',
  ].includes(item.metric || ''))
  const currentStatus = statusMeta(result?.status || 'insufficient_evidence')
  const benchmarkMapping = result?.peer_context?.benchmark_mapping || result?.classification?.benchmark_mapping
  const benchmarkDetail = benchmarkComposition(benchmarkMapping?.evidence_refs?.benchmarkComponents)
  const latestAttribution = attributionHistory[0]
  const activeAttributionCode = result?.target?.wind_code || selectedFund?.windCode || ''
  const researchMemos = researchEvidence?.research_memos
  const styleProfile = researchEvidence?.style_profile
  const memoManagers = Array.from(new Set((researchMemos?.items || []).map((item) => item.manager_name).filter(Boolean)))
  const visibleStyleEvidence = (styleProfile?.label_evidence || []).filter((item) => ['confirmed', 'quantitative'].includes(item.status || '')).slice(0, 6)

  return (
    <div className="space-y-7">
      <section className="border-b border-[#dce1dc] pb-7">
        <Link href="/discover" className="inline-flex items-center gap-2 text-xs font-bold text-[#28745c]">
          <ArrowLeft className="h-4 w-4" />返回找基金
        </Link>
      </section>

      {error ? <div className="border border-[#e4c37e] bg-[#fff8e6] px-5 py-4 text-sm text-[#77551c]">{error}</div> : null}

      <section className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(20rem,.8fr)]">
        <div className="min-w-0 border border-[#dbe1dc] bg-white p-5 sm:p-6">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-md bg-[#e7f0eb] text-[#25634f]"><Search className="h-5 w-5" /></span>
            <div><h2 className="font-bold text-[#1c2822]">1. 选择基金</h2><p className="mt-1 text-xs text-[#748079]">输入基金名称或代码</p></div>
          </div>
          <form onSubmit={searchFunds} className="mt-5 flex gap-2">
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="例如：005639 或 富国" className="h-12 min-w-0 flex-1 rounded-md border border-[#cfd6d0] px-4 text-sm outline-none focus:border-[#28745c] focus:ring-2 focus:ring-[#28745c]/10" />
            <button disabled={searching} className="inline-flex h-12 items-center gap-2 rounded-md bg-[#173f35] px-5 text-sm font-bold text-white disabled:opacity-60">
              {searching ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}查询
            </button>
          </form>
          {candidates.length ? (
            <div className="mt-3 divide-y divide-[#e2e6e2] border border-[#dce1dc]">
              {candidates.map((fund) => (
                <button key={fund.windCode} type="button" onClick={() => selectFund(fund)} className="flex w-full items-center gap-4 px-4 py-3 text-left hover:bg-[#f4f7f4]">
                  <span className="min-w-0 flex-1"><strong className="block truncate text-sm text-[#1f2b25]">{fund.name}</strong><small className="mt-1 block text-xs text-[#7a857f]">{fund.windCode} · {fund.type || '类别待确认'}</small></span>
                  <ArrowRight className="h-4 w-4 text-[#829089]" />
                </button>
              ))}
            </div>
          ) : null}

          <div className="mt-6">
            <h2 className="font-bold text-[#1c2822]">2. 选择时间</h2>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              {windows.map((item) => (
                <button key={item.key} type="button" onClick={() => setWindowKey(item.key)} className={`border px-4 py-3 text-left ${windowKey === item.key ? 'border-[#397c64] bg-[#edf5f1] text-[#214f40]' : 'border-[#d9dfda] text-[#5f6b65]'}`}>
                  <strong className="block text-sm">{item.label}</strong><span className="mt-1 block text-[11px] opacity-75">{item.hint}</span>
                </button>
              ))}
            </div>
          </div>

          <button type="button" onClick={runEvaluation} disabled={!selectedFund || running} className="mt-6 inline-flex h-12 w-full items-center justify-center gap-2 rounded-md bg-[#173f35] px-5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-45">
            {running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Gauge className="h-4 w-4" />}
            {running ? '正在评价' : '3. 开始评价并保存'}
          </button>
        </div>

        <div className="min-w-0 border border-[#dbe1dc] bg-[#f1f4f1] p-5 sm:p-6">
          <ShieldCheck className="h-5 w-5 text-[#2b735b]" />
          <h2 className="mt-3 text-lg font-bold">怎么评价</h2>
          <p className="mt-3 text-sm leading-7 text-[#65716b]">先分类，再与同类别、同策略基金比较。主动权益、债券、指数和货币基金使用不同指标与权重。</p>
          <div className="mt-5 space-y-3 text-xs leading-6 text-[#65716b]">
            <p>Barra 和 Brinson 只用于解释风险与业绩来源，不参与综合评分。</p>
            <p>结果用于基金研究，不提供买卖时点、购买金额或买卖建议。</p>
          </div>
          <div className="mt-5 grid grid-cols-4 gap-px bg-[#dbe1dc] text-center text-[10px] font-bold text-[#5d6a63]">
            {['分类', '同类评价', '业绩归因', 'AI 分析'].map((step, index) => <div key={step} className="bg-white px-2 py-3"><span className="mx-auto mb-2 grid h-5 w-5 place-items-center rounded-full bg-[#e4efe9] text-[#28634f]">{index + 1}</span>{step}</div>)}
          </div>
          {result?.methodology?.profile_name ? <div className="mt-5 border-l-4 border-[#2f7a5f] bg-white px-4 py-3"><span className="text-xs text-[#738078]">本次自动采用</span><strong className="mt-1 block text-sm">{result.methodology.profile_name}</strong></div> : null}
        </div>
      </section>

      {result ? (
        <section className="space-y-5" data-testid="evaluation-result">
          <div className="grid gap-5 border border-[#d6ded8] bg-white p-5 sm:p-7 lg:grid-cols-[15rem_minmax(0,1fr)]">
            <div className="lg:border-r lg:border-[#e0e5e1] lg:pr-7">
              <span className={`inline-flex border px-2.5 py-1 text-xs font-bold ${currentStatus.className}`}>{currentStatus.label}</span>
              <div className="mt-5 flex items-end gap-2"><strong className="text-6xl font-semibold tracking-[-0.07em] text-[#173f35]">{numberText(result.evaluation?.overall_score)}</strong><span className="pb-2 text-sm text-[#748079]">/ 100</span></div>
              <p className="mt-3 text-sm font-bold text-[#34473e]">等级 {result.evaluation?.overall_grade || '—'}</p>
            </div>
            <div>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div><h2 className="text-xl font-bold text-[#1c2822]">{result.target?.name || selectedFund?.name || result.target?.wind_code}</h2><p className="mt-1 text-sm text-[#718078]">{result.target?.wind_code || selectedFund?.windCode} · 数据截至 {result.target?.as_of_date || '待补'}</p></div>
                <Link href={`/funds/${encodeURIComponent(result.target?.wind_code || selectedFund?.windCode || '')}`} className="inline-flex items-center gap-2 text-xs font-bold text-[#28745c]">查看完整基金资料<ArrowRight className="h-4 w-4" /></Link>
              </div>
              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                <div className="bg-[#f3f6f3] p-4"><span className="text-xs text-[#75817b]">专业同类组</span><strong className="mt-2 block text-sm">{result.peer_context?.peer_group || result.classification?.peer_group || '待确认'}</strong></div>
                <div className="bg-[#f3f6f3] p-4"><span className="text-xs text-[#75817b]">评价基准</span><strong className="mt-2 block text-sm">{result.peer_context?.primary_benchmark || result.classification?.primary_benchmark || '待确认'}</strong>{benchmarkDetail ? <p className="mt-2 text-[11px] leading-5 text-[#6f7c75]">{benchmarkDetail}</p> : null}</div>
                <div className="bg-[#f3f6f3] p-4"><span className="text-xs text-[#75817b]">有效同类样本</span><strong className="mt-2 block text-sm">{result.peer_context?.valid_metric_peer_count ?? 0} 只</strong></div>
              </div>
            </div>
          </div>

          <div className="border border-[#dbe1dc] bg-white">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#e0e5e1] px-5 py-4">
              <div><h3 className="font-bold">基金分类画像</h3><p className="mt-1 text-xs text-[#77827c]">分类决定同类组、评价方法与比较基准，是评分前置门槛。</p></div>
              <span className={`px-2.5 py-1 text-[11px] font-bold ${result.classification?.status === 'classified' ? 'bg-[#e4f0e9] text-[#24624c]' : 'bg-[#fff0d4] text-[#7b581c]'}`}>{result.classification?.status === 'classified' ? `分类置信度 ${numberText((result.classification.confidence || 0) * 100, 0)}%` : '分类待补'}</span>
            </div>
            <div className="grid gap-px bg-[#e3e7e4] sm:grid-cols-2 lg:grid-cols-5">
              <div className="bg-white p-4"><div className="text-xs text-[#75817b]">标准同类组</div><strong className="mt-2 block text-sm">{result.classification?.peer_group || '待确认'}</strong></div>
              <div className="bg-white p-4"><div className="text-xs text-[#75817b]">策略族</div><strong className="mt-2 block text-sm">{result.classification?.strategy_family_name || '待确认'}</strong></div>
              <div className="bg-white p-4"><div className="text-xs text-[#75817b]">资产类别</div><strong className="mt-2 block text-sm">{assetClassLabels[result.classification?.asset_class || ''] || result.classification?.asset_class || result.classification?.legal_type || '待确认'}</strong></div>
              <div className="bg-white p-4"><div className="text-xs text-[#75817b]">管理方式</div><strong className="mt-2 block text-sm">{activePassiveLabels[result.classification?.active_passive || ''] || result.classification?.active_passive || '待确认'}</strong></div>
              <div className="bg-white p-4"><div className="text-xs text-[#75817b]">评价模板</div><strong className="mt-2 block text-sm">{result.methodology?.profile_name || result.classification?.evaluation_profile_key || '待确认'}</strong></div>
            </div>
            <div className="grid gap-4 border-t border-[#e3e7e4] bg-[#f7f9f7] px-5 py-4 text-xs leading-6 text-[#65716b] lg:grid-cols-[minmax(0,1fr)_auto]">
              <div><strong className="text-[#34473e]">基准映射：</strong>{benchmarkMapping?.rationale || `采用 ${result.classification?.primary_benchmark || '待确认基准'} 作为类别比较基准。`}</div>
              <div className="font-bold text-[#28745c]">{result.classification?.evidence?.length || 0} 条分类证据</div>
            </div>
          </div>

          {dimensions.length ? (
            <div className="border border-[#dbe1dc] bg-white p-5 sm:p-6">
              <h3 className="font-bold">核心维度</h3>
              <div className="mt-5 grid gap-x-8 gap-y-5 md:grid-cols-2">
                {dimensions.map(([key, item]) => {
                  const value = Number(item.score || 0)
                  return <div key={key}><div className="flex items-center justify-between gap-3 text-sm"><strong>{dimensionLabels[key] || key}</strong><span className="font-mono font-bold text-[#245f4b]">{numberText(item.score)}</span></div><div className="mt-2 h-2 overflow-hidden bg-[#e5eae6]"><div className="h-full bg-[#2e7b5e]" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div><p className="mt-2 text-xs text-[#77827c]">权重 {item.weight == null ? '—' : `${(item.weight * 100).toFixed(0)}%`}</p></div>
                })}
              </div>
            </div>
          ) : null}

          {peerMetrics.length ? (
            <div className="overflow-x-auto border border-[#dbe1dc] bg-white">
              <div className="border-b border-[#e0e5e1] px-5 py-4"><h3 className="font-bold">同类位置</h3><p className="mt-1 text-xs text-[#77827c]">只与同一专业同类组比较。</p></div>
              <table className="w-full min-w-[680px] text-left text-sm"><thead className="bg-[#f1f4f1] text-xs text-[#66726c]"><tr><th className="px-5 py-3">指标</th><th className="px-5 py-3 text-right">本基金</th><th className="px-5 py-3 text-right">同类分位</th><th className="px-5 py-3 text-right">排名</th></tr></thead><tbody className="divide-y divide-[#e4e8e4]">{peerMetrics.map(([key, item]) => <tr key={key}><td className="px-5 py-3 font-semibold">{item.label || dimensionLabels[key] || key}</td><td className="px-5 py-3 text-right font-mono">{metricText(item.value, item.unit)}</td><td className="px-5 py-3 text-right font-mono">{item.percentile == null ? '—' : `${item.percentile.toFixed(1)}%`}</td><td className="px-5 py-3 text-right font-mono">{item.rank && item.peer_count ? `${item.rank}/${item.peer_count}` : '—'}</td></tr>)}</tbody></table>
            </div>
          ) : null}

          <div className="border border-[#dbe1dc] bg-white">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#e0e5e1] px-5 py-4">
              <div><h3 className="font-bold">调研纪要与风格证据</h3><p className="mt-1 text-xs text-[#77827c]">纪要用于理解经理方法；基金风格优先采用已确认产品证据和量化持仓证据。</p></div>
              {loadingResearch ? <LoaderCircle className="h-4 w-4 animate-spin text-[#28745c]" /> : <span className={`px-2.5 py-1 text-[11px] font-bold ${(researchMemos?.count || 0) > 0 ? 'bg-[#e4f0e9] text-[#24624c]' : 'bg-[#eef1ef] text-[#66726c]'}`}>{researchMemos?.count || 0} 份相关纪要</span>}
            </div>
            <div className="grid gap-px bg-[#e3e7e4] lg:grid-cols-[13rem_minmax(0,1fr)_minmax(15rem,.8fr)]">
              <div className="bg-white p-4">
                <div className="text-xs text-[#75817b]">证据范围</div>
                <strong className="mt-2 block text-sm">基金专属 {researchMemos?.fund_specific_count || 0} · 经理层 {researchMemos?.manager_level_count || 0}</strong>
                <p className="mt-2 text-[11px] leading-5 text-[#7a8580]">{(researchMemos?.manager_level_count || 0) > 0 ? '经理层纪要不能直接外推为本基金持仓。' : '暂无经理层外推风险。'}</p>
              </div>
              <div className="bg-white p-4">
                <div className="text-xs text-[#75817b]">最近纪要</div>
                {researchMemos?.items?.length ? <><strong className="mt-2 line-clamp-2 block text-sm">{researchMemos.items[0].title || '无标题纪要'}</strong><p className="mt-2 text-[11px] text-[#7a8580]">{researchMemos.items[0].report_date || '日期待补'}{memoManagers.length ? ` · ${memoManagers.join('、')}` : ''}</p></> : <strong className="mt-2 block text-sm text-[#78837d]">暂无关联纪要</strong>}
              </div>
              <div className="bg-white p-4">
                <div className="text-xs text-[#75817b]">基金风格画像</div>
                <div className="mt-2 flex flex-wrap gap-1.5">{visibleStyleEvidence.length ? visibleStyleEvidence.map((item, index) => <span key={`${item.value}-${index}`} title={item.basis || item.caveat || ''} className={`rounded-sm px-2 py-1 text-[11px] font-bold ${item.status === 'confirmed' ? 'bg-[#e5eee9] text-[#28634f]' : 'bg-[#edf1f4] text-[#486274]'}`}>{item.value}{item.status === 'quantitative' ? ' · 量化' : ''}</span>) : <span className="text-sm text-[#78837d]">风格证据待补</span>}</div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 border-t border-[#e3e7e4] bg-[#f7f9f7] px-5 py-3">
              <Link href={`/research?search=${encodeURIComponent(memoManagers[0] || activeAttributionCode)}`} className="inline-flex items-center gap-2 rounded-sm border border-[#9fc4b4] bg-white px-3 py-2 text-xs font-bold text-[#245c49]">查看相关纪要<ArrowRight className="h-4 w-4" /></Link>
            </div>
          </div>

          <div className="border border-[#dbe1dc] bg-white">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#e0e5e1] px-5 py-4">
              <div><h3 className="font-bold">Barra / Brinson 归因证据</h3><p className="mt-1 text-xs text-[#77827c]">只解释收益与风险来源，不改变上方综合评分。</p></div>
              {loadingAttribution ? <LoaderCircle className="h-4 w-4 animate-spin text-[#28745c]" /> : <span className={`px-2.5 py-1 text-[11px] font-bold ${latestAttribution ? 'bg-[#e4f0e9] text-[#24624c]' : 'bg-[#fff0d4] text-[#7b581c]'}`}>{latestAttribution ? '已有保存结果' : '尚未运行'}</span>}
            </div>
            {latestAttribution ? (
              <div className="grid gap-px bg-[#e3e7e4] sm:grid-cols-5">
                <div className="bg-white p-4"><div className="text-xs text-[#75817b]">最近季度</div><strong className="mt-2 block">{latestAttribution.quarter || '—'}</strong><small className="mt-1 block text-[10px] text-[#8a948f]">{latestAttribution.benchmark_id || '基准待补'}</small></div>
                <div className="bg-white p-4"><div className="text-xs text-[#75817b]">主动收益</div><strong className="mt-2 block">{percentText(latestAttribution.active_return)}</strong></div>
                <div className="bg-white p-4"><div className="text-xs text-[#75817b]">配置效应</div><strong className="mt-2 block">{percentText(latestAttribution.allocation_effect)}</strong></div>
                <div className="bg-white p-4"><div className="text-xs text-[#75817b]">选择效应</div><strong className="mt-2 block">{percentText(latestAttribution.selection_effect)}</strong></div>
                <div className="bg-white p-4"><div className="text-xs text-[#75817b]">残差</div><strong className="mt-2 block">{percentText(latestAttribution.residual)}</strong></div>
              </div>
            ) : <div className="px-5 py-5 text-sm leading-7 text-[#65716b]">这只基金还没有保存过归因。进入归因页后由用户选择季度现场运行，系统不会批量预计算。</div>}
            <div className="flex flex-wrap gap-2 border-t border-[#e3e7e4] bg-[#f7f9f7] px-5 py-4">
              <Link href={`/analysis/advanced?fundCode=${encodeURIComponent(activeAttributionCode)}`} className="inline-flex items-center gap-2 rounded-sm bg-[#173f35] px-4 py-2 text-xs font-bold text-white">查看或运行业绩归因<ArrowRight className="h-4 w-4" /></Link>
              <Link href={`/analysis?fundCode=${encodeURIComponent(activeAttributionCode)}`} className="inline-flex items-center gap-2 rounded-sm border border-[#9fc4b4] bg-white px-4 py-2 text-xs font-bold text-[#245c49]">交给 AI 综合分析<ArrowRight className="h-4 w-4" /></Link>
            </div>
          </div>

          {crossMarketMetrics.length ? (
            <div className="overflow-hidden border border-[#dbe1dc] bg-white">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#e0e5e1] px-5 py-4">
                <div><h3 className="font-bold">同类持仓画像</h3><p className="mt-1 text-xs text-[#77827c]">{crossMarketHolding?.quarter || '季度待补'} · {crossMarketHolding?.peer_group_name || '当前专业同类组'}；不参与综合评分。</p></div>
                <span className={`px-2.5 py-1 text-[11px] font-bold ${crossMarketHolding?.status === 'peer_comparison_ready' ? 'bg-[#e2f0e8] text-[#1f684e]' : 'bg-[#fff1d2] text-[#815a16]'}`}>{crossMarketHolding?.status === 'peer_comparison_ready' ? `${crossMarketHolding.profile_peer_count || 0} 只样本` : `样本 ${crossMarketHolding?.profile_peer_count || 0}/${crossMarketHolding?.minimum_peer_count || 5}`}</span>
              </div>
              {crossMarketHolding?.labels?.length ? <div className="flex flex-wrap gap-2 border-b border-[#e8ece9] bg-[#f7faf8] px-5 py-3">{crossMarketHolding.labels.map((label) => <span key={label} className="bg-[#e4efe9] px-2.5 py-1 text-xs font-bold text-[#28654f]">{label}</span>)}</div> : null}
              <div className="grid gap-px bg-[#e3e7e4] sm:grid-cols-2 xl:grid-cols-5">
                {crossMarketMetrics.map((item) => <div key={item.metric} className="bg-white p-4"><div className="text-xs font-semibold text-[#59665f]">{item.label || item.metric}</div><div className="mt-2 text-xl font-bold text-[#1d2923]">{metricText(item.value, item.unit)}</div><div className="mt-2 text-[11px] leading-5 text-[#77827c]">{item.percentile == null ? `同类样本 ${item.sample_size || 0}/${item.minimum_peer_count || 5}` : item.position_label || `同类分位 ${item.percentile.toFixed(0)}%`}</div></div>)}
              </div>
              <div className="border-t border-[#e3e7e4] bg-[#fffaf0] px-5 py-3 text-[11px] leading-5 text-[#765d2c]">{crossMarketHolding?.boundary || '公开持仓画像只用于解释，不改变评分。'}</div>
            </div>
          ) : null}

          {holdingStability?.status === 'available' ? (
            <div className="overflow-hidden border border-[#dbe1dc] bg-white">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#e0e5e1] px-5 py-4">
                <div><h3 className="font-bold">公开持仓延续性</h3><p className="mt-1 text-xs text-[#77827c]">{holdingStability.previous_quarter} → {holdingStability.latest_quarter}；不参与综合评分。</p></div>
                <span className={`px-2.5 py-1 text-[11px] font-bold ${holdingStability.level === 'high' ? 'bg-[#e2f0e8] text-[#1f684e]' : holdingStability.level === 'medium' ? 'bg-[#fff1d2] text-[#815a16]' : 'bg-[#f5e5e0] text-[#8b4c41]'}`}>{holdingStability.label || '持仓变化待解释'}</span>
              </div>
              <div className="grid gap-px bg-[#e3e7e4] sm:grid-cols-3">
                <div className="bg-white p-4"><div className="text-xs font-semibold text-[#59665f]">前十大权重重合度</div><div className="mt-2 text-xl font-bold text-[#1d2923]">{holdingStability.top10_overlap_ratio == null ? '—' : `${(holdingStability.top10_overlap_ratio * 100).toFixed(1)}%`}</div></div>
                <div className="bg-white p-4"><div className="text-xs font-semibold text-[#59665f]">延续重仓</div><div className="mt-2 text-xl font-bold text-[#1d2923]">{holdingStability.retained_holding_count || 0} 只</div></div>
                <div className="bg-white p-4"><div className="text-xs font-semibold text-[#59665f]">行业权重重合度</div><div className="mt-2 text-xl font-bold text-[#1d2923]">{holdingStability.industry_overlap_ratio == null ? '—' : `${(holdingStability.industry_overlap_ratio * 100).toFixed(1)}%`}</div></div>
              </div>
              <div className="border-t border-[#e3e7e4] bg-[#fffaf0] px-5 py-3 text-[11px] leading-5 text-[#765d2c]">{holdingStability.boundary || '相邻两期前十大持仓稳定性只作解释，不改变评分。'}</div>
            </div>
          ) : null}

          {result.missing_items?.length ? <div className="border border-[#e2c58a] bg-[#fff9ec] p-5"><div className="flex items-center gap-2 font-bold text-[#72531d]"><CircleAlert className="h-5 w-5" />仍需补齐的证据</div><ul className="mt-3 space-y-2 text-sm text-[#775e31]">{result.missing_items.map((item) => <li key={item}>· {item}</li>)}</ul></div> : <div className="flex items-center gap-3 border border-[#afd1c1] bg-[#eef7f2] px-5 py-4 text-sm text-[#285e4b]"><CheckCircle2 className="h-5 w-5" />分类、基准和核心评价证据已通过。</div>}
        </section>
      ) : null}

      {selectedFund ? (
        <section className="border border-[#dbe1dc] bg-white">
          <div className="flex items-center justify-between gap-3 border-b border-[#e0e5e1] px-5 py-4"><div className="flex items-center gap-3"><Clock3 className="h-5 w-5 text-[#2b735b]" /><div><h2 className="font-bold">{selectedFund.name} 的评价历史</h2><p className="mt-1 text-xs text-[#77827c]">同一只基金不同时间、不同窗口的留存结果</p></div></div>{loadingHistory ? <LoaderCircle className="h-4 w-4 animate-spin text-[#2b735b]" /> : null}</div>
          <HistoryRows items={history} emptyText="还没有保存过评价。" onOpen={openHistory} />
        </section>
      ) : null}

      <section className="border border-[#dbe1dc] bg-white">
        <div className="border-b border-[#e0e5e1] px-5 py-4"><div className="flex items-center gap-3"><Clock3 className="h-5 w-5 text-[#2b735b]" /><div><h2 className="font-bold">最近评价结果</h2><p className="mt-1 text-xs text-[#77827c]">直接打开历史评分详情，无需重新搜索基金</p></div></div></div>
        <HistoryRows items={recentHistory} emptyText="还没有评价记录。" onOpen={openHistory} />
      </section>
    </div>
  )
}
