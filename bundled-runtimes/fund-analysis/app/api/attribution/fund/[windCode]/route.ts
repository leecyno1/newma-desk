import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ windCode: string }> },
) {
  try {
    const { windCode } = await params
    const requestUrl = new URL(request.url)
    const query = new URLSearchParams()
    for (const key of ['benchmark', 'quarter', 'startDate', 'endDate']) {
      const value = requestUrl.searchParams.get(key)
      if (value) query.set(key, value)
    }
    const suffix = query.size ? `?${query.toString()}` : ''
    const response = await fetch(
      `${backendApiBaseUrl}/api/attribution/fund/${encodeURIComponent(windCode)}${suffix}`,
      { cache: 'no-store', signal: AbortSignal.timeout(120_000) },
    )
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '读取基金业绩归因失败' },
        { status: response.status },
      )
    }
    return NextResponse.json(payload)
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '读取基金业绩归因失败' },
      { status: 500 },
    )
  }
}
