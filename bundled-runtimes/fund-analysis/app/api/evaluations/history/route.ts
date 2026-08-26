import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const requestUrl = new URL(request.url)
  const query = new URLSearchParams()
  for (const key of ['window', 'status', 'limit']) {
    const value = requestUrl.searchParams.get(key)
    if (value) query.set(key, value)
  }

  try {
    const response = await fetch(
      `${backendApiBaseUrl}/api/funds/evaluation-history/recent?${query.toString()}`,
      { cache: 'no-store', signal: AbortSignal.timeout(120_000) },
    )
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(
      response.ok ? payload : { error: payload.detail || payload.error || '最近评价结果不可用' },
      { status: response.status },
    )
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '最近评价结果不可用' },
      { status: 503 },
    )
  }
}
