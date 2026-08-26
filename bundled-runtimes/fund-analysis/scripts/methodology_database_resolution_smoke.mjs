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

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) throw new Error(`${label} missing: ${expected}`)
}

if (!commandExists('initdb') || !commandExists('pg_ctl') || !commandExists('createdb') || !commandExists('psql')) {
  console.log('SKIP methodology database resolution smoke: PostgreSQL CLI not installed')
  process.exit(0)
}

const root = process.cwd()
const pgdata = mkdtempSync(join(tmpdir(), 'fund-methodology-db-smoke-'))
const port = String(Number(process.env.METHODOLOGY_SMOKE_PGPORT || 55434))
const databaseName = 'fund_methodology_resolution_smoke'
const databaseUrl = `postgresql://postgres@localhost:${port}/${databaseName}`
let started = false

try {
  run('initdb', ['-D', pgdata, '-U', 'postgres', '--auth=trust'])
  run('pg_ctl', ['-D', pgdata, '-l', `${pgdata}.log`, '-o', `-p ${port}`, 'start'])
  started = true
  run('createdb', ['-U', 'postgres', '-h', 'localhost', '-p', port, databaseName])
  run('psql', [databaseUrl, '-v', 'ON_ERROR_STOP=1', '-f', 'scripts/seed_methodology_config.sql'])

  const resolution = run(process.execPath, ['--input-type=module', '-e', `
    const postgres = (await import('postgres')).default
    const sql = postgres(${JSON.stringify(databaseUrl)}, { max: 1 })
    const cases = [
      ['bond', '债券 固收', 'active', 'fixed_income', 6],
      ['index', '指数 ETF', 'passive', 'index_fund', 6],
      ['money', '货币 现金管理', 'active', 'money_market', 5],
      ['qdii', '全球 QDII', 'active', 'qdii', 6],
      ['fof', 'FOF 养老', 'active', 'fof', 6],
      ['quant', '量化 指数增强', 'active', 'quant_fund', 6],
    ]
    const outputs = []
    for (const [fundType, assetClass, activePassive, expected, expectedDimensions] of cases) {
      const rows = await sql\`
        SELECT
          t.key,
          t.source,
          m.priority,
          m.match_rules,
          (
            CASE WHEN lower(coalesce(m.fund_type, '')) = lower(\${fundType}) THEN 4 ELSE 0 END +
            CASE WHEN lower(coalesce(m.asset_class, '')) = lower(\${assetClass}) THEN 3 ELSE 0 END +
            CASE WHEN lower(coalesce(m.active_passive, '')) = lower(\${activePassive}) THEN 2 ELSE 0 END +
            CASE WHEN lower(coalesce(m.match_rules::text, '')) LIKE '%' || lower(\${assetClass}) || '%' THEN 1 ELSE 0 END
          ) AS score,
          (
            SELECT count(*)
            FROM research_methodology_dimensions d
            WHERE d.template_id = t.id
          )::int AS dimensions
        FROM research_methodology_mappings m
        JOIN research_methodology_templates t ON t.id = m.template_id
        WHERE t.is_active = true
        ORDER BY score DESC, m.priority ASC
        LIMIT 1
      \`
      outputs.push({
        expected,
        expectedDimensions,
        actual: rows[0]?.key,
        source: rows[0]?.source,
        dimensions: rows[0]?.dimensions,
        score: Number(rows[0]?.score || 0),
      })
    }
    await sql.end()
    console.log(JSON.stringify(outputs))
  `], { cwd: root, env: { ...process.env, DATABASE_URL: databaseUrl } })

  const outputs = JSON.parse(resolution)
  for (const output of outputs) {
    assertEqual(output.source, 'methodology_seed', `${output.expected} template source`)
    assertEqual(output.actual, output.expected, `${output.expected} template resolution`)
    assertEqual(output.dimensions, output.expectedDimensions, `${output.expected} dimensions`)
    if (output.score <= 0) throw new Error(`${output.expected} should match by seeded database rules`)
  }

  console.log('OK methodology database resolution uses seeded database mappings')
} finally {
  if (started) {
    spawnSync('pg_ctl', ['-D', pgdata, 'stop'], { encoding: 'utf8' })
  }
  rmSync(pgdata, { recursive: true, force: true })
  if (existsSync(`${pgdata}.log`)) rmSync(`${pgdata}.log`, { force: true })
}
