import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'
import { normalizeBuyBeforeDecisionSummary } from '@/lib/report-buy-before-decision'
import { shortlistSourceDecisionCards } from '@/lib/report-shortlist-source-decisions'
import { getSalesRuleGapsForCodes } from '@/lib/sales-rule-gaps'
import { buildReportRiskLevelGatePolicy } from '@/lib/report-risk-level-gate-policy'
import { fetchActiveSalesRuleEvidenceAlertsForCodes } from '@/lib/sales-rule-review-alerts'
import {
  buildComparisonDecisiveAudit,
  normalizeComparisonWinLossLines,
  type ComparisonWinLossLine as ReportWinLossLine,
} from '@/lib/comparison-decisive-audit'
import { materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const reportTypeLabel = (reportType: string | null | undefined) => {
  if (reportType === 'fund_pool_gap_snapshot') return '研究清单补证快照'
  if (reportType === 'fund_pool_shortlist_report') return '研究清单报告'
  if (reportType === 'fund_pre_purchase_check') return '研究复核报告'
  if (reportType?.includes('comparison')) return '对比研究报告'
  if (reportType === 'fund_research_report') return '基金研究报告'
  if (reportType?.includes('manager')) return '基金经理研究报告'
  if (reportType?.includes('fund')) return '基金研究报告'
  return '研究报告'
}

const cleanReportContent = (content: string) =>
  content
    .replace(/^<!--[\s\S]*?-->\s*/u, '')
    .replace(/^好的[，,][\s\S]*?---\s*/u, '')
    .trim()

const asRecord = (value: unknown): Record<string, unknown> => {
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      return parsed && typeof parsed === 'object' ? parsed : {}
    } catch {
      return {}
    }
  }
  return value && typeof value === 'object' ? value as Record<string, unknown> : {}
}

const asStringArray = (value: unknown) =>
  Array.isArray(value)
    ? value.map((item) => String(item || '').trim().toUpperCase()).filter(Boolean)
    : []

const asTextArray = (value: unknown) =>
  Array.isArray(value)
    ? value.map((item) => String(item || '').trim()).filter(Boolean)
    : []

function shortlistDecisionCards(members: unknown[]) {
  return members
    .map((member) => {
      const record = asRecord(member)
      const card = asRecord(record.decisionCard)
      const salesRuleMissingCount = Number(record.salesRuleMissingCount || 0)
      const nextActions = Array.isArray(record.nextActions) ? record.nextActions.map((item) => String(item || '').trim()).filter(Boolean) : []
      const missingItems = Array.isArray(record.salesRuleMissingItems) ? record.salesRuleMissingItems.map((item) => String(item || '').trim()).filter(Boolean) : []
      const label = String(card.label || record.decisionLabel || '').trim()
      return {
        windCode: String(record.windCode || '').trim().toUpperCase(),
        fundName: String(record.fundName || record.windCode || '').trim(),
        label,
        primaryAction: String(card.primaryAction || nextActions[0] || (salesRuleMissingCount ? '优先补销售规则，再决定是否保留候选' : '回到研究清单复核研究证据')).trim(),
        reasons: Array.isArray(card.reasons) && card.reasons.length
          ? card.reasons.map((item) => String(item || '').trim()).filter(Boolean)
          : [
              salesRuleMissingCount ? `销售规则仍缺 ${salesRuleMissingCount} 项${missingItems.length ? `：${missingItems.slice(0, 3).join('、')}` : ''}` : '',
              nextActions[0] || '',
            ].filter(Boolean),
        reverseTriggers: Array.isArray(card.reverseTriggers) && card.reverseTriggers.length
          ? card.reverseTriggers.map((item) => String(item || '').trim()).filter(Boolean)
          : [
              salesRuleMissingCount ? '销售规则硬缺口清零，并记录来源日期与平台字段' : '',
              '补齐同类横评、成本证据和持有回放后重新生成研究清单',
            ].filter(Boolean),
      }
    })
    .filter((card) => card.windCode || card.fundName || card.label || card.primaryAction)
}

function executionAmountGateSummary(dataSources: Record<string, unknown>, generationParams: Record<string, unknown>) {
  const members = Array.isArray(dataSources.members) ? dataSources.members.map(asRecord) : []
  const gates = members
    .map((member) => ({
      windCode: stringValue(member.windCode).toUpperCase(),
      fundName: stringValue(member.fundName || member.windCode),
      gate: asRecord(member.executionAmountGate),
    }))
    .filter((item) => stringValue(item.gate.status))
  const plannedAmount = reportPlannedAmount(dataSources, generationParams)
  if (!gates.length && !plannedAmount) return null

  const blocked = gates.filter((item) => item.gate.status === 'blocked')
  const unknown = gates.filter((item) => item.gate.status === 'unknown')
  const first = blocked[0] || unknown[0] || gates[0] || null
  const status = blocked.length ? 'blocked' : unknown.length ? 'unknown' : 'pass'
  return {
    status,
    label: stringValue(first?.gate.label) || (status === 'pass' ? '计划金额可执行' : status === 'blocked' ? '计划金额不可执行' : '计划金额待核'),
    detail: stringValue(first?.gate.detail) || (plannedAmount ? `报告计划金额 ${plannedAmount.toLocaleString('zh-CN')} 元；需结合销售规则实时复核。` : '报告未记录计划金额，不能判断起购、定投起点或限购约束。'),
    plannedAmount: plannedAmount ?? numberValue(first?.gate.plannedAmount),
    blockedCount: blocked.length,
    totalCount: gates.length,
    blockedFunds: blocked.slice(0, 5).map((item) => ({
      windCode: item.windCode,
      fundName: item.fundName,
      label: stringValue(item.gate.label),
      detail: stringValue(item.gate.detail),
    })),
  }
}

const stringValue = (value: unknown) => {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

const numberValue = (value: unknown) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const percentText = (value: unknown) => {
  const parsed = numberValue(value)
  return parsed === null ? '待补' : `${(parsed * 100).toFixed(2)}%`
}

const countText = (value: unknown, unit = '项') => {
  const parsed = numberValue(value)
  return parsed === null ? '待补' : `${parsed}${unit}`
}

type EvidenceCardTone = 'emerald' | 'amber' | 'rose' | 'blue' | 'slate' | 'purple'

type EvidenceCard = {
  label: string
  value: string
  detail: string
  tone: EvidenceCardTone
}

function modeLabel(mode: string, reportType: string) {
  if (mode === 'deterministic_evidence_backed') return '本地证据报告'
  if (mode === 'deterministic_pre_purchase_check') return '研究复核'
  if (mode === 'deterministic_fund_comparison') return '横向比较'
  if (mode === 'deterministic_fund_pool_shortlist') return '研究清单'
  if (mode === 'deterministic_fund_pool_gap_snapshot') return '补证快照'
  return reportTypeLabel(reportType)
}

function generationSourceLabel(mode: string, fallback: string) {
  if (mode === 'llm') return fallback
  if (mode === 'deterministic_evidence_backed') return '本地证据报告'
  if (mode === 'deterministic_pre_purchase_check') return '本地研究复核'
  if (mode === 'deterministic_fund_comparison') return '本地横向比较'
  if (mode === 'deterministic_fund_pool_shortlist') return '本地短名单核查'
  if (mode === 'deterministic_fund_pool_gap_snapshot') return '本地补证快照'
  return fallback
}

function reportWinLossLines(dataSources: Record<string, unknown>): ReportWinLossLine[] {
  const summary = asRecord(dataSources.summary)
  return [
    ...normalizeComparisonWinLossLines(dataSources.alternativeWinLossLines),
    ...normalizeComparisonWinLossLines(dataSources.decisionWinLossLines),
    ...normalizeComparisonWinLossLines(summary.decisionWinLossLines),
  ]
}

function reportDecisiveAudit(dataSources: Record<string, unknown>, generationParams: Record<string, unknown>, winLossLines: ReportWinLossLine[]) {
  const summary = asRecord(dataSources.summary)
  const existingAudit = asRecord(generationParams.decisiveAudit || dataSources.decisiveAudit || summary.decisiveAudit)
  if (stringValue(existingAudit.title)) return existingAudit
  return buildComparisonDecisiveAudit(winLossLines)
}

function buildEvidenceSummary(
  payload: Record<string, unknown>,
  dataSources: Record<string, unknown>,
  generationParams: Record<string, unknown>,
  gate: Awaited<ReturnType<typeof currentSalesRuleGate>>,
) {
  const reportType = String(payload.report_type || '')
  const mode = stringValue(generationParams.mode)
  const cards: EvidenceCard[] = []
  const warnings: string[] = []
  const nextActions: string[] = []
  const context = asRecord(dataSources.investorContext)
  const summary = asRecord(dataSources.summary)
  const verdict = asRecord(dataSources.verdict)
  const simulation = asRecord(dataSources.purchaseSimulation)
  const feeEstimate = asRecord(dataSources.feeEstimate)
  const holdings = asRecord(dataSources.holdingEvidence)
  const holdingExposure = asRecord(dataSources.holdingExposureDecision)
  const buyBeforeDecision = normalizeBuyBeforeDecisionSummary(dataSources.buy_before_decision, {
    content: String(payload.content || ''),
    summary,
  })
  const alternatives = asRecord(dataSources.alternativeEvidence)
  const alternativeDecision = asRecord(dataSources.alternativeDecision)
  const fund = asRecord(dataSources.fund)
  const sourceItems = Array.isArray(dataSources.items) ? dataSources.items.map(asRecord) : []
  const members = Array.isArray(dataSources.members) ? dataSources.members.map(asRecord) : []
  const decisionCards = shortlistDecisionCards(Array.isArray(dataSources.members) ? dataSources.members : [])
  const sourceDecisionCards = shortlistSourceDecisionCards(Array.isArray(dataSources.members) ? dataSources.members : [], {
    content: String(payload.content || ''),
  })
  const amountGate = executionAmountGateSummary(dataSources, generationParams)
  const currentContext = [
    stringValue(context.profile) || stringValue(generationParams.profile),
    stringValue(context.horizon) || stringValue(generationParams.horizon),
    stringValue(context.purchasePlan) || stringValue(generationParams.purchasePlan),
  ].filter(Boolean).join(' · ')

  cards.push({
    label: '生成口径',
    value: modeLabel(mode, reportType),
    detail: mode === 'llm'
      ? [
          stringValue(generationParams.provider),
          stringValue(generationParams.model),
          stringValue(generationParams.generatedAt),
        ].filter(Boolean).join(' · ') || '模型增强报告'
      : '由本地 Tushare 入库字段生成，未冒充模型结论',
    tone: 'slate',
  })

  if (currentContext) {
    cards.push({
      label: '研究画像',
      value: currentContext,
      detail: '报告结论必须放在该画像、持有期限和研究方式下阅读。',
      tone: 'blue',
    })
  }

  if (gate) {
    cards.push({
      label: '当前销售规则门禁',
      value: gate.status === 'ready' ? '无硬缺口' : gate.status === 'blocked' ? `仍缺 ${gate.missingCount ?? 0} 项` : '待扫描',
      detail: gate.status === 'blocked'
        ? `${gate.blockedFunds ?? 0} 只基金受影响；${gate.missingItems.slice(0, 5).join('、') || '销售规则待补'}`
        : gate.source || '本地合并销售规则',
      tone: gate.status === 'ready' ? 'emerald' : gate.status === 'blocked' ? 'amber' : 'slate',
    })
    if (gate.status === 'blocked') {
      warnings.push('销售规则硬缺口未补齐前，报告只能回看，不能作为继续研究复核的正式留痕。')
      nextActions.push('先补齐销售规则，再重新生成正式报告。')
    }
  }

  if (buyBeforeDecision) {
    const gateStatus = buyBeforeDecision.status
    const hardBlocks = buyBeforeDecision.hardBlocks
    const cautionFlags = buyBeforeDecision.cautionFlags
    const decisionNextActions = buyBeforeDecision.nextActions
    cards.push({
      label: '研究复核总闸门',
      value: buyBeforeDecision.label || gateStatus || '待补',
      detail: hardBlocks[0] || cautionFlags[0] || decisionNextActions[0] || '总闸门只用于基金研究分流，不构成申赎建议。',
      tone: gateStatus === 'blocked_by_hard_gate' ? 'rose' : gateStatus === 'verify_first' ? 'amber' : gateStatus === 'research_ready' ? 'emerald' : 'slate',
    })
    warnings.push(...hardBlocks.slice(0, 3))
    nextActions.push(...decisionNextActions.slice(0, 3))
  }

  if (reportType === 'fund_pre_purchase_check') {
    cards.push({
      label: '基金与结论',
      value: stringValue(verdict.label) || stringValue(generationParams.verdict) || '结论待补',
      detail: `${stringValue(fund.name) || stringValue(payload.target_id)} · 证据等级 ${stringValue(verdict.evidenceGrade) || stringValue(generationParams.evidenceGrade) || '待补'}`,
      tone: stringValue(verdict.label).includes('暂不') ? 'rose' : 'emerald',
    })

    if (Object.keys(simulation).length) {
      cards.push({
        label: '真实净值回放',
        value: `${countText(simulation.months || generationParams.months, '个月')} · ${countText(simulation.observations, '条')}`,
        detail: `一次性 ${stringValue(simulation.lumpSumAmount) || '待补'}；定投 ${stringValue(simulation.monthlyAmount) || '待补'}。`,
        tone: 'purple',
      })
    }

    if (Object.keys(feeEstimate).length) {
      cards.push({
        label: '费用后口径',
        value: `一次性 ${percentText(feeEstimate.lumpSumNetReturn || generationParams.lumpSumNetReturn)} / 定投 ${percentText(feeEstimate.sipNetReturn || generationParams.sipNetReturn)}`,
        detail: `申购费 ${percentText(feeEstimate.purchaseFeeRate || generationParams.purchaseFeeRate)}；赎回费 ${percentText(feeEstimate.redemptionFeeRate || generationParams.redemptionFeeRate)}。`,
        tone: 'amber',
      })
    }

    if (Object.keys(holdings).length) {
      cards.push({
        label: '持仓证据',
        value: stringValue(holdings.status) || '待补',
        detail: `${stringValue(holdings.quarter) || '季度待补'} · ${countText(holdings.holdings, '条持仓')}；${stringValue(holdings.note) || stringValue(holdings.source)}`,
        tone: stringValue(holdings.status) === 'available' ? 'emerald' : 'amber',
      })
    }

    if (Object.keys(holdingExposure).length) {
      const exposureLabel = stringValue(holdingExposure.label) || '持仓暴露待补'
      cards.push({
        label: '持仓暴露研究判断',
        value: `${exposureLabel} · ${stringValue(holdingExposure.score) || '待补'}分`,
        detail: [
          stringValue(holdingExposure.primaryRisk),
          stringValue(holdingExposure.nextAction),
        ].filter(Boolean).join('；') || '持仓暴露待补，不能解释行业/个股集中度。',
        tone: exposureLabel.includes('集中') ? 'amber' : exposureLabel.includes('待补') ? 'amber' : 'emerald',
      })
      const reverseTriggers = Array.isArray(holdingExposure.reverseTriggers)
        ? holdingExposure.reverseTriggers.map((item) => String(item || '').trim()).filter(Boolean)
        : []
      if (reverseTriggers.length) {
        warnings.push(`持仓暴露反转条件：${reverseTriggers.slice(0, 2).join('；')}`)
      }
      const nextAction = stringValue(holdingExposure.nextAction)
      if (nextAction) nextActions.push(nextAction)
    }

    if (Object.keys(alternatives).length) {
      cards.push({
        label: '替代候选',
        value: countText(alternatives.total, '只'),
        detail: stringValue(alternatives.note) || stringValue(alternatives.source) || '用于研究备选比较。',
        tone: 'blue',
      })
    }

    if (Object.keys(alternativeDecision).length) {
      const decisionStatus = stringValue(alternativeDecision.status)
      cards.push({
        label: '研究替代结论',
        value: stringValue(alternativeDecision.verdict) || '替代结论待补',
        detail: [
          stringValue(alternativeDecision.title),
          stringValue(alternativeDecision.next),
        ].filter(Boolean).join('；') || stringValue(alternativeDecision.detail) || '不要用单基金结论替代同画像横评。',
        tone: decisionStatus === 'compare_ready' ? 'emerald' : decisionStatus.includes('blocked') ? 'amber' : 'slate',
      })
      if (decisionStatus === 'blocked_primary') {
        warnings.push('主基金销售规则硬缺口未清零前，替代候选只作为研究观察，不能进入研究结论。')
      }
      if (decisionStatus === 'compare_ready') {
        nextActions.push('打开同画像横向比较，确认替代候选在收益、回撤、成本、经理和销售门禁上的差异。')
      }
    }
  }

  if (reportType.includes('comparison')) {
    const comparisonTotalFunds = numberValue(generationParams.totalFunds || summary.totalFunds) ?? sourceItems.length
    const rawDecisionReplayGateStatus = stringValue(generationParams.decisionReplayEvidenceGateStatus || summary.decisionReplayEvidenceGateStatus)
    const decisionReplayGateStatus = rawDecisionReplayGateStatus || 'missing'
    const replayGateVerifyCount = numberValue(generationParams.replayEvidenceGateVerifyCount || summary.replayEvidenceGateVerifyCount) ?? (decisionReplayGateStatus === 'missing' ? comparisonTotalFunds : 0)
    const replayGatePassCount = numberValue(generationParams.replayEvidenceGatePassCount || summary.replayEvidenceGatePassCount) ?? 0
    const rawDecisionReplayGateMissingEvidence = asTextArray(generationParams.decisionReplayEvidenceGateMissingEvidence || summary.decisionReplayEvidenceGateMissingEvidence)
    const decisionReplayGateMissingEvidence = rawDecisionReplayGateMissingEvidence.length
      ? rawDecisionReplayGateMissingEvidence
      : decisionReplayGateStatus === 'missing'
        ? ['测算采信门禁未标记', '需重跑真实净值、费率、回撤预算回放']
        : []
    cards.push({
      label: '决策排序口径',
      value: stringValue(generationParams.decisionFundName) || stringValue(summary.decisionFundName) || '待补',
      detail: `${stringValue(generationParams.decisionFundCode) || stringValue(summary.decisionFundCode)} · ${stringValue(generationParams.decisionBasis) || stringValue(summary.decisionBasis) || '综合排序'}`,
      tone: 'purple',
    })
    cards.push({
      label: '收益回放口径',
      value: percentText(generationParams.decisionReturn || summary.decisionReturn),
      detail: stringValue(generationParams.decisionReturnBasis) || '费后优先，否则真实净值回放。',
      tone: 'emerald',
    })
    cards.push({
      label: '测算证据门禁',
      value: decisionReplayGateStatus === 'missing'
        ? `旧横评缺门禁 · 全组 ${replayGateVerifyCount} 只待重跑`
        : decisionReplayGateStatus === 'pass'
        ? `首选通过 · 全组 ${replayGatePassCount} 只通过`
        : `首选待补 · 全组 ${replayGateVerifyCount} 只待补/只观察`,
      detail: decisionReplayGateStatus === 'missing'
        ? `旧横评未记录测算证据门禁；${decisionReplayGateMissingEvidence.slice(0, 5).join('、')}。重跑前只能回看，不能作为正式研究结论。`
        : decisionReplayGateMissingEvidence.length
        ? `首选缺口：${decisionReplayGateMissingEvidence.slice(0, 5).join('、')}；门禁未过的历史回放不能作为正式研究结论。`
        : '费用、回撤预算和回本等待均需随报告复核；门禁未过的历史回放不能作为正式研究结论。',
      tone: decisionReplayGateStatus === 'pass' && replayGateVerifyCount === 0 ? 'emerald' : 'amber',
    })
    if (decisionReplayGateStatus !== 'pass') {
      warnings.push(decisionReplayGateStatus === 'missing'
        ? '旧横评缺少测算证据门禁，不能作为今天的正式研究横评结论。'
        : '首选基金的测算证据门禁未通过，横评报告只能作为研究观察，不能作为正式研究结论。')
      nextActions.push('回到对比页重跑真实净值回放，并补齐费用、回撤预算和回本等待证据。')
    }
    cards.push({
      label: '费用可比性',
      value: `${countText(generationParams.feeComparableCount || summary.feeComparableCount, '只可比')} / ${countText(generationParams.feeGapCount || summary.feeGapCount, '只待补')}`,
      detail: sourceItems
        .filter((item) => stringValue(item.feeGapReason))
        .slice(0, 3)
        .map((item) => `${stringValue(item.windCode)} ${stringValue(item.feeGapReason)}`)
        .join('；') || '费用证据可用于横向比较。',
      tone: numberValue(generationParams.feeGapCount || summary.feeGapCount) ? 'amber' : 'emerald',
    })
  }

  if (reportType === 'fund_pool_shortlist_report' || reportType === 'fund_pool_gap_snapshot') {
    cards.push({
      label: '研究清单规模',
      value: countText(generationParams.totalMembers || summary.totalMembers, '只'),
      detail: `${countText(generationParams.readyCount || summary.readyCount, '只可推进')}；${countText(generationParams.verifyFirstCount || summary.verifyFirstCount, '只先核验')}；${countText(generationParams.blockedCount || summary.blockedCount, '只阻断')}`,
      tone: 'emerald',
    })
    cards.push({
      label: '销售规则缺口',
      value: countText(generationParams.salesRuleGapCount || summary.salesRuleGapCount, '只'),
      detail: `${countText(generationParams.highPriorityGapCount || summary.highPriorityGapCount, '只高优先级')}；样本 ${members.slice(0, 3).map((member) => stringValue(member.windCode)).filter(Boolean).join('、') || '待补'}`,
      tone: numberValue(generationParams.salesRuleGapCount || summary.salesRuleGapCount) ? 'amber' : 'emerald',
    })
    if (amountGate) {
      cards.push({
        label: '计划金额执行门禁',
        value: amountGate.plannedAmount ? `${amountGate.plannedAmount.toLocaleString('zh-CN')} 元 · ${amountGate.label}` : amountGate.label,
        detail: amountGate.blockedCount
          ? `${amountGate.blockedCount} 只金额不可执行：${amountGate.blockedFunds.map((fund) => fund.fundName || fund.windCode).filter(Boolean).join('、') || amountGate.detail}`
          : amountGate.detail,
        tone: amountGate.status === 'blocked' ? 'rose' : amountGate.status === 'unknown' ? 'amber' : 'emerald',
      })
      if (amountGate.status === 'blocked') nextActions.push('调整计划金额或补齐销售端起购/限购证据后，重新生成短名单报告。')
    }
    if (decisionCards.length) {
      const firstDecision = decisionCards[0]
      cards.push({
        label: '研究清单决策卡',
        value: firstDecision.label || '决策待补',
        detail: `${firstDecision.fundName || firstDecision.windCode}：${firstDecision.primaryAction || firstDecision.reasons[0] || '回到研究清单复核'}。反转条件：${firstDecision.reverseTriggers.slice(0, 2).join('；') || '持续复核销售规则、回撤和成本证据'}`,
        tone: firstDecision.label.includes('暂不') ? 'rose' : firstDecision.label.includes('补证') ? 'amber' : firstDecision.label.includes('可进入') ? 'emerald' : 'blue',
      })
      nextActions.push(`复核短名单决策卡：${firstDecision.fundName || firstDecision.windCode} · ${firstDecision.primaryAction || firstDecision.label}`)
    }
    if (sourceDecisionCards.length) {
      const firstSourceDecision = sourceDecisionCards[0]
      cards.push({
        label: '来源决策留痕',
        value: firstSourceDecision.label || '来源待补',
        detail: `${firstSourceDecision.fundName || firstSourceDecision.windCode}：${firstSourceDecision.latestConclusion || firstSourceDecision.nextAction || firstSourceDecision.bullets[0] || '回到来源页补筛选/榜单/横评依据'}。硬边界：${firstSourceDecision.hardBoundary || '销售规则、适当性、横评和研究证据未完成前，不进入正式研究候选。'}`,
        tone: firstSourceDecision.label.includes('待补') ? 'amber' : 'blue',
      })
      nextActions.push(`复核来源决策留痕：${firstSourceDecision.fundName || firstSourceDecision.windCode} · ${firstSourceDecision.nextAction || firstSourceDecision.label}`)
    }
  }

  if (!nextActions.length) {
    if (reportType.includes('comparison')) nextActions.push('回到对比页重跑矩阵，确认销售规则和费后回放仍然有效。')
    else if (reportType === 'fund_pre_purchase_check') nextActions.push('回到基金详情复核净值回放、费用和持仓证据。')
    else if (reportType === 'fund_pool_gap_snapshot') nextActions.push('补齐销售规则后，回到研究清单重新生成正式研究清单报告。')
    else if (reportType.includes('fund_pool')) nextActions.push('回到研究清单维护研究结论和下一轮横向比较。')
  }

  return {
    title: '结构化证据摘要',
    subtitle: '由保存报告时的本地数据源和当前销售规则门禁生成，不从正文 Markdown 猜测。',
    cards,
    warnings,
    nextActions,
  }
}

function isValidWindCode(value: string) {
  return /^[0-9A-Z]{6,12}\.(OF|SH|SZ|BJ)$/i.test(value.trim())
}

function uniqueValidCodes(codes: string[]) {
  return Array.from(new Set(codes.map((code) => code.trim().toUpperCase()).filter(isValidWindCode)))
}

function relatedReportCodes(payload: Record<string, unknown>, dataSources: Record<string, unknown>) {
  const items = Array.isArray(dataSources.items) ? dataSources.items : []
  const members = Array.isArray(dataSources.members) ? dataSources.members : []
  const fund = asRecord(dataSources.fund)
  const itemCodes = items.map((item) => String(asRecord(item).windCode || '').trim().toUpperCase())
  const memberCodes = members.map((member) => String(asRecord(member).windCode || '').trim().toUpperCase())
  const fundCode = String(fund.windCode || fund.wind_code || '').trim().toUpperCase()
  const targetId = String(payload.target_id || '').trim().toUpperCase()
  return uniqueValidCodes([
    targetId,
    fundCode,
    ...asStringArray(dataSources.codes),
    ...itemCodes,
    ...memberCodes,
  ])
}

function reportCodes(payload: Record<string, unknown>, dataSources: Record<string, unknown>) {
  const reportType = String(payload.report_type || '')
  const targetType = String(payload.target_type || '')
  if (targetType === 'fund' && reportType === 'fund_pre_purchase_check') {
    return relatedReportCodes(payload, dataSources).slice(0, 1)
  }
  if (targetType === 'comparison' || reportType.includes('comparison')) {
    return relatedReportCodes(payload, dataSources)
  }
  if (targetType === 'fund_pool' || reportType === 'fund_pool_shortlist_report' || reportType === 'fund_pool_gap_snapshot') {
    return relatedReportCodes(payload, dataSources)
  }
  return []
}

function reportPurchasePlan(dataSources: Record<string, unknown>, generationParams: Record<string, unknown>) {
  const context = asRecord(dataSources.investorContext)
  const summary = asRecord(dataSources.summary)
  const rawPlan = stringValue(dataSources.purchasePlan)
    || stringValue(context.purchasePlan)
    || stringValue(generationParams.purchasePlan)
    || stringValue(summary.purchasePlan)
  return rawPlan === 'lump_sum' || rawPlan === 'sip' ? rawPlan : null
}

function reportPlannedAmount(dataSources: Record<string, unknown>, generationParams: Record<string, unknown>) {
  const context = asRecord(dataSources.investorContext)
  const summary = asRecord(dataSources.summary)
  const amount = numberValue(dataSources.plannedAmount)
    ?? numberValue(generationParams.plannedAmount)
    ?? numberValue(summary.plannedAmount)
    ?? numberValue(context.plannedAmount)
  return amount && amount > 0 ? amount : null
}

function salesRulesHrefForCodes(codes: string[], purchasePlan: ReturnType<typeof reportPurchasePlan>, plannedAmount?: number | null) {
  const normalizedCodes = Array.from(new Set(codes.map((code) => String(code || '').trim().toUpperCase()).filter(Boolean)))
  const params = new URLSearchParams({ purchasePlan: purchasePlan || 'sip' })
  if (plannedAmount && plannedAmount > 0) params.set('plannedAmount', String(plannedAmount))
  if (normalizedCodes.length) params.set('codes', normalizedCodes.join(','))
  return materialEvidenceHref(params)
}

async function currentSalesRuleGate(payload: Record<string, unknown>, dataSources: Record<string, unknown>, generationParams: Record<string, unknown>) {
  const codes = reportCodes(payload, dataSources)
  if (!codes.length) return null
  const purchasePlan = reportPurchasePlan(dataSources, generationParams)
  const plannedAmount = reportPlannedAmount(dataSources, generationParams)
  try {
    const [gapPayload, activeSalesRuleEvidenceAlertsByCode] = await Promise.all([
      getSalesRuleGapsForCodes(codes, codes.length, {
        purchasePlan,
        plannedAmount,
      }),
      fetchActiveSalesRuleEvidenceAlertsForCodes(codes),
    ])
    const activeSalesRuleEvidenceAlerts = codes.flatMap((code) => activeSalesRuleEvidenceAlertsByCode.get(code.toUpperCase()) || [])
    const reviewAlertMissingItems = activeSalesRuleEvidenceAlerts.map((alert) => `复查队列未解决：${alert.fundCode}：${alert.title}${alert.message ? `（${alert.message}）` : ''}`)
    const missingItems = Array.from(new Set([
      ...reviewAlertMissingItems,
      ...(gapPayload.gaps || []).flatMap((gap) => gap.missingItems),
    ]))
    const reviewAlertBlocked = activeSalesRuleEvidenceAlerts.length > 0
    return {
      status: gapPayload.gapCount > 0 || reviewAlertBlocked ? 'blocked' : 'ready',
      missingCount: (gapPayload.gaps || []).reduce((sum, gap) => sum + gap.missingCount, 0) + activeSalesRuleEvidenceAlerts.length,
      missingItems,
      blockedFunds: Math.max(gapPayload.gapCount, new Set(activeSalesRuleEvidenceAlerts.map((alert) => alert.fundCode)).size),
      actionHref: reviewAlertBlocked ? reviewEventsHref() : salesRulesHrefForCodes(codes, purchasePlan, plannedAmount),
      source: reviewAlertBlocked ? `${gapPayload.source}+local.alert_events.sales_rule_evidence` : gapPayload.source,
    }
  } catch (error) {
    console.error('报告详情销售规则门禁读取失败:', error)
    return {
      status: 'unknown',
      missingCount: null,
      missingItems: [],
      blockedFunds: null,
      actionHref: salesRulesHrefForCodes(codes, purchasePlan, plannedAmount),
      source: 'explicit_codes_plus_local_sales_rules',
    }
  }
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    let response = await fetch(`${backendApiBaseUrl}/api/reports/${encodeURIComponent(id)}`, {
      cache: 'no-store',
    })
    let payload = await response.json().catch(() => ({}))

    if (!response.ok) {
      const researchResponse = await fetch(`${backendApiBaseUrl}/api/research-reports/${encodeURIComponent(id)}`, {
        cache: 'no-store',
      })
      const researchPayload = await researchResponse.json().catch(() => ({}))
      if (researchResponse.ok) {
        response = researchResponse
        payload = {
          id: researchPayload.id,
          target_type: researchPayload.manager_id ? 'manager' : 'research',
          target_id: researchPayload.manager_id || researchPayload.fund_ids?.[0] || '',
          report_type: 'uploaded_research_report',
          content: researchPayload.content || '',
          created_at: researchPayload.created_at || researchPayload.report_date,
          title: researchPayload.title,
          source: researchPayload.source,
          tags: researchPayload.tags || [],
          key_points: researchPayload.key_points || [],
          manager_id: researchPayload.manager_id || null,
          summary: researchPayload.summary || '',
        }
      }
    }

    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '报告不存在' },
        { status: response.status },
      )
    }

    const generationParams = asRecord(payload.generation_params)
    const dataSources = asRecord(payload.data_sources)
    const content = cleanReportContent(payload.content || '')
    const source = generationParams.provider || dataSources.source || 'PostgreSQL'
    const model = generationParams.model ? String(generationParams.model) : ''
    const mode = String(generationParams.mode || '')
    const sourceLabel = generationSourceLabel(mode, String(source))
    const targetType = String(payload.target_type || '')
    const targetLabel = targetType === 'fund'
      ? '基金'
      : targetType === 'fund_pool'
        ? '研究清单'
        : targetType === 'comparison'
          ? '基金对比'
          : targetType === 'manager'
            ? '基金经理'
            : '基金研究'
    const gate = await currentSalesRuleGate(payload, dataSources, generationParams)
    const purchasePlan = reportPurchasePlan(dataSources, generationParams) || 'sip'
    const plannedAmount = reportPlannedAmount(dataSources, generationParams)
    const amountGate = executionAmountGateSummary(dataSources, generationParams)
    const evidenceSummary = buildEvidenceSummary(payload, dataSources, generationParams, gate)
    const decisionCards = shortlistDecisionCards(Array.isArray(dataSources.members) ? dataSources.members : [])
    const sourceDecisionCards = shortlistSourceDecisionCards(Array.isArray(dataSources.members) ? dataSources.members : [], {
      content,
    })
    const winLossLines = reportWinLossLines(dataSources)
    const decisiveAudit = (targetType === 'comparison' || String(payload.report_type || '').includes('comparison'))
      ? reportDecisiveAudit(dataSources, generationParams, winLossLines)
      : null
    const buyBeforeDecision = normalizeBuyBeforeDecisionSummary(dataSources.buy_before_decision, {
      content,
      summary: asRecord(dataSources.summary),
    })
    const relatedCodes = relatedReportCodes(payload, dataSources)
    const riskLevelGatePolicy = buildReportRiskLevelGatePolicy({
      targetType: String(payload.target_type || ''),
      reportType: String(payload.report_type || ''),
      relatedCodes,
      createdAt: String(payload.created_at || ''),
      content,
      dataSources,
      generationParams,
    })

    return NextResponse.json({
      id: payload.id,
      title: payload.title || `${payload.target_id || ''} ${reportTypeLabel(payload.report_type)}`,
      content,
      summary: payload.summary || content.slice(0, 500),
      reportDate: payload.created_at,
      source: payload.source || (mode === 'llm' && model ? `${sourceLabel} · ${model}` : sourceLabel),
      targetId: payload.target_id || '',
      targetType: payload.target_type || '',
      reportType: payload.report_type || '',
      reportTypeLabel: reportTypeLabel(payload.report_type),
      purchasePlan,
      plannedAmount,
      relatedCodes,
      riskLevelGatePolicy,
      currentSalesRuleGate: gate,
      evidenceSummary,
      buyBeforeDecision,
      executionAmountGate: amountGate,
      purchaseDecisionCards: decisionCards.slice(0, 5),
      sourceDecisionCards: sourceDecisionCards.slice(0, 5),
      winLossLines: winLossLines.slice(0, 8),
      decisiveAudit,
      tags: payload.tags || [
        targetLabel,
        reportTypeLabel(payload.report_type),
        sourceLabel,
      ].filter(Boolean),
      keyPoints: payload.key_points || [],
      managerId: payload.manager_id || (payload.target_type === 'manager' ? payload.target_id : null),
      manager: null,
      createdAt: payload.created_at,
    })
  } catch (error) {
    console.error('获取本地基金研究报告失败:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '获取本地基金研究报告失败' },
      { status: 500 },
    )
  }
}

export async function PUT() {
  return NextResponse.json({ error: '本地生成报告暂不支持编辑' }, { status: 405 })
}

export async function DELETE() {
  return NextResponse.json({ error: '本地生成报告暂不支持删除' }, { status: 405 })
}
