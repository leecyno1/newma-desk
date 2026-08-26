const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3000'
const code = process.env.SMOKE_FUND_CODE || '519674.OF'

function todayText() {
  return new Date().toISOString().slice(0, 10)
}

async function fetchJson(path, options) {
  const response = await fetch(new URL(path, baseUrl).toString(), {
    cache: 'no-store',
    ...options,
  })
  const payload = await response.json().catch(() => ({}))
  return { response, payload }
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

const { response, payload } = await fetchJson(`/api/funds/${encodeURIComponent(code)}/sales-rules`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    platform: 'manual',
    purchaseStatus: 'unknown',
    purchaseStatusLabel: '申购待核',
    redemptionFeeRules: [],
    supportsSip: null,
    sourceUpdatedAt: todayText(),
    notes: 'smoke: thin evidence should be rejected and not written',
  }),
})

const currentRule = await fetchJson(`/api/funds/${encodeURIComponent(code)}/sales-rules?purchasePlan=sip`)

assert(currentRule.response.ok, `single-fund sales rule GET should be OK, got ${currentRule.response.status}`)
assert(currentRule.payload.fundCode === code, `sales rule GET should echo fundCode ${code}`)
assert(currentRule.payload.purchasePlan === 'sip', `sales rule GET should preserve purchasePlan=sip, got ${currentRule.payload.purchasePlan || 'missing'}`)
assert(
  String(currentRule.payload.manualMissingFields || '').includes('定投'),
  `sales rule GET should expose SIP-sensitive manualMissingFields, got ${currentRule.payload.manualMissingFields || 'missing'}`,
)
assert(
  String(currentRule.payload.disclaimer || '').includes('定投'),
  `sales rule GET disclaimer should be purchase-plan aware, got ${currentRule.payload.disclaimer || 'missing'}`,
)
assert(Array.isArray(currentRule.payload.missingRequired), 'sales rule GET should expose missingRequired array')
assert(currentRule.payload.salesRuleGap, 'sales rule GET should expose unified salesRuleGap for current real-data gaps')
assert(
  currentRule.payload.salesRuleGap.windCode === code,
  `salesRuleGap should be scoped to ${code}, got ${currentRule.payload.salesRuleGap.windCode || 'missing'}`,
)
assert(
  currentRule.payload.missingRequired.includes('销售风险等级'),
  'sales rule GET should treat missing/unsourced R1-R5 as a required gap',
)
assert(
  currentRule.payload.salesRuleGap.missingItems.includes('销售风险等级'),
  'salesRuleGap should include missing source-backed risk level',
)
assert(
  currentRule.payload.salesRuleGap.riskLevelSourceBacked === false,
  'salesRuleGap should expose source-backed risk-level status as false for missing/unsourced R1-R5',
)
assert(
  ['missing', 'unsourced', 'stale'].includes(currentRule.payload.salesRuleGap.riskLevelEvidenceStatus),
  `salesRuleGap should explain why R1-R5 is blocked, got ${currentRule.payload.salesRuleGap.riskLevelEvidenceStatus || 'missing'}`,
)
assert(
  String(currentRule.payload.salesRuleGap.riskLevelEvidenceDetail || '').includes('销售平台') || String(currentRule.payload.salesRuleGap.riskLevelEvidenceDetail || '').includes('基金合同'),
  'salesRuleGap should require sales-platform/contract evidence for R1-R5',
)

assert(response.status === 422, `thin single-fund sales rule PATCH should return 422, got ${response.status}`)
assert(payload.error === 'SALES_RULE_VALIDATION_FAILED', `expected SALES_RULE_VALIDATION_FAILED, got ${payload.error || 'unknown'}`)
assert(
  (payload.validationErrors || []).some((item) => String(item).includes('至少填写一项真实')),
  'validation response should explain that at least one real sales evidence item is required',
)

const dirtyRisk = await fetchJson(`/api/funds/${encodeURIComponent(code)}/sales-rules`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    platform: 'tushare_fund_basic',
    purchaseStatus: 'unknown',
    purchaseStatusLabel: '申购待核',
    riskLevel: 'R3',
    sourceUrl: 'tushare.fund_basic',
    sourceUpdatedAt: todayText(),
    notes: 'smoke: Tushare must not be accepted as sales risk-level evidence',
  }),
})

assert(dirtyRisk.response.status === 422, `Tushare risk-level PATCH should return 422, got ${dirtyRisk.response.status}`)
assert(dirtyRisk.payload.error === 'SALES_RULE_VALIDATION_FAILED', `expected SALES_RULE_VALIDATION_FAILED for Tushare risk-level, got ${dirtyRisk.payload.error || 'unknown'}`)
assert(
  (dirtyRisk.payload.validationErrors || []).some((item) => String(item).includes('不能用 Tushare fund_basic')),
  'validation response should reject Tushare fund_basic as risk-level source',
)

const placeholderSource = await fetchJson(`/api/funds/${encodeURIComponent(code)}/sales-rules`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    platform: 'manual',
    purchaseStatus: 'open',
    purchaseStatusLabel: '开放申购',
    purchaseFeeRate: 0.15,
    riskLevel: 'R3',
    sourceUrl: '示例链接',
    sourceUpdatedAt: todayText(),
    notes: '待补',
  }),
})

assert(placeholderSource.response.status === 422, `placeholder source PATCH should return 422, got ${placeholderSource.response.status}`)
assert(placeholderSource.payload.error === 'SALES_RULE_VALIDATION_FAILED', `expected SALES_RULE_VALIDATION_FAILED for placeholder source, got ${placeholderSource.payload.error || 'unknown'}`)
assert(
  (placeholderSource.payload.validationErrors || []).some((item) => String(item).includes('占位')),
  'validation response should reject placeholder sourceUrl/notes instead of treating them as source evidence',
)

const unsourcedTransactionField = await fetchJson(`/api/funds/${encodeURIComponent(code)}/sales-rules`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    platform: 'manual',
    purchaseStatus: 'open',
    purchaseStatusLabel: '开放申购',
    purchaseFeeRate: 0.15,
    sourceUpdatedAt: todayText(),
  }),
})

assert(unsourcedTransactionField.response.status === 422, `unsourced transaction-field PATCH should return 422, got ${unsourcedTransactionField.response.status}`)
assert(unsourcedTransactionField.payload.error === 'SALES_RULE_VALIDATION_FAILED', `expected SALES_RULE_VALIDATION_FAILED for unsourced transaction field, got ${unsourcedTransactionField.payload.error || 'unknown'}`)
assert(
  (unsourcedTransactionField.payload.validationErrors || []).some((item) => String(item).includes('来源背书必须指向真实')),
  'validation response should require real source identity for transaction fields, not just a source date',
)

console.log(`OK fund sales-rule validation smoke ${baseUrl}: ${code} patch=${response.status}, dirtyRisk=${dirtyRisk.response.status}, placeholder=${placeholderSource.response.status}, unsourced=${unsourcedTransactionField.response.status}`)
