import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import {
  buildExecutionAmountGate,
  buildSalesRuleMissingItems,
  isStaleSourceDate,
  riskLevelEvidence,
  statusFromMissingItems,
  type SalesRuleGateInput,
  type SalesRuleGateOutput,
} from './sales-rule-gate'
import { createToolResult } from './tooling'

export type MaterialEvidenceGateInput = SalesRuleGateInput
export type MaterialEvidenceGateOutput = SalesRuleGateOutput

const toolName = 'material-evidence-gate'
const version = '1.0.0'

export const materialEvidenceGateTool: ResearchTool<MaterialEvidenceGateInput, MaterialEvidenceGateOutput> = {
  manifest: {
    name: 'material-evidence-gate',
    version,
    domain: 'evidence',
    purpose: '对单只基金的销售端材料、R1-R5、费用、开放状态和金额字段做材料核验。',
    inputSchema: 'MaterialEvidenceGateInput',
    outputSchema: 'MaterialEvidenceGateOutput',
    evidencePolicy: 'strict_30d',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.noTradingDirective,
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      FUND_RESEARCH_GUARDRAILS.tushareFoundationBoundary,
      '材料核验只判断字段来源、时效和缺口，不输出申赎操作或研究结论动作。',
    ],
  },
  run(input) {
    const fundName = input.fundName || input.windCode
    const executionAmountGate = buildExecutionAmountGate(input.rule, input)
    const riskEvidence = riskLevelEvidence(input.rule)
    const missingItems = buildSalesRuleMissingItems(input)
    const status = statusFromMissingItems(missingItems, executionAmountGate)
    const actionHref = input.actionHref || `/evidence-coverage?section=materials&codes=${encodeURIComponent(input.windCode)}`
    const output: MaterialEvidenceGateOutput = {
      windCode: input.windCode,
      fundName,
      status,
      label: status === 'ready' ? '材料证据相对完整' : status === 'unknown' ? '材料证据待扫描' : '材料证据硬缺口',
      missingItems,
      missingCount: missingItems.length,
      riskEvidence,
      executionAmountGate,
      nextAction: missingItems.length
        ? `补齐 ${missingItems.slice(0, 3).join('、')}`
        : status === 'unknown'
          ? executionAmountGate.actionLabel
          : '材料证据相对完整，研究复核确认实时状态',
      actionHref,
      hardBoundary: '销售端材料、R1-R5、申赎、费用、起购、定投、限购和计划金额证据未过前，只能作为补证观察。',
    }
    return createToolResult(toolName, version, input, output, {
      ok: status === 'ready',
      hardBlocks: status === 'blocked' ? missingItems : [],
      gaps: missingItems.map((item) => ({
        key: item,
        label: item,
        severity: 'hard_block',
        subjectId: input.windCode,
        reason: `${fundName}：${item}`,
        requiredBeforeFormalReview: true,
      })),
      evidence: [{
        id: `material-evidence-gate:${input.windCode}`,
        label: '材料证据核验',
        source: input.rule?.sourceUrl || input.rule?.notes || input.rule?.platform || 'local.material_evidence',
        sourceUpdatedAt: input.rule?.sourceUpdatedAt || null,
        freshness: input.rule?.sourceUpdatedAt && !isStaleSourceDate(input.rule.sourceUpdatedAt) ? 'fresh_30d' : input.rule ? 'stale' : 'missing',
        subjectId: input.windCode,
        note: output.label,
      }],
      nextActions: [{
        key: 'material-evidence-gate',
        label: output.nextAction,
        href: output.actionHref,
        priority: status === 'blocked' ? 'high' : 'medium',
        reason: output.hardBoundary,
      }],
    })
  },
}
