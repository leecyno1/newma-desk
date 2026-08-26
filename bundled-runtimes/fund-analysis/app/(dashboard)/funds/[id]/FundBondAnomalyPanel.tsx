'use client'

import { Activity, CircleAlert, ExternalLink } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

export type FundBondAnomalyEvent = {
  date: string
  reason: string
  nav: number | null
  dailyReturn: number | null
  lowerBand: number | null
  peerMeanReturn: number | null
  peerThresholdReturn: number | null
  peerCount: number
  marketAdjustment: boolean
}

export type FundBondAnomalyChartPoint = {
  date: string
  navIndex: number | null
  lowerBandIndex: number | null
  peerIndex: number | null
  anomaly: boolean
  marketAdjustment: boolean
}

export type FundBondAnomalySnapshot = {
  windCode: string
  status: string
  asOfDate: string
  dataStart: string
  dataEnd: string
  observations: number
  currentSignal: string
  currentLabel: string
  dailyReturn: number | null
  weeklyReturn: number | null
  marketRegime: string
  marketRegimeLabel: string
  anomalyCounts: Record<string, number>
  events: FundBondAnomalyEvent[]
  chart: FundBondAnomalyChartPoint[]
  peerGroupName: string
  peerFundCount: number
  minimumPeerCount: number
  peerModelReady: boolean
  formalMonitorReady: boolean
  sourceUrl: string
  missingItems: string[]
  limitations: string[]
}

function formatPercent(value: number | null) {
  return value == null ? '—' : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
}

function formatDate(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

function signalTone(signal: string) {
  if (signal === 'abnormal') return 'bg-[#fbe7e3] text-[#91483e]'
  if (signal === 'recent_abnormal') return 'bg-[#fff0d2] text-[#7b5719]'
  return 'bg-[#e1eee7] text-[#246149]'
}

export default function FundBondAnomalyPanel({ snapshot, fundType }: { snapshot: FundBondAnomalySnapshot; fundType: string }) {
  const isBondFund = fundType.includes('债') || fundType.toLowerCase().includes('bond')
  if (!isBondFund) return null

  if (snapshot.status !== 'available') {
    return (
      <section className="border border-dashed border-[#cbd3cd] bg-white px-6 py-8">
        <div className="flex gap-3 text-sm text-[#65716b]">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-[#8d6a2f]" />
          <div><strong>债基净值异常监控待补充</strong><p className="mt-1 text-xs leading-6">{snapshot.missingItems[0] || '净值或同类分类证据不足。'}</p></div>
        </div>
      </section>
    )
  }

  const chart = snapshot.chart.map((point) => ({
    ...point,
    anomalyNavIndex: point.anomaly ? point.navIndex : null,
    dateLabel: point.date.slice(5),
  }))

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><Activity className="h-5 w-5 text-[#28745c]" />债基净值异常监控</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">26日净值下轨 + 债市调整期同类收益门槛。只提示异常复核，不参与基金评分。</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`px-2.5 py-1 text-[11px] font-bold ${signalTone(snapshot.currentSignal)}`}>{snapshot.currentLabel}</span>
          <span className={`px-2.5 py-1 text-[11px] font-bold ${snapshot.marketRegime === 'adjustment' ? 'bg-[#fff0d2] text-[#7b5719]' : 'bg-[#edf2ef] text-[#5d6a63]'}`}>{snapshot.marketRegimeLabel}</span>
          {snapshot.sourceUrl ? <a href={snapshot.sourceUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-bold text-[#28745c]">参考模型<ExternalLink className="h-3.5 w-3.5" /></a> : null}
        </div>
      </div>

      <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['最新日涨跌', formatPercent(snapshot.dailyReturn)],
          ['近1周涨跌', formatPercent(snapshot.weeklyReturn)],
          ['近1月异常日', `${snapshot.anomalyCounts.month || 0} 天`],
          ['近1年异常日', `${snapshot.anomalyCounts.year || 0} 天`],
        ].map(([label, value]) => <div key={label} className="bg-white p-5"><div className="text-xs font-bold text-[#66726c]">{label}</div><div className="mt-2 text-xl font-bold text-[#1d2923]">{value}</div></div>)}
      </div>

      <div className="grid border-t border-[#e1e6e2] xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.7fr)]">
        <div className="min-w-0 p-5 sm:p-6 xl:border-r xl:border-[#e1e6e2]">
          <div className="flex flex-wrap items-end justify-between gap-3"><div><h3 className="text-sm font-bold text-[#26342d]">净值与26日下轨</h3><p className="mt-1 text-[11px] text-[#7d8882]">归一化净值，红点表示触发异常。</p></div><span className="text-[10px] text-[#87918c]">{formatDate(snapshot.dataStart)}—{formatDate(snapshot.dataEnd)}</span></div>
          <div className="mt-4 h-[280px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chart} margin={{ top: 8, right: 10, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="#edf0ed" vertical={false} />
                <XAxis dataKey="dateLabel" tick={{ fontSize: 10, fill: '#7a8580' }} minTickGap={32} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: '#7a8580' }} domain={['auto', 'auto']} width={42} axisLine={false} tickLine={false} />
                <Tooltip formatter={(value, name) => [typeof value === 'number' ? value.toFixed(2) : '—', name === 'navIndex' ? '基金净值' : name === 'lowerBandIndex' ? '26日下轨' : '异常']} labelFormatter={(label) => `日期 ${label}`} />
                <Line type="monotone" dataKey="navIndex" name="基金净值" stroke="#397d66" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="lowerBandIndex" name="26日下轨" stroke="#c59a46" strokeWidth={1.5} strokeDasharray="5 4" dot={false} connectNulls={false} isAnimationActive={false} />
                <Line type="linear" dataKey="anomalyNavIndex" name="异常" stroke="none" dot={{ r: 4, fill: '#b65348', strokeWidth: 0 }} connectNulls={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-[#f8faf8] p-5 sm:p-6">
          <h3 className="text-sm font-bold text-[#26342d]">监控口径</h3>
          <div className="mt-4 space-y-4 text-xs leading-6 text-[#5c6962]">
            <div><strong className="block text-[#26342d]">日常异常</strong>净值低于此前26个净值日均值减2倍标准差。</div>
            <div><strong className="block text-[#26342d]">同类债市调整</strong>{snapshot.peerGroupName || '标准化同类组'}等权指数跌破26日均值减1倍标准差。</div>
            <div><strong className="block text-[#26342d]">调整期异常</strong>基金日收益低于同类均值减3倍标准差。</div>
          </div>
          <p className="mt-5 border-t border-[#dfe5e1] pt-4 text-[11px] leading-6 text-[#7b8680]">当前同类净值样本 {snapshot.peerFundCount} 只，门槛 {snapshot.minimumPeerCount} 只。{snapshot.limitations[0]}</p>
        </div>
      </div>

      <div className="border-t border-[#e1e6e2]">
        <div className="flex items-center justify-between gap-3 px-5 py-4 sm:px-6"><h3 className="text-sm font-bold text-[#26342d]">最近异常记录</h3><span className="text-[10px] text-[#87918c]">最多展示30条 · 截至 {formatDate(snapshot.asOfDate)}</span></div>
        {snapshot.events.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-xs">
              <thead className="bg-[#f5f7f5] text-[#75817a]"><tr><th className="px-5 py-3 font-medium">日期</th><th className="px-5 py-3 font-medium">触发原因</th><th className="px-5 py-3 text-right font-medium">当日涨跌</th><th className="px-5 py-3 text-right font-medium">同类门槛</th><th className="px-5 py-3 text-right font-medium">同类样本</th></tr></thead>
              <tbody className="divide-y divide-[#edf0ed] text-[#4f5d56]">{snapshot.events.slice(0, 10).map((event) => <tr key={`${event.date}-${event.reason}`}><td className="px-5 py-3 font-medium text-[#26342d]">{formatDate(event.date)}</td><td className="px-5 py-3">{event.reason}</td><td className="px-5 py-3 text-right">{formatPercent(event.dailyReturn)}</td><td className="px-5 py-3 text-right">{event.peerThresholdReturn == null ? '—' : formatPercent(event.peerThresholdReturn)}</td><td className="px-5 py-3 text-right">{event.peerCount || '—'} 只</td></tr>)}</tbody>
            </table>
          </div>
        ) : <p className="px-5 pb-6 text-xs leading-6 text-[#66726c] sm:px-6">近1年没有触发净值下轨或调整期同类异常。</p>}
      </div>
    </section>
  )
}
