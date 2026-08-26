import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ company: string }> },
) {
  const { company } = await params
  try {
    const response = await fetch(
      `${backendApiBaseUrl}/api/fund-companies/${encodeURIComponent(company)}`,
      { cache: 'no-store' },
    )
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(
      response.ok ? payload : { error: payload.detail || payload.error || '基金公司不存在' },
      { status: response.status },
    )
  } catch {
    return NextResponse.json({ error: '基金公司数据库暂时无法连接' }, { status: 503 })
  }
}
