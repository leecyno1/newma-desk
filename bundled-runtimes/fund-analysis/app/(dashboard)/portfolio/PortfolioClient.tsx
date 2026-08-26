'use client'

import { useCallback, useEffect, useState } from 'react'
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
    coverage: number
    coverage_note?: string
    reason?: string
    factors?: Array<{ factor: string; label: string; unit: string | null; weighted_exposure: number }>
  }
  correlation: {
    status: string
    lookback_days: number
    reason?: string
    pairs?: Array<{ fund_a: string; fund_b: string; correlation: number | null; overlap_days: number; status: string }>
  }
  boundary: string
}

type PerfMetrics = {
  cumulative_return: number
  annualized_return: number
  annualized_volatility: number
  max_drawdown: number
  sample_days: number
  start_date: string | null
  end_date: string | null
}

type Backtest = {
  status: string
  reason?: string
  weights_basis?: string
  sample?: { days: number; start_date: string; end_date: string; lookback_days: number }
  metrics?: PerfMetrics
  curve?: Array<{ date: string; value: number }>
  benchmark?: {
    source: string
    source_fund_code?: string
    code?: string | null
    name?: string | null
    status: string
    basis_note?: string
    metrics?: PerfMetrics
    excess_return?: number
  }
  boundary?: string
}

type Monitor = {
  status: string
  summary?: string
  rebalance_threshold?: number
  rebalance_needed?: boolean
  target_deviations?: Array<{
    peer_group_key: string
    peer_group_name: string | null
    target_weight: number
    actual_weight: number
    deviation: number
    needs_rebalance: boolean
  }>
  style_drifts?: Array<{
    wind_code: string
    fund_name: string | null
    status: string
    level: string | null
    label: string | null
    note: string
  }>
  drift_alerts?: Array<{ wind_code: string; level: string | null; label: string | null }>
  boundary?: string
}

type TradeList = {
  status: string
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

  const selectPortfolio = (portfolioId: string) => {
    if (portfolioId === selectedId) return
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
    setNotice('')
    setSelectedId(portfolioId)
  }

  const loadPortfolios = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/portfolios', { cache: 'no-store' })
      const payload = await response.json()
      setPortfolios(payload.data || [])
      if (!selectedId && (payload.data || []).length) {
        setSelectedId(payload.data[0].id)
      }
    } catch (exc) {
      setError(`组合列表加载失败: ${exc}`)
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  const loadDetail = useCallback(async (portfolioId: string) => {
    setLoading(true)
    setError('')
    try {
      const [detailResponse, analysisResponse] = await Promise.all([
        fetch(`/api/portfolios/${portfolioId}`, { cache: 'no-store' }),
        fetch(`/api/portfolios/${portfolioId}/analysis`, { cache: 'no-store' }),
      ])
      if (detailResponse.ok) {
        const payload = await detailResponse.json()
        setDetail(payload)
        setWeightDraft(
          Object.fromEntries(
            (payload.holdings || []).map((item: Holding) => [
              item.wind_code,
              item.weight != null ? (Number(item.weight) * 100).toFixed(1) : '',
            ]),
          ),
        )
      } else {
        setDetail(null)
      }
      setAnalysis(analysisResponse.ok ? await analysisResponse.json() : null)
    } catch (exc) {
      setError(`组合详情加载失败: ${exc}`)
    } finally {
      setLoading(false)
    }
  }, [])

  const beginTargetsEdit = () => {
    const rows: Array<{ key: string; name: string; weight: string }> = (detail?.targets || []).map((item) => ({
      key: item.peer_group_key,
      name: item.peer_group_name || '',
      weight: item.target_weight != null && Number(item.target_weight) > 0 ? (Number(item.target_weight) * 100).toFixed(1) : '',
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
      const targets = targetRows
        .filter((row) => row.key.trim() && row.weight.trim())
        .map((row) => ({
          peer_group_key: row.key.trim(),
          peer_group_name: row.name.trim() || null,
          target_weight: Number(row.weight) / 100,
        }))
      if (targets.some((item) => !(item.target_weight > 0))) {
        throw new Error('目标权重必须为正数（百分比）')
      }
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
      if (monitor) {
        await runMonitor()
      }
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

  const createPortfolio = async () => {
    const name = newName.trim()
    if (!name) return
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
    }
  }

  const addHolding = async () => {
    const code = addCode.trim().toUpperCase()
    if (!code || !selectedId) return
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
    }
  }

  const removeHolding = async (code: string) => {
    if (!selectedId) return
    try {
      const response = await fetch(`/api/portfolios/${selectedId}/holdings/${encodeURIComponent(code)}`, { method: 'DELETE' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || '移除失败')
      setNotice(`${code} 已移出组合。`)
      await loadDetail(selectedId)
      await loadPortfolios()
    } catch (exc) {
      setError(`移除持仓失败: ${exc}`)
    }
  }

  const applyEqualWeights = async () => {
    if (!selectedId) return
    try {
      const response = await fetch(`/api/portfolios/${selectedId}/weights/equal`, { method: 'POST' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || '等权失败')
      setNotice('已按等权设置全部持仓。')
      await loadDetail(selectedId)
    } catch (exc) {
      setError(`等权失败: ${exc}`)
    }
  }

  const saveCustomWeights = async () => {
    if (!selectedId || !detail) return
    const items = detail.holdings
      .map((item) => ({ wind_code: item.wind_code, weight: Number(weightDraft[item.wind_code]) / 100 }))
      .filter((item) => Number.isFinite(item.weight))
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
    } catch (exc) {
      setError(`保存权重失败: ${exc}`)
    }
  }

  const overlapPairs = analysis?.overlap?.pairs || []
  const correlationPairs = analysis?.correlation?.pairs || []
  const styleFactors = analysis?.style_aggregate?.factors || []

  const runBacktest = async () => {
    if (!selectedId) return
    setBacktestLoading(true)
    try {
      const response = await fetch(`/api/portfolios/${selectedId}/backtest?lookback_days=${backtestLookback}`, { cache: 'no-store' })
      setBacktest(response.ok ? await response.json() : null)
    } catch (exc) {
      setError(`回测失败: ${exc}`)
    } finally {
      setBacktestLoading(false)
    }
  }

  const runMonitor = async () => {
    if (!selectedId) return
    setMonitorLoading(true)
    try {
      const response = await fetch(`/api/portfolios/${selectedId}/monitor`, { cache: 'no-store' })
      setMonitor(response.ok ? await response.json() : null)
    } catch (exc) {
      setError(`监控失败: ${exc}`)
    } finally {
      setMonitorLoading(false)
    }
  }

  const generateTradeList = async () => {
    if (!selectedId) return
    const currentPositions = tradeInput
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const parts = line.split(/[,\s，]+/)
        return { wind_code: (parts[0] || '').toUpperCase(), weight: parts[1] != null ? Number(parts[1]) / 100 : undefined }
      })
      .filter((item) => item.wind_code)
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
      setTradeList(response.ok ? await response.json() : null)
    } catch (exc) {
      setError(`交易清单生成失败: ${exc}`)
    } finally {
      setTradeLoading(false)
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-end gap-3">
        <button type="button" className={button} onClick={() => (selectedId ? loadDetail(selectedId) : loadPortfolios())}>
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
        <aside className={card}>
          <h2 className={label}>组合列表</h2>
          <div className="mt-2 flex gap-2">
            <input
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="新组合名称"
              className="min-w-0 flex-1 rounded-lg border border-[#c8d4cb] px-2 py-1.5 text-sm"
            />
            <button type="button" className={primaryButton} onClick={createPortfolio} disabled={!newName.trim()}>
              <Plus className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          <ul className="mt-3 space-y-1">
            {portfolios.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => selectPortfolio(item.id)}
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
            {!portfolios.length && !loading ? (
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
                '选择或创建一个组合开始构建。'
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
                      <span className="text-emerald-800">权重已配置（{pct(detail.weight_summary.total_weight)}）</span>
                    ) : (
                      <span className="text-amber-700">权重未配齐（{pct(detail.weight_summary.total_weight)}），穿透暂按等权</span>
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
                            <tr key={`${row.key}-${index}`} className="border-b border-[#f0f4f1]">
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
                        （需为 100%；留空行保存时忽略；清空全部保存 = 移除目标配置）
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
                    {targetsError ? <p className="mt-2 text-xs text-[#a05a52]">{targetsError}</p> : null}
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
                  <p className="mt-1 text-sm text-[#748079]">{analysis?.overlap?.reason || '至少两只持仓才能比较重叠。'}</p>
                )}

                <h4 className={`${label} mt-4`}>风格暴露聚合（权重加权，最新披露季度）</h4>
                {styleFactors.length ? (
                  <div className="mt-1 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                    {styleFactors.map((factor) => (
                      <div key={factor.factor} className="flex items-baseline justify-between border-b border-[#f0f4f1] py-1">
                        <span className="text-[#3d5347]">{factor.label}</span>
                        <span className="font-medium text-[#1f2d26]">{factor.weighted_exposure.toFixed(3)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-1 text-sm text-[#748079]">{analysis?.style_aggregate?.reason || '暂无风格快照可聚合。'}</p>
                )}
                {analysis?.style_aggregate?.status === 'available' ? (
                  <p className="mt-1 text-xs text-[#748079]">覆盖 {pct(analysis.style_aggregate.coverage)} 权重的持仓；未覆盖部分为残差。</p>
                ) : null}

                <h4 className={`${label} mt-4`}>净值收益率相关性</h4>
                {correlationPairs.length ? (
                  <table className="mt-1 w-full text-sm">
                    <thead>
                      <tr className="border-b border-[#e4e9e5] text-left text-xs text-[#748079]">
                        <th className="py-1.5 pr-3">配对</th>
                        <th className="py-1.5 pr-3">相关系数</th>
                        <th className="py-1.5">重叠天数</th>
                      </tr>
                    </thead>
                    <tbody>
                      {correlationPairs.map((pair) => (
                        <tr key={`${pair.fund_a}-${pair.fund_b}-corr`} className="border-b border-[#f0f4f1]">
                          <td className="py-1.5 pr-3">{pair.fund_a} × {pair.fund_b}</td>
                          <td className="py-1.5 pr-3">{pair.correlation != null ? pair.correlation.toFixed(4) : '样本不足'}</td>
                          <td className="py-1.5">{pair.overlap_days} 天</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="mt-1 text-sm text-[#748079]">{analysis?.correlation?.reason || '至少两只持仓才能计算相关性。'}</p>
                )}

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
                      onChange={(event) => setBacktestLookback(Number(event.target.value))}
                      className="rounded-lg border border-[#c8d4cb] px-2 py-1.5 text-sm"
                      aria-label="回看窗口"
                    >
                      <option value={365}>回看 365 天</option>
                      <option value={730}>回看 730 天</option>
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
                {!backtest ? (
                  <p className="mt-2 text-sm text-[#748079]">以当前权重合成历史组合净值，输出累计收益/年化/最大回撤/波动，并与分类映射基准对比。样本不足时会明确拒答。</p>
                ) : backtest.status !== 'available' ? (
                  <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">{backtest.reason}</p>
                ) : (
                  <div className="mt-3 space-y-3">
                    <p className="text-xs text-[#748079]">
                      样本 {backtest.sample?.days} 天（{backtest.sample?.start_date} → {backtest.sample?.end_date}）；{backtest.weights_basis}
                    </p>
                    <div className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                      {[
                        ['累计收益', backtest.metrics?.cumulative_return != null ? pct(backtest.metrics.cumulative_return) : '—'],
                        ['年化收益', backtest.metrics?.annualized_return != null ? pct(backtest.metrics.annualized_return) : '—'],
                        ['最大回撤', backtest.metrics?.max_drawdown != null ? pct(backtest.metrics.max_drawdown) : '—'],
                        ['年化波动', backtest.metrics?.annualized_volatility != null ? pct(backtest.metrics.annualized_volatility) : '—'],
                        ...(backtest.benchmark?.status === 'available'
                          ? ([
                              ['基准累计（' + (backtest.benchmark.name || backtest.benchmark.code || backtest.benchmark.source) + '）', pct(backtest.benchmark.metrics?.cumulative_return)],
                              ['相对基准超额', pct(backtest.benchmark.excess_return)],
                            ] as Array<[string, string]>)
                          : [
                              ['基准对比', '数据不足（持仓无分类映射基准净值）'],
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
                        起点归一为 1；样本期内共 {(backtest.curve || []).length} 个交易日。{backtest.benchmark?.basis_note || ''}
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
                {!monitor ? (
                  <p className="mt-2 text-sm text-[#748079]">检查目标配置偏离（同类组权重对比，阈值 5%）与成分风格漂移信号，输出再平衡研究提示。</p>
                ) : (
                  <div className="mt-3 space-y-3">
                    <p className={`rounded-lg px-3 py-2 text-sm ${monitor.rebalance_needed ? 'bg-amber-50 text-amber-800' : 'bg-emerald-50 text-emerald-900'}`}>
                      {monitor.summary}
                    </p>
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
                              <td className="py-1.5">{item.needs_rebalance ? '偏离超阈值' : '—'}</td>
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
                  输入当前实际持仓（每行「代码 权重%」，权重可省略），生成从当前持仓到目标组合的申赎建议清单。仅供专业用户自行决策。
                </p>
                <div className="mt-3 grid gap-3 md:grid-cols-[1fr_180px]">
                  <textarea
                    value={tradeInput}
                    onChange={(event) => setTradeInput(event.target.value)}
                    placeholder={'588000.SH 60\n510310.SH 40'}
                    rows={4}
                    className="w-full rounded-lg border border-[#c8d4cb] px-2 py-1.5 text-sm"
                    aria-label="当前持仓"
                  />
                  <div className="space-y-2">
                    <input
                      value={tradeAmount}
                      onChange={(event) => setTradeAmount(event.target.value)}
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
                {tradeList?.items?.length ? (
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
                ) : tradeList ? (
                  <p className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-900">当前持仓与目标组合已一致，无需申赎调整。</p>
                ) : null}
                {tradeList?.boundary ? (
                  <p className="mt-3 border-t border-[#f0f4f1] pt-2 text-xs text-[#748079]">{tradeList.boundary}</p>
                ) : null}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
