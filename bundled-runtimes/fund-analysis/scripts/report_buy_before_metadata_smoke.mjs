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

const evidenceReport = read('backend/services/evidence_report.py')
const backendReports = read('backend/routes/reports.py')
const reportsApi = read('app/api/reports/route.ts')
const reportDetailApi = read('app/api/reports/[id]/route.ts')
const reportsPage = read('app/(dashboard)/reports/page.tsx')
const reportDetailPage = read('app/(dashboard)/reports/[id]/page.tsx')

assertIncludes(evidenceReport, 'def build_buy_before_decision_summary', 'evidence report exposes structured buy-before summary')
assertIncludes(evidenceReport, '"hardBlocks"', 'structured summary preserves hard blocks')
assertIncludes(evidenceReport, '"nextActions"', 'structured summary preserves next actions')

assertIncludes(backendReports, 'build_buy_before_decision_summary', 'backend report route builds structured buy-before summary')
assertIncludes(backendReports, '"buy_before_decision": buy_before_decision', 'backend report route stores buy-before metadata')
assertIncludes(backendReports, '"buyBeforeGateStatus": buy_before_decision.get("status")', 'backend report route stores list summary status')

assertIncludes(reportsApi, 'dataSources.buy_before_decision', 'reports list API reads buy-before metadata')
assertIncludes(reportsApi, 'buyBeforeGateHardBlocks', 'reports list API maps hard blocks')
assertIncludes(reportsApi, 'buyBeforeGateNextActions', 'reports list API maps next actions')
assertIncludes(reportsApi, 'decisionReplayEvidenceGateStatus', 'reports list API maps replay evidence gate status')
assertIncludes(reportsApi, 'decisionReplayEvidenceGateMissingEvidence', 'reports list API maps replay evidence gate missing items')
assertIncludes(reportsApi, 'replayEvidenceGateVerifyCount', 'reports list API maps replay evidence gate verify count')
assertIncludes(reportsApi, "isComparisonReport ? 'missing' : ''", 'reports list API downgrades legacy comparison reports without replay gate')
assertIncludes(reportsApi, '旧横评缺测算证据门禁', 'reports list API labels legacy comparison replay gate gaps')

assertIncludes(reportDetailApi, 'dataSources.buy_before_decision', 'report detail API reads buy-before metadata')
assertIncludes(reportDetailApi, 'buyBeforeDecision,', 'report detail API returns buy-before decision')
assertIncludes(reportDetailApi, '研究复核总闸门', 'report detail evidence summary labels buy-before gate')
assertIncludes(reportDetailApi, '测算证据门禁', 'report detail evidence summary labels replay evidence gate')
assertIncludes(reportDetailApi, 'decisionReplayEvidenceGateStatus', 'report detail API reads comparison replay evidence gate status')
assertIncludes(reportDetailApi, 'decisionReplayEvidenceGateMissingEvidence', 'report detail API reads comparison replay evidence gate missing items')
assertIncludes(reportDetailApi, 'replayEvidenceGateVerifyCount', 'report detail API reads replay evidence gate verify count')
assertIncludes(reportDetailApi, '门禁未过的历史回放不能作为正式研究结论', 'report detail replay evidence gate hard boundary')
assertIncludes(reportDetailApi, '首选基金的测算证据门禁未通过', 'report detail warns when comparison replay evidence gate is not passed')
assertIncludes(reportDetailApi, "rawDecisionReplayGateStatus || 'missing'", 'report detail downgrades legacy comparison reports without replay gate')
assertIncludes(reportDetailApi, '旧横评未记录测算证据门禁', 'report detail labels legacy comparison replay gate gaps')
assertIncludes(reportDetailApi, '旧横评缺少测算证据门禁，不能作为今天的正式研究横评结论', 'report detail blocks legacy comparison reports as formal conclusions')

assertIncludes(reportsPage, 'report-list-buy-before-gate-card', 'reports page renders buy-before gate card')
assertIncludes(reportsPage, '研究总闸门', 'reports page exposes gate label without opening detail')
assertIncludes(reportsPage, 'report-list-replay-evidence-gate-card', 'reports page renders replay evidence gate card')
assertIncludes(reportsPage, '测算证据门禁：', 'reports page exposes replay evidence gate label without opening detail')
assertIncludes(reportsPage, '门禁未过的历史回放不能作为正式研究结论', 'reports page warns failed replay gates are not formal research conclusions')
assertIncludes(reportsPage, '这份旧横评未记录测算证据门禁', 'reports page downgrades legacy comparison reports without replay gates')
assertIncludes(reportsPage, '重跑真实回放横评', 'reports page offers real replay rerun action for legacy comparison reports')
assertIncludes(reportsPage, "Boolean(replayEvidenceGateStatus) && replayEvidenceGateStatus !== 'pass'", 'reports reuse queue treats missing/failed replay gates as rerun required')
assertIncludes(reportsPage, '缺测算证据门禁或仍是先复核状态', 'reports reuse queue explains replay gate rerun cause')
assertIncludes(reportsPage, '横评缺测算证据门禁', 'reports reuse boundary blocks legacy comparison reports without replay gates')
assertIncludes(reportsPage, '补销售规则后仍需重跑真实回放横评', 'reports reuse invalidated lane preserves replay gate reason when sales gaps also block')
assertIncludes(reportDetailPage, 'report-detail-buy-before-gate', 'report detail renders dedicated buy-before gate block')
assertIncludes(reportDetailPage, 'buildBuyBeforeEvidenceQueue', 'report detail builds buy-before evidence actions')
assertIncludes(reportDetailPage, 'report-detail-buy-before-actions', 'report detail renders buy-before evidence action links')
assertIncludes(reportDetailPage, 'reportPlannedAmount', 'report detail recovers saved planned amount')
assertIncludes(reportDetailPage, 'reportActionHref(item.href, reportPurchasePlan, reportPlannedAmount, reportReturnHref)', 'report detail action links preserve purchase plan, planned amount, and return target')

console.log('OK reports expose structured buy-before gate metadata in backend, API, list, and detail')
