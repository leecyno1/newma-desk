import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ reportId: string; proposalId: string }> },
) {
  const { reportId, proposalId } = await params
  try {
    const body = await request.json()
    const response = await fetch(
      `${backendApiBaseUrl}/api/research-folders/reviews/${encodeURIComponent(reportId)}/${encodeURIComponent(proposalId)}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    )
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(response.ok ? payload : { error: payload.detail || '无法保存复核结果' }, { status: response.status })
  } catch {
    return NextResponse.json({ error: '无法保存复核结果' }, { status: 500 })
  }
}
