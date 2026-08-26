import { NextRequest, NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'
import { getSalesRuleGapsForCodes, type SalesRuleGapPurchasePlan } from '@/lib/sales-rule-gaps'
import {
  salesRuleFoundationDisclaimerForPlan,
  salesRuleFoundationManualFieldsForPlan,
} from '@/lib/sales-rule-purchase-plan-copy'
import { getMergedSalesRule, getSalesRule, upsertSalesRule } from '@/lib/sales-rules'
import { validateSalesRule } from '@/lib/sales-rule-validation'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

async function loadTushareEvidence(windCode: string) {
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(windCode)}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) return null
    const fund = payload.fund || payload
    const info = fund.raw_data?.info || {}
    return {
      source: 'tushare.fund_basic',
      purchaseStartDate: info.purchase_start_date ?? fund.operation_status?.purchase_start_date ?? null,
      redeemStartDate: info.redeem_start_date ?? fund.operation_status?.redeem_start_date ?? null,
      managementFee: info.management_fee ?? fund.fee_info?.management_fee ?? null,
      custodianFee: info.custodian_fee ?? fund.fee_info?.custodian_fee ?? null,
      status: info.status ?? fund.sales_status?.status ?? null,
      benchmark: info.benchmark ?? fund.benchmark ?? null,
    }
  } catch (error) {
    console.warn('读取 Tushare 材料证据失败:', error)
    return null
  }
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const { searchParams } = new URL(request.url)
    const purchasePlan: SalesRuleGapPurchasePlan = searchParams.get('purchasePlan') === 'lump_sum' ? 'lump_sum' : 'sip'
    const plannedAmount = Number(searchParams.get('plannedAmount') || '')
    const safePlannedAmount = Number.isFinite(plannedAmount) && plannedAmount > 0 ? plannedAmount : null
    const [salesRule, manualRule, tushareEvidence, gapPayload] = await Promise.all([
      getMergedSalesRule(id),
      getSalesRule(id),
      loadTushareEvidence(id),
      getSalesRuleGapsForCodes([id], 1, { purchasePlan, plannedAmount: safePlannedAmount }),
    ])
    const salesRuleGap = gapPayload.gaps[0] || null

    return NextResponse.json({
      fundCode: id,
      data: salesRule,
      manualRule,
      tushareEvidence,
      purchasePlan,
      plannedAmount: safePlannedAmount,
      missingRequired: salesRuleGap?.missingItems || [],
      salesRuleGap,
      manualMissingFields: salesRuleFoundationManualFieldsForPlan(purchasePlan),
      source: salesRule ? 'local.postgres.fund_sales_rules.merged' : 'not_configured',
      disclaimer: salesRuleFoundationDisclaimerForPlan(purchasePlan),
    })
  } catch (error) {
    console.error('读取单基金材料核验失败:', error)
    return NextResponse.json({ error: '读取单基金材料核验失败' }, { status: 500 })
  }
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const body = await request.json().catch(() => null)
    if (!body || typeof body !== 'object') {
      return NextResponse.json({ error: '请求体必须是 JSON 对象' }, { status: 400 })
    }

    const validationErrors = validateSalesRule(body as Record<string, unknown>)
    if (validationErrors.length) {
      return NextResponse.json(
        {
          error: 'MATERIAL_EVIDENCE_VALIDATION_FAILED',
          detail: validationErrors.join('；'),
          validationErrors,
        },
        { status: 422 },
      )
    }

    const salesRule = await upsertSalesRule(id, body)
    return NextResponse.json(
      {
        data: salesRule,
        source: 'local.postgres.fund_sales_rules',
      },
      { status: 200 },
    )
  } catch (error) {
    console.error('保存单基金材料核验失败:', error)
    return NextResponse.json({ error: '保存单基金材料核验失败' }, { status: 500 })
  }
}
