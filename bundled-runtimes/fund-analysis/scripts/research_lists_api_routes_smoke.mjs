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

function assertNotIncludes(content, unexpected, label) {
  if (content.includes(unexpected)) throw new Error(`${label} should not include: ${unexpected}`)
}

const researchListsRoute = read('app/api/market/research-lists/route.ts')
const researchListMembersRoute = read('app/api/market/research-lists/[id]/members/route.ts')
const researchListShortlistRoute = read('app/api/market/research-lists/[id]/shortlist-report/route.ts')
const researchListMemberPatchRoute = read('app/api/market/research-lists/members/[memberId]/route.ts')
const legacyFundPoolsRoute = read('app/api/fund-pools/route.ts')
const legacyFundPoolMembersRoute = read('app/api/fund-pools/[id]/members/route.ts')
const legacyFundPoolShortlistRoute = read('app/api/fund-pools/[id]/shortlist-report/route.ts')
const legacyFundPoolMemberPatchRoute = read('app/api/fund-pools/members/[memberId]/route.ts')

assertIncludes(researchListsRoute, 'backendApiBaseUrl', 'research lists route owns BFF implementation')
assertIncludes(researchListsRoute, 'toSnakePool', 'research lists route maps backend pool payload')
assertNotIncludes(researchListsRoute, "export { GET, POST } from '../../fund-pools/route'", 'research lists route')
assertIncludes(researchListMembersRoute, 'assertSalesRuleGate', 'research list members route owns evidence gate')
assertIncludes(researchListShortlistRoute, 'buildResearchListShortlistReport', 'research list shortlist route owns report implementation')
assertIncludes(researchListMemberPatchRoute, 'lookupMemberWindCode', 'research list member patch route owns evidence gate')
for (const [file, content] of [
  ['app/api/market/research-lists/route.ts', researchListsRoute],
  ['app/api/market/research-lists/[id]/members/route.ts', researchListMembersRoute],
  ['app/api/market/research-lists/[id]/shortlist-report/route.ts', researchListShortlistRoute],
  ['app/api/market/research-lists/members/[memberId]/route.ts', researchListMemberPatchRoute],
]) {
  for (const staleCopy of ['基金池', '候选池', '购买候选', '购买研究清单', '购买路径观察池', '买前短名单', '买前证据']) {
    assertNotIncludes(content, staleCopy, `${file} canonical research-list copy`)
  }
}
assertIncludes(legacyFundPoolsRoute, "export { GET, POST } from '../market/research-lists/route'", 'legacy fund-pools route delegates canonical research list route')
assertIncludes(legacyFundPoolMembersRoute, "export { GET, POST } from '../../../market/research-lists/[id]/members/route'", 'legacy fund-pool members route delegates canonical route')
assertIncludes(legacyFundPoolShortlistRoute, "export { GET } from '../../../market/research-lists/[id]/shortlist-report/route'", 'legacy fund-pool shortlist route delegates canonical route')
assertIncludes(legacyFundPoolMemberPatchRoute, "export { PATCH } from '../../../market/research-lists/members/[memberId]/route'", 'legacy fund-pool member patch route delegates canonical route')

const activeSurfaces = [
  'app/(dashboard)/funds/[id]/FundDetailClient.tsx',
  'app/(dashboard)/market/MarketBrowserClient.tsx',
  'app/(dashboard)/analysis/[id]/AnalysisDetailClient.tsx',
  'app/(dashboard)/analysis/comparison/page.tsx',
  'app/(dashboard)/reports/[id]/page.tsx',
].map((file) => [file, read(file)])

for (const [file, content] of activeSurfaces) {
  if (content.includes('/api/fund-pools')) throw new Error(`${file} should call canonical research-lists API`)
}

const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')
assertIncludes(acceptance, 'research_lists_api_routes_smoke.mjs', 'main acceptance includes research lists API smoke')

console.log('OK canonical research list APIs replace fund-pools API calls on active surfaces')
