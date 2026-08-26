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

function assertNotIncludes(content, expected, label) {
  if (content.includes(expected)) throw new Error(`${label} should not include: ${expected}`)
}

const canonicalRoutes = [
  ['app/api/evidence-coverage/review-events/route.ts', ['backendApiBaseUrl', '获取复查事件失败', 'export async function GET']],
  ['app/api/evidence-coverage/review-events/scan/route.ts', ['backendApiBaseUrl', '触发复查扫描失败', 'export async function POST']],
  ['app/api/evidence-coverage/review-events/rules/route.ts', ['backendApiBaseUrl', '获取复查规则失败', '创建复查规则失败']],
  ['app/api/evidence-coverage/review-events/rules/[ruleId]/route.ts', ['backendApiBaseUrl', '更新复查规则失败', '删除复查规则失败']],
  ['app/api/evidence-coverage/review-events/events/[eventId]/route.ts', ['backendApiBaseUrl', '更新复查事件失败']],
]

for (const [route, expectedSnippets] of canonicalRoutes) {
  const content = read(route)
  assertNotIncludes(content, "export {", `${route} canonical handler`)
  assertNotIncludes(content, '预警', `${route} canonical copy`)
  for (const expected of expectedSnippets) {
    assertIncludes(content, expected, `${route} canonical implementation`)
  }
}

const legacyRoutes = [
  'app/api/alerts/route.ts',
  'app/api/alerts/scan/route.ts',
  'app/api/alerts/rules/route.ts',
  'app/api/alerts/rules/[ruleId]/route.ts',
  'app/api/alerts/events/[eventId]/route.ts',
]

for (const route of legacyRoutes) {
  const content = read(route)
  assertIncludes(content, 'export {', `${route} legacy compatibility shell`)
  assertIncludes(content, 'evidence-coverage/review-events', `${route} redirects to canonical review-events`)
  assertNotIncludes(content, 'backendApiBaseUrl', `${route} legacy compatibility shell`)
  assertNotIncludes(content, '预警', `${route} legacy compatibility shell`)
}

const activeSurfaces = [
  'app/(dashboard)/funds/page.tsx',
  'app/(dashboard)/funds/[id]/FundDetailClient.tsx',
  'app/(dashboard)/market/MarketBrowserClient.tsx',
  'app/(dashboard)/managers/[id]/page.tsx',
  'app/(dashboard)/analysis/comparison/page.tsx',
].map((file) => [file, read(file)])

for (const [file, content] of activeSurfaces) {
  if (content.includes('/api/alerts')) throw new Error(`${file} should call canonical review-events API`)
}

const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')
assertIncludes(acceptance, 'review_events_api_routes_smoke.mjs', 'main acceptance includes review events API smoke')

console.log('OK canonical review event APIs replace alerts API calls on active surfaces')
