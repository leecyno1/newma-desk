import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export function GET() {
  return NextResponse.json({
    ok: true,
    service: 'fund-analysis-data',
    product: 'simple-fund-selection',
    capabilities: [
      'fund.search',
      'fund.research.snapshot',
      'fund.compare',
      'fund.attribution.run',
      'fund.analysis.run',
      'fund.recommendations.list',
    ],
    bridgeProtocol: '1.0',
    viewSpecVersion: '1.0',
    asOf: new Date().toISOString(),
  })
}
