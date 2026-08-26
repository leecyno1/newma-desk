'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { Search, Sparkles, FileText, Calendar, Tag, ChevronLeft, ChevronRight, ShieldCheck, Download } from 'lucide-react'
import { buildBuyBeforeEvidenceQueue, type BuyBeforeEvidenceQueueItem } from '@/lib/report-buy-before-evidence-queue'
import { canonicalResearchHref, materialEvidenceHref } from '@/lib/research-platform/routes'

interface Report {
  id: string
  title: string
  targetId: string
  targetType: string
  reportType: string
  reportTypeLabel: string
  purchasePlan?: 'lump_sum' | 'sip'
  plannedAmount?: number | null
  reportDate: string
  source: string
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
  summary: string | null
  tags: string[]
  actionHref: string
  relatedCodes?: string[]
  decisionSummary?: {
    readyCount: number
    verifyFirstCount: number
    blockedCount: number
    salesRuleGapCount: number
    evidenceGrade: string
    verdict: string
    totalFunds: number
    decisionFundName?: string
    decisionFundCode?: string
    decisionBasis?: string
    decisionReturn?: number | null
    decisionDrawdown?: number | null
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
    topPurchaseDecisionLabel?: string
    topPurchaseDecisionAction?: string
    topPurchaseDecisionReason?: string
    topSourceDecisionLabel?: string
    topSourceDecisionConclusion?: string
    topSourceDecisionNextAction?: string
    topSourceDecisionHardBoundary?: string
    holdingExposureLabel?: string
    holdingExposureScore?: number | string | null
    holdingExposureRisk?: string
    holdingExposureAction?: string
    buyBeforeGateStatus?: string
    buyBeforeGateLabel?: string
    buyBeforeGateHardBlocks?: string[]
    buyBeforeGateCautionFlags?: string[]
    buyBeforeGateNextActions?: string[]
    replayEvidenceGateStatus?: string
    replayEvidenceGateLabel?: string
    replayEvidenceGateMissingEvidence?: string[]
    replayEvidenceGatePassCount?: number
    replayEvidenceGateVerifyCount?: number
    decisiveAudit?: {
      title: string
      confidence: string
      passCount: number
      totalCount: number
      items: Array<{ label: string; passed: boolean; detail: string }>
      boundary: string
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
  }
  currentSalesRuleGate?: {
    status: 'ready' | 'blocked' | 'unknown'
    missingCount: number | null
    missingItems: string[]
    actionHref: string
    source: string
    blockedFunds?: number
  }
  managerId: string | null
  createdAt: string
}

type BuyBeforeGateFacets = {
  all: number
  blockedByHardGate: number
  verifyFirst: number
  researchReady: number
  missing: number
}

const reportTypeOptions = [
  { value: 'all', label: '全部报告', desc: '本地研究沉淀' },
  { value: 'fund_pre_purchase_check', label: '研究复核', desc: '单基金证据闭环' },
  { value: 'fund_comparison_report', label: '横向比较', desc: '多基金替代比较' },
  { value: 'fund_pool_shortlist_report', label: '短名单', desc: '研究样本队列' },
  { value: 'fund_pool_gap_snapshot', label: '补证快照', desc: '仅跟踪规则缺口' },
  { value: 'fund_research_report', label: '基金研究', desc: '单基金研究报告' },
]

const salesGateOptions = [
  { value: 'all', label: '全部留痕', desc: '不过滤当前规则' },
  { value: 'ready', label: '当前有效', desc: '销售规则无硬缺口' },
  { value: 'blocked', label: '仅供回看', desc: '当前规则仍待补' },
  { value: 'unknown', label: '待扫描', desc: '门禁状态未知' },
]

const buyBeforeGateOptions = [
  { value: 'all', label: '全部闸门', desc: '不过滤研究总闸门' },
  { value: 'blocked_by_hard_gate', label: '硬阻断', desc: '不能进入正式研究结论' },
  { value: 'verify_first', label: '先复核', desc: '只能作为研究观察样本' },
  { value: 'research_ready', label: '证据较完整', desc: '仍需正式研究复核' },
  { value: 'missing', label: '未标注', desc: '缺少可解析的研究总闸门' },
]

function initialUrlFilter(options: Array<{ value: string }>, key: string, fallback = 'all') {
  if (typeof window === 'undefined') return fallback
  const value = new URLSearchParams(window.location.search).get(key)
  return options.some((option) => option.value === value) ? value || fallback : fallback
}

function initialUrlText(key: string) {
  if (typeof window === 'undefined') return ''
  return new URLSearchParams(window.location.search).get(key) || ''
}

function reportTypeClass(reportType: string) {
  if (reportType === 'fund_pre_purchase_check') return 'bg-amber-100 text-amber-800'
  if (reportType === 'fund_comparison_report') return 'bg-purple-100 text-purple-800'
  if (reportType === 'fund_pool_shortlist_report') return 'bg-emerald-100 text-emerald-800'
  if (reportType === 'fund_pool_gap_snapshot') return 'bg-slate-100 text-slate-700'
  return 'bg-blue-100 text-blue-800'
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return `${(Number(value) * 100).toFixed(2)}%`
}

function appendReturnTo(href: string, returnTo: string) {
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`
}

function reportPurchasePlan(report: Pick<Report, 'purchasePlan'>) {
  return report.purchasePlan === 'lump_sum' ? 'lump_sum' : 'sip'
}

function purchasePlanLabel(purchasePlan?: 'lump_sum' | 'sip') {
  return purchasePlan === 'lump_sum' ? '一次性配置假设' : '定投假设'
}

function queueCategoryKey(item: Pick<BuyBeforeEvidenceQueueItem, 'key'>) {
  return String(item.key || '').split(':')[0] || 'other_evidence'
}

function reportPlannedAmount(report: Pick<Report, 'plannedAmount' | 'decisionSummary'>) {
  const amount = Number(report.plannedAmount ?? report.decisionSummary?.executionAmountGate?.plannedAmount ?? 0)
  return Number.isFinite(amount) && amount > 0 ? amount : null
}

function isReviewQueueGate(gate?: Report['currentSalesRuleGate'] | null) {
  return Boolean(
    gate?.actionHref?.startsWith('/alerts')
      || gate?.actionHref?.includes('section=review-events')
      || gate?.source?.includes('local.alert_events.sales_rule_evidence'),
  )
}

function appendPurchaseContext(href: string, report: Pick<Report, 'purchasePlan' | 'plannedAmount' | 'decisionSummary'>) {
  const [path, query = ''] = href.split('?')
  const params = new URLSearchParams(query)
  const purchasePlan = reportPurchasePlan(report)
  const plannedAmount = reportPlannedAmount(report)
  params.set('purchasePlan', purchasePlan)
  if (plannedAmount) {
    params.set('plannedAmount', String(plannedAmount))
    params.set(purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(plannedAmount))
  }
  return `${path}?${params.toString()}`
}

function riskLevelSourceQueueHref(report: Pick<Report, 'purchasePlan' | 'plannedAmount' | 'decisionSummary' | 'relatedCodes'>, returnTo = '/reports') {
  const relatedCodes = report.relatedCodes || []
  const params = new URLSearchParams({
    scope: 'market',
    focus: 'risk_level',
    queueMode: 'candidate_missing_risk',
  })
  if (relatedCodes.length) params.set('codes', relatedCodes.join(','))
  return appendReturnTo(
    appendPurchaseContext(materialEvidenceHref(params), report),
    returnTo,
  )
}

function replayEvidenceRerunHref(report: Pick<Report, 'actionHref' | 'purchasePlan' | 'plannedAmount' | 'decisionSummary' | 'relatedCodes'>, returnTo = '/reports') {
  const relatedCodes = report.relatedCodes || []
  if (relatedCodes.length >= 2) {
    return appendReturnTo(
      appendPurchaseContext(`/analysis/comparison?codes=${encodeURIComponent(relatedCodes.join(','))}&autoReplay=1`, report),
      returnTo,
    )
  }
  return report.actionHref
}

function reportFollowUp(report: Report) {
  const relatedCodes = report.relatedCodes || []
  const gate = report.currentSalesRuleGate
  if (gate?.status === 'blocked' || gate?.status === 'unknown') {
    const reviewQueueGate = isReviewQueueGate(gate)
    return {
      label: reviewQueueGate ? '处理复查队列' : '先补销售规则',
      href: appendReturnTo(gate.actionHref ? canonicalResearchHref(gate.actionHref) : appendPurchaseContext(materialEvidenceHref(), report), '/reports'),
      tone: 'amber',
      detail: gate.status === 'blocked'
        ? reviewQueueGate
          ? `复查队列仍有 ${gate.missingCount ?? 0} 项未解决事件；处理前报告只能回看。`
          : `仍缺 ${gate.missingCount ?? 0} 项；补齐后再把报告转为有效研究留痕。`
        : '先完成销售规则扫描，再判断报告是否有效。',
    }
  }
  if (report.reportType.includes('comparison') && relatedCodes.length >= 2) {
    return {
      label: '重跑横向比较',
      href: appendPurchaseContext(`/analysis/comparison?codes=${encodeURIComponent(relatedCodes.join(','))}&autoReplay=1`, report),
      tone: 'purple',
      detail: report.decisionSummary?.decisionFundName
        ? `重新核验 ${report.decisionSummary.decisionFundName} 的排序、费后回放和替代关系。`
        : '重新核验排序、费后回放和替代关系。',
    }
  }
  if (report.reportType === 'fund_pre_purchase_check' && report.targetId) {
    return {
      label: '复核基金详情',
      href: appendPurchaseContext(`/funds/${encodeURIComponent(report.targetId)}`, report),
      tone: 'blue',
      detail: '回到单基金详情复核净值回放、费用、持仓和替代候选。',
    }
  }
  if ((report.reportType === 'fund_pool_shortlist_report' || report.reportType === 'fund_pool_gap_snapshot' || report.targetType === 'fund_pool') && report.targetId) {
    return {
      label: '维护研究短名单',
      href: appendPurchaseContext(`/pools?poolId=${encodeURIComponent(report.targetId)}&status=candidate`, report),
      tone: 'emerald',
      detail: '回到研究短名单维护补证状态和下一轮横向比较。',
    }
  }
  if (report.targetType === 'manager' && report.managerId) {
    return {
      label: '查看基金经理',
      href: `/managers/${encodeURIComponent(report.managerId)}`,
      tone: 'slate',
      detail: '回到基金经理维度复核管理产品和任职证据。',
    }
  }
  return {
    label: '查看报告',
    href: report.actionHref || `/reports/${report.id}`,
    tone: 'slate',
    detail: '进入报告详情查看结构化证据和正文留痕。',
  }
}

function followUpClass(tone: string) {
  if (tone === 'amber') return 'border-amber-100 bg-amber-50 text-amber-900'
  if (tone === 'purple') return 'border-purple-100 bg-purple-50 text-purple-900'
  if (tone === 'blue') return 'border-blue-100 bg-blue-50 text-blue-900'
  if (tone === 'emerald') return 'border-emerald-100 bg-emerald-50 text-emerald-900'
  return 'border-slate-100 bg-slate-50 text-slate-900'
}

function reportScopeLabel(report: Report) {
  if (report.reportType === 'fund_pool_gap_snapshot') return '补证快照'
  if (report.reportType === 'fund_pool_shortlist_report') return '正式短名单报告'
  if (report.reportType === 'fund_comparison_report') return '正式横评报告'
  if (report.reportType === 'fund_pre_purchase_check') return '研究复核报告'
  return '基金研究资料'
}

function buyBeforeGateClass(status?: string) {
  if (status === 'blocked_by_hard_gate') return 'border-rose-100 bg-rose-50 text-rose-900'
  if (status === 'verify_first') return 'border-amber-100 bg-amber-50 text-amber-900'
  if (status === 'research_ready') return 'border-emerald-100 bg-emerald-50 text-emerald-900'
  return 'border-slate-100 bg-slate-50 text-slate-900'
}

function buyBeforeGateBadgeClass(status?: string) {
  if (status === 'blocked_by_hard_gate') return 'bg-rose-100 text-rose-800'
  if (status === 'verify_first') return 'bg-amber-100 text-amber-800'
  if (status === 'research_ready') return 'bg-emerald-100 text-emerald-800'
  return 'bg-slate-100 text-slate-700'
}

function replayEvidenceGateClass(status?: string) {
  if (status === 'pass') return 'border-emerald-100 bg-emerald-50 text-emerald-950'
  if (status === 'verify_first') return 'border-amber-100 bg-amber-50 text-amber-950'
  if (status === 'missing') return 'border-amber-100 bg-amber-50 text-amber-950'
  return 'border-slate-100 bg-slate-50 text-slate-900'
}

function replayEvidenceGateBadgeClass(status?: string) {
  if (status === 'pass') return 'bg-emerald-100 text-emerald-800'
  if (status === 'verify_first') return 'bg-amber-100 text-amber-800'
  if (status === 'missing') return 'bg-amber-100 text-amber-800'
  return 'bg-slate-100 text-slate-700'
}

function decisiveAuditClass(confidence?: string) {
  if (confidence === '领先较稳') return 'border-emerald-100 bg-emerald-50 text-emerald-950'
  if (confidence === '领先很脆弱') return 'border-rose-100 bg-rose-50 text-rose-950'
  if (confidence === '仅补证观察') return 'border-amber-100 bg-amber-50 text-amber-950'
  return 'border-slate-100 bg-slate-50 text-slate-900'
}

function evidenceQueueClass(tone: string) {
  if (tone === 'rose') return 'border-rose-100 bg-rose-50 text-rose-900'
  if (tone === 'purple') return 'border-purple-100 bg-purple-50 text-purple-900'
  if (tone === 'emerald') return 'border-emerald-100 bg-emerald-50 text-emerald-900'
  if (tone === 'blue') return 'border-blue-100 bg-blue-50 text-blue-900'
  return 'border-slate-100 bg-slate-50 text-slate-900'
}

const REPORT_REUSE_MAX_AGE_DAYS = 30

function reportAgeDays(reportDate: string | null | undefined) {
  if (!reportDate) return null
  const createdAt = new Date(reportDate)
  if (Number.isNaN(createdAt.getTime())) return null
  return Math.max(0, Math.floor((Date.now() - createdAt.getTime()) / 86_400_000))
}

function reportReuseClass(status: string) {
  if (status === 'invalidated') return 'border-rose-100 bg-rose-50 text-rose-950'
  if (status === 'rerun_required') return 'border-amber-100 bg-amber-50 text-amber-950'
  return 'border-emerald-100 bg-emerald-50 text-emerald-950'
}

function reportReuseBadgeClass(status: string) {
  if (status === 'invalidated') return 'bg-rose-100 text-rose-800'
  if (status === 'rerun_required') return 'bg-amber-100 text-amber-800'
  return 'bg-emerald-100 text-emerald-800'
}

function reportTodayUsabilityClass(decision: string) {
  if (decision === '只作历史回看') return 'border-rose-100 bg-rose-50 text-rose-950'
  if (decision === '需重跑') return 'border-amber-100 bg-amber-50 text-amber-950'
  return 'border-emerald-100 bg-emerald-50 text-emerald-950'
}

function reportTodayUsabilityBadgeClass(decision: string) {
  if (decision === '只作历史回看') return 'bg-rose-100 text-rose-800'
  if (decision === '需重跑') return 'bg-amber-100 text-amber-800'
  return 'bg-emerald-100 text-emerald-800'
}

function riskLevelPolicyBadgeClass(tone: NonNullable<Report['riskLevelGatePolicy']>['tone']) {
  if (tone === 'emerald') return 'bg-emerald-100 text-emerald-800'
  if (tone === 'amber') return 'bg-amber-100 text-amber-800'
  return 'bg-slate-100 text-slate-700'
}

function reportReuseAssessment(report: Report) {
  const ageDays = reportAgeDays(report.reportDate)
  const followUp = reportFollowUp(report)
  const salesGate = report.currentSalesRuleGate?.status || 'none'
  const buyBeforeStatus = report.decisionSummary?.buyBeforeGateStatus || ''
  const hardBlock = report.decisionSummary?.buyBeforeGateHardBlocks?.[0] || ''
  const caution = report.decisionSummary?.buyBeforeGateCautionFlags?.[0] || ''
  const replayEvidenceGateStatus = report.decisionSummary?.replayEvidenceGateStatus || ''
  const replayEvidenceGateLabel = report.decisionSummary?.replayEvidenceGateLabel || ''
  const replayEvidenceGateMissingEvidence = report.decisionSummary?.replayEvidenceGateMissingEvidence || []
  const isComparisonReport = report.targetType === 'comparison' || report.reportType.includes('comparison')
  const hasReplayEvidenceGap = isComparisonReport && Boolean(replayEvidenceGateStatus) && replayEvidenceGateStatus !== 'pass'
  const replayEvidenceGapSummary = hasReplayEvidenceGap
    ? `${replayEvidenceGateLabel || '测算证据门禁未通过'}，${
        replayEvidenceGateMissingEvidence.length
          ? `待补 ${replayEvidenceGateMissingEvidence.slice(0, 3).join('、')}`
          : '需重跑真实净值、费率、回撤预算和回本等待测算'
      }`
    : ''
  const riskLevelGatePolicy = report.riskLevelGatePolicy

  if (salesGate === 'blocked') {
    const reviewQueueGate = isReviewQueueGate(report.currentSalesRuleGate)
    return {
      status: 'invalidated',
      label: '不可复用',
      reason: reviewQueueGate
        ? `当前复查队列仍有 ${report.currentSalesRuleGate?.missingCount ?? 0} 项销售规则/R1-R5事件未解决，处理前只能回看。${replayEvidenceGapSummary ? `同时${replayEvidenceGapSummary}；处理复查队列后仍需重跑真实回放横评。` : ''}`
        : `当前销售规则仍缺 ${report.currentSalesRuleGate?.missingCount ?? 0} 项，R1-R5、费率、申赎或限购缺口清零前只能回看。${replayEvidenceGapSummary ? `同时${replayEvidenceGapSummary}；补销售规则后仍需重跑真实回放横评。` : ''}`,
      actionLabel: reviewQueueGate ? '处理复查队列' : '补销售规则',
      actionHref: report.currentSalesRuleGate?.actionHref || followUp.href,
      ageDays,
    }
  }
  if (salesGate === 'unknown') {
    return {
      status: 'invalidated',
      label: '门禁待扫描',
      reason: `当前销售规则门禁未知，不能证明 R1-R5、申赎和费用仍有效。${replayEvidenceGapSummary ? `同时${replayEvidenceGapSummary}；扫描销售规则后仍需重跑真实回放横评。` : ''}`,
      actionLabel: '扫描销售规则',
      actionHref: followUp.href,
      ageDays,
    }
  }
  if (buyBeforeStatus === 'blocked_by_hard_gate') {
    return {
      status: 'invalidated',
      label: '硬阻断失效',
      reason: hardBlock || '报告生成时研究总闸门已硬阻断，不能复用为正式研究依据。',
      actionLabel: '查看硬阻断',
      actionHref: report.actionHref,
      ageDays,
    }
  }
  if (riskLevelGatePolicy?.requiresRegeneration) {
    return {
      status: 'rerun_required',
      label: '旧R1-R5门禁',
      reason: `${riskLevelGatePolicy.detail} 生效日 ${riskLevelGatePolicy.effectiveDate}；先进入 R1-R5 来源补证队列，再重跑当前报告。`,
      actionLabel: '重跑R1-R5门禁',
      actionHref: riskLevelSourceQueueHref(report),
      ageDays,
    }
  }
  if (hasReplayEvidenceGap) {
    const missingEvidenceText = replayEvidenceGateMissingEvidence.length
      ? `待补：${replayEvidenceGateMissingEvidence.slice(0, 4).join('、')}。`
      : '需重跑真实净值、费率、回撤预算和回本等待测算。'
    return {
      status: 'rerun_required',
      label: replayEvidenceGateStatus === 'missing' ? '缺测算门禁' : '回放待补证',
      reason: `${replayEvidenceGateLabel || '测算证据门禁未通过'}；${missingEvidenceText} 门禁未过的历史回放不能作为正式研究横评结论。`,
      actionLabel: '重跑真实回放横评',
      actionHref: replayEvidenceRerunHref(report),
      ageDays,
    }
  }
  if (ageDays === null || ageDays > REPORT_REUSE_MAX_AGE_DAYS) {
    return {
      status: 'rerun_required',
      label: '需重跑',
      reason: ageDays === null
        ? '报告日期不可解析，无法证明 NAV、回放、费率和销售风险等级仍在复核窗口内。'
        : `报告已生成 ${ageDays} 天，超过 ${REPORT_REUSE_MAX_AGE_DAYS} 天复核窗口；NAV、费率、R1-R5 和持有回放需要重跑。`,
      actionLabel: followUp.label,
      actionHref: followUp.href,
      ageDays,
    }
  }
  if (buyBeforeStatus === 'verify_first') {
    return {
      status: 'rerun_required',
      label: '先复核再复用',
      reason: caution || '报告仅达到先复核状态，需补同类、持仓、经理任期或持有回放证据后重跑。',
      actionLabel: followUp.label,
      actionHref: followUp.href,
      ageDays,
    }
  }
  if (!buyBeforeStatus) {
    return {
      status: 'rerun_required',
      label: '缺研究闸门',
      reason: '旧报告缺少结构化研究总闸门，不能直接当作当前研究选择证据。',
      actionLabel: followUp.label,
      actionHref: followUp.href,
      ageDays,
    }
  }
  return {
    status: 'research_trace',
    label: '可作研究留痕',
    reason: '当前销售规则无硬缺口，研究总闸门具备结构化结论；正式使用前仍需复核销售平台实时页面。',
    actionLabel: followUp.label,
    actionHref: followUp.href,
    ageDays,
  }
}

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState(() => initialUrlText('search'))
  const [reportType, setReportType] = useState(() => initialUrlFilter(reportTypeOptions, 'reportType'))
  const [salesGate, setSalesGate] = useState(() => initialUrlFilter(salesGateOptions, 'salesGate'))
  const [buyBeforeGate, setBuyBeforeGate] = useState(() => initialUrlFilter(buyBeforeGateOptions, 'buyBeforeGate'))
  const [evidenceQueueCategory, setEvidenceQueueCategory] = useState('all')
  const [evidenceQueueScenario, setEvidenceQueueScenario] = useState<'all' | 'sip' | 'lump_sum'>('all')
  const [buyBeforeGateFacets, setBuyBeforeGateFacets] = useState<BuyBeforeGateFacets | null>(null)
  const [buyBeforeEvidenceQueueFacet, setBuyBeforeEvidenceQueueFacet] = useState<BuyBeforeEvidenceQueueItem[] | null>(null)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)

  const syncUrlFilters = useCallback((next: { reportType?: string; salesGate?: string; buyBeforeGate?: string; search?: string }) => {
    const params = new URLSearchParams(globalThis.location.search)
    const nextValues = {
      reportType,
      salesGate,
      buyBeforeGate,
      search,
      ...next,
    }
    ;([
      ['reportType', nextValues.reportType],
      ['salesGate', nextValues.salesGate],
      ['buyBeforeGate', nextValues.buyBeforeGate],
      ['search', nextValues.search],
    ] as Array<[string, string | undefined]>).forEach(([key, value]) => {
      if (value && value !== 'all') params.set(key, value)
      else params.delete(key)
    })
    const nextQuery = params.toString()
    const nextUrl = `${globalThis.location.pathname}${nextQuery ? `?${nextQuery}` : ''}`
    globalThis.history.replaceState(null, '', nextUrl)
  }, [buyBeforeGate, reportType, salesGate, search])

  const fetchReports = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '20',
        reportType,
        salesGate,
        buyBeforeGate,
        includeBuyBeforeFacets: '1',
        ...(search && { search })
      })

      const response = await fetch(`/api/reports?${params}`)
      const data = await response.json()

      setReports(data.data || [])
      setTotalPages(data.pagination?.totalPages || 1)
      setBuyBeforeGateFacets(data.facets?.buyBeforeGate || null)
      setBuyBeforeEvidenceQueueFacet(data.facets?.buyBeforeEvidenceQueue || null)
    } catch (error) {
      console.error('获取调研报告列表失败:', error)
      setBuyBeforeGateFacets(null)
      setBuyBeforeEvidenceQueueFacet(null)
    } finally {
      setLoading(false)
    }
  }, [page, reportType, salesGate, buyBeforeGate, search])

  useEffect(() => {
    const timeout = globalThis.setTimeout(() => {
      void fetchReports()
    }, 0)
    return () => globalThis.clearTimeout(timeout)
  }, [fetchReports])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    syncUrlFilters({ search })
    void fetchReports()
  }

  const currentPageGateSummary = reports.reduce((summary, report) => {
    const status = report.currentSalesRuleGate?.status || 'none'
    return {
      ready: summary.ready + (status === 'ready' ? 1 : 0),
      blocked: summary.blocked + (status === 'blocked' ? 1 : 0),
      unknown: summary.unknown + (status === 'unknown' ? 1 : 0),
      withoutGate: summary.withoutGate + (status === 'none' ? 1 : 0),
    }
  }, { ready: 0, blocked: 0, unknown: 0, withoutGate: 0 })

  const currentPageBuyBeforeSummary = reports.reduce((summary, report) => {
    const status = report.decisionSummary?.buyBeforeGateStatus || 'missing'
    return {
      blocked: summary.blocked + (status === 'blocked_by_hard_gate' ? 1 : 0),
      verifyFirst: summary.verifyFirst + (status === 'verify_first' ? 1 : 0),
      researchReady: summary.researchReady + (status === 'research_ready' ? 1 : 0),
      missing: summary.missing + (status === 'missing' ? 1 : 0),
    }
  }, { blocked: 0, verifyFirst: 0, researchReady: 0, missing: 0 })
  const buyBeforeSummary = buyBeforeGateFacets
    ? {
        all: buyBeforeGateFacets.all,
        blocked: buyBeforeGateFacets.blockedByHardGate,
        verifyFirst: buyBeforeGateFacets.verifyFirst,
        researchReady: buyBeforeGateFacets.researchReady,
        missing: buyBeforeGateFacets.missing,
      }
    : {
        all: reports.length,
        ...currentPageBuyBeforeSummary,
      }
  const buyBeforeEvidenceQueue = buyBeforeEvidenceQueueFacet || buildBuyBeforeEvidenceQueue(reports)
  const evidenceQueueCategoryOptions = [
    { value: 'all', label: '全部任务', count: buyBeforeEvidenceQueue.length },
    ...Array.from(
      buyBeforeEvidenceQueue.reduce((groups, item) => {
        const categoryKey = queueCategoryKey(item)
        const existing = groups.get(categoryKey) || { value: categoryKey, label: item.title, count: 0 }
        existing.count += 1
        groups.set(categoryKey, existing)
        return groups
      }, new Map<string, { value: string; label: string; count: number }>())
      .values(),
    ),
  ]
  const evidenceQueueScenarioOptions = [
    { value: 'all' as const, label: '全部方式', count: buyBeforeEvidenceQueue.length },
    { value: 'sip' as const, label: '定投假设', count: buyBeforeEvidenceQueue.filter((item) => item.purchasePlan === 'sip').length },
    { value: 'lump_sum' as const, label: '一次性配置假设', count: buyBeforeEvidenceQueue.filter((item) => item.purchasePlan === 'lump_sum').length },
  ]
  const focusedBuyBeforeEvidenceQueue = buyBeforeEvidenceQueue.filter((item) => {
    const categoryMatched = evidenceQueueCategory === 'all' || queueCategoryKey(item) === evidenceQueueCategory
    const scenarioMatched = evidenceQueueScenario === 'all' || item.purchasePlan === evidenceQueueScenario
    return categoryMatched && scenarioMatched
  })

  const downloadBuyBeforeEvidenceQueue = () => {
    const header = ['任务类型', '线索数', '研究方式假设', '研究金额口径', '基金代码', '样例原因', '处理入口']
    const rows = focusedBuyBeforeEvidenceQueue.map((item) => [
      item.title,
      String(item.count),
      purchasePlanLabel(item.purchasePlan),
      item.plannedAmount ? String(item.plannedAmount) : '',
      item.codes.join(','),
      item.reasons.join('；'),
      item.href,
    ])
    const tsv = [header, ...rows]
      .map((row) => row.map((cell) => String(cell || '').replace(/\t/g, ' ').replace(/\n/g, ' ')).join('\t'))
      .join('\n')
    const blob = new Blob([`\ufeff${tsv}`], { type: 'text/tab-separated-values;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `研究补证队列-${new Date().toISOString().slice(0, 10)}.tsv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  const pagePriorityAction = (() => {
    const blockedReports = reports.filter((report) => report.currentSalesRuleGate?.status === 'blocked')
    const unknownReports = reports.filter((report) => report.currentSalesRuleGate?.status === 'unknown')
    const hardBuyBeforeReports = reports.filter((report) => report.decisionSummary?.buyBeforeGateStatus === 'blocked_by_hard_gate')
    const readyDecisionReports = reports.filter((report) =>
      report.currentSalesRuleGate?.status === 'ready' && report.decisionSummary?.decisionFundName,
    )
    const comparisonReports = reports.filter((report) => report.reportType.includes('comparison') && (report.relatedCodes || []).length >= 2)
    if (blockedReports.length) {
      const firstBlocked = blockedReports[0]
      const reviewQueueGate = isReviewQueueGate(firstBlocked.currentSalesRuleGate)
      return {
        title: '优先修复报告有效性',
        label: reviewQueueGate ? '先处理复查队列' : '批量从第一份开始补规则',
        href: appendReturnTo(firstBlocked.currentSalesRuleGate?.actionHref ? canonicalResearchHref(firstBlocked.currentSalesRuleGate.actionHref) : appendPurchaseContext(materialEvidenceHref(), firstBlocked), '/reports'),
        tone: 'amber',
        detail: reviewQueueGate
          ? `当前页 ${blockedReports.length} 份报告存在未解决复查队列事件，先处理 ${firstBlocked.title}，否则只能回看，不能推进研究复核。`
          : `当前页 ${blockedReports.length} 份报告仍有销售规则硬缺口，先补 ${firstBlocked.title}，否则只能回看，不能推进研究复核。`,
      }
    }
    if (unknownReports.length) {
      return {
        title: '先完成门禁扫描',
        label: '去销售规则页扫描',
        href: appendPurchaseContext(materialEvidenceHref(), unknownReports[0]),
        tone: 'slate',
        detail: `当前页 ${unknownReports.length} 份报告门禁未知，先扫描销售规则，再决定是否重跑或转正式留痕。`,
      }
    }
    if (hardBuyBeforeReports.length) {
      const firstHard = hardBuyBeforeReports[0]
      return {
        title: '优先处理研究硬阻断',
        label: '查看第一份硬阻断报告',
        href: firstHard.actionHref,
        tone: 'amber',
        detail: `当前页 ${hardBuyBeforeReports.length} 份基金研究报告存在研究硬阻断：${firstHard.decisionSummary?.buyBeforeGateHardBlocks?.[0] || '销售规则、同类、持仓或经理证据待补'}。`,
      }
    }
    if (readyDecisionReports.length) {
      const firstReady = readyDecisionReports[0]
      return {
        title: '可推进研究复核',
        label: '查看优先对象',
        href: firstReady.decisionSummary?.decisionFundCode
          ? appendPurchaseContext(`/funds/${encodeURIComponent(firstReady.decisionSummary.decisionFundCode)}`, firstReady)
          : firstReady.actionHref,
        tone: 'emerald',
        detail: `当前页 ${readyDecisionReports.length} 份报告已有无硬缺口的优先对象，先复核 ${firstReady.decisionSummary?.decisionFundName || '首个对象'}。`,
      }
    }
    if (comparisonReports.length) {
      const firstComparison = comparisonReports[0]
      return {
        title: '建议重跑横向比较',
        label: '重跑第一组对比',
        href: appendPurchaseContext(`/analysis/comparison?codes=${encodeURIComponent((firstComparison.relatedCodes || []).join(','))}&autoReplay=1`, firstComparison),
        tone: 'purple',
        detail: '当前页有对比报告；重跑矩阵能重新确认销售规则、费后回放和替代关系是否仍然成立。',
      }
    }
    return {
      title: '从选基生成新报告',
      label: '去画像化研究筛选',
      href: canonicalResearchHref('/investor-selection'),
      tone: 'blue',
      detail: '当前页没有需要立即修复的报告；可以从筛选结果生成新的研究复核或对比报告。',
    }
  })()
  const reportReuseRows = reports.map((report) => ({
    report,
    assessment: reportReuseAssessment(report),
  }))
  const reportTodayUsabilityRows = reportReuseRows.map(({ report, assessment }) => {
    const todayDecision = assessment.status === 'research_trace'
      ? '今天可沿用研究'
      : assessment.status === 'rerun_required'
        ? '需重跑'
        : '只作历史回看'
    const hardBoundary = todayDecision === '今天可沿用研究'
      ? '沿用范围仅限研究留痕与样本复核；正式研究仍必须重新核验销售平台实时 R1-R5、费率、申赎、限购和最新净值回放。'
      : '历史报告不能跳过今日销售平台/R1-R5/费率/申赎/限购/真实回放证据；缺口清零前不得沿用为正式研究依据。'
    return {
      report,
      assessment,
      todayDecision,
      hardBoundary,
      nextEvidence: assessment.status === 'research_trace'
        ? '打开原报告对应对象，复核实时销售规则与最新净值回放'
        : assessment.reason,
    }
  })
  const reportTodayUsabilityAudit = [
    {
      decision: '只作历史回看',
      title: '先剔除失效报告',
      detail: '销售规则/R1-R5、研究硬闸门或复查队列仍阻断；这类报告不能沿用到今天的研究动作。',
      rows: reportTodayUsabilityRows.filter((row) => row.todayDecision === '只作历史回看'),
    },
    {
      decision: '需重跑',
      title: '再重跑关键证据',
      detail: `超过 ${REPORT_REUSE_MAX_AGE_DAYS} 天、缺研究闸门、旧 R1-R5 门禁或回放测算证据不足；先重跑后再进入样本复核。`,
      rows: reportTodayUsabilityRows.filter((row) => row.todayDecision === '需重跑'),
    },
    {
      decision: '今天可沿用研究',
      title: '最后沿用研究留痕',
      detail: '仅代表历史证据链可继续参考；不是正式结论，仍要做研究复核。',
      rows: reportTodayUsabilityRows.filter((row) => row.todayDecision === '今天可沿用研究'),
    },
  ]
  const downloadReportTodayUsabilityTsv = () => {
    const header = ['今日结论', '报告标题', '报告类型', '报告年龄', '下一步证据动作', '硬边界', '处理入口']
    const rows = reportTodayUsabilityRows.map((row) => [
      row.todayDecision,
      row.report.title,
      row.report.reportTypeLabel,
      row.assessment.ageDays === null ? '日期待核' : `${row.assessment.ageDays}天`,
      row.nextEvidence,
      row.hardBoundary,
      row.assessment.actionHref,
    ])
    const tsv = [header, ...rows]
      .map((row) => row.map((cell) => String(cell || '').replace(/\t/g, ' ').replace(/\n/g, ' ')).join('\t'))
      .join('\n')
    const blob = new Blob([`\ufeff${tsv}`], { type: 'text/tab-separated-values;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `报告今日沿用决策-${new Date().toISOString().slice(0, 10)}.tsv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }
  const reportReuseQueue = [
    {
      key: 'invalidated',
      title: '不可复用',
      detail: '销售规则、R1-R5 或研究硬闸门已经阻断，只能回看，不能推进正式研究。',
      rows: reportReuseRows.filter((row) => row.assessment.status === 'invalidated'),
    },
    {
      key: 'rerun_required',
      title: '需重跑/复核',
      detail: `超过 ${REPORT_REUSE_MAX_AGE_DAYS} 天复核窗口、缺研究闸门、缺测算证据门禁或仍是先复核状态；NAV、费率、回放和持仓证据要重算。`,
      rows: reportReuseRows.filter((row) => row.assessment.status === 'rerun_required'),
    },
    {
      key: 'research_trace',
      title: '可作为研究留痕',
      detail: '当前销售规则无硬缺口且研究总闸门结构化，可用于继续研究，但仍需正式研究复核。',
      rows: reportReuseRows.filter((row) => row.assessment.status === 'research_trace'),
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end">
        <div className="flex flex-wrap gap-2">
          <Link
            href="/investor-selection"
            className="flex items-center rounded-lg bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-700"
          >
            <ShieldCheck className="mr-2 h-4 w-4" />
            去选基
          </Link>
          <Link
            href="/analysis/fund"
            className="flex items-center rounded-lg border border-blue-200 px-4 py-2 text-blue-700 transition-colors hover:bg-blue-50"
          >
            <Sparkles className="mr-2 h-4 w-4" />
            生成研究报告
          </Link>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-6">
        {reportTypeOptions.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => {
              setReportType(option.value)
              setPage(1)
              syncUrlFilters({ reportType: option.value })
            }}
            className={`rounded-2xl border p-4 text-left transition ${
              reportType === option.value ? 'border-blue-500 bg-blue-50 shadow-sm' : 'border-gray-200 bg-white hover:border-blue-200'
            }`}
          >
            <div className="font-semibold text-gray-900">{option.label}</div>
            <div className="mt-1 text-xs text-gray-500">{option.desc}</div>
          </button>
        ))}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-900">当前销售规则门禁</div>
            <div className="mt-1 text-xs text-slate-500">
              当前页：有效 {currentPageGateSummary.ready}，仅供回看 {currentPageGateSummary.blocked}，待扫描 {currentPageGateSummary.unknown}，普通研究 {currentPageGateSummary.withoutGate}。
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {salesGateOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  setSalesGate(option.value)
                  setPage(1)
                  syncUrlFilters({ salesGate: option.value })
                }}
                title={option.desc}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                  salesGate === option.value
                    ? 'bg-slate-950 text-white'
                    : 'bg-slate-50 text-slate-700 ring-1 ring-slate-200 hover:bg-slate-100'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        {salesGate === 'blocked' ? (
          <div className="mt-3 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-800">
            这里展示的是“历史上生成过，但当前销售规则未补齐”的报告；只能用于回看当时研究过程，不能作为继续研究复核的有效留痕。
          </div>
        ) : null}
      </div>

      <div className="rounded-2xl border border-rose-100 bg-white p-4 shadow" data-testid="report-buy-before-gate-filter">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-900">研究总闸门</div>
            <div className="mt-1 text-xs text-slate-500">
              当前筛选结果 {buyBeforeSummary.all} 份：硬阻断 {buyBeforeSummary.blocked}，先复核 {buyBeforeSummary.verifyFirst}，证据较完整 {buyBeforeSummary.researchReady}，未标注 {buyBeforeSummary.missing}。
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {buyBeforeGateOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  setBuyBeforeGate(option.value)
                  setPage(1)
                  syncUrlFilters({ buyBeforeGate: option.value })
                }}
                title={option.desc}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                  buyBeforeGate === option.value
                    ? 'bg-rose-700 text-white'
                    : 'bg-rose-50 text-rose-800 ring-1 ring-rose-100 hover:bg-rose-100'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        {buyBeforeGate === 'blocked_by_hard_gate' ? (
          <div className="mt-3 rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-xs leading-5 text-rose-800">
            硬阻断报告不能进入正式研究结论；先处理销售规则、R1-R5、同类短板、持仓集中度或经理任期证据，再重新生成报告。
          </div>
        ) : null}
      </div>

      {buyBeforeEvidenceQueue.length ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow" data-testid="report-buy-before-evidence-queue">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-sm font-semibold text-slate-900">研究补证队列</div>
              <p className="mt-1 text-sm leading-6 text-slate-600">
                按当前页报告的硬阻断/风险提示自动聚类；先补证，再重跑研究报告或横向比较。
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                展示 {focusedBuyBeforeEvidenceQueue.length} / {buyBeforeEvidenceQueue.length} 类任务
              </span>
              <button
                type="button"
                onClick={downloadBuyBeforeEvidenceQueue}
                disabled={!focusedBuyBeforeEvidenceQueue.length}
                className="inline-flex items-center gap-1 rounded-full bg-slate-950 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
                data-testid="download-buy-before-evidence-queue"
              >
                <Download className="h-3.5 w-3.5" />
                下载当前补证 TSV
              </button>
            </div>
          </div>
          <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50 p-3" data-testid="report-buy-before-evidence-queue-filter">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="text-xs font-semibold text-slate-700">聚焦补证任务</div>
                <div className="mt-1 text-xs leading-5 text-slate-500">
                  先按缺口类型和研究方式假设收窄任务，避免把定投假设、一次性配置假设和不同证据缺口混在一起处理。
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {evidenceQueueCategoryOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setEvidenceQueueCategory(option.value)}
                    className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                      evidenceQueueCategory === option.value
                        ? 'bg-slate-950 text-white'
                        : 'bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-slate-100'
                    }`}
                  >
                    {option.label} · {option.count}
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2" data-testid="report-buy-before-evidence-queue-scenario-filter">
              {evidenceQueueScenarioOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setEvidenceQueueScenario(option.value)}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                    evidenceQueueScenario === option.value
                      ? 'bg-blue-700 text-white'
                      : 'bg-white text-blue-700 ring-1 ring-blue-100 hover:bg-blue-50'
                  }`}
                >
                  {option.label} · {option.count}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {focusedBuyBeforeEvidenceQueue.map((item) => (
              <div key={item.key} className={`rounded-2xl border p-4 ${evidenceQueueClass(item.tone)}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold opacity-75">{item.title}</div>
                    <div className="mt-1 text-lg font-bold">{item.count} 条线索</div>
                    <div className="mt-1 text-xs font-semibold opacity-80" data-testid="report-buy-before-evidence-queue-context">
                      {purchasePlanLabel(item.purchasePlan)}
                      {item.plannedAmount ? ` · ¥${item.plannedAmount.toLocaleString('zh-CN')}` : ''}
                    </div>
                  </div>
                  <span className="rounded-full bg-white/70 px-2.5 py-1 text-[11px] font-semibold">
                    {item.codes.length ? `${item.codes.length} 只基金` : '待定位'}
                  </span>
                </div>
                <div className="mt-2 text-xs leading-5 opacity-80">{item.detail}</div>
                {item.reasons.length ? (
                  <div className="mt-2 text-xs leading-5 opacity-80">
                    样例：{item.reasons.slice(0, 2).join('；')}
                  </div>
                ) : null}
                <Link
                  href={item.href}
                  className="mt-3 inline-flex text-xs font-semibold underline underline-offset-2"
                >
                  {item.action}
                </Link>
              </div>
            ))}
            {!focusedBuyBeforeEvidenceQueue.length ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-5 text-sm leading-6 text-slate-500">
                当前筛选下没有补证任务；切回“全部任务”或换一个研究方式假设继续排查。
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow" data-testid="report-reuse-validity-queue">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="text-sm font-semibold text-slate-900">报告复用有效性</div>
            <p className="mt-1 text-sm leading-6 text-slate-600">
              报告库不把历史报告默认当作今天可用；按当前销售规则、R1-R5、研究总闸门、测算证据门禁和 {REPORT_REUSE_MAX_AGE_DAYS} 天复核窗口拆分。
            </p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
            当前页 {reports.length} 份
          </span>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {reportReuseQueue.map((lane) => (
            <div key={lane.key} className={`rounded-2xl border p-4 ${reportReuseClass(lane.key)}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold">{lane.title}</div>
                  <div className="mt-1 text-xs leading-5 opacity-80">{lane.detail}</div>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${reportReuseBadgeClass(lane.key)}`}>
                  {lane.rows.length}
                </span>
              </div>
              <div className="mt-3 space-y-2">
                {lane.rows.slice(0, 4).map(({ report, assessment }) => (
                  <div key={`${lane.key}-${report.id}`} className="rounded-xl bg-white/80 p-3 text-xs shadow-sm ring-1 ring-white/80">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate font-semibold text-slate-950">{report.title}</div>
                        <div className="mt-0.5 text-slate-500">
                          {assessment.ageDays === null ? '日期待核' : `${assessment.ageDays} 天前`} · {report.reportTypeLabel}
                        </div>
                      </div>
                      <span className={`shrink-0 rounded-full px-2 py-0.5 font-semibold ${reportReuseBadgeClass(assessment.status)}`}>
                        {assessment.label}
                      </span>
                    </div>
                    <div className="mt-2 leading-5 text-slate-700">{assessment.reason}</div>
                    <Link href={assessment.actionHref} className="mt-2 inline-flex font-semibold underline underline-offset-2">
                      {assessment.actionLabel}
                    </Link>
                  </div>
                ))}
                {lane.rows.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-white/80 bg-white/60 px-3 py-4 text-xs leading-5 opacity-70">
                    当前页暂无该类报告。
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-800">
          复用边界：旧报告如果销售规则/R1-R5 不完整、NAV 与持有回放超过复核窗口、缺结构化研究闸门、或横评缺测算证据门禁，只能作为历史研究留痕，不能作为今天的正式研究依据。
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow" data-testid="report-today-usability-scorecard">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="text-sm font-semibold text-slate-900">今天还能不能沿用这份报告</div>
            <p className="mt-1 text-sm leading-6 text-slate-600">
              把复用有效性翻译成今天的操作结论：先剔除失效报告，再重跑关键证据，最后才允许沿用研究留痕。
            </p>
          </div>
          <button
            type="button"
            onClick={downloadReportTodayUsabilityTsv}
            disabled={!reportTodayUsabilityRows.length}
            className="inline-flex items-center gap-1 self-start rounded-full bg-slate-950 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            data-testid="download-report-today-usability-tsv"
          >
            <Download className="h-3.5 w-3.5" />
            下载今日沿用 TSV
          </button>
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {reportTodayUsabilityAudit.map((lane) => (
            <div key={lane.decision} className={`rounded-2xl border p-4 ${reportTodayUsabilityClass(lane.decision)}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold">{lane.title}</div>
                  <div className="mt-1 text-xs leading-5 opacity-80">{lane.detail}</div>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${reportTodayUsabilityBadgeClass(lane.decision)}`}>
                  {lane.decision} · {lane.rows.length}
                </span>
              </div>
              <div className="mt-3 space-y-2">
                {lane.rows.slice(0, 3).map((row) => (
                  <div key={`${lane.decision}-${row.report.id}`} className="rounded-xl bg-white/80 p-3 text-xs shadow-sm ring-1 ring-white/80">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate font-semibold text-slate-950">{row.report.title}</div>
                        <div className="mt-0.5 text-slate-500">
                          {row.assessment.ageDays === null ? '日期待核' : `${row.assessment.ageDays} 天前`} · {row.report.reportTypeLabel}
                        </div>
                      </div>
                      <span className={`shrink-0 rounded-full px-2 py-0.5 font-semibold ${reportTodayUsabilityBadgeClass(row.todayDecision)}`}>
                        {row.todayDecision}
                      </span>
                    </div>
                    <div className="mt-2 leading-5 text-slate-700">{row.nextEvidence}</div>
                    <div className="mt-2 rounded-lg bg-white/70 px-2 py-1.5 leading-5 text-slate-600">
                      {row.hardBoundary}
                    </div>
                    <Link href={row.assessment.actionHref} className="mt-2 inline-flex font-semibold underline underline-offset-2">
                      {row.assessment.actionLabel}
                    </Link>
                  </div>
                ))}
                {lane.rows.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-white/80 bg-white/60 px-3 py-4 text-xs leading-5 opacity-70">
                    当前页暂无该类报告。
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-xs leading-5 text-rose-800">
          今日沿用硬边界：旧报告不能绕过最新销售平台证据，R1-R5、费率、申赎、限购、净值回放和测算证据任一缺失，都只能降级为补证观察或历史回看。
        </div>
      </div>

      <div className={`rounded-2xl border p-5 shadow ${followUpClass(pagePriorityAction.tone)}`}>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="text-sm font-semibold">{pagePriorityAction.title}</div>
            <p className="mt-2 text-sm leading-6 opacity-85">{pagePriorityAction.detail}</p>
          </div>
          <Link
            href={pagePriorityAction.href}
            className="inline-flex shrink-0 items-center justify-center rounded-xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
          >
            {pagePriorityAction.label}
          </Link>
        </div>
      </div>

      {/* 搜索栏 */}
      <div className="bg-white p-4 rounded-lg shadow">
        <form onSubmit={handleSearch} className="flex gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="搜索报告标题、内容或摘要..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <button
            type="submit"
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            搜索
          </button>
        </form>
      </div>

      {/* 报告列表 */}
      <div className="bg-white rounded-lg shadow">
        {loading ? (
          <div className="p-8 text-center text-gray-500">加载中...</div>
        ) : reports.length === 0 ? (
          <div className="p-8 text-center">
            <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-500">暂无本地基金研究报告</p>
            <Link
              href={canonicalResearchHref('/investor-selection')}
              className="inline-block mt-4 text-blue-600 hover:text-blue-800"
            >
              从画像化研究筛选生成第一份研究报告
            </Link>
          </div>
        ) : (
          <>
            <div className="divide-y divide-gray-200">
              {reports.map((report) => (
                <div
                  key={report.id}
                  className="p-6 transition-colors hover:bg-gray-50"
                >
                  {(() => {
                    const followUp = reportFollowUp(report)
                    const reviewQueueGate = isReviewQueueGate(report.currentSalesRuleGate)
                    return (
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h3 className="text-lg font-semibold text-gray-900 mb-2">
                        {report.title}
                      </h3>
                      <div className="mb-3 flex flex-wrap gap-2">
                        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${reportTypeClass(report.reportType)}`}>
                          {report.reportTypeLabel}
                        </span>
                        <span className="rounded-full bg-white px-2.5 py-1 text-xs text-slate-700 ring-1 ring-slate-200">
                          {reportScopeLabel(report)}
                        </span>
                        {report.targetId ? (
                          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">
                            {report.targetId}
                          </span>
                        ) : null}
                        {report.decisionSummary?.totalFunds ? (
                          <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-700">
                            对象 {report.decisionSummary.totalFunds}
                          </span>
                        ) : null}
                        {report.decisionSummary?.decisionFundName ? (
                          <span className="rounded-full bg-purple-100 px-2.5 py-1 text-xs text-purple-800">
                            优先核查 {report.decisionSummary.decisionFundName}
                          </span>
                        ) : null}
                        {report.decisionSummary?.verifyFirstCount ? (
                          <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs text-amber-800">
                            先补证 {report.decisionSummary.verifyFirstCount}
                          </span>
                        ) : null}
                        {report.decisionSummary?.salesRuleGapCount ? (
                          <span className="rounded-full bg-rose-100 px-2.5 py-1 text-xs text-rose-800">
                            销售规则缺口 {report.decisionSummary.salesRuleGapCount}
                          </span>
                        ) : null}
                        {report.decisionSummary?.buyBeforeGateStatus ? (
                          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${buyBeforeGateBadgeClass(report.decisionSummary.buyBeforeGateStatus)}`}>
                            研究总闸门：{report.decisionSummary.buyBeforeGateLabel || report.decisionSummary.buyBeforeGateStatus}
                          </span>
                        ) : null}
                        {report.decisionSummary?.replayEvidenceGateStatus ? (
                          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${replayEvidenceGateBadgeClass(report.decisionSummary.replayEvidenceGateStatus)}`}>
                            测算证据：{report.decisionSummary.replayEvidenceGateLabel || report.decisionSummary.replayEvidenceGateStatus}
                          </span>
                        ) : null}
                        {report.currentSalesRuleGate?.status === 'blocked' ? (
                          <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">
                            {reviewQueueGate ? '复查队列未清零，仅供回看' : '当前规则待补，仅供回看'}
                          </span>
                        ) : null}
                        {report.currentSalesRuleGate?.status === 'ready' ? (
                          <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-800">
                            当前规则无硬缺口
                          </span>
                        ) : null}
                        {report.riskLevelGatePolicy ? (
                          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${riskLevelPolicyBadgeClass(report.riskLevelGatePolicy.tone)}`}>
                            R1-R5：{report.riskLevelGatePolicy.label}
                          </span>
                        ) : null}
                        {report.decisionSummary?.evidenceGrade ? (
                          <span className="rounded-full bg-blue-100 px-2.5 py-1 text-xs text-blue-800">
                            证据 {report.decisionSummary.evidenceGrade}
                          </span>
                        ) : null}
                      </div>
                      {report.currentSalesRuleGate?.status === 'blocked' ? (
                        <div className="mb-3 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                          <div className="font-semibold">
                            旧{report.reportType === 'fund_comparison_report' ? '横向比较报告' : report.reportType === 'fund_pool_shortlist_report' ? '研究短名单报告' : report.reportType === 'fund_pool_gap_snapshot' ? '补证快照' : '研究复核报告'}仅供回看：
                            {reviewQueueGate ? `复查队列仍有 ${report.currentSalesRuleGate.missingCount} 项未解决事件` : `当前销售规则仍缺 ${report.currentSalesRuleGate.missingCount} 项`}
                            {report.currentSalesRuleGate.blockedFunds ? `，涉及 ${report.currentSalesRuleGate.blockedFunds} 只基金` : ''}
                          </div>
                          <div className="mt-1 text-xs leading-5 text-amber-800">
                            {report.currentSalesRuleGate.missingItems.slice(0, 5).join('、') || (reviewQueueGate ? '复查队列待处理' : '销售规则待补')}；{reviewQueueGate ? '处理前' : '补齐前'}不把这份报告当作可继续研究复核的有效报告。
                          </div>
                          <Link
                            href={appendReturnTo(report.currentSalesRuleGate.actionHref, '/reports')}
                            className="mt-2 inline-flex text-xs font-semibold text-amber-800 underline underline-offset-2"
                          >
                            {reviewQueueGate ? '处理复查队列' : '先补销售规则'}
                          </Link>
                        </div>
                      ) : null}
                      {report.riskLevelGatePolicy?.requiresRegeneration ? (
                        <div className="mb-3 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="report-list-risk-level-policy-card">
                          <div className="font-semibold">
                            R1-R5 旧门禁/未标记：不能证明已采用 30 天来源背书
                          </div>
                          <div className="mt-1 text-xs leading-5 text-amber-800">
                            {report.riskLevelGatePolicy.detail}
                          </div>
                          <Link
                            href={riskLevelSourceQueueHref(report)}
                            className="mt-2 inline-flex text-xs font-semibold text-amber-800 underline underline-offset-2"
                          >
                            进入 R1-R5 来源补证队列
                          </Link>
                        </div>
                      ) : null}
                      {report.decisionSummary?.buyBeforeGateStatus ? (
                        <div className={`mb-3 rounded-xl border px-4 py-3 text-sm ${buyBeforeGateClass(report.decisionSummary.buyBeforeGateStatus)}`} data-testid="report-list-buy-before-gate-card">
                          <div className="font-semibold">
                            研究总闸门：{report.decisionSummary.buyBeforeGateLabel || report.decisionSummary.buyBeforeGateStatus}
                          </div>
                          <div className="mt-1 text-xs leading-5 opacity-80">
                            {report.decisionSummary.buyBeforeGateHardBlocks?.[0]
                              || report.decisionSummary.buyBeforeGateCautionFlags?.[0]
                              || '当前报告输入未发现硬阻断；正式研究仍需复核销售平台实时页面。'}
                          </div>
                          {report.decisionSummary.buyBeforeGateNextActions?.length ? (
                            <div className="mt-1 text-xs leading-5 opacity-80">
                              下一步：{report.decisionSummary.buyBeforeGateNextActions.slice(0, 2).join('；')}
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                      {report.decisionSummary?.replayEvidenceGateStatus ? (
                        <div className={`mb-3 rounded-xl border px-4 py-3 text-sm ${replayEvidenceGateClass(report.decisionSummary.replayEvidenceGateStatus)}`} data-testid="report-list-replay-evidence-gate-card">
                          <div className="font-semibold">
                            测算证据门禁：{report.decisionSummary.replayEvidenceGateLabel || report.decisionSummary.replayEvidenceGateStatus}
                          </div>
                          <div className="mt-1 text-xs leading-5 opacity-80">
                            通过 {report.decisionSummary.replayEvidenceGatePassCount ?? 0} 只；待补/只观察 {report.decisionSummary.replayEvidenceGateVerifyCount ?? 0} 只。
                            {report.decisionSummary.replayEvidenceGateStatus === 'missing'
                              ? ' 这份旧横评未记录测算证据门禁；重跑横评前只能回看，不进入正式研究结论。'
                              : report.decisionSummary.replayEvidenceGateStatus === 'pass'
                              ? ' 历史回放仍只作为压力测试证据，不能替代正式研究复核。'
                              : ' 门禁未过的历史回放不能作为正式研究结论。'}
                          </div>
                          {report.decisionSummary.replayEvidenceGateMissingEvidence?.length ? (
                            <div className="mt-1 text-xs leading-5 opacity-80">
                              待补证据：{report.decisionSummary.replayEvidenceGateMissingEvidence.slice(0, 4).join('、')}
                            </div>
                          ) : null}
                          {report.reportType.includes('comparison') && (report.relatedCodes || []).length >= 2 ? (
                            <Link
                              href={appendPurchaseContext(`/analysis/comparison?codes=${encodeURIComponent((report.relatedCodes || []).join(','))}&autoReplay=1`, report)}
                              className="mt-2 inline-flex text-xs font-semibold underline underline-offset-2"
                            >
                              重跑真实回放横评
                            </Link>
                          ) : null}
                        </div>
                      ) : null}
                      {report.reportType.includes('comparison') && report.decisionSummary?.decisiveAudit ? (
                        <div className={`mb-3 rounded-xl border px-4 py-3 text-sm ${decisiveAuditClass(report.decisionSummary.decisiveAudit.confidence)}`} data-testid="report-list-decisive-confidence-audit">
                          <div className="font-semibold">
                            第一名是否真赢：{report.decisionSummary.decisiveAudit.confidence}
                          </div>
                          <div className="mt-1 text-xs leading-5 opacity-80">
                            通过 {report.decisionSummary.decisiveAudit.passCount}/{report.decisionSummary.decisiveAudit.totalCount} 条胜负线；
                            {report.decisionSummary.decisiveAudit.totalCount === 0
                              ? '至少需要两只带胜负线的同类候选才能判断。'
                              : report.decisionSummary.decisiveAudit.items.filter((item) => !item.passed).slice(0, 3).map((item) => item.label).join('、') || '关键胜负线已通过。'}
                          </div>
                          <div className="mt-1 text-xs leading-5 opacity-80">
                            {report.decisionSummary.decisiveAudit.boundary}
                          </div>
                        </div>
                      ) : null}
                      {report.summary && (
                        <p className="text-sm text-gray-600 mb-3 line-clamp-2">
                          {report.summary}
                        </p>
                      )}
                      {report.decisionSummary?.executionAmountGate ? (
                        <div className={`mb-3 rounded-xl border px-4 py-3 text-sm ${
                          report.decisionSummary.executionAmountGate.status === 'blocked'
                            ? 'border-rose-100 bg-rose-50 text-rose-950'
                            : report.decisionSummary.executionAmountGate.status === 'unknown'
                              ? 'border-amber-100 bg-amber-50 text-amber-950'
                              : 'border-emerald-100 bg-emerald-50 text-emerald-950'
                        }`} data-testid="report-list-execution-amount-gate">
                          <div className="font-semibold">
                            计划金额门禁：{report.decisionSummary.executionAmountGate.plannedAmount ? `¥${report.decisionSummary.executionAmountGate.plannedAmount.toLocaleString('zh-CN')} · ` : ''}{report.decisionSummary.executionAmountGate.label}
                          </div>
                          <div className="mt-1 text-xs leading-5 opacity-80">
                            {report.decisionSummary.executionAmountGate.blockedCount
                              ? `${report.decisionSummary.executionAmountGate.blockedCount} 只金额不可执行：${report.decisionSummary.executionAmountGate.blockedFunds.map((fund) => fund.fundName || fund.windCode).filter(Boolean).slice(0, 3).join('、')}`
                              : report.decisionSummary.executionAmountGate.detail}
                          </div>
                        </div>
                      ) : null}
                      {report.decisionSummary?.decisionFundName ? (
                        <div className="mb-3 rounded-xl border border-purple-100 bg-purple-50 px-4 py-3 text-sm text-purple-900">
                          <div className="font-semibold">
                            研究优先对象：{report.decisionSummary.decisionFundName}
                            {report.decisionSummary.decisionFundCode ? `（${report.decisionSummary.decisionFundCode}）` : ''}
                          </div>
                          <div className="mt-1 text-xs leading-5 text-purple-700">
                            {report.decisionSummary.decisionBasis || '研究复核对象'}；
                            收益 {formatPercent(report.decisionSummary.decisionReturn)}；
                            回撤 {formatPercent(report.decisionSummary.decisionDrawdown)}
                          </div>
                        </div>
                      ) : null}
                      {report.decisionSummary?.topPurchaseDecisionLabel ? (
                        <div className="mb-3 rounded-xl border border-cyan-100 bg-cyan-50 px-4 py-3 text-sm text-cyan-950" data-testid="report-list-purchase-decision-card">
                          <div className="font-semibold">
                            短名单决策卡：{report.decisionSummary.topPurchaseDecisionLabel}
                          </div>
                          <div className="mt-1 text-xs leading-5 text-cyan-800">
                            {report.decisionSummary.purchaseDecisionCards?.[0]?.fundName || report.decisionSummary.purchaseDecisionCards?.[0]?.windCode || '研究样本'}：
                            {report.decisionSummary.topPurchaseDecisionAction || report.decisionSummary.topPurchaseDecisionReason || '回到研究短名单复核证据'}
                          </div>
                          {report.decisionSummary.purchaseDecisionCards?.[0]?.reverseTriggers?.length ? (
                            <div className="mt-1 text-xs leading-5 text-cyan-700">
                              反转条件：{report.decisionSummary.purchaseDecisionCards[0].reverseTriggers.slice(0, 2).join('；')}
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                      {report.decisionSummary?.topSourceDecisionLabel ? (
                        <div className="mb-3 rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-950" data-testid="report-list-source-decision-card">
                          <div className="font-semibold">
                            来源决策留痕：{report.decisionSummary.topSourceDecisionLabel}
                          </div>
                          <div className="mt-1 text-xs leading-5 text-blue-800">
                            {report.decisionSummary.sourceDecisionCards?.[0]?.fundName || report.decisionSummary.sourceDecisionCards?.[0]?.windCode || '研究样本'}：
                            {report.decisionSummary.topSourceDecisionConclusion || report.decisionSummary.topSourceDecisionNextAction || report.decisionSummary.sourceDecisionCards?.[0]?.bullets?.[0] || '回到来源页补筛选/榜单/横评依据'}
                          </div>
                          <div className="mt-1 text-xs leading-5 text-blue-700">
                            硬边界：{report.decisionSummary.topSourceDecisionHardBoundary || '销售规则、R1-R5、横评和研究证据未完成前，不进入正式研究结论。'}
                          </div>
                          {report.decisionSummary.sourceDecisionCards?.[0]?.reviewFreshnessLabel ? (
                            <div className="mt-1 rounded-lg bg-white/75 px-2 py-1 text-xs leading-5 text-blue-800" data-testid="report-list-review-freshness">
                              复查时效：{report.decisionSummary.sourceDecisionCards[0].reviewFreshnessLabel}
                              {report.decisionSummary.sourceDecisionCards[0].reviewFreshnessDetail ? `；${report.decisionSummary.sourceDecisionCards[0].reviewFreshnessDetail}` : ''}
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                      {report.reportType === 'fund_pre_purchase_check' && report.decisionSummary?.holdingExposureLabel ? (
                        <div className="mb-3 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-950" data-testid="report-list-holding-exposure-card">
                          <div className="font-semibold">
                            持仓暴露：{report.decisionSummary.holdingExposureLabel}
                            {report.decisionSummary.holdingExposureScore !== null && report.decisionSummary.holdingExposureScore !== undefined ? ` · ${report.decisionSummary.holdingExposureScore}分` : ''}
                          </div>
                          <div className="mt-1 text-xs leading-5 text-emerald-800">
                            {report.decisionSummary.holdingExposureRisk || '持仓暴露风险待补'}
                          </div>
                          {report.decisionSummary.holdingExposureAction ? (
                            <div className="mt-1 text-xs leading-5 text-emerald-700">
                              研究动作：{report.decisionSummary.holdingExposureAction}
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                      <div className={`mb-3 rounded-xl border px-4 py-3 text-sm ${followUpClass(followUp.tone)}`}>
                        <div className="font-semibold">下一步：{followUp.label}</div>
                        <div className="mt-1 text-xs leading-5 opacity-80">{followUp.detail}</div>
                        <Link
                          href={followUp.href}
                          className="mt-2 inline-flex text-xs font-semibold underline underline-offset-2"
                        >
                          执行下一步
                        </Link>
                      </div>
                      <div className="flex items-center gap-4 text-sm text-gray-500">
                        <div className="flex items-center">
                          <Calendar className="w-4 h-4 mr-1" />
                          {new Date(report.reportDate).toLocaleDateString('zh-CN')}
                        </div>
                        <div className="flex items-center">
                          <FileText className="w-4 h-4 mr-1" />
                          {report.source}
                        </div>
                      </div>
                    </div>
                    <div className="ml-4 flex flex-wrap justify-end gap-2">
                      {report.tags.slice(0, 3).map((tag, index) => (
                        <span
                          key={index}
                          className="inline-flex items-center px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded"
                        >
                          <Tag className="w-3 h-3 mr-1" />
                          {tag}
                        </span>
                      ))}
                      {report.tags.length > 3 && (
                        <span className="text-xs text-gray-500">
                          +{report.tags.length - 3}
                        </span>
                      )}
                      <Link
                        href={report.actionHref || `/reports/${report.id}`}
                        className="inline-flex rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
                      >
                        查看报告
                      </Link>
                    </div>
                  </div>
                    )
                  })()}
                </div>
              ))}
            </div>

            {/* 分页 */}
            <div className="bg-white px-4 py-3 flex items-center justify-between border-t border-gray-200">
              <div className="flex-1 flex justify-between sm:hidden">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                >
                  上一页
                </button>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="ml-3 relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                >
                  下一页
                </button>
              </div>
              <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm text-gray-700">
                    第 <span className="font-medium">{page}</span> 页，共{' '}
                    <span className="font-medium">{totalPages}</span> 页
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="relative inline-flex items-center px-3 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="relative inline-flex items-center px-3 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
