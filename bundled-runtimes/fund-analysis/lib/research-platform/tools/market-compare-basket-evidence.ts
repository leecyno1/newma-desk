import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type MarketCompareBasketEvidenceItemInput = {
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
  suitabilityLabel: string
  materialLabel: string
  materialMissingItems: string[]
  executionAmountGateLabel?: string | null
  executionAmountGateDetail?: string | null
  readinessLabel: string
  readinessGaps: string[]
  researchListStatus: string
  shareClassHint: string
  fundDetailHref: string
  materialHref: string
}

export type MarketCompareBasketEvidenceGateInput = {
  gapFunds: number
  missingItems: number
  unknownFunds: number
  amountBlockedFunds: number
  suitabilityMismatchFunds: number
  suitabilityMissingFunds: number
}

export type MarketCompareBasketEvidenceReadinessInput = {
  blocked: number
  verify: number
}

export type MarketCompareBasketEvidenceInput = {
  items: MarketCompareBasketEvidenceItemInput[]
  gate: MarketCompareBasketEvidenceGateInput
  readiness: MarketCompareBasketEvidenceReadinessInput
  profileLabel: string
  comparisonHref: string
  materialEvidenceHref: string
}

export type MarketCompareBasketEvidenceRow = {
  rank: number
  windCode: string
  name: string
  type: string
  screeningScore: string
  formalGate: string
  gateReason: string
  suitability: string
  materialStatus: string
  missingItems: string
  amountGate: string
  evidenceStatus: string
  researchListStatus: string
  shareClassHint: string
  nextAction: string
  fundDetailHref: string
  materialHref: string
}

export type MarketCompareBasketEvidenceOutput = {
  rows: MarketCompareBasketEvidenceRow[]
  nextAction: string
  tsv: string
}

const toolName = 'market-compare-basket-evidence'
const version = '1.0.0'

function tsvCell(value: unknown) {
  const text = String(value ?? '')
  return /[\t\n\r"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function buildNextAction(input: MarketCompareBasketEvidenceInput) {
  const gate = input.gate
  if (input.items.length < 2) {
    return '继续从列表加入至少 2 只基金，才能形成横向比较样本。'
  }
  if (gate.gapFunds > 0) {
    return `可先做横向比较，但 ${gate.gapFunds} 只基金仍有 ${gate.missingItems} 项材料核验硬缺口；补齐前不保存研究清单、不生成研究报告复核。`
  }
  if (gate.unknownFunds > 0) {
    return `可先做横向比较，但 ${gate.unknownFunds} 只基金尚未完成材料核验扫描；扫描完成前不保存研究清单、不生成研究报告复核。`
  }
  if (gate.amountBlockedFunds > 0) {
    return `可先做横向比较，但 ${gate.amountBlockedFunds} 只基金的计划金额不满足起点或限额门槛；调整金额或补规则前不保存研究清单、不生成研究报告复核。`
  }
  if (gate.suitabilityMismatchFunds > 0) {
    return `可先做横向比较，但 ${gate.suitabilityMismatchFunds} 只基金风险等级高于当前${input.profileLabel}上限；不进入研究清单、不保存研究报告。`
  }
  if (gate.suitabilityMissingFunds > 0) {
    return `可先做横向比较，但 ${gate.suitabilityMissingFunds} 只基金缺销售风险等级；补 R1-R5 前不保存研究清单、不生成研究报告复核。`
  }
  if (input.readiness.blocked > 0) {
    return '先移出不可入池基金，避免把终止、清算或状态阻断样本带入研究清单。'
  }
  if (input.readiness.verify > 0) {
    return '先补齐材料核验、经理和费率证据，再打开横向比较或保存研究清单。'
  }
  return '当前篮子可进入横向比较，并可保存到研究清单继续做研究报告复核。'
}

function buildRows(input: MarketCompareBasketEvidenceInput): MarketCompareBasketEvidenceRow[] {
  return input.items.map((item, index) => {
    const nextAction = item.formalGatePassed
      ? item.researchListStatus.startsWith('已在')
        ? '已在研究清单；进入基金详情生成或复核研究报告。'
        : '可保存研究清单；仍需基金详情研究报告门禁确认。'
      : `${item.formalGateActionLabel}：${item.formalGateReason}`
    return {
      rank: index + 1,
      windCode: item.windCode,
      name: item.name,
      type: item.type,
      screeningScore: `${item.initialScore}/${item.scoreGrade}/${item.scoreLabel}`,
      formalGate: item.formalGatePassed ? `通过：${item.formalGateReportLabel}` : `阻断：${item.formalGateReportLabel}`,
      gateReason: item.formalGateReason,
      suitability: item.suitabilityLabel,
      materialStatus: item.materialLabel,
      missingItems: item.materialMissingItems.length ? item.materialMissingItems.join('、') : '无',
      amountGate: item.executionAmountGateLabel && item.executionAmountGateDetail ? `${item.executionAmountGateLabel}：${item.executionAmountGateDetail}` : '金额门槛待扫描',
      evidenceStatus: `${item.readinessLabel}${item.readinessGaps.length ? `：${item.readinessGaps.join('、')}` : ''}`,
      researchListStatus: item.researchListStatus,
      shareClassHint: item.shareClassHint,
      nextAction,
      fundDetailHref: item.fundDetailHref,
      materialHref: item.materialHref,
    }
  })
}

function buildTsv(input: MarketCompareBasketEvidenceInput, rows: MarketCompareBasketEvidenceRow[], nextAction: string) {
  return [
    ['排序', '基金代码', '基金名称', '类型', '初筛分', '正式门禁', '门禁原因', '适当性', '材料核验/R1-R5', '缺口项', '计划金额门禁', '证据状态', '研究清单状态', '份额提示', '下一动作', '基金详情入口', '补证入口'],
    ...rows.map((row) => [
      row.rank,
      row.windCode,
      row.name,
      row.type,
      row.screeningScore,
      row.formalGate,
      row.gateReason,
      row.suitability,
      row.materialStatus,
      row.missingItems,
      row.amountGate,
      row.evidenceStatus,
      row.researchListStatus,
      row.shareClassHint,
      row.nextAction,
      row.fundDetailHref,
      row.materialHref,
    ]),
    ['说明', '对比篮证据工作单只服务基金筛选、基金分析和基金经理评价；材料核验/R1-R5、计划金额、适当性和研究报告复核未通过前，不保存正式研究清单，不形成配置建议。', '', '', '', '', '', '', '', '', '', '', '', '', nextAction, input.comparisonHref, input.materialEvidenceHref],
  ].map((row) => row.map(tsvCell).join('\t')).join('\n')
}

export const marketCompareBasketEvidenceTool: ResearchTool<MarketCompareBasketEvidenceInput, MarketCompareBasketEvidenceOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'evidence',
    purpose: '生成全市场对比篮证据工作单、下一步动作和 TSV，避免 Market 页面持有证据导出规则。',
    inputSchema: 'MarketCompareBasketEvidenceInput',
    outputSchema: 'MarketCompareBasketEvidenceOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      '对比篮证据工作单只服务基金研究，不输出申购、赎回或配置建议。',
    ],
  },
  run(input) {
    const rows = buildRows(input)
    const nextAction = buildNextAction(input)
    const output = {
      rows,
      nextAction,
      tsv: buildTsv(input, rows, nextAction),
    }
    return createToolResult(toolName, version, input, output, {
      ok: rows.length >= 2 && input.gate.gapFunds === 0 && input.gate.unknownFunds === 0 && input.gate.amountBlockedFunds === 0 && input.gate.suitabilityMismatchFunds === 0 && input.gate.suitabilityMissingFunds === 0,
      hardBlocks: rows.filter((row) => row.formalGate.startsWith('阻断')).map((row) => `${row.windCode}: ${row.gateReason}`),
      evidence: rows.map((row) => ({
        id: `market-compare-basket-evidence:${row.windCode}`,
        label: '全市场对比篮证据工作单',
        source: 'market.compare_basket.evidence_worklist',
        freshness: 'derived',
        subjectId: row.windCode,
        note: `${row.formalGate}；${row.evidenceStatus}`,
      })),
      gaps: rows.filter((row) => row.missingItems !== '无' || row.formalGate.startsWith('阻断')).map((row) => ({
        key: `market-compare-basket-evidence:${row.windCode}`,
        label: row.formalGate.startsWith('阻断') ? '对比篮证据硬阻断' : '对比篮证据待补',
        severity: row.formalGate.startsWith('阻断') ? 'hard_block' : 'verify_first',
        subjectId: row.windCode,
        reason: row.missingItems !== '无' ? row.missingItems : row.gateReason,
        requiredBeforeFormalReview: true,
      })),
      nextActions: rows.filter((row) => row.missingItems !== '无' || row.formalGate.startsWith('阻断')).map((row) => ({
        key: `market-compare-basket-evidence:${row.windCode}`,
        label: row.formalGate.startsWith('阻断') ? '处理对比篮阻断' : '补对比篮证据',
        href: row.materialHref,
        priority: row.formalGate.startsWith('阻断') ? 'high' : 'medium',
        reason: row.nextAction,
      })),
    })
  },
}
