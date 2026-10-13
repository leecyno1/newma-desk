import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const route = readFileSync(join(root, 'app/api/funds/[id]/research-review-report/route.ts'), 'utf8')
const legacyRoute = readFileSync(join(root, 'app/api/funds/[id]/pre-purchase-report/route.ts'), 'utf8')
const fundMaterialsRoute = readFileSync(join(root, 'app/api/funds/[id]/materials/route.ts'), 'utf8')

function assertIncludes(content, expected, label) {
  if (!content.includes(expected)) {
    throw new Error(`${label} missing text: ${expected}`)
  }
}

assertIncludes(legacyRoute, "export { GET, POST } from '../research-review-report/route'", 'legacy pre-purchase route delegates to research review report')
assertIncludes(route, 'buildFormalReportReadinessBlockPayload', 'research-review route formal readiness gate')
assertIncludes(route, "code: 'RESEARCH_EVIDENCE_NOT_READY'", 'research-review route evidence-not-ready code')
assertIncludes(route, 'fetchActiveSalesRuleEvidenceAlert', 'research-review route reads unresolved material evidence review events')
assertIncludes(route, "event.event_type === 'sales_rule_evidence'", 'research-review route filters material evidence review events')
assertIncludes(route, "event.status !== 'resolved'", 'research-review route ignores only resolved material evidence review events')
assertIncludes(route, 'buildReviewQueueAlertBlockPayload', 'research-review route builds review queue event block')
assertIncludes(route, "code: 'STALE_SALES_RULE_EVIDENCE_ALERT_BLOCKED'", 'research-review route blocks stale material evidence event')
assertIncludes(route, "reportStatus: 'blocked_by_review_queue'", 'research-review route reports review queue block status')
assertIncludes(route, "searchParams.get('draft') !== 'true'", 'research-review route allows only draft when event blocks formal report')
assertIncludes(route, "searchParams.get('plannedAmount')", 'research-review route accepts planned amount override')
assertIncludes(route, '{ purchasePlan: investorContext.purchasePlan, plannedAmount }', 'research-review route passes planned amount into material evidence gaps')
assertIncludes(route, 'executionAmountGate: salesRuleExecutionAmountGate', 'research-review route carries main fund execution amount gate')
assertIncludes(route, 'executionAmountGate: result.report.salesRuleGapEvidence.executionAmountGate || null', 'research-review route persists execution amount gate metadata')
assertIncludes(fundMaterialsRoute, "searchParams.get('plannedAmount')", 'fund materials route accepts planned amount')
assertIncludes(fundMaterialsRoute, 'getSalesRuleGapsForCodes([id], 1, { purchasePlan, plannedAmount: safePlannedAmount })', 'fund materials route scans execution amount gate by planned amount')
assertIncludes(fundMaterialsRoute, 'plannedAmount: safePlannedAmount', 'fund materials route returns planned amount context')
assertIncludes(route, '!report.purchaseSimulation', 'research-review route blocks missing NAV replay')
assertIncludes(route, 'report.purchaseSimulation.monthlyExperience.months < report.investorContext.minSampleMonths', 'research-review route blocks short replay sample')
assertIncludes(route, "report.verdict.evidenceGrade === 'D'", 'research-review route blocks D-grade evidence')
assertIncludes(route, "report.verdict.level === 'blocked'", 'research-review route blocks blocked verdict')
assertIncludes(route, '存在材料核验、风险预算或基础研究硬阻断', 'research-review route blocked verdict copy')
assertIncludes(route, "report.verdict.level === 'verify_first'", 'research-review route blocks verify-first verdict')
assertIncludes(route, "draft: 'true'", 'research-review route exposes draft-only path for blocked report')
assertIncludes(route, '不会写入报告库或冒充正式结论', 'research-review route formal-vs-draft copy')
assertIncludes(route, 'const readinessBlockPayload = buildFormalReportReadinessBlockPayload(id, result.report)', 'research-review route calls readiness gate')
assertIncludes(route, 'if (readinessBlockPayload) {', 'research-review POST uses readiness gate')

console.log('OK research review formal report save requires replay and sufficient evidence')
