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

function blockBeforeAlias(content, alias) {
  const marker = `) AS ${alias}`
  const markerIndex = content.indexOf(marker)
  if (markerIndex === -1) throw new Error(`Missing BOOL_OR alias: ${alias}`)
  const blockStart = content.lastIndexOf('BOOL_OR(', markerIndex)
  if (blockStart === -1) throw new Error(`Missing BOOL_OR block for alias: ${alias}`)
  return content.slice(blockStart, markerIndex)
}

function assertSourceBackedBlock(content, alias, predicate, label) {
  const block = blockBeforeAlias(content, alias)
  assertIncludes(block, predicate, `${label} predicate`)
  assertIncludes(block, 'source_updated_at IS NOT NULL', `${label} requires source date`)
  assertIncludes(block, "source_updated_at >= CURRENT_DATE - INTERVAL '30 days'", `${label} rejects stale source date`)
  assertIncludes(block, 'source_updated_at <= CURRENT_DATE', `${label} rejects future source date`)
  assertIncludes(block, "COALESCE(LOWER(platform), '') NOT LIKE '%tushare%'", `${label} rejects Tushare platform`)
  assertIncludes(block, "COALESCE(LOWER(source_url), '') NOT LIKE '%tushare.fund_basic%'", `${label} rejects Tushare fund_basic source URL`)
  assertIncludes(block, 'salesSourceIdentityClause', `${label} requires traceable source identity`)
}

const coverageLib = read('lib/evidence-coverage.ts')
const acceptanceSmoke = read('scripts/fund_research_acceptance_smoke.mjs')

const transactionFields = [
  ['has_purchase_status', "purchase_status <> 'unknown'", 'purchase status'],
  ['has_purchase_fee', 'purchase_fee_rate IS NOT NULL', 'purchase fee'],
  ['has_redemption_rule', "jsonb_array_length(COALESCE(redemption_fee_rules, '[]'::jsonb)) > 0", 'redemption rules'],
  ['has_min_purchase', 'min_purchase_amount IS NOT NULL', 'minimum purchase'],
  ['has_daily_limit', 'daily_limit_amount IS NOT NULL', 'daily purchase limit'],
  ['has_sales_service_fee', 'sales_service_fee_rate IS NOT NULL', 'sales service fee'],
  ['has_sip_rule', '(supports_sip IS NOT NULL OR min_sip_amount IS NOT NULL)', 'SIP rule'],
]

for (const [alias, predicate, label] of transactionFields) {
  assertSourceBackedBlock(coverageLib, alias, predicate, label)
}

assertIncludes(coverageLib, "COUNT(*) FILTER (WHERE sales_service_fee_ready)::int AS sales_service_fee_ready", 'coverage counts sales service fee readiness')
assertIncludes(coverageLib, "CASE WHEN NOT sales_service_fee_ready THEN '销售服务费' END", 'gap sample includes sales service fee')
assertIncludes(coverageLib, "CASE WHEN NOT sip_rule_ready THEN '定投规则' END", 'gap sample includes SIP rule')
assertIncludes(coverageLib, "(CASE WHEN NOT sales_service_fee_ready THEN 1 ELSE 0 END)", 'required gap count includes sales service fee')
assertIncludes(coverageLib, "(CASE WHEN NOT sip_rule_ready THEN 1 ELSE 0 END)", 'required gap count includes SIP rule')
assertIncludes(coverageLib, "dimension('sales_service_fee', '销售服务费', '研究复核'", 'dimensions include sales service fee')
assertIncludes(coverageLib, "dimension('sip_rule', '定投规则', '研究复核'", 'dimensions include SIP rule')
assertIncludes(coverageLib, "numberValue(row?.sales_service_fee_ready), total, true", 'sales service fee is a research-review required dimension')
assertIncludes(coverageLib, "numberValue(row?.sip_rule_ready), total, true", 'SIP rule is a research-review required dimension')
assertIncludes(coverageLib, '必须有 30 天内来源背书', 'transaction dimension copy explains 30-day source backing')

assertIncludes(acceptanceSmoke, 'scripts/evidence_coverage_transaction_source_smoke.mjs', 'acceptance smoke includes transaction source coverage check')

console.log('OK evidence coverage requires 30-day source-backed transaction fields')
