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

const buyEvidence = read('lib/buy-evidence.ts')
const salesRuleGaps = read('lib/sales-rule-gaps.ts')
const salesRuleGate = read('lib/research-platform/tools/sales-rule-gate.ts')
const evidenceReport = read('backend/services/evidence_report.py')
const fundRepo = read('backend/repositories/fund_repo.py')
const reportRiskSmoke = read('scripts/report_risk_level_source_gate_smoke.mjs')
const acceptanceSmoke = read('scripts/fund_research_acceptance_smoke.mjs')

assertIncludes(buyEvidence, 'if (!salesServiceFeeSourceBacked)', 'buy evidence hard-gates missing sales service fee')
assertIncludes(buyEvidence, '销售服务费不能默认按 0 处理', 'buy evidence refuses default-zero sales service fee')
assertIncludes(buyEvidence, 'requiredBeforeBuy: true', 'buy evidence marks transaction gaps required before buy')
assertIncludes(buyEvidence, 'if (purchasePlan === \'sip\' && !supportsSipSourceBacked)', 'buy evidence checks source-backed SIP support')

assertIncludes(salesRuleGaps, 'salesRuleGateTool', 'sales rule gaps delegates sales service fee gate to platform tool')
assertIncludes(salesRuleGate, '销售服务费（30天来源背书）', 'sales rule gate exposes sales service fee blocker')
assertIncludes(salesRuleGate, 'rule.salesServiceFeeSourceBacked ? \'\' : \'销售服务费（30天来源背书）\'', 'sales rule gate requires source-backed sales service fee')
assertIncludes(salesRuleGaps, 'missingItems.includes(\'销售服务费（30天来源背书）\')', 'sales rule gaps prioritizes sales service fee blocker')

assertIncludes(evidenceReport, 'sales_service_fee_source_backed', 'backend report reads sales service fee source-backed flag')
assertIncludes(evidenceReport, 'missing.append("销售服务费（30天来源背书）")', 'backend deterministic report hard-blocks missing sales service fee')
assertIncludes(fundRepo, 'BOOL_OR(fsr.sales_service_fee_rate IS NOT NULL AND {source_backed_sales_rule_clause})', 'backend complete sales-rule filter requires source-backed sales service fee')

assertIncludes(reportRiskSmoke, '"sales_service_fee_rate": 0', 'deterministic report smoke has valid sales service fee fixture')
assertIncludes(reportRiskSmoke, 'missing_service_fee_rule.pop("sales_service_fee_rate")', 'deterministic report smoke removes sales service fee fixture')
assertIncludes(reportRiskSmoke, 'missing sales service fee should hard-block deterministic buy-before summary', 'deterministic report smoke asserts sales service fee hard block')

assertIncludes(acceptanceSmoke, 'scripts/sales_service_fee_hard_gate_smoke.mjs', 'acceptance smoke includes sales service fee hard gate check')

console.log('OK sales service fee is a source-backed buy-before hard gate')
