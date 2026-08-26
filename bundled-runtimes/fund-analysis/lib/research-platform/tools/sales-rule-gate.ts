import { hasValidSalesRuleSourceIdentityEvidence } from '@/lib/sales-rule-source-evidence'
import { materialEvidenceHref } from '@/lib/research-platform/routes'
import { FUND_RESEARCH_GUARDRAILS, type ResearchTool } from '../contracts'
import { createToolResult } from './tooling'

export type SalesRuleGatePurchasePlan = 'lump_sum' | 'sip'

export type SalesRuleGateRule = {
  windCode?: string
  platform?: string | null
  purchaseStatus?: 'open' | 'closed' | 'limited' | 'unknown' | string | null
  purchaseStatusSourceBacked?: boolean
  minPurchaseAmount?: number | null
  minPurchaseSourceBacked?: boolean
  minSipAmount?: number | null
  minSipSourceBacked?: boolean
  dailyLimitAmount?: number | null
  dailyLimitSourceBacked?: boolean
  purchaseFeeRate?: number | null
  purchaseFeeSourceBacked?: boolean
  redemptionFeeRules?: Array<{ holdingDays?: number | null; feeRate?: number | null; label?: string }>
  redemptionFeeSourceUrl?: string | null
  redemptionFeeSourceUpdatedAt?: string | null
  redemptionFeePlatform?: string | null
  redemptionFeeNotes?: string | null
  salesServiceFeeRate?: number | null
  salesServiceFeeSourceBacked?: boolean
  riskLevel?: string | null
  supportsSip?: boolean | null
  supportsSipSourceBacked?: boolean
  sourceUrl?: string | null
  sourceUpdatedAt?: string | null
  notes?: string | null
  updatedAt?: string | null
}

export type SalesRuleGateInput = {
  windCode: string
  fundName?: string
  rule: SalesRuleGateRule | null
  purchasePlan?: SalesRuleGatePurchasePlan | null
  plannedAmount?: number | null
  actionHref?: string
}

export type SalesRuleExecutionAmountGate = {
  plannedAmount: number | null
  status: 'pass' | 'blocked' | 'unknown'
  label: string
  detail: string
  advice: string
  actionLabel: string
  shortfallAmount: number | null
  suggestedAmount: number | null
  minPurchaseAmount: number | null
  minSipAmount: number | null
  dailyLimitAmount: number | null
}

export type SalesRuleRiskEvidence = {
  riskLevel: string | null
  sourceBacked: boolean
  status: 'verified' | 'missing' | 'unsourced' | 'stale'
  label: string
  detail: string
}

export type SalesRuleGateOutput = {
  windCode: string
  fundName: string
  status: 'ready' | 'blocked' | 'unknown'
  label: string
  missingItems: string[]
  missingCount: number
  riskEvidence: SalesRuleRiskEvidence
  executionAmountGate: SalesRuleExecutionAmountGate
  nextAction: string
  actionHref: string
  hardBoundary: string
}

const toolName = 'sales-rule-gate'
const version = '1.0.0'
const maxSourceAgeDays = 30

function normalizePurchasePlan(value: SalesRuleGateInput['purchasePlan']) {
  return value === 'lump_sum' || value === 'sip' ? value : 'sip'
}

function normalizePlannedAmount(value: SalesRuleGateInput['plannedAmount']) {
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? amount : null
}

export function isStaleSourceDate(value: string | null | undefined) {
  if (!value) return false
  const sourceDate = new Date(`${value.slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(sourceDate.getTime())) return true
  const currentDate = new Date()
  currentDate.setUTCHours(0, 0, 0, 0)
  const ageDays = Math.floor((currentDate.getTime() - sourceDate.getTime()) / 86_400_000)
  return ageDays > maxSourceAgeDays || ageDays < 0
}

function hasRiskSourceEvidence(rule: SalesRuleGateRule | null) {
  const riskLevel = String(rule?.riskLevel || '').trim().toUpperCase()
  if (!/^R[1-5]$/u.test(riskLevel)) return false
  if (!rule?.sourceUpdatedAt || isStaleSourceDate(rule.sourceUpdatedAt)) return false
  return hasValidSalesRuleSourceIdentityEvidence({
    platform: rule.platform,
    sourceUrl: rule.sourceUrl,
    notes: rule.notes,
  })
}

function hasSourceBackedRedemptionRules(rule: SalesRuleGateRule | null) {
  if (!rule?.redemptionFeeRules?.length) return false
  const sourceUpdatedAt = rule.redemptionFeeSourceUpdatedAt || rule.sourceUpdatedAt
  if (!sourceUpdatedAt || isStaleSourceDate(sourceUpdatedAt)) return false
  return hasValidSalesRuleSourceIdentityEvidence({
    platform: rule.redemptionFeePlatform || rule.platform,
    sourceUrl: rule.redemptionFeeSourceUrl || rule.sourceUrl,
    notes: rule.redemptionFeeNotes || rule.notes,
  })
}

export function buildExecutionAmountGate(rule: SalesRuleGateRule | null, input: SalesRuleGateInput): SalesRuleExecutionAmountGate {
  const purchasePlan = normalizePurchasePlan(input.purchasePlan)
  const plannedAmount = normalizePlannedAmount(input.plannedAmount)
  const minPurchaseAmount = rule?.minPurchaseSourceBacked ? rule.minPurchaseAmount ?? null : null
  const minSipAmount = rule?.minSipSourceBacked ? rule.minSipAmount ?? null : null
  const dailyLimitAmount = rule?.dailyLimitSourceBacked ? rule.dailyLimitAmount ?? null : null
  const supportsSip = rule?.supportsSipSourceBacked ? rule.supportsSip ?? null : null

  if (plannedAmount === null) {
    return {
      plannedAmount,
      status: 'unknown',
      label: '计划金额待设置',
      detail: '未提供计划金额，不能判断是否满足起购、定投起点或限购约束。',
      advice: '先输入真实计划金额，再扫描起购、定投和限购门槛；未设置金额不能进入正式研究复核报告。',
      actionLabel: '设置计划金额',
      shortfallAmount: null,
      suggestedAmount: null,
      minPurchaseAmount,
      minSipAmount,
      dailyLimitAmount,
    }
  }
  if (!rule) {
    return {
      plannedAmount,
      status: 'unknown',
      label: '金额门槛待补',
      detail: '本地未取得销售规则，不能判断计划金额是否满足起购、定投起点或限购。',
      advice: '先补销售平台起购、定投起点和限购金额；未补前只能作为补证观察对象。',
      actionLabel: '补金额规则',
      shortfallAmount: null,
      suggestedAmount: null,
      minPurchaseAmount,
      minSipAmount,
      dailyLimitAmount,
    }
  }
  if (purchasePlan === 'sip' && supportsSip === false) {
    return {
      plannedAmount,
      status: 'blocked',
      label: '不支持定投',
      detail: '当前研究方式为定投，但销售规则显示不支持定投。',
      advice: '切换研究方式并重新评估，或换一只明确支持定投且适合当前画像的份额。',
      actionLabel: '换研究方式或份额',
      shortfallAmount: null,
      suggestedAmount: null,
      minPurchaseAmount,
      minSipAmount,
      dailyLimitAmount,
    }
  }
  const minimumAmount = purchasePlan === 'sip' ? minSipAmount : minPurchaseAmount
  if (minimumAmount === null) {
    return {
      plannedAmount,
      status: 'unknown',
      label: purchasePlan === 'sip' ? '定投起点待补' : '起购金额待补',
      detail: purchasePlan === 'sip'
        ? '缺少销售平台定投起点，不能判断月扣款金额是否可执行。'
        : '缺少销售平台起购金额，不能判断一次性计划金额是否可执行。',
      advice: purchasePlan === 'sip'
        ? '先补销售平台定投起点；未确认前不能把月扣款金额视为可执行研究条件。'
        : '先补销售平台起购金额；未确认前不能把一次性计划金额视为可执行研究条件。',
      actionLabel: purchasePlan === 'sip' ? '补定投起点' : '补起购金额',
      shortfallAmount: null,
      suggestedAmount: null,
      minPurchaseAmount,
      minSipAmount,
      dailyLimitAmount,
    }
  }
  if (plannedAmount < minimumAmount) {
    const shortfallAmount = minimumAmount - plannedAmount
    return {
      plannedAmount,
      status: 'blocked',
      label: purchasePlan === 'sip' ? '低于定投起点' : '低于起购金额',
      detail: `计划金额 ${plannedAmount.toLocaleString('zh-CN')} 元低于${purchasePlan === 'sip' ? '定投起点' : '起购金额'} ${minimumAmount.toLocaleString('zh-CN')} 元。`,
      advice: `若仍研究该基金，计划金额至少提高到 ${minimumAmount.toLocaleString('zh-CN')} 元，还差 ${shortfallAmount.toLocaleString('zh-CN')} 元；否则换起点更低的同类基金或份额。`,
      actionLabel: '提高金额或换低门槛基金',
      shortfallAmount,
      suggestedAmount: minimumAmount,
      minPurchaseAmount,
      minSipAmount,
      dailyLimitAmount,
    }
  }
  if (dailyLimitAmount !== null && dailyLimitAmount > 0 && plannedAmount > dailyLimitAmount) {
    const shortfallAmount = plannedAmount - dailyLimitAmount
    return {
      plannedAmount,
      status: 'blocked',
      label: '超过限购金额',
      detail: `计划金额 ${plannedAmount.toLocaleString('zh-CN')} 元超过销售端限购 ${dailyLimitAmount.toLocaleString('zh-CN')} 元。`,
      advice: `若仍研究该基金，单次计划金额需降到 ${dailyLimitAmount.toLocaleString('zh-CN')} 元以内，当前超出 ${shortfallAmount.toLocaleString('zh-CN')} 元；否则换不限购或限购更高的同类基金。`,
      actionLabel: '降低金额或换不限购基金',
      shortfallAmount,
      suggestedAmount: dailyLimitAmount,
      minPurchaseAmount,
      minSipAmount,
      dailyLimitAmount,
    }
  }
  return {
    plannedAmount,
    status: 'pass',
    label: '计划金额可执行',
    detail: purchasePlan === 'sip'
      ? `计划月扣款 ${plannedAmount.toLocaleString('zh-CN')} 元满足当前定投起点与限购约束；研究复核仍需确认销售平台实时状态。`
      : `计划金额 ${plannedAmount.toLocaleString('zh-CN')} 元满足当前起购与限购约束；研究复核仍需确认销售平台实时状态。`,
    advice: '金额门槛当前通过；下一步继续核 R1-R5 适当性、申购状态、费用和赎回规则。',
    actionLabel: '继续研究核查',
    shortfallAmount: null,
    suggestedAmount: plannedAmount,
    minPurchaseAmount,
    minSipAmount,
    dailyLimitAmount,
  }
}

export function riskLevelEvidence(rule: SalesRuleGateRule | null): SalesRuleRiskEvidence {
  const riskLevel = String(rule?.riskLevel || '').trim().toUpperCase()
  if (!/^R[1-5]$/u.test(riskLevel)) {
    return {
      riskLevel: null,
      sourceBacked: false,
      status: 'missing',
      label: 'R1-R5 待补',
      detail: '未取得销售平台或基金合同风险等级，不能用于适当性匹配。',
    }
  }
  if (!rule?.sourceUpdatedAt) {
    return {
      riskLevel,
      sourceBacked: false,
      status: 'unsourced',
      label: `${riskLevel} 缺来源日期`,
      detail: '已填写风险等级，但缺少可追溯来源日期，仍按销售风险等级缺口处理。',
    }
  }
  if (isStaleSourceDate(rule.sourceUpdatedAt)) {
    return {
      riskLevel,
      sourceBacked: false,
      status: 'stale',
      label: `${riskLevel} 来源过旧`,
      detail: '风险等级来源日期已超过研究复核窗口，需重新核验销售平台或基金合同。',
    }
  }
  if (!hasRiskSourceEvidence(rule)) {
    return {
      riskLevel,
      sourceBacked: false,
      status: 'unsourced',
      label: `${riskLevel} 缺来源背书`,
      detail: '已填写风险等级但缺少销售平台/基金合同来源证据，不能用于适当性匹配。',
    }
  }
  return {
    riskLevel,
    sourceBacked: true,
    status: 'verified',
    label: `${riskLevel} 有来源`,
    detail: '风险等级具备来源日期与销售平台/基金合同来源背书；研究复核仍需确认实时状态。',
  }
}

export function buildSalesRuleMissingItems(input: SalesRuleGateInput) {
  const rule = input.rule
  const purchasePlan = normalizePurchasePlan(input.purchasePlan)
  const executionAmountGate = buildExecutionAmountGate(rule, input)
  const executionAmountMissingItems = executionAmountGate.status === 'blocked'
    ? [`计划金额执行门禁：${executionAmountGate.label}`]
    : []
  if (!rule) {
    return [
      '销售规则整条待补',
      '申购状态（30天来源背书）',
      '申购费率（30天来源背书）',
      '赎回费/持有期',
      '最低申购金额（30天来源背书）',
      purchasePlan === 'lump_sum' ? '' : '定投支持/起点（30天来源背书）',
      '限购金额（30天来源背书）',
      '销售服务费（30天来源背书）',
      '销售风险等级',
      '来源日期',
      ...executionAmountMissingItems,
    ].filter(Boolean)
  }
  return [
    rule.purchaseStatusSourceBacked ? '' : '申购状态（30天来源背书）',
    rule.purchaseFeeSourceBacked ? '' : '申购费率（30天来源背书）',
    hasSourceBackedRedemptionRules(rule) ? '' : '赎回费/持有期',
    rule.minPurchaseSourceBacked ? '' : '最低申购金额（30天来源背书）',
    purchasePlan !== 'lump_sum' && !(rule.supportsSipSourceBacked && (rule.supportsSip === false || rule.minSipSourceBacked)) ? '定投支持/起点（30天来源背书）' : '',
    rule.dailyLimitSourceBacked ? '' : '限购金额（30天来源背书）',
    rule.salesServiceFeeSourceBacked ? '' : '销售服务费（30天来源背书）',
    hasRiskSourceEvidence(rule) ? '' : '销售风险等级',
    rule.sourceUpdatedAt ? (isStaleSourceDate(rule.sourceUpdatedAt) ? '来源日期过旧' : '') : '来源日期',
    ...executionAmountMissingItems,
  ].filter(Boolean)
}

export function statusFromMissingItems(missingItems: string[], executionAmountGate: SalesRuleExecutionAmountGate) {
  if (missingItems.length > 0 || executionAmountGate.status === 'blocked') return 'blocked'
  if (executionAmountGate.status === 'unknown') return 'unknown'
  return 'ready'
}

export const salesRuleGateTool: ResearchTool<SalesRuleGateInput, SalesRuleGateOutput> = {
  manifest: {
    name: toolName,
    version,
    domain: 'evidence',
    purpose: '对单只基金销售规则、R1-R5、费用、申赎、限购和计划金额做研究硬门禁。',
    inputSchema: 'SalesRuleGateInput',
    outputSchema: 'SalesRuleGateOutput',
    evidencePolicy: 'strict_30d',
    canRunBatch: true,
    sideEffects: ['none'],
    guardrails: [
      FUND_RESEARCH_GUARDRAILS.missingEvidenceBlocks,
      FUND_RESEARCH_GUARDRAILS.tushareFoundationBoundary,
      'R1-R5、申赎、费率、起购、定投、限购必须有 30 天内来源背书。',
    ],
  },
  run(input) {
    const fundName = input.fundName || input.windCode
    const riskEvidence = riskLevelEvidence(input.rule)
    const executionAmountGate = buildExecutionAmountGate(input.rule, input)
    const missingItems = buildSalesRuleMissingItems(input)
    const status = statusFromMissingItems(missingItems, executionAmountGate)
    const actionHref = input.actionHref || materialEvidenceHref({ codes: input.windCode })
    const output: SalesRuleGateOutput = {
      windCode: input.windCode,
      fundName,
      status,
      label: status === 'ready' ? '销售规则相对完整' : status === 'unknown' ? '销售规则待扫描' : '销售规则硬缺口',
      missingItems,
      missingCount: missingItems.length,
      riskEvidence,
      executionAmountGate,
      nextAction: missingItems.length
        ? `补齐 ${missingItems.slice(0, 3).join('、')}`
        : status === 'unknown'
          ? executionAmountGate.actionLabel
          : '销售规则相对完整，研究复核确认实时状态',
      actionHref,
      hardBoundary: '销售规则、R1-R5、申赎、费用、起购、定投、限购和计划金额门禁未过前，只能作为补证观察。',
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
        id: `sales-rule-gate:${input.windCode}`,
        label: '销售规则门禁',
        source: input.rule?.sourceUrl || input.rule?.notes || input.rule?.platform || 'local.sales_rule',
        sourceUpdatedAt: input.rule?.sourceUpdatedAt || null,
        freshness: input.rule?.sourceUpdatedAt && !isStaleSourceDate(input.rule.sourceUpdatedAt) ? 'fresh_30d' : input.rule ? 'stale' : 'missing',
        subjectId: input.windCode,
        note: output.label,
      }],
      nextActions: [{
        key: 'sales-rule-gate',
        label: output.nextAction,
        href: output.actionHref,
        priority: status === 'blocked' ? 'high' : 'medium',
        reason: output.hardBoundary,
      }],
    })
  },
}
