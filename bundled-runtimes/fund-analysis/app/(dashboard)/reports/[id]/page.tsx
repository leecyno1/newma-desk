'use client'

import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AlertTriangle, ArrowLeft, Calendar, CheckCircle2, Copy, Download, FileText, Layers, RefreshCw, ShieldCheck, Tag, User } from 'lucide-react'
import { buildBuyBeforeEvidenceQueue } from '@/lib/report-buy-before-evidence-queue'
import { canonicalResearchHref, materialEvidenceHref } from '@/lib/research-platform/routes'

interface Report {
  id: string
  title: string
  content: string
  summary: string | null
  reportDate: string
  source: string
  targetId: string
  targetType: string
  reportType: string
  reportTypeLabel?: string
  purchasePlan?: 'lump_sum' | 'sip'
  plannedAmount?: number | null
  relatedCodes?: string[]
  riskLevelGatePolicy?: {
    status: 'strict_30d_source_backed' | 'legacy_or_unmarked' | 'not_applicable'
    label: string
    detail: string
    tone: 'emerald' | 'amber' | 'slate'
    requiresRegeneration: boolean
    effectiveDate: string
    generatedAt: string
    signals: string[]
  }
  tags: string[]
  keyPoints: string[]
  currentSalesRuleGate?: {
    status: 'ready' | 'blocked' | 'unknown'
    missingCount: number | null
    missingItems: string[]
    blockedFunds?: number | null
    actionHref: string
    source: string
  } | null
  evidenceSummary?: {
    title: string
    subtitle: string
    cards: Array<{
      label: string
      value: string
      detail: string
      tone: 'emerald' | 'amber' | 'rose' | 'blue' | 'slate' | 'purple'
    }>
    warnings: string[]
    nextActions: string[]
  } | null
  buyBeforeDecision?: {
    status: string
    label: string
    hardBlocks: string[]
    cautionFlags: string[]
    nextActions: string[]
  } | null
  executionAmountGate?: {
    status: 'pass' | 'blocked' | 'unknown'
    label: string
    detail: string
    plannedAmount: number | null
    blockedCount: number
    totalCount: number
    blockedFunds: Array<{
      windCode: string
      fundName: string
      label: string
      detail: string
    }>
  } | null
  purchaseDecisionCards?: Array<{
    windCode: string
    fundName: string
    label: string
    primaryAction: string
    reasons: string[]
    reverseTriggers: string[]
  }>
  sourceDecisionCards?: Array<{
    windCode: string
    fundName: string
    label: string
    latestConclusion: string
    nextAction: string
    bullets: string[]
    hardBoundary: string
    reviewFreshnessStatus?: string
    reviewFreshnessLabel?: string
    reviewFreshnessDetail?: string
  }>
  winLossLines?: Array<{
    challengerCode: string
    challengerName: string
    status: string
    label: string
    summary: string
    thresholds: Array<{ key: string; label: string; passed: boolean; detail: string }>
    passedChecks: number
    totalChecks: number
  }>
  decisiveAudit?: {
    title: string
    confidence: string
    passCount: number
    totalCount: number
    items: Array<{ label: string; passed: boolean; detail: string }>
    boundary: string
  } | null
  managerId: string | null
  manager?: {
    id: string
    name: string
    company: string | null
  }
  createdAt: string
}

function evidenceToneClass(tone: NonNullable<Report['evidenceSummary']>['cards'][number]['tone']) {
  if (tone === 'emerald') return 'border-emerald-100 bg-emerald-50 text-emerald-900'
  if (tone === 'amber') return 'border-amber-100 bg-amber-50 text-amber-900'
  if (tone === 'rose') return 'border-rose-100 bg-rose-50 text-rose-900'
  if (tone === 'blue') return 'border-blue-100 bg-blue-50 text-blue-900'
  if (tone === 'purple') return 'border-purple-100 bg-purple-50 text-purple-900'
  return 'border-slate-100 bg-slate-50 text-slate-900'
}

function riskLevelPolicyClass(tone: NonNullable<Report['riskLevelGatePolicy']>['tone']) {
  if (tone === 'emerald') return 'border-emerald-100 bg-emerald-50 text-emerald-900'
  if (tone === 'amber') return 'border-amber-100 bg-amber-50 text-amber-900'
  return 'border-slate-100 bg-slate-50 text-slate-900'
}

function riskLevelPolicyBadgeClass(tone: NonNullable<Report['riskLevelGatePolicy']>['tone']) {
  if (tone === 'emerald') return 'bg-emerald-100 text-emerald-800'
  if (tone === 'amber') return 'bg-amber-100 text-amber-800'
  return 'bg-slate-100 text-slate-700'
}

function winLossStatusClass(status: string) {
  if (status === 'win') return 'bg-emerald-100 text-emerald-700'
  if (status === 'close') return 'bg-amber-100 text-amber-700'
  if (status === 'rules_pending') return 'bg-rose-100 text-rose-700'
  return 'bg-slate-100 text-slate-700'
}

function decisiveAuditClass(confidence?: string) {
  if (confidence === '领先较稳') return 'border-emerald-100 bg-emerald-50 text-emerald-950'
  if (confidence === '领先很脆弱') return 'border-rose-100 bg-rose-50 text-rose-950'
  if (confidence === '仅补证观察') return 'border-amber-100 bg-amber-50 text-amber-950'
  return 'border-slate-100 bg-slate-50 text-slate-900'
}

function buyBeforeGateClass(status?: string) {
  if (status === 'blocked_by_hard_gate') return 'border-rose-100 bg-rose-50 text-rose-900'
  if (status === 'verify_first') return 'border-amber-100 bg-amber-50 text-amber-900'
  if (status === 'research_ready') return 'border-emerald-100 bg-emerald-50 text-emerald-900'
  return 'border-slate-100 bg-slate-50 text-slate-900'
}

function appendReturnTo(href: string, returnTo: string) {
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`
}

function normalizedPlannedAmount(value?: number | null) {
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? amount : null
}

function isReviewQueueGate(gate?: Report['currentSalesRuleGate'] | null) {
  return Boolean(
    gate?.actionHref?.startsWith('/alerts')
      || gate?.actionHref?.includes('section=review-events')
      || gate?.source?.includes('local.alert_events.sales_rule_evidence'),
  )
}

function appendPurchaseContext(href: string, purchasePlan: 'lump_sum' | 'sip', plannedAmount?: number | null) {
  const [path, query = ''] = href.split('?')
  const params = new URLSearchParams(query)
  params.set('purchasePlan', purchasePlan)
  const amount = normalizedPlannedAmount(plannedAmount)
  if (amount) {
    params.set('plannedAmount', String(amount))
    params.set(purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(amount))
  }
  return `${path}?${params.toString()}`
}

function reportActionHref(href: string, purchasePlan: 'lump_sum' | 'sip', plannedAmount: number | null, returnTo: string) {
  const [path, query = ''] = href.split('?')
  const params = new URLSearchParams(query)
  params.set('purchasePlan', purchasePlan)
  if (plannedAmount) {
    params.set('plannedAmount', String(plannedAmount))
    params.set(purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(plannedAmount))
  }
  params.set('returnTo', returnTo)
  return `${path}?${params.toString()}`
}

function reportScopeLabel(reportType: string) {
  if (reportType === 'fund_pool_gap_snapshot') return '补证快照'
  if (reportType === 'fund_pool_shortlist_report') return '正式短名单报告'
  if (reportType === 'fund_comparison_report') return '正式横评报告'
  if (reportType === 'fund_pre_purchase_check') return '正式研究复核报告'
  return '基金研究资料'
}

function tsvCell(value: unknown) {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean).join('；').replace(/\t/g, ' ').replace(/\r?\n/g, ' / ')
  if (typeof value === 'object') return JSON.stringify(value).replace(/\t/g, ' ').replace(/\r?\n/g, ' / ')
  return String(value).replace(/\t/g, ' ').replace(/\r?\n/g, ' / ')
}

function safeFileStem(value: string) {
  return value.trim().replace(/[\\/:*?"<>|\s]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 80) || 'report_evidence'
}

export default function ReportDetailPage() {
  const params = useParams()
  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(true)
  const [reportEvidenceTsvStatus, setReportEvidenceTsvStatus] = useState<'idle' | 'copied' | 'fallback'>('idle')

  const fetchReportDetail = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetch(`/api/reports/${params.id}`)
      if (response.ok) {
        const data = await response.json()
        setReport(data)
      }
    } catch (error) {
      console.error('获取报告详情失败:', error)
    } finally {
      setLoading(false)
    }
  }, [params.id])

  useEffect(() => {
    if (params.id) {
      const timeout = globalThis.setTimeout(() => {
        void fetchReportDetail()
      }, 0)
      return () => globalThis.clearTimeout(timeout)
    }
  }, [fetchReportDetail, params.id])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-500">加载中...</div>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen">
        <div className="text-gray-500 mb-4">报告不存在</div>
        <Link href="/reports" className="text-blue-600 hover:text-blue-800">
          返回列表
        </Link>
      </div>
    )
  }

  const relatedCodes = report.relatedCodes || []
  const targetId = report.targetId || report.managerId || ''
  const reportReturnHref = `/reports/${encodeURIComponent(String(params.id || ''))}`
  const gateStatus = report.currentSalesRuleGate?.status || 'none'
  const reviewQueueGate = isReviewQueueGate(report.currentSalesRuleGate)
  const isGapSnapshot = report.reportType === 'fund_pool_gap_snapshot'
  const reportPurchasePlan = report.purchasePlan === 'lump_sum' ? 'lump_sum' : 'sip'
  const reportPlannedAmount = normalizedPlannedAmount(report.plannedAmount ?? report.executionAmountGate?.plannedAmount ?? null)
  const riskLevelPolicy = report.riskLevelGatePolicy
  const salesRuleParams = new URLSearchParams()
  if (relatedCodes.length) salesRuleParams.set('codes', relatedCodes.join(','))
  const salesRulesHref = report.currentSalesRuleGate?.actionHref
    ? canonicalResearchHref(report.currentSalesRuleGate.actionHref)
    : appendPurchaseContext(materialEvidenceHref(salesRuleParams), reportPurchasePlan, reportPlannedAmount)
  const salesRulesHrefWithReturn = appendReturnTo(salesRulesHref, reportReturnHref)
  const firstFundCode = relatedCodes[0] || (report.targetType === 'fund' ? targetId : '')
  const riskLevelAuditCodes = Array.from(new Set([...(relatedCodes || []), firstFundCode].map((code) => code.trim().toUpperCase()).filter(Boolean)))
  const riskLevelAuditParams = new URLSearchParams({
    scope: 'market',
    focus: 'risk_level',
    queueMode: 'candidate_missing_risk',
  })
  if (riskLevelAuditCodes.length) riskLevelAuditParams.set('codes', riskLevelAuditCodes.join(','))
  const riskLevelSourceAuditHref = reportActionHref(
    materialEvidenceHref(riskLevelAuditParams),
    reportPurchasePlan,
    reportPlannedAmount,
    reportReturnHref,
  )
  const reportBuyBeforeQueue = report.buyBeforeDecision
    ? buildBuyBeforeEvidenceQueue([{
        targetType: report.targetType || 'report',
        targetId: firstFundCode || targetId || report.id,
        relatedCodes: relatedCodes.length ? relatedCodes : firstFundCode ? [firstFundCode] : [],
        purchasePlan: reportPurchasePlan,
        plannedAmount: reportPlannedAmount,
        decisionSummary: {
          buyBeforeGateStatus: report.buyBeforeDecision.status,
          buyBeforeGateHardBlocks: report.buyBeforeDecision.hardBlocks || [],
          buyBeforeGateCautionFlags: report.buyBeforeDecision.cautionFlags || [],
        },
      }])
    : []
  const objectAction = (() => {
    if (report.targetType === 'fund' && firstFundCode) {
      return { label: '打开基金详情', href: appendPurchaseContext(`/funds/${encodeURIComponent(firstFundCode)}`, reportPurchasePlan, reportPlannedAmount) }
    }
    if (report.targetType === 'fund_pool' && targetId) {
      return { label: '打开研究清单', href: appendPurchaseContext(`/pools?poolId=${encodeURIComponent(targetId)}&status=candidate`, reportPurchasePlan, reportPlannedAmount) }
    }
    if ((report.targetType === 'comparison' || report.reportType.includes('comparison')) && relatedCodes.length >= 2) {
      return { label: '重跑对比矩阵', href: appendPurchaseContext(`/analysis/comparison?codes=${encodeURIComponent(relatedCodes.join(','))}&autoReplay=1`, reportPurchasePlan, reportPlannedAmount) }
    }
    if ((report.targetType === 'manager' || report.managerId) && targetId) {
      return { label: '打开基金经理', href: `/managers/${encodeURIComponent(targetId)}` }
    }
    return null
  })()
  const rerunAction = (() => {
    const blocked = gateStatus === 'blocked'
    if (report.reportType === 'fund_pre_purchase_check' && firstFundCode) {
      if (blocked) {
        return {
          label: reviewQueueGate ? '处理复查后再生成' : '先补规则再生成',
          href: salesRulesHrefWithReturn,
          note: reviewQueueGate
            ? '复查队列未清零，不提供草稿下载；处理完成后回到基金详情重新生成正式研究复核。'
            : '当前销售规则硬缺口未清零，不提供草稿下载；补齐真实规则后回到基金详情重新生成正式研究复核。',
        }
      }
      return {
        label: '下载正式研究复核',
        href: appendPurchaseContext(`/api/funds/${encodeURIComponent(firstFundCode)}/research-review-report?format=markdown`, reportPurchasePlan, reportPlannedAmount),
        note: '当前销售规则门禁通过后可下载',
      }
    }
    if ((report.targetType === 'fund_pool' || report.reportType === 'fund_pool_shortlist_report' || report.reportType === 'fund_pool_gap_snapshot') && targetId) {
      return {
        label: blocked ? '下载补证快照' : '下载正式短名单',
        href: appendPurchaseContext(`/api/market/research-lists/${encodeURIComponent(targetId)}/shortlist-report?status=candidate&format=markdown${blocked ? '&snapshot=1' : ''}`, reportPurchasePlan, reportPlannedAmount),
        note: blocked ? reviewQueueGate ? '非正式；只列复查队列、待补规则和研究队列' : '非正式；只列待补规则和研究队列' : '当前销售规则门禁通过后可下载',
      }
    }
    if ((report.targetType === 'comparison' || report.reportType.includes('comparison')) && relatedCodes.length >= 2) {
      return {
        label: '重跑横向比较',
        href: appendPurchaseContext(`/analysis/comparison?codes=${encodeURIComponent(relatedCodes.join(','))}&autoReplay=1`, reportPurchasePlan, reportPlannedAmount),
        note: '重新扫描销售规则与对比矩阵',
      }
    }
    if (report.targetType === 'fund' && firstFundCode) {
      return {
        label: '生成研究备忘录',
        href: `/analysis/fund?fundId=${encodeURIComponent(firstFundCode)}`,
        note: '普通研究备忘录，不替代研究复核',
      }
    }
    return null
  })()
  const validity = gateStatus === 'blocked'
    ? {
        icon: <AlertTriangle className="h-4 w-4" />,
        label: '仅供回看',
        className: 'bg-amber-100 text-amber-800',
        message: reviewQueueGate
          ? '当前复查队列仍有未解决销售规则/R1-R5事件，不能作为继续研究复核的有效留痕。'
          : '当前销售规则存在硬缺口，不能作为继续研究复核的有效留痕。',
      }
    : isGapSnapshot
      ? {
          icon: <FileText className="h-4 w-4" />,
          label: '补证快照',
          className: 'bg-slate-100 text-slate-700',
          message: '这是缺口追踪快照，不是正式研究清单；规则补齐后应重新生成正式研究清单报告。',
        }
      : gateStatus === 'ready'
      ? {
          icon: <CheckCircle2 className="h-4 w-4" />,
          label: '当前有效',
          className: 'bg-emerald-100 text-emerald-800',
          message: '当前销售规则未检测到硬缺口；研究复核仍需复核销售平台实时状态。',
        }
      : gateStatus === 'unknown'
        ? {
            icon: <AlertTriangle className="h-4 w-4" />,
            label: '待扫描',
            className: 'bg-slate-100 text-slate-700',
            message: '销售规则门禁暂未完成扫描，不能直接当作有效研究报告。',
          }
        : {
            icon: <FileText className="h-4 w-4" />,
            label: '普通研究',
            className: 'bg-blue-100 text-blue-800',
            message: '这类报告不承担正式研究复核门禁，只作为研究资料留痕。',
          }
  const reportUsabilityChecklist = [
    {
      label: '销售规则门禁',
      status: gateStatus === 'ready' ? 'done' : gateStatus === 'blocked' ? 'blocked' : gateStatus === 'unknown' ? 'verify' : 'neutral',
      value: gateStatus === 'ready'
        ? '当前无硬缺口'
        : gateStatus === 'blocked'
          ? reviewQueueGate ? `复查队列 ${report.currentSalesRuleGate?.missingCount ?? 0} 项未解决` : `仍缺 ${report.currentSalesRuleGate?.missingCount ?? 0} 项`
          : gateStatus === 'unknown'
            ? '待扫描'
            : '普通研究不适用',
      detail: gateStatus === 'blocked'
        ? `${report.currentSalesRuleGate?.missingItems.slice(0, 5).join('、') || (reviewQueueGate ? '复查队列待处理' : '销售规则待补')}；${reviewQueueGate ? '处理前' : '补齐前'}不能作为正式研究复核留痕。`
        : gateStatus === 'ready'
          ? '仍需在真实销售平台复核实时申赎、费率、限购和风险等级。'
          : gateStatus === 'unknown'
            ? '先完成销售规则扫描，再判断是否可继续用于研究复核。'
            : '仅作为研究资料，不承担销售规则门禁结论。',
      actionLabel: gateStatus === 'blocked' || gateStatus === 'unknown' ? reviewQueueGate ? '处理复查队列' : '补销售规则' : '查看规则',
      actionHref: salesRulesHrefWithReturn,
    },
    {
      label: 'R1-R5门禁版本',
      status: riskLevelPolicy?.status === 'strict_30d_source_backed'
        ? 'done'
        : riskLevelPolicy?.status === 'legacy_or_unmarked'
          ? 'blocked'
          : 'neutral',
      value: riskLevelPolicy?.label || '待识别',
      detail: riskLevelPolicy?.detail || '未返回报告生成时的 R1-R5 来源门禁版本，不能证明旧报告已使用最新规则。',
      actionLabel: riskLevelPolicy?.requiresRegeneration ? '重跑当前门禁' : '进入补证队列',
      actionHref: riskLevelPolicy?.requiresRegeneration ? riskLevelSourceAuditHref : riskLevelSourceAuditHref,
    },
    {
      label: '结构化证据',
      status: report.evidenceSummary?.cards.length ? 'done' : 'verify',
      value: report.evidenceSummary?.cards.length ? `${report.evidenceSummary.cards.length} 个维度` : '待补结构化证据',
      detail: report.evidenceSummary?.cards.length
        ? '报告详情已保留生成口径、画像、销售门禁、净值回放、持仓或短名单决策等结构化证据。'
        : '只有正文难以做研究复核，应回到对应基金、横评或研究清单重新生成结构化报告。',
      actionLabel: '查看证据',
      actionHref: '#report-evidence-summary',
    },
    {
      label: '研究对象入口',
      status: objectAction ? 'done' : 'verify',
      value: objectAction ? objectAction.label : '对象入口待补',
      detail: objectAction
        ? '可以回到原基金、研究清单、经理或横评矩阵，重新核对当前数据。'
        : '报告缺少可追溯对象入口，不能直接推进研究复核。',
      actionLabel: objectAction?.label || '返回报告库',
      actionHref: objectAction?.href || '/reports',
    },
    {
      label: '重新生成/复跑',
      status: rerunAction ? (gateStatus === 'blocked' ? 'blocked' : 'done') : 'verify',
      value: rerunAction?.label || '复跑入口待补',
      detail: rerunAction?.note || '缺少复跑入口时，只能回到原页面手动重新生成。',
      actionLabel: rerunAction?.label || '去选基',
      actionHref: rerunAction?.href || '/market',
    },
  ]
  const checklistClass = (status: string) => {
    if (status === 'done') return 'border-emerald-100 bg-emerald-50 text-emerald-900'
    if (status === 'blocked') return 'border-amber-100 bg-amber-50 text-amber-900'
    if (status === 'verify') return 'border-blue-100 bg-blue-50 text-blue-900'
    return 'border-slate-100 bg-slate-50 text-slate-800'
  }
  const checklistBadgeClass = (status: string) => {
    if (status === 'done') return 'bg-emerald-100 text-emerald-700'
    if (status === 'blocked') return 'bg-amber-100 text-amber-700'
    if (status === 'verify') return 'bg-blue-100 text-blue-700'
    return 'bg-slate-100 text-slate-600'
  }
  const checklistStatusLabel = (status: string) => {
    if (status === 'done') return '已具备'
    if (status === 'blocked') return '先补证'
    if (status === 'verify') return '待复核'
    return '资料'
  }
  const reportEvidenceRows: Array<[string, string, string, string, string]> = [
    ['模块', '对象/字段', '状态/结论', '证据/说明', '下一步/边界'],
    [
      '报告口径',
      report.title,
      `${report.reportTypeLabel || report.reportType || '研究报告'} / ${reportScopeLabel(report.reportType)}`,
      [
        `来源：${report.source || '未标注'}`,
        `报告日：${new Date(report.reportDate).toLocaleDateString('zh-CN')}`,
        `计划：${reportPurchasePlan === 'lump_sum' ? '单笔' : '定投'} ${reportPlannedAmount ? `¥${reportPlannedAmount}` : '金额待识别'}`,
        relatedCodes.length ? `基金：${relatedCodes.join('、')}` : `对象：${targetId || report.id}`,
      ].join('；'),
      '保存过的报告不能绕过最新销售平台适当性复核；只服务基金研究、筛选、分析和基金经理评价。',
    ],
    [
      '报告有效性',
      validity.label,
      gateStatus,
      validity.message,
      `${objectAction?.label || '对象入口待补'}；${rerunAction?.label || '复跑入口待补'}`,
    ],
  ]

  reportUsabilityChecklist.forEach((item) => {
    reportEvidenceRows.push([
      '研究复核清单',
      item.label,
      `${checklistStatusLabel(item.status)} / ${item.value}`,
      item.detail,
      `${item.actionLabel}：${item.actionHref}`,
    ])
  })

  if (report.buyBeforeDecision) {
    reportEvidenceRows.push([
      '研究复核总闸门',
      report.buyBeforeDecision.label || report.buyBeforeDecision.status,
      report.buyBeforeDecision.status,
      [
        report.buyBeforeDecision.hardBlocks.length ? `硬阻断：${report.buyBeforeDecision.hardBlocks.join('；')}` : '',
        report.buyBeforeDecision.cautionFlags.length ? `谨慎项：${report.buyBeforeDecision.cautionFlags.join('；')}` : '',
      ].filter(Boolean).join('；') || '未返回硬阻断，但仍需销售平台实时复核。',
      report.buyBeforeDecision.nextActions.join('；') || '无结构化下一步，回到对象页复核。',
    ])
  }

  if (report.executionAmountGate) {
    reportEvidenceRows.push([
      '计划金额执行门禁',
      report.executionAmountGate.label,
      report.executionAmountGate.status,
      [
        `计划金额：${report.executionAmountGate.plannedAmount ?? reportPlannedAmount ?? '待识别'}`,
        `阻断：${report.executionAmountGate.blockedCount}/${report.executionAmountGate.totalCount}`,
        report.executionAmountGate.blockedFunds.length
          ? `不可执行基金：${report.executionAmountGate.blockedFunds.map((fund) => `${fund.fundName || fund.windCode}(${fund.detail || fund.label})`).join('；')}`
          : report.executionAmountGate.detail,
      ].join('；'),
      '申赎字段必须有 30 天内销售平台/合同/招募说明书等来源背书；金额不满足则阻断研究结论。',
    ])
  }

  if (riskLevelPolicy) {
    reportEvidenceRows.push([
      'R1-R5 来源门禁',
      riskLevelPolicy.label,
      riskLevelPolicy.status,
      [
        riskLevelPolicy.detail,
        `生效日：${riskLevelPolicy.effectiveDate}`,
        `生成日：${riskLevelPolicy.generatedAt}`,
        `信号：${riskLevelPolicy.signals.join('、') || '未检测到'}`,
      ].join('；'),
      riskLevelPolicy.requiresRegeneration
        ? `重跑当前门禁：${riskLevelSourceAuditHref}`
        : 'R1-R5 必须来自 30 天内销售平台、基金合同、招募说明书或可追溯公告；Tushare fund_basic 不计入。',
    ])
  }

  report.sourceDecisionCards?.forEach((card) => {
    reportEvidenceRows.push([
      '来源决策留痕',
      `${card.fundName || card.windCode} ${card.windCode ? `(${card.windCode})` : ''}`,
      card.label,
      [card.latestConclusion, card.bullets.join('；')].filter(Boolean).join('；') || '来源依据待补。',
      card.nextAction || card.hardBoundary || '销售规则、适当性、横评和研究证据未完成前，不进入正式研究候选。',
    ])
  })

  report.purchaseDecisionCards?.forEach((card) => {
    reportEvidenceRows.push([
      '研究清单决策卡',
      `${card.fundName || card.windCode} ${card.windCode ? `(${card.windCode})` : ''}`,
      card.label,
      [
        card.primaryAction,
        card.reasons.length ? `依据：${card.reasons.join('；')}` : '',
        card.reverseTriggers.length ? `反转条件：${card.reverseTriggers.join('；')}` : '',
      ].filter(Boolean).join('；') || '研究决策卡待补。',
      '该卡只保留研究判断和反转条件，不输出申赎指令。',
    ])
  })

  report.evidenceSummary?.cards.forEach((card) => {
    reportEvidenceRows.push([
      '证据摘要',
      card.label,
      card.value,
      card.detail,
      report.evidenceSummary?.nextActions.join('；') || '回到对应基金、横评或研究清单重新生成结构化报告。',
    ])
  })

  if (report.evidenceSummary?.warnings.length) {
    reportEvidenceRows.push([
      '证据摘要',
      '警示',
      '待处理',
      report.evidenceSummary.warnings.join('；'),
      report.evidenceSummary.nextActions.join('；') || '先处理警示，再给正式研究结论。',
    ])
  }

  reportEvidenceRows.push([
    '正式边界',
    '基金研究模块',
    gateStatus === 'ready' && !riskLevelPolicy?.requiresRegeneration && report.executionAmountGate?.status !== 'blocked' ? '可继续研究复核' : '不得作为正式研究结论',
    '销售规则、R1-R5、计划金额、净值回放、正式报告门禁任一失败或缺证时，不能给默认正向信用。',
    '只能用于基金筛选、基金分析、基金经理评价和研究证据复核；不扩展到资产配置、申赎执行或审批流。',
  ])

  const reportEvidenceTsv = reportEvidenceRows.map((row) => row.map(tsvCell).join('\t')).join('\n')
  const downloadReportEvidenceTsv = () => {
    const blob = new Blob([reportEvidenceTsv], { type: 'text/tab-separated-values;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${safeFileStem(report.title || report.id)}_复核证据.tsv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }
  const copyReportEvidenceTsv = async () => {
    setReportEvidenceTsvStatus('idle')
    let copied = false
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(reportEvidenceTsv)
        copied = true
      }
    } catch {
      copied = false
    }
    if (!copied) {
      try {
        const textarea = document.createElement('textarea')
        textarea.value = reportEvidenceTsv
        textarea.setAttribute('readonly', 'true')
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        copied = document.execCommand('copy')
        textarea.remove()
      } catch {
        copied = false
      }
    }
    if (copied) {
      setReportEvidenceTsvStatus('copied')
      return
    }
    downloadReportEvidenceTsv()
    setReportEvidenceTsvStatus('fallback')
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Link
        href="/reports"
        className="inline-flex items-center text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        返回列表
      </Link>

      {/* 报告头部 */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{report.title}</h1>
            <p className="mt-2 text-sm text-gray-500">
              {report.reportTypeLabel || report.reportType || '研究报告'}
              {` · ${reportScopeLabel(report.reportType)}`}
              {targetId ? ` · 对象 ${targetId}` : ''}
              {relatedCodes.length ? ` · 涉及 ${relatedCodes.length} 只基金` : ''}
            </p>
          </div>
          <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold ${validity.className}`}>
            {validity.icon}
            {validity.label}
          </span>
        </div>

        <div className="flex flex-wrap gap-4 text-sm text-gray-600 mb-4">
          <div className="flex items-center">
            <Calendar className="w-4 h-4 mr-2" />
            {new Date(report.reportDate).toLocaleDateString('zh-CN')}
          </div>
          <div className="flex items-center">
            <FileText className="w-4 h-4 mr-2" />
            {report.source}
          </div>
          {report.manager && (
            <Link
              href={`/managers/${report.manager.id}`}
              className="flex items-center text-blue-600 hover:text-blue-800"
            >
              <User className="w-4 h-4 mr-2" />
              {report.manager.name}
              {report.manager.company && ` (${report.manager.company})`}
            </Link>
          )}
        </div>

        {report.tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {report.tags.map((tag, index) => (
              <span
                key={index}
                className="inline-flex items-center px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full"
              >
                <Tag className="w-3 h-3 mr-1" />
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Layers className="h-4 w-4 text-slate-500" />
              报告有效性与下一步
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-600">{validity.message}</p>
            {relatedCodes.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {relatedCodes.slice(0, 10).map((code) => (
                  <span key={code} className="rounded-full bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200">
                    {code}
                  </span>
                ))}
                {relatedCodes.length > 10 ? (
                  <span className="rounded-full bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-500 ring-1 ring-slate-200">
                    +{relatedCodes.length - 10}
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2 md:justify-end">
            <button
              type="button"
              onClick={() => void copyReportEvidenceTsv()}
              data-testid="report-detail-copy-evidence-tsv"
              className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2 text-sm font-semibold text-slate-800 ring-1 ring-slate-200 hover:bg-slate-50"
            >
              <Copy className="h-4 w-4" />
              复制复核 TSV
            </button>
            <button
              type="button"
              onClick={downloadReportEvidenceTsv}
              data-testid="report-detail-download-evidence-tsv"
              className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2 text-sm font-semibold text-slate-800 ring-1 ring-slate-200 hover:bg-slate-50"
            >
              <Download className="h-4 w-4" />
              下载复核 TSV
            </button>
            {gateStatus === 'blocked' || gateStatus === 'unknown' ? (
              <Link
                href={salesRulesHrefWithReturn}
                className="inline-flex items-center gap-2 rounded-xl bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700"
              >
                <ShieldCheck className="h-4 w-4" />
                {reviewQueueGate ? '处理复查队列' : '先补销售规则'}
              </Link>
            ) : null}
            {objectAction ? (
              <Link
                href={objectAction.href}
                className="inline-flex items-center gap-2 rounded-xl bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-800 hover:bg-slate-200"
              >
                <FileText className="h-4 w-4" />
                {objectAction.label}
              </Link>
            ) : null}
            {rerunAction ? (
              <a
                href={rerunAction.href}
                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
                title={rerunAction.note}
              >
                <RefreshCw className="h-4 w-4" />
                {rerunAction.label}
              </a>
            ) : null}
          </div>
        </div>
        {rerunAction?.note ? (
          <div className="mt-3 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600">
            {rerunAction.note}
          </div>
        ) : null}
        {reportEvidenceTsvStatus !== 'idle' ? (
          <div className="mt-3 rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-xs font-medium text-blue-800">
            {reportEvidenceTsvStatus === 'copied' ? '已复制复核 TSV' : '已转下载 TSV'}
          </div>
        ) : null}
        <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50 p-4" data-testid="report-usability-checklist">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-950">报告研究复核清单</div>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                判断这份报告今天还能不能继续用于研究复核；任一硬门禁未过，都只能回看或补证。
              </p>
            </div>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${validity.className}`}>
              {validity.label}
            </span>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {reportUsabilityChecklist.map((item) => (
              <div key={item.label} className={`rounded-2xl border p-4 ${checklistClass(item.status)}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold opacity-75">{item.label}</div>
                    <div className="mt-1 text-base font-bold">{item.value}</div>
                  </div>
                  <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${checklistBadgeClass(item.status)}`}>
                    {checklistStatusLabel(item.status)}
                  </span>
                </div>
                <div className="mt-2 text-xs leading-5 opacity-80">{item.detail}</div>
                <a href={item.actionHref} className="mt-3 inline-flex text-xs font-semibold underline underline-offset-2">
                  {item.actionLabel}
                </a>
              </div>
            ))}
          </div>
        </div>
      </div>

      {report.buyBeforeDecision ? (
        <div className={`rounded-2xl border p-5 shadow ${buyBeforeGateClass(report.buyBeforeDecision.status)}`} data-testid="report-detail-buy-before-gate">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-sm font-semibold">研究复核总闸门</div>
              <div className="mt-1 text-xl font-bold">{report.buyBeforeDecision.label || report.buyBeforeDecision.status}</div>
              <p className="mt-2 text-sm leading-6 opacity-80">
                {report.buyBeforeDecision.hardBlocks[0] || report.buyBeforeDecision.cautionFlags[0] || '当前报告输入未发现硬阻断；正式研究复核仍需复核销售平台实时页面。'}
              </p>
            </div>
            {report.buyBeforeDecision.status === 'blocked_by_hard_gate' ? (
              <Link
                href={salesRulesHrefWithReturn}
                className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700"
              >
                先补硬阻断
              </Link>
            ) : null}
          </div>
          {report.buyBeforeDecision.nextActions.length ? (
            <div className="mt-3 rounded-xl bg-white/60 px-4 py-3 text-xs leading-5 opacity-90">
              下一步：{report.buyBeforeDecision.nextActions.slice(0, 3).join('；')}
            </div>
          ) : null}
          {reportBuyBeforeQueue.length ? (
            <div className="mt-3 grid gap-2 md:grid-cols-3" data-testid="report-detail-buy-before-actions">
              {reportBuyBeforeQueue.slice(0, 3).map((item) => (
                <Link
                  key={item.key}
                  href={reportActionHref(item.href, reportPurchasePlan, reportPlannedAmount, reportReturnHref)}
                  className="rounded-xl bg-white/70 px-3 py-2 text-xs font-semibold ring-1 ring-black/5 hover:bg-white"
                >
                  <div>{item.action}</div>
                  <div className="mt-1 font-normal opacity-75">{item.count} 条线索 · {item.codes.slice(0, 2).join('、') || '报告对象'}</div>
                </Link>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {report.currentSalesRuleGate?.status === 'blocked' ? (
        <div className="rounded-2xl border border-amber-100 bg-amber-50 p-5 text-amber-900 shadow">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex items-center gap-2 font-semibold">
                <ShieldCheck className="h-5 w-5" />
                {reviewQueueGate ? '复查队列未清零，本报告仅供回看' : '当前销售规则待补，本报告仅供回看'}
              </div>
              <p className="mt-2 text-sm leading-6 text-amber-800">
                {reviewQueueGate ? `仍有 ${report.currentSalesRuleGate.missingCount} 项销售规则/R1-R5复查事件未解决` : `仍缺 ${report.currentSalesRuleGate.missingCount} 项销售规则`}
                {report.currentSalesRuleGate.blockedFunds ? `，涉及 ${report.currentSalesRuleGate.blockedFunds} 只基金` : ''}；
                {reviewQueueGate ? '处理前' : '补齐前'}不把这份报告当作可继续研究复核的有效报告。
              </p>
              <p className="mt-1 text-xs leading-5 text-amber-700">
                {report.currentSalesRuleGate.missingItems.slice(0, 8).join('、') || '销售规则待补'}
              </p>
            </div>
            <Link
              href={appendReturnTo(report.currentSalesRuleGate.actionHref, reportReturnHref)}
              className="rounded-xl bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700"
            >
              {reviewQueueGate ? '处理复查队列' : '先补销售规则'}
            </Link>
          </div>
        </div>
      ) : report.currentSalesRuleGate?.status === 'ready' ? (
        <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4 text-sm font-medium text-emerald-800 shadow">
          当前销售规则未检测到硬缺口；研究复核仍需复核销售平台实时状态。
        </div>
      ) : null}

      {report.executionAmountGate ? (
        <div className={`rounded-2xl border p-5 shadow ${
          report.executionAmountGate.status === 'blocked'
            ? 'border-rose-100 bg-rose-50 text-rose-950'
            : report.executionAmountGate.status === 'unknown'
              ? 'border-amber-100 bg-amber-50 text-amber-950'
              : 'border-emerald-100 bg-emerald-50 text-emerald-950'
        }`} data-testid="report-detail-execution-amount-gate">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex items-center gap-2 font-semibold">
                <ShieldCheck className="h-5 w-5" />
                计划金额执行门禁
              </div>
              <div className="mt-2 text-xl font-bold">
                {report.executionAmountGate.plannedAmount ? `¥${report.executionAmountGate.plannedAmount.toLocaleString('zh-CN')} · ` : ''}{report.executionAmountGate.label}
              </div>
              <p className="mt-2 text-sm leading-6 opacity-85">
                {report.executionAmountGate.blockedCount
                  ? `${report.executionAmountGate.blockedCount} 只基金金额不可执行：${report.executionAmountGate.blockedFunds.map((fund) => fund.fundName || fund.windCode).filter(Boolean).join('、') || report.executionAmountGate.detail}`
                  : report.executionAmountGate.detail}
              </p>
            </div>
            {salesRulesHrefWithReturn ? (
              <Link
                href={salesRulesHrefWithReturn}
                className="rounded-xl bg-white px-4 py-2 text-sm font-semibold ring-1 ring-black/5 hover:bg-slate-50"
              >
                复核起购/限购
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}

      {riskLevelPolicy ? (
        <div className={`rounded-2xl border p-5 shadow ${riskLevelPolicyClass(riskLevelPolicy.tone)}`} data-testid="report-risk-level-gate-policy">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex items-center gap-2 font-semibold">
                <ShieldCheck className="h-5 w-5" />
                报告生成时 R1-R5 门禁版本
              </div>
              <p className="mt-2 text-sm leading-6 opacity-85">{riskLevelPolicy.detail}</p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                <span className={`rounded-full px-3 py-1 font-semibold ${riskLevelPolicyBadgeClass(riskLevelPolicy.tone)}`}>
                  {riskLevelPolicy.label}
                </span>
                <span className="rounded-full bg-white/70 px-3 py-1 ring-1 ring-white/70">
                  新规则生效：{riskLevelPolicy.effectiveDate}
                </span>
                <span className="rounded-full bg-white/70 px-3 py-1 ring-1 ring-white/70">
                  信号：{riskLevelPolicy.signals.length ? riskLevelPolicy.signals.slice(0, 3).join('、') : '未检测到'}
                </span>
              </div>
            </div>
            <Link
              href={riskLevelSourceAuditHref}
              className="rounded-xl bg-white px-4 py-2 text-sm font-semibold ring-1 ring-black/5 hover:bg-slate-50"
            >
              {riskLevelPolicy.requiresRegeneration ? '重跑当前门禁' : '复核 R1-R5 来源'}
            </Link>
          </div>
        </div>
      ) : null}

      {(riskLevelAuditCodes.length || report.currentSalesRuleGate) ? (
        <div className="rounded-2xl border border-amber-100 bg-white p-5 text-amber-900 shadow" data-testid="report-risk-source-audit-entry">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex items-center gap-2 font-semibold">
                <ShieldCheck className="h-5 w-5" />
                报告 R1-R5 来源可信度闸门
              </div>
              <p className="mt-2 text-sm leading-6 text-amber-800">
                保存过的报告不能绕过最新销售平台适当性复核；R1-R5 缺失、无来源或来源过期时，只能回看研究结论，不能作为正式候选或研究复核报告依据。
              </p>
              <p className="mt-1 text-xs leading-5 text-amber-700">
                Tushare fund_basic 只提供基金基础档案，不能作为 R1-R5 来源；风险等级必须来自销售平台、基金合同、招募说明书或可追溯公告。
              </p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                <span className="rounded-full bg-amber-50 px-3 py-1 ring-1 ring-amber-100">
                  对象：{riskLevelAuditCodes.slice(0, 5).join('、') || '报告关联基金待识别'}
                </span>
                <span className="rounded-full bg-amber-50 px-3 py-1 ring-1 ring-amber-100">
                  当前销售规则：{gateStatus === 'blocked' ? '待补' : gateStatus === 'ready' ? '未见硬缺口' : '待扫描'}
                </span>
                <span className="rounded-full bg-amber-50 px-3 py-1 ring-1 ring-amber-100">
                  正式路径：未背书前只能研究观察
                </span>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link
                href={salesRulesHrefWithReturn}
                className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-amber-800 ring-1 ring-amber-200 hover:bg-amber-50"
              >
                维护销售规则
              </Link>
              <Link
                href={riskLevelSourceAuditHref}
                className="rounded-xl bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700"
              >
                进入 R1-R5 补证队列
              </Link>
            </div>
          </div>
        </div>
      ) : null}

      {report.evidenceSummary?.cards.length ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow" data-testid="report-evidence-summary">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <ShieldCheck className="h-4 w-4 text-emerald-600" />
                {report.evidenceSummary.title}
              </div>
              <p className="mt-1 text-sm leading-6 text-slate-600">{report.evidenceSummary.subtitle}</p>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
              {report.evidenceSummary.cards.length} 个证据维度
            </span>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {report.evidenceSummary.cards.map((card) => (
              <div key={`${card.label}-${card.value}`} className={`rounded-2xl border p-4 ${evidenceToneClass(card.tone)}`}>
                <div className="text-xs font-semibold opacity-80">{card.label}</div>
                <div className="mt-2 text-lg font-bold">{card.value}</div>
                <div className="mt-2 text-xs leading-5 opacity-80">{card.detail}</div>
              </div>
            ))}
          </div>
          {report.evidenceSummary.warnings.length ? (
            <div className="mt-4 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">
              {report.evidenceSummary.warnings.map((warning) => (
                <div key={warning}>⚠️ {warning}</div>
              ))}
            </div>
          ) : null}
            {report.evidenceSummary.nextActions.length ? (
            <div className="mt-4 rounded-xl bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">
              <span className="font-semibold text-slate-900">下一步：</span>
              {report.evidenceSummary.nextActions.join('；')}
            </div>
          ) : null}
        </div>
      ) : null}

      {report.decisiveAudit ? (
        <div className={`rounded-2xl border p-5 shadow ${decisiveAuditClass(report.decisiveAudit.confidence)}`} data-testid="report-detail-decisive-confidence-audit">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-sm font-semibold">横评置信审计</div>
              <h2 className="mt-1 text-lg font-bold">{report.decisiveAudit.title}</h2>
              <p className="mt-1 text-sm leading-6 opacity-80">
                当前置信度：{report.decisiveAudit.confidence}；通过 {report.decisiveAudit.passCount}/{report.decisiveAudit.totalCount} 条胜负线。
              </p>
            </div>
            <span className="rounded-full bg-white/75 px-3 py-1 text-xs font-semibold ring-1 ring-white/80">
              不输出申赎指令
            </span>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {(report.decisiveAudit.items.length ? report.decisiveAudit.items : [{
              label: '样本不足',
              passed: false,
              detail: '至少需要两只同类候选才能判断第一名是否真的胜出。',
            }]).map((item) => (
              <div key={item.label} className="rounded-xl bg-white/85 p-3 text-xs leading-5 ring-1 ring-white/80">
                <div className="flex items-start justify-between gap-2">
                  <div className="font-semibold">{item.label}</div>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${item.passed ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                    {item.passed ? '通过' : '待复核'}
                  </span>
                </div>
                <div className="mt-2 opacity-80">{item.detail}</div>
              </div>
            ))}
          </div>
          <div className="mt-3 rounded-xl bg-slate-950 px-3 py-2 text-xs leading-5 text-white/90">
            {report.decisiveAudit.boundary}
          </div>
        </div>
      ) : null}

      {report.winLossLines?.length ? (
        <div className="rounded-2xl border border-violet-100 bg-violet-50 p-5 text-violet-950 shadow" data-testid="report-detail-win-loss-lines">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-sm font-semibold">横评胜负线留痕</div>
              <p className="mt-1 text-sm leading-6 text-violet-800">
                展示保存报告时的结构化横评阈值：销售规则、回撤/收益、费用口径、经理样本等是否真正过线。
              </p>
            </div>
            <span className="rounded-full bg-white/75 px-3 py-1 text-xs font-semibold ring-1 ring-violet-200">
              {report.winLossLines.length} 组胜负线
            </span>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {report.winLossLines.slice(0, 6).map((line) => (
              <div key={`${line.challengerCode}-${line.label}`} className="rounded-2xl bg-white/85 p-4 ring-1 ring-violet-100">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold text-violet-700">对照基金</div>
                    <div className="mt-1 font-semibold text-slate-950">
                      {line.challengerName}{line.challengerCode ? ` · ${line.challengerCode}` : ''}
                    </div>
                  </div>
                  <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${winLossStatusClass(line.status)}`}>
                    {line.label} {line.passedChecks}/{line.totalChecks}
                  </span>
                </div>
                <div className="mt-3 text-sm leading-6 text-slate-700">{line.summary}</div>
                {line.thresholds.length ? (
                  <div className="mt-3 space-y-2">
                    {line.thresholds.map((threshold) => (
                      <div key={`${line.challengerCode}-${threshold.key}`} className={`rounded-xl px-3 py-2 text-xs leading-5 ${
                        threshold.passed ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-800'
                      }`}>
                        <span className="font-semibold">{threshold.label}</span>
                        ：{threshold.passed ? '过线' : '待证明'} · {threshold.detail}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {report.sourceDecisionCards?.length ? (
        <div className="rounded-2xl border border-blue-100 bg-blue-50 p-5 text-blue-950 shadow" data-testid="report-detail-source-decision-cards">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-sm font-semibold">来源决策留痕</div>
              <p className="mt-1 text-sm leading-6 text-blue-800">
                展示候选来自筛选、榜单或横评时的结论、依据和硬边界；旧记录缺留痕时不视为正向证据。
              </p>
            </div>
            <span className="rounded-full bg-white/75 px-3 py-1 text-xs font-semibold ring-1 ring-blue-200">
              研究证据链
            </span>
          </div>
          <div className="mt-4 space-y-3">
            {report.sourceDecisionCards.slice(0, 5).map((card) => (
              <div key={`${card.windCode}-${card.label}`} className="rounded-2xl bg-white/80 p-4 ring-1 ring-blue-100">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-semibold">
                    {card.fundName || card.windCode} · {card.label || '来源待补'}
                  </div>
                  {card.windCode ? <span className="rounded-full bg-blue-100 px-2.5 py-1 text-xs font-medium text-blue-800">{card.windCode}</span> : null}
                </div>
                <div className="mt-2 text-sm leading-6 text-blue-900">
                  {card.latestConclusion || card.nextAction || '回到来源页补筛选/榜单/横评依据。'}
                </div>
                {card.bullets.length ? (
                  <div className="mt-3 rounded-xl bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-800">
                    <span className="font-semibold">来源关键依据：</span>{card.bullets.slice(0, 4).join('；')}
                  </div>
                ) : null}
                <div className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                  <span className="font-semibold">来源硬边界：</span>{card.hardBoundary || '销售规则、适当性、横评和研究证据未完成前，不进入正式研究候选。'}
                </div>
                {card.reviewFreshnessLabel ? (
                  <div className="mt-2 rounded-xl bg-fuchsia-50 px-3 py-2 text-xs leading-5 text-fuchsia-900" data-testid="report-detail-review-freshness">
                    <span className="font-semibold">复查时效：</span>{card.reviewFreshnessLabel}
                    {card.reviewFreshnessDetail ? `；${card.reviewFreshnessDetail}` : ''}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {report.purchaseDecisionCards?.length ? (
        <div className="rounded-2xl border border-cyan-100 bg-cyan-50 p-5 text-cyan-950 shadow" data-testid="report-detail-purchase-decision-cards">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-sm font-semibold">研究清单决策卡</div>
              <p className="mt-1 text-sm leading-6 text-cyan-800">
                来自研究清单保存时的结构化证据，展示“当前判断依据”和“结论反转条件”，不从正文里猜。
              </p>
            </div>
            <span className="rounded-full bg-white/75 px-3 py-1 text-xs font-semibold ring-1 ring-cyan-200">
              不输出申赎指令
            </span>
          </div>
          <div className="mt-4 space-y-3">
            {report.purchaseDecisionCards.slice(0, 5).map((card) => (
              <div key={`${card.windCode}-${card.label}`} className="rounded-2xl bg-white/80 p-4 ring-1 ring-cyan-100">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-semibold">
                    {card.fundName || card.windCode} · {card.label || '决策待补'}
                  </div>
                  {card.windCode ? <span className="rounded-full bg-cyan-100 px-2.5 py-1 text-xs font-medium text-cyan-800">{card.windCode}</span> : null}
                </div>
                <div className="mt-2 text-sm leading-6 text-cyan-900">{card.primaryAction || '回到研究清单复核研究证据。'}</div>
                {card.reasons.length ? (
                  <div className="mt-3 rounded-xl bg-cyan-50 px-3 py-2 text-xs leading-5 text-cyan-800">
                    <span className="font-semibold">当前判断依据：</span>{card.reasons.slice(0, 3).join('；')}
                  </div>
                ) : null}
                {card.reverseTriggers.length ? (
                  <div className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                    <span className="font-semibold">结论反转条件：</span>{card.reverseTriggers.slice(0, 3).join('；')}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* 摘要 */}
      {report.summary && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">摘要</h2>
          <p className="text-gray-700 leading-relaxed">{report.summary}</p>
        </div>
      )}

      {/* 要点 */}
      {report.keyPoints && report.keyPoints.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">核心要点</h2>
          <ul className="space-y-2">
            {report.keyPoints.map((point, index) => (
              <li key={index} className="flex items-start">
                <span className="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center text-sm font-medium mr-3 mt-0.5">
                  {index + 1}
                </span>
                <span className="text-gray-700">{point}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 完整内容 */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">完整内容</h2>
        <div className="report-markdown prose max-w-none text-sm text-gray-700 leading-relaxed font-sans">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.content || ''}</ReactMarkdown>
        </div>
      </div>
    </div>
  )
}
