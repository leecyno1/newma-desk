import { proxyGet, proxyPatch, proxyDelete } from '@/lib/backend-proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type Params = { params: Promise<{ id: string }> }

export async function GET(_request: Request, { params }: Params) {
  const { id } = await params
  return proxyGet(`/api/research-queue/${encodeURIComponent(id)}`, _request)
}

export async function PATCH(request: Request, { params }: Params) {
  const { id } = await params
  return proxyPatch(`/api/research-queue/${encodeURIComponent(id)}`, request)
}

export async function DELETE(_request: Request, { params }: Params) {
  const { id } = await params
  return proxyDelete(`/api/research-queue/${encodeURIComponent(id)}`)
}
