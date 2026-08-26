import { backendApiBaseUrl, toCamelFund } from '@/lib/backend-api'
import FundDiscoverClient from './FundDiscoverClient'

export const dynamic = 'force-dynamic'

type FundAvailability = 'evaluated' | 'classified' | 'all'

async function loadFunds(peerGroup = '', search = '', availability: FundAvailability = 'evaluated') {
  try {
    const fundUrl = new URL('/api/fund-browser', backendApiBaseUrl)
    fundUrl.searchParams.set('page', '1')
    fundUrl.searchParams.set('page_size', '30')
    fundUrl.searchParams.set('availability', availability)
    if (peerGroup) {
      fundUrl.searchParams.set('peer_group', peerGroup)
      fundUrl.searchParams.set('sort_by', 'multi_period')
    }
    if (search) fundUrl.searchParams.set('keyword', search)
    const [fundResponse, categoryResponse] = await Promise.all([
      fetch(fundUrl, { cache: 'no-store' }),
      fetch(`${backendApiBaseUrl}/api/funds/recommendation-categories?limit=100`, { cache: 'no-store' }),
    ])
    if (!fundResponse.ok || !categoryResponse.ok) throw new Error('fund database unavailable')
    const payload = await fundResponse.json()
    const categoryPayload = await categoryResponse.json()
    return {
      funds: (payload.funds || []).map(toCamelFund),
      categories: (categoryPayload.categories || []).map((item: Record<string, unknown>) => ({
        id: String(item.id || item.key || item.name || ''),
        key: String(item.key || item.id || item.name || ''),
        name: String(item.name || ''),
        count: Number(item.fund_count || 0),
        evaluatedCount: Number(item.evaluated_fund_count || 0),
        pendingCount: Number(item.evaluation_pending_count || 0),
        evaluationCoverage: Number(item.evaluation_coverage || 0),
        evaluationAsOfDate: item.evaluation_as_of_date ? String(item.evaluation_as_of_date) : null,
        assetClass: item.asset_class ? String(item.asset_class) : null,
        activePassive: item.active_passive ? String(item.active_passive) : null,
        benchmarkCode: item.benchmark_code ? String(item.benchmark_code) : null,
        benchmarkName: item.benchmark_name ? String(item.benchmark_name) : null,
        strategyFamilyKey: item.strategy_family_key ? String(item.strategy_family_key) : null,
        strategyFamilyName: item.strategy_family_name ? String(item.strategy_family_name) : null,
        contractDimensions: (() => {
          const dimensions = item.contract_dimensions
          if (!dimensions || typeof dimensions !== 'object' || Array.isArray(dimensions)) return null
          const source = dimensions as Record<string, unknown>
          const baseIndex = String(source.base_index || source.baseIndex || '')
          const priceReturn = String(source.price_return || source.priceReturn || '')
          const tenor = String(source.tenor || '')
          return baseIndex && priceReturn && tenor ? { baseIndex, priceReturn, tenor } : null
        })(),
      })).filter((item: { id: string; name: string; count: number }) => item.id && item.name && item.count > 0),
      total: Number(payload.total || 0),
      source: String(payload.source || 'fund_database'),
      availability: String(payload.availability || availability) as FundAvailability,
      selectionContext: payload.selection_context && typeof payload.selection_context === 'object' ? payload.selection_context as Record<string, unknown> : {},
      styleTagCatalog: payload.style_tag_catalog && typeof payload.style_tag_catalog === 'object' ? payload.style_tag_catalog as Record<string, unknown> : {},
      error: '',
    }
  } catch {
    return {
      funds: [],
      categories: [],
      total: 0,
      source: 'unavailable',
      availability,
      selectionContext: {},
      styleTagCatalog: {},
      error: '基金数据库暂时无法连接，请先启动后端服务。',
    }
  }
}

export default async function DiscoverPage({ searchParams }: { searchParams: Promise<{ peerGroup?: string | string[]; search?: string | string[]; availability?: string | string[] }> }) {
  const params = await searchParams
  const peerGroupParam = params.peerGroup
  const peerGroup = Array.isArray(peerGroupParam) ? peerGroupParam[0] || '' : peerGroupParam || ''
  const searchParam = params.search
  const search = (Array.isArray(searchParam) ? searchParam[0] || '' : searchParam || '').trim()
  const availabilityParam = Array.isArray(params.availability) ? params.availability[0] : params.availability
  const availability: FundAvailability = availabilityParam === 'classified' || availabilityParam === 'all' ? availabilityParam : 'evaluated'
  const data = await loadFunds(peerGroup, search, availability)
  return <FundDiscoverClient initialFunds={data.funds} initialCategories={data.categories} initialTotal={data.total} initialSource={data.source} initialError={data.error} initialPeerGroup={peerGroup} initialSearch={search} initialAvailability={data.availability} initialSelectionContext={data.selectionContext} initialStyleTagCatalog={data.styleTagCatalog} />
}
