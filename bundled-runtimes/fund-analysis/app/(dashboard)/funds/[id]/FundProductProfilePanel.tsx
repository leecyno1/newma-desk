import { BookOpenText, Building2, Percent, ShieldCheck } from 'lucide-react'

export type FundFeeRule = {
  condition: string
  rate: string
  conditionLabel: string
}

export type FundProductProfile = {
  status: string
  source: string
  syncedAt: string
  sourceUrls: {
    basic: string
    fees: string
  }
  product: {
    managementCompany: string
    custodian: string
    investmentObjective: string
    investmentStyle: string
    investmentPhilosophy: string
    investmentScope: string
    investmentStrategy: string
    riskReturnCharacteristics: string
  }
  fees: {
    managementFeeRate: string
    custodianFeeRate: string
    salesServiceFeeRate: string
    subscriptionFeeRules: FundFeeRule[]
    purchaseFeeRules: FundFeeRule[]
    redemptionFeeRules: FundFeeRule[]
    note: string
  }
  missingItems: string[]
}

function display(value: string, fallback = '待同步') {
  return value || fallback
}

function FeeRules({ title, rows }: { title: string; rows: FundFeeRule[] }) {
  return (
    <div>
      <h4 className="text-xs font-bold text-[#536159]">{title}</h4>
      {rows.length ? (
        <div className="mt-2 overflow-hidden border border-[#e0e5e1]">
          {rows.map((row, index) => (
            <div key={`${row.condition}-${row.rate}-${index}`} className={`grid grid-cols-[minmax(0,1fr)_7rem] text-xs ${index ? 'border-t border-[#e6eae7]' : ''}`}>
              <div className="px-3 py-2.5 text-[#66726c]">{row.condition}</div>
              <div className="border-l border-[#e6eae7] px-3 py-2.5 text-right font-bold text-[#294f40]">{row.rate}</div>
            </div>
          ))}
        </div>
      ) : <p className="mt-2 text-xs text-[#8a948f]">暂无可核验分档数据</p>}
    </div>
  )
}

export default function FundProductProfilePanel({ profile }: { profile: FundProductProfile }) {
  const ready = profile.status === 'available'
  return (
    <section className="overflow-hidden border border-[#dbe1dc] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e1e6e2] bg-[#f5f8f6] p-5 sm:p-6">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold text-[#28745c]"><BookOpenText className="h-4 w-4" />产品介绍与费率</div>
          <h2 className="mt-3 text-xl font-bold text-[#1b2922]">先看清基金怎么投、收多少费</h2>
          <p className="mt-2 text-xs leading-6 text-[#68746e]">基金合同级产品信息与公开费率档案；交易渠道折扣需在实际平台再确认。</p>
        </div>
        <span className={`px-2.5 py-1 text-[11px] font-bold ${ready ? 'bg-[#e2f0e8] text-[#1f684e]' : 'bg-[#fff1d2] text-[#815a16]'}`}>{ready ? '已同步公开档案' : '档案待同步'}</span>
      </div>

      <div className="grid gap-px bg-[#e1e6e2] sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['基金管理人', display(profile.product.managementCompany)],
          ['基金托管人', display(profile.product.custodian)],
          ['投资风格', display(profile.product.investmentStyle)],
          ['运作费率', [profile.fees.managementFeeRate, profile.fees.custodianFeeRate].filter(Boolean).join(' + ') || '待同步'],
        ].map(([label, value]) => <div key={label} className="bg-white p-4"><div className="text-[11px] text-[#7a8580]">{label}</div><div className="mt-2 text-sm font-bold leading-6 text-[#24332b]">{value}</div></div>)}
      </div>

      <div className="grid lg:grid-cols-[minmax(0,1.25fr)_minmax(20rem,0.75fr)]">
        <div className="border-b border-[#e1e6e2] p-5 sm:p-6 lg:border-b-0 lg:border-r">
          <h3 className="flex items-center gap-2 text-sm font-bold"><Building2 className="h-4 w-4 text-[#28745c]" />产品介绍</h3>
          <div className="mt-5 space-y-5">
            <div><div className="text-xs font-bold text-[#536159]">投资目标</div><p className="mt-2 text-sm leading-7 text-[#56635c]">{display(profile.product.investmentObjective)}</p></div>
            <div><div className="text-xs font-bold text-[#536159]">投资理念</div><p className="mt-2 text-sm leading-7 text-[#56635c]">{display(profile.product.investmentPhilosophy)}</p></div>
            <div className="border border-[#e5e9e6] bg-[#fafbfa] p-4"><div className="flex items-center gap-2 text-xs font-bold text-[#536159]"><ShieldCheck className="h-4 w-4 text-[#8a6a2c]" />风险收益特征</div><p className="mt-2 text-sm leading-7 text-[#5f625e]">{display(profile.product.riskReturnCharacteristics)}</p></div>
            <details className="border-t border-[#e6eae7] pt-4">
              <summary className="cursor-pointer text-xs font-bold text-[#28745c]">展开完整投资范围与策略</summary>
              <div className="mt-4 space-y-4 text-sm leading-7 text-[#5b6861]"><div><strong className="text-xs text-[#536159]">投资范围</strong><p className="mt-1">{display(profile.product.investmentScope)}</p></div><div><strong className="text-xs text-[#536159]">投资策略</strong><p className="mt-1">{display(profile.product.investmentStrategy)}</p></div></div>
            </details>
          </div>
        </div>

        <div className="p-5 sm:p-6">
          <h3 className="flex items-center gap-2 text-sm font-bold"><Percent className="h-4 w-4 text-[#28745c]" />费率详情</h3>
          <div className="mt-4 grid grid-cols-3 gap-px overflow-hidden border border-[#e0e5e1] bg-[#e0e5e1] text-center">
            {[
              ['管理费', display(profile.fees.managementFeeRate)],
              ['托管费', display(profile.fees.custodianFeeRate)],
              ['销售服务费', display(profile.fees.salesServiceFeeRate, '—')],
            ].map(([label, value]) => <div key={label} className="bg-white p-3"><div className="text-[10px] text-[#7a8580]">{label}</div><div className="mt-2 text-sm font-bold text-[#294f40]">{value}</div></div>)}
          </div>
          <div className="mt-5 space-y-5">
            <FeeRules title="认购费率（前端）" rows={profile.fees.subscriptionFeeRules} />
            <FeeRules title="申购费率（前端）" rows={profile.fees.purchaseFeeRules} />
            <FeeRules title="赎回费率" rows={profile.fees.redemptionFeeRules} />
          </div>
          <p className="mt-5 border-t border-[#e6eae7] pt-4 text-[11px] leading-5 text-[#7c8580]">{profile.fees.note || '费率以基金合同、招募说明书和销售渠道最新规则为准。'}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#e1e6e2] bg-[#fafbfa] px-5 py-3 text-[10px] text-[#89938e]">
        <span>数据源：{profile.source || '本地基金库'}{profile.syncedAt ? ` · 同步于 ${profile.syncedAt.slice(0, 10)}` : ''}</span>
        <span className="flex items-center gap-3">{profile.sourceUrls.basic ? <a href={profile.sourceUrls.basic} target="_blank" rel="noreferrer" className="font-bold text-[#28745c]">查看产品档案</a> : null}{profile.sourceUrls.fees ? <a href={profile.sourceUrls.fees} target="_blank" rel="noreferrer" className="font-bold text-[#28745c]">查看费率原文</a> : null}</span>
      </div>
    </section>
  )
}
