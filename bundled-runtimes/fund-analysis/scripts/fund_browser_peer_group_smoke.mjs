import { readFileSync } from 'node:fs'

const baseUrl = process.env.FRONTEND_BASE_URL || 'http://127.0.0.1:3000'

async function fetchJson(path) {
  const response = await fetch(new URL(path, baseUrl), { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}: ${JSON.stringify(payload)}`)
  return payload
}

const discoverPage = readFileSync('app/(dashboard)/discover/FundDiscoverClient.tsx', 'utf8')
const simpleFundView = readFileSync('lib/simple-fund-view.ts', 'utf8')
const simpleFundDetailPage = readFileSync('app/(dashboard)/funds/[id]/page.tsx', 'utf8')
const simpleComparePage = readFileSync('app/(dashboard)/compare/page.tsx', 'utf8')
const categoryPresets = readFileSync('lib/fund-category-presets.ts', 'utf8')
for (const required of [
  "professionalPeerGroupId(fund)",
  "这只基金尚未完成专业分类",
  "比较已锁定",
  "params.set('peerGroup', nextPeerGroup)",
  "params.set('return6mMin'",
  "params.set('return3yMin'",
  "availability: nextAvailability",
  "可评价",
  "已分类 · 评价待补",
  "peerReturnMetric(fund, '6m')",
  "peerReturnMetric(fund, '3y')",
  "多周期同类领先",
  "基础指数",
  "收益口径",
  "期限",
  "categoryDisplayName",
  "selectBondDimension",
  "评价一只基金",
  "推荐方案",
  "已选条件",
  "selectRecommendedPlan",
  "fundBrowserSummary",
  "亮点：",
  "风险：",
  "本次筛选怎么来的",
  "为什么出现在这里",
  "条件已核对",
  "fundSelectionExplanation",
  "风格标签",
  "任一匹配",
  "全部匹配",
  "styleTagCatalog",
  "params.set('styleTags'",
  "先选一个用途",
]) {
  if (!discoverPage.includes(required)) throw new Error(`fund browser missing peer-group guard: ${required}`)
}

if (discoverPage.includes("professionalFundScore(fund) == null)")) {
  throw new Error('fund browser must not require a professional score before same-peer comparison')
}

for (const [label, source] of [
  ['fund browser', simpleFundView],
  ['fund detail', simpleFundDetailPage],
  ['fund comparison', simpleComparePage],
]) {
  if (!source.includes("'insufficient'")) {
    throw new Error(`${label} must hide scores when data quality is insufficient`)
  }
}

const defaultFunds = await fetchJson('/api/fund-browser?limit=10')
if (!Array.isArray(defaultFunds.data) || defaultFunds.data.length < 10) {
  throw new Error(`default fund browser must show a useful first page: ${JSON.stringify(defaultFunds)}`)
}
if (defaultFunds.data.some((fund) => fund.professionalScoring?.overall_score == null)) {
  throw new Error(`default fund browser must prioritize evidence-ready funds: ${JSON.stringify(defaultFunds.data)}`)
}
if (defaultFunds.availability !== 'evaluated' || defaultFunds.source !== 'evaluated_fund_universe') {
  throw new Error(`default fund browser must disclose evaluated-fund scope: ${JSON.stringify(defaultFunds)}`)
}
if (defaultFunds.data.some((fund) => fund.evaluationReady !== true || fund.classificationReady !== true)) {
  throw new Error(`default fund browser leaked non-evaluable funds: ${JSON.stringify(defaultFunds.data)}`)
}

const classifiedFunds = await fetchJson('/api/fund-browser?availability=classified&limit=10')
if (classifiedFunds.availability !== 'classified' || classifiedFunds.source !== 'standardized_classified_universe') {
  throw new Error(`classified fund scope missing: ${JSON.stringify(classifiedFunds)}`)
}
if (classifiedFunds.pagination?.total <= defaultFunds.pagination?.total) {
  throw new Error(`classified scope must be broader than evaluated scope: ${JSON.stringify({ classified: classifiedFunds.pagination, evaluated: defaultFunds.pagination })}`)
}

const fullDatabaseSearch = await fetchJson('/api/fund-browser?availability=all&search=017749.OF&limit=10')
if (fullDatabaseSearch.availability !== 'all' || fullDatabaseSearch.data?.[0]?.windCode !== '017749.OF') {
  throw new Error(`full database search must retain unevaluated funds: ${JSON.stringify(fullDatabaseSearch)}`)
}

const categories = await fetchJson('/api/fund-browser?peerGroup=%E6%8C%87%E6%95%B0-%E6%B2%AA%E6%B7%B1300&limit=30')
if (categories.source !== 'standardized_peer_group_universe') {
  throw new Error(`fund browser must disclose standardized peer-group source: ${JSON.stringify(categories)}`)
}
const snakeCaseCategory = await fetchJson('/api/fund-browser?peer_group=%E6%B7%B7%E5%90%88%E5%9E%8B-%E5%B9%B3%E8%A1%A1%E9%85%8D%E7%BD%AE&limit=5')
if (snakeCaseCategory.peerGroup !== '混合型-平衡配置' || snakeCaseCategory.data?.some((fund) => fund.researchProfile?.peerGroup !== '混合型-平衡配置')) {
  throw new Error(`snake_case peer-group adapter leaked across categories: ${JSON.stringify(snakeCaseCategory)}`)
}
const widthTag = categories.styleTagCatalog?.tags?.find((item) => item.value === '宽基')
if (!widthTag || widthTag.evidence_level !== 'classification' || widthTag.fund_count < 10) {
  throw new Error(`fund browser style tag catalog missing: ${JSON.stringify(categories.styleTagCatalog)}`)
}
const styleFiltered = await fetchJson('/api/fund-browser?peerGroup=%E6%8C%87%E6%95%B0-%E6%B2%AA%E6%B7%B1300&styleTags=%E5%AE%BD%E5%9F%BA,%E8%A2%AB%E5%8A%A8&styleMatch=all&limit=10')
if (!styleFiltered.data?.length || styleFiltered.selectionContext?.style_match !== 'all') {
  throw new Error(`fund browser style tag filter failed: ${JSON.stringify(styleFiltered)}`)
}
for (const fund of styleFiltered.data) {
  const rule = fund.selectionExplanation?.matched_rules?.find((item) => item.key === 'style_tags')
  if (rule?.operator !== 'all' || !rule.actual_text?.includes('宽基') || !rule.actual_text?.includes('被动')) {
    throw new Error(`fund browser style tag evidence missing: ${JSON.stringify(fund)}`)
  }
}
const holdingStyleFiltered = await fetchJson('/api/fund-browser?peerGroup=%E4%B8%BB%E5%8A%A8%E6%9D%83%E7%9B%8A-%E6%B2%AA%E6%B7%B1300%E5%8F%82%E8%80%83&styleTags=%E5%81%8F%E4%BB%B7%E5%80%BC&limit=10')
if (!holdingStyleFiltered.data?.length || holdingStyleFiltered.styleTagCatalog?.coverage?.holding_quantitative_fund_count < 3) {
  throw new Error(`real holding style tag coverage missing: ${JSON.stringify(holdingStyleFiltered.styleTagCatalog)}`)
}
for (const fund of holdingStyleFiltered.data) {
  const evidence = fund.researchProfile?.styleTagEvidence || []
  if (!evidence.some((item) => item.value === '偏价值' && item.evidenceLevel === 'strong')) {
    throw new Error(`holding style filter lacks strong evidence: ${JSON.stringify(fund)}`)
  }
}

const categoryCoverageResponse = await fetch(new URL('/api/funds/recommendation-categories?limit=100', process.env.BACKEND_API_URL || 'http://127.0.0.1:8005'), { cache: 'no-store' })
const categoryCoverage = await categoryCoverageResponse.json().catch(() => ({}))
if (!categoryCoverageResponse.ok) {
  throw new Error(`category coverage returned HTTP ${categoryCoverageResponse.status}: ${JSON.stringify(categoryCoverage)}`)
}
const moneyCoverage = categoryCoverage.categories?.find((item) => item.key === 'peer-money-cash-management')
if (!moneyCoverage || moneyCoverage.evaluated_fund_count < 40) {
  throw new Error(`money category must expose real evaluated coverage: ${JSON.stringify(moneyCoverage)}`)
}
if (moneyCoverage.evaluation_pending_count !== moneyCoverage.fund_count - moneyCoverage.evaluated_fund_count) {
  throw new Error(`category pending count must reconcile to classified minus evaluated: ${JSON.stringify(moneyCoverage)}`)
}
if (!moneyCoverage.evaluation_as_of_date) {
  throw new Error(`category evaluated coverage must disclose its data date: ${JSON.stringify(moneyCoverage)}`)
}
for (const fofCategoryKey of [
  'peer-fof-equity-allocation',
  'peer-fof-balanced-allocation',
  'peer-fof-bond-allocation',
]) {
  const category = categoryCoverage.categories?.find((item) => item.key === fofCategoryKey)
  if (!category || category.evaluated_fund_count < 5) {
    throw new Error(`FOF category must count metric-ready funds with sufficient public lookthrough: ${JSON.stringify(category)}`)
  }
}
const crossMarketCoverage = categoryCoverage.categories?.find((item) => item.name === '主动权益-沪港深')
if (!crossMarketCoverage || crossMarketCoverage.evaluated_fund_count < 5) {
  throw new Error(`cross-market active equity must use the supported active-equity evaluation method: ${JSON.stringify(crossMarketCoverage)}`)
}
const browserCoreCategories = [
  '指数-沪深300',
  '指数-中证A500',
  '指数-中证500',
  '主动权益-沪深300参考',
  '混合型-偏股配置',
  '固收-中证全债参考',
  '货币-现金管理',
  '主动权益-行业/消费主题',
  '指数增强-沪深300',
  '指数-创业板指',
]
for (const categoryName of browserCoreCategories) {
  if (!categoryPresets.includes(`category: '${categoryName}'`)) {
    throw new Error(`browser core category missing from quick presets: ${categoryName}`)
  }
  const category = categoryCoverage.categories?.find((item) => item.name === categoryName)
  if (!category || category.evaluated_fund_count < 10) {
    throw new Error(`browser core category must retain at least ten evaluated funds: ${JSON.stringify(category)}`)
  }
}
const bondCoverage = categoryCoverage.categories?.filter((item) => item.contract_dimensions)
if (!Array.isArray(bondCoverage) || bondCoverage.length < 20) {
  throw new Error(`bond browser must expose contract dimensions: ${JSON.stringify(bondCoverage)}`)
}
const targetBondCategory = bondCoverage.find((item) =>
  item.contract_dimensions?.base_index === 'composite'
  && item.contract_dimensions?.price_return === 'full_price'
  && item.contract_dimensions?.tenor === '1_3y'
)
if (!targetBondCategory || !targetBondCategory.asset_class || !targetBondCategory.benchmark_name || !targetBondCategory.strategy_family_name) {
  throw new Error(`bond contract category metadata missing: ${JSON.stringify(targetBondCategory)}`)
}
const duplicateBondCategory = bondCoverage.find((item) =>
  item.id !== targetBondCategory.id
  && item.contract_dimensions?.base_index === 'composite'
  && item.contract_dimensions?.price_return === 'full_price'
  && item.contract_dimensions?.tenor === '1_3y'
)
if (duplicateBondCategory) {
  throw new Error(`bond contract dimensions must locate one peer group: ${JSON.stringify([targetBondCategory, duplicateBondCategory])}`)
}
const bondFunds = await fetchJson(`/api/fund-browser?peerGroup=${encodeURIComponent(targetBondCategory.name)}&availability=classified&limit=10`)
if (!Array.isArray(bondFunds.data) || bondFunds.data.length < 2) {
  throw new Error(`bond contract browser returned too few funds: ${JSON.stringify(bondFunds)}`)
}
if (bondFunds.data.some((fund) => fund.researchProfile?.peerGroupId !== targetBondCategory.id)) {
  throw new Error(`cross-contract bond fund leaked into browser: ${JSON.stringify(bondFunds.data)}`)
}
if (!Array.isArray(categories.data) || categories.data.length < 2) {
  throw new Error(`expected at least two HS300 peers: ${JSON.stringify(categories)}`)
}
for (const fund of categories.data) {
  if (fund.researchProfile?.peerGroup !== '指数-沪深300' || fund.researchProfile?.peerGroupId !== 'peer-index-hs300') {
    throw new Error(`cross-category fund leaked into HS300 browser: ${JSON.stringify(fund)}`)
  }
}

const multiPeriod = await fetchJson('/api/fund-browser?peerGroup=%E6%8C%87%E6%95%B0-%E6%B2%AA%E6%B7%B1300&return6mMin=0&return1yMin=0&return3yMin=0&sortBy=multi_period&limit=10')
if (!Array.isArray(multiPeriod.data) || multiPeriod.data.length < 3) {
  throw new Error(`multi-period fund browser returned too few complete peers: ${JSON.stringify(multiPeriod)}`)
}
if (multiPeriod.selectionContext?.sort_label !== '多周期同类领先' || multiPeriod.selectionContext?.rules?.length !== 4) {
  throw new Error(`fund browser selection context missing: ${JSON.stringify(multiPeriod.selectionContext)}`)
}
for (const fund of multiPeriod.data) {
  const explanation = fund.selectionExplanation
  if (explanation?.status !== 'matched' || explanation.matched_rules?.length !== 4 || !explanation.sort_reason?.includes('多周期同类位置')) {
    throw new Error(`fund selection explanation missing for ${fund.windCode}: ${JSON.stringify(explanation)}`)
  }
}
for (const fund of multiPeriod.data) {
  for (const window of ['6m', '1y', '3y']) {
    const metric = fund.peerReturnMetrics?.[window]
    if (metric?.value == null || metric?.percentile == null || metric?.rank == null || metric?.peer_count == null) {
      throw new Error(`multi-period peer evidence missing for ${fund.windCode} ${window}: ${JSON.stringify(fund)}`)
    }
  }
}

const moneyFunds = await fetchJson('/api/fund-browser?peerGroup=%E8%B4%A7%E5%B8%81-%E7%8E%B0%E9%87%91%E7%AE%A1%E7%90%86&availability=evaluated&limit=1')
const searchableMoneyFund = moneyFunds.data?.[0]?.windCode
if (!searchableMoneyFund) {
  throw new Error(`money-market peer group must expose an evaluated fund: ${JSON.stringify(moneyFunds)}`)
}
const search = await fetchJson(`/api/fund-browser?peerGroup=%E8%B4%A7%E5%B8%81-%E7%8E%B0%E9%87%91%E7%AE%A1%E7%90%86&search=${encodeURIComponent(searchableMoneyFund)}&limit=30`)
if (search.pagination?.total !== 1 || search.data?.[0]?.windCode !== searchableMoneyFund) {
  throw new Error(`full peer-group keyword search failed: ${JSON.stringify(search)}`)
}
if (search.data[0].researchProfile?.peerGroupId !== 'peer-money-cash-management') {
  throw new Error(`money-market peer-group identity missing: ${JSON.stringify(search.data[0])}`)
}

console.log('OK fund browser filters, searches, and compares only within standardized peer groups')
