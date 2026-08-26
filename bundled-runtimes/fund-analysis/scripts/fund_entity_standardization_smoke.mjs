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
const migration = read('prisma/migrations/20260613000100_fund_entity_standardization/migration.sql')
const tool = read('lib/research-platform/tools/fund-entity-standardization.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')

for (const modelName of [
  'model FundCompany',
  'model FundProductLine',
  'model StrategyFamily',
  'model FundEntity',
  'model FundShareClass',
  'model FundLifecycleEvent',
  'model FundChangeHistory',
]) {
  assertIncludes(schema, modelName, `schema includes ${modelName}`)
}

for (const tableName of [
  'fund_companies',
  'fund_product_lines',
  'strategy_families',
  'fund_entities',
  'fund_share_classes',
  'fund_lifecycle_events',
  'fund_change_history',
]) {
  assertIncludes(migration, `CREATE TABLE "${tableName}"`, `migration creates ${tableName}`)
}

for (const field of [
  'canonicalCode',
  'companyName',
  'productLine',
  'strategyFamily',
  'activePassive',
  'lifecycleStage',
  'shareClasses',
  'changeHistory',
  'entityCompletenessScore',
]) {
  assertIncludes(tool, field, `entity standardization tool covers ${field}`)
}

assertIncludes(tool, '主基金实体', 'tool names canonical fund entity gap')
assertIncludes(tool, '份额映射', 'tool names share class mapping gap')
assertIncludes(tool, '基金公司', 'tool names fund company gap')
assertIncludes(tool, '产品线', 'tool names product line gap')
assertIncludes(tool, '策略族谱', 'tool names strategy family gap')
assertIncludes(tool, '生命周期', 'tool names lifecycle gap')
assertIncludes(tool, '变更历史', 'tool names change history gap')
assertIncludes(tool, 'FUND_RESEARCH_GUARDRAILS.noTradingDirective', 'tool keeps research-only guardrail')
assertIncludes(tool, "sideEffects: ['none']", 'tool is diagnostic and has no side effects')
assertIncludes(registry, 'fundEntityStandardizationTool', 'tool registry includes fund entity standardization')
assertIncludes(index, 'fundEntityStandardizationTool', 'tool index exports fund entity standardization')

console.log('OK fund entity standardization foundation is modeled, migrated, and registered')
