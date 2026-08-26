import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

function backendUrl(id: string, requestUrl: string) {
  const request = new URL(requestUrl)
  const query = new URLSearchParams()
  const window = request.searchParams.get('window')
  const limit = request.searchParams.get('limit')
  if (window) query.set('window', window)
  if (limit) query.set('limit', limit)
  const suffix = query.size ? `?${query.toString()}` : ''
  return `${backendApiBaseUrl}/api/funds/${encodeURIComponent(id)}/evaluation-history${suffix}`
}

async function proxy(request: Request, id: string, method: 'GET' | 'POST') {
  try {
    const response = await fetch(backendUrl(id, request.url), {
      method,
      cache: 'no-store',
      signal: AbortSignal.timeout(120_000),
    })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(
      response.ok ? payload : { error: payload.detail || payload.error || '评分历史不可用' },
      { status: response.status },
    )
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '评分历史不可用' },
      { status: 503 },
    )
  }
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  return proxy(request, id, 'GET')
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  return proxy(request, id, 'POST')
}
