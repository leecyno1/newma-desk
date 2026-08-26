import { hasValidSalesRuleSourceIdentityEvidence } from '@/lib/sales-rule-source-evidence'

type EvidenceConfidence = 'high' | 'medium' | 'low'
type GapSeverity = 'high' | 'medium' | 'low'

type EvidenceItem = {
  label: string
  value: string
  source: string
  confidence: EvidenceConfidence
}

type MissingItem = {
  label: string
  severity: GapSeverity
  reason: string
  requiredBeforeBuy: boolean
}

type BuyEvidencePurchasePlan = 'lump_sum' | 'sip'

type BuyEvidenceOptions = {
  purchasePlan?: BuyEvidencePurchasePlan | null
  plannedAmount?: number | string | null
}

type BuyEvidenceExecutionAmountGate = {
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

const RISK_LEVEL_SOURCE_MAX_AGE_DAYS = 30
const DEFAULT_PLANNED_AMOUNTS: Record<BuyEvidencePurchasePlan, number> = {
  lump_sum: 10000,
  sip: 1000,
}

function normalizePurchasePlan(value: BuyEvidenceOptions['purchasePlan']): BuyEvidencePurchasePlan {
  return value === 'lump_sum' ? 'lump_sum' : 'sip'
}

function asNumber(value: unknown) {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function normalizePlannedAmount(value: BuyEvidenceOptions['plannedAmount'], purchasePlan: BuyEvidencePurchasePlan) {
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? Math.round(amount) : DEFAULT_PLANNED_AMOUNTS[purchasePlan]
}

function getField(source: Record<string, any> | null | undefined, snakeKey: string, camelKey: string = snakeKey) {
  return source?.[snakeKey] ?? source?.[camelKey] ?? null
}

function feeText(value: unknown) {
  const parsed = asNumber(value)
  return parsed === null ? null : `${parsed.toFixed(2)}%`
}

function moneyText(value: unknown) {
  const parsed = asNumber(value)
  return parsed === null ? null : `${parsed.toFixed(2)} 元`
}

function boolText(value: unknown) {
  if (value === true) return '支持'
  if (value === false) return '不支持'
  return null
}

function buildExecutionAmountGate(
  salesRule: Record<string, any> | null | undefined,
  purchasePlan: BuyEvidencePurchasePlan,
  plannedAmount: number | null,
  minPurchaseAmount: number | null,
  minSipAmount: number | null,
  dailyLimitAmount: number | null,
  supportsSip: unknown,
): BuyEvidenceExecutionAmountGate {
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
  if (!salesRule) {
    return {
      plannedAmount,
      status: 'unknown',
      label: '金额门槛待补',
      detail: '本地未取得销售规则，不能判断计划金额是否满足起购、定投起点或限购。',
      advice: '先补销售平台起购、定投起点和限购金额；未补前不能把该基金作为可执行研究样本。',
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
      detail: '当前研究方式假设为定投，但销售规则显示不支持定投。',
      advice: '切换为一次性配置假设并重新评估，或换一只明确支持定投且适合当前画像的份额。',
      actionLabel: '换研究方式假设或份额',
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
        ? '先补销售平台定投起点；未确认前不能把月扣款金额视为可执行。'
        : '先补销售平台起购金额；未确认前不能把一次性计划金额视为可执行。',
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
      ? `计划月扣款 ${plannedAmount.toLocaleString('zh-CN')} 元满足当前定投起点与限购约束；研究复核仍需复核销售平台实时状态。`
      : `计划金额 ${plannedAmount.toLocaleString('zh-CN')} 元满足当前起购与限购约束；研究复核仍需复核销售平台实时状态。`,
    advice: '金额门槛当前通过；下一步继续核 R1-R5 适当性、申购状态、费用和赎回规则。',
    actionLabel: '继续研究复核',
    shortfallAmount: null,
    suggestedAmount: plannedAmount,
    minPurchaseAmount,
    minSipAmount,
    dailyLimitAmount,
  }
}

function firstSalesRule(fund: Record<string, any>) {
  if (fund.sales_rule || fund.salesRule) return fund.sales_rule ?? fund.salesRule
  const salesRules = fund.sales_rules ?? fund.salesRules
  if (Array.isArray(salesRules) && salesRules.length > 0) return salesRules[0]
  return null
}

function isFreshSourceDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}/u.test(value)) return false
  const sourceDate = new Date(`${value.slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(sourceDate.getTime())) return false
  const currentDate = new Date()
  currentDate.setUTCHours(0, 0, 0, 0)
  const ageDays = Math.floor((currentDate.getTime() - sourceDate.getTime()) / 86_400_000)
  return ageDays >= 0 && ageDays <= RISK_LEVEL_SOURCE_MAX_AGE_DAYS
}

function hasSourceBackedRiskLevel(rule: Record<string, any> | null | undefined) {
  const riskLevel = String(getField(rule, 'risk_level', 'riskLevel') || '').trim()
  if (!/^R[1-5]$/i.test(riskLevel)) return false
  const sourceUpdatedAt = String(getField(rule, 'source_updated_at', 'sourceUpdatedAt') || '').trim()
  if (!isFreshSourceDate(sourceUpdatedAt)) return false
  const platform = String(getField(rule, 'platform', 'platform') || '').trim()
  const sourceUrl = String(getField(rule, 'source_url', 'sourceUrl') || '').trim()
  const notes = String(rule?.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function hasSourceBackedRedemptionRules(rule: Record<string, any> | null | undefined, redemptionRules: unknown[]) {
  if (!redemptionRules.length) return false
  const sourceUpdatedAt = String(
    getField(rule, 'redemption_fee_source_updated_at', 'redemptionFeeSourceUpdatedAt')
    || getField(rule, 'source_updated_at', 'sourceUpdatedAt')
    || '',
  ).trim()
  if (!isFreshSourceDate(sourceUpdatedAt)) return false
  const platform = String(
    getField(rule, 'redemption_fee_platform', 'redemptionFeePlatform')
    || getField(rule, 'platform', 'platform')
    || '',
  ).trim()
  const sourceUrl = String(
    getField(rule, 'redemption_fee_source_url', 'redemptionFeeSourceUrl')
    || getField(rule, 'source_url', 'sourceUrl')
    || '',
  ).trim()
  const notes = String(
    getField(rule, 'redemption_fee_notes', 'redemptionFeeNotes')
    || rule?.notes
    || '',
  ).trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function hasSourceBackedSalesRule(rule: Record<string, any> | null | undefined) {
  const sourceUpdatedAt = String(getField(rule, 'source_updated_at', 'sourceUpdatedAt') || '').trim()
  if (!isFreshSourceDate(sourceUpdatedAt)) return false
  const platform = String(getField(rule, 'platform', 'platform') || '').trim()
  const sourceUrl = String(getField(rule, 'source_url', 'sourceUrl') || '').trim()
  const notes = String(rule?.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function hasSourceBackedSalesRuleField(
  rule: Record<string, any> | null | undefined,
  snakeFlag: string,
  camelFlag: string,
  value: unknown,
) {
  if (value === null || value === undefined || value === '') return false
  const explicitFlag = getField(rule, snakeFlag, camelFlag)
  if (explicitFlag === true) return true
  if (explicitFlag === false) return false
  return hasSourceBackedSalesRule(rule)
}

export function buildResearchEvidence(fund: Record<string, any>, options: BuyEvidenceOptions = {}) {
  const purchasePlan = normalizePurchasePlan(options.purchasePlan)
  const plannedAmount = normalizePlannedAmount(options.plannedAmount, purchasePlan)
  const operationStatus = fund.operation_status ?? fund.operationStatus ?? null
  const salesStatus = fund.sales_status ?? fund.salesStatus ?? null
  const feeInfo = fund.fee_info ?? fund.feeInfo ?? null
  const salesRule = firstSalesRule(fund)
  const benchmark = fund.benchmark ?? null
  const totalAsset = asNumber(fund.total_asset ?? fund.totalAsset)
  const navDate = fund.nav_date ?? fund.navDate ?? null
  const managementFee = getField(feeInfo, 'management_fee', 'managementFee')
  const custodianFee = getField(feeInfo, 'custodian_fee', 'custodianFee')
  const purchaseFeeRate = getField(salesRule, 'purchase_fee_rate', 'purchaseFeeRate')
  const redemptionFeeRules = getField(salesRule, 'redemption_fee_rules', 'redemptionFeeRules')
  const minPurchaseAmount = asNumber(getField(salesRule, 'min_purchase_amount', 'minPurchaseAmount'))
  const minSipAmount = asNumber(getField(salesRule, 'min_sip_amount', 'minSipAmount'))
  const dailyLimitAmount = asNumber(getField(salesRule, 'daily_limit_amount', 'dailyLimitAmount'))
  const salesServiceFeeRate = getField(salesRule, 'sales_service_fee_rate', 'salesServiceFeeRate')
  const riskLevel = getField(salesRule, 'risk_level', 'riskLevel')
  const hasVerifiedRiskLevel = hasSourceBackedRiskLevel(salesRule)
  const supportsSip = getField(salesRule, 'supports_sip', 'supportsSip')
  const purchaseFeeSourceBacked = hasSourceBackedSalesRuleField(salesRule, 'purchase_fee_source_backed', 'purchaseFeeSourceBacked', purchaseFeeRate)
  const minPurchaseSourceBacked = hasSourceBackedSalesRuleField(salesRule, 'min_purchase_source_backed', 'minPurchaseSourceBacked', minPurchaseAmount)
  const minSipSourceBacked = hasSourceBackedSalesRuleField(salesRule, 'min_sip_source_backed', 'minSipSourceBacked', minSipAmount)
  const dailyLimitSourceBacked = hasSourceBackedSalesRuleField(salesRule, 'daily_limit_source_backed', 'dailyLimitSourceBacked', dailyLimitAmount)
  const supportsSipSourceBacked = hasSourceBackedSalesRuleField(salesRule, 'supports_sip_source_backed', 'supportsSipSourceBacked', supportsSip)
  const salesServiceFeeSourceBacked = hasSourceBackedSalesRuleField(salesRule, 'sales_service_fee_source_backed', 'salesServiceFeeSourceBacked', salesServiceFeeRate)
  const salesRuleSource = salesRule?.platform ? `销售规则表（${salesRule.platform}）` : '销售规则表'
  const purchaseStartDate = getField(salesStatus, 'purchase_start_date', 'purchaseStartDate')
    ?? getField(operationStatus, 'purchase_start_date', 'purchaseStartDate')
  const redeemStartDate = getField(salesStatus, 'redeem_start_date', 'redeemStartDate')
    ?? getField(operationStatus, 'redeem_start_date', 'redeemStartDate')
  const executionAmountGate = buildExecutionAmountGate(
    salesRule,
    purchasePlan,
    plannedAmount,
    minPurchaseSourceBacked ? minPurchaseAmount : null,
    minSipSourceBacked ? minSipAmount : null,
    dailyLimitSourceBacked ? dailyLimitAmount : null,
    supportsSipSourceBacked ? supportsSip : null,
  )

  const knownItems: EvidenceItem[] = []
  const missingItems: MissingItem[] = []

  if (operationStatus?.label) {
    knownItems.push({
      label: '申购/存续状态',
      value: operationStatus.label,
      source: 'Tushare fund_basic',
      confidence: operationStatus.status === 'blocked' ? 'high' : 'medium',
    })
  } else {
    missingItems.push({
      label: '实时申购状态',
      severity: 'high',
      reason: '当前未取得销售平台实时申购/暂停申购状态。',
      requiredBeforeBuy: true,
    })
  }

  if (purchaseStartDate) {
    knownItems.push({
      label: '申购起始日',
      value: String(purchaseStartDate),
      source: 'Tushare fund_basic',
      confidence: 'medium',
    })
  }

  if (redeemStartDate) {
    knownItems.push({
      label: '赎回起始日',
      value: String(redeemStartDate),
      source: 'Tushare fund_basic',
      confidence: 'medium',
    })
  }

  const managementFeeText = feeText(managementFee)
  if (managementFeeText) {
    knownItems.push({
      label: '管理费',
      value: managementFeeText,
      source: 'Tushare fund_basic',
      confidence: 'medium',
    })
  }

  const custodianFeeText = feeText(custodianFee)
  if (custodianFeeText) {
    knownItems.push({
      label: '托管费',
      value: custodianFeeText,
      source: 'Tushare fund_basic',
      confidence: 'medium',
    })
  }

  const purchaseFeeText = feeText(purchaseFeeRate)
  if (purchaseFeeText && purchaseFeeSourceBacked) {
    knownItems.push({
      label: '申购费率',
      value: purchaseFeeText,
      source: salesRuleSource,
      confidence: 'medium',
    })
  }

  const redemptionRules = Array.isArray(redemptionFeeRules) ? redemptionFeeRules : []
  const hasVerifiedRedemptionRules = hasSourceBackedRedemptionRules(salesRule, redemptionRules)
  if (hasVerifiedRedemptionRules) {
    knownItems.push({
      label: '赎回费率/持有期规则',
      value: redemptionRules.map((rule: any) => rule.label || `${rule.holdingDays ?? '-'}天 ${feeText(rule.feeRate)}`).join('；'),
      source: salesRuleSource,
      confidence: 'medium',
    })
  }

  const minPurchaseText = moneyText(minPurchaseAmount)
  if (minPurchaseText && minPurchaseSourceBacked) {
    knownItems.push({
      label: '最低申购金额',
      value: minPurchaseText,
      source: salesRuleSource,
      confidence: 'medium',
    })
  }

  const limitText = moneyText(dailyLimitAmount)
  if (limitText && dailyLimitSourceBacked) {
    knownItems.push({
      label: '单日/单账户限购',
      value: limitText,
      source: salesRuleSource,
      confidence: 'medium',
    })
  }

  const minSipText = purchasePlan === 'sip' ? moneyText(minSipAmount) : null
  if (minSipText && minSipSourceBacked) {
    knownItems.push({
      label: '定投起点',
      value: minSipText,
      source: salesRuleSource,
      confidence: 'medium',
    })
  }

  const supportsSipText = purchasePlan === 'sip' ? boolText(supportsSip) : null
  if (supportsSipText && supportsSipSourceBacked) {
    knownItems.push({
      label: '定投支持状态',
      value: supportsSipText,
      source: salesRuleSource,
      confidence: 'medium',
    })
  }

  const salesServiceFeeText = feeText(salesServiceFeeRate)
  if (salesServiceFeeText && salesServiceFeeSourceBacked) {
    knownItems.push({
      label: '销售服务费',
      value: salesServiceFeeText,
      source: salesRuleSource,
      confidence: 'medium',
    })
  }

  if (hasVerifiedRiskLevel) {
    knownItems.push({
      label: '销售平台风险等级',
      value: String(riskLevel),
      source: salesRuleSource,
      confidence: 'medium',
    })
  }

  if (executionAmountGate.status === 'pass') {
    knownItems.push({
      label: '计划金额执行门禁',
      value: executionAmountGate.label,
      source: salesRuleSource,
      confidence: 'medium',
    })
  }

  if (benchmark) {
    knownItems.push({
      label: '业绩比较基准',
      value: String(benchmark),
      source: 'Tushare fund_basic',
      confidence: 'medium',
    })
  }

  if (totalAsset !== null && totalAsset > 0) {
    knownItems.push({
      label: '基金规模',
      value: `${totalAsset.toFixed(2)} 亿`,
      source: '本地基金基础表',
      confidence: 'medium',
    })
  } else {
    missingItems.push({
      label: '基金规模',
      severity: 'medium',
      reason: '缺少规模将影响容量、清盘风险和流动性判断。',
      requiredBeforeBuy: false,
    })
  }

  if (navDate) {
    knownItems.push({
      label: '净值日期',
      value: String(navDate),
      source: '本地基金基础表',
      confidence: 'medium',
    })
  }

  const salesSideGaps: MissingItem[] = []
  if (!purchaseFeeSourceBacked) {
    salesSideGaps.push({
      label: '申购费率',
      severity: 'high',
      reason: purchaseFeeText
        ? '已录入申购费率，但缺少 30 天内销售平台/基金合同来源背书，不能用于正式研究复核成本估算。'
        : 'Tushare fund_basic 不提供销售平台前端申购费或折扣费率。',
      requiredBeforeBuy: true,
    })
  }
  if (!hasVerifiedRedemptionRules) {
    salesSideGaps.push({
      label: '赎回费率',
      severity: 'high',
      reason: redemptionRules.length
        ? '已录入赎回费分档，但缺少 30 天内销售平台/基金合同来源背书，不能用于正式研究复核回放。'
        : '赎回费通常和持有期相关，必须在销售平台或基金合同中复核。',
      requiredBeforeBuy: true,
    })
  }
  if (!minPurchaseSourceBacked) {
    salesSideGaps.push({
      label: '最低申购金额',
      severity: 'medium',
      reason: minPurchaseText
        ? '已录入最低申购金额，但缺少 30 天内销售平台/基金合同来源背书，不能用于正式金额门禁。'
        : '不同销售平台起购金额可能不同，当前未接入。',
      requiredBeforeBuy: true,
    })
  }
  if (!dailyLimitSourceBacked) {
    salesSideGaps.push({
      label: '单日/单账户限购',
      severity: 'high',
      reason: limitText
        ? '已录入限购金额，但缺少 30 天内销售平台/基金合同来源背书，不能用于正式金额门禁。'
        : '限购会直接影响计划金额是否可执行，当前未接入销售平台状态。',
      requiredBeforeBuy: true,
    })
  }
  if (purchasePlan === 'sip' && !supportsSipSourceBacked) {
    salesSideGaps.push({
      label: '定投支持状态',
      severity: 'medium',
      reason: supportsSipText
        ? '已录入定投支持状态，但缺少 30 天内销售平台/基金合同来源背书，不能用于正式定投门禁。'
        : '是否支持定投和定投起点需按销售平台确认。',
      requiredBeforeBuy: true,
    })
  }
  if (purchasePlan === 'sip' && supportsSipSourceBacked && supportsSip === true && !minSipSourceBacked) {
    salesSideGaps.push({
      label: '定投起点',
      severity: 'medium',
      reason: minSipText
        ? '已录入定投起点，但缺少 30 天内销售平台/基金合同来源背书，不能用于正式定投门禁。'
        : '销售平台显示支持定投，但当前缺少定投起扣金额。',
      requiredBeforeBuy: true,
    })
  }
  if (!salesServiceFeeSourceBacked) {
    salesSideGaps.push({
      label: '销售服务费',
      severity: 'high',
      reason: salesServiceFeeText
        ? '已录入销售服务费，但缺少 30 天内销售平台/基金合同来源背书，不能用于正式持有成本估算。'
        : '销售服务费不能默认按 0 处理；A/C 类份额与短持成本必须取得 30 天内销售平台/基金合同来源背书。',
      requiredBeforeBuy: true,
    })
  }
  if (!hasVerifiedRiskLevel) {
    salesSideGaps.push({
      label: '销售平台风险等级',
      severity: 'high',
      reason: riskLevel
        ? '已填写风险等级但缺少 30 天内销售平台/基金合同来源证据，不能用于适当性匹配。'
        : '适当性匹配依赖销售平台风险等级、来源日期和研究画像。',
      requiredBeforeBuy: true,
    })
  }
  if (executionAmountGate.status === 'blocked') {
    salesSideGaps.push({
      label: '计划金额执行门禁',
      severity: 'high',
      reason: executionAmountGate.detail,
      requiredBeforeBuy: true,
    })
  }
  if (executionAmountGate.status === 'unknown' && plannedAmount === null) {
    salesSideGaps.push({
      label: '计划金额',
      severity: 'high',
      reason: executionAmountGate.detail,
      requiredBeforeBuy: true,
    })
  }
  missingItems.push(...salesSideGaps)

  const requiredMissingCount = missingItems.filter((item) => item.requiredBeforeBuy).length
  const knownScore = Math.min(60, knownItems.length * 8)
  const gapPenalty = requiredMissingCount * 8 + missingItems.filter((item) => item.severity === 'medium').length * 3
  const completenessScore = Math.max(0, Math.min(100, knownScore - gapPenalty + 50))
  const completenessLevel: 'strong' | 'partial' | 'thin' =
    completenessScore >= 75
      ? 'strong'
      : completenessScore >= 45
        ? 'partial'
        : 'thin'

  return {
    source: 'tushare_plus_sales_platform_checklist',
    purchasePlan,
    plannedAmount,
    executionAmountGate,
    completenessScore,
    completenessLevel,
    knownItems,
    missingItems,
    requiredMissingCount,
    mustVerifyBeforeBuy: [
      purchasePlan === 'sip'
        ? '销售平台实时申购/定投状态、暂停申购和限购金额'
        : '销售平台实时申购状态、暂停申购和限购金额',
      '申购费、赎回费、销售服务费与持有期规则',
      purchasePlan === 'sip'
        ? '最低申购金额、追加申购金额和定投起点'
        : '最低申购金额、追加申购金额和单笔限购',
      '基金合同、最新季报、风险等级与本人适当性匹配',
    ],
    conclusion:
      executionAmountGate.status === 'blocked'
        ? `计划金额不可执行：${executionAmountGate.detail}`
        : requiredMissingCount > 0
        ? '基础研究证据可用，但申赎执行证据不足；研究复核必须到销售平台复核。'
        : '研究复核关键申赎证据相对完整，仍需确认销售平台实时状态。',
  }
}
