import { readFileSync } from 'node:fs'

const detail = readFileSync('app/(dashboard)/funds/[id]/SimpleFundDetailClient.tsx', 'utf8')
const attribution = readFileSync('app/(dashboard)/funds/[id]/FundAttributionEvidence.tsx', 'utf8')
const holdings = readFileSync('app/(dashboard)/funds/[id]/FundHoldingProfile.tsx', 'utf8')
const assetAllocation = readFileSync('app/(dashboard)/funds/[id]/FundAssetAllocationPanel.tsx', 'utf8')
const holderStructure = readFileSync('app/(dashboard)/funds/[id]/FundHolderStructurePanel.tsx', 'utf8')
const holdingChanges = readFileSync('app/(dashboard)/funds/[id]/FundHoldingChangesPanel.tsx', 'utf8')
const managerTenurePerformance = readFileSync('app/(dashboard)/funds/[id]/FundManagerTenurePerformancePanel.tsx', 'utf8')
const productProfile = readFileSync('app/(dashboard)/funds/[id]/FundProductProfilePanel.tsx', 'utf8')
const page = readFileSync('app/(dashboard)/funds/[id]/page.tsx', 'utf8')
const snapshot = readFileSync('backend/services/fund_research_snapshot_service.py', 'utf8')
const simpleFundView = readFileSync('lib/simple-fund-view.ts', 'utf8')
const marketEnvironment = readFileSync('lib/fund-market-environment.ts', 'utf8')

for (const required of [
  '亮点与风险证据',
  'detailHighlights',
  '只在同类有效样本充足',
  'evaluationWindows',
  'selectedWindowLabel',
  '当前查看 {selectedWindowLabel}',
  'benchmarkGrowth',
  'chartData.length ? (',
  '基金真实净值口径',
  '基础费率',
  'baseFeeRate',
  "metric.key === 'expense_ratio'",
  '管理费 + 托管费',
  '综合评价',
  '量化评价',
  '风格标签',
  '调研纪要',
  'Barra / Brinson',
  'assessmentSummary',
  '合同基准',
  '团队起点',
  '市场涨时跟得上，跌时守得住吗',
  '上涨捕获率',
  '下跌捕获率',
  '<MarketEnvironmentPanel',
  '评分历史',
  '证据覆盖',
  '不宜直接比较',
  "payload.status === 'unchanged'",
]) {
  if (!detail.includes(required)) throw new Error(`fund product detail missing: ${required}`)
}
for (const required of ['共同交易日的月末累计净值', 'upsideCapture', 'downsideCapture', 'upOutperformanceRate', 'downProtectionRate']) {
  if (!marketEnvironment.includes(required)) throw new Error(`fund market environment missing: ${required}`)
}

if (detail.includes('professionalScoreReady && chartData.length')) {
  throw new Error('NAV browser must not be blocked by professional score readiness')
}
if (!page.includes('benchmarkNav: numberOrNull(point.benchmark_nav)')) {
  throw new Error('fund detail page must load benchmark NAV')
}
for (const required of [
  'const accumNav = numberOrNull(point.accum_nav ?? point.adj_nav)',
  'const accumNavCount = rawNavPoints.filter',
  'const useAccumNav = accumNavCount >= 2 && accumNavCount >= unitNavCount',
  "navBasis: useAccumNav ? 'accum_nav'",
  'nav: fund.nav ?? latestRawNavPoint?.unitNav',
]) {
  if (!page.includes(required)) throw new Error(`fund detail page missing NAV basis rule: ${required}`)
}
for (const required of ['evidence_coverage', 'comparison_status', 'raw_rank_change', 'drivers']) {
  if (!page.includes(required)) throw new Error(`fund detail page missing evaluation-history change evidence: ${required}`)
}
for (const required of [
  'buildChartSeries',
  "{ value: '1y', label: '近 1 年', observations: 252 }",
  'selectedRolling.window_start_date',
  'chartMatchesEvaluation',
  'nav.slice(-observations)',
  '累计净值口径',
  '基准共同日期',
  'benchmarkCoverage',
  '与评价窗口一致',
  '默认使用累计净值处理分红和份额折算',
]) {
  if (!detail.includes(required)) throw new Error(`fund detail chart missing audit evidence: ${required}`)
}
if (!page.includes('start_date: dateYearsAgo(4)')) {
  throw new Error('fund detail must fetch enough NAV history to cover the stored 3y evaluation window')
}
for (const required of [
  '现场分析收益来源',
  'A 股 Barra 描述子',
  '商业 Barra 因子收益和协方差矩阵尚未接入',
  'descriptor_model_ready',
  '最近分析记录',
  '/history?limit=6',
  '净值行为补充',
  '/api/attribution/fund/',
  "brinson?.status === 'insufficient_evidence'",
]) {
  if (!attribution.includes(required)) throw new Error(`fund attribution evidence missing: ${required}`)
}
if (!detail.includes('<FundAttributionEvidence')) {
  throw new Error('fund detail must embed on-demand attribution evidence')
}
for (const required of ['现任经理任职期表现', '完整任期', '本地可见期', '部分覆盖·不排名', '同区间同类位置', '实际净值起点']) {
  if (!managerTenurePerformance.includes(required)) throw new Error(`fund manager tenure performance missing: ${required}`)
}
if (!detail.includes('<FundManagerTenurePerformancePanel')) {
  throw new Error('fund detail must show current-manager tenure performance')
}
for (const required of ['snapshotPayload.manager_tenure_performance', 'coverage_ratio', 'peer_ranking', 'managerTenurePerformance']) {
  if (!page.includes(required)) throw new Error(`fund detail page missing manager tenure mapping: ${required}`)
}
for (const required of ['产品介绍与费率', '投资目标', '投资理念', '投资范围', '投资策略', '风险收益特征', '认购费率', '申购费率', '赎回费率', '查看产品档案', '查看费率原文']) {
  if (!productProfile.includes(required)) throw new Error(`fund product profile missing: ${required}`)
}
if (!detail.includes('<FundProductProfilePanel')) {
  throw new Error('fund detail must show the product introduction and fee profile')
}
for (const required of ['snapshotFundPayload.product_profile', 'normalizeProductProfile', 'subscription_fee_rules', 'redemption_fee_rules']) {
  if (!page.includes(required)) throw new Error(`fund detail page missing product profile mapping: ${required}`)
}
for (const required of ['最新公开持仓', '占股票市值', '不能解读为占基金净值', '行业分布']) {
  if (!holdings.includes(required)) throw new Error(`fund holding profile missing: ${required}`)
}
if (!detail.includes('<FundHoldingProfile')) {
  throw new Error('fund detail must embed the latest disclosed holdings profile')
}
for (const required of ['资产配置', '基金定期报告披露', '股票', '债券', '现金', '净资产', '查看原始披露']) {
  if (!assetAllocation.includes(required)) throw new Error(`fund asset allocation missing: ${required}`)
}
if (!detail.includes('<FundAssetAllocationPanel')) {
  throw new Error('fund detail must show asset allocation before disclosed holdings')
}
if (detail.indexOf('<FundAssetAllocationPanel') > detail.indexOf('<FundHoldingProfile')) {
  throw new Error('asset allocation must appear before the latest disclosed holdings')
}
for (const required of ['/asset-allocation?limit=24', 'stock_ratio', 'bond_ratio', 'cash_ratio', 'net_asset_yi']) {
  if (!page.includes(required)) throw new Error(`fund detail page missing asset allocation data: ${required}`)
}
for (const required of ['持有人结构', '天天基金 / 东方财富公开披露', '机构持有', '个人持有', '内部持有比例', '不等于员工自购', '不直接解释为主动申购或赎回', '查看原始披露']) {
  if (!holderStructure.includes(required)) throw new Error(`fund holder structure missing: ${required}`)
}
if (!page.includes('/holder-structure?limit=10')) {
  throw new Error('fund detail page must load holder structure history')
}
if (!detail.includes('<FundHolderStructurePanel')) {
  throw new Error('fund detail must show holder structure')
}
if (detail.indexOf('<FundHolderStructurePanel') < detail.indexOf('<FundAssetAllocationPanel') || detail.indexOf('<FundHolderStructurePanel') > detail.indexOf('<FundHoldingProfile')) {
  throw new Error('holder structure must appear after asset allocation and before disclosed holdings')
}
if (!page.includes('/holdings')) {
  throw new Error('fund detail page must load the latest disclosed holdings')
}
for (const required of ['持仓变化', '权重上升最多', '权重下降最多', '新进前十大', '退出前十大', '前三大集中度', '前十大集中度', '行业配置变化', '集中度趋势', '不能直接等同于主动买卖']) {
  if (!holdingChanges.includes(required)) throw new Error(`fund holding changes missing: ${required}`)
}
if (!page.includes('/holding-changes')) {
  throw new Error('fund detail page must load holding changes')
}
if (!detail.includes('<FundHoldingChangesPanel')) {
  throw new Error('fund detail must show disclosed holding changes')
}
for (const required of ['universe.get("company")', 'universe.get("management_fee")', 'universe.get("custodian_fee")', '"contract_benchmark"']) {
  if (!snapshot.includes(required)) throw new Error(`fund snapshot missing base fact: ${required}`)
}
if (!snapshot.includes('"product_profile": product_profile')) {
  throw new Error('fund snapshot must expose the locally stored product profile')
}
for (const required of ['EVALUATION_WINDOWS = ("6m", "1y", "3y")', '"evaluation_windows": evaluation_windows']) {
  if (!snapshot.includes(required)) throw new Error(`fund snapshot missing multi-window evaluation: ${required}`)
}
for (const required of ['"window_start_date"', '"window_end_date"', '"actual_observations"', '"benchmark_observations"']) {
  if (!snapshot.includes(required)) throw new Error(`fund snapshot missing rolling window evidence: ${required}`)
}
for (const required of ['"assessment_summary": assessment_summary', 'def _assessment_summary(', 'def _assessment_attribution_summary(']) {
  if (!snapshot.includes(required)) throw new Error(`fund snapshot missing unified assessment: ${required}`)
}
for (const required of ['"detail_highlights": detail_highlights', 'def _detail_highlights(', '不代表完整持有成本', '历史回放，不是未来预测']) {
  if (!snapshot.includes(required)) throw new Error(`fund snapshot missing detail highlight evidence: ${required}`)
}
for (const required of ['"plain_language_brief": plain_language_brief', 'def _plain_language_brief(', '一分钟看懂这只基金', '复制摘要']) {
  if (!`${snapshot}\n${detail}`.includes(required)) throw new Error(`fund detail missing plain-language brief: ${required}`)
}
if (detail.includes('综合费率') || snapshot.includes('综合费率')) {
  throw new Error('fund detail must call declared management/custodian sum 基础费率, not 综合费率')
}
if (!page.includes('include_attribution=true&live_attribution=false')) {
  throw new Error('fund detail must reuse saved attribution without triggering live calculation')
}
if (!simpleFundView.includes('rolling.total_return')) {
  throw new Error('plain-language period return must read total return')
}
if (simpleFundView.includes('rolling.annualized_return') && simpleFundView.indexOf('rolling.total_return') > simpleFundView.indexOf('rolling.annualized_return')) {
  throw new Error('plain-language period return must prefer total return over annualized return')
}

console.log('OK fund product detail prioritizes browsable facts, benchmark comparison, and plain-language evidence')
