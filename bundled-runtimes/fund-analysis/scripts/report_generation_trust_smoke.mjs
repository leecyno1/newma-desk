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

function assertNotIncludes(content, forbidden, label) {
  if (content.includes(forbidden)) {
    throw new Error(`${label} must not include text: ${forbidden}`)
  }
}

const aiReportService = read('backend/services/ai_report.py')
const backendReportsRoute = read('backend/routes/reports.py')
const analysisGenerateRoute = read('app/api/analysis/generate/route.ts')
const evidenceReport = read('backend/services/evidence_report.py')

assertIncludes(aiReportService, 'Refusing to generate mock report', 'AI report service refuses mock reports')
assertIncludes(aiReportService, '系统已阻止输出模拟研究报告', 'AI report service blocks simulated research reports')
assertNotIncludes(aiReportService, 'def _mock_report', 'AI report service mock report method')
assertNotIncludes(aiReportService, '当前使用模拟数据展示报告格式', 'AI report service mock report copy')
assertNotIncludes(aiReportService, 'Returning mock report', 'AI report service mock fallback')

assertIncludes(backendReportsRoute, '_is_unusable_llm_report', 'backend report route filters unusable LLM output')
assertIncludes(backendReportsRoute, '_reject_mock_data_source', 'backend report route blocks mock data source')
assertIncludes(backendReportsRoute, '当前数据服务为 mock_mode，已阻止生成研究报告', 'backend report route mock source rejection copy')
assertIncludes(backendReportsRoute, '_reject_mock_data_source(data_svc, "基金")', 'fund report route rejects mock source')
assertIncludes(backendReportsRoute, '_reject_mock_data_source(data_svc, "基金经理")', 'manager report route rejects mock source')
assertIncludes(backendReportsRoute, 'build_fund_research_report', 'fund report route falls back to deterministic evidence report')
assertIncludes(backendReportsRoute, 'generation_mode = "deterministic_evidence_backed"', 'fund report route marks deterministic evidence mode')
assertIncludes(analysisGenerateRoute, '已阻止输出模拟报告', 'frontend analysis stream refuses simulated backend report')
assertIncludes(evidenceReport, '不调用外部 LLM，不产出演示/Mock 文案', 'deterministic report states no mock output')

console.log('OK report generation refuses mock research output and preserves deterministic evidence fallback')
