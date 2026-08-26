import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const url = new URL(request.url)
  const requestedLimit = Number(url.searchParams.get('limit') || '50')
  const pageSize = Number.isFinite(requestedLimit) ? Math.min(50, Math.max(1, Math.trunc(requestedLimit))) : 50
  const backendParams = new URLSearchParams({
    page: url.searchParams.get('page') || '1',
    page_size: String(pageSize),
  })
  for (const key of ['keyword', 'manager_id', 'fund_id', 'folder_id', 'tags', 'viewpoint_topics', 'research_domain', 'start_date', 'end_date']) {
    const value = url.searchParams.get(key)
    if (value) backendParams.set(key, value)
  }

  try {
    const response = await fetch(`${backendApiBaseUrl}/api/research-reports/?${backendParams.toString()}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = Array.isArray(payload.detail)
        ? payload.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join('；')
        : payload.detail
      throw new Error(typeof detail === 'string' ? detail : '调研纪要库不可用')
    }
    return NextResponse.json(payload)
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '无法读取调研纪要' },
      { status: 503 },
    )
  }
}
