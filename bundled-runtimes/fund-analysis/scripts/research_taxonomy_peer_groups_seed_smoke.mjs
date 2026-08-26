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

const seed = read('scripts/seed_research_taxonomy_peer_groups.sql')
const startLocal = read('scripts/start-local-postgres.sh')
const runAudit = read('scripts/run_completion_audit.sh')
const acceptance = read('scripts/fund_research_acceptance_smoke.mjs')

for (const tableName of [
  'strategy_families',
  'fund_entities',
  'fund_share_classes',
  'peer_groups',
  'peer_group_members',
]) {
  assertIncludes(seed, `CREATE TABLE IF NOT EXISTS ${tableName}`, `taxonomy seed creates ${tableName}`)
}

for (const familyKey of [
  'active_equity_core',
  'active_equity_sector',
  'fixed_income_credit',
  'index_broad',
  'qdii_global_theme',
  'cash_management',
]) {
  assertIncludes(seed, `'${familyKey}'`, `taxonomy seed includes strategy family ${familyKey}`)
}

for (const peerGroupKey of [
  'peer-active-equity-core-large-5y',
  'peer-active-equity-sector-mid-3y',
  'peer-fixed-income-credit-mid-duration',
  'peer-index-hs300',
  'peer-money-cash-management',
  'peer-qdii-global-consumption',
]) {
  assertIncludes(seed, `'${peerGroupKey}'`, `taxonomy seed includes peer group ${peerGroupKey}`)
}

for (const phrase of [
  '基金实体',
  '同一主从份额以 fund_entities 为研究主对象',
  '同类池',
  '策略族谱',
  '资产类别',
  '主动/被动',
  '规模',
  '成立年限',
]) {
  assertIncludes(seed, phrase, `taxonomy seed covers ${phrase}`)
}

assertIncludes(seed, 'ON CONFLICT (canonical_code) DO UPDATE SET', 'taxonomy seed upserts entities')
assertIncludes(seed, 'ON CONFLICT (key) DO UPDATE SET', 'taxonomy seed upserts strategy families and peer groups')
assertIncludes(seed, 'ON CONFLICT (peer_group_id, entity_id) DO UPDATE SET', 'taxonomy seed upserts peer memberships')
assertNotIncludes(seed, '投委会', 'taxonomy seed must not add governance workflow')
assertNotIncludes(seed, '购买建议', 'taxonomy seed must not add purchase advice')

assertIncludes(startLocal, 'scripts/seed_research_taxonomy_peer_groups.sql', 'local postgres startup imports taxonomy seed')
assertIncludes(runAudit, 'scripts/seed_research_taxonomy_peer_groups.sql', 'completion audit imports taxonomy seed')
assertIncludes(acceptance, 'scripts/research_taxonomy_peer_groups_seed_smoke.mjs', 'fund research acceptance includes taxonomy seed smoke')

console.log('OK research taxonomy and peer groups seed is durable and research-scoped')
