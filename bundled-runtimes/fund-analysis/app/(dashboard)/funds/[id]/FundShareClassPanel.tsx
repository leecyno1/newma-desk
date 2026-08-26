import Link from 'next/link'
import { CircleAlert, ExternalLink, Split } from 'lucide-react'

export type FundShareClassItem = {
  windCode: string
  name: string
  shareClass: string
  currency: string
  isPrimary: boolean
  isCurrent: boolean
  nav: number | null
  navDate: string
  totalAsset: number | null
  establishmentDate: string
  managementFeeRate: number | null
  custodianFeeRate: number | null
  salesServiceFeeRate: number | null
  knownCoreFeeRate: number | null
  feeProfileStatus: string
  feeSourceUrl: string
  feeSyncedAt: string
  missingFeeItems: string[]
}

export type FundShareClassSnapshot = {
  status: string
  entity: {
    canonicalCode: string
    canonicalName: string
  } | null
  shareCount: number
  shares: FundShareClassItem[]
  feeEvidence: {
    status: string
    coreFeeReadyCount: number
    salesServiceFeeReadyCount: number
    note: string
  }
  boundary: string
  missingItems: string[]
}

function formatDate(value: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

function formatPercent(value: number | null) {
  return value == null ? '未取得' : `${(value * 100).toFixed(value * 100 < 0.1 && value > 0 ? 3 : 2)}%`
}

function formatAsset(value: number | null) {
  return value == null ? '—' : `${value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 亿元`
}

function knownOperationFee(share: FundShareClassItem) {
  if (share.knownCoreFeeRate == null || share.salesServiceFeeRate == null) return null
  return share.knownCoreFeeRate + share.salesServiceFeeRate
}

export default function FundShareClassPanel({ snapshot }: { snapshot: FundShareClassSnapshot }) {
  if (snapshot.status !== 'available' || snapshot.shareCount < 2) return null

  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] p-5 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><Split className="h-5 w-5 text-[#28745c]" />同一基金份额比较</h2>
          <p className="mt-1 text-xs leading-6 text-[#7a8580]">{snapshot.entity?.canonicalName || '同一基金实体'} · 共 {snapshot.shareCount} 个有效份额。</p>
        </div>
        <span className={`px-2.5 py-1 text-[11px] font-bold ${snapshot.feeEvidence.status === 'complete' ? 'bg-[#e2f0e8] text-[#1f684e]' : 'bg-[#fff1d2] text-[#815a16]'}`}>
          费率证据 {snapshot.feeEvidence.status === 'complete' ? '完整' : '部分完整'}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] text-left text-xs">
          <thead className="bg-[#f5f7f5] text-[#75817a]">
            <tr>
              <th className="px-5 py-3 font-medium">份额</th>
              <th className="px-5 py-3 text-right font-medium">管理费</th>
              <th className="px-5 py-3 text-right font-medium">托管费</th>
              <th className="px-5 py-3 text-right font-medium">销售服务费</th>
              <th className="px-5 py-3 text-right font-medium">已知运作费率</th>
              <th className="px-5 py-3 text-right font-medium">最新净值</th>
              <th className="px-5 py-3 text-right font-medium">成立日期</th>
              <th className="px-5 py-3 text-right font-medium">规模</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#edf0ed] text-[#4f5d56]">
            {snapshot.shares.map((share) => {
              const operationFee = knownOperationFee(share)
              return (
                <tr key={share.windCode} className={share.isCurrent ? 'bg-[#f2f8f4]' : ''}>
                  <td className="px-5 py-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link href={`/funds/${encodeURIComponent(share.windCode)}`} className="font-bold text-[#26342d] hover:text-[#28745c]">{share.shareClass || '未知'} 类</Link>
                      {share.isCurrent ? <span className="bg-[#dcece4] px-2 py-0.5 text-[10px] font-bold text-[#236149]">当前份额</span> : null}
                      {share.isPrimary ? <span className="border border-[#ccd7d1] bg-white px-2 py-0.5 text-[10px] text-[#637169]">代表份额</span> : null}
                    </div>
                    <div className="mt-1 text-[10px] text-[#8a948f]">{share.windCode} · {share.name}</div>
                  </td>
                  <td className="px-5 py-4 text-right">{formatPercent(share.managementFeeRate)}</td>
                  <td className="px-5 py-4 text-right">{formatPercent(share.custodianFeeRate)}</td>
                  <td className="px-5 py-4 text-right">{formatPercent(share.salesServiceFeeRate)}</td>
                  <td className="px-5 py-4 text-right font-bold text-[#26342d]">{formatPercent(operationFee)}</td>
                  <td className="px-5 py-4 text-right"><strong className="text-[#26342d]">{share.nav == null ? '—' : share.nav.toFixed(4)}</strong><span className="mt-1 block text-[10px] text-[#8c9691]">{formatDate(share.navDate)}</span></td>
                  <td className="px-5 py-4 text-right">{formatDate(share.establishmentDate)}</td>
                  <td className="px-5 py-4 text-right">{formatAsset(share.totalAsset)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="grid border-t border-[#e1e6e2] md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
        <div className="flex gap-3 bg-[#fffaf0] px-5 py-4 text-[11px] leading-6 text-[#765d2c]">
          <CircleAlert className="mt-1 h-4 w-4 shrink-0" />
          <p>{snapshot.feeEvidence.note} {snapshot.boundary}</p>
        </div>
        {snapshot.shares.find((share) => share.isCurrent)?.feeSourceUrl ? (
          <a href={snapshot.shares.find((share) => share.isCurrent)?.feeSourceUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 px-5 py-4 text-xs font-bold text-[#28745c]">查看当前份额费率原文<ExternalLink className="h-3.5 w-3.5" /></a>
        ) : null}
      </div>
    </section>
  )
}
