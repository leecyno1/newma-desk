export type YearlyChartPeriod = {
  year: number
  label: string
  isYtd: boolean
  return: number
  coverageStatus: string
  actualEndDate: string
}

export type YearlyChartFund = {
  windCode: string
  periods: YearlyChartPeriod[]
}

export type YearlyChartRow = Record<string, number | string | null>

// 同一自然年度内，各基金净值截止日不一致的年度收益不可直接并柱比较
//（例：18.1% 截至 6 月末与 27.3% 截至 9 月末）。只有覆盖完整、且截止日与
// 当年多数基金一致（并列取最新）的区间才进柱状图；其余留在明细表里看。
export function buildYearlyChartData(funds: YearlyChartFund[], calendarYears: number[]): YearlyChartRow[] {
  return [...calendarYears].sort((left, right) => left - right).map((year) => {
    const row: YearlyChartRow = {
      year: funds.flatMap((item) => item.periods).find((period) => period.year === year)?.label || `${year} 年`,
    }
    const cutoffCounts = new Map<string, number>()
    for (const item of funds) {
      const period = item.periods.find((entry) => entry.year === year)
      if (!period || period.coverageStatus !== 'complete') continue
      cutoffCounts.set(period.actualEndDate, (cutoffCounts.get(period.actualEndDate) || 0) + 1)
    }
    let chartedCutoff: string | null = null
    if (cutoffCounts.size > 1) {
      let winner = ''
      let winnerCount = 0
      for (const [cutoff, count] of cutoffCounts) {
        if (count > winnerCount || (count === winnerCount && cutoff > winner)) {
          winner = cutoff
          winnerCount = count
        }
      }
      chartedCutoff = winner
    }
    for (const item of funds) {
      const period = item.periods.find((entry) => entry.year === year)
      const comparable = period != null
        && period.coverageStatus === 'complete'
        && (chartedCutoff == null || period.actualEndDate === chartedCutoff)
      row[item.windCode] = comparable ? Number((period!.return * 100).toFixed(2)) : null
    }
    return row
  }).filter((row) => funds.some((item) => typeof row[item.windCode] === 'number'))
}
