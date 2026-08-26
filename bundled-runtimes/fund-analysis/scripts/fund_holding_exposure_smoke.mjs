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

const detailClient = read('app/(dashboard)/funds/[id]/FundDetailClient.tsx')
const researchReviewLib = read('lib/research-review-report.ts')
const holdingsRoute = read('app/api/funds/[id]/holdings/route.ts')
const researchReviewRoute = read('app/api/funds/[id]/research-review-report/route.ts')
const tushareService = read('backend/services/tushare_service.py')
const backendReports = read('backend/routes/reports.py')
const evidenceReport = read('backend/services/evidence_report.py')

assertIncludes(detailClient, 'buildHoldingExposureDecision', 'fund detail holding exposure decision builder')
assertIncludes(detailClient, 'fund-holding-exposure-decision-card', 'fund detail holding exposure card')
assertIncludes(detailClient, '持仓暴露研究判断', 'fund detail holding exposure card title')
assertIncludes(detailClient, '暴露分', 'fund detail holding exposure score')
assertIncludes(detailClient, '前十大', 'fund detail top ten concentration')
assertIncludes(detailClient, '第一行业', 'fund detail top industry exposure')
assertIncludes(detailClient, '结论反转条件', 'fund detail holding exposure reverse triggers')
assertIncludes(detailClient, 'holdingExposure: buildHoldingExposureDecision()', 'candidate pool holding exposure evidence')
assertIncludes(detailClient, '持仓暴露：${holdingExposureDecision.label}', 'one-page memo holding exposure line')
assertIncludes(detailClient, 'label: \'持仓暴露\'', 'purchase score holding exposure factor')
assertIncludes(detailClient, 'purchaseDecisionComponentScores.holdingExposure * 0.12', 'purchase score holding exposure contribution')
assertIncludes(detailClient, 'title: \'5. 持仓暴露\'', 'purchase workflow holding exposure step')

assertIncludes(researchReviewLib, 'type HoldingExposureDecision', 'research review holding exposure type')
assertIncludes(researchReviewLib, 'buildHoldingExposureDecision', 'research review holding exposure builder')
assertIncludes(researchReviewLib, '持仓暴露研究判断', 'research review holding exposure section')
assertIncludes(researchReviewLib, '暴露风险', 'research review holding exposure risk')
assertIncludes(researchReviewLib, '结论反转条件', 'research review holding exposure reverse triggers')
assertIncludes(researchReviewLib, 'holdingExposureDecision', 'research review structured holding exposure output')
assertIncludes(holdingsRoute, 'backend.tushare.fund_portfolio.filtered', 'fund holdings API labels Tushare fund_portfolio source')
assertIncludes(researchReviewRoute, 'backend.tushare.fund_portfolio.filtered', 'research review holding fallback labels fund_portfolio source')
assertIncludes(tushareService, 'self.pro.fund_portfolio', 'Tushare holdings use official fund_portfolio interface')
assertIncludes(tushareService, 'stk_mkv_ratio', 'Tushare holdings normalize portfolio market value ratio')
assertIncludes(backendReports, '_load_latest_local_holdings', 'backend fund report loads local holding snapshot')
assertIncludes(backendReports, '"holdings_status": holding_snapshot["status"]', 'backend fund report stores real holding status')
assertIncludes(backendReports, '"holdings_source": holding_snapshot["source"]', 'backend fund report stores holding source')
assertIncludes(evidenceReport, '## 4. 持仓与行业暴露', 'deterministic report prints holding exposure section')
assertIncludes(evidenceReport, '### 持仓集中度诊断', 'deterministic report prints holding concentration diagnosis')
assertIncludes(evidenceReport, '前十大合计', 'deterministic report computes top-ten concentration')
assertIncludes(evidenceReport, '第一行业', 'deterministic report calls out top industry exposure')
assertIncludes(evidenceReport, '不能按普通分散型基金理解', 'deterministic report flags high industry concentration')
assertIncludes(evidenceReport, '不能把持仓缺失视为行业分散', 'deterministic report blocks missing holdings as neutral')

console.log('OK fund detail and research review report include holding exposure decision evidence')
