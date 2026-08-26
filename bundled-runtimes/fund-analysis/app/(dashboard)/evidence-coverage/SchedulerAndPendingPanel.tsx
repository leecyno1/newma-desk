'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { AlertCircle, CalendarClock, ClipboardCheck, RefreshCw } from 'lucide-react'

type SchedulerRun = {
  ts?: string
  task?: string
  bucket?: string
  status?: 'ok' | 'failed' | 'skipped_locked'
  exit_code?: number
  start?: string
  end?: string
  duration_seconds?: number
  log?: string
}

type SchedulerPayload = {
  runbook_present: boolean
  runbook_path: string
  last_by_task: Record<string, SchedulerRun>
  buckets: Record<string, { last_run?: string; success_count: number; failed_count: number }>
  recent_runs: SchedulerRun[]
}

type PendingPayload = {
  total: number
  by_kind: Record<string, number>
}

type Payload = {
  scheduler: SchedulerPayload | null
  pending: PendingPayload | null
  errors: string[]
}

const KIND_LABEL: Record<string, string> = {
  manager: '经理身份',
  fund: '基金归属',
  classification: '分类',
  style_label: '风格标签',
  tag: '标签',
  other: '其他',
}

function formatDuration(seconds?: number) {
  if (!seconds && seconds !== 0) return '—'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds - m * 60
  return `${m}m${s}s`
}

function formatTime(iso?: string) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

function statusColor(status?: string) {
  if (status === 'ok') return 'bg-[#e6f2ec] text-[#1f5d3f]'
  if (status === 'failed') return 'bg-[#fde7e2] text-[#8f2f21]'
  if (status === 'skipped_locked') return 'bg-[#f4ecd8] text-[#7a5a1a]'
  return 'bg-[#eef1ee] text-[#5b6a63]'
}

export default function SchedulerAndPendingPanel() {
  const [data, setData] = useState<Payload | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  async function load(refresh = false) {
    if (refresh) setRefreshing(true)
    else setLoading(true)
    try {
      const response = await fetch('/api/data-health', { cache: 'no-store' })
      const payload = await response.json().catch(() => null)
      if (payload) setData(payload as Payload)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const scheduler = data?.scheduler
  const pending = data?.pending
  const bucketRows = scheduler ? Object.entries(scheduler.buckets || {}) : []
  const failedTasks = scheduler
    ? Object.values(scheduler.last_by_task || {}).filter((run) => run?.status === 'failed')
    : []

  return (
    <section className="mb-6 border border-[#d9dfda] bg-white">
      <header className="flex items-center justify-between border-b border-[#e6ebe6] px-5 py-3">
        <div className="flex items-center gap-2 text-sm font-bold text-[#1f5d49]">
          <CalendarClock className="h-4 w-4" />
          调度器状态 & 待确认队列
        </div>
        <button
          type="button"
          onClick={() => void load(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-1 border border-[#c8d0ca] px-2 py-1 text-xs text-[#4a5a52] hover:border-[#28745c] disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </header>

      {loading ? (
        <div className="px-5 py-6 text-sm text-[#6a7570]">正在加载数据健康摘要…</div>
      ) : (
        <div className="grid gap-px bg-[#e6ebe6] md:grid-cols-3">
          {/* 待确认收件箱 */}
          <div className="bg-white p-5">
            <div className="flex items-center gap-2 text-xs font-bold text-[#8a6b31]">
              <ClipboardCheck className="h-3.5 w-3.5" />
              待确认收件箱
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <strong className="text-3xl text-[#1f2d26]">{pending?.total ?? '—'}</strong>
              <span className="text-xs text-[#748079]">项待人工审核</span>
            </div>
            <div className="mt-4 space-y-1.5 text-xs text-[#4a5a52]">
              {pending && pending.by_kind
                ? Object.entries(pending.by_kind)
                    .sort((a, b) => b[1] - a[1])
                    .map(([kind, count]) => (
                      <div key={kind} className="flex items-center justify-between">
                        <span>{KIND_LABEL[kind] || kind}</span>
                        <strong className="text-[#28624e]">{count}</strong>
                      </div>
                    ))
                : <div className="text-[#a9b3ad]">暂无数据</div>}
            </div>
            <Link
              href="/research/pending"
              className="mt-4 inline-flex text-xs font-bold text-[#28745c] hover:underline"
            >
              打开待确认工作流 →
            </Link>
          </div>

          {/* Bucket 摘要 */}
          <div className="bg-white p-5">
            <div className="text-xs font-bold text-[#28624e]">最近调度</div>
            {!scheduler?.runbook_present ? (
              <p className="mt-3 text-xs text-[#7a8580]">
                尚未记录任何调度执行。首次运行后此处会展示每个 bucket 的最新状态。
              </p>
            ) : bucketRows.length === 0 ? (
              <p className="mt-3 text-xs text-[#7a8580]">runbook 已就绪但未记录 bucket 数据。</p>
            ) : (
              <table className="mt-3 w-full text-xs">
                <thead className="text-[#8b978f]">
                  <tr>
                    <th className="pb-1 text-left font-medium">Bucket</th>
                    <th className="pb-1 text-right font-medium">最近</th>
                    <th className="pb-1 text-right font-medium">成功/失败</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#f0f3f0]">
                  {bucketRows.map(([bucket, info]) => (
                    <tr key={bucket}>
                      <td className="py-1.5 font-semibold text-[#1f2d26]">{bucket}</td>
                      <td className="py-1.5 text-right text-[#4a5a52]">{formatTime(info.last_run)}</td>
                      <td className="py-1.5 text-right">
                        <span className="text-[#1f5d3f]">{info.success_count}</span>
                        <span className="mx-1 text-[#c9d0cb]">/</span>
                        <span className="text-[#8f2f21]">{info.failed_count}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* 失败任务告警 */}
          <div className="bg-white p-5">
            <div className="flex items-center gap-2 text-xs font-bold text-[#8f2f21]">
              <AlertCircle className="h-3.5 w-3.5" />
              失败任务
            </div>
            {failedTasks.length === 0 ? (
              <p className="mt-3 text-xs text-[#7a8580]">
                {scheduler?.runbook_present ? '当前所有任务最近一次执行均为成功。' : '尚未有调度记录。'}
              </p>
            ) : (
              <ul className="mt-3 space-y-2 text-xs">
                {failedTasks.slice(0, 5).map((run) => (
                  <li key={`${run.task}-${run.ts}`} className={`border-l-2 pl-2 ${statusColor(run.status)}`}>
                    <div className="font-semibold">{run.task}</div>
                    <div className="mt-0.5 flex gap-2 text-[10px] opacity-80">
                      <span>{formatTime(run.end || run.start)}</span>
                      <span>exit={run.exit_code ?? '?'}</span>
                      <span>{formatDuration(run.duration_seconds)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {data?.errors?.length ? (
        <div className="border-t border-[#e6ebe6] bg-[#fff8ec] px-5 py-2 text-xs text-[#7c5b2d]">
          后端 data-health 部分接口不可用：{data.errors.join(', ')}
        </div>
      ) : null}
    </section>
  )
}
