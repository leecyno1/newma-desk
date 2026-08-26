import { backendApiBaseUrl } from '@/lib/backend-api'
import EvaluationWorkspace from './EvaluationWorkspace'

export const dynamic = 'force-dynamic'

async function loadRecentHistory() {
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/funds/evaluation-history/recent?limit=30`, { cache: 'no-store' })
    if (!response.ok) return []
    const payload = await response.json()
    return Array.isArray(payload.items) ? payload.items : []
  } catch {
    return []
  }
}

export default async function EvaluationPage() {
  return <EvaluationWorkspace initialRecentHistory={await loadRecentHistory()} />
}
