import 'server-only'

import { backendApiBaseUrl, toCamelFund } from '@/lib/backend-api'
import { getEvidenceCoverage } from '@/lib/evidence-coverage'
import type {
  DailyCockpitAlert,
  DailyCockpitSelectedFund,
  DailyCockpitSource,
  DailyCockpitTask,
  DailyResearchCockpitSnapshot,
} from '@/lib/fund-research/contracts'
import { materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'
import { getSalesRuleGaps } from '@/lib/sales-rule-gaps'

type UnknownRecord = Record<string, unknown>

const REQUEST_TIMEOUT_MS = 7_000

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {}
}

function asRecordArray(value: unknown) {
  return Array.isArray(value) ? value.map(asRecord) : []
}

function textValue(value: unknown) {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function numberValue(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function errorMessage(value: unknown, fallback: string) {
  return value instanceof Error && value.message ? value.message : fallback
}

async function fetchBackend(path: string) {
  const response = await fetch(`${backendApiBaseUrl}${path}`, {
    cache: 'no-store',
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(textValue(asRecord(payload).detail) || textValue(asRecord(payload).error) || `HTTP ${response.status}`)
  }
  return payload
}

function alertFundCode(event: UnknownRecord) {
  const details = asRecord(event.details)
  return (
    textValue(details.wind_code) ||
    textValue(details.fund_code) ||
    textValue(event.fund_id)
  ).toUpperCase()
}

function normalizeAlerts(payload: unknown, selectedSymbol?: string) {
  const events = asRecordArray(asRecord(payload).events)
    .filter((event) => textValue(event.status) !== 'resolved')
  const severityOrder: Record<string, number> = { high: 0, medium: 1, low: 2 }
  events.sort((left, right) => {
    const leftSelected = alertFundCode(left) === selectedSymbol ? 0 : 1
    const rightSelected = alertFundCode(right) === selectedSymbol ? 0 : 1
    return leftSelected - rightSelected
      || (severityOrder[textValue(left.severity)] ?? 3) - (severityOrder[textValue(right.severity)] ?? 3)
  })

  const alerts: DailyCockpitAlert[] = events.slice(0, 6).map((event, index) => {
    const fundCode = alertFundCode(event)
    const severityValue = textValue(event.severity)
    const severity = severityValue === 'high' || severityValue === 'low' ? severityValue : 'medium'
    return {
      id: textValue(event.id) || `review-event-${index + 1}`,
      title: textValue(event.title) || '研究证据需要复核',
      detail: textValue(event.message) || '复核事件没有提供完整说明，请进入事件台账核验。',
      severity,
      fundCode: fundCode || undefined,
      href: fundCode ? reviewEventsHref({ codes: fundCode }) : reviewEventsHref(),
    }
  })

  return {
    alerts,
    unresolvedCount: events.length,
    highCount: events.filter((event) => textValue(event.severity) === 'high').length,
  }
}

function selectedFundSnapshot(payload: unknown): DailyCockpitSelectedFund {
  const root = asRecord(payload)
  const rawFund = Object.keys(asRecord(root.fund)).length ? asRecord(root.fund) : root
  const fund = toCamelFund(rawFund)
  const researchProfile = asRecord(fund.researchProfile)
  const trust = asRecord(fund.trust)
  const managers = asRecordArray(fund.managers)
    .map((manager) => textValue(manager.name))
    .filter(Boolean)

  return {
    id: fund.id || fund.windCode,
    symbol: fund.windCode,
    name: fund.name || fund.windCode,
    type: fund.type || '类型待补',
    nav: fund.nav,
    navDate: fund.navDate,
    totalAsset: fund.totalAsset,
    evidenceCoverage: numberValue(fund.evidenceCoverageScore),
    benchmark: textValue(researchProfile.primaryBenchmark) || '基准待核',
    peerGroup: textValue(researchProfile.peerGroup) || '同类组待核',
    styleLabel: textValue(researchProfile.styleLabel) || '风格待核',
    managers,
    dataQualityStatus: textValue(trust.dataQualityStatus) || 'unknown',
    dataAsOf: textValue(trust.dataAsOf) || textValue(fund.updatedAt) || null,
    detailHref: `/funds/${encodeURIComponent(fund.id || fund.windCode)}`,
  }
}

function latestHealthAsOf(payload: unknown) {
  const snapshots = asRecordArray(asRecord(payload).latest_snapshots)
  for (const snapshot of snapshots) {
    const value = textValue(snapshot.finished_at) || textValue(snapshot.started_at)
    if (value) return value
  }
  return undefined
}

function buildBrief(input: {
  errors: string[]
  blockedCandidateCount: number | null
  highAlertCount: number | null
  selectedFund: DailyCockpitSelectedFund | null
}) {
  if (input.errors.length >= 3) {
    return {
      label: '数据优先',
      title: '研究入口不完整，今天先恢复证据链。',
      detail: '多个研究数据源不可用。当前页面只展示已核验状态，不沿用旧结论，也不生成推测性评价。',
      tone: 'danger' as const,
    }
  }
  if ((input.highAlertCount || 0) > 0 || (input.blockedCandidateCount || 0) > 0) {
    return {
      label: '先补证',
      title: '硬证据仍在阻断研究推进。',
      detail: '优先处理高严重度复核事件和研究清单材料缺口，门槛清零后再进入同类评价或尽调。',
      tone: 'warning' as const,
    }
  }
  if (input.selectedFund) {
    return {
      label: '对象已定位',
      title: `${input.selectedFund.name} 已进入今日研究上下文。`,
      detail: '先核对数据时点、同类组和适配基准，再阅读绩效或持仓结论。',
      tone: 'neutral' as const,
    }
  }
  return {
    label: '研究就绪',
    title: '研究环境已就绪，先选择今天要推进的对象。',
    detail: '驾驶舱只呈现需要行动的变化；完整方法、证据和审计仍由九段式研究内核负责。',
    tone: 'positive' as const,
  }
}

export async function loadDailyResearchCockpit(input: {
  symbol?: string
} = {}): Promise<DailyResearchCockpitSnapshot> {
  const generatedAt = new Date().toISOString()
  const symbol = input.symbol?.trim().toUpperCase()
  const errors: string[] = []

  const [coverageResult, gapsResult, alertsResult, healthResult, fundResult] = await Promise.allSettled([
    getEvidenceCoverage(),
    getSalesRuleGaps('candidate', 120),
    fetchBackend('/api/alerts'),
    fetchBackend('/api/data-health/summary?stale_hours=72'),
    symbol ? fetchBackend(`/api/funds/${encodeURIComponent(symbol)}`) : Promise.resolve(null),
  ])

  const coverage = coverageResult.status === 'fulfilled' ? coverageResult.value : null
  if (coverageResult.status === 'rejected') errors.push(`证据覆盖：${errorMessage(coverageResult.reason, '读取失败')}`)
  const gaps = gapsResult.status === 'fulfilled' ? gapsResult.value : null
  if (gapsResult.status === 'rejected') errors.push(`研究清单：${errorMessage(gapsResult.reason, '读取失败')}`)
  const health = healthResult.status === 'fulfilled' ? asRecord(healthResult.value) : null
  if (healthResult.status === 'rejected') errors.push(`数据健康：${errorMessage(healthResult.reason, '读取失败')}`)
  const alertSummary = alertsResult.status === 'fulfilled'
    ? normalizeAlerts(alertsResult.value, symbol)
    : { alerts: [], unresolvedCount: null, highCount: null }
  if (alertsResult.status === 'rejected') errors.push(`复核事件：${errorMessage(alertsResult.reason, '读取失败')}`)

  let selectedFund: DailyCockpitSelectedFund | null = null
  if (symbol && fundResult.status === 'fulfilled' && fundResult.value) {
    selectedFund = selectedFundSnapshot(fundResult.value)
  } else if (symbol && fundResult.status === 'rejected') {
    errors.push(`研究对象 ${symbol}：${errorMessage(fundResult.reason, '读取失败')}`)
  }

  const tasks: DailyCockpitTask[] = []
  if (gaps && gaps.gapCount > 0) {
    const codes = gaps.gaps.slice(0, 30).map((gap) => gap.windCode).filter(Boolean)
    tasks.push({
      id: 'candidate-material-gates',
      title: '补齐研究清单硬证据',
      detail: `${gaps.gapCount}/${gaps.totalMembers} 只候选存在销售规则或来源缺口，其中 ${gaps.summary.high} 项为高优先级。`,
      href: materialEvidenceHref(codes.length ? { codes: codes.join(',') } : undefined),
      tone: gaps.summary.high > 0 ? 'danger' : 'warning',
      source: gaps.source || 'research-list-gates',
      actionId: 'fund.evidence.snapshot',
    })
  }
  for (const item of coverage?.priorityQueue.slice(0, 3) || []) {
    tasks.push({
      id: `coverage-${item.key}`,
      title: `修复${item.label}覆盖`,
      detail: `当前覆盖 ${item.coverage.toFixed(1)}%，仍有 ${item.missing.toLocaleString('zh-CN')} 个研究对象缺失。`,
      href: item.actionHref,
      tone: item.requiredBeforeBuy ? 'danger' : 'warning',
      source: coverage?.source || 'evidence-ledger',
      actionId: 'fund.evidence.snapshot',
    })
  }
  for (const alert of alertSummary.alerts.filter((item) => item.severity === 'high').slice(0, 2)) {
    tasks.push({
      id: `alert-${alert.id}`,
      title: alert.title,
      detail: alert.fundCode ? `${alert.fundCode} · ${alert.detail}` : alert.detail,
      href: alert.href,
      tone: 'danger',
      source: 'review-events',
    })
  }
  if (!symbol) {
    tasks.push({
      id: 'select-research-object',
      title: '选择今日研究对象',
      detail: '从研究清单或全市场研究库选择基金后，驾驶舱才会加载对象级证据与时点。',
      href: '/market?source=fund_daily_cockpit',
      tone: 'neutral',
      source: 'daily-cockpit',
    })
  }

  const staleDatasets = health ? asRecordArray(health.stale_datasets) : []
  const failedSyncCount = health ? numberValue(health.recent_failed_count) : null
  const sources: DailyCockpitSource[] = [
    {
      id: 'research-database',
      label: '基金研究业务库',
      detail: coverage ? `${coverage.totalFunds.toLocaleString('zh-CN')} 只基金纳入证据覆盖统计` : '业务库覆盖统计当前不可用',
      asOf: coverage?.generatedAt,
      status: coverage ? 'healthy' : 'unavailable',
    },
    {
      id: 'data-health',
      label: '数据同步与新鲜度',
      detail: health
        ? staleDatasets.length || (failedSyncCount || 0) > 0
          ? `${staleDatasets.length} 个陈旧数据集，${failedSyncCount || 0} 次近期同步失败`
          : '未发现陈旧数据集或近期同步失败'
        : '数据健康摘要当前不可用',
      asOf: health ? latestHealthAsOf(health) : undefined,
      status: !health ? 'unavailable' : staleDatasets.length || (failedSyncCount || 0) > 0 ? 'stale' : 'healthy',
    },
    {
      id: 'review-events',
      label: '研究复核事件',
      detail: alertsResult.status === 'fulfilled'
        ? `${alertSummary.unresolvedCount || 0} 个未解决事件，其中 ${alertSummary.highCount || 0} 个高严重度`
        : '复核事件当前不可用',
      status: alertsResult.status === 'fulfilled' ? 'healthy' : 'unavailable',
    },
  ]
  if (symbol) {
    sources.push({
      id: 'selected-fund',
      label: selectedFund ? `${selectedFund.name} 对象快照` : `${symbol} 对象快照`,
      detail: selectedFund ? `同类组：${selectedFund.peerGroup}；基准：${selectedFund.benchmark}` : '对象级数据当前不可用',
      asOf: selectedFund?.dataAsOf || undefined,
      status: selectedFund ? 'healthy' : 'unavailable',
    })
  }

  const blockedCandidateCount = gaps?.gapCount ?? null
  const highAlertCount = alertSummary.highCount
  const status = errors.length === 0 ? 'ready' : errors.length >= 4 ? 'unavailable' : 'partial'

  return {
    generatedAt,
    status,
    errors,
    brief: buildBrief({ errors, blockedCandidateCount, highAlertCount, selectedFund }),
    metrics: {
      totalFunds: coverage?.totalFunds ?? null,
      evidenceCoverage: coverage?.coverageScore ?? null,
      candidateCount: gaps?.totalMembers ?? null,
      blockedCandidateCount,
      unresolvedAlertCount: alertSummary.unresolvedCount,
      highAlertCount,
      staleDatasetCount: health ? staleDatasets.length : null,
      failedSyncCount,
    },
    selectedFund,
    tasks: tasks.slice(0, 7),
    alerts: alertSummary.alerts,
    sources,
  }
}
