'use client'

import { BarChart3, CircleAlert } from 'lucide-react'

export type FundManagerTenurePeerMetric = {
  metricName: string
  label: string
  value: number | null
  rank: number | null
  peerCount: number
  percentile: number | null
  sampleStatus: string
}

export type FundManagerTenurePerformance = {
  status: string
  coverageStatus: string
  requestedStartDate: string
  actualStartDate: string
  actualEndDate: string
  requestedTenureDays: number
  metricCoverageDays: number
  coverageRatio: number | null
  observations: number
  totalReturn: number | null
  annualizedReturn: number | null
  maxDrawdown: number | null
  sharpeRatio: number | null
  peerRankingStatus: string
  peerGroupName: string
  validPeerCount: number
  peerMetrics: FundManagerTenurePeerMetric[]
  scopeNote: string
  includedInScore: boolean
}

function formatDate(value: string) {
  if (!value) return '—'
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString('zh-CN')
}

function percent(value: number | null) {
  return value == null ? '—' : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
}

function ratio(value: number | null) {
  return value == null ? '—' : `${(value * 100).toFixed(0)}%`
}

function metricValue(metric: FundManagerTenurePeerMetric) {
  if (metric.value == null) return '—'
  if (['total_return', 'annualized_return', 'max_drawdown', 'record_breaking_days_ratio'].includes(metric.metricName)) {
    return percent(metric.value)
  }
  return metric.value.toFixed(2)
}

export default function FundManagerTenurePerformancePanel({ snapshot }: { snapshot: FundManagerTenurePerformance }) {
  if (snapshot.status === 'unavailable') {
    return (
      <section className="border border-[#dfd8c8] bg-[#fffaf0] p-5 sm:p-6">
        <div className="flex gap-3">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-[#8a6a2c]" />
          <div><h2 className="text-base font-bold text-[#433a27]">现任经理任职期表现待补</h2><p className="mt-2 text-xs leading-6 text-[#786744]">{snapshot.scopeNote || '当前没有足够的任职日期和净值数据。'}</p></div>
        </div>
      </section>
    )
  }

  const fullTenure = snapshot.coverageStatus === 'full_tenure'
  const rankedMetrics = snapshot.peerMetrics.filter((item) => item.rank != null && item.peerCount > 0)

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><BarChart3 className="h-5 w-5 text-[#28745c]" />现任经理任职期表现</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">只使用现任团队上任后的真实净值；多人共管按当前团队最晚上任日计算。</p>
        </div>
        <span className={`px-2.5 py-1 text-[11px] font-bold ${fullTenure ? 'bg-[#e3efe8] text-[#236149]' : 'bg-[#fff0d1] text-[#805b18]'}`}>{fullTenure ? '完整任期' : '本地可见期'}</span>
      </div>

      <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-2 lg:grid-cols-5">
        {[
          ['任期收益', percent(snapshot.totalReturn)],
          ['年化收益', percent(snapshot.annualizedReturn)],
          ['最大回撤', percent(snapshot.maxDrawdown)],
          ['Sharpe', snapshot.sharpeRatio == null ? '—' : snapshot.sharpeRatio.toFixed(2)],
          ['任期覆盖', ratio(snapshot.coverageRatio)],
        ].map(([label, value]) => <div key={label} className="bg-white p-5"><span className="text-[11px] text-[#78837d]">{label}</span><strong className="mt-2 block text-xl text-[#26342d]">{value}</strong></div>)}
      </div>

      <div className="grid gap-px border-t border-[#e1e6e2] bg-[#e1e6e2] sm:grid-cols-2 lg:grid-cols-4">
        <div className="bg-[#f7f9f7] px-5 py-3"><span className="text-[10px] text-[#818b86]">团队上任日</span><strong className="mt-1 block text-sm text-[#34423b]">{formatDate(snapshot.requestedStartDate)}</strong></div>
        <div className="bg-[#f7f9f7] px-5 py-3"><span className="text-[10px] text-[#818b86]">实际净值起点</span><strong className="mt-1 block text-sm text-[#34423b]">{formatDate(snapshot.actualStartDate)}</strong></div>
        <div className="bg-[#f7f9f7] px-5 py-3"><span className="text-[10px] text-[#818b86]">数据截止</span><strong className="mt-1 block text-sm text-[#34423b]">{formatDate(snapshot.actualEndDate)}</strong></div>
        <div className="bg-[#f7f9f7] px-5 py-3"><span className="text-[10px] text-[#818b86]">净值证据</span><strong className="mt-1 block text-sm text-[#34423b]">{snapshot.observations || '—'} 个净值日</strong><span className="mt-1 block text-[10px] text-[#8a948f]">覆盖 {snapshot.metricCoverageDays || '—'} / {snapshot.requestedTenureDays || '—'} 天</span></div>
      </div>

      {rankedMetrics.length ? (
        <div className="border-t border-[#e1e6e2]">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-6"><div><h3 className="text-sm font-bold">同区间同类位置</h3><p className="mt-1 text-[11px] text-[#7b8680]">{snapshot.peerGroupName || '当前专业同类组'} · 有效样本 {snapshot.validPeerCount || rankedMetrics[0].peerCount} 只</p></div></div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-left text-xs"><thead className="bg-[#f5f7f5] text-[#75817a]"><tr><th className="px-5 py-3 font-medium">指标</th><th className="px-5 py-3 text-right font-medium">本基金</th><th className="px-5 py-3 text-right font-medium">同类名次</th><th className="px-5 py-3 text-right font-medium">有利分位</th></tr></thead><tbody className="divide-y divide-[#e7ebe8]">{rankedMetrics.map((metric) => <tr key={metric.metricName}><td className="px-5 py-3 font-semibold text-[#34423b]">{metric.label}</td><td className="px-5 py-3 text-right font-mono">{metricValue(metric)}</td><td className="px-5 py-3 text-right font-mono">{metric.rank} / {metric.peerCount}</td><td className="px-5 py-3 text-right font-mono">{metric.percentile == null ? '—' : `${metric.percentile.toFixed(1)}%`}</td></tr>)}</tbody></table>
          </div>
        </div>
      ) : (
        <div className="border-t border-[#e1e6e2] bg-[#fffaf0] px-5 py-4 text-xs leading-6 text-[#765d2c]">
          <strong>{fullTenure ? '同类排名待补' : '部分覆盖·不排名'}</strong>：{fullTenure ? '当前同区间有效同类样本不足。' : '本地净值明显晚于现任团队上任日，不能把可见期表现冒充完整任期。'}
        </div>
      )}

      <div className="border-t border-[#e1e6e2] bg-[#f7f9f7] px-5 py-3 text-[11px] leading-5 text-[#68746e]">{snapshot.scopeNote}{!snapshot.includedInScore ? ' 该经理任期维度不参与综合评分。' : ''}</div>
    </section>
  )
}
