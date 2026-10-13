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

function assertNotIncludes(content, unexpected, label) {
  if (content.includes(unexpected)) {
    throw new Error(`${label} should not include text: ${unexpected}`)
  }
}

const managerDetail = read('app/(dashboard)/managers/[id]/page.tsx')
const managerList = read('app/(dashboard)/managers/page.tsx')
const managerAnalysis = read('app/(dashboard)/analysis/manager/page.tsx')
const analysisGenerateRoute = read('app/api/analysis/generate/route.ts')

// 98790a6 把经理页收敛为纯研究视角：经理列表/详情不再有购买前证据卡与购买队列，
// 购买路径与销售规则门禁只在基金维度提供（由 fund_detail_purchase、sales_service_fee、
// share_class、fund_pool_sales_rule_gate、investor_sales_rule_gate 等 smoke 守护）。
// 这里反向守护：经理页面不得重新引入购买/申购入口，防止在经理维度绕过逐基金门禁。
for (const [label, content] of [
  ['manager detail page', managerDetail],
  ['manager list page', managerList],
]) {
  for (const forbidden of ['申购', '购买', '买入', '下单', 'plannedAmount', 'purchasePlan']) {
    assertNotIncludes(content, forbidden, `${label} must stay research-only without purchase paths`)
  }
}

// 经理维度的补证引导必须落到逐基金材料核验页：详情页以名下基金 codes 批量
// 跳转材料核验，而不是在经理维度给结论。
assertIncludes(managerDetail, 'const managerMaterialEvidenceHref = materialEvidenceHref(evidenceQuery)', 'manager detail routes evidence gaps to fund-level material coverage')
assertIncludes(managerDetail, 'codes: managerFundCodes.join(\',\')', 'manager detail carries managed fund codes into material coverage')

// 经理维度的购买上下文只在按需生成的经理分析报告链路里出现，且完整保留
// 计划金额口径与安全回跳，供研究口径披露与后续逐基金核验跳转。
assertIncludes(managerAnalysis, '研究方式口径', 'manager analysis page exposes research-plan scope')
assertIncludes(managerAnalysis, "params.get('purchasePlan')", 'manager analysis page hydrates purchase plan from URL')
assertIncludes(managerAnalysis, "params.get('plannedAmount')", 'manager analysis page hydrates planned amount from URL')
assertIncludes(managerAnalysis, "params.get(nextPurchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount')", 'manager analysis page hydrates amount alias from URL')
assertIncludes(managerAnalysis, "setSourceReturnHref(safeReturnPath(params.get('returnTo')))", 'manager analysis page hydrates safe return path from URL')
assertIncludes(managerAnalysis, 'purchasePlan,', 'manager analysis request sends purchase plan')
assertIncludes(managerAnalysis, 'plannedAmount: Number(normalizePlannedAmountInput(plannedAmount, purchasePlan))', 'manager analysis request sends planned amount')
assertIncludes(managerAnalysis, 'returnTo: sourceReturnHref', 'manager analysis request sends return path')
assertIncludes(managerAnalysis, 'data-testid="manager-analysis-return-link"', 'manager analysis exposes return link for browser verification')
assertIncludes(managerAnalysis, 'appendReturnTo(`/reports/${reportId}`, sourceReturnHref)', 'manager analysis report detail link preserves source return path')

assertIncludes(analysisGenerateRoute, 'normalizePurchasePlan(body.purchasePlan)', 'analysis generate normalizes purchase plan')
assertIncludes(analysisGenerateRoute, 'safeReturnPath(body.returnTo)', 'analysis generate sanitizes manager report return path')
assertIncludes(analysisGenerateRoute, 'normalizePlannedAmount(body.plannedAmount, purchasePlan)', 'analysis generate normalizes planned amount')
assertIncludes(analysisGenerateRoute, 'purchaseContextParams(purchasePlan, plannedAmount)', 'manager memo centralizes purchase amount query')
assertIncludes(analysisGenerateRoute, 'buildManagerMemo(managerPayload, scorePayload, request.url, purchasePlan, plannedAmount, safeReturnPath(body.returnTo))', 'analysis generate manager memo receives purchase plan, amount, and return path')
assertIncludes(analysisGenerateRoute, '研究方式口径：${purchasePlanLabel(purchasePlan)}', 'manager memo discloses research-plan scope')
assertIncludes(analysisGenerateRoute, '计划金额：${plannedAmount.toLocaleString(\'zh-CN\')} 元', 'manager memo discloses planned amount scope')
assertIncludes(analysisGenerateRoute, '&${purchaseContextQuery}&autoReplay=1', 'manager memo comparison link preserves purchase plan and amount')
assertIncludes(analysisGenerateRoute, 'new URLSearchParams(purchaseContextQuery)', 'manager memo sales-rule link preserves purchase plan and amount')
assertIncludes(analysisGenerateRoute, 'appendReturnTo(`/analysis/comparison?codes=', 'manager memo comparison link preserves manager return path')
assertIncludes(analysisGenerateRoute, 'appendReturnTo(materialEvidenceHref(salesRuleParams), managerHref)', 'manager memo sales-rule link preserves manager return path')

console.log('OK manager pages stay research-only; manager memo keeps purchase-plan scope for fund-level verification')
