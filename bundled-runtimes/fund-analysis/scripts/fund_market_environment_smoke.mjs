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
const points = [{ date: '2026-01-31', nav: fundNav, benchmarkNav }]

benchmarkReturns.forEach((benchmarkReturn, index) => {
  benchmarkNav *= 1 + benchmarkReturn
  fundNav *= 1 + fundReturns[index]
  points.push({
    date: `2026-${String(index + 2).padStart(2, '0')}-28`,
    nav: fundNav,
    benchmarkNav,
  })
})

const result = buildFundMarketEnvironment(points)
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

console.log('OK fund market environment uses aligned real month-end NAV and keeps missing benchmarks unavailable')
