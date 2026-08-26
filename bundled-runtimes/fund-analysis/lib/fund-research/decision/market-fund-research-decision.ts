import {
  evaluateResearchReadiness,
  type EvidenceConfidence,
  type FundResearchDecision,
  type PillarAssessment,
  type ResearchGate,
  type ResearchReadiness,
} from '../contracts/research-decision'
import {
  buildMarketResearchChecklist,
  operationStatus,
  type Fund,
  type MarketResearchChecklist,
} from '../market/market-workbench'
import { PROFESSIONAL_METHODOLOGY_VERSION } from '../methodology/professional-methodology'

export type MarketResearchRiskProfile = 'conservative' | 'balanced' | 'aggressive'

export type MarketExecutionAmountGate = {
  status: 'pass' | 'blocked' | 'unknown'
  label: string
  detail: string
}

export type MarketMaterialRuleSnapshot = {
  windCode: string
  riskLevel: string | null
  riskLevelSourceBacked: boolean
  riskLevelEvidenceLabel: string
  missingItems: string[]
  missingCount: number
  executionAmountGate: MarketExecutionAmountGate | null
}

export type MarketMaterialGapSnapshot = {
  windCode: string
  missingItems: string[]
  missingCount: number
  nextAction: string
  executionAmountGate: MarketExecutionAmountGate | null
}

export type MarketReviewEventSnapshot = {
  id?: string
  fund_id?: string | null
  event_type?: string
  status?: string
  title?: string
  message?: string
  details?: unknown
}

export type MarketMaterialEvidence = {
  status: 'complete' | 'gap' | 'unknown'
  label: string
  missingItems: string[]
  missingCount: number
  executionAmountGate: MarketExecutionAmountGate | null
  riskLevel: string | null
  riskLevelSourceBacked: boolean
  riskLevelEvidenceLabel: string
  reviewEventCount: number
  nextAction: string | null
  actionKind: 'review-events' | 'material-evidence' | null
  gateSource: 'local.alert_events.sales_rule_evidence' | 'local.sales_rules'
}

export type MarketSuitabilityAssessment = {
  status: 'matched' | 'mismatch' | 'missing'
  label: string
  detail: string
}

export type MarketFormalResearchGate = {
  passed: boolean
  label: string
  reportLabel: string
  reason: string
  actionLabel: string
}

export type MarketResearchReadiness = {
  level: 'ready' | 'verify' | 'blocked'
  label: string
  gaps: string[]
}

export type MarketFundResearchDecision = {
  decision: FundResearchDecision
  readiness: MarketResearchReadiness
  canonicalReadiness: ResearchReadiness
  material: MarketMaterialEvidence
  suitability: MarketSuitabilityAssessment
  formalGate: MarketFormalResearchGate
  checklist: MarketResearchChecklist
  operation: ReturnType<typeof operationStatus>
}

const profileMaxSalesRiskLevel: Record<MarketResearchRiskProfile, number> = {
  conservative: 2,
  balanced: 3,
  aggressive: 5,
}

const profileLabel: Record<MarketResearchRiskProfile, string> = {
  conservative: '稳健画像',
  balanced: '平衡画像',
  aggressive: '进取画像',
}

export function marketSalesRiskLevelCeiling(riskProfile: MarketResearchRiskProfile) {
  return profileMaxSalesRiskLevel[riskProfile]
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function normalizeCode(value: unknown) {
  return String(value ?? '').trim().toUpperCase()
}

function uniqueText(items: string[]) {
  return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)))
}

function riskLevelNumber(value: string | null) {
  const match = String(value || '').match(/[1-5]/)
  return match ? Number(match[0]) : null
}

function checklistItem(checklist: MarketResearchChecklist, key: MarketResearchChecklist['items'][number]['key']) {
  return checklist.items.find((item) => item.key === key)
}

export function marketReviewEventCode(event: MarketReviewEventSnapshot) {
  const details = asRecord(event.details)
  return normalizeCode(details.wind_code || details.fund_code || event.fund_id)
}

export function buildMarketMaterialEvidence(input: {
  windCode: string
  materialRule?: MarketMaterialRuleSnapshot | null
  materialGap?: MarketMaterialGapSnapshot | null
  reviewEvents?: MarketReviewEventSnapshot[]
}): MarketMaterialEvidence {
  const windCode = normalizeCode(input.windCode)
  const reviewEvents = (input.reviewEvents || []).filter((event) => {
    const eventCode = marketReviewEventCode(event)
    return !eventCode || eventCode === windCode
  })
  const alertMissingItems = reviewEvents.map((event) => (
    `复查队列未解决：${event.title || '销售规则/R1-R5事件'}${event.message ? `（${event.message}）` : ''}`
  ))
  const missingItems = uniqueText([
    ...(input.materialGap?.missingItems || input.materialRule?.missingItems || []),
    ...alertMissingItems,
  ])
  const status: MarketMaterialEvidence['status'] = reviewEvents.length || missingItems.length
    ? 'gap'
    : input.materialRule
      ? 'complete'
      : 'unknown'
  const actionKind = reviewEvents.length
    ? 'review-events' as const
    : input.materialGap
      ? 'material-evidence' as const
      : null

  return {
    status,
    label: status === 'complete'
      ? '材料核验相对完整'
      : status === 'gap'
        ? `材料待补 ${missingItems.length} 项`
        : '材料尚未扫描',
    missingItems,
    missingCount: missingItems.length,
    executionAmountGate: input.materialGap?.executionAmountGate || input.materialRule?.executionAmountGate || null,
    riskLevel: input.materialRule?.riskLevel || null,
    riskLevelSourceBacked: input.materialRule?.riskLevelSourceBacked === true,
    riskLevelEvidenceLabel: input.materialRule?.riskLevelEvidenceLabel || 'R1-R5 来源待补',
    reviewEventCount: reviewEvents.length,
    nextAction: reviewEvents.length
      ? '先处理复查队列，再回到全市场严格重评'
      : input.materialGap?.nextAction || (status === 'gap' ? '补齐材料核验后重评' : null),
    actionKind,
    gateSource: reviewEvents.length ? 'local.alert_events.sales_rule_evidence' : 'local.sales_rules',
  }
}

export function assessMarketSuitability(
  material: MarketMaterialEvidence,
  riskProfile: MarketResearchRiskProfile,
): MarketSuitabilityAssessment {
  const riskLevel = riskLevelNumber(material.riskLevel)
  if (riskLevel === null || !material.riskLevelSourceBacked) {
    return {
      status: 'missing',
      label: '风险等级缺失',
      detail: 'R1-R5 来源未完成可信度闸门，不能推断适当性通过。',
    }
  }
  if (riskLevel > profileMaxSalesRiskLevel[riskProfile]) {
    return {
      status: 'mismatch',
      label: '适当性不匹配',
      detail: `风险等级超过当前${profileLabel[riskProfile]}上限。`,
    }
  }
  return {
    status: 'matched',
    label: '适当性匹配',
    detail: `${material.riskLevel} 与当前${profileLabel[riskProfile]}匹配。`,
  }
}

function buildFormalResearchGate(input: {
  operation: ReturnType<typeof operationStatus>
  material: MarketMaterialEvidence
  suitability: MarketSuitabilityAssessment
}): MarketFormalResearchGate {
  if (input.operation.status === 'blocked') {
    return {
      passed: false,
      label: '产品状态阻断',
      reportLabel: '产品状态阻断',
      reason: input.operation.reason,
      actionLabel: '看排除原因',
    }
  }
  if (input.material.status !== 'complete') {
    return {
      passed: false,
      label: '材料核验阻断',
      reportLabel: '材料核验/R1-R5 未清零',
      reason: input.material.missingItems.join('、') || '材料核验尚未完成',
      actionLabel: input.material.actionKind === 'review-events' ? '开复查队列' : '补材料核验',
    }
  }
  if (input.material.executionAmountGate?.status === 'blocked') {
    return {
      passed: false,
      label: '金额不匹配',
      reportLabel: '计划金额门禁阻断',
      reason: input.material.executionAmountGate.detail,
      actionLabel: '补金额门槛',
    }
  }
  if (input.suitability.status !== 'matched') {
    return {
      passed: false,
      label: input.suitability.label,
      reportLabel: input.suitability.label,
      reason: input.suitability.detail,
      actionLabel: '补风险等级',
    }
  }
  return {
    passed: true,
    label: '正式门禁通过',
    reportLabel: '可进入研究复核',
    reason: '材料核验、金额门禁与适当性均未触发结构化阻断。',
    actionLabel: '看详情',
  }
}

function buildResearchGates(input: {
  windCode: string
  checklist: MarketResearchChecklist
  operation: ReturnType<typeof operationStatus>
  material: MarketMaterialEvidence
  suitability: MarketSuitabilityAssessment
}): ResearchGate[] {
  const foundation = checklistItem(input.checklist, 'foundation')
  const amountGate = input.material.executionAmountGate
  return [
    {
      id: 'universe-operation-status',
      stage: 'universe-identity',
      label: '产品生命周期与运行状态',
      status: input.operation.status === 'blocked' ? 'block' : input.operation.status === 'watch' ? 'review' : 'pass',
      reason: input.operation.reason,
      evidenceIds: [`fund:${input.windCode}:operation-status`],
      resolution: input.operation.status === 'blocked' ? '核验终止、清算、暂停或限制状态后重新建立研究范围。' : undefined,
    },
    {
      id: 'universe-identity-completeness',
      stage: 'universe-identity',
      label: '基金身份与基础事实',
      status: foundation?.status === 'blocked' ? 'block' : foundation?.status === 'ready' ? 'pass' : 'review',
      reason: foundation?.detail || '基金身份与基础事实待核。',
      evidenceIds: [`fund:${input.windCode}:identity`],
      resolution: foundation?.status === 'ready' ? undefined : '补齐基金身份、规模、成立日期和生命周期证据。',
    },
    {
      id: 'evidence-material-completeness',
      stage: 'evidence-quality',
      label: '材料核验与 R1-R5 来源',
      status: input.material.status === 'complete' ? 'pass' : 'block',
      reason: input.material.status === 'complete'
        ? input.material.riskLevelEvidenceLabel
        : input.material.missingItems.join('、') || '材料核验尚未扫描。',
      evidenceIds: input.material.missingItems.map((_, index) => `fund:${input.windCode}:material-gap:${index + 1}`),
      resolution: input.material.status === 'complete' ? undefined : input.material.nextAction || '补齐材料核验与来源日期。',
    },
    {
      id: 'evidence-amount-execution',
      stage: 'evidence-quality',
      label: '计划金额执行门槛',
      status: amountGate?.status === 'blocked' ? 'block' : amountGate?.status === 'unknown' || !amountGate ? 'review' : 'pass',
      reason: amountGate?.detail || amountGate?.label || '金额门槛待扫描。',
      evidenceIds: [`fund:${input.windCode}:amount-gate`],
      resolution: amountGate?.status === 'pass' ? undefined : '补齐起点、限额与份额规则，或调整计划金额后重新评估。',
    },
    {
      id: 'evidence-risk-suitability',
      stage: 'evidence-quality',
      label: '风险等级来源与当前画像适当性',
      status: input.suitability.status === 'matched' ? 'pass' : 'block',
      reason: input.suitability.detail,
      evidenceIds: [`fund:${input.windCode}:risk-level`],
      resolution: input.suitability.status === 'matched' ? undefined : '补齐来源背书的 R1-R5，或使用匹配的研究画像重新评估。',
    },
  ]
}

function pillarFromChecklist(input: {
  checklist: MarketResearchChecklist
  stage: PillarAssessment['stage']
  keys: MarketResearchChecklist['items'][number]['key'][]
  finding: string
}): PillarAssessment {
  const items = input.keys
    .map((key) => checklistItem(input.checklist, key))
    .filter((item): item is NonNullable<typeof item> => Boolean(item))
  const readyItems = items.filter((item) => item.status === 'ready')
  const gapItems = items.filter((item) => item.status !== 'ready')
  return {
    stage: input.stage,
    status: gapItems.length ? 'insufficient' : 'supportive',
    confidence: gapItems.length ? (readyItems.length ? 'medium' : 'low') : 'medium',
    finding: gapItems.length ? gapItems.map((item) => item.detail).join('；') : input.finding,
    supportingEvidence: readyItems.map((item) => item.detail),
    counterEvidence: gapItems.map((item) => item.detail),
  }
}

function buildResearchPillars(checklist: MarketResearchChecklist): PillarAssessment[] {
  return [
    pillarFromChecklist({
      checklist,
      stage: 'quantitative-evaluation',
      keys: ['performance', 'risk'],
      finding: '绩效与风险轨迹具备当前页基础研究证据。',
    }),
    pillarFromChecklist({
      checklist,
      stage: 'holdings-style',
      keys: ['holdings'],
      finding: '持仓暴露达到当前页基础研究要求。',
    }),
    pillarFromChecklist({
      checklist,
      stage: 'qualitative-due-diligence',
      keys: ['manager'],
      finding: '经理任职证据达到当前页基础研究要求。',
    }),
  ]
}

function confidenceForDecision(input: {
  material: MarketMaterialEvidence
  canonicalReadiness: ResearchReadiness
}): EvidenceConfidence {
  if (input.material.status === 'unknown') return 'unknown'
  if (input.canonicalReadiness.blockingGates.length) return 'low'
  if (input.canonicalReadiness.reviewGates.length || input.canonicalReadiness.insufficientPillars.length) return 'medium'
  return 'high'
}

function projectMarketReadiness(
  checklist: MarketResearchChecklist,
  canonicalReadiness: ResearchReadiness,
): MarketResearchReadiness {
  const gaps = uniqueText([
    ...canonicalReadiness.blockingGates.map((gate) => gate.reason),
    ...canonicalReadiness.reviewGates.map((gate) => gate.reason),
    ...checklist.items.filter((item) => item.status !== 'ready').map((item) => item.detail),
    ...canonicalReadiness.insufficientPillars.flatMap((pillar) => pillar.counterEvidence),
  ])
  if (canonicalReadiness.blockingGates.length) {
    return { level: 'blocked', label: '研究路径阻断', gaps }
  }
  if (gaps.length) return { level: 'verify', label: '证据待补', gaps }
  return { level: 'ready', label: '可进入研究复核', gaps: [] }
}

export function buildMarketFundResearchDecision(input: {
  fund: Fund
  riskProfile: MarketResearchRiskProfile
  materialRule?: MarketMaterialRuleSnapshot | null
  materialGap?: MarketMaterialGapSnapshot | null
  reviewEvents?: MarketReviewEventSnapshot[]
  asOf?: string
}): MarketFundResearchDecision {
  const material = buildMarketMaterialEvidence({
    windCode: input.fund.windCode,
    materialRule: input.materialRule,
    materialGap: input.materialGap,
    reviewEvents: input.reviewEvents,
  })
  const suitability = assessMarketSuitability(material, input.riskProfile)
  const operation = operationStatus(input.fund)
  const checklist = buildMarketResearchChecklist(input.fund, material.status === 'complete')
  const formalGate = buildFormalResearchGate({ operation, material, suitability })
  const gates = buildResearchGates({
    windCode: input.fund.windCode,
    checklist,
    operation,
    material,
    suitability,
  })
  const pillars = buildResearchPillars(checklist)
  const canonicalReadiness = evaluateResearchReadiness(gates, pillars)
  const readiness = projectMarketReadiness(checklist, canonicalReadiness)
  const confidence = confidenceForDecision({ material, canonicalReadiness })
  const counterThesis = uniqueText([
    ...canonicalReadiness.blockingGates.map((gate) => gate.reason),
    ...canonicalReadiness.reviewGates.map((gate) => gate.reason),
    ...canonicalReadiness.insufficientPillars.map((pillar) => pillar.finding),
  ])
  const decision: FundResearchDecision = {
    subjectId: input.fund.windCode,
    asOf: input.asOf || new Date().toISOString(),
    methodologyVersion: PROFESSIONAL_METHODOLOGY_VERSION,
    disposition: canonicalReadiness.disposition,
    thesis: canonicalReadiness.disposition === 'due-diligence-ready'
      ? `${input.fund.name} 的当前证据达到尽调起点，下一步进入同类、基准和定性复核。`
      : `${input.fund.name} 当前处于“${canonicalReadiness.reason}”对应的研究处置。`,
    counterThesis,
    confidence,
    gates,
    pillars,
    reversalConditions: [
      '经理、团队、策略或产品生命周期发生重大变化。',
      '材料来源超过研究复核窗口，或 R1-R5、费用、限额与计划金额事实变化。',
      '同类组、基准、持仓风格或风险轨迹出现足以改变当前判断的新证据。',
    ],
  }

  return {
    decision,
    readiness,
    canonicalReadiness,
    material,
    suitability,
    formalGate,
    checklist,
    operation,
  }
}
