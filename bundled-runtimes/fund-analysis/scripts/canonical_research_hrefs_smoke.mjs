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
  if (content.includes(unexpected)) throw new Error(`${label} should not include stale href: ${unexpected}`)
}

const routesHelper = read('lib/research-platform/routes.ts')
assertIncludes(routesHelper, "section', 'materials'", 'material evidence href helper')
assertIncludes(routesHelper, "section', 'review-events'", 'review events href helper')

for (const file of [
  'lib/report-buy-before-evidence-queue.ts',
  'lib/sales-rule-impact.ts',
  'lib/evidence-coverage.ts',
  'lib/research-list-shortlist-report.ts',
  'lib/research-platform/tools/sales-rule-gate.ts',
  'app/api/funds/[id]/research-review-report/route.ts',
  'app/api/reports/[id]/route.ts',
  'app/api/reports/real-data/route.ts',
  'app/api/market/research-candidates/route.ts',
  'app/api/market/research-lists/[id]/shortlist-report/route.ts',
  'app/api/market/research-lists/[id]/members/route.ts',
  'app/api/market/research-lists/members/[memberId]/route.ts',
]) {
  const content = read(file)
  assertNotIncludes(content, "alertsHref: '/alerts'", `${file} canonical review event href`)
  assertNotIncludes(content, "actionHref: '/alerts'", `${file} canonical review event href`)
  assertNotIncludes(content, "return `/sales-rules", `${file} canonical material evidence href`)
  assertNotIncludes(content, "salesRulesHref: `/sales-rules", `${file} canonical material evidence href`)
  assertNotIncludes(content, "batchSalesRules: `/sales-rules", `${file} canonical material evidence href`)
  assertNotIncludes(content, "salesRules: `/sales-rules", `${file} canonical material evidence href`)
}

for (const file of [
  'app/(dashboard)/funds/page.tsx',
  'app/(dashboard)/market/MarketBrowserClient.tsx',
  'app/(dashboard)/analysis/comparison/page.tsx',
  'app/(dashboard)/managers/[id]/page.tsx',
]) {
  const content = read(file)
  assertNotIncludes(content, '/alerts', `${file} frontend review-events href`)
  assertNotIncludes(content, '/sales-rules', `${file} frontend material evidence href`)
  assertIncludes(content, 'reviewEventsHref', `${file} frontend review-events helper`)
  assertIncludes(content, 'materialEvidenceHref', `${file} frontend material evidence helper`)
}

for (const file of [
  'app/(dashboard)/reports/page.tsx',
  'app/(dashboard)/reports/[id]/page.tsx',
  'app/(dashboard)/reports/search/page.tsx',
  'app/(dashboard)/analysis/[id]/AnalysisDetailClient.tsx',
  'components/analysis/ReportActionBar.tsx',
  'app/(dashboard)/managers/page.tsx',
]) {
  const content = read(file)
  assertNotIncludes(content, '/sales-rules', `${file} frontend material evidence href`)
  assertIncludes(content, 'materialEvidenceHref', `${file} frontend material evidence helper`)
}

for (const file of ['app/(dashboard)/funds/[id]/FundDetailClient.tsx']) {
  const content = read(file)
  assertNotIncludes(content, 'href="/alerts"', `${file} frontend review-events href`)
  assertIncludes(content, 'reviewEventsHref', `${file} frontend review-events helper`)
}

const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')
assertIncludes(acceptance, 'canonical_research_hrefs_smoke.mjs', 'main acceptance includes canonical href smoke')

console.log('OK core research outputs point to evidence coverage instead of legacy alerts/sales-rules')
