'use client'

import Link from 'next/link'
import { useCallback, useState } from 'react'
import { ArrowRight, Database, Layers3, Search, UsersRound } from 'lucide-react'

export type FundCompanySummary = {
  company: string
  short_name: string
  fund_count: number
  manager_count: number
  classified_count: number
  classification_coverage: number
  asset_sample_count: number
  synced_total_asset: number | null
  metric_ready_count: number
  metric_coverage: number
  peer_group_count: number
  evaluated_peer_group_count: number
  metric_as_of: string | null
}

type Props = {
  initialCompanies: FundCompanySummary[]
  initialSummary: Record<string, number | string | null>
  initialTotal: number
  initialError: string
}

function formatAsset(value: number | null) {
  return value == null ? '—' : `${Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} 亿`
}

function formatCoverage(value: number) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`
}

export default function FundCompanyBrowserClient({ initialCompanies, initialSummary, initialTotal, initialError }: Props) {
  const [companies, setCompanies] = useState(initialCompanies)
  const [searchText, setSearchText] = useState('')
  const [sort, setSort] = useState('fund_count')
  const [total, setTotal] = useState(initialTotal)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(initialError)

  const runSearch = useCallback(async (nextSort = sort) => {
    setLoading(true)
    setError('')
    const params = new URLSearchParams({ limit: '30', sort: nextSort })
    if (searchText.trim()) params.set('search', searchText.trim())
    try {
      const response = await fetch(`/api/fund-companies?${params.toString()}`, { cache: 'no-store' })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || '基金公司查询失败')
      setCompanies(Array.isArray(payload.companies) ? payload.companies : [])
      setTotal(Number(payload.total || 0))
    } catch (searchError) {
      setCompanies([])
      setError(searchError instanceof Error ? searchError.message : '基金公司查询失败')
    } finally {
      setLoading(false)
    }
  }, [searchText, sort])

  return (
    <div className="space-y-7">
      <section className="border-b border-[#dce1dc] pb-7">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="grid grid-cols-2 gap-px overflow-hidden border border-[#d7ddd8] bg-[#d7ddd8] text-sm sm:grid-cols-4">
            <div className="bg-white px-4 py-3"><strong className="block text-lg">{Number(initialSummary.company_count || 0).toLocaleString('zh-CN')}</strong><span className="text-xs text-[#758079]">基金公司</span></div>
            <div className="bg-white px-4 py-3"><strong className="block text-lg">{Number(initialSummary.fund_count || 0).toLocaleString('zh-CN')}</strong><span className="text-xs text-[#758079]">基金份额</span></div>
            <div className="bg-white px-4 py-3"><strong className="block text-lg">{Number(initialSummary.classified_count || 0).toLocaleString('zh-CN')}</strong><span className="text-xs text-[#758079]">已专业分类</span></div>
            <div className="bg-white px-4 py-3"><strong className="block text-lg">{Number(initialSummary.metric_ready_count || 0).toLocaleString('zh-CN')}</strong><span className="text-xs text-[#758079]">已同步业绩</span></div>
          </div>
        </div>

        <form
          className="mt-7 grid gap-3 lg:grid-cols-[minmax(0,1fr)_15rem_auto]"
          onSubmit={(event) => { event.preventDefault(); void runSearch() }}
        >
          <label className="relative block">
            <span className="sr-only">搜索基金公司</span>
            <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#7d8882]" />
            <input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="输入基金公司名称" className="h-12 w-full rounded-md border border-[#cfd6d0] bg-white pl-12 pr-4 text-sm outline-none focus:border-[#28745c]" />
          </label>
          <select value={sort} onChange={(event) => { const next = event.target.value; setSort(next); void runSearch(next) }} className="h-12 rounded-md border border-[#cfd6d0] bg-white px-4 text-sm outline-none focus:border-[#28745c]" aria-label="公司排序">
            <option value="fund_count">按产品覆盖排序</option>
            <option value="coverage">按业绩样本排序</option>
            <option value="category_coverage">按可评价同类组排序</option>
            <option value="asset">按已同步规模排序</option>
          </select>
          <button type="submit" disabled={loading} className="h-12 rounded-md bg-[#173f35] px-6 text-sm font-bold text-white disabled:opacity-60">{loading ? '查询中' : '查找公司'}</button>
        </form>
      </section>

      <section className="border-l-4 border-[#d7b46a] bg-[#fff9eb] px-5 py-4 text-xs leading-6 text-[#755722]">
        “已同步规模”只覆盖已补齐深度数据的样本，不代表行业官方总规模。公司不按跨类别收益排名，点进详情后按专业同类组看业绩。
      </section>

      {error ? <div className="border border-[#e5c98f] bg-[#fff8e8] px-5 py-4 text-sm text-[#78551c]">{error}</div> : null}

      <section>
        <div className="mb-4 flex items-end justify-between gap-3"><div><h2 className="text-lg font-bold">基金公司</h2><p className="mt-1 text-xs text-[#7b8680]">共 {total.toLocaleString('zh-CN')} 家；优先补齐你关注公司的代表产品与经理数据。</p></div></div>
        {companies.length === 0 ? (
          <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-16 text-center text-sm text-[#748079]">没有找到基金公司。</div>
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            {companies.map((company) => (
              <article key={company.company} className="border border-[#dbe1dc] bg-white p-5 transition hover:border-[#88aa9b]">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-bold text-[#1d2b25]">{company.short_name}</h3>
                    <p className="mt-1 text-xs text-[#7b8680]">{company.company}</p>
                  </div>
                  <Link href={`/companies/${encodeURIComponent(company.company)}`} className="inline-flex items-center gap-1 text-xs font-bold text-[#28745c]">查看详情<ArrowRight className="h-3.5 w-3.5" /></Link>
                </div>
                <div className="mt-5 grid grid-cols-3 gap-px overflow-hidden border border-[#e0e5e1] bg-[#e0e5e1] text-center">
                  <div className="bg-[#f9faf8] px-2 py-3"><strong className="block text-base">{Number(company.fund_count || 0).toLocaleString('zh-CN')}</strong><span className="text-[11px] text-[#7a8580]">基金份额</span></div>
                  <div className="bg-[#f9faf8] px-2 py-3"><strong className="block text-base">{Number(company.manager_count || 0)}</strong><span className="text-[11px] text-[#7a8580]">已关联经理</span></div>
                  <div className="bg-[#f9faf8] px-2 py-3"><strong className="block text-base">{formatAsset(company.synced_total_asset)}</strong><span className="text-[11px] text-[#7a8580]">规模样本 {company.asset_sample_count}</span></div>
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className="border border-[#e3e7e4] p-3"><span className="text-xs text-[#78837d]">已覆盖专业同类组</span><strong className="mt-2 block text-lg text-[#267257]">{Number(company.peer_group_count || 0)}</strong><span className="mt-1 block text-[11px] text-[#8a948f]">基于标准基金分类</span></div>
                  <div className="border border-[#e3e7e4] p-3"><span className="text-xs text-[#78837d]">已有 1 年业绩的同类组</span><strong className="mt-2 block text-lg text-[#267257]">{Number(company.evaluated_peer_group_count || 0)}</strong><span className="mt-1 block text-[11px] text-[#8a948f]">进入详情查看各类别样本</span></div>
                </div>
                <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[#66726c]">
                  <span className="inline-flex items-center gap-1.5"><Database className="h-3.5 w-3.5" />专业分类 {company.classified_count}（{formatCoverage(company.classification_coverage)}）</span>
                  <span className="inline-flex items-center gap-1.5"><UsersRound className="h-3.5 w-3.5" />业绩样本 {company.metric_ready_count}（{formatCoverage(company.metric_coverage)}）</span>
                  <span className="inline-flex items-center gap-1.5"><Layers3 className="h-3.5 w-3.5" />可评价同类组 {company.evaluated_peer_group_count}/{company.peer_group_count}</span>
                  <span>数据日 {company.metric_as_of || '待补'}</span>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
