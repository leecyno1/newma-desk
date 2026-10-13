'use client'

import { useContext, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { FundNavigationContext, useFundPageData } from '@/lib/newma-desk/page-data'
import type { SalesRule } from '@/lib/sales-rules'
import EvidenceActionPanel, { type EvidenceAction } from './EvidenceActionPanel'

type ReviewEvent = {
  id: string; fund_id?: string; event_type?: string; severity?: string; title?: string
  message?: string; status?: string; triggered_at?: string
  details?: { wind_code?: string; fund_code?: string }
}
type Records = { events?: ReviewEvent[]; rules?: SalesRule[]; total?: number; count?: number; missingCodes?: string[]; source?: string }
type Props = { section: 'materials' | 'review-events'; query: Record<string, string> }
const show = (value: unknown) => value === null || value === undefined || value === '' ? '—' : String(value)
const eventCode = (event: ReviewEvent) => event.details?.wind_code || event.details?.fund_code || event.fund_id || ''
const statusLabels: Record<string, string> = { open: '待处理', acknowledged: '已知悉', resolved: '已解决', high: '高', medium: '中', low: '低' }
function sourceHref(value: string | null) {
  if (!value) return undefined
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined } catch { return undefined }
}

export default function EvidenceRecordsClient({ section, query }: Props) {
  const navigateDesk = useContext(FundNavigationContext)
  const materials = section === 'materials'
  const [codes, setCodes] = useState(query.codes || '')
  const [status, setStatus] = useState(query.status || '')
  const [severity, setSeverity] = useState(query.severity || '')
  const [platform, setPlatform] = useState(query.platform || '')
  const [applied, setApplied] = useState({ codes, status, severity, platform })
  const [refresh, setRefresh] = useState(0)
  const [data, setData] = useState<Records | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [action, setAction] = useState<EvidenceAction | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const requestedCodes = useMemo(() => [...new Set(applied.codes.split(/[,，\s]+/).map(code => code.trim().toUpperCase()).filter(Boolean))], [applied.codes])
  const request = useMemo(() => {
    const params = new URLSearchParams()
    if (materials) {
      params.set('limit', '100')
      if (requestedCodes.length) params.set('codes', requestedCodes.join(','))
      else if (applied.platform) params.set('platform', applied.platform)
    } else {
      if (applied.status) params.set('status', applied.status)
      if (applied.severity) params.set('severity', applied.severity)
    }
    return `/api/evidence-coverage/${section}?${params}`
  }, [materials, requestedCodes, applied, section])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(null); setData(null); setPage(1)
    void (async () => {
      try {
        const response = await fetch(request, { signal: controller.signal, cache: 'no-store' })
        const result = await response.json()
        if (!response.ok) throw new Error(result.error || '证据读取失败')
        if (!Array.isArray(materials ? result.rules : result.events)) throw new Error('接口未返回有效证据列表')
        if (!controller.signal.aborted) setData(result)
      } catch (caught) {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '证据读取失败')
      } finally { if (!controller.signal.aborted) setLoading(false) }
    })()
    return () => controller.abort()
  }, [request, refresh, materials])
  const events = useMemo(() => (data?.events || []).filter(event => !requestedCodes.length || requestedCodes.includes(eventCode(event).toUpperCase())), [data, requestedCodes])
  const rules = useMemo(() => (data?.rules || []).filter(rule => !applied.platform || rule.platform === applied.platform), [data, applied.platform])
  const rows = materials ? rules : events
  const pageCount = Math.max(1, Math.ceil(rows.length / 25))
  const visibleEvents = useMemo(() => events.slice((page - 1) * 25, page * 25), [events, page])
  const visibleRules = useMemo(() => rules.slice((page - 1) * 25, page * 25), [rules, page])
  const title = materials ? '材料证据' : '研究复查'
  const appliedQuery = useMemo(() => new URLSearchParams({ ...query, ...applied, section }), [query, applied, section])
  function submit() {
    setApplied({ codes, status, severity, platform }); setRefresh(value => value + 1)
    const params = new URLSearchParams({ ...query, codes, status, severity, platform, section })
    if (!navigateDesk?.('/evidence-coverage', params.toString())) window.history.replaceState(null, '', `/evidence-coverage?${params}`)
  }
  useFundPageData(useMemo(() => ({ title, selection: null,
    filters: { applied, draft: { codes, status, severity, platform }, page,
      researchContext: { purchasePlan: query.purchasePlan ?? null, plannedAmount: query.plannedAmount ?? null, focus: query.focus ?? null, queueMode: query.queueMode ?? null } },
    visibleBlocks: [{ id: section, type: 'table', title }],
    summary: { view: section, status: loading ? 'loading' : error ? 'error' : 'ready', error,
      returnedCount: data ? (materials ? data.rules?.length : data.events?.length) : null,
      sourceTotal: data?.total ?? data?.count ?? null, filteredCount: data ? rows.length : null,
      missingCodes: data?.missingCodes ?? null, source: data?.source ?? (materials ? null : 'local.alert_events'),
      rows: !loading && !error ? (materials ? visibleRules : visibleEvents) : [], lastOperation: notice,
      boundary: '默认读取已有记录，不自动扫描、确认、导入或核验；新增来源或处置事件必须人工确认。材料最多读取100条；按代码检索最多500个代码且采用合并口径。复查按代码在已返回事件中筛选；事件状态不是投资风险结论。focus/queueMode和配置金额仅为来源研究上下文，未执行优先队列计算或适当性判断。' },
  }), [title, applied, codes, status, severity, platform, page, query, section, loading, error, data, materials, rows.length, visibleRules, visibleEvents, notice]))
  const returnTo = query.returnTo === '/reports' || query.returnTo?.startsWith('/reports?') || /^\/managers\/[^/?#]+$/.test(query.returnTo || '') ? query.returnTo : '/reports'
  return <div className="space-y-5 text-sm">
    <nav aria-label="证据栏目" className="flex flex-wrap items-center gap-5 border-b border-[var(--vibe-border)] pb-3">
      <Link href={returnTo} className="underline">{returnTo.startsWith('/managers/') ? '返回基金经理' : '返回报告列表'}</Link>
      <Link href="/evidence-coverage">覆盖总览</Link>
      <Link href={`/evidence-coverage?${new URLSearchParams({ ...Object.fromEntries(appliedQuery), section: 'review-events' })}`} aria-current={!materials ? 'page' : undefined}>研究复查</Link>
      <Link href={`/evidence-coverage?${new URLSearchParams({ ...Object.fromEntries(appliedQuery), section: 'materials' })}`} aria-current={materials ? 'page' : undefined}>材料证据</Link>
    </nav>
    <p className="text-[var(--vibe-text-soft)]">{materials ? '查看已存申赎、费率与风险等级来源。空值表示未提供；有记录不代表来源有效或适当性通过。' : '查看已扫描形成的复查事件。不自动扫描；状态变更须逐项人工确认，不代表风险消失。'}</p>
    {notice ? <p role="status">{notice}</p> : null}
    {materials && !action ? <button className="border border-[var(--vibe-border)] px-4 py-2" onClick={() => { setNotice(null); setAction({ kind: 'material', code: requestedCodes.length === 1 ? requestedCodes[0] : '' }) }}>新增来源证据</button> : null}
    {action ? <EvidenceActionPanel key={action.kind === 'event' ? action.id : action.kind} action={action} onCancel={() => setAction(null)} onSaved={message => { setNotice(message); setAction(null); setRefresh(value => value + 1) }} /> : null}
    {query.queueMode || query.focus ? <p role="note" className="text-[var(--vibe-warning)]">来源任务：{query.focus || query.queueMode}。当前展示已有记录，未执行来源任务的优先级筛选或自动补证。</p> : null}
    <form className="flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); submit() }}>
      <label className="flex flex-col gap-1">基金代码<input aria-label="证据基金代码" className="border border-[var(--vibe-border)] bg-transparent px-3 py-2" placeholder="000001.OF，多个代码用逗号分隔" value={codes} onChange={event => setCodes(event.target.value)} /></label>
      {materials ? <label className="flex flex-col gap-1">来源平台<input aria-label="来源平台" className="border border-[var(--vibe-border)] bg-transparent px-3 py-2" value={platform} onChange={event => setPlatform(event.target.value)} /></label> : <>
        <label className="flex flex-col gap-1">事件状态<select className="bg-[var(--vibe-surface)] p-2" value={status} onChange={event => setStatus(event.target.value)}><option value="">全部状态</option><option value="open">待处理</option><option value="acknowledged">已知悉</option><option value="resolved">已解决</option></select></label>
        <label className="flex flex-col gap-1">严重程度<select className="bg-[var(--vibe-surface)] p-2" value={severity} onChange={event => setSeverity(event.target.value)}><option value="">全部程度</option><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label>
      </>}
      <button className="border border-[var(--vibe-border)] px-4 py-2" type="submit">查询证据</button>
    </form>
    {loading ? <p role="status">正在读取{title}…</p> : error ? <div role="alert"><p>{error}；不能判断没有缺项或风险。</p><button className="mt-2 underline" onClick={() => setRefresh(value => value + 1)}>重试读取证据</button></div> : <>
      <p>当前筛选 {rows.length} 条 · 第 {page}/{pageCount} 页 · {materials ? '无代码时最多读取100条，不代表全量覆盖。按代码查询使用跨平台合并口径。' : '事件为历史扫描记录，不是实时风险扫描。'}</p>
      {data?.missingCodes?.length ? <p role="status">未找到材料记录：{data.missingCodes.join('、')}</p> : null}
      {!rows.length ? <p>当前查询未返回记录；不能据此判断证据完整或不存在风险。</p> : <div className="overflow-x-auto"><table className="w-full border-collapse text-left"><thead><tr className="border-b border-[var(--vibe-border)]">
        {(materials ? ['基金 / 平台', '申购 / 费率', '风险等级 / 来源日期', '来源证据'] : ['基金 / 事件', '严重程度 / 状态', '触发日期', '复查内容']).map(label => <th className="p-3 font-semibold" key={label}>{label}</th>)}
      </tr></thead><tbody>
        {materials ? visibleRules.map((rule, index) => <tr className="border-b border-[var(--vibe-border)] align-top" key={`${rule.windCode}:${rule.platform}:${index}`}>
          <td className="p-3"><Link className="underline" href={`/funds/${encodeURIComponent(rule.windCode)}`}>{rule.windCode}</Link><div>{show(rule.platform)}</div></td>
          <td className="p-3">{show(rule.purchaseStatusLabel)}{rule.purchaseStatusSourceBacked === false ? <div className="text-[var(--vibe-warning)]">申购状态缺少正式来源背书</div> : null}<div>申购费率：{rule.purchaseFeeRate == null ? '—' : `${rule.purchaseFeeRate}%`}</div><div>销售服务费：{rule.salesServiceFeeRate == null ? '—' : `${rule.salesServiceFeeRate}%`}</div></td>
          <td className="p-3">{show(rule.riskLevel)}<div>{show(rule.sourceUpdatedAt)}</div></td>
          <td className="max-w-md p-3">{sourceHref(rule.sourceUrl) ? <a href={sourceHref(rule.sourceUrl)} target="_blank" rel="noopener noreferrer" className="underline">打开来源原文</a> : '未提供有效来源链接'}<div className="mt-1 text-[var(--vibe-text-soft)]">{show(rule.notes)}</div></td>
        </tr>) : visibleEvents.map(event => <tr className="border-b border-[var(--vibe-border)] align-top" key={event.id}>
          <td className="p-3">{show(eventCode(event))}<div>{show(event.title || event.event_type)}</div></td>
          <td className="p-3">{statusLabels[event.severity || ''] || show(event.severity)} / {statusLabels[event.status || ''] || show(event.status)}</td>
          <td className="whitespace-nowrap p-3">{show(event.triggered_at)}</td><td className="max-w-xl whitespace-pre-wrap p-3">{show(event.message)}<div className="mt-2"><button disabled={Boolean(action) || !['open', 'acknowledged'].includes(event.status || '')} className="underline disabled:opacity-40" onClick={() => { setNotice(null); setAction({ kind: 'event', id: event.id, title: event.title || event.id, status: event.status || 'open' }) }}>处置事件</button></div></td>
        </tr>)}
      </tbody></table></div>}
      {pageCount > 1 ? <div className="flex items-center gap-4"><button disabled={page <= 1} onClick={() => setPage(value => value - 1)}>上一页</button><button disabled={page >= pageCount} onClick={() => setPage(value => value + 1)}>下一页</button></div> : null}
    </>}
  </div>
}
