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

const reportsRoute = read('backend/routes/reports.py')
const evidenceReport = read('backend/services/evidence_report.py')

assertIncludes(reportsRoute, 'from services.peer_comparison_service import PeerComparisonService', 'fund report imports peer percentile service')
assertIncludes(reportsRoute, 'peer_percentiles = PeerComparisonService().build_peer_percentiles(wind_code, window="1y")', 'fund report loads real peer percentiles')
assertIncludes(reportsRoute, '_ensure_peer_percentile_section(report_content, peer_percentiles)', 'fund report appends peer percentile section for all modes')
assertIncludes(reportsRoute, '"peer_percentiles": peer_percentiles', 'fund report saves peer percentile evidence')
assertIncludes(reportsRoute, '"peer_percentile_status": peer_percentiles.get("sample_status")', 'fund report stores peer percentile status')

assertIncludes(evidenceReport, 'def build_peer_percentile_report_section', 'deterministic report has peer percentile section builder')
assertIncludes(evidenceReport, '## 同类分位与胜负线', 'deterministic report renders peer percentile title')
assertIncludes(evidenceReport, '同类胜负线', 'deterministic report renders peer win/loss line')
assertIncludes(evidenceReport, '样本状态', 'deterministic report discloses peer sample status')
assertIncludes(evidenceReport, '销售规则、风险等级、费率、赎回规则和净值回放仍是正式买前硬门禁', 'peer percentile section preserves buy-before hard gates')

console.log('OK fund reports include peer percentile win/loss evidence')
