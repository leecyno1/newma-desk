import { rankingLeaderQuestionsTool, reportReuseAssessmentTool, salesRuleGateTool, screeningConditionHealthTool } from '../lib/research-platform/tools'
import { listResearchSkillManifests } from '../lib/research-platform/skills'

const screening = screeningConditionHealthTool.run({
  hasScreened: true,
  resultCodes: ['519674.OF', '000001.OF', '000002.OF'],
  traces: [
    { matchedCriteriaCount: 3, missingCriteriaCount: 0, outsideCriteriaCount: 0 },
    { matchedCriteriaCount: 2, missingCriteriaCount: 1, outsideCriteriaCount: 0 },
  ],
  salesRuleGaps: [],
  salesRuleGapsChecked: true,
  salesRuleGapMissingItems: 0,
  salesRuleGapHref: '/sales-rules?codes=519674.OF',
  salesRulesHref: '/sales-rules',
  marketHref: '/market',
  screeningReturnHref: '/screening',
  comparisonHref: '/analysis/comparison?codes=519674.OF,000001.OF',
})

const leader = rankingLeaderQuestionsTool.run({
  leader: {
    windCode: '519674.OF',
    name: '示例基金A',
    investorScore: 82,
    investorRating: 'A',
    reasons: ['同类分位较好'],
    purchaseGate: {
      level: 'verify_first',
      label: '先复核',
      description: '销售规则和回放证据仍需复核。',
      evidenceGrade: 'B',
      cautionFlags: ['回放证据待补'],
    },
    scoreBreakdown: [{ label: '回撤', score: 18, maxScore: 20 }],
    costEvidence: { status: 'missing', label: '成本待补' },
  },
  peerCount: 8,
  comparisonCodes: ['000001.OF', '000002.OF'],
  visibleFundCount: 5,
  purchasePlan: 'sip',
  plannedAmount: 1000,
  costMissing: ['申购费率'],
  rankingReturnHref: '/rankings',
  fundDetailHref: '/funds/519674.OF',
  salesRulesHref: '/sales-rules?codes=519674.OF',
  comparisonHref: '/analysis/comparison?codes=519674.OF,000001.OF,000002.OF',
  marketHref: '/market',
})

const report = reportReuseAssessmentTool.run({
  id: 'report-1',
  title: '示例研究报告',
  targetType: 'fund',
  reportType: 'fund_pre_purchase_check',
  reportDate: new Date().toISOString(),
  actionHref: '/reports/report-1',
  currentSalesRuleGate: { status: 'ready', missingCount: 0 },
  decisionSummary: { buyBeforeGateStatus: 'research_ready' },
  followUp: { label: '复核基金详情', href: '/funds/519674.OF' },
})

const salesGate = salesRuleGateTool.run({
  windCode: '519674.OF',
  fundName: '示例基金A',
  purchasePlan: 'sip',
  plannedAmount: 1000,
  actionHref: '/sales-rules?codes=519674.OF',
  rule: {
    windCode: '519674.OF',
    platform: 'manual-sales-platform',
    purchaseStatus: 'open',
    purchaseStatusSourceBacked: true,
    minPurchaseAmount: 10,
    minPurchaseSourceBacked: true,
    minSipAmount: 10,
    minSipSourceBacked: true,
    dailyLimitAmount: 100000,
    dailyLimitSourceBacked: true,
    purchaseFeeRate: 0.15,
    purchaseFeeSourceBacked: true,
    redemptionFeeRules: [{ holdingDays: 7, feeRate: 1.5, label: '7天内' }],
    redemptionFeeSourceUpdatedAt: new Date().toISOString().slice(0, 10),
    redemptionFeePlatform: 'manual-sales-platform',
    redemptionFeeNotes: '销售平台页面核验',
    salesServiceFeeRate: 0,
    salesServiceFeeSourceBacked: true,
    riskLevel: 'R3',
    supportsSip: true,
    supportsSipSourceBacked: true,
    sourceUpdatedAt: new Date().toISOString().slice(0, 10),
    notes: '销售平台页面核验',
  },
})

const skills = listResearchSkillManifests()

if (!screening.data?.rows.length) throw new Error('screening tool returned no rows')
if (!leader.data?.rows.length) throw new Error('ranking leader tool returned no rows')
if (report.data?.todayDecision !== '今天可沿用研究') throw new Error('report reuse tool returned unexpected decision')
if (salesGate.data?.status !== 'ready') throw new Error('sales rule gate returned unexpected status')
if (skills.length < 6) throw new Error('skill registry is incomplete')
