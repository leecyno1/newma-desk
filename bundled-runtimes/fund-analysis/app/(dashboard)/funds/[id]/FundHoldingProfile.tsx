import { ChartPie, CircleAlert, TableProperties } from 'lucide-react'

export type FundHolding = {
  stockCode: string
  stockName: string
  market: string
  industry: string
  industrySource: string
  industryAsOfDate: string
  industryEvidenceUrl: string
  fundNavWeight: number | null
  equityPortfolioWeight: number | null
  marketValue: number | null
  reportDate: string
  announcementDate: string
}

export type FundHoldingSnapshot = {
  latestQuarter: string
  source: string
  industryEvidence: {
    status: string
    hongKongHoldingCount: number
    matchedHoldingCount: number
    asOfDate: string
    source: string
    evidenceUrl: string
    note: string
  }
  holdings: FundHolding[]
  summary: {
    holdingCount: number
    weightBasis: string
    reportDate: string
    announcementDate: string
    syncedAt: string
    holdingSources: string[]
    weightSources: string[]
    weightSourceUrls: string[]
    fundNetAssetBases: string[]
    fundNetAssetDate: string
    topThreeWeight: number | null
    topTenWeight: number | null
    topThreeEquityWeight: number | null
    topTenEquityWeight: number | null
    industryWeightBasis: string
    weightValidation: {
      status: string
      totalWeight: number
      validCount: number
      missingCount: number
      invalidCount: number
      reason: string
    }
    industryBuckets: Array<{ industry: string; weight: number }>
    marketBuckets: Array<{ market: string; weight: number }>
  }
}

function formatPercent(value: number | null, digits = 2) {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

function formatDate(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

function holdingWeight(holding: FundHolding, basis: string) {
  return basis === 'fund_nav' ? holding.fundNavWeight : holding.equityPortfolioWeight
}

function weightSourceLabel(value: string) {
  if (value.startsWith('tushare.fund_nav.')) return 'Tushare 报告期净资产'
  if (value.includes('eastmoney')) return '东财定期报告净资产'
  return value || '来源待补'
}

export default function FundHoldingProfile({
  snapshot,
  fundType,
}: {
  snapshot: FundHoldingSnapshot
  fundType: string
}) {
  const { holdings, summary } = snapshot
  const usesFundNavWeight = summary.weightBasis === 'fund_nav'
  const invalidWeightScale = summary.weightValidation.status === 'invalid_weight_scale'
  const topTen = usesFundNavWeight ? summary.topTenWeight : summary.topTenEquityWeight
  const topThree = usesFundNavWeight ? summary.topThreeWeight : summary.topThreeEquityWeight
  const topIndustry = summary.industryBuckets[0]
  const maxIndustryWeight = Math.max(...summary.industryBuckets.map((item) => item.weight), 0)
  const weightLabel = usesFundNavWeight ? '占基金净值' : '占股票市值'
  const isBondFund = /债/u.test(fundType)
  const hongKongEvidence = snapshot.industryEvidence.hongKongHoldingCount > 0
    ? snapshot.industryEvidence
    : null
  const weightSourceText = Array.from(new Set(summary.weightSources.map(weightSourceLabel))).join('、')

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-3 pb-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><TableProperties className="h-5 w-5 text-[#28745c]" />最新公开持仓</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">
            {snapshot.latestQuarter ? `${snapshot.latestQuarter} 报告期` : '报告期待补'}
            {summary.reportDate ? ` · 截至 ${formatDate(summary.reportDate)}` : ''}
            {summary.announcementDate ? ` · 公告 ${formatDate(summary.announcementDate)}` : ''}
          </p>
          {summary.marketBuckets.length ? <p className="mt-1 text-[11px] text-[#87918c]">市场分布：{summary.marketBuckets.map((item) => `${item.market} ${formatPercent(item.weight, 1)}`).join(' · ')}</p> : null}
          {weightSourceText ? <p className="mt-1 text-[11px] text-[#68766f]">权重分母：{weightSourceText}{summary.fundNetAssetDate ? ` · 报告期 ${formatDate(summary.fundNetAssetDate)}` : ''}</p> : null}
        </div>
        <div className="text-[11px] text-[#85908a]">来源：{snapshot.source === 'tushare.fund_portfolio' ? 'Tushare 基金持仓' : snapshot.source === 'local.postgres.holdings' ? '本地持仓库（源自 Tushare）' : snapshot.source || '待补'}</div>
      </div>

      {!holdings.length ? (
        <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-10 text-center text-sm text-[#748079]">当前没有可核验的公开重仓股。</div>
      ) : (
        <div className="overflow-hidden border border-[#dbe1dc] bg-white">
          <div className="grid gap-px bg-[#e0e5e1] sm:grid-cols-2 lg:grid-cols-4">
            <div className="bg-white p-5"><div className="text-[11px] text-[#7a8580]">已披露重仓股</div><div className="mt-2 text-2xl font-bold text-[#1d2923]">{summary.holdingCount} 只</div><div className="mt-2 text-[11px] text-[#8b9590]">公开披露，不代表完整组合</div></div>
            <div className="bg-white p-5"><div className="text-[11px] text-[#7a8580]">前十大{weightLabel}</div><div className="mt-2 text-2xl font-bold text-[#1d2923]">{formatPercent(topTen, 1)}</div><div className="mt-2 text-[11px] text-[#8b9590]">前三大 {formatPercent(topThree, 1)}</div></div>
            <div className="bg-white p-5"><div className="text-[11px] text-[#7a8580]">第一重仓</div><div className="mt-2 truncate text-base font-bold text-[#1d2923]">{holdings[0]?.stockName || '—'}</div><div className="mt-2 text-[11px] text-[#8b9590]">{weightLabel} {formatPercent(holdingWeight(holdings[0], summary.weightBasis), 1)}</div></div>
            <div className="bg-white p-5"><div className="text-[11px] text-[#7a8580]">第一行业</div><div className="mt-2 truncate text-base font-bold text-[#1d2923]">{topIndustry?.industry || '—'}</div><div className="mt-2 text-[11px] text-[#8b9590]">{weightLabel} {formatPercent(topIndustry?.weight ?? null, 1)}</div></div>
          </div>

          {!usesFundNavWeight || isBondFund ? (
            <div className="flex gap-3 border-y border-[#eadfbf] bg-[#fffaf0] px-5 py-4 text-xs leading-6 text-[#735b2b]">
              <CircleAlert className="mt-1 h-4 w-4 shrink-0" />
              <p>
                {invalidWeightScale ? '该报告期“持仓市值 ÷ 基金净资产”的单位口径异常，系统已清空错误净值权重；当前只保留 Tushare 公布的“占股票市值比”。' : !usesFundNavWeight ? '当前比例是 Tushare 公布的“占股票市值比”，不能解读为占基金净值。' : ''}
                {isBondFund ? ' 这是一只债券基金，以下仅反映股票仓位，不代表债券资产结构。' : ''}
              </p>
            </div>
          ) : null}

          <div className="grid lg:grid-cols-[minmax(0,1.4fr)_minmax(18rem,0.6fr)]">
            <div className="min-w-0 overflow-x-auto">
              <table className="w-full min-w-[48rem] text-left text-xs">
                <thead className="bg-[#f5f7f5] text-[#68746e]"><tr><th className="px-5 py-3 font-medium">排名</th><th className="px-5 py-3 font-medium">重仓股</th><th className="px-5 py-3 font-medium">市场</th><th className="px-5 py-3 font-medium">行业</th><th className="px-5 py-3 text-right font-medium">{weightLabel}</th></tr></thead>
                <tbody className="divide-y divide-[#e6e9e6]">
                  {holdings.slice(0, 10).map((holding, index) => (
                    <tr key={`${holding.stockCode}-${index}`} className="hover:bg-[#fafbf9]">
                      <td className="px-5 py-3 text-[#8a948f]">{index + 1}</td>
                      <td className="px-5 py-3"><div className="font-bold text-[#26322c]">{holding.stockName || holding.stockCode}</div><div className="mt-1 text-[11px] text-[#929b96]">{holding.stockCode}</div></td>
                      <td className="px-5 py-3 text-[#59665f]">{holding.market || '其他'}</td>
                      <td className="px-5 py-3 text-[#59665f]"><div>{holding.industry || '行业待补'}</div>{holding.industrySource === 'hang_seng_indexes.official' ? <div className="mt-1 text-[10px] text-[#2d725a]">恒生官方分类 · {holding.industryAsOfDate || '日期待补'}</div> : null}</td>
                      <td className="px-5 py-3 text-right font-bold text-[#28654f]">{formatPercent(holdingWeight(holding, summary.weightBasis), 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="border-t border-[#e0e5e1] p-5 lg:border-l lg:border-t-0">
              <h3 className="flex items-center gap-2 text-sm font-bold"><ChartPie className="h-4 w-4 text-[#28745c]" />行业分布</h3>
              <p className="mt-1 text-[11px] leading-5 text-[#87918c]">基于已披露重仓股，口径为{weightLabel}。</p>
              <div className="mt-5 space-y-4">
                {summary.industryBuckets.slice(0, 6).map((item) => (
                  <div key={item.industry}>
                    <div className="flex items-center justify-between gap-3 text-xs"><span className="truncate text-[#4f5d56]">{item.industry}</span><span className="font-bold text-[#28654f]">{formatPercent(item.weight, 1)}</span></div>
                    <div className="mt-2 h-1.5 overflow-hidden bg-[#e7ebe8]"><div className="h-full bg-[#3a8068]" style={{ width: `${maxIndustryWeight > 0 ? Math.max(4, (item.weight / maxIndustryWeight) * 100) : 0}%` }} /></div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {hongKongEvidence ? (
            <div className="border-t border-[#dfe5e1] bg-[#f4f8f5] px-5 py-3 text-[11px] leading-5 text-[#52645b]">
              港股行业匹配 {hongKongEvidence.matchedHoldingCount}/{hongKongEvidence.hongKongHoldingCount} 只
              {hongKongEvidence.asOfDate ? ` · 恒生行业快照 ${hongKongEvidence.asOfDate}` : ''}。
              {hongKongEvidence.note}
              {hongKongEvidence.evidenceUrl ? <a className="ml-1 font-bold text-[#24644e] underline" href={hongKongEvidence.evidenceUrl} target="_blank" rel="noreferrer">查看官方来源</a> : null}
            </div>
          ) : null}
          {summary.weightSourceUrls[0] ? <div className="border-t border-[#dfe5e1] bg-[#f7f9f7] px-5 py-3 text-[11px] leading-5 text-[#66746d]">持仓来自 Tushare 基金定期报告，净值权重按报告期基金净资产换算。<a className="ml-1 font-bold text-[#24644e] underline" href={summary.weightSourceUrls[0]} target="_blank" rel="noreferrer">查看净资产来源</a></div> : null}
        </div>
      )}
    </section>
  )
}
