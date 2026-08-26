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
const migration = read('prisma/migrations/20260614000400_methodology_config_foundation/migration.sql')
const tool = read('lib/research-platform/tools/methodology-config.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')

for (const modelName of [
  'model ResearchMethodologyTemplate',
  'model ResearchMethodologyDimension',
  'model ResearchMethodologyMapping',
]) {
  assertIncludes(schema, modelName, `schema includes ${modelName}`)
}

for (const tableName of [
  'research_methodology_templates',
  'research_methodology_dimensions',
  'research_methodology_mappings',
]) {
  assertIncludes(migration, `CREATE TABLE "${tableName}"`, `migration creates ${tableName}`)
}

for (const templateKey of [
  'active_equity',
  'fixed_income',
  'index_fund',
  'money_market',
  'qdii',
  'fof',
  'quant_fund',
]) {
  assertIncludes(tool, templateKey, `methodology tool supports ${templateKey}`)
}

for (const dimension of [
  '基准与归因',
  '同类池',
  '持仓穿透',
  '基金经理',
  '基金公司',
  '费用与跟踪误差',
  '收益竞争力',
  '本金保护',
  '信用暴露',
  '汇率与区域暴露',
  '底层基金穿透',
  '模型稳定性',
]) {
  assertIncludes(tool, dimension, `methodology tool covers ${dimension}`)
}

assertIncludes(tool, 'methodology-config', 'tool declares methodology-config manifest')
assertIncludes(tool, 'unclassifiedMethodologyOutput', 'tool exposes an explicit unclassified gate')
assertIncludes(tool, "templateKey: 'unclassified'", 'unknown classifications do not borrow a category template')
assertIncludes(tool, 'matched.categoryScore > 0', 'active/passive metadata alone cannot choose a category')
assertIncludes(tool, '未确认基金分类时不选择任何评价模板', 'unknown classifications stop methodology selection')
assertNotIncludes(tool, '默认进入主动权益模板', 'unknown classifications must not default to active equity')
assertIncludes(tool, 'FUND_RESEARCH_GUARDRAILS.noTradingDirective', 'tool keeps research-only guardrail')
assertIncludes(tool, '不能用同一套评价维度覆盖所有基金类型', 'tool blocks one-size-fits-all evaluation')
assertNotIncludes(tool, '投委会', 'tool must not include investment committee workflow')
assertNotIncludes(tool, '购买建议', 'tool must not output purchase advice')

assertIncludes(registry, 'methodologyConfigTool', 'tool registry includes methodology config')
assertIncludes(index, 'MethodologyConfigOutput', 'tool index exports methodology config types')

console.log('OK methodology configuration foundation is modeled, tooled, and registered')
