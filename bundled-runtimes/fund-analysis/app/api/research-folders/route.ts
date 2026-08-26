import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

async function payload(response: Response) {
  return response.json().catch(() => ({}))
}

export async function GET() {
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/research-folders/`, { cache: 'no-store' })
    const body = await payload(response)
    return NextResponse.json(response.ok ? body : { error: body.detail || '无法读取本地文件夹' }, { status: response.status })
  } catch {
    return NextResponse.json({ error: '本地文件夹服务暂时不可用' }, { status: 503 })
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const response = await fetch(`${backendApiBaseUrl}/api/research-folders/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const result = await payload(response)
    return NextResponse.json(response.ok ? result : { error: result.detail || '无法连接本地文件夹' }, { status: response.status })
  } catch {
    return NextResponse.json({ error: '无法连接本地文件夹' }, { status: 500 })
  }
}
