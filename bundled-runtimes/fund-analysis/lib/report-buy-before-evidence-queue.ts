import { appendReturnTo, materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'

export type ReportPurchasePlan = 'lump_sum' | 'sip'
const defaultPlannedAmountByPlan: Record<ReportPurchasePlan, number> = {
  lump_sum: 10000,
  sip: 1000,
}

export type BuyBeforeQueueReport = {
  targetType: string
  targetId: string
  relatedCodes?: string[]
  purchasePlan?: ReportPurchasePlan
  plannedAmount?: number | null
  decisionSummary?: {
    buyBeforeGateStatus?: string
    buyBeforeGateHardBlocks?: string[]
    buyBeforeGateCautionFlags?: string[]
    replayEvidenceGateStatus?: string
    replayEvidenceGateLabel?: string
    replayEvidenceGateMissingEvidence?: string[]
  }
  currentSalesRuleGate?: {
    status?: 'ready' | 'blocked' | 'unknown' | string
    missingCount?: number | null
    missingItems?: string[]
    actionHref?: string
    source?: string
  }
}

export type BuyBeforeEvidenceQueueItem = {
  key: string
  title: string
  action: string
  detail: string
  tone: string
  count: number
  codes: string[]
  reasons: string[]
  purchasePlan: ReportPurchasePlan
  plannedAmount: number | null
  href: string
}

function reportPurchasePlan(report: Pick<BuyBeforeQueueReport, 'purchasePlan'>): ReportPurchasePlan {
  return report.purchasePlan === 'lump_sum' ? 'lump_sum' : 'sip'
}

function reportPlannedAmount(report: Pick<BuyBeforeQueueReport, 'purchasePlan' | 'plannedAmount'>) {
  const amount = Number(report.plannedAmount)
  return Number.isFinite(amount) && amount > 0
    ? amount
    : defaultPlannedAmountByPlan[reportPurchasePlan(report)]
}

function reportFundCodes(report: BuyBeforeQueueReport) {
  return Array.from(new Set([
    report.targetType === 'fund' ? report.targetId : '',
    ...(report.relatedCodes || []),
  ].map((code) => String(code || '').trim().toUpperCase()).filter(Boolean)))
}

export function classifyBuyBeforeEvidenceGap(reason: string) {
  if (/复查队列未解决|复查队列读取失败|sales_rule_evidence|local\.alert_events\.sales_rule_evidence/u.test(reason)) {
    return {
      key: 'sales_rule_review_queue',
      title: '复查队列销售规则证据',
      action: '处理复查队列',
      detail: '销售规则/R1-R5 过期或待补事件未清零前，历史报告只能回看，不能推进正式研究复核。',
      tone: 'rose',
    }
  }
  if (/测算证据|测算采信|历史回放|真实净值|回撤预算|回本等待|压力测试|费后回放/u.test(reason)) {
    return {
      key: 'replay_evidence',
      title: '测算证据门禁补证',
      action: '重跑真实回放横评',
      detail: '重跑真实净值、费率、回撤预算和回本等待测算；门禁未过的历史回放不能作为正式研究结论。',
      tone: 'amber',
    }
  }
  if (/销售规则|R1-R5|申购|赎回|费率|起购|限购/u.test(reason)) {
    return {
      key: 'sales_rules',
      title: '销售规则与适当性补证',
      action: '去补销售规则',
      detail: '优先补齐申购状态、费率、赎回、限购、起购金额和 R1-R5。',
      tone: 'rose',
    }
  }
  if (/同类|分位|净值|滚动指标|横评/u.test(reason)) {
    return {
      key: 'peer_metrics',
      title: '同类分位与净值指标补证',
      action: '同步同类指标',
      detail: '补齐净值、滚动收益/回撤/波动后，再做同类胜负排序。',
      tone: 'purple',
    }
  }
  if (/持仓|行业|集中度|重仓/u.test(reason)) {
    return {
      key: 'holding_exposure',
      title: '持仓暴露复核',
      action: '查看持仓暴露',
      detail: '复核前十大、行业集中度和重仓股解释，避免按普通分散基金理解。',
      tone: 'emerald',
    }
  }
  if (/经理|任期|manager_tenure/u.test(reason)) {
    return {
      key: 'manager_tenure',
      title: '经理任期切片补证',
      action: '同步经理任期',
      detail: '补齐现任经理任期切片，避免把历史业绩错误归因给当前经理。',
      tone: 'blue',
    }
  }
  return {
    key: 'other_evidence',
    title: '其他研究证据补证',
    action: '查看证据覆盖',
    detail: '补齐未归类的研究证据缺口，再重新生成研究报告。',
    tone: 'slate',
  }
}

function buyBeforeQueueHref(category: string, codes: string[], purchasePlan: ReportPurchasePlan, plannedAmount: number | null) {
  const params = new URLSearchParams({ purchasePlan })
  if (plannedAmount) params.set('plannedAmount', String(plannedAmount))
  if (plannedAmount) {
    params.set(purchasePlan === 'lump_sum' ? 'lumpSumAmount' : 'monthlyAmount', String(plannedAmount))
  }
  if (codes.length) params.set('codes', codes.join(','))
  if (category === 'sales_rule_review_queue') return appendReturnTo(reviewEventsHref(), '/reports')
  if (category === 'sales_rules') return appendReturnTo(materialEvidenceHref(params), '/reports')
  if (category === 'replay_evidence') {
    params.set('autoReplay', '1')
    return appendReturnTo(`/analysis/comparison?${params.toString()}`, '/reports')
  }
  if (category === 'peer_metrics' || category === 'manager_tenure') return appendReturnTo(`/evidence-coverage?${params.toString()}`, '/reports')
  if (category === 'holding_exposure' && codes[0]) return appendReturnTo(`/funds/${encodeURIComponent(codes[0])}?${params.toString()}`, '/reports')
  return appendReturnTo('/evidence-coverage', '/reports')
}

export function buildBuyBeforeEvidenceQueue(reports: BuyBeforeQueueReport[]): BuyBeforeEvidenceQueueItem[] {
  const groups = new Map<string, {
    key: string
    categoryKey: string
    title: string
    action: string
    detail: string
    tone: string
    count: number
    codes: Set<string>
    reasons: string[]
    purchasePlan: ReportPurchasePlan
    plannedAmount: number | null
  }>()

  const addReason = (report: BuyBeforeQueueReport, reason: string) => {
      const category = classifyBuyBeforeEvidenceGap(reason)
      const purchasePlan = reportPurchasePlan(report)
      const plannedAmount = reportPlannedAmount(report)
      const groupKey = `${category.key}:${purchasePlan}:${plannedAmount}`
      const existing = groups.get(groupKey) || {
        ...category,
        key: groupKey,
        categoryKey: category.key,
        count: 0,
        codes: new Set<string>(),
        reasons: [],
        purchasePlan,
        plannedAmount,
      }
      existing.count += 1
      reportFundCodes(report).forEach((code) => existing.codes.add(code))
      if (existing.reasons.length < 3 && !existing.reasons.includes(reason)) existing.reasons.push(reason)
      groups.set(groupKey, existing)
  }

  reports.forEach((report) => {
    const decision = report.decisionSummary
    const currentSalesRuleGate = report.currentSalesRuleGate

    if (currentSalesRuleGate?.status === 'blocked') {
      const missingItems = currentSalesRuleGate.missingItems?.length
        ? currentSalesRuleGate.missingItems
        : [`销售规则/R1-R5 当前复查仍有 ${currentSalesRuleGate.missingCount ?? 0} 项未解决缺口`]
      missingItems.forEach((reason) => addReason(report, reason))
    }

    if (currentSalesRuleGate?.status === 'unknown') {
      addReason(report, '当前销售规则/R1-R5 门禁待扫描，不能作为今天的正式研究选择依据')
    }

    if (!decision) return

    if (decision.buyBeforeGateStatus && decision.buyBeforeGateStatus !== 'research_ready') {
      [
        ...(decision.buyBeforeGateHardBlocks || []),
        ...(decision.buyBeforeGateCautionFlags || []),
      ].filter(Boolean).forEach((reason) => addReason(report, reason))
    }

    if (decision.replayEvidenceGateStatus && decision.replayEvidenceGateStatus !== 'pass') {
      const replayReasons = [
        decision.replayEvidenceGateLabel ? `测算证据门禁：${decision.replayEvidenceGateLabel}` : '',
        ...(decision.replayEvidenceGateMissingEvidence || []),
      ].filter(Boolean)
      ;(replayReasons.length ? replayReasons : ['测算证据门禁未通过，需重跑真实净值、费率、回撤预算回放'])
        .forEach((reason) => addReason(report, reason))
    }
  })

  return Array.from(groups.values())
    .map((group) => {
      const codes = Array.from(group.codes).slice(0, 20)
      return {
        key: group.key,
        title: group.title,
        action: group.action,
        detail: group.detail,
        tone: group.tone,
        count: group.count,
        codes,
        reasons: group.reasons,
        purchasePlan: group.purchasePlan,
        plannedAmount: group.plannedAmount,
        href: buyBeforeQueueHref(group.categoryKey, codes, group.purchasePlan, group.plannedAmount),
      }
    })
    .sort((left, right) => right.count - left.count)
}
