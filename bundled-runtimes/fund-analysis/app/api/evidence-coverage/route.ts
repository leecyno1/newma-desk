import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'
import { getEvidenceCoverage, type EvidenceCoveragePayload } from '@/lib/evidence-coverage'
import { getSalesRuleGaps, type SalesRuleGapsPayload } from '@/lib/sales-rule-gaps'
import { getSalesRuleImpact } from '@/lib/sales-rule-impact'
import { materialEvidenceHref } from '@/lib/research-platform/routes'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type SalesRuleUnlockPreview = {
  unlockableCount: number
  topScore: number | null
  averageScore: number
  topCodes: string[]
  missingItemBuckets: Array<{ label: string; count: number }>
  message: string
}

const strictInvestorSelectionPath = '/market?profile=balanced&horizon=1to3y&purchasePlan=sip&lens=score&eligibleOnly=true&minEvidenceGrade=B&sourceLimit=500&minScore=55'
const strictInvestorSelectionApiQuery = 'profile=balanced&horizon=1to3y&purchasePlan=sip&lens=score&eligibleOnly=true&minEvidenceGrade=B&sourceLimit=500&limit=120&minScore=55'

function errorText(error: unknown) {
  if (error instanceof Error) return error.message || error.name
  return String(error || '')
}

function isDatabaseUnavailable(error: unknown) {
  const text = errorText(error)
  return /ECONNREFUSED|database_unavailable|connection refused|5432|OperationalError/i.test(text)
}

async function getStrictSelectionUnlockPreview(origin: string) {
  try {
    const response = await fetch(`${origin}/api/market/research-candidates?${strictInvestorSelectionApiQuery}`, {
      cache: 'no-store',
    })
    if (!response.ok) return null
    const payload = await response.json().catch(() => null)
    return (payload?.filters?.salesRuleUnlockPreview || null) as SalesRuleUnlockPreview | null
  } catch (error) {
    console.error('读取严格选基解锁预览失败:', error)
    return null
  }
}

function buildBuyReadiness(
  coverage: EvidenceCoveragePayload,
  candidateSalesRuleGaps: SalesRuleGapsPayload | null,
  salesRuleUnlockPreview: SalesRuleUnlockPreview | null,
) {
  const requiredDimensions = coverage.dimensions.filter((dimension) => dimension.requiredBeforeBuy)
  const requiredDimensionMissing = requiredDimensions.reduce((sum, dimension) => {
    return sum + Math.max(0, dimension.total - dimension.covered)
  }, 0)
  const candidateTotal = candidateSalesRuleGaps?.totalMembers ?? null
  const blockedCandidateCount = candidateSalesRuleGaps?.gapCount ?? null
  const missingItemBuckets = Array.from(
    (candidateSalesRuleGaps?.gaps || []).reduce((bucket, gap) => {
      gap.missingItems.forEach((item) => {
        bucket.set(item, (bucket.get(item) || 0) + 1)
      })
      return bucket
    }, new Map<string, number>()),
  )
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, 'zh-CN'))
    .slice(0, 8)
  const topBlockedCodes = (candidateSalesRuleGaps?.gaps || []).slice(0, 12).map((gap) => ({
    windCode: gap.windCode,
    fundName: gap.fundName,
    missingCount: gap.missingCount,
    priority: gap.priority,
  }))
  const blockedCodes = Array.from(new Set((candidateSalesRuleGaps?.gaps || []).map((gap) => gap.windCode).filter(Boolean)))
  const salesRulesParams = new URLSearchParams()
  if (blockedCodes.length > 0) {
    salesRulesParams.set('codes', blockedCodes.join(','))
  }
  const unlockableCount = salesRuleUnlockPreview?.unlockableCount || 0
  const unlockMessage = unlockableCount > 0
    ? `按当前严格研究筛选条件，补齐销售规则后预计 ${unlockableCount} 只可重新进入研究复核评估；最高选基分 ${salesRuleUnlockPreview?.topScore ?? '-'}，平均 ${salesRuleUnlockPreview?.averageScore ?? 0}。`
    : '当前严格选基条件下，暂未发现只因销售规则硬缺口被过滤的基金。'

  if (!candidateSalesRuleGaps) {
    return {
      status: 'unknown',
      label: '研究清单门禁待核',
      message: '研究清单销售规则缺口暂时未读到，只能查看全市场覆盖率，不能判断研究候选是否可用。',
      candidateTotal,
      blockedCandidateCount,
      requiredDimensionMissing,
      missingItemBuckets,
      topBlockedCodes,
      salesRuleUnlockPreview,
      salesRulesHref: materialEvidenceHref(),
      strictInvestorSelectionHref: strictInvestorSelectionPath,
      expectedUnlock: '先恢复研究清单缺口读取，再按销售规则硬证据补齐。',
    }
  }

  if (candidateTotal === 0) {
    return {
      status: 'empty',
      label: '研究清单为空',
      message: '当前没有研究清单成员，需要先从基金筛选或全市场浏览加入研究候选。',
      candidateTotal,
      blockedCandidateCount,
      requiredDimensionMissing,
      missingItemBuckets,
      topBlockedCodes,
      salesRuleUnlockPreview,
      salesRulesHref: materialEvidenceHref(),
      strictInvestorSelectionHref: strictInvestorSelectionPath,
      expectedUnlock: '先建立研究清单，再做销售规则硬证据扫描。',
    }
  }

  if ((blockedCandidateCount || 0) > 0) {
    return {
      status: 'blocked',
      label: '研究门禁拦截',
      message: `研究清单 ${blockedCandidateCount}/${candidateTotal} 只基金存在销售规则硬缺口，严格研究筛选和正式研究复核报告会被拦截。`,
      candidateTotal,
      blockedCandidateCount,
      requiredDimensionMissing,
      missingItemBuckets,
      topBlockedCodes,
      salesRuleUnlockPreview,
      salesRulesHref: salesRulesParams.size ? materialEvidenceHref(salesRulesParams) : materialEvidenceHref(),
      strictInvestorSelectionHref: strictInvestorSelectionPath,
      expectedUnlock: `优先补齐 ${missingItemBuckets.slice(0, 4).map((item) => item.label).join('、') || '销售规则'}；${unlockMessage}`,
    }
  }

  return {
    status: 'ready',
    label: '研究清单销售规则通过',
    message: '当前研究清单未发现销售规则硬缺口，可以进入严格研究筛选；形成研究结论前仍需复核销售平台实时状态。',
    candidateTotal,
    blockedCandidateCount,
    requiredDimensionMissing,
    missingItemBuckets,
    topBlockedCodes,
    salesRuleUnlockPreview,
    salesRulesHref: materialEvidenceHref(),
    strictInvestorSelectionHref: strictInvestorSelectionPath,
    expectedUnlock: requiredDimensionMissing > 0
      ? '研究清单已过销售规则门禁；全市场覆盖缺口仍可作为后续数据治理队列。'
      : '研究清单和全市场研究硬证据均未发现统计缺口。',
  }
}

export async function GET(request: Request) {
  try {
    const origin = new URL(request.url).origin
    const [coverage, healthResponse, candidateSalesRuleGaps, salesRuleUnlockPreview, salesRuleImpact] = await Promise.all([
      getEvidenceCoverage(),
      fetch(`${backendApiBaseUrl}/api/data-health/summary?stale_hours=72`, {
        cache: 'no-store',
      }).catch(() => null),
      getSalesRuleGaps('candidate', 100).catch((gapError) => {
        console.error('读取研究清单销售规则缺口失败:', gapError)
        return null
      }),
      getStrictSelectionUnlockPreview(origin),
      getSalesRuleImpact().catch((impactError) => {
        console.error('读取销售规则适当性影响失败:', impactError)
        return null
      }),
    ])

    const dataHealth = healthResponse?.ok
      ? await healthResponse.json().catch(() => null)
      : null

    return NextResponse.json({
      ...coverage,
      dataHealth,
      candidateSalesRuleGaps,
      salesRuleImpact,
      buyReadiness: buildBuyReadiness(coverage, candidateSalesRuleGaps, salesRuleUnlockPreview),
    })
  } catch (error) {
    console.error('读取证据覆盖率失败:', error)
    if (isDatabaseUnavailable(error)) {
      return NextResponse.json(
        {
          error: '基金研究数据库不可用，请先启动 PostgreSQL 并确认本地基金库已导入。',
          code: 'database_unavailable',
        },
        { status: 503 },
      )
    }
    return NextResponse.json(
      { error: errorText(error) || '读取证据覆盖率失败', code: 'evidence_coverage_failed' },
      { status: 500 },
    )
  }
}
