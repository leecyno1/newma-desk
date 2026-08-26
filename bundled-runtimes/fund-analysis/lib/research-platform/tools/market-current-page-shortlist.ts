import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type MarketShortlistLane = 'shortlist' | 'repair' | 'exclude'
export type MarketShortlistPrimaryActionKind = 'compare' | 'review_events' | 'material_evidence' | 'fallback'

export type MarketCurrentPageShortlistItemInput = {
  windCode: string
  name: string
  type: string
  initialScore: number
  scoreGrade: string
  scoreLabel: string
  formalGatePassed: boolean
  formalGateLabel: string
  formalGateReportLabel: string
  formalGateReason: string
  formalGateActionLabel: string
  formalGateActionHref: string
  readinessLevel: 'ready' | 'verify' | 'blocked' | string
  readinessLabel: string
  readinessGaps: string[]
  materialStatus: 'complete' | 'gap' | 'unknown' | string
  materialLabel: string
  materialReviewHref?: string | null
  executionAmountGateStatus?: 'pass' | 'blocked' | 'unknown' | string | null
  executionAmountGateLabel?: string | null
  executionAmountGateDetail?: string | null
  suitabilityStatus: 'matched' | 'mismatch' | 'missing' | string
  suitabilityLabel: string
  hasHoldingEvidence: boolean
  operationStatus?: 'blocked' | 'watch' | 'unknown' | string | null
  researchChecklistLabel: string
  researchChecklistLights: string
  researchChecklistFirstGap: string
  researchChecklistBackend: string
  detailHref: string
}

export type MarketCurrentPageShortlistInput = {
  items: MarketCurrentPageShortlistItemInput[]
  compareLimit: number
}

export type MarketShortlistRow = MarketCurrentPageShortlistItemInput & {
  lane: MarketShortlistLane
  laneLabel: string
  shortlistScore: number
  mainReason: string
  nextAction: string
  href: string
}

export type MarketShortlistPrimaryAction = {
  kind: MarketShortlistPrimaryActionKind
  label: string
  codes: string[]
}

export type MarketCurrentPageShortlistOutput = {
  rows: MarketShortlistRow[]
  topRows: MarketShortlistRow[]
  shortlistRows: MarketShortlistRow[]
  repairRows: MarketShortlistRow[]
  excludeRows: MarketShortlistRow[]
  compareCodes: string[]
  primaryAction: MarketShortlistPrimaryAction
  summary: string
  tsv: string
}

const toolName = 'market-current-page-shortlist'
const version = '1.0.0'

function tsvCell(value: unknown) {
  const text = String(value ?? '')
  return /[\t\n\r"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function scoreItem(item: MarketCurrentPageShortlistItemInput) {
  const amountBlocked = item.executionAmountGateStatus === 'blocked'
  const rawScore = item.initialScore
    + (item.formalGatePassed ? 32 : -18)
    + (item.readinessLevel === 'ready' ? 18 : item.readinessLevel === 'verify' ? 4 : -45)
    + (item.materialStatus === 'complete' ? 22 : item.materialStatus === 'gap' ? -28 : -12)
    + (item.suitabilityStatus === 'matched' ? 18 : item.suitabilityStatus === 'missing' ? -16 : -60)
    + (item.hasHoldingEvidence ? 4 : -4)
    + (amountBlocked ? -55 : 0)
  return Math.max(0, Math.min(100, Math.round(rawScore)))
}

function laneForItem(item: MarketCurrentPageShortlistItemInput): MarketShortlistLane {
  if (item.operationStatus === 'blocked' || item.suitabilityStatus === 'mismatch') return 'exclude'
  return item.formalGatePassed ? 'shortlist' : 'repair'
}

function laneLabel(lane: MarketShortlistLane) {
  if (lane === 'shortlist') return '优先横评'
  if (lane === 'repair') return '先补证'
  return '先排除'
}

function buildRow(item: MarketCurrentPageShortlistItemInput): MarketShortlistRow {
  const lane = laneForItem(item)
  const mainReason = item.formalGatePassed
    ? `${item.initialScore}分；${item.suitabilityLabel}；${item.readinessLabel}；${item.materialLabel}`
    : item.formalGateReason
  const nextAction = lane === 'shortlist'
    ? '加入横评篮；进入详情复核份额成本、回撤等待和研究报告复核。'
    : lane === 'repair'
      ? `${item.formalGateActionLabel}：${item.formalGateReason}`
      : '不进入研究清单；仅保留为排除样本或回看。'
  return {
    ...item,
    lane,
    laneLabel: laneLabel(lane),
    shortlistScore: scoreItem(item),
    mainReason,
    nextAction,
    href: lane === 'repair' ? item.formalGateActionHref : item.detailHref,
  }
}

function buildPrimaryAction(input: MarketCurrentPageShortlistInput, shortlistRows: MarketShortlistRow[], repairRows: MarketShortlistRow[]): MarketShortlistPrimaryAction {
  const compareCodes = shortlistRows.map((row) => row.windCode).slice(0, input.compareLimit)
  const reviewRepairRows = repairRows.filter((row) => Boolean(row.materialReviewHref))
  const repairCodes = repairRows.map((row) => row.windCode).slice(0, input.compareLimit)
  if (compareCodes.length >= 2) {
    return {
      kind: 'compare',
      label: `横评短名单 ${compareCodes.length} 只`,
      codes: compareCodes,
    }
  }
  if (reviewRepairRows.length) {
    return {
      kind: 'review_events',
      label: `先处理复查队列 ${reviewRepairRows.length} 只`,
      codes: reviewRepairRows.map((row) => row.windCode).slice(0, input.compareLimit),
    }
  }
  if (repairCodes.length) {
    return {
      kind: 'material_evidence',
      label: `先补证 ${repairCodes.length} 只`,
      codes: repairCodes,
    }
  }
  return {
    kind: 'fallback',
    label: '回到研究筛选',
    codes: [],
  }
}

function buildTsv(rows: MarketShortlistRow[]) {
  return [
    ['排名', '分层', '研究短名单分', '基金代码', '基金名称', '类型', '初筛分', '正式门禁', '适当性', '材料核验', '金额门禁', '证据状态', '研究体检', '体检六灯', '体检首要缺口', '后端全市场体检', '关键理由', '下一动作', '详情入口'],
    ...rows.map((row, index) => [
      index + 1,
      row.laneLabel,
      row.shortlistScore,
      row.windCode,
      row.name,
      row.type || '待补',
      `${row.initialScore}/${row.scoreGrade}/${row.scoreLabel}`,
      row.formalGatePassed ? row.formalGateReportLabel : row.formalGateLabel,
      row.suitabilityLabel,
      row.materialLabel,
      row.executionAmountGateLabel && row.executionAmountGateDetail ? `${row.executionAmountGateLabel}：${row.executionAmountGateDetail}` : '金额门槛待扫描',
      `${row.readinessLabel}${row.readinessGaps.length ? `：${row.readinessGaps.join('、')}` : ''}`,
      row.researchChecklistLabel,
      row.researchChecklistLights,
      row.researchChecklistFirstGap,
      row.researchChecklistBackend,
      row.mainReason,
      row.nextAction,
      row.href,
    ]),
  ].map((row) => row.map(tsvCell).join('\t')).join('\n')
}

export const marketCurrentPageShortlistTool: ResearchTool<MarketCurrentPageShortlistInput, MarketCurrentPageShortlistOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'screening',
    purpose: '生成全市场当前页研究短名单、分层、主动作和 TSV，避免 Market 页面持有短名单评分规则。',
    inputSchema: 'MarketCurrentPageShortlistInput',
    outputSchema: 'MarketCurrentPageShortlistOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '短名单分只服务基金研究排序；硬阻断不得被高收益或高初筛分抵消。',
    ],
  },
  run(input) {
    const rows = input.items.map(buildRow).sort((left, right) => {
      const laneWeight = { shortlist: 3, repair: 2, exclude: 1 }
      return laneWeight[right.lane] - laneWeight[left.lane]
        || right.shortlistScore - left.shortlistScore
        || right.initialScore - left.initialScore
    })
    const shortlistRows = rows.filter((row) => row.lane === 'shortlist')
    const repairRows = rows.filter((row) => row.lane === 'repair')
    const excludeRows = rows.filter((row) => row.lane === 'exclude')
    const primaryAction = buildPrimaryAction(input, shortlistRows, repairRows)
    const compareCodes = shortlistRows.map((row) => row.windCode).slice(0, input.compareLimit)
    const output = {
      rows,
      topRows: rows.slice(0, 8),
      shortlistRows,
      repairRows,
      excludeRows,
      compareCodes,
      primaryAction,
      summary: rows.length
        ? `当前页 ${rows.length} 只基金：优先横评 ${shortlistRows.length} 只、先补证 ${repairRows.length} 只、先排除 ${excludeRows.length} 只；短名单分只用于研究排序，不能替代正式研究复核。`
        : '当前页暂无基金样本，先加载或放宽筛选条件。',
      tsv: buildTsv(rows),
    }
    return createToolResult(toolName, version, input, output, {
      ok: rows.length > 0 && excludeRows.length === 0,
      hardBlocks: excludeRows.map((row) => `${row.windCode}: ${row.suitabilityLabel || row.formalGateReason}`),
      evidence: rows.map((row) => ({
        id: `market-current-page-shortlist:${row.windCode}`,
        label: '全市场当前页研究短名单',
        source: 'market.current_page_shortlist.derived_metric',
        freshness: 'derived',
        subjectId: row.windCode,
        note: `${row.laneLabel}；研究短名单分 ${row.shortlistScore}`,
      })),
      gaps: rows.filter((row) => row.lane !== 'shortlist').map((row) => ({
        key: `market-current-page-shortlist:${row.windCode}`,
        label: row.lane === 'exclude' ? '短名单硬阻断' : '短名单证据待补',
        severity: row.lane === 'exclude' ? 'hard_block' : 'verify_first',
        subjectId: row.windCode,
        reason: row.mainReason,
        requiredBeforeFormalReview: true,
      })),
      nextActions: rows.filter((row) => row.lane !== 'shortlist').map((row) => ({
        key: `market-current-page-shortlist:${row.windCode}`,
        label: row.lane === 'exclude' ? '保留为排除样本' : row.formalGateActionLabel,
        href: row.href,
        priority: row.lane === 'exclude' ? 'high' : 'medium',
        reason: row.nextAction,
      })),
    })
  },
}
