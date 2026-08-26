import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    encoding: 'utf8',
    stdio: options.stdio || 'pipe',
    env: options.env || process.env,
    cwd: options.cwd || process.cwd(),
  })
  if (result.error) throw result.error
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(' ')} failed\n${result.stderr || result.stdout}`)
  }
  return result.stdout.trim()
}

function commandExists(command) {
  const result = spawnSync('bash', ['-lc', `command -v ${command}`], { encoding: 'utf8' })
  return result.status === 0
}

function assertEqual(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label}: expected ${expected}, got ${actual}`)
}

function assertAtLeast(actual, expected, label) {
  if (actual < expected) throw new Error(`${label}: expected at least ${expected}, got ${actual}`)
}

if (!commandExists('initdb') || !commandExists('pg_ctl') || !commandExists('createdb') || !commandExists('psql')) {
  console.log('SKIP research taxonomy peer groups database smoke: PostgreSQL CLI not installed')
  process.exit(0)
}

const root = process.cwd()
const pgdata = mkdtempSync(join(tmpdir(), 'fund-taxonomy-peer-db-smoke-'))
const port = String(Number(process.env.TAXONOMY_SMOKE_PGPORT || 55435))
const databaseName = 'fund_taxonomy_peer_smoke'
const databaseUrl = `postgresql://postgres@localhost:${port}/${databaseName}`
let started = false

try {
  run('initdb', ['-D', pgdata, '-U', 'postgres', '--auth=trust'])
  run('pg_ctl', ['-D', pgdata, '-l', `${pgdata}.log`, '-o', `-p ${port}`, 'start'])
  started = true
  run('createdb', ['-U', 'postgres', '-h', 'localhost', '-p', port, databaseName])
  run('psql', [databaseUrl, '-v', 'ON_ERROR_STOP=1', '-c', 'CREATE TABLE funds (id text PRIMARY KEY, wind_code text UNIQUE);'])
  run('psql', [databaseUrl, '-v', 'ON_ERROR_STOP=1', '-f', 'scripts/seed_research_taxonomy_peer_groups.sql'])
  run('psql', [databaseUrl, '-v', 'ON_ERROR_STOP=1', '-f', 'scripts/seed_research_taxonomy_peer_groups.sql'])

  const payload = run(process.execPath, ['--input-type=module', '-e', `
    const postgres = (await import('postgres')).default
    const sql = postgres(${JSON.stringify(databaseUrl)}, { max: 1 })
    const rows = await sql\`
      SELECT json_build_object(
        'families', (SELECT count(*)::int FROM strategy_families WHERE source = 'research_taxonomy_seed'),
        'entities', (SELECT count(*)::int FROM fund_entities WHERE source = 'research_taxonomy_seed'),
        'shareClasses', (SELECT count(*)::int FROM fund_share_classes WHERE source = 'research_taxonomy_seed'),
        'peerGroups', (SELECT count(*)::int FROM peer_groups WHERE source = 'research_taxonomy_seed'),
        'members', (SELECT count(*)::int FROM peer_group_members WHERE source = 'research_taxonomy_seed'),
        'memberLinks', (
          SELECT count(*)::int
          FROM peer_group_members pgm
          JOIN peer_groups pg ON pg.id = pgm.peer_group_id
          JOIN fund_entities fe ON fe.id = pgm.entity_id
          JOIN strategy_families sf ON sf.id = fe.strategy_family_id
          WHERE pg.strategy_family_id = sf.id
        ),
        'indexBenchmark', (
          SELECT benchmark_code
          FROM peer_groups
          WHERE key = 'peer-index-hs300'
        ),
        'equityPeerLayers', (
          SELECT inclusion_rules->'layers'
          FROM peer_groups
          WHERE key = 'peer-active-equity-core-large-5y'
        )
      ) AS data
    \`
    await sql.end()
    console.log(JSON.stringify(rows[0].data))
  `], { cwd: root, env: { ...process.env, DATABASE_URL: databaseUrl } })

  const data = JSON.parse(payload)
  assertEqual(data.families, 6, 'strategy family count')
  assertEqual(data.entities, 12, 'fund entity count')
  assertEqual(data.shareClasses, 12, 'share class count')
  assertEqual(data.peerGroups, 10, 'peer group count')
  assertEqual(data.members, 12, 'peer group member count')
  assertEqual(data.memberLinks, 12, 'peer group members link to matching strategy families')
  assertEqual(data.indexBenchmark, '000300.SH', 'index peer benchmark')
  assertAtLeast(Object.keys(data.equityPeerLayers || {}).length, 4, 'equity peer layers')

  console.log('OK research taxonomy peer groups load into database with explainable links')
} finally {
  if (started) {
    spawnSync('pg_ctl', ['-D', pgdata, 'stop'], { encoding: 'utf8' })
  }
  rmSync(pgdata, { recursive: true, force: true })
  if (existsSync(`${pgdata}.log`)) rmSync(`${pgdata}.log`, { force: true })
}
