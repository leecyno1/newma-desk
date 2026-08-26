import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'
import { getMergedSalesRule, type SalesRule } from '@/lib/sales-rules'
import { hasValidSalesRuleSourceIdentityEvidence } from '@/lib/sales-rule-source-evidence'

type NavPoint = {
  date: string
  nav: number
}

type PurchasePlan = 'lump_sum' | 'sip'

function asNumber(value: unknown) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function normalizePurchasePlan(value: string | null): PurchasePlan {
  return value === 'lump_sum' ? 'lump_sum' : 'sip'
}

function parseDrawdownTolerance(value: string | null) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return null
  const normalized = parsed > 1 ? parsed / 100 : parsed
  return clamp(normalized, 0.01, 0.8)
}

function percentText(value: number | null) {
  return value === null ? '待补' : `${(value * 100).toFixed(2)}%`
}

function dateMonthsAgo(months: number) {
  const date = new Date()
  date.setMonth(date.getMonth() - months)
  return date.toISOString().slice(0, 10)
}

function normalizeNavRows(rows: Array<Record<string, unknown>>): NavPoint[] {
  return rows
    .map((row) => ({
      date: String(row.date || ''),
      nav: asNumber(row.nav) ?? 0,
    }))
    .filter((row) => row.date && row.nav > 0)
    .sort((left, right) => left.date.localeCompare(right.date))
}

function maxDrawdown(values: number[]) {
  let peak = values[0] ?? 0
  let worst = 0
  for (const value of values) {
    if (value > peak) peak = value
    if (peak > 0) worst = Math.min(worst, value / peak - 1)
  }
  return worst
}

function monthlyFirstRows(rows: NavPoint[]) {
  const seen = new Set<string>()
  return rows.filter((row) => {
    const month = row.date.slice(0, 7)
    if (seen.has(month)) return false
    seen.add(month)
    return true
  })
}

function monthlyReturns(rows: NavPoint[]) {
  const monthLast = new Map<string, NavPoint>()
  for (const row of rows) {
    monthLast.set(row.date.slice(0, 7), row)
  }
  const monthRows = Array.from(monthLast.values()).sort((left, right) => left.date.localeCompare(right.date))
  const returns = []
  for (let index = 1; index < monthRows.length; index += 1) {
    const previous = monthRows[index - 1]
    const current = monthRows[index]
    returns.push({
      month: current.date.slice(0, 7),
      returnRate: current.nav / previous.nav - 1,
    })
  }
  return returns
}

function buildStressExperience(rows: NavPoint[], returns: Array<{ month: string; returnRate: number }>) {
  const first = rows[0]
  let peakNav = first.nav
  let peakDate = first.date
  let troughDate = first.date
  let worstDrawdown = 0
  let worstRecoveryDays: number | null = null
  let longestUnderwaterDays = 0
  let currentUnderwaterStart: string | null = null

  for (const row of rows) {
    if (row.nav >= peakNav) {
      if (currentUnderwaterStart) {
        longestUnderwaterDays = Math.max(longestUnderwaterDays, daysBetween(currentUnderwaterStart, row.date) ?? 0)
        if (peakDate <= troughDate && row.date >= troughDate && worstRecoveryDays === null) {
          worstRecoveryDays = daysBetween(peakDate, row.date)
        }
        currentUnderwaterStart = null
      }
      peakNav = row.nav
      peakDate = row.date
    } else {
      if (!currentUnderwaterStart) currentUnderwaterStart = peakDate
      const drawdown = row.nav / peakNav - 1
      if (drawdown < worstDrawdown) {
        worstDrawdown = drawdown
        troughDate = row.date
        worstRecoveryDays = null
      }
    }
  }

  if (currentUnderwaterStart) {
    longestUnderwaterDays = Math.max(longestUnderwaterDays, daysBetween(currentUnderwaterStart, rows[rows.length - 1].date) ?? 0)
  }

  let longestLosingStreakMonths = 0
  let currentLosingStreakMonths = 0
  let worstThreeMonthReturn: null | { startMonth: string; endMonth: string; returnRate: number } = null

  returns.forEach((item, index) => {
    if (item.returnRate < 0) {
      currentLosingStreakMonths += 1
      longestLosingStreakMonths = Math.max(longestLosingStreakMonths, currentLosingStreakMonths)
    } else {
      currentLosingStreakMonths = 0
    }

    if (index >= 2) {
      const windowRows = returns.slice(index - 2, index + 1)
      const compoundedReturn = windowRows.reduce((product, row) => product * (1 + row.returnRate), 1) - 1
      if (!worstThreeMonthReturn || compoundedReturn < worstThreeMonthReturn.returnRate) {
        worstThreeMonthReturn = {
          startMonth: windowRows[0].month,
          endMonth: windowRows[windowRows.length - 1].month,
          returnRate: compoundedReturn,
        }
      }
    }
  })

  const stressScore = Math.round(Math.max(0, Math.min(100,
    100 -
    Math.abs(worstDrawdown) * 220 -
    longestLosingStreakMonths * 6 -
    Math.min(30, longestUnderwaterDays / 18),
  )))
  const stressLevel = stressScore >= 75
    ? 'comfortable'
    : stressScore >= 60
      ? 'watchable'
      : stressScore >= 45
        ? 'bumpy'
        : 'stressful'
  const label = stressLevel === 'comfortable'
    ? '压力体验较温和'
    : stressLevel === 'watchable'
      ? '压力体验可观察'
      : stressLevel === 'bumpy'
        ? '压力体验偏颠簸'
        : '压力体验压力较大'

  return {
    label,
    stressLevel,
    stressScore,
    worstDrawdown,
    troughDate,
    recoveryDays: worstRecoveryDays,
    longestUnderwaterDays,
    longestLosingStreakMonths,
    worstThreeMonthReturn,
    interpretation: worstRecoveryDays === null
      ? '历史回放期内最大回撤尚未完全回本，研究复核需确认账面亏损持续时间。'
      : `最大回撤后约 ${worstRecoveryDays} 天回到前高，研究复核需结合计划观察期判断等待成本。`,
  }
}

function simulateLumpSum(rows: NavPoint[], amount: number) {
  const first = rows[0]
  const last = rows[rows.length - 1]
  const units = amount / first.nav
  const endingValue = units * last.nav
  const navValues = rows.map((row) => row.nav)
  return {
    totalInvested: amount,
    endingValue: Math.round(endingValue * 100) / 100,
    profit: Math.round((endingValue - amount) * 100) / 100,
    returnRate: endingValue / amount - 1,
    maxDrawdown: maxDrawdown(navValues),
    startDate: first.date,
    endDate: last.date,
  }
}

type SipLot = {
  date: string
  grossAmount: number
  netAmount: number
  purchaseFee: number
  units: number
}

function simulateSip(rows: NavPoint[], monthlyAmount: number) {
  const contributionRows = monthlyFirstRows(rows)
  let totalInvested = 0
  let units = 0
  const lots: SipLot[] = []
  const accountValues: number[] = []

  for (const row of rows) {
    if (contributionRows.some((item) => item.date === row.date)) {
      totalInvested += monthlyAmount
      const contributionUnits = monthlyAmount / row.nav
      units += contributionUnits
      lots.push({
        date: row.date,
        grossAmount: monthlyAmount,
        netAmount: monthlyAmount,
        purchaseFee: 0,
        units: contributionUnits,
      })
    }
    accountValues.push(units * row.nav)
  }

  const last = rows[rows.length - 1]
  const endingValue = units * last.nav
  return {
    monthlyAmount,
    contributionCount: contributionRows.length,
    totalInvested,
    endingValue: Math.round(endingValue * 100) / 100,
    profit: Math.round((endingValue - totalInvested) * 100) / 100,
    returnRate: totalInvested > 0 ? endingValue / totalInvested - 1 : null,
    averageCost: units > 0 ? totalInvested / units : null,
    maxAccountDrawdown: maxDrawdown(accountValues.filter((value) => value > 0)),
    firstContributionDate: contributionRows[0]?.date ?? null,
    lastContributionDate: contributionRows[contributionRows.length - 1]?.date ?? null,
    lots,
  }
}

function roundMoney(value: number) {
  return Math.round(value * 100) / 100
}

function daysBetween(startDate: string, endDate: string) {
  const start = new Date(startDate)
  const end = new Date(endDate)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null
  return Math.max(0, Math.floor((end.getTime() - start.getTime()) / 86_400_000))
}

function sortedRedemptionRules(rules: SalesRule['redemptionFeeRules']) {
  return [...rules]
    .filter((rule) => Number.isFinite(Number(rule.feeRate)))
    .sort((left, right) => (left.holdingDays ?? Number.MAX_SAFE_INTEGER) - (right.holdingDays ?? Number.MAX_SAFE_INTEGER))
}

function redemptionRuleAtHoldingDays(rules: SalesRule['redemptionFeeRules'], holdingDays: number | null) {
  if (!rules.length) return null
  const sortedRules = sortedRedemptionRules(rules)
  if (!sortedRules.length) return null
  if (holdingDays === null) return sortedRules[0]
  const matchedRule = sortedRules.find((rule) => rule.holdingDays === null || holdingDays < rule.holdingDays)
  return matchedRule ?? sortedRules[sortedRules.length - 1] ?? null
}

function applicableRedemptionFeeRate(rules: SalesRule['redemptionFeeRules'], holdingDays: number | null) {
  return redemptionRuleAtHoldingDays(rules, holdingDays)?.feeRate ?? null
}

function buildRedemptionFeeLadder(rules: SalesRule['redemptionFeeRules'], currentHoldingDays: number | null) {
  const currentRule = redemptionRuleAtHoldingDays(rules, currentHoldingDays)
  return sortedRedemptionRules(rules).map((rule) => ({
    holdingDays: rule.holdingDays,
    feeRate: rule.feeRate,
    label: rule.label || '赎回费率',
    isCurrent: Boolean(currentRule && currentRule.holdingDays === rule.holdingDays && currentRule.feeRate === rule.feeRate),
    daysUntilEffective: currentHoldingDays === null || rule.holdingDays === null ? null : Math.max(0, rule.holdingDays - currentHoldingDays),
  }))
}

function isFreshSalesRuleSourceDate(value: string | null | undefined) {
  if (!value) return false
  const sourceDate = new Date(`${String(value).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(sourceDate.getTime())) return false
  const currentDate = new Date()
  currentDate.setUTCHours(0, 0, 0, 0)
  const ageDays = Math.floor((currentDate.getTime() - sourceDate.getTime()) / 86_400_000)
  return ageDays >= 0 && ageDays <= 30
}

function hasSourceBackedRedemptionRules(salesRule: SalesRule | null) {
  if (!salesRule?.redemptionFeeRules.length) return false
  const sourceUpdatedAt = salesRule.redemptionFeeSourceUpdatedAt || salesRule.sourceUpdatedAt
  if (!isFreshSalesRuleSourceDate(sourceUpdatedAt)) return false
  const platform = String(salesRule.redemptionFeePlatform || salesRule.platform || '').trim()
  const sourceUrl = String(salesRule.redemptionFeeSourceUrl || salesRule.sourceUrl || '').trim()
  const notes = String(salesRule.redemptionFeeNotes || salesRule.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function hasSourceBackedSalesRuleField(salesRule: SalesRule | null, sourceFlag: keyof SalesRule, value: unknown) {
  if (value === null || value === undefined || value === '') return false
  const explicitFlag = salesRule?.[sourceFlag]
  if (explicitFlag === true) return true
  if (explicitFlag === false) return false
  if (!isFreshSalesRuleSourceDate(salesRule?.sourceUpdatedAt)) return false
  const platform = String(salesRule?.platform || '').trim()
  const sourceUrl = String(salesRule?.sourceUrl || '').trim()
  const notes = String(salesRule?.notes || '').trim()
  return hasValidSalesRuleSourceIdentityEvidence({ platform, sourceUrl, notes })
}

function netSubscriptionAmount(grossAmount: number, purchaseFeeRate: number | null) {
  if (purchaseFeeRate === null) {
    return { netAmount: grossAmount, purchaseFee: 0 }
  }
  const netAmount = grossAmount / (1 + purchaseFeeRate / 100)
  return {
    netAmount,
    purchaseFee: grossAmount - netAmount,
  }
}

function buildFeeAdjustedSimulation({
  rows,
  lumpSumAmount,
  monthlyAmount,
  salesRule,
}: {
  rows: NavPoint[]
  lumpSumAmount: number
  monthlyAmount: number
  salesRule: SalesRule | null
}) {
  const first = rows[0]
  const last = rows[rows.length - 1]
  const rawPurchaseFeeRate = salesRule?.purchaseFeeRate ?? null
  const purchaseFeeRate = hasSourceBackedSalesRuleField(salesRule, 'purchaseFeeSourceBacked', rawPurchaseFeeRate)
    ? rawPurchaseFeeRate
    : null
  const redemptionFeeRules = hasSourceBackedRedemptionRules(salesRule) ? salesRule?.redemptionFeeRules || [] : []
  const missingItems = [
    purchaseFeeRate === null ? '申购费率' : '',
    redemptionFeeRules.length === 0 ? '赎回费/持有期' : '',
  ].filter(Boolean)

  if (!salesRule || (purchaseFeeRate === null && redemptionFeeRules.length === 0)) {
    return {
      coverage: 'none' as const,
      missingItems,
      assumptions: {
        purchaseFeeRate,
        redemptionFeeRules,
        salesRulePlatform: salesRule?.platform || null,
      },
      lumpSum: null,
      sip: null,
    }
  }

  const lumpSumSubscription = netSubscriptionAmount(lumpSumAmount, purchaseFeeRate)
  const lumpSumUnits = lumpSumSubscription.netAmount / first.nav
  const lumpSumGrossEndingValue = lumpSumUnits * last.nav
  const lumpSumHoldingDays = daysBetween(first.date, last.date)
  const lumpSumRedemptionRule = redemptionRuleAtHoldingDays(redemptionFeeRules, lumpSumHoldingDays)
  const lumpSumRedemptionFeeRate = lumpSumRedemptionRule?.feeRate ?? null
  const lumpSumRedemptionFee = lumpSumRedemptionFeeRate === null ? 0 : lumpSumGrossEndingValue * lumpSumRedemptionFeeRate / 100
  const lumpSumEndingValue = lumpSumGrossEndingValue - lumpSumRedemptionFee
  const contributionRows = monthlyFirstRows(rows)
  const sipLots = contributionRows.map((row) => {
    const subscription = netSubscriptionAmount(monthlyAmount, purchaseFeeRate)
    return {
      date: row.date,
      grossAmount: monthlyAmount,
      netAmount: subscription.netAmount,
      purchaseFee: subscription.purchaseFee,
      units: subscription.netAmount / row.nav,
    }
  })
  const sipTotalInvested = sipLots.reduce((sum, lot) => sum + lot.grossAmount, 0)
  const sipPurchaseFee = sipLots.reduce((sum, lot) => sum + lot.purchaseFee, 0)
  const sipGrossEndingValue = sipLots.reduce((sum, lot) => sum + lot.units * last.nav, 0)
  const sipRedemptionRuleBuckets = new Map<string, {
    label: string
    feeRate: number
    holdingDays: number | null
    lotCount: number
    redemptionFee: number
  }>()
  const sipRedemptionFee = sipLots.reduce((sum, lot) => {
    const holdingDays = daysBetween(lot.date, last.date)
    const redemptionRule = redemptionRuleAtHoldingDays(redemptionFeeRules, holdingDays)
    const redemptionFeeRate = redemptionRule?.feeRate ?? null
    const fee = redemptionFeeRate === null ? 0 : lot.units * last.nav * redemptionFeeRate / 100
    if (redemptionRule) {
      const key = `${redemptionRule.holdingDays ?? 'open'}-${redemptionRule.feeRate}-${redemptionRule.label}`
      const bucket = sipRedemptionRuleBuckets.get(key) || {
        label: redemptionRule.label || '赎回费率',
        feeRate: redemptionRule.feeRate,
        holdingDays: redemptionRule.holdingDays,
        lotCount: 0,
        redemptionFee: 0,
      }
      bucket.lotCount += 1
      bucket.redemptionFee += fee
      sipRedemptionRuleBuckets.set(key, bucket)
    }
    return sum + fee
  }, 0)
  const sipEndingValue = sipGrossEndingValue - sipRedemptionFee

  return {
    coverage: missingItems.length ? 'partial' as const : 'full' as const,
    missingItems,
    assumptions: {
      purchaseFeeRate,
      redemptionFeeRules,
      salesRulePlatform: salesRule.platform,
    },
    lumpSum: {
      totalInvested: lumpSumAmount,
      purchaseFee: roundMoney(lumpSumSubscription.purchaseFee),
      redemptionFee: roundMoney(lumpSumRedemptionFee),
      totalFee: roundMoney(lumpSumSubscription.purchaseFee + lumpSumRedemptionFee),
      endingValue: roundMoney(lumpSumEndingValue),
      profit: roundMoney(lumpSumEndingValue - lumpSumAmount),
      returnRate: lumpSumEndingValue / lumpSumAmount - 1,
      holdingDays: lumpSumHoldingDays,
      redemptionRule: lumpSumRedemptionRule ? {
        label: lumpSumRedemptionRule.label || '赎回费率',
        feeRate: lumpSumRedemptionRule.feeRate,
        holdingDays: lumpSumRedemptionRule.holdingDays,
      } : null,
      redemptionFeeLadder: buildRedemptionFeeLadder(redemptionFeeRules, lumpSumHoldingDays),
    },
    sip: {
      monthlyAmount,
      contributionCount: sipLots.length,
      totalInvested: sipTotalInvested,
      purchaseFee: roundMoney(sipPurchaseFee),
      redemptionFee: roundMoney(sipRedemptionFee),
      totalFee: roundMoney(sipPurchaseFee + sipRedemptionFee),
      endingValue: roundMoney(sipEndingValue),
      profit: roundMoney(sipEndingValue - sipTotalInvested),
      returnRate: sipTotalInvested > 0 ? sipEndingValue / sipTotalInvested - 1 : null,
      redemptionRuleBuckets: Array.from(sipRedemptionRuleBuckets.values()).map((bucket) => ({
        ...bucket,
        redemptionFee: roundMoney(bucket.redemptionFee),
      })),
    },
  }
}

function buildSimulationEvidenceGate({
  purchasePlan,
  maxDrawdownTolerance,
  feeAdjusted,
  stressExperience,
  lumpSum,
  sip,
}: {
  purchasePlan: PurchasePlan
  maxDrawdownTolerance: number | null
  feeAdjusted: ReturnType<typeof buildFeeAdjustedSimulation>
  stressExperience: ReturnType<typeof buildStressExperience>
  lumpSum: ReturnType<typeof simulateLumpSum>
  sip: ReturnType<typeof simulateSip>
}) {
  const reasons: string[] = []
  const actions: string[] = []
  let status: 'pass' | 'verify_first' = 'pass'
  const replayDrawdown = purchasePlan === 'sip' ? sip.maxAccountDrawdown : lumpSum.maxDrawdown
  const stressDrawdown = Math.abs(stressExperience.worstDrawdown || replayDrawdown || 0)
  const replayInvested = purchasePlan === 'sip' ? sip.totalInvested : lumpSum.totalInvested
  const plannedReplayAmount = purchasePlan === 'sip' ? sip.monthlyAmount : lumpSum.totalInvested
  const estimatedLoss = replayDrawdown === null ? null : roundMoney(Math.abs(replayDrawdown) * replayInvested)
  const missingEvidence = [
    ...feeAdjusted.missingItems,
    maxDrawdownTolerance === null ? '研究场景回撤预算' : '',
    stressExperience.recoveryDays === null ? '最大回撤回本确认' : '',
  ].filter(Boolean)

  if (feeAdjusted.coverage !== 'full') {
    status = 'verify_first'
    reasons.push(`费用证据不完整：缺 ${feeAdjusted.missingItems.join('、') || '销售规则来源'}。`)
    actions.push('先补申购费、赎回费和销售规则来源，再保存正式研究复核报告。')
  } else {
    reasons.push('申购费和赎回费已进入费用后回放。')
  }

  if (maxDrawdownTolerance === null) {
    status = 'verify_first'
    reasons.push('缺少研究场景回撤预算，本次回放不能判断是否超出观察约束。')
    actions.push('带入研究场景和回撤预算后重新测算。')
  } else if (stressDrawdown > maxDrawdownTolerance) {
    status = 'verify_first'
    reasons.push(`历史压力回撤 ${percentText(-stressDrawdown)} 超过当前画像预算 ${percentText(maxDrawdownTolerance)}。`)
    actions.push('先调低金额、切换定投或更换同画像替代基金横评。')
  } else {
    reasons.push(`历史压力回撤 ${percentText(-stressDrawdown)} 未超过当前画像预算 ${percentText(maxDrawdownTolerance)}。`)
  }

  if (stressExperience.recoveryDays === null) {
    status = 'verify_first'
    reasons.push('最大回撤在回放期内尚未回本。')
    actions.push('确认未回本等待是否可接受，再进入详情页研究复核报告。')
  }

  return {
    status,
    label: status === 'pass' ? '可纳入研究回放证据' : '只可作压力观察',
    summary: status === 'pass'
      ? '真实净值、费用覆盖和回撤预算未触发测算证据门禁，可作为研究复核证据之一。'
      : '真实净值回放已完成，但费用、回撤预算或回本等待仍不足以支持正式研究结论。',
    hardBoundary: '历史回放不是研究建议；材料证据、费用和回撤预算未清零前，不得保存为正式研究候选。',
    purchasePlan,
    maxDrawdownTolerance,
    feeCoverage: feeAdjusted.coverage,
    missingEvidence,
    plannedReplayAmount,
    replayInvested,
    replayDrawdown,
    stressDrawdown,
    estimatedLoss,
    recoveryDays: stressExperience.recoveryDays,
    reasons: reasons.slice(0, 5),
    actions: Array.from(new Set(actions)).slice(0, 4),
  }
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const { searchParams } = new URL(request.url)
    const months = Math.max(3, Math.min(60, Number(searchParams.get('months') || '12')))
    const lumpSumAmount = Math.max(1, Number(searchParams.get('lumpSumAmount') || '10000'))
    const monthlyAmount = Math.max(1, Number(searchParams.get('monthlyAmount') || '1000'))
    const purchasePlan = normalizePurchasePlan(searchParams.get('purchasePlan'))
    const maxDrawdownTolerance = parseDrawdownTolerance(searchParams.get('maxDrawdownTolerance'))
    const endDate = searchParams.get('endDate') || new Date().toISOString().slice(0, 10)
    const startDate = searchParams.get('startDate') || dateMonthsAgo(months)

    const backendUrl = new URL(`/api/funds/${encodeURIComponent(id)}/nav`, backendApiBaseUrl)
    backendUrl.searchParams.set('start_date', startDate)
    backendUrl.searchParams.set('end_date', endDate)
    const response = await fetch(backendUrl, { cache: 'no-store' })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '真实净值序列读取失败' },
        { status: response.status },
      )
    }

    const rows = normalizeNavRows(payload.data || [])
    if (rows.length < 2) {
      return NextResponse.json(
        { error: '净值样本不足，无法进行历史净值回放' },
        { status: 422 },
      )
    }

    const returns = monthlyReturns(rows)
    const positiveMonths = returns.filter((item) => item.returnRate > 0).length
    const bestMonth = returns.reduce((best, item) => !best || item.returnRate > best.returnRate ? item : best, null as null | { month: string; returnRate: number })
    const worstMonth = returns.reduce((worst, item) => !worst || item.returnRate < worst.returnRate ? item : worst, null as null | { month: string; returnRate: number })
    const stressExperience = buildStressExperience(rows, returns)

    const salesRule = await getMergedSalesRule(id)
    const feeAdjusted = buildFeeAdjustedSimulation({
      rows,
      lumpSumAmount,
      monthlyAmount,
      salesRule,
    })
    const lumpSum = simulateLumpSum(rows, lumpSumAmount)
    const sip = simulateSip(rows, monthlyAmount)
    const evidenceGate = buildSimulationEvidenceGate({
      purchasePlan,
      maxDrawdownTolerance,
      feeAdjusted,
      stressExperience,
      lumpSum,
      sip,
    })

    return NextResponse.json({
      fundCode: id,
      source: 'backend.tushare.fund_nav',
      period: {
        requestedStartDate: startDate,
        requestedEndDate: endDate,
        startDate: rows[0].date,
        endDate: rows[rows.length - 1].date,
        observations: rows.length,
        months,
      },
      assumptions: {
        lumpSumAmount,
        monthlyAmount,
        purchasePlan,
        maxDrawdownTolerance,
        sipFrequency: '每月首个可用净值日',
        feeIncluded: feeAdjusted.coverage !== 'none',
      },
      lumpSum,
      sip,
      feeAdjusted,
      evidenceGate,
      monthlyExperience: {
        months: returns.length,
        positiveMonths,
        positiveRatio: returns.length ? positiveMonths / returns.length : null,
        bestMonth,
        worstMonth,
      },
      stressExperience,
      disclaimer: feeAdjusted.coverage === 'full'
        ? '本测算基于历史净值和本地销售规则估算申购/赎回费用；不含税费、销售平台折扣、限购和未来收益预测。'
        : '本测算基于历史净值回放；费用后结果仅按已录入销售规则粗估，缺失费率、限购或风险等级时仍需研究复核。',
    })
  } catch (error) {
    console.error('历史净值回放失败:', error)
    return NextResponse.json(
      { error: '历史净值回放失败' },
      { status: 500 },
    )
  }
}
