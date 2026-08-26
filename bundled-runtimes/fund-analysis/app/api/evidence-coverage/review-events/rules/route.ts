import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const response = await fetch(`${backendApiBaseUrl}/api/alerts/rules?${searchParams.toString()}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '获取复查规则失败' },
        { status: response.status }
      )
    }

    return NextResponse.json(payload)
  } catch (error) {
    console.error('获取复查规则失败:', error)
    return NextResponse.json({ error: '获取复查规则失败' }, { status: 500 })
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const response = await fetch(`${backendApiBaseUrl}/api/alerts/rules`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '创建复查规则失败' },
        { status: response.status }
      )
    }

    return NextResponse.json(payload, { status: 201 })
  } catch (error) {
    console.error('创建复查规则失败:', error)
    return NextResponse.json({ error: '创建复查规则失败' }, { status: 500 })
  }
}
