import { proxyGet, proxyPatch } from '@/lib/backend-proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyGet(`/api/portfolios/${encodeURIComponent(id)}`, request)
}

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyPatch(`/api/portfolios/${encodeURIComponent(id)}`, request)
}
