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
const migration = read('prisma/migrations/20260614000200_manager_research_loop/migration.sql')
const tool = read('lib/research-platform/tools/manager-research-loop.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')

for (const modelName of [
  'model ManagerTenureSlice',
  'model ManagerRepresentativeAttribution',
  'model ManagerTransitionEvent',
]) {
  assertIncludes(schema, modelName, `schema includes ${modelName}`)
}

for (const tableName of [
  'manager_tenure_slices',
  'manager_representative_attributions',
  'manager_transition_events',
]) {
  assertIncludes(migration, `CREATE TABLE "${tableName}"`, `migration creates ${tableName}`)
}

for (const field of [
  'tenureSlices',
  'coManagerNames',
  'representativeFunds',
  'styleDriftScore',
  'transitionEvents',
  'platformContribution',
  'tenureCoverage',
  'representativeAttribution',
  'transitionImpact',
]) {
  assertIncludes(tool, field, `manager research loop tool covers ${field}`)
}

assertIncludes(tool, '经理任期切片', 'tool names tenure slicing')
assertIncludes(tool, '共管产品拆分', 'tool names co-managed product split')
assertIncludes(tool, '代表作归因', 'tool names representative attribution')
assertIncludes(tool, '风格漂移', 'tool names style drift')
assertIncludes(tool, '离任/接任影响', 'tool names departure/succession impact')
assertIncludes(tool, '团队平台贡献', 'tool names team platform contribution')
assertIncludes(tool, '不得把公司名气或经理名气直接当成基金结论', 'tool blocks manager fame shortcut')
assertIncludes(tool, '不能进行经理归因闭环评价', 'tool hard-blocks missing tenure')
assertIncludes(tool, 'FUND_RESEARCH_GUARDRAILS.noTradingDirective', 'tool keeps research-only guardrail')
assertNotIncludes(tool, '购买建议', 'tool must not output purchase advice')

assertIncludes(registry, 'managerResearchLoopTool', 'tool registry includes manager research loop')
assertIncludes(index, 'ManagerResearchLoopOutput', 'tool index exports manager research loop types')

console.log('OK manager research loop foundation is modeled, tooled, and registered')
