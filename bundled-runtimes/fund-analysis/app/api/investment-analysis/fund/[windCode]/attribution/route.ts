import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ windCode: string }> }
) {
  try {
    const { windCode } = await params
    const url = new URL(request.url)
    const backendParams = new URLSearchParams()
    for (const key of ['benchmark', 'startDate', 'endDate']) {
      const value = url.searchParams.get(key)
      if (value) backendParams.set(key, value)
    }
    const suffix = backendParams.toString() ? `?${backendParams.toString()}` : ''
    const response = await fetch(
      `${backendApiBaseUrl}/api/investment-analysis/fund/${encodeURIComponent(windCode)}/attribution${suffix}`,
      { cache: 'no-store' }
    )
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '读取主动归因失败' },
        { status: response.status }
      )
    }
    return NextResponse.json(payload)
  } catch (error) {
    console.error('读取主动归因失败:', error)
    return NextResponse.json({ error: '读取主动归因失败' }, { status: 500 })
  }
}
