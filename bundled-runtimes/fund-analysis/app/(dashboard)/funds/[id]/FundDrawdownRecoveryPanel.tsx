import { CircleAlert, TrendingDown } from 'lucide-react'

export type FundDrawdownEpisode = {
  startDate: string
  troughDate: string
  recoveryDate: string
  depth: number | null
  depthAtEnd: number | null
  declineDays: number
  recoveryDays: number | null
  underwaterDays: number
  status: string
}

export type FundDrawdownRecoverySnapshot = {
  status: string
  label: string
  navBasis: string
  historyStart: string
  historyEnd: string
  observations: number
  currentDrawdown: number | null
  currentUnderwaterDays: number
  worstDrawdown: number | null
  worstPeakDate: string
  worstTroughDate: string
  worstRecoveryDate: string
  worstDeclineDays: number
  worstRecoveryDays: number | null
  longestUnderwaterDays: number
  materialEpisodeCount: number
  recoveredMaterialEpisodeCount: number
  episodes: FundDrawdownEpisode[]
  note: string
  boundary: string
  missingItems: string[]
}

function percent(value: number | null) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function date(value: string) {
  return value || '—'
}

function statusLabel(status: string) {
  if (status === 'deep_unrecovered') return '深度回撤未修复'
  if (status === 'current_drawdown') return '仍在明显回撤'
  if (status === 'minor_drawdown') return '小幅回撤'
  if (status === 'near_high') return '接近历史高位'
  return '证据待补'
}

export default function FundDrawdownRecoveryPanel({ snapshot }: { snapshot: FundDrawdownRecoverySnapshot }) {
  const available = snapshot.status !== 'insufficient_evidence' && snapshot.observations >= 2
  const warning = snapshot.status === 'deep_unrecovered' || snapshot.status === 'current_drawdown'

  if (!available) {
    return (
      <section className="border border-[#ded8c8] bg-[#fffaf0] p-5 sm:p-6">
        <div className="flex gap-3 text-[#735f35]">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <h2 className="text-base font-bold">回撤与修复时间待补</h2>
            <p className="mt-2 text-xs leading-6">{snapshot.missingItems[0] || snapshot.note || '至少需要两个可用净值日。'}</p>
          </div>
        </div>
      </section>
    )
  }

  const metrics = [
    ['当前回撤', percent(snapshot.currentDrawdown), snapshot.currentUnderwaterDays ? `低于前高 ${snapshot.currentUnderwaterDays} 天` : '当前已回到前高附近'],
    ['可见区间最大回撤', percent(snapshot.worstDrawdown), `${date(snapshot.worstPeakDate)} 至 ${date(snapshot.worstTroughDate)}`],
    ['最大回撤下跌用时', `${snapshot.worstDeclineDays} 天`, '从峰值到谷底'],
    ['谷底后修复用时', snapshot.worstRecoveryDays == null ? '尚未修复' : `${snapshot.worstRecoveryDays} 天`, snapshot.worstRecoveryDate ? `恢复于 ${snapshot.worstRecoveryDate}` : '尚未回到原高点'],
  ]

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><TrendingDown className="h-5 w-5 text-[#28745c]" />回撤与修复</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">基于真实{snapshot.navBasis === 'accum_nav' ? '累计净值' : '单位净值'}，统计跌离前高、跌到谷底和恢复至原高点的时间。</p>
        </div>
        <span className={`px-2.5 py-1 text-[11px] font-bold ${warning ? 'bg-[#fbe9e5] text-[#915248]' : 'bg-[#e2f0e8] text-[#1f684e]'}`}>{statusLabel(snapshot.status)}</span>
      </div>

      <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(([label, value, detail]) => (
          <div key={label} className="bg-white p-5">
            <div className="text-xs text-[#748079]">{label}</div>
            <div className={`mt-2 text-xl font-bold ${label.includes('回撤') && value !== '0.0%' ? 'text-[#915248]' : 'text-[#1d2923]'}`}>{value}</div>
            <div className="mt-2 text-[11px] text-[#919a95]">{detail}</div>
          </div>
        ))}
      </div>

      <div className="border-t border-[#e1e6e2] p-5 sm:p-6">
        <p className="text-sm leading-7 text-[#536159]">{snapshot.note}</p>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[10px] text-[#89938e]">
          <span>{snapshot.historyStart} 至 {snapshot.historyEnd}</span>
          <span>{snapshot.observations} 个净值日</span>
          <span>5% 以上回撤 {snapshot.materialEpisodeCount} 次，已修复 {snapshot.recoveredMaterialEpisodeCount} 次</span>
          <span>最长低于前高 {snapshot.longestUnderwaterDays} 天</span>
        </div>
      </div>

      {snapshot.episodes.length ? (
        <div className="border-t border-[#e1e6e2] p-5 sm:p-6">
          <h3 className="text-sm font-bold text-[#2b3932]">较深回撤记录</h3>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-[680px] w-full text-left text-xs">
              <thead className="border-b border-[#dfe5e1] text-[#7b8680]">
                <tr><th className="pb-3 font-medium">峰值</th><th className="pb-3 font-medium">谷底</th><th className="pb-3 font-medium">最大回撤</th><th className="pb-3 font-medium">下跌用时</th><th className="pb-3 font-medium">恢复情况</th><th className="pb-3 font-medium">低于前高</th></tr>
              </thead>
              <tbody className="divide-y divide-[#edf0ed] text-[#4f5d56]">
                {snapshot.episodes.map((episode) => (
                  <tr key={`${episode.startDate}-${episode.troughDate}`}>
                    <td className="py-3">{date(episode.startDate)}</td>
                    <td className="py-3">{date(episode.troughDate)}</td>
                    <td className="py-3 font-bold text-[#915248]">{percent(episode.depth)}</td>
                    <td className="py-3">{episode.declineDays} 天</td>
                    <td className="py-3">{episode.recoveryDate ? `${episode.recoveryDays} 天，${episode.recoveryDate}` : '尚未修复'}</td>
                    <td className="py-3">{episode.underwaterDays} 天</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      <div className="border-t border-[#e1e6e2] bg-[#fafbf9] px-5 py-3 text-[10px] leading-5 text-[#8a948f]">{snapshot.boundary}</div>
    </section>
  )
}
