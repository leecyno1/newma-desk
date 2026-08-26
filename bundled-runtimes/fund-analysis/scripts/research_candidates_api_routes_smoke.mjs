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

const route = read('app/api/market/research-candidates/route.ts')
assertIncludes(route, 'export async function GET', 'research candidates route owns candidate handler')
assertIncludes(read('app/api/investor-selection/route.ts'), "export { GET } from '../market/research-candidates/route'", 'legacy investor-selection API delegates canonical candidate handler')
if (route.includes('/investor-selection')) throw new Error('research candidates API should not emit investor-selection links')

for (const expected of [
  'researchScore: clamp(score)',
  'researchRating:',
  'researchPreferences: preferences',
  'researchGate: purchaseGate',
  'researchEvidence: buyEvidence',
  'researchGateBuckets:',
  '查看历史净值回放并调整观察场景',
  '加入研究清单并设置复核日期',
  '研究候选过滤：',
  '费用证据：',
  '本页仅用于基金研究候选筛选',
]) {
  assertIncludes(route, expected, 'research candidates API exposes research-native aliases')
}

const activeSurfaces = [
  'app/(dashboard)/funds/[id]/FundDetailClient.tsx',
  'app/api/evidence-coverage/route.ts',
  'app/api/funds/[id]/pre-purchase-report/route.ts',
].map((file) => [file, read(file)])

for (const [file, content] of activeSurfaces) {
  if (content.includes('/api/investor-selection')) throw new Error(`${file} should call canonical research-candidates API`)
}

const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')
assertIncludes(acceptance, 'research_candidates_api_routes_smoke.mjs', 'main acceptance includes research candidates API smoke')

console.log('OK canonical research candidates API replaces investor-selection API calls on active surfaces')
