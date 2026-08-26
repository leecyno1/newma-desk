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

const reportBuilder = read('lib/fund-comparison-report.ts')
const renderer = read('lib/fund-comparison-report-markdown.ts')

assertIncludes(reportBuilder, 'renderFundComparisonMarkdown(payloadWithoutMarkdown)', 'comparison report builder delegates markdown rendering')
assertNotIncludes(reportBuilder, 'function buildMarkdown', 'comparison report builder no longer owns markdown renderer')
assertNotIncludes(reportBuilder, '# 基金横向比较报告', 'comparison report builder no longer embeds report body copy')
assertNotIncludes(reportBuilder, 'strictRiskLevelSourcePolicyMarkdownLines', 'comparison report builder no longer imports markdown helpers')

assertIncludes(renderer, 'export function renderFundComparisonMarkdown', 'markdown renderer exports stable function')
assertIncludes(renderer, '# 基金横向比较报告', 'markdown renderer owns title')
assertIncludes(renderer, '## 研究复核结论', 'markdown renderer owns research conclusion section')
assertIncludes(renderer, '横评研究评分', 'markdown renderer renders research score')
assertIncludes(renderer, '研究评分拆解', 'markdown renderer renders score breakdown')
assertIncludes(renderer, 'strictRiskLevelSourcePolicyMarkdownLines', 'markdown renderer keeps risk source policy block')
assertIncludes(renderer, 'shareClassLine', 'markdown renderer owns share class copy')
assertNotIncludes(renderer, '购买决策分', 'markdown renderer avoids legacy purchase decision score wording')
assertNotIncludes(renderer, '买前', 'markdown renderer avoids buy-before wording')

console.log('OK comparison report markdown rendering is isolated from report builder')
