const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3000'

async function fetchJson(url, options) {
  const response = await fetch(url, { cache: 'no-store', ...options })
  const payload = await response.json().catch(() => ({}))
  return { response, payload }
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

const allowedHardGateErrors = new Set(['SALES_RULE_GAP_BLOCKED', 'SALES_RULE_REVIEW_ALERT_BLOCKED'])

async function findBlockedPoolMember() {
  const { response: poolsResponse, payload: poolsPayload } = await fetchJson(new URL('/api/fund-pools', baseUrl).toString())
  assert(poolsResponse.ok, `fund pools returned ${poolsResponse.status}: ${poolsPayload.error || poolsPayload.detail || 'unknown error'}`)

  for (const pool of poolsPayload.pools || []) {
    for (const status of ['candidate', 'watch', 'rejected', 'core']) {
      const membersUrl = new URL(`/api/fund-pools/${pool.id}/members`, baseUrl)
      membersUrl.searchParams.set('status', status)
      const { response: membersResponse, payload: membersPayload } = await fetchJson(membersUrl.toString())
      if (!membersResponse.ok) continue

      const members = membersPayload.members || []
      const codes = members
        .map((member) => member.fund_wind_code || member.fund_id)
        .filter(Boolean)
        .slice(0, 100)
      if (!codes.length) continue

      const gapsUrl = new URL('/api/sales-rules/gaps', baseUrl)
      gapsUrl.searchParams.set('codes', codes.join(','))
      gapsUrl.searchParams.set('limit', '100')
      const { response: gapsResponse, payload: gapsPayload } = await fetchJson(gapsUrl.toString())
      if (!gapsResponse.ok) continue

      const gapMap = new Map((gapsPayload.gaps || []).map((gap) => [String(gap.windCode).toUpperCase(), gap]))
      const member = members.find((item) => gapMap.has(String(item.fund_wind_code || item.fund_id).toUpperCase()))
      if (member) {
        const code = String(member.fund_wind_code || member.fund_id).toUpperCase()
        return { pool, status, member, code, gap: gapMap.get(code) }
      }
    }
  }
  return null
}

const blocked = await findBlockedPoolMember()
assert(blocked, 'expected at least one pool member with sales-rule hard gaps for smoke verification')

const { response: patchResponse, payload: patchPayload } = await fetchJson(
  new URL(`/api/fund-pools/members/${blocked.member.id}`, baseUrl).toString(),
  {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'candidate', updatedBy: 'fund-pool-gate-smoke-noop' }),
  },
)

assert(patchResponse.status === 409, `blocked member PATCH should return 409, got ${patchResponse.status}`)
assert(allowedHardGateErrors.has(patchPayload.error), `blocked member PATCH should return a sales-rule hard gate, got ${patchPayload.error || 'unknown'}`)
assert(
  (patchPayload.missingItems || []).length > 0 || patchPayload.alertsHref,
  'blocked member PATCH should expose missing sales-rule items or review-alert link for补证',
)

const { response: postWatchResponse, payload: postWatchPayload } = await fetchJson(
  new URL(`/api/fund-pools/${blocked.pool.id}/members`, baseUrl).toString(),
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      fundId: blocked.code,
      status: 'watch',
      reason: 'market browser smoke should not bypass sales-rule hard gates',
      evidence: {
        source: 'market-browser',
        investorContext: { purchasePlan: 'sip', profile: 'balanced' },
        purchaseGate: { level: 'watchlist', label: '可放入观察池' },
      },
      createdBy: 'market-browser-ui',
    }),
  },
)

assert(postWatchResponse.status === 409, `purchase-path watch POST should return 409, got ${postWatchResponse.status}`)
assert(
  allowedHardGateErrors.has(postWatchPayload.error),
  `purchase-path watch POST should return a sales-rule hard gate, got ${postWatchPayload.error || 'unknown'}`,
)
assert(
  String(postWatchPayload.detail || '').includes('购买路径观察池'),
  'purchase-path watch POST should identify purchase-path watch gate',
)

console.log(`OK fund-pool sales-rule gate smoke ${baseUrl}: ${blocked.code} missing=${blocked.gap?.missingCount || patchPayload.missingItems.length}, patch=${patchResponse.status}, watchPost=${postWatchResponse.status}`)
