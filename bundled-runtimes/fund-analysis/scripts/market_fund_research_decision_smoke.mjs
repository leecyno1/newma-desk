import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) throw new Error(`Missing required file: ${relativePath}`)
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) throw new Error(`${label} missing text: ${expected}`)
}

function assertNotIncludes(content, unexpected, label) {
  if (content.includes(unexpected)) throw new Error(`${label} should not include stale text: ${unexpected}`)
}

const marketClient = read('app/(dashboard)/market/MarketBrowserClient.tsx')
const researchDecision = read('lib/fund-research/decision/market-fund-research-decision.ts')
const researchDecisionIndex = read('lib/fund-research/decision/index.ts')
const fundResearchIndex = read('lib/fund-research/index.ts')
const marketWorkbench = read('lib/fund-research/market/market-workbench.ts')

assertIncludes(researchDecision, 'evaluateResearchReadiness', 'research decision delegates canonical readiness evaluation')
assertIncludes(researchDecision, 'FundResearchDecision', 'research decision emits the canonical contract')
assertIncludes(researchDecision, 'buildResearchGates', 'research decision owns research gates')
assertIncludes(researchDecision, 'buildResearchPillars', 'research decision owns research pillars')
assertIncludes(researchDecision, 'buildFormalResearchGate', 'research decision owns the formal research gate')
assertIncludes(researchDecision, 'buildMarketMaterialEvidence', 'research decision owns material evidence normalization')
assertIncludes(researchDecision, 'assessMarketSuitability', 'research decision owns suitability assessment')
assertIncludes(researchDecision, 'canonicalReadiness', 'research decision exposes canonical readiness')
assertIncludes(researchDecision, 'methodologyVersion: PROFESSIONAL_METHODOLOGY_VERSION', 'research decision is methodology-versioned')
assertIncludes(researchDecisionIndex, "export * from './market-fund-research-decision'", 'decision module exports its interface')
assertIncludes(fundResearchIndex, "export * from './decision'", 'fund research exports the decision module')

assertIncludes(marketClient, 'buildMarketFundResearchDecision', 'market browser consumes the research decision module')
assertIncludes(marketClient, 'const researchDecisionByCode = useMemo', 'market browser creates one decision map per page state')
assertIncludes(marketClient, 'researchDecisionFor(fund)', 'market browser projects decision results')
assertIncludes(marketClient, 'researchDecision.formalGate.passed', 'single pool save uses the canonical formal gate')
assertIncludes(marketClient, '.filter((fund) => researchDecisionFor(fund).formalGate.passed)', 'batch pool save uses the canonical formal gate')
assertIncludes(marketClient, 'fundResearchDecision: researchDecision.decision', 'pool evidence preserves the canonical research decision')
assertIncludes(marketClient, 'materialActionHrefForDecision', 'market browser keeps route projection outside the decision module')

for (const staleLocalRule of [
  'getSalesRuleGapStatus',
  'riskSuitabilityStatus',
  'formalPurchaseGate',
  'suitabilityGateAllowsResearch',
  'executionAmountGateAllowsResearch',
  'function reviewEventCode',
  'function toRiskLevel',
]) {
  assertNotIncludes(marketClient, staleLocalRule, `market browser must not own ${staleLocalRule}`)
}

assertNotIncludes(marketWorkbench, 'export function buyReadiness', 'market workbench no longer owns a competing readiness rule')
assertNotIncludes(marketWorkbench, 'export type MarketReadiness', 'market workbench no longer exposes competing readiness state')

console.log('OK market fund research decision kernel smoke passed')
