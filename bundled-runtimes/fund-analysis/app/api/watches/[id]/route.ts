import { proxyPatch, proxyDelete } from '@/lib/backend-proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type Params = { params: Promise<{ id: string }> }

export async function PATCH(request: Request, { params }: Params) {
  const { id } = await params
  return proxyPatch(`/api/watches/${encodeURIComponent(id)}`, request)
}

export async function DELETE(_request: Request, { params }: Params) {
  const { id } = await params
  return proxyDelete(`/api/watches/${encodeURIComponent(id)}`)
}
