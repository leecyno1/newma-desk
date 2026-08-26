import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'
import { buyEvidenceTool } from '@/lib/research-platform/tools'
import { getMergedSalesRulesByWindCodes, type SalesRule } from '@/lib/sales-rules'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type PurchasePlan = 'lump_sum' | 'sip'

function normalizePurchasePlan(value: unknown): PurchasePlan {
  return value === 'lump_sum' ? 'lump_sum' : 'sip'
}

function normalizePlannedAmount(value: unknown) {
  const amount = Number(value)
  return Number.isFinite(amount) && amount > 0 ? amount : null
}

async function loadBuyEvidence(windCode: string, purchasePlan: PurchasePlan, plannedAmount: number | null, salesRule: SalesRule | null) {
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(windCode)}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) return {}
    const fund = payload.fund ?? payload
    const fundWithSalesRule = {
      ...fund,
      salesRule,
    }
    return {
      id: fund.id ?? null,
      operation_status: fund.operation_status ?? null,
      sales_status: fund.sales_status ?? null,
      fee_info: fund.fee_info ?? null,
      benchmark: fund.benchmark ?? null,
      sales_rule: salesRule,
      buy_evidence: buyEvidenceTool.run({
        fund: fundWithSalesRule,
        purchasePlan,
        plannedAmount,
      }).data,
    }
  } catch (error) {
    console.warn(`读取 ${windCode} 研究证据失败:`, error)
    return {}
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const purchasePlan = normalizePurchasePlan(body.purchasePlan)
    const plannedAmount = normalizePlannedAmount(body.plannedAmount)
    const response = await fetch(`${backendApiBaseUrl}/api/funds/compare-matrix`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        windCodes: body.windCodes || [],
        window: body.window || '1y',
      }),
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '生成对比矩阵失败' },
        { status: response.status }
      )
    }

    const matrixFunds = (payload.funds || []) as Record<string, unknown>[]
    const matrixCodes = matrixFunds
      .map((fund) => typeof fund.wind_code === 'string' ? fund.wind_code : '')
      .filter(Boolean)
    const salesRulesByCode = await getMergedSalesRulesByWindCodes(matrixCodes)
    const funds = await Promise.all(
      matrixFunds.map(async (fund: Record<string, unknown>) => {
        const windCode = typeof fund.wind_code === 'string' ? fund.wind_code : ''
        return {
          ...fund,
          ...(windCode ? await loadBuyEvidence(windCode, purchasePlan, plannedAmount, salesRulesByCode.get(windCode) || null) : {}),
        }
      }),
    )

    return NextResponse.json({
      ...payload,
      purchasePlan,
      plannedAmount,
      funds,
    })
  } catch (error) {
    console.error('生成对比矩阵失败:', error)
    return NextResponse.json(
      { error: '生成对比矩阵失败' },
      { status: 500 }
    )
  }
}
