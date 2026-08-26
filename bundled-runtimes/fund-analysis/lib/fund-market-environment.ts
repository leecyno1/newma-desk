export type MarketEnvironmentNavPoint = {
  date: string
  nav: number
  benchmarkNav: number | null
}

export type MarketEnvironmentMonth = {
  month: string
  date: string
  fundReturn: number
  benchmarkReturn: number
  excessReturn: number
  market: 'up' | 'down' | 'flat'
}

export type FundMarketEnvironment = {
  status: 'ready' | 'partial' | 'insufficient'
  sampleStart: string
  sampleEnd: string
  monthlyPeriods: number
  upMonths: number
  downMonths: number
  upsideCapture: number | null
  downsideCapture: number | null
  upOutperformanceRate: number | null
  downProtectionRate: number | null
  upAverageExcessReturn: number | null
  downAverageExcessReturn: number | null
  benchmarkCoverage: number
  months: MarketEnvironmentMonth[]
  missingItems: string[]
  methodology: string
}

function average(values: number[]) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
}

function annualizedConditionalReturn(values: number[]) {
  if (!values.length) return null
  const compounded = values.reduce((result, value) => result * (1 + value), 1)
  if (compounded <= 0) return null
  return compounded ** (12 / values.length) - 1
}

function captureRatio(fundReturns: number[], benchmarkReturns: number[]) {
  const fundAnnualized = annualizedConditionalReturn(fundReturns)
  const benchmarkAnnualized = annualizedConditionalReturn(benchmarkReturns)
  if (fundAnnualized == null || benchmarkAnnualized == null || Math.abs(benchmarkAnnualized) < 1e-9) return null
  return fundAnnualized / benchmarkAnnualized
}

function emptyProfile(missingItems: string[], benchmarkCoverage = 0): FundMarketEnvironment {
  return {
    status: 'insufficient',
    sampleStart: '',
    sampleEnd: '',
    monthlyPeriods: 0,
    upMonths: 0,
    downMonths: 0,
    upsideCapture: null,
    downsideCapture: null,
    upOutperformanceRate: null,
    downProtectionRate: null,
    upAverageExcessReturn: null,
    downAverageExcessReturn: null,
    benchmarkCoverage,
    months: [],
    missingItems,
    methodology: '按共同交易日的月末累计净值计算自然月收益，再按基准上涨月和下跌月分组。',
  }
}

export function buildFundMarketEnvironment(points: MarketEnvironmentNavPoint[]): FundMarketEnvironment {
  const validPoints = points
    .filter((point) => point.date && Number.isFinite(point.nav) && point.nav > 0)
    .sort((left, right) => left.date.localeCompare(right.date))
  const alignedPoints = validPoints.filter(
    (point): point is MarketEnvironmentNavPoint & { benchmarkNav: number } =>
      point.benchmarkNav != null && Number.isFinite(point.benchmarkNav) && point.benchmarkNav > 0,
  )
  const benchmarkCoverage = validPoints.length ? alignedPoints.length / validPoints.length : 0

  if (alignedPoints.length < 2) {
    return emptyProfile(['基金与评价基准缺少足够的共同净值日期。'], benchmarkCoverage)
  }

  const monthEnds = new Map<string, MarketEnvironmentNavPoint & { benchmarkNav: number }>()
  for (const point of alignedPoints) monthEnds.set(point.date.slice(0, 7), point)
  const monthlyPoints = Array.from(monthEnds.values()).sort((left, right) => left.date.localeCompare(right.date))
  if (monthlyPoints.length < 4) {
    return emptyProfile(['共同月末净值少于 4 个，暂不判断上涨参与和下跌防守。'], benchmarkCoverage)
  }

  const months: MarketEnvironmentMonth[] = []
  for (let index = 1; index < monthlyPoints.length; index += 1) {
    const previous = monthlyPoints[index - 1]
    const current = monthlyPoints[index]
    const fundReturn = current.nav / previous.nav - 1
    const benchmarkReturn = current.benchmarkNav / previous.benchmarkNav - 1
    if (!Number.isFinite(fundReturn) || !Number.isFinite(benchmarkReturn) || fundReturn <= -1 || benchmarkReturn <= -1) continue
    months.push({
      month: current.date.slice(0, 7),
      date: current.date,
      fundReturn,
      benchmarkReturn,
      excessReturn: fundReturn - benchmarkReturn,
      market: benchmarkReturn > 0 ? 'up' : benchmarkReturn < 0 ? 'down' : 'flat',
    })
  }

  const upMonths = months.filter((item) => item.market === 'up')
  const downMonths = months.filter((item) => item.market === 'down')
  const missingItems = []
  if (months.length < 6) missingItems.push('月度样本少于 6 期，结论仅作初步观察。')
  if (upMonths.length < 2) missingItems.push('基准上涨月少于 2 期。')
  if (downMonths.length < 2) missingItems.push('基准下跌月少于 2 期。')

  const status = months.length >= 6 && upMonths.length >= 2 && downMonths.length >= 2
    ? 'ready'
    : months.length >= 3 && upMonths.length && downMonths.length
      ? 'partial'
      : 'insufficient'

  return {
    status,
    sampleStart: monthlyPoints[0]?.date || '',
    sampleEnd: monthlyPoints[monthlyPoints.length - 1]?.date || '',
    monthlyPeriods: months.length,
    upMonths: upMonths.length,
    downMonths: downMonths.length,
    upsideCapture: captureRatio(upMonths.map((item) => item.fundReturn), upMonths.map((item) => item.benchmarkReturn)),
    downsideCapture: captureRatio(downMonths.map((item) => item.fundReturn), downMonths.map((item) => item.benchmarkReturn)),
    upOutperformanceRate: upMonths.length
      ? upMonths.filter((item) => item.excessReturn > 0).length / upMonths.length
      : null,
    downProtectionRate: downMonths.length
      ? downMonths.filter((item) => item.excessReturn > 0).length / downMonths.length
      : null,
    upAverageExcessReturn: average(upMonths.map((item) => item.excessReturn)),
    downAverageExcessReturn: average(downMonths.map((item) => item.excessReturn)),
    benchmarkCoverage,
    months,
    missingItems,
    methodology: '按共同交易日的月末累计净值计算自然月收益，再按基准上涨月和下跌月分组；捕获率使用条件月收益几何年化后相除。',
  }
}
