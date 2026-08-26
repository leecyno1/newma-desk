const baseUrl = process.env.APP_BASE_URL || 'http://127.0.0.1:3000'

async function requireResponse(path) {
  const response = await fetch(`${baseUrl}${path}`)
  const text = await response.text()
  if (!response.ok) throw new Error(`${path} returned ${response.status}: ${text.slice(0, 300)}`)
  return text
}

const payload = JSON.parse(await requireResponse('/api/managers/browser?category=fixed_income&evidence=research_ready&page=1&page_size=5'))
if (payload.interface_version !== 'fund_manager_browser_v2') throw new Error('manager browser interface missing')
if (!Array.isArray(payload.managers) || payload.managers.length < 1) throw new Error('manager browser data missing')
if (!payload.managers.every((manager) => Array.isArray(manager.category_labels))) throw new Error('category labels missing')
if (!payload.managers.every((manager) => manager.representative_fund?.wind_code)) throw new Error('representative fund missing')
if (!payload.managers.every((manager) => manager.memo_count > 0 && manager.metric_fund_count > 0)) throw new Error('research-ready filter leaked incomplete managers')
if (!payload.managers.every((manager) => manager.representative_fund?.quantitative_evidence?.window)) throw new Error('manager quantitative evidence missing')
if (!payload.managers.every((manager) => manager.latest_memo?.id)) throw new Error('latest manager memo missing')
if (payload.product_scope?.investment_decision !== 'excluded') throw new Error('investment decision scope leaked')
if (payload.product_scope?.sales_rules !== 'excluded') throw new Error('sales rule scope leaked')

const page = await requireResponse('/managers?category=fixed_income&evidence=research_ready')
for (const required of ['当前结果', '代表基金', '量化摘要', '最新经理观点', '调研+量化']) {
  if (!page.includes(required)) throw new Error(`manager browser page missing: ${required}`)
}
for (const forbidden of ['计划金额', '风险偏好', '销售规则', '经理综合收益榜']) {
  if (page.includes(forbidden)) throw new Error(`manager browser page contains excluded content: ${forbidden}`)
}

console.log(`fund manager browser smoke passed: managers=${payload.managers.length}, total=${payload.total}`)
