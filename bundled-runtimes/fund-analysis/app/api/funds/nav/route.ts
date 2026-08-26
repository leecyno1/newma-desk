import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const fundCode = searchParams.get('fundCode')
    const startDate = searchParams.get('startDate')
    const endDate = searchParams.get('endDate')

    if (!fundCode) {
      return NextResponse.json(
        { error: '请提供基金代码' },
        { status: 400 }
      )
    }

    const backendUrl = new URL(`/api/funds/${encodeURIComponent(fundCode)}/nav`, backendApiBaseUrl)
    if (startDate) backendUrl.searchParams.set('start_date', startDate)
    if (endDate) backendUrl.searchParams.set('end_date', endDate)

    const response = await fetch(backendUrl, {
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || data.error || '真实净值数据读取失败' },
        { status: response.status },
      )
    }
    return NextResponse.json({ ...data, isMock: false, source: 'backend.tushare.fund_nav' })
  } catch (error) {
    console.error('获取净值数据失败:', error)
    return NextResponse.json(
      { error: '获取净值数据失败' },
      { status: 500 }
    )
  }
}
