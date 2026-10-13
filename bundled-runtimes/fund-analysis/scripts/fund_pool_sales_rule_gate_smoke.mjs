const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3000'
const backendBaseUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8005'

async function fetchJson(url, options) {
  const response = await fetch(url, { cache: 'no-store', ...options })
  const payload = await response.json().catch(() => ({}))
  return { response, payload }
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

const allowedHardGateErrors = new Set([
  'SALES_RULE_GAP_BLOCKED',
  'SALES_RULE_REVIEW_ALERT_BLOCKED',
  'SALES_RULE_AMOUNT_GATE_BLOCKED',
])

// 自建可清理的验证成员：rejected 不是 formal status，加入放行；
// candidate/watch 的 409 门禁不产生任何数据变更，测完删除成员即还原。
async function setUp() {
  const { response: poolsResponse, payload: poolsPayload } = await fetchJson(new URL('/api/fund-pools', baseUrl).toString())
  assert(poolsResponse.ok, `fund pools returned ${poolsResponse.status}: ${poolsPayload.error || poolsPayload.detail || 'unknown error'}`)
  const pool = (poolsPayload.pools || [])[0]
  assert(pool, 'no visible fund pool for smoke verification')

  const { payload: browserPayload } = await fetchJson(new URL('/api/fund-browser?limit=5', baseUrl).toString())
  const code = (browserPayload.data || []).map((fund) => fund.windCode).find(Boolean)
  assert(code, 'no fund code available to verify sales-rule gates')

  const gapsUrl = new URL('/api/sales-rules/gaps', baseUrl)
  gapsUrl.searchParams.set('codes', code)
  gapsUrl.searchParams.set('limit', '1')
  const { payload: gapsPayload } = await fetchJson(gapsUrl.toString())
  const gap = (gapsPayload.gaps || [])[0]
  assert(gap && Number(gap.missingCount) > 0, `${code} has no sales-rule hard gaps; cannot verify pool gate`)

  return { pool, code, gap }
}

const { pool, code, gap } = await setUp()

const { response: createResponse, payload: createPayload } = await fetchJson(
  new URL(`/api/fund-pools/${pool.id}/members`, baseUrl).toString(),
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      fundId: code,
      status: 'rejected',
      reason: 'smoke fixture: sales-rule hard gate verification',
      createdBy: 'fund-pool-gate-smoke',
    }),
  },
)
assert(createResponse.ok, `rejected member fixture should be accepted, got ${createResponse.status}: ${JSON.stringify(createPayload)}`)
const memberId = createPayload.id || createPayload.member_id
assert(memberId, `member fixture missing id: ${JSON.stringify(createPayload)}`)

try {
  const { response: patchResponse, payload: patchPayload } = await fetchJson(
    new URL(`/api/fund-pools/members/${memberId}`, baseUrl).toString(),
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
    new URL(`/api/fund-pools/${pool.id}/members`, baseUrl).toString(),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fundId: code,
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
    String(postWatchPayload.detail || '').includes('不能加入研究观察清单'),
    'purchase-path watch POST should identify the research watchlist gate',
  )

  console.log(`OK fund-pool sales-rule gate smoke ${baseUrl}: ${code} missing=${gap.missingCount}, patch=${patchResponse.status}, watchPost=${postWatchResponse.status}`)
} finally {
  const { response: cleanupResponse } = await fetchJson(
    new URL(`/api/fund-pools/members/${encodeURIComponent(memberId)}`, backendBaseUrl).toString(),
    { method: 'DELETE' },
  )
  assert(cleanupResponse.ok, `smoke fixture cleanup failed: ${cleanupResponse.status}`)
}
