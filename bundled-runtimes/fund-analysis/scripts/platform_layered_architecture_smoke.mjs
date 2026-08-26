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

const architecture = read('docs/architecture/fund-research-platform-layered-architecture.md')
const boundary = read('docs/fund-research-module-boundary.md')

assertIncludes(architecture, 'Tools、数据库底座、Skills 与 AI 大模型', 'layered architecture title')
assertIncludes(architecture, '能整', 'layered architecture supports full-system usage')
assertIncludes(architecture, '能零', 'layered architecture supports standalone capabilities')
assertIncludes(architecture, '数据库底座层', 'database foundation layer')
assertIncludes(architecture, 'Tools 层', 'tools layer')
assertIncludes(architecture, 'Skills 层', 'skills layer')
assertIncludes(architecture, 'AI 大模型层', 'AI model layer')
assertIncludes(architecture, 'EvidenceLedger', 'evidence ledger concept')
assertIncludes(architecture, 'ToolResult', 'tool result contract')
assertIncludes(architecture, 'SkillRun', 'skill run contract')
assertIncludes(architecture, 'Tool Manifest', 'tool manifest contract')
assertIncludes(architecture, 'Skill Manifest', 'skill manifest contract')
assertIncludes(architecture, 'AI Agent 只调用 Skill，不绕过 Tool', 'AI orchestration guardrail')
assertIncludes(architecture, '缺证不得默认为正向', 'missing evidence guardrail')
assertIncludes(architecture, 'Tushare `fund_basic`', 'Tushare R1-R5 boundary')
assertIncludes(architecture, '不直接生成“买入/卖出/交易建议”', 'AI no-trading guardrail')
assertIncludes(architecture, '旧入口必须正位', 'legacy entry route canonicalization guardrail')
assertIncludes(architecture, 'canonicalResearchHref', 'canonical research href seam')
assertIncludes(architecture, '页面不承载核心规则', 'page as renderer target')
assertIncludes(architecture, '删除某个页面不会删除核心研究能力', 'delete-page test success criterion')
assertIncludes(architecture, 'screening-condition-health', 'first tool extraction task')
assertIncludes(architecture, 'ranking-leader-questions', 'ranking leader tool extraction task')
assertIncludes(architecture, 'report-reuse-assessment', 'report reuse tool extraction task')
assertIncludes(architecture, 'peer-group-benchmark', 'peer group benchmark tool extraction task')
assertIncludes(architecture, 'comparison-research-score', 'comparison research score tool extraction task')
assertIncludes(architecture, 'comparison-research-summary', 'comparison research summary tool extraction task')
assertIncludes(architecture, 'comparison-win-loss-audit', 'comparison win/loss audit tool extraction task')
assertIncludes(architecture, 'fund-comparison-report-markdown', 'comparison report markdown renderer extraction task')
assertIncludes(architecture, 'market-compare-basket-evidence', 'market compare basket evidence tool extraction task')
assertIncludes(architecture, 'market-compare-basket-win-loss', 'market compare basket win/loss tool extraction task')
assertIncludes(architecture, 'market-current-page-shortlist', 'market current page shortlist tool extraction task')
assertIncludes(architecture, 'market-decision-explainer', 'market decision explainer tool extraction task')
assertIncludes(architecture, 'market-promotion-queue', 'market promotion queue tool extraction task')
assertIncludes(architecture, 'canonicalResearchHref', 'canonical route seam extraction task')
assertIncludes(architecture, 'skills registry smoke', 'skill registry verification task')
assertIncludes(architecture, 'fund-comparison', 'comparison skill')
assertIncludes(architecture, 'manager-evaluation', 'manager evaluation skill')
assertIncludes(architecture, 'evidence-repair', 'evidence repair skill')
assertIncludes(boundary, '基金筛选、基金分析、基金经理评价', 'module boundary remains fund research only')
assertNotIncludes(architecture, ['投委', '会流程'].join(''), 'architecture should not add committee flow')
assertNotIncludes(architecture, ['交易', '执行层'].join(''), 'architecture should not add execution layer')

console.log('OK platform layered architecture defines tools/database/skills/AI seams and fund-research guardrails')
