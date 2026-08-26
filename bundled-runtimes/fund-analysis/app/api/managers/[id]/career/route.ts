import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const search = new URL(request.url).searchParams
    const query = new URLSearchParams()
    for (const key of ['fund_code', 'tenure_start_date', 'period', 'start_date', 'end_date']) {
      const value = search.get(key)
      if (value) query.set(key, value)
    }
    const suffix = query.size ? `?${query.toString()}` : ''
    const response = await fetch(
      `${backendApiBaseUrl}/api/managers/${encodeURIComponent(id)}/career${suffix}`,
      { cache: 'no-store' },
    )
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(payload, { status: response.status })
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '获取基金经理生涯曲线失败' },
      { status: 500 },
    )
  }
}
