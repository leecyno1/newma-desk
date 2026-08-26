import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const search = new URL(request.url).searchParams
  const backendUrl = new URL('/api/managers/compare', backendApiBaseUrl)
  for (const managerId of search.getAll('manager_id')) backendUrl.searchParams.append('manager_id', managerId)
  for (const productCode of search.getAll('product_code')) backendUrl.searchParams.append('product_code', productCode)
  const category = search.get('category')
  if (category) backendUrl.searchParams.set('category', category)
  try {
    const response = await fetch(backendUrl, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    return NextResponse.json(payload, { status: response.status })
  } catch {
    return NextResponse.json({ error: '基金经理对比服务暂时无法连接' }, { status: 503 })
  }
}
