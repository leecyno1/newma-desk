import { buildBuyEvidence } from '@/lib/buy-evidence'
import { FUND_RESEARCH_GUARDRAILS, type EvidenceGap, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type BuyEvidenceToolPurchasePlan = 'lump_sum' | 'sip'

export type BuyEvidenceToolInput = {
  fund: Record<string, unknown>
  purchasePlan?: BuyEvidenceToolPurchasePlan | null
  plannedAmount?: number | string | null
}

export type BuyEvidenceToolOutput = ReturnType<typeof buildBuyEvidence>

const toolName = 'buy-evidence'
const version = '1.0.0'

function fundCodeOf(fund: Record<string, unknown>) {
  return String(fund.windCode || fund.wind_code || fund.code || fund.id || 'unknown')
}

function fundNameOf(fund: Record<string, unknown>) {
  return String(fund.name || fund.fund_name || fund.fundName || fundCodeOf(fund))
}

function evidenceGapsFromOutput(output: BuyEvidenceToolOutput, subjectId: string): EvidenceGap[] {
  return output.missingItems.map((item) => ({
    key: item.label,
    label: item.label,
    severity: item.requiredBeforeBuy ? 'hard_block' : item.severity === 'medium' ? 'verify_first' : 'observe',
    subjectId,
    reason: item.reason,
    requiredBeforeFormalReview: item.requiredBeforeBuy,
  }))
}

export const buyEvidenceTool: ResearchTool<BuyEvidenceToolInput, BuyEvidenceToolOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'fund',
    purpose: '对单只基金的基础事实、销售规则、费用、金额门禁和适当性证据做研究复核。',
    inputSchema: 'BuyEvidenceToolInput',
    outputSchema: 'BuyEvidenceToolOutput',
    evidencePolicy: 'strict_30d',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      FUND_RESEARCH_GUARDRAILS.tushareFoundationBoundary,
      '研究证据只输出研究核查、补证观察和正式研究复核状态，不输出申赎操作指令。',
    ],
  },
  run(input) {
    const subjectId = fundCodeOf(input.fund)
    const output = buildBuyEvidence(input.fund, {
      purchasePlan: input.purchasePlan,
      plannedAmount: input.plannedAmount,
    })
    const gaps = evidenceGapsFromOutput(output, subjectId)
    const hardBlocks = gaps
      .filter((gap) => gap.requiredBeforeFormalReview)
      .map((gap) => gap.reason)
    return createToolResult(toolName, version, input, output, {
      ok: hardBlocks.length === 0,
      gaps,
      hardBlocks,
      evidence: output.knownItems.map((item, index) => ({
        id: `buy-evidence:${subjectId}:${index}`,
        label: item.label,
        source: item.source,
        freshness: item.source.includes('销售规则') ? 'fresh_30d' : 'snapshot',
        subjectId,
        note: `${item.value}；置信度 ${item.confidence}`,
      })),
      nextActions: [{
        key: 'buy-evidence-review',
        label: hardBlocks.length ? '补齐研究证据' : '进入正式研究复核',
        href: `/funds/${encodeURIComponent(subjectId)}`,
        priority: hardBlocks.length ? 'high' : 'medium',
        reason: `${fundNameOf(input.fund)}：${output.conclusion}`,
      }],
    })
  },
}
