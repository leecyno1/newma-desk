import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const response = await fetch(`${backendApiBaseUrl}/api/research-folders/reviews/confirm-labels`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(response.ok ? payload : { error: payload.detail || '批量确认失败' }, { status: response.status })
  } catch {
    return NextResponse.json({ error: '批量确认失败' }, { status: 500 })
  }
}
