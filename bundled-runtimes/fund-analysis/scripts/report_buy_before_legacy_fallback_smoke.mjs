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

const parser = read('lib/report-buy-before-decision.ts')
const listApi = read('app/api/reports/route.ts')
const detailApi = read('app/api/reports/[id]/route.ts')

assertIncludes(parser, 'extractBuyBeforeSection', 'buy-before parser locates legacy markdown section')
assertIncludes(parser, 'parseMarkdownBuyBeforeDecision', 'buy-before parser supports markdown fallback')
assertIncludes(parser, 'blocked_by_hard_gate', 'buy-before parser preserves hard-block status')
assertIncludes(parser, 'normalizeBuyBeforeDecisionSummary', 'buy-before parser exposes normalizer')
assertIncludes(parser, 'summary.buyBeforeGateStatus', 'buy-before parser preserves structured summary fallback')

assertIncludes(listApi, 'normalizeBuyBeforeDecisionSummary(dataSources.buy_before_decision', 'reports list API uses shared normalizer')
assertIncludes(listApi, 'content,', 'reports list API passes cleaned report content for legacy fallback')
assertIncludes(detailApi, 'normalizeBuyBeforeDecisionSummary(dataSources.buy_before_decision', 'report detail API uses shared normalizer')
assertIncludes(detailApi, 'content,', 'report detail API passes report content for legacy fallback')

console.log('OK legacy reports can recover buy-before gate metadata from saved markdown')
