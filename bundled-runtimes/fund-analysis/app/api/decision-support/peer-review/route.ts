import { proxyPost } from '@/lib/backend-proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(request: Request) {
  return proxyPost('/api/decision-support/peer-review', request)
}
