import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type ScreeningDecisionTraceForHealth = {
  matchedCriteriaCount: number
  missingCriteriaCount: number
  outsideCriteriaCount: number
}

export type SalesRuleGapForHealth = {
  windCode: string
  missingCount?: number | null
  alertsHref?: string | null
}

export type ScreeningConditionHealthInput = {
  hasScreened: boolean
  resultCodes: string[]
  traces: ScreeningDecisionTraceForHealth[]
  salesRuleGaps: SalesRuleGapForHealth[]
  salesRuleGapsChecked: boolean
  salesRuleGapMissingItems: number
  salesRuleGapHref: string
  salesRulesHref: string
  marketHref: string
  screeningReturnHref: string
  comparisonHref: string
}

export type ScreeningConditionHealthRow = {
  key: string
  title: string
  status: string
  detail: string
  actionLabel: string
  actionHref: string
}

export type ScreeningConditionHealthOutput = {
  rows: ScreeningConditionHealthRow[]
  summary: {
    resultCount: number
    totalCriteria: number
    missingCriteria: number
    outsideCriteria: number
    salesRuleGapCount: number
  }
  hardBoundary: string
}

const toolName = 'screening-condition-health'
const version = '1.0.0'

export const screeningConditionHealthTool: ResearchTool<ScreeningConditionHealthInput, ScreeningConditionHealthOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'screening',
    purpose: '把筛选结果解释为条件健康度、证据缺口和下一步研究动作。',
    inputSchema: 'ScreeningConditionHealthInput',
    outputSchema: 'ScreeningConditionHealthOutput',
    evidencePolicy: 'derived_metric',
    canRunBatch: false,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      FUND_RESEARCH_GUARDRAILS.pageAsRenderer,
      '筛选条件健康只说明结果是否值得继续研究，不形成正式研究结论。',
    ],
  },
  run(input) {
    const totalCriteria = input.traces.reduce((sum, trace) => sum + trace.matchedCriteriaCount + trace.missingCriteriaCount + trace.outsideCriteriaCount, 0)
    const missingCriteria = input.traces.reduce((sum, trace) => sum + trace.missingCriteriaCount, 0)
    const outsideCriteria = input.traces.reduce((sum, trace) => sum + trace.outsideCriteriaCount, 0)
    const resultCount = input.resultCodes.length
    const reviewAlertBlocked = input.salesRuleGaps.some((gap) => Boolean(gap.alertsHref))
    const rows: ScreeningConditionHealthRow[] = [
      {
        key: 'result-size',
        title: '结果规模是否合理',
        status: !input.hasScreened ? '待筛选' : resultCount === 0 ? '条件过窄' : resultCount < 3 ? '样本偏少' : '可继续',
        detail: !input.hasScreened
          ? '先运行筛选，才能判断条件是否过窄。'
          : resultCount === 0
            ? '当前条件没有命中基金，优先放宽收益、回撤、规模或基金类型，再回到研究模型重排。'
            : resultCount < 3
              ? `仅命中 ${resultCount} 只，难以形成替代横评；建议放宽一项硬条件或扩大基金类型。`
              : `命中 ${resultCount} 只，可进入证据检查和横向比较。`,
        actionLabel: resultCount >= 3 ? '进入横评' : '放宽筛选',
        actionHref: resultCount >= 3 ? input.comparisonHref : input.marketHref,
      },
      {
        key: 'criteria-evidence',
        title: '筛选条件证据是否充分',
        status: !input.traces.length ? '待补解释' : missingCriteria > 0 || outsideCriteria > 0 ? '证据待补' : '证据较完整',
        detail: !input.traces.length
          ? '当前结果缺少条件级命中解释，不能证明为什么进入研究样本。'
          : missingCriteria > 0 || outsideCriteria > 0
            ? `条件级证据共 ${totalCriteria} 项，其中待补 ${missingCriteria}、未通过 ${outsideCriteria}；缺证不按中性分处理。`
            : `条件级证据 ${totalCriteria} 项均有可解释结果，可继续做销售规则和研究复核。`,
        actionLabel: missingCriteria > 0 || outsideCriteria > 0 ? '下载证据 TSV' : '复核证据 TSV',
        actionHref: input.screeningReturnHref,
      },
      {
        key: 'sales-rule',
        title: '销售规则是否阻断',
        status: !input.salesRuleGapsChecked ? '扫描中' : input.salesRuleGaps.length ? '规则阻断' : '规则未见硬缺口',
        detail: !input.salesRuleGapsChecked
          ? '正在扫描销售规则和复查队列，扫描完成前不能加入研究清单或生成研究复核报告。'
          : input.salesRuleGaps.length
            ? `${input.salesRuleGaps.length} 只基金仍有 ${input.salesRuleGapMissingItems} 项销售规则/R1-R5/申赎字段缺口；先补证。`
            : '当前结果未检测到销售规则硬缺口，仍需研究复核销售平台实时页面。',
        actionLabel: input.salesRuleGaps.length ? reviewAlertBlocked ? '处理复查队列' : '补规则缺口' : '查销售规则',
        actionHref: input.salesRuleGaps.length ? input.salesRuleGapHref : input.salesRulesHref,
      },
      {
        key: 'next-step',
        title: '下一步是否能形成横评',
        status: resultCount >= 2 && input.salesRuleGapsChecked && !input.salesRuleGaps.length ? '可横评' : '先补证',
        detail: resultCount >= 2 && input.salesRuleGapsChecked && !input.salesRuleGaps.length
          ? '样本数量和销售规则初扫允许进入横向比较；横评仍需真实净值、费用和回撤预算证据。'
          : '至少需要两个可比较样本，并先清理销售规则硬缺口后再做横评。',
        actionLabel: resultCount >= 2 ? '打开横评' : '回全市场扩样',
        actionHref: resultCount >= 2 ? input.comparisonHref : input.marketHref,
      },
    ]
    const hardBlocks = [
      ...(!input.hasScreened ? ['尚未运行筛选'] : []),
      ...(input.salesRuleGapsChecked && input.salesRuleGaps.length ? ['销售规则/R1-R5/申赎字段缺口未清零'] : []),
    ]
    return createToolResult(toolName, version, input, {
      rows,
      summary: {
        resultCount,
        totalCriteria,
        missingCriteria,
        outsideCriteria,
        salesRuleGapCount: input.salesRuleGaps.length,
      },
      hardBoundary: '筛选条件健康只说明这批结果是否值得继续研究；销售规则/R1-R5、计划金额、费用、横评和研究复核报告门禁未完成前，不形成正式研究结论。',
    }, {
      ok: hardBlocks.length === 0,
      hardBlocks,
      gaps: [
        ...(missingCriteria ? [{
          key: 'criteria-evidence',
          label: '筛选条件证据待补',
          severity: 'verify_first' as const,
          reason: `条件级证据待补 ${missingCriteria} 项。`,
          requiredBeforeFormalReview: true,
        }] : []),
        ...(input.salesRuleGaps.length ? [{
          key: 'sales-rule',
          label: '销售规则硬缺口',
          severity: 'hard_block' as const,
          reason: `${input.salesRuleGaps.length} 只基金存在销售规则/R1-R5/申赎字段缺口。`,
          requiredBeforeFormalReview: true,
        }] : []),
      ],
      evidence: [{
        id: 'screening-decision-trace',
        label: '筛选条件级证据汇总',
        source: 'screening_api.database_predicate_pushdown_trace_v1',
        freshness: 'derived',
        note: `样本 ${resultCount} 只，条件证据 ${totalCriteria} 项。`,
      }],
      nextActions: rows.map((row) => ({
        key: row.key,
        label: row.actionLabel,
        href: row.actionHref,
        priority: row.key === 'sales-rule' && input.salesRuleGaps.length ? 'high' : 'medium',
        reason: row.detail,
      })),
    })
  },
}
