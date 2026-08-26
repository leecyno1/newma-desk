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

const canonicalLib = read('lib/research-review-report.ts')
const legacyLib = read('lib/pre-purchase-report.ts')
const canonicalRoute = read('app/api/funds/[id]/research-review-report/route.ts')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

assertIncludes(canonicalLib, 'export function buildResearchReviewReport', 'canonical research review report lib owns builder')
assertIncludes(canonicalLib, 'export function normalizeNavRows', 'canonical research review report lib owns NAV normalization')
assertIncludes(canonicalLib, 'export function buildPurchaseSimulationFromNav', 'canonical research review report lib owns historical replay conversion')
assertIncludes(legacyLib, "export { buildResearchReviewReport as buildPrePurchaseReport } from './research-review-report'", 'legacy pre-purchase lib delegates builder alias')
assertNotIncludes(legacyLib, 'export function buildPrePurchaseReport', 'legacy pre-purchase lib implementation')
assertIncludes(canonicalRoute, '@/lib/research-review-report', 'research review route imports canonical report lib')
assertIncludes(canonicalRoute, 'buildResearchReviewReport({', 'research review route calls canonical builder')
assertNotIncludes(canonicalRoute, '@/lib/pre-purchase-report', 'research review route should not import legacy report lib')
assertIncludes(acceptance, 'research_review_report_lib_smoke.mjs', 'main acceptance includes research review report lib smoke')

console.log('OK research review report lib owns implementation and legacy pre-purchase lib is compatibility-only')
