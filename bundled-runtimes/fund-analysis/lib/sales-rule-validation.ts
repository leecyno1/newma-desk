import {
  hasValidSalesRuleSourceIdentityEvidence,
  isPlaceholderSalesRuleSourceText,
} from '@/lib/sales-rule-source-evidence'

export function isValidWindCode(value: unknown) {
  return typeof value === 'string' && /^[0-9A-Z]{6,12}\.(OF|SH|SZ|BJ)$/i.test(value.trim())
}

function numberOrNull(value: unknown) {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function boolOrNull(value: unknown) {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'boolean') return value
  if (value === 'true') return true
  if (value === 'false') return false
  return null
}

function hasInputValue(value: unknown) {
  return value !== null && value !== undefined && value !== ''
}

function fieldValue(rule: Record<string, unknown>, camelKey: string, snakeKey: string) {
  return rule[camelKey] ?? rule[snakeKey]
}

function validateNumberRange(
  errors: string[],
  rawValue: unknown,
  label: string,
  options: { min?: number; max?: number } = {},
) {
  if (!hasInputValue(rawValue)) return
  const parsed = numberOrNull(rawValue)
  if (parsed === null) {
    errors.push(`${label} 必须是数字`)
    return
  }
  if (options.min !== undefined && parsed < options.min) {
    errors.push(`${label} 不能小于 ${options.min}`)
  }
  if (options.max !== undefined && parsed > options.max) {
    errors.push(`${label} 不能大于 ${options.max}`)
  }
}

function isFutureDateText(value: string) {
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return true
  const today = new Date()
  today.setUTCHours(0, 0, 0, 0)
  return parsed.getTime() > today.getTime()
}

function isStaleDateText(value: string, maxAgeDays = 30) {
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return true
  const today = new Date()
  today.setUTCHours(0, 0, 0, 0)
  const ageDays = Math.floor((today.getTime() - parsed.getTime()) / 86_400_000)
  return ageDays > maxAgeDays
}

function hasValidRedemptionRule(value: unknown) {
  if (!Array.isArray(value)) return false
  return value.some((item) => {
    if (!item || typeof item !== 'object') return false
    const record = item as Record<string, unknown>
    return numberOrNull(record.feeRate ?? record.fee_rate) !== null
  })
}

function hasUsableSalesEvidence(rule: Record<string, unknown>) {
  return [
    rule.purchaseStatus && rule.purchaseStatus !== 'unknown',
    numberOrNull(rule.purchaseFeeRate ?? rule.purchase_fee_rate) !== null,
    numberOrNull(rule.minPurchaseAmount ?? rule.min_purchase_amount) !== null,
    numberOrNull(rule.minSipAmount ?? rule.min_sip_amount) !== null,
    numberOrNull(rule.dailyLimitAmount ?? rule.daily_limit_amount) !== null,
    numberOrNull(rule.salesServiceFeeRate ?? rule.sales_service_fee_rate) !== null,
    hasValidRedemptionRule(rule.redemptionFeeRules ?? rule.redemption_fee_rules),
    typeof rule.riskLevel === 'string' && /^R[1-5]$/i.test(rule.riskLevel.trim()),
    boolOrNull(rule.supportsSip ?? rule.supports_sip) !== null,
  ].some(Boolean)
}

export function validateSalesRule(rule: Record<string, unknown>) {
  const errors: string[] = []
  const hasSalesEvidence = hasUsableSalesEvidence(rule)
  const riskLevel = typeof rule.riskLevel === 'string' ? rule.riskLevel.trim() : ''
  const platform = typeof rule.platform === 'string' ? rule.platform.trim().toLowerCase() : ''
  const sourceUrl = typeof rule.sourceUrl === 'string'
    ? rule.sourceUrl.trim()
    : typeof rule.source_url === 'string'
      ? rule.source_url.trim()
      : ''
  const normalizedSourceUrl = sourceUrl.toLowerCase()
  const notes = typeof rule.notes === 'string' ? rule.notes.trim() : ''
  const sourceUpdatedAt = typeof rule.sourceUpdatedAt === 'string'
    ? rule.sourceUpdatedAt.trim()
    : typeof rule.source_updated_at === 'string'
      ? rule.source_updated_at.trim()
      : ''

  if (riskLevel && !/^R[1-5]$/i.test(riskLevel)) {
    errors.push('riskLevel 必须是 R1-R5，不能保存占位符')
  }
  if (riskLevel && (platform.includes('tushare') || normalizedSourceUrl.includes('tushare.fund_basic'))) {
    errors.push('riskLevel 必须来自销售平台、基金合同或招募说明书，不能用 Tushare fund_basic 作为风险等级来源')
  }
  if (riskLevel && !sourceUrl && !notes) {
    errors.push('riskLevel 必须填写来源链接或来源备注，说明销售平台/基金合同/招募说明书出处')
  }
  if ((sourceUrl && isPlaceholderSalesRuleSourceText(sourceUrl)) || (notes && isPlaceholderSalesRuleSourceText(notes))) {
    errors.push('来源链接或来源备注不能使用示例、待补、placeholder、demo、mock、test 等占位内容')
  }
  if (hasSalesEvidence && !hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })) {
    errors.push('来源背书必须指向真实销售平台、基金合同或招募说明书，不能使用占位来源')
  }
  if (!sourceUpdatedAt || !/^\d{4}-\d{2}-\d{2}$/u.test(sourceUpdatedAt)) {
    errors.push('sourceUpdatedAt 必须填写 YYYY-MM-DD 来源日期')
  } else if (isFutureDateText(sourceUpdatedAt)) {
    errors.push('sourceUpdatedAt 不能晚于今天')
  } else if (isStaleDateText(sourceUpdatedAt)) {
    errors.push('sourceUpdatedAt 必须是 30 天内销售平台、基金合同或招募说明书核验日期')
  }
  if (!hasSalesEvidence) {
    errors.push('至少填写一项真实申购状态、费率、起购/定投/限购、风险等级或定投支持证据')
  }
  validateNumberRange(errors, fieldValue(rule, 'purchaseFeeRate', 'purchase_fee_rate'), '申购费率', { min: 0, max: 100 })
  validateNumberRange(errors, fieldValue(rule, 'salesServiceFeeRate', 'sales_service_fee_rate'), '销售服务费率', { min: 0, max: 100 })
  validateNumberRange(errors, fieldValue(rule, 'minPurchaseAmount', 'min_purchase_amount'), '最低申购金额', { min: 0 })
  validateNumberRange(errors, fieldValue(rule, 'minSipAmount', 'min_sip_amount'), '定投起点', { min: 0 })
  validateNumberRange(errors, fieldValue(rule, 'dailyLimitAmount', 'daily_limit_amount'), '限购金额', { min: 0 })
  const redemptionRules = rule.redemptionFeeRules ?? rule.redemption_fee_rules
  if (Array.isArray(redemptionRules)) {
    redemptionRules.forEach((item, index) => {
      if (!item || typeof item !== 'object') return
      const record = item as Record<string, unknown>
      validateNumberRange(errors, record.feeRate ?? record.fee_rate, `第 ${index + 1} 条赎回费率`, { min: 0, max: 100 })
      validateNumberRange(errors, record.holdingDays ?? record.holding_days, `第 ${index + 1} 条赎回持有天数`, { min: 0 })
    })
  }

  return errors
}
