import Link from 'next/link'
import { notFound } from 'next/navigation'
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  CircleAlert,
  Database,
  Layers3,
  UserRoundSearch,
  UsersRound,
} from 'lucide-react'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

type UnknownRow = Record<string, unknown>

type CompanyDetail = {
  company: UnknownRow
  category_breakdown: UnknownRow[]
  category_window_performance: UnknownRow[]
  representative_funds: UnknownRow[]
  funds: UnknownRow[]
  managers: UnknownRow[]
}

function numberValue(value: unknown) {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function formatPercent(value: unknown, digits = 1) {
  const parsed = numberValue(value)
  if (parsed == null) return '—'
  const normalized = Math.abs(parsed) <= 2 ? parsed * 100 : parsed
  return `${normalized.toFixed(digits)}%`
}

function formatAsset(value: unknown) {
  const parsed = numberValue(value)
  return parsed == null ? '—' : `${parsed.toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 亿`
}

function formatCoverage(value: unknown) {
  const parsed = numberValue(value) || 0
  return `${(parsed * 100).toFixed(1)}%`
}

function scoreLabel(value: unknown, status?: unknown) {
  const score = numberValue(value)
  if (score != null) return score.toFixed(1)
  return status === 'observation_period' ? '观察期' : '评价待补'
}

function managementLabel(value: unknown) {
  if (value === 'active') return '主动管理'
  if (value === 'passive') return '被动指数'
  return '标准分类'
}

const performanceWindows = [
  { key: '3m', label: '3 个月' },
  { key: '6m', label: '6 个月' },
  { key: '1y', label: '1 年' },
  { key: '3y', label: '3 年' },
] as const

function formatSharpe(value: unknown) {
  const parsed = numberValue(value)
  return parsed == null ? '—' : parsed.toFixed(2)
}

function encodedParams(values: Record<string, string>) {
  return new URLSearchParams(values).toString()
}

async function loadCompany(company: string): Promise<CompanyDetail | null> {
  const response = await fetch(`${backendApiBaseUrl}/api/fund-companies/${encodeURIComponent(company)}`, { cache: 'no-store' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error('基金公司详情暂时不可用')
  return response.json()
}

export default async function FundCompanyDetailPage({ params }: { params: Promise<{ company: string }> }) {
  const { company: encodedCompany } = await params
  const companyName = decodeURIComponent(encodedCompany)
  const data = await loadCompany(companyName)
  if (!data) notFound()

  const summary = data.company
  const shortName = String(summary.short_name || summary.company || companyName)
  const categories = data.category_breakdown || []
  const categoryWindowPerformance = data.category_window_performance || []
  const categoryPerformance = new Map<string, Map<string, UnknownRow>>()
  for (const row of categoryWindowPerformance) {
    const peerGroupId = String(row.peer_group_id || '')
    const window = String(row.metric_window || '')
    if (!peerGroupId || !window) continue
    if (!categoryPerformance.has(peerGroupId)) categoryPerformance.set(peerGroupId, new Map())
    categoryPerformance.get(peerGroupId)?.set(window, row)
  }
  const categoriesWithPerformance = categories.filter((category) => categoryPerformance.has(String(category.peer_group_id || '')))
  const representativeFunds = data.representative_funds || data.funds || []
  const scoredFundCount = representativeFunds.filter((fund) => numberValue(fund.professional_score) != null).length
  const observationFundCount = representativeFunds.filter((fund) => fund.evaluation_status === 'observation_period').length

  return (
    <div className="space-y-8">
      <Link href="/companies" className="inline-flex items-center gap-2 text-sm font-bold text-[#28745c]">
        <ArrowLeft className="h-4 w-4" />返回基金公司
      </Link>

      <section className="relative overflow-hidden border border-[#cfd8d1] bg-[#173f35] px-6 py-7 text-white sm:px-8 sm:py-9">
        <div className="absolute -right-16 -top-20 h-64 w-64 rounded-full border border-white/10" />
        <div className="absolute -right-4 top-10 h-40 w-40 rounded-full border border-white/10" />
        <div className="relative grid gap-8 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
          <div className="max-w-3xl">
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">{shortName}</h1>
            <p className="mt-2 text-sm text-[#c6d8d0]">{String(summary.company || companyName)}</p>
          </div>
          <div className="grid grid-cols-2 gap-px overflow-hidden border border-white/20 bg-white/20 text-[#18231e] sm:grid-cols-4">
            <div className="bg-[#f7f5ed] px-4 py-4"><strong className="block text-xl">{Number(summary.fund_count || 0).toLocaleString('zh-CN')}</strong><span className="text-[11px] text-[#68756e]">基金份额</span></div>
            <div className="bg-[#f7f5ed] px-4 py-4"><strong className="block text-xl">{Number(summary.classified_count || 0)}</strong><span className="text-[11px] text-[#68756e]">已专业分类</span></div>
            <div className="bg-[#f7f5ed] px-4 py-4"><strong className="block text-xl">{representativeFunds.length}</strong><span className="text-[11px] text-[#68756e]">类别代表基金</span></div>
            <div className="bg-[#f7f5ed] px-4 py-4"><strong className="block text-xl">{Number(summary.manager_count || 0)}</strong><span className="text-[11px] text-[#68756e]">已关联经理</span></div>
          </div>
        </div>
      </section>

      <section className="grid gap-3 lg:grid-cols-3">
        <article className="border border-[#dbe1dc] bg-white p-5">
          <Layers3 className="h-5 w-5 text-[#28745c]" />
          <strong className="mt-4 block text-base">专业类别覆盖</strong>
          <p className="mt-2 text-sm leading-6 text-[#66736c]">当前覆盖 {categories.length} 个标准同类组，A/C 份额已合并为基金实体。</p>
        </article>
        <article className="border border-[#dbe1dc] bg-white p-5">
          <BarChart3 className="h-5 w-5 text-[#28745c]" />
          <strong className="mt-4 block text-base">评价证据</strong>
          <p className="mt-2 text-sm leading-6 text-[#66736c]">{scoredFundCount} 只代表基金已有专业评分；{observationFundCount} 只新基金处于观察期，其余才标记“评价待补”。</p>
        </article>
        <article className="border border-[#dbe1dc] bg-white p-5">
          <UserRoundSearch className="h-5 w-5 text-[#28745c]" />
          <strong className="mt-4 block text-base">经理与产品</strong>
          <p className="mt-2 text-sm leading-6 text-[#66736c]">经理只展示本地已核实的现任产品关联，不按公司名猜测。</p>
        </article>
      </section>

      <section className="border-l-4 border-[#d7b46a] bg-[#fff9eb] px-5 py-4 text-xs leading-6 text-[#755722]">
        当前专业分类覆盖 {formatCoverage(summary.classification_coverage)}，一年业绩样本覆盖 {formatCoverage(summary.metric_coverage)}。规模仅汇总 {Number(summary.asset_sample_count || 0)} 个已同步样本（{formatAsset(summary.synced_total_asset)}），不代表公司官方总规模。
      </section>

      <section>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-[#28745c]"><Layers3 className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.12em]">Product map</span></div>
            <h2 className="mt-2 text-2xl font-bold">公司强在哪些专业类别</h2>
            <p className="mt-1 text-sm text-[#6d7872]">只在标准同类组内理解收益和回撤，不混合比较货币、债券、主动权益与指数基金。</p>
          </div>
        </div>
        {categories.length ? (
          <div className="grid gap-4 lg:grid-cols-2">
            {categories.map((category) => {
              const representative = category.representative_fund as UnknownRow | null | undefined
              const peerGroup = String(category.peer_group_name || '专业类别待补')
              return (
                <article key={String(category.peer_group_id || peerGroup)} className="group border border-[#d7ded8] bg-white p-5 transition hover:border-[#82a898]">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <span className="text-[11px] font-bold tracking-[0.08em] text-[#7a8680]">{managementLabel(category.active_passive)}</span>
                      <h3 className="mt-1 text-lg font-bold text-[#1e2b25]">{peerGroup}</h3>
                    </div>
                    <span className="rounded-full bg-[#e8f1ec] px-3 py-1 text-xs font-bold text-[#28624e]">{Number(category.fund_count || 0)} 个产品</span>
                  </div>
                  <div className="mt-5 grid grid-cols-3 gap-px overflow-hidden border border-[#e3e7e4] bg-[#e3e7e4] text-center">
                    <div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-sm text-[#267257]">{formatPercent(category.return_1y)}</strong><span className="text-[10px] text-[#7d8782]">近 1 年中位数</span></div>
                    <div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-sm text-[#8b4f48]">{formatPercent(category.max_drawdown_1y)}</strong><span className="text-[10px] text-[#7d8782]">回撤中位数</span></div>
                    <div className="bg-[#fafbf9] px-2 py-3"><strong className="block text-sm">{Number(category.return_sample_count || 0)}</strong><span className="text-[10px] text-[#7d8782]">业绩样本</span></div>
                  </div>
                  {representative ? (
                    <div className="mt-5 border-l-2 border-[#2f755d] pl-4">
                      <span className="text-[11px] font-bold text-[#6f7b74]">先研究这只</span>
                      <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <Link href={`/funds/${encodeURIComponent(String(representative.wind_code))}`} className="font-bold text-[#1d2b25] hover:text-[#28745c]">{String(representative.name || representative.wind_code)}</Link>
                          <p className="mt-1 text-xs text-[#7b8680]">{String(representative.wind_code)} · {representative.evaluation_status === 'observation_period' ? '成立时间不足，暂处观察期' : `专业评分 ${scoreLabel(representative.professional_score, representative.evaluation_status)}`}</p>
                        </div>
                        <Link href={`/discover?${encodedParams({ peerGroup })}`} className="inline-flex items-center gap-1 text-xs font-bold text-[#28745c]">浏览同类基金<ArrowRight className="h-3.5 w-3.5" /></Link>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-5 flex items-center gap-2 text-xs text-[#8a6d35]"><CircleAlert className="h-4 w-4" />该类别代表基金评价证据待补齐。</p>
                  )}
                </article>
              )
            })}
          </div>
        ) : <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-14 text-center text-sm text-[#748079]">该公司尚未完成标准专业分类。</div>}
      </section>

      <section>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-[#28745c]"><BarChart3 className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.12em]">Category performance</span></div>
            <h2 className="mt-2 text-2xl font-bold">同类组多周期业绩证据</h2>
            <p className="mt-1 text-sm text-[#6d7872]">每一行只聚合同一标准同类组的基金实体；区间回报、最大回撤与 Sharpe 均取已同步样本中位数。</p>
          </div>
          <span className="text-xs text-[#77827c]">可评价 {categoriesWithPerformance.length}/{categories.length} 个同类组</span>
        </div>
        {categoriesWithPerformance.length ? (
          <div className="overflow-x-auto border border-[#dbe1dc] bg-white">
            <table className="w-full min-w-[1180px] border-collapse text-left text-sm">
              <thead className="bg-[#eef2ee] text-xs text-[#66726c]">
                <tr>
                  <th className="px-4 py-3">专业同类组</th>
                  {performanceWindows.map((window) => <th key={window.key} className="px-4 py-3 text-center">{window.label}</th>)}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#e5e9e5]">
                {categoriesWithPerformance.map((category) => {
                  const peerGroupId = String(category.peer_group_id || '')
                  const windowMap = categoryPerformance.get(peerGroupId)
                  const peerGroup = String(category.peer_group_name || '专业分类待补')
                  return (
                    <tr key={peerGroupId} className="align-top hover:bg-[#f8faf8]">
                      <td className="px-4 py-4">
                        <Link href={`/discover?${encodedParams({ peerGroup })}`} className="font-bold text-[#2b634f] hover:underline">{peerGroup}</Link>
                        <span className="mt-1 block text-[11px] text-[#88918d]">{Number(category.fund_count || 0)} 个基金实体 · {managementLabel(category.active_passive)}</span>
                      </td>
                      {performanceWindows.map((window) => {
                        const metric = windowMap?.get(window.key)
                        if (!metric) return <td key={window.key} className="px-4 py-4 text-center text-[#9a7334]">样本待补</td>
                        const sampleCount = Number(metric.return_sample_count || 0)
                        const sharpeLabel = category.asset_class === 'money_market' ? '不适用' : formatSharpe(metric.sharpe_ratio)
                        return (
                          <td key={window.key} className="px-4 py-4 text-center">
                            <strong className="block text-[#267257]">{formatPercent(metric.total_return)}</strong>
                            <span className="mt-1 block text-[11px] text-[#8b4f48]">回撤 {formatPercent(metric.max_drawdown)}</span>
                            <span className="mt-1 block text-[11px] text-[#66736c]">Sharpe {sharpeLabel} · 样本 {sampleCount}</span>
                            {sampleCount < 3 ? <span className="mt-1 block text-[10px] font-bold text-[#9a7334]">小样本，仅作证据线索</span> : null}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-14 text-center text-sm text-[#748079]">该公司尚无可按同类组聚合的多周期业绩样本。</div>}
      </section>

      <section>
        <div className="mb-4">
          <div className="flex items-center gap-2 text-[#28745c]"><CheckCircle2 className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.12em]">Research shortlist</span></div>
          <h2 className="mt-2 text-2xl font-bold">各类别代表基金</h2>
          <p className="mt-1 text-sm text-[#6d7872]">每个专业类别只选一个研究入口，依据是同类专业评分、量化证据完整度和规模样本，不是跨类别收益榜。</p>
        </div>
        <div className="overflow-x-auto border border-[#dbe1dc] bg-white">
          <table className="w-full min-w-[1020px] border-collapse text-left text-sm">
            <thead className="bg-[#eef2ee] text-xs text-[#66726c]"><tr><th className="px-4 py-3">专业类别</th><th className="px-4 py-3">代表基金</th><th className="px-4 py-3">现任经理</th><th className="px-4 py-3 text-right">近 1 年</th><th className="px-4 py-3 text-right">最大回撤</th><th className="px-4 py-3 text-right">专业评分</th><th className="px-4 py-3">为什么先看</th></tr></thead>
            <tbody className="divide-y divide-[#e5e9e5]">
              {representativeFunds.map((fund) => {
                const managers = Array.isArray(fund.managers) ? fund.managers as UnknownRow[] : []
                const peerGroup = String(fund.peer_group || '专业分类待补')
                return (
                  <tr key={String(fund.wind_code)} className="align-top transition hover:bg-[#f8faf8]">
                    <td className="px-4 py-4"><Link href={`/discover?${encodedParams({ peerGroup })}`} className="font-bold text-[#2b634f] hover:underline">{peerGroup}</Link><span className="mt-1 block text-[11px] text-[#88918d]">{Number(fund.category_fund_count || 0)} 个基金实体</span></td>
                    <td className="px-4 py-4"><Link href={`/funds/${encodeURIComponent(String(fund.wind_code))}`} className="font-bold hover:text-[#28745c]">{String(fund.name || fund.wind_code)}</Link><span className="mt-1 block text-xs text-[#7b8680]">{String(fund.wind_code)} · {formatAsset(fund.total_asset)}</span></td>
                    <td className="px-4 py-4">{managers.length ? managers.map((manager) => <Link key={String(manager.wind_code)} href={`/managers/${encodeURIComponent(String(manager.wind_code))}`} className="mr-2 inline-block font-medium hover:text-[#28745c]">{String(manager.name || '')}</Link>) : <span className="text-[#9a7334]">待补充</span>}</td>
                    <td className="px-4 py-4 text-right font-bold text-[#267257]">{formatPercent(fund.annualized_return_1y)}</td>
                    <td className="px-4 py-4 text-right text-[#8b4f48]">{formatPercent(fund.max_drawdown_1y)}</td>
                    <td className="px-4 py-4 text-right"><strong className={numberValue(fund.professional_score) == null ? 'text-[#9a7334]' : 'text-[#245f4b]'}>{scoreLabel(fund.professional_score, fund.evaluation_status)}</strong></td>
                    <td className="max-w-[18rem] px-4 py-4 text-xs leading-6 text-[#66736c]">{String(fund.selection_reason || '评价证据待补齐')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <div className="mb-4">
          <div className="flex items-center gap-2 text-[#28745c]"><UsersRound className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.12em]">Manager map</span></div>
          <h2 className="mt-2 text-2xl font-bold">代表经理及其产品</h2>
          <p className="mt-1 text-sm text-[#6d7872]">按已核实管理年限和代表产品展示，先从产品进入经理研究，不做公司内经理总排名。</p>
        </div>
        {data.managers.length ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data.managers.map((manager) => {
              const representativeCode = String(manager.representative_fund_code || '')
              return (
                <article key={String(manager.wind_code)} className="flex min-h-52 flex-col border border-[#dbe1dc] bg-white p-5 transition hover:border-[#87aa9b]">
                  <div className="flex items-start justify-between gap-3">
                    <div><Link href={`/managers/${encodeURIComponent(String(manager.wind_code))}`} className="text-lg font-bold hover:text-[#28745c]">{String(manager.name || '姓名待补')}</Link><p className="mt-1 text-xs text-[#77827c]">管理年限 {numberValue(manager.management_years)?.toFixed(1) || '—'} 年 · 关联 {Number(manager.current_fund_count || 0)} 只</p></div>
                    <UserRoundSearch className="h-5 w-5 text-[#769488]" />
                  </div>
                  <div className="mt-5 border-t border-[#e4e8e5] pt-4">
                    <span className="text-[11px] font-bold text-[#7b8680]">代表产品</span>
                    {representativeCode ? <><Link href={`/funds/${encodeURIComponent(representativeCode)}`} className="mt-1 block font-bold hover:text-[#28745c]">{String(manager.representative_fund_name || representativeCode)}</Link><p className="mt-1 text-xs text-[#77827c]">{String(manager.representative_peer_group || '专业分类待补')} · 近 1 年 {formatPercent(manager.representative_return_1y)}</p></> : <p className="mt-1 text-xs text-[#9a7334]">代表产品待补充</p>}
                  </div>
                  <Link href={`/managers/${encodeURIComponent(String(manager.wind_code))}`} className="mt-auto inline-flex items-center gap-1 pt-5 text-xs font-bold text-[#28745c]">查看经理研究<ArrowRight className="h-3.5 w-3.5" /></Link>
                </article>
              )
            })}
          </div>
        ) : <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-14 text-center text-sm text-[#748079]">该公司代表基金的经理关系尚未同步。</div>}
      </section>

      <section className="grid gap-4 border border-[#d7ded8] bg-[#eef3ef] p-5 md:grid-cols-[auto_1fr] md:items-center">
        <Database className="h-6 w-6 text-[#28745c]" />
        <div><strong className="text-sm">口径说明</strong><p className="mt-1 text-xs leading-6 text-[#66736c]">公司基金总数按份额代码计数；类别业绩按基金实体合并 A/C 份额，并在每个标准同类组内取区间回报中位数。公司详情不做总评分，不输出跨类别公司收益。</p></div>
      </section>
    </div>
  )
}
