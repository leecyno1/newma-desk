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

const canonicalLib = read('lib/research-evidence.ts')
const legacyLib = read('lib/buy-evidence.ts')
const researchEvidenceTool = read('lib/research-platform/tools/research-evidence.ts')
const researchReviewRoute = read('app/api/funds/[id]/research-review-report/route.ts')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

assertIncludes(canonicalLib, 'export function buildResearchEvidence', 'canonical research evidence lib owns builder')
assertIncludes(legacyLib, "export { buildResearchEvidence as buildBuyEvidence } from './research-evidence'", 'legacy buy evidence lib delegates builder alias')
assertNotIncludes(legacyLib, 'export function buildBuyEvidence', 'legacy buy evidence lib implementation')
assertIncludes(researchEvidenceTool, "import { buildResearchEvidence } from '@/lib/research-evidence'", 'research evidence tool imports canonical lib')
assertIncludes(researchEvidenceTool, 'ReturnType<typeof buildResearchEvidence>', 'research evidence tool output type uses canonical builder')
assertIncludes(researchEvidenceTool, 'buildResearchEvidence(input.fund', 'research evidence tool calls canonical builder')
assertIncludes(researchReviewRoute, "import { buildResearchEvidence } from '@/lib/research-evidence'", 'research review route imports canonical evidence lib')
assertIncludes(researchReviewRoute, 'buildResearchEvidence(fundWithSalesRule', 'research review route calls canonical evidence builder')
assertNotIncludes(researchReviewRoute, '@/lib/buy-evidence', 'research review route should not import legacy buy evidence lib')
assertIncludes(acceptance, 'research_evidence_lib_smoke.mjs', 'main acceptance includes research evidence lib smoke')

console.log('OK research evidence lib owns implementation and legacy buy evidence lib is compatibility-only')
