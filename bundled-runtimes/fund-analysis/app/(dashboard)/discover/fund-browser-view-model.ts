import {
  asRecord,
  drawdownMetric,
  evidenceCoverage,
  formatPercent,
  peerReturnMetric,
  returnMetric,
  sharpeMetric,
  styleLabel,
  textValue,
  type SimpleFund,
} from '@/lib/simple-fund-view'

export const returnWindows = [
  { key: '6m', label: '近 6 月' },
  { key: '1y', label: '近 1 年' },
  { key: '3y', label: '近 3 年' },
] as const

export type SelectionRule = {
  key: string
  label: string
  text: string
  actualText: string
}

export type FundSelectionExplanation = {
  status: string
  headline: string
  classificationReason: string
  matchedRules: SelectionRule[]
  evidenceAsOf: string
  missingItems: string[]
}

export function normalizeSelectionRule(value: unknown): SelectionRule {
  const item = asRecord(value)
  return {
    key: textValue(item.key),
    label: textValue(item.label),
    text: textValue(item.text),
    actualText: textValue(item.actual_text, item.actualText),
  }
}

export function fundSelectionExplanation(fund: SimpleFund): FundSelectionExplanation | null {
  const item = asRecord(fund.selectionExplanation)
  if (!textValue(item.headline)) return null
  const matchedRuleValues = item.matched_rules ?? item.matchedRules
  const missingItemValues = item.missing_items ?? item.missingItems
  return {
    status: textValue(item.status),
    headline: textValue(item.headline),
    classificationReason: textValue(item.classification_reason, item.classificationReason),
    matchedRules: (Array.isArray(matchedRuleValues) ? matchedRuleValues : []).map(normalizeSelectionRule).filter((rule) => rule.key),
    evidenceAsOf: textValue(item.evidence_as_of, item.evidenceAsOf),
    missingItems: (Array.isArray(missingItemValues) ? missingItemValues : []).map((entry) => textValue(entry)).filter(Boolean),
  }
}

export function fundStyleBadge(fund: SimpleFund) {
  const confirmedStyle = styleLabel(fund)
  if (confirmedStyle !== '风格待确认') return confirmedStyle
  const profile = asRecord(fund.researchProfile)
  const evidence = (Array.isArray(profile.styleTagEvidence) ? profile.styleTagEvidence : [])
    .map((item) => asRecord(item))
    .filter((item) => textValue(item.value))
  const priority = ['strong', 'context', 'classification']
  for (const evidenceLevel of priority) {
    const matches = evidence.filter((item) => textValue(item.evidenceLevel, item.evidence_level) === evidenceLevel)
    if (!matches.length) continue
    const labels = Array.from(new Set(matches.map((item) => textValue(item.value)).filter(Boolean))).slice(0, 2)
    const prefix = evidenceLevel === 'strong' ? '持仓风格' : evidenceLevel === 'context' ? '纪要风格' : '产品定位'
    return `${prefix}：${labels.join(' / ')}`
  }
  return confirmedStyle
}

export function peerRankLabel(rank: number | null, peerCount: number | null, percentile: number | null) {
  if (rank != null && peerCount != null && peerCount > 0) {
    const position = Math.max(1, Math.ceil((rank / peerCount) * 100))
    const band = position <= 50 ? `同类前 ${position}%` : `同类第 ${Math.round(rank)}`
    return `${band} · ${Math.round(rank)}/${Math.round(peerCount)}`
  }
  return percentile == null ? '同类位置待补' : `同类分位 ${Math.round(percentile)}`
}

export function fundBrowserSummary(fund: SimpleFund) {
  const metrics = returnWindows.map((window) => ({
    ...window,
    value: returnMetric(fund, window.key),
    peer: peerReturnMetric(fund, window.key),
  }))
  const ranked = metrics.filter((item) => item.peer.rank != null && item.peer.peerCount != null && Number(item.peer.peerCount) > 0)
  const leading = ranked.filter((item) => Number(item.peer.rank) / Number(item.peer.peerCount) <= 0.4)
  const drawdown = drawdownMetric(fund)
  const sharpe = sharpeMetric(fund)
  const coverage = Math.round(evidenceCoverage(fund))

  let highlight = '已有基础净值和分类信息，可继续查看详情。'
  if (leading.length >= 2) {
    highlight = `${leading.map((item) => item.label).join('、')}均位于同类前 40%。`
  } else if (leading.length === 1) {
    highlight = `${leading[0].label}位于${peerRankLabel(leading[0].peer.rank, leading[0].peer.peerCount, leading[0].peer.percentile)}。`
  } else if (sharpe != null && sharpe >= 1) {
    highlight = `近 1 年 Sharpe 为 ${sharpe.toFixed(2)}，风险调整后收益较好。`
  } else if (ranked.length) {
    const best = [...ranked].sort((left, right) => Number(left.peer.rank) / Number(left.peer.peerCount) - Number(right.peer.rank) / Number(right.peer.peerCount))[0]
    const bestPosition = Number(best.peer.rank) / Number(best.peer.peerCount)
    highlight = bestPosition <= 0.6
      ? `${best.label}在三个周期中相对较好，${peerRankLabel(best.peer.rank, best.peer.peerCount, best.peer.percentile)}。`
      : '三个观察周期均未进入同类前 50%，暂未发现明确业绩亮点。'
  }

  let risk = '同类位置数据不足，暂不能判断相对优劣。'
  if (drawdown != null && Math.abs(drawdown) >= 0.2) {
    risk = `近 1 年最大回撤为 ${formatPercent(drawdown)}，波动承受要求较高。`
  } else if (metrics.some((item) => item.value != null && Number(item.value) < 0)) {
    const negative = metrics.find((item) => item.value != null && Number(item.value) < 0)
    risk = `${negative?.label || '部分周期'}收益为负，需确认是否符合持有期限。`
  } else if (ranked.length < 3) {
    risk = `仅有 ${ranked.length} 个周期具备同类排名，长期稳定性证据不足。`
  } else if (coverage < 80) {
    risk = `数据完整度为 ${coverage}%，部分评价证据仍待补充。`
  } else if (drawdown != null) {
    risk = `近 1 年最大回撤为 ${formatPercent(drawdown)}，过往表现不代表未来。`
  }

  return { highlight, risk }
}
