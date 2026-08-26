import Link from 'next/link'
import { ArrowLeft, CircleAlert } from 'lucide-react'
import { backendApiBaseUrl, toCamelFund, type CamelFund } from '@/lib/backend-api'
import SimpleFundDetailClient, {
  type FundEvaluation,
  type FundNavPoint,
  type FundPeerMetric,
  type FundHoldingStyle,
  type FundHoldingStyleFactor,
  type FundHoldingExperience,
  type FundResearchMemo,
  type FundAssessmentSummary,
  type FundDetailHighlight,
  type FundPlainLanguageBrief,
  type FundEvaluationHistoryItem,
} from './SimpleFundDetailClient'
import type { FundHoldingSnapshot } from './FundHoldingProfile'
import type { FundAssetAllocationSnapshot } from './FundAssetAllocationPanel'
import type { FundBondAnomalySnapshot } from './FundBondAnomalyPanel'
import type { FundBondDurationSnapshot } from './FundBondDurationPanel'
import type { FundBondHoldingSnapshot } from './FundBondHoldingPanel'
import type { FundHolderStructureSnapshot } from './FundHolderStructurePanel'
import type { FundHoldingChange, FundHoldingChanges } from './FundHoldingChangesPanel'
import type { FundFeeRule, FundProductProfile } from './FundProductProfilePanel'
import type { FundFofHoldingSnapshot } from './FundFofHoldingPanel'
import type { FundDataQualitySnapshot } from './FundDataQualityPanel'
import type { FundDrawdownRecoverySnapshot } from './FundDrawdownRecoveryPanel'
import type { FundPeriodPerformanceSnapshot } from './FundPeriodPerformancePanel'
import type { FundShareClassSnapshot } from './FundShareClassPanel'
import type { FundManagerHistorySnapshot } from './FundManagerHistoryPanel'
import type { FundManagerTenurePerformance } from './FundManagerTenurePerformancePanel'

export const dynamic = 'force-dynamic'

type UnknownRecord = Record<string, unknown>

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {}
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

function normalizeFeeRules(value: unknown): FundFeeRule[] {
  return (Array.isArray(value) ? value : []).map((entry) => {
    const row = asRecord(entry)
    return {
      condition: textValue(row.condition),
      rate: textValue(row.rate),
      conditionLabel: textValue(row.condition_label) || '适用条件',
    }
  }).filter((row) => row.condition || row.rate)
}

function normalizeProductProfile(value: unknown): FundProductProfile {
  const profile = asRecord(value)
  const sourceUrls = asRecord(profile.source_urls)
  const product = asRecord(profile.product)
  const fees = asRecord(profile.fees)
  return {
    status: textValue(profile.status) || 'unavailable',
    source: textValue(profile.source),
    syncedAt: textValue(profile.synced_at),
    sourceUrls: {
      basic: textValue(sourceUrls.basic),
      fees: textValue(sourceUrls.fees),
    },
    product: {
      managementCompany: textValue(product.management_company),
      custodian: textValue(product.custodian),
      investmentObjective: textValue(product.investment_objective),
      investmentStyle: textValue(product.investment_style),
      investmentPhilosophy: textValue(product.investment_philosophy),
      investmentScope: textValue(product.investment_scope),
      investmentStrategy: textValue(product.investment_strategy),
      riskReturnCharacteristics: textValue(product.risk_return_characteristics),
    },
    fees: {
      managementFeeRate: textValue(fees.management_fee_rate),
      custodianFeeRate: textValue(fees.custodian_fee_rate),
      salesServiceFeeRate: textValue(fees.sales_service_fee_rate),
      subscriptionFeeRules: normalizeFeeRules(fees.subscription_fee_rules),
      purchaseFeeRules: normalizeFeeRules(fees.purchase_fee_rules),
      redemptionFeeRules: normalizeFeeRules(fees.redemption_fee_rules),
      note: textValue(fees.note),
    },
    missingItems: stringArray(profile.missing_items),
  }
}

function normalizeHoldingStyleFactor(value: unknown): FundHoldingStyleFactor {
  const item = asRecord(value)
  return {
    factor: textValue(item.factor),
    label: textValue(item.label),
    exposure: numberOrNull(item.exposure),
    unit: textValue(item.unit),
    percentile: numberOrNull(item.percentile),
    percentileLabel: textValue(item.percentile_label),
    sampleSize: Number(item.sample_size || 0),
  }
}

function dateYearsAgo(years: number) {
  const date = new Date()
  date.setFullYear(date.getFullYear() - years)
  return date.toISOString().slice(0, 10)
}

function normalizeEvaluation(payload: unknown): FundEvaluation {
  const root = asRecord(payload)
  const target = asRecord(root.target)
  const classification = asRecord(root.classification)
  const peerContext = asRecord(root.peer_context)
  const methodology = asRecord(root.methodology)
  const benchmarkMapping = asRecord(classification.benchmark_mapping || peerContext.benchmark_mapping)
  const benchmarkEvidence = asRecord(benchmarkMapping.evidence_refs)
  const contractDimensions = asRecord(benchmarkEvidence.contractBenchmarkDimensions)
  const benchmarkComponents = (Array.isArray(benchmarkEvidence.benchmarkComponents) ? benchmarkEvidence.benchmarkComponents : [])
    .map((value) => {
      const component = asRecord(value)
      return {
        code: textValue(component.code),
        name: textValue(component.name),
        asset: textValue(component.asset),
        weight: numberOrNull(component.weight),
      }
    })
    .filter((component): component is { code: string; name: string; asset: string; weight: number } => Boolean(component.name) && component.weight != null)
  const evaluation = asRecord(root.evaluation)
  const dimensionScores = asRecord(evaluation.dimension_scores)
  const metricScores = asRecord(evaluation.metric_scores)
  const peerPercentiles = asRecord(evaluation.peer_percentiles)
  const explanatoryEvidence = asRecord(root.explanatory_evidence)
  const crossMarketHolding = asRecord(explanatoryEvidence.cross_market_holding)
  const dataQuality = asRecord(evaluation.data_quality)
  const status = textValue(root.status) || 'unavailable'
  const sampleStatus = textValue(peerContext.sample_status) || 'unavailable'
  const rawScore = numberOrNull(evaluation.overall_score)
  const score = status === 'insufficient_evidence' || textValue(dataQuality.status) === 'insufficient'
    ? null
    : rawScore

  const peerMetrics: FundPeerMetric[] = Object.entries(peerPercentiles).map(([key, value]) => {
    const metric = asRecord(value)
    return {
      key,
      label: textValue(metric.label) || key,
      value: numberOrNull(metric.value),
      unit: textValue(metric.unit),
      percentile: numberOrNull(metric.percentile),
      rank: numberOrNull(metric.rank),
      peerCount: Number(metric.peer_count || 0),
      sampleStatus: textValue(metric.sample_status),
      metricWindow: textValue(metric.metric_window),
    }
  })

  return {
    status,
    methodologyVersion: textValue(root.methodology_version),
    calculationMethod: textValue(evaluation.calculation_method),
    evaluationWindow: textValue(peerContext.metric_window || methodology.evaluation_window),
    asOfDate: textValue(target.as_of_date),
    classificationStatus: textValue(classification.status) || 'unclassified',
    peerGroup: textValue(classification.peer_group || peerContext.peer_group),
    peerGroupId: textValue(classification.peer_group_id || peerContext.peer_group_id),
    benchmark: textValue(classification.primary_benchmark || peerContext.primary_benchmark),
    benchmarkCode: textValue(classification.benchmark_code || peerContext.benchmark_code),
    benchmarkType: textValue(benchmarkMapping.benchmark_type),
    benchmarkWeight: numberOrNull(benchmarkEvidence.primaryReferenceWeight),
    benchmarkComponents,
    contractDimensions: textValue(contractDimensions.base_index) && textValue(contractDimensions.price_return) && textValue(contractDimensions.tenor)
      ? {
          baseIndex: textValue(contractDimensions.base_index),
          priceReturn: textValue(contractDimensions.price_return),
          tenor: textValue(contractDimensions.tenor),
        }
      : null,
    strategyFamily: textValue(classification.strategy_family_name || classification.strategy_family_key),
    activePassive: textValue(classification.active_passive),
    confidence: numberOrNull(classification.confidence),
    sampleStatus,
    validPeerCount: Number(peerContext.valid_metric_peer_count || 0),
    minimumPeerCount: Number(peerContext.minimum_peer_count || 0),
    score,
    grade: score == null ? '' : textValue(evaluation.overall_grade),
    dimensions: Object.entries(dimensionScores).map(([key, value]) => {
      const dimension = asRecord(value)
      return {
        key,
        score: numberOrNull(dimension.score),
        weight: numberOrNull(dimension.weight),
        weightedScore: numberOrNull(dimension.weighted_score),
        evidence: stringArray(dimension.evidence),
      }
    }),
    metricScores: Object.fromEntries(
      Object.entries(metricScores)
        .map(([key, value]) => [key, numberOrNull(value)] as const)
        .filter((item): item is readonly [string, number] => item[1] != null),
    ),
    methodology: {
      status: textValue(methodology.status) || 'unavailable',
      profileKey: textValue(methodology.profile_key),
      profileName: textValue(methodology.profile_name),
      evaluationWindow: textValue(methodology.evaluation_window),
      scoreFormula: textValue(methodology.score_formula),
      boundary: textValue(methodology.boundary),
      dimensions: (Array.isArray(methodology.dimensions) ? methodology.dimensions : []).map((value) => {
        const dimension = asRecord(value)
        return {
          key: textValue(dimension.key),
          label: textValue(dimension.label),
          weight: numberOrNull(dimension.weight),
          metrics: (Array.isArray(dimension.metrics) ? dimension.metrics : []).map((value) => {
            const metric = asRecord(value)
            return {
              path: textValue(metric.path),
              label: textValue(metric.label),
              unit: textValue(metric.unit),
              direction: textValue(metric.direction),
              rule: textValue(metric.rule),
              fallbackPaths: stringArray(metric.fallback_paths),
            }
          }).filter((metric) => metric.path),
        }
      }).filter((dimension) => dimension.key),
    },
    peerMetrics,
    crossMarketHolding: {
      status: textValue(crossMarketHolding.status) || 'unavailable',
      quarter: textValue(crossMarketHolding.quarter),
      peerGroupName: textValue(crossMarketHolding.peer_group_name),
      profilePeerCount: Number(crossMarketHolding.profile_peer_count || 0),
      minimumPeerCount: Number(crossMarketHolding.minimum_peer_count || 5),
      labels: stringArray(crossMarketHolding.labels),
      comparisons: (Array.isArray(crossMarketHolding.comparisons) ? crossMarketHolding.comparisons : []).map((value) => {
        const item = asRecord(value)
        const dispersion = asRecord(item.dispersion)
        return {
          metric: textValue(item.metric),
          label: textValue(item.label),
          value: numberOrNull(item.value),
          unit: textValue(item.unit),
          percentile: numberOrNull(item.percentile),
          positionLabel: textValue(item.position_label),
          sampleSize: Number(item.sample_size || 0),
          minimumPeerCount: Number(item.minimum_peer_count || 5),
          sampleStatus: textValue(item.sample_status),
          dispersionStatus: textValue(dispersion.status),
        }
      }).filter((item) => item.metric),
      missingItems: stringArray(crossMarketHolding.missing_items),
      boundary: textValue(crossMarketHolding.boundary),
    },
    positiveFactors: stringArray(evaluation.positive_factors),
    negativeFactors: stringArray(evaluation.negative_factors),
    missingItems: stringArray(root.missing_items),
    dataQualityStatus: textValue(dataQuality.status),
    dataQualityScore: numberOrNull(dataQuality.score),
  }
}

function normalizeEvaluationHistoryItem(value: unknown): FundEvaluationHistoryItem {
  const item = asRecord(value)
  const change = asRecord(item.change)
  const dimensionScores = asRecord(item.dimension_scores ?? item.dimensionScores)
  const evidenceCoverage = asRecord(item.evidence_coverage ?? item.evidenceCoverage)
  const drivers = Array.isArray(change.drivers) ? change.drivers : []
  return {
    id: textValue(item.id),
    evaluationWindow: textValue(item.evaluation_window ?? item.evaluationWindow),
    asOfDate: textValue(item.as_of_date ?? item.asOfDate),
    createdAt: textValue(item.created_at ?? item.createdAt),
    status: textValue(item.status),
    methodologyVersion: textValue(item.methodology_version ?? item.methodologyVersion),
    calculationMethod: textValue(item.calculation_method ?? item.calculationMethod),
    peerGroupName: textValue(item.peer_group_name ?? item.peerGroupName),
    overallScore: numberOrNull(item.overall_score ?? item.overallScore),
    overallGrade: textValue(item.overall_grade ?? item.overallGrade),
    peerRank: numberOrNull(item.peer_rank ?? item.peerRank),
    peerCount: numberOrNull(item.peer_count ?? item.peerCount),
    peerPercentile: numberOrNull(item.peer_percentile ?? item.peerPercentile),
    dimensions: Object.entries(dimensionScores).map(([key, raw]) => {
      const dimension = asRecord(raw)
      return { key, score: numberOrNull(dimension.score) }
    }),
    evidenceCoverage: {
      coveragePercent: numberOrNull(evidenceCoverage.coverage_percent ?? evidenceCoverage.coveragePercent),
      missingDimensions: stringArray(evidenceCoverage.missing_dimensions ?? evidenceCoverage.missingDimensions),
    },
    missingItems: stringArray(item.missing_items ?? item.missingItems),
    change: Object.keys(change).length ? {
      summary: textValue(change.summary),
      comparisonStatus: textValue(change.comparison_status ?? change.comparisonStatus),
      comparable: Boolean(change.comparable),
      scoreDelta: numberOrNull(change.score_delta ?? change.scoreDelta),
      rawScoreDelta: numberOrNull(change.raw_score_delta ?? change.rawScoreDelta),
      rankChange: numberOrNull(change.rank_change ?? change.rankChange),
      rawRankChange: numberOrNull(change.raw_rank_change ?? change.rawRankChange),
      percentileDelta: numberOrNull(change.percentile_delta ?? change.percentileDelta),
      evidenceCoverageDelta: numberOrNull(change.evidence_coverage_delta ?? change.evidenceCoverageDelta),
      dataQualityDelta: numberOrNull(change.data_quality_delta ?? change.dataQualityDelta),
      drivers: drivers.map((raw) => {
        const driver = asRecord(raw)
        return { key: textValue(driver.key), delta: numberOrNull(driver.delta) || 0 }
      }).filter((driver) => driver.key),
      methodologyChanged: Boolean(change.methodology_changed ?? change.methodologyChanged),
      peerGroupChanged: Boolean(change.peer_group_changed ?? change.peerGroupChanged),
    } : null,
  }
}

async function loadFundDetail(code: string) {
  const endDate = new Date().toISOString().slice(0, 10)
  const navParams = new URLSearchParams({ start_date: dateYearsAgo(4), end_date: endDate })
  const [snapshotResult, navResult, holdingsResult, assetAllocationResult, shareClassesResult, managerHistoryResult, fofHoldingsResult, bondDurationResult, bondAnomalyResult, bondHoldingsResult, holderStructureResult, holdingChangesResult, evaluationHistoryResult] = await Promise.allSettled([
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/research-snapshot?window=1y&include_research=true&include_attribution=true&live_attribution=false`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/nav?${navParams.toString()}`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/holdings`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/asset-allocation?limit=24`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/share-classes`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/manager-history`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/fof-holdings`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/bond-duration?window_weeks=104`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/bond-anomaly?window_days=252`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/bond-holdings?limit=8`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/holder-structure?limit=10`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/holding-changes`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/evaluation-history?limit=60`, { cache: 'no-store' }),
  ])

  if (snapshotResult.status !== 'fulfilled' || !snapshotResult.value.ok) return null

  const snapshotPayload = asRecord(await snapshotResult.value.json().catch(() => ({})))
  const snapshotFundPayload = asRecord(snapshotPayload.fund)
  const evaluationPayload = asRecord(snapshotPayload.evaluation)
  const evaluationWindowPayloads = asRecord(snapshotPayload.evaluation_windows)
  const fund = toCamelFund({
    ...snapshotFundPayload,
    managers: snapshotPayload.managers,
    research_profile: snapshotPayload.research_profile,
    style_profile: snapshotPayload.style_profile,
    rolling_metrics: snapshotPayload.rolling_metrics,
    data_quality: snapshotPayload.data_quality,
    professional_scoring: asRecord(evaluationPayload.evaluation),
    fund_evaluation: evaluationPayload,
    research_evidence: snapshotPayload.evidence,
  }) as CamelFund
  const productProfile = normalizeProductProfile(snapshotFundPayload.product_profile)
  const navPayload = navResult.status === 'fulfilled' && navResult.value.ok
    ? asRecord(await navResult.value.json().catch(() => ({})))
    : {}
  const memoPayload = asRecord(snapshotPayload.research_memos)
  const assessmentPayload = asRecord(snapshotPayload.assessment_summary)
  const detailHighlightPayload = Array.isArray(snapshotPayload.detail_highlights) ? snapshotPayload.detail_highlights : []
  const plainLanguageBriefPayload = asRecord(snapshotPayload.plain_language_brief)
  const dataQualityPayload = asRecord(snapshotPayload.data_quality)
  const evidencePayload = asRecord(snapshotPayload.evidence)
  const styleProfilePayload = asRecord(snapshotPayload.style_profile)
  const holdingStylePayload = asRecord(styleProfilePayload.holding_style)
  const holdingExperiencePayload = asRecord(snapshotPayload.holding_experience)
  const drawdownRecoveryPayload = asRecord(snapshotPayload.drawdown_recovery)
  const holdingsPayload = holdingsResult.status === 'fulfilled' && holdingsResult.value.ok
    ? asRecord(await holdingsResult.value.json().catch(() => ({})))
    : {}
  const assetAllocationPayload = assetAllocationResult.status === 'fulfilled' && assetAllocationResult.value.ok
    ? asRecord(await assetAllocationResult.value.json().catch(() => ({})))
    : {}
  const shareClassesPayload = shareClassesResult.status === 'fulfilled' && shareClassesResult.value.ok
    ? asRecord(await shareClassesResult.value.json().catch(() => ({})))
    : {}
  const managerHistoryPayload = managerHistoryResult.status === 'fulfilled' && managerHistoryResult.value.ok
    ? asRecord(await managerHistoryResult.value.json().catch(() => ({})))
    : {}
  const managerTenurePerformancePayload = asRecord(snapshotPayload.manager_tenure_performance)
  const fofHoldingsPayload = fofHoldingsResult.status === 'fulfilled' && fofHoldingsResult.value.ok
    ? asRecord(await fofHoldingsResult.value.json().catch(() => ({})))
    : {}
  const bondDurationPayload = bondDurationResult.status === 'fulfilled' && bondDurationResult.value.ok
    ? asRecord(await bondDurationResult.value.json().catch(() => ({})))
    : {}
  const bondAnomalyPayload = bondAnomalyResult.status === 'fulfilled' && bondAnomalyResult.value.ok
    ? asRecord(await bondAnomalyResult.value.json().catch(() => ({})))
    : {}
  const bondHoldingsPayload = bondHoldingsResult.status === 'fulfilled' && bondHoldingsResult.value.ok
    ? asRecord(await bondHoldingsResult.value.json().catch(() => ({})))
    : {}
  const holderStructurePayload = holderStructureResult.status === 'fulfilled' && holderStructureResult.value.ok
    ? asRecord(await holderStructureResult.value.json().catch(() => ({})))
    : {}
  const holdingChangesPayload = holdingChangesResult.status === 'fulfilled' && holdingChangesResult.value.ok
    ? asRecord(await holdingChangesResult.value.json().catch(() => ({})))
    : {}
  const evaluationHistoryPayload = evaluationHistoryResult.status === 'fulfilled' && evaluationHistoryResult.value.ok
    ? asRecord(await evaluationHistoryResult.value.json().catch(() => ({})))
    : {}
  const periodPerformancePayload = asRecord(snapshotPayload.period_performance)
  const holdingSummaryPayload = asRecord(holdingsPayload.summary)
  const holdingWeightValidationPayload = asRecord(holdingSummaryPayload.weight_validation)
  const holdingIndustryEvidencePayload = asRecord(holdingsPayload.industry_evidence)

  const rawNavPoints = (Array.isArray(navPayload.data) ? navPayload.data : [])
    .map((value) => {
      const point = asRecord(value)
      const unitNav = numberOrNull(point.unit_nav ?? point.nav)
      const accumNav = numberOrNull(point.accum_nav ?? point.adj_nav)
      return {
        date: textValue(point.date),
        unitNav,
        accumNav,
        benchmarkNav: numberOrNull(point.benchmark_nav),
      }
    })
    .filter((point) => point.date && (point.unitNav != null || point.accumNav != null))
    .sort((left, right) => left.date.localeCompare(right.date))

  const accumNavCount = rawNavPoints.filter((point) => point.accumNav != null).length
  const unitNavCount = rawNavPoints.filter((point) => point.unitNav != null).length
  const useAccumNav = accumNavCount >= 2 && accumNavCount >= unitNavCount
  const nav: FundNavPoint[] = rawNavPoints
    .map((point) => ({
      ...point,
      nav: useAccumNav ? point.accumNav ?? Number.NaN : point.unitNav ?? Number.NaN,
      navBasis: useAccumNav ? 'accum_nav' as const : 'unit_nav' as const,
    }))
    .filter((point) => Number.isFinite(point.nav) && point.nav > 0)

  const researchMemos: FundResearchMemo[] = (Array.isArray(memoPayload.items) ? memoPayload.items : []).map((value) => {
    const memo = asRecord(value)
    const evidenceScope = textValue(memo.evidence_scope) || 'manager_level'
    const classifications = stringArray(memo.classifications)
    const styleLabels = stringArray(memo.style_labels)
    const fundClassifications = stringArray(memo.fund_classifications)
    const fundStyleLabels = stringArray(memo.fund_style_labels)
    const managerClassifications = stringArray(memo.manager_classifications)
    const managerStyleLabels = stringArray(memo.manager_style_labels)
    const hasScopedLabels = [
      'fund_classifications',
      'fund_style_labels',
      'manager_classifications',
      'manager_style_labels',
    ].some((key) => Object.prototype.hasOwnProperty.call(memo, key))
    return {
      id: textValue(memo.id),
      title: textValue(memo.title),
      managerName: textValue(memo.manager_name),
      reportDate: textValue(memo.report_date),
      source: textValue(memo.source),
      summary: textValue(memo.summary),
      classifications,
      styleLabels,
      fundClassifications: hasScopedLabels
        ? fundClassifications
        : evidenceScope === 'fund_specific' ? classifications : [],
      fundStyleLabels: hasScopedLabels
        ? fundStyleLabels
        : evidenceScope === 'fund_specific' ? styleLabels : [],
      managerClassifications: hasScopedLabels
        ? managerClassifications
        : evidenceScope === 'manager_level' ? classifications : [],
      managerStyleLabels: hasScopedLabels
        ? managerStyleLabels
        : evidenceScope === 'manager_level' ? styleLabels : [],
      keyPoints: stringArray(memo.key_points),
      evidenceScope,
    }
  }).filter((memo: FundResearchMemo) => memo.id)

  const evaluationWindows = Object.fromEntries(
    ['6m', '1y', '3y'].map((window) => [
      window,
      normalizeEvaluation(evaluationWindowPayloads[window] || (window === '1y' ? evaluationPayload : {})),
    ]),
  )
  const evaluationHistory = (Array.isArray(evaluationHistoryPayload.items) ? evaluationHistoryPayload.items : [])
    .map(normalizeEvaluationHistoryItem)
    .filter((item) => item.id && item.evaluationWindow)

  const holdingStyle: FundHoldingStyle = {
    status: textValue(holdingStylePayload.status) || 'unavailable',
    quarter: textValue(holdingStylePayload.quarter),
    peerGroupName: textValue(holdingStylePayload.peer_group_name),
    sampleSize: Number(holdingStylePayload.sample_size || 0),
    minimumPeerCount: Number(holdingStylePayload.minimum_peer_count || 5),
    holdingsDisclosedWeight: numberOrNull(holdingStylePayload.holdings_disclosed_weight),
    labels: stringArray(holdingStylePayload.labels),
    descriptors: (Array.isArray(holdingStylePayload.descriptors) ? holdingStylePayload.descriptors : []).map(normalizeHoldingStyleFactor),
    peerPercentiles: (Array.isArray(holdingStylePayload.peer_percentiles) ? holdingStylePayload.peer_percentiles : []).map(normalizeHoldingStyleFactor),
    modelScope: textValue(holdingStylePayload.model_scope) || '公开持仓风格描述子与同类分位，不是完整 Barra 风险模型。',
    missingItems: stringArray(holdingStylePayload.missing_items),
  }

  const holdingExperience: FundHoldingExperience = {
    status: textValue(holdingExperiencePayload.status) || 'insufficient_evidence',
    source: textValue(holdingExperiencePayload.source),
    navBasis: textValue(holdingExperiencePayload.nav_basis),
    sampleStart: textValue(holdingExperiencePayload.sample_start),
    sampleEnd: textValue(holdingExperiencePayload.sample_end),
    navObservations: Number(holdingExperiencePayload.nav_observations || 0),
    periods: (Array.isArray(holdingExperiencePayload.periods) ? holdingExperiencePayload.periods : []).map((value) => {
      const item = asRecord(value)
      return {
        months: Number(item.months || 0),
        label: textValue(item.label),
        status: textValue(item.status),
        sampleCount: Number(item.sample_count || 0),
        positiveProbability: numberOrNull(item.positive_probability),
        nonLossProbability: numberOrNull(item.non_loss_probability),
        returnThresholdProbabilities: (Array.isArray(item.return_threshold_probabilities) ? item.return_threshold_probabilities : []).map((value) => {
          const threshold = asRecord(value)
          return {
            threshold: Number(threshold.threshold || 0),
            probability: numberOrNull(threshold.probability),
          }
        }),
        medianReturn: numberOrNull(item.median_return),
        averageReturn: numberOrNull(item.average_return),
        bestReturn: numberOrNull(item.best_return),
        worstReturn: numberOrNull(item.worst_return),
        averageActualDays: numberOrNull(item.average_actual_days),
        firstBuyDate: textValue(item.first_buy_date),
        lastBuyDate: textValue(item.last_buy_date),
      }
    }).filter((item) => item.months > 0),
    missingItems: stringArray(holdingExperiencePayload.missing_items),
  }

  const drawdownRecovery: FundDrawdownRecoverySnapshot = {
    status: textValue(drawdownRecoveryPayload.status) || 'insufficient_evidence',
    label: textValue(drawdownRecoveryPayload.label),
    navBasis: textValue(drawdownRecoveryPayload.nav_basis),
    historyStart: textValue(drawdownRecoveryPayload.history_start),
    historyEnd: textValue(drawdownRecoveryPayload.history_end),
    observations: Number(drawdownRecoveryPayload.observations || 0),
    currentDrawdown: numberOrNull(drawdownRecoveryPayload.current_drawdown),
    currentUnderwaterDays: Number(drawdownRecoveryPayload.current_underwater_days || 0),
    worstDrawdown: numberOrNull(drawdownRecoveryPayload.worst_drawdown),
    worstPeakDate: textValue(drawdownRecoveryPayload.worst_peak_date),
    worstTroughDate: textValue(drawdownRecoveryPayload.worst_trough_date),
    worstRecoveryDate: textValue(drawdownRecoveryPayload.worst_recovery_date),
    worstDeclineDays: Number(drawdownRecoveryPayload.worst_decline_days || 0),
    worstRecoveryDays: numberOrNull(drawdownRecoveryPayload.worst_recovery_days),
    longestUnderwaterDays: Number(drawdownRecoveryPayload.longest_underwater_days || 0),
    materialEpisodeCount: Number(drawdownRecoveryPayload.material_episode_count || 0),
    recoveredMaterialEpisodeCount: Number(drawdownRecoveryPayload.recovered_material_episode_count || 0),
    episodes: (Array.isArray(drawdownRecoveryPayload.episodes) ? drawdownRecoveryPayload.episodes : []).map((value) => {
      const item = asRecord(value)
      return {
        startDate: textValue(item.start_date),
        troughDate: textValue(item.trough_date),
        recoveryDate: textValue(item.recovery_date),
        depth: numberOrNull(item.depth),
        depthAtEnd: numberOrNull(item.depth_at_end),
        declineDays: Number(item.decline_days || 0),
        recoveryDays: numberOrNull(item.recovery_days),
        underwaterDays: Number(item.underwater_days || 0),
        status: textValue(item.status),
      }
    }),
    note: textValue(drawdownRecoveryPayload.note),
    boundary: textValue(drawdownRecoveryPayload.boundary),
    missingItems: stringArray(drawdownRecoveryPayload.missing_items),
  }

  const periodPerformanceSummaryPayload = asRecord(periodPerformancePayload.summary)
  const normalizePeriodSummary = (value: unknown) => {
    const item = asRecord(value)
    const itemReturn = numberOrNull(item.return)
    return itemReturn == null || !textValue(item.label) ? null : {
      label: textValue(item.label),
      return: itemReturn,
    }
  }
  const periodPerformance: FundPeriodPerformanceSnapshot = {
    status: textValue(periodPerformancePayload.status) || 'insufficient_evidence',
    navBasis: textValue(periodPerformancePayload.nav_basis),
    latestNavDate: textValue(periodPerformancePayload.latest_nav_date),
    peerGroupName: textValue(periodPerformancePayload.peer_group_name),
    minimumPeerCount: Number(periodPerformancePayload.minimum_peer_count || 5),
    periods: (Array.isArray(periodPerformancePayload.periods) ? periodPerformancePayload.periods : []).map((value) => {
      const item = asRecord(value)
      return {
        year: Number(item.year || 0),
        label: textValue(item.label),
        isYtd: Boolean(item.is_ytd),
        return: Number(item.return),
        requestedStartDate: textValue(item.requested_start_date),
        requestedEndDate: textValue(item.requested_end_date),
        actualStartDate: textValue(item.actual_start_date),
        actualEndDate: textValue(item.actual_end_date),
        observations: Number(item.observations || 0),
        expectedObservations: Number(item.expected_observations || 0),
        observationCoverage: Number(item.observation_coverage || 0),
        coverageStatus: textValue(item.coverage_status),
        returnBasis: textValue(item.return_basis),
        sampleStatus: textValue(item.sample_status),
        rank: numberOrNull(item.rank),
        peerCount: Number(item.peer_count || 0),
        percentile: numberOrNull(item.percentile),
        peerMedianReturn: numberOrNull(item.peer_median_return),
        abovePeerMedian: typeof item.above_peer_median === 'boolean' ? item.above_peer_median : null,
      }
    }).filter((item) => item.year > 0 && item.label && Number.isFinite(item.return)),
    summary: {
      availablePeriodCount: Number(periodPerformanceSummaryPayload.available_period_count || 0),
      completePeriodCount: Number(periodPerformanceSummaryPayload.complete_period_count || 0),
      positivePeriodCount: Number(periodPerformanceSummaryPayload.positive_period_count || 0),
      peerRankedPeriodCount: Number(periodPerformanceSummaryPayload.peer_ranked_period_count || 0),
      abovePeerMedianCount: Number(periodPerformanceSummaryPayload.above_peer_median_count || 0),
      bestPeriod: normalizePeriodSummary(periodPerformanceSummaryPayload.best_period),
      worstPeriod: normalizePeriodSummary(periodPerformanceSummaryPayload.worst_period),
    },
    boundary: textValue(periodPerformancePayload.boundary),
    missingItems: stringArray(periodPerformancePayload.missing_items),
  }

  const dataQuality: FundDataQualitySnapshot = {
    score: numberOrNull(dataQualityPayload.score),
    status: textValue(dataQualityPayload.status) || 'unavailable',
    summary: textValue(dataQualityPayload.summary),
    checks: Object.entries(asRecord(dataQualityPayload.checks)).map(([key, value]) => {
      const check = asRecord(value)
      return {
        key,
        passed: Boolean(check.passed),
        message: textValue(check.message),
        missingFields: stringArray(check.missing_fields),
        source: textValue(check.source),
        value: textValue(check.value),
        notApplicable: Boolean(check.not_applicable),
        observations: Number(check.observations || 0),
        coverageDays: Number(check.coverage_days || 0),
        startDate: textValue(check.start_date),
        endDate: textValue(check.end_date),
        metricCount: Number(check.metric_count || 0),
        windows: stringArray(check.windows),
      }
    }),
    issues: stringArray(dataQualityPayload.issues),
    asOfDate: textValue(evidencePayload.as_of_date),
    fundDataAsOf: textValue(evidencePayload.fund_data_as_of),
    profileAsOf: textValue(evidencePayload.profile_as_of),
    researchLatestDate: textValue(evidencePayload.research_latest_date),
    evidenceMissingItems: stringArray(evidencePayload.missing_items),
  }

  const holdingSnapshot: FundHoldingSnapshot = {
    latestQuarter: textValue(holdingsPayload.latest_quarter),
    source: textValue(holdingsPayload.source),
    industryEvidence: {
      status: textValue(holdingIndustryEvidencePayload.status) || 'not_applicable',
      hongKongHoldingCount: Number(holdingIndustryEvidencePayload.hong_kong_holding_count || 0),
      matchedHoldingCount: Number(holdingIndustryEvidencePayload.matched_holding_count || 0),
      asOfDate: textValue(holdingIndustryEvidencePayload.as_of_date),
      source: textValue(holdingIndustryEvidencePayload.source),
      evidenceUrl: textValue(holdingIndustryEvidencePayload.evidence_url),
      note: textValue(holdingIndustryEvidencePayload.note),
    },
    holdings: (Array.isArray(holdingsPayload.holdings) ? holdingsPayload.holdings : []).map((value) => {
      const holding = asRecord(value)
      return {
        stockCode: textValue(holding.stock_code),
        stockName: textValue(holding.stock_name),
        market: textValue(holding.market),
        industry: textValue(holding.industry),
        industrySource: textValue(holding.industry_source),
        industryAsOfDate: textValue(holding.industry_as_of_date),
        industryEvidenceUrl: textValue(holding.industry_evidence_url),
        fundNavWeight: numberOrNull(holding.fund_nav_weight ?? holding.weight),
        equityPortfolioWeight: numberOrNull(holding.equity_portfolio_weight),
        marketValue: numberOrNull(holding.market_cap),
        reportDate: textValue(holding.report_date),
        announcementDate: textValue(holding.announcement_date),
      }
    }),
    summary: {
      holdingCount: Number(holdingSummaryPayload.holding_count || 0),
      weightBasis: textValue(holdingSummaryPayload.weight_basis),
      reportDate: textValue(holdingSummaryPayload.report_date),
      announcementDate: textValue(holdingSummaryPayload.announcement_date),
      syncedAt: textValue(holdingSummaryPayload.synced_at),
      holdingSources: stringArray(holdingSummaryPayload.holding_sources),
      weightSources: stringArray(holdingSummaryPayload.weight_sources),
      weightSourceUrls: stringArray(holdingSummaryPayload.weight_source_urls),
      fundNetAssetBases: stringArray(holdingSummaryPayload.fund_net_asset_bases),
      fundNetAssetDate: textValue(holdingSummaryPayload.fund_net_asset_date),
      topThreeWeight: numberOrNull(holdingSummaryPayload.top_three_weight),
      topTenWeight: numberOrNull(holdingSummaryPayload.top_ten_weight),
      topThreeEquityWeight: numberOrNull(holdingSummaryPayload.top_three_equity_weight),
      topTenEquityWeight: numberOrNull(holdingSummaryPayload.top_ten_equity_weight),
      industryWeightBasis: textValue(holdingSummaryPayload.industry_weight_basis),
      weightValidation: {
        status: textValue(holdingWeightValidationPayload.status),
        totalWeight: Number(holdingWeightValidationPayload.total_weight || 0),
        validCount: Number(holdingWeightValidationPayload.valid_count || 0),
        missingCount: Number(holdingWeightValidationPayload.missing_count || 0),
        invalidCount: Number(holdingWeightValidationPayload.invalid_count || 0),
        reason: textValue(holdingWeightValidationPayload.reason),
      },
      industryBuckets: (Array.isArray(holdingSummaryPayload.industry_buckets) ? holdingSummaryPayload.industry_buckets : []).map((value) => {
        const bucket = asRecord(value)
        return { industry: textValue(bucket.industry), weight: Number(bucket.weight || 0) }
      }).filter((bucket) => bucket.industry && Number.isFinite(bucket.weight)),
      marketBuckets: (Array.isArray(holdingSummaryPayload.market_buckets) ? holdingSummaryPayload.market_buckets : []).map((value) => {
        const bucket = asRecord(value)
        return { market: textValue(bucket.market), weight: Number(bucket.weight || 0) }
      }).filter((bucket) => bucket.market && Number.isFinite(bucket.weight)),
    },
  }

  const normalizeAssetAllocationRow = (value: unknown) => {
    const row = asRecord(value)
    return {
      reportDate: textValue(row.report_date),
      stockRatio: numberOrNull(row.stock_ratio),
      bondRatio: numberOrNull(row.bond_ratio),
      cashRatio: numberOrNull(row.cash_ratio),
      netAssetYi: numberOrNull(row.net_asset_yi),
      source: textValue(row.source),
      sourceUrl: textValue(row.source_url),
    }
  }
  const assetAllocationHistory = (Array.isArray(assetAllocationPayload.history) ? assetAllocationPayload.history : [])
    .map(normalizeAssetAllocationRow)
    .filter((row) => row.reportDate)
  const scaleTrendPayload = asRecord(assetAllocationPayload.scale_trend)
  const assetAllocation: FundAssetAllocationSnapshot = {
    status: textValue(assetAllocationPayload.status) || 'unavailable',
    latest: assetAllocationPayload.latest ? normalizeAssetAllocationRow(assetAllocationPayload.latest) : null,
    history: assetAllocationHistory,
    scaleTrend: {
      status: textValue(scaleTrendPayload.status) || 'insufficient_evidence',
      label: textValue(scaleTrendPayload.label) || '规模趋势待补',
      latestReportDate: textValue(scaleTrendPayload.latest_report_date),
      latestAssetYi: numberOrNull(scaleTrendPayload.latest_asset_yi),
      oneYearChange: numberOrNull(scaleTrendPayload.one_year_change),
      threeYearChange: numberOrNull(scaleTrendPayload.three_year_change),
      peakAssetYi: numberOrNull(scaleTrendPayload.peak_asset_yi),
      peakDate: textValue(scaleTrendPayload.peak_date),
      latestFromPeak: numberOrNull(scaleTrendPayload.latest_from_peak),
      observations: Number(scaleTrendPayload.observations || 0),
      note: textValue(scaleTrendPayload.note),
      boundary: textValue(scaleTrendPayload.boundary),
    },
    source: textValue(assetAllocationPayload.source),
    sourceUrl: textValue(assetAllocationPayload.source_url),
    missingItems: stringArray(assetAllocationPayload.missing_items),
  }

  const shareEntityPayload = asRecord(shareClassesPayload.entity)
  const shareFeeEvidencePayload = asRecord(shareClassesPayload.fee_evidence)
  const shareClasses: FundShareClassSnapshot = {
    status: textValue(shareClassesPayload.status) || 'unavailable',
    entity: Object.keys(shareEntityPayload).length ? {
      canonicalCode: textValue(shareEntityPayload.canonical_code),
      canonicalName: textValue(shareEntityPayload.canonical_name),
    } : null,
    shareCount: Number(shareClassesPayload.share_count || 0),
    shares: (Array.isArray(shareClassesPayload.shares) ? shareClassesPayload.shares : []).map((value) => {
      const share = asRecord(value)
      return {
        windCode: textValue(share.wind_code),
        name: textValue(share.name),
        shareClass: textValue(share.share_class),
        currency: textValue(share.currency) || 'CNY',
        isPrimary: Boolean(share.is_primary),
        isCurrent: Boolean(share.is_current),
        nav: numberOrNull(share.nav),
        navDate: textValue(share.nav_date),
        totalAsset: numberOrNull(share.total_asset),
        establishmentDate: textValue(share.establishment_date),
        managementFeeRate: numberOrNull(share.management_fee_rate),
        custodianFeeRate: numberOrNull(share.custodian_fee_rate),
        salesServiceFeeRate: numberOrNull(share.sales_service_fee_rate),
        knownCoreFeeRate: numberOrNull(share.known_core_fee_rate),
        feeProfileStatus: textValue(share.fee_profile_status),
        feeSourceUrl: textValue(share.fee_source_url),
        feeSyncedAt: textValue(share.fee_synced_at),
        missingFeeItems: stringArray(share.missing_fee_items),
      }
    }).filter((share) => share.windCode),
    feeEvidence: {
      status: textValue(shareFeeEvidencePayload.status) || 'insufficient',
      coreFeeReadyCount: Number(shareFeeEvidencePayload.core_fee_ready_count || 0),
      salesServiceFeeReadyCount: Number(shareFeeEvidencePayload.sales_service_fee_ready_count || 0),
      note: textValue(shareFeeEvidencePayload.note),
    },
    boundary: textValue(shareClassesPayload.boundary),
    missingItems: stringArray(shareClassesPayload.missing_items),
  }

  const managerHistoryProduct = asRecord(managerHistoryPayload.product)
  const managerHistorySummary = asRecord(managerHistoryPayload.summary)
  const managerHistory: FundManagerHistorySnapshot = {
    windCode: code,
    status: textValue(managerHistoryPayload.status) || 'unavailable',
    product: {
      canonicalCode: textValue(managerHistoryProduct.canonical_code) || code,
      canonicalName: textValue(managerHistoryProduct.canonical_name),
      shareCodes: stringArray(managerHistoryProduct.share_codes),
    },
    summary: {
      managerCount: Number(managerHistorySummary.manager_count || 0),
      currentManagerCount: Number(managerHistorySummary.current_manager_count || 0),
      historicalManagerCount: Number(managerHistorySummary.historical_manager_count || 0),
      changeEventCount: Number(managerHistorySummary.change_event_count || 0),
      teamMode: textValue(managerHistorySummary.team_mode),
      firstTenureStart: textValue(managerHistorySummary.first_tenure_start),
      recordUpdatedAt: textValue(managerHistorySummary.record_updated_at),
    },
    tenures: (Array.isArray(managerHistoryPayload.tenures) ? managerHistoryPayload.tenures : []).map((value) => {
      const tenure = asRecord(value)
      return {
        managerId: textValue(tenure.manager_id),
        managerName: textValue(tenure.manager_name),
        company: textValue(tenure.company),
        startDate: textValue(tenure.start_date),
        endDate: textValue(tenure.end_date),
        isCurrent: Boolean(tenure.is_current),
        tenureDays: Number(tenure.tenure_days || 0),
        shareCodes: stringArray(tenure.share_codes),
        sources: stringArray(tenure.sources),
      }
    }).filter((tenure) => tenure.managerId && tenure.startDate),
    sources: stringArray(managerHistoryPayload.sources),
    boundary: textValue(managerHistoryPayload.boundary),
    missingItems: stringArray(managerHistoryPayload.missing_items),
  }

  const managerTenurePeerRankingPayload = asRecord(managerTenurePerformancePayload.peer_ranking)
  const managerTenurePeerMetricsPayload = asRecord(managerTenurePeerRankingPayload.metrics)
  const managerTenurePerformance: FundManagerTenurePerformance = {
    status: textValue(managerTenurePerformancePayload.status) || 'unavailable',
    coverageStatus: textValue(managerTenurePerformancePayload.coverage_status),
    requestedStartDate: textValue(managerTenurePerformancePayload.requested_start_date),
    actualStartDate: textValue(managerTenurePerformancePayload.actual_start_date),
    actualEndDate: textValue(managerTenurePerformancePayload.actual_end_date),
    requestedTenureDays: Number(managerTenurePerformancePayload.requested_tenure_days || 0),
    metricCoverageDays: Number(managerTenurePerformancePayload.metric_coverage_days || 0),
    coverageRatio: numberOrNull(managerTenurePerformancePayload.coverage_ratio),
    observations: Number(managerTenurePerformancePayload.observations || 0),
    totalReturn: numberOrNull(managerTenurePerformancePayload.total_return),
    annualizedReturn: numberOrNull(managerTenurePerformancePayload.annualized_return),
    maxDrawdown: numberOrNull(managerTenurePerformancePayload.max_drawdown),
    sharpeRatio: numberOrNull(managerTenurePerformancePayload.sharpe_ratio),
    peerRankingStatus: textValue(managerTenurePeerRankingPayload.status),
    peerGroupName: textValue(managerTenurePeerRankingPayload.peer_group_name),
    validPeerCount: Number(managerTenurePeerRankingPayload.valid_peer_count || 0),
    peerMetrics: Object.entries(managerTenurePeerMetricsPayload).map(([metricName, value]) => {
      const metric = asRecord(value)
      return {
        metricName: textValue(metric.metric_name) || metricName,
        label: textValue(metric.label) || metricName,
        value: numberOrNull(metric.value),
        rank: numberOrNull(metric.rank),
        peerCount: Number(metric.peer_count || 0),
        percentile: numberOrNull(metric.percentile),
        sampleStatus: textValue(metric.sample_status),
      }
    }),
    scopeNote: textValue(managerTenurePerformancePayload.scope_note),
    includedInScore: Boolean(managerTenurePerformancePayload.included_in_score),
  }

  const fofLatestPayload = asRecord(fofHoldingsPayload.latest)
  const fofProfilePayload = asRecord(fofHoldingsPayload.professional_profile)
  const fofEvidenceGatePayload = asRecord(fofHoldingsPayload.evidence_gate)
  const fofHoldings: FundFofHoldingSnapshot = {
    status: textValue(fofHoldingsPayload.status) || 'unavailable',
    reportDate: textValue(fofLatestPayload.report_date),
    holdingCount: Number(fofLatestPayload.holding_count || 0),
    disclosedNavRatio: numberOrNull(fofLatestPayload.disclosed_nav_ratio),
    holdings: (Array.isArray(fofLatestPayload.holdings) ? fofLatestPayload.holdings : []).map((value) => {
      const holding = asRecord(value)
      return {
        sequence: Number(holding.sequence || 0),
        fundCode: textValue(holding.underlying_fund_code),
        matchedFundCode: textValue(holding.matched_fund_code),
        fundName: textValue(holding.underlying_fund_name),
        navRatio: numberOrNull(holding.nav_ratio),
        dailyReturn: numberOrNull(holding.daily_return),
        peerGroup: textValue(holding.peer_group_name),
        classificationLabel: textValue(holding.classification_label),
        classificationStatus: textValue(holding.classification_status) || 'unmatched',
      }
    }).filter((holding) => holding.fundCode && holding.fundName),
    professionalProfile: {
      top5NavRatio: numberOrNull(fofProfilePayload.top5_nav_ratio),
      largestNavRatio: numberOrNull(fofProfilePayload.largest_nav_ratio),
      concentrationLabel: textValue(fofProfilePayload.concentration_label),
      classifiedFundCount: Number(fofProfilePayload.classified_fund_count || 0),
      classificationCoverage: numberOrNull(fofProfilePayload.classification_coverage),
      dominantClassification: textValue(fofProfilePayload.dominant_classification),
      classificationDistribution: (Array.isArray(fofProfilePayload.classification_distribution) ? fofProfilePayload.classification_distribution : []).map((value) => {
        const item = asRecord(value)
        return {
          category: textValue(item.category),
          navRatio: Number(item.nav_ratio || 0),
          shareOfDisclosed: Number(item.share_of_disclosed || 0),
        }
      }).filter((item) => item.category),
      doubleFeeStatus: textValue(fofProfilePayload.double_fee_status),
      boundary: textValue(fofProfilePayload.boundary),
    },
    evidenceGate: {
      status: textValue(fofEvidenceGatePayload.status) || 'insufficient_evidence',
      minimumDisclosedFunds: Number(fofEvidenceGatePayload.minimum_disclosed_funds || 5),
      minimumDisclosedNavRatio: Number(fofEvidenceGatePayload.minimum_disclosed_nav_ratio || 20),
      missingItems: stringArray(fofEvidenceGatePayload.missing_items),
    },
    source: textValue(fofHoldingsPayload.source),
    sourceUrl: textValue(fofHoldingsPayload.source_url),
    scope: textValue(fofHoldingsPayload.scope),
    missingItems: stringArray(fofHoldingsPayload.missing_items),
  }

  const bondDuration: FundBondDurationSnapshot = {
    windCode: textValue(bondDurationPayload.wind_code) || code,
    status: textValue(bondDurationPayload.status) || 'unavailable',
    asOfDate: textValue(bondDurationPayload.as_of_date),
    dataStart: textValue(bondDurationPayload.data_start),
    dataEnd: textValue(bondDurationPayload.data_end),
    windowWeeks: Number(bondDurationPayload.window_weeks || 104),
    observations: Number(bondDurationPayload.observations || 0),
    estimatedDuration: numberOrNull(bondDurationPayload.estimated_duration),
    durationBucket: textValue(bondDurationPayload.duration_bucket),
    rSquared: numberOrNull(bondDurationPayload.r_squared),
    trackingError: numberOrNull(bondDurationPayload.tracking_error),
    fitLabel: textValue(bondDurationPayload.fit_label) || '尚未测算',
    formalDurationReady: Boolean(bondDurationPayload.formal_duration_ready),
    weights: (Array.isArray(bondDurationPayload.weights) ? bondDurationPayload.weights : []).map((value) => {
      const row = asRecord(value)
      return {
        seriesKey: textValue(row.series_key),
        groupLabel: textValue(row.group_label),
        periodLabel: textValue(row.period_label),
        weight: Number(row.weight || 0),
        indexDuration: Number(row.index_duration || 0),
        durationContribution: Number(row.duration_contribution || 0),
      }
    }),
    missingItems: stringArray(bondDurationPayload.missing_items),
    limitations: stringArray(bondDurationPayload.limitations),
    sourceUrl: textValue(bondDurationPayload.source_url),
  }

  const bondAnomaly: FundBondAnomalySnapshot = {
    windCode: textValue(bondAnomalyPayload.wind_code) || code,
    status: textValue(bondAnomalyPayload.status) || 'unavailable',
    asOfDate: textValue(bondAnomalyPayload.as_of_date),
    dataStart: textValue(bondAnomalyPayload.data_start),
    dataEnd: textValue(bondAnomalyPayload.data_end),
    observations: Number(bondAnomalyPayload.observations || 0),
    currentSignal: textValue(bondAnomalyPayload.current_signal),
    currentLabel: textValue(bondAnomalyPayload.current_label) || '暂不可用',
    dailyReturn: numberOrNull(bondAnomalyPayload.daily_return),
    weeklyReturn: numberOrNull(bondAnomalyPayload.weekly_return),
    marketRegime: textValue(bondAnomalyPayload.market_regime),
    marketRegimeLabel: textValue(bondAnomalyPayload.market_regime_label) || '同类债市状态未知',
    anomalyCounts: Object.fromEntries(Object.entries(asRecord(bondAnomalyPayload.anomaly_counts)).map(([key, value]) => [key, Number(value || 0)])),
    events: (Array.isArray(bondAnomalyPayload.events) ? bondAnomalyPayload.events : []).map((value) => {
      const event = asRecord(value)
      return {
        date: textValue(event.date),
        reason: textValue(event.reason),
        nav: numberOrNull(event.nav),
        dailyReturn: numberOrNull(event.daily_return),
        lowerBand: numberOrNull(event.lower_band),
        peerMeanReturn: numberOrNull(event.peer_mean_return),
        peerThresholdReturn: numberOrNull(event.peer_threshold_return),
        peerCount: Number(event.peer_count || 0),
        marketAdjustment: Boolean(event.market_adjustment),
      }
    }),
    chart: (Array.isArray(bondAnomalyPayload.chart) ? bondAnomalyPayload.chart : []).map((value) => {
      const point = asRecord(value)
      return {
        date: textValue(point.date),
        navIndex: numberOrNull(point.nav_index),
        lowerBandIndex: numberOrNull(point.lower_band_index),
        peerIndex: numberOrNull(point.peer_index),
        anomaly: Boolean(point.anomaly),
        marketAdjustment: Boolean(point.market_adjustment),
      }
    }),
    peerGroupName: textValue(bondAnomalyPayload.peer_group_name),
    peerFundCount: Number(bondAnomalyPayload.peer_fund_count || 0),
    minimumPeerCount: Number(bondAnomalyPayload.minimum_peer_count || 5),
    peerModelReady: Boolean(bondAnomalyPayload.peer_model_ready),
    formalMonitorReady: Boolean(bondAnomalyPayload.formal_monitor_ready),
    sourceUrl: textValue(bondAnomalyPayload.source_url),
    missingItems: stringArray(bondAnomalyPayload.missing_items),
    limitations: stringArray(bondAnomalyPayload.limitations),
  }

  const normalizeBondHoldingPeriod = (value: unknown) => {
    const period = asRecord(value)
    const issuerConcentration = asRecord(period.issuer_concentration)
    const topIssuer = asRecord(issuerConcentration.top_issuer)
    return {
      reportDate: textValue(period.report_date),
      disclosedCount: Number(period.disclosed_count || 0),
      disclosedNavRatio: numberOrNull(period.disclosed_nav_ratio),
      classifiedNavRatio: numberOrNull(period.classified_nav_ratio),
      classificationCoverage: numberOrNull(period.classification_coverage),
      dominantType: textValue(period.dominant_type),
      metadataAvailableCount: Number(period.metadata_available_count || 0),
      metadataCoverage: numberOrNull(period.metadata_coverage),
      metadataCountCoverage: numberOrNull(period.metadata_count_coverage),
      issuerConcentration: {
        issuerCount: Number(issuerConcentration.issuer_count || 0),
        coverage: numberOrNull(issuerConcentration.coverage),
        topIssuer: topIssuer.issuer ? {
          issuer: textValue(topIssuer.issuer),
          navRatio: Number(topIssuer.nav_ratio || 0),
          shareOfDisclosed: numberOrNull(topIssuer.share_of_disclosed),
          holdingCount: Number(topIssuer.holding_count || 0),
        } : null,
        topThreeNavRatio: Number(issuerConcentration.top_three_nav_ratio || 0),
        topThreeShareOfDisclosed: numberOrNull(issuerConcentration.top_three_share_of_disclosed),
        issuers: (Array.isArray(issuerConcentration.issuers) ? issuerConcentration.issuers : []).map((value) => {
          const item = asRecord(value)
          return {
            issuer: textValue(item.issuer),
            navRatio: Number(item.nav_ratio || 0),
            shareOfDisclosed: numberOrNull(item.share_of_disclosed),
            holdingCount: Number(item.holding_count || 0),
          }
        }),
      },
      ratingDistribution: (Array.isArray(period.rating_distribution) ? period.rating_distribution : []).map((value) => {
        const item = asRecord(value)
        return {
          rating: textValue(item.rating),
          navRatio: Number(item.nav_ratio || 0),
          shareOfRated: numberOrNull(item.share_of_rated),
          holdingCount: Number(item.holding_count || 0),
          ratingTypes: stringArray(item.rating_types),
        }
      }),
      ratingCoverage: numberOrNull(period.rating_coverage),
      maturityBuckets: (Array.isArray(period.maturity_buckets) ? period.maturity_buckets : []).map((value) => {
        const item = asRecord(value)
        return {
          key: textValue(item.key),
          label: textValue(item.label),
          navRatio: Number(item.nav_ratio || 0),
          shareOfKnown: numberOrNull(item.share_of_known),
          holdingCount: Number(item.holding_count || 0),
        }
      }),
      maturityCoverage: numberOrNull(period.maturity_coverage),
      buckets: (Array.isArray(period.buckets) ? period.buckets : []).map((value) => {
        const bucket = asRecord(value)
        return {
          key: textValue(bucket.key),
          label: textValue(bucket.label),
          navRatio: Number(bucket.nav_ratio || 0),
          shareOfDisclosed: numberOrNull(bucket.share_of_disclosed),
          holdingCount: Number(bucket.holding_count || 0),
        }
      }),
      holdings: (Array.isArray(period.holdings) ? period.holdings : []).map((value) => {
        const holding = asRecord(value)
        const bondType = textValue(holding.bond_type)
        const typeLabels: Record<string, string> = {
          convertible_exchangeable: '可转债/可交换债',
          policy_bank: '政策性金融债',
          financial: '金融债/资本债',
          government: '国债',
          local_government: '地方政府债',
          government_local: '国债/地方政府债（旧口径）',
          credit: '企业信用债',
          interbank_cd: '同业存单',
          asset_backed: '资产支持证券',
          other: '其他/待核验',
        }
        return {
          sequence: Number(holding.sequence || 0),
          bondCode: textValue(holding.bond_code),
          bondName: textValue(holding.bond_name),
          bondType,
          bondTypeLabel: typeLabels[bondType] || bondType || '其他/待核验',
          navRatio: numberOrNull(holding.nav_ratio),
          marketValueWan: numberOrNull(holding.market_value_wan),
          classificationBasis: textValue(holding.classification_basis),
          issuer: textValue(holding.issuer),
          securityBondType: textValue(holding.security_bond_type),
          creditRating: textValue(holding.credit_rating),
          ratingType: textValue(holding.rating_type),
          maturityDate: textValue(holding.maturity_date),
          remainingYears: numberOrNull(holding.remaining_years),
          couponRate: numberOrNull(holding.coupon_rate),
          metadataSource: textValue(holding.metadata_source),
          metadataUrl: textValue(holding.metadata_url),
          metadataStatus: textValue(holding.metadata_status),
        }
      }),
    }
  }
  const bondHoldingHistory = (Array.isArray(bondHoldingsPayload.history) ? bondHoldingsPayload.history : [])
    .map(normalizeBondHoldingPeriod)
    .filter((period) => period.reportDate)
  const professionalProfilePayload = asRecord(bondHoldingsPayload.professional_profile)
  const professionalProfileAverages = asRecord(professionalProfilePayload.averages)
  const bondHoldings: FundBondHoldingSnapshot = {
    status: textValue(bondHoldingsPayload.status) || 'unavailable',
    latest: bondHoldingsPayload.latest ? normalizeBondHoldingPeriod(bondHoldingsPayload.latest) : null,
    history: bondHoldingHistory,
    professionalProfile: {
      status: textValue(professionalProfilePayload.status) || 'insufficient_periods',
      label: textValue(professionalProfilePayload.label),
      periodCount: Number(professionalProfilePayload.period_count || 0),
      requiredPeriods: Number(professionalProfilePayload.required_periods || 4),
      averages: {
        rateShare: numberOrNull(professionalProfileAverages.rate_share),
        localGovernmentShare: numberOrNull(professionalProfileAverages.local_government_share),
        financialShare: numberOrNull(professionalProfileAverages.financial_share),
        creditShare: numberOrNull(professionalProfileAverages.credit_share),
        convertibleShare: numberOrNull(professionalProfileAverages.convertible_share),
        otherShare: numberOrNull(professionalProfileAverages.other_share),
        highRatingShare: numberOrNull(professionalProfileAverages.high_rating_share),
        bondRatingCoverage: numberOrNull(professionalProfileAverages.bond_rating_coverage),
        issuerRatingCoverage: numberOrNull(professionalProfileAverages.issuer_rating_coverage),
        metadataCoverage: numberOrNull(professionalProfileAverages.metadata_coverage),
        classificationCoverage: numberOrNull(professionalProfileAverages.classification_coverage),
      },
      periods: (Array.isArray(professionalProfilePayload.periods) ? professionalProfilePayload.periods : []).map((value) => {
        const period = asRecord(value)
        return {
          reportDate: textValue(period.report_date),
          rateShare: numberOrNull(period.rate_share),
          localGovernmentShare: numberOrNull(period.local_government_share),
          financialShare: numberOrNull(period.financial_share),
          creditShare: numberOrNull(period.credit_share),
          convertibleShare: numberOrNull(period.convertible_share),
          bondRatingCoverage: numberOrNull(period.bond_rating_coverage),
          metadataCoverage: numberOrNull(period.metadata_coverage),
        }
      }),
      secondaryLabels: stringArray(professionalProfilePayload.secondary_labels),
      basis: textValue(professionalProfilePayload.basis),
      methodology: textValue(professionalProfilePayload.methodology),
      limitations: stringArray(professionalProfilePayload.limitations),
      formalClassificationReady: Boolean(professionalProfilePayload.formal_classification_ready),
    },
    source: textValue(bondHoldingsPayload.source),
    sourceUrl: textValue(bondHoldingsPayload.source_url),
    scope: textValue(bondHoldingsPayload.scope),
    classificationMethod: textValue(bondHoldingsPayload.classification_method),
    missingItems: stringArray(bondHoldingsPayload.missing_items),
  }

  const normalizeHolderStructureRow = (value: unknown) => {
    const row = asRecord(value)
    return {
      reportDate: textValue(row.report_date),
      institutionRatio: numberOrNull(row.institution_ratio),
      individualRatio: numberOrNull(row.individual_ratio),
      internalRatio: numberOrNull(row.internal_ratio),
      totalSharesYi: numberOrNull(row.total_shares_yi),
      source: textValue(row.source),
      sourceUrl: textValue(row.source_url),
    }
  }
  const holderStructureComparisonPayload = asRecord(holderStructurePayload.comparison)
  const holderStructure: FundHolderStructureSnapshot = {
    status: textValue(holderStructurePayload.status) || 'unavailable',
    latest: holderStructurePayload.latest ? normalizeHolderStructureRow(holderStructurePayload.latest) : null,
    previous: holderStructurePayload.previous ? normalizeHolderStructureRow(holderStructurePayload.previous) : null,
    comparison: holderStructurePayload.comparison ? {
      previousReportDate: textValue(holderStructureComparisonPayload.previous_report_date),
      institutionRatioChange: numberOrNull(holderStructureComparisonPayload.institution_ratio_change),
      individualRatioChange: numberOrNull(holderStructureComparisonPayload.individual_ratio_change),
      internalRatioChange: numberOrNull(holderStructureComparisonPayload.internal_ratio_change),
      totalSharesYiChange: numberOrNull(holderStructureComparisonPayload.total_shares_yi_change),
    } : null,
    history: (Array.isArray(holderStructurePayload.history) ? holderStructurePayload.history : [])
      .map(normalizeHolderStructureRow)
      .filter((row) => row.reportDate),
    source: textValue(holderStructurePayload.source),
    sourceUrl: textValue(holderStructurePayload.source_url),
    scope: textValue(holderStructurePayload.scope),
    internalRatioNote: textValue(holderStructurePayload.internal_ratio_note),
    missingItems: stringArray(holderStructurePayload.missing_items),
  }

  const normalizeHoldingChange = (value: unknown): FundHoldingChange => {
    const item = asRecord(value)
    return {
      stockCode: textValue(item.stock_code),
      stockName: textValue(item.stock_name),
      industry: textValue(item.industry),
      latestWeight: numberOrNull(item.latest_weight),
      previousWeight: numberOrNull(item.previous_weight),
      weightChange: numberOrNull(item.weight_change),
      changeType: textValue(item.change_type),
    }
  }
  const holdingChangesSummary = asRecord(holdingChangesPayload.summary)
  const holdingChangesStability = asRecord(holdingChangesPayload.stability)
  const holdingChanges: FundHoldingChanges = {
    status: textValue(holdingChangesPayload.status) || 'insufficient_evidence',
    latestQuarter: textValue(holdingChangesPayload.latest_quarter),
    previousQuarter: textValue(holdingChangesPayload.previous_quarter),
    latestReportDate: textValue(holdingChangesPayload.latest_report_date),
    previousReportDate: textValue(holdingChangesPayload.previous_report_date),
    weightBasis: textValue(holdingChangesPayload.weight_basis),
    changes: (Array.isArray(holdingChangesPayload.changes) ? holdingChangesPayload.changes : []).map(normalizeHoldingChange),
    concentrationTrend: (Array.isArray(holdingChangesPayload.concentration_trend) ? holdingChangesPayload.concentration_trend : []).map((value) => {
      const item = asRecord(value)
      return {
        quarter: textValue(item.quarter),
        reportDate: textValue(item.report_date),
        top3Weight: numberOrNull(item.top3_weight),
        top10Weight: numberOrNull(item.top10_weight),
        topIndustry: textValue(item.top_industry),
        topIndustryWeight: numberOrNull(item.top_industry_weight),
      }
    }),
    industryChanges: (Array.isArray(holdingChangesPayload.industry_changes) ? holdingChangesPayload.industry_changes : []).map((value) => {
      const item = asRecord(value)
      return {
        industry: textValue(item.industry),
        latestWeight: numberOrNull(item.latest_weight),
        previousWeight: numberOrNull(item.previous_weight),
        weightChange: numberOrNull(item.weight_change),
      }
    }),
    stability: {
      status: textValue(holdingChangesStability.status) || 'insufficient_evidence',
      level: textValue(holdingChangesStability.level),
      label: textValue(holdingChangesStability.label),
      top10OverlapRatio: numberOrNull(holdingChangesStability.top10_overlap_ratio),
      industryOverlapRatio: numberOrNull(holdingChangesStability.industry_overlap_ratio),
      jaccardScore: numberOrNull(holdingChangesStability.jaccard_score),
      retainedHoldingCount: Number(holdingChangesStability.retained_holding_count || 0),
      unionHoldingCount: Number(holdingChangesStability.union_holding_count || 0),
      boundary: textValue(holdingChangesStability.boundary),
    },
    summary: {
      enteredTop10Count: Number(holdingChangesSummary.entered_top10_count || 0),
      exitedTop10Count: Number(holdingChangesSummary.exited_top10_count || 0),
      largestIncrease: holdingChangesSummary.largest_increase ? normalizeHoldingChange(holdingChangesSummary.largest_increase) : null,
      largestDecrease: holdingChangesSummary.largest_decrease ? normalizeHoldingChange(holdingChangesSummary.largest_decrease) : null,
      latestTop3Weight: numberOrNull(holdingChangesSummary.latest_top3_weight),
      latestTop10Weight: numberOrNull(holdingChangesSummary.latest_top10_weight),
      top3WeightChange: numberOrNull(holdingChangesSummary.top3_weight_change),
      top10WeightChange: numberOrNull(holdingChangesSummary.top10_weight_change),
    },
    scope: textValue(holdingChangesPayload.scope),
    missingItems: stringArray(holdingChangesPayload.missing_items),
  }

  const styleEvidencePayload = asRecord(assessmentPayload.style_evidence)
  const styleDriftEvidencePayload = asRecord(assessmentPayload.style_drift_evidence)
  const managerStabilityEvidencePayload = asRecord(assessmentPayload.manager_stability_evidence)
  const scaleTrendEvidencePayload = asRecord(assessmentPayload.scale_trend_evidence)
  const drawdownRecoveryEvidencePayload = asRecord(assessmentPayload.drawdown_recovery_evidence)
  const researchEvidencePayload = asRecord(assessmentPayload.research_evidence)
  const attributionEvidencePayload = asRecord(assessmentPayload.attribution_evidence)
  const assessmentSummary: FundAssessmentSummary = {
    status: textValue(assessmentPayload.status) || 'unavailable',
    evaluationWindow: textValue(assessmentPayload.evaluation_window) || '1y',
    evaluationWindowLabel: textValue(assessmentPayload.evaluation_window_label) || '近 1 年',
    verdict: textValue(assessmentPayload.verdict),
    peerGroup: textValue(assessmentPayload.peer_group),
    score: numberOrNull(assessmentPayload.score),
    grade: textValue(assessmentPayload.grade),
    peerRank: numberOrNull(assessmentPayload.peer_rank),
    peerCount: numberOrNull(assessmentPayload.peer_count),
    peerPercentile: numberOrNull(assessmentPayload.peer_percentile),
    advantages: stringArray(assessmentPayload.advantages),
    risks: stringArray(assessmentPayload.risks),
    managerStabilityEvidence: {
      status: textValue(managerStabilityEvidencePayload.status) || 'unavailable',
      label: textValue(managerStabilityEvidencePayload.label),
      currentManagerCount: Number(managerStabilityEvidencePayload.current_manager_count || 0),
      currentManagerNames: stringArray(managerStabilityEvidencePayload.current_manager_names),
      teamMode: textValue(managerStabilityEvidencePayload.team_mode),
      currentTeamStart: textValue(managerStabilityEvidencePayload.current_team_start),
      currentTeamDays: Number(managerStabilityEvidencePayload.current_team_days || 0),
      latestChangeDate: textValue(managerStabilityEvidencePayload.latest_change_date),
      changesLastYear: Number(managerStabilityEvidencePayload.changes_last_year || 0),
      changesLastThreeYears: Number(managerStabilityEvidencePayload.changes_last_three_years || 0),
      includedInScore: Boolean(managerStabilityEvidencePayload.included_in_score),
      note: textValue(managerStabilityEvidencePayload.note),
    },
    scaleTrendEvidence: {
      status: textValue(scaleTrendEvidencePayload.status) || 'insufficient_evidence',
      label: textValue(scaleTrendEvidencePayload.label),
      latestReportDate: textValue(scaleTrendEvidencePayload.latest_report_date),
      latestAssetYi: numberOrNull(scaleTrendEvidencePayload.latest_asset_yi),
      oneYearChange: numberOrNull(scaleTrendEvidencePayload.one_year_change),
      threeYearChange: numberOrNull(scaleTrendEvidencePayload.three_year_change),
      peakAssetYi: numberOrNull(scaleTrendEvidencePayload.peak_asset_yi),
      peakDate: textValue(scaleTrendEvidencePayload.peak_date),
      latestFromPeak: numberOrNull(scaleTrendEvidencePayload.latest_from_peak),
      observations: Number(scaleTrendEvidencePayload.observations || 0),
      includedInScore: Boolean(scaleTrendEvidencePayload.included_in_score),
      note: textValue(scaleTrendEvidencePayload.note),
    },
    drawdownRecoveryEvidence: {
      status: textValue(drawdownRecoveryEvidencePayload.status) || 'insufficient_evidence',
      label: textValue(drawdownRecoveryEvidencePayload.label),
      historyStart: textValue(drawdownRecoveryEvidencePayload.history_start),
      historyEnd: textValue(drawdownRecoveryEvidencePayload.history_end),
      navBasis: textValue(drawdownRecoveryEvidencePayload.nav_basis),
      observations: Number(drawdownRecoveryEvidencePayload.observations || 0),
      currentDrawdown: numberOrNull(drawdownRecoveryEvidencePayload.current_drawdown),
      currentUnderwaterDays: Number(drawdownRecoveryEvidencePayload.current_underwater_days || 0),
      worstDrawdown: numberOrNull(drawdownRecoveryEvidencePayload.worst_drawdown),
      worstRecoveryDays: numberOrNull(drawdownRecoveryEvidencePayload.worst_recovery_days),
      longestUnderwaterDays: Number(drawdownRecoveryEvidencePayload.longest_underwater_days || 0),
      materialEpisodeCount: Number(drawdownRecoveryEvidencePayload.material_episode_count || 0),
      recoveredMaterialEpisodeCount: Number(drawdownRecoveryEvidencePayload.recovered_material_episode_count || 0),
      includedInScore: Boolean(drawdownRecoveryEvidencePayload.included_in_score),
      note: textValue(drawdownRecoveryEvidencePayload.note),
    },
    styleEvidence: {
      status: textValue(styleEvidencePayload.status),
      labels: stringArray(styleEvidencePayload.labels),
      memoLabels: stringArray(styleEvidencePayload.memo_labels),
      quarter: textValue(styleEvidencePayload.quarter),
      sampleSize: Number(styleEvidencePayload.sample_size || 0),
      scope: textValue(styleEvidencePayload.scope),
      note: textValue(styleEvidencePayload.note),
    },
    styleDriftEvidence: {
      status: textValue(styleDriftEvidencePayload.status) || 'insufficient_evidence',
      level: textValue(styleDriftEvidencePayload.level) || 'unavailable',
      label: textValue(styleDriftEvidencePayload.label),
      previousQuarter: textValue(styleDriftEvidencePayload.previous_quarter),
      latestQuarter: textValue(styleDriftEvidencePayload.latest_quarter),
      factorCount: Number(styleDriftEvidencePayload.factor_count || 0),
      changedFactorCount: Number(styleDriftEvidencePayload.changed_factor_count || 0),
      maxPercentileChange: numberOrNull(styleDriftEvidencePayload.max_percentile_change),
      addedLabels: stringArray(styleDriftEvidencePayload.added_labels),
      removedLabels: stringArray(styleDriftEvidencePayload.removed_labels),
      includedInScore: Boolean(styleDriftEvidencePayload.included_in_score),
      note: textValue(styleDriftEvidencePayload.note),
      boundary: textValue(styleDriftEvidencePayload.boundary),
    },
    researchEvidence: {
      status: textValue(researchEvidencePayload.status),
      count: Number(researchEvidencePayload.count || 0),
      fundLevelCount: Number(researchEvidencePayload.fund_level_count ?? researchEvidencePayload.fund_specific_count ?? 0),
      fundSpecificCount: Number(researchEvidencePayload.fund_specific_count || 0),
      managerLevelCount: Number(researchEvidencePayload.manager_level_count || 0),
      latestTitle: textValue(researchEvidencePayload.latest_title),
      latestDate: textValue(researchEvidencePayload.latest_date),
      note: textValue(researchEvidencePayload.note),
    },
    attributionEvidence: {
      status: textValue(attributionEvidencePayload.status) || 'not_run',
      mode: textValue(attributionEvidencePayload.mode),
      headline: textValue(attributionEvidencePayload.headline),
      detail: textValue(attributionEvidencePayload.detail),
      quarter: textValue(attributionEvidencePayload.quarter),
      activeReturn: numberOrNull(attributionEvidencePayload.active_return),
      coverage: numberOrNull(attributionEvidencePayload.coverage),
      formalBarraReady: Boolean(attributionEvidencePayload.formal_barra_ready),
      barraDescriptorReady: Boolean(attributionEvidencePayload.barra_descriptor_ready),
    },
    boundary: textValue(assessmentPayload.boundary),
  }

  const detailHighlights: FundDetailHighlight[] = detailHighlightPayload.map((value) => {
    const item = asRecord(value)
    const rawTone = textValue(item.tone)
    const tone: FundDetailHighlight['tone'] = rawTone === 'strength' || rawTone === 'risk' ? rawTone : 'neutral'
    return {
      id: textValue(item.id),
      tone,
      label: textValue(item.label),
      value: textValue(item.value),
      detail: textValue(item.detail),
      source: textValue(item.source),
      asOfDate: textValue(item.as_of_date),
      metricName: textValue(item.metric_name),
    }
  }).filter((item: FundDetailHighlight) => item.id && item.label)

  const plainLanguageBrief: FundPlainLanguageBrief = {
    status: textValue(plainLanguageBriefPayload.status) || 'insufficient_evidence',
    title: textValue(plainLanguageBriefPayload.title) || '一分钟看懂这只基金',
    fundName: textValue(plainLanguageBriefPayload.fund_name),
    evidenceCount: Number(plainLanguageBriefPayload.evidence_count || 0),
    items: (Array.isArray(plainLanguageBriefPayload.items) ? plainLanguageBriefPayload.items : []).map((value) => {
      const item = asRecord(value)
      return {
        key: textValue(item.key),
        label: textValue(item.label),
        text: textValue(item.text),
        status: textValue(item.status),
        source: textValue(item.source),
        asOfDate: textValue(item.as_of_date),
        evidenceId: textValue(item.evidence_id),
      }
    }).filter((item) => item.key && item.text),
    copyText: textValue(plainLanguageBriefPayload.copy_text),
    boundary: textValue(plainLanguageBriefPayload.boundary),
  }

  const latestRawNavPoint = rawNavPoints[rawNavPoints.length - 1]
  const latestNavPoint = nav[nav.length - 1]
  const resolvedFund: CamelFund = {
    ...fund,
    nav: fund.nav ?? latestRawNavPoint?.unitNav ?? latestNavPoint?.nav ?? null,
    navDate: fund.navDate || latestRawNavPoint?.date || latestNavPoint?.date || null,
  }

  return { fund: resolvedFund, nav, evaluationWindows, evaluationHistory, assessmentSummary, detailHighlights, plainLanguageBrief, researchMemos, dataQuality, shareClasses, managerHistory, managerTenurePerformance, assetAllocation, drawdownRecovery, periodPerformance, fofHoldings, bondAnomaly, bondDuration, bondHoldings, holderStructure, holdingSnapshot, holdingChanges, holdingStyle, holdingExperience, productProfile }
}

export default async function FundDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const data = await loadFundDetail(id)

  if (!data) {
    return (
      <div className="mx-auto max-w-3xl py-12 text-center">
        <CircleAlert className="mx-auto h-7 w-7 text-[#8d6a2f]" />
        <h1 className="mt-4 text-3xl font-bold text-[#18231e]">暂时无法读取这只基金</h1>
        <p className="mt-3 text-sm leading-7 text-[#68746e]">基金代码为 {id}。请确认后端基金数据库已启动，或返回重新搜索。</p>
        <Link href="/discover" className="mt-7 inline-flex h-11 items-center gap-2 rounded-md bg-[#173f35] px-5 text-sm font-bold text-white"><ArrowLeft className="h-4 w-4" />返回找基金</Link>
      </div>
    )
  }

  return <SimpleFundDetailClient {...data} />
}
