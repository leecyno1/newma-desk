import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ eventId: string }> }
) {
  try {
    const { eventId } = await params
    const body = await request.json()
    if (!['open', 'acknowledged', 'resolved'].includes(body?.status)) {
      return NextResponse.json({ error: '事件状态只能为待处理、已知悉或已解决' }, { status: 400 })
    }
    const response = await fetch(`${backendApiBaseUrl}/api/alerts/events/${encodeURIComponent(eventId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: body.status }),
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '更新复查事件失败' },
        { status: response.status }
      )
    }

    return NextResponse.json(payload)
  } catch (error) {
    console.error('更新复查事件失败:', error)
    return NextResponse.json({ error: '更新复查事件失败' }, { status: 500 })
  }
}
