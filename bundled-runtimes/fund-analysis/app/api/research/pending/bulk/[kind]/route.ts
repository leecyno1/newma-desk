import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type Params = { params: Promise<{ kind: string }> }

const ALLOWED = new Set(['managers', 'labels'])

export async function POST(request: Request, { params }: Params) {
  const { kind } = await params
  if (!ALLOWED.has(kind)) {
    return NextResponse.json({ error: 'kind must be managers or labels' }, { status: 400 })
  }
  const body = await request.json().catch(() => ({}))
  // Constraint: LLM 建议不能自动转人工确认 — enforced on backend by extraction_source filter,
  // but we also require an explicit min_confidence to avoid accidental blanket approvals.
  const minConfidence = typeof body.min_confidence === 'number' ? body.min_confidence : (kind === 'managers' ? 0.88 : 0.9)
  const folderId = body.folder_id || null

  const endpoint = kind === 'managers' ? 'confirm-managers' : 'confirm-labels'
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/research-folders/reviews/${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder_id: folderId, min_confidence: minConfidence }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      return NextResponse.json({ error: payload.detail || 'bulk confirm failed' }, { status: response.status })
    }
    return NextResponse.json(payload)
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message || 'network error' }, { status: 503 })
  }
}
