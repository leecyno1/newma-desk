import { existsSync, readFileSync } from 'node:fs'
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
  if (content.includes(forbidden)) throw new Error(`${label} must not include duplicate source of truth: ${forbidden}`)
}

const registry = read('lib/research-platform/open-source-references.ts')
const index = read('lib/research-platform/index.ts')
const coreModules = read('lib/research-platform/core-modules.ts')
const architecture = read('docs/architecture/professional-fund-research-architecture.md')

for (const expected of [
  'openSourceReuseReferences',
  'openSourceReferencesForModule',
  'OpenBB Open Data Platform',
  'AKShare',
  'FinanceToolkit',
  'QuantStats / empyrical',
  'QuantStats tear sheet patterns',
  'FinRobot',
  'Anthropic financial services prompt patterns',
  'a-stock-data skill',
  'candidateModules',
  'boundary',
  'adopt-as-adapter-pattern',
  'reuse-metric-definition',
  'reuse-agent-orchestration-pattern',
]) {
  assertIncludes(registry, expected, `open-source reuse registry records ${expected}`)
}

for (const moduleId of [
  'data-ingestion',
  'research-universe',
  'evidence-ledger',
  'holding-exposure',
  'manager-and-company-research',
  'peer-comparison',
  'research-report-lifecycle',
]) {
  assertIncludes(registry, moduleId, `open-source reuse registry maps module ${moduleId}`)
}

assertIncludes(index, "export * from './open-source-references'", 'research platform exports open-source reuse registry')
assertIncludes(coreModules, 'openSourceReuseReferences as reusableOpenSourceReferences', 'core modules keeps compatibility alias')
assertNotIncludes(coreModules, "name: 'OpenBB'", 'core modules no longer owns duplicated OSS list')
assertIncludes(architecture, 'lib/research-platform/open-source-references.ts', 'architecture points to the reusable OSS registry')
assertIncludes(architecture, 'Anthropic financial-services prompt patterns', 'architecture records financial-services prompt reuse boundary')

console.log('OK open-source reuse decisions are centralized and guarded by research module boundaries')
