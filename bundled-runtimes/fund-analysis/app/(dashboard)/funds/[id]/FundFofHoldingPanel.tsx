import { CircleAlert, ExternalLink, Layers3, ShieldCheck } from 'lucide-react'
import Link from 'next/link'

export type FundFofUnderlyingHolding = {
  sequence: number
  fundCode: string
  matchedFundCode: string
  fundName: string
  navRatio: number | null
  dailyReturn: number | null
  peerGroup: string
  classificationLabel: string
  classificationStatus: string
}

export type FundFofHoldingSnapshot = {
  status: string
  reportDate: string
  holdingCount: number
  disclosedNavRatio: number | null
  holdings: FundFofUnderlyingHolding[]
  professionalProfile: {
    top5NavRatio: number | null
    largestNavRatio: number | null
    concentrationLabel: string
    classifiedFundCount: number
    classificationCoverage: number | null
    dominantClassification: string
    classificationDistribution: Array<{
      category: string
      navRatio: number
      shareOfDisclosed: number
    }>
    doubleFeeStatus: string
    boundary: string
  }
  evidenceGate: {
    status: string
    minimumDisclosedFunds: number
    minimumDisclosedNavRatio: number
    missingItems: string[]
  }
  source: string
  sourceUrl: string
  scope: string
  missingItems: string[]
}

function formatDate(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

function formatPercent(value: number | null) {
  return value == null ? '未披露' : `${value.toFixed(2)}%`
}

function formatDailyReturn(value: number | null) {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

export default function FundFofHoldingPanel({ snapshot }: { snapshot: FundFofHoldingSnapshot }) {
  const gatePassed = snapshot.evidenceGate.status === 'sufficient'

  if (!snapshot.reportDate || !snapshot.holdings.length) {
    return (
      <section className="border border-dashed border-[#cbd3cd] bg-white px-6 py-8">
        <div className="flex gap-3 text-sm text-[#65716b]">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-[#8d6a2f]" />
          <div>
            <strong>FOF 底层基金持仓待同步</strong>
            <p className="mt-1 text-xs leading-6">{snapshot.missingItems[0] || '本地尚无可用的公开底层基金持仓。'}</p>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><Layers3 className="h-5 w-5 text-[#28745c]" />FOF 底层基金</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">报告期 {formatDate(snapshot.reportDate)} · {snapshot.scope || '只展示公开披露范围。'}</p>
        </div>
        {snapshot.sourceUrl ? <a href={snapshot.sourceUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-bold text-[#28745c]">查看原始披露<ExternalLink className="h-3.5 w-3.5" /></a> : null}
      </div>

      <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['公开底层基金', `${snapshot.holdingCount} 只`],
          ['公开净值覆盖', formatPercent(snapshot.disclosedNavRatio)],
          ['前五大占净值', formatPercent(snapshot.professionalProfile.top5NavRatio)],
          ['集中度', snapshot.professionalProfile.concentrationLabel || '待判断'],
        ].map(([label, value]) => (
          <div key={label} className="bg-white p-5">
            <div className="text-xs font-bold text-[#66726c]">{label}</div>
            <div className="mt-2 text-xl font-bold text-[#1d2923]">{value}</div>
          </div>
        ))}
      </div>

      <div className={`flex gap-3 border-t px-5 py-4 text-sm ${gatePassed ? 'border-[#cfe1d7] bg-[#f3f8f5] text-[#285c49]' : 'border-[#ead7aa] bg-[#fff9eb] text-[#775d23]'}`}>
        {gatePassed ? <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" /> : <CircleAlert className="mt-0.5 h-5 w-5 shrink-0" />}
        <div>
          <strong>{gatePassed ? '底层证据门槛已通过' : '底层证据不足'}</strong>
          <p className="mt-1 text-xs leading-6">
            要求至少 {snapshot.evidenceGate.minimumDisclosedFunds} 只底层基金、公开占净值至少 {snapshot.evidenceGate.minimumDisclosedNavRatio.toFixed(0)}%。
            {gatePassed ? '该门槛用于判断 FOF 评价是否可用，不直接加分。' : ` ${snapshot.evidenceGate.missingItems.join('；')}`}
          </p>
        </div>
      </div>

      {snapshot.professionalProfile.classificationDistribution.length ? (
        <div className="border-t border-[#e1e6e2] px-5 py-5 sm:px-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div><h3 className="text-sm font-bold text-[#26342d]">底层基金类别穿透</h3><p className="mt-1 text-[11px] leading-5 text-[#7a8580]">标准分类优先；缺失时按数据库登记类型做宽分类，不根据名称猜测。</p></div>
            <span className="text-xs font-bold text-[#28745c]">已分类权重覆盖 {snapshot.professionalProfile.classificationCoverage == null ? '—' : `${(snapshot.professionalProfile.classificationCoverage * 100).toFixed(1)}%`}</span>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {snapshot.professionalProfile.classificationDistribution.map((item) => (
              <div key={item.category} className="border border-[#e2e6e3] bg-[#fafbfa] px-4 py-3">
                <span className="text-xs text-[#6e7973]">{item.category}</span>
                <strong className="mt-1 block text-base text-[#26342d]">{formatPercent(item.navRatio)}</strong>
                <span className="mt-1 block text-[10px] text-[#929b96]">占已披露底层 {(item.shareOfDisclosed * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] leading-5 text-[#7a8580]">这是底层基金类别分布，不等同于完整股票、债券资产穿透；未匹配部分单列为“未分类”。</p>
        </div>
      ) : null}

      <div className="overflow-x-auto border-t border-[#e1e6e2]">
        <table className="w-full min-w-[620px] text-left text-xs">
          <thead className="bg-[#f5f7f5] text-[#75817a]">
            <tr><th className="px-5 py-3 font-medium">底层基金</th><th className="px-5 py-3 text-right font-medium">占 FOF 净值</th><th className="px-5 py-3 text-right font-medium">披露日涨跌</th></tr>
          </thead>
          <tbody className="divide-y divide-[#edf0ed] text-[#4f5d56]">
            {snapshot.holdings.map((holding) => (
              <tr key={`${holding.sequence}-${holding.fundCode}`}>
                <td className="px-5 py-3">
                  {holding.matchedFundCode ? <Link href={`/funds/${encodeURIComponent(holding.matchedFundCode)}`} className="block font-bold text-[#26342d] hover:text-[#28745c]">{holding.fundName}</Link> : <strong className="block text-[#26342d]">{holding.fundName}</strong>}
                  <span className="mt-1 block text-[10px] text-[#929b96]">{holding.matchedFundCode || holding.fundCode}{holding.peerGroup ? ` · ${holding.peerGroup}` : holding.classificationLabel ? ` · ${holding.classificationLabel}` : ' · 分类待补'}</span>
                </td>
                <td className="px-5 py-3 text-right font-medium">{formatPercent(holding.navRatio)}</td>
                <td className={`px-5 py-3 text-right ${holding.dailyReturn == null ? 'text-[#89938e]' : holding.dailyReturn > 0 ? 'text-[#a04f45]' : holding.dailyReturn < 0 ? 'text-[#24705a]' : ''}`}>{formatDailyReturn(holding.dailyReturn)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="border-t border-[#e1e6e2] bg-[#fffaf0] px-5 py-4 text-[11px] leading-6 text-[#765d2c]">
        <strong>双层费用边界：</strong>{snapshot.professionalProfile.boundary || '未取得全部底层基金费率前，不宣称完整双层费用。'}
      </div>
    </section>
  )
}
