import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ ruleId: string }> }
) {
  try {
    const { ruleId } = await params
    const body = await request.json()
    const response = await fetch(`${backendApiBaseUrl}/api/alerts/rules/${encodeURIComponent(ruleId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '更新复查规则失败' },
        { status: response.status }
      )
    }

    return NextResponse.json(payload)
  } catch (error) {
    console.error('更新复查规则失败:', error)
    return NextResponse.json({ error: '更新复查规则失败' }, { status: 500 })
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ ruleId: string }> }
) {
  try {
    const { ruleId } = await params
    const response = await fetch(`${backendApiBaseUrl}/api/alerts/rules/${encodeURIComponent(ruleId)}`, {
      method: 'DELETE',
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '删除复查规则失败' },
        { status: response.status }
      )
    }

    return NextResponse.json(payload)
  } catch (error) {
    console.error('删除复查规则失败:', error)
    return NextResponse.json({ error: '删除复查规则失败' }, { status: 500 })
  }
}
