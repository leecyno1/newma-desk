import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export async function POST(request: Request, { params }: { params: Promise<{ folderId: string }> }) {
  const { folderId } = await params
  try {
    const requestUrl = new URL(request.url)
    const backendUrl = new URL(`/api/research-folders/${encodeURIComponent(folderId)}/scan`, backendApiBaseUrl)
    if (requestUrl.searchParams.get('retry_llm') === 'true') backendUrl.searchParams.set('retry_llm', 'true')
    const response = await fetch(backendUrl, {
      method: 'POST',
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(response.ok ? payload : { error: payload.detail || '扫描失败' }, { status: response.status })
  } catch {
    return NextResponse.json({ error: '扫描服务暂时不可用' }, { status: 503 })
  }
}
