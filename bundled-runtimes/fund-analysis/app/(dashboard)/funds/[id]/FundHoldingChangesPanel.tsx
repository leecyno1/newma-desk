import { ArrowDownRight, ArrowUpRight, CircleAlert, RefreshCcw, ShieldCheck } from 'lucide-react'

export type FundHoldingChange = {
  stockCode: string
  stockName: string
  industry: string
  latestWeight: number | null
  previousWeight: number | null
  weightChange: number | null
  changeType: string
}

export type FundHoldingConcentrationPeriod = {
  quarter: string
  reportDate: string
  top3Weight: number | null
  top10Weight: number | null
  topIndustry: string
  topIndustryWeight: number | null
}

export type FundHoldingIndustryChange = {
  industry: string
  latestWeight: number | null
  previousWeight: number | null
  weightChange: number | null
}

export type FundHoldingChanges = {
  status: string
  latestQuarter: string
  previousQuarter: string
  latestReportDate: string
  previousReportDate: string
  weightBasis: string
  changes: FundHoldingChange[]
  concentrationTrend: FundHoldingConcentrationPeriod[]
  industryChanges: FundHoldingIndustryChange[]
  stability: {
    status: string
    level: string
    label: string
    top10OverlapRatio: number | null
    industryOverlapRatio: number | null
    jaccardScore: number | null
    retainedHoldingCount: number
    unionHoldingCount: number
    boundary: string
  }
  summary: {
    enteredTop10Count: number
    exitedTop10Count: number
    largestIncrease: FundHoldingChange | null
    largestDecrease: FundHoldingChange | null
    latestTop3Weight: number | null
    latestTop10Weight: number | null
    top3WeightChange: number | null
    top10WeightChange: number | null
  }
  scope: string
  missingItems: string[]
}

function formatDate(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

function formatWeight(value: number | null) {
  return value == null ? '—' : `${(value * 100).toFixed(2)}%`
}

function formatChange(value: number | null) {
  if (value == null) return '—'
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)} 个百分点`
}

const changeLabels: Record<string, string> = {
  entered_top10: '新进前十大',
  exited_top10: '退出前十大',
  increased: '权重上升',
  decreased: '权重下降',
  stable: '基本稳定',
}

export default function FundHoldingChangesPanel({ snapshot }: { snapshot: FundHoldingChanges }) {
  if (snapshot.status !== 'available') {
    return (
      <section className="border border-dashed border-[#cbd3cd] bg-white px-6 py-8">
        <div className="flex gap-3 text-sm text-[#65716b]"><CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-[#8d6a2f]" /><div><strong>持仓变化待补充</strong><p className="mt-1 text-xs leading-6">{snapshot.missingItems[0] || '至少需要两个季度的公开持仓。'}</p></div></div>
      </section>
    )
  }

  const meaningfulChanges = snapshot.changes.filter((item) => item.changeType !== 'stable').slice(0, 8)
  const basisLabel = snapshot.weightBasis === 'equity_portfolio_weight' ? '占股票市值' : '占基金净值'

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><RefreshCcw className="h-5 w-5 text-[#28745c]" />持仓变化</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">{snapshot.previousQuarter} → {snapshot.latestQuarter} · {formatDate(snapshot.previousReportDate)} 至 {formatDate(snapshot.latestReportDate)} · 比较口径：{basisLabel}</p>
        </div>
        <div className="text-xs text-[#738078]">新进前十大 {snapshot.summary.enteredTop10Count} · 退出前十大 {snapshot.summary.exitedTop10Count}</div>
      </div>

      {snapshot.stability.status === 'available' ? (
        <div className="border-b border-[#e1e6e2] bg-[#f4f8f5] p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h3 className="flex items-center gap-2 text-sm font-bold text-[#244f40]"><ShieldCheck className="h-4 w-4" />公开持仓延续性</h3><p className="mt-1 text-[11px] leading-5 text-[#6f7c75]">相邻两期前十大重仓股归一化比较，只用于判断公开组合是否大幅变化。</p></div>
            <span className={`px-2.5 py-1 text-[11px] font-bold ${snapshot.stability.level === 'high' ? 'bg-[#dfeee6] text-[#24634c]' : snapshot.stability.level === 'medium' ? 'bg-[#fff0cd] text-[#805c1c]' : 'bg-[#f5e4df] text-[#8c4b40]'}`}>{snapshot.stability.label}</span>
          </div>
          <div className="mt-4 grid gap-px bg-[#dfe5e0] sm:grid-cols-3">
            <div className="bg-white p-4"><div className="text-[11px] text-[#77827c]">权重重合度</div><strong className="mt-1 block text-lg text-[#1d2923]">{formatWeight(snapshot.stability.top10OverlapRatio)}</strong></div>
            <div className="bg-white p-4"><div className="text-[11px] text-[#77827c]">延续重仓</div><strong className="mt-1 block text-lg text-[#1d2923]">{snapshot.stability.retainedHoldingCount} 只</strong></div>
            <div className="bg-white p-4"><div className="text-[11px] text-[#77827c]">行业重合度</div><strong className="mt-1 block text-lg text-[#1d2923]">{formatWeight(snapshot.stability.industryOverlapRatio)}</strong></div>
          </div>
        </div>
      ) : null}

      <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-2 xl:grid-cols-4">
        <div className="bg-[#f4f8f5] p-5">
          <div className="flex items-center gap-2 text-xs font-bold text-[#28745c]"><ArrowUpRight className="h-4 w-4" />权重上升最多</div>
          <div className="mt-3 text-lg font-bold text-[#1d2923]">{snapshot.summary.largestIncrease?.stockName || '暂无'}</div>
          <div className="mt-1 text-xs text-[#65716b]">{formatChange(snapshot.summary.largestIncrease?.weightChange ?? null)}</div>
        </div>
        <div className="bg-[#fff8f4] p-5">
          <div className="flex items-center gap-2 text-xs font-bold text-[#915248]"><ArrowDownRight className="h-4 w-4" />权重下降最多</div>
          <div className="mt-3 text-lg font-bold text-[#1d2923]">{snapshot.summary.largestDecrease?.stockName || '暂无'}</div>
          <div className="mt-1 text-xs text-[#65716b]">{formatChange(snapshot.summary.largestDecrease?.weightChange ?? null)}</div>
        </div>
        <div className="bg-white p-5">
          <div className="text-xs font-bold text-[#66726c]">前三大集中度</div>
          <div className="mt-3 text-lg font-bold text-[#1d2923]">{formatWeight(snapshot.summary.latestTop3Weight)}</div>
          <div className="mt-1 text-xs text-[#65716b]">较上期 {formatChange(snapshot.summary.top3WeightChange)}</div>
        </div>
        <div className="bg-white p-5">
          <div className="text-xs font-bold text-[#66726c]">前十大集中度</div>
          <div className="mt-3 text-lg font-bold text-[#1d2923]">{formatWeight(snapshot.summary.latestTop10Weight)}</div>
          <div className="mt-1 text-xs text-[#65716b]">较上期 {formatChange(snapshot.summary.top10WeightChange)}</div>
        </div>
      </div>

      {meaningfulChanges.length ? (
        <div className="divide-y divide-[#edf0ed]">
          {meaningfulChanges.map((item) => (
            <div key={item.stockCode} className="grid gap-3 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center">
              <div><div className="font-bold text-[#26342d]">{item.stockName}<span className="ml-2 text-[11px] font-normal text-[#89938e]">{item.stockCode}</span></div><div className="mt-1 text-[11px] text-[#7b8680]">{item.industry || '行业待补'} · {changeLabels[item.changeType] || item.changeType}</div></div>
              <div className="text-xs text-[#65716b]">{formatWeight(item.previousWeight)} → {formatWeight(item.latestWeight)}</div>
              <div className={`text-xs font-bold ${item.weightChange != null && item.weightChange > 0 ? 'text-[#28745c]' : item.weightChange != null && item.weightChange < 0 ? 'text-[#a2574e]' : 'text-[#707a75]'}`}>{formatChange(item.weightChange)}</div>
            </div>
          ))}
        </div>
      ) : <div className="px-6 py-8 text-center text-sm text-[#748079]">最近两期前十大重仓股权重基本稳定。</div>}

      <div className="grid border-t border-[#e1e6e2] lg:grid-cols-2">
        <div className="border-b border-[#e1e6e2] p-5 lg:border-b-0 lg:border-r sm:p-6">
          <h3 className="text-sm font-bold text-[#26342d]">行业配置变化</h3>
          <p className="mt-1 text-[11px] leading-5 text-[#7b8680]">仅汇总前十大重仓股，帮助识别暴露方向变化。</p>
          <div className="mt-4 space-y-3">
            {snapshot.industryChanges.slice(0, 5).map((item) => <div key={item.industry} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 text-xs"><div><strong className="text-[#34443b]">{item.industry}</strong><span className="ml-2 text-[#89938e]">{formatWeight(item.previousWeight)} → {formatWeight(item.latestWeight)}</span></div><span className={`font-bold ${item.weightChange != null && item.weightChange > 0 ? 'text-[#28745c]' : item.weightChange != null && item.weightChange < 0 ? 'text-[#a2574e]' : 'text-[#707a75]'}`}>{formatChange(item.weightChange)}</span></div>)}
          </div>
        </div>
        <div className="p-5 sm:p-6">
          <h3 className="text-sm font-bold text-[#26342d]">集中度趋势</h3>
          <p className="mt-1 text-[11px] leading-5 text-[#7b8680]">观察组合是否越来越集中在少数重仓股。</p>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[420px] text-left text-xs"><thead className="text-[#7b8680]"><tr><th className="pb-2 font-medium">季度</th><th className="pb-2 font-medium">前三大</th><th className="pb-2 font-medium">前十大</th><th className="pb-2 font-medium">第一行业</th></tr></thead><tbody className="divide-y divide-[#edf0ed]">{snapshot.concentrationTrend.map((item) => <tr key={item.quarter}><td className="py-2.5 font-bold text-[#34443b]">{item.quarter}</td><td className="py-2.5">{formatWeight(item.top3Weight)}</td><td className="py-2.5">{formatWeight(item.top10Weight)}</td><td className="py-2.5">{item.topIndustry || '—'} {formatWeight(item.topIndustryWeight)}</td></tr>)}</tbody></table>
          </div>
        </div>
      </div>

      <div className="border-t border-[#e1e6e2] bg-[#fffaf0] px-5 py-3 text-[11px] leading-5 text-[#765d2c]">{snapshot.scope || '这里只比较公开披露的前十大重仓股；权重变化还会受股价涨跌、申购赎回影响，不能直接等同于主动买卖。'}</div>
    </section>
  )
}
