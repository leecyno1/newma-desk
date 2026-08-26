import { proxyPost } from '@/lib/backend-proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyPost(`/api/portfolios/${encodeURIComponent(id)}/trade-list`, request)
}
