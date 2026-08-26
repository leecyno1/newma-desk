import { NextResponse } from 'next/server'
import { backendApiBaseUrl, toCamelFund } from '@/lib/backend-api'
import { normalizeFundReports } from '@/lib/fund-report-normalizer'
import { buyEvidenceTool } from '@/lib/research-platform/tools'
import { fetchActiveSalesRuleEvidenceAlertForCode } from '@/lib/sales-rule-review-alerts'
import { getMergedSalesRule } from '@/lib/sales-rules'

const PEER_PERCENTILE_DETAIL_TIMEOUT_MS = 5000

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const { searchParams } = new URL(request.url)
    const purchasePlan = searchParams.get('purchasePlan') === 'lump_sum' ? 'lump_sum' : 'sip'
    const plannedAmount = Number(searchParams.get('plannedAmount') || '')
    const safePlannedAmount = Number.isFinite(plannedAmount) && plannedAmount > 0 ? plannedAmount : null
    const response = await fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(id)}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '基金不存在' },
        { status: response.status }
      )
    }

    const fund = toCamelFund(payload.fund ? payload.fund : payload)
    const fundWithReports = {
      ...fund,
      aiReports: normalizeFundReports(fund.aiReports),
    }
    const salesRule = fundWithReports.windCode ? await getMergedSalesRule(fundWithReports.windCode) : null
    const activeSalesRuleEvidenceAlert = fundWithReports.windCode
      ? await fetchActiveSalesRuleEvidenceAlertForCode(fundWithReports.windCode)
      : null
    const fundWithSalesRule = {
      ...fundWithReports,
      salesRule,
      activeSalesRuleEvidenceAlert,
    }
    let peerPercentiles = null
    if (fund.windCode) {
      try {
        const peerResponse = await fetch(
          `${backendApiBaseUrl}/api/funds/${encodeURIComponent(fund.windCode)}/peer-percentiles?window=1y`,
          { cache: 'no-store', signal: AbortSignal.timeout(PEER_PERCENTILE_DETAIL_TIMEOUT_MS) },
        )
        if (peerResponse.ok) {
          peerPercentiles = await peerResponse.json()
        }
      } catch (peerError) {
        console.warn('获取同类分位失败:', peerError)
      }
    }

    return NextResponse.json({
      ...fundWithSalesRule,
      peerPercentiles,
      buyEvidence: buyEvidenceTool.run({
        fund: fundWithSalesRule,
        purchasePlan,
        plannedAmount: safePlannedAmount,
      }).data,
    })
  } catch (error) {
    console.error('获取基金详情失败:', error)
    return NextResponse.json(
      { error: '获取基金详情失败' },
      { status: 500 }
    )
  }
}

export async function PUT() {
  return NextResponse.json(
    { error: '当前版本请通过数据同步流程更新基金数据' },
    { status: 405 }
  )
}

export async function DELETE() {
  return NextResponse.json(
    { error: '当前版本不支持从浏览器删除基金' },
    { status: 405 }
  )
}
