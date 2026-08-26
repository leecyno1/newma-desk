export type SalesRulePurchasePlan = 'lump_sum' | 'sip'

export function normalizeSalesRulePurchasePlan(value: unknown, fallback: SalesRulePurchasePlan = 'sip'): SalesRulePurchasePlan {
  return value === 'lump_sum' || value === 'sip' ? value : fallback
}

export function salesRuleFoundationManualFieldsForPlan(purchasePlan: SalesRulePurchasePlan) {
  return purchasePlan === 'sip'
    ? '申购费、赎回费、定投、限购和风险等级'
    : '申购费、赎回费、起购金额、限购和风险等级'
}

export function salesRuleFoundationSourceNoteForPlan(purchasePlan: SalesRulePurchasePlan) {
  return `该来源不提供销售平台${salesRuleFoundationManualFieldsForPlan(purchasePlan)}；正式研究结论前仍需人工核验。`
}

export function salesRuleFoundationDisclaimerForPlan(purchasePlan: SalesRulePurchasePlan) {
  return `该接口只补 Tushare 基础申赎状态证据，不补${salesRuleFoundationManualFieldsForPlan(purchasePlan)}。`
}

export function salesRuleEvidenceCopyForPlan(purchasePlan: SalesRulePurchasePlan) {
  if (purchasePlan === 'lump_sum') {
    return {
      fields: '申购、赎回、起购金额、限购、风险等级和来源日期',
      hardGapDetail: '申购状态、申购费、赎回费、起购金额、限购、风险等级或来源日期未补齐，严格模式不会放行。',
      cleanDetail: '申购、赎回、起购金额、限购和来源字段未见硬缺口',
      executionCleanDetail: '申购状态、起购金额和限购未见首要执行缺口',
      executionGoal: '核申购开放、起购金额和限购金额。',
      executionAction: '核申购开放、起购金额、限购和费用。',
      executionChecklistAction: '确认实时申购、起购金额和限购',
      costFilterFields: '申购费、赎回费、销售服务费、起购金额和限购',
    }
  }
  return {
    fields: '申购、赎回、定投、限购、风险等级和来源日期',
    hardGapDetail: '申购状态、申购费、赎回费、定投支持/起点、限购、风险等级或来源日期未补齐，严格模式不会放行。',
    cleanDetail: '申购、赎回、定投、限购和来源字段未见硬缺口',
    executionCleanDetail: '申购状态、起购、定投和限购未见首要执行缺口',
    executionGoal: '核申购开放、起购、定投支持和限购金额。',
    executionAction: '核申购开放、定投支持、起购金额、限购和费用。',
    executionChecklistAction: '确认实时申购、定投、起购和限购',
    costFilterFields: '申购费、赎回费、销售服务费、定投起点和限购',
  }
}
