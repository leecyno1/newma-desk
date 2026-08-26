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

const dashboard = read('app/(dashboard)/page.tsx')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

assertIncludes(dashboard, '经理研究覆盖', 'root page keeps the research workstation home with manager research coverage')
assertIncludes(dashboard, 'form action="/discover"', 'root page exposes the simple fund search entry')
assertIncludes(dashboard, 'href="/discover"', 'root page links to the simple fund browser')

for (const staleDirectLink of [
  'href="/investor-selection"',
  'href="/pools"',
  'href="/rankings"',
  "href: '/investor-selection",
  "href: '/pools",
  "href: '/rankings",
]) {
  assertNotIncludes(dashboard, staleDirectLink, 'dashboard canonical research links')
}

assertIncludes(acceptance, 'dashboard_canonical_research_links_smoke.mjs', 'main acceptance includes dashboard canonical link smoke')

console.log('OK root page gives ordinary users a simple fund-selection home and browser entry')
