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

function assertNotIncludes(content, unexpected, label) {
  if (content.includes(unexpected)) {
    throw new Error(`${label} should not include text: ${unexpected}`)
  }
}

const salesRules = read('lib/sales-rules.ts')
const backendReports = read('backend/routes/reports.py')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

assertIncludes(salesRules, 'function hasSourceBackedRedemptionFeeRule', 'merged sales rules define source-backed redemption selector')
assertIncludes(salesRules, 'rule.redemptionFeeSourceUpdatedAt || rule.sourceUpdatedAt', 'redemption selector keeps source date on redemption row')
assertIncludes(salesRules, 'rule.redemptionFeePlatform || rule.platform', 'redemption selector keeps source platform on redemption row')
assertIncludes(salesRules, 'rule.redemptionFeeSourceUrl || rule.sourceUrl', 'redemption selector keeps source URL on redemption row')
assertIncludes(salesRules, 'rule.redemptionFeeNotes || rule.notes', 'redemption selector keeps source notes on redemption row')
assertIncludes(salesRules, 'const redemptionFeeRule = pickSourceBackedRule', 'merged sales rules pick source-backed redemption row first')
assertIncludes(salesRules, 'hasSourceBackedRedemptionFeeRule,', 'merged sales rules use source-backed redemption predicate')
assertNotIncludes(salesRules, 'const redemptionFeeRule = orderedRules.find((rule) => rule.redemptionFeeRules.length > 0)', 'merged sales rules must not use first redemption row shortcut')

assertIncludes(backendReports, 'same_row_redemption_source_evidence', 'backend report merged sales rule defines redemption source selector')
assertIncludes(backendReports, 'next((rule for rule in rules if same_row_redemption_source_evidence(rule)), None)', 'backend report picks source-backed redemption row first')
assertNotIncludes(backendReports, 'redemption_rule = next((rule for rule in rules if rule.get("redemption_fee_rules")), {})', 'backend report must not use first redemption row shortcut')
assertIncludes(acceptance, 'scripts/sales_rule_transaction_source_cohesion_smoke.mjs', 'fund research acceptance includes transaction source cohesion smoke')

console.log('OK sales rule transaction evidence keeps redemption rules bound to source-backed rows')
