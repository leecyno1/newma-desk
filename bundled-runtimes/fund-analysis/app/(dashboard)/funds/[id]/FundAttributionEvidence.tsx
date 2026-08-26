'use client'

import Link from 'next/link'
import { ArrowRight, ChartNoAxesCombined, CircleAlert, Clock3, LoaderCircle, Play, RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

type Status = 'ok' | 'partial_evidence' | 'insufficient_evidence' | 'not_applicable'

type AttributionEffect = {
  name: string
  label: string
  value?: number | null
}

type StyleFactor = {
  factor: string
  label?: string
  exposure: number
  unit?: string
  descriptor_coverage?: number
  fund_nav_coverage?: number
}

type PeerStyleFactor = StyleFactor & {
  percentile: number
  percentile_label: string
  sample_size: number
  minimum_peer_count: number
  peer_group_name?: string
  quarter?: string
}

type MarketHoldingProfile = {
  market_code: string
  market_label: string
  holding_count: number
  disclosed_weight: number
  share_of_disclosed: number
  top_three_weight: number
  top_three_share_within_market: number
  security_hhi: number
  industry_hhi: number
  industry_source?: string | null
  industry_as_of_date?: string | null
  industry_exposures?: Array<{
    industry: string
    fund_nav_weight: number
    share_within_market: number
  }>
}

type AttributionBundle = {
  status?: Status
  history_saved?: boolean
  quarter?: string
  holding_snapshot_quarter?: string
  benchmark?: string | null
  benchmark_detail?: {
    benchmark_name?: string
    contract_components?: Array<{ code?: string; name?: string; asset?: string; weight?: number }>
  }
  barra?: {
    status?: Status
    formal_model_ready?: boolean
    descriptor_model_ready?: boolean
    factor_exposures?: StyleFactor[]
    industry_exposures?: Record<string, number>
    holdings_count?: number
    holdings_disclosed_weight?: number
    peer_percentiles?: PeerStyleFactor[]
    style_labels?: string[]
    peer_group?: { name?: string; sample_size?: number; minimum_peer_count?: number }
    public_risk_model?: {
      status?: Status
      is_formal_barra?: boolean
      observations?: number
      fund_nav_coverage?: number
      portfolio_beta?: number
      observed_volatility?: number
      modeled_volatility?: number
      risk_contributions?: Array<{ factor: string; label: string; risk_share?: number | null }>
      missing_items?: string[]
    }
    missing_items?: string[]
  }
  cross_market_holding_profile?: {
    status?: 'available' | Status
    total_disclosed_weight?: number
    markets?: MarketHoldingProfile[]
    labels?: string[]
    boundary?: string
    missing_items?: string[]
  }
  brinson?: {
    status?: Status
    period?: {
      benchmark_weight_date?: string | null
      hong_kong_benchmark_weight_date?: string | null
    }
    returns?: {
      fund?: number | null
      benchmark?: number | null
      active?: number | null
      benchmark_basis?: string
    }
    effects?: AttributionEffect[]
    coverage?: {
      portfolio_holdings?: number
      benchmark_constituents?: number
      holding_returns?: number
    }
    component_evidence?: {
      hong_kong?: {
        status?: 'point_in_time_snapshot' | 'aggregate_only'
        as_of_date?: string | null
        source?: string | null
      }
    }
    missing_items?: string[]
  }
  nav_return_attribution?: {
    status?: 'ok' | 'insufficient_evidence'
  }
}

type AttributionHistoryItem = {
  quarter: string
  holding_quarter?: string | null
  status?: Status
  benchmark_id?: string | null
  active_return?: number | string | null
  updated_at?: string | null
  evidence?: AttributionBundle
}

const statusCopy: Record<Status, { label: string; tone: string }> = {
  ok: { label: '正式结果可用', tone: 'bg-[#e2f0e8] text-[#1f684e]' },
  partial_evidence: { label: '部分证据可用', tone: 'bg-[#fff1d2] text-[#815a16]' },
  insufficient_evidence: { label: '证据不足', tone: 'bg-[#f7e8e4] text-[#944f44]' },
  not_applicable: { label: '当前不适用', tone: 'bg-[#edf0ed] text-[#66726c]' },
}

function formatPercent(value?: number | null, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  const prefix = value > 0 ? '+' : ''
  return `${prefix}${(value * 100).toFixed(digits)}%`
}

function StatusBadge({ status = 'insufficient_evidence' }: { status?: Status }) {
  const copy = statusCopy[status]
  return <span className={`rounded-sm px-2.5 py-1 text-[11px] font-bold ${copy.tone}`}>{copy.label}</span>
}

function formatDateTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace('T', ' ')
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date)
}

function factorValue(item: StyleFactor) {
  if (!Number.isFinite(item.exposure)) return '—'
  if (item.unit === 'cny_100m') return `${item.exposure.toFixed(0)} 亿元`
  if (item.unit === 'ratio') return `${(item.exposure * 100).toFixed(1)}%`
  return item.exposure.toFixed(2)
}

function resultSummary(result: AttributionBundle) {
  const brinson = result.brinson
  if (brinson?.status === 'not_applicable') return brinson.missing_items?.[0] || '当前基金不适用股票行业归因。'
  if (brinson?.status === 'insufficient_evidence') return brinson.missing_items?.[0] || '公开持仓、基准或区间行情不足，暂时无法解释收益来源。'
  const effects = (brinson?.effects || []).filter((item) => item.value != null)
  if (!effects.length) return brinson?.missing_items?.[0] || '公开持仓、基准或区间行情不足，暂时无法解释收益来源。'

  const positive = [...effects].filter((item) => Number(item.value) > 0).sort((a, b) => Number(b.value) - Number(a.value))[0]
  const negative = [...effects].filter((item) => Number(item.value) < 0).sort((a, b) => Number(a.value) - Number(b.value))[0]
  const parts = [`本季度相对基准 ${formatPercent(brinson?.returns?.active)}。`]
  if (positive) parts.push(`已披露部分中，${positive.label}贡献最大（${formatPercent(positive.value)}）。`)
  if (negative) parts.push(`${negative.label}拖累最大（${formatPercent(negative.value)}）。`)
  const coverage = brinson?.coverage?.portfolio_holdings
  if (coverage != null && coverage < 0.8) parts.push(`持仓披露覆盖仅 ${(coverage * 100).toFixed(1)}%，不能视为全组合解释。`)
  return parts.join('')
}

export default function FundAttributionEvidence({
  fundCode,
  fundType,
  fullReportHref,
}: {
  fundCode: string
  fundType: string
  fullReportHref: string
}) {
  const [result, setResult] = useState<AttributionBundle | null>(null)
  const [history, setHistory] = useState<AttributionHistoryItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const industries = useMemo(
    () => Object.entries(result?.barra?.industry_exposures || {}).sort((left, right) => right[1] - left[1]),
    [result],
  )
  const styleFactors = useMemo(
    () => (result?.barra?.factor_exposures || []).filter((item) => Number.isFinite(item.exposure)),
    [result],
  )
  const peerStyleFactors = useMemo(
    () => (result?.barra?.peer_percentiles || []).filter((item) => Number.isFinite(item.percentile)),
    [result],
  )
  const publicRisk = result?.barra?.public_risk_model
  const publicRiskShares = useMemo(
    () => Object.fromEntries((publicRisk?.risk_contributions || []).map((item) => [item.factor, item.risk_share])),
    [publicRisk],
  )
  const marketProfiles = useMemo(
    () => result?.cross_market_holding_profile?.markets || [],
    [result],
  )
  const hongKongProfile = useMemo(
    () => marketProfiles.find((item) => item.market_code === 'HK'),
    [marketProfiles],
  )
  const warnings = useMemo(
    () => Array.from(new Set([...(result?.brinson?.missing_items || []), ...(result?.barra?.missing_items || []), ...(result?.cross_market_holding_profile?.missing_items || [])])).slice(0, 4),
    [result],
  )
  const hasHongKongBenchmark = Boolean(result?.benchmark_detail?.contract_components?.some((item) => item.code === 'HSI' || item.asset === 'hong_kong_equity'))
  const hongKongEvidence = hasHongKongBenchmark ? result?.brinson?.component_evidence?.hong_kong : null

  async function loadHistory() {
    setHistoryLoading(true)
    try {
      const response = await fetch(`/api/attribution/fund/${encodeURIComponent(fundCode)}/history?limit=6`, { cache: 'no-store' })
      const payload = await response.json().catch(() => ({})) as { history?: AttributionHistoryItem[] }
      setHistory(response.ok ? payload.history || [] : [])
    } catch {
      setHistory([])
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    void loadHistory()
  }, [fundCode])

  async function runAttribution() {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`/api/attribution/fund/${encodeURIComponent(fundCode)}`, { cache: 'no-store' })
      const payload = await response.json().catch(() => ({})) as AttributionBundle & { error?: string; detail?: string }
      if (!response.ok) throw new Error(payload.error || payload.detail || '业绩归因运行失败')
      setResult(payload)
      if (payload.history_saved) await loadHistory()
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : '业绩归因运行失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="overflow-hidden border border-[#cad9d1] bg-[#f7faf8]">
      <div className="grid gap-5 border-b border-[#dce5df] p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
        <div>
          <div className="flex flex-wrap items-center gap-2 text-xs font-bold text-[#28745c]"><ChartNoAxesCombined className="h-4 w-4" />收益与风险来源<span className="rounded-sm bg-white px-2 py-1 text-[10px] text-[#6b7771]">现场计算，不影响评分</span></div>
          <h2 className="mt-3 text-xl font-bold text-[#1b2922]">这只基金为什么跑赢或跑输</h2>
          <p className="mt-2 max-w-3xl text-xs leading-6 text-[#68746e]">用上一季度公开持仓解释下一季度收益。Brinson 解释行业配置与选择，Barra 描述子刻画风格，公开持仓模型补充市场与个股风险。</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button type="button" onClick={() => void runAttribution()} disabled={loading} className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-[#173f35] px-5 text-sm font-bold text-white hover:bg-[#225747] disabled:opacity-50">
            {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : result ? <RotateCcw className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            {loading ? '正在核验数据' : result ? '重新运行' : '现场分析收益来源'}
          </button>
          <Link href={fullReportHref} className="inline-flex h-11 items-center gap-2 rounded-md border border-[#9fb6aa] bg-white px-4 text-sm font-bold text-[#285d4b]">完整归因<ArrowRight className="h-4 w-4" /></Link>
        </div>
      </div>

      {error ? <div className="m-5 flex gap-3 border border-[#e3b8ae] bg-[#fff1ee] px-4 py-3 text-sm text-[#8b443a]"><CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />{error}</div> : null}

      {!result ? (
        <div className="grid gap-px bg-[#dfe6e1] sm:grid-cols-3">
          <div className="bg-white p-5"><div className="text-xs font-bold text-[#2e6652]">Brinson</div><p className="mt-2 text-sm font-bold">行业配置与选择</p><p className="mt-2 text-xs leading-6 text-[#707c76]">点击后核验持仓、基准权重和同期收益。</p></div>
          <div className="bg-white p-5"><div className="text-xs font-bold text-[#2e6652]">跨市场持仓</div><p className="mt-2 text-sm font-bold">A 股与港股分开画像</p><p className="mt-2 text-xs leading-6 text-[#707c76]">分别计算市场、行业和集中度，不把港股混入 A 股 Barra 描述子。</p></div>
          <div className="bg-white p-5"><div className="text-xs font-bold text-[#7a5b24]">模型边界</div><p className="mt-2 text-sm font-bold">正式 Barra 仍待接入</p><p className="mt-2 text-xs leading-6 text-[#707c76]">{/[债货币]/u.test(fundType) ? '当前股票 Barra/Brinson 通常不适用于这类基金。' : '公开模型会估计市场与特异风险，但不会冒充商业 Barra。'}</p></div>
        </div>
      ) : (
        <div className="space-y-0">
          <div className="grid gap-px bg-[#dfe6e1] sm:grid-cols-4">
            <div className="bg-white p-4 sm:p-5"><div className="text-[11px] text-[#7a8580]">综合状态</div><div className="mt-3"><StatusBadge status={result.status} /></div><div className="mt-2 text-[11px] text-[#89938e]">{result.history_saved ? '本次分析已留存' : '本次结果未留存'}</div></div>
            <div className="bg-white p-4 sm:p-5"><div className="text-[11px] text-[#7a8580]">归因季度</div><div className="mt-2 text-sm font-bold">{result.quarter || '—'}</div><div className="mt-1 text-[11px] text-[#89938e]">持仓快照 {result.holding_snapshot_quarter || '—'}</div></div>
            <div className="bg-white p-4 sm:p-5"><div className="text-[11px] text-[#7a8580]">比较基准</div><div className="mt-2 text-sm font-bold">{result.benchmark_detail?.benchmark_name || result.benchmark || '缺少基准'}</div><div className="mt-1 text-[11px] text-[#89938e]">{result.brinson?.returns?.benchmark_basis === 'contract_composite' ? '合同复合基准收益' : '行业参照指数收益'}</div></div>
            <div className="bg-white p-4 sm:p-5"><div className="text-[11px] text-[#7a8580]">持仓披露覆盖</div><div className="mt-2 text-sm font-bold">{result.brinson?.coverage?.portfolio_holdings == null ? '—' : `${(result.brinson.coverage.portfolio_holdings * 100).toFixed(1)}%`}</div><div className="mt-1 text-[11px] text-[#89938e]">覆盖越低，结论越局部</div></div>
          </div>

          <div className="grid gap-6 border-t border-[#dfe6e1] bg-white p-5 sm:p-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(20rem,0.75fr)]">
            <div>
              <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-sm font-bold text-[#1d2923]">普通话结论</h3><StatusBadge status={result.brinson?.status} /></div>
              <p className="mt-3 text-sm font-medium leading-7 text-[#35443c]">{resultSummary(result)}</p>
              {result.brinson?.status !== 'insufficient_evidence' && (result.brinson?.effects || []).length ? (
                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  {(result.brinson?.effects || []).map((effect) => (
                    <div key={effect.name} className="border border-[#e1e6e2] bg-[#fafbfa] p-4">
                      <div className="text-xs text-[#707c76]">{effect.label}</div>
                      <div className={`mt-2 text-lg font-bold ${Number(effect.value) > 0 ? 'text-[#236c51]' : Number(effect.value) < 0 ? 'text-[#a04f43]' : 'text-[#526058]'}`}>{formatPercent(effect.value)}</div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="space-y-3">
              <div className="border border-[#dfe5e1] p-4">
                <div className="flex items-center justify-between gap-3"><span className="text-xs font-bold">A 股 Barra 描述子</span><span className={`text-xs font-bold ${result.barra?.descriptor_model_ready ? 'text-[#236c51]' : 'text-[#8a6422]'}`}>{result.barra?.descriptor_model_ready ? '已计算' : '证据不足'}</span></div>
                <p className="mt-2 text-xs leading-6 text-[#6a7670]">{result.barra?.descriptor_model_ready ? (peerStyleFactors.length ? `只使用 A 股持仓，按 ${result.barra.peer_group?.name || '标准同类组'}、同季度 ${result.barra.peer_group?.sample_size || peerStyleFactors[0]?.sample_size} 只基金计算分位。` : '只用真实 A 股重仓股计算原始描述子；港股另列，同类样本不足时不贴风格标签。') : result.barra?.missing_items?.[0] || '缺少 A 股持仓与风格因子输入。'}</p>
                {(result.barra?.style_labels || []).length ? <div className="mt-3 flex flex-wrap gap-2">{result.barra?.style_labels?.map((label) => <span key={label} className="rounded-sm bg-[#e6f0ea] px-2.5 py-1 text-[11px] font-bold text-[#28624e]">{label}</span>)}</div> : null}
                {styleFactors.length ? <div className="mt-3 grid grid-cols-2 gap-2">{styleFactors.map((item) => { const peer = peerStyleFactors.find((candidate) => candidate.factor === item.factor); return <div key={item.factor} className="bg-[#f4f7f5] px-3 py-2"><div className="text-[10px] text-[#78847e]">{item.label || item.factor}</div><div className="mt-1 text-xs font-bold text-[#243c31]">{peer?.percentile_label || '原始描述子'}</div><div className="mt-0.5 text-[10px] text-[#7f8a84]">{factorValue(item)}{peer ? ` · 同类分位 ${(peer.percentile * 100).toFixed(0)}%` : ''}</div></div>})}</div> : null}
                <p className="mt-3 text-[10px] leading-5 text-[#8a6422]">{result.barra?.formal_model_ready ? '完整 Barra 风险模型可用。' : '商业 Barra 因子收益和协方差矩阵尚未接入；下方统计风险模型独立展示，不冒充正式 Barra。'}</p>
              </div>
              {publicRisk?.status === 'partial_evidence' ? (
                <div className="border border-[#dfe5e1] p-4">
                  <div className="flex items-center justify-between gap-3"><span className="text-xs font-bold">公开持仓统计风险</span><span className="text-[11px] font-bold text-[#8a6422]">非正式 Barra</span></div>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <div className="bg-[#f4f7f5] px-3 py-2"><div className="text-[10px] text-[#78847e]">组合 Beta</div><div className="mt-1 text-sm font-bold text-[#243c31]">{publicRisk.portfolio_beta?.toFixed(2) ?? '—'}</div></div>
                    <div className="bg-[#f4f7f5] px-3 py-2"><div className="text-[10px] text-[#78847e]">历史波动</div><div className="mt-1 text-sm font-bold text-[#243c31]">{formatPercent(publicRisk.observed_volatility, 1)}</div></div>
                    <div className="bg-[#f4f7f5] px-3 py-2"><div className="text-[10px] text-[#78847e]">市场风险占比</div><div className="mt-1 text-sm font-bold text-[#243c31]">{formatPercent(publicRiskShares.MARKET, 1)}</div></div>
                    <div className="bg-[#f4f7f5] px-3 py-2"><div className="text-[10px] text-[#78847e]">个股特异风险</div><div className="mt-1 text-sm font-bold text-[#243c31]">{formatPercent(publicRiskShares.SPECIFIC, 1)}</div></div>
                  </div>
                  <p className="mt-3 text-[10px] leading-5 text-[#7a8580]">使用 {publicRisk.observations || 0} 个交易日，覆盖基金净值 {formatPercent(publicRisk.fund_nav_coverage, 1)} 的已披露 A 股持仓。</p>
                </div>
              ) : null}
              {marketProfiles.length ? (
                <div className="border border-[#dfe5e1] p-4">
                  <div className="flex items-center justify-between gap-3"><span className="text-xs font-bold">跨市场公开持仓画像</span><span className="text-[11px] font-bold text-[#236c51]">A/H 分开计算</span></div>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    {marketProfiles.map((market) => (
                      <div key={market.market_code} className="bg-[#f4f7f5] px-3 py-2">
                        <div className="text-[10px] text-[#78847e]">{market.market_label} · {market.holding_count} 只</div>
                        <div className="mt-1 text-sm font-bold text-[#243c31]">占基金净值 {(market.disclosed_weight * 100).toFixed(1)}%</div>
                        <div className="mt-0.5 text-[10px] text-[#7f8a84]">前三大占该市场 {(market.top_three_share_within_market * 100).toFixed(0)}%</div>
                      </div>
                    ))}
                  </div>
                  {(result.cross_market_holding_profile?.labels || []).length ? <div className="mt-3 flex flex-wrap gap-2">{result.cross_market_holding_profile?.labels?.map((label) => <span key={label} className="rounded-sm bg-[#e6f0ea] px-2.5 py-1 text-[11px] font-bold text-[#28624e]">{label}</span>)}</div> : null}
                  {hongKongProfile?.industry_exposures?.length ? <div className="mt-3 text-[11px] leading-5 text-[#607069]">港股行业：{hongKongProfile.industry_exposures.slice(0, 4).map((item) => `${item.industry} ${(item.fund_nav_weight * 100).toFixed(1)}%`).join(' · ')}{hongKongProfile.industry_as_of_date ? ` · 官方分类 ${hongKongProfile.industry_as_of_date}` : ''}</div> : null}
                  <p className="mt-3 text-[10px] leading-5 text-[#8a6422]">{result.cross_market_holding_profile?.boundary}</p>
                </div>
              ) : null}
              <div className="border border-[#dfe5e1] p-4">
                <div className="text-xs font-bold">A 股主要行业暴露</div>
                {industries.length ? <div className="mt-3 flex flex-wrap gap-2">{industries.slice(0, 5).map(([industry, weight]) => <span key={industry} className="rounded-sm bg-[#edf3ef] px-2.5 py-1.5 text-[11px] text-[#3f5b4e]">{industry} {(weight * 100).toFixed(1)}%</span>)}</div> : <p className="mt-2 text-xs leading-6 text-[#7a8580]">A 股 Barra 覆盖门槛未通过；已披露 A 股行业仍可在上方跨市场画像中查看。</p>}
              </div>
              {hongKongEvidence ? (
                <div className="border border-[#dfe5e1] p-4">
                  <div className="flex items-center justify-between gap-3"><span className="text-xs font-bold">港股基准证据</span><span className={`text-[11px] font-bold ${hongKongEvidence.status === 'point_in_time_snapshot' ? 'text-[#236c51]' : 'text-[#8a6422]'}`}>{hongKongEvidence.status === 'point_in_time_snapshot' ? '点时快照' : '仅资产桶'}</span></div>
                  <p className="mt-2 text-xs leading-6 text-[#6a7670]">
                    {hongKongEvidence.status === 'point_in_time_snapshot'
                      ? `使用归因区间开始日前的恒指官方权重快照${hongKongEvidence.as_of_date ? `（${hongKongEvidence.as_of_date}）` : ''}，可进入港股行业级 Brinson。`
                      : '区间开始日前没有恒指权重快照，因此港股只按资产桶处理，不使用事后权重倒推历史归因。'}
                  </p>
                </div>
              ) : null}
              <div className="border border-[#dfe5e1] p-4">
                <div className="flex items-center justify-between gap-3"><span className="text-xs font-bold">净值行为补充</span><span className="text-[11px] font-bold text-[#6d7872]">非 Barra / Brinson</span></div>
                <p className="mt-2 text-xs leading-6 text-[#6a7670]">{result.nav_return_attribution?.status === 'ok' ? '可作为补充解释，但不替代持仓归因。' : '当前净值与基准重叠序列不足，未输出补充结论。'}</p>
              </div>
            </div>
          </div>

          {warnings.length ? <div className="border-t border-[#ead9ae] bg-[#fff9ea] px-5 py-4 text-xs leading-6 text-[#73541c]">{warnings.map((warning) => <div key={warning}>• {warning}</div>)}</div> : null}
        </div>
      )}

      <div className="border-t border-[#dfe6e1] bg-white p-5 sm:p-6">
        <div className="flex items-center gap-2 text-xs font-bold text-[#43584d]"><Clock3 className="h-4 w-4" />最近分析记录</div>
        {historyLoading ? <p className="mt-3 text-xs text-[#7a8580]">正在读取…</p> : history.length ? (
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {history.map((item) => (
              <button key={`${item.quarter}-${item.updated_at || ''}`} type="button" onClick={() => item.evidence && setResult({ ...item.evidence, history_saved: true })} className="border border-[#dfe5e1] bg-[#fafbfa] p-3 text-left hover:border-[#8fac9e] hover:bg-[#f4f8f5]">
                <div className="flex items-center justify-between gap-2"><span className="text-xs font-bold text-[#263c31]">{item.quarter}</span><StatusBadge status={item.status} /></div>
                <div className="mt-2 text-sm font-bold text-[#315f4d]">相对基准 {formatPercent(item.active_return == null ? null : Number(item.active_return))}</div>
                <div className="mt-1 text-[10px] text-[#7c8781]">持仓 {item.holding_quarter || '—'} · {formatDateTime(item.updated_at)}</div>
              </button>
            ))}
          </div>
        ) : <p className="mt-3 text-xs leading-6 text-[#7a8580]">还没有历史记录。运行一次现场分析后会自动留存。</p>}
      </div>
    </section>
  )
}
