import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const comparisonPage = readFileSync(join(root, 'app/(dashboard)/analysis/comparison/page.tsx'), 'utf8')
const comparisonReport = readFileSync(join(root, 'lib/fund-comparison-report.ts'), 'utf8')
const comparisonReportMarkdown = readFileSync(join(root, 'lib/fund-comparison-report-markdown.ts'), 'utf8')
const comparisonScoreTool = readFileSync(join(root, 'lib/research-platform/tools/comparison-research-score.ts'), 'utf8')
const comparisonReportRoute = readFileSync(join(root, 'app/api/funds/comparison-report/route.ts'), 'utf8')

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

for (const [label, content, replayCopy, scoreCapCopy] of [
  ['comparison page', comparisonPage, '持有体验回放缺失，本项不加分，并触发决策分封顶', '持有体验回放缺失，决策分封顶 68'],
  ['comparison score tool', comparisonScoreTool, '历史回放缺失，本项不加分，并触发研究评分封顶', '历史回放缺失，研究评分封顶 68'],
]) {
  assertNotIncludes(content, '按 50 分中性处理', label)
  assertNotIncludes(content, 'professional_score ?? 50', label)
  assertNotIncludes(content, 'stressScore ?? 50', label)
  assertNotIncludes(content, 'stressScore ?? null\\n        const stressComfortScore = stressScore ?? 50', label)
  assertNotIncludes(content, 'completenessScore ?? 35', label)
  assertNotIncludes(content, 'item.evidenceScore || 35', label)
  assertIncludes(content, replayCopy, label)
  assertIncludes(content, label === 'comparison page' ? '回撤回放缺失，本项不加分，并触发决策分封顶' : '回撤回放缺失，本项不加分，并触发研究评分封顶', label)
  assertIncludes(content, label === 'comparison page' ? '压力体验缺失，本项不加分，并触发决策分封顶' : '压力体验缺失，本项不加分，并触发研究评分封顶', label)
  assertIncludes(content, scoreCapCopy, label)
  assertIncludes(content, label === 'comparison page' ? '回撤回放缺失，决策分封顶 70' : '回撤回放缺失，研究评分封顶 70', label)
  assertIncludes(content, label === 'comparison page' ? '压力体验缺失，决策分封顶 70' : '压力体验缺失，研究评分封顶 70', label)
}

assertIncludes(comparisonPage, 'const evidenceScore = fund.buy_evidence?.completenessScore ?? 0', 'comparison page evidence missing gate')
assertIncludes(comparisonPage, 'const professionalScore = professionalScoreMissing ? 0 : fund.professional_score as number', 'comparison page professional missing gate')
assertIncludes(comparisonPage, 'const stressComfortScore = stressScoreMissing ? 0 : stressScore', 'comparison page stress missing gate')
assertIncludes(comparisonPage, 'plannedAmount: String(currentPlannedAmount())', 'comparison page preserves planned amount in return/detail context')
assertIncludes(comparisonPage, 'plannedAmount: String(currentPlannedAmount())', 'comparison page sales-rule gaps receive planned amount')
assertIncludes(comparisonPage, 'comparison-execution-amount-gate', 'comparison page displays amount execution gate')
assertIncludes(comparisonPage, '计划金额未通过起购/定投起点/限购门禁', 'comparison page blocks formal report save on amount gate')
assertIncludes(comparisonScoreTool, 'rawScore: item.evidenceScore', 'comparison score tool preserves zero evidence score')
assertIncludes(comparisonScoreTool, 'const stressScore = stressScoreMissing ? 0 : item.replay?.stressScore as number', 'comparison score tool stress missing gate')
assertIncludes(comparisonScoreTool, '测算证据门禁未过，研究评分封顶 62', 'comparison score tool caps score when replay evidence gate is not passed')
assertIncludes(comparisonReport, 'plannedAmount: number | null', 'comparison report context records planned amount')
assertIncludes(comparisonReportMarkdown, '计划金额 ${payload.context.plannedAmount.toLocaleString', 'comparison report markdown renders planned amount')
assertIncludes(comparisonReportRoute, 'Number(body.plannedAmount)', 'comparison report route accepts planned amount from POST body')
assertIncludes(comparisonReportRoute, 'plannedAmount: safePlannedAmount', 'comparison report route passes planned amount into report builder')
assertIncludes(comparisonReportRoute, 'SALES_RULE_AMOUNT_GATE_BLOCKED', 'comparison report route blocks amount-incompatible formal report')
assertIncludes(comparisonReportRoute, 'salesRuleRules: jsonSafe(currentSalesRuleGaps.rules)', 'comparison report route persists execution amount gate rules')
if (comparisonReportRoute.indexOf('SALES_RULE_AMOUNT_GATE_BLOCKED') > comparisonReportRoute.indexOf('SALES_RULE_GAP_BLOCKED')) {
  throw new Error('comparison report route must block amount gates before generic sales-rule gaps')
}

console.log('OK comparison missing replay/stress/evidence no longer receives neutral decision credit')
