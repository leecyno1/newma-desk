import { readFile } from 'node:fs/promises'

const baseUrl = process.env.APP_BASE_URL || 'http://127.0.0.1:3000'
const managerIds = (process.env.FUND_MANAGER_COMPARISON_IDS || '汤龑|M|硕士,孟杰|M|博士').split(',').filter(Boolean)

async function requireResponse(path) {
  const response = await fetch(`${baseUrl}${path}`)
  const text = await response.text()
  if (!response.ok) throw new Error(`${path} returned ${response.status}: ${text.slice(0, 300)}`)
  return text
}

const params = new URLSearchParams()
for (const managerId of managerIds) params.append('manager_id', managerId)
const payload = JSON.parse(await requireResponse(`/api/managers/compare?${params}`))
if (!Array.isArray(payload.managers) || payload.managers.length !== managerIds.length) throw new Error('compared managers missing')
for (const manager of payload.managers) {
  for (const field of ['product_positioning', 'investment_objective', 'investment_method']) {
    if (!Object.hasOwn(manager.profile || {}, field)) throw new Error(`comparison profile field missing: ${field}`)
  }
  for (const field of ['manager_assessment', 'representative_product', 'evidence', 'product_tenures']) {
    if (!Object.hasOwn(manager, field)) throw new Error(`comparison evidence field missing: ${field}`)
  }
  if (!Object.hasOwn(manager.manager_assessment || {}, 'peer_ranked_product_count')) {
    throw new Error('manager assessment peer coverage missing')
  }
  if (!Array.isArray(manager.product_tenures)) throw new Error('manager product tenure table missing')
}
if (!Object.hasOwn(payload.common_period || {}, 'highlight_eligible')) throw new Error('comparison highlight gate missing')
if (payload.common_period?.status === 'available') {
  if (!Object.hasOwn(payload.common_period, 'observation_coverage')) throw new Error('comparison sample coverage missing')
  if (!Object.hasOwn(payload.common_period.metric_meta || {}, 'record_breaking_days_ratio')) throw new Error('record-breaking day ratio missing')
  if (payload.comparison_summary?.status !== 'available' || !payload.comparison_summary.headline) throw new Error('plain-language comparison summary missing')
}

const page = await requireResponse(`/managers/compare?${params}`)
if (!page.includes('基金经理对比')) throw new Error('manager comparison page missing title')
const clientSource = await readFile(new URL('../app/(dashboard)/managers/compare/ManagerComparisonClient.tsx', import.meta.url), 'utf8')
const renderedSource = `${page}\n${clientSource}`
for (const required of ['先看结论', '创新高天数占比', '经理评价摘要', '同类任期排名', '管理起始日', '代表产品', '有据字段']) {
  if (!renderedSource.includes(required)) throw new Error(`manager comparison page missing: ${required}`)
}
for (const forbidden of ['计划金额', '风险偏好', '销售规则']) {
  if (renderedSource.includes(forbidden)) throw new Error(`manager comparison page contains excluded content: ${forbidden}`)
}

console.log(`fund manager comparison smoke passed: ${managerIds.join(' / ')}`)
