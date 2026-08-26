'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  AlertCircle,
  CheckCircle2,
  Copy,
  DatabaseZap,
  Download,
  ExternalLink,
  RefreshCw,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import { canonicalResearchHref, materialEvidenceHref } from '@/lib/research-platform/routes'
import SchedulerAndPendingPanel from './SchedulerAndPendingPanel'

type CoverageLevel = 'strong' | 'partial' | 'weak'

type Dimension = {
  key: string
  label: string
  group: '基础研究' | '经理评价' | '研究复核' | '研究增强'
  covered: number
  total: number
  coverage: number
  level: CoverageLevel
  requiredBeforeBuy: boolean
  description: string
  actionHref: string
  actionLabel: string
}

type GapFund = {
  id: string
  windCode: string
  name: string
  type: string | null
  navDate: string | null
  updatedAt: string | null
  gapCount: number
  requiredGapCount: number
  gaps: string[]
}

type CandidateSalesRuleGap = {
  memberId?: string
  windCode: string
  fundName: string
  fundType: string
  status: string
  priority: 'high' | 'medium' | 'low'
  missingItems: string[]
  missingCount: number
  evidenceMissingCount: number
  evidenceScore: number | null
  purchaseGateLabel: string
  nextAction: string
}

type CandidateSalesRuleGapsPayload = {
  source: string
  status: string
  totalMembers: number
  gapCount: number
  gaps: CandidateSalesRuleGap[]
  summary: {
    high: number
    medium: number
    low: number
  }
}

type BuyReadinessStatus = 'ready' | 'blocked' | 'empty' | 'unknown'

type SalesRuleImpactPayload = {
  totalFunds: number
  source: string
  profiles: Array<{
    key: 'conservative' | 'balanced' | 'aggressive'
    label: string
    maxSalesRiskLevel: number
    matchedCount: number
    mismatchCount: number
    missingRiskCount: number
    knownRiskCount: number
    reopenableCount: number
    actionHref: string
  }>
  summary: {
    riskLevelKnownCount: number
    riskLevelMissingCount: number
    riskLevelCoverage: number
    totalReopenableSlots: number
  }
  nextActions: Array<{
    label: string
    detail: string
    href: string
    priority: 'high' | 'medium' | 'low'
  }>
}

type CoveragePayload = {
  totalFunds: number
  coverageScore: number
  generatedAt: string
  source: string
  dimensions: Dimension[]
  groupSummary: Array<{
    group: Dimension['group']
    averageCoverage: number
    missingCount: number
    requiredMissingCount: number
  }>
  priorityQueue: Array<{
    key: string
    label: string
    missing: number
    coverage: number
    requiredBeforeBuy: boolean
    actionHref: string
  }>
  gapFunds: GapFund[]
  dataHealth?: {
    recent_failed_count?: number
    stale_datasets?: Array<{ dataset?: string; status?: string; last_seen_at?: string }>
    latest_snapshots?: Array<{ dataset?: string; status?: string; finished_at?: string; started_at?: string }>
  } | null
  candidateSalesRuleGaps?: CandidateSalesRuleGapsPayload | null
  salesRuleImpact?: SalesRuleImpactPayload | null
  buyReadiness?: {
    status: BuyReadinessStatus
    label: string
    message: string
    candidateTotal: number | null
    blockedCandidateCount: number | null
    requiredDimensionMissing: number
    missingItemBuckets: Array<{ label: string; count: number }>
    topBlockedCodes: Array<{
      windCode: string
      fundName: string
      missingCount: number
      priority: 'high' | 'medium' | 'low'
    }>
    salesRuleUnlockPreview: {
      unlockableCount: number
      topScore: number | null
      averageScore: number
      topCodes: string[]
      missingItemBuckets: Array<{ label: string; count: number }>
      message: string
    } | null
    salesRulesHref: string
    strictInvestorSelectionHref: string
    expectedUnlock: string
  }
}

const groupOrder: Dimension['group'][] = ['基础研究', '经理评价', '研究复核', '研究增强']

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '0'
  return value.toLocaleString('zh-CN')
}

function formatTime(value: string | null | undefined) {
  if (!value) return '待补'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function formatCoverage(value: number) {
  if (value > 0 && value < 0.1) return '<0.1%'
  return `${value.toFixed(1)}%`
}

function levelClass(level: CoverageLevel) {
  if (level === 'strong') return 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100'
  if (level === 'partial') return 'bg-amber-50 text-amber-700 ring-1 ring-amber-100'
  return 'bg-rose-50 text-rose-700 ring-1 ring-rose-100'
}

function scoreTone(score: number) {
  if (score >= 80) return 'text-emerald-700'
  if (score >= 45) return 'text-amber-700'
  return 'text-rose-700'
}

function progressColor(level: CoverageLevel) {
  if (level === 'strong') return 'bg-emerald-500'
  if (level === 'partial') return 'bg-amber-500'
  return 'bg-rose-500'
}

function priorityClass(priority: CandidateSalesRuleGap['priority']) {
  if (priority === 'high') return 'bg-rose-50 text-rose-700 ring-1 ring-rose-100'
  if (priority === 'medium') return 'bg-amber-50 text-amber-700 ring-1 ring-amber-100'
  return 'bg-blue-50 text-blue-700 ring-1 ring-blue-100'
}

function readinessClass(status: BuyReadinessStatus) {
  if (status === 'ready') return 'border-emerald-200 bg-emerald-50'
  if (status === 'blocked') return 'border-rose-200 bg-rose-50'
  return 'border-amber-200 bg-amber-50'
}

function readinessTextClass(status: BuyReadinessStatus) {
  if (status === 'ready') return 'text-emerald-800'
  if (status === 'blocked') return 'text-rose-800'
  return 'text-amber-800'
}

function appendReturnTo(href: string, returnTo: string) {
  if (href.includes('returnTo=')) return href
  const separator = href.includes('?') ? '&' : '?'
  return `${href}${separator}returnTo=${encodeURIComponent(returnTo)}`
}

function withEvidenceCoverageReturn(href: string) {
  const canonicalHref = canonicalResearchHref(href)
  if (!canonicalHref.startsWith('/evidence-coverage')) return canonicalHref
  return appendReturnTo(canonicalHref, '/evidence-coverage')
}

function salesRulesHrefForEvidenceCoverage(codes: string[] = [], extraParams?: Record<string, string>) {
  const normalizedCodes = Array.from(new Set(codes.map((code) => code.trim().toUpperCase()).filter(Boolean)))
  const params = new URLSearchParams({ purchasePlan: 'sip', ...(extraParams || {}) })
  if (normalizedCodes.length) params.set('codes', normalizedCodes.join(','))
  return withEvidenceCoverageReturn(materialEvidenceHref(params))
}

export default function EvidenceCoverageClient() {
  const [payload, setPayload] = useState<CoveragePayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [activeGroup, setActiveGroup] = useState<Dimension['group'] | '全部'>('全部')
  const [remediationTsvStatus, setRemediationTsvStatus] = useState<'idle' | 'copied' | 'fallback'>('idle')

  const fetchCoverage = useCallback(async () => {
    try {
      setLoading(true)
      setErrorMessage(null)
      const response = await fetch('/api/evidence-coverage', { cache: 'no-store' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data.error || '证据覆盖率暂时不可用')
      }
      setPayload(data)
    } catch (error) {
      console.error('读取证据覆盖率失败:', error)
      setPayload(null)
      setErrorMessage(error instanceof Error ? error.message : '读取证据覆盖率失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void fetchCoverage()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [fetchCoverage])

  const filteredDimensions = useMemo(() => {
    if (!payload) return []
    if (activeGroup === '全部') return payload.dimensions
    return payload.dimensions.filter((item) => item.group === activeGroup)
  }, [activeGroup, payload])

  const requiredGapTotal = useMemo(() => {
    if (!payload) return 0
    return payload.dimensions
      .filter((item) => item.requiredBeforeBuy)
      .reduce((sum, item) => sum + Math.max(0, item.total - item.covered), 0)
  }, [payload])

  const staleDatasets = payload?.dataHealth?.stale_datasets || []
  const failedCount = Number(payload?.dataHealth?.recent_failed_count || 0)
  const candidateSalesRuleGaps = payload?.candidateSalesRuleGaps || null
  const salesRuleImpact = payload?.salesRuleImpact || null
  const evidenceCoverageReturnHref = '/evidence-coverage'
  const candidateGapCodes = useMemo(() => {
    return Array.from(new Set((candidateSalesRuleGaps?.gaps || []).map((gap) => gap.windCode).filter(Boolean)))
  }, [candidateSalesRuleGaps])
  const candidateSalesRulesHref = useMemo(() => {
    return salesRulesHrefForEvidenceCoverage(candidateGapCodes)
  }, [candidateGapCodes])
  const candidateMissingTotal = useMemo(() => {
    return (candidateSalesRuleGaps?.gaps || []).reduce((sum, gap) => sum + gap.missingCount, 0)
  }, [candidateSalesRuleGaps])
  const buyBeforeRemediationSteps = useMemo(() => {
    if (!payload) return []

    const blockedCandidateCount = payload.buyReadiness?.blockedCandidateCount ?? candidateSalesRuleGaps?.gapCount ?? 0
    const missingRiskCount = salesRuleImpact?.summary.riskLevelMissingCount ?? 0
    const weakDimensions = payload.priorityQueue
      .filter((item) => !item.requiredBeforeBuy && item.missing > 0)
      .slice(0, 3)
    const weakDimensionMissing = weakDimensions.reduce((sum, item) => sum + item.missing, 0)
    const firstWeakDimension = weakDimensions[0]

    return [
      {
        title: '第一优先级：研究清单销售规则',
        badge: '硬门禁',
        count: blockedCandidateCount,
        unit: '只基金',
        reason: '申购状态、费率、最低金额、限购、销售风险等级等字段缺失，会直接拦截严格筛选和正式报告。',
        actionLabel: '打开研究清单补证',
        href: candidateSalesRulesHref,
        className: blockedCandidateCount > 0
          ? 'border-rose-200 bg-rose-50'
          : 'border-emerald-200 bg-emerald-50',
        badgeClassName: blockedCandidateCount > 0
          ? 'bg-rose-600 text-white'
          : 'bg-emerald-600 text-white',
      },
      {
        title: '第二优先级：R1-R5 来源适当性',
        badge: '全市场',
        count: missingRiskCount,
        unit: '只待补',
        reason: 'R1-R5 缺失、无来源或来源过期时，无法判断基金是否适合保守、均衡、进取画像，匹配池会被迫收缩。',
        actionLabel: '补全市场风险来源',
        href: salesRulesHrefForEvidenceCoverage([], {
          scope: 'market',
          focus: 'risk_level',
          queueMode: 'high_score_missing_risk',
        }),
        className: missingRiskCount > 0
          ? 'border-amber-200 bg-amber-50'
          : 'border-emerald-200 bg-emerald-50',
        badgeClassName: missingRiskCount > 0
          ? 'bg-amber-600 text-white'
          : 'bg-emerald-600 text-white',
      },
      {
        title: '第三优先级：覆盖率薄弱维度',
        badge: '研究质量',
        count: weakDimensionMissing,
        unit: '项缺口',
        reason: weakDimensions.length
          ? `优先补 ${weakDimensions.map((item) => item.label).join('、')}，减少基金分析和经理评价里的证据空洞。`
          : '基础研究、基金分析和经理评价维度当前没有进入优先队列的薄弱缺口。',
        actionLabel: firstWeakDimension ? `处理${firstWeakDimension.label}` : '查看覆盖维度',
        href: firstWeakDimension ? withEvidenceCoverageReturn(firstWeakDimension.actionHref) : '/evidence-coverage',
        className: weakDimensionMissing > 0
          ? 'border-blue-200 bg-blue-50'
          : 'border-emerald-200 bg-emerald-50',
        badgeClassName: weakDimensionMissing > 0
          ? 'bg-blue-600 text-white'
          : 'bg-emerald-600 text-white',
      },
    ]
  }, [candidateSalesRuleGaps?.gapCount, candidateSalesRulesHref, payload, salesRuleImpact?.summary.riskLevelMissingCount])
  const evidenceGapRoiQueue = useMemo(() => {
    if (!payload) return []

    const unlockPreview = payload.buyReadiness?.salesRuleUnlockPreview || null
    const roiItems: Array<{
      key: string
      title: string
      badge: string
      impactCount: number
      unit: string
      reason: string
      actionLabel: string
      href: string
      sampleCodes: string[]
      hardGateRank: number
    }> = []

    if (unlockPreview) {
      roiItems.push({
        key: 'strict_selection_sales_rules',
        title: '严格选基销售规则清零',
        badge: '预计解锁研究候选',
        impactCount: unlockPreview.unlockableCount,
        unit: '只可重评',
        reason: unlockPreview.unlockableCount > 0
          ? `补齐申购、费率、赎回、限购、R1-R5 等硬字段后，严格选基可重新评估这些高分样本。最高选基分 ${unlockPreview.topScore ?? '-'}。`
          : '当前严格选基口径下，没有只因销售规则硬缺口被拦截的样本；仍需保持销售规则完整。',
        actionLabel: '补严格研究规则',
        href: candidateSalesRulesHref,
        sampleCodes: unlockPreview.topCodes || [],
        hardGateRank: 4,
      })
    }

    if (salesRuleImpact) {
      roiItems.push({
        key: 'market_risk_level',
        title: '全市场 R1-R5 来源背书',
        badge: '适当性槽位',
        impactCount: salesRuleImpact.summary.totalReopenableSlots || salesRuleImpact.summary.riskLevelMissingCount,
        unit: '个待判断',
        reason: `R1-R5 来源背书覆盖率 ${formatCoverage(salesRuleImpact.summary.riskLevelCoverage)}；缺失、无来源或来源过期时，稳健/均衡/进取匹配池不能推断通过。`,
        actionLabel: '补风险来源',
        href: salesRulesHrefForEvidenceCoverage([], {
          scope: 'market',
          focus: 'risk_level',
          queueMode: 'high_score_missing_risk',
        }),
        sampleCodes: [],
        hardGateRank: 3,
      })
    }

    ;(payload.buyReadiness?.missingItemBuckets || []).slice(0, 4).forEach((bucket) => {
      roiItems.push({
        key: `candidate_field_${bucket.label}`,
        title: `研究清单字段：${bucket.label}`,
        badge: '字段清零',
        impactCount: bucket.count,
        unit: '只研究候选',
        reason: `研究清单中 ${bucket.count} 只基金卡在“${bucket.label}”；字段补齐前不能进入正式研究候选或保存正式报告。`,
        actionLabel: '补该字段',
        href: candidateSalesRulesHref,
        sampleCodes: candidateGapCodes.slice(0, 6),
        hardGateRank: 2,
      })
    })

    payload.priorityQueue
      .filter((item) => !item.requiredBeforeBuy && item.missing > 0)
      .slice(0, 4)
      .forEach((item) => {
        roiItems.push({
          key: `weak_dimension_${item.key}`,
          title: `研究弱证据：${item.label}`,
          badge: '质量增益',
          impactCount: item.missing,
          unit: '项缺口',
          reason: `覆盖率 ${formatCoverage(item.coverage)}；补齐后减少筛选、横评和详情页中的“待补证”样本。`,
          actionLabel: `处理${item.label}`,
          href: withEvidenceCoverageReturn(item.actionHref),
          sampleCodes: [],
          hardGateRank: 1,
        })
      })

    return roiItems
      .filter((item) => item.impactCount > 0 || item.hardGateRank >= 3)
      .sort((left, right) =>
        right.hardGateRank - left.hardGateRank
        || right.impactCount - left.impactCount
        || left.title.localeCompare(right.title, 'zh-CN'),
      )
      .slice(0, 8)
  }, [candidateGapCodes, candidateSalesRulesHref, payload, salesRuleImpact])
  const remediationTsvCell = (value: unknown) => String(value ?? '').replace(/\t/g, ' ').replace(/\r?\n/g, ' ').trim()
  const buyBeforeRemediationTsv = [
    ['证据组', '优先级', '任务', '影响口径', '影响数量', '原因', '样本代码', '下一动作', '入口', '硬边界'].join('\t'),
    ...evidenceGapRoiQueue.map((item, index) => [
      '研究复核数据缺口 ROI 队列',
      index + 1,
      item.title,
      item.badge,
      `${item.impactCount} ${item.unit}`,
      item.reason,
      item.sampleCodes.join('、') || '',
      item.actionLabel,
      item.href,
      '缺口数量不是加分项；只有补齐真实来源字段后，基金才允许重新进入严格筛选、横向比较或正式研究复核报告路径。',
    ].map(remediationTsvCell).join('\t')),
    ...buyBeforeRemediationSteps.map((step, index) => [
      '研究复核补证作业队列',
      index + 1,
      step.title,
      step.badge,
      `${step.count} ${step.unit}`,
      step.reason,
      '',
      step.actionLabel,
      step.href,
      '销售规则硬缺口补齐前不能进入正式研究候选，不能保存正式研究复核报告；只能作为研究观察或补证样本。',
    ].map(remediationTsvCell).join('\t')),
    ['说明', '', '证据覆盖率补证清单', '基金研究模块', payload ? `覆盖分 ${payload.coverageScore.toFixed(1)}` : '', '只服务基金筛选、基金分析和基金经理评价；不输出申赎操作指令。', '', '按最高 ROI/最高优先级补证', '/evidence-coverage', 'R1-R5、销售规则、计划金额、净值回放、持仓和正式研究复核报告门禁未清零前，不形成研究建议。'].map(remediationTsvCell).join('\t'),
  ].join('\n')
  const downloadBuyBeforeRemediationTsv = () => {
    if (!payload) return
    const blob = new Blob([`\ufeff${buyBeforeRemediationTsv}`], { type: 'text/tab-separated-values;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `证据覆盖率_研究复核补证清单_${new Date().toISOString().slice(0, 10)}.tsv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }
  const copyBuyBeforeRemediationTsv = async () => {
    if (!payload) return
    try {
      if (!globalThis.navigator?.clipboard?.writeText) {
        throw new Error('clipboard unavailable')
      }
      await globalThis.navigator.clipboard.writeText(buyBeforeRemediationTsv)
      setRemediationTsvStatus('copied')
    } catch {
      downloadBuyBeforeRemediationTsv()
      setRemediationTsvStatus('fallback')
    }
    globalThis.setTimeout(() => setRemediationTsvStatus('idle'), 1800)
  }

  return (
    <div className="space-y-6">
      <SchedulerAndPendingPanel />
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start lg:justify-end">
        <button
          type="button"
          onClick={() => void fetchCoverage()}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-blue-200 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-60"
          disabled={loading}
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          刷新真实覆盖率
        </button>
      </div>

      {errorMessage ? (
        <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <AlertCircle className="mt-0.5 h-4 w-4" />
          <span>{errorMessage}</span>
        </div>
      ) : null}

      {loading && !payload ? (
        <div className="rounded-2xl bg-white p-8 text-sm text-gray-500 shadow">正在读取本地 PostgreSQL 证据覆盖率...</div>
      ) : null}

      {payload ? (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
            <div className="rounded-2xl bg-white p-5 shadow">
              <div className="text-xs text-gray-500">本地基金数</div>
              <div className="mt-2 text-3xl font-bold text-gray-900">{formatNumber(payload.totalFunds)}</div>
              <div className="mt-2 text-xs text-gray-500">{payload.source}</div>
            </div>
            <div className="rounded-2xl bg-white p-5 shadow">
              <div className="text-xs text-gray-500">加权覆盖分</div>
              <div className={`mt-2 text-3xl font-bold ${scoreTone(payload.coverageScore)}`}>
                {payload.coverageScore.toFixed(1)}
              </div>
              <div className="mt-2 text-xs text-gray-500">研究复核硬证据权重更高</div>
            </div>
            <div className="rounded-2xl bg-white p-5 shadow">
              <div className="text-xs text-gray-500">研究复核硬缺口</div>
              <div className="mt-2 text-3xl font-bold text-rose-700">{formatNumber(requiredGapTotal)}</div>
              <div className="mt-2 text-xs text-gray-500">申购状态、费率、限购、风险等级等</div>
            </div>
            <div className="rounded-2xl bg-white p-5 shadow">
              <div className="text-xs text-gray-500">数据健康</div>
              <div className={`mt-2 text-3xl font-bold ${failedCount || staleDatasets.length ? 'text-amber-700' : 'text-emerald-700'}`}>
                {failedCount || staleDatasets.length ? '待核' : '正常'}
              </div>
              <div className="mt-2 text-xs text-gray-500">生成：{formatTime(payload.generatedAt)}</div>
            </div>
          </div>

          {(failedCount > 0 || staleDatasets.length > 0) ? (
            <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              <ShieldAlert className="mt-0.5 h-4 w-4" />
              <span>
                数据健康有待核项：近 72 小时失败 {failedCount} 次，过期/失败数据集 {staleDatasets.length} 个。
                {staleDatasets.slice(0, 3).map((item) => ` ${item.dataset || '未知'}(${item.status || 'unknown'})`).join('；')}
              </span>
            </div>
          ) : (
            <div className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              <CheckCircle2 className="mt-0.5 h-4 w-4" />
              <span>后端数据健康接口可读取，当前没有返回过期或失败数据集。</span>
            </div>
          )}

          {payload.buyReadiness ? (
            <div className={`rounded-2xl border p-5 shadow-sm ${readinessClass(payload.buyReadiness.status)}`}>
              <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
                <div>
                  <div className="flex items-center gap-2">
                    {payload.buyReadiness.status === 'ready' ? (
                      <CheckCircle2 className="h-5 w-5 text-emerald-700" />
                    ) : (
                      <ShieldAlert className="h-5 w-5 text-rose-700" />
                    )}
                    <h2 className={`text-lg font-semibold ${readinessTextClass(payload.buyReadiness.status)}`}>
                      {payload.buyReadiness.label}
                    </h2>
                  </div>
                  <p className={`mt-2 max-w-4xl text-sm leading-6 ${readinessTextClass(payload.buyReadiness.status)}`}>
                    {payload.buyReadiness.message}
                  </p>
                  <p className="mt-2 text-sm text-gray-600">{payload.buyReadiness.expectedUnlock}</p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Link
                    href={withEvidenceCoverageReturn(payload.buyReadiness.salesRulesHref)}
                    className="inline-flex items-center gap-1 rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700"
                  >
                    补销售规则 <ExternalLink className="h-3.5 w-3.5" />
                  </Link>
                  <Link
                    href={payload.buyReadiness.strictInvestorSelectionHref}
                    className="inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                  跑研究筛选
                  </Link>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-4">
                <div className="rounded-xl bg-white/80 p-4">
                  <div className="text-xs text-gray-500">研究清单成员</div>
                  <div className="mt-1 text-2xl font-bold text-gray-900">{formatNumber(payload.buyReadiness.candidateTotal ?? 0)}</div>
                </div>
                <div className="rounded-xl bg-white/80 p-4">
                  <div className="text-xs text-gray-500">门禁拦截</div>
                  <div className={`mt-1 text-2xl font-bold ${payload.buyReadiness.status === 'blocked' ? 'text-rose-700' : 'text-emerald-700'}`}>
                    {formatNumber(payload.buyReadiness.blockedCandidateCount ?? 0)}
                  </div>
                </div>
                <div className="rounded-xl bg-white/80 p-4">
                  <div className="text-xs text-gray-500">全市场硬缺口</div>
                  <div className="mt-1 text-2xl font-bold text-amber-700">{formatNumber(payload.buyReadiness.requiredDimensionMissing)}</div>
                </div>
                <div className="rounded-xl bg-white/80 p-4">
                  <div className="text-xs text-gray-500">待补字段类型</div>
                  <div className="mt-1 text-2xl font-bold text-gray-900">{formatNumber(payload.buyReadiness.missingItemBuckets.length)}</div>
                </div>
              </div>

              {payload.buyReadiness.missingItemBuckets.length > 0 ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {payload.buyReadiness.missingItemBuckets.map((item) => (
                    <span key={item.label} className="rounded-full bg-white px-3 py-1 text-xs font-medium text-gray-700 ring-1 ring-gray-200">
                      {item.label} × {formatNumber(item.count)}
                    </span>
                  ))}
                </div>
              ) : null}

              {payload.buyReadiness.salesRuleUnlockPreview ? (
                <div className="mt-4 rounded-2xl border border-emerald-100 bg-white/80 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <div className="text-sm font-semibold text-emerald-900">补证后预计解锁</div>
                      <p className="mt-1 text-xs leading-5 text-emerald-800">
                        {payload.buyReadiness.salesRuleUnlockPreview.message}
                      </p>
                    </div>
                    <Link
                      href={payload.buyReadiness.strictInvestorSelectionHref}
                      className="shrink-0 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-700"
                    >
                      补完后重跑
                    </Link>
                  </div>
                  <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-3">
                    <div className="rounded-xl bg-emerald-50 p-3">
                      <div className="text-xs text-emerald-700">可重新评估</div>
                      <div className="mt-1 text-xl font-bold text-emerald-900">
                        {formatNumber(payload.buyReadiness.salesRuleUnlockPreview.unlockableCount)} 只
                      </div>
                    </div>
                    <div className="rounded-xl bg-emerald-50 p-3">
                      <div className="text-xs text-emerald-700">最高选基分</div>
                      <div className="mt-1 text-xl font-bold text-emerald-900">
                        {payload.buyReadiness.salesRuleUnlockPreview.topScore ?? '-'}
                      </div>
                    </div>
                    <div className="rounded-xl bg-emerald-50 p-3">
                      <div className="text-xs text-emerald-700">平均选基分</div>
                      <div className="mt-1 text-xl font-bold text-emerald-900">
                        {payload.buyReadiness.salesRuleUnlockPreview.averageScore}
                      </div>
                    </div>
                  </div>
                  {payload.buyReadiness.salesRuleUnlockPreview.missingItemBuckets.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {payload.buyReadiness.salesRuleUnlockPreview.missingItemBuckets.slice(0, 6).map((item) => (
                        <span key={item.label} className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs text-emerald-800 ring-1 ring-emerald-100">
                          {item.label} × {formatNumber(item.count)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}

          <div
            className="rounded-2xl border border-cyan-100 bg-white p-5 shadow"
            data-testid="evidence-gap-roi-queue"
          >
            <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
              <div>
                <div className="flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-cyan-700" />
                  <h2 className="text-lg font-semibold text-gray-900">研究复核数据缺口 ROI 队列</h2>
                </div>
                <p className="mt-1 max-w-4xl text-sm leading-6 text-gray-500">
                  先补哪个字段最能解锁正式研究候选：按预计解锁研究候选、适当性槽位和硬门禁强度排序，只服务基金筛选、基金分析和基金经理评价的研究证据。
                </p>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void copyBuyBeforeRemediationTsv()}
                  className="inline-flex items-center gap-1 rounded-lg border border-cyan-200 bg-white px-4 py-2 text-sm font-medium text-cyan-800 hover:bg-cyan-50"
                  data-testid="evidence-remediation-tsv-copy"
                >
                  <Copy className="h-3.5 w-3.5" />
                  {remediationTsvStatus === 'copied' ? '已复制 TSV' : remediationTsvStatus === 'fallback' ? '已转下载 TSV' : '复制补证 TSV'}
                </button>
                <button
                  type="button"
                  onClick={downloadBuyBeforeRemediationTsv}
                  className="inline-flex items-center gap-1 rounded-lg border border-cyan-200 bg-white px-4 py-2 text-sm font-medium text-cyan-800 hover:bg-cyan-50"
                  data-testid="evidence-remediation-tsv-download"
                >
                  <Download className="h-3.5 w-3.5" />
                  下载补证 TSV
                </button>
                <Link
                  href={evidenceGapRoiQueue[0]?.href || candidateSalesRulesHref}
                  className="inline-flex items-center gap-1 rounded-lg bg-cyan-700 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-800"
                >
                  处理最高 ROI 缺口 <ExternalLink className="h-3.5 w-3.5" />
                </Link>
              </div>
            </div>
            <div className="mt-5 grid grid-cols-1 gap-3 xl:grid-cols-4">
              {evidenceGapRoiQueue.map((item, index) => (
                <div key={item.key} className="rounded-2xl border border-cyan-100 bg-cyan-50 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-xs font-semibold text-cyan-700">#{index + 1} · {item.badge}</div>
                      <div className="mt-1 font-semibold text-slate-950">{item.title}</div>
                    </div>
                    <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-cyan-800 ring-1 ring-cyan-100">
                      {formatNumber(item.impactCount)} {item.unit}
                    </span>
                  </div>
                  <p className="mt-3 min-h-20 text-xs leading-5 text-slate-700">{item.reason}</p>
                  {item.sampleCodes.length ? (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {item.sampleCodes.slice(0, 4).map((code) => (
                        <span key={`${item.key}-${code}`} className="rounded-full bg-white px-2 py-0.5 text-[11px] text-slate-600 ring-1 ring-cyan-100">
                          {code}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <Link
                    href={item.href}
                    className="mt-4 inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-cyan-800 ring-1 ring-cyan-100 hover:bg-cyan-100"
                  >
                    {item.actionLabel} <ExternalLink className="h-3 w-3" />
                  </Link>
                </div>
              ))}
              {evidenceGapRoiQueue.length === 0 ? (
                <div className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-700">
                  当前没有可排序的研究复核数据缺口；继续保持销售规则、R1-R5 和 NAV 回放复核。
                </div>
              ) : null}
            </div>
            <div className="mt-3 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-800">
              ROI 边界：缺口数量不是加分项；只有补齐真实来源字段后，基金才允许重新进入严格筛选、横向比较或正式研究复核报告路径。
            </div>
          </div>

          <div
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow"
            data-testid="evidence-buy-before-remediation-playbook"
          >
            <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
              <div>
                <div className="flex items-center gap-2">
                  <DatabaseZap className="h-5 w-5 text-slate-700" />
                  <h2 className="text-lg font-semibold text-gray-900">研究复核补证作业队列</h2>
                </div>
                <p className="mt-1 max-w-4xl text-sm leading-6 text-gray-500">
                  这不是展示用统计，而是按研究复核门禁排出来的处理顺序：先让研究清单可进入研究复核，再扩大适当性匹配池，最后补齐分析弱证据。
                </p>
                <p className="mt-2 text-sm font-medium text-rose-700">
                  销售规则硬缺口补齐前不能进入正式研究候选，不能保存正式研究复核报告；只能作为研究观察或补证样本。
                </p>
              </div>
              <Link
                href={candidateSalesRulesHref}
                className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
              >
                处理最高优先级 <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-3 lg:grid-cols-3">
              {buyBeforeRemediationSteps.map((step) => (
                <div key={step.title} className={`rounded-2xl border p-4 ${step.className}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-gray-900">{step.title}</div>
                      <div className="mt-2 flex items-end gap-2">
                        <span className="text-3xl font-bold text-gray-950">{formatNumber(step.count)}</span>
                        <span className="pb-1 text-xs text-gray-500">{step.unit}</span>
                      </div>
                    </div>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${step.badgeClassName}`}>
                      {step.badge}
                    </span>
                  </div>
                  <p className="mt-3 min-h-16 text-xs leading-5 text-gray-700">{step.reason}</p>
                  <Link
                    href={step.href}
                    className="mt-4 inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-gray-800 ring-1 ring-gray-200 hover:bg-gray-50"
                  >
                    {step.actionLabel} <ExternalLink className="h-3 w-3" />
                  </Link>
                </div>
              ))}
            </div>
          </div>

          {salesRuleImpact ? (
            <div className="rounded-2xl border border-emerald-100 bg-white p-5 shadow" data-testid="evidence-sales-rule-impact">
              <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
                <div>
                  <div className="flex items-center gap-2">
                    <ShieldAlert className="h-5 w-5 text-emerald-600" />
                    <h2 className="text-lg font-semibold text-gray-900">全市场适当性匹配影响</h2>
                  </div>
                  <p className="mt-1 max-w-4xl text-sm leading-6 text-gray-500">
                    这是销售规则门禁的全市场视角：R1-R5 没有销售平台/基金合同来源背书，或来源日期超过 30 天研究复核窗口时，基金不能进入稳健/均衡/进取匹配池。
                  </p>
                </div>
                <Link
                  href={salesRulesHrefForEvidenceCoverage([], {
                    scope: 'market',
                    focus: 'risk_level',
                    queueMode: 'high_score_missing_risk',
                  })}
                  className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
                >
                  补全市场风险来源 <ExternalLink className="h-3.5 w-3.5" />
                </Link>
              </div>

              <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-4">
                <div className="rounded-xl bg-emerald-50 p-4">
                  <div className="text-xs text-emerald-700">全市场基金</div>
                  <div className="mt-1 text-2xl font-bold text-emerald-900">{formatNumber(salesRuleImpact.totalFunds)}</div>
                </div>
                <div className="rounded-xl bg-amber-50 p-4">
                  <div className="text-xs text-amber-700">风险来源待补</div>
                  <div className="mt-1 text-2xl font-bold text-amber-900">{formatNumber(salesRuleImpact.summary.riskLevelMissingCount)}</div>
                </div>
                <div className="rounded-xl bg-blue-50 p-4">
                  <div className="text-xs text-blue-700">风险来源覆盖率</div>
                  <div className="mt-1 text-2xl font-bold text-blue-900">{formatCoverage(salesRuleImpact.summary.riskLevelCoverage)}</div>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <div className="text-xs text-slate-500">潜在解锁槽位</div>
                  <div className="mt-1 text-2xl font-bold text-slate-900">{formatNumber(salesRuleImpact.summary.totalReopenableSlots)}</div>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
                {salesRuleImpact.profiles.map((profile) => (
                  <div key={profile.key} className="rounded-xl border border-gray-100 bg-slate-50 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold text-gray-900">{profile.label}</div>
                        <div className="mt-1 text-xs text-gray-500">最高可接受 R{profile.maxSalesRiskLevel}</div>
                      </div>
                      <Link href={`/market?salesRiskFilter=matched&profile=${profile.key}&sortBy=screeningScore&sortOrder=desc`} className="rounded-lg bg-white px-2.5 py-1.5 text-xs font-medium text-emerald-700 ring-1 ring-emerald-100 hover:bg-emerald-50">
                        看匹配池
                      </Link>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                      <div className="rounded-lg bg-white px-2 py-2">
                        <div className="text-gray-500">已匹配</div>
                        <div className="mt-1 text-base font-bold text-emerald-700">{formatNumber(profile.matchedCount)}</div>
                      </div>
                      <div className="rounded-lg bg-white px-2 py-2">
                        <div className="text-gray-500">不匹配</div>
                        <div className="mt-1 text-base font-bold text-rose-700">{formatNumber(profile.mismatchCount)}</div>
                      </div>
                      <div className="rounded-lg bg-white px-2 py-2">
                        <div className="text-gray-500">待补</div>
                        <div className="mt-1 text-base font-bold text-amber-700">{formatNumber(profile.missingRiskCount)}</div>
                      </div>
                    </div>
                    <div className="mt-3 text-xs leading-5 text-gray-600">
                      补完后可重新判断 {formatNumber(profile.reopenableCount)} 只基金是否适合该画像。
                    </div>
                    <Link href={withEvidenceCoverageReturn(profile.actionHref)} className="mt-3 inline-flex rounded-lg bg-amber-600 px-3 py-2 text-xs font-semibold text-white hover:bg-amber-700">
                      打开补证队列
                    </Link>
                  </div>
                ))}
              </div>

              <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
                {salesRuleImpact.nextActions.map((action) => (
                  <Link
                    key={`${action.label}-${action.href}`}
                    href={withEvidenceCoverageReturn(action.href)}
                    className={`rounded-xl p-3 text-xs leading-5 ring-1 ${
                      action.priority === 'high'
                        ? 'bg-amber-50 text-amber-900 ring-amber-100 hover:bg-amber-100'
                        : action.priority === 'medium'
                          ? 'bg-blue-50 text-blue-900 ring-blue-100 hover:bg-blue-100'
                          : 'bg-slate-50 text-slate-800 ring-slate-100 hover:bg-slate-100'
                    }`}
                  >
                    <div className="font-semibold">{action.label}</div>
                    <div className="mt-1 opacity-80">{action.detail}</div>
                  </Link>
                ))}
              </div>
            </div>
          ) : null}

          <div className="rounded-2xl border border-rose-100 bg-white p-5 shadow">
            <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
              <div>
                <div className="flex items-center gap-2">
                  <ShieldAlert className="h-5 w-5 text-rose-600" />
                  <h2 className="text-lg font-semibold text-gray-900">研究清单复核补证队列</h2>
                </div>
                <p className="mt-1 text-sm text-gray-500">
                  只看当前研究清单，不用全市场噪音；销售规则缺口没有真实来源就保持待补。
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link
                  href={candidateSalesRulesHref}
                  className="inline-flex items-center gap-1 rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700"
                >
                  批量补当前缺口 <ExternalLink className="h-3.5 w-3.5" />
                </Link>
                <Link
                  href={canonicalResearchHref('/pools?status=candidate')}
                  className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  回研究清单
                </Link>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-4">
              <div className="rounded-xl bg-rose-50 p-4">
                <div className="text-xs text-rose-600">待补基金</div>
                <div className="mt-1 text-2xl font-bold text-rose-700">{formatNumber(candidateSalesRuleGaps?.gapCount || 0)}</div>
              </div>
              <div className="rounded-xl bg-rose-50 p-4">
                <div className="text-xs text-rose-600">待补字段</div>
                <div className="mt-1 text-2xl font-bold text-rose-700">{formatNumber(candidateMissingTotal)}</div>
              </div>
              <div className="rounded-xl bg-amber-50 p-4">
                <div className="text-xs text-amber-600">高优先级</div>
                <div className="mt-1 text-2xl font-bold text-amber-700">{formatNumber(candidateSalesRuleGaps?.summary.high || 0)}</div>
              </div>
              <div className="rounded-xl bg-gray-50 p-4">
                <div className="text-xs text-gray-500">研究清单成员</div>
                <div className="mt-1 text-2xl font-bold text-gray-900">{formatNumber(candidateSalesRuleGaps?.totalMembers || 0)}</div>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-3">
              {(candidateSalesRuleGaps?.gaps || []).slice(0, 6).map((gap) => (
                <div key={gap.memberId || gap.windCode} className="rounded-xl border border-gray-100 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-gray-900">{gap.fundName || gap.windCode}</div>
                      <div className="mt-1 text-xs text-gray-500">{gap.windCode} · {gap.fundType || '未分类'}</div>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-xs ${priorityClass(gap.priority)}`}>
                      {gap.priority === 'high' ? '高' : gap.priority === 'medium' ? '中' : '低'}
                    </span>
                  </div>
                  <div className="mt-3 text-xs text-rose-700">{gap.nextAction}</div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {gap.missingItems.slice(0, 4).map((item) => (
                      <span key={item} className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                        {item}
                      </span>
                    ))}
                    {gap.missingItems.length > 4 ? (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">+{gap.missingItems.length - 4}</span>
                    ) : null}
                  </div>
                  <div className="mt-3 flex gap-3 text-xs font-medium">
                    <Link href={`/funds/${encodeURIComponent(gap.windCode)}`} className="text-blue-600 hover:text-blue-800">
                      看基金
                    </Link>
                    <Link href={salesRulesHrefForEvidenceCoverage([gap.windCode])} className="text-blue-600 hover:text-blue-800">
                      补销售规则
                    </Link>
                  </div>
                </div>
              ))}
              {candidateSalesRuleGaps && candidateSalesRuleGaps.gapCount === 0 ? (
                <div className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-700">当前研究清单没有销售规则缺口。</div>
              ) : null}
              {!candidateSalesRuleGaps ? (
                <div className="rounded-xl bg-amber-50 p-4 text-sm text-amber-700">研究清单缺口暂时未读到；全市场覆盖率仍可查看。</div>
              ) : null}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
            {payload.groupSummary
              .sort((left, right) => groupOrder.indexOf(left.group) - groupOrder.indexOf(right.group))
              .map((item) => (
                <button
                  key={item.group}
                  type="button"
                  onClick={() => setActiveGroup(item.group)}
                  className={`rounded-2xl border p-5 text-left shadow-sm transition ${
                    activeGroup === item.group ? 'border-blue-300 bg-blue-50' : 'border-transparent bg-white hover:border-blue-100'
                  }`}
                >
                  <div className="text-sm font-semibold text-gray-900">{item.group}</div>
                  <div className="mt-2 text-2xl font-bold text-gray-900">{item.averageCoverage.toFixed(1)}%</div>
                  <div className="mt-2 text-xs text-gray-500">
                    缺口 {formatNumber(item.missingCount)}
                    {item.requiredMissingCount > 0 ? `，研究复核硬缺口 ${formatNumber(item.requiredMissingCount)}` : ''}
                  </div>
                </button>
              ))}
          </div>

          <div className="rounded-2xl bg-white p-5 shadow">
            <div className="flex flex-col justify-between gap-3 md:flex-row md:items-center">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">证据维度覆盖</h2>
                <p className="mt-1 text-sm text-gray-500">低覆盖维度优先补证；红色标记是研究复核必须复核的销售端证据。</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {(['全部', ...groupOrder] as Array<Dimension['group'] | '全部'>).map((group) => (
                  <button
                    key={group}
                    type="button"
                    onClick={() => setActiveGroup(group)}
                    className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                      activeGroup === group ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    {group}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
              {filteredDimensions.map((item) => (
                <div key={item.key} className="rounded-xl border border-gray-100 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-gray-900">{item.label}</span>
                        <span className={`rounded-full px-2 py-0.5 text-xs ${levelClass(item.level)}`}>
                          {formatCoverage(item.coverage)}
                        </span>
                        {item.requiredBeforeBuy ? (
                          <span className="rounded-full bg-rose-50 px-2 py-0.5 text-xs text-rose-700 ring-1 ring-rose-100">
                            研究复核硬证据
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-sm text-gray-500">{item.description}</p>
                    </div>
                    <Link
                      href={item.requiredBeforeBuy ? candidateSalesRulesHref : withEvidenceCoverageReturn(item.actionHref)}
                      className="shrink-0 text-xs font-medium text-blue-600 hover:text-blue-800"
                    >
                      {item.actionLabel}
                    </Link>
                  </div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-gray-100">
                    <div className={`h-full ${progressColor(item.level)}`} style={{ width: `${Math.min(100, item.coverage)}%` }} />
                  </div>
                  <div className="mt-2 flex justify-between text-xs text-gray-500">
                    <span>已覆盖 {formatNumber(item.covered)}</span>
                    <span>缺口 {formatNumber(Math.max(0, item.total - item.covered))}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[0.9fr_1.1fr]">
            <div className="rounded-2xl bg-white p-5 shadow">
              <div className="flex items-center gap-2">
                <DatabaseZap className="h-5 w-5 text-blue-600" />
                <h2 className="text-lg font-semibold text-gray-900">补证优先队列</h2>
              </div>
              <div className="mt-4 space-y-3">
                {payload.priorityQueue.map((item, index) => (
                  <div key={item.key} className="rounded-xl border border-gray-100 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-gray-900">
                          {index + 1}. {item.label}
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          缺口 {formatNumber(item.missing)}，覆盖率 {formatCoverage(item.coverage)}
                          {item.requiredBeforeBuy ? '，研究复核必须补' : ''}
                        </div>
                      </div>
                      <Link
                        href={item.requiredBeforeBuy ? candidateSalesRulesHref : withEvidenceCoverageReturn(item.actionHref)}
                        className="inline-flex items-center gap-1 rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100"
                      >
                        去处理 <ExternalLink className="h-3 w-3" />
                      </Link>
                    </div>
                  </div>
                ))}
                {payload.priorityQueue.length === 0 ? (
                  <div className="rounded-xl bg-emerald-50 p-4 text-sm text-emerald-700">当前没有统计到证据缺口。</div>
                ) : null}
              </div>
            </div>

            <div className="rounded-2xl bg-white p-5 shadow">
              <div className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-blue-600" />
                <h2 className="text-lg font-semibold text-gray-900">缺口基金样本</h2>
              </div>
              <div className="mt-4 overflow-hidden rounded-xl border border-gray-100">
                <table className="min-w-full divide-y divide-gray-100 text-sm">
                  <thead className="bg-gray-50 text-left text-xs text-gray-500">
                    <tr>
                      <th className="px-4 py-3 font-medium">基金</th>
                      <th className="px-4 py-3 font-medium">缺口</th>
                      <th className="px-4 py-3 font-medium">净值日</th>
                      <th className="px-4 py-3 font-medium">动作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white">
                    {payload.gapFunds.slice(0, 12).map((fund) => (
                      <tr key={fund.id}>
                        <td className="px-4 py-3">
                          <div className="font-medium text-gray-900">{fund.name || '名称待补'}</div>
                          <div className="text-xs text-gray-500">{fund.windCode} · {fund.type || '未分类'}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="text-xs text-rose-700">研究复核硬缺口 {fund.requiredGapCount}</div>
                          <div className="mt-1 flex max-w-md flex-wrap gap-1">
                            {fund.gaps.slice(0, 5).map((gap) => (
                              <span key={gap} className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                                {gap}
                              </span>
                            ))}
                            {fund.gaps.length > 5 ? (
                              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">+{fund.gaps.length - 5}</span>
                            ) : null}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-500">{fund.navDate || '待补'}</td>
                        <td className="px-4 py-3">
                          <div className="flex flex-col gap-2">
                            <Link href={`/market?search=${encodeURIComponent(fund.windCode)}`} className="text-xs font-medium text-blue-600 hover:text-blue-800">
                              市场页补证
                            </Link>
                            <Link href={salesRulesHrefForEvidenceCoverage([fund.windCode])} className="text-xs font-medium text-blue-600 hover:text-blue-800">
                              录销售规则
                            </Link>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {payload.gapFunds.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-4 py-8 text-center text-sm text-gray-500">没有发现缺口基金样本。</td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}
