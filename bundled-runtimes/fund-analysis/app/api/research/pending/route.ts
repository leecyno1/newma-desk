import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const url = new URL(request.url)
  const folderId = url.searchParams.get('folder_id') || ''
  const suffix = folderId ? `?folder_id=${encodeURIComponent(folderId)}` : ''
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/research-folders/reviews${suffix}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      return NextResponse.json({ error: payload.detail || 'pending queue unavailable' }, { status: response.status })
    }
    return NextResponse.json(payload)
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message || 'network error' }, { status: 503 })
  }
}
