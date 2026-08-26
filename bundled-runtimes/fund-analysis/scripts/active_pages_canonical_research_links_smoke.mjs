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
  if (content.includes(unexpected)) throw new Error(`${label} should not include stale direct link: ${unexpected}`)
}

const activePages = [
  'app/(dashboard)/analysis/comparison/page.tsx',
  'app/(dashboard)/funds/[id]/FundDetailClient.tsx',
  'app/(dashboard)/evidence-coverage/EvidenceCoverageClient.tsx',
]

for (const file of activePages) {
  const content = read(file)
  assertIncludes(content, 'canonicalResearchHref', `${file} uses canonical research href seam`)
  for (const staleDirectLink of [
    'href="/investor-selection"',
    'href="/pools"',
    'href="/rankings"',
    "href: '/investor-selection",
    "href: '/pools",
    "href: '/rankings",
    'return `/investor-selection',
    'return `/pools',
    'return `/rankings',
  ]) {
    assertNotIncludes(content, staleDirectLink, file)
  }
}

const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')
assertIncludes(acceptance, 'active_pages_canonical_research_links_smoke.mjs', 'main acceptance includes active pages canonical link smoke')

console.log('OK active pages route legacy research links through canonical surfaces')
