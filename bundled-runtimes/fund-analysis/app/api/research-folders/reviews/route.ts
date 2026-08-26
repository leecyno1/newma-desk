import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const backendUrl = new URL('/api/research-folders/reviews', backendApiBaseUrl)
  const folderId = searchParams.get('folder_id')
  if (folderId) backendUrl.searchParams.set('folder_id', folderId)
  try {
    const response = await fetch(backendUrl, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(response.ok ? payload : { error: payload.detail || '无法读取待确认内容' }, { status: response.status })
  } catch {
    return NextResponse.json({ error: '待确认队列暂时不可用' }, { status: 503 })
  }
}
