import { proxyPut } from '@/lib/backend-proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyPut(`/api/portfolios/${encodeURIComponent(id)}/targets`, request)
}
