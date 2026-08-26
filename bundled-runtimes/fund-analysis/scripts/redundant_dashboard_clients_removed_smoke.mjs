import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const root = process.cwd()

function read(relativePath) {
  return readFileSync(join(root, relativePath), 'utf8')
}

function assertNotExists(relativePath) {
  if (existsSync(join(root, relativePath))) throw new Error(`Redundant dashboard client should be removed: ${relativePath}`)
}

function assertRedirect(relativePath, target) {
  const content = read(relativePath)
  if (!content.includes('redirectToMergedResearchRoute')) throw new Error(`${relativePath} should use the centralized merged-route redirect seam`)
  if (!content.includes(target)) throw new Error(`${relativePath} should redirect from ${target}`)
}

for (const file of [
  'app/(dashboard)/investor-selection/InvestorSelectionClient.tsx',
  'app/(dashboard)/sales-rules/SalesRulesClient.tsx',
  'app/(dashboard)/alerts/AlertsClient.tsx',
  'app/(dashboard)/pools/FundPoolsClient.tsx',
  'app/(dashboard)/rankings/RankingsClient.tsx',
]) {
  assertNotExists(file)
}

const helper = read('app/(dashboard)/legacyResearchRedirect.ts')
const routes = read('lib/research-platform/routes.ts')

if (!helper.includes('mergedResearchRouteTarget')) throw new Error('legacy redirect helper should use canonical route target registry')
if (!routes.includes('mergedResearchRouteSources')) throw new Error('routes should own merged route source mapping')

assertRedirect('app/(dashboard)/investor-selection/page.tsx', '/investor-selection')
assertRedirect('app/(dashboard)/sales-rules/page.tsx', '/sales-rules')
assertRedirect('app/(dashboard)/alerts/page.tsx', '/alerts')
assertRedirect('app/(dashboard)/pools/page.tsx', '/pools')
assertRedirect('app/(dashboard)/rankings/page.tsx', '/rankings')

console.log('OK redundant dashboard clients are removed and merged routes stay redirect-only')
