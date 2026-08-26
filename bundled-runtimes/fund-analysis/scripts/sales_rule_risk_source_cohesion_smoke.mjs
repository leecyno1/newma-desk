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

const salesRules = read('lib/sales-rules.ts')
const backendReports = read('backend/routes/reports.py')

assertIncludes(salesRules, 'hasRiskLevelSourceEvidenceOnSameRule', 'frontend merged sales rule requires same-row R1-R5 evidence')
assertIncludes(salesRules, 'const riskLevelRule = orderedRules.find(hasRiskLevelSourceEvidenceOnSameRule)', 'frontend merged sales rule chooses source-backed R1-R5 row first')
assertIncludes(salesRules, 'sourceUrl: riskLevelRule?.riskLevel ? riskLevelRule.sourceUrl', 'frontend merged source URL stays with R1-R5 row')
assertIncludes(salesRules, 'sourceUpdatedAt: riskLevelRule?.riskLevel ? riskLevelRule.sourceUpdatedAt', 'frontend merged source date stays with R1-R5 row')
assertIncludes(salesRules, 'notes: mergedNotes', 'frontend merged notes do not borrow unrelated notes for R1-R5')
assertIncludes(salesRules, "String(rule.sourceUrl || '').toLowerCase().includes('tushare.fund_basic')", 'frontend merged sales rule excludes Tushare fund_basic as R1-R5 source')

assertIncludes(backendReports, 'same_row_risk_source_evidence', 'backend report merged sales rule requires same-row R1-R5 evidence')
assertIncludes(backendReports, 'risk_rule = (', 'backend report uses a dedicated R1-R5 source row')
assertIncludes(backendReports, '"risk_level": risk_rule.get("risk_level")', 'backend report risk level comes from risk source row')
assertIncludes(backendReports, '"source_updated_at": risk_rule.get("source_updated_at") if risk_rule.get("risk_level")', 'backend report source date stays with R1-R5 row')
assertIncludes(backendReports, '"source_url": risk_rule.get("source_url") if risk_rule.get("risk_level")', 'backend report source URL stays with R1-R5 row')
assertIncludes(backendReports, '"notes": risk_rule.get("notes") if risk_rule.get("risk_level")', 'backend report notes stay with R1-R5 row')
assertIncludes(backendReports, '"tushare.fund_basic" in source_url', 'backend report excludes Tushare fund_basic as R1-R5 source')

console.log('OK sales rule R1-R5 source evidence is bound to the same source row')
