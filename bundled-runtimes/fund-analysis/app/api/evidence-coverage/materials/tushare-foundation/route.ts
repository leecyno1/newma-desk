import { NextRequest, NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'
import { getSalesRuleGapsForCodes, type SalesRuleGapsPayload } from '@/lib/sales-rule-gaps'
import { upsertSalesRule, type SalesRuleInput } from '@/lib/sales-rules'
import {
  normalizeSalesRulePurchasePlan,
  salesRuleFoundationDisclaimerForPlan,
  salesRuleFoundationManualFieldsForPlan,
  salesRuleFoundationSourceNoteForPlan,
  type SalesRulePurchasePlan,
} from '@/lib/sales-rule-purchase-plan-copy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const MAX_CODES = 100
const PLATFORM = 'tushare_fund_basic'
const IMPORT_CONCURRENCY = 5

function normalizeCodes(value: unknown) {
  const rawCodes = Array.isArray(value)
    ? value
    : typeof value === 'string'
      ? value.split(',')
      : []
  return Array.from(new Set(
    rawCodes
      .map((code) => String(code || '').trim().toUpperCase())
      .filter((code) => /^[0-9A-Z]{6,12}\.(OF|SH|SZ|BJ)$/i.test(code)),
  )).slice(0, MAX_CODES)
}

function todayText() {
  return new Date().toISOString().slice(0, 10)
}

function toDate(value: unknown) {
  if (typeof value !== 'string' || !value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function statusFromPurchaseStart(purchaseStartDate: unknown) {
  const purchaseStart = toDate(purchaseStartDate)
  if (!purchaseStart) {
    return {
      purchaseStatus: 'unknown' as const,
      purchaseStatusLabel: '申购待核',
    }
  }
  const currentDate = new Date()
  currentDate.setHours(0, 0, 0, 0)
  return purchaseStart > currentDate
    ? {
        purchaseStatus: 'closed' as const,
        purchaseStatusLabel: '申购未开放',
      }
    : {
        purchaseStatus: 'open' as const,
        purchaseStatusLabel: 'Tushare申购起始日已到',
      }
}

async function syncFundFromTushare(windCode: string) {
  const response = await fetch(`${backendApiBaseUrl}/api/data-sync/funds/${encodeURIComponent(windCode)}`, {
    cache: 'no-store',
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(payload.detail) ? payload.detail.join('；') : payload.detail
    throw new Error(detail || payload.error || '同步基金基础数据失败')
  }
  return payload
}

async function fetchFundEvidence(windCode: string, retryAfterSync = true): Promise<{
  name: string
  purchaseStartDate: unknown
  redeemStartDate: unknown
  status: unknown
  syncedBeforeRead: boolean
  foundationStatusFound: boolean
}> {
  const response = await fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(windCode)}`, {
    cache: 'no-store',
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || '读取基金基础字段失败')
  }
  const fund = payload.fund || payload
  const salesStatus = fund.sales_status || fund.salesStatus || {}
  const operationStatus = fund.operation_status || fund.operationStatus || {}
  const purchaseStartDate = salesStatus.purchase_start_date || operationStatus.purchase_start_date || null
  const redeemStartDate = salesStatus.redeem_start_date || operationStatus.redeem_start_date || null
  const status = salesStatus.status || operationStatus.raw_state || null
  if (!purchaseStartDate && !redeemStartDate && !status) {
    if (retryAfterSync) {
      await syncFundFromTushare(windCode)
      const syncedEvidence = await fetchFundEvidence(windCode, false)
      return {
        ...syncedEvidence,
        syncedBeforeRead: true,
      }
    }
  }
  return {
    name: fund.name || fund.fund_name || windCode,
    purchaseStartDate,
    redeemStartDate,
    status,
    syncedBeforeRead: false,
    foundationStatusFound: Boolean(purchaseStartDate || redeemStartDate || status),
  }
}

function buildRuleInput(windCode: string, evidence: Awaited<ReturnType<typeof fetchFundEvidence>>, purchasePlan: SalesRulePurchasePlan): SalesRuleInput {
  const purchaseStatus = statusFromPurchaseStart(evidence.purchaseStartDate)
  return {
    windCode,
    platform: PLATFORM,
    purchaseStatus: purchaseStatus.purchaseStatus,
    purchaseStatusLabel: purchaseStatus.purchaseStatusLabel,
    sourceUrl: 'tushare.fund_basic',
    sourceUpdatedAt: todayText(),
    notes: [
      `${evidence.name} 的基础申赎状态来自 Tushare fund_basic。`,
      evidence.purchaseStartDate ? `申购起始日：${evidence.purchaseStartDate}` : '',
      evidence.redeemStartDate ? `赎回起始日：${evidence.redeemStartDate}` : '',
      evidence.status ? `原始状态：${evidence.status}` : '',
      evidence.foundationStatusFound ? '' : 'Tushare fund_basic 未返回明确申购/赎回起始日，申购状态仍需销售平台核验。',
      salesRuleFoundationSourceNoteForPlan(purchasePlan),
    ].filter(Boolean).join('；'),
  }
}

async function importFoundationForCode(windCode: string, purchasePlan: SalesRulePurchasePlan) {
  const evidence = await fetchFundEvidence(windCode)
  const rule = buildRuleInput(windCode, evidence, purchasePlan)
  const savedRule = await upsertSalesRule(windCode, rule, PLATFORM)
  return {
    ...savedRule,
    syncedBeforeRead: evidence.syncedBeforeRead,
    foundationStatusFound: evidence.foundationStatusFound,
  }
}

async function mapWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  worker: (item: T) => Promise<R>,
) {
  const results: R[] = []
  let nextIndex = 0
  const workerCount = Math.min(Math.max(1, concurrency), items.length)

  await Promise.all(Array.from({ length: workerCount }, async () => {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex
      nextIndex += 1
      results[currentIndex] = await worker(items[currentIndex])
    }
  }))

  return results
}

function missingItemsByCode(payload: SalesRuleGapsPayload) {
  return new Map(
    payload.rules.map((rule) => [rule.windCode.toUpperCase(), rule.missingItems]),
  )
}

function buildGapImpact(codes: string[], before: SalesRuleGapsPayload, after: SalesRuleGapsPayload) {
  const beforeByCode = missingItemsByCode(before)
  const afterByCode = missingItemsByCode(after)
  const funds = codes.map((windCode) => {
    const beforeItems = beforeByCode.get(windCode) || []
    const afterItems = afterByCode.get(windCode) || []
    const closedMissingItems = beforeItems.filter((item) => !afterItems.includes(item))
    return {
      windCode,
      beforeMissingItems: beforeItems,
      afterMissingItems: afterItems,
      closedMissingItems,
      remainingMissingItems: afterItems,
      closedCount: closedMissingItems.length,
      remainingCount: afterItems.length,
      foundationCoveredItems: closedMissingItems.filter((item) => item === '申购状态' || item === '来源日期' || item === '来源日期过旧'),
      manualStillRequiredItems: afterItems.filter((item) => item !== '申购状态' && item !== '来源日期' && item !== '来源日期过旧'),
      unlocked: beforeItems.length > 0 && afterItems.length === 0,
      improved: closedMissingItems.length > 0 && afterItems.length > 0,
    }
  })
  return {
    summary: {
      beforeGapFunds: before.gapCount,
      afterGapFunds: after.gapCount,
      unlockedFunds: funds.filter((fund) => fund.unlocked).length,
      improvedFunds: funds.filter((fund) => fund.improved).length,
      closedMissingItemCount: funds.reduce((sum, fund) => sum + fund.closedCount, 0),
      remainingMissingItemCount: funds.reduce((sum, fund) => sum + fund.remainingCount, 0),
    },
    funds,
    beforeSource: before.source,
    afterSource: after.source,
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}))
    const codes = normalizeCodes((body as Record<string, unknown>).codes)
    const purchasePlan = normalizeSalesRulePurchasePlan(
      (body as Record<string, unknown>).purchasePlan || request.nextUrl.searchParams.get('purchasePlan'),
    )
    const plannedAmountValue = Number((body as Record<string, unknown>).plannedAmount || request.nextUrl.searchParams.get('plannedAmount') || '')
    const plannedAmount = Number.isFinite(plannedAmountValue) && plannedAmountValue > 0 ? plannedAmountValue : null
    if (codes.length === 0) {
      return NextResponse.json({ error: '请提供 codes 数组或逗号分隔基金代码' }, { status: 400 })
    }

    const beforeGapPayload = await getSalesRuleGapsForCodes(codes, codes.length, { purchasePlan, plannedAmount })
    const results = await mapWithConcurrency(codes, IMPORT_CONCURRENCY, async (windCode) => {
      try {
        return {
          ok: true as const,
          value: await importFoundationForCode(windCode, purchasePlan),
        }
      } catch (error) {
        return {
          ok: false as const,
          value: {
            windCode,
            error: error instanceof Error ? error.message : '导入基础申赎状态失败',
          },
        }
      }
    })
    const saved = results.filter((result) => result.ok).map((result) => result.value)
    const failed = results.filter((result) => !result.ok).map((result) => result.value)
    const afterGapPayload = await getSalesRuleGapsForCodes(codes, codes.length, { purchasePlan, plannedAmount })
    const gapImpact = buildGapImpact(codes, beforeGapPayload, afterGapPayload)

    return NextResponse.json({
      savedCount: saved.length,
      failedCount: failed.length,
      saved,
      failed,
      source: 'backend.tushare.fund_basic_to_local_sales_rules',
      purchasePlan,
      plannedAmount,
      gapImpact,
      manualMissingFields: salesRuleFoundationManualFieldsForPlan(purchasePlan),
      disclaimer: salesRuleFoundationDisclaimerForPlan(purchasePlan),
    }, { status: failed.length > 0 ? 207 : 200 })
  } catch (error) {
    console.error('导入 Tushare 基础申赎状态失败:', error)
    return NextResponse.json({ error: '导入 Tushare 基础申赎状态失败' }, { status: 500 })
  }
}
