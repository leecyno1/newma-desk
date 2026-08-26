import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

async function proxy(response: Response, fallback: string, status?: number) {
  const payload = await response.json().catch(() => ({}))
  return NextResponse.json(
    response.ok ? payload : { error: payload.detail || payload.error || fallback },
    { status: status || response.status },
  )
}

export async function GET() {
  try {
    return proxy(await fetch(`${backendApiBaseUrl}/api/watchlists`, { cache: 'no-store' }), '加载自选分组失败')
  } catch {
    return NextResponse.json({ error: '自选基金数据库暂时无法连接' }, { status: 503 })
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const response = await fetch(`${backendApiBaseUrl}/api/watchlists`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
    })
    return proxy(response, '创建自选分组失败', response.ok ? 201 : response.status)
  } catch {
    return NextResponse.json({ error: '创建自选分组失败' }, { status: 503 })
  }
}
