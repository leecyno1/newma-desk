import { NextResponse } from 'next/server'
import suite from '@/desk/suite.json'

export const dynamic = 'force-static'

export function GET() {
  return NextResponse.json(suite, {
    headers: {
      'Cache-Control': 'public, max-age=300, stale-while-revalidate=3600',
    },
  })
}
