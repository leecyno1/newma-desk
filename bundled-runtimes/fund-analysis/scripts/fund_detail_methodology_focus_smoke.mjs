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

const detailClient = read('app/(dashboard)/funds/[id]/FundDetailClient.tsx')

assertIncludes(detailClient, 'methodologyConfigTool', 'fund detail imports methodology config tool')
assertIncludes(detailClient, 'buildFundDetailMethodologyFocus', 'fund detail builds methodology focus')
assertIncludes(detailClient, 'fund-detail-methodology-focus', 'fund detail renders methodology focus card')
assertIncludes(detailClient, '研究模板', 'fund detail labels research template')
assertIncludes(detailClient, '核心研究维度', 'fund detail lists core research dimensions')
assertIncludes(detailClient, '方法论缺口', 'fund detail lists methodology gaps')
assertIncludes(detailClient, 'methodologyFocus.tsvRows', 'fund detail exports methodology focus to TSV')
assertIncludes(detailClient, '方法论模板只决定研究口径', 'fund detail preserves methodology boundary')
assertNotIncludes(detailClient, '投委会', 'fund detail methodology focus must not add governance workflow')

console.log('OK fund detail page focuses evidence by methodology template')
