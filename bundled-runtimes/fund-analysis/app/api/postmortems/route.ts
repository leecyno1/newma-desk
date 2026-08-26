import { proxyGet, proxyPost } from '@/lib/backend-proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  return proxyGet('/api/postmortems', request)
}

export async function POST(request: Request) {
  return proxyPost('/api/postmortems', request)
}
