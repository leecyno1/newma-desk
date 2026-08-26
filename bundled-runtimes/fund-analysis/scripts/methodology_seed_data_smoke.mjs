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

function assertNotIncludes(content, unexpected, label) {
  if (content.includes(unexpected)) throw new Error(`${label} should not include: ${unexpected}`)
}

const seed = read('scripts/seed_methodology_config.sql')
const startLocal = read('scripts/start-local-postgres.sh')
const runAudit = read('scripts/run_completion_audit.sh')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

for (const tableName of [
  'research_methodology_templates',
  'research_methodology_dimensions',
  'research_methodology_mappings',
]) {
  assertIncludes(seed, `CREATE TABLE IF NOT EXISTS ${tableName}`, `methodology seed creates ${tableName}`)
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
  assertIncludes(seed, `'${templateKey}'`, `methodology seed includes ${templateKey}`)
}

for (const dimension of [
  '基准与归因',
  '同类池',
  '持仓穿透',
  '基金经理',
  '基金公司',
  '费用与跟踪误差',
  '信用暴露',
  '久期与曲线暴露',
  '规模与流动性',
  '收益竞争力',
  '本金保护',
  '汇率与区域暴露',
  '底层基金穿透',
  '资产配置归因',
  '模型稳定性',
]) {
  assertIncludes(seed, dimension, `methodology seed covers ${dimension}`)
}

for (const idempotentClause of [
  'ON CONFLICT (key) DO UPDATE SET',
  'ON CONFLICT (template_id, dimension_key) DO UPDATE SET',
  'ON CONFLICT (id) DO UPDATE SET',
]) {
  assertIncludes(seed, idempotentClause, `methodology seed is idempotent via ${idempotentClause}`)
}

for (const phrase of [
  '方法论模板只决定研究口径',
  '不输出交易执行',
  '不输出交易执行或组合动作',
]) {
  assertIncludes(seed, phrase, `methodology seed keeps research boundary: ${phrase}`)
}

assertNotIncludes(seed, '投委会', 'methodology seed must not add governance workflow')
assertNotIncludes(seed, '购买建议', 'methodology seed must not add purchase advice')
assertNotIncludes(seed, '申购建议', 'methodology seed must not add subscription advice')
assertNotIncludes(seed, '赎回建议', 'methodology seed must not add redemption advice')

assertIncludes(startLocal, 'scripts/seed_methodology_config.sql', 'local postgres startup imports methodology seed')
assertIncludes(runAudit, 'scripts/seed_methodology_config.sql', 'completion audit imports methodology seed')
assertIncludes(acceptance, 'scripts/methodology_seed_data_smoke.mjs', 'fund research acceptance includes methodology seed smoke')

console.log('OK methodology seed data is durable, idempotent, and research-scoped')
