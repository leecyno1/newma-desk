import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const response = await fetch(`${backendApiBaseUrl}/api/alerts?${searchParams.toString()}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '获取复查事件失败' },
        { status: response.status }
      )
    }

    return NextResponse.json(payload)
  } catch (error) {
    console.error('获取复查事件失败:', error)
    return NextResponse.json({ error: '获取复查事件失败' }, { status: 500 })
  }
}
