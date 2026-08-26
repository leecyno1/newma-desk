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

function assertNotIncludes(content, unexpected, label) {
  if (content.includes(unexpected)) {
    throw new Error(`${label} contains forbidden text: ${unexpected}`)
  }
}

function assertCount(content, expected, count, label) {
  const actual = content.split(expected).length - 1
  if (actual !== count) {
    throw new Error(`${label} expected ${count} occurrences of ${expected}, got ${actual}`)
  }
}

const tushareService = read('backend/services/tushare_service.py')
const scoringEngine = read('backend/services/scoring_engine.py')
const evidenceReport = read('backend/services/evidence_report.py')

const styleSection = tushareService.slice(
  tushareService.indexOf('def get_fund_style'),
  tushareService.indexOf('def get_all_funds'),
)

assertIncludes(styleSection, 'holdings_derived_industry_only', 'Tushare style returns holdings-derived status')
assertIncludes(styleSection, 'style_factors_status', 'Tushare style marks Barra factor status')
assertIncludes(styleSection, '不能输出 SIZE/BETA/MOMENTUM', 'Tushare style refuses fake Barra factors')
assertCount(styleSection, 'return self._mock_style()', 1, 'real-mode Tushare style only keeps explicit mock-mode branch')
assertNotIncludes(styleSection, '"SIZE": size_exposure', 'real-mode Tushare style must not emit synthetic SIZE')
assertNotIncludes(styleSection, '"BETA": 0.8', 'real-mode Tushare style must not emit synthetic BETA')

assertIncludes(scoringEngine, 'style_factors_status") == "unavailable"', 'scoring engine recognizes unavailable style factors')
assertIncludes(scoringEngine, 'status": "insufficient_evidence"', 'scoring engine labels missing style evidence')
assertIncludes(scoringEngine, 'factor_stability_score = 0.0', 'scoring engine gives no neutral credit to missing style evidence')
assertIncludes(scoringEngine, 'ScoreDimension.STYLE: {"score": 0.0, "weighted_score": 0.0, "count": 0', 'metric snapshot scoring gives no style credit when missing')
assertIncludes(scoringEngine, 'count": len(numeric_exposures)', 'scoring engine counts only numeric style factors')

assertIncludes(evidenceReport, 'Barra 风格因子不可用', 'fund report discloses missing Barra style factors')
assertIncludes(evidenceReport, '不用行业暴露反推风格稳定性', 'fund report blocks industry-to-style inference')

console.log('OK real-mode style exposure avoids mock Barra factors and labels insufficient evidence')
