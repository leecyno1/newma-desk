import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) {
    throw new Error(`Missing required file: ${relativePath}`)
  }
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) {
    throw new Error(`${label} missing text: ${expected}`)
  }
}

const reportsApi = read('app/api/reports/route.ts')
const reportsPage = read('app/(dashboard)/reports/page.tsx')

assertIncludes(reportsApi, "searchParams.get('buyBeforeGate')", 'reports API accepts buy-before gate filter')
assertIncludes(reportsApi, 'includeBuyBeforeFacets', 'reports API accepts buy-before facets flag')
assertIncludes(reportsApi, 'function buyBeforeGateFacets', 'reports API builds buy-before facets before pagination')
assertIncludes(reportsApi, 'buyBeforeEvidenceQueue: buildBuyBeforeEvidenceQueue(reportsForBuyBeforeFacets || reports)', 'reports API returns buy-before evidence queue facets after current gate enrichment')
assertIncludes(reportsApi, "'blocked_by_hard_gate', 'verify_first', 'research_ready', 'missing'", 'reports API recognizes all buy-before filter states')
assertIncludes(reportsApi, 'needsBuyBeforeGateFiltering', 'reports API forces local filtering for buy-before gate')
assertIncludes(reportsApi, 'report.decisionSummary.buyBeforeGateStatus', 'reports API filters by normalized gate status')
assertIncludes(reportsApi, 'buildReportRiskLevelGatePolicy', 'reports API builds generation-time R1-R5 gate policy')
assertIncludes(reportsApi, 'riskLevelGatePolicy,', 'reports API exposes generation-time R1-R5 gate policy')

assertIncludes(reportsPage, 'const buyBeforeGateOptions', 'reports page defines buy-before gate filter options')
assertIncludes(reportsPage, "initialUrlFilter(buyBeforeGateOptions, 'buyBeforeGate')", 'reports page stores buy-before gate filter state from URL')
assertIncludes(reportsPage, 'syncUrlFilters({ buyBeforeGate: option.value })', 'reports page syncs buy-before gate filter to URL')
assertIncludes(reportsPage, 'setBuyBeforeGateFacets(data.facets?.buyBeforeGate || null)', 'reports page reads buy-before facets')
assertIncludes(reportsPage, 'setBuyBeforeEvidenceQueueFacet(data.facets?.buyBeforeEvidenceQueue || null)', 'reports page reads buy-before evidence queue facets')
assertIncludes(reportsPage, 'buyBeforeGate,', 'reports page sends buy-before gate filter to API')
assertIncludes(reportsPage, "includeBuyBeforeFacets: '1'", 'reports page requests buy-before facets')
assertIncludes(reportsPage, 'report-buy-before-gate-filter', 'reports page renders buy-before gate filter block')
assertIncludes(reportsPage, '当前筛选结果', 'reports page labels buy-before counts as full filtered result')
assertIncludes(reportsPage, '硬阻断报告不能进入正式研究结论', 'reports page preserves hard-gate warning copy')
assertIncludes(reportsPage, 'riskLevelGatePolicy?.requiresRegeneration', 'reports page sends old R1-R5 policy reports to rerun queue')
assertIncludes(reportsPage, 'function riskLevelSourceQueueHref', 'reports page centralizes R1-R5 source queue href')
assertIncludes(reportsPage, 'actionHref: riskLevelSourceQueueHref(report)', 'reports page old R1-R5 rerun action opens source queue')
assertIncludes(reportsPage, 'report-list-risk-level-policy-card', 'reports page renders old R1-R5 policy card')
assertIncludes(reportsPage, 'R1-R5：{report.riskLevelGatePolicy.label}', 'reports page badges generation-time R1-R5 policy')
assertIncludes(reportsPage, '不能证明已采用 30 天来源背书', 'reports page explains old R1-R5 gate policy boundary')

console.log('OK report library supports buy-before gate filtering')
