import calendar from '../backend/data/sse_trading_calendar.json' with { type: 'json' }

export type MarketEnvironmentNavPoint = {
  date: string
  adjNav: number | null
  benchmarkNav: number | null
  riskCalendar?: string | null
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
  methodologyVersion: string
  excludedMonths: number
  benchmarkIdentityVerified: boolean
}

const methodologyVersion = 'adjusted_consecutive_month_end_v2'
const methodology = '仅用复权净值与库存基准的同日月末端点；不跨缺失月份，不纳入未结束月份。捕获率为条件月收益几何年化之比；未知市场月末按7自然日容忍，不冒充交易日历核验。'
const closed = new Set<string>(calendar.closed_weekdays)
const openWeekends = new Set<string>(calendar.open_weekends)

function expectedMonthEnd(month: string, useSse: boolean) {
  const [year, number] = month.split('-').map(Number)
  const day = new Date(Date.UTC(year, number, 0))
  const naturalEnd = day.toISOString().slice(0, 10)
  if (!useSse) return { naturalEnd, expectedEnd: naturalEnd }
  if (naturalEnd < calendar.start_date || naturalEnd > calendar.end_date) return { naturalEnd, expectedEnd: '' }
  while (day.toISOString().slice(0, 7) === month) {
    const value = day.toISOString().slice(0, 10)
    if ((day.getUTCDay() > 0 && day.getUTCDay() < 6 && !closed.has(value)) || openWeekends.has(value)) return { naturalEnd, expectedEnd: value }
    day.setUTCDate(day.getUTCDate() - 1)
  }
  return { naturalEnd, expectedEnd: '' }
}

function monthNumber(month: string) {
  const [year, number] = month.split('-').map(Number)
  return year * 12 + number
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

function emptyProfile(missingItems: string[], benchmarkCoverage = 0, benchmarkIdentityVerified = false): FundMarketEnvironment {
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
    methodology, methodologyVersion, excludedMonths: 0, benchmarkIdentityVerified,
  }
}

export function buildFundMarketEnvironment(points: MarketEnvironmentNavPoint[], options: { asOfDate?: string; benchmarkIdentityVerified?: boolean } = {}): FundMarketEnvironment {
  const asOfDate = options.asOfDate || new Date().toISOString().slice(0, 10)
  const dated = new Map<string, MarketEnvironmentNavPoint>()
  for (const point of points) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(point.date) && point.date <= asOfDate
        && !Number.isNaN(Date.parse(point.date)) && new Date(point.date).toISOString().slice(0, 10) === point.date) dated.set(point.date, point)
  }
  const rawPoints = [...dated.values()].sort((a, b) => a.date.localeCompare(b.date))
  const valid = (point: MarketEnvironmentNavPoint) => point.adjNav != null && Number.isFinite(point.adjNav) && point.adjNav > 0
    && point.benchmarkNav != null && Number.isFinite(point.benchmarkNav) && point.benchmarkNav > 0
  const alignedPoints = rawPoints.filter(valid)
  const benchmarkCoverage = rawPoints.length ? alignedPoints.length / rawPoints.length : 0
  const benchmarkIdentityVerified = options.benchmarkIdentityVerified === true
  const identityMissing = benchmarkIdentityVerified ? [] : ['库存基准未保存可核验的代码/来源，不能将其视为当前指定评价基准。']

  if (alignedPoints.length < 2) {
    return emptyProfile(['复权净值与库存基准缺少足够的共同有效日期。', ...identityMissing], benchmarkCoverage, benchmarkIdentityVerified)
  }

  const useSse = rawPoints.length > 0 && rawPoints.every(point => point.riskCalendar === 'SSE')
  const monthEnds = new Map<string, MarketEnvironmentNavPoint>()
  for (const point of rawPoints) monthEnds.set(point.date.slice(0, 7), point)
  const monthlyPoints = [...monthEnds.values()]
  if (monthlyPoints.length < 4) {
    return emptyProfile(['月末记录少于 4 个，暂不判断上涨参与和下跌防守。', ...identityMissing], benchmarkCoverage, benchmarkIdentityVerified)
  }

  const months: MarketEnvironmentMonth[] = []
  const usableEnd = (point: MarketEnvironmentNavPoint) => {
    const { naturalEnd, expectedEnd } = expectedMonthEnd(point.date.slice(0, 7), useSse)
    return valid(point) && naturalEnd <= asOfDate && expectedEnd
      && (useSse ? point.date >= expectedEnd : (Date.parse(naturalEnd) - Date.parse(point.date)) / 86400000 <= 7)
  }
  let excludedMonths = 0
  for (let index = 1; index < monthlyPoints.length; index += 1) {
    const previous = monthlyPoints[index - 1]
    const current = monthlyPoints[index]
    if (monthNumber(current.date.slice(0, 7)) - monthNumber(previous.date.slice(0, 7)) !== 1
        || !usableEnd(previous) || !usableEnd(current)) { excludedMonths += 1; continue }
    const fundReturn = current.adjNav! / previous.adjNav! - 1
    const benchmarkReturn = current.benchmarkNav! / previous.benchmarkNav! - 1
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
  if (excludedMonths) missingItems.push(`${excludedMonths} 个候选月份因缺端点、断月或月份未结束而排除。`)
  if (!useSse) missingItems.push('交易日历未核验，月末仅按7自然日容忍。')
  missingItems.push(...identityMissing)
  if (months.length < 6) missingItems.push('月度样本少于 6 期，结论仅作初步观察。')
  if (upMonths.length < 2) missingItems.push('基准上涨月少于 2 期。')
  if (downMonths.length < 2) missingItems.push('基准下跌月少于 2 期。')

  const status = months.length >= 6 && upMonths.length >= 2 && downMonths.length >= 2 && useSse && options.benchmarkIdentityVerified
    ? 'ready'
    : months.length >= 3 && upMonths.length && downMonths.length
      ? 'partial'
      : 'insufficient'

  return {
    status,
    sampleStart: months.length ? monthlyPoints.find(point => monthNumber(point.date.slice(0, 7)) === monthNumber(months[0].month) - 1)?.date || '' : '',
    sampleEnd: months.at(-1)?.date || '',
    monthlyPeriods: months.length,
    upMonths: upMonths.length,
    downMonths: downMonths.length,
    upsideCapture: upMonths.length >= 2 ? captureRatio(upMonths.map((item) => item.fundReturn), upMonths.map((item) => item.benchmarkReturn)) : null,
    downsideCapture: downMonths.length >= 2 ? captureRatio(downMonths.map((item) => item.fundReturn), downMonths.map((item) => item.benchmarkReturn)) : null,
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
    methodology, methodologyVersion, excludedMonths,
    benchmarkIdentityVerified,
  }
}
