import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET() {
  const [schedulerResult, pendingResult] = await Promise.allSettled([
    fetch(`${backendApiBaseUrl}/api/data-health/scheduler`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/data-health/pending-queue`, { cache: 'no-store' }),
  ])

  const scheduler = schedulerResult.status === 'fulfilled' && schedulerResult.value.ok
    ? await schedulerResult.value.json().catch(() => null)
    : null
  const pending = pendingResult.status === 'fulfilled' && pendingResult.value.ok
    ? await pendingResult.value.json().catch(() => null)
    : null

  const errors: string[] = []
  if (!scheduler) errors.push('scheduler_unavailable')
  if (!pending) errors.push('pending_queue_unavailable')

  return NextResponse.json({
    scheduler,
    pending,
    errors,
  })
}
