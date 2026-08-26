'use client'

import Link from 'next/link'
import { ArrowRight, BookmarkPlus, Check } from 'lucide-react'
import {
  evidenceCoverage,
  formatAsset,
  formatPercent,
  managerName,
  peerReturnMetric,
  professionalFundScore,
  professionalPeerGroupId,
  professionalScoreStatus,
  returnMetric,
  type SimpleFund,
} from '@/lib/simple-fund-view'
import {
  fundBrowserSummary,
  fundSelectionExplanation,
  fundStyleBadge,
  peerRankLabel,
  returnWindows,
} from './fund-browser-view-model'

export default function FundBrowserResultCard({
  fund,
  selected,
  compareCount,
  onToggleCompare,
  onOpenWatchlist,
}: {
  fund: SimpleFund
  selected: boolean
  compareCount: number
  onToggleCompare: (fund: SimpleFund) => void
  onOpenWatchlist: (fund: SimpleFund) => void
}) {
  const professionalScore = professionalFundScore(fund)
  const scoreStatus = professionalScoreStatus(fund)
  const evaluationReady = Boolean(fund.evaluationReady ?? professionalScore != null)
  const classificationReady = Boolean(professionalPeerGroupId(fund))
  const summary = fundBrowserSummary(fund)
  const selectionExplanation = fundSelectionExplanation(fund)

  return (
    <article className={`border bg-white p-5 transition hover:border-[#8eb1a3] hover:shadow-[0_12px_30px_rgba(30,59,48,0.08)] ${selected ? 'border-[#28745c] ring-1 ring-[#28745c]' : 'border-[#dbe1dc]'}`}>
      <div className="flex items-start gap-4">
        <button
          type="button"
          onClick={() => onToggleCompare(fund)}
          disabled={!selected && (compareCount >= 6 || !classificationReady)}
          className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center border ${selected ? 'border-[#2c765d] bg-[#2c765d] text-white' : classificationReady ? 'border-[#c7d0ca] text-transparent hover:border-[#2c765d]' : 'cursor-not-allowed border-[#e0e4e1] bg-[#f3f5f3] text-transparent'}`}
          aria-label={selected ? `移出对比：${fund.name}` : `加入对比：${fund.name}`}
        >
          <Check className="h-4 w-4" />
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <Link href={`/funds/${encodeURIComponent(fund.windCode)}`} className="text-base font-bold text-[#1b2923] hover:text-[#28745c]">{fund.name || fund.windCode}</Link>
              <p className="mt-1 text-xs text-[#7b8680]">{fund.windCode} · {managerName(fund)} · {formatAsset(fund.totalAsset)}</p>
            </div>
            <div className="text-right">
              <strong className="text-xl text-[#245f4b]">{professionalScore == null ? '—' : professionalScore.toFixed(1)}</strong>
              <span className="block text-[10px] text-[#7f8984]">专业评分{scoreStatus === 'partial' ? ' · 部分评价' : ''}</span>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
            <span className="bg-[#edf1ed] px-2 py-1 text-[#536159]">{fundStyleBadge(fund)}</span>
            <span className={`px-2 py-1 font-bold ${evaluationReady ? 'bg-[#e7f0eb] text-[#28624e]' : 'bg-[#fff2d9] text-[#805e20]'}`}>{evaluationReady ? '可评价' : '评价待补'}</span>
          </div>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-3 gap-px bg-[#dfe5e0]">
        {returnWindows.map((window) => {
          const value = returnMetric(fund, window.key)
          const peer = peerReturnMetric(fund, window.key)
          return (
            <div key={`${fund.windCode}-${window.key}`} className="bg-[#f7f9f7] px-3 py-3 text-center">
              <span className="block text-[10px] font-bold text-[#78837d]">{window.label}</span>
              <strong className={`mt-1 block text-base ${value != null && value < 0 ? 'text-[#a84d47]' : 'text-[#267257]'}`}>{formatPercent(value)}</strong>
              <small className="mt-1 block text-[10px] text-[#68756e]">{peerRankLabel(peer.rank, peer.peerCount, peer.percentile)}</small>
            </div>
          )
        })}
      </div>

      {selectionExplanation ? (
        <div className="mt-4 border border-[#d9e2dc] bg-[#f8faf8] px-3 py-3">
          <div className="flex items-center justify-between gap-3">
            <strong className="text-xs text-[#315b49]">为什么出现在这里</strong>
            <span className={`text-[10px] font-bold ${selectionExplanation.status === 'matched' ? 'text-[#28745c]' : 'text-[#9a7334]'}`}>{selectionExplanation.status === 'matched' ? '条件已核对' : '部分证据待补'}</span>
          </div>
          <p className="mt-2 text-xs leading-5 text-[#4e5f56]">{selectionExplanation.headline}</p>
          <p className="mt-1 text-[10px] leading-5 text-[#7b8781]">{selectionExplanation.classificationReason}{selectionExplanation.evidenceAsOf ? ` 数据截至 ${selectionExplanation.evidenceAsOf}。` : ''}</p>
          {selectionExplanation.matchedRules.length ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {selectionExplanation.matchedRules.slice(0, 5).map((rule) => <span key={rule.key} className="bg-white px-2 py-1 text-[10px] text-[#5c6a63] ring-1 ring-[#dce4df]">{rule.label}：{rule.actualText || '已通过'}</span>)}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="mt-4 grid gap-2 text-xs leading-5 sm:grid-cols-2">
        <div className="border-l-2 border-[#2e7a5e] bg-[#eef6f1] px-3 py-2 text-[#315e4d]"><strong>亮点：</strong>{summary.highlight}</div>
        <div className="border-l-2 border-[#b57943] bg-[#fff6ec] px-3 py-2 text-[#73512f]"><strong>风险：</strong>{summary.risk}</div>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-[#e4e8e4] pt-4">
        <span className="text-[10px] text-[#818c86]">数据完整度 {Math.round(evidenceCoverage(fund))}% · 成立 {fund.establishmentDate || '待补'}</span>
        <div className="flex gap-2">
          <button type="button" onClick={() => onOpenWatchlist(fund)} className="inline-flex h-9 items-center gap-1.5 border border-[#bfc9c2] px-3 text-xs font-bold text-[#315d4c]"><BookmarkPlus className="h-3.5 w-3.5" />自选</button>
          <Link href={`/funds/${encodeURIComponent(fund.windCode)}`} className="inline-flex h-9 items-center gap-1.5 bg-[#173f35] px-3 text-xs font-bold text-white">查看详情<ArrowRight className="h-3.5 w-3.5" /></Link>
        </div>
      </div>
    </article>
  )
}
