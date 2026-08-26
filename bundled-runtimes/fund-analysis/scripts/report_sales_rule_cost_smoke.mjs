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

assertIncludes(reportsRoute, 'def _load_local_sales_rules', 'fund report loads local sales rules')
assertIncludes(reportsRoute, 'FROM fund_sales_rules', 'fund report reads sales rule table')
assertIncludes(reportsRoute, 'sales_rule_snapshot = _load_local_sales_rules(wind_code)', 'fund report collects sales rule snapshot')
assertIncludes(reportsRoute, '_ensure_sales_rule_cost_section(report_content, sales_rule_snapshot, safe_purchase_plan)', 'fund report appends sales rule cost section for all modes')
assertIncludes(reportsRoute, '"sales_rule_status": sales_rule_snapshot.get("status")', 'fund report stores sales rule status')

assertIncludes(evidenceReport, 'def build_sales_rule_cost_report_section', 'deterministic report has sales rule cost section builder')
assertIncludes(evidenceReport, '## 费用与销售规则快照', 'deterministic report renders sales rule section title')
assertIncludes(evidenceReport, '申购费率', 'deterministic report renders purchase fee')
assertIncludes(evidenceReport, '赎回规则', 'deterministic report renders redemption rules')
assertIncludes(evidenceReport, '销售风险等级', 'deterministic report renders risk level')
assertIncludes(evidenceReport, 'RISK_LEVEL_SOURCE_MAX_AGE_DAYS = 30', 'deterministic report uses 30d risk-level source window')
assertIncludes(evidenceReport, 'def _has_source_backed_sales_risk_level', 'deterministic report validates source-backed risk level')
assertIncludes(evidenceReport, 'Tushare fund_basic 不可作为 R1-R5 来源', 'deterministic report rejects Tushare as R1-R5 source')
assertIncludes(evidenceReport, '销售风险等级（R1-R5 30天来源背书）', 'deterministic report treats unsourced risk level as hard gap')
assertIncludes(evidenceReport, '费用、赎回、限购和 R1-R5 是购买前硬门禁', 'sales rule section preserves buy-before hard gate')

console.log('OK fund reports include fee and sales-rule cost evidence')
