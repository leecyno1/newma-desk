const baseUrl = process.env.APP_BASE_URL || 'http://127.0.0.1:3000'
const managerId = process.env.FUND_MANAGER_ID || '张仲维|M|硕士'

async function requireResponse(path) {
  const response = await fetch(`${baseUrl}${path}`)
  const text = await response.text()
  if (!response.ok) throw new Error(`${path} returned ${response.status}: ${text.slice(0, 300)}`)
  return { response, text }
}

const detailPath = `/api/managers/${encodeURIComponent(managerId)}`
const detail = JSON.parse((await requireResponse(detailPath)).text)
if (detail.source !== 'fund_manager_research_snapshot_v1') throw new Error('manager research snapshot source missing')
if (!Array.isArray(detail.funds) || detail.funds.length < 1) throw new Error('current funds missing')
if (detail.funds.length !== detail.productTenures.currentProductCount) throw new Error('current fund cards must be deduplicated by fund entity')
if (detail.funds.some((fund) => !Array.isArray(fund.shareCodes) || fund.shareCodes.length < 1)) throw new Error('share class trace is missing')
if (!Array.isArray(detail.reports)) throw new Error('research memo list missing')
if (!detail.historicalViewpoints || detail.historicalViewpoints.methodology !== 'confirmed_manager_memo_timeline_v1') throw new Error('manager viewpoint timeline missing')
if (detail.historicalViewpoints.count !== detail.reports.length) throw new Error('viewpoint timeline and confirmed memo count diverged')
if (!Array.isArray(detail.historicalViewpoints.years)) throw new Error('viewpoint year filters missing')
if (detail.reports.length > 0 && detail.historicalViewpoints.years.length < 1) throw new Error('viewpoint year filters missing')
if (detail.reports.length === 0 && (detail.historicalViewpoints.status !== 'empty' || detail.historicalViewpoints.count !== 0)) throw new Error('empty viewpoint timeline status missing')
if (detail.historicalViewpoints.items.some((item) => !item.date || !item.title || !item.viewpoint)) throw new Error('viewpoint timeline evidence incomplete')
if (detail.historicalViewpoints.items.some((item) => !['manager_profile_evidence', 'memo_key_point', 'memo_summary'].includes(item.viewpointSource))) throw new Error('viewpoint timeline source is not evidence-backed')
if (!detail.productTenures || !Array.isArray(detail.productTenures.items)) throw new Error('manager product tenure list missing')
if (detail.productTenures.items.some((item) => !item.peerRanking || !item.peerRanking.methodology_version)) throw new Error('same-period peer ranking evidence missing')
if (detail.productTenures.currentProductCount < 1) throw new Error('current manager products missing')
if (!detail.coverage || typeof detail.coverage.tenureMetricFundCount !== 'number') throw new Error('tenure metric coverage missing')
if (!detail.managerAssessment || !['available', 'partial'].includes(detail.managerAssessment.status)) throw new Error('manager evidence assessment missing')
if (!detail.portfolioSummary || detail.portfolioSummary.currentProductCount !== detail.productTenures.currentProductCount) throw new Error('manager portfolio summary missing or product count diverged')
if (typeof detail.portfolioSummary.currentShareCount !== 'number') throw new Error('manager share count summary missing')
if (typeof detail.portfolioSummary.managedAssetProductCount !== 'number') throw new Error('manager asset coverage summary missing')
if (!Array.isArray(detail.portfolioSummary.categoryDistribution)) throw new Error('manager category distribution missing')
if (!Object.hasOwn(detail.portfolioSummary, 'institutionalHoldingRatio')) throw new Error('institutional holding connection status missing')
if (detail.managerAssessment.currentProductCount !== detail.productTenures.currentProductCount) throw new Error('manager assessment product count diverged')
if (detail.managerAssessment.tenureEvaluatedProductCount < 1) throw new Error('manager assessment lacks product-level tenure evidence')
if (detail.managerAssessment.peerRankedProductCount < 1) throw new Error('manager assessment lacks same-period peer evidence')
if (!detail.managerAssessment.representativeProduct?.fund_code) throw new Error('representative evidence product missing')
if (!Array.isArray(detail.managerAssessment.strengths) || !Array.isArray(detail.managerAssessment.risks)) throw new Error('manager strengths or risks missing')
if (!detail.managerAssessment.scopeNote?.includes('不生成经理综合收益')) throw new Error('manager assessment scope note missing')
if (detail.funds.some((fund) => !fund.evaluationSummary)) throw new Error('evaluation evidence summary missing')
if (!Object.hasOwn(detail.profile || {}, 'excessReturnSource')) throw new Error('excess return source field missing')
if (!Object.hasOwn(detail.profile || {}, 'holdingStyle')) throw new Error('holding style field missing')
for (const field of ['productPositioning', 'investmentObjective', 'investmentMethod']) {
  if (!Object.hasOwn(detail.profile || {}, field)) throw new Error(`manager profile field missing: ${field}`)
}

const careerFundCode = detail.managerAssessment.representativeProduct.fund_code
const career = JSON.parse((await requireResponse(`${detailPath}/career?fund_code=${encodeURIComponent(careerFundCode)}&period=tenure`)).text)
if (career.status !== 'available') throw new Error(`manager career curve unavailable: ${JSON.stringify(career).slice(0, 300)}`)
if (career.simulation_used !== false) throw new Error('manager career curve must explicitly reject simulated data')
if (!Array.isArray(career.products) || career.products.length < 1) throw new Error('manager career products missing')
if (new Set(career.products.map((product) => product.tenure_key)).size !== career.products.length) throw new Error('manager tenure selector keys are not unique')
if (!Array.isArray(career.curve) || career.curve.length < 2) throw new Error('manager career real NAV curve missing')
if (!career.metrics || !Object.hasOwn(career.metrics, 'downside_risk') || !Object.hasOwn(career.metrics, 'sortino_ratio') || !Object.hasOwn(career.metrics, 'record_breaking_days_ratio')) throw new Error('manager career risk or holding-experience metrics missing')
if (!career.benchmark || career.benchmark.status !== 'available') throw new Error('verified benchmark curve missing for benchmark-ready product')
if (!Object.hasOwn(career.metrics, 'benchmark_return') || !Object.hasOwn(career.metrics, 'excess_return')) throw new Error('manager career relative metrics missing')
if (!career.peer_ranking || career.peer_ranking.methodology_version !== 'manager_tenure_same_period_peer_rank_v3') throw new Error('manager career same-period peer ranking missing')
if (!['sufficient', 'insufficient_peer_sample'].includes(career.peer_ranking.status)) throw new Error(`manager career peer ranking unavailable: ${career.peer_ranking.status}`)
if (career.peer_ranking.status === 'sufficient' && (!career.peer_ranking.metrics?.total_return?.rank || !career.peer_ranking.metrics?.total_return?.peer_count)) throw new Error('manager career peer rank evidence missing')
if (!Object.hasOwn(career.peer_ranking.metrics || {}, 'max_drawdown') || !Object.hasOwn(career.peer_ranking.metrics || {}, 'sharpe_ratio') || !Object.hasOwn(career.peer_ranking.metrics || {}, 'record_breaking_days_ratio')) throw new Error('manager career risk or holding-experience peer ranks missing')
if (!Array.isArray(career.events)) throw new Error('manager career memo events missing')

const page = (await requireResponse(`/managers/${encodeURIComponent(managerId)}`)).text
for (const required of ['经理评价摘要', '先看证据覆盖，再看具体产品', '代表性观察产品', '已证实的相对优势', '需要关注的相对弱项', '基金经理生涯曲线', '真实净值', '不把不同产品拼成经理综合净值', '回撤控制', '不跨基金类别', '当前管理基金与任期证据', '分类内评价', '该经理任期', '产品任职全景', '同类任期排名', '同区间', '投资框架与风格画像', '调研纪要与历史观点']) {
  if (!page.includes(required)) throw new Error(`manager page missing: ${required}`)
}
if (detail.profile.status === 'empty') {
  if (!page.includes('经理画像待从纪要确认')) throw new Error('manager empty profile state missing')
} else {
  for (const required of ['产品定位', '投资目标', '投资方法', '超额收益来源', '持股风格']) {
    if (!page.includes(required)) throw new Error(`manager profile section missing: ${required}`)
  }
}
if (detail.reports.length > 0) {
  for (const required of ['搜索观点', '全部年份', '仅含已绑定到该经理的本地纪要']) {
    if (!page.includes(required)) throw new Error(`manager memo timeline missing: ${required}`)
  }
} else if (!page.includes('尚未关联调研纪要')) {
  throw new Error('manager empty memo state missing')
}
for (const required of ['产品 / 份额', '在管类型分布', '管理规模覆盖', '机构持有占比', '待接入']) {
  if (!page.includes(required)) throw new Error(`manager portfolio summary page missing: ${required}`)
}
for (const forbidden of ['计划金额', '销售规则', '风险偏好']) {
  if (page.includes(forbidden)) throw new Error(`manager page still contains excluded content: ${forbidden}`)
}

console.log(`fund manager detail smoke passed: ${managerId}, funds=${detail.funds.length}, memos=${detail.reports.length}`)
