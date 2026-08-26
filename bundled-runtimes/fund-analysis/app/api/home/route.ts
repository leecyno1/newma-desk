import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/home`, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(
      response.ok ? payload : { error: payload.detail || payload.error || '选基首页数据不可用' },
      { status: response.status },
    )
  } catch {
    return NextResponse.json({ error: '选基首页数据暂时无法连接' }, { status: 503 })
  }
}
