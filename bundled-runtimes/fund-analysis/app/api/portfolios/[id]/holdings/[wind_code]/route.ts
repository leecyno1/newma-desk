import { proxyDelete } from '@/lib/backend-proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string; wind_code: string }> }) {
  const { id, wind_code } = await params
  return proxyDelete(`/api/portfolios/${encodeURIComponent(id)}/holdings/${encodeURIComponent(wind_code)}`)
}
