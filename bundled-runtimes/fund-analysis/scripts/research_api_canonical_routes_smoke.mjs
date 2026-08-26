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

function assertNotIncludes(content, unexpected, label) {
  if (content.includes(unexpected)) throw new Error(`${label} should not include: ${unexpected}`)
}

const canonicalReportRoute = read('app/api/funds/[id]/research-review-report/route.ts')
const canonicalReplayRoute = read('app/api/funds/[id]/historical-nav-replay/route.ts')
const legacyPrePurchaseRoute = read('app/api/funds/[id]/pre-purchase-report/route.ts')
const legacyPurchaseSimulationRoute = read('app/api/funds/[id]/purchase-simulation/route.ts')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')
const architecture = read('docs/architecture/professional-fund-research-architecture.md')
const activeSurfaces = [
  'app/(dashboard)/funds/[id]/FundDetailClient.tsx',
  'app/(dashboard)/reports/[id]/page.tsx',
  'app/(dashboard)/analysis/[id]/AnalysisDetailClient.tsx',
  'app/(dashboard)/market/MarketBrowserClient.tsx',
  'app/(dashboard)/analysis/comparison/page.tsx',
].map((file) => [file, read(file)])

assertIncludes(canonicalReportRoute, 'buildResearchReviewReport', 'research review report route owns deterministic report implementation')
assertIncludes(canonicalReportRoute, 'research-review-report', 'research review report route keeps canonical report links')
assertIncludes(canonicalReportRoute, "source: 'research_review_report'", 'research review report stores canonical source')
assertIncludes(canonicalReportRoute, "mode: 'deterministic_research_review'", 'research review report stores canonical generation mode')
assertIncludes(canonicalReportRoute, "'fund_research_review'", 'research review report stores canonical report type')
assertNotIncludes(canonicalReportRoute, "source: 'pre_purchase_report'", 'research review report source')
assertNotIncludes(canonicalReportRoute, "mode: 'deterministic_pre_purchase_check'", 'research review report generation mode')
assertNotIncludes(canonicalReportRoute, "'fund_pre_purchase_check'", 'research review report type')
assertIncludes(legacyPrePurchaseRoute, "export { GET, POST } from '../research-review-report/route'", 'legacy pre-purchase report route delegates to canonical research review route')
assertIncludes(canonicalReplayRoute, 'simulateLumpSum', 'historical NAV replay route owns deterministic replay implementation')
assertIncludes(canonicalReplayRoute, 'buildSimulationEvidenceGate', 'historical NAV replay route owns replay evidence gate')
assertIncludes(legacyPurchaseSimulationRoute, "export { GET } from '../historical-nav-replay/route'", 'legacy purchase simulation route delegates to canonical historical replay route')
assertIncludes(acceptance, 'research_api_canonical_routes_smoke.mjs', 'acceptance includes canonical route smoke')
assertIncludes(architecture, '/api/funds/[id]/research-review-report', 'architecture documents canonical research report API')
assertIncludes(architecture, '/api/funds/[id]/historical-nav-replay', 'architecture documents canonical historical replay API')

for (const [file, content] of activeSurfaces) {
  if (content.includes('/pre-purchase-report')) throw new Error(`${file} should call canonical research-review-report API`)
  if (content.includes('/purchase-simulation')) throw new Error(`${file} should call canonical historical-nav-replay API`)
}

console.log('OK canonical fund research APIs exist for research review report and historical NAV replay')
