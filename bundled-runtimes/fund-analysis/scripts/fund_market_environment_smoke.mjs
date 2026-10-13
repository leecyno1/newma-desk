import { buildFundMarketEnvironment } from '../lib/fund-market-environment.ts'

function closeTo(actual, expected, tolerance = 1e-10) {
  if (actual == null || Math.abs(actual - expected) > tolerance) {
    throw new Error(`expected ${expected}, got ${actual}`)
  }
}

const benchmarkReturns = [0.10, -0.10, 0.05, -0.05, 0.02, -0.02]
const fundReturns = [0.12, -0.05, 0.04, -0.04, 0.03, -0.01]
let benchmarkNav = 100
let fundNav = 100
const points = [{ date: '2026-01-31', adjNav: fundNav, benchmarkNav, riskCalendar: 'SSE' }]

benchmarkReturns.forEach((benchmarkReturn, index) => {
  benchmarkNav *= 1 + benchmarkReturn
  fundNav *= 1 + fundReturns[index]
  points.push({
    date: new Date(Date.UTC(2026, index + 2, 0)).toISOString().slice(0, 10),
    adjNav: fundNav,
    benchmarkNav, riskCalendar: 'SSE',
  })
})

const options = { asOfDate: '2026-08-01', benchmarkIdentityVerified: true }
const result = buildFundMarketEnvironment(points, options)
if (result.status !== 'ready') throw new Error(`expected ready, got ${result.status}`)
if (result.monthlyPeriods !== 6 || result.upMonths !== 3 || result.downMonths !== 3) {
  throw new Error(`unexpected market samples: ${JSON.stringify(result)}`)
}
closeTo(result.upOutperformanceRate, 2 / 3)
closeTo(result.downProtectionRate, 1)
if (result.upsideCapture == null || result.upsideCapture <= 1) throw new Error('upside capture should exceed the benchmark')
if (result.downsideCapture == null || result.downsideCapture >= 1) throw new Error('downside capture should show better protection')

const unavailable = buildFundMarketEnvironment(points.map((point) => ({ ...point, benchmarkNav: null })))
if (unavailable.status !== 'insufficient' || !unavailable.missingItems.length) {
  throw new Error('missing benchmark evidence must remain unavailable')
}
if (!unavailable.missingItems.some(item => item.includes('代码/来源'))) throw new Error('sparse data must still disclose unknown benchmark identity')
const identifiedSparse = buildFundMarketEnvironment(points.slice(0, 2), options)
if (!identifiedSparse.benchmarkIdentityVerified || identifiedSparse.status !== 'insufficient') throw new Error('verified identity does not make short history sufficient')

const missingAdjusted = buildFundMarketEnvironment(points.map(point => ({ ...point, nav: point.adjNav, adjNav: null })), options)
if (missingAdjusted.status !== 'insufficient') throw new Error('unit/cumulative nav must not replace missing adjusted NAV')

const missingMonth = buildFundMarketEnvironment(points.filter(point => !point.date.startsWith('2026-04')), options)
if (missingMonth.months.some(month => month.month === '2026-05')) throw new Error('missing month must not become a two-month return')

const nullRevision = buildFundMarketEnvironment([...points, { ...points[2], adjNav: null }], options)
if (nullRevision.months.some(month => ['2026-03', '2026-04'].includes(month.month))) throw new Error('NULL revision must not revive an old month endpoint')

const currentMonth = buildFundMarketEnvironment([...points, { date: '2026-08-12', adjNav: 200, benchmarkNav: 200, riskCalendar: 'SSE' }], { ...options, asOfDate: '2026-08-12' })
if (currentMonth.months.some(month => month.month === '2026-08')) throw new Error('unfinished month must not enter capture ratios')

const missingMonthEnd = buildFundMarketEnvironment(points.map(point => point.date.startsWith('2026-06') ? { ...point, date: '2026-06-25' } : point), options)
if (missingMonthEnd.months.some(month => ['2026-06', '2026-07'].includes(month.month))) throw new Error('missing final exchange open day must invalidate month endpoint')

const missingBenchmarkEnd = buildFundMarketEnvironment(points.map(point => point.date.startsWith('2026-05') ? { ...point, benchmarkNav: null } : point), options)
if (missingBenchmarkEnd.months.some(month => ['2026-05', '2026-06'].includes(month.month))) throw new Error('month end without matching benchmark must not fall back earlier')

const unknownIdentity = buildFundMarketEnvironment(points, { asOfDate: options.asOfDate })
if (unknownIdentity.status === 'ready' || !unknownIdentity.missingItems.some(item => item.includes('代码/来源'))) throw new Error('benchmark identity must not be invented')

const future = buildFundMarketEnvironment([...points, { date: '2099-01-31', adjNav: 200, benchmarkNav: 200 }], options)
if (future.monthlyPeriods !== result.monthlyPeriods) throw new Error('future dates must not leak into the sample')

const noCalendar = buildFundMarketEnvironment(points.map(point => ({ ...point, riskCalendar: null })), options)
if (noCalendar.status === 'ready') throw new Error('unknown market calendar must remain unverified')

console.log('OK fund market environment uses aligned real month-end NAV and keeps missing benchmarks unavailable')
