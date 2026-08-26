import { readFileSync } from 'node:fs'

const frontendBaseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3010'
const backendBaseUrl = process.env.BACKEND_API_URL || 'http://127.0.0.1:8005'
const codes = ['000961.OF', '007538.OF', '008390.OF']

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

const comparisonPage = readFileSync('app/(dashboard)/compare/page.tsx', 'utf8')
const comparisonClient = readFileSync('app/(dashboard)/compare/SimpleComparisonClient.tsx', 'utf8')

assert(comparisonPage.includes('/research-snapshot'), 'comparison must use the unified research snapshot')
assert(comparisonPage.includes('evaluation_windows'), 'comparison must read all evaluation windows')
assert(comparisonPage.includes('period_performance'), 'comparison must reuse calendar-year performance from the unified snapshot')
assert(comparisonPage.includes('manager_tenure_performance'), 'comparison must reuse manager tenure coverage from the unified snapshot')
assert(comparisonPage.includes('multi_period_evidence'), 'comparison must reuse multi-period evidence from the unified snapshot')
assert(comparisonPage.includes('holdings?local_only=true'), 'comparison holdings must stay local-only')
assert(comparisonPage.includes('/compare-aligned'), 'comparison must use backend aligned NAV evidence')
assert(comparisonPage.includes('/holding-similarity'), 'comparison must load aligned disclosed-holding similarity')
assert(!comparisonPage.includes('fund.performanceData = {}'), 'comparison must preserve real performance when scores are missing')
assert(comparisonClient.includes('直接添加比较基金'), 'comparison must support direct fund search')
assert(comparisonClient.includes('当前综合评分证据不足，但真实净值'), 'comparison must explain score-independent metrics')
assert(comparisonClient.includes('manager.managementYears'), 'comparison must show manager tenure')
assert(comparisonClient.includes('现任经理任职期表现'), 'comparison must show current-manager tenure performance')
assert(comparisonClient.includes('部分覆盖·不排名'), 'comparison must reject peer ranking for partial manager tenure coverage')
assert(comparisonClient.includes('researchMemoCount'), 'comparison must show linked memo counts')
assert(comparisonClient.includes('最新持仓差异'), 'comparison must show holding differences')
assert(comparisonClient.includes('重仓相似度'), 'comparison must show pairwise disclosed-holding similarity')
assert(comparisonClient.includes('不是完整组合相关性'), 'comparison must explain the holding-similarity boundary')
assert(comparisonClient.includes('selectedEvaluation(item, window)'), 'comparison must switch peer samples with the selected window')
assert(comparisonClient.includes('所有基金只使用共同有净值的日期'), 'comparison must explain the shared NAV date gate')
assert(comparisonClient.includes('部分共同区间 · 不排名'), 'comparison must not rank funds when the selected window is only partially covered')
assert(comparisonClient.includes('alignedWindow?.rankingEligible === true'), 'comparison leaders must require full aligned-window coverage')
assert(comparisonClient.includes("alignedMetric(item, 'totalReturn')"), 'comparison metrics must use the aligned interval')
assert(comparisonClient.includes('年度业绩稳定性'), 'comparison must show calendar-year performance stability')
assert(comparisonClient.includes('部分区间 · 不排名'), 'comparison must keep partial years out of peer ranking')
assert(comparisonClient.includes('period.peerMedianReturn'), 'comparison must show the peer median for each complete year')
assert(comparisonClient.includes('回撤修复对比'), 'comparison must show aligned drawdown recovery evidence')
assert(comparisonClient.includes('谷底后修复'), 'comparison must explain recovery time after the trough')
assert(comparisonClient.includes("alignedMetric(item, 'longestUnderwaterDays')"), 'comparison must rank underwater duration from aligned NAV dates')
assert(comparisonClient.includes('短期和长期分开看'), 'comparison must explain short-term versus long-term evidence')
assert(comparisonClient.includes('近 3 年证据完整'), 'comparison must label complete long-term evidence')

for (const code of codes) {
  const [snapshotResponse, navResponse, holdingsResponse] = await Promise.all([
    fetch(`${backendBaseUrl}/api/funds/${encodeURIComponent(code)}/research-snapshot`, { cache: 'no-store' }),
    fetch(`${backendBaseUrl}/api/funds/${encodeURIComponent(code)}/nav?start_date=2023-08-12&end_date=2026-08-12`, { cache: 'no-store' }),
    fetch(`${backendBaseUrl}/api/funds/${encodeURIComponent(code)}/holdings?local_only=true`, { cache: 'no-store' }),
  ])
  assert(snapshotResponse.ok, `${code} research snapshot unavailable: ${snapshotResponse.status}`)
  assert(navResponse.ok, `${code} nav unavailable: ${navResponse.status}`)
  assert(holdingsResponse.ok, `${code} local holdings unavailable: ${holdingsResponse.status}`)
  const snapshot = await snapshotResponse.json()
  const nav = await navResponse.json()
  const holdings = await holdingsResponse.json()
  assert(snapshot.evaluation?.classification?.peer_group_id === 'peer-index-hs300', `${code} is not in the standardized HS300 peer group`)
  assert(Array.isArray(snapshot.managers) && snapshot.managers.length > 0, `${code} manager team missing`)
  if (snapshot.manager_tenure_performance?.status === 'not_applicable') {
    assert(snapshot.manager_tenure_performance?.coverage_status === 'not_applicable', `${code} manager tenure applicability is inconsistent`)
  } else {
    assert(snapshot.manager_tenure_performance?.requested_start_date, `${code} manager tenure start missing`)
  }
  assert(Number.isFinite(Number(snapshot.fund?.performance_data?.return_1y)), `${code} real return missing`)
  assert(Number.isFinite(Number(snapshot.fund?.risk_metrics?.max_drawdown_1y)), `${code} real drawdown missing`)
  assert(snapshot.period_performance?.status === 'available', `${code} calendar-year performance missing`)
  assert(snapshot.multi_period_evidence?.status === 'long_term_ready', `${code} long-term evidence missing`)
  assert(snapshot.multi_period_evidence?.data_as_of, `${code} long-term evidence date missing`)
  assert(Array.isArray(snapshot.period_performance?.periods) && snapshot.period_performance.periods.length >= 3, `${code} calendar-year history too short`)
  assert(Array.isArray(nav.data) && nav.data.length > 200, `${code} nav history too short`)
  for (const window of ['6m', '1y', '3y']) {
    const evaluation = snapshot.evaluation_windows?.[window]
    assert(evaluation?.peer_context?.metric_window === window, `${code} ${window} evaluation window missing`)
    assert(Number(evaluation?.peer_context?.valid_metric_peer_count) > 0, `${code} ${window} peer sample missing`)
  }
  assert(holdings.source == null || holdings.source === 'local.postgres.holdings', `${code} local-only holdings triggered a remote source`)
}

const alignedResponse = await fetch(`${backendBaseUrl}/api/funds/compare-aligned`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ windCodes: codes }),
  cache: 'no-store',
})
assert(alignedResponse.ok, `aligned comparison unavailable: ${alignedResponse.status}`)
const aligned = await alignedResponse.json()
assert(aligned.methodology === 'same_period_shared_nav_dates_v1', 'aligned comparison methodology missing')
assert(aligned.simulation_used === false, 'aligned comparison must reject simulated NAV')
for (const window of ['6m', '1y', '3y']) {
  const evidence = aligned.windows?.[window]
  assert(['available', 'partial'].includes(evidence?.status), `${window} common NAV window unavailable`)
  assert(Number(evidence.observations) > 20, `${window} common NAV observations too short`)
  assert(Array.isArray(evidence.funds) && evidence.funds.length === codes.length, `${window} aligned fund metrics missing`)
  assert(new Set(evidence.funds.map((item) => Number(item.observations))).size === 1, `${window} funds do not use the same dates`)
  assert(Array.isArray(evidence.chart) && evidence.chart.length === Number(evidence.observations), `${window} aligned chart incomplete`)
  assert(Number(evidence.calendar_coverage_ratio) > 0, `${window} calendar coverage missing`)
  assert(Number(evidence.observation_coverage_ratio) > 0, `${window} observation coverage missing`)
  assert(typeof evidence.ranking_eligible === 'boolean', `${window} ranking eligibility missing`)
  assert(evidence.scope_note.includes('回撤和修复时间'), `${window} aligned drawdown scope missing`)
  assert(evidence.funds.every((item) => Number.isFinite(Number(item.current_drawdown))), `${window} current drawdown missing`)
  assert(evidence.funds.every((item) => Number.isFinite(Number(item.longest_underwater_days))), `${window} underwater duration missing`)
  assert(evidence.funds.every((item) => typeof item.worst_recovered === 'boolean'), `${window} recovery status missing`)
}

const similarityCodes = ['000051.OF', '510310.SH']
const similarityResponse = await fetch(`${backendBaseUrl}/api/funds/holding-similarity`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ windCodes: similarityCodes }),
  cache: 'no-store',
})
assert(similarityResponse.ok, `holding similarity unavailable: ${similarityResponse.status}`)
const similarity = await similarityResponse.json()
assert(similarity.methodology === 'same_quarter_top10_normalized_overlap_v1', 'holding similarity methodology missing')
assert(similarity.simulation_used === false, 'holding similarity must reject simulated holdings')
if (similarity.status === 'insufficient') {
  // 两基金无同一披露季度的公开持仓时，服务必须拒绝输出相似度结论（证据边界原则）。
  assert(Array.isArray(similarity.wind_codes), 'insufficient similarity still reports requested codes')
} else {
  assert(/^\d{4}Q[1-4]$/.test(String(similarity.pairs?.[0]?.quarter)), 'holding similarity must use a shared disclosure quarter')
  assert(Number(similarity.pairs?.[0]?.common_holding_count) >= 5, 'real overlapping holdings not detected')
  assert(Number(similarity.pairs?.[0]?.overlap_ratio) > 0.5, 'real weighted overlap is unexpectedly low')
}

const compareUrl = new URL('/compare', frontendBaseUrl)
compareUrl.searchParams.set('codes', codes.join(','))
const compareResponse = await fetch(compareUrl, { cache: 'no-store' })
const html = await compareResponse.text()
assert(compareResponse.ok, `comparison page unavailable: ${compareResponse.status}`)
for (const phrase of ['指数-沪深300', '天弘沪深300ETF联接-A', '永赢沪深300ETF联接-A', '国联安沪深300ETF联接-A', '直接添加比较基金', '现任经理任职期表现', '本地可见期', '同一净值区间', '完整共同区间', '短期和长期分开看', '近 3 年证据完整', '同区间归一化净值', '跟踪误差较小', '年度业绩稳定性', '高于同类中位数', '回撤修复对比', '谷底后修复', '最长低于前高', '最新持仓差异', '不同权重口径不会混排', '重仓相似度']) {
  assert(html.includes(phrase), `comparison page missing: ${phrase}`)
}

console.log('OK fund comparison aligns NAV dates, calendar years, drawdown recovery and disclosed holdings')
