import { readFileSync, existsSync } from 'node:fs'
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

const schema = read('prisma/schema.prisma')
const migration = read('prisma/migrations/20260613000200_explainable_peer_groups/migration.sql')
const tool = read('lib/research-platform/tools/peer-group-benchmark.ts')

for (const modelName of ['model PeerGroup', 'model PeerGroupMember']) {
  assertIncludes(schema, modelName, `schema includes ${modelName}`)
}

for (const tableName of ['peer_groups', 'peer_group_members']) {
  assertIncludes(migration, `CREATE TABLE "${tableName}"`, `migration creates ${tableName}`)
}

for (const dimension of [
  'assetClass',
  'strategyFamily',
  'activePassive',
  'styleTags',
  'scaleBucket',
  'ageBucket',
  'explainablePeerKey',
  'matchedRules',
  'missingRules',
  'exclusionWarnings',
  'benchmarkMappingRationale',
]) {
  assertIncludes(tool, dimension, `peer benchmark tool explains ${dimension}`)
}

assertIncludes(tool, '资产类别', 'peer benchmark tool names asset class dimension')
assertIncludes(tool, '策略族谱', 'peer benchmark tool names strategy family dimension')
assertIncludes(tool, '主动/被动', 'peer benchmark tool names active/passive dimension')
assertIncludes(tool, '风格标签', 'peer benchmark tool names style dimension')
assertIncludes(tool, '规模分层', 'peer benchmark tool names scale dimension')
assertIncludes(tool, '成立年限', 'peer benchmark tool names fund age dimension')
assertIncludes(tool, '主动/被动属性缺失，可能把指数、增强和主动产品混比', 'peer benchmark tool warns about mixed active/passive peers')
assertIncludes(tool, '正式研究前需复核基准是否与合同或招募书一致', 'peer benchmark tool requires benchmark evidence review')

console.log('OK explainable peer group foundation is modeled and tool-enforced')
