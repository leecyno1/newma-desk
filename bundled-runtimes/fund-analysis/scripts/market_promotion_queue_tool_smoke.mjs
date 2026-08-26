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

const tool = read('lib/research-platform/tools/market-promotion-queue.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')
const marketClient = read('app/(dashboard)/market/MarketBrowserClient.tsx')

assertIncludes(tool, "const toolName = 'market-promotion-queue'", 'market promotion queue tool declares stable tool name')
assertIncludes(tool, "domain: 'screening'", 'market promotion queue tool lives in screening domain')
assertIncludes(tool, 'MarketPromotionQueueInput', 'market promotion queue tool declares input contract')
assertIncludes(tool, 'MarketPromotionQueueOutput', 'market promotion queue tool declares output contract')
assertIncludes(tool, 'laneForItem', 'market promotion queue tool owns lane decision')
assertIncludes(tool, 'buildGateAudit', 'market promotion queue tool owns gate audit')
assertIncludes(tool, 'buildTasksTsv', 'market promotion queue tool owns TSV generation')
assertIncludes(tool, 'createToolResult', 'market promotion queue tool returns audited ToolResult')
assertIncludes(tool, 'hardBlocks', 'market promotion queue tool emits hard blocks')
assertIncludes(tool, 'gaps', 'market promotion queue tool emits evidence gaps')
assertIncludes(tool, 'nextActions', 'market promotion queue tool emits next actions')
assertNotIncludes(tool, '买前', 'market promotion queue tool avoids buy-before wording')
assertNotIncludes(tool, '购买', 'market promotion queue tool avoids purchase wording')
assertNotIncludes(tool, '买入', 'market promotion queue tool avoids buy wording')
assertNotIncludes(tool, '交易', 'market promotion queue tool avoids trading wording')

assertIncludes(registry, 'marketPromotionQueueTool', 'research tool registry includes market promotion queue tool')
assertIncludes(index, 'MarketPromotionQueueOutput', 'research tool index exports market promotion queue types')

assertIncludes(marketClient, 'marketPromotionQueueTool.run(marketPromotionQueueInput)', 'market browser calls market promotion queue tool')
assertIncludes(marketClient, 'marketPromotionQueueResult.data', 'market browser consumes promotion queue tool result')
assertIncludes(marketClient, 'marketPromotionQueue.tasksTsv', 'market browser consumes promotion queue TSV')
assertNotIncludes(marketClient, 'const laneMeta = [', 'market browser no longer owns promotion lane definitions')
assertNotIncludes(marketClient, 'const marketPromotionGateAudit = (() =>', 'market browser no longer owns promotion gate audit')
assertNotIncludes(marketClient, 'const marketPromotionTasksTsv = [', 'market browser no longer owns promotion TSV generation')
assertNotIncludes(marketClient, 'const missingEvidence = readiness.gaps.filter', 'market browser no longer owns promotion evidence routing')

console.log('OK market promotion queue tool owns lanes, audit, task rows, and TSV generation')
