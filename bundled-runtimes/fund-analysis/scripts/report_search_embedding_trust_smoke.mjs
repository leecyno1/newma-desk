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
// 写路径与读路径同库（PostgreSQL）：上传的报告立即可在报告列表/搜索中查到，
// 不再有 Mongo 写 / PG 读 的存储割裂。
assertNotIncludes(researchReportsRoute, 'from service_registry import get_db', 'research report writes must not depend on MongoDB')
assertNotIncludes(researchReportsRoute, 'db.research_reports.insert_one', 'research report writes must go to PostgreSQL')
assertIncludes(researchReportsRoute, 'PostgresLocalResearchFolderRepo().create_report(', 'research report create persists to PostgreSQL')
assertIncludes(researchReportsRoute, 'PostgresLocalResearchFolderRepo().update_report(', 'research report update persists to PostgreSQL')
assertIncludes(researchReportsRoute, 'PostgresLocalResearchFolderRepo().delete_report(', 'research report delete persists to PostgreSQL')
assertIncludes(researchReportsRoute, '"embedding_status": "available" if embedding else "unavailable"', 'research report stores embedding status')
assertIncludes(researchReportsRoute, '"embedding_source": "openai_compatible" if embedding else "keyword_only_no_mock"', 'research report stores keyword-only source')
assertIncludes(reportSearchRoute, "mode: 'local_full_text'", 'report search BFF discloses keyword search mode')

console.log('OK report search refuses random embeddings and falls back to disclosed keyword search')
