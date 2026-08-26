import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const requestUrl = new URL(request.url)
  const window = requestUrl.searchParams.get('window') || '1y'
  try {
    const response = await fetch(
      `${backendApiBaseUrl}/api/funds/${encodeURIComponent(id)}/evaluation-statistics?window=${encodeURIComponent(window)}`,
      {
        cache: 'no-store',
        signal: AbortSignal.timeout(120_000),
      },
    )
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(
      response.ok ? payload : { error: payload.detail || payload.error || '同类评分统计不可用' },
      { status: response.status },
    )
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '同类评分统计不可用' },
      { status: 503 },
    )
  }
}
