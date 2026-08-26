'use client'

import Link from 'next/link'
import { ArrowRight, BookOpenText, CalendarDays, Search, UserRound } from 'lucide-react'

export type ManagerResearchProfile = {
  id: string
  name: string
  company: string
  managementYears: string
  memoCount: number
  fundCount: number
  latestDate: string
  latestMemoTitle: string
  topTopics: Array<{ topic: string; count: number }>
  labels: string[]
}

function dateText(value: string) {
  if (!value) return '日期待补'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('zh-CN')
}

export default function ManagerResearchGrid({
  profiles,
  query,
  onQueryChange,
  onOpenMemos,
  onOpenLatestMemo,
}: {
  profiles: ManagerResearchProfile[]
  query: string
  onQueryChange: (value: string) => void
  onOpenMemos: (managerName: string) => void
  onOpenLatestMemo: (managerName: string) => void
}) {
  return (
    <section className="space-y-4" aria-labelledby="manager-library-heading">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="manager-library-heading" className="text-xl font-bold">基金经理研究台</h2>
          <p className="mt-1 text-xs text-[#748078]">先看经理纪要覆盖、观点主题和已确认画像，再进入基金与任期研究。</p>
        </div>
        <span className="text-xs text-[#748078]">当前 {profiles.length} 位</span>
      </div>

      <label className="relative block min-w-0">
        <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#7d8882]" />
        <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="搜索基金经理、基金公司、主题或风格" className="h-12 w-full rounded-md border border-[#cfd6d0] bg-white pl-12 pr-4 text-sm outline-none focus:border-[#28745c]" />
      </label>

      {profiles.length ? (
        <div className="grid gap-3 xl:grid-cols-2">
          {profiles.map((profile) => {
            const topicMax = Math.max(...profile.topTopics.map((item) => item.count), 1)
            return (
              <article key={profile.name} className="min-w-0 border border-[#dbe1dc] bg-white">
                <div className="grid gap-4 p-5 sm:grid-cols-[minmax(0,1fr)_9rem]">
                  <div className="min-w-0">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-sm bg-[#e5eee9] text-[#28634f]"><UserRound className="h-5 w-5" /></span>
                      <div className="min-w-0">
                        <h3 className="truncate text-base font-bold text-[#1d2923]">{profile.name}</h3>
                        <p className="mt-1 truncate text-xs text-[#6e7a73]">{profile.company || '基金公司待补'}{profile.managementYears ? ` · 管理 ${profile.managementYears}` : ''}</p>
                      </div>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-1.5">
                      {profile.labels.length ? profile.labels.map((label) => <span key={label} className="rounded-sm bg-[#e7f0eb] px-2 py-1 text-[11px] font-bold text-[#28634f]">{label}</span>) : <span className="rounded-sm bg-[#f0f2f0] px-2 py-1 text-[11px] text-[#748078]">长期风格待确认</span>}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-px self-start bg-[#dfe5e1] text-center">
                    <div className="bg-[#f7f9f7] p-3"><span className="block text-[10px] text-[#748078]">纪要</span><strong className="mt-1 block text-lg text-[#183d33]">{profile.memoCount}</strong></div>
                    <div className="bg-[#f7f9f7] p-3"><span className="block text-[10px] text-[#748078]">关联基金</span><strong className="mt-1 block text-lg text-[#183d33]">{profile.fundCount}</strong></div>
                  </div>
                </div>

                <div className="grid gap-5 border-t border-[#e3e8e4] px-5 py-4 sm:grid-cols-[minmax(0,1fr)_minmax(12rem,.8fr)]">
                  <div>
                    <div className="flex items-center gap-2 text-[11px] text-[#75817b]"><CalendarDays className="h-3.5 w-3.5" />最新纪要 {dateText(profile.latestDate)}</div>
                    <button type="button" onClick={() => onOpenLatestMemo(profile.name)} className="mt-2 line-clamp-2 text-left text-sm font-bold leading-6 text-[#26362f] hover:text-[#28745c]">{profile.latestMemoTitle || '查看经理纪要'}</button>
                  </div>
                  <div className="space-y-2">
                    {profile.topTopics.length ? profile.topTopics.slice(0, 3).map((item) => <div key={item.topic} className="grid grid-cols-[4rem_minmax(0,1fr)_1.5rem] items-center gap-2 text-[10px] text-[#66726c]"><span className="truncate">{item.topic}</span><span className="h-1.5 bg-[#edf0ed]"><span className="block h-full bg-[#4b8a72]" style={{ width: `${Math.max(8, item.count / topicMax * 100)}%` }} /></span><strong className="text-right">{item.count}</strong></div>) : <span className="text-[11px] text-[#879189]">观点主题待提取</span>}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 border-t border-[#e3e8e4] bg-[#f7f9f7] px-5 py-3">
                  <button type="button" onClick={() => onOpenMemos(profile.name)} className="inline-flex items-center gap-2 rounded-sm bg-[#173f35] px-3 py-2 text-xs font-bold text-white"><BookOpenText className="h-4 w-4" />查看全部纪要</button>
                  {profile.id ? <Link href={`/managers/${encodeURIComponent(profile.id)}`} className="inline-flex items-center gap-2 rounded-sm border border-[#9fc4b4] bg-white px-3 py-2 text-xs font-bold text-[#245c49]">经理完整研究<ArrowRight className="h-4 w-4" /></Link> : null}
                </div>
              </article>
            )
          })}
        </div>
      ) : <div className="border border-dashed border-[#cbd3cd] bg-white px-6 py-14 text-center text-sm text-[#748078]">没有符合条件的基金经理。</div>}
    </section>
  )
}
