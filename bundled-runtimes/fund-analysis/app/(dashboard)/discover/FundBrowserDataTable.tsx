'use client'

import Link from 'next/link'
import { BookmarkPlus, Check } from 'lucide-react'
import {
  drawdownMetric,
  evidenceCoverage,
  formatAsset,
  formatPercent,
  managerName,
  managerYears,
  peerReturnMetric,
  professionalFundScore,
  professionalPeerGroup,
  professionalPeerGroupId,
  professionalScoreStatus,
  returnMetric,
  sharpeMetric,
  type SimpleFund,
} from '@/lib/simple-fund-view'
import { fundStyleBadge, peerRankLabel } from './fund-browser-view-model'

function ReturnCell({ value, percentile, rank, peerCount }: { value: number | null; percentile: number | null; rank: number | null; peerCount: number | null }) {
  const tone = value != null && value < 0 ? 'text-[#a84d47]' : 'text-[#267257]'
  return (
    <td className="px-4 py-4 text-right">
      <strong className={tone}>{formatPercent(value)}</strong>
      <span className={`mt-1 block text-[10px] ${percentile != null && percentile >= 70 ? 'font-bold text-[#267257]' : 'text-[#7b8680]'}`}>{peerRankLabel(rank, peerCount, percentile)}</span>
    </td>
  )
}

export default function FundBrowserDataTable({
  funds,
  compareCodes,
  peerGroupName,
  onToggleCompare,
  onOpenWatchlist,
}: {
  funds: SimpleFund[]
  compareCodes: string[]
  peerGroupName: (name: string) => string
  onToggleCompare: (fund: SimpleFund) => void
  onOpenWatchlist: (fund: SimpleFund) => void
}) {
  return (
    <div className="overflow-x-auto border-t border-[#dbe1dc]">
      <table className="w-full min-w-[1180px] border-collapse text-left text-sm">
        <thead className="sticky top-[95px] z-10 bg-[#f1f4f1] text-xs text-[#66726c] shadow-[0_1px_0_#dbe1dc]">
          <tr>
            <th className="w-12 px-4 py-3">对比</th><th className="px-4 py-3">基金</th><th className="px-4 py-3">专业同类组 / 风格</th>
            <th className="px-4 py-3 text-right">近 6 月 / 同类</th><th className="px-4 py-3 text-right">近 1 年 / 同类</th><th className="px-4 py-3 text-right">近 3 年 / 同类</th>
            <th className="px-4 py-3 text-right">最大回撤</th><th className="px-4 py-3 text-right">Sharpe</th><th className="px-4 py-3 text-right">专业评分</th>
            <th className="px-4 py-3 text-right">规模</th><th className="px-4 py-3">经理 / 管理年限</th><th className="px-4 py-3 text-right">数据完整度</th><th className="px-4 py-3 text-right">自选</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#e5e9e5]">
          {funds.map((fund) => {
            const selected = compareCodes.includes(fund.windCode)
            const professionalScore = professionalFundScore(fund)
            const classificationReady = Boolean(professionalPeerGroupId(fund))
            const sixMonthReturn = returnMetric(fund, '6m')
            const annualReturn = returnMetric(fund, '1y')
            const threeYearReturn = returnMetric(fund, '3y')
            const sixMonthPeer = peerReturnMetric(fund, '6m')
            const oneYearPeer = peerReturnMetric(fund, '1y')
            const threeYearPeer = peerReturnMetric(fund, '3y')
            const scoreStatus = professionalScoreStatus(fund)
            const evaluationReady = Boolean(fund.evaluationReady ?? professionalScore != null)
            return (
              <tr key={fund.windCode} className={`transition hover:bg-[#f7faf7] ${evaluationReady ? '' : 'bg-[#fcfcfb]'}`}>
                <td className="px-4 py-4"><button type="button" onClick={() => onToggleCompare(fund)} disabled={!selected && (compareCodes.length >= 6 || !classificationReady)} className={`grid h-7 w-7 place-items-center rounded border ${selected ? 'border-[#2c765d] bg-[#2c765d] text-white' : classificationReady ? 'border-[#c7d0ca] text-transparent hover:border-[#2c765d]' : 'cursor-not-allowed border-[#e0e4e1] bg-[#f3f5f3] text-transparent'}`} aria-label={selected ? `移出对比：${fund.name}` : classificationReady ? `加入对比：${fund.name}` : `专业分类待确认：${fund.name}`}><Check className="h-4 w-4" /></button></td>
                <td className="px-4 py-4"><Link href={`/funds/${encodeURIComponent(fund.windCode)}`} className="font-bold text-[#1b2923] hover:text-[#28745c]">{fund.name || fund.windCode}</Link><div className="mt-1 text-xs text-[#7b8680]">{fund.windCode} · 成立 {fund.establishmentDate || '待补'} · 净值 {fund.nav?.toFixed(4) || '—'}</div><span className={`mt-2 inline-flex px-2 py-1 text-[10px] font-bold ${evaluationReady ? 'bg-[#e7f0eb] text-[#28624e]' : classificationReady ? 'bg-[#fff2d9] text-[#805e20]' : 'bg-[#f0f1ef] text-[#68736d]'}`}>{evaluationReady ? '可评价' : classificationReady ? '已分类 · 评价待补' : '待分类'}</span></td>
                <td className="px-4 py-4"><div className="max-w-[14rem] truncate font-medium">{peerGroupName(professionalPeerGroup(fund)) || '专业分类待确认'}</div><div className="mt-1 flex flex-wrap gap-2"><span className="inline-flex rounded-sm bg-[#edf1ed] px-2 py-1 text-xs text-[#5f6b65]">{fundStyleBadge(fund)}</span><span className="inline-flex px-1 py-1 text-xs text-[#8a948f]">{fund.type || '法律类型待补'}</span></div></td>
                <ReturnCell value={sixMonthReturn} percentile={sixMonthPeer.percentile} rank={sixMonthPeer.rank} peerCount={sixMonthPeer.peerCount} />
                <ReturnCell value={annualReturn} percentile={oneYearPeer.percentile} rank={oneYearPeer.rank} peerCount={oneYearPeer.peerCount} />
                <ReturnCell value={threeYearReturn} percentile={threeYearPeer.percentile} rank={threeYearPeer.rank} peerCount={threeYearPeer.peerCount} />
                <td className="px-4 py-4 text-right text-[#8b4f48]">{formatPercent(drawdownMetric(fund))}</td><td className="px-4 py-4 text-right">{sharpeMetric(fund)?.toFixed(2) || '—'}</td>
                <td className="px-4 py-4 text-right"><strong className="text-[#245f4b]">{professionalScore == null ? '—' : professionalScore.toFixed(1)}</strong>{professionalScore != null && scoreStatus === 'partial' ? <span className="mt-1 block text-[10px] text-[#9a7334]">部分评价</span> : null}{professionalScore == null ? <span className="mt-1 block text-[10px] text-[#9a7334]">评价待补</span> : null}</td>
                <td className="px-4 py-4 text-right">{formatAsset(fund.totalAsset)}</td><td className="px-4 py-4"><span className="block">{managerName(fund)}</span><small className="mt-1 block text-xs text-[#7b8680]">{managerYears(fund) == null ? '年限待补' : `${managerYears(fund)?.toFixed(1)} 年`}</small></td>
                <td className="px-4 py-4 text-right"><span className="font-bold">{Math.round(evidenceCoverage(fund))}%</span></td><td className="px-4 py-4 text-right"><button type="button" onClick={() => onOpenWatchlist(fund)} className="inline-flex h-9 items-center gap-2 border border-[#bfc9c2] px-3 text-xs font-bold text-[#315d4c] transition hover:border-[#28745c] hover:bg-[#eef5f1]"><BookmarkPlus className="h-3.5 w-3.5" />加入</button></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
