import { buildResearchEvidence } from '@/lib/research-evidence'
import { FUND_RESEARCH_GUARDRAILS, type EvidenceGap, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type ResearchEvidenceToolReviewMode = 'lump_sum' | 'sip'

export type ResearchEvidenceToolInput = {
  fund: Record<string, unknown>
  reviewMode?: ResearchEvidenceToolReviewMode | null
  plannedAmount?: number | string | null
}

export type ResearchEvidenceToolOutput = ReturnType<typeof buildResearchEvidence>

const toolName = 'research-evidence'
const version = '1.0.0'

function fundCodeOf(fund: Record<string, unknown>) {
  return String(fund.windCode || fund.wind_code || fund.code || fund.id || 'unknown')
}

function fundNameOf(fund: Record<string, unknown>) {
  return String(fund.name || fund.fund_name || fund.fundName || fundCodeOf(fund))
}

function evidenceGapsFromOutput(output: ResearchEvidenceToolOutput, subjectId: string): EvidenceGap[] {
  return output.missingItems.map((item) => ({
    key: item.label,
    label: item.label,
    severity: item.requiredBeforeBuy ? 'hard_block' : item.severity === 'medium' ? 'verify_first' : 'observe',
    subjectId,
    reason: item.reason,
    requiredBeforeFormalReview: item.requiredBeforeBuy,
  }))
}

export const researchEvidenceTool: ResearchTool<ResearchEvidenceToolInput, ResearchEvidenceToolOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'fund',
    purpose: '对单只基金基础事实、材料来源、费用、金额字段和适当性证据做研究复核。',
    inputSchema: 'ResearchEvidenceToolInput',
    outputSchema: 'ResearchEvidenceToolOutput',
    evidencePolicy: 'strict_30d',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      FUND_RESEARCH_GUARDRAILS.tushareFoundationBoundary,
      '研究证据只输出材料核验、补证观察和研究复核状态，不输出申赎操作指令。',
    ],
  },
  run(input) {
    const subjectId = fundCodeOf(input.fund)
    const output = buildResearchEvidence(input.fund, {
      purchasePlan: input.reviewMode,
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
        id: `research-evidence:${subjectId}:${index}`,
        label: item.label,
        source: item.source,
        freshness: item.source.includes('销售规则') ? 'fresh_30d' : 'snapshot',
        subjectId,
        note: `${item.value}；置信度 ${item.confidence}`,
      })),
      nextActions: [{
        key: 'research-evidence-review',
        label: hardBlocks.length ? '补齐研究复核证据' : '进入研究复核',
        href: `/funds/${encodeURIComponent(subjectId)}`,
        priority: hardBlocks.length ? 'high' : 'medium',
        reason: `${fundNameOf(input.fund)}：${output.conclusion}`,
      }],
    })
  },
}
