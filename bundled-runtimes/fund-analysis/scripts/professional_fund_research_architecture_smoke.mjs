import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const root = process.cwd()

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) throw new Error(`Missing required file: ${relativePath}`)
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) throw new Error(`${label} missing: ${expected}`)
}

function assertNotIncludes(content, forbidden, label) {
  if (content.includes(forbidden)) throw new Error(`${label} must not include: ${forbidden}`)
}

const architecture = read('docs/architecture/professional-fund-research-architecture.md')
const simpleProductScope = read('docs/adr/0002-simple-fund-selection-product-scope.md')
const modules = read('lib/research-platform/core-modules.ts')
const dashboardLayout = read('app/(dashboard)/layout.tsx')
const appNavigation = read('components/navigation/AppNavigation.tsx')
const comparisonPage = read('app/(dashboard)/compare/SimpleComparisonClient.tsx')
const investorSelectionPage = read('app/(dashboard)/investor-selection/page.tsx')
const salesRulesPage = read('app/(dashboard)/sales-rules/page.tsx')
const alertsPage = read('app/(dashboard)/alerts/page.tsx')
const poolsPage = read('app/(dashboard)/pools/page.tsx')
const rankingsPage = read('app/(dashboard)/rankings/page.tsx')
const legacyRedirect = read('app/(dashboard)/legacyResearchRedirect.ts')
const routes = read('lib/research-platform/routes.ts')

for (const phrase of [
  '不覆盖交易、购买或风控',
  '全市场研究库',
  '同类横评',
  '持仓画像',
  '经理与公司研究',
  '研究报告生命周期',
  'OpenBB',
  'QuantStats',
  'FinGPT',
]) {
  assertIncludes(architecture, phrase, `professional architecture documents ${phrase}`)
}

for (const moduleName of [
  'research-universe',
  'fund-profile',
  'peer-comparison',
  'holding-exposure',
  'manager-and-company-research',
  'research-report-lifecycle',
  'evidence-ledger',
  'data-ingestion',
]) {
  assertIncludes(modules, moduleName, `core module registry includes ${moduleName}`)
}

for (const mergedRoute of [
  '/investor-selection',
  '/sales-rules',
  '/alerts',
  '/pools',
  '/rankings',
]) {
  assertIncludes(modules, mergedRoute, `core module registry declares merged route ${mergedRoute}`)
}

for (const obsoleteNav of ['投资者选基', '销售规则', '基金池', '基金复查队列', '基金排行榜', '尽调工作台', '监控复核']) {
  assertNotIncludes(appNavigation, obsoleteNav, 'primary navigation removes professional workflow label')
}

for (const activeNav of ['找基金', '调研库', 'AI 分析', '基金推荐']) {
  assertIncludes(appNavigation, activeNav, `primary navigation keeps simple product label ${activeNav}`)
}
for (const route of ['/discover', '/research', '/analysis', '/recommendations']) {
  assertIncludes(appNavigation, route, `primary navigation exposes ${route}`)
}
assertIncludes(dashboardLayout, 'FundWorkspaceShell', 'dashboard uses the shared workspace shell')
assertIncludes(simpleProductScope, '必须先确认基金类别，再进行同类比较', 'simple product scope preserves peer comparison boundary')
assertIncludes(comparisonPage, 'peerGroupIds.length === 1', 'simple comparison enforces one professional peer group')
assertIncludes(comparisonPage, '横向比较结论', 'simple comparison summarizes research priority for ordinary users')
assertIncludes(comparisonPage, '现场综合分析', 'simple comparison links the leading candidate to on-demand analysis')
assertIncludes(comparisonPage, '七日年化较高', 'money-market comparison uses category-specific income evidence')
assertIncludes(comparisonPage, '不使用股票基金的 Sharpe 结论', 'money-market comparison rejects stock-fund comparison language')
assertIncludes(comparisonPage, '跟踪误差较小', 'index comparison uses tracking-quality evidence')
assertIncludes(comparisonPage, '指数基金优先比较跟踪质量、费率和规模', 'index comparison explains its category-specific method')
assertNotIncludes(comparisonPage, 'purchasePlan', 'simple comparison excludes purchase workflow state')

assertIncludes(legacyRedirect, 'redirect(mergedResearchRouteTarget(pathname))', 'legacy redirect helper centralizes page redirect')
assertIncludes(routes, 'mergedResearchRouteTarget', 'routes expose canonical merged page target')

for (const [content, route] of [
  [investorSelectionPage, '/investor-selection'],
  [salesRulesPage, '/sales-rules'],
  [alertsPage, '/alerts'],
  [poolsPage, '/pools'],
  [rankingsPage, '/rankings'],
]) {
  assertIncludes(content, 'redirectToMergedResearchRoute', `merged page uses centralized redirect for ${route}`)
  assertIncludes(content, route, `merged page declares legacy source route ${route}`)
}

console.log('OK professional fund research architecture removes redundant navigation and declares canonical modules')
