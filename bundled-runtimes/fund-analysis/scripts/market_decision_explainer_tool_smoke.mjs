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

const tool = read('lib/research-platform/tools/market-decision-explainer.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')
const marketClient = read('app/(dashboard)/market/MarketBrowserClient.tsx')

assertIncludes(tool, "const toolName = 'market-decision-explainer'", 'market decision explainer tool declares stable tool name')
assertIncludes(tool, "domain: 'screening'", 'market decision explainer tool lives in screening domain')
assertIncludes(tool, 'MarketDecisionExplainerInput', 'market decision explainer tool declares input contract')
assertIncludes(tool, 'MarketDecisionExplainerOutput', 'market decision explainer tool declares output contract')
assertIncludes(tool, 'buildPrimaryAction', 'market decision explainer tool owns primary action')
assertIncludes(tool, 'sortExplanation', 'market decision explainer tool owns sort explanation')
assertIncludes(tool, 'createToolResult', 'market decision explainer tool returns audited ToolResult')
assertIncludes(tool, 'hardBlocks', 'market decision explainer tool emits hard blocks')
assertIncludes(tool, 'gaps', 'market decision explainer tool emits evidence gaps')
assertIncludes(tool, 'nextActions', 'market decision explainer tool emits next actions')
assertNotIncludes(tool, '买前', 'market decision explainer tool avoids buy-before wording')
assertNotIncludes(tool, '购买', 'market decision explainer tool avoids purchase wording')
assertNotIncludes(tool, '买入', 'market decision explainer tool avoids buy wording')
assertNotIncludes(tool, '交易', 'market decision explainer tool avoids trading wording')

assertIncludes(registry, 'marketDecisionExplainerTool', 'research tool registry includes market decision explainer tool')
assertIncludes(index, 'MarketDecisionExplainerOutput', 'research tool index exports market decision explainer types')

assertIncludes(marketClient, 'marketDecisionExplainerTool.run(marketDecisionExplainerInput)', 'market browser calls market decision explainer tool')
assertIncludes(marketClient, 'marketDecisionExplainerResult.data', 'market browser consumes decision explainer tool result')
assertNotIncludes(marketClient, 'const marketDecisionExplainer = (() =>', 'market browser no longer owns decision explainer rules')
assertNotIncludes(marketClient, 'const actionableRows = rows.filter', 'market browser no longer owns actionable row grouping')
assertNotIncludes(marketClient, 'const topFundCopy = topRows.length', 'market browser no longer owns top fund copy')

console.log('OK market decision explainer tool owns quality explanation, primary action, and sort reasoning')
