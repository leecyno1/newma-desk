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

const researchReviewRoute = read('app/api/funds/[id]/research-review-report/route.ts')
const reportsRoute = read('app/api/reports/route.ts')
const reportDetailRoute = read('app/api/reports/[id]/route.ts')
const reportsPage = read('app/(dashboard)/reports/page.tsx')
const reportDetailPage = read('app/(dashboard)/reports/[id]/page.tsx')
const buyBeforeQueue = read('lib/report-buy-before-evidence-queue.ts')

assertIncludes(researchReviewRoute, 'holdingExposureDecision: result.report.holdingExposureDecision', 'saved report carries holding exposure decision')
assertIncludes(researchReviewRoute, 'holdingExposureLabel', 'saved report generation params carry holding exposure label')
assertIncludes(researchReviewRoute, 'holdingExposureScore', 'saved report generation params carry holding exposure score')

assertIncludes(reportsRoute, 'holdingExposureDecision', 'reports list extracts holding exposure')
assertIncludes(reportsRoute, 'holdingExposureLabel', 'reports list decision summary carries exposure label')
assertIncludes(reportsRoute, 'holdingExposureAction', 'reports list decision summary carries exposure action')
assertIncludes(reportsRoute, 'reportPurchasePlanFromSources', 'reports list extracts saved purchase-plan context')
assertIncludes(reportsRoute, 'getSalesRuleGapsForCodes(planCodes, planCodes.length, { purchasePlan, plannedAmount })', 'reports list sales-rule gate scans by saved purchase plan and planned amount')
assertIncludes(reportsRoute, 'salesRulesHrefForCodes(report.comparisonCodes, purchasePlan, plannedAmount)', 'reports list comparison sales-rule href carries purchase plan and planned amount')

assertIncludes(reportDetailRoute, 'holdingExposureDecision', 'report detail extracts holding exposure')
assertIncludes(reportDetailRoute, '持仓暴露研究判断', 'report detail evidence summary labels holding exposure')
assertIncludes(reportDetailRoute, '持仓暴露反转条件', 'report detail evidence summary carries reverse triggers')
assertIncludes(reportDetailRoute, 'reportWinLossLines', 'report detail extracts saved win/loss lines')
assertIncludes(reportDetailRoute, 'alternativeWinLossLines', 'report detail extracts pre-purchase win/loss lines')
assertIncludes(reportDetailRoute, 'decisionWinLossLines', 'report detail extracts comparison win/loss lines')
assertIncludes(reportDetailRoute, 'salesRulesHrefForCodes(codes, purchasePlan, plannedAmount)', 'report detail sales-rule href carries saved purchase plan and planned amount')

assertIncludes(reportsPage, 'report-list-holding-exposure-card', 'reports list renders holding exposure card')
assertIncludes(reportsPage, '持仓暴露：{report.decisionSummary.holdingExposureLabel}', 'reports list exposure label render')
assertIncludes(reportsPage, '研究动作：{report.decisionSummary.holdingExposureAction}', 'reports list exposure action render')
assertIncludes(reportsPage, 'reportPurchasePlan', 'reports list derives purchase-plan context')
assertIncludes(reportsPage, 'reportPlannedAmount', 'reports list derives saved planned amount context')
assertIncludes(reportsPage, 'appendPurchaseContext', 'reports list uses purchase context helper')
assertIncludes(reportsPage, "params.set('plannedAmount', String(plannedAmount))", 'reports list links carry planned amount')
assertIncludes(reportsPage, "params.set(purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(plannedAmount))", 'reports list links carry amount alias')
assertIncludes(reportsPage, "appendPurchaseContext(`/analysis/comparison?codes=${encodeURIComponent(relatedCodes.join(','))}&autoReplay=1`, report)", 'reports list comparison rerun carries purchase plan and amount')
assertIncludes(reportsPage, "appendPurchaseContext(`/funds/${encodeURIComponent(report.targetId)}`, report)", 'reports list fund detail action carries purchase plan and amount')
assertIncludes(reportsPage, "appendPurchaseContext(`/pools?poolId=${encodeURIComponent(report.targetId)}&status=candidate`, report)", 'reports list pool action carries purchase plan and amount')
assertIncludes(reportDetailPage, 'report-evidence-summary', 'report detail renders evidence summary including exposure')
assertIncludes(reportDetailPage, 'report-detail-win-loss-lines', 'report detail renders saved win/loss lines')
assertIncludes(reportDetailPage, '横评胜负线留痕', 'report detail labels win/loss lines')
assertIncludes(reportDetailPage, '费用口径', 'report detail win/loss lines preserve fee threshold labels')
assertIncludes(buyBeforeQueue, 'plannedAmount?: number | null', 'buy-before evidence queue accepts planned amount')
assertIncludes(buyBeforeQueue, "if (plannedAmount) params.set('plannedAmount', String(plannedAmount))", 'buy-before evidence queue links carry planned amount')
assertIncludes(buyBeforeQueue, 'const plannedAmount = reportPlannedAmount(report)', 'buy-before evidence queue preserves report planned amount per scenario group')

console.log('OK report library preserves and displays holding exposure and win/loss decision evidence')
