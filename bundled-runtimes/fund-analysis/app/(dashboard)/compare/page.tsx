import { backendApiBaseUrl, toCamelFund, type CamelFund } from '@/lib/backend-api'
import SimpleComparisonClient, { type AlignedComparison, type ComparisonFund, type HoldingSimilaritySnapshot } from './SimpleComparisonClient'

export const dynamic = 'force-dynamic'

const evaluationWindowKeys = ['6m', '1y', '3y'] as const

type UnknownRecord = Record<string, unknown>

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {}
}

function textValue(value: unknown) {
  return value == null ? '' : String(value)
}

function numberValue(value: unknown) {
  if (value == null || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function parseCodes(value?: string | string[]) {
  const raw = Array.isArray(value) ? value.join(',') : value || ''
  return Array.from(new Set(raw.split(',').map((code) => code.trim().toUpperCase()).filter(Boolean))).slice(0, 6)
}

async function loadComparisonFund(code: string): Promise<ComparisonFund | null> {
  const [snapshotResponse, holdingsResponse] = await Promise.all([
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/research-snapshot`, { cache: 'no-store' }),
    fetch(`${backendApiBaseUrl}/api/funds/${encodeURIComponent(code)}/holdings?local_only=true`, { cache: 'no-store' }),
  ])
  if (!snapshotResponse.ok) return null

  const snapshot = asRecord(await snapshotResponse.json().catch(() => ({})))
  const evaluationPayload = asRecord(snapshot.evaluation)
  const classification = asRecord(evaluationPayload.classification)
  const peerContext = asRecord(evaluationPayload.peer_context)
  const evaluation = asRecord(evaluationPayload.evaluation)
  const dataQuality = asRecord(evaluation.data_quality)
  const metricScores = asRecord(evaluation.metric_scores)
  const evaluationWindowsPayload = asRecord(snapshot.evaluation_windows)
  const managers = Array.isArray(snapshot.managers) ? snapshot.managers.map(asRecord) : []
  const researchProfile = asRecord(snapshot.research_profile)
  const researchMemos = asRecord(snapshot.research_memos)
  const periodPerformancePayload = asRecord(snapshot.period_performance)
  const periodPerformanceSummary = asRecord(periodPerformancePayload.summary)
  const managerTenurePerformancePayload = asRecord(snapshot.manager_tenure_performance)
  const multiPeriodEvidencePayload = asRecord(snapshot.multi_period_evidence)
  const managerTenurePeerRanking = asRecord(managerTenurePerformancePayload.peer_ranking)
  const managerTenurePeerMetrics = asRecord(managerTenurePeerRanking.metrics)
  const managerTenureReturnRank = asRecord(managerTenurePeerMetrics.total_return)
  const rollingMetrics = { ...asRecord(snapshot.rolling_metrics) } as Record<string, Record<string, unknown>>

  for (const [path, value] of Object.entries(metricScores)) {
    const separator = path.indexOf('.')
    if (separator <= 0 || value == null) continue
    const metricWindow = path.slice(0, separator)
    const metricName = path.slice(separator + 1)
    rollingMetrics[metricWindow] = {
      ...(rollingMetrics[metricWindow] || {}),
      [metricName]: value,
    }
  }

  const fund = toCamelFund({
    ...asRecord(snapshot.fund),
    managers,
    research_profile: researchProfile,
    rolling_metrics: rollingMetrics,
    data_quality: snapshot.data_quality,
  }) as CamelFund

  if (fund.totalAsset == null && metricScores['latest.aum'] != null) {
    fund.totalAsset = Number(metricScores['latest.aum'])
  }
  const holdingsPayload = holdingsResponse.ok ? asRecord(await holdingsResponse.json().catch(() => ({}))) : {}
  const holdingSummary = asRecord(holdingsPayload.summary)
  const holdings = Array.isArray(holdingsPayload.holdings) ? holdingsPayload.holdings.map(asRecord) : []

  const evaluationReady = textValue(evaluationPayload.status) !== 'insufficient_evidence'
    && textValue(dataQuality.status) !== 'insufficient'
  const score = numberValue(evaluation.overall_score)

  // Attribution / style / memo evidence for the three-sided evidence strip
  const assessmentSummary = asRecord(snapshot.assessment_summary ?? evaluationPayload.assessment_summary)
  const attributionEvidenceRecord = asRecord(assessmentSummary.attribution_evidence)
  const styleEvidenceRecord = asRecord(assessmentSummary.style_evidence)
  const memoItemsRaw = Array.isArray(researchMemos.items) ? researchMemos.items.map(asRecord) : []
  const memoHighlights = memoItemsRaw.slice(0, 3).map((memo) => {
    const scopeRaw = textValue(memo.scope || memo.memo_scope).toLowerCase()
    const scope: 'fund' | 'manager' | 'other' =
      scopeRaw === 'fund' || scopeRaw === 'fund_specific' ? 'fund'
      : scopeRaw === 'manager' || scopeRaw === 'manager_level' ? 'manager'
      : 'other'
    return {
      id: textValue(memo.id || memo.report_id),
      title: textValue(memo.title) || '无标题纪要',
      reportDate: textValue(memo.report_date),
      managerName: textValue(memo.manager_name),
      scope,
      summary: textValue(memo.summary || memo.excerpt || memo.viewpoint),
    }
  })

  const evaluationWindows = Object.fromEntries(evaluationWindowKeys.map((key) => {
    const windowPayload = asRecord(evaluationWindowsPayload[key] || (key === '1y' ? evaluationPayload : {}))
    const windowPeerContext = asRecord(windowPayload.peer_context)
    const windowEvaluation = asRecord(windowPayload.evaluation)
    const professionalPosition = asRecord(asRecord(windowEvaluation.peer_percentiles).professional_score)
    const ready = textValue(windowPayload.status) !== 'insufficient_evidence'
      && textValue(asRecord(windowEvaluation.data_quality).status) !== 'insufficient'
    return [key, {
      status: textValue(windowPayload.status) || 'unavailable',
      sampleStatus: textValue(windowPeerContext.sample_status) || 'unavailable',
      validPeerCount: numberValue(windowPeerContext.valid_metric_peer_count) || 0,
      minimumPeerCount: numberValue(windowPeerContext.minimum_peer_count) || 0,
      score: ready ? numberValue(windowEvaluation.overall_score) : null,
      grade: ready ? textValue(windowEvaluation.overall_grade) : '',
      peerRank: ready ? numberValue(professionalPosition.rank) : null,
      peerCount: ready ? numberValue(professionalPosition.peer_count) : null,
      peerPercentile: ready ? numberValue(professionalPosition.percentile) : null,
    }]
  })) as ComparisonFund['evaluationWindows']

  const firstHolding = holdings[0] || {}

  return {
    fund,
    classification: {
      status: textValue(classification.status) || 'unclassified',
      peerGroup: textValue(classification.peer_group),
      peerGroupId: textValue(classification.peer_group_id),
      benchmark: textValue(classification.primary_benchmark),
    },
    evaluation: {
      status: textValue(evaluationPayload.status) || 'unavailable',
      sampleStatus: textValue(peerContext.sample_status) || 'unavailable',
      validPeerCount: numberValue(peerContext.valid_metric_peer_count) || 0,
      minimumPeerCount: numberValue(peerContext.minimum_peer_count) || 0,
      score: evaluationReady ? score : null,
      grade: evaluationReady ? textValue(evaluation.overall_grade) : '',
    },
    evaluationWindows,
    holding: {
      latestQuarter: textValue(holdingsPayload.latest_quarter),
      reportDate: textValue(holdingSummary.report_date),
      announcementDate: textValue(holdingSummary.announcement_date),
      holdingCount: numberValue(holdingSummary.holding_count) || 0,
      weightBasis: textValue(holdingSummary.weight_basis),
      topTenWeight: numberValue(holdingSummary.top_ten_weight),
      topTenEquityWeight: numberValue(holdingSummary.top_ten_equity_weight),
      firstStockName: textValue(firstHolding.stock_name),
      firstStockWeight: numberValue(
        textValue(holdingSummary.weight_basis) === 'fund_nav'
          ? firstHolding.fund_nav_weight ?? firstHolding.weight
          : firstHolding.equity_portfolio_weight,
      ),
    },
    managers: managers.map((manager) => ({
      id: textValue(manager.manager_id || manager.wind_code || manager.name),
      name: textValue(manager.name) || '经理待补充',
      managementYears: numberValue(manager.management_years),
      beginDate: textValue(manager.begin_date),
    })),
    managerTenureStart: textValue(researchProfile.manager_tenure_start),
    managerTenurePerformance: {
      status: textValue(managerTenurePerformancePayload.status) || 'unavailable',
      coverageStatus: textValue(managerTenurePerformancePayload.coverage_status),
      requestedStartDate: textValue(managerTenurePerformancePayload.requested_start_date),
      actualStartDate: textValue(managerTenurePerformancePayload.actual_start_date),
      actualEndDate: textValue(managerTenurePerformancePayload.actual_end_date),
      coverageRatio: numberValue(managerTenurePerformancePayload.coverage_ratio),
      observations: numberValue(managerTenurePerformancePayload.observations) || 0,
      totalReturn: numberValue(managerTenurePerformancePayload.total_return),
      annualizedReturn: numberValue(managerTenurePerformancePayload.annualized_return),
      maxDrawdown: numberValue(managerTenurePerformancePayload.max_drawdown),
      sharpeRatio: numberValue(managerTenurePerformancePayload.sharpe_ratio),
      peerRankingStatus: textValue(managerTenurePeerRanking.status),
      peerRank: numberValue(managerTenureReturnRank.rank),
      peerCount: numberValue(managerTenureReturnRank.peer_count),
      peerPercentile: numberValue(managerTenureReturnRank.percentile),
      scopeNote: textValue(managerTenurePerformancePayload.scope_note),
    },
    multiPeriodEvidence: {
      status: textValue(multiPeriodEvidencePayload.status) || 'short_term_only',
      return6m: numberValue(multiPeriodEvidencePayload.return_6m),
      return1y: numberValue(multiPeriodEvidencePayload.return_1y),
      annualizedReturn1y: numberValue(multiPeriodEvidencePayload.annualized_return_1y),
      annualizedReturn3y: numberValue(multiPeriodEvidencePayload.annualized_return_3y),
      maxDrawdown1y: numberValue(multiPeriodEvidencePayload.max_drawdown_1y),
      maxDrawdown3y: numberValue(multiPeriodEvidencePayload.max_drawdown_3y),
      sharpeRatio3y: numberValue(multiPeriodEvidencePayload.sharpe_ratio_3y),
      annualizedReturnGap: numberValue(multiPeriodEvidencePayload.annualized_return_gap),
      consistencyStatus: textValue(multiPeriodEvidencePayload.consistency_status),
      consistencyLabel: textValue(multiPeriodEvidencePayload.consistency_label),
      usedInScore: Boolean(multiPeriodEvidencePayload.used_in_score),
      dataAsOf: textValue(multiPeriodEvidencePayload.data_as_of),
    },
    researchMemoCount: numberValue(researchMemos.count) || 0,
    attributionEvidence: {
      status: textValue(attributionEvidenceRecord.status) || 'unavailable',
      headline: textValue(attributionEvidenceRecord.headline),
      detail: textValue(attributionEvidenceRecord.detail),
      coverage: numberValue(attributionEvidenceRecord.coverage),
      formalBarraReady: Boolean(attributionEvidenceRecord.formal_barra_ready),
      barraDescriptorReady: Boolean(attributionEvidenceRecord.barra_descriptor_ready),
    },
    styleEvidence: {
      status: textValue(styleEvidenceRecord.status) || 'unavailable',
      scope: textValue(styleEvidenceRecord.scope),
      quarter: textValue(styleEvidenceRecord.quarter),
      labels: Array.isArray(styleEvidenceRecord.labels) ? styleEvidenceRecord.labels.map(textValue).filter(Boolean) : [],
      memoLabels: Array.isArray(styleEvidenceRecord.memo_labels) ? styleEvidenceRecord.memo_labels.map(textValue).filter(Boolean) : [],
    },
    memoHighlights,
    periodPerformance: {
      status: textValue(periodPerformancePayload.status) || 'insufficient_evidence',
      navBasis: textValue(periodPerformancePayload.nav_basis),
      latestNavDate: textValue(periodPerformancePayload.latest_nav_date),
      peerGroupName: textValue(periodPerformancePayload.peer_group_name),
      periods: (Array.isArray(periodPerformancePayload.periods) ? periodPerformancePayload.periods : [])
        .flatMap((value) => {
          const period = asRecord(value)
          const year = Number(period.year || 0)
          const label = textValue(period.label)
          const periodReturn = numberValue(period.return)
          if (year <= 0 || !label || periodReturn == null) return []
          return [{
            year,
            label,
            isYtd: Boolean(period.is_ytd),
            return: periodReturn,
            coverageStatus: textValue(period.coverage_status),
            observationCoverage: numberValue(period.observation_coverage),
            rank: numberValue(period.rank),
            peerCount: numberValue(period.peer_count) || 0,
            percentile: numberValue(period.percentile),
            peerMedianReturn: numberValue(period.peer_median_return),
            abovePeerMedian: typeof period.above_peer_median === 'boolean' ? period.above_peer_median : null,
          }]
        }),
      summary: {
        completePeriodCount: Number(periodPerformanceSummary.complete_period_count || 0),
        positivePeriodCount: Number(periodPerformanceSummary.positive_period_count || 0),
        peerRankedPeriodCount: Number(periodPerformanceSummary.peer_ranked_period_count || 0),
        abovePeerMedianCount: Number(periodPerformanceSummary.above_peer_median_count || 0),
      },
      boundary: textValue(periodPerformancePayload.boundary),
    },
  }
}

async function loadAlignedComparison(codes: string[]): Promise<AlignedComparison | null> {
  if (codes.length < 2) return null
  const response = await fetch(`${backendApiBaseUrl}/api/funds/compare-aligned`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ windCodes: codes }),
    cache: 'no-store',
  })
  if (!response.ok) return null
  const payload = asRecord(await response.json().catch(() => ({})))
  const sourceWindows = asRecord(payload.windows)
  const windows = Object.fromEntries(evaluationWindowKeys.map((key) => {
    const source = asRecord(sourceWindows[key])
    const sourceFunds = Array.isArray(source.funds) ? source.funds.map(asRecord) : []
    return [key, {
      status: textValue(source.status) || 'insufficient',
      requestedStartDate: textValue(source.requested_start_date),
      actualStartDate: textValue(source.actual_start_date),
      actualEndDate: textValue(source.actual_end_date),
      observations: numberValue(source.observations) || 0,
      actualSpanDays: numberValue(source.actual_span_days) || 0,
      calendarCoverageRatio: numberValue(source.calendar_coverage_ratio) || 0,
      observationCoverageRatio: numberValue(source.observation_coverage_ratio) || 0,
      rankingEligible: source.ranking_eligible === true,
      scopeNote: textValue(source.scope_note),
      funds: Object.fromEntries(sourceFunds.map((item) => {
        const windCode = textValue(item.wind_code)
        return [windCode, {
          windCode,
          navBasis: textValue(item.nav_basis),
          observations: numberValue(item.observations) || 0,
          totalReturn: numberValue(item.total_return),
          annualizedReturn: numberValue(item.annualized_return),
          maxDrawdown: numberValue(item.max_drawdown),
          annualizedVolatility: numberValue(item.annualized_volatility),
          sharpeRatio: numberValue(item.sharpe_ratio),
          drawdownStatus: textValue(item.drawdown_status),
          drawdownLabel: textValue(item.drawdown_label),
          currentDrawdown: numberValue(item.current_drawdown),
          currentUnderwaterDays: numberValue(item.current_underwater_days) || 0,
          worstDeclineDays: numberValue(item.worst_decline_days) || 0,
          worstRecoveryDays: numberValue(item.worst_recovery_days),
          worstRecovered: Boolean(item.worst_recovered),
          longestUnderwaterDays: numberValue(item.longest_underwater_days) || 0,
          materialEpisodeCount: numberValue(item.material_episode_count) || 0,
          recoveredMaterialEpisodeCount: numberValue(item.recovered_material_episode_count) || 0,
        }]
      }).filter(([windCode]) => Boolean(windCode))),
      chart: (Array.isArray(source.chart) ? source.chart.map(asRecord) : []).map((point) => ({
        date: textValue(point.date),
        values: Object.fromEntries(Object.entries(asRecord(point.values)).flatMap(([code, value]) => {
          const parsed = numberValue(value)
          return parsed == null ? [] : [[code, parsed]]
        })),
      })).filter((point) => point.date),
    }]
  })) as AlignedComparison['windows']

  return {
    status: textValue(payload.status) || 'insufficient',
    methodology: textValue(payload.methodology),
    riskFreeRate: numberValue(payload.risk_free_rate) || 0,
    simulationUsed: Boolean(payload.simulation_used),
    windows,
  }
}

async function loadHoldingSimilarity(codes: string[]): Promise<HoldingSimilaritySnapshot | null> {
  if (codes.length < 2) return null
  const response = await fetch(`${backendApiBaseUrl}/api/funds/holding-similarity`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ windCodes: codes }),
    cache: 'no-store',
  })
  if (!response.ok) return null
  const payload = asRecord(await response.json().catch(() => ({})))
  return {
    status: textValue(payload.status) || 'insufficient',
    methodology: textValue(payload.methodology),
    scope: textValue(payload.scope),
    source: textValue(payload.source),
    simulationUsed: Boolean(payload.simulation_used),
    pairCount: numberValue(payload.pair_count) || 0,
    availablePairCount: numberValue(payload.available_pair_count) || 0,
    missingCodes: Array.isArray(payload.missing_codes) ? payload.missing_codes.map(textValue).filter(Boolean) : [],
    pairs: (Array.isArray(payload.pairs) ? payload.pairs : []).map((value) => {
      const pair = asRecord(value)
      return {
        status: textValue(pair.status) || 'insufficient',
        fundA: textValue(pair.fund_a),
        fundB: textValue(pair.fund_b),
        quarter: textValue(pair.quarter),
        reportDateA: textValue(pair.report_date_a),
        reportDateB: textValue(pair.report_date_b),
        weightBasisA: textValue(pair.weight_basis_a),
        weightBasisB: textValue(pair.weight_basis_b),
        holdingCountA: numberValue(pair.holding_count_a) || 0,
        holdingCountB: numberValue(pair.holding_count_b) || 0,
        commonHoldingCount: numberValue(pair.common_holding_count) || 0,
        unionHoldingCount: numberValue(pair.union_holding_count) || 0,
        overlapRatio: numberValue(pair.overlap_ratio),
        jaccardScore: numberValue(pair.jaccard_score),
        cosineSimilarity: numberValue(pair.cosine_similarity),
        similarityLevel: textValue(pair.similarity_level) || 'unknown',
        commonHoldings: (Array.isArray(pair.common_holdings) ? pair.common_holdings : []).map((holdingValue) => {
          const holding = asRecord(holdingValue)
          return {
            stockCode: textValue(holding.stock_code),
            stockName: textValue(holding.stock_name),
            weightA: numberValue(holding.weight_a),
            weightB: numberValue(holding.weight_b),
            overlapContribution: numberValue(holding.overlap_contribution),
          }
        }),
        missingItems: Array.isArray(pair.missing_items) ? pair.missing_items.map(textValue).filter(Boolean) : [],
      }
    }),
  }
}

export default async function ComparePage({ searchParams }: { searchParams: Promise<{ codes?: string | string[] }> }) {
  const codes = parseCodes((await searchParams).codes)
  const [loaded, alignedComparison, holdingSimilarity] = await Promise.all([
    Promise.all(codes.map(loadComparisonFund)),
    loadAlignedComparison(codes),
    loadHoldingSimilarity(codes),
  ])
  const funds = loaded.filter((item): item is ComparisonFund => Boolean(item))
  return <SimpleComparisonClient funds={funds} alignedComparison={alignedComparison} holdingSimilarity={holdingSimilarity} />
}
