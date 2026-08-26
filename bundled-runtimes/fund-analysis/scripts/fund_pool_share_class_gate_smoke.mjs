import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))

function read(relativePath) {
  const fullPath = join(root, relativePath)
  if (!existsSync(fullPath)) {
    throw new Error(`Missing required file: ${relativePath}`)
  }
  return readFileSync(fullPath, 'utf8')
}

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) {
    throw new Error(`${label} missing text: ${expected}`)
  }
}

const memberCreateRoute = read('app/api/market/research-lists/[id]/members/route.ts')
const memberPatchRoute = read('app/api/market/research-lists/members/[memberId]/route.ts')

for (const [content, label] of [[memberCreateRoute, 'create'], [memberPatchRoute, 'patch']]) {
  assertIncludes(content, 'shareClassEvidence', `fund pool ${label} gate reads share-class evidence`)
  assertIncludes(content, 'shareClassDecision', `fund pool ${label} gate reads share-class decision`)
  assertIncludes(content, 'const shareClassSiblingCount = Number(', `fund pool ${label} gate counts sibling share classes`)
  assertIncludes(content, 'const shareClassFormalChoiceReady = evidence', `fund pool ${label} gate reads formal share-class readiness`)
  assertIncludes(content, 'shareClassSiblingCount) && shareClassSiblingCount > 0 && !shareClassFormalChoiceReady', `fund pool ${label} gate only blocks detected multi-share funds`)
  assertIncludes(content, '同基金多份额正式选择未完成，不能把核查顺序当成研究候选', `research list ${label} gate blocks tentative share-class order`)
}

console.log('OK fund pool promotion blocks multi-share candidates without formal share-class choice')
