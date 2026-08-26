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

const tool = read('lib/research-platform/tools/market-current-page-shortlist.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')
const marketClient = read('app/(dashboard)/market/MarketBrowserClient.tsx')

assertIncludes(tool, "const toolName = 'market-current-page-shortlist'", 'market current page shortlist tool declares stable tool name')
assertIncludes(tool, "domain: 'screening'", 'market current page shortlist tool lives in screening domain')
assertIncludes(tool, 'MarketCurrentPageShortlistInput', 'market current page shortlist tool declares input contract')
assertIncludes(tool, 'MarketCurrentPageShortlistOutput', 'market current page shortlist tool declares output contract')
assertIncludes(tool, 'scoreItem', 'market current page shortlist tool owns score formula')
assertIncludes(tool, 'laneForItem', 'market current page shortlist tool owns lane decision')
assertIncludes(tool, 'buildPrimaryAction', 'market current page shortlist tool owns primary action selection')
assertIncludes(tool, 'buildTsv', 'market current page shortlist tool owns TSV generation')
assertIncludes(tool, 'createToolResult', 'market current page shortlist tool returns audited ToolResult')
assertIncludes(tool, 'hardBlocks', 'market current page shortlist tool emits hard blocks')
assertIncludes(tool, 'gaps', 'market current page shortlist tool emits evidence gaps')
assertIncludes(tool, 'nextActions', 'market current page shortlist tool emits next actions')
assertNotIncludes(tool, '买前', 'market current page shortlist tool avoids buy-before wording')
assertNotIncludes(tool, '购买', 'market current page shortlist tool avoids purchase wording')
assertNotIncludes(tool, '买入', 'market current page shortlist tool avoids buy wording')
assertNotIncludes(tool, '交易', 'market current page shortlist tool avoids trading wording')

assertIncludes(registry, 'marketCurrentPageShortlistTool', 'research tool registry includes market current page shortlist tool')
assertIncludes(index, 'MarketCurrentPageShortlistOutput', 'research tool index exports market current page shortlist types')

assertIncludes(marketClient, 'marketCurrentPageShortlistTool.run(marketShortlistInput)', 'market browser calls market current page shortlist tool')
assertIncludes(marketClient, 'marketShortlistResult.data', 'market browser consumes shortlist tool result')
assertIncludes(marketClient, 'marketShortlist.tsv', 'market browser consumes shortlist tool TSV')
assertNotIncludes(marketClient, 'const rawScore = score.total', 'market browser no longer owns shortlist score formula')
assertNotIncludes(marketClient, "const marketShortlistTsv = [", 'market browser no longer owns shortlist TSV generation')
assertNotIncludes(marketClient, "const lane: 'shortlist' | 'repair' | 'exclude'", 'market browser no longer owns shortlist lane decision')

console.log('OK market current page shortlist tool owns scoring, lanes, primary action, and TSV generation')
