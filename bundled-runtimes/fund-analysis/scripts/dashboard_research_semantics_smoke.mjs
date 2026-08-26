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
  if (content.includes(unexpected)) throw new Error(`${label} should not include stale dashboard copy: ${unexpected}`)
}

const dashboard = read('app/(dashboard)/page.tsx')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

assertIncludes(dashboard, '经理研究覆盖', 'dashboard is the research workstation home')
assertIncludes(dashboard, 'form action="/discover"', 'dashboard exposes direct fund search')
assertIncludes(dashboard, 'href="/discover"', 'dashboard exposes the simple fund browser')

for (const staleCopy of [
  '投资者选基',
  '基金排行榜',
  '基金池',
  '购买研究路径工作台',
  '买前研究作战台',
  '购买候选',
  '可购买',
  '买前',
  '买入',
  '购买',
  '销售规则',
  '适当性',
]) {
  assertNotIncludes(dashboard, staleCopy, 'dashboard research semantics')
}

assertIncludes(acceptance, 'dashboard_research_semantics_smoke.mjs', 'main acceptance includes dashboard research semantics smoke')

console.log('OK default dashboard no longer exposes legacy research or purchase-decision semantics')
