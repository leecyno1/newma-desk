import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const managerRoute = readFileSync(join(root, 'backend/routes/managers.py'), 'utf8')
const scoringRoute = readFileSync(join(root, 'backend/routes/scoring.py'), 'utf8')
const reportsRoute = readFileSync(join(root, 'backend/routes/reports.py'), 'utf8')
const scoringEngine = readFileSync(join(root, 'backend/services/scoring_engine.py'), 'utf8')

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
  ['manager route', managerRoute],
  ['scoring route', scoringRoute],
  ['reports route', reportsRoute],
  ['scoring engine', scoringEngine],
]) {
  assertNotIncludes(content, 'overall_score": 75', label)
  assertNotIncludes(content, 'overall_score": 50, "evidence"', label)
  assertNotIncludes(content, 'if fund_scores else 50', label)
  assertNotIncludes(content, 'if fund_details else 50', label)
  assertNotIncludes(content, 'performance_data.get("overall_score", 50)', label)
  assertNotIncludes(content, 'performance_data.get("style_stability", 70)', label)
  assertNotIncludes(content, '样本不足给中等分', label)
}

assertIncludes(managerRoute, '"score_evidence"] = "insufficient_evidence"', 'manager list score evidence')
assertIncludes(managerRoute, '"overall_score": None', 'manager detail insufficient evidence score')
assertIncludes(managerRoute, '缺少可验证的管理基金评分，不输出默认基金经理分。', 'manager route insufficient evidence copy')
assertIncludes(scoringEngine, '"scoring_source": "insufficient_evidence"', 'manager scoring engine insufficient evidence')
assertIncludes(scoringEngine, '"scoring_source": "manager_fund_performance_evidence"', 'manager scoring engine evidence source')
assertIncludes(scoringRoute, 'else None', 'manager scoring route no default score')
assertIncludes(reportsRoute, 'else None', 'manager report route no default score')

console.log('OK manager scoring refuses default scores and labels insufficient evidence')
