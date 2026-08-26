import { backendApiBaseUrl } from '@/lib/backend-api'
import FundCompanyBrowserClient, { type FundCompanySummary } from './FundCompanyBrowserClient'

export const dynamic = 'force-dynamic'

async function loadCompanies() {
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/fund-companies?page=1&page_size=30`, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || 'company database unavailable')
    return {
      companies: (Array.isArray(payload.companies) ? payload.companies : []) as FundCompanySummary[],
      summary: payload.summary || {},
      total: Number(payload.total || 0),
      error: '',
    }
  } catch {
    return { companies: [], summary: {}, total: 0, error: '基金公司数据库暂时无法连接，请先启动后端服务。' }
  }
}

export default async function FundCompaniesPage() {
  const data = await loadCompanies()
  return <FundCompanyBrowserClient initialCompanies={data.companies} initialSummary={data.summary} initialTotal={data.total} initialError={data.error} />
}
