import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type MarketCompareBasketItemInput = {
  windCode: string
  name: string
  initialScore: number
  scoreGrade: string
  scoreLabel: string
  formalGatePassed: boolean
  formalGateLabel: string
  formalGateReason: string
  readinessLevel: 'ready' | 'verify' | 'blocked' | string
  readinessGaps: string[]
  materialStatus: 'complete' | 'gap' | 'unknown' | string
  materialLabel: string
  materialHref: string
  executionAmountGateStatus?: 'pass' | 'blocked' | 'unknown' | string | null
  executionAmountGateDetail?: string | null
  suitabilityStatus: 'matched' | 'mismatch' | 'missing' | string
  suitabilityLabel: string
  suitabilityDetail: string
  returnValue: number | null
  drawdownValue: number | null
  sharpeValue: number | null
  feeValue: number | null
  fundDetailHref: string
}

export type MarketCompareBasketWinLossInput = {
  items: MarketCompareBasketItemInput[]
  comparisonHref: string
  materialEvidenceHref: string
}

export type MarketCompareBasketLane = '保留横评' | '补证观察' | '淘汰/移出'
export type MarketCompareBasketAuditTone = 'slate' | 'rose' | 'amber' | 'emerald'

export type MarketCompareBasketWinLossRow = MarketCompareBasketItemInput & {
  hardBlocks: string[]
  evidenceGaps: string[]
  researchScore: number
  lane: MarketCompareBasketLane
  winLossLine: string
  nextAction: string
}

export type MarketCompareBasketWinLossAudit = {
  tone: MarketCompareBasketAuditTone
  verdict: string
  summary: string
  nextAction: string
}

export type MarketCompareBasketWinLossOutput = {
  rows: MarketCompareBasketWinLossRow[]
  leader: MarketCompareBasketWinLossRow | null
  audit: MarketCompareBasketWinLossAudit
  tsv: string
}

const toolName = 'market-compare-basket-win-loss'
const version = '1.0.0'

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return `${(Number(value) * 100).toFixed(2)}%`
}

function formatFee(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '待补'
  return `${Number(value).toFixed(2)}%`
}

function tsvCell(value: unknown) {
  const text = String(value ?? '')
  return /[\t\n\r"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function scoreItem(item: MarketCompareBasketItemInput) {
  return item.initialScore
    + (item.formalGatePassed ? 15 : -40)
    + (item.suitabilityStatus === 'matched' ? 10 : item.suitabilityStatus === 'mismatch' ? -30 : -12)
    + (item.materialStatus === 'complete' ? 10 : item.materialStatus === 'gap' ? -18 : -10)
    + (item.readinessLevel === 'ready' ? 8 : item.readinessLevel === 'blocked' ? -25 : -8)
    + (item.returnValue == null ? 0 : item.returnValue * 30)
    - (item.drawdownValue == null ? 0 : Math.abs(item.drawdownValue) * 25)
    - (item.feeValue == null ? 0 : item.feeValue * 2)
}

function buildRow(item: MarketCompareBasketItemInput): MarketCompareBasketWinLossRow {
  const hardBlocks = [
    item.formalGatePassed ? '' : item.formalGateReason,
    item.executionAmountGateStatus === 'blocked' ? item.executionAmountGateDetail || '' : '',
    item.suitabilityStatus === 'mismatch' ? item.suitabilityDetail : '',
  ].filter(Boolean)
  const evidenceGaps = [
    ...item.readinessGaps,
    item.materialStatus !== 'complete' ? item.materialLabel : '',
    item.suitabilityStatus === 'missing' ? 'R1-R5适当性待补' : '',
  ].filter(Boolean)
  const researchScore = scoreItem(item)
  const lane: MarketCompareBasketLane = hardBlocks.length
    ? '淘汰/移出'
    : evidenceGaps.length
      ? '补证观察'
      : '保留横评'
  const winLossLine = hardBlocks[0]
    || evidenceGaps.slice(0, 2).join('、')
    || `初筛 ${item.initialScore}，收益 ${formatPercent(item.returnValue)}，回撤 ${formatPercent(item.drawdownValue)}，夏普 ${item.sharpeValue == null ? '待补' : Number(item.sharpeValue).toFixed(2)}`
  const nextAction = hardBlocks.length
    ? '从对比篮移出或只作排除样本；硬阻断解除后重新加入。'
    : evidenceGaps.length
      ? '先补齐缺口，再重新比较收益、回撤、费用和适当性。'
      : '进入正式横评页面，继续做同类、份额成本和研究报告复核。'
  return {
    ...item,
    hardBlocks,
    evidenceGaps,
    researchScore,
    lane,
    winLossLine,
    nextAction,
  }
}

function buildAudit(input: MarketCompareBasketWinLossInput, rows: MarketCompareBasketWinLossRow[]): MarketCompareBasketWinLossAudit {
  if (input.items.length < 2) {
    return {
      tone: 'slate',
      verdict: '样本不足',
      summary: '至少加入 2 只基金后，才能生成对比篮胜负线。',
      nextAction: '继续从当前页加入同类型、同画像基金。',
    }
  }
  const hardBlockedCount = rows.filter((row) => row.hardBlocks.length).length
  const verifyCount = rows.filter((row) => !row.hardBlocks.length && row.evidenceGaps.length).length
  if (hardBlockedCount) {
    return {
      tone: 'rose',
      verdict: '先淘汰硬阻断',
      summary: `${hardBlockedCount} 只基金触发材料核验、金额门禁或适当性硬阻断；不能进入正式研究清单。`,
      nextAction: '先移出硬阻断样本，或进入材料核验台补证后重新筛选。',
    }
  }
  if (verifyCount) {
    return {
      tone: 'amber',
      verdict: '先补证再判胜负',
      summary: `${verifyCount} 只基金仍缺 R1-R5、材料核验、持仓、费用或研究证据；当前胜负只能作为研究排序。`,
      nextAction: '补齐缺口后重新生成对比篮胜负线。',
    }
  }
  const leader = rows[0] || null
  return {
    tone: 'emerald',
    verdict: '可进入正式横评',
    summary: leader
      ? `${leader.name} 暂列对比篮首位，但仍需进入横评页验证同类、份额成本和报告门禁。`
      : '对比篮可进入正式横评。',
    nextAction: '打开横向比较，继续做详情页研究报告留痕。',
  }
}

function buildTsv(input: MarketCompareBasketWinLossInput, rows: MarketCompareBasketWinLossRow[], audit: MarketCompareBasketWinLossAudit) {
  return [
    ['排序', '胜负分', '处理分层', '基金代码', '基金名称', '初筛分', '收益', '回撤', '夏普', '总费率', '正式门禁', '适当性', '材料核验', '证据缺口', '胜负线/淘汰线', '下一步', '详情入口', '补证入口', '硬边界'],
    ...rows.map((row, index) => [
      index + 1,
      Math.round(row.researchScore),
      row.lane,
      row.windCode,
      row.name,
      `${row.initialScore}/${row.scoreGrade}/${row.scoreLabel}`,
      formatPercent(row.returnValue),
      formatPercent(row.drawdownValue),
      row.sharpeValue == null ? '待补' : Number(row.sharpeValue).toFixed(2),
      formatFee(row.feeValue),
      row.formalGateLabel,
      row.suitabilityLabel,
      row.materialLabel,
      row.evidenceGaps.slice(0, 6).join('、') || '暂无',
      row.winLossLine,
      row.nextAction,
      row.fundDetailHref,
      row.materialHref,
      '对比篮胜负线只服务基金筛选和研究横评；不得替代正式横评、详情页研究报告和材料实时复核。',
    ]),
    ['审计', audit.verdict, audit.summary, '', '', '', '', '', '', '', '', '', '', '', audit.nextAction, input.comparisonHref, input.materialEvidenceHref, '', '字段级缺口不按中性分处理；硬阻断未解除前必须淘汰或降级。'],
  ].map((row) => row.map(tsvCell).join('\t')).join('\n')
}

export const marketCompareBasketWinLossTool: ResearchTool<MarketCompareBasketWinLossInput, MarketCompareBasketWinLossOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'comparison',
    purpose: '生成全市场对比篮胜负线、研究分层、审计和 TSV，避免 Market 页面持有排序门禁规则。',
    inputSchema: 'MarketCompareBasketWinLossInput',
    outputSchema: 'MarketCompareBasketWinLossOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '对比篮胜负线只服务研究横评，不输出申购、赎回或配置建议。',
    ],
  },
  run(input) {
    const rows = input.items.map(buildRow).sort((left, right) => right.researchScore - left.researchScore)
    const audit = buildAudit(input, rows)
    const output = {
      rows,
      leader: rows[0] || null,
      audit,
      tsv: buildTsv(input, rows, audit),
    }
    return createToolResult(toolName, version, input, output, {
      ok: rows.length >= 2 && !rows.some((row) => row.hardBlocks.length),
      hardBlocks: rows.flatMap((row) => row.hardBlocks.map((block) => `${row.windCode}: ${block}`)),
      evidence: rows.map((row) => ({
        id: `market-compare-basket:${row.windCode}`,
        label: '全市场对比篮胜负线',
        source: 'market.compare_basket.derived_metric',
        freshness: 'derived',
        subjectId: row.windCode,
        note: `${row.lane}；${row.winLossLine}`,
      })),
      gaps: rows.filter((row) => row.hardBlocks.length || row.evidenceGaps.length).map((row) => ({
        key: `market-compare-basket:${row.windCode}`,
        label: row.hardBlocks.length ? '对比篮硬阻断' : '对比篮证据待补',
        severity: row.hardBlocks.length ? 'hard_block' : 'verify_first',
        subjectId: row.windCode,
        reason: [...row.hardBlocks, ...row.evidenceGaps].join('；'),
        requiredBeforeFormalReview: true,
      })),
      nextActions: rows.filter((row) => row.hardBlocks.length || row.evidenceGaps.length).map((row) => ({
        key: `market-compare-basket:${row.windCode}`,
        label: row.lane === '淘汰/移出' ? '移出或排除样本' : '补对比篮证据',
        href: row.materialHref,
        priority: row.hardBlocks.length ? 'high' : 'medium',
        reason: row.nextAction,
      })),
    })
  },
}
