import FundAnalysisWorkspace from './FundAnalysisWorkspace'
import { backendApiBaseUrl, toCamelFund } from '@/lib/backend-api'

export const dynamic = 'force-dynamic'

export default async function AnalysisPage({ searchParams }: { searchParams: Promise<{ fundCode?: string }> }) {
  const { fundCode = '' } = await searchParams
  let initialFund = null
  if (fundCode) {
    try {
      const response = await fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(fundCode)}`, { cache: 'no-store' })
      if (response.ok) {
        const payload = await response.json().catch(() => ({}))
        const fund = toCamelFund(payload.fund || payload)
        initialFund = {
          windCode: fund.windCode,
          name: fund.name || fund.windCode,
          type: fund.type,
          managers: Array.isArray(fund.managers) ? fund.managers : [],
        }
      }
    } catch {
      initialFund = null
    }
  }
  return <FundAnalysisWorkspace initialFund={initialFund} />
}
