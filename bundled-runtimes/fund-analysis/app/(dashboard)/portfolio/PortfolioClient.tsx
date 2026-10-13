'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useFundPageData } from '@/lib/newma-desk/page-data'
import { portfolioEvidence, portfolioHistoryVerified, portfolioHistoryUnavailable } from '@/lib/portfolio-evidence'
import {
  BadgeCheck,
  ClipboardList,
  GitCompareArrows,
  HeartPulse,
  LineChart,
  LoaderCircle,
  Plus,
  RefreshCw,
  Scale,
  Trash2,
} from 'lucide-react'

type PortfolioListItem = {
  id: string
  name: string
  objective: string | null
  status: string
  holding_count: number
  total_weight: number | string | null
}

type Holding = {
  wind_code: string
  fund_name: string | null
  weight: number | string | null
  weight_source: string | null
  note: string | null
  evaluation: {
    overall_score: number | null
    grade: string | null
    evaluated_at: string | null
  } | null
}

type Target = {
  peer_group_key: string
  peer_group_name: string | null
  target_weight: number | string
}

type PortfolioDetail = {
  id: string
  name: string
  objective: string | null
  status: string
  targets: Target[]
  holdings: Holding[]
  weight_summary: {
    holding_count: number
    weighted_count: number
    total_weight: number
    is_complete: boolean
  }
}

type Analysis = {
  holding_count: number
  weights: Record<string, number>
  overlap: {
    status: string
    reason?: string
    pairs?: Array<{
      fund_a: string
      fund_b: string
      overlap_ratio: number | null
      similarity_level: string | null
      quarter: string | null
      common_holding_count?: number | null
    }>
  }
  style_aggregate: {
    status: string
    coverage: number | null
    coverage_note?: string
    reason?: string
    factors?: Array<{ factor: string; label: string; unit: string | null; weighted_exposure: number | null; coverage?: number; quarters?: string[]; undated?: boolean; status?: string }>
  }
  correlation: {
    status: string
    lookback_days: number
    methodology_version?: string
    nav_basis?: string
    note?: string
    reason?: string
    pairs?: Array<{ fund_a: string; fund_b: string; correlation: number | null; overlap_days: number; return_intervals?: number; start_date?: string | null; end_date?: string | null; status: string }>
  }
  boundary: string
}

type PerfMetrics = {
  cumulative_return: number
  annualized_return: number | null
  annualized_volatility: number | null
  volatility_note?: string
  max_drawdown: number
  sample_days: number
  start_date: string | null
  end_date: string | null
}

type Backtest = {
  status: string
  methodology_version?: string
  nav_basis?: string
  reason?: string
  weights_basis?: string
  sample?: { days: number; start_date: string; end_date: string; lookback_days: number; return_intervals?: number; omitted_union_dates?: number; data_lag_calendar_days?: number }
  metrics?: PerfMetrics
  curve?: Array<{ date: string; value: number }>
  benchmark?: {
    source: string
    source_fund_code?: string
    code?: string | null
    name?: string | null
    status: string
    basis_note?: string
    reason?: string
    aligned_to_portfolio?: boolean
    metrics?: PerfMetrics
    excess_return?: number
  }
  boundary?: string
}

type Monitor = {
  status: string
  summary?: string
  rebalance_threshold?: number
  rebalance_needed?: boolean | null
  target_assessable?: boolean
  weights_basis?: string
  target_deviations?: Array<{
    peer_group_key: string
    peer_group_name: string | null
    target_weight: number | null
    actual_weight: number | null
    deviation: number | null
    needs_rebalance: boolean | null
  }>
  style_drifts?: Array<{
    wind_code: string
    fund_name: string | null
    status: string
    level: string | null
    label: string | null
    note: string
    previous_quarter?: string | null
    latest_quarter?: string | null
  }>
  drift_alerts?: Array<{ wind_code: string; level: string | null; label: string | null }>
  boundary?: string
}

type TradeList = {
  status: string
  reason?: string
  total_amount?: number | null
  items?: Array<{
    wind_code: string
    fund_name: string | null
    action: string
    current_weight: number
    target_weight: number
    weight_delta: number
    amount: number | null
    shares: number | null
    latest_nav: number | null
    nav_date: string | null
  }>
  boundary?: string
}

const card = 'rounded-xl border border-[#d9ded9] bg-white p-4 shadow-sm'
const label = 'text-xs font-semibold text-[#5c6b61]'
const button = 'rounded-lg border border-[#c8d4cb] bg-white px-3 py-1.5 text-sm text-[#1f2d26] transition hover:bg-[#eef3ef] disabled:opacity-50'
const primaryButton = 'rounded-lg bg-[#28745c] px-3 py-1.5 text-sm font-medium text-white transition hover:bg-[#1f5d49] disabled:opacity-50'

function pct(value: number | string | null | undefined): string {
  if (value == null) return '—'
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  return `${(num * 100).toFixed(1)}%`
}

function Sparkline({ series, color, height = 96 }: { series: number[]; color: string; height?: number }) {
  if (series.length < 2) return null
  const min = Math.min(...series)
  const max = Math.max(...series)
  const range = max - min || 1
  const points = series
    .map((value, index) => `${(index / (series.length - 1)) * 100},${100 - ((value - min) / range) * 100}`)
    .join(' ')
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ height }} className="w-full">
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export default function PortfolioClient() {
  const [portfolios, setPortfolios] = useState<PortfolioListItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<PortfolioDetail | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [newName, setNewName] = useState('')
  const [addCode, setAddCode] = useState('')
  const [weightDraft, setWeightDraft] = useState<Record<string, string>>({})
  const [backtest, setBacktest] = useState<Backtest | null>(null)
  const [backtestLookback, setBacktestLookback] = useState(365)
  const [backtestLoading, setBacktestLoading] = useState(false)
  const [monitor, setMonitor] = useState<Monitor | null>(null)
  const [monitorLoading, setMonitorLoading] = useState(false)
  const [targetsEditing, setTargetsEditing] = useState(false)
  const [targetRows, setTargetRows] = useState<Array<{ key: string; name: string; weight: string }>>([])
  const [targetsSaving, setTargetsSaving] = useState(false)
  const [targetsError, setTargetsError] = useState('')
  const [tradeList, setTradeList] = useState<TradeList | null>(null)
  const [tradeInput, setTradeInput] = useState('')
  const [tradeAmount, setTradeAmount] = useState('')
  const [tradeLoading, setTradeLoading] = useState(false)
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [analysisError, setAnalysisError] = useState('')
  const [backtestError, setBacktestError] = useState('')
  const [monitorError, setMonitorError] = useState('')
  const [tradeError, setTradeError] = useState('')
  const [saving, setSaving] = useState(false)
  const [backtestApplied, setBacktestApplied] = useState<number | null>(null)
  const [tradeApplied, setTradeApplied] = useState<{ positions: string; amount: string } | null>(null)
  const revision = useRef(0)
  const listRequest = useRef(0)
  const backtestRequest = useRef(0)
  const monitorRequest = useRef(0)
  const tradeRequest = useRef(0)

  const clearResults = useCallback(() => {
    setBacktest(null); setBacktestApplied(null); setBacktestLoading(false); setBacktestError('')
    setMonitor(null); setMonitorLoading(false); setMonitorError('')
    setTradeList(null); setTradeApplied(null); setTradeLoading(false); setTradeError('')
  }, [])

  const selectPortfolio = (portfolioId: string) => {
    if (portfolioId === selectedId) return
    ++revision.current
    clearResults()
    setDetail(null)
    setAnalysis(null)
    setWeightDraft({})
    setBacktest(null)
    setMonitor(null)
    setTradeList(null)
    setTargetsEditing(false)
    setTargetRows([])
    setTargetsError('')
    setTradeInput('')
    setTradeAmount('')
    setAddCode('')
    setError('')
    setAnalysisError('')
    setNotice('')
    setSelectedId(portfolioId)
  }

  const loadPortfolios = useCallback(async () => {
    const request = ++listRequest.current
    setListLoading(true)
    setListError('')
    try {
      const response = await fetch('/api/portfolios', { cache: 'no-store' })
      const payload = await response.json()
      if (request !== listRequest.current) return
      if (!response.ok) throw new Error(payload.detail || payload.error || '组合列表暂时不可用')
      setPortfolios(payload.data || [])
      setSelectedId(current => current || payload.data?.[0]?.id || null)
    } catch (exc) {
      if (request === listRequest.current) setListError(`组合列表加载失败: ${exc}`)
    } finally {
      if (request === listRequest.current) setListLoading(false)
    }
  }, [])

  const loadDetail = useCallback(async (portfolioId: string) => {
    const request = ++revision.current
    clearResults()
    setDetail(null)
    setAnalysis(null)
    setWeightDraft({})
    setAnalysisError('')
    setLoading(true)
    setError('')
    try {
      const [detailResult, analysisResult] = await Promise.allSettled([
        fetch(`/api/portfolios/${portfolioId}`, { cache: 'no-store' }),
        fetch(`/api/portfolios/${portfolioId}/analysis`, { cache: 'no-store' }),
      ])
      if (request !== revision.current) return
      if (detailResult.status === 'rejected') throw new Error('读取组合失败')
      const detailResponse = detailResult.value
      const payload = await detailResponse.json()
      if (request !== revision.current) return
      if (detailResponse.ok) {
        setDetail(payload)
        setWeightDraft(
          Object.fromEntries(
            (payload.holdings || []).map((item: Holding) => [
              item.wind_code,
              item.weight != null ? String(Number((Number(item.weight) * 100).toFixed(6))) : '',
            ]),
          ),
        )
      } else {
        throw new Error(payload.detail || payload.error || '组合详情暂时不可用')
      }
      try {
        if (analysisResult.status === 'rejected' || !analysisResult.value.ok) throw new Error('组合穿透读取失败，请刷新重试')
        const data = await analysisResult.value.json()
        if (data.correlation && !portfolioHistoryVerified(data.correlation)) {
          data.correlation = { status: 'unsupported_methodology', lookback_days: data.correlation.lookback_days, reason: portfolioHistoryUnavailable, pairs: [] }
        }
        if (request === revision.current) setAnalysis(data)
      } catch (exc) {
        if (request === revision.current) setAnalysisError(exc instanceof Error ? exc.message : '穿透读取失败')
      }
    } catch (exc) {
      if (request === revision.current) setError(`组合详情加载失败: ${exc}`)
    } finally {
      if (request === revision.current) setLoading(false)
    }
  }, [clearResults])

  const beginTargetsEdit = () => {
    const rows: Array<{ key: string; name: string; weight: string }> = (detail?.targets || []).map((item) => ({
      key: item.peer_group_key,
      name: item.peer_group_name || '',
      weight: item.target_weight != null ? String(Number((Number(item.target_weight) * 100).toFixed(6))) : '',
    }))
    // 监控披露的实际分组（尚未配置目标的）也预填，便于直接补权重
    const known = new Set(rows.map((row) => row.key))
    for (const item of monitor?.target_deviations || []) {
      if (!known.has(item.peer_group_key)) {
        rows.push({ key: item.peer_group_key, name: item.peer_group_name || '', weight: '' })
      }
    }
    setTargetRows(rows)
    setTargetsError('')
    setTargetsEditing(true)
  }

  const saveTargets = async () => {
    if (!detail) return
    setTargetsSaving(true)
    setTargetsError('')
    try {
      if (targetRows.some(row => (row.key.trim() || row.name.trim() || row.weight.trim()) && (!row.key.trim() || !row.weight.trim()))) {
        throw new Error('请补齐每一行的同类组和目标权重，或删除该行')
      }
      const targets = targetRows
        .filter((row) => row.key.trim() && row.weight.trim())
        .map((row) => ({
          peer_group_key: row.key.trim(),
          peer_group_name: row.name.trim() || null,
          target_weight: Number(row.weight) / 100,
        }))
      if (targets.some((item) => !Number.isFinite(item.target_weight) || !(item.target_weight > 0) || item.target_weight > 1)) {
        throw new Error('目标权重必须为正数（百分比）')
      }
      if (new Set(targets.map(item => item.peer_group_key)).size !== targets.length) throw new Error('同类组不能重复')
      const total = targets.reduce((sum, item) => sum + item.target_weight, 0)
      if (targets.length && Math.abs(total - 1) > 0.005) {
        throw new Error(`权重合计需为 100%（当前 ${(total * 100).toFixed(1)}%）`)
      }
      const response = await fetch(`/api/portfolios/${detail.id}/targets`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ targets }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || payload.error || '保存失败')
      setTargetsEditing(false)
      await loadDetail(detail.id)
    } catch (exc) {
      setTargetsError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setTargetsSaving(false)
    }
  }

  useEffect(() => {
    void loadPortfolios()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId)
  }, [selectedId, loadDetail])

  useEffect(() => () => { ++revision.current; ++listRequest.current }, [])

  const createPortfolio = async () => {
    const name = newName.trim()
    if (!name) return
    if (saving || targetsSaving) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const response = await fetch('/api/portfolios', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || '创建失败')
      setNewName('')
      await loadPortfolios()
      selectPortfolio(payload.id)
      setNotice(`组合「${name}」已创建，请在详情中添加持仓。`)
    } catch (exc) {
      setError(`创建组合失败: ${exc}`)
    } finally {
      setSaving(false)
    }
  }

  const addHolding = async () => {
    const code = addCode.trim().toUpperCase()
    if (!code || !selectedId) return
    if (saving || targetsSaving) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const response = await fetch(`/api/portfolios/${selectedId}/holdings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wind_code: code }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || '添加失败')
      setAddCode('')
      setNotice(`${code} 已加入组合。`)
      await loadDetail(selectedId)
      await loadPortfolios()
    } catch (exc) {
      setError(`添加持仓失败: ${exc}`)
    } finally {
      setSaving(false)
    }
  }

  const removeHolding = async (code: string) => {
    if (!selectedId) return
    if (saving || targetsSaving) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const response = await fetch(`/api/portfolios/${selectedId}/holdings/${encodeURIComponent(code)}`, { method: 'DELETE' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || '移除失败')
      setNotice(`${code} 已移出组合。`)
      await loadDetail(selectedId)
      await loadPortfolios()
    } catch (exc) {
      setError(`移除持仓失败: ${exc}`)
    } finally {
      setSaving(false)
    }
  }

  const applyEqualWeights = async () => {
    if (!selectedId) return
    if (saving || targetsSaving) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const response = await fetch(`/api/portfolios/${selectedId}/weights/equal`, { method: 'POST' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || '等权失败')
      setNotice('已按等权设置全部持仓。')
      await loadDetail(selectedId)
      await loadPortfolios()
    } catch (exc) {
      setError(`等权失败: ${exc}`)
    } finally {
      setSaving(false)
    }
  }

  const saveCustomWeights = async () => {
    if (!selectedId || !detail) return
    if (detail.holdings.some(item => !(weightDraft[item.wind_code] ?? '').trim())) {
      setError('请填写每只基金的权重；空白不代表 0%')
      return
    }
    const items = detail.holdings
      .map((item) => ({ wind_code: item.wind_code, weight: Number(weightDraft[item.wind_code]) / 100 }))
    if (items.some(item => !Number.isFinite(item.weight) || item.weight <= 0 || item.weight > 0.4)) {
      setError('每只基金的权重须大于 0% 且不超过 40%；零权重基金请移出组合')
      return
    }
    if (Math.abs(items.reduce((sum, item) => sum + item.weight, 0) - 1) > 0.005) {
      setError('基金权重合计需为 100%')
      return
    }
    if (saving || targetsSaving) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const response = await fetch(`/api/portfolios/${selectedId}/weights`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items, source: 'custom' }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || '保存失败')
      setNotice('自定义权重已保存。')
      await loadDetail(selectedId)
      await loadPortfolios()
    } catch (exc) {
      setError(`保存权重失败: ${exc}`)
    } finally {
      setSaving(false)
    }
  }

  const overlapPairs = analysis?.overlap?.pairs || []
  const correlationPairs = analysis?.correlation?.pairs || []
  const styleFactors = analysis?.style_aggregate?.factors || []
  const evidence = useMemo(() => portfolioEvidence(detail?.holdings || [], detail?.targets || [], analysis?.weights, monitor), [detail, analysis, monitor])

  const runBacktest = async () => {
    if (!selectedId) return
    const version = revision.current, request = ++backtestRequest.current, lookback = backtestLookback
    setBacktest(null); setBacktestApplied(null); setBacktestError('')
    setBacktestLoading(true)
    try {
      const response = await fetch(`/api/portfolios/${selectedId}/backtest?lookback_days=${backtestLookback}`, { cache: 'no-store' })
      const payload = await response.json()
      if (version !== revision.current || request !== backtestRequest.current) return
      if (!response.ok) throw new Error(payload.detail || payload.error || '回测接口暂时不可用')
      if (payload.benchmark?.status === 'available' && payload.benchmark.aligned_to_portfolio !== true) {
        payload.benchmark = { ...payload.benchmark, status: 'unaligned', metrics: undefined, excess_return: undefined,
          basis_note: undefined, reason: '基准未完成同区间对齐，暂不展示超额收益。' }
      }
      setBacktest(portfolioHistoryVerified(payload) ? payload : { status: 'unsupported_methodology', reason: portfolioHistoryUnavailable })
      setBacktestApplied(lookback)
    } catch (exc) {
      if (version === revision.current && request === backtestRequest.current) setBacktestError(`回测失败: ${exc}`)
    } finally {
      if (version === revision.current && request === backtestRequest.current) setBacktestLoading(false)
    }
  }

  const runMonitor = async () => {
    if (!selectedId) return
    const version = revision.current, request = ++monitorRequest.current
    setMonitor(null); setMonitorError('')
    setMonitorLoading(true)
    try {
      const response = await fetch(`/api/portfolios/${selectedId}/monitor`, { cache: 'no-store' })
      const payload = await response.json()
      if (version !== revision.current || request !== monitorRequest.current) return
      if (!response.ok) throw new Error(payload.detail || payload.error || '监控接口暂时不可用')
      setMonitor(payload)
    } catch (exc) {
      if (version === revision.current && request === monitorRequest.current) setMonitorError(`监控失败: ${exc}`)
    } finally {
      if (version === revision.current && request === monitorRequest.current) setMonitorLoading(false)
    }
  }

  const generateTradeList = async () => {
    if (!selectedId) return
    const version = revision.current, request = ++tradeRequest.current
    setTradeList(null); setTradeApplied(null); setTradeError('')
    const currentPositions = tradeInput
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const parts = line.split(/[,\s，]+/)
        return { wind_code: (parts[0] || '').toUpperCase(), weight: parts[1] != null ? Number(parts[1]) / 100 : undefined }
      })
      .filter((item) => item.wind_code)
    if (!currentPositions.length || currentPositions.some(item => item.weight == null || !Number.isFinite(item.weight) || item.weight < 0 || item.weight > 1)) {
      setTradeError('请逐行填写基金代码及 0% 至 100% 的权重；未知持仓不能按零计算')
      return
    }
    if (new Set(currentPositions.map(item => item.wind_code)).size !== currentPositions.length) {
      setTradeError('当前持仓中有重复基金代码，请先合并')
      return
    }
    if (Math.abs(currentPositions.reduce((sum, item) => sum + (item.weight ?? 0), 0) - 1) > 0.005) {
      setTradeError('当前基金持仓权重合计需为 100%；现金和其他资产请在组合中心管理')
      return
    }
    if (tradeAmount.trim() && (!Number.isFinite(Number(tradeAmount)) || Number(tradeAmount) <= 0)) {
      setTradeError('投资金额须为正数，未知金额请留空')
      return
    }
    setTradeLoading(true)
    try {
      const response = await fetch(`/api/portfolios/${selectedId}/trade-list`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_positions: currentPositions,
          total_amount: Number(tradeAmount) || null,
        }),
      })
      const payload = await response.json()
      if (version !== revision.current || request !== tradeRequest.current) return
      if (!response.ok) throw new Error(payload.detail || payload.error || '清单接口暂时不可用')
      setTradeList(payload)
      setTradeApplied({ positions: tradeInput, amount: tradeAmount })
    } catch (exc) {
      if (version === revision.current && request === tradeRequest.current) setTradeError(`交易清单生成失败: ${exc}`)
    } finally {
      if (version === revision.current && request === tradeRequest.current) setTradeLoading(false)
    }
  }

  useFundPageData(useMemo(() => ({
    selection: null,
    filters: { portfolioId: selectedId, weightDraftPercent: weightDraft,
      targetDraft: targetsEditing ? targetRows : null,
      backtest: { requestedDays: backtestLookback, appliedDays: backtestApplied },
      trade: { requested: { positions: tradeInput, amount: tradeAmount }, applied: tradeApplied } },
    visibleBlocks: [{ id: 'portfolio-holdings', type: 'table', title: '研究组合与已保存权重' },
      { id: 'portfolio-analysis', type: 'summary', title: '穿透、回测、监控与研究清单' }],
    summary: {
      status: saving || targetsSaving ? 'saving' : loading || listLoading ? 'loading' : error ? 'error' : detail ? 'ready' : 'idle',
      error: error || null, notice: notice || null,
      list: { status: listLoading ? 'loading' : listError ? 'error' : 'ready', error: listError || null,
        count: listError || listLoading ? null : portfolios.length, rows: portfolios.slice(0, 50) },
      portfolio: detail ? { id: detail.id, name: detail.name, objective: detail.objective, status: detail.status,
        targets: detail.targets, holdings: detail.holdings.slice(0, 200), holdingsTruncated: detail.holdings.length > 200,
        weightSummary: detail.weight_summary } : null,
      analysis: { status: loading ? 'loading' : analysisError ? 'error' : analysis ? 'ready' : 'not-loaded', error: analysisError || null,
        result: analysis ? { ...analysis,
          coverageInterpretation: 'style_aggregate.coverage 是基金快照计算权重覆盖，不是底层资产穿透率；因子未提供 coverage 或 quarters 时该因子的覆盖或披露期未知。weighted_exposure 只是已知部分的加权贡献，不能视作全组合暴露。',
          overlap: { ...analysis.overlap, pairs: analysis.overlap.pairs?.slice(0, 100) },
          correlation: { ...analysis.correlation, pairs: analysis.correlation.pairs?.slice(0, 100) } } : null },
      backtest: { status: backtestLoading ? 'loading' : backtestError ? 'error' : backtest ? 'ready' : 'not-run', error: backtestError || null,
        result: backtest ? { ...backtest, curve: undefined, curvePointCount: backtest.curve?.length ?? 0,
          curveTail: backtest.curve?.slice(-12), curveTruncated: (backtest.curve?.length ?? 0) > 12 } : null },
      evidence,
      monitor: { status: monitorLoading ? 'loading' : monitorError ? 'error' : monitor ? 'ready' : 'not-run', error: monitorError || null,
        result: monitor ? { ...monitor, summary: evidence.summary, rebalance_needed: evidence.rebalanceNeeded,
          target_deviations: monitor.target_deviations?.map(item => ({ ...item, needs_rebalance: evidence.targetAssessable ? item.needs_rebalance : null })) } : null },
      tradeList: { status: tradeLoading ? 'loading' : tradeError ? 'error' : tradeList ? 'ready' : 'not-run', error: tradeError || null,
        result: tradeList ? { ...tradeList, items: tradeList.items?.slice(0, 100), itemsTruncated: (tradeList.items?.length ?? 0) > 100 } : null },
      targetSaveError: targetsError || null,
      boundary: '这是研究型基金组合，不是账户实盘。已保存成分权重、同类组目标和未保存草稿分别记录；草稿不参与现有分析。分析实际使用权重以 analysis.weights 为准。当前权重历史回看不是实盘业绩，前十大重叠不是完整穿透。交易清单仅为试算、不执行交易，未知日期与缺失证据不能当作最新或零风险。',
    },
  }), [selectedId, weightDraft, targetsEditing, targetRows, backtestLookback, backtestApplied, tradeInput, tradeAmount, tradeApplied,
    saving, targetsSaving, loading, listLoading, error, notice, listError, portfolios, detail, analysisError, analysis, evidence,
    backtestLoading, backtestError, backtest, monitorLoading, monitorError, monitor, tradeLoading, tradeError, tradeList, targetsError]))

  return (
    <fieldset disabled={saving || targetsSaving} className="mx-auto min-w-0 max-w-7xl space-y-4 border-0 p-2 md:p-3">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-[#5c6b61]">研究组合 · 草稿与已保存配置分离 · 不执行交易</p>
        <button type="button" className={button} disabled={loading || listLoading} onClick={() => { void loadPortfolios(); if (selectedId) void loadDetail(selectedId) }}>
          <RefreshCw className="mr-1 inline h-4 w-4" aria-hidden="true" />
          刷新
        </button>
      </header>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800" role="alert">
          {error}
          <button type="button" className="ml-2 underline" onClick={() => setError('')}>关闭</button>
        </div>
      ) : null}
      {notice ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-900" role="status">
          {notice}
          <button type="button" className="ml-2 underline" onClick={() => setNotice('')}>关闭</button>
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <aside className={`${card} self-start`}>
          <h2 className={label}>组合列表</h2>
          <div className="mt-2 flex gap-2">
            <input
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="新组合名称"
              className="min-w-0 flex-1 rounded-lg border border-[#c8d4cb] px-2 py-1.5 text-sm"
            />
            <button type="button" aria-label="创建研究组合" className={primaryButton} onClick={createPortfolio} disabled={!newName.trim() || listLoading}>
              <Plus className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          <ul className="mt-3 space-y-1">
            {portfolios.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => selectPortfolio(item.id)}
                  aria-pressed={selectedId === item.id}
                  style={{ borderLeft: `3px solid ${selectedId === item.id ? 'var(--vibe-accent)' : 'transparent'}` }}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${
                    selectedId === item.id ? 'bg-[#e7f0ea] font-medium text-[#1f2d26]' : 'text-[#3d5347] hover:bg-[#f2f6f3]'
                  }`}
                >
                  <span className="block truncate">{item.name}</span>
                  <span className="mt-0.5 block text-xs text-[#748079]">
                    {item.holding_count} 只持仓 · 权重 {pct(item.total_weight)}
                  </span>
                </button>
              </li>
            ))}
            {listError ? <li role="alert" className="text-sm">{listError}，请点击刷新重试。</li> : null}
            {listLoading ? <li className="text-sm">正在读取组合列表…</li> : null}
            {!portfolios.length && !listLoading && !listError ? (
              <li className="rounded-lg bg-[#f7f9f8] px-3 py-3 text-sm text-[#748079]">暂无组合，先创建一个。</li>
            ) : null}
          </ul>
        </aside>

        <section className="space-y-4">
          {!detail ? (
            <div className={`${card} text-sm text-[#748079]`}>
              {loading ? (
                <span className="inline-flex items-center gap-2">
                  <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
                  加载中…
                </span>
              ) : (
                error ? '组合读取失败，请刷新重试。' : '选择或创建一个组合开始构建。'
              )}
            </div>
          ) : (
            <>
              <div className={card}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h2 className="text-lg font-bold text-[#1f2d26]">{detail.name}</h2>
                    {detail.objective ? <p className="mt-1 text-sm text-[#5c6b61]">{detail.objective}</p> : null}
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <BadgeCheck className="h-4 w-4 text-[#28745c]" aria-hidden="true" />
                    {detail.weight_summary.is_complete ? (
                      <span className="text-[#28745c]">权重已配置（{pct(detail.weight_summary.total_weight)}）</span>
                    ) : (
                      <span className="text-amber-700">权重未配齐（{pct(detail.weight_summary.total_weight)}），请核对下方计算权重</span>
                    )}
                  </div>
                </div>
                {targetsEditing ? (
                  <div className="mt-3">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-[#e4e9e5] text-left text-xs text-[#748079]">
                          <th className="py-1.5 pr-2">同类组 key</th>
                          <th className="py-1.5 pr-2">显示名称</th>
                          <th className="py-1.5 pr-2 w-28">目标权重 %</th>
                          <th className="py-1.5 w-10"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {targetRows.map((row, index) => {
                          return (
                            <tr key={index} className="border-b border-[#f0f4f1]">
                              <td className="py-1.5 pr-2">
                                <input
                                  value={row.key}
                                  onChange={(event) => {
                                    const next = [...targetRows]
                                    next[index] = { ...row, key: event.target.value }
                                    setTargetRows(next)
                                  }}
                                  className="w-full rounded border border-[#d5ded8] px-2 py-1 text-sm"
                                  placeholder="如 混合型-偏股配置"
                                />
                              </td>
                              <td className="py-1.5 pr-2">
                                <input
                                  value={row.name}
                                  onChange={(event) => {
                                    const next = [...targetRows]
                                    next[index] = { ...row, name: event.target.value }
                                    setTargetRows(next)
                                  }}
                                  className="w-full rounded border border-[#d5ded8] px-2 py-1 text-sm"
                                  placeholder="显示名称（可空）"
                                />
                              </td>
                              <td className="py-1.5 pr-2">
                                <input
                                  value={row.weight}
                                  onChange={(event) => {
                                    const next = [...targetRows]
                                    next[index] = { ...row, weight: event.target.value }
                                    setTargetRows(next)
                                  }}
                                  className="w-24 rounded border border-[#d5ded8] px-2 py-1 text-sm"
                                  placeholder="如 30"
                                  inputMode="decimal"
                                />
                              </td>
                              <td className="py-1.5">
                                <button
                                  type="button"
                                  onClick={() => setTargetRows(targetRows.filter((_, i) => i !== index))}
                                  className="text-xs text-[#a05a52] hover:underline"
                                  aria-label="删除此行"
                                >
                                  删除
                                </button>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-[#68766f]">
                      <span>
                        合计：
                        <strong className="mx-1 text-[#1f2d26]">
                          {targetRows.reduce((sum, item) => sum + (Number(item.weight) || 0), 0).toFixed(1)}%
                        </strong>
                        （需为 100%；完全空白行忽略；清空全部保存 = 移除目标配置）
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setTargetRows([...targetRows, { key: '', name: '', weight: '' }])}
                          className="rounded border border-[#a8bcb2] px-2 py-1 text-xs font-bold text-[#285d4b] hover:bg-[#edf4f0]"
                        >
                          添加一行
                        </button>
                        <button
                          type="button"
                          disabled={targetsSaving}
                          onClick={() => void saveTargets()}
                          className="rounded bg-[#173f35] px-3 py-1 text-xs font-bold text-white hover:bg-[#28624e] disabled:opacity-60"
                        >
                          {targetsSaving ? '保存中…' : '保存目标配置'}
                        </button>
                        <button
                          type="button"
                          disabled={targetsSaving}
                          onClick={() => setTargetsEditing(false)}
                          className="rounded border border-[#a8bcb2] px-2 py-1 text-xs font-bold text-[#5c6b61] hover:bg-[#f2f5f3]"
                        >
                          取消
                        </button>
                      </div>
                    </div>
                    {targetsError ? <p role="alert" className="mt-2 text-xs text-[#a05a52]">{targetsError}</p> : null}
                  </div>
                ) : detail.targets.length ? (
                  <div className="mt-3">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-[#e4e9e5] text-left text-xs text-[#748079]">
                            <th className="py-1.5 pr-3">目标同类组</th>
                            <th className="py-1.5">目标权重</th>
                          </tr>
                        </thead>
                        <tbody>
                          {detail.targets.map((target) => (
                            <tr key={target.peer_group_key} className="border-b border-[#f0f4f1]">
                              <td className="py-1.5 pr-3">{target.peer_group_name || target.peer_group_key}</td>
                              <td className="py-1.5">{pct(target.target_weight)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <button
                      type="button"
                      onClick={beginTargetsEdit}
                      className="mt-2 text-xs font-bold text-[#28745c] hover:underline"
                    >
                      修改目标配置
                    </button>
                  </div>
                ) : (
                  <div className="mt-3">
                    <p className="text-xs text-[#748079]">
                      未配置目标同类组权重——监控只披露实际分组权重，不做再平衡判定。
                    </p>
                    <button
                      type="button"
                      onClick={beginTargetsEdit}
                      className="mt-2 rounded border border-[#a8bcb2] px-2.5 py-1 text-xs font-bold text-[#285d4b] hover:bg-[#edf4f0]"
                    >
                      配置目标权重
                    </button>
                  </div>
                )}
              </div>

              <div className={card}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="flex items-center gap-1.5 font-semibold text-[#1f2d26]">
                    <Scale className="h-4 w-4 text-[#28745c]" aria-hidden="true" />
                    持仓与权重（单只 ≤ 40%）
                  </h3>
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      value={addCode}
                      onChange={(event) => setAddCode(event.target.value)}
                      placeholder="基金代码，如 588000.SH"
                      className="w-44 rounded-lg border border-[#c8d4cb] px-2 py-1.5 text-sm"
                    />
                    <button type="button" className={button} onClick={addHolding} disabled={!addCode.trim()}>添加</button>
                    <button type="button" className={button} onClick={applyEqualWeights} disabled={!detail.holdings.length}>等权</button>
                    <button type="button" className={primaryButton} onClick={saveCustomWeights} disabled={!detail.holdings.length}>保存权重</button>
                  </div>
                </div>
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[#e4e9e5] text-left text-xs text-[#748079]">
                        <th className="py-1.5 pr-3">基金</th>
                        <th className="py-1.5 pr-3">权重 %</th>
                        <th className="py-1.5 pr-3">来源</th>
                        <th className="py-1.5 pr-3">评价分</th>
                        <th className="py-1.5">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.holdings.map((item) => (
                        <tr key={item.wind_code} className="border-b border-[#f0f4f1]">
                          <td className="py-1.5 pr-3">
                            <span className="font-medium">{item.wind_code}</span>
                            <span className="ml-2 text-xs text-[#748079]">{item.fund_name || ''}</span>
                          </td>
                          <td className="py-1.5 pr-3">
                            <input
                              value={weightDraft[item.wind_code] ?? ''}
                              onChange={(event) => setWeightDraft((prev) => ({ ...prev, [item.wind_code]: event.target.value }))}
                              inputMode="decimal"
                              className="w-20 rounded border border-[#c8d4cb] px-2 py-1 text-sm"
                              aria-label={`${item.wind_code} 权重百分比`}
                            />
                          </td>
                          <td className="py-1.5 pr-3 text-xs text-[#748079]">
                            {item.weight_source === 'equal' ? '等权' : item.weight_source === 'custom' ? '自定义' : '未设置'}
                          </td>
                          <td className="py-1.5 pr-3">
                            {item.evaluation?.overall_score != null ? (
                              <span>{item.evaluation.overall_score}</span>
                            ) : (
                              <span className="text-xs text-[#748079]">暂无快照（每日积累，实时评分见推荐页）</span>
                            )}
                          </td>
                          <td className="py-1.5">
                            <button type="button" className="text-[#a05a52] hover:underline" onClick={() => removeHolding(item.wind_code)}>
                              <Trash2 className="h-4 w-4" aria-hidden="true" />
                              <span className="sr-only">移除 {item.wind_code}</span>
                            </button>
                          </td>
                        </tr>
                      ))}
                      {!detail.holdings.length ? (
                        <tr>
                          <td colSpan={5} className="py-3 text-sm text-[#748079]">暂无持仓，输入基金代码添加（需满足推荐就绪口径）。</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className={card}>
                <h3 className="flex items-center gap-1.5 font-semibold text-[#1f2d26]">
                  <GitCompareArrows className="h-4 w-4 text-[#28745c]" aria-hidden="true" />
                  组合穿透
                </h3>
                {analysisError ? <p role="alert" className="mt-2 text-sm">{analysisError}；不能据此判断重叠或风险为零。</p> : null}
                <p className="mt-2 text-xs text-[#748079]">下列结果使用已保存配置；编辑中的权重和目标需保存后才生效。</p>
                {analysis ? <p className="mt-2 text-xs text-[#748079]">本次穿透计算权重：{Object.entries(analysis.weights || {}).map(([code, weight]) => `${code} ${pct(weight)}`).join(' · ') || '未提供'}。权重未配齐时服务可能使用等权假设，不代表真实仓位。</p> : null}
                {analysis ? <p className="mt-1 text-sm">{evidence.calculationMatchesSaved ? '计算权重与已保存成分一致。' : '计算权重未能与完整已保存成分核对，结果仅供假设研究。'}</p> : null}

                <h4 className={`${label} mt-3`}>重仓股重叠（同一披露季度前十大）</h4>
                {overlapPairs.length ? (
                  <table className="mt-1 w-full text-sm">
                    <thead>
                      <tr className="border-b border-[#e4e9e5] text-left text-xs text-[#748079]">
                        <th className="py-1.5 pr-3">配对</th>
                        <th className="py-1.5 pr-3">重叠率</th>
                        <th className="py-1.5 pr-3">级别</th>
                        <th className="py-1.5">季度</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overlapPairs.map((pair) => (
                        <tr key={`${pair.fund_a}-${pair.fund_b}`} className="border-b border-[#f0f4f1]">
                          <td className="py-1.5 pr-3">{pair.fund_a} × {pair.fund_b}</td>
                          <td className="py-1.5 pr-3">{pair.overlap_ratio != null ? pct(pair.overlap_ratio) : '—'}</td>
                          <td className="py-1.5 pr-3">{pair.similarity_level || '—'}</td>
                          <td className="py-1.5">{pair.quarter || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="mt-1 text-sm text-[#748079]">{analysis?.overlap?.reason || '尚无可核验的重叠结果，不能判断是否分散。'}</p>
                )}

                <h4 className={`${label} mt-4`}>风格已知贡献（各基金最新披露期，可能跨期）</h4>
                {styleFactors.length ? (
                  <div className="mt-1 overflow-x-auto"><table className="w-full text-sm">
                    <thead><tr className="border-b border-[#e4e9e5] text-left text-xs text-[#748079]"><th className="py-2">因子 / 单位</th><th>已知加权贡献</th><th>因子覆盖权重</th><th>披露期</th></tr></thead><tbody>
                    {styleFactors.map((factor) => (
                      <tr key={factor.factor} className="border-b border-[#f0f4f1]">
                        <td className="py-2 pr-3">{factor.label} · {factor.unit || '单位未提供'}</td>
                        <td className="pr-3 tabular-nums">{factor.status === 'incomparable_units' ? '单位不一致，不能聚合' : factor.weighted_exposure != null && Number.isFinite(factor.weighted_exposure) ? factor.weighted_exposure.toFixed(3) : '—'}</td>
                        <td className="pr-3 tabular-nums">{pct(factor.coverage)}</td>
                        <td>{factor.quarters?.length ? factor.quarters.join(' / ') : '未提供'}{factor.undated ? ' · 含未知期' : ''}</td>
                      </tr>
                    ))}
                    </tbody></table></div>
                ) : (
                  <p className="mt-1 text-sm text-[#748079]">{analysis?.style_aggregate?.reason || '尚无可核验的风格聚合结果。'}</p>
                )}
                {analysis?.style_aggregate?.status === 'available' ? (
                  <p className="mt-2 text-xs text-[#748079]">服务报告的基金快照覆盖权重 {pct(analysis.style_aggregate.coverage)}，不是底层资产穿透率。因子未返回覆盖权重或披露期时显示“— / 未提供”，不能解释为全覆盖；已知贡献不补齐未知部分，也不重新归一化。</p>
                ) : null}

                <h4 className={`${label} mt-4`}>复权收益相关性（配对共同区间）</h4>
                {correlationPairs.length ? (
                  <table className="mt-1 w-full text-sm">
                    <thead>
                      <tr className="border-b border-[#e4e9e5] text-left text-xs text-[#748079]">
                        <th className="py-1.5 pr-3">配对</th>
                        <th className="py-1.5 pr-3">相关系数</th>
                        <th className="py-1.5 pr-3">收益区间数</th>
                        <th className="py-1.5">实际样本期</th>
                      </tr>
                    </thead>
                    <tbody>
                      {correlationPairs.map((pair) => (
                        <tr key={`${pair.fund_a}-${pair.fund_b}-corr`} className="border-b border-[#f0f4f1]">
                          <td className="py-1.5 pr-3">{pair.fund_a} × {pair.fund_b}</td>
                          <td className="py-1.5 pr-3">{pair.correlation != null ? pair.correlation.toFixed(4) : pair.status === 'zero_variance' ? '常数序列，未定义' : '样本不足'}</td>
                          <td className="py-1.5 pr-3">{pair.return_intervals ?? '—'}</td>
                          <td className="py-1.5">{pair.start_date || '未知'} → {pair.end_date || '未知'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="mt-1 text-sm text-[#748079]">{analysis?.correlation?.reason || '尚无可核验的相关性结果。'}</p>
                )}
                {analysis?.correlation?.note ? <p className="mt-2 text-xs text-[#748079]">{analysis.correlation.note}</p> : null}

                <p className="mt-4 border-t border-[#f0f4f1] pt-2 text-xs text-[#748079]">{analysis?.boundary}</p>
              </div>

              <div className={card}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="flex items-center gap-1.5 font-semibold text-[#1f2d26]">
                    <LineChart className="h-4 w-4 text-[#28745c]" aria-hidden="true" />
                    基础回测（当前权重回看历史）
                  </h3>
                  <div className="flex items-center gap-2">
                    <select
                      value={backtestLookback}
                      onChange={(event) => { ++backtestRequest.current; setBacktestLookback(Number(event.target.value)); setBacktest(null); setBacktestApplied(null); setBacktestError(''); setBacktestLoading(false) }}
                      className="rounded-lg border border-[#c8d4cb] px-2 py-1.5 text-sm"
                      aria-label="回看窗口"
                    >
                      <option value={365}>回看 365 自然日</option>
                      <option value={730}>回看 730 自然日</option>
                    </select>
                    <button type="button" className={primaryButton} onClick={runBacktest} disabled={backtestLoading || !detail.holdings.length}>
                      {backtestLoading ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
                      ) : (
                        '运行回测'
                      )}
                    </button>
                  </div>
                </div>
                {backtestError ? <p role="alert" className="mt-2 text-sm">{backtestError}</p> : null}
                {!backtest ? (
                  <p className="mt-2 text-sm text-[#748079]">以当前权重合成历史组合净值，输出累计收益/年化/最大回撤/波动，并与分类映射基准对比。样本不足时会明确拒答。</p>
                ) : backtest.status !== 'available' ? (
                  <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">{backtest.reason}</p>
                ) : (
                  <div className="mt-3 space-y-3">
                    <p className="text-xs text-[#748079]">
                      复权净值 · {backtest.sample?.days} 个共同净值点 / {backtest.sample?.return_intervals ?? '未知'} 个收益区间（{backtest.sample?.start_date} → {backtest.sample?.end_date}）；{backtest.weights_basis}
                    </p>
                    <p className="text-xs text-[#748079]">最新共同净值距计算日 {backtest.sample?.data_lag_calendar_days ?? '未知'} 个自然日；区间内剔除非共同日期 {backtest.sample?.omitted_union_dates ?? '未知'} 个。{backtest.metrics?.volatility_note}</p>
                    <div className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                      {[
                        ['累计收益', backtest.metrics?.cumulative_return != null ? pct(backtest.metrics.cumulative_return) : '—'],
                        ['年化收益', backtest.metrics?.annualized_return != null ? pct(backtest.metrics.annualized_return) : '—'],
                        ['最大回撤', backtest.metrics?.max_drawdown != null ? pct(backtest.metrics.max_drawdown) : '—'],
                        ['年化波动', backtest.metrics?.annualized_volatility != null ? pct(backtest.metrics.annualized_volatility) : '—'],
                        ...(backtest.benchmark?.status === 'available' && backtest.benchmark.aligned_to_portfolio === true
                          ? ([
                              ['基准累计（' + (backtest.benchmark.name || backtest.benchmark.code || backtest.benchmark.source) + '）', pct(backtest.benchmark.metrics?.cumulative_return)],
                              ['同区间累计收益差', pct(backtest.benchmark.excess_return)],
                            ] as Array<[string, string]>)
                          : [
                              ['基准对比', backtest.benchmark?.reason || '基准未完成同区间对齐'],
                            ] as Array<[string, string]>),
                      ].map(([key, value]) => (
                        <div key={key} className="flex items-baseline justify-between border-b border-[#f0f4f1] py-1">
                          <span className="text-[#3d5347]">{key}</span>
                          <span className="font-medium text-[#1f2d26]">{value}</span>
                        </div>
                      ))}
                    </div>
                    <div>
                      <h4 className={label}>组合净值曲线（归一化）</h4>
                      <Sparkline series={(backtest.curve || []).map((point) => point.value)} color="#28745c" />
                      <p className="mt-1 text-xs text-[#748079]">
                        含起点 1，共 {(backtest.curve || []).length} 个净值点。{backtest.benchmark?.basis_note || ''}
                      </p>
                    </div>
                  </div>
                )}
                {backtest?.boundary ? (
                  <p className="mt-3 border-t border-[#f0f4f1] pt-2 text-xs text-[#748079]">{backtest.boundary}</p>
                ) : null}
              </div>

              <div className={card}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="flex items-center gap-1.5 font-semibold text-[#1f2d26]">
                    <HeartPulse className="h-4 w-4 text-[#28745c]" aria-hidden="true" />
                    组合监控
                  </h3>
                  <button type="button" className={primaryButton} onClick={runMonitor} disabled={monitorLoading || !detail.holdings.length}>
                    {monitorLoading ? (
                      <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
                    ) : (
                      '运行监控'
                    )}
                  </button>
                </div>
                {monitorError ? <p role="alert" className="mt-2 text-sm">{monitorError}</p> : null}
                {!monitor ? (
                  <p className="mt-2 text-sm text-[#748079]">检查目标配置偏离（同类组权重对比，阈值 5%）与成分风格漂移信号，输出再平衡研究提示。</p>
                ) : (
                  <div className="mt-3 space-y-3">
                    <p className="border-l-2 border-[#28745c] pl-3 text-sm" role="status">
                      {evidence.summary}
                    </p>
                    <p className="text-xs text-[#748079]">风格可判定部分占已保存权重 {pct(evidence.assessedWeight)}；{evidence.missingCodes.length ? `待补证：${evidence.missingCodes.join('、')}` : '无缺失成分不等于无风险'}。未包含账户现金、其他资产或实时风险。</p>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-[#e4e9e5] text-left text-xs text-[#748079]">
                            <th className="py-1.5 pr-3">同类组</th>
                            <th className="py-1.5 pr-3">目标</th>
                            <th className="py-1.5 pr-3">实际</th>
                            <th className="py-1.5 pr-3">偏离</th>
                            <th className="py-1.5">再平衡提示</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(monitor.target_deviations || []).map((item) => (
                            <tr key={item.peer_group_key} className="border-b border-[#f0f4f1]">
                              <td className="py-1.5 pr-3">{item.peer_group_name || item.peer_group_key}</td>
                              <td className="py-1.5 pr-3">{pct(item.target_weight)}</td>
                              <td className="py-1.5 pr-3">{pct(item.actual_weight)}</td>
                              <td className={`py-1.5 pr-3 ${item.deviation != null && item.deviation < 0 ? 'text-[#a05a52]' : ''}`}>{item.deviation != null ? pct(item.deviation) : '—'}</td>
                              <td className="py-1.5">{!evidence.targetAssessable ? '待补证' : item.needs_rebalance ? '偏离超阈值' : '未超阈值'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div>
                      <h4 className={label}>成分风格漂移</h4>
                      <ul className="mt-1 space-y-1 text-sm">
                        {(monitor.style_drifts || []).map((drift) => (
                          <li key={drift.wind_code} className="flex flex-wrap items-baseline gap-2 border-b border-[#f0f4f1] py-1">
                            <span className="font-medium">{drift.wind_code}</span>
                            <span className="text-xs text-[#748079]">{drift.fund_name || ''}</span>
                            <span className={`ml-auto text-xs ${drift.level === 'high' ? 'text-[#a05a52] font-semibold' : drift.level === 'medium' ? 'text-amber-700' : 'text-[#748079]'}`}>
                              {drift.label || drift.status}
                            </span>
                            <span className="w-full text-xs text-[#748079]">{drift.previous_quarter || '起始期未提供'} → {drift.latest_quarter || '结束期未提供'} · {drift.note || '未返回判定依据'}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
                {monitor?.boundary ? (
                  <p className="mt-3 border-t border-[#f0f4f1] pt-2 text-xs text-[#748079]">{monitor.boundary}</p>
                ) : null}
              </div>

              <div className={card}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="flex items-center gap-1.5 font-semibold text-[#1f2d26]">
                    <ClipboardList className="h-4 w-4 text-[#28745c]" aria-hidden="true" />
                    交易清单（研究输出）
                  </h3>
                </div>
                <p className="mt-2 text-sm text-[#748079]">
                  输入完整的当前基金持仓（每行「代码 权重%」，合计 100%），生成与已保存研究组合的差异试算。未知权重不能当作零；不含现金或其他资产，不执行交易。
                </p>
                <div className="mt-3 grid gap-3 md:grid-cols-[1fr_180px]">
                  <textarea
                    value={tradeInput}
                    disabled={tradeLoading}
                    onChange={(event) => { setTradeInput(event.target.value); setTradeList(null); setTradeApplied(null); setTradeError('') }}
                    placeholder={'588000.SH 60\n510310.SH 40'}
                    rows={4}
                    className="w-full rounded-lg border border-[#c8d4cb] px-2 py-1.5 text-sm"
                    aria-label="当前持仓"
                  />
                  <div className="space-y-2">
                    <input
                      value={tradeAmount}
                      disabled={tradeLoading}
                      onChange={(event) => { setTradeAmount(event.target.value); setTradeList(null); setTradeApplied(null); setTradeError('') }}
                      placeholder="总投资金额（元）可选"
                      inputMode="decimal"
                      className="w-full rounded-lg border border-[#c8d4cb] px-2 py-1.5 text-sm"
                      aria-label="总投资金额"
                    />
                    <button type="button" className={`${primaryButton} w-full`} onClick={generateTradeList} disabled={tradeLoading || !detail.holdings.length || !tradeInput.trim()}>
                      {tradeLoading ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
                      ) : (
                        '生成清单'
                      )}
                    </button>
                  </div>
                </div>
                {tradeError ? <p role="alert" className="mt-2 text-sm">{tradeError}</p> : null}
                {tradeList?.status === 'available' && tradeList.items?.length ? (
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-[#e4e9e5] text-left text-xs text-[#748079]">
                          <th className="py-1.5 pr-3">方向</th>
                          <th className="py-1.5 pr-3">基金</th>
                          <th className="py-1.5 pr-3">当前 → 目标</th>
                          <th className="py-1.5 pr-3">金额</th>
                          <th className="py-1.5 pr-3">份额（参考）</th>
                          <th className="py-1.5">净值日</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tradeList.items.map((item) => (
                          <tr key={item.wind_code} className="border-b border-[#f0f4f1]">
                            <td className={`py-1.5 pr-3 font-medium ${item.action === '申购' ? 'text-emerald-800' : 'text-[#a05a52]'}`}>{item.action}</td>
                            <td className="py-1.5 pr-3">
                              <span className="font-medium">{item.wind_code}</span>
                              <span className="ml-2 text-xs text-[#748079]">{item.fund_name || ''}</span>
                            </td>
                            <td className="py-1.5 pr-3">{pct(item.current_weight)} → {pct(item.target_weight)}</td>
                            <td className="py-1.5 pr-3">{item.amount != null ? item.amount.toLocaleString('zh-CN') + ' 元' : '—'}</td>
                            <td className="py-1.5 pr-3">{item.shares != null ? item.shares.toLocaleString('zh-CN') : '—'}</td>
                            <td className="py-1.5 text-xs text-[#748079]">{item.nav_date || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : tradeList?.status === 'available' && Array.isArray(tradeList.items) && !tradeList.items.length ? (
                  <p className="mt-3 text-sm text-[#748079]">在本次输入和差异阈值下，没有生成调整项；不代表实际账户已核对一致。</p>
                ) : tradeList ? (
                  <p role="alert" className="mt-3 text-sm">{tradeList.reason || '证据不足，尚不能生成有效清单。'}</p>
                ) : null}
                {tradeList?.boundary ? (
                  <p className="mt-3 border-t border-[#f0f4f1] pt-2 text-xs text-[#748079]">{tradeList.boundary}</p>
                ) : null}
              </div>
            </>
          )}
        </section>
      </div>
    </fieldset>
  )
}
