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
  if (content.includes(unexpected)) throw new Error(`${label} should not include stale manager copy: ${unexpected}`)
}

const managerList = read('app/(dashboard)/managers/page.tsx')
const managerDetail = read('app/(dashboard)/managers/[id]/page.tsx')
const reportsPage = read('app/(dashboard)/reports/page.tsx')

for (const expected of [
  '当前结果',
  '所选类别',
  '专业分类',
  '任期指标',
  '调研纪要',
  '补产品证据',
]) {
  assertIncludes(managerList, expected, `manager page uses research term ${expected}`)
}

for (const expected of [
  '当前管理基金与任期证据',
  '产品任职全景',
  '投资框架与风格画像',
  '调研纪要与历史观点',
  '复查事件',
  '补研究材料',
]) {
  assertIncludes(managerDetail, expected, `manager detail uses research term ${expected}`)
}

for (const expected of [
  '研究复核',
  '研究总闸门',
  '研究补证队列',
  '研究复核报告',
  '研究方式假设',
]) {
  assertIncludes(reportsPage, expected, `reports page uses research term ${expected}`)
}

for (const staleCopy of [
  '买前',
  '买入',
  '购买',
  '交易',
  '投资者',
  '可买',
  '可购买候选',
  '购买候选',
  '正式购买',
  '一次性买入',
]) {
  assertNotIncludes(managerList, staleCopy, 'manager research semantics')
  assertNotIncludes(managerDetail, staleCopy, 'manager detail research semantics')
  assertNotIncludes(reportsPage, staleCopy, 'reports research semantics')
}

console.log('OK manager and report pages use canonical research semantics without legacy buy language')
