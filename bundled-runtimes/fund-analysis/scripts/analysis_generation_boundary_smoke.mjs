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

const route = read('app/api/analysis/generate/route.ts')
const analysisRoute = read('app/api/analysis/route.ts')
const analysisPage = read('app/(dashboard)/analysis/page.tsx')
const fundAnalysisPage = read('app/(dashboard)/analysis/fund/page.tsx')
const fundAnalysisClient = read('app/(dashboard)/analysis/fund/FundAnalysisClient.tsx')

assertIncludes(route, 'buyBeforeBoundary', 'analysis generation consumes score buy-before boundary')
assertIncludes(route, 'const scoreBoundary = scorePayload.buyBeforeBoundary', 'analysis generation reads score boundary')
assertIncludes(route, '评分边界：${scoreBoundary?.label', 'manager memo prints score boundary label')
assertIncludes(route, "scoreBoundary?.detail || '评分只用于研究排序", 'manager memo prints score boundary detail')
assertIncludes(route, '评分后仍需通过：', 'manager memo lists post-score gates')
assertIncludes(route, 'R1-R5 适当性', 'manager memo keeps suitability gate after scoring')
assertIncludes(route, '正式研究复核报告', 'manager memo keeps formal research report gate after scoring')
assertIncludes(route, "const purchasePlan = normalizePurchasePlan(body.purchasePlan)", 'analysis generation normalizes purchase plan once')
assertIncludes(route, "const plannedAmount = normalizePlannedAmount(body.plannedAmount, purchasePlan)", 'analysis generation normalizes planned amount once')
assertIncludes(route, "reportUrl.searchParams.set('purchase_plan', purchasePlan)", 'fund analysis forwards purchase plan to backend report generation')
assertIncludes(route, "reportUrl.searchParams.set('planned_amount', String(plannedAmount))", 'fund analysis forwards planned amount to backend report generation')
assertIncludes(fundAnalysisPage, 'initialPlannedAmount={initialPlannedAmount}', 'fund analysis page hydrates planned amount from URL')
assertIncludes(fundAnalysisClient, 'plannedAmount: currentPlannedAmount()', 'fund analysis request sends planned amount')
assertIncludes(fundAnalysisClient, '研究口径：', 'fund analysis page discloses planned amount execution context')
assertIncludes(analysisRoute, 'buildReportRiskLevelGatePolicy', 'analysis report list builds R1-R5 gate policy')
assertIncludes(analysisRoute, 'riskLevelGatePolicy,', 'analysis report list returns R1-R5 gate policy')
assertIncludes(analysisPage, 'analysis-report-risk-level-policy', 'analysis page shows R1-R5 gate policy badge')
assertIncludes(analysisPage, 'analysis-report-risk-level-policy-card', 'analysis page warns old R1-R5 gate policy')
assertIncludes(analysisPage, '不能证明已采用 30 天 R1-R5 来源背书', 'analysis page explains old R1-R5 policy boundary')

console.log('OK analysis generation carries score boundary, purchase plan, and planned amount into report generation')
