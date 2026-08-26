import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type BackendManager = {
  manager_id?: string
  name?: string
  company?: string | null
  edu?: string | null
  education?: string | null
  tenure_years?: number | null
  work_years?: number | null
  fund_count?: number | null
  avg_score?: number | null
  funds?: Array<{ wind_code?: string; fund_name?: string; start_date?: string | null; end_date?: string | null }>
}

function toManager(manager: BackendManager) {
  const funds = Array.isArray(manager.funds) ? manager.funds : []
  const fundCodes = funds.map((fund) => fund.wind_code).filter((code): code is string => Boolean(code))
  const currentFundCodes = funds
    .filter((fund) => !fund.end_date)
    .map((fund) => fund.wind_code)
    .filter((code): code is string => Boolean(code))
  return {
    id: manager.manager_id || manager.name || '',
    windCode: manager.manager_id || null,
    name: manager.name || manager.manager_id || '姓名待补',
    company: manager.company || null,
    education: manager.education || manager.edu || null,
    workYears: manager.work_years ?? null,
    managementYears: manager.tenure_years ?? null,
    currentFunds: Array.from(new Set(currentFundCodes)),
    fundCount: manager.fund_count ?? fundCodes.length,
    avgScore: manager.avg_score ?? null,
    funds,
    source: 'backend.tushare.fund_manager',
  }
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const page = Math.max(1, Number(searchParams.get('page') || 1))
    const limit = Math.max(1, Math.min(100, Number(searchParams.get('limit') || 20)))
    const backendParams = new URLSearchParams({
      page: String(page),
      page_size: String(limit),
    })
    const search = searchParams.get('search')
    const company = searchParams.get('company')
    if (search) backendParams.set('keyword', search)
    if (company) backendParams.set('company', company)

    const response = await fetch(`${backendApiBaseUrl}/api/managers/?${backendParams.toString()}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '获取基金经理列表失败' },
        { status: response.status },
      )
    }

    const total = Number(payload.total || 0)
    return NextResponse.json({
      data: ((payload.managers || []) as BackendManager[]).map(toManager),
      pagination: {
        page: Number(payload.page || page),
        limit: Number(payload.page_size || limit),
        total,
        totalPages: Math.max(1, Math.ceil(total / limit)),
      },
      source: payload.source || 'backend.tushare.fund_manager',
    })
  } catch (error) {
    console.error('获取基金经理列表失败:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '获取基金经理列表失败' },
      { status: 500 },
    )
  }
}

export async function POST() {
  return NextResponse.json(
    { error: '基金经理来自本地 Tushare 同步数据，暂不支持前端手工创建。' },
    { status: 405 },
  )
}
