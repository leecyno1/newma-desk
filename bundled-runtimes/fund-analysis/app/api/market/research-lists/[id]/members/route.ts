import { NextResponse } from 'next/server'
import { backendApiBaseUrl, toSnakePoolMember } from '@/lib/backend-api'
import { getSalesRuleGapsForCodes } from '@/lib/sales-rule-gaps'
import { fetchActiveSalesRuleEvidenceAlertsForCodes } from '@/lib/sales-rule-review-alerts'
import { materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'

const validWindCodePattern = /^[0-9A-Z]{6,12}\.(OF|SH|SZ|BJ)$/i
const formalPoolStatuses = new Set(['candidate', 'core'])
const purchasePathCreators = new Set([
  'market-browser-ui',
  'investor-selection-ui',
  'fund-detail-ui',
  'comparison-ui',
  'screening-ui',
])
type PurchasePlan = 'lump_sum' | 'sip'

function isFormalPoolStatus(status: string) {
  return formalPoolStatuses.has(status)
}

function isPurchasePathWatch(body: Record<string, unknown>) {
  const status = String(body.status || 'candidate')
  if (status !== 'watch') return false

  const evidence = body.evidence as {
    source?: unknown
    marketBrowser?: unknown
    purchaseGate?: unknown
    riskSuitability?: unknown
    salesRuleGap?: unknown
  } | undefined
  const createdBy = String(body.createdBy || body.created_by || '').trim()
  const evidenceSource = String(evidence?.source || '').trim()

  return (
    purchasePathCreators.has(createdBy) ||
    evidenceSource.startsWith('market-browser') ||
    evidence?.marketBrowser != null ||
    evidence?.purchaseGate != null ||
    evidence?.riskSuitability != null ||
    evidence?.salesRuleGap != null
  )
}

function requiresSalesRuleGate(body: Record<string, unknown>) {
  const status = String(body.status || 'candidate')
  return isFormalPoolStatus(status) || isPurchasePathWatch(body)
}

function extractCandidateWindCode(body: Record<string, unknown>) {
  const evidence = body.evidence as { salesRuleGap?: { checkedCode?: unknown } } | undefined
  const candidates = [
    body.fundWindCode,
    body.fund_wind_code,
    body.fundId,
    body.fund_id,
    evidence?.salesRuleGap?.checkedCode,
  ]

  for (const candidate of candidates) {
    const code = String(candidate || '').trim().toUpperCase()
    if (validWindCodePattern.test(code)) return code
  }
  return ''
}

function extractPurchasePlan(body: Record<string, unknown>): PurchasePlan {
  const evidence = body.evidence as {
    investorContext?: { purchasePlan?: unknown; purchasePlanLabel?: unknown }
    purchaseGate?: { purchasePlan?: unknown }
  } | undefined
  const rawPlan = [
    body.purchasePlan,
    evidence?.investorContext?.purchasePlan,
    evidence?.investorContext?.purchasePlanLabel,
    evidence?.purchaseGate?.purchasePlan,
  ].map((value) => String(value || '').trim()).find(Boolean) || ''
  if (rawPlan === 'lump_sum' || rawPlan.includes('一次性')) return 'lump_sum'
  return 'sip'
}

function defaultPlannedAmountForPlan(purchasePlan: PurchasePlan) {
  return purchasePlan === 'lump_sum' ? 10000 : 1000
}

function extractPlannedAmount(body: Record<string, unknown>, purchasePlan: PurchasePlan) {
  const evidence = body.evidence as {
    investorContext?: { plannedAmount?: unknown }
    purchaseGate?: { plannedAmount?: unknown }
  } | undefined
  const amount = [
    body.plannedAmount,
    body.planned_amount,
    evidence?.investorContext?.plannedAmount,
    evidence?.purchaseGate?.plannedAmount,
  ]
    .map((value) => Number(value))
    .find((value) => Number.isFinite(value) && value > 0)
  return amount || defaultPlannedAmountForPlan(purchasePlan)
}

async function assertSalesRuleGate(body: Record<string, unknown>) {
  const status = String(body.status || 'candidate')
  if (!requiresSalesRuleGate(body)) return null

  const windCode = extractCandidateWindCode(body)
  const purchasePlan = extractPurchasePlan(body)
  const plannedAmount = extractPlannedAmount(body, purchasePlan)
  if (!windCode) return null

  const [gapPayload, activeSalesRuleEvidenceAlertsByCode] = await Promise.all([
    getSalesRuleGapsForCodes([windCode], 1, { purchasePlan, plannedAmount }),
    fetchActiveSalesRuleEvidenceAlertsForCodes([windCode]),
  ])
  const gap = gapPayload.gaps[0]
  const executionAmountGate = gap?.executionAmountGate || gapPayload.rules[0]?.executionAmountGate || null
  const activeSalesRuleEvidenceAlerts = activeSalesRuleEvidenceAlertsByCode.get(windCode.toUpperCase()) || []
  if (!gap && executionAmountGate?.status !== 'blocked' && !activeSalesRuleEvidenceAlerts.length) return null
  const reviewAlertBlocked = activeSalesRuleEvidenceAlerts.length > 0
  return {
    windCode,
    purchasePlan,
    plannedAmount,
    amountGateBlocked: executionAmountGate?.status === 'blocked',
    reviewAlertBlocked,
    gapCount: (gap?.missingCount || 0) + activeSalesRuleEvidenceAlerts.length || 1,
    missingItems: [
      ...(gap?.missingItems || []),
      ...activeSalesRuleEvidenceAlerts.map((alert) => `复查队列未解决：${alert.title}${alert.message ? `（${alert.message}）` : ''}`),
      ...(!gap && executionAmountGate?.status === 'blocked' ? [`计划金额执行门禁：${executionAmountGate.label}`] : []),
    ],
    message: reviewAlertBlocked
      ? `仍有未解决销售规则/R1-R5复查事件，不能加入${status === 'watch' ? '研究观察清单' : status === 'candidate' ? '研究候选清单' : '核心跟踪'}。`
      : executionAmountGate?.status === 'blocked'
      ? `计划金额不可执行：${executionAmountGate.detail}，不能加入${status === 'watch' ? '研究观察清单' : status === 'candidate' ? '研究候选清单' : '核心跟踪'}。`
      : `销售规则仍有 ${gap?.missingCount || 0} 项硬缺口，不能加入${status === 'watch' ? '研究观察清单' : status === 'candidate' ? '研究候选清单' : '核心跟踪'}。`,
  }
}

function assertFormalEvidenceGate(body: Record<string, unknown>) {
  const status = String(body.status || 'candidate')
  if (!isFormalPoolStatus(status)) return null

  const evidence = body.evidence as {
    formalReportGate?: {
      blocked?: unknown
      checkedAt?: unknown
      replay?: {
        months?: unknown
        observations?: unknown
      } | null
    }
    purchaseGate?: {
      level?: unknown
      evidenceGrade?: unknown
      cautionFlags?: unknown
    }
    buyEvidence?: {
      requiredMissingCount?: unknown
    } | null
    shareClassEvidence?: {
      current?: {
        siblingCount?: unknown
      } | null
    } | null
    shareClassDecision?: {
      formalChoiceReady?: unknown
    } | null
  } | undefined

  const formalGate = evidence?.formalReportGate
  const replay = formalGate?.replay || null
  const replayMonths = Number(replay?.months)
  const replayObservations = Number(replay?.observations)
  const evidenceGrade = String(evidence?.purchaseGate?.evidenceGrade || '')
  const purchaseGateLevel = String(evidence?.purchaseGate?.level || '')
  const requiredMissingCount = Number(evidence?.buyEvidence?.requiredMissingCount ?? 0)
  const shareClassSiblingCount = Number(evidence?.shareClassEvidence?.current?.siblingCount ?? 0)
  const shareClassFormalChoiceReady = evidence?.shareClassDecision?.formalChoiceReady === true
  const reasons = [
    !formalGate ? '缺少正式研究复核报告门禁证据' : '',
    formalGate?.blocked === true ? '正式研究复核报告门禁仍处于阻断状态' : '',
    !formalGate?.checkedAt ? '缺少正式研究复核门禁核验时间' : '',
    !replay || !Number.isFinite(replayMonths) || replayMonths <= 0 ? '缺少真实净值回放月份证据' : '',
    !replay || !Number.isFinite(replayObservations) || replayObservations <= 0 ? '缺少真实净值回放观测数' : '',
    evidenceGrade === 'D' ? '证据等级为 D' : '',
    purchaseGateLevel === 'verify_first' || purchaseGateLevel === 'blocked' ? `研究闸门仍为 ${purchaseGateLevel}` : '',
    Number.isFinite(requiredMissingCount) && requiredMissingCount > 0 ? `研究必补证据仍有 ${requiredMissingCount} 项` : '',
    Number.isFinite(shareClassSiblingCount) && shareClassSiblingCount > 0 && !shareClassFormalChoiceReady ? '同基金多份额正式选择未完成，不能把核查顺序当成研究候选' : '',
  ].filter(Boolean)

  if (!reasons.length) return null

  return {
    error: 'PRE_PURCHASE_EVIDENCE_NOT_READY',
    detail: `正式研究复核证据未达标，不能加入${status === 'candidate' ? '研究候选清单' : '核心跟踪'}。`,
    action: '先完成真实净值回放、销售规则核验和研究复核报告门禁，再保存为研究候选。',
    reasons,
  }
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const { searchParams } = new URL(request.url)
    const backendParams = new URLSearchParams()
    const status = searchParams.get('status')
    if (status) backendParams.set('status', status)

    const response = await fetch(
      `${backendApiBaseUrl}/api/fund-pools/${encodeURIComponent(id)}/members?${backendParams.toString()}`,
      { cache: 'no-store' }
    )
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '加载研究清单成员失败' },
        { status: response.status }
      )
    }

    return NextResponse.json({
      ...payload,
      members: (payload.members || []).map(toSnakePoolMember),
    })
  } catch (error) {
    console.error('加载研究清单成员失败:', error)
    return NextResponse.json({ error: '加载研究清单成员失败' }, { status: 500 })
  }
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const body = await request.json()
    const gateBlock = await assertSalesRuleGate(body)
    if (gateBlock) {
      const requestedStatus = String(body.status || 'candidate')
      return NextResponse.json(
        {
          error: gateBlock.reviewAlertBlocked ? 'SALES_RULE_REVIEW_ALERT_BLOCKED' : gateBlock.amountGateBlocked ? 'SALES_RULE_AMOUNT_GATE_BLOCKED' : 'SALES_RULE_GAP_BLOCKED',
          code: gateBlock.reviewAlertBlocked ? 'SALES_RULE_REVIEW_ALERT_BLOCKED' : gateBlock.amountGateBlocked ? 'SALES_RULE_AMOUNT_GATE_BLOCKED' : 'SALES_RULE_GAP_BLOCKED',
          detail: gateBlock.message,
          action: gateBlock.reviewAlertBlocked
            ? '先处理复查队列，再保存为研究观察或研究候选。'
            : requestedStatus === 'watch'
            ? '先补齐销售规则和销售风险等级，再保存为研究观察。'
            : '先补齐销售规则，再保存为研究候选。',
          salesRulesHref: gateBlock.reviewAlertBlocked ? null : materialEvidenceHref({
            codes: gateBlock.windCode || undefined,
            purchasePlan: gateBlock.purchasePlan,
            plannedAmount: gateBlock.plannedAmount,
          }),
          alertsHref: gateBlock.reviewAlertBlocked ? reviewEventsHref() : null,
          missingItems: gateBlock.missingItems,
        },
        { status: 409 },
      )
    }
    const formalGateBlock = assertFormalEvidenceGate(body)
    if (formalGateBlock) {
      return NextResponse.json(formalGateBlock, { status: 409 })
    }
    const response = await fetch(`${backendApiBaseUrl}/api/fund-pools/${encodeURIComponent(id)}/members`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '加入研究清单失败' },
        { status: response.status }
      )
    }

    return NextResponse.json(toSnakePoolMember(payload), { status: 201 })
  } catch (error) {
    console.error('加入研究清单失败:', error)
    return NextResponse.json({ error: '加入研究清单失败' }, { status: 500 })
  }
}
