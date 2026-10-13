import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/funds/recommendation-coverage?limit=100`, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || '基金评价覆盖暂时不可用')
    return NextResponse.json(payload)
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '基金评价覆盖暂时不可用' },
      { status: 503 },
    )
  }
}
