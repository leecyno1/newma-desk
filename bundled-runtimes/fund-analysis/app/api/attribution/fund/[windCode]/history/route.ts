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
    const limit = new URL(request.url).searchParams.get('limit') || '8'
    const response = await fetch(
      `${backendApiBaseUrl}/api/attribution/fund/${encodeURIComponent(windCode)}/history?limit=${encodeURIComponent(limit)}`,
      { cache: 'no-store', signal: AbortSignal.timeout(30_000) },
    )
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '读取归因历史失败' },
        { status: response.status },
      )
    }
    return NextResponse.json(payload)
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '读取归因历史失败' },
      { status: 500 },
    )
  }
}
