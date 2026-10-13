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
    throw new Error(`${label} should not include stale text: ${unexpected}`)
  }
}

const simpleDetailClient = read('app/(dashboard)/funds/[id]/SimpleFundDetailClient.tsx')
const buyEvidenceLib = read('lib/research-evidence.ts')
const fundReportNormalizerLib = read('lib/fund-report-normalizer.ts')
const reportBuyBeforeEvidenceQueueLib = read('lib/report-buy-before-evidence-queue.ts')
const prePurchaseLib = read('lib/research-review-report.ts')
const prePurchaseRoute = read('app/api/funds/[id]/research-review-report/route.ts')
const purchaseSimulationRoute = read('app/api/funds/[id]/historical-nav-replay/route.ts')
const materialEvidenceRoute = read('app/api/evidence-coverage/materials/route.ts')
const reviewAlertsLib = read('lib/sales-rule-review-alerts.ts')
const salesRuleSourceEvidenceLib = read('lib/sales-rule-source-evidence.ts')

// e3478bb 起基金详情页收敛为研究画像（SimpleFundDetailClient）；购买前门禁 UI 与其
// Next 代理路由（app/api/funds/[id]/route.ts）只存在于已删除的死组件
// FundDetailClient（357KB、零引用）中。购买路径由 /market、/analysis/fund、
// /evidence-coverage 与正式研究复核报告（research-review-report）在基金维度提供。
for (const removedPath of [
  'app/(dashboard)/funds/[id]/FundDetailClient.tsx',
  'app/api/funds/[id]/route.ts',
]) {
  if (existsSync(join(root, removedPath))) {
    throw new Error(`dead fund-detail purchase component/route must stay removed: ${removedPath}`)
  }
}

// 详情页保持研究画像：不得重新引入购买前门禁 UI，防止在详情页绕过基金维度的正式门禁流程。
// （"买入日"等历史回放描述词不属于购买入口。）
for (const forbidden of ['申购', '购买', '下单', 'plannedAmount', 'purchasePlan', 'buyEvidence', 'activeSalesRuleEvidenceAlert', '加入研究清单']) {
  assertNotIncludes(simpleDetailClient, forbidden, 'fund detail page must stay research-profile')
}

// 详情页保留 AI 评价分析报告入口：本地证据 + LLM 叙述，生成后跳转报告详情。
assertIncludes(simpleDetailClient, 'GenerateFundReportButton', 'fund detail keeps the AI evaluation report entry')

// 活链路守护：复查告警助手、材料核验 API、报告门禁归一化、买前证据库与
// 正式研究复核报告（含份额选择、金额门禁、持有体验回放）全部保留。
assertIncludes(reviewAlertsLib, 'fetchActiveSalesRuleEvidenceAlertForCode', 'sales-rule review alert helper fetches active alert by code')
assertIncludes(reviewAlertsLib, "item.event_type === 'sales_rule_evidence'", 'sales-rule review alert helper filters sales-rule evidence events')
assertIncludes(reviewAlertsLib, "item.status !== 'resolved'", 'sales-rule review alert helper ignores resolved alerts')
assertIncludes(materialEvidenceRoute, 'getMergedSalesRulesByWindCodes', 'material evidence API can fetch merged rules by code')
assertIncludes(materialEvidenceRoute, "source: 'local.postgres.fund_sales_rules.merged_by_code'", 'material evidence API declares merged-by-code source')
assertIncludes(materialEvidenceRoute, 'missingCodes', 'material evidence API discloses missing requested sales-rule codes')
assertIncludes(fundReportNormalizerLib, 'normalizeBuyBeforeDecisionSummary', 'fund report normalizer uses buy-before gate parser')
assertIncludes(fundReportNormalizerLib, 'buyBeforeDecision: normalizeBuyBeforeDecisionSummary', 'fund report normalizer returns saved report buy-before gate')
assertIncludes(fundReportNormalizerLib, 'buildReportRiskLevelGatePolicy', 'fund report normalizer builds saved report R1-R5 gate policy')
assertIncludes(fundReportNormalizerLib, 'riskLevelGatePolicy: buildReportRiskLevelGatePolicy', 'fund report normalizer returns saved report R1-R5 gate policy')
assertIncludes(fundReportNormalizerLib, 'relatedCodes = reportCodes(record, dataSources)', 'fund report normalizer extracts report-related fund codes')
assertIncludes(buyEvidenceLib, "const purchasePlan = normalizePurchasePlan(options.purchasePlan)", 'buy evidence normalizes purchase plan')
assertIncludes(buyEvidenceLib, 'const plannedAmount = normalizePlannedAmount(options.plannedAmount, purchasePlan)', 'buy evidence normalizes planned amount')
assertIncludes(buyEvidenceLib, 'DEFAULT_PLANNED_AMOUNTS', 'buy evidence falls back to default planned amount')
assertIncludes(buyEvidenceLib, 'buildExecutionAmountGate', 'buy evidence builds execution amount gate')
assertIncludes(buyEvidenceLib, 'shortfallAmount', 'buy evidence quantifies amount execution shortfall')
assertIncludes(buyEvidenceLib, 'suggestedAmount', 'buy evidence exposes suggested executable planned amount')
assertIncludes(buyEvidenceLib, 'actionLabel', 'buy evidence exposes investor-facing amount gate action')
assertIncludes(buyEvidenceLib, '金额门槛当前通过；下一步继续核 R1-R5 适当性、申购状态、费用和赎回规则。', 'buy evidence keeps amount pass as research gate, not buy advice')
assertIncludes(buyEvidenceLib, "label: '计划金额执行门禁'", 'buy evidence turns amount blockers into required evidence')
assertIncludes(buyEvidenceLib, 'executionAmountGate.status === \'blocked\'', 'buy evidence blocks amount-incompatible plans')
assertIncludes(buyEvidenceLib, '计划金额不可执行：${executionAmountGate.detail}', 'buy evidence conclusion discloses amount execution blocker')
assertIncludes(buyEvidenceLib, "purchasePlan === 'sip' ? moneyText(minSipAmount) : null", 'buy evidence ignores SIP-only amount for lump sum')
assertIncludes(buyEvidenceLib, "if (purchasePlan === 'sip' && !supportsSipSourceBacked)", 'buy evidence only adds source-backed SIP support gap for SIP plan')
assertIncludes(buyEvidenceLib, "if (purchasePlan === 'sip' && supportsSipSourceBacked && supportsSip === true && !minSipSourceBacked)", 'buy evidence requires source-backed SIP minimum only for SIP plan')
assertIncludes(buyEvidenceLib, "purchasePlan === 'sip'", 'buy evidence must-verify checklist is purchase-plan aware')
assertIncludes(buyEvidenceLib, 'hasSourceBackedRiskLevel', 'buy evidence requires source-backed risk level')
assertIncludes(buyEvidenceLib, 'RISK_LEVEL_SOURCE_MAX_AGE_DAYS = 30', 'buy evidence enforces 30-day risk-level source freshness')
assertIncludes(buyEvidenceLib, 'isFreshSourceDate(sourceUpdatedAt)', 'buy evidence rejects stale or future risk-level source dates')
assertIncludes(buyEvidenceLib, 'hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })', 'buy evidence delegates risk-level source identity validation')
assertIncludes(buyEvidenceLib, '已填写风险等级但缺少 30 天内销售平台/基金合同来源证据', 'buy evidence treats stale or unsourced risk level as missing')
assertIncludes(salesRuleSourceEvidenceLib, "platform.includes('tushare')", 'shared source evidence rejects Tushare platform as risk-level source')
assertIncludes(salesRuleSourceEvidenceLib, "normalizedSourceUrl.includes('tushare.fund_basic')", 'shared source evidence rejects Tushare fund_basic as risk-level source')
assertIncludes(reportBuyBeforeEvidenceQueueLib, "action: '去补销售规则'", 'buy-before evidence queue sales-rule action')
assertIncludes(reportBuyBeforeEvidenceQueueLib, "action: '同步同类指标'", 'buy-before evidence queue peer metrics action')
assertIncludes(reportBuyBeforeEvidenceQueueLib, "action: '查看持仓暴露'", 'buy-before evidence queue holding exposure action')
assertIncludes(reportBuyBeforeEvidenceQueueLib, "action: '同步经理任期'", 'buy-before evidence queue manager tenure action')

assertIncludes(prePurchaseLib, '同基金份额比较', 'pre-purchase share class evidence')
assertIncludes(prePurchaseLib, 'salesRuleEvidenceCopyForPlan', 'pre-purchase report uses purchase-plan aware sales-rule copy')
assertIncludes(prePurchaseLib, "formalFields: '申购费、赎回费、销售服务费、起购金额、限购和风险等级'", 'pre-purchase lump-sum hard gate copy skips SIP-only fields')
assertIncludes(prePurchaseLib, 'hasSourceBackedSalesRiskLevel', 'pre-purchase report requires source-backed risk level')
assertIncludes(prePurchaseLib, 'SALES_RISK_SOURCE_MAX_AGE_DAYS = 30', 'pre-purchase report enforces 30-day risk-level source freshness')
assertIncludes(prePurchaseLib, 'isFreshSalesRiskSourceDate(sourceUpdatedAt)', 'pre-purchase report rejects stale or future risk-level source dates')
assertIncludes(prePurchaseLib, "platform.toLowerCase().includes('tushare')", 'pre-purchase report rejects Tushare platform as risk-level source')
assertIncludes(prePurchaseLib, 'const salesRiskLevel = hasVerifiedSalesRiskLevel ? parseSalesRiskLevel', 'pre-purchase report does not use unsourced risk level for suitability')
assertIncludes(prePurchaseLib, 'buildRiskLevelSourcePolicy', 'pre-purchase report builds structured R1-R5 source policy')
assertIncludes(prePurchaseLib, 'R1-R5 来源背书', 'pre-purchase report renders R1-R5 source-backed signal')
assertIncludes(prePurchaseLib, '30天来源窗口', 'pre-purchase report renders 30-day source-window signal')
assertIncludes(prePurchaseLib, '销售风险等级（R1-R5 30天来源背书）', 'pre-purchase report renders strict R1-R5 gate signal')
assertIncludes(prePurchaseLib, 'Tushare fund_basic 不能作为 R1-R5 风险等级来源', 'pre-purchase report renders Tushare exclusion signal')
assertIncludes(prePurchaseLib, 'recheckTriggers', 'pre-purchase recheck triggers')
assertIncludes(prePurchaseLib, '什么情况下结论会改变', 'pre-purchase recheck triggers')
assertIncludes(prePurchaseLib, '同画像替代候选已可比较', 'pre-purchase recheck triggers')
assertIncludes(prePurchaseLib, '替代横评矩阵', 'pre-purchase alternative decision matrix')
assertIncludes(prePurchaseLib, '收益差', 'pre-purchase alternative decision matrix')
assertIncludes(prePurchaseLib, '回撤差', 'pre-purchase alternative decision matrix')
assertIncludes(prePurchaseLib, 'buildAlternativeWinLossLines', 'pre-purchase alternative win/loss lines')
assertIncludes(prePurchaseLib, '横评胜负线', 'pre-purchase alternative win/loss lines')
assertIncludes(prePurchaseLib, 'alternativeWinLossLines', 'pre-purchase structured win/loss lines')
assertIncludes(prePurchaseLib, "label: '销售规则'", 'pre-purchase win/loss sales rule threshold')
assertIncludes(prePurchaseLib, '费用口径', 'pre-purchase win/loss cost threshold')
assertIncludes(prePurchaseLib, 'buildStressExperience', 'pre-purchase stress experience builder')
assertIncludes(prePurchaseLib, '持有压力体验', 'pre-purchase stress experience section')
assertIncludes(prePurchaseLib, '最长亏损等待', 'pre-purchase stress underwater days')
assertIncludes(prePurchaseLib, '最差三个月', 'pre-purchase stress worst three months')
assertIncludes(prePurchaseLib, '不能只凭长期收益或评分进入研究候选', 'pre-purchase stress hard reminder')
assertIncludes(prePurchaseLib, 'stressExperience', 'pre-purchase structured stress experience')
assertIncludes(prePurchaseLib, 'shareClassEvidence', 'pre-purchase share class evidence')
assertIncludes(prePurchaseLib, 'horizonDaysForContext', 'pre-purchase report maps investor horizon to redemption holding days')
assertIncludes(prePurchaseLib, 'redemptionRuleAtHoldingDays', 'pre-purchase report matches redemption fee by holding days')
assertIncludes(prePurchaseLib, '按计划持有期约', 'pre-purchase report renders redemption holding-day matching policy')
assertIncludes(prePurchaseLib, '不默认使用第一条赎回规则', 'pre-purchase report rejects first-rule shortcut in copy')
assertNotIncludes(prePurchaseLib, 'const redemptionRule = fund.salesRule?.redemptionFeeRules?.[0] || null', 'pre-purchase report must not use first redemption rule by default')
assertIncludes(purchaseSimulationRoute, 'redemptionRuleAtHoldingDays', 'purchase simulation matches redemption fee by holding days')
assertIncludes(purchaseSimulationRoute, 'buildRedemptionFeeLadder', 'purchase simulation returns redemption fee ladder')
assertIncludes(purchaseSimulationRoute, 'redemptionRuleBuckets', 'purchase simulation returns SIP redemption rule buckets')
assertIncludes(purchaseSimulationRoute, 'holdingDays', 'purchase simulation carries holding days for redemption matching')
assertIncludes(prePurchaseLib, 'shareClassDecision', 'pre-purchase share class decision')
assertIncludes(prePurchaseLib, '份额选择建议', 'pre-purchase share class decision')
assertIncludes(prePurchaseLib, '份额门禁', 'pre-purchase share class hard gate')
assertIncludes(prePurchaseLib, '计划金额成本', 'pre-purchase share class planned amount cost lines')
assertIncludes(prePurchaseLib, '份额金额门禁', 'pre-purchase share class amount gate lines')
assertIncludes(prePurchaseLib, 'plannedAmount: plannedAmountInput', 'pre-purchase report accepts planned amount independent of replay')
assertIncludes(prePurchaseLib, 'const fallbackPlannedAmount = asNumber(plannedAmountInput)', 'pre-purchase report preserves planned amount when replay is missing')
assertIncludes(prePurchaseLib, 'plannedAmount,', 'pre-purchase report returns planned amount for blocked links and metadata')
assertIncludes(prePurchaseLib, 'knownCost', 'pre-purchase share class evidence carries known planned amount cost')
assertIncludes(prePurchaseLib, 'executionAmountGate?.status === \'pass\'', 'pre-purchase share class decision sorts executable share classes first')
assertIncludes(prePurchaseLib, '未通过当前计划金额门禁，不能作为正式推荐', 'pre-purchase share class decision blocks amount-incompatible share classes')
assertIncludes(prePurchaseLib, '同基金 A/C/I/H', 'pre-purchase share class checklist')
assertIncludes(prePurchaseLib, 'type ManagerAttributionDecision', 'pre-purchase manager attribution decision type')
assertIncludes(prePurchaseLib, 'buildManagerAttributionDecision', 'pre-purchase manager attribution decision builder')
assertIncludes(prePurchaseLib, '经理归因覆盖', 'pre-purchase manager attribution markdown section')
assertIncludes(prePurchaseLib, '经理归因覆盖率未达 100%', 'pre-purchase manager attribution recheck trigger')
assertIncludes(prePurchaseRoute, 'fetchShareClassEvidence', 'pre-purchase share class route')
assertIncludes(prePurchaseRoute, 'fetchShareClassEvidence(fund, investorContext, plannedAmount)', 'pre-purchase share class route preserves investor context and planned amount')
assertIncludes(prePurchaseRoute, 'plannedAmount,', 'pre-purchase report builder receives planned amount')
assertIncludes(prePurchaseRoute, 'const plannedAmountOverride = asPositiveNumber(', 'pre-purchase report accepts planned amount override')
assertIncludes(prePurchaseRoute, '    1,', 'pre-purchase report does not raise low positive planned amounts')
assertIncludes(prePurchaseRoute, "alternativesUrl.searchParams.set('plannedAmount', String(plannedAmount))", 'pre-purchase alternatives preserve planned amount')
assertIncludes(prePurchaseRoute, "alternativesUrl.searchParams.set(investorContext.purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(plannedAmount))", 'pre-purchase alternatives preserve planned amount alias')
assertIncludes(prePurchaseRoute, 'fetchActiveSalesRuleEvidenceAlertsForCodes', 'pre-purchase alternatives and share classes read active review alerts')
assertIncludes(prePurchaseRoute, 'reviewAlertMissingItems', 'pre-purchase converts active review alerts into missing items')
assertIncludes(prePurchaseRoute, '复查队列未解决', 'pre-purchase marks active review alerts as hard missing evidence')
assertIncludes(prePurchaseRoute, 'local.sales_rule_gaps+local.alert_events.sales_rule_evidence', 'pre-purchase alternative evidence records review-alert source')
assertIncludes(prePurchaseRoute, 'api.funds.keyword_share_class+local.alert_events.sales_rule_evidence', 'pre-purchase share class evidence records review-alert source')
assertIncludes(prePurchaseRoute, '先打开复查队列，处理销售规则/R1-R5过期或待补事件', 'pre-purchase review-alert next action routes to review queue')
assertIncludes(prePurchaseRoute, 'function reportAmountParams', 'pre-purchase blocked links share amount context')
assertIncludes(prePurchaseRoute, 'const plannedAmount = Number(report.plannedAmount)', 'pre-purchase blocked links prefer report planned amount')
assertIncludes(prePurchaseRoute, 'function strictInvestorSelectionParams', 'pre-purchase strict re-selection link preserves amount context')
assertIncludes(prePurchaseRoute, 'strictInvestorSelectionHref: `/investor-selection?${strictInvestorSelectionParams(report).toString()}`', 'pre-purchase blocked strict re-selection uses planned amount')
assertIncludes(prePurchaseRoute, 'salesRulesHref: materialEvidenceHref(new URLSearchParams({', 'pre-purchase blocked material-evidence link uses planned amount')
assertIncludes(prePurchaseRoute, '...Object.fromEntries(amountParams)', 'pre-purchase blocked draft link uses planned amount')
assertIncludes(prePurchaseRoute, 'purchase_plan: investorContext.purchasePlan', 'pre-purchase share class backend search carries purchase plan')
assertIncludes(prePurchaseRoute, 'getMergedSalesRulesByWindCodes(shareClassCodes)', 'pre-purchase share class route fetches sibling merged sales rules')
assertIncludes(prePurchaseRoute, 'getSalesRuleGapsForCodes(shareClassCodes, shareClassCodes.length', 'pre-purchase share class route fetches sibling amount gates')
assertIncludes(prePurchaseRoute, 'executionAmountGate: gapSummary?.executionAmountGate || null', 'pre-purchase share class evidence stores amount gate')
assertIncludes(prePurchaseRoute, 'costMissingItems', 'pre-purchase share class evidence stores cost missing items')
assertIncludes(prePurchaseRoute, 'buildResearchEvidence(fundWithSalesRule, { purchasePlan: investorContext.purchasePlan, plannedAmount })', 'research-review report evidence uses investor purchase plan and planned amount')
assertIncludes(prePurchaseRoute, 'normalizeShareClassBaseName', 'pre-purchase share class route')
assertIncludes(prePurchaseRoute, 'shareClassSiblingCount', 'pre-purchase share class metadata')
assertIncludes(prePurchaseRoute, 'shareClassRecommendedCode', 'pre-purchase share class metadata')
assertIncludes(prePurchaseRoute, 'shareClassDecisionConfidence', 'pre-purchase share class metadata')
assertIncludes(prePurchaseRoute, 'managerAttributionCoverageRatio', 'pre-purchase manager attribution metadata')
assertIncludes(prePurchaseRoute, 'managerAttributionDecision: result.report.managerAttributionDecision', 'pre-purchase manager attribution response')
assertIncludes(prePurchaseRoute, 'riskLevelSourcePolicy: result.report.riskLevelSourcePolicy', 'pre-purchase save stores R1-R5 source policy')
assertIncludes(prePurchaseRoute, 'plannedAmount: result.report.plannedAmount ?? null', 'pre-purchase save stores planned amount outside replay')
assertIncludes(prePurchaseRoute, 'riskLevelGateSignals: result.report.riskLevelSourcePolicy.signals', 'pre-purchase save stores R1-R5 gate signals')
assertIncludes(prePurchaseRoute, 'recheckTriggerCount', 'pre-purchase recheck trigger metadata')
assertIncludes(prePurchaseRoute, 'stressScore', 'pre-purchase stress score metadata')
assertIncludes(prePurchaseRoute, 'longestUnderwaterDays', 'pre-purchase stress underwater metadata')
assertIncludes(prePurchaseRoute, 'worstThreeMonthReturn', 'pre-purchase stress worst three month metadata')

console.log('OK fund detail stays research-profile; purchase gates live in market, analysis, evidence coverage and formal review reports')
