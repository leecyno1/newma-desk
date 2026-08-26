import { backendApiBaseUrl, toCamelFund } from '@/lib/backend-api'
import RecommendationClient from './RecommendationClient'

export const dynamic = 'force-dynamic'

async function loadRecommendationUniverse() {
  try {
    const [fundResponse, categoryResponse] = await Promise.all([
      fetch(`${backendApiBaseUrl}/api/fund-browser?page=1&page_size=30`, { cache: 'no-store' }),
      fetch(`${backendApiBaseUrl}/api/funds/recommendation-categories?limit=100`, { cache: 'no-store' }),
    ])
    if (!fundResponse.ok || !categoryResponse.ok) throw new Error('fund database unavailable')
    const payload = await fundResponse.json()
    const categoryPayload = await categoryResponse.json()
    const readyCategories = (Array.isArray(categoryPayload.categories) ? categoryPayload.categories : [])
      .filter((item: Record<string, unknown>) => (
        Number(item.evaluated_fund_count || 0) >= Math.max(1, Number(item.minimum_peer_count || 1))
      ))
    return {
      funds: (payload.funds || []).map(toCamelFund),
      categories: readyCategories.map((item: Record<string, unknown>) => String(item.name || '')).filter(Boolean),
      readyCategoryCount: readyCategories.length,
      total: Number(payload.total || 0),
      error: '',
    }
  } catch {
    return {
      funds: [],
      categories: [],
      readyCategoryCount: 0,
      total: 0,
      error: '基金数据库暂时无法连接，无法生成候选组。',
    }
  }
}

export default async function RecommendationsPage({ searchParams }: { searchParams: Promise<{ category?: string | string[] }> }) {
  const categoryParam = (await searchParams).category
  const initialCategory = (Array.isArray(categoryParam) ? categoryParam[0] || '' : categoryParam || '').trim()
  const data = await loadRecommendationUniverse()
  return <RecommendationClient initialFunds={data.funds} initialCategories={data.categories} universeTotal={data.total} initialReadyCategoryCount={data.readyCategoryCount} initialError={data.error} initialCategory={initialCategory} />
}
