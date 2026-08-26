import { Building2, CircleAlert, ExternalLink, UsersRound } from 'lucide-react'

export type FundHolderStructureRow = {
  reportDate: string
  institutionRatio: number | null
  individualRatio: number | null
  internalRatio: number | null
  totalSharesYi: number | null
  source: string
  sourceUrl: string
}

export type FundHolderStructureComparison = {
  previousReportDate: string
  institutionRatioChange: number | null
  individualRatioChange: number | null
  internalRatioChange: number | null
  totalSharesYiChange: number | null
}

export type FundHolderStructureSnapshot = {
  status: string
  latest: FundHolderStructureRow | null
  previous: FundHolderStructureRow | null
  comparison: FundHolderStructureComparison | null
  history: FundHolderStructureRow[]
  source: string
  sourceUrl: string
  scope: string
  internalRatioNote: string
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

function formatShares(value: number | null) {
  return value == null ? '未披露' : `${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 亿份`
}

function formatRatioChange(value: number | null) {
  if (value == null) return '—'
  const points = value * 100
  return `${points > 0 ? '+' : ''}${points.toFixed(2)} 个百分点`
}

function formatSharesChange(value: number | null) {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(2)} 亿份`
}

export default function FundHolderStructurePanel({ snapshot }: { snapshot: FundHolderStructureSnapshot }) {
  const latest = snapshot.latest
  const comparison = snapshot.comparison

  if (!latest) {
    return (
      <section className="border border-dashed border-[#cbd3cd] bg-white px-6 py-8">
        <div className="flex gap-3 text-sm text-[#65716b]">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-[#8d6a2f]" />
          <div><strong>持有人结构待补充</strong><p className="mt-1 text-xs leading-6">{snapshot.missingItems[0] || '公开披露暂未返回持有人结构。'}</p></div>
        </div>
      </section>
    )
  }

  const institutionWidth = Math.max(0, Math.min(100, (latest.institutionRatio || 0) * 100))
  const individualWidth = Math.max(0, Math.min(100 - institutionWidth, (latest.individualRatio || 0) * 100))

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><UsersRound className="h-5 w-5 text-[#28745c]" />持有人结构</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">天天基金 / 东方财富公开披露 · 报告期 {formatDate(latest.reportDate)}。{snapshot.scope}</p>
        </div>
        {snapshot.sourceUrl ? <a href={snapshot.sourceUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-bold text-[#28745c]">查看原始披露<ExternalLink className="h-3.5 w-3.5" /></a> : null}
      </div>

      <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['机构持有', formatRatio(latest.institutionRatio)],
          ['个人持有', formatRatio(latest.individualRatio)],
          ['总份额', formatShares(latest.totalSharesYi)],
          ['内部持有口径', formatRatio(latest.internalRatio)],
        ].map(([label, value]) => <div key={label} className="bg-white p-5"><div className="text-xs font-bold text-[#66726c]">{label}</div><div className="mt-2 text-xl font-bold text-[#1d2923]">{value}</div></div>)}
      </div>

      {latest.institutionRatio != null && latest.individualRatio != null ? (
        <div className="border-t border-[#e1e6e2] p-5 sm:p-6">
          <div className="flex h-3 overflow-hidden bg-[#edf0ed]" aria-label="机构和个人持有比例">
            <div className="bg-[#3a8068]" style={{ width: `${institutionWidth}%` }} />
            <div className="bg-[#aab8b0]" style={{ width: `${individualWidth}%` }} />
          </div>
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-xs text-[#65716b]">
            <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 bg-[#3a8068]" />机构 {formatRatio(latest.institutionRatio)}</span>
            <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 bg-[#aab8b0]" />个人 {formatRatio(latest.individualRatio)}</span>
          </div>
        </div>
      ) : null}

      {comparison ? (
        <div className="grid gap-px border-t border-[#e1e6e2] bg-[#e1e6e2] sm:grid-cols-2">
          <div className="bg-[#f8faf8] p-5"><div className="text-xs text-[#748079]">机构比例较 {formatDate(comparison.previousReportDate)}</div><strong className="mt-2 block text-lg text-[#1d2923]">{formatRatioChange(comparison.institutionRatioChange)}</strong></div>
          <div className="bg-[#f8faf8] p-5"><div className="text-xs text-[#748079]">总份额较 {formatDate(comparison.previousReportDate)}</div><strong className="mt-2 block text-lg text-[#1d2923]">{formatSharesChange(comparison.totalSharesYiChange)}</strong></div>
        </div>
      ) : null}

      {snapshot.history.length > 1 ? (
        <div className="overflow-x-auto border-t border-[#e1e6e2]">
          <table className="w-full min-w-[680px] text-left text-xs">
            <thead className="bg-[#f5f7f5] text-[#75817a]"><tr><th className="px-5 py-3 font-medium">报告期</th><th className="px-5 py-3 font-medium">机构</th><th className="px-5 py-3 font-medium">个人</th><th className="px-5 py-3 font-medium">内部口径</th><th className="px-5 py-3 font-medium">总份额</th></tr></thead>
            <tbody className="divide-y divide-[#edf0ed] text-[#4f5d56]">
              {snapshot.history.slice(0, 5).map((row) => <tr key={row.reportDate}><td className="px-5 py-3 font-medium text-[#26342d]">{formatDate(row.reportDate)}</td><td className="px-5 py-3">{formatRatio(row.institutionRatio)}</td><td className="px-5 py-3">{formatRatio(row.individualRatio)}</td><td className="px-5 py-3">{formatRatio(row.internalRatio)}</td><td className="px-5 py-3">{formatShares(row.totalSharesYi)}</td></tr>)}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="flex gap-3 border-t border-[#eadfbf] bg-[#fffaf0] px-5 py-4 text-xs leading-6 text-[#735b2b]">
        <Building2 className="mt-1 h-4 w-4 shrink-0" />
        <p>{snapshot.internalRatioNote || '“内部持有比例”为数据源披露口径，不等于员工自购。'} 机构和个人比例变化只表示相邻披露期差异，不直接解释为主动申购或赎回。</p>
      </div>
    </section>
  )
}
