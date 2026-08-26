import { readFileSync } from 'node:fs'

const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3000'

async function fetchJson(path) {
  const response = await fetch(new URL(path, baseUrl), { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}: ${JSON.stringify(payload)}`)
  return payload
}

const browserPage = readFileSync('app/(dashboard)/companies/FundCompanyBrowserClient.tsx', 'utf8')
const detailPage = readFileSync('app/(dashboard)/companies/[company]/page.tsx', 'utf8')
for (const required of ['规模样本', '业绩样本', '专业分类', '可评价同类组', '公司不按跨类别收益排名']) {
  if (!browserPage.includes(required)) throw new Error(`fund company browser missing disclosure: ${required}`)
}
for (const required of ['公司本身不输出综合评分', '按份额代码计数', '专业类别覆盖', '同类组多周期业绩证据', '区间回报', '小样本，仅作证据线索', '各类别代表基金', '代表经理及其产品', '浏览同类基金']) {
  if (!detailPage.includes(required)) throw new Error(`fund company detail missing research boundary: ${required}`)
}
if (detailPage.includes('公司样本表现') || detailPage.includes('比较前')) {
  throw new Error('company detail must not mix categories into a company performance table or cross-category comparison')
}

const listing = await fetchJson('/api/fund-companies?search=%E6%98%93%E6%96%B9%E8%BE%BE&limit=5')
if (!Array.isArray(listing.companies) || listing.companies.length !== 1) {
  throw new Error(`company search must resolve 易方达: ${JSON.stringify(listing)}`)
}
const company = listing.companies[0]
if (!company.metric_ready_count || company.metric_coverage <= 0 || company.metric_coverage >= 1) {
  throw new Error(`company coverage disclosure invalid: ${JSON.stringify(company)}`)
}
if (!company.peer_group_count || !company.evaluated_peer_group_count || company.evaluated_peer_group_count > company.peer_group_count) {
  throw new Error(`company peer-group coverage invalid: ${JSON.stringify(company)}`)
}

const detail = await fetchJson(`/api/fund-companies/${encodeURIComponent(company.company)}`)
if (!Array.isArray(detail.category_breakdown) || !detail.category_breakdown.length) {
  throw new Error(`company category breakdown unavailable: ${JSON.stringify(detail)}`)
}
if (!Array.isArray(detail.funds) || !detail.funds.some((fund) => fund.metric_as_of)) {
  throw new Error(`company detail must expose dated fund metrics: ${JSON.stringify(detail.funds)}`)
}
if (!Array.isArray(detail.category_window_performance) || !detail.category_window_performance.some((row) => row.peer_group_name && row.metric_window === '1y' && row.total_return != null)) {
  throw new Error(`company detail must expose peer-group window performance: ${JSON.stringify(detail.category_window_performance)}`)
}
if ('window_performance' in detail) {
  throw new Error('company detail must not expose cross-category company performance')
}
if (!detail.category_breakdown.some((category) => category.peer_group_name && category.representative_fund?.wind_code)) {
  throw new Error(`company categories must link representative funds: ${JSON.stringify(detail.category_breakdown)}`)
}
if (!Array.isArray(detail.managers) || !detail.managers.some((manager) => manager.representative_fund_code)) {
  throw new Error(`company detail must expose managers linked to representative products: ${JSON.stringify(detail.managers)}`)
}

console.log('OK company detail uses real categories, representative funds and linked managers')
