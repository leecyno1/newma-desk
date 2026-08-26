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

function assertAllowsMinOne(content, label) {
  if (!content.includes('min={1}') && !content.includes('min="1"')) {
    throw new Error(`${label} planned amount input should allow 1 via min={1} or min="1"`)
  }
}

const files = [
  ['app/(dashboard)/managers/page.tsx', 'manager list page'],
  ['app/(dashboard)/managers/[id]/page.tsx', 'manager detail page'],
  ['app/(dashboard)/analysis/manager/page.tsx', 'manager analysis page'],
  ['app/(dashboard)/analysis/fund/FundAnalysisClient.tsx', 'fund analysis page'],
  ['app/(dashboard)/market/MarketBrowserClient.tsx', 'market browser'],
]

for (const [relativePath, label] of files) {
  const content = read(relativePath)
  assertAllowsMinOne(content, label)
  assertNotIncludes(content, "min={purchasePlan === 'lump_sum' ? 100 : 10}", `${label} must not block low planned amount at UI level`)
  assertNotIncludes(content, "step={purchasePlan === 'lump_sum' ? 100 : 10}", `${label} must not force 10/100 amount steps`)
}

const managerList = read('app/(dashboard)/managers/page.tsx')
const managerDetail = read('app/(dashboard)/managers/[id]/page.tsx')
const managerAnalysis = read('app/(dashboard)/analysis/manager/page.tsx')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

assertIncludes(managerList, 'return Number.isFinite(amount) && amount > 0 ? String(Math.round(amount)) : defaultPlannedAmountForPlan(purchasePlan)', 'manager list preserves any positive planned amount')
assertIncludes(managerDetail, 'return Number.isFinite(amount) && amount > 0 ? String(Math.round(amount)) : defaultPlannedAmountForPlan(purchasePlan)', 'manager detail preserves any positive planned amount')
assertIncludes(managerAnalysis, 'return Number.isFinite(amount) && amount > 0 ? String(Math.round(amount)) : defaultPlannedAmountForPlan(purchasePlan)', 'manager analysis preserves any positive planned amount')
assertIncludes(acceptance, 'scripts/planned_amount_low_value_smoke.mjs', 'fund research acceptance includes low planned amount smoke')

console.log('OK planned amount inputs preserve true low positive values across buy-before paths')
