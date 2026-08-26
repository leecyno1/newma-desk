import { proxyGet } from '@/lib/backend-proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  return proxyGet('/api/portfolios/admission', request)
}
