import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type MarketDecisionPrimaryActionKind = 'compare' | 'amount_gate' | 'review_events' | 'material_evidence' | 'fallback'

export type MarketDecisionExplainerItemInput = {
  windCode: string
  name: string
  initialScore: number
  formalGatePassed: boolean
  formalGateLabel: string
  materialStatus: 'complete' | 'gap' | 'unknown' | string
  materialReviewHref?: string | null
  executionAmountGateStatus?: 'pass' | 'blocked' | 'unknown' | string | null
  suitabilityStatus: 'matched' | 'mismatch' | 'missing' | string
  readinessLevel: 'ready' | 'verify' | 'blocked' | string
  operationStatus?: 'blocked' | 'watch' | 'unknown' | string | null
}

export type MarketDecisionExplainerInput = {
  items: MarketDecisionExplainerItemInput[]
  profileLabel: string
  activeSortLabel: string
  sortOrder: 'asc' | 'desc'
  compareLimit: number
}

export type MarketDecisionPrimaryAction = {
  kind: MarketDecisionPrimaryActionKind
  label: string
  codes: string[]
}

export type MarketDecisionExplainerOutput = {
  qualityLabel: string
  qualityDetail: string
  actionableRatio: number
  visibleCount: number
  actionableCount: number
  amountBlockedCount: number
  salesRuleBlockedCount: number
  evidenceOnlyCount: number
  suitabilityMismatchCount: number
  primaryAction: MarketDecisionPrimaryAction
  topFundCopy: string
  sortExplanation: string
}

const toolName = 'market-decision-explainer'
const version = '1.0.0'

function buildPrimaryAction(input: MarketDecisionExplainerInput, groups: {
  actionableRows: MarketDecisionExplainerItemInput[]
  amountBlockedRows: MarketDecisionExplainerItemInput[]
  reviewQueueBlockedRows: MarketDecisionExplainerItemInput[]
  salesRuleBlockedRows: MarketDecisionExplainerItemInput[]
  evidenceOnlyRows: MarketDecisionExplainerItemInput[]
}): MarketDecisionPrimaryAction {
  if (groups.actionableRows.length >= 2) {
    return {
      kind: 'compare',
      label: '打开可行动横评',
      codes: groups.actionableRows.map((row) => row.windCode).slice(0, input.compareLimit),
    }
  }
  if (groups.amountBlockedRows.length > 0) {
    return {
      kind: 'amount_gate',
      label: '补金额门槛',
      codes: groups.amountBlockedRows.map((row) => row.windCode),
    }
  }
  if (groups.reviewQueueBlockedRows.length > 0) {
    return {
      kind: 'review_events',
      label: '处理复查队列',
      codes: groups.reviewQueueBlockedRows.map((row) => row.windCode),
    }
  }
  if (groups.salesRuleBlockedRows.length > 0) {
    return {
      kind: 'material_evidence',
      label: '补材料核验/R1-R5',
      codes: groups.salesRuleBlockedRows.map((row) => row.windCode),
    }
  }
  if (groups.evidenceOnlyRows.length >= 2) {
    return {
      kind: 'compare',
      label: '先做证据横评',
      codes: groups.evidenceOnlyRows.map((row) => row.windCode).slice(0, input.compareLimit),
    }
  }
  return {
    kind: 'fallback',
    label: '回到研究筛选',
    codes: [],
  }
}

export const marketDecisionExplainerTool: ResearchTool<MarketDecisionExplainerInput, MarketDecisionExplainerOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'screening',
    purpose: '生成全市场当前页决策质量解释、主动作、排序说明和优先解释样本，避免 Market 页面持有解释规则。',
    inputSchema: 'MarketDecisionExplainerInput',
    outputSchema: 'MarketDecisionExplainerOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '决策解释只服务基金筛选和研究复核，不输出申购、赎回或配置建议。',
    ],
  },
  run(input) {
    const rows = input.items
    const actionableRows = rows.filter((row) => row.formalGatePassed)
    const amountBlockedRows = rows.filter((row) => row.executionAmountGateStatus === 'blocked')
    const reviewQueueBlockedRows = rows.filter((row) => Boolean(row.materialReviewHref))
    const salesRuleBlockedRows = rows.filter((row) => row.materialStatus !== 'complete' || row.suitabilityStatus === 'missing')
    const suitabilityMismatchRows = rows.filter((row) => row.suitabilityStatus === 'mismatch')
    const evidenceOnlyRows = rows.filter((row) =>
      !row.formalGatePassed &&
      row.materialStatus === 'complete' &&
      row.executionAmountGateStatus !== 'blocked' &&
      row.suitabilityStatus === 'matched' &&
      row.readinessLevel !== 'blocked',
    )
    const actionableRatio = rows.length ? Math.round((actionableRows.length / rows.length) * 100) : 0
    const topRows = [...rows]
      .filter((row) => row.operationStatus !== 'blocked')
      .sort((left, right) => right.initialScore - left.initialScore)
      .slice(0, 3)
    const topFundCopy = topRows.length
      ? topRows.map((row) => `${row.name} ${row.initialScore}分/${row.formalGatePassed ? '可继续研究复核' : row.formalGateLabel}`).join('；')
      : '暂无可解释样本'
    const qualityLabel = rows.length === 0
      ? '暂无样本'
      : actionableRows.length > 0
        ? '已有可行动样本'
        : amountBlockedRows.length > 0
          ? '先处理金额门禁'
          : reviewQueueBlockedRows.length > 0
            ? '先处理复查队列'
            : salesRuleBlockedRows.length > 0
              ? '先补材料核验'
              : evidenceOnlyRows.length > 0
                ? '先补研究证据'
                : '先排除不适配样本'
    const qualityDetail = rows.length === 0
      ? '当前没有基金结果，先放宽筛选条件或切换模板。'
      : actionableRows.length > 0
        ? `当前页 ${actionableRows.length} 只基金通过材料核验和${input.profileLabel}适当性门禁，但仍需横评、份额成本和正式研究报告复核。`
        : amountBlockedRows.length > 0
          ? `当前页 ${amountBlockedRows.length} 只基金的计划金额不满足起点或限额门槛，调整金额或补规则前不能进入研究清单。`
          : reviewQueueBlockedRows.length > 0
            ? `当前页 ${reviewQueueBlockedRows.length} 只基金仍有未解决材料核验/R1-R5复查事件，处理前不能进入正式研究清单。`
            : salesRuleBlockedRows.length > 0
              ? `当前页 ${salesRuleBlockedRows.length} 只基金卡在材料核验/R1-R5 来源，缺口不清零就不能进入正式研究清单。`
              : evidenceOnlyRows.length > 0
                ? `当前页 ${evidenceOnlyRows.length} 只基金主要缺持仓、费率、经理或净值回放证据，只能先研究观察。`
                : `当前页 ${suitabilityMismatchRows.length || rows.length} 只基金存在产品状态阻断或风险适当性不匹配，应优先排除。`
    const primaryAction = buildPrimaryAction(input, {
      actionableRows,
      amountBlockedRows,
      reviewQueueBlockedRows,
      salesRuleBlockedRows,
      evidenceOnlyRows,
    })
    const output = {
      qualityLabel,
      qualityDetail,
      actionableRatio,
      visibleCount: rows.length,
      actionableCount: actionableRows.length,
      amountBlockedCount: amountBlockedRows.length,
      salesRuleBlockedCount: salesRuleBlockedRows.length,
      evidenceOnlyCount: evidenceOnlyRows.length,
      suitabilityMismatchCount: suitabilityMismatchRows.length,
      primaryAction,
      topFundCopy,
      sortExplanation: `当前按「${input.activeSortLabel}」${input.sortOrder === 'asc' ? '升序' : '降序'}展示；排序只是研究线索，正式路径仍以材料核验、R1-R5 来源、适当性和研究证据门禁为准。`,
    }
    return createToolResult(toolName, version, input, output, {
      ok: actionableRows.length > 0,
      hardBlocks: rows.filter((row) => row.operationStatus === 'blocked' || row.suitabilityStatus === 'mismatch').map((row) => `${row.windCode}: ${row.formalGateLabel}`),
      evidence: rows.map((row) => ({
        id: `market-decision-explainer:${row.windCode}`,
        label: '全市场当前页决策质量解释',
        source: 'market.decision_explainer.derived_metric',
        freshness: 'derived',
        subjectId: row.windCode,
        note: `${row.initialScore}分；${row.formalGatePassed ? '可行动' : row.formalGateLabel}`,
      })),
      gaps: rows.filter((row) => !row.formalGatePassed).map((row) => ({
        key: `market-decision-explainer:${row.windCode}`,
        label: row.operationStatus === 'blocked' || row.suitabilityStatus === 'mismatch' ? '当前页硬阻断' : '当前页证据待补',
        severity: row.operationStatus === 'blocked' || row.suitabilityStatus === 'mismatch' ? 'hard_block' : 'verify_first',
        subjectId: row.windCode,
        reason: row.formalGateLabel,
        requiredBeforeFormalReview: true,
      })),
      nextActions: rows.filter((row) => !row.formalGatePassed).map((row) => ({
        key: `market-decision-explainer:${row.windCode}`,
        label: row.materialStatus !== 'complete' ? '补材料核验' : '补研究证据',
        href: '#market-decision-explainer',
        priority: row.operationStatus === 'blocked' || row.suitabilityStatus === 'mismatch' ? 'high' : 'medium',
        reason: row.formalGateLabel,
      })),
    })
  },
}
