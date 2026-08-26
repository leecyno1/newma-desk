import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const requestUrl = new URL(request.url)
    const windowWeeks = requestUrl.searchParams.get('window_weeks') || '104'
    const response = await fetch(
      `${backendApiBaseUrl}/api/funds/${encodeURIComponent(id)}/bond-duration/calculate?window_weeks=${encodeURIComponent(windowWeeks)}`,
      { method: 'POST', cache: 'no-store', signal: AbortSignal.timeout(120_000) },
    )
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(
      response.ok ? payload : { error: payload.detail || payload.error || '债基久期现场测算失败' },
      { status: response.status },
    )
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '债基久期现场测算失败' },
      { status: 503 },
    )
  }
}
