import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) {
    throw new Error(`Missing required file: ${relativePath}`)
  }
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) {
    throw new Error(`${label} missing text: ${expected}`)
  }
}

function assertNotIncludes(content, unexpected, label) {
  if (content.includes(unexpected)) {
    throw new Error(`${label} should not include stale text: ${unexpected}`)
  }
}

const comparisonPage = read('app/(dashboard)/analysis/comparison/page.tsx')

const staleBuy = '买'
const stalePurchase = '购'
const staleTrade = '交' + '易'
const staleInvestor = '投' + '资' + '者'
const staleOrder = '下' + '单'

for (const staleCopy of [
  `${staleBuy}前`,
  `${staleBuy}入`,
  `${stalePurchase}${staleBuy}`,
  staleOrder,
  staleTrade,
  staleInvestor,
  `可${stalePurchase}${staleBuy}`,
  `${stalePurchase}${staleBuy}候选`,
]) {
  assertNotIncludes(comparisonPage, staleCopy, `comparison page research-only copy guard ${staleCopy}`)
}

assertIncludes(comparisonPage, '研究选择结论', 'comparison page has research decision header')
assertIncludes(comparisonPage, '研究复核体检', 'comparison page has research review health check')
assertIncludes(comparisonPage, '研究决策评分卡', 'comparison page has research scorecard')
assertIncludes(comparisonPage, '研究比较备忘录', 'comparison page has research memo')
assertIncludes(comparisonPage, '研究证据', 'comparison page uses research evidence language')
assertIncludes(comparisonPage, '持有体验回放', 'comparison page uses holding replay language')
assertIncludes(comparisonPage, '申赎/运作状态', 'comparison page uses subscription/redemption status language')
assertIncludes(comparisonPage, '不构成申赎操作指令', 'comparison page keeps research-only operation boundary')
assertIncludes(comparisonPage, '第一名研究复核四问', 'comparison page exposes leader research review questions')
assertIncludes(comparisonPage, '横评第一名只能回答“先研究谁”', 'comparison page limits leader interpretation to research priority')

console.log('OK comparison page uses research-review semantics without legacy buy/trading language')
