const baseUrl = process.env.LOCAL_APP_URL || process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3000'

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function requestJson(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  })
  const payload = await response.json().catch(() => ({}))
  return { response, payload }
}

const purchasePlan = 'sip'
const plannedAmount = 1000
const fundsQuery = `/api/funds?limit=5&sortBy=screeningScore&sortOrder=desc&purchasePlan=${purchasePlan}&plannedAmount=${plannedAmount}`
const { response: fundsResponse, payload: fundsPayload } = await requestJson(fundsQuery)
assert(fundsResponse.ok, `fund list failed: ${fundsResponse.status}`)
assert(Array.isArray(fundsPayload.data) && fundsPayload.data.length >= 2, 'expected at least two real funds from market browser API')

const [primaryFund, secondaryFund] = fundsPayload.data
assert(primaryFund.windCode && primaryFund.id, `primary fund missing identifiers: ${JSON.stringify(primaryFund)}`)

const detailPath = `/api/funds/${encodeURIComponent(primaryFund.id)}?purchasePlan=${purchasePlan}&plannedAmount=${plannedAmount}`
const { response: detailResponse, payload: detailPayload } = await requestJson(detailPath)
assert(detailResponse.ok, `fund detail failed: ${detailResponse.status}`)
assert(detailPayload.windCode === primaryFund.windCode, 'fund detail should resolve the selected real fund')
assert(detailPayload.buyEvidence, 'fund detail should expose buyEvidence')
assert(detailPayload.peerPercentiles !== undefined, 'fund detail should expose peer percentile field, even if unavailable')

const compareCodes = [primaryFund.windCode, secondaryFund.windCode]
const { response: compareResponse, payload: comparePayload } = await requestJson('/api/funds/compare-matrix', {
  method: 'POST',
  body: JSON.stringify({ windCodes: compareCodes, purchasePlan, plannedAmount, window: '1y' }),
})
assert(compareResponse.ok, `compare matrix failed: ${compareResponse.status}`)
assert(Array.isArray(comparePayload.funds) && comparePayload.funds.length >= 2, 'compare matrix should return compared funds')
assert(comparePayload.funds.every((fund) => fund.buy_evidence !== undefined), 'compare matrix should attach buy evidence for each fund')

const gapsPath = `/api/sales-rules/gaps?codes=${encodeURIComponent(primaryFund.windCode)}&purchasePlan=${purchasePlan}&plannedAmount=${plannedAmount}&limit=1`
const { response: gapsResponse, payload: gapsPayload } = await requestJson(gapsPath)
assert(gapsResponse.ok, `sales-rule gaps failed: ${gapsResponse.status}`)
assert(gapsPayload.source && Array.isArray(gapsPayload.gaps), 'sales-rule gaps should expose source and gap list')

const { response: poolsResponse, payload: poolsPayload } = await requestJson('/api/fund-pools')
assert(poolsResponse.ok, `fund pools failed: ${poolsResponse.status}`)
assert(Array.isArray(poolsPayload.pools) && poolsPayload.pools.length > 0, 'expected at least one real fund pool')
const defaultPool = poolsPayload.pools.find((pool) => pool.is_default) || poolsPayload.pools[0]
assert(defaultPool.id, 'default fund pool should have id')

if (gapsPayload.gapCount > 0) {
  const { response: memberResponse, payload: memberPayload } = await requestJson(`/api/fund-pools/${encodeURIComponent(defaultPool.id)}/members`, {
    method: 'POST',
    body: JSON.stringify({
      fundId: primaryFund.windCode,
      status: 'watch',
      reason: 'local_real_flow_smoke 验证销售规则硬门禁',
      latestConclusion: '缺销售规则时应阻断购买路径观察池。',
      evidence: {
        source: 'market-browser-local-real-flow-smoke',
        investorContext: { purchasePlan, plannedAmount },
        purchaseGate: {
          level: 'verify_first',
          evidenceGrade: 'B',
          plannedAmount,
        },
      },
      createdBy: 'market-browser-ui',
    }),
  })
  assert(memberResponse.status === 409, `missing sales rules should block pool member creation, got ${memberResponse.status}`)
  assert(
    ['SALES_RULE_GAP_BLOCKED', 'SALES_RULE_AMOUNT_GATE_BLOCKED', 'SALES_RULE_REVIEW_ALERT_BLOCKED'].includes(memberPayload.error),
    `unexpected pool gate error: ${JSON.stringify(memberPayload)}`,
  )
  assert(Array.isArray(memberPayload.missingItems) && memberPayload.missingItems.length > 0, 'pool gate should return missingItems')
}

const { response: membersResponse, payload: membersPayload } = await requestJson(`/api/fund-pools/${encodeURIComponent(defaultPool.id)}/members?status=watch`)
assert(membersResponse.ok, `fund pool members failed: ${membersResponse.status}`)
assert(Array.isArray(membersPayload.members), 'fund pool members should return members array')

const { response: rulesResponse, payload: rulesPayload } = await requestJson('/api/alerts/rules')
assert(rulesResponse.ok, `alert rules failed: ${rulesResponse.status}`)
assert(Array.isArray(rulesPayload.rules), 'alert rules should return rules array')

const { response: scanResponse, payload: scanPayload } = await requestJson('/api/alerts/scan', { method: 'POST' })
assert(scanResponse.ok, `alert scan failed: ${scanResponse.status}`)
assert(typeof scanPayload.createdCount === 'number', 'alert scan should expose createdCount')

console.log(`OK local real flow verified with ${primaryFund.windCode}: market/detail/compare/sales-gate/pool/alert scan`)
