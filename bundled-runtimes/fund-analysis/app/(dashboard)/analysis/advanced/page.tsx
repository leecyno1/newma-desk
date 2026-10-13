import { backendApiBaseUrl } from '@/lib/backend-api'
import AttributionWorkspace from './AttributionWorkspace'

function latestCompletedQuarter() {
  const now = new Date()
  const currentQuarter = Math.floor(now.getMonth() / 3) + 1
  return currentQuarter === 1 ? `${now.getFullYear() - 1}Q4` : `${now.getFullYear()}Q${currentQuarter - 1}`
}

export default async function PerformanceAttributionPage({
  searchParams,
}: {
  searchParams: Promise<{ fundCode?: string; benchmark?: string; quarter?: string; run?: string }>
}) {
  const query = await searchParams
  const fundCode = query.fundCode || '000051.OF'
  let initialHistory: Record<string, unknown>[] = []
  let initialHistoryError = ''
  try {
    const response = await fetch(
      `${backendApiBaseUrl}/api/attribution/fund/${encodeURIComponent(fundCode)}/history?limit=8`,
      { cache: 'no-store', signal: AbortSignal.timeout(30_000) },
    )
    if (!response.ok) throw new Error('读取归因历史失败，请重试')
    const payload = await response.json()
    initialHistory = Array.isArray(payload.history) ? payload.history : []
  } catch {
    initialHistoryError = '归因历史暂时不可用，不能据此判断没有历史记录'
  }
  return (
    <AttributionWorkspace
      initialFundCode={fundCode}
      initialBenchmark={query.benchmark || ''}
      initialQuarter={query.quarter || latestCompletedQuarter()}
      initialHistory={initialHistory}
      initialHistoryError={initialHistoryError}
      autoRun={query.run === '1'}
    />
  )
}
