"""Causal preprocessing, aggregation, and governed cycle state estimation."""

from seven_cycle_platform.cycles.adaptive import (
    AdaptiveFilterConfig,
    AdaptiveHarmonicResult,
    DEFAULT_ADAPTIVE_FILTER_CONFIGS,
    adaptive_harmonic_state_filter,
)
from seven_cycle_platform.cycles.aggregation import (
    CategoryAggregationResult,
    aggregate_category_balanced,
)
from seven_cycle_platform.cycles.c2_regime import (
    build_c2_historical_dating,
    build_direct_c2_state,
    date_c2_turning_points,
    future_transition_target,
)
from seven_cycle_platform.cycles.discovery import (
    CategorySupport,
    DiscoveryEvidence,
    MethodAgreement,
    bootstrap_interval,
    bootstrap_period_interval,
    build_views,
    category_support,
    evaluate_period_candidate,
    method_agreement,
    red_noise_log_excess,
)
from seven_cycle_platform.cycles.engine import (
    CausalStateHistory,
    CycleComputationDiagnostics,
    SevenCycleEngine,
    compute_seven_cycle_states,
)
from seven_cycle_platform.cycles.model_version import (
    CycleModelVersion,
    ManualOverride,
    RecalibrationReason,
    RecalibrationStatus,
)
from seven_cycle_platform.cycles.phase import CyclePhase, phase_from_level_slope
from seven_cycle_platform.cycles.preprocess import (
    causal_transform,
    expanding_standardize,
    regularize_panel,
)
from seven_cycle_platform.cycles.recalibration import (
    RecalibrationPolicy,
    recalibrate_cycle,
)
from seven_cycle_platform.cycles.state_space import (
    HarmonicStateResult,
    harmonic_state_filter,
)
from seven_cycle_platform.cycles.vintage import (
    CYCLE_VINTAGE_COLUMNS,
    VintagePanels,
    VintageSelection,
    build_vintage_panels,
    read_vintage,
    reconstruct_cycle_phase_vintage,
    reconstruct_cycle_vintage,
    select_vintage_observations,
)

__all__ = [
    "AdaptiveFilterConfig",
    "AdaptiveHarmonicResult",
    "CategoryAggregationResult",
    "CategorySupport",
    "CYCLE_VINTAGE_COLUMNS",
    "CausalStateHistory",
    "CycleComputationDiagnostics",
    "CycleModelVersion",
    "CyclePhase",
    "DEFAULT_ADAPTIVE_FILTER_CONFIGS",
    "DiscoveryEvidence",
    "HarmonicStateResult",
    "ManualOverride",
    "MethodAgreement",
    "RecalibrationPolicy",
    "RecalibrationReason",
    "RecalibrationStatus",
    "SevenCycleEngine",
    "VintagePanels",
    "VintageSelection",
    "aggregate_category_balanced",
    "adaptive_harmonic_state_filter",
    "bootstrap_interval",
    "bootstrap_period_interval",
    "build_views",
    "build_c2_historical_dating",
    "build_direct_c2_state",
    "build_vintage_panels",
    "causal_transform",
    "category_support",
    "compute_seven_cycle_states",
    "evaluate_period_candidate",
    "expanding_standardize",
    "harmonic_state_filter",
    "date_c2_turning_points",
    "future_transition_target",
    "method_agreement",
    "phase_from_level_slope",
    "read_vintage",
    "recalibrate_cycle",
    "reconstruct_cycle_phase_vintage",
    "reconstruct_cycle_vintage",
    "red_noise_log_excess",
    "regularize_panel",
    "select_vintage_observations",
]
