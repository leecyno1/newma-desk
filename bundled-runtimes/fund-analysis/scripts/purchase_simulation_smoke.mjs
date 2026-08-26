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
    throw new Error(`${label} should not include stale text: ${unexpected}`)
  }
}

const navRoute = read('app/api/funds/nav/route.ts')
assertIncludes(navRoute, 'backend.tushare.fund_nav', 'real nav BFF')
assertIncludes(navRoute, 'isMock: false', 'real nav BFF')
if (navRoute.includes('generateMockNavData') || navRoute.includes('Math.random')) {
  throw new Error('real nav BFF must not generate mock NAV data')
}

const simulationRoute = read('app/api/funds/[id]/historical-nav-replay/route.ts')
assertIncludes(simulationRoute, 'simulateLumpSum', 'purchase simulation route')
assertIncludes(simulationRoute, 'simulateSip', 'purchase simulation route')
assertIncludes(simulationRoute, 'backend.tushare.fund_nav', 'purchase simulation route')
assertIncludes(simulationRoute, 'buildStressExperience', 'purchase simulation stress experience')
assertIncludes(simulationRoute, 'buildSimulationEvidenceGate', 'purchase simulation evidence gate builder')
assertIncludes(simulationRoute, 'evidenceGate', 'purchase simulation returns evidence gate')
assertIncludes(simulationRoute, 'normalizePurchasePlan', 'purchase simulation accepts purchase plan context')
assertIncludes(simulationRoute, 'parseDrawdownTolerance', 'purchase simulation accepts drawdown budget context')
assertIncludes(simulationRoute, '历史回放不是研究建议；材料证据、费用和回撤预算未清零前，不得保存为正式研究候选。', 'purchase simulation formal boundary')
assertIncludes(simulationRoute, '费用证据不完整：缺 ${feeAdjusted.missingItems.join', 'purchase simulation evidence gate downgrades missing fee evidence')
assertIncludes(simulationRoute, '历史压力回撤 ${percentText(-stressDrawdown)} 超过当前画像预算 ${percentText(maxDrawdownTolerance)}', 'purchase simulation evidence gate compares stress drawdown with budget')
assertNotIncludes(simulationRoute, '当前画像预算 ${percentText(-maxDrawdownTolerance)}', 'purchase simulation evidence gate must not render risk budget as negative')
assertIncludes(simulationRoute, '最大回撤在回放期内尚未回本', 'purchase simulation evidence gate flags unrecovered drawdown')
assertIncludes(simulationRoute, 'longestUnderwaterDays', 'purchase simulation stress experience')
assertIncludes(simulationRoute, 'longestLosingStreakMonths', 'purchase simulation stress experience')
assertIncludes(simulationRoute, 'worstThreeMonthReturn', 'purchase simulation stress experience')
assertIncludes(simulationRoute, '回放期内最大回撤尚未完全回本', 'purchase simulation stress interpretation')
assertIncludes(simulationRoute, '本地销售规则估算申购/赎回费用', 'purchase simulation disclaimer')
assertIncludes(simulationRoute, '费用后结果仅按已录入销售规则粗估', 'purchase simulation disclaimer')
assertIncludes(simulationRoute, "Math.max(1, Number(searchParams.get('lumpSumAmount')", 'purchase simulation preserves true low lump-sum amount')
assertIncludes(simulationRoute, "Math.max(1, Number(searchParams.get('monthlyAmount')", 'purchase simulation preserves true low SIP amount')
assertNotIncludes(simulationRoute, "Math.max(100, Number(searchParams.get('lumpSumAmount')", 'purchase simulation must not raise lump-sum amount to 100')
assertNotIncludes(simulationRoute, "Math.max(10, Number(searchParams.get('monthlyAmount')", 'purchase simulation must not raise SIP amount to 10')

console.log('OK purchase simulation uses real NAV, fee-aware replay, and no mock fallback')
