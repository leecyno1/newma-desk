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

function assertNotIncludes(content, forbidden, label) {
  if (content.includes(forbidden)) throw new Error(`${label} should not include: ${forbidden}`)
}

const tool = read('lib/research-platform/tools/market-compare-basket-win-loss.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')
const marketClient = read('app/(dashboard)/market/MarketBrowserClient.tsx')

assertIncludes(tool, "const toolName = 'market-compare-basket-win-loss'", 'market compare basket tool declares stable tool name')
assertIncludes(tool, "domain: 'comparison'", 'market compare basket tool lives in comparison domain')
assertIncludes(tool, 'MarketCompareBasketWinLossInput', 'market compare basket tool declares input contract')
assertIncludes(tool, 'MarketCompareBasketWinLossOutput', 'market compare basket tool declares output contract')
assertIncludes(tool, 'buildRow', 'market compare basket tool owns row construction')
assertIncludes(tool, 'buildAudit', 'market compare basket tool owns audit construction')
assertIncludes(tool, 'buildTsv', 'market compare basket tool owns TSV construction')
assertIncludes(tool, 'createToolResult', 'market compare basket tool returns audited ToolResult')
assertIncludes(tool, 'hardBlocks', 'market compare basket tool emits hard blocks')
assertIncludes(tool, 'gaps', 'market compare basket tool emits evidence gaps')
assertIncludes(tool, 'nextActions', 'market compare basket tool emits next actions')
assertNotIncludes(tool, '买前', 'market compare basket tool avoids buy-before wording')
assertNotIncludes(tool, '购买', 'market compare basket tool avoids purchase wording')
assertNotIncludes(tool, '买入', 'market compare basket tool avoids buy wording')
assertNotIncludes(tool, '交易', 'market compare basket tool avoids trading wording')

assertIncludes(registry, 'marketCompareBasketWinLossTool', 'research tool registry includes market compare basket tool')
assertIncludes(index, 'MarketCompareBasketWinLossOutput', 'research tool index exports market compare basket types')

assertIncludes(marketClient, 'marketCompareBasketWinLossTool.run(compareBasketWinLossInput)', 'market browser calls market compare basket tool')
assertIncludes(marketClient, 'compareBasketWinLossResult.data?.rows', 'market browser consumes tool rows')
assertIncludes(marketClient, 'compareBasketWinLossResult.data?.audit', 'market browser consumes tool audit')
assertIncludes(marketClient, 'compareBasketWinLossResult.data?.tsv', 'market browser consumes tool TSV')
assertNotIncludes(marketClient, 'const compareBasketWinLossAudit = (() =>', 'market browser no longer owns win/loss audit rules')
assertNotIncludes(marketClient, 'const compareBasketWinLossTsv = [', 'market browser no longer owns win/loss TSV rules')
assertNotIncludes(marketClient, 'const researchScore = score.total', 'market browser no longer owns win/loss scoring formula')

console.log('OK market compare basket win/loss tool owns scoring, audit, and TSV generation')
