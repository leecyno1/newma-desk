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
const migration = read('prisma/migrations/20260614000300_company_research_foundation/migration.sql')
const tool = read('lib/research-platform/tools/company-research.ts')
const registry = read('lib/research-platform/tools/registry.ts')
const index = read('lib/research-platform/tools/index.ts')

for (const modelName of [
  'model FundCompanyResearchProfile',
  'model FundProductLineResearchSnapshot',
  'model FundCompanyResearchEvent',
]) {
  assertIncludes(schema, modelName, `schema includes ${modelName}`)
}

for (const tableName of [
  'fund_company_research_profiles',
  'fund_product_line_research_snapshots',
  'fund_company_research_events',
]) {
  assertIncludes(migration, `CREATE TABLE "${tableName}"`, `migration creates ${tableName}`)
}

for (const field of [
  'productLines',
  'researchTeam',
  'platformCapabilityScore',
  'scaleTrend',
  'sameCompanyReviewCount',
  'issuanceCount',
  'liquidationCount',
  'scaleChange',
  'productLineReview',
]) {
  assertIncludes(tool, field, `company research tool covers ${field}`)
}

assertIncludes(tool, '产品线', 'tool names product line research')
assertIncludes(tool, '投研团队', 'tool names research team')
assertIncludes(tool, '平台能力', 'tool names platform capability')
assertIncludes(tool, '发行/清盘/规模变化', 'tool names issuance liquidation and scale change')
assertIncludes(tool, '同公司产品横评', 'tool names same-company product review')
assertIncludes(tool, '不能把公司品牌直接当成基金质量结论', 'tool blocks brand shortcut')
assertIncludes(tool, '不得把基金公司品牌、规模或单一明星经理直接外推为单基金研究结论', 'tool blocks company-level overreach')
assertIncludes(tool, 'FUND_RESEARCH_GUARDRAILS.noTradingDirective', 'tool keeps research-only guardrail')
assertNotIncludes(tool, '购买建议', 'tool must not output purchase advice')

assertIncludes(registry, 'companyResearchTool', 'tool registry includes company research')
assertIncludes(index, 'CompanyResearchOutput', 'tool index exports company research types')

console.log('OK fund company research foundation is modeled, tooled, and registered')
