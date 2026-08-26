import { CircleAlert, ExternalLink, Layers3, TrendingDown, TrendingUp } from 'lucide-react'

export type FundAssetAllocationRow = {
  reportDate: string
  stockRatio: number | null
  bondRatio: number | null
  cashRatio: number | null
  netAssetYi: number | null
  source: string
  sourceUrl: string
}

export type FundAssetAllocationSnapshot = {
  status: string
  latest: FundAssetAllocationRow | null
  history: FundAssetAllocationRow[]
  scaleTrend: {
    status: string
    label: string
    latestReportDate: string
    latestAssetYi: number | null
    oneYearChange: number | null
    threeYearChange: number | null
    peakAssetYi: number | null
    peakDate: string
    latestFromPeak: number | null
    observations: number
    note: string
    boundary: string
  }
  source: string
  sourceUrl: string
  missingItems: string[]
}

function formatDate(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

function formatRatio(value: number | null) {
  return value == null ? '未披露' : `${(value * 100).toFixed(2)}%`
}

function formatAsset(value: number | null) {
  return value == null ? '未披露' : `${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 亿元`
}

function formatChange(value: number | null) {
  if (value == null) return '待补'
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
}

export default function FundAssetAllocationPanel({ snapshot }: { snapshot: FundAssetAllocationSnapshot }) {
  const latest = snapshot.latest

  if (!latest) {
    return (
      <section className="border border-dashed border-[#cbd3cd] bg-white px-6 py-8">
        <div className="flex gap-3 text-sm text-[#65716b]">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-[#8d6a2f]" />
          <div><strong>资产配置待补充</strong><p className="mt-1 text-xs leading-6">{snapshot.missingItems[0] || '公开定期报告暂未返回资产配置。'}</p></div>
        </div>
      </section>
    )
  }

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><Layers3 className="h-5 w-5 text-[#28745c]" />资产配置</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">基金定期报告披露 · 报告期 {formatDate(latest.reportDate)}。比例均为占基金净值比例。</p>
        </div>
        {snapshot.sourceUrl ? <a href={snapshot.sourceUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-bold text-[#28745c]">查看原始披露<ExternalLink className="h-3.5 w-3.5" /></a> : null}
      </div>

      <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['股票', formatRatio(latest.stockRatio)],
          ['债券', formatRatio(latest.bondRatio)],
          ['现金', formatRatio(latest.cashRatio)],
          ['净资产', formatAsset(latest.netAssetYi)],
        ].map(([label, value]) => <div key={label} className="bg-white p-5"><div className="text-xs font-bold text-[#66726c]">{label}</div><div className="mt-2 text-xl font-bold text-[#1d2923]">{value}</div></div>)}
      </div>

      {snapshot.scaleTrend.status !== 'insufficient_evidence' ? (
        <div className="border-t border-[#e1e6e2] bg-[#f7f9f7] p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-sm font-bold text-[#314139]">
                {snapshot.scaleTrend.oneYearChange != null && snapshot.scaleTrend.oneYearChange < 0
                  ? <TrendingDown className="h-4 w-4 text-[#9a5147]" />
                  : <TrendingUp className="h-4 w-4 text-[#28745c]" />}
                规模趋势：{snapshot.scaleTrend.label}
              </div>
              <p className="mt-2 max-w-4xl text-xs leading-6 text-[#68746e]">{snapshot.scaleTrend.note}</p>
            </div>
            <span className="bg-white px-2.5 py-1 text-[10px] font-bold text-[#65736c]">{snapshot.scaleTrend.observations} 个报告期</span>
          </div>
          <div className="mt-4 grid gap-px bg-[#dfe5e1] sm:grid-cols-3">
            <div className="bg-white px-4 py-3"><span className="text-[10px] text-[#7d8882]">近一年变化</span><strong className="mt-1 block text-sm text-[#33433b]">{formatChange(snapshot.scaleTrend.oneYearChange)}</strong></div>
            <div className="bg-white px-4 py-3"><span className="text-[10px] text-[#7d8882]">近三年变化</span><strong className="mt-1 block text-sm text-[#33433b]">{formatChange(snapshot.scaleTrend.threeYearChange)}</strong></div>
            <div className="bg-white px-4 py-3"><span className="text-[10px] text-[#7d8882]">较历史峰值</span><strong className="mt-1 block text-sm text-[#33433b]">{formatChange(snapshot.scaleTrend.latestFromPeak)}</strong></div>
          </div>
          <p className="mt-3 text-[10px] leading-5 text-[#8a948f]">{snapshot.scaleTrend.boundary}</p>
        </div>
      ) : null}

      {snapshot.history.length > 1 ? (
        <div className="overflow-x-auto border-t border-[#e1e6e2]">
          <table className="w-full min-w-[620px] text-left text-xs">
            <thead className="bg-[#f5f7f5] text-[#75817a]"><tr><th className="px-5 py-3 font-medium">报告期</th><th className="px-5 py-3 font-medium">股票</th><th className="px-5 py-3 font-medium">债券</th><th className="px-5 py-3 font-medium">现金</th><th className="px-5 py-3 font-medium">净资产</th></tr></thead>
            <tbody className="divide-y divide-[#edf0ed] text-[#4f5d56]">
              {snapshot.history.slice(0, 5).map((row) => <tr key={row.reportDate}><td className="px-5 py-3 font-medium text-[#26342d]">{formatDate(row.reportDate)}</td><td className="px-5 py-3">{formatRatio(row.stockRatio)}</td><td className="px-5 py-3">{formatRatio(row.bondRatio)}</td><td className="px-5 py-3">{formatRatio(row.cashRatio)}</td><td className="px-5 py-3">{formatAsset(row.netAssetYi)}</td></tr>)}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
