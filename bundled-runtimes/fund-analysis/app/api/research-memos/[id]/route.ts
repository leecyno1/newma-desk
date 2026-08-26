import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/research-reports/${encodeURIComponent(id)}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || '调研纪要不存在')
    return NextResponse.json(payload)
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '无法读取调研纪要' },
      { status: 404 },
    )
  }
}
