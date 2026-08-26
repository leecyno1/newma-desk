import { CircleAlert, ExternalLink, Landmark } from 'lucide-react'
import type { FundAssetAllocationSnapshot } from './FundAssetAllocationPanel'

export type FundBondHolding = {
  sequence: number
  bondCode: string
  bondName: string
  bondType: string
  bondTypeLabel: string
  navRatio: number | null
  marketValueWan: number | null
  classificationBasis: string
  issuer: string
  securityBondType: string
  creditRating: string
  ratingType: string
  maturityDate: string
  remainingYears: number | null
  couponRate: number | null
  metadataSource: string
  metadataUrl: string
  metadataStatus: string
}

export type FundBondHoldingBucket = {
  key: string
  label: string
  navRatio: number
  shareOfDisclosed: number | null
  holdingCount: number
}

export type FundBondHoldingPeriod = {
  reportDate: string
  disclosedCount: number
  disclosedNavRatio: number | null
  classifiedNavRatio: number | null
  classificationCoverage: number | null
  dominantType: string
  metadataAvailableCount: number
  metadataCoverage: number | null
  metadataCountCoverage: number | null
  issuerConcentration: {
    issuerCount: number
    coverage: number | null
    topIssuer: { issuer: string; navRatio: number; shareOfDisclosed: number | null; holdingCount: number } | null
    topThreeNavRatio: number
    topThreeShareOfDisclosed: number | null
    issuers: { issuer: string; navRatio: number; shareOfDisclosed: number | null; holdingCount: number }[]
  }
  ratingDistribution: { rating: string; navRatio: number; shareOfRated: number | null; holdingCount: number; ratingTypes: string[] }[]
  ratingCoverage: number | null
  maturityBuckets: { key: string; label: string; navRatio: number; shareOfKnown: number | null; holdingCount: number }[]
  maturityCoverage: number | null
  buckets: FundBondHoldingBucket[]
  holdings: FundBondHolding[]
}

export type FundBondProfessionalProfile = {
  status: string
  label: string
  periodCount: number
  requiredPeriods: number
  averages: {
    rateShare: number | null
    localGovernmentShare: number | null
    financialShare: number | null
    creditShare: number | null
    convertibleShare: number | null
    otherShare: number | null
    highRatingShare: number | null
    bondRatingCoverage: number | null
    issuerRatingCoverage: number | null
    metadataCoverage: number | null
    classificationCoverage: number | null
  }
  periods: {
    reportDate: string
    rateShare: number | null
    localGovernmentShare: number | null
    financialShare: number | null
    creditShare: number | null
    convertibleShare: number | null
    bondRatingCoverage: number | null
    metadataCoverage: number | null
  }[]
  secondaryLabels: string[]
  basis: string
  methodology: string
  limitations: string[]
  formalClassificationReady: boolean
}

export type FundBondHoldingSnapshot = {
  status: string
  latest: FundBondHoldingPeriod | null
  history: FundBondHoldingPeriod[]
  professionalProfile: FundBondProfessionalProfile
  source: string
  sourceUrl: string
  scope: string
  classificationMethod: string
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

function formatMarketValue(value: number | null) {
  if (value == null) return '未披露'
  return `${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 万元`
}

function formatRemainingYears(value: number | null) {
  if (value == null) return '未取得'
  return value < 1 ? `${Math.max(0, value * 12).toFixed(0)} 个月` : `${value.toFixed(1)} 年`
}

export default function FundBondHoldingPanel({ snapshot, fundType, assetAllocation }: { snapshot: FundBondHoldingSnapshot; fundType: string; assetAllocation: FundAssetAllocationSnapshot }) {
  const latest = snapshot.latest
  const profile = snapshot.professionalProfile
  const isBondFund = fundType.includes('债') || fundType.toLowerCase().includes('bond')

  if (!latest) {
    if (!isBondFund) return null
    return (
      <section className="border border-dashed border-[#cbd3cd] bg-white px-6 py-8">
        <div className="flex gap-3 text-sm text-[#65716b]">
          <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-[#8d6a2f]" />
          <div><strong>公开债券持仓待同步</strong><p className="mt-1 text-xs leading-6">{snapshot.missingItems[0] || '本地尚无公开债券持仓。'}</p></div>
        </div>
      </section>
    )
  }

  const matchingAllocation = assetAllocation.history.find((row) => row.reportDate === latest.reportDate)
  const disclosedPortfolioCoverage = matchingAllocation?.bondRatio && latest.disclosedNavRatio != null
    ? latest.disclosedNavRatio / matchingAllocation.bondRatio
    : null

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><Landmark className="h-5 w-5 text-[#28745c]" />公开重仓债券券种结构</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">报告期 {formatDate(latest.reportDate)} · {snapshot.scope}</p>
        </div>
        {snapshot.sourceUrl ? <a href={snapshot.sourceUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-bold text-[#28745c]">查看原始披露<ExternalLink className="h-3.5 w-3.5" /></a> : null}
      </div>

      <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['公开债券', `${latest.disclosedCount} 只`],
          ['债券仓位覆盖', formatRatio(disclosedPortfolioCoverage)],
          ['主数据覆盖', formatRatio(latest.metadataCoverage)],
          ['第一发行主体', latest.issuerConcentration.topIssuer?.issuer || '待取得'],
        ].map(([label, value]) => <div key={label} className="bg-white p-5"><div className="text-xs font-bold text-[#66726c]">{label}</div><div className="mt-2 text-xl font-bold text-[#1d2923]">{value}</div></div>)}
      </div>

      {profile.status === 'available' ? (
        <div className="border-t border-[#e1e6e2] bg-[#f8faf8] p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex flex-wrap items-center gap-2"><h3 className="text-sm font-bold text-[#26342d]">近四期公开债券画像</h3><span className="bg-[#dfece5] px-2 py-1 text-[10px] font-bold text-[#246149]">{profile.label}</span>{profile.secondaryLabels.map((label) => <span key={label} className="border border-[#cfd8d2] bg-white px-2 py-1 text-[10px] text-[#607068]">{label}</span>)}</div>
              <p className="mt-2 text-xs leading-6 text-[#64716a]">{profile.basis}</p>
            </div>
            <span className="text-[10px] text-[#87918c]">使用 {profile.periodCount} / {profile.requiredPeriods} 期 · 主数据 {formatRatio(profile.averages.metadataCoverage)} · 债项评级 {formatRatio(profile.averages.bondRatingCoverage)}</span>
          </div>
          <div className="mt-5 grid gap-px bg-[#dfe5e1] sm:grid-cols-2 xl:grid-cols-5">
            {[
              ['利率债', formatRatio(profile.averages.rateShare)],
              ['地方政府债', formatRatio(profile.averages.localGovernmentShare)],
              ['金融债 / 存单', formatRatio(profile.averages.financialShare)],
              ['信用债', formatRatio(profile.averages.creditShare)],
              ['可转债', formatRatio(profile.averages.convertibleShare)],
            ].map(([label, value]) => <div key={label} className="bg-white p-4"><span className="text-[11px] text-[#78837d]">四期公开持仓平均</span><strong className="mt-1 block text-lg text-[#26342d]">{label} {value}</strong></div>)}
          </div>
          <div className="mt-5 overflow-x-auto border border-[#e0e5e1] bg-white">
            <table className="w-full min-w-[860px] text-left text-xs">
              <thead className="bg-[#f3f6f4] text-[#75817a]"><tr><th className="px-4 py-3 font-medium">报告期</th><th className="px-4 py-3 font-medium">利率债</th><th className="px-4 py-3 font-medium">地方政府债</th><th className="px-4 py-3 font-medium">金融债 / 存单</th><th className="px-4 py-3 font-medium">信用债</th><th className="px-4 py-3 font-medium">可转债</th><th className="px-4 py-3 font-medium">债项评级覆盖</th><th className="px-4 py-3 font-medium">主数据覆盖</th></tr></thead>
              <tbody className="divide-y divide-[#edf0ed] text-[#4f5d56]">{profile.periods.map((period) => <tr key={period.reportDate}><td className="px-4 py-3 font-medium text-[#26342d]">{formatDate(period.reportDate)}</td><td className="px-4 py-3">{formatRatio(period.rateShare)}</td><td className="px-4 py-3">{formatRatio(period.localGovernmentShare)}</td><td className="px-4 py-3">{formatRatio(period.financialShare)}</td><td className="px-4 py-3">{formatRatio(period.creditShare)}</td><td className="px-4 py-3">{formatRatio(period.convertibleShare)}</td><td className="px-4 py-3">{formatRatio(period.bondRatingCoverage)}</td><td className="px-4 py-3">{formatRatio(period.metadataCoverage)}</td></tr>)}</tbody>
            </table>
          </div>
          <p className="mt-4 text-[11px] leading-6 text-[#7b7060]">这是公开重仓债券证据标签，不替代基金正式分类。{profile.limitations.join(' ')}</p>
        </div>
      ) : null}

      <div className="grid border-t border-[#e1e6e2] lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.4fr)]">
        <div className="border-b border-[#e1e6e2] p-5 sm:p-6 lg:border-b-0 lg:border-r">
          <h3 className="text-sm font-bold text-[#26342d]">券种分布</h3>
          <div className="mt-5 space-y-4">
            {latest.buckets.map((bucket) => (
              <div key={bucket.key}>
                <div className="flex items-center justify-between gap-3 text-xs"><span className="font-medium text-[#4f5d56]">{bucket.label} · {bucket.holdingCount} 只</span><strong>{formatRatio(bucket.navRatio)}</strong></div>
                <div className="mt-2 h-1.5 overflow-hidden bg-[#e8ece9]"><div className="h-full bg-[#3a8068]" style={{ width: `${Math.max(0, Math.min(100, (bucket.shareOfDisclosed || 0) * 100))}%` }} /></div>
                <div className="mt-1 text-[10px] text-[#8b958f]">占本期公开重仓债券 {formatRatio(bucket.shareOfDisclosed)}</div>
              </div>
            ))}
          </div>
          <p className="mt-5 border-t border-[#edf0ed] pt-4 text-[11px] leading-6 text-[#7b8680]">{snapshot.classificationMethod} 本期公开债券中可归类覆盖 {formatRatio(latest.classificationCoverage)}。</p>
        </div>

        <div className="min-w-0 overflow-x-auto">
          <table className="w-full min-w-[660px] text-left text-xs">
            <thead className="bg-[#f5f7f5] text-[#75817a]"><tr><th className="px-5 py-3 font-medium">债券</th><th className="px-5 py-3 font-medium">券种</th><th className="px-5 py-3 text-right font-medium">占净值</th><th className="px-5 py-3 text-right font-medium">市值</th></tr></thead>
            <tbody className="divide-y divide-[#edf0ed] text-[#4f5d56]">
              {latest.holdings.slice(0, 10).map((holding) => (
                <tr key={`${holding.sequence}-${holding.bondCode}`}>
                  <td className="px-5 py-3"><strong className="block text-[#26342d]">{holding.bondName}</strong><span className="mt-1 block text-[10px] text-[#929b96]">{holding.bondCode}</span></td>
                  <td className="px-5 py-3" title={holding.classificationBasis}>{holding.bondTypeLabel}</td>
                  <td className="px-5 py-3 text-right font-medium">{formatRatio(holding.navRatio)}</td>
                  <td className="px-5 py-3 text-right">{formatMarketValue(holding.marketValueWan)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid gap-px border-t border-[#e1e6e2] bg-[#e1e6e2] xl:grid-cols-3">
        <div className="bg-white p-5 sm:p-6">
          <div className="flex items-baseline justify-between gap-3"><h3 className="text-sm font-bold text-[#26342d]">发行主体集中度</h3><span className="text-[10px] text-[#87918c]">覆盖 {formatRatio(latest.issuerConcentration.coverage)}</span></div>
          <div className="mt-4 grid grid-cols-2 gap-3 text-xs"><div className="bg-[#f5f7f5] p-3"><span className="block text-[#7a8580]">主体数量</span><strong className="mt-1 block text-base">{latest.issuerConcentration.issuerCount || '—'}</strong></div><div className="bg-[#f5f7f5] p-3"><span className="block text-[#7a8580]">前三主体</span><strong className="mt-1 block text-base">{formatRatio(latest.issuerConcentration.topThreeShareOfDisclosed)}</strong></div></div>
          <div className="mt-4 space-y-3">{latest.issuerConcentration.issuers.slice(0, 5).map((item) => <div key={item.issuer} className="flex items-start justify-between gap-4 text-xs"><span className="min-w-0 text-[#4f5d56]">{item.issuer}</span><strong className="shrink-0">{formatRatio(item.shareOfDisclosed)}</strong></div>)}</div>
        </div>

        <div className="bg-white p-5 sm:p-6">
          <div className="flex items-baseline justify-between gap-3"><h3 className="text-sm font-bold text-[#26342d]">公开评级分布</h3><span className="text-[10px] text-[#87918c]">覆盖 {formatRatio(latest.ratingCoverage)}</span></div>
          <div className="mt-4 space-y-4">{latest.ratingDistribution.length ? latest.ratingDistribution.slice(0, 6).map((item) => <div key={item.rating}><div className="flex items-center justify-between gap-3 text-xs"><span className="font-medium text-[#4f5d56]">{item.rating} · {item.holdingCount} 只</span><strong>{formatRatio(item.shareOfRated)}</strong></div><div className="mt-2 h-1.5 overflow-hidden bg-[#e8ece9]"><div className="h-full bg-[#9a7c45]" style={{ width: `${Math.max(0, Math.min(100, (item.shareOfRated || 0) * 100))}%` }} /></div><div className="mt-1 text-[10px] text-[#8b958f]">{item.ratingTypes.includes('bond') ? '含债项评级' : '主体评级'}</div></div>) : <p className="text-xs text-[#7a8580]">公开主数据未取得评级。</p>}</div>
        </div>

        <div className="bg-white p-5 sm:p-6">
          <div className="flex items-baseline justify-between gap-3"><h3 className="text-sm font-bold text-[#26342d]">剩余到期年限结构</h3><span className="text-[10px] text-[#87918c]">覆盖 {formatRatio(latest.maturityCoverage)}</span></div>
          <div className="mt-4 space-y-4">{latest.maturityBuckets.map((item) => <div key={item.key}><div className="flex items-center justify-between gap-3 text-xs"><span className="font-medium text-[#4f5d56]">{item.label} · {item.holdingCount} 只</span><strong>{formatRatio(item.shareOfKnown)}</strong></div><div className="mt-2 h-1.5 overflow-hidden bg-[#e8ece9]"><div className="h-full bg-[#5f7d92]" style={{ width: `${Math.max(0, Math.min(100, (item.shareOfKnown || 0) * 100))}%` }} /></div></div>)}</div>
        </div>
      </div>

      <div className="min-w-0 overflow-x-auto border-t border-[#e1e6e2]">
        <table className="w-full min-w-[980px] text-left text-xs">
          <thead className="bg-[#f5f7f5] text-[#75817a]"><tr><th className="px-5 py-3 font-medium">债券</th><th className="px-5 py-3 font-medium">发行主体</th><th className="px-5 py-3 font-medium">公开评级</th><th className="px-5 py-3 font-medium">到期日 / 剩余年限</th><th className="px-5 py-3 text-right font-medium">占净值</th></tr></thead>
          <tbody className="divide-y divide-[#edf0ed] text-[#4f5d56]">
            {latest.holdings.slice(0, 10).map((holding) => (
              <tr key={`metadata-${holding.sequence}-${holding.bondCode}`}>
                <td className="px-5 py-3"><strong className="block text-[#26342d]">{holding.bondName}</strong><span className="mt-1 block text-[10px] text-[#929b96]">{holding.bondCode} · {holding.securityBondType || holding.bondTypeLabel}</span></td>
                <td className="px-5 py-3">{holding.issuer || '未取得'}</td>
                <td className="px-5 py-3"><strong className="text-[#26342d]">{holding.creditRating || '未取得'}</strong>{holding.creditRating ? <span className="ml-1 text-[10px] text-[#8b958f]">{holding.ratingType === 'bond' ? '债项' : '主体'}</span> : null}</td>
                <td className="px-5 py-3">{holding.maturityDate ? formatDate(holding.maturityDate) : '未取得'}<span className="ml-1 text-[10px] text-[#8b958f]">{formatRemainingYears(holding.remainingYears)}</span></td>
                <td className="px-5 py-3 text-right font-medium">{formatRatio(holding.navRatio)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="border-t border-[#e1e6e2] bg-[#fbfaf6] px-5 py-4 text-[11px] leading-6 text-[#72694f]">
        当前只覆盖公开重仓债券，不代表完整组合；剩余到期年限不等于久期；主体评级不等于债项评级。基于净值回归的久期估算还需接入中债分期限指数后单独实现。
      </div>

      {snapshot.history.length > 1 ? (
        <div className="overflow-x-auto border-t border-[#e1e6e2]">
          <table className="w-full min-w-[620px] text-left text-xs">
            <thead className="bg-[#f5f7f5] text-[#75817a]"><tr><th className="px-5 py-3 font-medium">报告期</th><th className="px-5 py-3 font-medium">公开数量</th><th className="px-5 py-3 font-medium">合计占净值</th><th className="px-5 py-3 font-medium">主要券种</th><th className="px-5 py-3 font-medium">可归类覆盖</th></tr></thead>
            <tbody className="divide-y divide-[#edf0ed] text-[#4f5d56]">
              {snapshot.history.slice(0, 6).map((period) => <tr key={period.reportDate}><td className="px-5 py-3 font-medium text-[#26342d]">{formatDate(period.reportDate)}</td><td className="px-5 py-3">{period.disclosedCount} 只</td><td className="px-5 py-3">{formatRatio(period.disclosedNavRatio)}</td><td className="px-5 py-3">{period.dominantType || '待核验'}</td><td className="px-5 py-3">{formatRatio(period.classificationCoverage)}</td></tr>)}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
