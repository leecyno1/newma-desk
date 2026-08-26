import { readFileSync, existsSync } from 'node:fs'
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

function assertNotIncludes(content, expected, label) {
  if (content.includes(expected)) throw new Error(`${label} should not include: ${expected}`)
}

const canonicalRoutes = [
  ['app/api/evidence-coverage/materials/route.ts', ['export async function GET', 'export async function POST', '读取材料核验列表失败']],
  ['app/api/evidence-coverage/materials/gaps/route.ts', ['export async function GET', '读取材料核验待补清单失败']],
  ['app/api/evidence-coverage/materials/impact/route.ts', ['export async function GET', '读取材料核验影响失败']],
  ['app/api/evidence-coverage/materials/tushare-foundation/route.ts', ['export async function POST', '导入 Tushare 基础申赎状态失败']],
  ['app/api/funds/[id]/materials/route.ts', ['export async function GET', 'export async function PATCH', '读取单基金材料核验失败', 'MATERIAL_EVIDENCE_VALIDATION_FAILED']],
]

for (const [route, expectedSnippets] of canonicalRoutes) {
  const content = read(route)
  assertNotIncludes(content, "export {", `${route} canonical handler`)
  for (const expected of expectedSnippets) {
    assertIncludes(content, expected, `${route} canonical implementation`)
  }
}

const legacyRoutes = [
  'app/api/sales-rules/route.ts',
  'app/api/sales-rules/gaps/route.ts',
  'app/api/sales-rules/impact/route.ts',
  'app/api/sales-rules/tushare-foundation/route.ts',
  'app/api/funds/[id]/sales-rules/route.ts',
]

for (const route of legacyRoutes) {
  const content = read(route)
  assertIncludes(content, 'export {', `${route} legacy compatibility shell`)
  assertIncludes(content, route.includes('/funds/') ? '../materials/route' : 'evidence-coverage/materials', `${route} redirects to canonical materials`)
}

const activeSurfaces = [
  'app/(dashboard)/funds/page.tsx',
  'app/(dashboard)/funds/[id]/FundDetailClient.tsx',
  'app/(dashboard)/market/MarketBrowserClient.tsx',
  'app/(dashboard)/analysis/[id]/AnalysisDetailClient.tsx',
  'app/(dashboard)/analysis/comparison/page.tsx',
].map((file) => [file, read(file)])

for (const [file, content] of activeSurfaces) {
  if (content.includes('/api/sales-rules')) throw new Error(`${file} should call canonical material evidence API`)
  if (content.includes('/sales-rules')) throw new Error(`${file} should link canonical material evidence pages`)
}

const fundDetail = read('app/(dashboard)/funds/[id]/FundDetailClient.tsx')
assertIncludes(fundDetail, '/api/funds/${encodeURIComponent(fund.windCode)}/materials', 'fund detail saves material evidence through canonical per-fund API')
assertNotIncludes(fundDetail, '/api/funds/${encodeURIComponent(fund.windCode)}/sales-rules', 'fund detail per-fund legacy material API')

const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')
assertIncludes(acceptance, 'material_evidence_api_routes_smoke.mjs', 'main acceptance includes material evidence API smoke')

console.log('OK canonical material evidence APIs replace sales-rules API calls on active surfaces')
