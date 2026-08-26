import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) throw new Error(`Missing required file: ${relativePath}`)
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) throw new Error(`${label} missing text: ${expected}`)
}

function assertNotIncludes(content, forbidden, label) {
  if (content.includes(forbidden)) throw new Error(`${label} should not include: ${forbidden}`)
}

const repository = read('lib/research-platform/methodology-mapping-repository.ts')
const reportLib = read('lib/research-review-report.ts')

assertIncludes(repository, 'research_methodology_templates', 'repository reads methodology templates table')
assertIncludes(repository, 'research_methodology_dimensions', 'repository reads methodology dimensions table')
assertIncludes(repository, 'research_methodology_mappings', 'repository reads methodology mappings table')
assertIncludes(repository, 'resolveMethodologyConfigFromData', 'repository exposes data-first resolver')
assertIncludes(repository, 'methodologyConfigTool.run', 'repository falls back to default methodology tool')
assertIncludes(repository, 'matchMethodologyTemplateFromRows', 'repository matches rows by priority')
assertIncludes(repository, 'unclassifiedMethodologyOutput', 'repository stops when classification mapping is unknown')
assertIncludes(repository, 'mappingCandidates[0].categoryScore > 0', 'database matching requires category evidence')
assertNotIncludes(repository, "fallbackOutputForKey('active_equity')", 'repository must not default unknown classifications to active equity')
assertIncludes(repository, 'DATABASE_URL', 'repository uses local database when configured')
assertIncludes(repository, '方法论模板只决定研究口径', 'repository preserves methodology boundary')
assertNotIncludes(repository, '投委会', 'repository must not add governance workflow')

assertIncludes(reportLib, 'resolveMethodologyConfigFromDataSync', 'report uses sync methodology repository fallback')

console.log('OK methodology mapping repository provides data-first methodology resolution')
