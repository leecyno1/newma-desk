import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/reports/ai-health`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(5_000),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      return NextResponse.json(
        { status: 'degraded', configured: false, error: payload.detail || '模型状态读取失败' },
        { status: response.status },
      )
    }
    return NextResponse.json(payload)
  } catch (error) {
    return NextResponse.json({
      status: 'degraded',
      configured: false,
      error: error instanceof Error ? error.message : '模型状态读取失败',
    })
  }
}
