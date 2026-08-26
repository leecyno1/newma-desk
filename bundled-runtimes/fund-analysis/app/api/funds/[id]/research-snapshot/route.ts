import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const requestUrl = new URL(request.url)
    const query = new URLSearchParams()
    for (const key of ['window', 'include_research', 'include_attribution', 'live_attribution']) {
      const value = requestUrl.searchParams.get(key)
      if (value) query.set(key, value)
    }
    const suffix = query.size ? `?${query.toString()}` : ''
    const response = await fetch(
      `${backendApiBaseUrl}/api/funds/${encodeURIComponent(id)}/research-snapshot${suffix}`,
      { cache: 'no-store', signal: AbortSignal.timeout(120_000) },
    )
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(
      response.ok ? payload : { error: payload.detail || payload.error || '基金研究快照不可用' },
      { status: response.status },
    )
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '基金研究快照不可用' },
      { status: 503 },
    )
  }
}
