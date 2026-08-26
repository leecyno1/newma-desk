import type { ResearchTool } from '../contracts'
import { benchmarkAttributionTool } from './benchmark-attribution'
import { companyResearchTool } from './company-research'
import { comparisonResearchScoreTool } from './comparison-research-score'
import { comparisonResearchSummaryTool } from './comparison-research-summary'
import { comparisonWinLossAuditTool } from './comparison-win-loss-audit'
import { fundEntityStandardizationTool } from './fund-entity-standardization'
import { holdingDeepResearchTool } from './holding-deep-research'
import { managerResearchLoopTool } from './manager-research-loop'
import { marketCompareBasketEvidenceTool } from './market-compare-basket-evidence'
import { marketCompareBasketWinLossTool } from './market-compare-basket-win-loss'
import { marketCurrentPageShortlistTool } from './market-current-page-shortlist'
import { marketDecisionExplainerTool } from './market-decision-explainer'
import { marketPromotionQueueTool } from './market-promotion-queue'
import { materialEvidenceGateTool } from './material-evidence-gate'
import { methodologyConfigTool } from './methodology-config'
import { peerGroupBenchmarkTool } from './peer-group-benchmark'
import { rankingLeaderQuestionsTool } from './ranking-leader-questions'
import { researchEvidenceTool } from './research-evidence'
import { reportReuseAssessmentTool } from './report-reuse-assessment'
import { screeningConditionHealthTool } from './screening-condition-health'

export const researchTools = [
  benchmarkAttributionTool,
  companyResearchTool,
  comparisonResearchScoreTool,
  comparisonResearchSummaryTool,
  comparisonWinLossAuditTool,
  fundEntityStandardizationTool,
  holdingDeepResearchTool,
  managerResearchLoopTool,
  marketCompareBasketEvidenceTool,
  marketCompareBasketWinLossTool,
  marketCurrentPageShortlistTool,
  marketDecisionExplainerTool,
  marketPromotionQueueTool,
  materialEvidenceGateTool,
  methodologyConfigTool,
  peerGroupBenchmarkTool,
  researchEvidenceTool,
  screeningConditionHealthTool,
  rankingLeaderQuestionsTool,
  reportReuseAssessmentTool,
] as const satisfies readonly ResearchTool<unknown, unknown>[]

export type ResearchToolName = (typeof researchTools)[number]['manifest']['name']

export function listResearchToolManifests() {
  return researchTools.map((tool) => tool.manifest)
}

export function getResearchTool(name: ResearchToolName) {
  const tool = researchTools.find((candidate) => candidate.manifest.name === name)
  if (!tool) throw new Error(`Unknown research tool: ${name}`)
  return tool
}
