import { NextResponse } from 'next/server'
import { backendApiBaseUrl, toCamelFund } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/watchlists/${encodeURIComponent(id)}/members`, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      return NextResponse.json({ error: payload.detail || payload.error || '加载自选基金失败' }, { status: response.status })
    }
    return NextResponse.json({
      ...payload,
      members: (payload.members || []).map((member: Record<string, unknown>) => ({
        ...toCamelFund(member),
        memberId: String(member.member_id || ''),
        poolId: String(member.pool_id || ''),
        status: String(member.status || 'watch'),
        reason: String(member.reason || ''),
        latestConclusion: String(member.latest_conclusion || ''),
        riskNotes: String(member.risk_notes || ''),
        nextReviewDate: member.next_review_date || null,
        memberCreatedAt: member.member_created_at || null,
        memberUpdatedAt: member.member_updated_at || null,
      })),
    })
  } catch {
    return NextResponse.json({ error: '自选基金数据库暂时无法连接' }, { status: 503 })
  }
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  try {
    const body = await request.json()
    const response = await fetch(`${backendApiBaseUrl}/api/watchlists/${encodeURIComponent(id)}/members`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(
      response.ok ? payload : { error: payload.detail || payload.error || '加入自选失败' },
      { status: response.ok ? 201 : response.status },
    )
  } catch {
    return NextResponse.json({ error: '加入自选失败' }, { status: 503 })
  }
}
