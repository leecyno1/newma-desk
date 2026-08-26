'use client'

import Link from 'next/link'
import { useMemo, useState } from 'react'
import { ArrowRight, CalendarDays, FileText, Search } from 'lucide-react'

type ViewpointItem = {
  id?: string
  date?: string
  dateSource?: string
  datePrecision?: string
  year?: string
  sourceLabel?: string
  title?: string
  viewpoint?: string
  viewpointSource?: string
  evidenceFields?: string[]
  summary?: string
  keyPoints?: string[]
  tags?: string[]
  relativePath?: string
  identityVerifications?: Array<Record<string, unknown>>
}

type RawViewpointItem = ViewpointItem & {
  source_label?: string
  date_source?: string
  date_precision?: string
  viewpoint_source?: string
  evidence_fields?: string[]
  key_points?: string[]
  relative_path?: string
  identity_verifications?: Array<Record<string, unknown>>
}

type ViewpointData = {
  count?: number
  years?: string[]
  sources?: string[]
  items?: RawViewpointItem[]
}

function text(value: unknown) {
  return typeof value === 'string' ? value : value == null ? '' : String(value)
}

function viewpointDateLabel(item: ViewpointItem) {
  const value = text(item.date).slice(0, 10)
  if (!value) return '日期待确认'
  if (item.datePrecision === 'quarter') {
    const month = Number(value.slice(5, 7))
    return `${value.slice(0, 4)} Q${Math.floor((month - 1) / 3) + 1}`
  }
  if (item.datePrecision === 'month') return `${value.slice(0, 7)} 月`
  return value
}

function identityLabel(item: ViewpointItem) {
  const statuses = (item.identityVerifications || []).map((verification) => text(verification.status))
  if (statuses.includes('identity_conflict')) return '身份待复核'
  if (statuses.includes('exact_name_evidence_incomplete')) return '身份已关联 · 证据待补'
  if (statuses.includes('unique_exact_name')) return '身份已核验'
  return '历史已关联'
}

export default function ManagerViewpointTimeline({ managerName, data }: { managerName: string; data: Record<string, unknown> }) {
  const timeline = data as ViewpointData
  const items = useMemo(() => (Array.isArray(timeline.items) ? timeline.items : []).map((item) => ({
    ...item,
    sourceLabel: item.sourceLabel || item.source_label,
    dateSource: item.dateSource || item.date_source,
    datePrecision: item.datePrecision || item.date_precision,
    viewpointSource: item.viewpointSource || item.viewpoint_source,
    evidenceFields: item.evidenceFields || item.evidence_fields || [],
    keyPoints: item.keyPoints || item.key_points || [],
    relativePath: item.relativePath || item.relative_path,
    identityVerifications: item.identityVerifications || item.identity_verifications || [],
  })), [timeline.items])
  const years = Array.isArray(timeline.years) ? timeline.years : []
  const sources = Array.isArray(timeline.sources) ? timeline.sources : []
  const [year, setYear] = useState('all')
  const [source, setSource] = useState('all')
  const [keyword, setKeyword] = useState('')

  const filtered = useMemo(() => {
    const needle = keyword.trim().toLowerCase()
    return items.filter((item) => {
      if (year !== 'all' && item.year !== year) return false
      if (source !== 'all' && item.sourceLabel !== source) return false
      if (!needle) return true
      return [item.title, item.viewpoint, item.summary, ...(item.keyPoints || []), ...(item.tags || [])]
        .map(text)
        .join(' ')
        .toLowerCase()
        .includes(needle)
    })
  }, [items, keyword, source, year])

  return (
    <div className="border border-[#d4ddd7] bg-[#fbfcfa]">
      <div className="grid gap-3 border-b border-[#dfe5e1] bg-white p-4 md:grid-cols-[160px_220px_minmax(0,1fr)]">
        <label className="text-[11px] font-bold text-[#68756e]">
          年份
          <select value={year} onChange={(event) => setYear(event.target.value)} className="mt-1 h-10 w-full border border-[#ccd6cf] bg-[#fbfcfa] px-3 text-xs text-[#28362f] outline-none focus:border-[#28745c]">
            <option value="all">全部年份</option>
            {years.map((item) => <option key={item} value={item}>{item} 年</option>)}
          </select>
        </label>
        <label className="text-[11px] font-bold text-[#68756e]">
          来源
          <select value={source} onChange={(event) => setSource(event.target.value)} className="mt-1 h-10 w-full border border-[#ccd6cf] bg-[#fbfcfa] px-3 text-xs text-[#28362f] outline-none focus:border-[#28745c]">
            <option value="all">全部经理纪要</option>
            {sources.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="text-[11px] font-bold text-[#68756e]">
          搜索观点
          <span className="relative mt-1 block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#829088]" />
            <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="标题、摘要、行业或风格" className="h-10 w-full border border-[#ccd6cf] bg-[#fbfcfa] pl-10 pr-3 text-xs text-[#28362f] outline-none focus:border-[#28745c]" />
          </span>
        </label>
      </div>

      <div className="flex items-center justify-between gap-4 border-b border-[#e4e9e6] px-5 py-3 text-xs text-[#6f7c75]">
        <span>共 {items.length} 期，当前显示 {filtered.length} 期</span>
        <span>仅含已绑定到该经理的本地纪要</span>
      </div>

      {filtered.length ? (
        <div className="divide-y divide-[#e0e6e2]">
          {filtered.map((item, index) => (
            <article key={item.id || `${item.date}-${item.title}-${index}`} className="relative grid gap-4 px-5 py-5 md:grid-cols-[128px_minmax(0,1fr)_auto]">
              <div className="relative border-l border-[#9fbaad] pl-5 text-xs text-[#6b7971]">
                <span className="absolute -left-[5px] top-1 h-2.5 w-2.5 rounded-full border-2 border-[#28745c] bg-[#fbfcfa]" />
                <CalendarDays className="mb-2 h-4 w-4 text-[#28745c]" />
                <strong className="block text-[#33443b]">{viewpointDateLabel(item)}</strong>
                <span className="mt-1 block leading-5">{item.sourceLabel || '本地调研纪要'}</span>
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-bold text-[#233129]">{item.title || '无标题纪要'}</h3>
                  <span className="bg-[#e7f0eb] px-2 py-0.5 text-[10px] font-bold text-[#2d6853]">{item.viewpointSource === 'manager_profile_evidence' ? '投资框架原文' : '纪要摘要'}</span>
                  <span className="bg-[#eef1ef] px-2 py-0.5 text-[10px] font-bold text-[#607069]">{identityLabel(item)}</span>
                </div>
                <p className="mt-2 text-sm leading-7 text-[#53645b]">{item.viewpoint || item.summary || '观点摘要待提取'}</p>
                {(item.keyPoints || []).length > 1 && (
                  <ul className="mt-3 space-y-1 text-xs leading-5 text-[#68766e]">
                    {(item.keyPoints || []).slice(1, 4).map((point) => <li key={point}>· {point}</li>)}
                  </ul>
                )}
                {(item.tags || []).length > 0 && <div className="mt-3 flex flex-wrap gap-2">{(item.tags || []).slice(0, 8).map((tag) => <span key={tag} className="bg-[#eef3ef] px-2.5 py-1 text-[10px] text-[#526159]">{tag}</span>)}</div>}
                {item.relativePath && <div className="mt-3 inline-flex items-center gap-1 text-[10px] text-[#859189]"><FileText className="h-3 w-3" />{item.relativePath}</div>}
              </div>
              <Link href={`/research?search=${encodeURIComponent(item.title || managerName)}`} className="inline-flex h-fit items-center gap-1 text-xs font-bold text-[#28745c]">查看纪要<ArrowRight className="h-3.5 w-3.5" /></Link>
            </article>
          ))}
        </div>
      ) : (
        <p className="px-5 py-12 text-center text-sm text-[#748079]">当前没有匹配的真实调研纪要。</p>
      )}
    </div>
  )
}
