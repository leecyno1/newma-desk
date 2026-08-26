import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type Params = { params: Promise<{ reportId: string; proposalId: string }> }

export async function PATCH(request: Request, { params }: Params) {
  const { reportId, proposalId } = await params
  const body = await request.json().catch(() => ({}))
  if (!body.action || !['confirmed', 'rejected'].includes(body.action)) {
    return NextResponse.json({ error: 'action must be confirmed or rejected' }, { status: 400 })
  }
  try {
    const response = await fetch(
      `${backendApiBaseUrl}/api/research-folders/reviews/${encodeURIComponent(reportId)}/${encodeURIComponent(proposalId)}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: body.action }),
      },
    )
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      return NextResponse.json({ error: payload.detail || 'review failed' }, { status: response.status })
    }
    return NextResponse.json(payload)
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message || 'network error' }, { status: 503 })
  }
}
