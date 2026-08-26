import { readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'

const root = process.cwd()

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) throw new Error(`Missing required file: ${relativePath}`)
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) throw new Error(`${label} missing: ${expected}`)
}

function assertNotIncludes(content, unexpected, label) {
  if (content.includes(unexpected)) throw new Error(`${label} should not include: ${unexpected}`)
}

const contracts = [
  'lib/research-platform/contracts/evidence.ts',
  'lib/research-platform/contracts/actions.ts',
  'lib/research-platform/contracts/tool-result.ts',
  'lib/research-platform/contracts/skill-run.ts',
  'lib/research-platform/contracts/guardrails.ts',
  'lib/research-platform/contracts/index.ts',
]
const tools = [
  'lib/research-platform/tools/benchmark-attribution.ts',
  'lib/research-platform/tools/company-research.ts',
  'lib/research-platform/tools/comparison-research-score.ts',
  'lib/research-platform/tools/comparison-research-summary.ts',
  'lib/research-platform/tools/comparison-win-loss-audit.ts',
  'lib/research-platform/tools/fund-entity-standardization.ts',
  'lib/research-platform/tools/holding-deep-research.ts',
  'lib/research-platform/tools/manager-research-loop.ts',
  'lib/research-platform/tools/market-compare-basket-evidence.ts',
  'lib/research-platform/tools/market-compare-basket-win-loss.ts',
  'lib/research-platform/tools/market-current-page-shortlist.ts',
  'lib/research-platform/tools/market-decision-explainer.ts',
  'lib/research-platform/tools/market-promotion-queue.ts',
  'lib/research-platform/tools/screening-condition-health.ts',
  'lib/research-platform/tools/ranking-leader-questions.ts',
  'lib/research-platform/tools/report-reuse-assessment.ts',
  'lib/research-platform/tools/material-evidence-gate.ts',
  'lib/research-platform/tools/methodology-config.ts',
  'lib/research-platform/tools/peer-group-benchmark.ts',
  'lib/research-platform/tools/research-evidence.ts',
  'lib/research-platform/tools/registry.ts',
  'lib/research-platform/tools/index.ts',
]
const skills = [
  'lib/research-platform/skills/registry.ts',
  'lib/research-platform/skills/index.ts',
]

for (const file of [...contracts, ...tools, ...skills]) read(file)

const contractsIndex = read('lib/research-platform/contracts/index.ts')
assertIncludes(contractsIndex, 'EvidenceRef', 'contracts export evidence refs')
assertIncludes(contractsIndex, 'EvidenceGap', 'contracts export evidence gaps')
assertIncludes(contractsIndex, 'ToolResult', 'contracts export tool results')
assertIncludes(contractsIndex, 'ResearchToolManifest', 'contracts export tool manifest')
assertIncludes(contractsIndex, 'SkillRun', 'contracts export skill run')
assertIncludes(contractsIndex, 'ResearchSkillManifest', 'contracts export skill manifest')

const toolRegistry = read('lib/research-platform/tools/registry.ts')
assertIncludes(toolRegistry, 'benchmarkAttributionTool', 'tool registry includes benchmark attribution')
assertIncludes(toolRegistry, 'companyResearchTool', 'tool registry includes company research')
assertIncludes(toolRegistry, 'comparisonResearchScoreTool', 'tool registry includes comparison research score')
assertIncludes(toolRegistry, 'comparisonResearchSummaryTool', 'tool registry includes comparison research summary')
assertIncludes(toolRegistry, 'comparisonWinLossAuditTool', 'tool registry includes comparison win/loss audit')
assertIncludes(toolRegistry, 'fundEntityStandardizationTool', 'tool registry includes fund entity standardization')
assertIncludes(toolRegistry, 'holdingDeepResearchTool', 'tool registry includes holding deep research')
assertIncludes(toolRegistry, 'managerResearchLoopTool', 'tool registry includes manager research loop')
assertIncludes(toolRegistry, 'marketCompareBasketEvidenceTool', 'tool registry includes market compare basket evidence')
assertIncludes(toolRegistry, 'marketCompareBasketWinLossTool', 'tool registry includes market compare basket win/loss')
assertIncludes(toolRegistry, 'marketCurrentPageShortlistTool', 'tool registry includes market current page shortlist')
assertIncludes(toolRegistry, 'marketDecisionExplainerTool', 'tool registry includes market decision explainer')
assertIncludes(toolRegistry, 'marketPromotionQueueTool', 'tool registry includes market promotion queue')
assertIncludes(toolRegistry, 'screeningConditionHealthTool', 'tool registry includes screening condition health')
assertIncludes(toolRegistry, 'rankingLeaderQuestionsTool', 'tool registry includes ranking leader questions')
assertIncludes(toolRegistry, 'reportReuseAssessmentTool', 'tool registry includes report reuse assessment')
assertIncludes(toolRegistry, 'materialEvidenceGateTool', 'tool registry includes material evidence gate')
assertIncludes(toolRegistry, 'methodologyConfigTool', 'tool registry includes methodology config')
assertIncludes(toolRegistry, 'peerGroupBenchmarkTool', 'tool registry includes peer group benchmark')
assertIncludes(toolRegistry, 'researchEvidenceTool', 'tool registry includes research evidence')
assertIncludes(toolRegistry, 'listResearchToolManifests', 'tool registry exposes manifests')
assertIncludes(toolRegistry, 'getResearchTool', 'tool registry exposes lookup')

for (const file of tools.filter((toolPath) => !toolPath.endsWith('/registry.ts') && !toolPath.endsWith('/index.ts'))) {
  const content = read(file)
  assertIncludes(content, 'manifest:', `${file} has manifest`)
  assertIncludes(content, 'guardrails:', `${file} has guardrails`)
  assertIncludes(content, 'createToolResult', `${file} returns audited ToolResult`)
  assertIncludes(content, 'hardBlocks', `${file} emits hard blocks`)
  assertIncludes(content, 'gaps', `${file} emits evidence gaps`)
  assertIncludes(content, 'nextActions', `${file} emits next actions`)
}

const skillRegistry = read('lib/research-platform/skills/registry.ts')
for (const skillName of [
  'full-market-screening',
  'single-fund-research-review',
  'fund-comparison',
  'manager-evaluation',
  'report-reuse',
  'evidence-repair',
]) {
  assertIncludes(skillRegistry, skillName, `skill registry includes ${skillName}`)
}
assertIncludes(skillRegistry, 'allowedSurfaces', 'skills declare allowed surfaces')
assertIncludes(skillRegistry, 'failureMode', 'skills declare failure modes')
assertIncludes(skillRegistry, 'FUND_RESEARCH_GUARDRAILS', 'skills reuse fund research guardrails')

const allPlatformCode = [...contracts, ...tools, ...skills]
  .map((file) => read(file))
  .join('\n')

for (const banned of [
  ['投委', '会'].join(''),
  ['组合', '构建'].join(''),
  ['交易', '执行'].join(''),
  ['investment', '_committee'].join(''),
  ['portfolio', '/optimize'].join(''),
]) {
  assertNotIncludes(allPlatformCode, banned, 'research platform must stay in fund research scope')
}

console.log('OK research platform registry exposes callable tools, skills, contracts, and guardrails')
