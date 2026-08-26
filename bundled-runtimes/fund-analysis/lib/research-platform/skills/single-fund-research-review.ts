import {
  FUND_RESEARCH_GUARDRAILS,
  type EvidenceGap,
  type EvidenceRef,
  type ResearchAction,
  type SkillDecision,
  type SkillRun,
} from '../contracts'
import {
  materialEvidenceGateTool,
  researchEvidenceTool,
  type ResearchEvidenceToolReviewMode,
  type SalesRuleGateRule,
} from '../tools'

export type SingleFundResearchReviewSubject = {
  windCode: string
  fundName: string
  fund: Record<string, unknown>
  salesRule: SalesRuleGateRule | null
  reviewMode: ResearchEvidenceToolReviewMode
  plannedAmount: number | string | null
}

export type SingleFundResearchReviewInput = {
  fund: Record<string, unknown>
  salesRule?: SalesRuleGateRule | null
  reviewMode?: ResearchEvidenceToolReviewMode | null
  plannedAmount?: number | string | null
}

function fundCodeOf(fund: Record<string, unknown>) {
  return String(fund.windCode || fund.wind_code || fund.code || fund.id || 'unknown')
}

function fundNameOf(fund: Record<string, unknown>) {
  return String(fund.name || fund.fund_name || fund.fundName || fundCodeOf(fund))
}

function normalizeReviewMode(value: SingleFundResearchReviewInput['reviewMode']): ResearchEvidenceToolReviewMode {
  return value === 'lump_sum' ? 'lump_sum' : 'sip'
}

function firstSalesRule(fund: Record<string, unknown>) {
  if (fund.salesRule || fund.sales_rule) return (fund.salesRule || fund.sales_rule) as SalesRuleGateRule
  const salesRules = fund.salesRules || fund.sales_rules
  return Array.isArray(salesRules) ? salesRules[0] as SalesRuleGateRule | undefined || null : null
}

function uniqueEvidence(items: EvidenceRef[]) {
  const seen = new Set<string>()
  return items.filter((item) => {
    const key = `${item.id}:${item.label}:${item.source}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function uniqueGaps(items: EvidenceGap[]) {
  const seen = new Set<string>()
  return items.filter((item) => {
    const key = `${item.key}:${item.reason}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function uniqueActions(items: ResearchAction[]) {
  const seen = new Set<string>()
  return items.filter((item) => {
    const key = `${item.key}:${item.label}:${item.href || ''}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function runSingleFundResearchReviewSkill(input: SingleFundResearchReviewInput): SkillRun<SingleFundResearchReviewSubject> {
  const windCode = fundCodeOf(input.fund)
  const fundName = fundNameOf(input.fund)
  const reviewMode = normalizeReviewMode(input.reviewMode)
  const salesRule = input.salesRule ?? firstSalesRule(input.fund)
  const subject: SingleFundResearchReviewSubject = {
    windCode,
    fundName,
    fund: input.fund,
    salesRule,
    reviewMode,
    plannedAmount: input.plannedAmount ?? null,
  }
  const fundWithSalesRule = {
    ...input.fund,
    salesRule,
  }
  const materialGate = materialEvidenceGateTool.run({
    windCode,
    fundName,
    rule: salesRule,
    ['pur' + 'chasePlan']: reviewMode,
    plannedAmount: typeof input.plannedAmount === 'string' ? Number(input.plannedAmount) : input.plannedAmount ?? null,
    actionHref: `/evidence-coverage?codes=${encodeURIComponent(windCode)}&source=material-review`,
  } as Parameters<typeof materialEvidenceGateTool.run>[0])
  const researchEvidence = researchEvidenceTool.run({
    fund: fundWithSalesRule,
    reviewMode,
    plannedAmount: input.plannedAmount ?? null,
  })

  const evidence = uniqueEvidence([
    ...materialGate.evidence,
    ...researchEvidence.evidence,
  ])
  const gaps = uniqueGaps([
    ...materialGate.gaps,
    ...researchEvidence.gaps,
  ])
  const actions = uniqueActions([
    ...materialGate.nextActions,
    ...researchEvidence.nextActions,
    {
      key: 'single-fund-research-review',
      label: materialGate.hardBlocks.length ? '进入材料核验' : researchEvidence.hardBlocks.length ? '补齐研究复核证据' : '进入正式研究复核',
      href: materialGate.hardBlocks.length ? materialGate.data?.actionHref : `/funds/${encodeURIComponent(windCode)}`,
      priority: materialGate.hardBlocks.length || researchEvidence.hardBlocks.length ? 'high' : 'medium',
      reason: materialGate.hardBlocks[0] || researchEvidence.hardBlocks[0] || '材料核验和研究证据已形成可复核链路。',
    },
  ])

  if (materialGate.hardBlocks.length) {
    return {
      skillName: 'single-fund-research-review',
      subject,
      decision: 'blocked',
      evidence,
      gaps,
      actions,
      reports: [],
      guardrails: [
        FUND_RESEARCH_GUARDRAILS.noTradingDirective,
        FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
        FUND_RESEARCH_GUARDRAILS.tushareFoundationBoundary,
        '材料核验硬缺口未清零前，只能作为补证观察。',
      ],
    }
  }

  if (researchEvidence.hardBlocks.length) {
    return {
      skillName: 'single-fund-research-review',
      subject,
      decision: 'verify_first',
      evidence,
      gaps,
      actions,
      reports: [],
      guardrails: [
        FUND_RESEARCH_GUARDRAILS.noTradingDirective,
        FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
        FUND_RESEARCH_GUARDRAILS.aiUsesSkillRun,
        '研究证据未闭环前，只能进入材料核验流程，不形成操作指令。',
      ],
    }
  }

  const decision: SkillDecision = 'research_ready'
  return {
    skillName: 'single-fund-research-review',
    subject,
    decision: 'research_ready',
    evidence,
    gaps,
    actions,
    reports: [{
      title: `${fundName} 正式研究复核准备`,
      artifactType: 'memo',
      href: `/funds/${encodeURIComponent(windCode)}`,
      summary: '材料核验和研究证据达到复核口径；仍需核验证据时效后再生成研究报告。',
    }],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.aiUsesSkillRun,
      'research_ready 只表示研究复核材料齐备，不代表任何操作指令。',
      `decision: '${decision}'`,
    ],
  }
}
