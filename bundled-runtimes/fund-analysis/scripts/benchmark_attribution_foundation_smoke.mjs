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

function assertNotIncludes(content, forbidden, label) {
  if (content.includes(forbidden)) throw new Error(`${label} should not include: ${forbidden}`)
}

const schema = read('prisma/schema.prisma')
const migration = read('prisma/migrations/20260613000300_benchmark_attribution_foundation/migration.sql')
const tool = read('lib/research-platform/tools/benchmark-attribution.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')

for (const modelName of ['model BenchmarkMapping', 'model AttributionExplanation']) {
  assertIncludes(schema, modelName, `schema includes ${modelName}`)
}

for (const tableName of ['benchmark_mappings', 'attribution_explanations']) {
  assertIncludes(migration, `CREATE TABLE "${tableName}"`, `migration creates ${tableName}`)
}

for (const field of [
  'benchmarkCode',
  'benchmarkName',
  'mappingMethod',
  'mappingRationale',
  'excessReturn',
  'allocationEffect',
  'selectionEffect',
  'interactionEffect',
  'styleContribution',
  'industryContribution',
  'assetAllocation',
  'residualReturn',
  'dominantSource',
]) {
  assertIncludes(tool, field, `benchmark attribution tool covers ${field}`)
}

assertIncludes(tool, '自动基准映射', 'tool names benchmark mapping requirement')
assertIncludes(tool, '超额收益', 'tool names excess return decomposition')
assertIncludes(tool, '配置效应', 'tool names allocation effect')
assertIncludes(tool, '选择效应', 'tool names selection effect')
assertIncludes(tool, '风格暴露', 'tool names style exposure attribution')
assertIncludes(tool, '行业贡献', 'tool names industry attribution')
assertIncludes(tool, '资产配置拆解', 'tool names asset allocation attribution')
assertIncludes(tool, '不能用残差包装成能力', 'tool blocks residual-as-skill conclusion')
assertIncludes(tool, '缺少可追溯基准映射', 'tool blocks missing benchmark mapping')
assertIncludes(tool, 'FUND_RESEARCH_GUARDRAILS.noTradingDirective', 'tool keeps research-only guardrail')
assertNotIncludes(tool, '购买建议', 'tool must not output purchase advice')

assertIncludes(registry, 'benchmarkAttributionTool', 'tool registry includes benchmark attribution')
assertIncludes(index, 'BenchmarkAttributionOutput', 'tool index exports benchmark attribution types')

console.log('OK benchmark mapping and attribution explanation foundation is modeled, tooled, and registered')
