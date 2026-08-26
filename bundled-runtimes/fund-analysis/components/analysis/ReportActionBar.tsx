import Link from 'next/link'
import { BarChart3, ClipboardCheck, ExternalLink, FileText, ShieldCheck, UserCheck } from 'lucide-react'
import { materialEvidenceHref } from '@/lib/research-platform/routes'

type TargetType = 'fund' | 'manager'
type PurchasePlan = 'lump_sum' | 'sip'

type ActionItem = {
  label: string
  href: string
  description: string
  icon: 'detail' | 'rules' | 'compare' | 'report'
  external?: boolean
}

type ActionContext = {
  purchasePlan?: PurchasePlan
  plannedAmount?: number | null
  returnTo?: string | null
}

const iconClassName = 'w-4 h-4'

function actionIcon(icon: ActionItem['icon']) {
  if (icon === 'rules') return <ShieldCheck className={iconClassName} />
  if (icon === 'compare') return <BarChart3 className={iconClassName} />
  if (icon === 'report') return <FileText className={iconClassName} />
  return <UserCheck className={iconClassName} />
}

function normalizeHref(rawHref: string) {
  const href = rawHref.trim().replace(/[，。；;、]+$/u, '')
  if (!href) return null
  if (href.startsWith('/')) return { href, external: false }

  try {
    const url = new URL(href)
    const isLocalApp = ['localhost', '127.0.0.1', '::1'].includes(url.hostname)
    return {
      href: isLocalApp ? `${url.pathname}${url.search}${url.hash}` : url.href,
      external: !isLocalApp,
    }
  } catch {
    return null
  }
}

function safeReturnPath(returnTo: string | null | undefined) {
  return returnTo?.startsWith('/') && !returnTo.startsWith('//') ? returnTo : null
}

function appendSearchParams(href: string, params: URLSearchParams) {
  const query = params.toString()
  if (!query) return href
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}${query}`
}

function purchaseContextParams(context: ActionContext) {
  const purchasePlan = context.purchasePlan === 'lump_sum' ? 'lump_sum' : 'sip'
  const params = new URLSearchParams({ purchasePlan })
  const amount = Number(context.plannedAmount)
  if (Number.isFinite(amount) && amount > 0) {
    const normalizedAmount = String(Math.round(amount))
    params.set('plannedAmount', normalizedAmount)
    params.set(purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', normalizedAmount)
  }
  const returnTo = safeReturnPath(context.returnTo)
  if (returnTo) params.set('returnTo', returnTo)
  return params
}

function inferIcon(label: string): ActionItem['icon'] {
  if (/销售|规则|材料|费率/u.test(label)) return 'rules'
  if (/对比|比较|横向/u.test(label)) return 'compare'
  if (/报告|备忘录/u.test(label)) return 'report'
  return 'detail'
}

function extractActionsFromContent(content: string) {
  const actions: ActionItem[] = []
  const actionLinePattern = /^-\s*([^:：\n]{2,24})[:：]\s*(https?:\/\/\S+|\/\S+)/gmu
  for (const match of content.matchAll(actionLinePattern)) {
    const normalized = normalizeHref(match[2])
    if (!normalized) continue
    actions.push({
      label: match[1].trim(),
      href: normalized.href,
      external: normalized.external,
      icon: inferIcon(match[1]),
      description: normalized.external ? '打开外部证据入口' : '继续完成研究复核',
    })
  }
  return actions
}

function uniqueActions(actions: ActionItem[]) {
  const seen = new Set<string>()
  return actions.filter((action) => {
    const key = `${action.label}:${action.href}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function buildBaseActions(targetType: TargetType, targetId: string, reportId: string | null | undefined, context: ActionContext): ActionItem[] {
  const safeTargetId = targetId.trim()
  if (!safeTargetId) return []

  const contextParams = purchaseContextParams(context)
  const actions: ActionItem[] = []
  if (targetType === 'fund') {
    actions.push(
      {
        label: '查看基金详情',
        href: appendSearchParams(`/funds/${encodeURIComponent(safeTargetId)}`, contextParams),
        description: '回到净值、评分、证据缺口，并保留研究口径',
        icon: 'detail',
      },
      {
        label: '核查材料证据',
        href: appendSearchParams(materialEvidenceHref({ codes: safeTargetId }), contextParams),
        description: '按当前计划金额补费率、申赎、风险等级',
        icon: 'rules',
      },
      {
        label: '进入横向对比',
        href: appendSearchParams(`/analysis/comparison?codes=${encodeURIComponent(safeTargetId)}&autoReplay=1`, contextParams),
        description: '带入本基金和研究口径，再补同类样本',
        icon: 'compare',
      },
    )
  } else {
    actions.push({
      label: '查看经理详情',
      href: appendSearchParams(`/managers/${encodeURIComponent(safeTargetId)}`, contextParams),
      description: '核查任职记录、管理基金和研究门禁',
      icon: 'detail',
    })
  }

  if (reportId) {
    actions.push({
      label: '查看完整报告',
      href: appendSearchParams(`/reports/${reportId}`, contextParams),
      description: '打开已落库的研究报告并保留复核口径',
      icon: 'report',
    })
  }

  return actions
}

export default function ReportActionBar({
  targetId,
  targetType,
  content,
  reportId,
  purchasePlan = 'sip',
  plannedAmount = null,
  returnTo = null,
}: {
  targetId: string
  targetType: TargetType
  content: string
  reportId?: string | null
  purchasePlan?: PurchasePlan
  plannedAmount?: number | null
  returnTo?: string | null
}) {
  const actions = uniqueActions([
    ...buildBaseActions(targetType, targetId, reportId, { purchasePlan, plannedAmount, returnTo }),
    ...extractActionsFromContent(content),
  ])

  if (actions.length === 0) return null

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-white p-2 text-slate-700 shadow-sm">
          <ClipboardCheck className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-slate-900">生成后继续核查</h3>
          <p className="mt-1 text-xs text-slate-600">
            报告只给研究底稿，正式结论仍要沿着材料证据、同类比较和复查事件继续验证。
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {actions.map((action) => {
              const className = 'flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm shadow-sm transition hover:border-blue-300 hover:bg-blue-50'
              const body = (
                <>
                  <span className="rounded-md bg-blue-100 p-1.5 text-blue-700">{actionIcon(action.icon)}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium text-slate-900">{action.label}</span>
                    <span className="block truncate text-xs text-slate-500">{action.description}</span>
                  </span>
                  {action.external && <ExternalLink className="h-3.5 w-3.5 text-slate-400" />}
                </>
              )

              if (action.external) {
                return (
                  <a key={`${action.label}-${action.href}`} href={action.href} target="_blank" rel="noreferrer" className={className}>
                    {body}
                  </a>
                )
              }

              return (
                <Link key={`${action.label}-${action.href}`} href={action.href} className={className}>
                  {body}
                </Link>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
