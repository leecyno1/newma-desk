import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const root = process.cwd()

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) throw new Error(`${label}: missing ${expected}`)
}

const page = read('app/(dashboard)/research/ResearchLibraryClient.tsx')
const backendMain = read('backend/main.py')
const memoRepo = read('backend/repositories/local_research_folder_repo.py')

for (const expected of [
  '本地文件夹路径',
  '已连接',
  'research-folder-select',
  '扫描更新',
  '上次扫描',
  '新增',
  '已更新',
  '未变化',
  '失败',
  '待确认',
  '确认',
  '拒绝',
  '来源原文',
  '经理归类',
  '确认唯一经理',
  '多人纪要',
  '确认高置信标签',
  '当前只识别基金经理、基金代码和原文明示的分类/风格字段',
  '不会把普通关键词当成已确认风格',
]) {
  assertIncludes(page, expected, 'research library user flow')
}

for (const expected of [
  "fetch('/api/research-folders'",
  '/scan`, { method: \'POST\' }',
  "fetch('/api/research-folders/reviews'",
  "fetch('/api/research-folders/reviews/confirm-managers'",
  "fetch('/api/research-folders/reviews/confirm-labels'",
  "method: 'PATCH'",
]) {
  assertIncludes(page, expected, 'research library API wiring')
}

assertIncludes(backendMain, 'research_folders', 'backend registers local folder routes')
for (const expected of ['llm_extraction_status', 'extraction_provider', 'extraction_model', 'llm_extraction_error']) {
  assertIncludes(memoRepo, expected, 'memo storage exposes extraction provenance')
}

for (const route of [
  'app/api/research-folders/route.ts',
  'app/api/research-folders/[folderId]/scan/route.ts',
  'app/api/research-folders/reviews/route.ts',
  'app/api/research-folders/reviews/confirm-managers/route.ts',
  'app/api/research-folders/reviews/confirm-labels/route.ts',
  'app/api/research-folders/reviews/[reportId]/[proposalId]/route.ts',
]) {
  if (!fs.existsSync(path.join(root, route))) throw new Error(`missing Next.js API bridge: ${route}`)
}

if (/webkitdirectory|type="file"|\.doc\b/u.test(page)) {
  throw new Error('research library should use durable server-side folder indexing and must not advertise legacy .doc parsing')
}

console.log('OK research library exposes durable scan status and evidence review workflow')
