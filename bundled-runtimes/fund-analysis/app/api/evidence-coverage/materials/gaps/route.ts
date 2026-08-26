import { NextResponse } from 'next/server'
import { getSalesRuleGaps, getSalesRuleGapsForCodes, type SalesRuleGapPurchasePlan } from '@/lib/sales-rule-gaps'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const status = searchParams.get('status') || 'candidate'
    const limit = Number(searchParams.get('limit') || '100')
    const codes = searchParams.get('codes')
    const purchasePlan = searchParams.get('purchasePlan')
    const plannedAmount = Number(searchParams.get('plannedAmount') || '')
    const safePurchasePlan: SalesRuleGapPurchasePlan | null = purchasePlan === 'lump_sum' || purchasePlan === 'sip'
      ? purchasePlan
      : null
    const options = {
      purchasePlan: safePurchasePlan,
      plannedAmount: Number.isFinite(plannedAmount) && plannedAmount > 0 ? plannedAmount : null,
    }
    if (codes) {
      return NextResponse.json(await getSalesRuleGapsForCodes(codes.split(','), limit, options))
    }
    return NextResponse.json(await getSalesRuleGaps(status, limit, options))
  } catch (error) {
    console.error('读取材料核验待补清单失败:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '读取材料核验待补清单失败' },
      { status: 500 },
    )
  }
}
