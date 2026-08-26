const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3000'

function investorSelectionUrl(overrides = {}) {
  const params = new URLSearchParams({
    profile: 'balanced',
    lens: 'score',
    limit: '20',
    sourceLimit: '500',
    minScore: '55',
    horizon: '1to3y',
    purchasePlan: 'sip',
    plannedAmount: '5000',
    maxDrawdownTolerance: '0.15',
    eligibleOnly: 'false',
    minEvidenceGrade: 'D',
    requireSalesRule: 'false',
    minManagerYears: '0',
    minCostScore: '0',
    ...overrides,
  })
  return new URL(`/api/market/research-candidates?${params.toString()}`, baseUrl).toString()
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}: ${payload.error || payload.detail || 'unknown error'}`)
  }
  return payload
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

function parseLocalHref(href) {
  return new URL(href, baseUrl)
}

const researchPayload = await fetchJson(investorSelectionUrl())
const bulkSalesRulesHref = researchPayload.filters?.salesRuleUnlockPreview?.bulkSalesRulesHref || ''
const bulkSalesRulesUrl = parseLocalHref(bulkSalesRulesHref)
assert(researchPayload.total > 0, 'research mode should return real local fund samples')
assert(
  researchPayload.funds?.some((fund) => (fund.currentSalesRuleGate?.missingCount || fund.salesRuleGap?.missingCount || 0) > 0),
  'research mode should keep待补规则 samples visible for补证 research',
)
assert(
  (researchPayload.filters?.salesRuleUnlockPreview?.nearPurchasableQueue || []).length > 0,
  'research mode should expose a near-purchasable sales-rule unlock queue',
)
assert(
  bulkSalesRulesUrl.pathname === '/sales-rules' && Boolean(bulkSalesRulesUrl.searchParams.get('codes')),
  'near-purchasable queue should expose a batch sales-rule evidence link',
)
assert(
  bulkSalesRulesUrl.searchParams.get('purchasePlan') === 'sip',
  'near-purchasable queue should preserve current purchase-plan evidence scope',
)
assert(
  bulkSalesRulesUrl.searchParams.get('plannedAmount') === '5000',
  'near-purchasable queue should preserve current planned amount evidence scope',
)
assert(
  researchPayload.filters?.salesRuleUnlockPreview?.strictReviewHref?.includes('plannedAmount=5000'),
  'near-purchasable strict re-review link should preserve current planned amount',
)
assert(
  researchPayload.filters?.salesRuleUnlockPreview?.strictReviewHref?.includes('eligibleOnly=true'),
  'near-purchasable queue should expose a strict re-review link',
)
assert(
  (researchPayload.filters?.salesRuleUnlockPreview?.nearPurchasableQueue || []).every((item) => item.unlockRank && item.unlockAction && item.missingCount > 0),
  'near-purchasable queue items should carry rank, action, and missing-count evidence',
)
assert(
  (researchPayload.filters?.salesRuleUnlockPreview?.nearPurchasableQueue || []).every((item) => item.riskLevelSourceBacked === false && item.riskLevelEvidenceLabel && item.riskLevelEvidenceDetail),
  'near-purchasable queue items should carry source-backed R1-R5 evidence diagnostics',
)
assert(
  (researchPayload.filters?.salesRuleUnlockPreview?.nearPurchasableQueue || []).every((item) => item.formalCandidateAfterSalesRule === true && item.unlockReadiness?.formalCandidateAfterSalesRule === true),
  'near-purchasable queue must only include samples that can be strictly re-reviewed after sales-rule gaps close',
)

const strictPayload = await fetchJson(investorSelectionUrl({ requireSalesRule: 'true' }))
assert(strictPayload.total === 0, 'strict sales-rule mode must not include funds with sales-rule hard gaps')
assert(
  (strictPayload.filters?.filterStats?.sales_rule_incomplete || 0) > 0,
  'strict sales-rule mode should explain that local rules are incomplete, not silently return empty',
)
assert(
  (strictPayload.filters?.strictBlockerDiagnostics?.diagnostics || []).length > 0,
  'strict sales-rule mode should return structured empty-result blocker diagnostics',
)
assert(
  strictPayload.filters?.strictBlockerDiagnostics?.primary?.href,
  'strict blocker diagnostics should expose an actionable next-step link',
)
assert(
  (strictPayload.funds || []).every((fund) => (fund.currentSalesRuleGate?.missingCount || fund.salesRuleGap?.missingCount || 0) === 0),
  'strict sales-rule mode must not return funds with embedded sales-rule gaps',
)

console.log(`OK investor sales-rule gate smoke ${baseUrl}: research=${researchPayload.total}, strict=${strictPayload.total}, unlockQueue=${researchPayload.filters?.salesRuleUnlockPreview?.nearPurchasableQueue?.length || 0}, incomplete=${strictPayload.filters?.filterStats?.sales_rule_incomplete || 0}`)
