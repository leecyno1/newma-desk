import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const detailClient = readFileSync(join(root, 'app/(dashboard)/funds/[id]/SimpleFundDetailClient.tsx'), 'utf8')
const comparisonReport = readFileSync(join(root, 'lib/fund-comparison-report.ts'), 'utf8')
const comparisonScoreTool = readFileSync(join(root, 'lib/research-platform/tools/comparison-research-score.ts'), 'utf8')

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
  ['fund detail', detailClient],
  ['comparison report', comparisonReport],
]) {
  assertNotIncludes(content, 'professionalScore ?? 50', label)
  assertNotIncludes(content, '专业评分待补，用中性分参与买前研究分。', label)
  assertNotIncludes(content, '专业评分待补，按 50 分中性处理', label)
}

// 详情页现行边界：专业评分就绪才渲染评分与排名，样本不足时不输出综合分。
assertIncludes(detailClient, 'const professionalScoreReady = evaluation.score != null', 'fund detail professional readiness flag')
assertIncludes(detailClient, '{professionalScoreReady ? <EvaluationDetailPanel evaluation={evaluation} /> : null}', 'fund detail hides score panel when professional score is missing')
assertIncludes(detailClient, '样本不足时不输出综合分和排名', 'fund detail refuses scores under peer sample gates')
assertIncludes(comparisonScoreTool, 'const professionalScoreMissing = item.professionalScore === null', 'comparison professional missing flag')
assertIncludes(comparisonScoreTool, 'const professionalScore = professionalScoreMissing ? 0 : item.professionalScore as number', 'comparison no professional missing score boost')
assertIncludes(comparisonScoreTool, '专业评分缺失，研究评分封顶 65', 'comparison professional missing cap')
assertIncludes(comparisonScoreTool, '专业评分待补，本项不加分，并触发横评分封顶', 'comparison professional missing explanation')

console.log('OK missing professional scores no longer receive neutral purchase-decision credit')
