const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3000'

async function fetchJson(path) {
  const response = await fetch(new URL(path, baseUrl).toString(), { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}: ${payload.error || payload.detail || 'unknown error'}`)
  }
  return payload
}

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

const combinedPayload = await fetchJson('/api/sales-rules/gaps?status=candidate,watch&limit=100')

assert(
  combinedPayload.status === 'candidate,watch',
  `combined gap scope should include candidate,watch, got ${combinedPayload.status}`,
)
assert(
  combinedPayload.source === 'candidate_watch_pool_plus_local_sales_rules',
  `combined gap scope should expose candidate_watch source, got ${combinedPayload.source}`,
)
assert(
  Number(combinedPayload.totalMembers || 0) >= Number(combinedPayload.gapCount || 0),
  'totalMembers should be greater than or equal to gapCount',
)
assert(
  Array.isArray(combinedPayload.gaps),
  'combined gap payload should include gaps array',
)

console.log(`OK sales-rule gaps scope smoke ${baseUrl}: status=${combinedPayload.status}, members=${combinedPayload.totalMembers}, gaps=${combinedPayload.gapCount}`)
