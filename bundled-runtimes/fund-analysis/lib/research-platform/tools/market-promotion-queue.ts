import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type MarketPromotionLaneKey = 'compare' | 'sales_rules' | 'evidence' | 'exclude'
export type MarketPromotionLaneTone = 'emerald' | 'amber' | 'sky' | 'rose'
export type MarketPromotionPrimaryActionKind = 'material_evidence' | 'evidence_coverage' | 'compare' | 'fallback'

export type MarketPromotionQueueItemInput = {
  windCode: string
  name: string
  initialScore: number
  operationStatus?: 'blocked' | 'watch' | 'unknown' | string | null
  operationReason?: string | null
  readinessGaps: string[]
  materialStatus: 'complete' | 'gap' | 'unknown' | string
  materialMissingCount?: number | null
  materialMissingItems: string[]
  materialReviewHref?: string | null
  materialNextAction?: string | null
  executionAmountGateStatus?: 'pass' | 'blocked' | 'unknown' | string | null
  executionAmountGateDetail?: string | null
  suitabilityStatus: 'matched' | 'mismatch' | 'missing' | string
  suitabilityDetail: string
  formalGateReason: string
  hasHoldingEvidence: boolean
  detailHref: string
  materialHref: string
  researchChecklistLabel: string
  researchChecklistLights: string
  researchChecklistFirstGap: string
  researchChecklistBackend: string
}

export type MarketPromotionQueueInput = {
  items: MarketPromotionQueueItemInput[]
  compareLimit: number
  rowLimitPerLane: number
  visibleCount: number
  profileLabel: string
  materialEvidenceFields: string
}

export type MarketPromotionQueueRow = {
  windCode: string
  name: string
  score: number
  reason: string
  nextAction: string
  href: string
  actionLabel: string
  priorityScore: number
  researchChecklist: string
  researchChecklistLights: string
  researchChecklistFirstGap: string
  researchChecklistBackend: string
}

export type MarketPromotionQueueLane = {
  key: MarketPromotionLaneKey
  title: string
  tone: MarketPromotionLaneTone
  description: string
  rows: MarketPromotionQueueRow[]
}

export type MarketPromotionTaskRow = {
  priority: string
  laneKey: MarketPromotionLaneKey
  lane: string
  windCode: string
  name: string
  score: number
  reason: string
  researchChecklist: string
  researchChecklistLights: string
  researchChecklistFirstGap: string
  researchChecklistBackend: string
  nextAction: string
  href: string
  boundary: string
}

export type MarketPromotionGateAudit = {
  compareCount: number
  salesRulesCount: number
  evidenceCount: number
  excludeCount: number
  totalTaskCount: number
  hardBlockedCount: number
  formalBlockedCount: number
  reviewQueueCount: number
  amountGateCount: number
  primaryBlocker: string
  primaryActionKind: MarketPromotionPrimaryActionKind
  actionableRatio: number
  verdict: string
  boundary: string
}

export type MarketPromotionQueueOutput = {
  lanes: MarketPromotionQueueLane[]
  taskRows: MarketPromotionTaskRow[]
  gateAudit: MarketPromotionGateAudit
  compareCodes: string[]
  salesRuleCodes: string[]
  evidenceCodes: string[]
  promotionCompareCodes: string[]
  compareCodeCount: number
  totalVisible: number
  summary: string
  tasksTsv: string
}

const toolName = 'market-promotion-queue'
const version = '1.0.0'

const laneMeta: Array<Omit<MarketPromotionQueueLane, 'rows'>> = [
  {
    key: 'compare',
    title: '可横评',
    tone: 'emerald',
    description: '材料核验与适当性未触发硬阻断，可进入横向比较，但正式报告仍需逐项复核。',
  },
  {
    key: 'sales_rules',
    title: '补材料核验',
    tone: 'amber',
    description: '材料核验/R1-R5 或复查队列未清零时不允许进入正式研究清单，优先补高分样本。',
  },
  {
    key: 'evidence',
    title: '补持仓或费用',
    tone: 'sky',
    description: '材料核验相对完整，但持仓、费率、经理或净值回放不足，只能先做研究观察。',
  },
  {
    key: 'exclude',
    title: '排除',
    tone: 'rose',
    description: '产品状态阻断或风险适当性不匹配，不能进入研究清单。',
  },
]

function tsvCell(value: unknown) {
  const text = String(value ?? '')
  return /[\t\n\r"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function missingResearchEvidence(item: MarketPromotionQueueItemInput) {
  return item.readinessGaps.filter((gap) =>
    !gap.includes('销售')
    && !gap.includes('风险适当性')
    && !gap.includes('申购状态')
    && !gap.startsWith('销售缺'),
  )
}

function laneForItem(item: MarketPromotionQueueItemInput, missingEvidence: string[]): MarketPromotionLaneKey {
  const amountBlocked = item.executionAmountGateStatus === 'blocked'
  if (item.operationStatus === 'blocked' || item.suitabilityStatus === 'mismatch') return 'exclude'
  if (item.materialStatus !== 'complete' || amountBlocked || item.suitabilityStatus === 'missing') return 'sales_rules'
  if (missingEvidence.length > 0 || !item.hasHoldingEvidence) return 'evidence'
  return 'compare'
}

function buildReason(input: MarketPromotionQueueInput, item: MarketPromotionQueueItemInput, laneKey: MarketPromotionLaneKey, missingEvidence: string[], evidenceGapCopy: string) {
  if (laneKey === 'compare') return `初筛 ${item.initialScore} 分，${item.formalGateReason}`
  if (laneKey === 'sales_rules') {
    if (item.executionAmountGateStatus === 'blocked') return `初筛 ${item.initialScore} 分，但${item.executionAmountGateDetail || '计划金额不满足金额门槛'}`
    if (item.materialReviewHref) return `初筛 ${item.initialScore} 分，但复查队列仍有未解决材料核验/R1-R5事件：${item.materialMissingItems.slice(0, 2).join('、') || '证据待补'}。`
    if (item.materialStatus === 'unknown') return `初筛 ${item.initialScore} 分，但材料核验尚未扫描；不能推断 ${input.profileLabel} 画像适当性通过。`
    return `初筛 ${item.initialScore} 分，材料核验缺 ${item.materialMissingCount ?? 0} 项：${item.materialMissingItems.slice(0, 3).join('、') || '风险等级/来源证据'}。`
  }
  if (laneKey === 'evidence') return `初筛 ${item.initialScore} 分，材料核验相对完整；仍缺 ${evidenceGapCopy}，先横评观察。`
  return `初筛 ${item.initialScore} 分，但${item.operationStatus === 'blocked' ? '存在产品状态阻断' : item.suitabilityDetail}。`
}

function buildNextAction(input: MarketPromotionQueueInput, item: MarketPromotionQueueItemInput, laneKey: MarketPromotionLaneKey, evidenceGapCopy: string) {
  if (laneKey === 'compare') return '加入横评篮，比较同类、份额成本、回撤和研究报告证据。'
  if (laneKey === 'sales_rules') {
    if (item.executionAmountGateStatus === 'blocked') return '调整计划金额，或补齐起点/限额/份额规则后再复核。'
    if (item.materialReviewHref) return '先打开复查队列，处理材料核验/R1-R5过期或待补事件，再回到全市场严格复核。'
    return item.materialNextAction || `先补${input.materialEvidenceFields}，再回到全市场复核。`
  }
  if (laneKey === 'evidence') return `补 ${evidenceGapCopy} 后，再决定是否进入正式研究清单。`
  return item.operationReason || item.suitabilityDetail
}

function buildRow(input: MarketPromotionQueueInput, item: MarketPromotionQueueItemInput): { laneKey: MarketPromotionLaneKey; row: MarketPromotionQueueRow } {
  const missingEvidence = missingResearchEvidence(item)
  const evidenceGapCopy = missingEvidence.slice(0, 3).join('、') || (item.hasHoldingEvidence ? '净值回放/经理证据' : '持仓暴露')
  const laneKey = laneForItem(item, missingEvidence)
  const reason = buildReason(input, item, laneKey, missingEvidence, evidenceGapCopy)
  const nextAction = buildNextAction(input, item, laneKey, evidenceGapCopy)
  const row = {
    windCode: item.windCode,
    name: item.name,
    score: item.initialScore,
    reason,
    nextAction,
    href: laneKey === 'sales_rules' ? (item.materialReviewHref || item.materialHref) : item.detailHref,
    actionLabel: laneKey === 'compare'
      ? '看详情'
      : laneKey === 'sales_rules'
        ? item.materialReviewHref ? '开复查队列' : '补材料'
        : laneKey === 'evidence'
          ? '补证据'
          : '看排除原因',
    priorityScore: item.initialScore
      + (laneKey === 'compare' ? 80 : laneKey === 'sales_rules' ? 50 : laneKey === 'evidence' ? 30 : -60)
      - (item.materialMissingCount || 0) * 3
      - missingEvidence.length * 2,
    researchChecklist: item.researchChecklistLabel,
    researchChecklistLights: item.researchChecklistLights,
    researchChecklistFirstGap: item.researchChecklistFirstGap,
    researchChecklistBackend: item.researchChecklistBackend,
  }
  return { laneKey, row }
}

function taskBoundary(laneKey: MarketPromotionLaneKey) {
  if (laneKey === 'compare') return '仍需研究复核报告、横评和材料来源实时复核'
  if (laneKey === 'sales_rules') return '材料核验和R1-R5来源背书未清零前，不进正式研究清单'
  if (laneKey === 'evidence') return '证据补齐前只做研究观察，不保存正式研究报告'
  return '排除项不进入研究清单'
}

function buildTaskRows(lanes: MarketPromotionQueueLane[]): MarketPromotionTaskRow[] {
  return lanes.flatMap((lane, laneIndex) =>
    lane.rows.map((row, rowIndex) => ({
      priority: `P${laneIndex + 1}.${rowIndex + 1}`,
      laneKey: lane.key,
      lane: lane.title,
      windCode: row.windCode,
      name: row.name,
      score: row.score,
      reason: row.reason,
      researchChecklist: row.researchChecklist,
      researchChecklistLights: row.researchChecklistLights,
      researchChecklistFirstGap: row.researchChecklistFirstGap,
      researchChecklistBackend: row.researchChecklistBackend,
      nextAction: row.nextAction,
      href: row.href,
      boundary: taskBoundary(lane.key),
    })),
  )
}

function buildGateAudit(taskRows: MarketPromotionTaskRow[]): MarketPromotionGateAudit {
  const countByLane = taskRows.reduce<Record<string, number>>((acc, row) => {
    acc[row.laneKey] = (acc[row.laneKey] || 0) + 1
    return acc
  }, {})
  const compareCount = countByLane.compare || 0
  const salesRulesCount = countByLane.sales_rules || 0
  const evidenceCount = countByLane.evidence || 0
  const excludeCount = countByLane.exclude || 0
  const totalTaskCount = taskRows.length
  const hardBlockedCount = salesRulesCount + excludeCount
  const formalBlockedCount = salesRulesCount + evidenceCount + excludeCount
  const reviewQueueCount = taskRows.filter((row) => row.reason.includes('复查队列')).length
  const amountGateCount = taskRows.filter((row) => row.reason.includes('计划金额') || row.reason.includes('金额门槛')).length
  const primaryBlocker = salesRulesCount > 0
    ? (reviewQueueCount > 0 ? '复查队列/R1-R5 未清零' : amountGateCount > 0 ? '计划金额门禁或材料核验未过' : '材料核验/R1-R5 来源未补齐')
    : evidenceCount > 0
      ? '持仓、费用、经理或净值回放证据不足'
      : excludeCount > 0
        ? '产品状态或风险适当性不匹配'
        : '当前页未发现结构化硬阻断'
  const primaryActionKind: MarketPromotionPrimaryActionKind = salesRulesCount > 0
    ? 'material_evidence'
    : evidenceCount > 0
      ? 'evidence_coverage'
      : compareCount > 0
        ? 'compare'
        : 'fallback'
  return {
    compareCount,
    salesRulesCount,
    evidenceCount,
    excludeCount,
    totalTaskCount,
    hardBlockedCount,
    formalBlockedCount,
    reviewQueueCount,
    amountGateCount,
    primaryBlocker,
    primaryActionKind,
    actionableRatio: totalTaskCount > 0 ? Math.round((compareCount / totalTaskCount) * 100) : 0,
    verdict: hardBlockedCount > 0
      ? '当前页不能整体进入正式研究清单'
      : evidenceCount > 0
        ? '当前页可研究但仍需补证'
        : compareCount > 0
          ? '当前页可进入横评复核'
          : '当前页暂无可行动样本',
    boundary: '门禁体检只服务基金筛选与基金研究；硬阻断不因收益、规模或初筛分较高而被放行。',
  }
}

function buildTasksTsv(taskRows: MarketPromotionTaskRow[], gateAudit: MarketPromotionGateAudit) {
  return [
    ['优先级', '分流', '基金代码', '基金名称', '初筛分', '缺口/原因', '研究体检', '体检六灯', '体检首要缺口', '后端全市场体检', '下一步', '入口', '研究边界'],
    ...taskRows.map((row) => [
      row.priority,
      row.lane,
      row.windCode,
      row.name,
      row.score,
      row.reason,
      row.researchChecklist,
      row.researchChecklistLights,
      row.researchChecklistFirstGap,
      row.researchChecklistBackend,
      row.nextAction,
      row.href,
      row.boundary,
    ]),
    ['审计', gateAudit.verdict, '可横评', gateAudit.compareCount, '补材料', gateAudit.salesRulesCount, '补证据', gateAudit.evidenceCount, '排除', gateAudit.excludeCount, '主阻断', gateAudit.primaryBlocker, gateAudit.boundary],
  ].map((row) => row.map(tsvCell).join('\t')).join('\n')
}

export const marketPromotionQueueTool: ResearchTool<MarketPromotionQueueInput, MarketPromotionQueueOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'screening',
    purpose: '生成全市场晋级分流、任务队列、门禁审计和 TSV，避免 Market 页面持有分流规则。',
    inputSchema: 'MarketPromotionQueueInput',
    outputSchema: 'MarketPromotionQueueOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '晋级分流只服务基金研究，不输出申购、赎回或配置建议。',
    ],
  },
  run(input) {
    const lanes = laneMeta.map((lane) => ({ ...lane, rows: [] as MarketPromotionQueueRow[] }))
    input.items.slice(0, 30).forEach((item) => {
      const { laneKey, row } = buildRow(input, item)
      lanes.find((lane) => lane.key === laneKey)?.rows.push(row)
    })
    const sortedLanes = lanes.map((lane) => ({
      ...lane,
      rows: lane.rows.sort((left, right) => right.priorityScore - left.priorityScore).slice(0, input.rowLimitPerLane),
    }))
    const compareCodes = sortedLanes.find((lane) => lane.key === 'compare')?.rows.map((row) => row.windCode).slice(0, input.compareLimit) || []
    const salesRuleCodes = sortedLanes.find((lane) => lane.key === 'sales_rules')?.rows.map((row) => row.windCode) || []
    const evidenceCodes = sortedLanes.find((lane) => lane.key === 'evidence')?.rows.map((row) => row.windCode).slice(0, input.compareLimit) || []
    const promotionCompareCodes = compareCodes.length >= 2 ? compareCodes : evidenceCodes
    const taskRows = buildTaskRows(sortedLanes)
    const gateAudit = buildGateAudit(taskRows)
    const output = {
      lanes: sortedLanes,
      taskRows,
      gateAudit,
      compareCodes,
      salesRuleCodes,
      evidenceCodes,
      promotionCompareCodes,
      compareCodeCount: promotionCompareCodes.length,
      totalVisible: input.visibleCount,
      summary: `当前可见 ${input.visibleCount} 只基金：可横评 ${sortedLanes.find((lane) => lane.key === 'compare')?.rows.length || 0} 只，待补材料核验 ${sortedLanes.find((lane) => lane.key === 'sales_rules')?.rows.length || 0} 只，待补持仓或费用 ${sortedLanes.find((lane) => lane.key === 'evidence')?.rows.length || 0} 只。`,
      tasksTsv: buildTasksTsv(taskRows, gateAudit),
    }
    return createToolResult(toolName, version, input, output, {
      ok: gateAudit.hardBlockedCount === 0,
      hardBlocks: taskRows.filter((row) => row.laneKey === 'sales_rules' || row.laneKey === 'exclude').map((row) => `${row.windCode}: ${row.reason}`),
      evidence: taskRows.map((row) => ({
        id: `market-promotion-queue:${row.windCode}`,
        label: '全市场晋级分流',
        source: 'market.promotion_queue.derived_metric',
        freshness: 'derived',
        subjectId: row.windCode,
        note: `${row.lane}；${row.reason}`,
      })),
      gaps: taskRows.filter((row) => row.laneKey !== 'compare').map((row) => ({
        key: `market-promotion-queue:${row.windCode}`,
        label: row.laneKey === 'exclude' ? '晋级硬阻断' : '晋级证据待补',
        severity: row.laneKey === 'exclude' || row.laneKey === 'sales_rules' ? 'hard_block' : 'verify_first',
        subjectId: row.windCode,
        reason: row.reason,
        requiredBeforeFormalReview: true,
      })),
      nextActions: taskRows.filter((row) => row.laneKey !== 'compare').map((row) => ({
        key: `market-promotion-queue:${row.windCode}`,
        label: row.laneKey === 'exclude' ? '保留为排除样本' : row.laneKey === 'sales_rules' ? '补材料核验' : '补研究证据',
        href: row.href,
        priority: row.laneKey === 'sales_rules' || row.laneKey === 'exclude' ? 'high' : 'medium',
        reason: row.nextAction,
      })),
    })
  },
}
