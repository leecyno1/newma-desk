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

const detailClient = read('app/(dashboard)/funds/[id]/FundDetailClient.tsx')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

for (const expected of [
  '研究复核体检：存在硬阻断',
  '研究复核体检：先补证再比较',
  '研究复核体检：可进入最终复核',
  '单基金研究判断 · {detailGate.profileLabel}',
  '研究复核工作流',
  '研究复核一页纸',
  '单基金研究复核必须先确认 R1-R5',
  '研究动作：<span',
  '加入研究清单',
  '已在研究清单',
  '研究清单待补证',
]) {
  assertIncludes(detailClient, expected, 'fund detail exposes research-review semantics')
}

if (!acceptance.includes('fund_detail_research_semantics_smoke.mjs')) {
  throw new Error('main acceptance should include fund detail research semantics smoke')
}

console.log('OK fund detail page exposes research-review semantics on active entry points')
