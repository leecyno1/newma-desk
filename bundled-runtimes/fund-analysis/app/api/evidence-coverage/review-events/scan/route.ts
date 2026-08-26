import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export async function POST(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const maxMembersPerStatus = searchParams.get('maxMembersPerStatus') || '20'
    const includePeerMetrics = searchParams.get('includePeerMetrics') || 'false'
    const backendUrl = new URL('/api/alerts/scan', backendApiBaseUrl)
    backendUrl.searchParams.set('max_members_per_status', maxMembersPerStatus)
    backendUrl.searchParams.set('include_peer_metrics', includePeerMetrics)
    const response = await fetch(backendUrl, {
      method: 'POST',
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '触发复查扫描失败' },
        { status: response.status }
      )
    }

    return NextResponse.json({
      ...payload,
      createdCount: payload.createdCount ?? payload.created_count ?? payload.created ?? 0,
    })
  } catch (error) {
    console.error('触发复查扫描失败:', error)
    return NextResponse.json({ error: '触发复查扫描失败' }, { status: 500 })
  }
}
