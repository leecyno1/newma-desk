const baseUrl = process.env.APP_BASE_URL || process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3000'

async function requireResponse(path) {
  const response = await fetch(`${baseUrl}${path}`)
  const text = await response.text()
  if (!response.ok) throw new Error(`${path} returned ${response.status}: ${text.slice(0, 300)}`)
  return text
}

const home = JSON.parse(await requireResponse('/api/home'))
if (home.interface_version !== 'fund_selection_home_v1') throw new Error('home interface version missing')
for (const key of ['fund_share_count', 'fund_manager_count', 'research_memo_count', 'recommendation_ready_category_count']) {
  if (!(Number(home.summary?.[key]) > 0)) throw new Error(`home summary missing: ${key}`)
}
if (!Array.isArray(home.featured_peer_groups) || home.featured_peer_groups.length === 0) throw new Error('featured peer groups missing')
if (!Array.isArray(home.featured_managers) || home.featured_managers.length === 0) throw new Error('featured managers missing')
if (!Array.isArray(home.latest_research_memos) || home.latest_research_memos.length === 0) throw new Error('latest research memos missing')

const page = await requireResponse('/')
for (const required of ['基金名称 / 代码 / 经理 / 公司', '主动基金评价覆盖', '最近入库纪要', 'AI 研究分析']) {
  if (!page.includes(required)) throw new Error(`home page missing: ${required}`)
}
for (const forbidden of ['机构交易情绪', '择时信号', '配置建议', '计划金额', '销售规则']) {
  if (page.includes(forbidden)) throw new Error(`home page contains excluded content: ${forbidden}`)
}

const searchPage = await requireResponse(`/discover?search=${encodeURIComponent('景顺长城景盛双息')}`)
if (!searchPage.includes('景顺长城景盛双息')) throw new Error('home fund search does not reach filtered browser')

console.log(`fund home smoke passed: shares=${home.summary.fund_share_count}, managers=${home.summary.fund_manager_count}, memos=${home.summary.research_memo_count}`)
