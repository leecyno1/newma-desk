'use client'

import Link from 'next/link'
import { GitCompareArrows, LayoutGrid, Table2, X } from 'lucide-react'

export type FundBrowserViewMode = 'cards' | 'table'

export default function FundBrowserViewControls({
  mode,
  onModeChange,
  compareCount,
  compareHref,
  onClearCompare,
}: {
  mode: FundBrowserViewMode
  onModeChange: (mode: FundBrowserViewMode) => void
  compareCount: number
  compareHref: string
  onClearCompare: () => void
}) {
  return (
    <div className="sticky top-[48px] z-20 -mx-1 flex flex-wrap items-center justify-between gap-3 border-y border-[#d8dfd9] bg-[#f7f9f6]/95 px-3 py-2.5 backdrop-blur">
      <div className="flex items-center gap-2">
        <span className="text-xs font-bold text-[#4e5c55]">结果视图</span>
        <div className="flex border border-[#cbd4ce] bg-white p-0.5" role="group" aria-label="结果视图">
          <button type="button" onClick={() => onModeChange('cards')} aria-pressed={mode === 'cards'} className={`inline-flex h-8 items-center gap-1.5 px-2.5 text-xs font-bold ${mode === 'cards' ? 'bg-[#173f35] text-white' : 'text-[#68756e] hover:bg-[#edf3ef]'}`}><LayoutGrid size={13} aria-hidden="true" />研究卡片</button>
          <button type="button" onClick={() => onModeChange('table')} aria-pressed={mode === 'table'} className={`inline-flex h-8 items-center gap-1.5 px-2.5 text-xs font-bold ${mode === 'table' ? 'bg-[#173f35] text-white' : 'text-[#68756e] hover:bg-[#edf3ef]'}`}><Table2 size={13} aria-hidden="true" />数据表格</button>
        </div>
      </div>
      {compareCount ? (
        <div className="flex items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1.5 bg-[#e7f0eb] px-2.5 py-1.5 font-bold text-[#28624e]"><GitCompareArrows size={13} aria-hidden="true" />已选 {compareCount} 只</span>
          <Link href={compareHref} className="bg-[#173f35] px-3 py-1.5 font-bold text-white">打开比较</Link>
          <button type="button" onClick={onClearCompare} className="grid h-7 w-7 place-items-center border border-[#cbd4ce] bg-white text-[#68756e] hover:bg-[#edf3ef]" aria-label="清空比较"><X size={13} aria-hidden="true" /></button>
        </div>
      ) : <span className="text-[11px] text-[#87928c]">可从结果中选择同类基金进行比较</span>}
    </div>
  )
}
