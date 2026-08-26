import { NextResponse } from 'next/server'
import { backendApiBaseUrl, toSnakePool } from '@/lib/backend-api'

export async function GET() {
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/fund-pools`, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '加载研究清单失败' },
        { status: response.status }
      )
    }

    return NextResponse.json({
      ...payload,
      pools: (payload.pools || []).map(toSnakePool),
    })
  } catch (error) {
    console.error('加载研究清单失败:', error)
    return NextResponse.json({ error: '加载研究清单失败' }, { status: 500 })
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const response = await fetch(`${backendApiBaseUrl}/api/fund-pools`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '创建研究清单失败' },
        { status: response.status }
      )
    }

    return NextResponse.json(toSnakePool(payload), { status: 201 })
  } catch (error) {
    console.error('创建研究清单失败:', error)
    return NextResponse.json({ error: '创建研究清单失败' }, { status: 500 })
  }
}
