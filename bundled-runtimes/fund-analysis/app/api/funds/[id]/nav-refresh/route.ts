import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export async function POST(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/data-sync/funds/${encodeURIComponent(id)}/nav-refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lookback_days: 30 }),
      cache: 'no-store',
      signal: AbortSignal.timeout(30_000),
    })
    const data = await response.json()
    return NextResponse.json(data, { status: response.status })
  } catch {
    // 请求中断时不能判断后端事务结果，允许先刷新页面核对。
    return NextResponse.json({ detail: '暂未收到更新结果，请刷新页面核对净值日期。' }, { status: 502 })
  }
}
