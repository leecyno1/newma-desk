import assert from 'node:assert/strict'
import fs from 'node:fs'

const baseUrl = process.env.APP_BASE_URL || 'http://127.0.0.1:3000'

async function request(path, init) {
  const response = await fetch(new URL(path, baseUrl), init)
  const payload = await response.json().catch(() => ({}))
  assert(response.ok, `${path} returned ${response.status}: ${payload.error || payload.detail || 'unknown error'}`)
  return payload
}

const navigation = fs.readFileSync('components/navigation/AppNavigation.tsx', 'utf8')
const discover = fs.readFileSync('app/(dashboard)/discover/FundDiscoverClient.tsx', 'utf8')
const watchlist = fs.readFileSync('app/(dashboard)/watchlist/WatchlistClient.tsx', 'utf8')

assert(navigation.includes("href: '/watchlist'"), 'navigation should expose 我的自选')
assert(discover.includes('加入自选'), 'fund browser should support adding to watchlist')
for (const label of ['自选分组', '收藏理由', '专业评分', '最大回撤']) {
  assert(watchlist.includes(label), `watchlist page should expose ${label}`)
}

const groups = await request('/api/watchlists')
const defaultGroup = groups.watchlists.find((item) => item.is_default)
assert(defaultGroup?.id, 'default watchlist should exist')

const funds = await request('/api/fund-browser?limit=1')
const fund = funds.data?.[0]
assert(fund?.windCode, 'fund browser should return a real fund')

const added = await request(`/api/watchlists/${encodeURIComponent(defaultGroup.id)}/members`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ fundId: fund.windCode, reason: 'watchlist-smoke' }),
})
assert(added.memberId, 'adding a fund should return memberId')

const members = await request(`/api/watchlists/${encodeURIComponent(defaultGroup.id)}/members`)
const saved = members.members.find((item) => item.memberId === added.memberId)
assert(saved, 'saved fund should appear in watchlist')
assert.equal(saved.reason, 'watchlist-smoke')
assert(saved.researchProfile?.peerGroup, 'saved fund should include professional classification')
assert(saved.rollingMetrics?.['1y'], 'saved fund should include one-year metrics')
assert(saved.professionalScoring, 'saved fund should include professional scoring')

await request(`/api/watchlists/members/${encodeURIComponent(added.memberId)}`, { method: 'DELETE' })

console.log('OK 我的自选：默认分组、加入、评价展示与移出均可用')
