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

const tool = read('lib/research-platform/tools/comparison-research-score.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')
const comparisonReport = read('lib/fund-comparison-report.ts')
const comparisonReportMarkdown = read('lib/fund-comparison-report-markdown.ts')

assertIncludes(tool, "const toolName = 'comparison-research-score'", 'comparison score tool declares stable tool name')
assertIncludes(tool, "domain: 'comparison'", 'comparison score tool lives in comparison domain')
assertIncludes(tool, 'weights', 'comparison score tool centralizes weights')
assertIncludes(tool, 'researchScore', 'comparison score tool emits research score')
assertIncludes(tool, '研究评分封顶', 'comparison score tool applies evidence caps')
assertIncludes(tool, 'QuantStats/Empyrical 风险收益指标拆解', 'comparison score tool records metric reference')
assertIncludes(tool, 'OpenBB provider-style 数据来源隔离', 'comparison score tool records data seam reference')
assertIncludes(tool, 'FinRobot tool-to-report 可审计编排', 'comparison score tool records orchestration reference')
assertNotIncludes(tool, '购买', 'comparison score tool avoids purchase wording')
assertNotIncludes(tool, '交易', 'comparison score tool avoids trading wording')

assertIncludes(registry, 'comparisonResearchScoreTool', 'research tool registry includes comparison score tool')
assertIncludes(index, 'ComparisonResearchScoreOutput', 'research tool index exports comparison score types')

assertIncludes(comparisonReport, 'comparisonResearchScoreTool.run', 'comparison report calls comparison score tool')
assertIncludes(comparisonReport, 'scoreByCode', 'comparison report consumes score map')
assertIncludes(comparisonReportMarkdown, '横评研究评分', 'comparison report renderer renders research score')
assertIncludes(comparisonReportMarkdown, '研究评分拆解', 'comparison report renderer renders score breakdown')
assertNotIncludes(comparisonReport, 'buildReturnScoreScale', 'comparison report no longer owns return scale scoring')
assertNotIncludes(comparisonReport, '买前', 'comparison report removes buy-before wording')
assertNotIncludes(comparisonReport, '购买', 'comparison report removes purchase wording')
assertNotIncludes(comparisonReport, '买入', 'comparison report removes buy wording')

console.log('OK comparison research score tool owns comparison scoring and report uses it')
