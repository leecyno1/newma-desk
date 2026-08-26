import { NextResponse } from 'next/server'
import { backendApiBaseUrl } from '@/lib/backend-api'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type UnknownRecord = Record<string, unknown>

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {}
}

function asRecordArray(value: unknown) {
  return Array.isArray(value) ? value.map(asRecord) : []
}

function textValue(value: unknown) {
  return typeof value === 'string' ? value : value == null ? '' : String(value)
}

function numberOrNull(value: unknown) {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function stringArray(value: unknown) {
  return Array.isArray(value) ? value.map(textValue).filter(Boolean) : []
}

function toManagerDetail(payload: unknown) {
  const root = asRecord(payload)
  const manager = asRecord(root.manager)
  const coverage = asRecord(root.coverage)
  const profile = asRecord(root.profile)
  const memoBlock = asRecord(root.research_memos)
  const viewpointBlock = asRecord(root.historical_viewpoints)
  const productTenures = asRecord(root.product_tenures)
  const managerAssessment = asRecord(root.manager_assessment)
  const portfolioSummary = asRecord(root.portfolio_summary)
  const evidence = asRecord(root.evidence)
  const funds = asRecordArray(root.current_funds).map((fund) => ({
    wind_code: textValue(fund.wind_code),
    name: textValue(fund.name || fund.wind_code),
    fund_name: textValue(fund.name || fund.wind_code),
    type: textValue(fund.type),
    peerGroup: textValue(fund.peer_group),
    peerGroupId: textValue(fund.peer_group_id),
    styleLabel: textValue(fund.style_label),
    classificationStatus: textValue(fund.classification_status),
    professionalScore: numberOrNull(fund.professional_score),
    professionalGrade: textValue(fund.professional_grade),
    evaluationStatus: textValue(fund.evaluation_status),
    evaluationSummary: textValue(fund.evaluation_summary),
    evaluationMissingData: stringArray(fund.evaluation_missing_data),
    evaluationQualityScore: numberOrNull(fund.evaluation_quality_score),
    evaluationAsOfDate: textValue(fund.evaluation_as_of_date),
    totalAsset: numberOrNull(fund.total_asset),
    navDate: textValue(fund.nav_date),
    entityId: textValue(fund.entity_id),
    shareCount: Number(fund.share_count || 1),
    shareCodes: stringArray(fund.share_codes),
    managerProductTenure: asRecord(fund.manager_product_tenure),
    rollingMetrics: asRecord(fund.rolling_metrics),
  }))
  const reports = asRecordArray(memoBlock.items).map((report) => ({
    id: textValue(report.id),
    title: textValue(report.title),
    reportDate: textValue(report.report_date),
    reportDateSource: textValue(report.report_date_source),
    reportDatePrecision: textValue(report.report_date_precision),
    source: textValue(report.source),
    summary: textValue(report.summary),
    keyPoints: stringArray(report.key_points),
    tags: stringArray(report.tags),
    classifications: stringArray(report.classifications),
    styleLabels: stringArray(report.style_labels),
    reviewStatus: textValue(report.review_status),
    localRelativePath: textValue(report.local_relative_path),
    identityVerifications: asRecordArray(report.identity_verifications),
  }))
  const viewpoints = asRecordArray(viewpointBlock.items).map((item) => ({
    id: textValue(item.id),
    date: textValue(item.date),
    dateSource: textValue(item.date_source),
    datePrecision: textValue(item.date_precision),
    year: textValue(item.year),
    sourceType: textValue(item.source_type),
    sourceLabel: textValue(item.source_label),
    title: textValue(item.title),
    viewpoint: textValue(item.viewpoint),
    viewpointSource: textValue(item.viewpoint_source),
    evidenceFields: stringArray(item.evidence_fields),
    summary: textValue(item.summary),
    keyPoints: stringArray(item.key_points),
    tags: stringArray(item.tags),
    reviewStatus: textValue(item.review_status),
    relativePath: textValue(item.relative_path),
    identityVerifications: asRecordArray(item.identity_verifications),
  }))
  const currentFunds = stringArray(manager.current_funds)
  const tenureItems = asRecordArray(productTenures.items).map((item) => ({
    fundCode: textValue(item.fund_code),
    fundName: textValue(item.fund_name || item.fund_code),
    type: textValue(item.type),
    category: textValue(item.category),
    totalAsset: numberOrNull(item.total_asset),
    startDate: textValue(item.start_date),
    endDate: textValue(item.end_date),
    tenureDays: numberOrNull(item.tenure_days),
    isCurrent: Boolean(item.is_current),
    isPrimaryShare: Boolean(item.is_primary_share),
    shareCount: Number(item.share_count || 1),
    shareCodes: stringArray(item.share_codes),
    tenureReturn: numberOrNull(item.tenure_return),
    annualizedReturn: numberOrNull(item.annualized_return),
    recordBreakingDaysRatio: numberOrNull(item.record_breaking_days_ratio),
    maxDrawdown: numberOrNull(item.max_drawdown),
    annualizedVolatility: numberOrNull(item.annualized_volatility),
    downsideRisk: numberOrNull(item.downside_risk),
    sharpeRatio: numberOrNull(item.sharpe_ratio),
    sortinoRatio: numberOrNull(item.sortino_ratio),
    metricAsOfDate: textValue(item.metric_as_of_date),
    metricObservations: numberOrNull(item.metric_observations),
    peerRanking: asRecord(item.peer_ranking),
    metricStatus: textValue(item.metric_status),
  }))

  return {
    id: textValue(manager.id || manager.manager_id),
    windCode: textValue(manager.manager_id) || null,
    name: textValue(manager.name) || '姓名待补',
    company: textValue(manager.company) || null,
    education: textValue(manager.education) || null,
    gender: textValue(manager.gender) || null,
    birthYear: numberOrNull(manager.birth_year),
    workYears: numberOrNull(manager.work_years),
    managementYears: numberOrNull(manager.management_years),
    currentFunds,
    fundCount: Number(coverage.current_fund_count || funds.length),
    funds,
    productTenures: {
      status: textValue(productTenures.status) || 'empty',
      shareCount: Number(productTenures.share_count || tenureItems.length),
      productCount: Number(productTenures.product_count || 0),
      currentShareCount: Number(productTenures.current_share_count || 0),
      currentProductCount: Number(productTenures.current_product_count || 0),
      historicalShareCount: Number(productTenures.historical_share_count || 0),
      historicalProductCount: Number(productTenures.historical_product_count || 0),
      items: tenureItems,
    },
    managerAssessment: {
      status: textValue(managerAssessment.status) || 'empty',
      summary: textValue(managerAssessment.summary),
      currentProductCount: Number(managerAssessment.current_product_count || 0),
      tenureEvaluatedProductCount: Number(managerAssessment.tenure_evaluated_product_count || 0),
      peerRankedProductCount: Number(managerAssessment.peer_ranked_product_count || 0),
      memoCount: Number(managerAssessment.memo_count || 0),
      representativeProduct: asRecord(managerAssessment.representative_product),
      strengths: asRecordArray(managerAssessment.strengths),
      risks: asRecordArray(managerAssessment.risks),
      scopeNote: textValue(managerAssessment.scope_note),
      methodologyVersion: textValue(managerAssessment.methodology_version),
    },
    portfolioSummary: {
      managerTypeLabels: stringArray(portfolioSummary.manager_type_labels),
      categoryDistribution: asRecordArray(portfolioSummary.category_distribution).map((item) => ({
        key: textValue(item.key),
        label: textValue(item.label),
        productCount: Number(item.product_count || 0),
        classifiedProductCount: Number(item.classified_product_count || 0),
        managedAsset: numberOrNull(item.managed_asset),
        managedAssetProductCount: Number(item.managed_asset_product_count || 0),
      })),
      currentProductCount: Number(portfolioSummary.current_product_count || 0),
      currentShareCount: Number(portfolioSummary.current_share_count || 0),
      classifiedProductCount: Number(portfolioSummary.classified_product_count || 0),
      evaluatedProductCount: Number(portfolioSummary.evaluated_product_count || 0),
      managedAsset: numberOrNull(portfolioSummary.managed_asset),
      managedAssetProductCount: Number(portfolioSummary.managed_asset_product_count || 0),
      managedAssetCoverage: numberOrNull(portfolioSummary.managed_asset_coverage),
      managedAssetScope: textValue(portfolioSummary.managed_asset_scope),
      institutionalHoldingRatio: numberOrNull(portfolioSummary.institutional_holding_ratio),
      institutionalHoldingStatus: textValue(portfolioSummary.institutional_holding_status),
      institutionalHoldingScope: textValue(portfolioSummary.institutional_holding_scope),
    },
    profile: {
      status: textValue(profile.status) || 'empty',
      productPositioning: textValue(profile.product_positioning),
      investmentObjective: textValue(profile.investment_objective),
      investmentMethod: textValue(profile.investment_method),
      corePhilosophy: textValue(profile.core_philosophy),
      stockSelectionLogic: textValue(profile.stock_selection_logic),
      riskPhilosophy: textValue(profile.risk_philosophy),
      focusIndustries: stringArray(profile.focus_industries),
      competenceAdvantages: textValue(profile.competence_advantages),
      competenceBoundaries: textValue(profile.competence_boundaries),
      styleLabel: textValue(profile.style_label),
      memoStyleLabels: stringArray(profile.style_labels_from_memos),
      memoClassifications: stringArray(profile.classifications_from_memos),
      keyInsights: stringArray(profile.key_insights),
      redFlags: stringArray(profile.red_flags),
      interviewsAnalyzed: Number(profile.interviews_analyzed || 0),
      lastInterviewDate: textValue(profile.last_interview_date),
      excessReturnSource: textValue(profile.excess_return_source),
      holdingStyle: textValue(profile.holding_style),
      concentration: textValue(profile.concentration),
      turnover: textValue(profile.turnover),
      evidence: asRecord(profile.evidence),
    },
    reports,
    historicalViewpoints: {
      status: textValue(viewpointBlock.status) || 'empty',
      count: Number(viewpointBlock.count || viewpoints.length),
      years: stringArray(viewpointBlock.years),
      sources: stringArray(viewpointBlock.sources),
      items: viewpoints,
      sourceScope: stringArray(viewpointBlock.source_scope),
      unavailableSources: stringArray(viewpointBlock.unavailable_sources),
      methodology: textValue(viewpointBlock.methodology),
    },
    coverage: {
      currentFundCount: Number(coverage.current_fund_count || funds.length),
      classifiedFundCount: Number(coverage.classified_fund_count || 0),
      evaluatedFundCount: Number(coverage.evaluated_fund_count || 0),
      evaluationCompleteFundCount: Number(coverage.evaluation_complete_fund_count || 0),
      evaluationPartialFundCount: Number(coverage.evaluation_partial_fund_count || 0),
      evaluationMissingFundCount: Number(coverage.evaluation_missing_fund_count || 0),
      tenureMetricFundCount: Number(coverage.tenure_metric_fund_count || 0),
    },
    evidence: {
      managerUpdatedAt: textValue(evidence.manager_updated_at),
      fundMetricLatestDate: textValue(evidence.fund_metric_latest_date),
      researchLatestDate: textValue(evidence.research_latest_date),
      missingItems: stringArray(evidence.missing_items),
    },
    source: textValue(root.interface_version) || 'fund_manager_research_snapshot_v1',
  }
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const response = await fetch(`${backendApiBaseUrl}/api/managers/${encodeURIComponent(id)}`, {
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      return NextResponse.json(
        { error: payload.detail || payload.error || '基金经理不存在或本地数据未同步' },
        { status: response.status },
      )
    }
    return NextResponse.json(toManagerDetail(payload))
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '获取基金经理详情失败' },
      { status: 500 },
    )
  }
}

export async function PUT() {
  return NextResponse.json({ error: '基金经理来自本地同步数据，暂不支持前端手工更新。' }, { status: 405 })
}

export async function DELETE() {
  return NextResponse.json({ error: '基金经理来自本地同步数据，暂不支持前端删除。' }, { status: 405 })
}
