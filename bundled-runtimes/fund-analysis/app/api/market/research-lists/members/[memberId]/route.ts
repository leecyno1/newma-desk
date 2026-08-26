import { NextResponse } from 'next/server'
import postgres from 'postgres'
import { backendApiBaseUrl, toSnakePoolMember } from '@/lib/backend-api'
import { getSalesRuleGapsForCodes } from '@/lib/sales-rule-gaps'
import { fetchActiveSalesRuleEvidenceAlertsForCodes } from '@/lib/sales-rule-review-alerts'
import { materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'

const sql = postgres(process.env.DATABASE_URL || '', { max: 1 })
const validWindCodePattern = /^[0-9A-Z]{6,12}\.(OF|SH|SZ|BJ)$/i
const salesRuleGateStatuses = new Set(['candidate', 'core'])
type PurchasePlan = 'lump_sum' | 'sip'

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

async function lookupMemberWindCode(memberId: string) {
  const rows = await sql<Array<{
    fund_id: string | null
    fund_wind_code: string | null
    fund_name: string | null
  }>>`
    SELECT
      pool_members.fund_id,
      funds.wind_code AS fund_wind_code,
      funds.name AS fund_name
    FROM pool_members
    LEFT JOIN funds
      ON pool_members.fund_id = funds.id::text
      OR pool_members.fund_id = funds.wind_code
    WHERE pool_members.id = CAST(${memberId} AS UUID)
    LIMIT 1
  `
  const member = rows[0]
  if (!member) return null
  const code = String(member.fund_wind_code || member.fund_id || '').trim().toUpperCase()
  return {
    code: validWindCodePattern.test(code) ? code : '',
    name: member.fund_name || code,
  }
}

async function assertSalesRuleGate(memberId: string, body: Record<string, unknown>) {
  const status = String(body.status || '')
  if (!salesRuleGateStatuses.has(status)) return null

  const purchasePlan = extractPurchasePlan(body)
  const plannedAmount = extractPlannedAmount(body, purchasePlan)
  const bodyWindCode = extractCandidateWindCode(body)
  const member = bodyWindCode ? null : await lookupMemberWindCode(memberId)
  const windCode = bodyWindCode || member?.code || ''
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
      ? `${member?.name || windCode} 仍有未解决销售规则/R1-R5复查事件，不能转为${status === 'candidate' ? '研究候选' : '核心跟踪'}。`
      : executionAmountGate?.status === 'blocked'
      ? `${member?.name || windCode} 计划金额不可执行：${executionAmountGate.detail}，不能转为${status === 'candidate' ? '研究候选' : '核心跟踪'}。`
      : `${member?.name || windCode} 销售规则仍有 ${gap?.missingCount || 0} 项硬缺口，不能转为${status === 'candidate' ? '研究候选' : '核心跟踪'}。`,
  }
}

function assertFormalEvidenceGate(body: Record<string, unknown>) {
  const status = String(body.status || '')
  if (!salesRuleGateStatuses.has(status)) return null

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

  if (!evidence) {
    return {
      error: 'PRE_PURCHASE_EVIDENCE_NOT_READY',
      detail: `缺少结构化研究证据，不能转为${status === 'candidate' ? '研究候选' : '核心跟踪'}。`,
      action: '先从基金详情页完成研究复核并写入正式门禁证据。',
      reasons: ['缺少成员 evidence 载荷'],
    }
  }

  const formalGate = evidence.formalReportGate
  const replay = formalGate?.replay || null
  const replayMonths = Number(replay?.months)
  const replayObservations = Number(replay?.observations)
  const evidenceGrade = String(evidence.purchaseGate?.evidenceGrade || '')
  const purchaseGateLevel = String(evidence.purchaseGate?.level || '')
  const requiredMissingCount = Number(evidence.buyEvidence?.requiredMissingCount ?? 0)
  const shareClassSiblingCount = Number(evidence.shareClassEvidence?.current?.siblingCount ?? 0)
  const shareClassFormalChoiceReady = evidence.shareClassDecision?.formalChoiceReady === true
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
    detail: `正式研究复核证据未达标，不能转为${status === 'candidate' ? '研究候选' : '核心跟踪'}。`,
    action: '先完成真实净值回放、销售规则核验和研究复核报告门禁，再转入研究候选或核心跟踪。',
    reasons,
  }
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ memberId: string }> }
) {
  try {
    const { memberId } = await params
    const body = await request.json()
    const gateBlock = await assertSalesRuleGate(memberId, body)
    if (gateBlock) {
      return NextResponse.json(
        {
          error: gateBlock.reviewAlertBlocked ? 'SALES_RULE_REVIEW_ALERT_BLOCKED' : gateBlock.amountGateBlocked ? 'SALES_RULE_AMOUNT_GATE_BLOCKED' : 'SALES_RULE_GAP_BLOCKED',
          code: gateBlock.reviewAlertBlocked ? 'SALES_RULE_REVIEW_ALERT_BLOCKED' : gateBlock.amountGateBlocked ? 'SALES_RULE_AMOUNT_GATE_BLOCKED' : 'SALES_RULE_GAP_BLOCKED',
          detail: gateBlock.message,
          action: gateBlock.reviewAlertBlocked ? '先处理复查队列，再转入研究候选或核心跟踪。' : '先补齐销售规则，再转入研究候选或核心跟踪。',
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
    const response = await fetch(`${backendApiBaseUrl}/api/fund-pools/members/${encodeURIComponent(memberId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '更新研究清单成员失败' },
        { status: response.status }
      )
    }

    return NextResponse.json(toSnakePoolMember(payload))
  } catch (error) {
    console.error('更新研究清单成员失败:', error)
    return NextResponse.json({ error: '更新研究清单成员失败' }, { status: 500 })
  }
}
