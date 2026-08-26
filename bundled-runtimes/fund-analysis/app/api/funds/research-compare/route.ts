import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const response = await fetch(`${backendApiBaseUrl}/api/funds/compare-matrix`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        windCodes: Array.isArray(body.windCodes) ? body.windCodes : [],
        window: body.window || '1y',
      }),
      cache: 'no-store',
      signal: AbortSignal.timeout(120_000),
    })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(
      response.ok ? payload : { error: payload.detail || payload.error || '基金比较不可用' },
      { status: response.status },
    )
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '基金比较不可用' },
      { status: 503 },
    )
  }
}
