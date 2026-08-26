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

const coverageLib = read('lib/evidence-coverage.ts')
const coverageClient = read('app/(dashboard)/evidence-coverage/EvidenceCoverageClient.tsx')
const coverageRoute = read('app/api/evidence-coverage/route.ts')
const acceptanceSmoke = read('scripts/fund_research_acceptance_smoke.mjs')

assertIncludes(coverageLib, "tableExists('holdings')", 'evidence coverage detects holdings table')
assertIncludes(coverageLib, "columnExists('holdings', 'wind_code')", 'evidence coverage supports backend holdings schema')
assertIncludes(coverageLib, "columnExists('holdings', 'fund_id')", 'evidence coverage supports prisma holdings schema')
assertIncludes(coverageLib, 'AS holding_ready', 'evidence coverage computes holding readiness')
assertIncludes(coverageLib, 'COUNT(*) FILTER (WHERE holding_ready)::int AS holding_ready', 'evidence coverage counts holding readiness')
assertIncludes(coverageLib, "CASE WHEN NOT holding_ready THEN '持仓明细' END", 'gap sample includes holding gaps')
assertIncludes(coverageLib, "dimension('holding', '持仓明细', '研究复核'", 'evidence dimensions include holdings')
assertIncludes(coverageLib, '至少 5 条带季度、股票和权重的持仓', 'holding dimension explains verified evidence threshold')
assertIncludes(coverageLib, "NULLIF(UPPER(risk_level), '') ~ '^R[1-5]$'", 'evidence coverage requires valid R1-R5 risk level')
assertIncludes(coverageLib, "source_updated_at >= CURRENT_DATE - INTERVAL '30 days'", 'evidence coverage rejects stale risk-level source dates')
assertIncludes(coverageLib, 'source_updated_at <= CURRENT_DATE', 'evidence coverage rejects future risk-level source dates')
assertIncludes(coverageLib, "COALESCE(LOWER(platform), '') NOT LIKE '%tushare%'", 'evidence coverage rejects Tushare platform as risk-level source')
assertIncludes(coverageLib, "COALESCE(LOWER(source_url), '') NOT LIKE '%tushare.fund_basic%'", 'evidence coverage rejects Tushare as risk-level source')
assertIncludes(coverageLib, "NULLIF(source_url, '') IS NOT NULL", 'evidence coverage requires risk-level source evidence')
assertIncludes(coverageLib, "dimension('risk_level', '风险等级来源背书'", 'evidence coverage labels source-backed risk-level dimension')
assertIncludes(coverageLib, '30 天研究复核窗口', 'evidence coverage explains risk-level freshness window')

assertIncludes(coverageClient, 'filteredDimensions.map', 'evidence coverage client renders dynamic dimensions')
assertIncludes(coverageClient, 'payload.priorityQueue.map', 'evidence coverage client renders dynamic priority queue')
assertIncludes(coverageClient, 'data-testid="evidence-buy-before-remediation-playbook"', 'evidence coverage has buy-before remediation playbook hook')
assertIncludes(coverageClient, '研究复核补证作业队列', 'evidence coverage renders remediation playbook')
assertIncludes(coverageClient, 'evidenceGapRoiQueue', 'evidence coverage builds gap ROI queue')
assertIncludes(coverageClient, 'data-testid="evidence-gap-roi-queue"', 'evidence coverage renders gap ROI queue')
assertIncludes(coverageClient, '研究复核数据缺口 ROI 队列', 'evidence coverage shows gap ROI queue title')
assertIncludes(coverageClient, '先补哪个字段最能解锁正式研究候选', 'evidence coverage explains formal candidate unlock ROI')
assertIncludes(coverageClient, '按预计解锁研究候选、适当性槽位和硬门禁强度排序', 'evidence coverage sorts ROI by unlock value and hard gates')
assertIncludes(coverageClient, 'ROI 边界：缺口数量不是加分项', 'evidence coverage keeps missing evidence from becoming positive signal')
assertIncludes(coverageClient, 'buyBeforeRemediationTsv', 'evidence coverage buy-before remediation TSV model')
assertIncludes(coverageClient, 'copyBuyBeforeRemediationTsv', 'evidence coverage buy-before remediation TSV copy action')
assertIncludes(coverageClient, 'downloadBuyBeforeRemediationTsv', 'evidence coverage buy-before remediation TSV download action')
assertIncludes(coverageClient, 'evidence-remediation-tsv-copy', 'evidence coverage buy-before remediation TSV copy button')
assertIncludes(coverageClient, 'evidence-remediation-tsv-download', 'evidence coverage buy-before remediation TSV download button')
assertIncludes(coverageClient, '复制补证 TSV', 'evidence coverage buy-before remediation TSV copy label')
assertIncludes(coverageClient, '下载补证 TSV', 'evidence coverage buy-before remediation TSV download label')
assertIncludes(coverageClient, '已转下载 TSV', 'evidence coverage buy-before remediation TSV fallback label')
assertIncludes(coverageClient, 'R1-R5、销售规则、计划金额、净值回放、持仓和正式研究复核报告门禁未清零前，不形成研究建议', 'evidence coverage remediation TSV keeps buy-before hard boundary')
assertIncludes(coverageClient, '严格选基销售规则清零', 'evidence coverage ROI includes strict selection sales-rule item')
assertIncludes(coverageClient, '全市场 R1-R5 来源背书', 'evidence coverage ROI includes suitability risk-level source item')
assertIncludes(coverageClient, '第一优先级：研究清单销售规则', 'evidence coverage prioritizes research-list sales rules')
assertIncludes(coverageClient, '第二优先级：R1-R5 来源适当性', 'evidence coverage prioritizes suitability risk-level source')
assertIncludes(coverageClient, '第三优先级：覆盖率薄弱维度', 'evidence coverage prioritizes weak evidence dimensions')
assertIncludes(coverageClient, '补齐前不能进入正式研究候选', 'evidence coverage preserves hard gate copy')
assertIncludes(coverageClient, '不能保存正式研究复核报告', 'evidence coverage blocks formal report saving before hard gaps are fixed')
assertIncludes(coverageClient, 'buyBeforeRemediationSteps.map', 'evidence coverage renders remediation steps from real payload')
assertIncludes(coverageClient, '全市场适当性匹配影响', 'evidence coverage renders market suitability impact')
assertIncludes(coverageClient, 'data-testid="evidence-sales-rule-impact"', 'evidence coverage has impact test hook')
assertIncludes(coverageClient, 'salesRuleImpact.profiles.map', 'evidence coverage renders profile suitability counts')
assertIncludes(coverageClient, '补全市场风险来源', 'evidence coverage links to market risk-level source queue')
assertIncludes(coverageClient, '来源日期超过 30 天研究复核窗口', 'evidence coverage impact copy blocks stale risk-level sources')
assertIncludes(coverageClient, '风险来源覆盖率', 'evidence coverage labels risk-level source coverage metric')
assertIncludes(coverageClient, 'salesRulesHrefForEvidenceCoverage', 'evidence coverage central sales-rule href builder')
assertIncludes(coverageClient, "new URLSearchParams({ purchasePlan: 'sip'", 'evidence coverage sales-rule href carries default purchase plan')
assertIncludes(coverageRoute, 'salesRuleImpact', 'evidence coverage API includes sales rule impact')
assertIncludes(coverageRoute, 'getSalesRuleImpact', 'evidence coverage API calls sales rule impact service')

assertIncludes(acceptanceSmoke, 'scripts/evidence_coverage_holdings_smoke.mjs', 'acceptance smoke includes holding coverage check')

console.log('OK evidence coverage tracks holding detail readiness and gap queue')
