import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) {
    throw new Error(`Missing required file: ${relativePath}`)
  }
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) {
    throw new Error(`${label} missing text: ${expected}`)
  }
}

const reportsRoute = read('backend/routes/reports.py')
const evidenceReport = read('backend/services/evidence_report.py')

assertIncludes(evidenceReport, 'def build_buy_before_decision_section', 'deterministic report has buy-before decision builder')
assertIncludes(evidenceReport, '## 买前总闸门结论', 'deterministic report renders buy-before decision title')
assertIncludes(evidenceReport, 'blocked_by_hard_gate', 'buy-before decision can hard-block')
assertIncludes(evidenceReport, 'verify_first', 'buy-before decision can require verification')
assertIncludes(evidenceReport, 'research_ready', 'buy-before decision can mark research-ready boundary')
assertIncludes(evidenceReport, '该结论只用于基金研究流程分流，不构成买卖建议', 'buy-before decision preserves no-advice boundary')
assertIncludes(evidenceReport, '销售规则缺口：', 'buy-before decision includes sales-rule hard gaps')
assertIncludes(evidenceReport, '同类短板：', 'buy-before decision includes peer weaknesses')

assertIncludes(reportsRoute, 'def _ensure_buy_before_decision_section', 'fund report has buy-before decision appender')
assertIncludes(reportsRoute, '_ensure_buy_before_decision_section(', 'fund report appends buy-before decision section')

console.log('OK fund reports include buy-before decision gate synthesis')
