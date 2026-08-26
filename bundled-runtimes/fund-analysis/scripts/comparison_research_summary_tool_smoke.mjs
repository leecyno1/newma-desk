import { existsSync, readFileSync } from 'node:fs'
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

function assertNotIncludes(content, forbidden, label) {
  if (content.includes(forbidden)) throw new Error(`${label} should not include: ${forbidden}`)
}

const tool = read('lib/research-platform/tools/comparison-research-summary.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')
const comparisonReport = read('lib/fund-comparison-report.ts')

assertIncludes(tool, "const toolName = 'comparison-research-summary'", 'summary tool declares stable tool name')
assertIncludes(tool, "domain: 'comparison'", 'summary tool lives in comparison domain')
assertIncludes(tool, 'decisionBasis', 'summary tool emits decision basis')
assertIncludes(tool, 'decisionReasons', 'summary tool emits decision reasons')
assertIncludes(tool, 'QuantStats/Empyrical attribution-style metric explanation', 'summary tool records metric explanation reference')
assertIncludes(tool, 'OpenBB provider-style evidence separation', 'summary tool records data seam reference')
assertIncludes(tool, 'FinRobot auditable summary orchestration', 'summary tool records orchestration reference')
assertNotIncludes(tool, '购买', 'summary tool avoids purchase wording')
assertNotIncludes(tool, '交易', 'summary tool avoids trading wording')

assertIncludes(registry, 'comparisonResearchSummaryTool', 'research tool registry includes summary tool')
assertIncludes(index, 'ComparisonResearchSummaryOutput', 'research tool index exports summary types')

assertIncludes(comparisonReport, 'comparisonResearchSummaryTool.run', 'comparison report calls summary tool')
assertIncludes(comparisonReport, 'summaryResult', 'comparison report consumes summary tool result')
assertNotIncludes(comparisonReport, '费用优先回放收益差', 'comparison report no longer owns summary reason copy')
assertNotIncludes(comparisonReport, '同类指标领先维度与研究证据综合评分', 'comparison report no longer owns decision basis copy')

console.log('OK comparison research summary tool owns decision basis and reasons')
