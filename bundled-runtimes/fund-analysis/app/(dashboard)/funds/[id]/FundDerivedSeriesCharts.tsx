'use client'

import { CircleAlert, Waves } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

export type FundDerivedSeriesSnapshot = {
  status: string
  window: string
  navBasis: string
  historyStart: string
  historyEnd: string
  observations: number
  drawdownSeries: { date: string; drawdown: number | null }[]
  rollingReturnSeries: { date: string; value: number | null }[]
  boundary: string
  missingItems: string[]
}

function percent(value: number | null, digits = 1) {
  return value == null ? '—' : `${(value * 100).toFixed(digits)}%`
}

function signedPercent(value: number | null) {
  return value == null ? '—' : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
}

function formatDate(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

function navBasisLabel(navBasis: string) {
  if (navBasis === 'adj_nav') return '复权净值'
  if (navBasis === 'accum_nav') return '累计净值'
  return '单位净值'
}

const WINDOW_LABELS: Record<string, string> = { '3m': '3 个月', '6m': '6 个月', '1y': '1 年', '3y': '3 年' }

export default function FundDerivedSeriesCharts({ series }: { series: FundDerivedSeriesSnapshot }) {
  const hasDrawdown = series.drawdownSeries.length >= 2
  const hasRolling = series.rollingReturnSeries.length >= 2

  // 短样本可能只是滚动窗口不够：只要回撤轨迹真实可用就照常展示，
  // 滚动图由自己的占位说明，不再因 status 整段隐藏（UAT：短样本回撤隐藏）。
  if (!hasDrawdown && !hasRolling) {
    return (
      <section className="border border-dashed border-[#cbd3cd] bg-white px-6 py-8">
        <div className="flex gap-3 text-sm text-[#65716b]">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-[#8d6a2f]" />
          <div>
            <strong>回撤轨迹与滚动收益待补充</strong>
            <p className="mt-1 text-xs leading-6">{series.missingItems[0] || '净值历史不足，无法绘制水下回撤与滚动收益。'}</p>
          </div>
        </div>
      </section>
    )
  }

  const worstDrawdown = series.drawdownSeries.reduce((min, point) => Math.min(min, point.drawdown ?? 0), 0)
  const rollingValues = series.rollingReturnSeries.map((point) => point.value ?? 0)
  const rollingMin = rollingValues.length ? Math.min(...rollingValues) : 0
  const rollingMax = rollingValues.length ? Math.max(...rollingValues) : 0
  const historyStart = series.historyStart || series.drawdownSeries[0]?.date || series.rollingReturnSeries[0]?.date || ''
  const historyEnd = series.historyEnd || series.drawdownSeries.at(-1)?.date || series.rollingReturnSeries.at(-1)?.date || ''

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><Waves className="h-5 w-5 text-[#28745c]" />回撤轨迹与滚动收益</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">
            左图是净值相对历史前高的水下回撤；右图是任意时点买入后持有{WINDOW_LABELS[series.window] || series.window}的滚动收益。基于真实{navBasisLabel(series.navBasis)}，只描述历史轨迹。
          </p>
        </div>
        <span className="bg-[#edf2ef] px-2.5 py-1 text-[11px] font-bold text-[#5d6a63]">{navBasisLabel(series.navBasis)}口径</span>
      </div>

      <div className="grid gap-px bg-[#e1e6e2] xl:grid-cols-2">
        <div className="bg-white p-5">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="text-sm font-bold text-[#2b3932]">水下回撤轨迹</h3>
            <span className="text-[11px] text-[#919a95]">区间最深 {percent(worstDrawdown)}</span>
          </div>
          {hasDrawdown ? (
            <div className="mt-4 h-[240px] w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 320, height: 240 }}>
                <AreaChart data={series.drawdownSeries} margin={{ top: 8, right: 8, bottom: 4, left: -12 }}>
                  <CartesianGrid stroke="#e6eae6" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" minTickGap={56} tick={{ fontSize: 11, fill: '#718078' }} tickLine={false} axisLine={false} />
                  <YAxis domain={['auto', 0]} tick={{ fontSize: 11, fill: '#718078' }} tickLine={false} axisLine={false} tickFormatter={(value) => `${(Number(value) * 100).toFixed(0)}%`} />
                  <Tooltip labelFormatter={(label) => formatDate(String(label))} formatter={(value) => [percent(Number(value)), '回撤']} />
                  <ReferenceLine y={0} stroke="#c8cfc9" />
                  <Area type="monotone" dataKey="drawdown" stroke="#915248" strokeWidth={1.8} fill="#915248" fillOpacity={0.12} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : <div className="mt-4 grid h-[240px] place-items-center border border-dashed border-[#cdd5cf] text-xs text-[#79847e]">回撤数据不足</div>}
        </div>

        <div className="bg-white p-5">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="text-sm font-bold text-[#2b3932]">滚动 {WINDOW_LABELS[series.window] || series.window} 收益</h3>
            {hasRolling ? <span className="text-[11px] text-[#919a95]">{signedPercent(rollingMin)} ~ {signedPercent(rollingMax)}</span> : null}
          </div>
          {hasRolling ? (
            <div className="mt-4 h-[240px] w-full">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 320, height: 240 }}>
                <LineChart data={series.rollingReturnSeries} margin={{ top: 8, right: 8, bottom: 4, left: -12 }}>
                  <CartesianGrid stroke="#e6eae6" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" minTickGap={56} tick={{ fontSize: 11, fill: '#718078' }} tickLine={false} axisLine={false} />
                  <YAxis domain={['auto', 'auto']} tick={{ fontSize: 11, fill: '#718078' }} tickLine={false} axisLine={false} tickFormatter={(value) => `${(Number(value) * 100).toFixed(0)}%`} />
                  <Tooltip labelFormatter={(label) => formatDate(String(label))} formatter={(value) => [signedPercent(Number(value)), `滚动 ${WINDOW_LABELS[series.window] || series.window} 收益`]} />
                  <ReferenceLine y={0} stroke="#c8cfc9" />
                  <Line type="monotone" dataKey="value" stroke="#176a52" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : <div className="mt-4 grid h-[240px] place-items-center border border-dashed border-[#cdd5cf] px-4 text-center text-xs leading-6 text-[#79847e]">{series.missingItems[0] || '净值点数不足以计算滚动收益'}</div>}
        </div>
      </div>

      <div className="border-t border-[#e1e6e2] bg-[#fafbf9] px-5 py-3 text-[10px] leading-5 text-[#8a948f]">
        {formatDate(historyStart)} 至 {formatDate(historyEnd)} · {series.observations} 个净值日 · {series.boundary}
      </div>
    </section>
  )
}
