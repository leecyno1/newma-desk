import { NextResponse } from 'next/server'
import postgres from 'postgres'
import { buildResearchListShortlistReport } from '@/lib/research-list-shortlist-report'
import { materialEvidenceHref, reviewEventsHref } from '@/lib/research-platform/routes'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const sql = postgres(process.env.DATABASE_URL || '', { max: 1 })

function jsonSafe(value: unknown) {
  return JSON.parse(JSON.stringify(value))
}

type ShortlistReport = Awaited<ReturnType<typeof buildResearchListShortlistReport>>
type PurchasePlan = 'lump_sum' | 'sip'

function purchasePlanParam(value: string | null): PurchasePlan {
  return value === 'lump_sum' || value === 'sip' ? value : 'sip'
}

function defaultPlannedAmountForPlan(purchasePlan: PurchasePlan) {
  return purchasePlan === 'lump_sum' ? 10000 : 1000
}

function plannedAmountParam(value: string | null, purchasePlan: PurchasePlan) {
  const amount = Number(value || '')
  return Number.isFinite(amount) && amount > 0 ? amount : defaultPlannedAmountForPlan(purchasePlan)
}

function gapSnapshotMarkdown(report: ShortlistReport) {
  return report.markdown
    .replace(/^# .+? · 研究短名单报告/u, `# ${report.pool.name} · 补证快照（非正式短名单）`)
    .replace(
      '- 本报告只用于基金研究和研究复核，不构成投资建议。',
      '- 本快照只用于补齐销售规则、同类横评、历史回放、成本证据和正式研究复核门禁，不是正式研究复核短名单报告。',
    )
}

function salesRuleGapBlockPayload(report: ShortlistReport) {
  const reviewAlertBlocked = report.members.some((member) =>
    member.salesRuleMissingItems.some((item) => item.includes('复查队列未解决')),
  )
  const salesRuleGaps = report.members
    .filter((member) => member.salesRuleMissingCount > 0)
    .map((member) => ({
      windCode: member.windCode,
      fundName: member.fundName,
      missingCount: member.salesRuleMissingCount,
      missingItems: member.salesRuleMissingItems,
    }))
  const gapCodes = Array.from(new Set(salesRuleGaps.map((gap) => gap.windCode).filter(Boolean)))
  return {
    error: reviewAlertBlocked
      ? `当前研究清单仍有未解决销售规则/R1-R5复查事件，不能生成正式研究复核短名单报告。`
      : `当前研究清单仍有 ${report.summary.salesRuleGapCount} 只基金销售规则待补，不能生成正式研究复核短名单报告。`,
    code: reviewAlertBlocked ? 'SALES_RULE_REVIEW_ALERT_BLOCKED' : 'SALES_RULE_GAP_BLOCKED',
    actionHref: reviewAlertBlocked ? reviewEventsHref() : materialEvidenceHref(gapCodes.length ? { codes: gapCodes.join(',') } : undefined),
    alertsHref: reviewAlertBlocked ? reviewEventsHref() : null,
    salesRuleGapCount: report.summary.salesRuleGapCount,
    highPriorityGapCount: report.summary.highPriorityGapCount,
    salesRuleGaps,
  }
}

function prePurchaseEvidenceBlockPayload(report: ShortlistReport) {
  return {
    error: `当前研究清单仍有 ${report.summary.prePurchaseEvidenceGapCount} 只基金研究证据未达标，不能生成正式研究复核短名单报告。`,
    code: 'PRE_PURCHASE_SHORTLIST_NOT_READY',
    actionHref: report.actionLinks.pool,
    verifyFirstCount: report.summary.verifyFirstCount,
    blockedCount: report.summary.blockedCount,
    prePurchaseEvidenceGapCount: report.summary.prePurchaseEvidenceGapCount,
    blockers: report.members
      .filter((member) => member.decisionBucket !== 'ready')
      .map((member) => ({
        windCode: member.windCode,
        fundName: member.fundName,
        decisionLabel: member.decisionLabel,
        nextActions: member.nextActions,
      })),
  }
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const { searchParams } = new URL(request.url)
    const status = searchParams.get('status') || 'candidate'
    const purchasePlan = purchasePlanParam(searchParams.get('purchasePlan'))
    const plannedAmount = plannedAmountParam(searchParams.get('plannedAmount'), purchasePlan)
    const format = searchParams.get('format') || 'json'
    const snapshot = searchParams.get('snapshot') === '1'
    const report = await buildResearchListShortlistReport(id, status, { purchasePlan, plannedAmount })

    if (format === 'markdown') {
      if (report.summary.salesRuleGapCount > 0 && !snapshot) {
        return NextResponse.json(salesRuleGapBlockPayload(report), { status: 409 })
      }
      if (report.summary.prePurchaseEvidenceGapCount > 0 && !snapshot) {
        return NextResponse.json(prePurchaseEvidenceBlockPayload(report), { status: 409 })
      }
      const filename = snapshot
        ? `${report.pool.name}-${status}-gap-snapshot.md`
        : `${report.pool.name}-${status}-shortlist-report.md`
      return new NextResponse(snapshot ? gapSnapshotMarkdown(report) : report.markdown, {
        headers: {
          'Content-Type': 'text/markdown; charset=utf-8',
          'Content-Disposition': `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`,
        },
      })
    }

    return NextResponse.json(report)
  } catch (error) {
    console.error('生成研究清单短名单报告失败:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '生成研究清单短名单报告失败' },
      { status: 500 },
    )
  }
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const { searchParams } = new URL(request.url)
    const status = searchParams.get('status') || 'candidate'
    const purchasePlan = purchasePlanParam(searchParams.get('purchasePlan'))
    const plannedAmount = plannedAmountParam(searchParams.get('plannedAmount'), purchasePlan)
    const allowGapSnapshot = searchParams.get('allowGapSnapshot') === '1'
    const report = await buildResearchListShortlistReport(id, status, { purchasePlan, plannedAmount })

    if (report.summary.salesRuleGapCount > 0 && !allowGapSnapshot) {
      return NextResponse.json(salesRuleGapBlockPayload(report), { status: 409 })
    }
    if (report.summary.prePurchaseEvidenceGapCount > 0 && !allowGapSnapshot) {
      return NextResponse.json(prePurchaseEvidenceBlockPayload(report), { status: 409 })
    }

    const savingGapSnapshot = (report.summary.salesRuleGapCount > 0 || report.summary.prePurchaseEvidenceGapCount > 0) && allowGapSnapshot
    const reportType = savingGapSnapshot ? 'fund_pool_gap_snapshot' : 'fund_pool_shortlist_report'
    const reportContent = savingGapSnapshot ? gapSnapshotMarkdown(report) : report.markdown
    const dataSources = jsonSafe({
      source: savingGapSnapshot ? 'fund_pool_gap_snapshot' : 'fund_pool_shortlist_report',
      pool: report.pool,
      status: report.status,
      purchasePlan,
      plannedAmount,
      summary: report.summary,
      riskLevelSourcePolicy: report.riskLevelSourcePolicy,
      actionLinks: report.actionLinks,
      salesRuleGate: {
        status: report.summary.salesRuleGapCount > 0 || report.summary.prePurchaseEvidenceGapCount > 0 ? 'blocked_snapshot' : 'ready',
        allowGapSnapshot,
      },
      members: report.members.map((member) => ({
        windCode: member.windCode,
        fundName: member.fundName,
        decisionBucket: member.decisionBucket,
        decisionLabel: member.decisionLabel,
        decisionCard: member.decisionCard,
        sourceDecisionLabel: member.sourceDecisionLabel,
        sourceDecisionLatestConclusion: member.sourceDecisionLatestConclusion,
        sourceDecisionNextAction: member.sourceDecisionNextAction,
        sourceDecisionBullets: member.sourceDecisionBullets,
        sourceDecisionHardBoundary: member.sourceDecisionHardBoundary,
        screeningTraceSummary: member.screeningTraceSummary,
        screeningTraceCriteria: member.screeningTraceCriteria,
        screeningTraceHardBoundary: member.screeningTraceHardBoundary,
        screeningTraceSource: member.screeningTraceSource,
        reviewFreshnessStatus: member.reviewFreshnessStatus,
        reviewFreshnessLabel: member.reviewFreshnessLabel,
        reviewFreshnessDetail: member.reviewFreshnessDetail,
        salesRuleMissingCount: member.salesRuleMissingCount,
        nextActions: member.nextActions,
        actionLinks: member.actionLinks,
        executionAmountGate: member.executionAmountGate,
      })),
    })
    const generationParams = jsonSafe({
      mode: savingGapSnapshot ? 'deterministic_fund_pool_gap_snapshot' : 'deterministic_fund_pool_shortlist',
      provider: 'local_pool_research',
      model: 'backend_fund_pools_sales_rule_gaps',
      generatedAt: report.generatedAt,
      status: report.status,
      purchasePlan,
      plannedAmount,
      totalMembers: report.summary.totalMembers,
      readyCount: report.summary.readyCount,
      verifyFirstCount: report.summary.verifyFirstCount,
      blockedCount: report.summary.blockedCount,
      salesRuleGapCount: report.summary.salesRuleGapCount,
      highPriorityGapCount: report.summary.highPriorityGapCount,
      prePurchaseEvidenceGapCount: report.summary.prePurchaseEvidenceGapCount,
      salesRuleGateStatus: report.summary.salesRuleGapCount > 0 || report.summary.prePurchaseEvidenceGapCount > 0 ? 'blocked_snapshot' : 'ready',
      prePurchaseEvidenceGateStatus: report.summary.prePurchaseEvidenceGapCount > 0 ? 'blocked_snapshot' : 'ready',
      riskLevelSourcePolicyStatus: report.riskLevelSourcePolicy.status,
      riskLevelSourceBacked: report.riskLevelSourcePolicy.sourceBacked,
      riskLevelGateSignals: report.riskLevelSourcePolicy.signals,
      allowGapSnapshot,
    })

    const savedRows = await sql<{ id: string }[]>`
      INSERT INTO ai_analysis_reports (
        target_type,
        target_id,
        report_type,
        content,
        data_sources,
        research_reports_used,
        generation_params,
        created_at
      ) VALUES (
        'fund_pool',
        ${id},
        ${reportType},
        ${reportContent},
        CAST(${JSON.stringify(dataSources)} AS jsonb),
        ARRAY[]::text[],
        CAST(${JSON.stringify(generationParams)} AS jsonb),
        NOW()
      )
      RETURNING id::text
    `
    const saved = savedRows[0]

    return NextResponse.json({
      id: saved?.id,
      reportId: saved?.id,
      saved: Boolean(saved?.id),
      report,
    })
  } catch (error) {
    console.error('保存研究清单短名单报告失败:', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '保存研究清单短名单报告失败' },
      { status: 500 },
    )
  }
}
