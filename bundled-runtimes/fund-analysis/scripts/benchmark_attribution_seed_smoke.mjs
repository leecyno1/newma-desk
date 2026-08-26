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

const seed = read('scripts/seed_benchmark_attribution.sql')
const startLocal = read('scripts/start-local-postgres.sh')
const runAudit = read('scripts/run_completion_audit.sh')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

for (const tableName of ['benchmark_mappings', 'attribution_explanations']) {
  assertIncludes(seed, `CREATE TABLE IF NOT EXISTS ${tableName}`, `benchmark attribution seed creates ${tableName}`)
}

for (const benchmark of [
  'CSI800',
  'CSI_TECH',
  'CBA_CREDIT',
  '000300.SH',
  'MSCI_GLOBAL_CONSUMER',
]) {
  assertIncludes(seed, `'${benchmark}'`, `benchmark attribution seed maps ${benchmark}`)
}

for (const dimension of [
  '基准映射',
  '超额收益',
  '配置效应',
  '选择效应',
  '风格',
  '行业',
  '资产配置',
  '残差',
  '不能包装为能力',
]) {
  assertIncludes(seed, dimension, `benchmark attribution seed covers ${dimension}`)
}

assertIncludes(seed, 'ON CONFLICT (entity_id, benchmark_code, effective_from) DO UPDATE SET', 'benchmark mapping seed is idempotent')
assertIncludes(seed, 'ON CONFLICT (entity_id, period_start, period_end, benchmark_mapping_id) DO UPDATE SET', 'attribution explanation seed is idempotent')
assertNotIncludes(seed, '投委会', 'benchmark attribution seed must not add governance workflow')
assertNotIncludes(seed, '购买建议', 'benchmark attribution seed must not add purchase advice')

assertIncludes(startLocal, 'scripts/seed_benchmark_attribution.sql', 'local postgres startup imports benchmark attribution seed')
assertIncludes(runAudit, 'scripts/seed_benchmark_attribution.sql', 'completion audit imports benchmark attribution seed')
assertIncludes(acceptance, 'scripts/benchmark_attribution_seed_smoke.mjs', 'fund research acceptance includes benchmark attribution seed smoke')

console.log('OK benchmark attribution seed is durable and research-scoped')
