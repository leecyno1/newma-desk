import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type Holding = {
  stockCode: string
  stockName: string
  industry: string
  weight: number | null
  quarters?: string[]
}

const mockStockNames = new Set([
  '贵州茅台',
  '五粮液',
  '宁德时代',
  '中国平安',
  '招商银行',
  '比亚迪',
  '长江电力',
  '东方财富',
  '海康威视',
  '隆基绿能',
])

function numberOrNull(value: unknown) {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function normalizeHolding(row: Record<string, unknown>): Holding {
  return {
    stockCode: String(row.stock_code ?? row.stockCode ?? ''),
    stockName: String(row.stock_name ?? row.stockName ?? ''),
    industry: String(row.industry ?? '行业待补'),
    weight: numberOrNull(row.weight),
    quarters: Array.isArray(row.quarters) ? row.quarters.map(String) : undefined,
  }
}

function isMockLike(holdings: Holding[]) {
  if (holdings.length === 0) return false
  const mockNameCount = holdings.filter((holding) => mockStockNames.has(holding.stockName)).length
  const mockShare = mockNameCount / holdings.length
  const firstFiveAreCanonical = holdings
    .slice(0, 5)
    .every((holding) => mockStockNames.has(holding.stockName))
  return holdings.length >= 5 && mockShare >= 0.8 && firstFiveAreCanonical
}

function candidateQuarters() {
  const now = new Date()
  let year = now.getFullYear()
  let quarter = Math.floor(now.getMonth() / 3)
  if (quarter === 0) {
    year -= 1
    quarter = 4
  }
  const quarters: string[] = []
  for (let index = 0; index < 8; index += 1) {
    quarters.push(`${year}Q${quarter}`)
    quarter -= 1
    if (quarter === 0) {
      year -= 1
      quarter = 4
    }
  }
  return quarters
}

function summarizeIndustries(holdings: Holding[]) {
  const buckets = holdings.reduce((acc: Record<string, number>, holding) => {
    const key = holding.industry || '行业待补'
    acc[key] = (acc[key] || 0) + (holding.weight || 0)
    return acc
  }, {})
  return Object.entries(buckets)
    .sort((left, right) => right[1] - left[1])
    .map(([industry, weight]) => ({ industry, weight }))
}

async function fetchBackendHoldings(windCode: string, quarter: string): Promise<{ quarter: string; holdings: Holding[]; error: string | null }> {
  const response = await fetch(
    `${backendApiBaseUrl}/api/funds/${encodeURIComponent(windCode)}/holdings?quarter=${encodeURIComponent(quarter)}`,
    { cache: 'no-store' },
  )
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) return { quarter, holdings: [], error: payload.detail || payload.error || '读取失败' }
  const holdings = Array.isArray(payload.holdings)
    ? payload.holdings.map((row: Record<string, unknown>) => normalizeHolding(row)).filter((row: Holding) => row.stockCode || row.stockName)
    : []
  return { quarter, holdings, error: null }
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const { searchParams } = new URL(request.url)
    const requestedQuarter = searchParams.get('quarter')
    const quarters = requestedQuarter ? [requestedQuarter] : candidateQuarters()
    const checkedQuarters: string[] = []
    const rejectedMockLikeQuarters: string[] = []
    const errors: Array<{ quarter: string; error: string }> = []

    for (const quarter of quarters) {
      const result = await fetchBackendHoldings(id, quarter)
      checkedQuarters.push(quarter)
      if (result.error) {
        errors.push({ quarter, error: result.error })
        continue
      }
      if (isMockLike(result.holdings)) {
        rejectedMockLikeQuarters.push(quarter)
        continue
      }
      if (result.holdings.length > 0) {
        const totalWeight = result.holdings.reduce((sum, holding) => sum + (holding.weight || 0), 0)
        return NextResponse.json({
          status: 'available',
          windCode: id,
          quarter,
          holdings: result.holdings.sort((left, right) => (right.weight || 0) - (left.weight || 0)),
          industryBuckets: summarizeIndustries(result.holdings),
          totalWeight,
          checkedQuarters,
          rejectedMockLikeQuarters,
          source: 'backend.tushare.fund_portfolio.filtered',
          note: '仅展示通过 mock-like 过滤的持仓；研究复核仍需以基金季报/销售平台披露为准。',
        })
      }
    }

    return NextResponse.json({
      status: 'unavailable',
      windCode: id,
      holdings: [],
      industryBuckets: [],
      totalWeight: null,
      checkedQuarters,
      rejectedMockLikeQuarters,
      errors,
      source: 'backend.tushare.fund_portfolio.filtered',
      note: rejectedMockLikeQuarters.length
        ? '后端返回的持仓疑似 mock-like 样例，已拦截不展示；请接入可靠季报持仓后再做行业/个股暴露判断。'
        : '未取得可验证持仓，暂不做行业/个股暴露判断。',
    })
  } catch (error) {
    console.error('读取可信持仓失败:', error)
    return NextResponse.json({ error: '读取可信持仓失败' }, { status: 500 })
  }
}
