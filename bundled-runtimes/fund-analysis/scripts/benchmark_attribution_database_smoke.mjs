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
  console.log('SKIP benchmark attribution database smoke: PostgreSQL CLI not installed')
  process.exit(0)
}

const root = process.cwd()
const pgdata = mkdtempSync(join(tmpdir(), 'fund-benchmark-attribution-db-smoke-'))
const port = String(Number(process.env.BENCHMARK_ATTRIBUTION_SMOKE_PGPORT || 55436))
const databaseName = 'fund_benchmark_attribution_smoke'
const databaseUrl = `postgresql://postgres@localhost:${port}/${databaseName}`
let started = false

try {
  run('initdb', ['-D', pgdata, '-U', 'postgres', '--auth=trust'])
  run('pg_ctl', ['-D', pgdata, '-l', `${pgdata}.log`, '-o', `-p ${port}`, 'start'])
  started = true
  run('createdb', ['-U', 'postgres', '-h', 'localhost', '-p', port, databaseName])
  run('psql', [databaseUrl, '-v', 'ON_ERROR_STOP=1', '-c', 'CREATE TABLE funds (id text PRIMARY KEY, wind_code text UNIQUE);'])
  run('psql', [databaseUrl, '-v', 'ON_ERROR_STOP=1', '-f', 'scripts/seed_research_taxonomy_peer_groups.sql'])
  run('psql', [databaseUrl, '-v', 'ON_ERROR_STOP=1', '-f', 'scripts/seed_benchmark_attribution.sql'])
  run('psql', [databaseUrl, '-v', 'ON_ERROR_STOP=1', '-f', 'scripts/seed_benchmark_attribution.sql'])

  const payload = run(process.execPath, ['--input-type=module', '-e', `
    const postgres = (await import('postgres')).default
    const sql = postgres(${JSON.stringify(databaseUrl)}, { max: 1 })
    const rows = await sql\`
      SELECT json_build_object(
        'mappings', (SELECT count(*)::int FROM benchmark_mappings WHERE source = 'benchmark_attribution_seed'),
        'attributions', (SELECT count(*)::int FROM attribution_explanations WHERE quality_status = 'reviewable'),
        'linkedAttributions', (
          SELECT count(*)::int
          FROM attribution_explanations ae
          JOIN benchmark_mappings bm ON bm.id = ae.benchmark_mapping_id
          JOIN fund_entities fe ON fe.id = ae.entity_id
          WHERE bm.entity_id = fe.id
        ),
        'positiveExcess', (
          SELECT count(*)::int
          FROM attribution_explanations
          WHERE excess_return > 0
        ),
        'residualWarnings', (
          SELECT count(*)::int
          FROM attribution_explanations
          WHERE residual_explanation LIKE '%不能包装为能力%'
             OR residual_explanation LIKE '%不能直接归因为能力%'
        ),
        'hs300Mapping', (
          SELECT benchmark_name
          FROM benchmark_mappings
          WHERE benchmark_code = '000300.SH'
        ),
        'equityStyleCount', (
          SELECT jsonb_array_length(style_contribution)
          FROM attribution_explanations ae
          JOIN benchmark_mappings bm ON bm.id = ae.benchmark_mapping_id
          WHERE bm.benchmark_code = 'CSI800'
          ORDER BY ae.excess_return DESC
          LIMIT 1
        )
      ) AS data
    \`
    await sql.end()
    console.log(JSON.stringify(rows[0].data))
  `], { cwd: root, env: { ...process.env, DATABASE_URL: databaseUrl } })

  const data = JSON.parse(payload)
  assertEqual(data.mappings, 12, 'benchmark mapping count')
  assertEqual(data.attributions, 7, 'attribution explanation count')
  assertEqual(data.linkedAttributions, 7, 'attributions link to entity and benchmark')
  assertAtLeast(data.positiveExcess, 5, 'positive excess sample count')
  assertAtLeast(data.residualWarnings, 2, 'residual warning count')
  assertEqual(data.hs300Mapping, '沪深300', 'HS300 benchmark mapping')
  assertAtLeast(data.equityStyleCount, 2, 'equity style contribution count')

  console.log('OK benchmark attribution loads into database with linked explanations')
} finally {
  if (started) {
    spawnSync('pg_ctl', ['-D', pgdata, 'stop'], { encoding: 'utf8' })
  }
  rmSync(pgdata, { recursive: true, force: true })
  if (existsSync(`${pgdata}.log`)) rmSync(`${pgdata}.log`, { force: true })
}
