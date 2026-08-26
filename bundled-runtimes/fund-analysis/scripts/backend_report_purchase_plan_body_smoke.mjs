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
const aiReport = read('backend/services/ai_report.py')
const backendReports = read('backend/routes/reports.py')

assertIncludes(evidenceReport, 'purchase_plan: str = "sip"', 'deterministic fund report accepts purchase plan')
assertIncludes(evidenceReport, '买入方式口径', 'deterministic fund report prints purchase-plan scope')
assertIncludes(evidenceReport, '一次性买入', 'deterministic fund report supports lump-sum label')
assertIncludes(evidenceReport, '定投支持、定投起点', 'deterministic fund report keeps SIP-specific evidence fields')
assertIncludes(evidenceReport, '起购金额、限购、赎回规则、费率、销售风险等级', 'deterministic fund report keeps lump-sum evidence fields')
assertIncludes(evidenceReport, '缺失证据视为中性或默认通过', 'deterministic fund report blocks missing evidence as neutral')

assertIncludes(aiReport, 'purchase_plan: str = "sip"', 'LLM fund report accepts purchase plan')
assertIncludes(aiReport, '## 买前研究口径', 'LLM fund prompt injects buy-before scope')
assertIncludes(aiReport, '买入方式口径：{}', 'LLM fund prompt requires purchase-plan disclosure')
assertIncludes(aiReport, '缺失销售证据不得视为中性或默认通过', 'LLM fund prompt blocks missing sales evidence as neutral')

assertIncludes(backendReports, 'planned_amount: Optional[float] = Query(None', 'backend report route accepts planned amount')
assertIncludes(backendReports, 'safe_planned_amount = _normalize_planned_amount(planned_amount, safe_purchase_plan)', 'backend report route normalizes planned amount')
assertIncludes(backendReports, '_ensure_purchase_plan_notice(report_content, safe_purchase_plan, safe_planned_amount)', 'backend report route forces purchase-plan and amount notice before saving')
assertIncludes(backendReports, 'purchase_plan=safe_purchase_plan', 'backend report route passes purchase plan into generators')
assertIncludes(backendReports, '"plannedAmount": safe_planned_amount', 'backend report route stores planned amount in metadata')
assertIncludes(backendReports, '计划金额：{amount:,} 元', 'backend report route notice includes planned amount')
assertIncludes(backendReports, '正式买前判断前必须补齐并复核', 'backend report route notice includes hard evidence gate')

console.log('OK backend fund report body discloses purchase-plan scope and buy-before evidence gates')
