import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const searchService = readFileSync(join(root, 'backend/services/search_service.py'), 'utf8')
const researchReportsRoute = readFileSync(join(root, 'backend/routes/research_reports.py'), 'utf8')
const reportSearchRoute = readFileSync(join(root, 'app/api/reports/search/route.ts'), 'utf8')

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) {
    throw new Error(`${label} missing text: ${expected}`)
  }
}

function assertNotIncludes(content, expected, label) {
  if (content.includes(expected)) {
    throw new Error(`${label} must not include text: ${expected}`)
  }
}

for (const [label, content] of [
  ['search service', searchService],
  ['research reports route', researchReportsRoute],
]) {
  assertNotIncludes(content, 'random.uniform', label)
  assertNotIncludes(content, 'import random', label)
  assertNotIncludes(content, '_mock_embedding', label)
}

assertIncludes(searchService, 'return None', 'embedding service returns unavailable instead of mock')
assertIncludes(searchService, 'Semantic search unavailable; falling back to keyword search only', 'search service keyword-only fallback')
assertIncludes(searchService, 'Optional[List[float]]', 'search service nullable embedding contract')
assertIncludes(researchReportsRoute, '"embedding_status": "available" if embedding else "unavailable"', 'research report stores embedding status')
assertIncludes(researchReportsRoute, '"embedding_source": "openai_compatible" if embedding else "keyword_only_no_mock"', 'research report stores keyword-only source')
assertIncludes(reportSearchRoute, "mode: 'local_full_text'", 'report search BFF discloses keyword search mode')

console.log('OK report search refuses random embeddings and falls back to disclosed keyword search')
