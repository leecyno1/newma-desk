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

const tool = read('lib/research-platform/tools/market-compare-basket-evidence.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')
const marketClient = read('app/(dashboard)/market/MarketBrowserClient.tsx')

assertIncludes(tool, "const toolName = 'market-compare-basket-evidence'", 'market compare basket evidence tool declares stable tool name')
assertIncludes(tool, "domain: 'evidence'", 'market compare basket evidence tool lives in evidence domain')
assertIncludes(tool, 'MarketCompareBasketEvidenceInput', 'market compare basket evidence tool declares input contract')
assertIncludes(tool, 'MarketCompareBasketEvidenceOutput', 'market compare basket evidence tool declares output contract')
assertIncludes(tool, 'buildRows', 'market compare basket evidence tool owns row construction')
assertIncludes(tool, 'buildNextAction', 'market compare basket evidence tool owns basket next action')
assertIncludes(tool, 'buildTsv', 'market compare basket evidence tool owns TSV generation')
assertIncludes(tool, 'createToolResult', 'market compare basket evidence tool returns audited ToolResult')
assertIncludes(tool, 'hardBlocks', 'market compare basket evidence tool emits hard blocks')
assertIncludes(tool, 'gaps', 'market compare basket evidence tool emits evidence gaps')
assertIncludes(tool, 'nextActions', 'market compare basket evidence tool emits next actions')
assertNotIncludes(tool, '买前', 'market compare basket evidence tool avoids buy-before wording')
assertNotIncludes(tool, '购买', 'market compare basket evidence tool avoids purchase wording')
assertNotIncludes(tool, '买入', 'market compare basket evidence tool avoids buy wording')
assertNotIncludes(tool, '交易', 'market compare basket evidence tool avoids trading wording')

assertIncludes(registry, 'marketCompareBasketEvidenceTool', 'research tool registry includes market compare basket evidence tool')
assertIncludes(index, 'MarketCompareBasketEvidenceOutput', 'research tool index exports market compare basket evidence types')

assertIncludes(marketClient, 'marketCompareBasketEvidenceTool.run(compareBasketEvidenceInput)', 'market browser calls market compare basket evidence tool')
assertIncludes(marketClient, 'compareBasketEvidenceResult.data?.rows', 'market browser consumes evidence tool rows')
assertIncludes(marketClient, 'compareBasketEvidenceResult.data?.nextAction', 'market browser consumes evidence tool next action')
assertIncludes(marketClient, 'compareBasketEvidenceResult.data?.tsv', 'market browser consumes evidence tool TSV')
assertNotIncludes(marketClient, 'const compareBasketNextAction = (() =>', 'market browser no longer owns compare basket next action')
assertNotIncludes(marketClient, 'const compareBasketEvidenceTsv = [', 'market browser no longer owns compare basket evidence TSV')
assertNotIncludes(marketClient, 'const rowNextAction = formalGate.passed', 'market browser no longer owns compare basket evidence row action')

console.log('OK market compare basket evidence tool owns rows, next action, and TSV generation')
