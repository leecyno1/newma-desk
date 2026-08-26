import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ memberId: string }> },
) {
  const { memberId } = await params
  try {
    const body = await request.json()
    const response = await fetch(`${backendApiBaseUrl}/api/watchlists/members/${encodeURIComponent(memberId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(response.ok ? payload : { error: payload.detail || payload.error || '更新备注失败' }, { status: response.status })
  } catch {
    return NextResponse.json({ error: '更新备注失败' }, { status: 503 })
  }
}

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ memberId: string }> },
) {
  const { memberId } = await params
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/watchlists/members/${encodeURIComponent(memberId)}`, {
      method: 'DELETE',
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(response.ok ? payload : { error: payload.detail || payload.error || '移出自选失败' }, { status: response.status })
  } catch {
    return NextResponse.json({ error: '移出自选失败' }, { status: 503 })
  }
}
