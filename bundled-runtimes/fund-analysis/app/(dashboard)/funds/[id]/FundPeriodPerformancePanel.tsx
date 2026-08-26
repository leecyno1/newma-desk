import { CalendarRange, CircleAlert } from 'lucide-react'

export type FundPeriodPerformancePeriod = {
  year: number
  label: string
  isYtd: boolean
  return: number
  requestedStartDate: string
  requestedEndDate: string
  actualStartDate: string
  actualEndDate: string
  observations: number
  expectedObservations: number
  observationCoverage: number
  coverageStatus: string
  returnBasis: string
  sampleStatus: string
  rank: number | null
  peerCount: number
  percentile: number | null
  peerMedianReturn: number | null
  abovePeerMedian: boolean | null
}

export type FundPeriodPerformanceSnapshot = {
  status: string
  navBasis: string
  latestNavDate: string
  peerGroupName: string
  minimumPeerCount: number
  periods: FundPeriodPerformancePeriod[]
  summary: {
    availablePeriodCount: number
    completePeriodCount: number
    positivePeriodCount: number
    peerRankedPeriodCount: number
    abovePeerMedianCount: number
    bestPeriod: { label: string; return: number } | null
    worstPeriod: { label: string; return: number } | null
  }
  boundary: string
  missingItems: string[]
}

function percent(value: number | null, digits = 1) {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${(value * 100).toFixed(digits)}%`
}

function returnTone(value: number | null) {
  if (value == null || value === 0) return 'text-[#4f5d56]'
  return value > 0 ? 'text-[#a04f45]' : 'text-[#24705a]'
}

export default function FundPeriodPerformancePanel({ snapshot }: { snapshot: FundPeriodPerformanceSnapshot }) {
  if (snapshot.status !== 'available' || !snapshot.periods.length) {
    return (
      <section className="border border-[#ded8c8] bg-[#fffaf0] p-5 sm:p-6">
        <div className="flex gap-3 text-[#735f35]">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0" />
          <div><h2 className="text-base font-bold">年度业绩待补</h2><p className="mt-2 text-xs leading-6">{snapshot.missingItems[0] || '自然年度净值覆盖不足。'}</p></div>
        </div>
      </section>
    )
  }

  const summary = snapshot.summary
  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><CalendarRange className="h-5 w-5 text-[#28745c]" />年度业绩</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">按自然年度计算真实{snapshot.navBasis === 'accum_nav' ? '累计净值' : '单位净值'}收益，只与“{snapshot.peerGroupName || '标准同类组待补'}”比较。</p>
        </div>
        <span className="text-xs text-[#7a8580]">净值截至 {snapshot.latestNavDate || '—'}</span>
      </div>

      <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-2 xl:grid-cols-4">
        <div className="bg-white p-5"><div className="text-xs text-[#748079]">完整年度</div><strong className="mt-2 block text-xl text-[#1d2923]">{summary.completePeriodCount} 个</strong><span className="mt-2 block text-[11px] text-[#919a95]">共展示 {summary.availablePeriodCount} 个区间</span></div>
        <div className="bg-white p-5"><div className="text-xs text-[#748079]">取得正收益</div><strong className="mt-2 block text-xl text-[#1d2923]">{summary.positivePeriodCount} / {summary.completePeriodCount || '—'}</strong><span className="mt-2 block text-[11px] text-[#919a95]">仅统计覆盖完整区间</span></div>
        <div className="bg-white p-5"><div className="text-xs text-[#748079]">高于同类中位数</div><strong className="mt-2 block text-xl text-[#1d2923]">{summary.abovePeerMedianCount} / {summary.peerRankedPeriodCount || '—'}</strong><span className="mt-2 block text-[11px] text-[#919a95]">同类样本达到最低门槛</span></div>
        <div className="bg-white p-5"><div className="text-xs text-[#748079]">较好年度</div><strong className={`mt-2 block text-xl ${returnTone(summary.bestPeriod?.return ?? null)}`}>{summary.bestPeriod ? percent(summary.bestPeriod.return) : '—'}</strong><span className="mt-2 block text-[11px] text-[#919a95]">{summary.bestPeriod?.label || '完整年度不足'}</span></div>
      </div>

      <div className="overflow-x-auto border-t border-[#e1e6e2]">
        <table className="w-full min-w-[760px] text-left text-xs">
          <thead className="bg-[#f5f7f5] text-[#75817a]"><tr><th className="px-5 py-3 font-medium">年度</th><th className="px-5 py-3 text-right font-medium">本基金收益</th><th className="px-5 py-3 text-right font-medium">同类中位数</th><th className="px-5 py-3 text-right font-medium">同类名次</th><th className="px-5 py-3 text-right font-medium">净值覆盖</th></tr></thead>
          <tbody className="divide-y divide-[#edf0ed] text-[#4f5d56]">
            {snapshot.periods.map((period) => (
              <tr key={period.year}>
                <td className="px-5 py-4"><strong className="text-[#26342d]">{period.label}</strong><span className="mt-1 block text-[10px] text-[#929b96]">{period.actualStartDate} 至 {period.actualEndDate}</span></td>
                <td className={`px-5 py-4 text-right text-sm font-bold ${returnTone(period.return)}`}>{percent(period.return)}</td>
                <td className={`px-5 py-4 text-right ${returnTone(period.peerMedianReturn)}`}>{percent(period.peerMedianReturn)}</td>
                <td className="px-5 py-4 text-right">{period.rank && period.peerCount ? <><strong className="text-[#26342d]">{period.rank} / {period.peerCount}</strong><span className="mt-1 block text-[10px] text-[#929b96]">有利分位 {period.percentile?.toFixed(0)}%</span></> : <span className="text-[#929b96]">{period.coverageStatus === 'complete' ? '同类样本不足' : '区间不完整'}</span>}</td>
                <td className="px-5 py-4 text-right"><span className={period.coverageStatus === 'complete' ? 'font-bold text-[#28745c]' : 'font-bold text-[#8a6a2c]'}>{period.coverageStatus === 'complete' ? '完整' : '部分'}</span><span className="mt-1 block text-[10px] text-[#929b96]">{period.observations} 个净值日 · {(period.observationCoverage * 100).toFixed(0)}%</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="border-t border-[#e1e6e2] bg-[#fafbf9] px-5 py-3 text-[10px] leading-5 text-[#8a948f]">{snapshot.boundary}</div>
    </section>
  )
}
