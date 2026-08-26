import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const url = new URL(request.url)
  const backendUrl = new URL('/api/managers/browser', backendApiBaseUrl)
  for (const key of ['keyword', 'category', 'evidence', 'page', 'page_size']) {
    const value = url.searchParams.get(key)
    if (value) backendUrl.searchParams.set(key, value)
  }
  const search = url.searchParams.get('search')
  const limit = url.searchParams.get('limit')
  if (search) backendUrl.searchParams.set('keyword', search)
  if (limit) backendUrl.searchParams.set('page_size', limit)

  try {
    const response = await fetch(backendUrl, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(
      response.ok ? payload : { error: payload.detail || payload.error || '基金经理数据库不可用' },
      { status: response.status },
    )
  } catch {
    return NextResponse.json({ error: '基金经理数据库暂时无法连接' }, { status: 503 })
  }
}
