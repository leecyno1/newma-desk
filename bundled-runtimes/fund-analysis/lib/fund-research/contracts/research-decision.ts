export const RESEARCH_STAGE_IDS = [
  'universe-identity',
  'evidence-quality',
  'peer-benchmark',
  'quantitative-evaluation',
  'holdings-style',
  'qualitative-due-diligence',
  'decision-governance',
  'monitoring',
  'methodology-audit',
] as const

export type ResearchStageId = (typeof RESEARCH_STAGE_IDS)[number]

export type ResearchGateStatus = 'pass' | 'review' | 'block' | 'not-applicable'
export type PillarAssessmentStatus = 'supportive' | 'mixed' | 'concern' | 'insufficient'
export type EvidenceConfidence = 'high' | 'medium' | 'low' | 'unknown'

export type ResearchGate = {
  id: string
  stage: ResearchStageId
  label: string
  status: ResearchGateStatus
  reason: string
  evidenceIds: string[]
  resolution?: string
}

export type PillarAssessment = {
  stage: ResearchStageId
  status: PillarAssessmentStatus
  confidence: EvidenceConfidence
  finding: string
  supportingEvidence: string[]
  counterEvidence: string[]
}

export type ResearchDisposition =
  | 'blocked'
  | 'evidence-repair'
  | 'watchlist'
  | 'due-diligence-ready'
  | 'monitoring-required'

export type FundResearchDecision = {
  subjectId: string
  asOf: string
  methodologyVersion: string
  disposition: ResearchDisposition
  thesis: string
  counterThesis: string[]
  confidence: EvidenceConfidence
  gates: ResearchGate[]
  pillars: PillarAssessment[]
  reversalConditions: string[]
  reviewer?: string
}

export type ResearchReadiness = {
  disposition: ResearchDisposition
  blockingGates: ResearchGate[]
  reviewGates: ResearchGate[]
  insufficientPillars: PillarAssessment[]
  reason: string
}

/**
 * Professional fund selection is a staged decision, not a weighted sum.
 * Hard evidence failures stop the workflow; weak coverage routes the case to
 * evidence repair; only then can qualitative and quantitative pillars be
 * reviewed together.
 */
export function evaluateResearchReadiness(
  gates: ResearchGate[],
  pillars: PillarAssessment[],
): ResearchReadiness {
  const blockingGates = gates.filter((gate) => gate.status === 'block')
  const reviewGates = gates.filter((gate) => gate.status === 'review')
  const insufficientPillars = pillars.filter((pillar) => pillar.status === 'insufficient')

  if (blockingGates.length > 0) {
    return {
      disposition: 'blocked',
      blockingGates,
      reviewGates,
      insufficientPillars,
      reason: `存在 ${blockingGates.length} 项硬门槛未通过，不能进入正式尽调结论。`,
    }
  }

  if (insufficientPillars.length > 0) {
    return {
      disposition: 'evidence-repair',
      blockingGates,
      reviewGates,
      insufficientPillars,
      reason: `存在 ${insufficientPillars.length} 个证据不足的研究柱，先补证再判断。`,
    }
  }

  if (reviewGates.length > 0 || pillars.some((pillar) => pillar.status === 'concern')) {
    return {
      disposition: 'watchlist',
      blockingGates,
      reviewGates,
      insufficientPillars,
      reason: '没有硬阻断，但仍有待复核门槛或重要反证，只进入观察清单。',
    }
  }

  return {
    disposition: 'due-diligence-ready',
    blockingGates,
    reviewGates,
    insufficientPillars,
    reason: '准入门槛与证据覆盖达到尽调起点；这不是购买建议，也不替代后续定性与运营尽调。',
  }
}
