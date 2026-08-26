import { NextResponse } from 'next/server'
import postgres from 'postgres'
import { backendApiBaseUrl, toCamelFund } from '@/lib/backend-api'
import { buildResearchEvidence } from '@/lib/research-evidence'
import { getSalesRuleGapsForCodes } from '@/lib/sales-rule-gaps'
import { getMergedSalesRule, getMergedSalesRulesByWindCodes } from '@/lib/sales-rules'
import { hasValidSalesRuleSourceIdentityEvidence } from '@/lib/sales-rule-source-evidence'
import { fetchActiveSalesRuleEvidenceAlertsForCodes, type ActiveSalesRuleEvidenceAlert } from '@/lib/sales-rule-review-alerts'
import { buildShareClassInfoByCode, inferShareClass, normalizeShareClassBaseName } from '@/lib/share-class'
import type { AlternativeCandidate, AlternativeEvidence } from '@/lib/research-review-report'
import {
  buildResearchReviewReport,
  buildPurchaseSimulationFromNav,
  normalizeInvestorContext,
  normalizeNavRows,
} from '@/lib/research-review-report'
import { materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'

const sql = postgres(process.env.DATABASE_URL || '', { max: 1 })

function asPositiveNumber(value: string | null, fallback: number, min: number, max: number) {
  if (value === null || value.trim() === '') return fallback
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return fallback
  return Math.max(min, Math.min(max, parsed))
}

function dateMonthsAgo(months: number) {
  const date = new Date()
  date.setMonth(date.getMonth() - months)
  return date.toISOString().slice(0, 10)
}

function reportFilename(fund: { windCode?: string; name?: string }) {
  const rawName = `${fund.windCode || 'fund'}_${fund.name || '基金'}_研究复核报告.md`
  return rawName.replace(/[\\/:*?"<>|]/g, '_')
}

function isFreshSalesRuleSourceDate(value: string | null | undefined) {
  if (!value) return false
  const sourceDate = new Date(`${String(value).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(sourceDate.getTime())) return false
  const currentDate = new Date()
  currentDate.setUTCHours(0, 0, 0, 0)
  const ageDays = Math.floor((currentDate.getTime() - sourceDate.getTime()) / 86_400_000)
  return ageDays >= 0 && ageDays <= 30
}

function hasSourceBackedRedemptionRules(rule: {
  redemptionFeeRules?: unknown[]
  redemptionFeeSourceUpdatedAt?: string | null
  redemptionFeeSourceUrl?: string | null
  redemptionFeePlatform?: string | null
  redemptionFeeNotes?: string | null
  sourceUpdatedAt?: string | null
  sourceUrl?: string | null
  platform?: string | null
  notes?: string | null
} | null | undefined) {
  if (!rule?.redemptionFeeRules?.length) return false
  const sourceUpdatedAt = rule.redemptionFeeSourceUpdatedAt || rule.sourceUpdatedAt
  if (!isFreshSalesRuleSourceDate(sourceUpdatedAt)) return false
  const platform = String(rule.redemptionFeePlatform || rule.platform || '').trim()
  const sourceUrl = String(rule.redemptionFeeSourceUrl || rule.sourceUrl || '').trim()
  const notes = String(rule.redemptionFeeNotes || rule.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function hasSourceBackedSalesRuleField(rule: {
  sourceUpdatedAt?: string | null
  sourceUrl?: string | null
  platform?: string | null
  notes?: string | null
  [key: string]: unknown
} | null | undefined, sourceFlag: string, value: unknown) {
  if (value === null || value === undefined || value === '') return false
  const explicitFlag = rule?.[sourceFlag]
  if (explicitFlag === true) return true
  if (explicitFlag === false) return false
  if (!isFreshSalesRuleSourceDate(rule?.sourceUpdatedAt)) return false
  const platform = String(rule?.platform || '').trim()
  const sourceUrl = String(rule?.sourceUrl || '').trim()
  const notes = String(rule?.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function reviewAlertMissingItems(alerts: ActiveSalesRuleEvidenceAlert[] | undefined) {
  return (alerts || []).map((alert) => (
    `复查队列未解决：${alert.title || '销售规则/R1-R5证据待补'}${alert.message ? `（${alert.message}）` : ''}`
  ))
}

async function fetchPurchaseSimulation(
  windCode: string,
  months: number,
  lumpSumAmount: number,
  monthlyAmount: number,
) {
  const backendUrl = new URL(`/api/funds/${encodeURIComponent(windCode)}/nav`, backendApiBaseUrl)
  backendUrl.searchParams.set('start_date', dateMonthsAgo(months))
  backendUrl.searchParams.set('end_date', new Date().toISOString().slice(0, 10))
  const response = await fetch(backendUrl, { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    return {
      simulation: null,
      error: payload.detail || payload.error || '真实净值序列读取失败',
    }
  }

  const rows = normalizeNavRows(payload.data || [])
  const simulation = buildPurchaseSimulationFromNav(rows, months, lumpSumAmount, monthlyAmount)
  return {
    simulation,
    error: simulation ? null : '净值样本不足，无法进行历史净值回放',
  }
}

async function fetchHoldingEvidence(request: Request, windCode: string) {
  const requestUrl = new URL(request.url)
  const holdingsUrl = new URL(`/api/funds/${encodeURIComponent(windCode)}/holdings`, requestUrl.origin)
  const response = await fetch(holdingsUrl, { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    return {
      status: 'unavailable',
      windCode,
      holdings: [],
      industryBuckets: [],
      totalWeight: null,
      checkedQuarters: [],
      rejectedMockLikeQuarters: [],
      source: 'backend.tushare.fund_portfolio.filtered',
      note: payload.detail || payload.error || '可信持仓读取失败，暂不做行业/个股暴露判断。',
    }
  }
  return payload
}

async function fetchAlternativeEvidence(
  request: Request,
  fund: { windCode?: string; type?: string },
  investorContext: ReturnType<typeof normalizeInvestorContext>,
  plannedAmount: number,
): Promise<AlternativeEvidence> {
  if (!fund.windCode) {
    return {
      status: 'unavailable',
      note: '基金代码缺失，无法拉取同画像替代候选。',
      attempts: [],
      total: 0,
      source: 'api.investor_selection',
      funds: [],
    }
  }

  const requestUrl = new URL(request.url)
  const attempts = [
    {
      label: fund.type ? `同类型 ${fund.type} · 研究候选 · 证据B+` : '同类型待补 · 研究候选 · 证据B+',
      type: fund.type || '',
      eligibleOnly: 'true',
      minEvidenceGrade: 'B',
      limit: '16',
    },
    {
      label: fund.type ? `同类型 ${fund.type} · 放宽证据到C` : '同类型待补 · 放宽证据到C',
      type: fund.type || '',
      eligibleOnly: 'false',
      minEvidenceGrade: 'C',
      limit: '24',
    },
    {
      label: '全类型 · 研究候选 · 证据B+',
      type: '',
      eligibleOnly: 'true',
      minEvidenceGrade: 'B',
      limit: '24',
    },
  ]
  const attemptedLabels: string[] = []

  for (const attempt of attempts) {
    attemptedLabels.push(attempt.label)
    const alternativesUrl = new URL('/api/market/research-candidates', requestUrl.origin)
    alternativesUrl.searchParams.set('profile', investorContext.profile)
    alternativesUrl.searchParams.set('horizon', investorContext.horizon)
    alternativesUrl.searchParams.set('purchasePlan', investorContext.purchasePlan)
    alternativesUrl.searchParams.set('plannedAmount', String(plannedAmount))
    alternativesUrl.searchParams.set(investorContext.purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(plannedAmount))
    alternativesUrl.searchParams.set('lens', 'score')
    alternativesUrl.searchParams.set('eligibleOnly', attempt.eligibleOnly)
    alternativesUrl.searchParams.set('minEvidenceGrade', attempt.minEvidenceGrade)
    alternativesUrl.searchParams.set('limit', attempt.limit)
    if (attempt.type) alternativesUrl.searchParams.set('type', attempt.type)

    const response = await fetch(alternativesUrl, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) continue

    const alternatives = ((payload.funds || []) as AlternativeCandidate[])
      .filter((item) => item.windCode !== fund.windCode)
      .filter((item) => item.purchaseGate?.level !== 'blocked')
      .slice(0, 4)

    if (alternatives.length > 0) {
      const gapPayload = await getSalesRuleGapsForCodes(
        alternatives.map((item) => item.windCode || '').filter(Boolean),
        alternatives.length,
        { purchasePlan: investorContext.purchasePlan, plannedAmount },
      )
      const gapMap = new Map((gapPayload.gaps || []).map((gap) => [gap.windCode.toUpperCase(), gap]))
      const ruleMap = new Map((gapPayload.rules || []).map((rule) => [rule.windCode.toUpperCase(), rule]))
      const activeSalesRuleEvidenceAlertsByCode = await fetchActiveSalesRuleEvidenceAlertsForCodes(
        alternatives.map((item) => item.windCode || '').filter(Boolean),
      )
      const annotatedAlternatives = alternatives.map((item) => {
        const gap = item.windCode ? gapMap.get(item.windCode.toUpperCase()) : null
        const rule = item.windCode ? ruleMap.get(item.windCode.toUpperCase()) : null
        const alertMissingItems = item.windCode
          ? reviewAlertMissingItems(activeSalesRuleEvidenceAlertsByCode.get(item.windCode.toUpperCase()))
          : []
        const missingItems = Array.from(new Set([
          ...(gap?.missingItems || []),
          ...alertMissingItems,
          ...(!gap && rule?.executionAmountGate?.status === 'blocked' ? [rule.executionAmountGate.label || '计划金额门槛'] : []),
        ]))
        const amountBlocked = rule?.executionAmountGate?.status === 'blocked'
        const hasHardGap = Boolean(gap?.missingCount || missingItems.length || amountBlocked)
        return {
          ...item,
          salesRuleGap: hasHardGap
            ? {
                missingCount: Math.max(gap?.missingCount || 0, missingItems.length),
                missingItems,
                priority: gap?.priority || 'high',
                nextAction: alertMissingItems.length
                  ? '先打开复查队列，处理销售规则/R1-R5过期或待补事件'
                  : gap?.nextAction || rule?.executionAmountGate?.detail || '调整计划金额或补齐销售平台金额规则',
              }
            : null,
        }
      })
      const readyAlternatives = annotatedAlternatives.filter((item) => !item.salesRuleGap?.missingCount)
      const blockedCount = annotatedAlternatives.length - readyAlternatives.length
      if (!readyAlternatives.length) {
        return {
          status: 'unavailable',
          note: `采用：${attempt.label}；找到 ${annotatedAlternatives.length} 只同画像候选，但全部存在销售规则硬缺口，补齐前不作为可比替代结论。`,
          attempts: attemptedLabels,
          total: Number(payload.total || 0),
          source: `${payload.source || 'api.investor_selection'} + local.sales_rule_gaps+local.alert_events.sales_rule_evidence`,
          funds: annotatedAlternatives,
        }
      }
      return {
        status: 'available',
        note: `采用：${attempt.label}；返回 ${readyAlternatives.length} 只销售规则已过硬缺口扫描的可比替代${blockedCount ? `，另有 ${blockedCount} 只待补规则` : ''}。`,
        attempts: attemptedLabels,
        total: Number(payload.total || 0),
        source: `${payload.source || 'api.investor_selection'} + local.sales_rule_gaps+local.alert_events.sales_rule_evidence`,
        funds: [...readyAlternatives, ...annotatedAlternatives.filter((item) => item.salesRuleGap?.missingCount)].slice(0, 4),
      }
    }
  }

  return {
    status: 'unavailable',
    note: '当前画像下未找到可比较替代候选；建议回到选基页放宽画像、证据等级或基金类型。',
    attempts: attemptedLabels,
    total: 0,
    source: 'api.investor_selection',
    funds: [],
  }
}

async function fetchShareClassEvidence(
  fund: { windCode?: string; name?: string; type?: string },
  investorContext: ReturnType<typeof normalizeInvestorContext>,
  plannedAmount: number,
) {
  const baseName = normalizeShareClassBaseName(fund.name)
  const classType = inferShareClass(fund.name)
  if (!fund.windCode || !baseName || !classType) {
    return {
      status: 'unavailable' as const,
      source: 'api.funds.keyword_share_class',
      note: '基金名称未识别出 A/C/I/H 等份额类别，研究复核仍需核对是否存在其他份额。',
      current: null,
      funds: [],
    }
  }

  try {
    const params = new URLSearchParams({
      page: '1',
      page_size: '50',
      keyword: baseName,
      sort_by: 'name',
      sort_order: 'asc',
      purchase_plan: investorContext.purchasePlan,
    })
    const response = await fetch(`${backendApiBaseUrl}/api/funds?${params.toString()}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      return {
        status: 'unavailable' as const,
        source: 'api.funds.keyword_share_class',
        note: payload.detail || payload.error || '同基金份额检索失败。',
        current: null,
        funds: [],
      }
    }

    const siblings = (payload.funds || [])
      .map(toCamelFund)
      .filter((item: { name?: string; type?: string }) => normalizeShareClassBaseName(item.name) === baseName)
      .filter((item: { type?: string }) => !fund.type || !item.type || item.type === fund.type)
    const funds = siblings.length
      ? siblings
      : [{ windCode: fund.windCode, name: fund.name, type: fund.type }]
    const shareClassCodes: string[] = Array.from(new Set(
      funds
        .map((item: { windCode?: string }) => String(item.windCode || '').trim().toUpperCase())
        .filter((code: string): code is string => Boolean(code)),
    ))
    const [salesRuleMap, salesRuleGapPayload] = shareClassCodes.length
      ? await Promise.all([
          getMergedSalesRulesByWindCodes(shareClassCodes),
          getSalesRuleGapsForCodes(shareClassCodes, shareClassCodes.length, {
            purchasePlan: investorContext.purchasePlan,
            plannedAmount,
          }),
        ])
      : [new Map(), { rules: [] }]
    const activeSalesRuleEvidenceAlertsByCode = shareClassCodes.length
      ? await fetchActiveSalesRuleEvidenceAlertsForCodes(shareClassCodes)
      : new Map<string, ActiveSalesRuleEvidenceAlert[]>()
    const gapSummaryByCode = new Map((salesRuleGapPayload.rules || []).map((rule) => [rule.windCode.toUpperCase(), rule]))
    const amountByRate = (amount: number, rate: number | null | undefined) => {
      const value = Number(rate)
      return Number.isFinite(value) ? Math.round(amount * value / 100) : null
    }
    const feeRate = (item: { feeInfo?: Record<string, unknown> | null }) => {
      const managementFee = Number(item.feeInfo?.management_fee ?? item.feeInfo?.managementFee)
      const custodianFee = Number(item.feeInfo?.custodian_fee ?? item.feeInfo?.custodianFee)
      return Number.isFinite(managementFee) && Number.isFinite(custodianFee) ? managementFee + custodianFee : null
    }
    const infoByCode = buildShareClassInfoByCode(funds.map((item: { windCode?: string; name?: string; type?: string }) => ({
      windCode: item.windCode,
      name: item.name,
      type: item.type,
    })))
    const current = infoByCode.get(fund.windCode.toUpperCase()) || null

    return {
      status: current ? 'available' as const : 'unavailable' as const,
      source: 'api.funds.keyword_share_class+local.alert_events.sales_rule_evidence',
      note: current
        ? `检索到 ${current.siblingCount} 个同基金份额样本，正式判断前需比较份额费率、持有期和复查队列事件。`
        : '当前本地样本未发现同基金其他份额；研究复核仍需核对销售平台份额列表。',
      current,
      funds: funds.map((item: { windCode?: string; name?: string; type?: string; feeInfo?: Record<string, unknown> | null }) => {
        const normalizedCode = String(item.windCode || '').trim().toUpperCase()
	        const rule = normalizedCode ? salesRuleMap.get(normalizedCode) || null : null
	        const gapSummary = normalizedCode ? gapSummaryByCode.get(normalizedCode) || null : null
	        const alertMissingItems = normalizedCode
	          ? reviewAlertMissingItems(activeSalesRuleEvidenceAlertsByCode.get(normalizedCode))
	          : []
	        const annualBaseFeeAmount = amountByRate(plannedAmount, feeRate(item))
	        const purchaseFeeRate = hasSourceBackedSalesRuleField(rule, 'purchaseFeeSourceBacked', rule?.purchaseFeeRate) ? rule?.purchaseFeeRate ?? null : null
	        const salesServiceFeeRate = hasSourceBackedSalesRuleField(rule, 'salesServiceFeeSourceBacked', rule?.salesServiceFeeRate) ? rule?.salesServiceFeeRate ?? null : null
	        const purchaseFeeAmount = amountByRate(plannedAmount, purchaseFeeRate)
	        const salesServiceFeeAmount = amountByRate(plannedAmount, salesServiceFeeRate)
	        const knownParts = [annualBaseFeeAmount, purchaseFeeAmount, salesServiceFeeAmount]
	          .filter((value): value is number => value !== null)
	        const costMissingItems = [
	          !rule ? '兄弟份额销售规则待补' : '',
	          annualBaseFeeAmount === null ? '管理/托管费' : '',
	          purchaseFeeAmount === null ? '申购费（30天来源背书）' : '',
	          hasSourceBackedRedemptionRules(rule) ? '' : '赎回费/持有期',
	          salesServiceFeeAmount === null ? '销售服务费（30天来源背书）' : '',
          ...(gapSummary?.missingItems || []).filter((item) => item.startsWith('计划金额执行门禁')),
          ...alertMissingItems,
        ].filter(Boolean)
        const salesRuleMissingItems = Array.from(new Set([
          ...(gapSummary?.missingItems || (rule ? [] : ['销售规则整条待补'])),
          ...alertMissingItems,
        ]))
        return {
          windCode: item.windCode,
          name: item.name,
          type: item.type,
          shareClass: inferShareClass(item.name),
          annualBaseFeeAmount,
          purchaseFeeAmount,
          salesServiceFeeAmount,
          knownCost: knownParts.length ? knownParts.reduce((sum, value) => sum + value, 0) : null,
          costMissingItems,
          executionAmountGate: gapSummary?.executionAmountGate || null,
          salesRuleMissingItems,
          salesRuleMissingCount: Math.max(gapSummary?.missingCount ?? (rule ? 0 : 1), salesRuleMissingItems.length),
        }
      }),
    }
  } catch (error) {
    return {
      status: 'unavailable' as const,
      source: 'api.funds.keyword_share_class',
      note: error instanceof Error ? error.message : '同基金份额检索失败。',
      current: null,
      funds: [],
    }
  }
}

async function buildReportForRequest(request: Request, id: string) {
  const { searchParams } = new URL(request.url)
  const investorContext = normalizeInvestorContext({
    profile: searchParams.get('profile'),
    horizon: searchParams.get('horizon'),
    purchasePlan: searchParams.get('purchasePlan'),
  })
  const months = asPositiveNumber(searchParams.get('months'), 12, 3, 60)
  let lumpSumAmount = asPositiveNumber(searchParams.get('lumpSumAmount'), 10000, 1, 10_000_000)
  let monthlyAmount = asPositiveNumber(searchParams.get('monthlyAmount'), 1000, 1, 1_000_000)
  const plannedAmountOverride = asPositiveNumber(
    searchParams.get('plannedAmount'),
    investorContext.purchasePlan === 'lump_sum' ? lumpSumAmount : monthlyAmount,
    1,
    investorContext.purchasePlan === 'lump_sum' ? 10_000_000 : 1_000_000,
  )
  if (investorContext.purchasePlan === 'lump_sum') {
    lumpSumAmount = plannedAmountOverride
  } else {
    monthlyAmount = plannedAmountOverride
  }
  const plannedAmount = investorContext.purchasePlan === 'lump_sum' ? lumpSumAmount : monthlyAmount

  try {
    const fundResponse = await fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(id)}`, {
      cache: 'no-store',
    })
    const fundPayload = await fundResponse.json().catch(() => ({}))
    if (!fundResponse.ok) {
      return {
        report: null,
        status: fundResponse.status,
        error: fundPayload.detail || fundPayload.error || '基金不存在',
      }
    }

    const fund = toCamelFund(fundPayload.fund ? fundPayload.fund : fundPayload)
    const salesRule = fund.windCode ? await getMergedSalesRule(fund.windCode) : null
    const fundWithSalesRule = {
      ...fund,
      salesRule,
    }
    const buyEvidence = buildResearchEvidence(fundWithSalesRule, { purchasePlan: investorContext.purchasePlan, plannedAmount })
    const simulationResult = fund.windCode
      ? await fetchPurchaseSimulation(fund.windCode, months, lumpSumAmount, monthlyAmount)
      : { simulation: null, error: '基金代码缺失，无法读取净值回放' }
    const holdingEvidence = fund.windCode
      ? await fetchHoldingEvidence(request, fund.windCode)
      : {
          status: 'unavailable',
          windCode: id,
          holdings: [],
          industryBuckets: [],
          totalWeight: null,
          checkedQuarters: [],
          rejectedMockLikeQuarters: [],
          source: 'backend.tushare.fund_portfolio.filtered',
          note: '基金代码缺失，无法读取可信持仓。',
        }
    const salesRuleGapPayload = fund.windCode
      ? await getSalesRuleGapsForCodes([fund.windCode], 1, { purchasePlan: investorContext.purchasePlan, plannedAmount })
      : null
    const salesRuleGap = salesRuleGapPayload?.gaps?.[0] || null
    const salesRuleExecutionAmountGate = salesRuleGapPayload?.rules?.[0]?.executionAmountGate || null
    const alternativeEvidence = await fetchAlternativeEvidence(request, fund, investorContext, plannedAmount)
    const shareClassEvidence = await fetchShareClassEvidence(fund, investorContext, plannedAmount)

    return {
      report: buildResearchReviewReport({
        fund: fundWithSalesRule,
        buyEvidence,
        investorContext,
        plannedAmount,
        purchaseSimulation: simulationResult.simulation,
        simulationError: simulationResult.error,
        holdingEvidence,
        salesRuleGapEvidence: {
          status: salesRuleGapPayload ? 'available' : 'unavailable',
          source: salesRuleGapPayload?.source || 'explicit_codes_plus_local_sales_rules',
          total: salesRuleGapPayload?.totalMembers || 0,
          executionAmountGate: salesRuleExecutionAmountGate,
          gap: salesRuleGap,
        },
        alternativeEvidence,
        shareClassEvidence,
        generatedAt: new Date().toISOString(),
      }),
      status: 200,
      error: null,
    }
  } catch (error) {
    console.error('生成研究复核报告失败:', error)
    return {
      report: null,
      status: 500,
      error: '生成研究复核报告失败',
    }
  }
}

function jsonSafe(value: unknown) {
  return JSON.parse(JSON.stringify(value))
}

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : {}
    } catch {
      return {}
    }
  }
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

function stringValue(value: unknown) {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

type ReviewQueueAlertEvent = {
  id?: string
  fund_id?: string | null
  event_type?: string
  severity?: string
  title?: string
  message?: string
  status?: string
  details?: unknown
}

function alertWindCode(event: ReviewQueueAlertEvent) {
  const details = asRecord(event.details)
  return (
    stringValue(details.wind_code) ||
    stringValue(details.fund_code) ||
    stringValue(event.fund_id)
  ).toUpperCase()
}

async function fetchActiveSalesRuleEvidenceAlert(windCode: string) {
  const normalizedCode = windCode.trim().toUpperCase()
  if (!normalizedCode) return null
  const alertsUrl = new URL('/api/alerts', backendApiBaseUrl)
  const response = await fetch(alertsUrl, { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || '复查队列读取失败，不能证明销售规则/R1-R5证据有效。')
  }
  const events = Array.isArray(payload.events) ? payload.events as ReviewQueueAlertEvent[] : []
  return events.find((event) => (
    event.event_type === 'sales_rule_evidence' &&
    event.status !== 'resolved' &&
    alertWindCode(event) === normalizedCode
  )) || null
}

function reportAmountParams(report: ReturnType<typeof buildResearchReviewReport>) {
  const plannedAmount = Number(report.plannedAmount)
  const safePlannedAmount = Number.isFinite(plannedAmount) && plannedAmount > 0 ? plannedAmount : null
  const params = new URLSearchParams({
    purchasePlan: report.investorContext.purchasePlan,
    lumpSumAmount: String(
      report.investorContext.purchasePlan === 'lump_sum'
        ? safePlannedAmount || report.purchaseSimulation?.assumptions.lumpSumAmount || 10000
        : report.purchaseSimulation?.assumptions.lumpSumAmount || 10000,
    ),
    monthlyAmount: String(
      report.investorContext.purchasePlan === 'sip'
        ? safePlannedAmount || report.purchaseSimulation?.assumptions.monthlyAmount || 1000
        : report.purchaseSimulation?.assumptions.monthlyAmount || 1000,
    ),
  })
  params.set('plannedAmount', report.investorContext.purchasePlan === 'lump_sum'
    ? params.get('lumpSumAmount') || '10000'
    : params.get('monthlyAmount') || '1000')
  return params
}

function buildReviewQueueAlertBlockPayload(
  id: string,
  report: ReturnType<typeof buildResearchReviewReport>,
  alert: ReviewQueueAlertEvent,
) {
  const windCode = report.fund.windCode || id
  const amountParams = reportAmountParams(report)
  const draftParams = new URLSearchParams({
    profile: report.investorContext.profile,
    horizon: report.investorContext.horizon,
    draft: 'true',
    ...Object.fromEntries(amountParams),
  })
  const salesRulesParams = new URLSearchParams(Object.fromEntries(amountParams))
  salesRulesParams.set('codes', windCode)
  salesRulesParams.set('returnTo', `/funds/${encodeURIComponent(windCode)}`)
  return {
    error: `${report.fund.name || windCode} 存在未解决的销售规则/R1-R5 复查事件，补齐前不能生成或保存正式研究复核报告。`,
    code: 'STALE_SALES_RULE_EVIDENCE_ALERT_BLOCKED',
    reportStatus: 'blocked_by_review_queue',
    alertsHref: reviewEventsHref({ returnTo: `/funds/${encodeURIComponent(windCode)}` }),
    salesRulesHref: materialEvidenceHref(salesRulesParams),
    draftHref: `/api/funds/${encodeURIComponent(windCode)}/research-review-report?${draftParams.toString()}`,
    alert: {
      id: stringValue(alert.id),
      fundCode: alertWindCode(alert),
      severity: stringValue(alert.severity) || 'medium',
      title: stringValue(alert.title) || '销售规则/R1-R5证据待补',
      message: stringValue(alert.message) || '销售规则、R1-R5来源、费率或赎回规则存在过期/待补事件。',
    },
    message: '复查队列事件是正式研究复核报告前置门禁；可查看 draft 草稿继续补证，但不会写入报告库或冒充正式结论。',
  }
}

function strictInvestorSelectionParams(report: ReturnType<typeof buildResearchReviewReport>) {
  const params = reportAmountParams(report)
  params.set('profile', report.investorContext.profile)
  params.set('horizon', report.investorContext.horizon)
  params.set('lens', 'score')
  params.set('eligibleOnly', 'true')
  params.set('minEvidenceGrade', 'B')
  params.set('sourceLimit', '500')
  params.set('minScore', '55')
  return params
}

function buildSalesRuleGapBlockPayload(
  id: string,
  report: ReturnType<typeof buildResearchReviewReport>,
) {
  const salesRuleGap = report.salesRuleGapEvidence?.gap || null
  if (!salesRuleGap?.missingCount) return null

  const windCode = report.fund.windCode || id
  const amountParams = reportAmountParams(report)
  return {
    error: `${report.fund.name || windCode} 销售规则仍缺 ${salesRuleGap.missingCount} 项，补齐前不能生成正式研究复核报告。`,
    code: 'SALES_RULE_GAP_BLOCKED',
    reportStatus: 'blocked_before_generation',
    salesRulesHref: materialEvidenceHref(new URLSearchParams({
      codes: windCode,
      ...Object.fromEntries(amountParams),
    })),
    strictInvestorSelectionHref: `/investor-selection?${strictInvestorSelectionParams(report).toString()}`,
    salesRuleGap: {
      windCode: salesRuleGap.windCode,
      fundName: salesRuleGap.fundName,
      priority: salesRuleGap.priority,
      missingCount: salesRuleGap.missingCount,
      missingItems: salesRuleGap.missingItems,
      nextAction: salesRuleGap.nextAction,
    },
    alternativeEvidence: report.alternativeEvidence ? {
      status: report.alternativeEvidence.status,
      note: report.alternativeEvidence.note,
      attempts: report.alternativeEvidence.attempts,
      total: report.alternativeEvidence.total,
      source: report.alternativeEvidence.source,
      funds: report.alternativeEvidence.funds.slice(0, 4).map((item) => ({
        windCode: item.windCode,
        name: item.name,
        type: item.type,
        investorScore: item.investorScore,
        evidenceGrade: item.purchaseGate?.evidenceGrade || null,
        salesRuleGap: item.salesRuleGap ? {
          missingCount: item.salesRuleGap.missingCount,
          missingItems: item.salesRuleGap.missingItems,
          priority: item.salesRuleGap.priority || 'high',
          nextAction: item.salesRuleGap.nextAction || '补齐销售规则硬证据',
        } : null,
      })),
    } : null,
    alternativeDecision: report.alternativeDecision,
    message: '这是正式研究复核报告生成门禁，不会输出 Markdown；如需继续，请先录入真实销售平台/基金合同材料后重新生成。',
  }
}

function buildFormalReportReadinessBlockPayload(
  id: string,
  report: ReturnType<typeof buildResearchReviewReport>,
) {
  const blockReasons = [
    !report.purchaseSimulation
      ? '真实净值回放未完成，不能验证持有体验、回撤和压力测试。'
      : '',
    report.purchaseSimulation && report.purchaseSimulation.monthlyExperience.months < report.investorContext.minSampleMonths
      ? `${report.investorContext.horizonLabel}至少需要 ${report.investorContext.minSampleMonths} 个月回放，当前 ${report.purchaseSimulation.monthlyExperience.months} 个月。`
      : '',
    report.verdict.evidenceGrade === 'D'
      ? '证据等级为 D，关键研究证据不足。'
      : '',
    report.verdict.level === 'blocked'
      ? `当前结论为“${report.verdict.label}”，存在材料核验、风险预算或基础研究硬阻断，不能保存为正式研究复核报告。`
      : '',
    report.verdict.level === 'verify_first'
      ? '当前结论仍是“先补证再比较”，不能保存为正式研究复核报告。'
      : '',
  ].filter(Boolean)

  if (!blockReasons.length) return null

  const windCode = report.fund.windCode || id
  const amountParams = reportAmountParams(report)
  return {
    error: `${report.fund.name || windCode} 研究证据尚未达到正式报告保存条件。`,
    code: 'RESEARCH_EVIDENCE_NOT_READY',
    reportStatus: 'blocked_before_formal_save',
    blockReasons,
    draftHref: `/api/funds/${encodeURIComponent(windCode)}/research-review-report?${new URLSearchParams({
      profile: report.investorContext.profile,
      horizon: report.investorContext.horizon,
      draft: 'true',
      ...Object.fromEntries(amountParams),
    }).toString()}`,
    salesRulesHref: materialEvidenceHref(new URLSearchParams({
      codes: windCode,
      ...Object.fromEntries(amountParams),
    })),
    strictInvestorSelectionHref: `/investor-selection?${strictInvestorSelectionParams(report).toString()}`,
    verdict: {
      level: report.verdict.level,
      label: report.verdict.label,
      evidenceGrade: report.verdict.evidenceGrade,
      cautionFlags: report.verdict.cautionFlags,
      recheckTriggers: report.verdict.recheckTriggers,
    },
    purchaseSimulation: report.purchaseSimulation ? {
      source: report.purchaseSimulation.source,
      months: report.purchaseSimulation.monthlyExperience.months,
      observations: report.purchaseSimulation.period.observations,
      startDate: report.purchaseSimulation.period.startDate,
      endDate: report.purchaseSimulation.period.endDate,
    } : null,
    message: '这是正式研究复核报告保存门禁；可查看 draft 草稿继续补证，但不会写入报告库或冒充正式结论。',
  }
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const { searchParams } = new URL(request.url)
    const result = await buildReportForRequest(request, id)
    if (!result.report) {
      return NextResponse.json(
        { error: result.error },
        { status: result.status },
      )
    }
    const reviewQueueAlert = result.report.fund.windCode
      ? await fetchActiveSalesRuleEvidenceAlert(result.report.fund.windCode)
      : null
    if (reviewQueueAlert && searchParams.get('draft') !== 'true') {
      return NextResponse.json(buildReviewQueueAlertBlockPayload(id, result.report, reviewQueueAlert), {
        status: 409,
        headers: {
          'Cache-Control': 'no-store',
        },
      })
    }
    const blockPayload = buildSalesRuleGapBlockPayload(id, result.report)
    if (blockPayload && searchParams.get('draft') !== 'true') {
      return NextResponse.json(blockPayload, {
        status: 409,
        headers: {
          'Cache-Control': 'no-store',
        },
      })
    }
    const readinessBlockPayload = buildFormalReportReadinessBlockPayload(id, result.report)
    if (readinessBlockPayload && searchParams.get('draft') !== 'true') {
      return NextResponse.json(readinessBlockPayload, {
        status: 409,
        headers: {
          'Cache-Control': 'no-store',
        },
      })
    }

    if (searchParams.get('format') === 'markdown') {
      const filename = reportFilename(result.report.fund)
      return new Response(result.report.markdown, {
        status: 200,
        headers: {
          'Content-Type': 'text/markdown; charset=utf-8',
          'Cache-Control': 'no-store',
          'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`,
        },
      })
    }

    return NextResponse.json(result.report, {
      headers: {
        'Cache-Control': 'no-store',
      },
    })
  } catch (error) {
    console.error('生成研究复核报告失败:', error)
    return NextResponse.json(
      { error: '生成研究复核报告失败' },
      { status: 500 },
    )
  }
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const result = await buildReportForRequest(request, id)
    if (!result.report) {
      return NextResponse.json(
        { error: result.error },
        { status: result.status },
      )
    }
    const reviewQueueAlert = result.report.fund.windCode
      ? await fetchActiveSalesRuleEvidenceAlert(result.report.fund.windCode)
      : null
    if (reviewQueueAlert) {
      return NextResponse.json(
        buildReviewQueueAlertBlockPayload(id, result.report, reviewQueueAlert),
        { status: 409 },
      )
    }
    const salesRuleGap = result.report.salesRuleGapEvidence?.gap || null
    if (salesRuleGap?.missingCount) {
      return NextResponse.json(
        buildSalesRuleGapBlockPayload(id, result.report) || {
          error: '材料证据存在硬缺口，补齐前不保存正式研究复核报告。',
          code: 'SALES_RULE_GAP_BLOCKED',
        },
        { status: 409 },
      )
    }
    const readinessBlockPayload = buildFormalReportReadinessBlockPayload(id, result.report)
    if (readinessBlockPayload) {
      return NextResponse.json(readinessBlockPayload, { status: 409 })
    }

    const dataSources = jsonSafe({
      source: 'research_review_report',
      sources: result.report.sources,
      fund: result.report.fund,
      investorContext: result.report.investorContext,
      plannedAmount: result.report.plannedAmount ?? null,
      verdict: result.report.verdict,
      recheckTriggers: result.report.verdict.recheckTriggers,
      riskLevelSourcePolicy: result.report.riskLevelSourcePolicy,
      purchaseSimulation: result.report.purchaseSimulation ? {
        months: result.report.purchaseSimulation.monthlyExperience.months,
        observations: result.report.purchaseSimulation.period.observations,
        lumpSumAmount: result.report.purchaseSimulation.assumptions.lumpSumAmount,
        monthlyAmount: result.report.purchaseSimulation.assumptions.monthlyAmount,
        stressExperience: result.report.purchaseSimulation.stressExperience || null,
      } : null,
      stressExperience: result.report.purchaseSimulation?.stressExperience ? {
        label: result.report.purchaseSimulation.stressExperience.label,
        stressLevel: result.report.purchaseSimulation.stressExperience.stressLevel,
        stressScore: result.report.purchaseSimulation.stressExperience.stressScore,
        longestUnderwaterDays: result.report.purchaseSimulation.stressExperience.longestUnderwaterDays,
        recoveryDays: result.report.purchaseSimulation.stressExperience.recoveryDays,
        worstDrawdown: result.report.purchaseSimulation.stressExperience.worstDrawdown,
        troughDate: result.report.purchaseSimulation.stressExperience.troughDate,
        longestLosingStreakMonths: result.report.purchaseSimulation.stressExperience.longestLosingStreakMonths,
        worstThreeMonthReturn: result.report.purchaseSimulation.stressExperience.worstThreeMonthReturn,
      } : null,
      feeEstimate: result.report.feeEstimate ? {
        purchaseFeeRate: result.report.feeEstimate.purchaseFeeRate,
        redemptionFeeRate: result.report.feeEstimate.redemptionFeeRate,
        redemptionRuleLabel: result.report.feeEstimate.redemptionRuleLabel,
        lumpSumEstimatedCost: result.report.feeEstimate.lumpSumEstimatedCost,
        sipEstimatedCost: result.report.feeEstimate.sipEstimatedCost,
        lumpSumNetReturn: result.report.feeEstimate.lumpSumNetReturn,
        sipNetReturn: result.report.feeEstimate.sipNetReturn,
      } : null,
      holdingEvidence: result.report.holdingEvidence ? {
        status: result.report.holdingEvidence.status,
        quarter: result.report.holdingEvidence.quarter || null,
        holdings: result.report.holdingEvidence.holdings?.length || 0,
        industryBuckets: result.report.holdingEvidence.industryBuckets?.slice(0, 5) || [],
        totalWeight: result.report.holdingEvidence.totalWeight ?? null,
        checkedQuarters: result.report.holdingEvidence.checkedQuarters || [],
        rejectedMockLikeQuarters: result.report.holdingEvidence.rejectedMockLikeQuarters || [],
        source: result.report.holdingEvidence.source || null,
        note: result.report.holdingEvidence.note || null,
      } : null,
      holdingExposureDecision: result.report.holdingExposureDecision,
      managerAttributionDecision: result.report.managerAttributionDecision,
      salesRuleGapEvidence: result.report.salesRuleGapEvidence ? {
        status: result.report.salesRuleGapEvidence.status,
        source: result.report.salesRuleGapEvidence.source,
        total: result.report.salesRuleGapEvidence.total,
        executionAmountGate: result.report.salesRuleGapEvidence.executionAmountGate || null,
        gap: result.report.salesRuleGapEvidence.gap ? {
          windCode: result.report.salesRuleGapEvidence.gap.windCode,
          fundName: result.report.salesRuleGapEvidence.gap.fundName,
          priority: result.report.salesRuleGapEvidence.gap.priority,
          missingCount: result.report.salesRuleGapEvidence.gap.missingCount,
          missingItems: result.report.salesRuleGapEvidence.gap.missingItems,
          nextAction: result.report.salesRuleGapEvidence.gap.nextAction,
        } : null,
      } : null,
      alternativeEvidence: result.report.alternativeEvidence ? {
        status: result.report.alternativeEvidence.status,
        note: result.report.alternativeEvidence.note,
        attempts: result.report.alternativeEvidence.attempts,
        total: result.report.alternativeEvidence.total,
        source: result.report.alternativeEvidence.source,
        funds: result.report.alternativeEvidence.funds.map((item) => ({
          windCode: item.windCode,
          name: item.name,
          type: item.type,
          investorScore: item.investorScore,
          purchaseGate: item.purchaseGate?.label || null,
          evidenceGrade: item.purchaseGate?.evidenceGrade || null,
        })),
      } : null,
      alternativeWinLossLines: result.report.alternativeWinLossLines || [],
      shareClassEvidence: result.report.shareClassEvidence ? {
        status: result.report.shareClassEvidence.status,
        source: result.report.shareClassEvidence.source,
        note: result.report.shareClassEvidence.note,
        current: result.report.shareClassEvidence.current,
        funds: result.report.shareClassEvidence.funds,
      } : null,
      shareClassDecision: result.report.shareClassDecision,
      alternativeDecision: result.report.alternativeDecision,
    })
    const generationParams = jsonSafe({
      mode: 'deterministic_research_review',
      provider: 'local_rules',
      model: 'tushare_postgres_sales_rules_nav_replay',
      generatedAt: result.report.generatedAt,
      evidenceGrade: result.report.verdict.evidenceGrade,
      verdict: result.report.verdict.label,
      recheckTriggerCount: result.report.verdict.recheckTriggers.length,
      profile: result.report.investorContext.profile,
      horizon: result.report.investorContext.horizon,
      purchasePlan: result.report.investorContext.purchasePlan,
      plannedAmount: result.report.plannedAmount ?? null,
      months: result.report.purchaseSimulation?.monthlyExperience.months ?? null,
      lumpSumAmount: result.report.purchaseSimulation?.assumptions.lumpSumAmount ?? null,
      monthlyAmount: result.report.purchaseSimulation?.assumptions.monthlyAmount ?? null,
      stressScore: result.report.purchaseSimulation?.stressExperience?.stressScore ?? null,
      stressLevel: result.report.purchaseSimulation?.stressExperience?.stressLevel ?? null,
      longestUnderwaterDays: result.report.purchaseSimulation?.stressExperience?.longestUnderwaterDays ?? null,
      recoveryDays: result.report.purchaseSimulation?.stressExperience?.recoveryDays ?? null,
      worstThreeMonthReturn: result.report.purchaseSimulation?.stressExperience?.worstThreeMonthReturn?.returnRate ?? null,
      purchaseFeeRate: result.report.feeEstimate?.purchaseFeeRate ?? null,
      redemptionFeeRate: result.report.feeEstimate?.redemptionFeeRate ?? null,
      lumpSumNetReturn: result.report.feeEstimate?.lumpSumNetReturn ?? null,
      sipNetReturn: result.report.feeEstimate?.sipNetReturn ?? null,
      holdingEvidenceStatus: result.report.holdingEvidence?.status ?? null,
      holdingEvidenceQuarter: result.report.holdingEvidence?.quarter ?? null,
      holdingExposureLabel: result.report.holdingExposureDecision.label,
      holdingExposureScore: result.report.holdingExposureDecision.score,
      holdingExposureTopIndustry: result.report.holdingExposureDecision.topIndustry,
      holdingExposureTopTenWeight: result.report.holdingExposureDecision.topTenWeight,
      managerAttributionStatus: result.report.managerAttributionDecision.status,
      managerAttributionCoverageRatio: result.report.managerAttributionDecision.coverageRatio,
      managerAttributionWindowYears: result.report.managerAttributionDecision.attributionWindowYears,
      salesRuleHardGapCount: result.report.salesRuleGapEvidence?.gap?.missingCount ?? 0,
      salesRuleHardGapPriority: result.report.salesRuleGapEvidence?.gap?.priority ?? null,
      riskLevelSourcePolicyStatus: result.report.riskLevelSourcePolicy.status,
      riskLevelSourceBacked: result.report.riskLevelSourcePolicy.sourceBacked,
      riskLevelGateSignals: result.report.riskLevelSourcePolicy.signals,
      alternativeEvidenceStatus: result.report.alternativeEvidence?.status ?? null,
      alternativeCandidateCount: result.report.alternativeEvidence?.funds.length ?? 0,
      alternativeWinLossLineCount: result.report.alternativeWinLossLines?.length ?? 0,
      shareClassEvidenceStatus: result.report.shareClassEvidence?.status ?? null,
      shareClassSiblingCount: result.report.shareClassEvidence?.current?.siblingCount ?? 0,
      shareClassRecommendedCode: result.report.shareClassDecision.recommendedCode || null,
      shareClassDecisionConfidence: result.report.shareClassDecision.confidence,
      shareClassFormalChoiceReady: result.report.shareClassDecision.formalChoiceReady,
      alternativeDecisionStatus: result.report.alternativeDecision.status,
      alternativeDecisionVerdict: result.report.alternativeDecision.verdict,
    })
    const savedRows = await sql<{ id: string }[]>`
      INSERT INTO ai_analysis_reports (
        target_type,
        target_id,
        report_type,
        content,
        data_sources,
        research_reports_used,
        generation_params,
        created_at
      ) VALUES (
        'fund',
        ${result.report.fund.windCode || id},
        'fund_research_review',
        ${result.report.markdown},
        CAST(${JSON.stringify(dataSources)} AS jsonb),
        ARRAY[]::text[],
        CAST(${JSON.stringify(generationParams)} AS jsonb),
        NOW()
      )
      RETURNING id::text
    `
    const saved = savedRows[0]

    return NextResponse.json({
      id: saved?.id,
      reportId: saved?.id,
      saved: Boolean(saved?.id),
      report: result.report,
    })
  } catch (error) {
    console.error('保存研究复核报告失败:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '保存研究复核报告失败' },
      { status: 500 },
    )
  }
}
