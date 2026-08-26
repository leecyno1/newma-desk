import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'
import { buildBuyBeforeEvidenceQueue } from '@/lib/report-buy-before-evidence-queue'
import { normalizeBuyBeforeDecisionSummary } from '@/lib/report-buy-before-decision'
import { shortlistSourceDecisionCards } from '@/lib/report-shortlist-source-decisions'
import { getSalesRuleGapsForCodes } from '@/lib/sales-rule-gaps'
import { buildReportRiskLevelGatePolicy } from '@/lib/report-risk-level-gate-policy'
import {
  buildComparisonDecisiveAudit,
  normalizeComparisonWinLossLines,
} from '@/lib/comparison-decisive-audit'
import { materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const reportTypeLabel = (reportType: string | null | undefined) => {
  if (reportType === 'fund_pool_gap_snapshot') return '研究清单补证快照'
  if (reportType === 'fund_pool_shortlist_report') return '研究短名单报告'
  if (reportType === 'fund_pre_purchase_check') return '研究复核报告'
  if (reportType?.includes('comparison')) return '对比研究报告'
  if (reportType === 'fund_research_report') return '基金研究报告'
  if (reportType?.includes('manager')) return '基金经理研究报告'
  if (reportType?.includes('fund')) return '基金研究报告'
  return '研究报告'
}

const cleanPreview = (content: string) =>
  content
    .replace(/^<!--[\s\S]*?-->\s*/u, '')
    .replace(/^好的[，,][\s\S]*?---\s*/u, '')
    .trim()

const generationSourceLabel = (mode: string, fallback: string) => {
  if (mode === 'llm') return fallback
  if (mode === 'deterministic_evidence_backed') return '本地证据报告'
  if (mode === 'deterministic_pre_purchase_check') return '本地研究复核'
  if (mode === 'deterministic_fund_pool_shortlist') return '本地短名单核查'
  if (mode === 'deterministic_fund_pool_gap_snapshot') return '本地补证快照'
  if (mode === 'deterministic_fund_comparison') return '本地横向比较'
  return fallback
}

const asRecord = (value: unknown): Record<string, unknown> => {
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      return parsed && typeof parsed === 'object' ? parsed : {}
    } catch {
      return {}
    }
  }
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

const asStringArray = (value: unknown) =>
  Array.isArray(value)
    ? value.map((item) => String(item || '').trim().toUpperCase()).filter(Boolean)
    : []

const asTextArray = (value: unknown) =>
  Array.isArray(value)
    ? value.map((item) => String(item || '').trim()).filter(Boolean)
    : []

const comparisonDecisiveAuditFromSources = (dataSources: Record<string, unknown>, generationParams: Record<string, unknown>) => {
  const summary = asRecord(dataSources.summary)
  const existingAudit = asRecord(generationParams.decisiveAudit || dataSources.decisiveAudit || summary.decisiveAudit)
  if (existingAudit.title) return existingAudit
  const winLossLines = [
    ...normalizeComparisonWinLossLines(dataSources.decisionWinLossLines),
    ...normalizeComparisonWinLossLines(summary.decisionWinLossLines),
  ]
  return buildComparisonDecisiveAudit(winLossLines)
}

type ReportPurchasePlan = 'lump_sum' | 'sip'

function reportPurchasePlanFromSources(dataSources: Record<string, unknown>, generationParams: Record<string, unknown>) {
  const investorContext = asRecord(dataSources.investorContext)
  const summary = asRecord(dataSources.summary)
  const rawPlan = String(dataSources.purchasePlan || investorContext.purchasePlan || generationParams.purchasePlan || summary.purchasePlan || '').trim()
  return rawPlan === 'lump_sum' || rawPlan === 'sip' ? rawPlan as ReportPurchasePlan : 'sip'
}

function reportPlannedAmountFromSources(dataSources: Record<string, unknown>, generationParams: Record<string, unknown>) {
  const investorContext = asRecord(dataSources.investorContext)
  const summary = asRecord(dataSources.summary)
  const amount = Number(dataSources.plannedAmount ?? generationParams.plannedAmount ?? summary.plannedAmount ?? investorContext.plannedAmount)
  return Number.isFinite(amount) && amount > 0 ? amount : null
}

function salesRulesHrefForCodes(codes: string[], purchasePlan: ReportPurchasePlan, plannedAmount?: number | null) {
  const normalizedCodes = Array.from(new Set(codes.map((code) => String(code || '').trim().toUpperCase()).filter(Boolean)))
  const params = new URLSearchParams({ purchasePlan })
  if (plannedAmount && Number.isFinite(plannedAmount) && plannedAmount > 0) params.set('plannedAmount', String(plannedAmount))
  if (normalizedCodes.length) params.set('codes', normalizedCodes.join(','))
  return materialEvidenceHref(params)
}

function appendReturnTo(href: string, returnTo: string) {
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`
}

type ReportAlertEvent = {
  id?: string
  fund_id?: string | null
  event_type?: string
  severity?: string
  title?: string
  message?: string
  status?: string
  details?: unknown
}

function alertWindCode(event: ReportAlertEvent) {
  const details = asRecord(event.details)
  return String(details.wind_code || details.fund_code || event.fund_id || '').trim().toUpperCase()
}

async function fetchActiveSalesRuleEvidenceAlertsByCode() {
  const alertsUrl = new URL('/api/alerts', backendApiBaseUrl)
  const response = await fetch(alertsUrl, { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || '复查队列读取失败')
  }
  const alertMap = new Map<string, ReportAlertEvent[]>()
  const events = Array.isArray(payload.events) ? payload.events as ReportAlertEvent[] : []
  events
    .filter((event) => event.event_type === 'sales_rule_evidence' && event.status !== 'resolved')
    .forEach((event) => {
      const code = alertWindCode(event)
      if (!code) return
      const current = alertMap.get(code) || []
      current.push(event)
      alertMap.set(code, current)
    })
  return alertMap
}

function reportReviewQueueAlerts(report: MappedReport, alertMap: Map<string, ReportAlertEvent[]>) {
  const codes = report.relatedCodes.length
    ? report.relatedCodes
    : report.targetType === 'fund' && report.targetId
      ? [report.targetId]
      : []
  const normalizedCodes = Array.from(new Set(codes.map((code) => String(code || '').trim().toUpperCase()).filter(Boolean)))
  return normalizedCodes.flatMap((code) => alertMap.get(code) || [])
}

function reviewQueueGateForReport(
  report: MappedReport,
  alertMap: Map<string, ReportAlertEvent[]>,
  purchasePlan: ReportPurchasePlan,
  plannedAmount?: number | null,
) {
  const alerts = reportReviewQueueAlerts(report, alertMap)
  if (!alerts.length) return null
  const alertCodes = Array.from(new Set(alerts.map(alertWindCode).filter(Boolean)))
  const missingItems = alerts.slice(0, 8).map((event) => {
    const code = alertWindCode(event)
    const title = String(event.title || '销售规则/R1-R5证据待补').trim()
    const message = String(event.message || '').trim()
    return `复查队列未解决：${code ? `${code}：` : ''}${title}${message ? `（${message}` : ''}${message ? '）' : ''}`
  })
  return {
    status: 'blocked' as const,
    missingCount: alerts.length,
    missingItems,
    actionHref: reviewEventsHref(),
    source: 'local.alert_events.sales_rule_evidence',
    blockedFunds: alertCodes.length,
  }
}

function executionAmountGateSummary(dataSources: Record<string, unknown>, generationParams: Record<string, unknown>) {
  const members = Array.isArray(dataSources.members) ? dataSources.members.map(asRecord) : []
  const gates = members
    .map((member) => ({
      windCode: String(member.windCode || '').trim().toUpperCase(),
      fundName: String(member.fundName || member.windCode || '').trim(),
      gate: asRecord(member.executionAmountGate),
    }))
    .filter((item) => String(item.gate.status || '').trim())
  const plannedAmount = reportPlannedAmountFromSources(dataSources, generationParams)
  if (!gates.length && !plannedAmount) return null

  const blocked = gates.filter((item) => item.gate.status === 'blocked')
  const unknown = gates.filter((item) => item.gate.status === 'unknown')
  const first = blocked[0] || unknown[0] || gates[0] || null
  const status = blocked.length ? 'blocked' : unknown.length ? 'unknown' : 'pass'
  return {
    status,
    label: String(first?.gate.label || (status === 'pass' ? '计划金额可执行' : status === 'blocked' ? '计划金额不可执行' : '计划金额待核')).trim(),
    detail: String(first?.gate.detail || (plannedAmount ? `报告计划金额 ${plannedAmount.toLocaleString('zh-CN')} 元；需结合销售规则实时复核。` : '报告未记录计划金额，不能判断起购、定投起点或限购约束。')).trim(),
    plannedAmount: plannedAmount ?? (Number(first?.gate.plannedAmount || 0) || null),
    blockedCount: blocked.length,
    totalCount: gates.length,
    blockedFunds: blocked.slice(0, 5).map((item) => ({
      windCode: item.windCode,
      fundName: item.fundName,
      label: String(item.gate.label || '').trim(),
      detail: String(item.gate.detail || '').trim(),
    })),
  }
}

function shortlistDecisionCards(members: unknown[]) {
  return members
    .map((member) => {
      const record = asRecord(member)
      const card = asRecord(record.decisionCard)
      const salesRuleMissingCount = Number(record.salesRuleMissingCount || 0)
      const nextActions = Array.isArray(record.nextActions) ? record.nextActions.map((item) => String(item || '').trim()).filter(Boolean) : []
      const missingItems = Array.isArray(record.salesRuleMissingItems) ? record.salesRuleMissingItems.map((item) => String(item || '').trim()).filter(Boolean) : []
      const label = String(card.label || record.decisionLabel || '').trim()
      return {
        windCode: String(record.windCode || '').trim().toUpperCase(),
        fundName: String(record.fundName || record.windCode || '').trim(),
        label,
        primaryAction: String(card.primaryAction || nextActions[0] || (salesRuleMissingCount ? '优先补销售规则，再决定是否保留候选' : '回到研究清单复核研究证据')).trim(),
        reasons: Array.isArray(card.reasons) && card.reasons.length
          ? card.reasons.map((item) => String(item || '').trim()).filter(Boolean)
          : [
              salesRuleMissingCount ? `销售规则仍缺 ${salesRuleMissingCount} 项${missingItems.length ? `：${missingItems.slice(0, 3).join('、')}` : ''}` : '',
              nextActions[0] || '',
            ].filter(Boolean),
        reverseTriggers: Array.isArray(card.reverseTriggers) && card.reverseTriggers.length
          ? card.reverseTriggers.map((item) => String(item || '').trim()).filter(Boolean)
          : [
              salesRuleMissingCount ? '销售规则硬缺口清零，并记录来源日期与平台字段' : '',
              '补齐同类横评、成本证据和真实回放后重新生成短名单',
            ].filter(Boolean),
      }
    })
    .filter((card) => card.windCode || card.fundName || card.label || card.primaryAction)
}

function mapReport(report: Record<string, unknown>) {
  const dataSources = asRecord(report.data_sources)
  const generationParams = asRecord(report.generation_params)
  const summaryData = asRecord(dataSources.summary)
  const holdingExposure = asRecord(dataSources.holdingExposureDecision)
  const dataSourceItems = Array.isArray(dataSources.items) ? dataSources.items : []
  const dataSourceMembers = Array.isArray(dataSources.members) ? dataSources.members : []
  const decisionCards = shortlistDecisionCards(dataSourceMembers)
  const purchasePlan = reportPurchasePlanFromSources(dataSources, generationParams)
  const plannedAmount = reportPlannedAmountFromSources(dataSources, generationParams)
  const amountGateSummary = executionAmountGateSummary(dataSources, generationParams)
  const itemCodes = dataSourceItems
    .map((item) => asRecord(item).windCode)
    .map((code) => String(code || '').trim().toUpperCase())
    .filter(Boolean)
  const memberCodes = dataSourceMembers
    .map((member) => asRecord(member).windCode)
    .map((code) => String(code || '').trim().toUpperCase())
    .filter(Boolean)
  const targetId = String(report.target_id || '')
  const reportType = typeof report.report_type === 'string' ? report.report_type : ''
  const targetType = String(report.target_type || '')
  const isComparisonReport = targetType === 'comparison' || reportType.includes('comparison')
  const content = cleanPreview(String(report.content || report.content_preview || ''))
  const sourceDecisionCards = shortlistSourceDecisionCards(dataSourceMembers, { content })
  const buyBeforeDecision = normalizeBuyBeforeDecisionSummary(dataSources.buy_before_decision, {
    content,
    summary: summaryData,
  })
  const source = String(generationParams.provider || dataSources.source || 'PostgreSQL')
  const model = generationParams.model ? String(generationParams.model) : ''
  const mode = String(generationParams.mode || '')
  const sourceLabel = generationSourceLabel(mode, source)
  const targetLabel = targetType === 'fund'
    ? '基金'
    : targetType === 'fund_pool'
      ? '研究清单'
      : targetType === 'comparison'
        ? '基金对比'
        : '基金经理'
  const comparisonCodes = targetType === 'comparison' || reportType.includes('comparison')
    ? Array.from(new Set([...asStringArray(dataSources.codes), ...itemCodes]))
    : []
  const poolCodes = targetType === 'fund_pool' || reportType === 'fund_pool_shortlist_report' || reportType === 'fund_pool_gap_snapshot'
    ? Array.from(new Set(memberCodes))
    : []
  const relatedCodes = Array.from(new Set([
    ...(targetType === 'fund' && targetId ? [targetId.trim().toUpperCase()] : []),
    ...comparisonCodes,
    ...poolCodes,
  ].filter(Boolean)))
  const riskLevelGatePolicy = buildReportRiskLevelGatePolicy({
    targetType,
    reportType,
    relatedCodes,
    createdAt: String(report.created_at || ''),
    content,
    dataSources,
    generationParams,
  })
  const totalFunds = Number(generationParams.totalFunds ?? summaryData.totalMembers ?? summaryData.totalFunds ?? 0)
  const rawReplayEvidenceGateStatus = String(generationParams.decisionReplayEvidenceGateStatus ?? summaryData.decisionReplayEvidenceGateStatus ?? '').trim()
  const replayEvidenceGateStatus = rawReplayEvidenceGateStatus || (isComparisonReport ? 'missing' : '')
  const replayEvidenceGateMissingEvidence = asTextArray(generationParams.decisionReplayEvidenceGateMissingEvidence ?? summaryData.decisionReplayEvidenceGateMissingEvidence)
  const replayEvidenceGateVerifyCount = Number(generationParams.replayEvidenceGateVerifyCount ?? summaryData.replayEvidenceGateVerifyCount ?? (replayEvidenceGateStatus === 'missing' ? totalFunds : 0))
  const decisiveAudit = isComparisonReport ? comparisonDecisiveAuditFromSources(dataSources, generationParams) : null

  return {
    id: report.id,
    title: `${targetId} ${reportTypeLabel(reportType)}`,
    targetId,
    targetType,
    reportType,
    reportTypeLabel: reportTypeLabel(reportType),
    reportDate: report.created_at,
    source: mode === 'llm' && model ? `${sourceLabel} · ${model}` : sourceLabel,
    summary: content.slice(0, 300),
    content,
    actionHref: `/reports/${report.id}`,
    decisionSummary: {
      readyCount: Number(generationParams.readyCount ?? summaryData.readyCount ?? 0),
      verifyFirstCount: Number(generationParams.verifyFirstCount ?? summaryData.verifyFirstCount ?? 0),
      blockedCount: Number(generationParams.blockedCount ?? summaryData.blockedCount ?? 0),
      salesRuleGapCount: Number(generationParams.salesRuleGapCount ?? generationParams.salesHardGapCount ?? summaryData.salesRuleGapCount ?? summaryData.salesHardGapCount ?? 0),
      evidenceGrade: String(generationParams.evidenceGrade || ''),
      verdict: String(generationParams.verdict || ''),
      totalFunds,
      decisionFundName: String(generationParams.decisionFundName ?? summaryData.decisionFundName ?? ''),
      decisionFundCode: String(generationParams.decisionFundCode ?? summaryData.decisionFundCode ?? ''),
      decisionBasis: String(generationParams.decisionBasis ?? summaryData.decisionBasis ?? ''),
      decisionReturn: generationParams.decisionReturn ?? summaryData.decisionReturn ?? null,
      decisionDrawdown: generationParams.decisionDrawdown ?? summaryData.decisionDrawdown ?? null,
      purchaseDecisionCards: decisionCards.slice(0, 3),
      topPurchaseDecisionLabel: decisionCards[0]?.label || '',
      topPurchaseDecisionAction: decisionCards[0]?.primaryAction || '',
      topPurchaseDecisionReason: decisionCards[0]?.reasons?.[0] || '',
      sourceDecisionCards: sourceDecisionCards.slice(0, 3),
      topSourceDecisionLabel: sourceDecisionCards[0]?.label || '',
      topSourceDecisionConclusion: sourceDecisionCards[0]?.latestConclusion || '',
      topSourceDecisionNextAction: sourceDecisionCards[0]?.nextAction || '',
      topSourceDecisionHardBoundary: sourceDecisionCards[0]?.hardBoundary || '',
      holdingExposureLabel: String(holdingExposure.label || generationParams.holdingExposureLabel || '').trim(),
      holdingExposureScore: holdingExposure.score ?? generationParams.holdingExposureScore ?? null,
      holdingExposureRisk: String(holdingExposure.primaryRisk || '').trim(),
      holdingExposureAction: String(holdingExposure.nextAction || '').trim(),
      buyBeforeGateStatus: buyBeforeDecision?.status || '',
      buyBeforeGateLabel: buyBeforeDecision?.label || '',
      buyBeforeGateHardBlocks: buyBeforeDecision?.hardBlocks || [],
      buyBeforeGateCautionFlags: buyBeforeDecision?.cautionFlags || [],
      buyBeforeGateNextActions: buyBeforeDecision?.nextActions || [],
      executionAmountGate: amountGateSummary,
      replayEvidenceGateStatus,
      replayEvidenceGateLabel: String(generationParams.decisionReplayEvidenceGateLabel ?? summaryData.decisionReplayEvidenceGateLabel ?? (replayEvidenceGateStatus === 'missing' ? '旧横评缺测算证据门禁' : '')),
      replayEvidenceGateMissingEvidence: replayEvidenceGateMissingEvidence.length
        ? replayEvidenceGateMissingEvidence
        : replayEvidenceGateStatus === 'missing'
          ? ['测算采信门禁未标记', '需重跑真实净值、费率、回撤预算回放']
          : [],
      replayEvidenceGatePassCount: Number(generationParams.replayEvidenceGatePassCount ?? summaryData.replayEvidenceGatePassCount ?? 0),
      replayEvidenceGateVerifyCount,
      decisiveAudit,
    },
    tags: [
      targetLabel,
      reportTypeLabel(reportType),
      sourceLabel,
    ].filter(Boolean),
    managerId: targetType === 'manager' ? targetId : null,
    relatedCodes,
    riskLevelGatePolicy,
    purchasePlan,
    plannedAmount,
    comparisonCodes,
    poolCodes,
    keyPoints: [],
    createdAt: report.created_at,
  }
}

type MappedReport = ReturnType<typeof mapReport>
type SalesRuleGateReport = MappedReport & {
  currentSalesRuleGate?: {
    status: 'ready' | 'blocked' | 'unknown'
  }
}

function isFundResearchReport(report: MappedReport) {
  if (report.reportType === 'fund_research_report') return true
  if (report.reportType === 'fund_standard_analysis') return true
  if (report.targetType !== 'fund') return false
  return ![
    'fund_pre_purchase_check',
    'fund_pool_shortlist_report',
    'fund_pool_gap_snapshot',
  ].includes(report.reportType) && !report.reportType.includes('comparison')
}

function buyBeforeGateFacets(reports: MappedReport[]) {
  return reports.reduce((summary, report) => {
    const status = report.decisionSummary.buyBeforeGateStatus || 'missing'
    return {
      all: summary.all + 1,
      blockedByHardGate: summary.blockedByHardGate + (status === 'blocked_by_hard_gate' ? 1 : 0),
      verifyFirst: summary.verifyFirst + (status === 'verify_first' ? 1 : 0),
      researchReady: summary.researchReady + (status === 'research_ready' ? 1 : 0),
      missing: summary.missing + (status === 'missing' ? 1 : 0),
    }
  }, { all: 0, blockedByHardGate: 0, verifyFirst: 0, researchReady: 0, missing: 0 })
}

const MAX_FILTER_SCAN = 2000
const BACKEND_PAGE_SIZE = 100

async function fetchBackendReports(params: {
  page: number
  limit: number
  targetType: string | null
}) {
  const backendUrl = new URL('/api/reports', backendApiBaseUrl)
  backendUrl.searchParams.set('page', String(params.page))
  backendUrl.searchParams.set('limit', String(params.limit))
  if (params.targetType) backendUrl.searchParams.set('target_type', params.targetType)

  const response = await fetch(backendUrl, { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || '报告列表读取失败')
  }

  return payload
}

async function fetchReportsForLocalFiltering(targetType: string | null) {
  const reports: MappedReport[] = []
  let backendTotal = 0
  let backendPage = 1

  while (reports.length < MAX_FILTER_SCAN) {
    const payload = await fetchBackendReports({
      page: backendPage,
      limit: BACKEND_PAGE_SIZE,
      targetType,
    })
    const batch = (payload.reports || []).map(mapReport)
    reports.push(...batch)
    backendTotal = Number(payload.total || reports.length)

    if (batch.length === 0 || reports.length >= backendTotal) break
    backendPage += 1
  }

  return reports
}

async function attachCurrentSalesRuleGate(reports: MappedReport[]) {
  const codes = Array.from(new Set([
    ...reports
      .filter((report) => report.targetType === 'fund' && report.reportType === 'fund_pre_purchase_check')
      .map((report) => report.targetId.trim().toUpperCase())
      .filter(Boolean),
    ...reports.flatMap((report) => report.comparisonCodes),
    ...reports.flatMap((report) => report.poolCodes),
  ]))
  if (!codes.length) return reports

  try {
    const reviewAlertMap = await fetchActiveSalesRuleEvidenceAlertsByCode()
    const reportsByPlan = reports.reduce((groups, report) => {
      const plan = report.purchasePlan === 'lump_sum' ? 'lump_sum' : 'sip'
      const amountKey = report.plannedAmount && Number.isFinite(Number(report.plannedAmount)) && Number(report.plannedAmount) > 0 ? String(Number(report.plannedAmount)) : 'none'
      const key = `${plan}:${amountKey}`
      if (!groups[key]) groups[key] = []
      groups[key].push(report)
      return groups
    }, {} as Record<string, MappedReport[]>)
    const gapMapsByPlan = new Map<string, Map<string, Awaited<ReturnType<typeof getSalesRuleGapsForCodes>>['gaps'][number]>>()
    let gapSource = 'report_codes_plus_local_sales_rules'
    for (const [scanKey, planReports] of Object.entries(reportsByPlan)) {
      const [purchasePlan, amountKey] = scanKey.split(':') as [ReportPurchasePlan, string]
      const plannedAmount = amountKey === 'none' ? null : Number(amountKey)
      const planCodes = Array.from(new Set(planReports.flatMap((report) => report.relatedCodes)))
      if (!planCodes.length) continue
      const payload = await getSalesRuleGapsForCodes(planCodes, planCodes.length, { purchasePlan, plannedAmount })
      gapSource = payload.source
      gapMapsByPlan.set(scanKey, new Map((payload.gaps || []).map((gap) => [gap.windCode.toUpperCase(), gap])))
    }
    return reports.map((report) => {
      const purchasePlan = report.purchasePlan === 'lump_sum' ? 'lump_sum' : 'sip'
      const plannedAmount = report.plannedAmount && Number.isFinite(Number(report.plannedAmount)) && Number(report.plannedAmount) > 0 ? Number(report.plannedAmount) : null
      const scanKey = `${purchasePlan}:${plannedAmount || 'none'}`
      const gapMap = gapMapsByPlan.get(scanKey) || new Map()
      const reviewGate = reviewQueueGateForReport(report, reviewAlertMap, purchasePlan, plannedAmount)
      if (report.targetType === 'comparison' || report.reportType.includes('comparison')) {
        const gaps = report.comparisonCodes
          .map((code) => gapMap.get(code))
          .filter(Boolean)
        const status = gaps.length || reviewGate ? 'blocked' : 'ready'
        const missingItems = Array.from(new Set([
          ...(reviewGate?.missingItems || []),
          ...gaps.flatMap((gap) => gap?.missingItems || []),
        ]))
        return {
          ...report,
          currentSalesRuleGate: {
            status,
            missingCount: gaps.reduce((sum, gap) => sum + (gap?.missingCount || 0), 0) + (reviewGate?.missingCount || 0),
            missingItems,
            actionHref: reviewGate?.actionHref || salesRulesHrefForCodes(report.comparisonCodes, purchasePlan, plannedAmount),
            source: reviewGate ? `${gapSource}+${reviewGate.source}` : gapSource,
            blockedFunds: Math.max(gaps.length, reviewGate?.blockedFunds || 0),
          },
        }
      }
      if (report.targetType === 'fund_pool' || report.reportType === 'fund_pool_shortlist_report' || report.reportType === 'fund_pool_gap_snapshot') {
        const gaps = report.poolCodes
          .map((code) => gapMap.get(code))
          .filter(Boolean)
        const status = gaps.length || reviewGate ? 'blocked' : 'ready'
        const missingItems = Array.from(new Set([
          ...(reviewGate?.missingItems || []),
          ...gaps.flatMap((gap) => gap?.missingItems || []),
        ]))
        return {
          ...report,
          currentSalesRuleGate: {
            status,
            missingCount: gaps.reduce((sum, gap) => sum + (gap?.missingCount || 0), 0) + (reviewGate?.missingCount || 0),
            missingItems,
            actionHref: reviewGate?.actionHref || salesRulesHrefForCodes(report.poolCodes, purchasePlan, plannedAmount),
            source: reviewGate ? `${gapSource}+${reviewGate.source}` : gapSource,
            blockedFunds: Math.max(gaps.length, reviewGate?.blockedFunds || 0),
          },
        }
      }
      if (report.targetType !== 'fund' || report.reportType !== 'fund_pre_purchase_check') return report
      const code = report.targetId.trim().toUpperCase()
      const gap = gapMap.get(code)
      const missingItems = Array.from(new Set([
        ...(reviewGate?.missingItems || []),
        ...(gap?.missingItems || []),
      ]))
      return {
        ...report,
        currentSalesRuleGate: {
          status: gap?.missingCount || reviewGate ? 'blocked' : 'ready',
          missingCount: (gap?.missingCount || 0) + (reviewGate?.missingCount || 0),
          missingItems,
          actionHref: reviewGate?.actionHref || salesRulesHrefForCodes([code], purchasePlan, plannedAmount),
          source: reviewGate ? `${gapSource}+${reviewGate.source}` : gapSource,
          blockedFunds: reviewGate?.blockedFunds || (gap?.missingCount ? 1 : 0),
        },
      }
    })
  } catch (error) {
    console.error('报告列表销售规则门禁读取失败:', error)
    return reports.map((report) => {
      if (report.targetType === 'comparison' || report.reportType.includes('comparison')) {
        return {
          ...report,
          currentSalesRuleGate: {
            status: 'unknown',
            missingCount: null,
            missingItems: [],
            actionHref: salesRulesHrefForCodes(report.comparisonCodes, report.purchasePlan, report.plannedAmount),
            source: 'explicit_codes_plus_local_sales_rules',
          },
        }
      }
      if (report.targetType === 'fund_pool' || report.reportType === 'fund_pool_shortlist_report' || report.reportType === 'fund_pool_gap_snapshot') {
        return {
          ...report,
          currentSalesRuleGate: {
            status: 'unknown',
            missingCount: null,
            missingItems: [],
            actionHref: salesRulesHrefForCodes(report.poolCodes, report.purchasePlan, report.plannedAmount),
            source: 'explicit_codes_plus_local_sales_rules',
          },
        }
      }
      if (report.targetType !== 'fund' || report.reportType !== 'fund_pre_purchase_check') return report
      return {
        ...report,
        currentSalesRuleGate: {
          status: 'unknown',
          missingCount: null,
          missingItems: [],
          actionHref: salesRulesHrefForCodes([report.targetId], report.purchasePlan, report.plannedAmount),
          source: 'explicit_codes_plus_local_sales_rules',
        },
      }
    })
  }
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const page = parseInt(searchParams.get('page') || '1')
  const limit = parseInt(searchParams.get('limit') || '20')
  const search = (searchParams.get('search') || '').trim().toLowerCase()
  const targetType = searchParams.get('targetType') || searchParams.get('target_type')
  const reportType = searchParams.get('reportType') || searchParams.get('report_type')
  const salesGate = searchParams.get('salesGate') || searchParams.get('sales_gate') || 'all'
  const buyBeforeGate = searchParams.get('buyBeforeGate') || searchParams.get('buy_before_gate') || 'all'
  const includeBuyBeforeFacets = ['1', 'true', 'yes'].includes((searchParams.get('includeBuyBeforeFacets') || searchParams.get('include_buy_before_facets') || '').toLowerCase())
  const needsSalesGateFiltering = ['ready', 'blocked', 'unknown'].includes(salesGate)
  const needsBuyBeforeGateFiltering = ['blocked_by_hard_gate', 'verify_first', 'research_ready', 'missing'].includes(buyBeforeGate)
  const needsLocalFiltering = Boolean(search || (reportType && reportType !== 'all') || needsSalesGateFiltering || needsBuyBeforeGateFiltering || includeBuyBeforeFacets)

  try {
    const payload = needsLocalFiltering
      ? null
      : await fetchBackendReports({ page, limit, targetType })

    let reports: MappedReport[] = payload
      ? (payload.reports || []).map(mapReport)
      : await fetchReportsForLocalFiltering(targetType)

    if (reportType && reportType !== 'all') {
      reports = reports.filter((report) =>
        reportType === 'fund_research_report'
          ? isFundResearchReport(report)
          : report.reportType === reportType,
      )
    }
    if (search) {
      reports = reports.filter((report) =>
        [report.title, report.summary, report.content, report.source, report.reportTypeLabel, report.tags.join(' ')]
          .join(' ')
          .toLowerCase()
          .includes(search),
      )
    }
    const reportsForBuyBeforeFacets = includeBuyBeforeFacets
      ? await attachCurrentSalesRuleGate(reports)
      : null
    const facets = includeBuyBeforeFacets
      ? {
          buyBeforeGate: buyBeforeGateFacets(reports),
          buyBeforeEvidenceQueue: buildBuyBeforeEvidenceQueue(reportsForBuyBeforeFacets || reports),
        }
      : null

    if (needsBuyBeforeGateFiltering) {
      reports = reports.filter((report) => {
        const status = report.decisionSummary.buyBeforeGateStatus
        return buyBeforeGate === 'missing' ? !status : status === buyBeforeGate
      })
    }

    let enrichedReports: SalesRuleGateReport[] | null = null
    if (needsSalesGateFiltering) {
      enrichedReports = await attachCurrentSalesRuleGate(reports) as SalesRuleGateReport[]
      reports = enrichedReports.filter((report) => report.currentSalesRuleGate?.status === salesGate)
    }

    const total = needsLocalFiltering ? reports.length : Number(payload?.total || reports.length)
    const pagedReports = needsLocalFiltering
      ? reports.slice((page - 1) * limit, page * limit)
      : reports
    const pagedEnrichedReports = enrichedReports
      ? pagedReports
      : await attachCurrentSalesRuleGate(pagedReports)

    return NextResponse.json({
      data: pagedEnrichedReports,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.max(1, Math.ceil(total / limit)),
      },
      ...(facets ? { facets } : {}),
    })
  } catch (error) {
    console.error('读取本地基金研究报告失败:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '读取本地基金研究报告失败' },
      { status: 500 },
    )
  }
}
