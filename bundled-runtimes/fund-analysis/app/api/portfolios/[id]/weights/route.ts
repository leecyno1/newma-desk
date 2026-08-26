import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = await request.json().catch(() => ({}))
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/portfolios/${encodeURIComponent(id)}/weights`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(payload, { status: response.status })
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message || 'backend unavailable' }, { status: 503 })
  }
}
