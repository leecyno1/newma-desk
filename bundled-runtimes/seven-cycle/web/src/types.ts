export type PublicationStatus = 'formal' | 'limited' | 'blocked' | 'scenario_only' | 'calendar_only'

export interface TrackForecast {
  status: PublicationStatus | 'unavailable'
  statusReason?: string
  method: string
  caveat: string
  vintageDate?: string
  inputAsOf?: string
  inputLagMonths?: number
  dates: string[]
  median: Array<number | null>
  low: Array<number | null>
  high: Array<number | null>
  bridge?: { date: string; value: number }
  validation?: {
    qualifiedHorizons: number
    requiredHorizons: number
    metrics: Array<{
      horizonMonths: number
      testOrigins: number
      mae: number
      baselineMae: number
      directionAccuracy: number
      baselineDirectionAccuracy: number
      qualified: boolean
    }>
  }
  judgment?: {
    currentSlope3: number | null
    direction3: string | null
    turningPoint: string | null
  }
}

export interface CycleContributionComponent {
  pointContribution: number
  absoluteShare: number
  signedShare: number
  slope3: number | null
  varianceShare120: number | null
  coefficient: number
  filterRobustness?: {
    status: 'stable' | 'weak'
    primaryFilter: string
    comparisonFilter: string
    directionAgreement: boolean
    preprocessingDirectionAgreement?: boolean
    pathCorrelation: number | null
    relativePointDifference: number | null
    absoluteShareDifference: number | null
    varianceShareDifference: number | null
    comparisonPointContribution?: number | null
    comparisonAbsoluteShare?: number | null
    comparisonVarianceShare120?: number | null
  }
}

export interface RealtimeContributionComponent {
  status: 'limited_confirmed' | 'weak'
  pointContribution: number
  direction: 'positive' | 'negative'
  stateWeightModel?: 'track_only' | 'peer_shared' | 'dynamic_factor' | 'nearest_factor' | 'causal_orthogonal'
  uncertainty: number
  stateUncertainty?: number
  coefficientUncertainty?: number
  coefficientUncertaintyShare?: number
  stateSpecificationCount?: number
  stateSpecificationDirectionAgreement?: number | null
  rollingStateSpecificationDirectionAgreement?: number | null
  stateSpecificationUncertainty?: number
  stateSpecificationUncertaintyShare?: number
  stateSpecificationWeights?: Record<string, number>
  stateSpecificationEffectiveCount?: number
  stateSpecificationWeightEntropy?: number
  peerPoolingUncertainty?: number
  peerPoolingUncertaintyShare?: number
  standalonePointContribution?: number
  peerSharedPointContribution?: number
  peerSharedEligible?: boolean
  peerSharedFamilyLevel?: 'category' | 'group' | 'global' | null
  peerSharedFamilyKey?: string | null
  peerSharedPeerCount?: number
  peerSharedEvidenceWeight?: number
  standaloneStateSpecificationWeights?: Record<string, number>
  peerSharedStateSpecificationWeights?: Record<string, number>
  dynamicFactorAdopted?: boolean
  dynamicFactorPointContribution?: number
  dynamicFactorEvidenceWeight?: number
  dynamicFactorUncertainty?: number
  dynamicFactorUncertaintyShare?: number
  dynamicFactorStateSpecificationWeights?: Record<string, number>
  nearestFactorAdopted?: boolean
  nearestFactorPointContribution?: number
  nearestFactorEvidenceWeight?: number
  nearestFactorPeerCount?: number
  nearestFactorUncertainty?: number
  nearestFactorUncertaintyShare?: number
  nearestFactorSpecificationPoints?: Record<string, number>
  nearestFactorSpecificationDirectionAgreement?: number | null
  nearestFactorSpecificationUncertainty?: number
  nearestFactorSpecificationUncertaintyShare?: number
  nearestFactorStateSpecificationWeights?: Record<string, number>
  causalOrthogonalAdopted?: boolean
  orthogonalizationOrder?: 'long_to_short'
  orthogonalizationPrimarySpan?: number
  orthogonalizationComparisonSpan?: number
  basePointContribution?: number
  orthogonalPointContribution?: number
  orthogonalComparisonPointContribution?: number
  orthogonalizationUncertainty?: number
  orthogonalizationUncertaintyShare?: number
  orthogonalizationSpanUncertainty?: number
  orthogonalizationSpanUncertaintyShare?: number
  orthogonalSpanEndpointDirectionAgreement?: boolean
  orthogonalSpanRollingDirectionAgreement?: number | null
  orthogonalSpanRollingCorrelation?: number | null
  signalToUncertainty: number
  latestCoefficient?: number
  rollingCoefficientMedian?: number | null
  rollingCoefficientDeviation?: number | null
  coefficientSignAgreement?: number | null
  rollingDirectionAgreement: number | null
  rollingContributionCorrelation: number | null
  medianAbsoluteRevision: number | null
  retrospectivePointContribution: number
  endpointDirectionAgreement: boolean
}

export interface RealtimeContributionConfirmation {
  status: 'causal_realtime_confirmation' | 'unavailable'
  method?: string
  reason?: string
  eligibleCycles?: string[]
  summary?: {
    confirmedCycles: number
    comparableCycles: number
  }
  training?: {
    originCount: number
    originStart: string
    originEnd: string
    minimumTrainObservations: number
    latestTrainStart: string
    latestTrainEnd: string
    latestTrainObservations: number
    selectedAlpha: number
    latestTrainSelectionR2: number | null
    selectedStateWeightModel?: 'track_only' | 'peer_shared' | 'dynamic_factor' | 'nearest_factor' | 'causal_orthogonal'
    orthogonalBaseStateWeightModel?: 'track_only' | 'peer_shared' | 'dynamic_factor' | 'nearest_factor'
    rollingReconstructionR2: number | null
    equalMedianRollingReconstructionR2?: number | null
    rollingR2ImprovementVsEqualMedian?: number | null
    rollingTargetVariance?: number | null
    rollingReferenceTargetVariance?: number | null
    rollingTargetVarianceRatio?: number | null
    lowTargetVarianceWarning?: boolean
    standaloneRollingReconstructionR2?: number | null
    standaloneRollingMae?: number | null
    standalonePredictionDirectionAgreement?: number | null
    peerSharedRollingReconstructionR2?: number | null
    peerSharedRollingMae?: number | null
    peerSharedPredictionDirectionAgreement?: number | null
    peerSharedRollingR2Improvement?: number | null
    peerSharedMaeImprovement?: number | null
    peerSharedDirectionImprovement?: number | null
    peerSharedStatus?: 'adopted' | 'rejected' | 'unavailable'
    peerSharedAdoptionReasons?: string[]
    peerSharedEligibleCycles?: string[]
    dynamicFactorRollingReconstructionR2?: number | null
    dynamicFactorRollingMae?: number | null
    dynamicFactorPredictionDirectionAgreement?: number | null
    dynamicFactorRollingR2Improvement?: number | null
    dynamicFactorMaeImprovement?: number | null
    dynamicFactorDirectionImprovement?: number | null
    dynamicFactorStatus?: 'adopted' | 'rejected' | 'unavailable'
    dynamicFactorAdoptionReasons?: string[]
    dynamicFactorEligibleCycles?: string[]
    nearestFactorRollingReconstructionR2?: number | null
    nearestFactorRollingMae?: number | null
    nearestFactorPredictionDirectionAgreement?: number | null
    nearestFactorRollingR2Improvement?: number | null
    nearestFactorMaeImprovement?: number | null
    nearestFactorDirectionImprovement?: number | null
    nearestFactorStatus?: 'adopted' | 'rejected' | 'unavailable'
    nearestFactorAdoptionReasons?: string[]
    nearestFactorEligibleCycles?: string[]
    nearestFactorSpecificationStable?: boolean
    nearestFactorRobustlyAdopted?: boolean
    nearestFactorSpecificationAdoptedCount?: number
    nearestFactorSpecificationCount?: number
    nearestFactorSpecifications?: Record<string, {
      maximumPeers: number
      minimumAbsoluteCorrelation: number
      spanMultiplier: number
      rollingReconstructionR2: number | null
      rollingMae: number | null
      predictionDirectionAgreement: number | null
      r2Improvement: number | null
      maeImprovement: number | null
      directionImprovement: number | null
      status: 'adopted' | 'rejected'
      adoptionReasons: string[]
    }>
    nearestFactorVintageSplits?: Record<'early' | 'late', {
      originCount: number
      originStart: string | null
      originEnd: string | null
      r2Improvement: number | null
      maeImprovement: number | null
      directionImprovement: number | null
      targetVariance: number | null
      referenceTargetVariance: number | null
      targetVarianceRatio: number | null
      lowTargetVarianceWarning: boolean
    }>
    causalOrthogonalStatus?: 'adopted' | 'rejected'
    causalOrthogonalAdoptionReasons?: string[]
    orthogonalPrimaryRollingReconstructionR2?: number | null
    orthogonalPrimaryRollingMae?: number | null
    orthogonalPrimaryPredictionDirectionAgreement?: number | null
    orthogonalPrimaryRollingR2Improvement?: number | null
    orthogonalPrimaryMaeImprovement?: number | null
    orthogonalPrimaryDirectionImprovement?: number | null
    orthogonalComparisonRollingReconstructionR2?: number | null
    orthogonalComparisonRollingMae?: number | null
    orthogonalComparisonPredictionDirectionAgreement?: number | null
    orthogonalComparisonRollingR2Improvement?: number | null
    orthogonalComparisonMaeImprovement?: number | null
    orthogonalComparisonDirectionImprovement?: number | null
    baseComponentCollinearity?: {
      medianAbsoluteCorrelation: number | null
      maximumAbsoluteCorrelation: number | null
      conditionNumber: number | null
    }
    orthogonalPrimaryComponentCollinearity?: {
      medianAbsoluteCorrelation: number | null
      maximumAbsoluteCorrelation: number | null
      conditionNumber: number | null
    }
    orthogonalComparisonComponentCollinearity?: {
      medianAbsoluteCorrelation: number | null
      maximumAbsoluteCorrelation: number | null
      conditionNumber: number | null
    }
  }
  current?: {
    date: string
    indicatorValue: number
    baseline: number
    cycleTotal: number
    residual: number
    conservationError: number
    components: Record<string, RealtimeContributionComponent>
  }
  caveat?: string
}

export interface TrackCycleContribution {
  status: 'retrospective_diagnostic' | 'unavailable'
  quality?: 'stable' | 'weak'
  method: string
  eligibleCycles: string[]
  excludedCycles: Array<{
    cycleId: string
    reason: string
    observations?: number
    requiredObservations?: number
  }>
  current?: {
    date: string
    indicatorValue: number
    baseline: number
    cycleTotal: number
    residual: number
    conservationError: number
    dominantCycle: string
    components: Record<string, CycleContributionComponent>
  }
  diagnostics?: {
    fitStart: string
    fitEnd: string
    fitObservations: number
    edgeTrimMonths: number
    selectedAlpha: number
    reconstructionR2: number | null
    holdoutReconstructionR2: number | null
    coefficientSignAgreement: number | null
    residualVarianceShare120: number | null
  }
  filterRobustness?: {
    status: 'stable' | 'weak' | 'unavailable'
    primaryFilter: string
    comparisonFilter: string
    primaryModelQuality?: 'stable' | 'weak'
    comparisonModelQuality?: 'stable' | 'weak'
    stableCycles: number
    comparableCycles: number
    directionAgreementCycles?: number
    medianPathCorrelation?: number | null
    reason?: string
  }
  realtimeConfirmation?: RealtimeContributionConfirmation
  paths?: {
    baseline: number
    cycleTotal: Array<number | null>
    residual: Array<number | null>
    components: Record<string, Array<number | null>>
  }
  caveat: string
}

export interface IndicatorContributionRow {
  trackId: string
  label: string
  category: string
  group: 'market' | 'economic'
  date: string
  pointContribution: number
  absoluteShare: number
  signedShare: number
  slope3: number | null
  varianceShare120: number | null
  quality: 'stable' | 'weak'
  reconstructionR2: number | null
  holdoutReconstructionR2: number | null
  residualVarianceShare120: number | null
  filterDirectionAgreement?: boolean | null
  filterPathCorrelation?: number | null
  filterRelativePointDifference?: number | null
  filterAbsoluteShareDifference?: number | null
  filterVarianceShareDifference?: number | null
  modelQualityPass?: boolean
  realtimeStatus?: 'limited_confirmed' | 'weak' | null
  realtimeStateWeightModel?: 'track_only' | 'peer_shared' | 'dynamic_factor' | 'nearest_factor' | 'causal_orthogonal' | null
  realtimePeerSharedFamilyLevel?: 'category' | 'group' | 'global' | null
  realtimePeerSharedPeerCount?: number | null
  realtimePointContribution?: number | null
  realtimeDirection?: 'positive' | 'negative' | null
  realtimeSignalToUncertainty?: number | null
  realtimeCoefficientSignAgreement?: number | null
  realtimeCoefficientUncertaintyShare?: number | null
  realtimeStateSpecificationDirectionAgreement?: number | null
  realtimeRollingStateSpecificationDirectionAgreement?: number | null
  realtimeStateSpecificationUncertaintyShare?: number | null
  realtimeStateSpecificationWeights?: Record<string, number> | null
  realtimeStateSpecificationEffectiveCount?: number | null
  realtimeStateSpecificationWeightEntropy?: number | null
  realtimeRollingDirectionAgreement?: number | null
  realtimeRollingContributionCorrelation?: number | null
  realtimeMedianAbsoluteRevision?: number | null
  realtimeRollingReconstructionR2?: number | null
  realtimeEqualMedianRollingReconstructionR2?: number | null
  realtimeRollingR2ImprovementVsEqualMedian?: number | null
  realtimePeerSharedStatus?: 'adopted' | 'rejected' | 'unavailable' | null
  realtimePeerSharedRollingR2Improvement?: number | null
  realtimePeerSharedMaeImprovement?: number | null
  realtimePeerSharedDirectionImprovement?: number | null
  realtimeCausalOrthogonalStatus?: 'adopted' | 'rejected' | null
  realtimeOrthogonalPrimaryR2Improvement?: number | null
  realtimeOrthogonalComparisonR2Improvement?: number | null
  realtimeBaseMaximumCorrelation?: number | null
  realtimeOrthogonalMaximumCorrelation?: number | null
  realtimeBaseConditionNumber?: number | null
  realtimeOrthogonalConditionNumber?: number | null
  realtimeOrthogonalizationUncertaintyShare?: number | null
  realtimeOrthogonalizationSpanUncertaintyShare?: number | null
  realtimeEndpointDirectionAgreement?: boolean | null
}

export interface IndicatorContributionCycleStudy {
  status: 'retrospective_diagnostic' | 'excluded' | 'unavailable'
  eligibleTracks: number
  stableTracks?: number
  modelStableTracks?: number
  pathStableTracks?: number
  pointAmplitudeStableTracks?: number
  absoluteShareStableTracks?: number
  varianceShareStableTracks?: number
  realtimeEligibleTracks?: number
  realtimeConfirmedTracks?: number
  realtimePositiveTracks?: number
  realtimeNegativeTracks?: number
  medianRealtimeSignalToUncertainty?: number | null
  medianRealtimeCoefficientSignAgreement?: number | null
  medianRealtimeCoefficientUncertaintyShare?: number | null
  medianRealtimeStateSpecificationDirectionAgreement?: number | null
  medianRealtimeRollingStateSpecificationDirectionAgreement?: number | null
  medianRealtimeStateSpecificationUncertaintyShare?: number | null
  medianRealtimeStateSpecificationWeights?: Record<string, number | null>
  medianRealtimeStateSpecificationEffectiveCount?: number | null
  medianRealtimeStateSpecificationWeightEntropy?: number | null
  medianRealtimeRollingDirectionAgreement?: number | null
  medianRealtimeRollingContributionCorrelation?: number | null
  medianRealtimeAbsoluteRevision?: number | null
  medianRealtimeRollingReconstructionR2?: number | null
  medianRealtimeEqualMedianRollingReconstructionR2?: number | null
  medianRealtimeDynamicWeightR2Improvement?: number | null
  realtimeDynamicWeightImprovedTracks?: number
  realtimePeerSharedEligibleTracks?: number
  realtimePeerSharedAdoptedTracks?: number
  realtimePeerSharedPositiveR2Tracks?: number
  medianRealtimePeerSharedR2Improvement?: number | null
  medianRealtimePeerSharedMaeImprovement?: number | null
  medianRealtimePeerSharedDirectionImprovement?: number | null
  realtimeDynamicFactorEligibleTracks?: number
  realtimeDynamicFactorAdoptedTracks?: number
  realtimeDynamicFactorPositiveR2Tracks?: number
  medianRealtimeDynamicFactorR2Improvement?: number | null
  medianRealtimeDynamicFactorMaeImprovement?: number | null
  medianRealtimeDynamicFactorDirectionImprovement?: number | null
  realtimeNearestFactorEligibleTracks?: number
  realtimeNearestFactorAdoptedTracks?: number
  realtimeNearestFactorPositiveR2Tracks?: number
  medianRealtimeNearestFactorR2Improvement?: number | null
  medianRealtimeNearestFactorMaeImprovement?: number | null
  medianRealtimeNearestFactorDirectionImprovement?: number | null
  realtimeNearestFactorSpecificationStableTracks?: number
  realtimeNearestFactorRobustlyAdoptedTracks?: number
  realtimeNearestFactorPositiveEarlyVintageTracks?: number
  realtimeNearestFactorPositiveLateVintageTracks?: number
  medianRealtimeNearestFactorEarlyVintageR2Improvement?: number | null
  medianRealtimeNearestFactorLateVintageR2Improvement?: number | null
  realtimeLowTargetVarianceWarningTracks?: number
  realtimeCausalOrthogonalAdoptedTracks?: number
  realtimeCausalOrthogonalPositiveR2Tracks?: number
  medianRealtimeOrthogonalPrimaryR2Improvement?: number | null
  medianRealtimeOrthogonalComparisonR2Improvement?: number | null
  medianRealtimeBaseMaximumCorrelation?: number | null
  medianRealtimeOrthogonalMaximumCorrelation?: number | null
  medianRealtimeBaseConditionNumber?: number | null
  medianRealtimeOrthogonalConditionNumber?: number | null
  medianRealtimeOrthogonalizationUncertaintyShare?: number | null
  medianRealtimeOrthogonalizationSpanUncertaintyShare?: number | null
  positiveTracks?: number
  negativeTracks?: number
  medianAbsoluteShare?: number
  medianVarianceShare120?: number
  medianReconstructionR2?: number
  directionAgreementTracks?: number
  medianFilterPathCorrelation?: number | null
  topPositive?: IndicatorContributionRow[]
  topNegative?: IndicatorContributionRow[]
  topInfluence?: IndicatorContributionRow[]
  reason?: string
  caveat?: string
}

export interface CrossFilterGainCycleCalibration {
  status: 'adopted' | 'rejected' | 'unavailable'
  gain?: number | null
  eligibleTracks: number
  validationRelativeImprovement?: number | null
  auditRelativeImprovement?: number | null
  validationImprovedTrackShare?: number | null
  auditImprovedTrackShare?: number | null
  reason?: string | null
}

export interface CrossFilterGainCalibration {
  status: string
  method: string
  cycles: Record<string, CrossFilterGainCycleCalibration>
}

export interface IndicatorContributionStudy {
  status: string
  definition: string
  method: string
  notCausalAttribution: boolean
  notForecastWeight: boolean
  cycles: Record<string, IndicatorContributionCycleStudy>
  crossFilterGainCalibration?: CrossFilterGainCalibration
  longHistory?: {
    status: string
    frequency: 'A'
    asOf: string
    trackCount: number
    method: string
    crossFilterGainCalibration?: CrossFilterGainCalibration
    cycles: Record<string, IndicatorContributionCycleStudy>
  }
}

export interface MarketTrack {
  id: string
  label: string
  category: string
  group: 'market' | 'economic'
  unit: string
  frequency: string
  source: string
  sourceCode: string
  transform: string
  proxyStatus: 'direct' | 'proxy'
  caveat: string | null
  coverage: {
    start: string
    end: string
    observations: number
    rawStart: string | null
    changeObservations: number
  }
  dates: string[]
  raw: Array<number | null>
  change: Array<number | null>
  standardized: Array<number | null>
  governedStack: Array<number | null>
  researchStack: Array<number | null>
  cycleComponents: Record<string, Array<number | null>>
  cycleContribution: TrackCycleContribution
  forecast: TrackForecast
}

export interface MarketSurfaceData {
  meta: {
    generated: string
    asOf: string
    trackCount: number
    groupCounts: Record<string, number>
    defaultTrackIds: string[]
    trackPresets: Array<{
      id: string
      label: string
      description: string
      trackIds: string[]
    }>
    governedCycles: string[]
    researchOnlyCycles: string[]
    excludedFromMonthlyStack: string[]
    forecastStatus: string
    forecastVintage: string
    forecastStaleMonths: number
    forecastTrackCounts: Record<string, number>
    surfaceVintage: string
  }
  indicatorContributionStudy: IndicatorContributionStudy
  tracks: MarketTrack[]
}

export interface CyclePolicy {
  id: string
  name: string
  role: string
  centerPriorMonths: number
  periodMode: string
  empiricalBandMonths: number[] | null
  publication: {
    historical: PublicationStatus
    realtime: PublicationStatus
    forecast: PublicationStatus
    asset_statistics: PublicationStatus
    reason: string
  }
  evidence: {
    evidence_status: string
    center_prior_months: number
    empirical_band_months: number[] | null
    family_centers_months: number[]
    reason_codes: string[]
    summary: string
  }
}

export interface CycleDirectionHorizon {
  label: string
  months: number
  probability: number
  outcome: string
  accuracy: number
  qualified: boolean
}

export interface CycleDirectionPublication {
  status: 'limited' | 'blocked'
  layer: 'direction_probability' | 'state_direction_probability' | 'risk_state_probability'
  badgeLabel: string
  label: string
  asOf: string
  currentLabel: string
  horizons: CycleDirectionHorizon[]
  exactCycleStatus: PublicationStatus
  assetForecastStatus: PublicationStatus
  gate: {
    passed: boolean
    checks: Record<string, boolean>
    reasonCodes: string[]
  }
  caveat: string
}

export type CycleDiagnostic = Record<string, any> & {
  directionPublication?: CycleDirectionPublication
}

export interface CycleResearchData {
  meta: Record<string, unknown>
  governance: { asOf: string; cycles: CyclePolicy[] }
  C1: any
  C4: any
  C4Realtime: any
  C4Forecast: any
  C6: any
  diagnostics: Record<string, CycleDiagnostic>
  indicatorContributionStudy: IndicatorContributionStudy
}

export interface PhaseStats {
  n: number
  ann_return: number
  ann_vol: number
  positive_rate: number
}

export interface AssetRow {
  asset_id: string
  category: string
  name: string
  start: string | null
  end: string | null
  n_months: number
  data_identity: string
  phase_stats: Record<string, PhaseStats> | null
  best_phase: string | null
  worst_phase: string | null
  beta_level: number | null
  beta_slope3: number | null
  impact_bps_per_1sigma: number | null
  in_sample_r2: number | null
  oos_r2: number | null
  confidence: string
  actual_2019: number | null
  c4_assoc_contribution_2019: number | null
}

export interface AssetStatisticsData {
  meta: {
    generated: string
    historicalStatisticsGenerated?: string
    historicalStatisticsAsOf?: string
    forecastGenerated?: string
    forecastAsOf?: string
    forecastAssetDataThrough?: string
    [key: string]: unknown
  }
  summary: Record<string, any>
  assets: AssetRow[]
  phase_labels: Record<string, string>
  publication: Record<string, PublicationStatus>
  researchPhaseLabels?: Record<string, string>
  researchMappings?: Record<string, any>
  stateMappings?: Record<string, any>
  stateDiagnostics?: Record<string, any>
  currentCycleForecast?: AssetCycleStateForecastData
}

export type AssetCycleStateForecastModel = 'state_analog' | 'state_analog_shrunk' | 'state_analog_strong_shrink' | 'state_analog_recency' | 'state_ridge' | 'category_context_ridge' | 'state_model_consensus' | 'nested_model_average'

export interface AssetCycleStateForecastValidation {
  model: AssetCycleStateForecastModel | 'nested_walk_forward'
  observations: number
  directionAccuracy?: number
  baseAccuracy?: number
  brier?: number
  baseBrier?: number
  mae?: number
  baseMae?: number
  oosR2?: number
  passedGateCount: number
  qualified: boolean
  reason: string
  reasonCodes: string[]
  recentValidation?: AssetCycleStateForecastValidation
  recentStable?: boolean
  recentTrace?: Array<{
    date: string
    actualReturn: number
    predictedReturn: number
    baselineReturn: number
    probabilityUp: number
  }>
  nonOverlapStable?: boolean
  nonOverlappingValidation?: {
    spacingMonths: number
    minimumObservationsPerPath: number
    eligiblePaths: number
    stablePaths: number
    requiredStablePaths: number
    medianOosR2?: number
    stable: boolean
    paths: Array<{
      offset: number
      observations: number
      directionAccuracy?: number
      baseAccuracy?: number
      brier?: number
      baseBrier?: number
      mae?: number
      baseMae?: number
      oosR2?: number
      passedGateCount: number
      stable: boolean
    }>
  }
  modelCounts?: Partial<Record<AssetCycleStateForecastModel, number>>
  switches?: number
  recentSelections?: Array<{
    date: string
    model: AssetCycleStateForecastModel
    models?: AssetCycleStateForecastModel[]
  }>
  topModelCount?: number
  uncertainty?: AssetCycleStateForecastUncertainty | null
  recentUncertainty?: AssetCycleStateForecastUncertainty | null
  robustnessStable?: boolean
  robustnessReasonCode?: string
  ensembleSizeRobustness?: {
    primarySize: number
    sizes: Record<string, {
      qualified?: boolean
      recentStable?: boolean
      nonOverlapStable?: boolean
      passedGateCount?: number
      oosR2?: number
    }>
  }
  robustness?: {
    halfLivesMonths: number[]
    results: Record<string, {
      qualified: boolean
      recentStable: boolean
      passedGateCount: number
      oosR2?: number
    }>
  }
  challengerMateriality?: {
    passed: boolean
    gates: Record<string, boolean>
    relativeMaeImprovement: number
    brierImprovement: number
    minimumOosR2: number
    minimumRelativeMaeImprovement: number
    minimumBrierImprovement: number
  }
}

export interface AssetCycleStateForecastUncertainty {
  confidenceLevel: number
  observations: number
  blockMonths: number
  bootstrapSamples: number
  directionAccuracy: {
    low: number
    high: number
  }
  oosR2: {
    low: number
    high: number
  }
  evidenceStrength: 'strong' | 'moderate' | 'weak'
}

export interface AssetCycleStateForecastEstimate {
  analogs: number
  model: AssetCycleStateForecastModel
  localWeight?: number
  halfLifeMonths?: number
  componentCount?: number
  componentModels?: AssetCycleStateForecastModel[]
  ensembleSizeSensitivity?: Record<string, {
    componentModels: AssetCycleStateForecastModel[]
    probabilityUp: number
    medianReturn: number
    low20: number
    high80: number
    conditionalVol: number
    valueAtRisk95: number
    expectedShortfall95: number
  }>
  probabilityUp: number
  downsideProbability: number
  medianReturn: number
  low20: number
  high80: number
  conditionalVol: number
  valueAtRisk95: number
  expectedShortfall95: number
}

export interface AssetCycleStateContributionMetrics {
  probabilityUp: number
  medianReturn: number
  conditionalVol: number
  valueAtRisk95: number
}

export interface AssetCycleStateAttribution {
  method: 'shapley_current_state_neutralization'
  model: AssetCycleStateForecastModel
  horizonMonths: number
  cycles: Array<'C4' | 'C5' | 'C7'>
  baseline: AssetCycleStateContributionMetrics
  full: AssetCycleStateContributionMetrics
  contributions: Record<'C4' | 'C5' | 'C7', AssetCycleStateContributionMetrics>
  ranking: Array<'C4' | 'C5' | 'C7'>
  neutralValues: Record<string, Record<string, number>>
  conservationError: number
  publishedMatchError: number
  notCausal: true
  definition: string
}

export interface AssetCycleStateAttributionStability {
  status: 'stable' | 'mixed' | 'unstable' | 'low_impact'
  observations: number
  spacingMonths: number
  start: string
  end: string
  currentDominantCycle: 'C4' | 'C5' | 'C7'
  dominantPersistence: number
  dominantSignConsistency: number | null
  dominanceStatus: 'persistent' | 'mixed' | 'rotating'
  directionStatus: 'consistent' | 'mixed' | 'reversing'
  materiality: 'high' | 'medium' | 'low'
  absoluteCurrentReturnContribution: number
  normalizedReturnContribution: number
  cycles: Record<'C4' | 'C5' | 'C7', {
    currentReturnContribution: number
    medianReturnContribution: number
    positiveShare: number
    sameSignShare: number | null
    dominantShare: number
  }>
  history: Array<{
    date: string
    dominantCycle: 'C4' | 'C5' | 'C7'
    contributions: Record<'C4' | 'C5' | 'C7', AssetCycleStateContributionMetrics>
  }>
  frozenCurrentSpecification: true
  noFutureTargetLeakage: true
  notForecastAccuracy: true
  definition: string
}

export interface AssetCycleStateForecastModelResult {
  validation: AssetCycleStateForecastValidation
  forecast: AssetCycleStateForecastEstimate | null
}

export interface AssetCycleStateForecastHorizon {
  championModel: AssetCycleStateForecastModel
  selectionPolicy: 'nested_champion' | 'nested_model_average' | 'fixed_model'
  models: Partial<Record<AssetCycleStateForecastModel, AssetCycleStateForecastModelResult>>
  validation: AssetCycleStateForecastValidation
  selectionValidation: AssetCycleStateForecastValidation
  forecast: AssetCycleStateForecastEstimate | null
  cycleAttribution?: AssetCycleStateAttribution | null
  cycleAttributionStability?: AssetCycleStateAttributionStability | null
  fullSampleQualified: boolean
  publicationQualified: boolean
  synchronousReferenceStable?: boolean
  publicationReasonCodes: string[]
  status: PublicationStatus
}

export interface AssetCycleStateForecastRow {
  assetId: string
  majorCategory: '股票' | '债券' | '商品' | '外汇'
  category: string
  name: string
  dataEnd: string | null
  observations: number
  currentDataAvailable: boolean
  freshnessStatus: 'current' | 'source_lag' | 'stale'
  lagMonths: number | null
  qualifiedHorizons: string[]
  status: PublicationStatus
  horizons: Record<string, AssetCycleStateForecastHorizon>
}

export interface AssetCycleStateClock {
  mode: string
  decisionAsOf: string
  cycles: Array<{
    cycleId: string
    observationUsed: string
    sourceDataThrough: string
    availabilityLagMonths: number
    availableForDecisionMonth: string
    identity: string
  }>
}

export interface AssetCycleStateForecastData {
  meta: {
    generated: string
    asOf: string
    assetDataThrough: string
    definition: string
    riskDefinition: string
    stateIdentity: string
    modelVersion: string
    modelPolicies: Record<string, 'nested_champion' | 'nested_model_average' | 'fixed_state_analog_shrunk'>
    forecastClock: string
    stateClock: AssetCycleStateClock
    synchronousReferenceClock: AssetCycleStateClock
    synchronousReference: {
      status: 'cached' | 'refreshed'
      generated: string | null
      asOf: string
      assetDataThrough: string
      path: string
    }
    notPortfolioBacktest: boolean
    layer: 'joint_state_forecast'
    includedCycles: string[]
    separateFromSingleCycleMapping: boolean
  }
  summary: {
    assets: number
    refreshedAssets: number
    sourceLagAssets: number
    staleAssets: number
    horizons: Record<string, {
      validatedAssets: number
      nestedValidatedAssets: number
      nestedQualifiedAssets: number
      nestedRecentStableAssets: number
      fullSampleQualifiedAssets: number
      qualifiedAssets: number
      researchForecastAssets: number
      championModels: Record<AssetCycleStateForecastModel, number>
      blockedReasonCounts: Record<string, number>
    }>
  }
  governance: {
    publicationStatus: PublicationStatus
    allowed: string[]
    notAllowed: string[]
  }
  clockComparison: {
    status: string
    publicationClock: string
    referenceClock: string
    minimumCommonObservations: number
    rule: string
    horizons: Record<string, {
      assetsCompared: number
      commonObservationsMedian: number | null
      commonWindowStart: string | null
      commonWindowEnd: string | null
      asynchronous: {
        directionAccuracyMedian: number | null
        brierMedian: number | null
        maeMedian: number | null
        oosR2Median: number | null
        publicationQualifiedAssets: number
      }
      synchronous: {
        directionAccuracyMedian: number | null
        brierMedian: number | null
        maeMedian: number | null
        oosR2Median: number | null
        publicationQualifiedAssets: number
      }
      asynchronousBetterAssets: {
        directionAccuracy: number
        brier: number
        mae: number
        oosR2: number
      }
    }>
  }
  caveat: string
  assets: AssetCycleStateForecastRow[]
}

export interface AssetConditionalForecast {
  assetId: string
  name: string
  category: string
  confidence: string
  oosR2: number | null
  horizonAssociationImpact: Record<string, number | null>
  path: Array<{
    date: string
    phaseMixAnnReturn: number
    phaseMixAnnVol: number
    c4AssociationMonthly: number
  }>
  status: PublicationStatus
  caveat: string
}

export interface ForecastExtensionData {
  meta: Record<string, any>
  modelSummary: Array<Record<string, any>>
  qualifiedModels: string[]
  history: Array<Record<string, any>>
  forecast: Array<Record<string, any>>
  phaseWindows: Array<Record<string, any>>
  eligibility: Record<string, string>
  assetConditionalForecasts: AssetConditionalForecast[]
}

export interface AuditData {
  meta: Record<string, string>
  governance: { cycles: CyclePolicy[] }
  sources: Array<Record<string, string>>
  c2C3Sources?: Array<{
    name: string
    coverage: string
    role: string
    url: string
    cache: string
    cacheUpdated: string
    bytes: number
  }>
  proxyColumns?: Array<{
    column: string
    proxyFor: string
    fitStart: string
    fitEnd: string
    directThrough: string
    proxyStart: string
    proxyEnd: string
    proxyObservations: number
    r2: number
    method: string
    identity: string
  }>
  calibrations: Array<Record<string, string>>
}
