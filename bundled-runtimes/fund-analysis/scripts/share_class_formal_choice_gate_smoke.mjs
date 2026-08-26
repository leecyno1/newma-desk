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

const prePurchaseLib = read('lib/pre-purchase-report.ts')
const prePurchaseRoute = read('app/api/funds/[id]/pre-purchase-report/route.ts')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

assertIncludes(prePurchaseLib, 'formalChoiceReady: boolean', 'share-class decision exposes formal readiness')
assertIncludes(prePurchaseLib, 'const hasCompleteTransactionFeeRates = purchaseFeeRate !== null && redemptionFeeRate !== null && salesServiceFeeRate !== null', 'fee completeness includes sales service fee')
assertIncludes(prePurchaseLib, 'const formalChoiceReady = Boolean(', 'share-class decision computes formal readiness')
assertIncludes(prePurchaseLib, "recommended.executionAmountGate?.status === 'pass'", 'share-class formal choice requires executable amount gate')
assertIncludes(prePurchaseLib, 'costMissingCount === 0', 'share-class formal choice requires all cost gaps cleared')
assertIncludes(prePurchaseLib, "recommendedCode: formalChoiceReady ? recommended?.windCode || '' : ''", 'share-class decision withholds recommended code before formal readiness')
assertIncludes(prePurchaseLib, '份额金额门禁或成本证据未清零前，不输出正式推荐份额代码', 'share-class report explains no recommendation before evidence clears')
assertIncludes(prePurchaseLib, '暂不输出推荐代码', 'share-class warning blocks recommendation-like copy')
assertIncludes(prePurchaseRoute, 'shareClassFormalChoiceReady', 'pre-purchase metadata stores share-class formal readiness')
assertIncludes(acceptance, 'scripts/share_class_formal_choice_gate_smoke.mjs', 'acceptance smoke includes share-class formal choice gate')

console.log('OK share-class choice withholds recommendation until amount and cost evidence are complete')
