import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const response = await fetch(
      `${backendApiBaseUrl}/api/funds/${encodeURIComponent(id)}/manager-history/sync`,
      { method: 'POST', cache: 'no-store', signal: AbortSignal.timeout(60_000) },
    )
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(
      response.ok ? payload : { error: payload.detail || payload.error || '经理任职数据同步失败' },
      { status: response.status },
    )
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '经理任职数据同步失败' },
      { status: 503 },
    )
  }
}
