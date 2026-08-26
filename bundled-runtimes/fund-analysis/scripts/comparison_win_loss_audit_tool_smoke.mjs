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

const tool = read('lib/research-platform/tools/comparison-win-loss-audit.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')
const comparisonReport = read('lib/fund-comparison-report.ts')
const decisiveAudit = read('lib/comparison-decisive-audit.ts')

assertIncludes(tool, "const toolName = 'comparison-win-loss-audit'", 'win/loss audit tool declares stable tool name')
assertIncludes(tool, "domain: 'comparison'", 'win/loss audit tool lives in comparison domain')
assertIncludes(tool, 'buildComparisonDecisiveAudit', 'win/loss audit tool reuses decisive audit')
assertIncludes(tool, 'recheckTriggers', 'win/loss audit tool emits recheck triggers')
assertIncludes(tool, 'winLossLines', 'win/loss audit tool emits structured lines')
assertIncludes(tool, 'QuantStats/Empyrical drawdown-return comparison pattern', 'win/loss audit tool records metric reference')
assertIncludes(tool, 'OpenBB provider-style evidence separation', 'win/loss audit tool records data seam reference')
assertIncludes(tool, 'FinRobot auditable tool-to-report orchestration', 'win/loss audit tool records orchestration reference')
assertNotIncludes(tool, '购买', 'win/loss audit tool avoids purchase wording')
assertNotIncludes(tool, '交易', 'win/loss audit tool avoids trading wording')

assertIncludes(registry, 'comparisonWinLossAuditTool', 'research tool registry includes win/loss audit tool')
assertIncludes(index, 'ComparisonWinLossAuditOutput', 'research tool index exports win/loss audit types')

assertIncludes(comparisonReport, 'comparisonWinLossAuditTool.run', 'comparison report calls win/loss audit tool')
assertIncludes(comparisonReport, 'winLossAuditResult', 'comparison report consumes win/loss tool result')
assertNotIncludes(comparisonReport, 'function buildComparisonWinLossLines', 'comparison report no longer owns win/loss line builder')
assertNotIncludes(comparisonReport, 'buildComparisonDecisiveAudit', 'comparison report no longer owns decisive audit call')
assertNotIncludes(comparisonReport, '买前', 'comparison report removes buy-before wording')
assertNotIncludes(comparisonReport, '购买', 'comparison report removes purchase wording')
assertNotIncludes(comparisonReport, '买入', 'comparison report removes buy wording')

assertIncludes(decisiveAudit, '材料核验可正式横评', 'decisive audit uses material evidence wording')
assertNotIncludes(decisiveAudit, '买前证据', 'decisive audit avoids buy-before evidence wording')

console.log('OK comparison win/loss audit tool owns win/loss lines and report uses it')
