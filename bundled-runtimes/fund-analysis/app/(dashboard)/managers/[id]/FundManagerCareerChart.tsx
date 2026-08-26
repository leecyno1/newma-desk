'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { CalendarDays, CircleAlert, FileText, LoaderCircle } from 'lucide-react'

type UnknownRecord = Record<string, unknown>

type Product = {
  fund_code: string
  fund_name: string
  tenure_key?: string
  category?: string
  start_date?: string
  end_date?: string
  is_current?: boolean
  share_codes?: string[]
}

type CurvePoint = {
  date: string
  fund_return: number
  benchmark_return: number | null
}

type CareerEvent = {
  id: string
  date: string
  chart_date?: string
  type: string
  title: string
  summary?: string
  source?: string
}

type CareerPayload = {
  status: string
  reason?: string
  products?: Product[]
  selected_product?: Product & { actual_curve_code?: string }
  period?: string
  period_label?: string
  actual_start_date?: string
  actual_end_date?: string
  available_years?: number[]
  period_options?: { key: string; label: string }[]
  benchmark?: {
    code?: string
    name?: string
    status?: string
    observations?: number
    coverage?: number
  }
  metrics?: UnknownRecord
  peer_ranking?: {
    status?: string
    peer_group_name?: string
    period_start?: string
    period_end?: string
    valid_peer_count?: number
    minimum_peer_count?: number
    metrics?: Record<string, {
        rank?: number
        peer_count?: number
        percentile?: number
        sample_status?: string
      }>
  }
  curve?: CurvePoint[]
  events?: CareerEvent[]
  evidence?: UnknownRecord
  simulation_used?: boolean
}

const BASE_PERIODS = [
  { key: 'tenure', label: '任职以来' },
  { key: 'ytd', label: '今年以来' },
  { key: '3m', label: '近3月' },
  { key: '6m', label: '近6月' },
  { key: '1y', label: '近1年' },
  { key: '3y', label: '近3年' },
  { key: '5y', label: '近5年' },
]

function numberOrNull(value: unknown) {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function percent(value: unknown, digits = 2) {
  const parsed = numberOrNull(value)
  return parsed == null ? '—' : `${(parsed * 100).toFixed(digits)}%`
}

function ratio(value: unknown) {
  const parsed = numberOrNull(value)
  return parsed == null ? '—' : parsed.toFixed(2)
}

function dateText(value?: string) {
  return value ? value.slice(0, 10) : '—'
}

function productTenureKey(product: Product) {
  return product.tenure_key || `${product.fund_code}::${product.start_date || ''}`
}

function parseTenureSelection(value: string) {
  const separator = value.lastIndexOf('::')
  if (separator < 0) return { fundCode: value, tenureStartDate: '' }
  return {
    fundCode: value.slice(0, separator),
    tenureStartDate: value.slice(separator + 2),
  }
}

function metricColor(value: unknown) {
  const parsed = numberOrNull(value)
  if (parsed == null) return 'text-[#26342d]'
  return parsed >= 0 ? 'text-[#267257]' : 'text-[#9a5149]'
}

function peerRankText(metric?: { rank?: number; peer_count?: number; sample_status?: string }) {
  if (metric?.sample_status === 'sufficient' && metric.rank && metric.peer_count) {
    return `${metric.rank} / ${metric.peer_count}`
  }
  if (metric?.sample_status === 'insufficient_peer_sample') return '样本不足'
  return '暂无数据'
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="border border-[#ccd5cf] bg-white px-3 py-2 text-xs shadow-lg">
      <div className="mb-2 font-bold text-[#28352e]">{label}</div>
      {payload.map((item) => (
        <div key={item.name} className="mt-1 flex justify-between gap-6" style={{ color: item.color }}>
          <span>{item.name}</span><strong>{percent(item.value)}</strong>
        </div>
      ))}
    </div>
  )
}

export default function FundManagerCareerChart({ managerId, initialFundCode = '' }: { managerId: string; initialFundCode?: string }) {
  const [payload, setPayload] = useState<CareerPayload | null>(null)
  const [tenureSelection, setTenureSelection] = useState(initialFundCode)
  const [period, setPeriod] = useState('tenure')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      setLoading(true)
      setError('')
      const query = new URLSearchParams({ period })
      const selectedTenure = parseTenureSelection(tenureSelection)
      if (selectedTenure.fundCode) query.set('fund_code', selectedTenure.fundCode)
      if (selectedTenure.tenureStartDate) query.set('tenure_start_date', selectedTenure.tenureStartDate)
      if (period === 'custom') {
        if (!customStart || !customEnd) {
          setLoading(false)
          return
        }
        query.set('start_date', customStart)
        query.set('end_date', customEnd)
      }
      try {
        const response = await fetch(`/api/managers/${encodeURIComponent(managerId)}/career?${query}`, {
          cache: 'no-store',
          signal: controller.signal,
        })
        const result = await response.json()
        if (!response.ok) throw new Error(result.detail || result.error || '获取生涯曲线失败')
        setPayload(result)
        const resolvedSelection = result.selected_product ? productTenureKey(result.selected_product) : ''
        if (!tenureSelection.includes('::') && resolvedSelection) setTenureSelection(resolvedSelection)
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === 'AbortError') return
        setError(caught instanceof Error ? caught.message : '获取生涯曲线失败')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [customEnd, customStart, managerId, period, tenureSelection])

  const products = payload?.products || []
  const metrics = payload?.metrics || {}
  const curve = useMemo(() => payload?.curve || [], [payload?.curve])
  const events = useMemo(() => payload?.events || [], [payload?.events])
  const chartData = useMemo(() => {
    const eventDates = new Set(events.map((event) => event.chart_date).filter(Boolean))
    return curve.map((item) => ({
      ...item,
      event_return: eventDates.has(item.date) ? item.fund_return : null,
    }))
  }, [curve, events])
  const years = payload?.available_years || []
  const benchmarkAvailable = payload?.benchmark?.status === 'available'
  const selected = payload?.selected_product
  const peerRanking = payload?.peer_ranking
  const peerMetrics = [
    ['任期收益', peerRanking?.metrics?.total_return],
    ['创新高占比', peerRanking?.metrics?.record_breaking_days_ratio],
    ['年化收益', peerRanking?.metrics?.annualized_return],
    ['回撤控制', peerRanking?.metrics?.max_drawdown],
    ['夏普比率', peerRanking?.metrics?.sharpe_ratio],
  ] as const

  const cards = [
    ['区间收益', metrics.total_return, 'percent'],
    ['创新高占比', metrics.record_breaking_days_ratio, 'percent'],
    ['基准收益', metrics.benchmark_return, 'percent'],
    ['超额收益', metrics.excess_return, 'percent'],
    ['最大回撤', metrics.max_drawdown, 'percent'],
    ['夏普比率', metrics.sharpe_ratio, 'ratio'],
    ['下行风险', metrics.downside_risk, 'percent'],
    ['年化波动', metrics.annualized_volatility, 'percent'],
    ['索提诺比率', metrics.sortino_ratio, 'ratio'],
  ] as const

  return (
    <section className="border border-[#cfd8d1] bg-white" data-testid="manager-career-chart">
      <div className="border-b border-[#e1e6e2] bg-[#f4f7f4] px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-bold tracking-[0.12em] text-[#28745c]">单产品任期证据</div>
            <h2 className="mt-2 text-2xl font-bold text-[#1f2d26]">基金经理生涯曲线</h2>
            <p className="mt-1 text-sm text-[#68756e]">选择一只真实任职产品查看，不把不同产品拼成经理综合净值；同时提供同区间同类排名，不跨基金类别。</p>
          </div>
          {payload?.simulation_used === false && <span className="bg-[#e8f1ec] px-3 py-1.5 text-xs font-bold text-[#28624e]">真实净值 · 无模拟曲线</span>}
        </div>
        <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(260px,1fr)_auto] lg:items-end">
          <label className="text-xs font-bold text-[#526159]">
            选择产品
            <select
              value={tenureSelection}
              onChange={(event) => { setTenureSelection(event.target.value); setPeriod('tenure') }}
              className="mt-2 block h-11 w-full border border-[#bcc8c0] bg-white px-3 text-sm font-medium text-[#25332c] outline-none focus:border-[#28745c]"
            >
              {products.map((product) => (
                <option key={productTenureKey(product)} value={productTenureKey(product)}>
                  {product.fund_code} {product.fund_name} · {dateText(product.start_date)} 至 {product.is_current ? '今' : dateText(product.end_date)}
                </option>
              ))}
            </select>
          </label>
          <div className="text-xs text-[#6c7872] lg:text-right">
            <div>任职 {dateText(selected?.start_date)} 至 {selected?.is_current ? '今' : dateText(selected?.end_date)}</div>
            <div className="mt-1">{selected?.category || '分类待补'}{selected?.share_codes && selected.share_codes.length > 1 ? ` · 份额 ${selected.share_codes.join(' / ')}` : ''}</div>
          </div>
        </div>
      </div>

      <div className="px-5 py-5 sm:px-6">
        <div className="flex flex-wrap gap-2">
          {BASE_PERIODS.map((option) => (
            <button key={option.key} onClick={() => setPeriod(option.key)} className={`border px-3 py-2 text-xs font-bold ${period === option.key ? 'border-[#28745c] bg-[#28745c] text-white' : 'border-[#d4dcd6] bg-white text-[#57665e]'}`}>
              {option.label}
            </button>
          ))}
          {years.slice(0, 5).map((year) => (
            <button key={year} onClick={() => setPeriod(`year:${year}`)} className={`border px-3 py-2 text-xs font-bold ${period === `year:${year}` ? 'border-[#28745c] bg-[#28745c] text-white' : 'border-[#d4dcd6] bg-white text-[#57665e]'}`}>
              {year}
            </button>
          ))}
          <button onClick={() => setPeriod('custom')} className={`border px-3 py-2 text-xs font-bold ${period === 'custom' ? 'border-[#28745c] bg-[#28745c] text-white' : 'border-[#d4dcd6] bg-white text-[#57665e]'}`}>自定义</button>
        </div>

        {period === 'custom' && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <input type="date" value={customStart} onChange={(event) => setCustomStart(event.target.value)} className="border border-[#c9d2cc] px-3 py-2" />
            <span>至</span>
            <input type="date" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} className="border border-[#c9d2cc] px-3 py-2" />
          </div>
        )}

        {loading ? (
          <div className="flex h-[430px] items-center justify-center text-sm text-[#718078]"><LoaderCircle className="mr-2 h-4 w-4 animate-spin" />加载真实净值...</div>
        ) : error ? (
          <div className="mt-5 flex min-h-64 items-center justify-center border border-[#ecd2a8] bg-[#fff8e9] px-6 text-center text-sm text-[#805e2d]"><CircleAlert className="mr-2 h-4 w-4" />{error}</div>
        ) : payload?.status !== 'available' ? (
          <div className="mt-5 flex min-h-64 items-center justify-center border border-dashed border-[#cbd3cd] bg-[#fafbf9] px-6 text-center text-sm text-[#748079]">该产品所选区间尚无足够真实净值，系统不会生成替代曲线。</div>
        ) : (
          <>
            <div className="mt-5 grid grid-cols-2 gap-px border border-[#dfe5e1] bg-[#dfe5e1] md:grid-cols-4 xl:grid-cols-9">
              {cards.map(([label, value, format]) => (
                <div key={label} className="bg-[#fafbf9] px-3 py-4 text-center">
                  <strong className={`block text-base ${metricColor(value)}`}>{format === 'percent' ? percent(value) : ratio(value)}</strong>
                  <span className="mt-1 block text-[10px] text-[#78847e]">{label}</span>
                </div>
              ))}
            </div>

            <div className="mt-4 border border-[#d8e0da] bg-[#f6f8f5] px-4 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-bold text-[#526159]">同区间同类比较</div>
                  <p className="mt-1 text-xs leading-5 text-[#748079]">只比较标准同类组内、覆盖相同日期区间的真实净值，不跨基金类别。</p>
                </div>
                {peerRanking?.status !== 'sufficient' && (
                  <div className="text-right text-xs text-[#8a6b31]">
                    <strong className="block">暂不排名</strong>
                    <span className="mt-1 block">有效同类 {peerRanking?.valid_peer_count || 0} 只，最低需要 {peerRanking?.minimum_peer_count || 5} 只</span>
                  </div>
                )}
              </div>
              <div className="mt-4 grid grid-cols-2 gap-px bg-[#dfe5e1] md:grid-cols-5">
                {peerMetrics.map(([label, metric]) => (
                  <div key={label} className="bg-white px-3 py-3 text-center">
                    <strong className={metric?.sample_status === 'sufficient' ? 'text-[#28745c]' : 'text-[#8a948f]'}>{peerRankText(metric)}</strong>
                    <span className="mt-1 block text-[10px] text-[#748079]">{label}</span>
                    {numberOrNull(metric?.percentile) != null && metric?.sample_status === 'sufficient' && (
                      <span className="mt-1 block text-[10px] text-[#6d7973]">领先 {Number(metric?.percentile).toFixed(0)}% 同类</span>
                    )}
                  </div>
                ))}
              </div>
              <div className="mt-3 text-[10px] text-[#7b8680]">同类组：{peerRanking?.peer_group_name || selected?.category || '待补'}。创新高占比表示净值在所选区间刷新此前高点的频率；回撤越接近 0 越好，其他指标越高越好。</div>
            </div>

            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-xs text-[#6d7973]">
              <span>{payload.period_label} · {dateText(payload.actual_start_date)} 至 {dateText(payload.actual_end_date)} · {curve.length} 个净值观察</span>
              <span>{benchmarkAvailable ? `基准：${payload.benchmark?.name || payload.benchmark?.code} · 覆盖 ${percent(payload.benchmark?.coverage, 1)}` : `基准曲线：${payload.benchmark?.name || payload.benchmark?.code || '未映射'} · 暂无可核验数据`}</span>
            </div>

            <div className="mt-4 h-[390px] min-w-0 w-full">
              <ResponsiveContainer
                width="100%"
                height="100%"
                minWidth={0}
                minHeight={390}
                initialDimension={{ width: 960, height: 390 }}
              >
                <LineChart data={chartData} margin={{ top: 15, right: 20, left: 5, bottom: 10 }}>
                  <CartesianGrid stroke="#e5e9e6" strokeDasharray="3 4" vertical={false} />
                  <XAxis dataKey="date" minTickGap={48} tick={{ fontSize: 11, fill: '#718078' }} tickLine={false} axisLine={{ stroke: '#d8dfda' }} />
                  <YAxis tickFormatter={(value) => percent(value, 0)} tick={{ fontSize: 11, fill: '#718078' }} tickLine={false} axisLine={false} width={54} />
                  <Tooltip content={<ChartTooltip />} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="fund_return" name="产品收益" stroke="#28745c" strokeWidth={2.4} dot={false} activeDot={{ r: 4 }} />
                  {benchmarkAvailable && <Line type="monotone" dataKey="benchmark_return" name="基准收益" stroke="#c18b3e" strokeWidth={1.8} dot={false} />}
                  <Line type="linear" dataKey="event_return" name="纪要事件" stroke="transparent" connectNulls={false} dot={{ r: 4, fill: '#8a5a9f', stroke: '#fff', strokeWidth: 1.5 }} activeDot={false} legendType="none" />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="mt-5 border-t border-[#e1e6e2] pt-5">
              <div className="flex items-center gap-2 text-sm font-bold text-[#2b3931]"><CalendarDays className="h-4 w-4 text-[#28745c]" />区间纪要事件</div>
              {events.length ? (
                <div className="mt-3 grid gap-3 lg:grid-cols-2">
                  {events.slice(0, 8).map((event) => (
                    <article key={event.id || `${event.date}-${event.title}`} className="border border-[#dce2de] bg-[#fafbf9] p-4">
                      <div className="flex items-center justify-between gap-3 text-[11px] text-[#76827c]"><span>{dateText(event.date)}</span><span>{event.type}</span></div>
                      <h3 className="mt-2 text-sm font-bold text-[#26342d]">{event.title}</h3>
                      {event.summary && <p className="mt-2 line-clamp-2 text-xs leading-5 text-[#68756e]">{event.summary}</p>}
                    </article>
                  ))}
                </div>
              ) : <div className="mt-3 flex items-center gap-2 text-xs text-[#7a8680]"><FileText className="h-4 w-4" />所选区间没有已确认绑定到该经理的纪要。</div>}
            </div>
          </>
        )}
      </div>
    </section>
  )
}
