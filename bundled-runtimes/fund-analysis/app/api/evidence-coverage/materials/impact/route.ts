import { NextRequest, NextResponse } from 'next/server'
import { getSalesRuleImpact } from '@/lib/sales-rule-impact'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  try {
    const purchasePlan = request.nextUrl.searchParams.get('purchasePlan') === 'lump_sum' ? 'lump_sum' : 'sip'
    const plannedAmount = request.nextUrl.searchParams.get('plannedAmount')
    return NextResponse.json(await getSalesRuleImpact(purchasePlan, plannedAmount))
  } catch (error) {
    console.error('读取材料核验影响失败:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '读取材料核验影响失败' },
      { status: 500 },
    )
  }
}
