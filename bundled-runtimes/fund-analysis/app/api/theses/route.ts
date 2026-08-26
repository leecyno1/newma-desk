import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const url = new URL(request.url)
  const search = url.searchParams.toString()
  const suffix = search ? `?${search}` : ''
  const response = await fetch(`${backendApiBaseUrl}/api/theses${suffix}`, { cache: 'no-store' })
  const payload = await response.json().catch(() => ({}))
  return NextResponse.json(payload, { status: response.status })
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}))
  const response = await fetch(`${backendApiBaseUrl}/api/theses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = await response.json().catch(() => ({}))
  return NextResponse.json(payload, { status: response.status })
}
