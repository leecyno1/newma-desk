import { proxyGet } from '@/lib/backend-proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type Params = { params: Promise<{ code: string }> }

export async function GET(_request: Request, { params }: Params) {
  const { code } = await params
  return proxyGet(`/api/decision-support/counter-evidence/${encodeURIComponent(code)}`, _request)
}
