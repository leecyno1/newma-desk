export const backendApiBaseUrl =
  process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://127.0.0.1:8005'

type BackendRecord = Record<string, unknown>

export type CamelFund = {
  id: string
  windCode: string
  name: string
  type: string
  nav: number | null
  navDate: string | null
  totalAsset: number | null
  establishmentDate: string | null
  company: string
  contractBenchmark: string
  custodian: string
  investType: string
  contractType: string
  managementFee: number | null
  custodianFee: number | null
  performanceData: Record<string, unknown>
    riskMetrics: Record<string, unknown>
    evidenceCoverageScore?: number | null
    managerIds: string[]
  scores: Array<Record<string, unknown>>
  aiReports: Array<Record<string, unknown>>
  [key: string]: unknown
}

function asRecord(value: unknown): BackendRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as BackendRecord : null
}

function asText(value: unknown, fallback = '') {
  if (value == null) return fallback
  return typeof value === 'string' ? value : String(value)
}

function asNumberOrNull(value: unknown) {
  if (value == null || value === '') return null
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

function asStringArray(value: unknown) {
  return Array.isArray(value) ? value.map((item) => asText(item)).filter(Boolean) : []
}

function asRecordArray(value: unknown) {
  return Array.isArray(value) ? value.map((item) => asRecord(item)).filter((item): item is BackendRecord => Boolean(item)) : []
}

export function toCamelFund(fund: BackendRecord): CamelFund {
  const windCode = asText(fund.wind_code ?? fund.windCode)
  const researchProfile = asRecord(fund.research_profile ?? fund.researchProfile)
  const styleProfile = asRecord(fund.style_profile ?? fund.styleProfile)
  const bondHoldingStyle = asRecord(styleProfile?.bond_holding_style ?? styleProfile?.bondHoldingStyle)
  const fofHoldingStyle = asRecord(styleProfile?.fof_holding_style ?? styleProfile?.fofHoldingStyle)
  const fundEvaluation = asRecord(fund.fund_evaluation ?? fund.fundEvaluation)
  const recommendationEvidence = asRecord(fund.recommendation_evidence ?? fund.recommendationEvidence)
  const recommendationManagerTenure = asRecord(
    recommendationEvidence?.manager_tenure ?? recommendationEvidence?.managerTenure,
  )
  const recommendationMultiPeriod = asRecord(
    recommendationEvidence?.multi_period ?? recommendationEvidence?.multiPeriod,
  )
  const trust = asRecord(fund.trust)

  return {
    id: asText(fund.id ?? windCode),
    windCode,
    name: asText(fund.name),
    type: asText(fund.type),
    managerIds: asStringArray(fund.manager_ids ?? fund.managerIds),
    managers: (Array.isArray(fund.managers) ? fund.managers : []).map((manager) => {
      const managerRecord = asRecord(manager) || {}
      return ({
        managerId: asText(managerRecord.manager_id ?? managerRecord.managerId ?? managerRecord.wind_code ?? managerRecord.windCode),
        windCode: asText(managerRecord.wind_code ?? managerRecord.windCode ?? managerRecord.manager_id ?? managerRecord.managerId),
        name: asText(managerRecord.name),
        company: asText(managerRecord.company),
        education: asText(managerRecord.education),
        workYears: asNumberOrNull(managerRecord.work_years ?? managerRecord.workYears),
        managementYears: asNumberOrNull(managerRecord.management_years ?? managerRecord.managementYears),
        currentFunds: asStringArray(managerRecord.current_funds ?? managerRecord.currentFunds),
        beginDate: managerRecord.begin_date == null && managerRecord.beginDate == null ? null : asText(managerRecord.begin_date ?? managerRecord.beginDate),
        endDate: managerRecord.end_date == null && managerRecord.endDate == null ? null : asText(managerRecord.end_date ?? managerRecord.endDate),
        source: asText(managerRecord.source, 'tushare.fund_manager'),
      })
    }),
    nav: asNumberOrNull(fund.nav),
    navDate: fund.nav_date == null && fund.navDate == null ? null : asText(fund.nav_date ?? fund.navDate),
    totalAsset: asNumberOrNull(fund.total_asset ?? fund.totalAsset),
    establishmentDate: fund.establishment_date == null && fund.establishmentDate == null ? null : asText(fund.establishment_date ?? fund.establishmentDate),
    company: asText(fund.company),
    contractBenchmark: asText(fund.contract_benchmark ?? fund.contractBenchmark ?? fund.benchmark),
    custodian: asText(fund.custodian),
    investType: asText(fund.invest_type ?? fund.investType),
    contractType: asText(fund.contract_type ?? fund.contractType),
    managementFee: asNumberOrNull(fund.management_fee ?? fund.managementFee),
    custodianFee: asNumberOrNull(fund.custodian_fee ?? fund.custodianFee),
    operationStatus: fund.operation_status ?? fund.operationStatus ?? null,
    salesStatus: fund.sales_status ?? fund.salesStatus ?? null,
    feeInfo: fund.fee_info ?? fund.feeInfo ?? null,
    salesRule: fund.sales_rule ?? fund.salesRule ?? null,
    benchmark: fund.benchmark ?? null,
    peerPercentiles: fund.peer_percentiles ?? fund.peerPercentiles ?? null,
    peerReturnMetrics: fund.peer_return_metrics ?? fund.peerReturnMetrics ?? {},
    performanceData: asRecord(fund.performance_data ?? fund.performance ?? fund.performanceData) || {},
    riskMetrics: asRecord(fund.risk_metrics ?? fund.riskMetrics) || {},
    screeningScore: fund.screening_score ?? fund.screeningScore ?? null,
    evidenceCoverageScore: asNumberOrNull(fund.evidence_coverage_score ?? fund.evidenceCoverageScore),
    marketResearchChecklist: fund.market_research_checklist ?? fund.marketResearchChecklist ?? null,
    holdingCount: asNumberOrNull(fund.holding_count ?? fund.holdingCount),
    updatedAt: fund.updated_at ?? fund.updatedAt ?? null,
    researchProfile: researchProfile
      ? {
          primaryBenchmark: researchProfile.primary_benchmark ?? researchProfile.primaryBenchmark ?? '',
          secondaryBenchmark: researchProfile.secondary_benchmark ?? researchProfile.secondaryBenchmark ?? null,
          peerGroup: researchProfile.peer_group ?? researchProfile.peerGroup ?? '',
          peerGroupId: researchProfile.peer_group_id ?? researchProfile.peerGroupId ?? '',
          peerGroupKey: researchProfile.peer_group_key ?? researchProfile.peerGroupKey ?? '',
          styleLabel: researchProfile.style_label ?? researchProfile.styleLabel ?? '',
          strategyTags: researchProfile.strategy_tags ?? researchProfile.strategyTags ?? [],
          managerTenureStart: researchProfile.manager_tenure_start ?? researchProfile.managerTenureStart ?? null,
          capacityNotes: researchProfile.capacity_notes ?? researchProfile.capacityNotes ?? null,
          dataQualityNotes: researchProfile.data_quality_notes ?? researchProfile.dataQualityNotes ?? null,
          classificationConfidence: researchProfile.classification_confidence ?? researchProfile.classificationConfidence ?? null,
          classificationSource: researchProfile.classification_source ?? researchProfile.classificationSource ?? null,
          filterStyleTags: asStringArray(researchProfile.filter_style_tags ?? researchProfile.filterStyleTags),
          styleTagEvidence: asRecordArray(researchProfile.style_tag_evidence ?? researchProfile.styleTagEvidence).map((item) => ({
            value: asText(item.value),
            sourceKey: asText(item.source_key ?? item.sourceKey),
            sourceLabel: asText(item.source_label ?? item.sourceLabel),
            evidenceLevel: asText(item.evidence_level ?? item.evidenceLevel),
            asOf: item.as_of == null && item.asOf == null ? null : asText(item.as_of ?? item.asOf),
            source: asText(item.source),
          })),
          evidence: researchProfile.evidence ?? null,
          memoStyleSuggestions: asRecordArray(
            researchProfile.memo_style_suggestions ?? researchProfile.memoStyleSuggestions,
          ).map((suggestion) => ({
            value: asText(suggestion.value),
            confidence: asNumberOrNull(suggestion.confidence),
            status: asText(suggestion.status, 'llm_suggested'),
            reportCount: asNumberOrNull(suggestion.report_count ?? suggestion.reportCount),
            reportTitles: asStringArray(suggestion.report_titles ?? suggestion.reportTitles),
          })),
          derivedStyleEvidence: asRecordArray(
            researchProfile.derived_style_evidence ?? researchProfile.derivedStyleEvidence,
          ).map((item) => ({
            value: asText(item.value),
            status: asText(item.status, 'derived'),
            source: asText(item.source),
            basis: asText(item.basis),
            confidence: asNumberOrNull(item.confidence),
            evidenceScope: asText(item.evidence_scope ?? item.evidenceScope),
            caveat: asText(item.caveat),
          })),
          holdingStyleEvidence: asRecordArray(
            researchProfile.holding_style_evidence ?? researchProfile.holdingStyleEvidence,
          ),
        }
      : null,
    styleProfile: styleProfile
      ? {
          primaryLabel: styleProfile.primary_label ?? styleProfile.primaryLabel ?? null,
          status: styleProfile.status ?? 'unavailable',
          primaryEvidence: styleProfile.primary_evidence ?? styleProfile.primaryEvidence ?? null,
          labelEvidence: asRecordArray(styleProfile.label_evidence ?? styleProfile.labelEvidence),
          styleLabel: styleProfile.style_label ?? styleProfile.styleLabel ?? null,
          strategyTags: asStringArray(styleProfile.strategy_tags ?? styleProfile.strategyTags),
          quantitativeLabels: asStringArray(styleProfile.quantitative_labels ?? styleProfile.quantitativeLabels),
          bondHoldingStyle: bondHoldingStyle
            ? {
                ...bondHoldingStyle,
                periodCount: asNumberOrNull(bondHoldingStyle.period_count ?? bondHoldingStyle.periodCount),
                requiredPeriods: asNumberOrNull(bondHoldingStyle.required_periods ?? bondHoldingStyle.requiredPeriods),
                secondaryLabels: asStringArray(bondHoldingStyle.secondary_labels ?? bondHoldingStyle.secondaryLabels),
                formalClassificationReady: Boolean(
                  bondHoldingStyle.formal_classification_ready ?? bondHoldingStyle.formalClassificationReady,
                ),
              }
            : null,
          fofHoldingStyle: fofHoldingStyle
            ? {
                ...fofHoldingStyle,
                reportDate: fofHoldingStyle.report_date ?? fofHoldingStyle.reportDate ?? null,
                disclosedFundCount: asNumberOrNull(
                  fofHoldingStyle.disclosed_fund_count ?? fofHoldingStyle.disclosedFundCount,
                ),
                disclosedNavRatio: asNumberOrNull(
                  fofHoldingStyle.disclosed_nav_ratio ?? fofHoldingStyle.disclosedNavRatio,
                ),
                top5NavRatio: asNumberOrNull(fofHoldingStyle.top5_nav_ratio ?? fofHoldingStyle.top5NavRatio),
                concentrationLabel: fofHoldingStyle.concentration_label ?? fofHoldingStyle.concentrationLabel ?? null,
                classificationCoverage: asNumberOrNull(
                  fofHoldingStyle.classification_coverage ?? fofHoldingStyle.classificationCoverage,
                ),
                dominantClassification:
                  fofHoldingStyle.dominant_classification ?? fofHoldingStyle.dominantClassification ?? null,
                classificationDistribution:
                  fofHoldingStyle.classification_distribution ?? fofHoldingStyle.classificationDistribution ?? [],
              }
            : null,
          suggestedLabels: asRecordArray(styleProfile.suggested_labels ?? styleProfile.suggestedLabels),
          derivedLabels: asRecordArray(styleProfile.derived_labels ?? styleProfile.derivedLabels),
          holdingStyle: styleProfile.holding_style ?? styleProfile.holdingStyle ?? null,
          source: styleProfile.source ?? null,
        }
      : null,
    fundEvaluation: fundEvaluation || null,
    researchEvidence: fund.research_evidence ?? fund.researchEvidence ?? null,
    rollingMetrics: fund.rolling_metrics ?? fund.rollingMetrics ?? {},
    dataQuality: fund.data_quality ?? fund.dataQuality ?? null,
    professionalScoring: fund.professional_scoring ?? fund.professionalScoring ?? null,
    classificationReady: Boolean(fund.classification_ready ?? fund.classificationReady),
    evaluationReady: Boolean(fund.evaluation_ready ?? fund.evaluationReady),
    selectionExplanation: fund.selection_explanation ?? fund.selectionExplanation ?? null,
    recommendationEvidence: recommendationEvidence
      ? {
          reasons: asStringArray(recommendationEvidence.reasons),
          risks: asStringArray(recommendationEvidence.risks),
          dataAsOf: recommendationEvidence.data_as_of ?? recommendationEvidence.dataAsOf ?? null,
          methodologyVersion: recommendationEvidence.methodology_version ?? recommendationEvidence.methodologyVersion ?? '',
          scoreScope: recommendationEvidence.score_scope ?? recommendationEvidence.scoreScope ?? '',
          multiPeriod: Object.keys(recommendationMultiPeriod || {}).length
            ? {
                status: asText(recommendationMultiPeriod?.status, 'short_term_only'),
                return6m: asNumberOrNull(recommendationMultiPeriod?.return_6m ?? recommendationMultiPeriod?.return6m),
                return1y: asNumberOrNull(recommendationMultiPeriod?.return_1y ?? recommendationMultiPeriod?.return1y),
                annualizedReturn1y: asNumberOrNull(recommendationMultiPeriod?.annualized_return_1y ?? recommendationMultiPeriod?.annualizedReturn1y),
                annualizedReturn3y: asNumberOrNull(recommendationMultiPeriod?.annualized_return_3y ?? recommendationMultiPeriod?.annualizedReturn3y),
                maxDrawdown1y: asNumberOrNull(recommendationMultiPeriod?.max_drawdown_1y ?? recommendationMultiPeriod?.maxDrawdown1y),
                maxDrawdown3y: asNumberOrNull(recommendationMultiPeriod?.max_drawdown_3y ?? recommendationMultiPeriod?.maxDrawdown3y),
                sharpeRatio3y: asNumberOrNull(recommendationMultiPeriod?.sharpe_ratio_3y ?? recommendationMultiPeriod?.sharpeRatio3y),
                annualizedReturnGap: asNumberOrNull(recommendationMultiPeriod?.annualized_return_gap ?? recommendationMultiPeriod?.annualizedReturnGap),
                consistencyStatus: asText(recommendationMultiPeriod?.consistency_status ?? recommendationMultiPeriod?.consistencyStatus),
                consistencyLabel: asText(recommendationMultiPeriod?.consistency_label ?? recommendationMultiPeriod?.consistencyLabel),
                usedInScore: Boolean(recommendationMultiPeriod?.used_in_score ?? recommendationMultiPeriod?.usedInScore),
                dataAsOf: recommendationMultiPeriod?.data_as_of ?? recommendationMultiPeriod?.dataAsOf ?? null,
              }
            : null,
          managerTenure: recommendationManagerTenure
            ? {
                status: asText(recommendationManagerTenure.status, 'unavailable'),
                coverageStatus: asText(recommendationManagerTenure.coverage_status ?? recommendationManagerTenure.coverageStatus),
                coverageRatio: asNumberOrNull(recommendationManagerTenure.coverage_ratio ?? recommendationManagerTenure.coverageRatio),
                requestedStartDate: asText(recommendationManagerTenure.requested_start_date ?? recommendationManagerTenure.requestedStartDate),
                actualStartDate: asText(recommendationManagerTenure.actual_start_date ?? recommendationManagerTenure.actualStartDate),
                totalReturn: asNumberOrNull(recommendationManagerTenure.total_return ?? recommendationManagerTenure.totalReturn),
                applicable: Boolean(recommendationManagerTenure.applicable),
                includedInScore: Boolean(recommendationManagerTenure.included_in_score ?? recommendationManagerTenure.includedInScore),
                note: asText(recommendationManagerTenure.note),
              }
            : null,
          alternatives: asRecordArray(recommendationEvidence.alternatives).map((alternative) => ({
            windCode: asText(alternative.wind_code ?? alternative.windCode),
            name: asText(alternative.name),
            styleLabel: asText(alternative.style_label ?? alternative.styleLabel),
            overallScore: asNumberOrNull(alternative.overall_score ?? alternative.overallScore),
            reason: asText(alternative.reason),
          })),
        }
      : null,
    scores: asRecordArray(fund.scores),
    aiReports: asRecordArray(fund.ai_reports ?? fund.aiReports),
    trust: trust
      ? {
          dataAsOf: trust.data_as_of ?? trust.dataAsOf ?? null,
          syncedAt: trust.synced_at ?? trust.syncedAt ?? null,
          scoreAsOf: trust.score_as_of ?? trust.scoreAsOf ?? null,
          scoreCount: trust.score_count ?? trust.scoreCount ?? 0,
          reportCount: trust.report_count ?? trust.reportCount ?? 0,
          dataQualityStatus: trust.data_quality_status ?? trust.dataQualityStatus ?? 'unknown',
          dataQualityScore: trust.data_quality_score ?? trust.dataQualityScore ?? 0,
          dataQualityIssues: trust.data_quality_issues ?? trust.dataQualityIssues ?? [],
        }
      : undefined,
  }
}

export function toSnakePool(pool: Record<string, unknown>) {
  return {
    ...pool,
    is_default: pool.is_default ?? pool.isDefault,
    created_at: pool.created_at ?? pool.createdAt,
    updated_at: pool.updated_at ?? pool.updatedAt,
  }
}

export function toSnakePoolMember(member: Record<string, unknown>) {
  return {
    ...member,
    pool_id: member.pool_id ?? member.poolId,
    fund_id: member.fund_id ?? member.fundId,
    latest_conclusion: member.latest_conclusion ?? member.latestConclusion,
    next_review_date: member.next_review_date ?? member.nextReviewDate,
    risk_notes: member.risk_notes ?? member.riskNotes,
    created_at: member.created_at ?? member.createdAt,
    updated_at: member.updated_at ?? member.updatedAt,
  }
}
