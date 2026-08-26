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

const actionBar = read('components/analysis/ReportActionBar.tsx')
const fundAnalysis = read('app/(dashboard)/analysis/fund/FundAnalysisClient.tsx')
const managerAnalysis = read('app/(dashboard)/analysis/manager/page.tsx')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

assertIncludes(actionBar, 'type PurchasePlan = \'lump_sum\' | \'sip\'', 'report action bar has purchase plan type')
assertIncludes(actionBar, 'type ActionContext', 'report action bar accepts buy-before action context')
assertIncludes(actionBar, 'function purchaseContextParams', 'report action bar centralizes purchase context params')
assertIncludes(actionBar, "params.set('plannedAmount', normalizedAmount)", 'report action bar preserves planned amount')
assertIncludes(actionBar, "params.set(purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', normalizedAmount)", 'report action bar preserves plan-specific amount alias')
assertIncludes(actionBar, 'safeReturnPath(context.returnTo)', 'report action bar sanitizes return path')
assertIncludes(actionBar, 'appendSearchParams(`/sales-rules?codes=${encodeURIComponent(safeTargetId)}`, contextParams)', 'report action bar sales-rule link carries context')
assertIncludes(actionBar, 'appendSearchParams(`/analysis/comparison?codes=${encodeURIComponent(safeTargetId)}&autoReplay=1`, contextParams)', 'report action bar comparison link carries context and auto replay')
assertIncludes(actionBar, 'appendSearchParams(`/reports/${reportId}`, contextParams)', 'report action bar report link carries context')
assertIncludes(actionBar, '按当前计划金额补费率、申赎、风险等级', 'report action bar explains amount-aware rules')
assertIncludes(fundAnalysis, 'const currentAnalysisReturnHref = `/analysis/fund?${new URLSearchParams', 'fund analysis builds return-aware action context')
assertIncludes(fundAnalysis, 'purchasePlan={purchasePlan}', 'fund analysis passes purchase plan to action bar')
assertIncludes(fundAnalysis, 'plannedAmount={currentPlannedAmount()}', 'fund analysis passes planned amount to action bar')
assertIncludes(fundAnalysis, 'returnTo={currentAnalysisReturnHref}', 'fund analysis passes safe return context to action bar')
assertIncludes(managerAnalysis, 'const currentPlannedAmount = Number(normalizePlannedAmountInput(plannedAmount, purchasePlan))', 'manager analysis normalizes action bar amount')
assertIncludes(managerAnalysis, 'purchasePlan={purchasePlan}', 'manager analysis passes purchase plan to action bar')
assertIncludes(managerAnalysis, 'plannedAmount={currentPlannedAmount}', 'manager analysis passes planned amount to action bar')
assertIncludes(managerAnalysis, 'returnTo={sourceReturnHref}', 'manager analysis passes return context to action bar')
assertIncludes(acceptance, 'scripts/report_action_bar_context_smoke.mjs', 'fund research acceptance includes report action bar context smoke')

console.log('OK report action bar preserves buy-before context in follow-up actions')
